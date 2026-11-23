"""A1945 (K10, #30877/#30878): Fragen-Topf – was an einer Frage hängt, blockiert oder nicht, Push gebündelt höchstens alle
fragen_takt_h Stunden (blockierend sofort), Frist fragen_frist_h: Lead und hängende Agenten einmal benachrichtigt."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime
import os
import tempfile
import time
import unittest

from amw import db, fragentopf, kern, wartegrund


def vor_h(stunden):
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=stunden)).strftime("%Y-%m-%dT%H:%M:%SZ")


class Topf(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.fid = kern.frage_neu(self.con, self.pid, "CC1", "entwickler", "Welche Farbe?", [("A", "blau"), ("B", "grün")], "A", "weil",
                                  geprueft="keine Treffer")
        self.a = kern.aufgabe_neu(self.con, self.pid, "TL", "Symbol malen", agent="CC1", rang=10)
        with db.schreiben(self.con):
            self.con.execute("UPDATE frage SET an = 'entwickler' WHERE id = ?", (self.fid,))   # nach der Frage-Prüfung beim Menschen
            wartegrund.anlegen(self.con, self.pid, "CC1", self.a, f"F{self.fid}")
            self.con.execute("UPDATE aufgabe SET status = 'wartet' WHERE id = ?", (self.a,))

    def push(self, stunden, ergebnis="gesendet", fid=None):
        schluessel = f"frage:{fid or self.fid}" if ergebnis == "offen" else f"frage:{900 + int(stunden)}"   # früherer Push: andere Frage
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "push_versand", projekt_id=self.pid, zeit_utc=vor_h(stunden), ereignis="frage",
                                schluessel=schluessel, titel="Neue Frage", text="", prioritaet=4, sicht="fragen",
                                ergebnis=ergebnis, geaendert_utc=vor_h(stunden))

    def faellig(self):
        return [dict(r) for r in self.con.execute("SELECT * FROM push_versand WHERE ergebnis = 'offen'")]

    def test_haengt_und_blockiert(self):
        self.assertEqual([x["aufgabe"] for x in fragentopf.haengt(self.con, self.pid, self.fid)], [self.a])
        self.assertTrue(fragentopf.blockiert(self.con, self.pid, self.fid))                    # CC1 hat sonst nichts
        anders = kern.aufgabe_neu(self.con, self.pid, "TL", "Etwas anderes", agent="CC1", rang=20)
        self.assertFalse(fragentopf.blockiert(self.con, self.pid, self.fid))                   # jetzt hat er Arbeit
        with db.schreiben(self.con):
            self.con.execute("UPDATE frage SET blockiert = 1 WHERE id = ?", (self.fid,))
        self.assertTrue(fragentopf.blockiert(self.con, self.pid, self.fid))                    # als blockierend gestellt
        self.assertEqual(fragentopf.naechste_startklare(self.con, self.pid, "CC1", {self.a})["id"], anders)

    def test_buendeln_nach_takt(self):
        kern.aufgabe_neu(self.con, self.pid, "TL", "Etwas anderes", agent="CC1", rang=20)   # nicht blockierend
        self.push(1)                                                                           # letzter Frage-Push vor 1 h
        neu = self.push(0, ergebnis="offen")
        self.assertEqual(fragentopf.zurueckhalten(self.con, self.pid, self.faellig(), time.time()), {neu})
        kern.projekt_einstellen(self.con, self.pid, "TL", fragen_takt_h=0)                   # 0 = sofort wie bisher
        self.assertEqual(fragentopf.zurueckhalten(self.con, self.pid, self.faellig(), time.time()), set())
        kern.projekt_einstellen(self.con, self.pid, "TL", fragen_takt_h=0.5)
        self.assertEqual(fragentopf.zurueckhalten(self.con, self.pid, self.faellig(), time.time()), set())   # Takt um

    def test_blockierende_geht_sofort(self):
        self.push(1)
        self.push(0, ergebnis="offen")
        self.assertEqual(fragentopf.zurueckhalten(self.con, self.pid, self.faellig(), time.time()), set())   # CC1 blockiert

    def test_frist_einmal_lead_und_agent(self):
        weiter = kern.aufgabe_neu(self.con, self.pid, "TL", "Etwas anderes", agent="CC1", rang=20)
        with db.schreiben(self.con):
            self.con.execute("UPDATE frage SET zeit_utc = ? WHERE id = ?", (vor_h(25), self.fid))
        self.assertEqual(fragentopf.runde(self.con), [f"F{self.fid}: Frist (1 hängen)"])
        an = lambda k: [r[0] for r in self.con.execute("SELECT n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id"   # noqa: E731
                                                         " WHERE e.agent = ? ORDER BY n.id", (k,))]
        self.assertIn(f"F{self.fid} seit 25 h ohne Antwort", an("TL"))
        self.assertIn(f"F{self.fid} seit 25 h offen – weiter mit A{weiter}", an("CC1"))
        self.assertEqual(fragentopf.runde(self.con), [])                                        # einmal je Frage
        with db.schreiben(self.con):
            self.con.execute("UPDATE frage SET zeit_utc = ? WHERE id = ?", (vor_h(2), self.fid))
        self.assertEqual(fragentopf.runde(self.con), [])


if __name__ == "__main__":
    unittest.main()
