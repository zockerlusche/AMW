"""Schlüssel je Projekt für den MCP-Connector (A1826): nur der Hash liegt auf dem PC (außerhalb von Repo/DB), nur der Mensch
erzeugt ihn (Terminal oder Workbench am PC), der Klartext erscheint genau einmal."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import aktionen, cli, db, kern, mcp_schluessel


class Schluessel(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad, "LOCALAPPDATA": os.path.join(self.ordner.name, "lad")})
        u.start()
        self.addCleanup(u.stop)
        os.environ.pop("AMW_AGENT", None)
        os.environ.pop("CLAUDE_CODE_MESSAGING_SOCKET", None)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")

    def cli(self, *args):
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(list(args) + ["--projekt", "Spiel"])
        return rc, aus.getvalue()

    def test_nur_hash_gespeichert_und_pruefung(self):
        s = mcp_schluessel.erzeugen("Spiel")
        with open(mcp_schluessel.pfad("Spiel"), encoding="utf-8") as f:
            self.assertNotIn(s, f.read())                                                    # Klartext nirgends gespeichert
        self.assertTrue(mcp_schluessel.pruefen("Spiel", s))
        self.assertFalse(mcp_schluessel.pruefen("Spiel", s + "x"))
        self.assertFalse(mcp_schluessel.pruefen("Anderes", s))
        neu = mcp_schluessel.erzeugen("Spiel")
        self.assertFalse(mcp_schluessel.pruefen("Spiel", s))                                 # erneuert: der alte gilt nicht mehr
        self.assertTrue(mcp_schluessel.pruefen("Spiel", neu))
        self.assertIn('"--projekt", "Spiel", "--von", "TL"', mcp_schluessel.eintrag("Spiel", "TL"))

    def test_nur_der_mensch_erzeugt(self):
        rc, aus = self.cli("mcp", "schluessel", "--von", "TL")
        self.assertTrue(rc)
        self.assertIn("nur der Mensch", aus)
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_MESSAGING_SOCKET": "x"}):         # aus einer Claude-Sitzung nie
            rc, aus = self.cli("mcp", "schluessel", "--von", "Entwickler")
        self.assertTrue(rc)
        self.assertFalse(mcp_schluessel.stand("Spiel")["da"])
        rc, aus = self.cli("mcp", "schluessel", "--von", "Entwickler")
        self.assertFalse(rc)
        self.assertIn("nur jetzt sichtbar", aus)
        with self.assertRaises(aktionen.Ungueltig):
            aktionen.ausfuehren(self.con, self.pid, "/api/mcp/schluessel", {"_benutzer": "x"}, kanal="netz")   # online nie
        r = aktionen.ausfuehren(self.con, self.pid, "/api/mcp/schluessel", {})
        self.assertTrue(mcp_schluessel.pruefen("Spiel", r["schluessel"]))


if __name__ == "__main__":
    unittest.main()
