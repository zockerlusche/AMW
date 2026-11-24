"""A2038 (D1531 §4, V3): Halt und Weiter – „--von Entwickler“ gilt nur im eigenen Terminal des Menschen, nie aus einer
Agenten-Sitzung; der Lead hält mit eigenem Namen an. Der Schreibweg /api/halt und /api/weiter nimmt nur die Workbench am PC
und die Online-Seite an (andere Kanäle, etwa ein Aufruf ohne Seite, werden abgewiesen); online gelten die Rollen wie bisher."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import aktionen, benutzer, db, kern

MENSCH = {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}          # wie im Terminal des Menschen


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Produkt", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")

    def cli(self, *args, env=None):
        from amw import cli
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {**MENSCH, **(env or {})}), contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "Produkt", *args])
        return rc, aus.getvalue()

    def halte(self):
        return self.con.execute("SELECT count(*) FROM sperre WHERE art = 'halt' AND aufgehoben_utc IS NULL").fetchone()[0]


class HaltImTerminal(Grund):
    def test_entwickler_aus_agenten_sitzung_abgewiesen(self):
        for env in ({"CLAUDECODE": "1"}, {"CLAUDE_CODE_MESSAGING_SOCKET": r"\\.\pipe\x"}, {"AMW_AGENT": "CC1"}):
            rc, aus = self.cli("halt", "--fuer", "alle", "--text", "Probe", "--von", "Entwickler", env=env)
            self.assertNotEqual(rc, 0, env)
            self.assertTrue("nicht aus einer Agenten-Sitzung" in aus or "--von Entwickler geht nicht" in aus, aus)
        self.assertEqual(self.halte(), 0)                                                          # nichts gesetzt

    def test_weiter_aus_agenten_sitzung_abgewiesen(self):
        kern.halt(self.con, self.pid, kern.ENTWICKLER, "alle", "vom Menschen")
        rc, aus = self.cli("weiter", "--fuer", "alle", "--von", "Entwickler", env={"CLAUDECODE": "1"})
        self.assertNotEqual(rc, 0)
        self.assertIn("nicht aus einer Agenten-Sitzung", aus)
        self.assertEqual(self.halte(), 1)                                                          # der Halt des Menschen bleibt

    def test_mensch_im_terminal_und_lead_aus_sitzung_erlaubt(self):
        rc, aus = self.cli("halt", "--fuer", "alle", "--text", "Pause", "--von", "Entwickler")
        self.assertEqual(rc, 0, aus)
        self.assertEqual(self.halte(), 1)
        rc, aus = self.cli("weiter", "--fuer", "alle", "--von", "TL", env={"CLAUDECODE": "1"})     # der Lead mit eigenem Namen
        self.assertEqual(rc, 0, aus)
        self.assertEqual(self.halte(), 0)
        rc, aus = self.cli("halt", "--fuer", "CC1", "--text", "kurz", "--von", "TL", env={"CLAUDECODE": "1"})
        self.assertEqual(rc, 0, aus)
        self.assertTrue(kern.halt_gilt(self.con, self.pid, "CC1"))

    def test_agent_ohne_lead_bleibt_abgewiesen(self):
        rc, aus = self.cli("halt", "--fuer", "alle", "--text", "x", "--von", "CC1", env={"CLAUDECODE": "1"})
        self.assertNotEqual(rc, 0, aus)
        self.assertEqual(self.halte(), 0)


class HaltUeberDieSeite(Grund):
    def test_nur_workbench_und_online_seite(self):
        for kanal in ("datei", "mcp", ""):
            with self.assertRaises(aktionen.Ungueltig, msg=kanal):
                aktionen.ausfuehren(self.con, self.pid, "/api/halt", {"fuer": "alle", "text": "x"}, kanal=kanal)
            with self.assertRaises(aktionen.Ungueltig, msg=kanal):
                aktionen.ausfuehren(self.con, self.pid, "/api/weiter", {"fuer": "alle"}, kanal=kanal)
        self.assertEqual(self.halte(), 0)
        aktionen.ausfuehren(self.con, self.pid, "/api/halt", {"fuer": "alle", "text": "am PC"}, kanal="seite")
        self.assertEqual(self.halte(), 1)
        aktionen.ausfuehren(self.con, self.pid, "/api/weiter", {"fuer": "alle"}, kanal="seite")
        self.assertEqual(self.halte(), 0)

    def test_online_wie_bisher_ab_bearbeiter(self):
        """Die Rollen bleiben, wie die Hilfe sie beschreibt (Bearbeiter: … Anhalten); ein Leser hält nicht an."""
        benutzer.neu(self.con, kern.ENTWICKLER, "les", rolle="leser", projekte=[self.pid])
        benutzer.neu(self.con, kern.ENTWICKLER, "bea", rolle="bearbeiter", projekte=[self.pid])
        with self.assertRaises(aktionen.Ungueltig):
            aktionen.ausfuehren(self.con, self.pid, "/api/halt", {"fuer": "alle", "text": "x", "_benutzer": "les"}, kanal="netz")
        self.assertEqual(self.halte(), 0)
        aktionen.ausfuehren(self.con, self.pid, "/api/halt", {"fuer": "alle", "text": "unterwegs", "_benutzer": "bea"}, kanal="netz")
        self.assertEqual(self.halte(), 1)
        aktionen.ausfuehren(self.con, self.pid, "/api/weiter", {"fuer": "alle", "_benutzer": "bea"}, kanal="netz")
        self.assertEqual(self.halte(), 0)

if __name__ == "__main__":
    unittest.main()
