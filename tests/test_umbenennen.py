"""Tests für das Umbenennen von Agenten: neue Kennung überall, alte bleibt als Alias gültig."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from amw import betrieb, bruecke, cli, db, kern, wartegrund


class Umbenennen(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.pfad = os.path.join(self.ordner.name, "t.db")
        self.con = db.anlegen(self.pfad)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
            self.p2 = db.einfuegen(self.con, "projekt", name="Q", angelegt_utc=db.jetzt())
        for k, r in (("TL", "lead"), ("CC1", None), ("CC3", None)):
            kern.agent_neu(self.con, self.pid, k, rolle=r)
        kern.agent_neu(self.con, self.p2, "CC3")                       # gleiche Kennung im anderen Projekt bleibt
        self.n = kern.posten(self.con, self.pid, "CC3", "CC1", "info", "von CC3")[0]
        self.m = kern.posten(self.con, self.pid, "CC1", "CC3", "auftrag", "an CC3")[0]
        self.a = kern.aufgabe_neu(self.con, self.pid, "TL", "Engine", agent="CC3", pruefer="CC1")
        kern.aufgabe_status(self.con, self.pid, "CC3", self.a, "start")
        self.b = kern.aufgabe_neu(self.con, self.pid, "TL", "wartet auf die Engine", agent="CC1")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.b, "start")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.b, "wartet", auf="CC3")
        self.l = betrieb.lauf_start(self.con, self.pid, "CC3", "Build", speicher_frei=20)
        self.f = kern.frage_neu(self.con, self.pid, "CC3", "tl", "darf ich?", [])
        kern.halt(self.con, self.pid, "TL", "CC3", "kurz warten")

    def tearDown(self):
        self.con.close()
        self.ordner.cleanup()

    def cli(self, *args, agent=None):
        os.environ["AMW_DB"] = self.pfad
        if agent:
            os.environ["AMW_AGENT"] = agent
        aus = io.StringIO()
        try:
            with redirect_stdout(aus):
                rc = cli.main(["--projekt", "P", *args])
        finally:
            os.environ.pop("AMW_DB", None)
            os.environ.pop("AMW_AGENT", None)
        return rc, aus.getvalue()

    def wert(self, sql, *par):
        return self.con.execute(sql, par).fetchone()[0]

    def test_alles_umbenannt_alte_kennung_gilt_weiter(self):
        anzahl = kern.agent_umbenennen(self.con, self.pid, "TL", "CC3", "CCengine")
        for k in ("nachricht.von", "empfang.agent", "aufgabe.agent", "lauf.agent", "frage.von", "sperre.gilt_fuer",
                  "wartegrund.bezug"):
            self.assertIn(k, anzahl)
        self.assertEqual(self.wert("SELECT von FROM nachricht WHERE id = ?", self.n), "CCengine")
        self.assertEqual(self.wert("SELECT agent FROM empfang WHERE nachricht_id = ?", self.m), "CCengine")
        self.assertEqual(self.wert("SELECT kurz FROM nachricht WHERE id = ?", self.n), "von CC3")    # Freitext bleibt
        self.assertEqual(self.wert("SELECT agent FROM aufgabe WHERE id = ?", self.a), "CCengine")
        self.assertEqual(self.wert("SELECT pruefer FROM aufgabe WHERE id = ?", self.a), "CC1")
        self.assertEqual([g["bezug"] for g in wartegrund.offene(self.con, self.b)], ["CCengine"])
        self.assertEqual(self.wert("SELECT alias FROM agent WHERE kennung = 'CCengine'"), "CC3")
        self.assertEqual(self.wert("SELECT count(*) FROM agent WHERE projekt_id = ? AND kennung = 'CC3'", self.p2), 1)
        self.assertTrue(kern.halt_gilt(self.con, self.pid, "CCengine"))
        # alte Kennung: Absender, Empfänger, Aufgaben-Filter, Umgebungsvariable
        rc, aus = self.cli("posten", "--an", "CC3", "--art", "info", "--kurz", "hallo", agent="CC1")
        self.assertEqual((rc, aus.strip().split(" an ")[1]), (0, "CCengine"))
        rc, aus = self.cli("posten", "--an", "CC1", "--art", "info", "--kurz", "von alt", "--aufgabe", str(self.b), agent="CC3")
        self.assertEqual(rc, 0)
        self.assertEqual(self.wert("SELECT von FROM nachricht WHERE kurz = 'von alt'"), "CCengine")
        self.assertEqual(wartegrund.offene(self.con, self.b), [])           # CCengine hat zur Aufgabe geschrieben
        rc, aus = self.cli("aufgabe", "liste", "--agent", "CC3", "--von", "TL")
        self.assertIn(f"A{self.a}", aus)
        self.assertEqual(kern.empfaenger(self.con, self.pid, "CC3, CC1", "TL"), ["CCengine", "CC1"])
        rc, aus = self.cli("agent", "liste", "--von", "TL")
        self.assertIn("(früher CC3)", aus)

    def test_regeln(self):
        with self.assertRaises(kern.AmwFehler):                            # nur Lead/Entwickler
            kern.agent_umbenennen(self.con, self.pid, "CC1", "CC3", "CCengine")
        with self.assertRaises(kern.AmwFehler):                            # schon vergeben
            kern.agent_umbenennen(self.con, self.pid, "TL", "CC3", "CC1")
        for falsch in ("alle", "Entwickler", "3d", "mit leer", ""):
            with self.assertRaises(kern.AmwFehler):
                kern.agent_umbenennen(self.con, self.pid, "TL", "CC3", falsch)
        kern.agent_umbenennen(self.con, self.pid, "TL", "CC3", "CCengine")
        with self.assertRaises(kern.AmwFehler):                            # Alias nicht als neuer Agent
            kern.agent_neu(self.con, self.pid, "CC3")
        with self.assertRaises(kern.AmwFehler):                            # Alias nicht als neuer Name
            kern.agent_umbenennen(self.con, self.pid, "TL", "CC1", "CC3")
        kern.agent_umbenennen(self.con, self.pid, "TL", "CC3", "CCmotor")      # über den Alias, zweites Mal
        self.assertEqual(self.wert("SELECT alias FROM agent WHERE kennung = 'CCmotor'"), "CC3,CCengine")
        self.assertEqual(kern.kennung_heute(self.con, "CCengine", self.pid), "CCmotor")

    def test_lead_umbenennen_bruecke_und_cli(self):
        rc, aus = self.cli("agent", "umbenennen", "TL", "CClead", "--von", "Entwickler")
        self.assertEqual(rc, 0, aus)
        self.assertIn("TL heißt jetzt CClead", aus)
        self.assertTrue(kern.ist_lead(self.con, self.pid, "CClead"))
        rc, aus = self.cli("posten", "--an", "CC1", "--art", "info", "--kurz", "über die Brücke", "--von", bruecke.VON)
        self.assertEqual(rc, 0)
        self.assertEqual(self.wert("SELECT von FROM nachricht WHERE kurz = 'über die Brücke'"), "CClead")
        with db.schreiben(self.con):
            aid = self.wert("SELECT id FROM agent WHERE kennung = 'CClead'")
            db.einfuegen(self.con, "sitzung", agent_id=aid, gestartet_utc=db.jetzt())
        os.environ["AMW_DB"] = self.pfad
        try:
            bruecke.puls(taetigkeit="plant")                                 # VON = "TL" findet CClead
        finally:
            os.environ.pop("AMW_DB", None)
        self.assertEqual(self.wert("SELECT taetigkeit FROM sitzung WHERE agent_id = ?", aid), "plant")


if __name__ == "__main__":
    unittest.main()
