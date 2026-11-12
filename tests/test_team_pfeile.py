"""Team-Baum 1.66.0: wer auf wen wartet (Pfeile) und Platz in der gemeinsamen Warteschlange des Rechners – am PC mit
fremdem Projekt und Agent, online ohne."""
import datetime
import os
import tempfile
import unittest

from amw import abgleich, betrieb, db, kern, workbench


class TeamPfeile(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        alt = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self.ordner.name                   # keine echten Einstellungen dieses PCs
        self.addCleanup(lambda: os.environ.__setitem__("LOCALAPPDATA", alt) if alt else os.environ.pop("LOCALAPPDATA", None))
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Werkstatt", angelegt_utc=db.jetzt())
            self.fremd = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        for k in ("CC1", "CC2"):
            kern.agent_neu(self.con, self.pid, k)
        kern.agent_neu(self.con, self.fremd, "G1")
        t = lambda m: (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with db.schreiben(self.con):
            self.fremd_lauf = db.einfuegen(self.con, "lauf", projekt_id=self.fremd, agent="G1", beschreibung="Kacheln", status="laeuft",
                                           angemeldet_utc=t(-30), start_utc=t(-20), erwartet_min=40, braucht_gb=1, gpu=1, schwer=1)
            self.mein = db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="CC2", beschreibung="Bilder", status="angemeldet",
                                     angemeldet_utc=t(-5), erwartet_min=10, braucht_gb=1, gpu=1, schwer=1)
            aid = db.einfuegen(self.con, "aufgabe", projekt_id=self.pid, titel="Texturen", agent="CC2", status="wartet", einstufung="aktiv",
                               angelegt_utc=db.jetzt(), angelegt_von="TL")
            db.einfuegen(self.con, "wartegrund", projekt_id=self.pid, aufgabe_id=aid, art="agent", bezug="CC1", angelegt_utc=db.jetzt(), angelegt_von="CC2")
            db.einfuegen(self.con, "wartegrund", projekt_id=self.pid, aufgabe_id=aid, art="frage", bezug="F9", angelegt_utc=db.jetzt(), angelegt_von="CC2")

    def cc2(self, d):
        return next(a for a in d["agenten"] if a["kennung"] == "CC2")

    def test_am_pc_mit_fremdem_projekt_und_agent(self):
        a = self.cc2(workbench.daten_start(self.con, self.pid))
        self.assertEqual(a["wartet_auf"], ["CC1"])                                              # Frage F9 ist kein Pfeil
        wp = a["warteplatz"]
        self.assertEqual((wp["lauf"], wp["platz"], wp["von"]), (self.mein, 1, 1))
        self.assertEqual(wp["auf"], [{"lauf": self.fremd_lauf, "projekt": "Spiel", "agent": "G1", "laeuft": True}])
        self.assertIn("belegt die Grafikkarte", wp["grund"])

    def test_online_ohne_namen_fremder_projekte(self):
        start = abgleich.ansichten(self.con, self.pid)["/api/start"]
        wp = self.cc2(start)["warteplatz"]
        self.assertEqual(wp["auf"][0]["projekt"], None)
        self.assertEqual(wp["auf"][0]["agent"], None)
        self.assertIsNone(wp["grund"])
        self.assertNotIn("Spiel", str(self.cc2(start)))
        self.assertIsNone(betrieb.warteposition(self.con, self.pid, self.con.execute("SELECT * FROM lauf WHERE id = ?", (self.fremd_lauf,)).fetchone())["platz"])


if __name__ == "__main__":
    unittest.main()
