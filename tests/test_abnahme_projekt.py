"""A1920 (TH160 F2, Mehrprojekt 2): Rückschritt-Tests (Regressions-Kurzsuite) und Zeitlimit der Abnahme je Projekt –
regression_befehl (Befehl | aus | leer = Vorgabe) und abnahme_frist_min (1–720, Vorgabe 30). Ohne Einstellung gilt die
Kurzsuite der AMW nur für das Projekt, das die AMW selbst ist; andere Projekte laufen ohne und bekommen das klar gemeldet."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import abnahme, cli, db, kern, pruefung_c


class Einstellungen(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad, "LOCALAPPDATA": os.path.join(self.ordner.name, "lad")})
        u.start()
        self.addCleanup(u.stop)
        os.environ.pop("AMW_AGENT", None)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.amw = db.einfuegen(self.con, "projekt", name="Leitstand", angelegt_utc=db.jetzt())   # Name egal
            self.spiel = db.einfuegen(self.con, "projekt", name="AMW", angelegt_utc=db.jetzt())       # heißt nur so
        for p in (self.amw, self.spiel):
            kern.agent_neu(self.con, p, "TL", rolle="lead")
            kern.agent_neu(self.con, p, "CC1")
        o = os.path.join(self.ordner.name, "amw-repo")
        os.makedirs(os.path.join(o, "amw"))
        for f in ("amw-cli.py", os.path.join("amw", "pruefung_c.py")):
            open(os.path.join(o, f), "w").close()
        kern.projekt_ordner_setzen(self.con, self.amw, o)
        s = os.path.join(self.ordner.name, "spiel")
        os.makedirs(s)
        kern.projekt_ordner_setzen(self.con, self.spiel, s)

    def test_vorgabe_je_projekt(self):
        a = pruefung_c.projekt_abnahme(self.con, self.amw)
        self.assertEqual(a, {"regression": pruefung_c.REGRESSION, "hinweis": None, "frist_s": abnahme.FRIST_S, "sprache": "auto"})
        s = pruefung_c.projekt_abnahme(self.con, self.spiel)
        self.assertEqual((s["regression"], s["hinweis"], s["frist_s"]), (None, pruefung_c.OHNE_REGRESSION, abnahme.FRIST_S))

    def test_eigener_befehl_aus_und_frist(self):
        kern.projekt_einstellen(self.con, self.spiel, "TL", regression_befehl="npm test -- --quick", abnahme_frist_min="90")
        s = pruefung_c.projekt_abnahme(self.con, self.spiel)
        self.assertEqual((s["regression"], s["hinweis"], s["frist_s"]), ("npm test -- --quick", None, 5400))
        self.assertEqual(pruefung_c.projekt_abnahme(self.con, self.amw)["frist_s"], abnahme.FRIST_S)    # anderes Projekt unberührt
        kern.projekt_einstellen(self.con, self.amw, kern.ENTWICKLER, regression_befehl="aus")
        a = pruefung_c.projekt_abnahme(self.con, self.amw)
        self.assertEqual((a["regression"], a["hinweis"]), (None, pruefung_c.AUS_REGRESSION))
        kern.projekt_einstellen(self.con, self.amw, "TL", regression_befehl="")                    # leer = wieder die Vorgabe
        self.assertEqual(pruefung_c.projekt_abnahme(self.con, self.amw)["regression"], pruefung_c.REGRESSION)

    def test_pruefung_der_werte(self):
        for falsch in ({"regression_befehl": "a\nb"}, {"regression_befehl": "x" * 501}, {"abnahme_frist_min": "0"},
                       {"abnahme_frist_min": "721"}):
            with self.assertRaises(kern.AmwFehler, msg=falsch):
                kern.projekt_einstellen(self.con, self.spiel, "TL", **falsch)
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.spiel, "CC1", regression_befehl="aus")                 # nur Lead oder Mensch

    def test_nicht_aus_einer_agenten_sitzung(self):
        for wert in ("regression_befehl=aus", "abnahme_frist_min=5"):
            aus = io.StringIO()
            with mock.patch.dict(os.environ, {"AMW_AGENT": "", "CLAUDECODE": "1", "CLAUDE_CODE_MESSAGING_SOCKET": ""}), \
                    contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
                rc = cli.main(["--projekt", "AMW", "--von", "Entwickler", "projekt", "einstellen", wert])
            self.assertNotEqual(rc, 0, wert)
            self.assertIn("nicht aus einer Agenten-Sitzung", aus.getvalue())
        self.assertEqual(pruefung_c.projekt_abnahme(self.con, self.spiel)["frist_s"], abnahme.FRIST_S)


if __name__ == "__main__":
    unittest.main()
