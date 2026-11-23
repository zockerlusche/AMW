"""A1953 (TH155 Pkt 7, #30624/#30625): „macht gerade“ leitet die AMW ab – Lauf › Aufgabe › Meldung; amw taetigkeit ergänzt
nur; Quelle und Alter; ohne Puls seit 30 min veraltet; beendete Läufe und beendete Sitzungen nie."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime
import os
import tempfile
import unittest

from amw import db, gerade, kern, workbench


def vor(minuten):
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minuten)).strftime("%Y-%m-%dT%H:%M:%SZ")


class Gerade(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.gid = self.con.execute("SELECT id FROM agent WHERE kennung = 'CC1'").fetchone()[0]
        with db.schreiben(self.con):
            self.sid = db.einfuegen(self.con, "sitzung", agent_id=self.gid, claude_sitzung="s1", gestartet_utc=vor(90),
                                    letzter_puls_utc=vor(1))

    def aufgabe(self, titel, start=True):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel, agent="CC1")
        if start:
            with db.schreiben(self.con):
                self.con.execute("UPDATE aufgabe SET status = 'laeuft', begonnen_utc = ? WHERE id = ?", (vor(20), aid))
        return aid

    def lauf(self, status="laeuft", aid=None, beschreibung="Gesamtlauf"):
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="CC1", beschreibung=beschreibung, status=status,
                                angemeldet_utc=vor(10), start_utc=vor(9), aufgabe_id=aid)

    def angabe(self, text, minuten, aid=None):
        with db.schreiben(self.con):
            self.con.execute("UPDATE sitzung SET taetigkeit = ?, taetigkeit_utc = ?, aufgabe_id = ? WHERE id = ?",
                             (text, vor(minuten), aid, self.sid))

    def g(self):
        return gerade.ableiten(self.con, self.pid, "CC1")

    def test_lauf_vor_aufgabe_vor_meldung(self):
        self.assertIsNone(self.g())
        alt = kern.aufgabe_neu(self.con, self.pid, "TL", "Alte Sache", agent="CC1")
        kern._posten(self.con, self.pid, "CC1", "TL", "info", f"A{alt} fertig gebaut", "", aufgabe_id=alt)
        self.assertEqual((self.g()["quelle"], self.g()["aufgabe"]), ("meldung", alt))
        a = self.aufgabe("Gesamtlauf parallel")
        g = self.g()
        self.assertEqual((g["quelle"], g["aufgabe"], g["text"]), ("aufgabe", a, f"A{a} · Gesamtlauf parallel"))
        lid = self.lauf(aid=a, beschreibung="Messlauf 3")
        g = self.g()
        self.assertEqual((g["quelle"], g["aufgabe"]), ("lauf", a))
        self.assertEqual(g["text"], f"A{a} · Gesamtlauf parallel – L{lid} läuft: Messlauf 3")
        self.assertFalse(g["veraltet"])

    def test_a1989_fertige_aufgabe_aus_meldung_nie(self):                                   # #30969: „A1971 … (letzte Meldung)“
        a = kern.aufgabe_neu(self.con, self.pid, "TL", "Schon erledigt", agent="CC1")
        kern._posten(self.con, self.pid, "CC1", "TL", "info", f"A{a} ausgeliefert", "", aufgabe_id=a)
        self.assertEqual(self.g()["quelle"], "meldung")
        for status in ("fertig", "verworfen"):
            with db.schreiben(self.con):
                self.con.execute("UPDATE aufgabe SET status = ?, beleg = 'abc1234' WHERE id = ?", (status, a))
            self.assertIsNone(self.g(), status)
        b = kern.aufgabe_neu(self.con, self.pid, "TL", "Noch offen", agent="CC1")
        kern._posten(self.con, self.pid, "CC1", "TL", "info", f"A{b} wartet auf Prüfung", "", aufgabe_id=b)
        self.assertEqual((self.g()["quelle"], self.g()["aufgabe"]), ("meldung", b))

    def test_a1989_angabe_mit_beendetem_lauf_faellt_weg(self):                              # #30969: „L3096 Planer … seit 9 h“
        lid = self.lauf(beschreibung="Planer")
        self.angabe(f"L{lid} Planer prüfen", 5)
        self.assertEqual((self.g()["quelle"], self.g()["ergaenzung"]), ("lauf", f"L{lid} Planer prüfen"))
        for status in ("fertig", "abgebrochen"):
            with db.schreiben(self.con):
                self.con.execute("UPDATE lauf SET status = ? WHERE id = ?", (status, lid))
            self.assertIsNone(self.g(), status)                                                # auch nicht als alleinige Angabe
        a = self.aufgabe("Etwas anderes")
        self.angabe(f"L{lid} nachsehen", 1, aid=a)
        self.assertEqual((self.g()["quelle"], self.g()["ergaenzung"]), ("aufgabe", None))      # nicht als Ergänzung
        self.angabe("L99999 und Tests", 1, aid=a)                                              # unbekannter Lauf: bleibt
        self.assertEqual(self.g()["ergaenzung"], "L99999 und Tests")

    def test_beendeter_lauf_und_beendete_sitzung_nie(self):                                 # #30625: L3054 „seit 1 h“
        a = self.aufgabe("Etwas")
        self.lauf(status="fertig", aid=a)
        self.lauf(status="abgebrochen", aid=a)
        self.assertEqual(self.g()["quelle"], "aufgabe")
        with db.schreiben(self.con):
            self.con.execute("UPDATE sitzung SET zustand = 'beendet' WHERE id = ?", (self.sid,))
        self.assertIsNone(self.g())

    def test_eigene_angabe_ergaenzt_nur(self):
        a = self.aufgabe("A1966 Gesamtlauf")
        self.angabe("A1955 Bilder machen", 5, aid=None)                                     # nennt eine andere Aufgabe
        self.assertEqual((self.g()["quelle"], self.g()["ergaenzung"]), ("aufgabe", None))
        self.angabe("Messlauf 2 von 3", 5, aid=a)                                            # zur selben Aufgabe, jünger
        self.assertEqual(self.g()["ergaenzung"], "Messlauf 2 von 3")
        self.angabe("Messlauf 2 von 3", 60, aid=a)                                           # älter als der Beginn der Aufgabe
        self.assertIsNone(self.g()["ergaenzung"])
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'wartet' WHERE id = ?", (a,))
        self.angabe("Doku lesen", 3)
        g = self.g()                                                                          # nichts abgeleitet: die Angabe allein
        self.assertEqual((g["quelle"], g["text"]), ("angabe", "Doku lesen"))

    def test_veraltet_ohne_puls_seit_30_min(self):
        self.aufgabe("Etwas")
        self.assertFalse(self.g()["veraltet"])
        with db.schreiben(self.con):
            self.con.execute("UPDATE sitzung SET letzter_puls_utc = ?, status_utc = ?, taetigkeit_utc = NULL WHERE id = ?",
                             (vor(45), vor(31), self.sid))
        self.assertTrue(self.g()["veraltet"])
        self.assertIn("veraltet?", gerade.zeile(self.g()))
        f = workbench.gerade_felder(self.con, self.pid, "CC1")
        self.assertEqual((f["gerade_quelle"], f["gerade_veraltet"]), ("aufgabe", True))
        self.assertTrue(f["gerade_seit"])

    def test_aufgabe_start_ersetzt_angabe_zu_anderer_aufgabe(self):                         # Ursache „seit 2 h A1955“
        a = kern.aufgabe_neu(self.con, self.pid, "TL", "Erste", agent="CC1")
        b = kern.aufgabe_neu(self.con, self.pid, "TL", "Zweite", agent="CC1")
        kern.aufgabe_status(self.con, self.pid, "CC1", a, "start")
        self.assertEqual(self.con.execute("SELECT aufgabe_id FROM sitzung WHERE id = ?", (self.sid,)).fetchone()[0], a)
        kern.aufgabe_status(self.con, self.pid, "CC1", a, "wartet", auf="TL")
        kern.aufgabe_status(self.con, self.pid, "CC1", b, "start")
        s = self.con.execute("SELECT taetigkeit, aufgabe_id FROM sitzung WHERE id = ?", (self.sid,)).fetchone()
        self.assertEqual(s["aufgabe_id"], b)
        self.assertIn("Zweite", s["taetigkeit"])


if __name__ == "__main__":
    unittest.main()
