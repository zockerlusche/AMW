"""A2039 (D1531 §6/§7, V11): Einen Agenten legt nur der Lead oder der Mensch an (bisher nur für einen neuen Lead geprüft);
den Dienst startet nur der Mensch, der Lead oder die AMW selbst (Release-Kette) neu – kein beliebiger Agent aus seiner Sitzung."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import db, einrichtung, kern

MENSCH = {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}          # wie im Terminal des Menschen
SITZUNG = {"CLAUDECODE": "1"}


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

    def agenten(self):
        return sorted(r[0] for r in self.con.execute("SELECT kennung FROM agent WHERE projekt_id = ?", (self.pid,)))


class AgentNeu(Grund):
    def test_coder_legt_keinen_agenten_an(self):
        rc, aus = self.cli("agent", "neu", "CC7", "--von", "CC1", env=SITZUNG)
        self.assertNotEqual(rc, 0)
        self.assertIn("Einen Agenten anlegen: nur der Lead oder der Mensch", aus)
        self.assertEqual(self.agenten(), ["CC1", "TL"])

    def test_entwickler_aus_agenten_sitzung_abgewiesen(self):
        rc, aus = self.cli("agent", "neu", "CC7", "--von", "Entwickler", env=SITZUNG)
        self.assertNotEqual(rc, 0)
        self.assertIn("nicht aus einer Agenten-Sitzung", aus)
        self.assertEqual(self.agenten(), ["CC1", "TL"])

    def test_mensch_und_lead_legen_an(self):
        rc, aus = self.cli("agent", "neu", "CC7", "--von", "Entwickler")
        self.assertEqual(rc, 0, aus)
        rc, aus = self.cli("agent", "neu", "CC8", "--von", "TL", env=SITZUNG)
        self.assertEqual(rc, 0, aus)
        self.assertEqual(self.agenten(), ["CC1", "CC7", "CC8", "TL"])

    def test_neuer_lead_wie_bisher(self):
        rc, aus = self.cli("agent", "neu", "CC9", "--rolle", "lead", "--von", "CC1", env=SITZUNG)
        self.assertNotEqual(rc, 0)
        self.assertIn("Einen Lead anlegen: nur der Lead oder der Mensch", aus)


class DienstNeustart(Grund):
    def neustart(self, *args, env=None):
        """Ruft `dienst neustart` auf, ohne den echten Dienst anzufassen: (rc, Ausgabe, ob PowerShell lief)."""
        lief = []
        with mock.patch.object(einrichtung, "fremde_aufgabe", return_value=None), \
                mock.patch.object(einrichtung, "powershell", side_effect=lambda *_: lief.append(1) or (0, "Dienst neu gestartet")):
            rc, aus = self.cli("dienst", "neustart", *args, env=env)
        return rc, aus, bool(lief)

    def test_coder_aus_sitzung_abgewiesen(self):
        for args, env in ((("--von", "CC1"), SITZUNG), ((), {**SITZUNG, "AMW_AGENT": "CC1"}), (("--von", "Entwickler"), SITZUNG)):
            rc, aus, lief = self.neustart(*args, env=env)
            self.assertNotEqual(rc, 0, (args, env))
            self.assertIn("nicht aus einer Agenten-Sitzung", aus)
            self.assertFalse(lief, (args, env))

    def test_mensch_lead_und_kette_erlaubt(self):
        for args, env in (((), None), (("--von", "TL"), SITZUNG), (("--von", "AMW"), SITZUNG)):
            rc, aus, lief = self.neustart(*args, env=env)
            self.assertEqual(rc, 0, (args, env, aus))
            self.assertTrue(lief, (args, env))


if __name__ == "__main__":
    unittest.main()
