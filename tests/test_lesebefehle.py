"""Fehlende Lesebefehle für Leads (A1821, B2818 – nur über die Schnittstelle): Inhalt eines Dokuments, Agenten kompakt mit
Aufgabe und Wartegrund, erfasste Aussagen seit einem Zeitpunkt."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import cli, db, dokumente, kern, wissen

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")


class Lesebefehle(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "daten", "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")

    def cli(self, *args):
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(list(args) + ["--projekt", "Spiel", "--von", "TL"])
        return rc, aus.getvalue()

    def datei(self, name, inhalt):
        p = os.path.join(self.ordner.name, name)
        with open(p, "wb" if isinstance(inhalt, bytes) else "w", **({} if isinstance(inhalt, bytes) else {"encoding": "utf-8"})) as f:
            f.write(inhalt)
        return p

    def test_dokument_inhalt_text_und_bild(self):
        md = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("b.md", "# Bericht\nSpeicher gelb"), "Bericht", "bericht")
        dokumente.version(self.con, self.pid, "CC1", md, self.datei("b2.md", "# Bericht\nSpeicher grün"), "v2")
        _, aus = self.cli("dokument", "zeigen", str(md), "--inhalt")
        self.assertIn("--- Inhalt v2 (.md) ---", aus)
        self.assertIn("Speicher grün", aus)
        _, aus = self.cli("dokument", "zeigen", str(md), "--inhalt", "--fassung", "1")
        self.assertIn("Speicher gelb", aus)
        bild = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("s.png", PNG), "Standbild", "bild")
        _, aus = self.cli("dokument", "zeigen", str(bild), "--inhalt")
        self.assertIn("ist kein Text", aus)

    def test_agenten_mit_aufgabe_und_wartegrund(self):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Karte neu", "CC1")
        kern.aufgabe_status(self.con, self.pid, "CC1", aid, "wartet", auf="TL")
        _, aus = self.cli("agent", "liste")
        self.assertIn(f"Aufgabe: A{aid} wartet auf TL – Karte neu", aus)

    def test_wortlaut_seit(self):
        wissen.wortlaut_neu(self.con, self.pid, "TL", "alte Aussage", "chat-tl", "2026-11-14T10:00:00Z")
        w = wissen.wortlaut_neu(self.con, self.pid, "TL", "neue Aussage zur Karte", "chat-tl", "2026-11-16T09:30:00Z")
        _, aus = self.cli("wortlaut", "--liste", "--seit", "2026-11-15")
        self.assertIn(f"W{w}", aus)
        self.assertIn("neue Aussage zur Karte", aus)
        self.assertNotIn("alte Aussage", aus)
        _, aus = self.cli("wortlaut", "--liste", "--seit", "2026-11-16T09:31:00Z")
        self.assertIn("keine", aus)


if __name__ == "__main__":
    unittest.main()
