"""A1926 (Mehrprojekt 8, D1304 v12 §5): Projekt-Schalter aus | probe | an – Probe an einer Kopie mit Zählprobe (Zeilen, Nummern,
Verweise), Bericht als Dokument; an nur nach bestandener Probe und nur der Mensch; aus: keine p-Starts, kein Gegenlesen;
nichts gelöscht."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from amw import cli, db, gegenlesen, kern, planung, schalter


class Schalter(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad, "LOCALAPPDATA": os.path.join(self.ordner.name, "lad")})
        u.start()
        self.addCleanup(u.stop)
        for k in ("AMW_AGENT", "AMW_PROJEKT"):
            os.environ.pop(k, None)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        self.pid = {}
        for name in ("GlassWorld", "Anderes"):
            with db.schreiben(self.con):
                self.pid[name] = db.einfuegen(self.con, "projekt", name=name, angelegt_utc=db.jetzt())
            kern.agent_neu(self.con, self.pid[name], "TL", rolle="lead")
            kern.agent_neu(self.con, self.pid[name], "CC1")
        g = self.pid["GlassWorld"]
        self.bogen = planung.bogen_neu(self.con, g, "TL", "Erster Bogen")
        self.a1 = kern.aufgabe_neu(self.con, g, "TL", "Eins", "CC1")
        self.a2 = kern.aufgabe_neu(self.con, g, "TL", "Zwei", "CC1")
        fremd = kern.aufgabe_neu(self.con, self.pid["Anderes"], "TL", "Fremd", "CC1")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET bogen_id = ? WHERE id = ?", (self.bogen, self.a1))
            db.einfuegen(self.con, "plan_ereignis", projekt_id=g, zeit_utc=db.jetzt(), von="TL", art="notiz", aufgabe_id=self.a2, text="x")
            db.einfuegen(self.con, "plan_ereignis", projekt_id=g, zeit_utc=db.jetzt(), von="TL", art="notiz", aufgabe_id=fremd,
                         text="Verweis auf ein anderes Projekt")

    def zeilen(self):
        return {t: self.con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("aufgabe", "plan_ereignis", "projekt", "bogen")}

    def test_zaehlprobe_und_bericht(self):
        g = self.pid["GlassWorld"]
        live = schalter.zaehlen(self.con, g)
        self.assertEqual(live["aufgabe"]["zeilen"], 2)
        self.assertEqual(live["aufgabe"]["verweise"]["bogen_id"], 1)
        self.assertEqual(live["plan_ereignis"]["fremd"]["aufgabe_id"], 1)                            # der Verweis nach außen
        vorher = self.zeilen()
        r = schalter.probe(self.con, g, "TL")
        self.assertTrue(r["bestanden"], r["unterschiede"])
        self.assertEqual(self.zeilen(), {**vorher, "plan_ereignis": vorher["plan_ereignis"] + 1})       # nichts gelöscht, ein Eintrag
        self.assertTrue(os.path.isfile(r["kopie"]))                                                    # die Sicherung bleibt
        k = sqlite3.connect(r["kopie"])
        try:
            self.assertEqual(sorted(x[0] for x in k.execute("SELECT id FROM aufgabe")), sorted([self.a1, self.a2]))   # Nummern bleiben
        finally:
            k.close()
        d = self.con.execute("SELECT titel FROM dokument WHERE id = ?", (r["dokument"],)).fetchone()
        self.assertEqual(d["titel"], "Probe Projekt-Schalter GlassWorld")
        self.assertEqual(r["stufe"], "an")                                                             # P406: ohne Eintrag bleibt an
        self.assertEqual(kern.projekt_schalter(self.con, g), "an")
        self.assertNotIn("schalter", json.loads(self.con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (g,)).fetchone()[0] or "{}"))

    def test_nur_aus_wird_zu_probe(self):
        """P406-Auflage: ohne Eintrag (wie die AMW) bleibt ein Projekt nach der Probe an; nur ein ausgeschaltetes wird probe."""
        g, o = self.pid["GlassWorld"], self.pid["Anderes"]
        self.assertEqual(schalter.probe(self.con, o, "TL")["stufe"], "an")
        schalter.umschalten(self.con, g, kern.ENTWICKLER, "aus")
        self.assertEqual(schalter.probe(self.con, g, "TL")["stufe"], "probe")
        self.assertEqual(kern.projekt_schalter(self.con, g), "probe")

    def test_unterschied_wird_gefunden(self):
        g = self.pid["GlassWorld"]
        live = schalter.zaehlen(self.con, g)
        kaputt = json.loads(json.dumps(live))
        kaputt["aufgabe"]["zeilen"] -= 1
        kaputt["aufgabe"]["verweise"]["bogen_id"] = 0
        d = schalter.vergleichen(live, kaputt)
        self.assertEqual([(t, w) for t, w, *_ in d], [("aufgabe", "zeilen"), ("aufgabe", "Verweise bogen_id")])
        self.assertIn("nicht bestanden", schalter.bericht("X", "k.db", live, d))
        self.assertEqual(schalter.vergleichen(live, live), [])

    def test_rechte_und_einschalten_nur_nach_probe(self):
        g = self.pid["GlassWorld"]
        with self.assertRaisesRegex(kern.AmwFehler, "Lead oder der Mensch"):
            schalter.probe(self.con, g, "CC1")
        with self.assertRaisesRegex(kern.AmwFehler, "nach einer bestandenen Probe"):
            schalter.umschalten(self.con, g, kern.ENTWICKLER, "an")
        schalter.umschalten(self.con, g, kern.ENTWICKLER, "aus")
        schalter.probe(self.con, g, "TL")
        with self.assertRaisesRegex(kern.AmwFehler, "nur der Mensch"):
            schalter.umschalten(self.con, g, "TL", "an")
        self.assertEqual(schalter.umschalten(self.con, g, kern.ENTWICKLER, "an"), ("probe", "an"))
        self.assertEqual(schalter.probe(self.con, g, "TL")["stufe"], "an")                             # eine neue Probe schaltet nicht ab
        self.assertEqual(schalter.umschalten(self.con, g, kern.ENTWICKLER, "aus"), ("an", "aus"))
        self.assertEqual(schalter.probe(self.con, g, "TL")["stufe"], "probe")
        with self.assertRaisesRegex(kern.AmwFehler, "amw projekt schalter"):
            kern.projekt_einstellen(self.con, g, "TL", schalter="an")                                  # nur über den Schalter

    def test_aus_kein_gegenlesen(self):
        g = self.pid["GlassWorld"]
        with mock.patch.dict(os.environ, {"AMW_GEGENLESEN_AUS": ""}), mock.patch.object(gegenlesen, "STARTER", side_effect=AssertionError):
            schalter.probe(self.con, g, "TL")
            schalter.umschalten(self.con, g, kern.ENTWICKLER, "aus")
            self.assertIsNone(gegenlesen.anstossen(self.con, g, 1, 1))

    def cli(self, *argv, sitzung=False):
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_AGENT": "", "CLAUDECODE": "1" if sitzung else "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}), \
                contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "GlassWorld", *argv])
        return rc, aus.getvalue()

    def test_cli(self):
        self.assertEqual(self.cli("--von", "Entwickler", "projekt", "schalter", "GlassWorld", "aus")[0], 0)
        rc, aus = self.cli("--von", "TL", "projekt", "schalter", "GlassWorld", "probe")
        self.assertEqual(rc, 0, aus)
        self.assertIn("Probe bestanden – Bericht D", aus)
        rc, aus = self.cli("--von", "Entwickler", "projekt", "schalter", "GlassWorld", "an", sitzung=True)
        self.assertNotEqual(rc, 0)
        self.assertIn("nur der Mensch im eigenen Terminal", aus)
        rc, aus = self.cli("--von", "TL", "projekt", "schalter", "GlassWorld", "an")
        self.assertNotEqual(rc, 0)
        rc, aus = self.cli("--von", "Entwickler", "projekt", "schalter", "GlassWorld", "an")
        self.assertEqual(rc, 0, aus)
        self.assertIn("GlassWorld: Schalter probe → an", aus)
        self.assertEqual(kern.projekt_schalter(self.con, self.pid["GlassWorld"]), "an")
        self.assertEqual(kern.projekt_schalter(self.con, self.pid["Anderes"]), "an")                    # anderes Projekt unberührt


if __name__ == "__main__":
    unittest.main()
