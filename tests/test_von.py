"""Jeder schreibt nur als er selbst (1.34.0): in einer Agenten-Sitzung (AMW_AGENT) muss --von passen; Alias zählt als dieselbe
Kennung; die Brücke und das Terminal ohne AMW_AGENT bleiben wie bisher."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from amw import bruecke, cli, db, kern


class Von(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.addCleanup(self.ordner.cleanup)
        umgebung = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        umgebung.start()
        self.addCleanup(umgebung.stop)
        for k in ("AMW_PROJEKT", "AMW_AGENT"):
            os.environ.pop(k, None)
        self.con = db.anlegen()
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        for k, r in (("TL", "lead"), ("CC1", None), ("CC3", None)):
            kern.agent_neu(self.con, self.pid, k, rolle=r)

    def cli(self, *args, sitzung=None):
        aus, fehler = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_AGENT": sitzung} if sitzung else {}), redirect_stdout(aus), redirect_stderr(fehler):
            rc = cli.main(list(args) + ["--projekt", "P"])
        return rc, aus.getvalue() + fehler.getvalue()

    def test_fremdes_von_in_einer_sitzung_abgelehnt(self):
        rc, aus = self.cli("posten", "--an", "CC3", "--art", "info", "--kurz", "ich bin der TL", "--von", "TL", sitzung="CC1")
        self.assertEqual(rc, 1)
        self.assertIn("Du bist CC1", aus)
        self.assertEqual(self.con.execute("SELECT count(*) FROM nachricht").fetchone()[0], 0)
        rc, aus = self.cli("posten", "--an", "CC3", "--art", "info", "--kurz", "Entwickler spielen", "--von", "Entwickler",
                           sitzung="CC1")
        self.assertEqual(rc, 1)

    def test_eigenes_von_und_ohne_von(self):
        self.assertEqual(self.cli("posten", "--an", "CC3", "--art", "info", "--kurz", "a", "--von", "CC1", sitzung="CC1")[0], 0)
        self.assertEqual(self.cli("posten", "--an", "CC3", "--art", "info", "--kurz", "b", sitzung="CC1")[0], 0)
        von = [r[0] for r in self.con.execute("SELECT von FROM nachricht ORDER BY id")]
        self.assertEqual(von, ["CC1", "CC1"])

    def test_alter_name_gilt_als_derselbe(self):
        kern.agent_umbenennen(self.con, self.pid, "TL", "CC1", "CCdesign")
        self.assertEqual(self.cli("posten", "--an", "CC3", "--art", "info", "--kurz", "c", "--von", "CCdesign", sitzung="CC1")[0], 0)
        self.assertEqual(self.cli("posten", "--an", "CC3", "--art", "info", "--kurz", "d", "--von", "CC1", sitzung="CCdesign")[0], 0)

    def test_terminal_ohne_sitzung_und_bruecke_wie_bisher(self):
        self.assertEqual(self.cli("posten", "--an", "CC3", "--art", "info", "--kurz", "e", "--von", "TL")[0], 0)
        with tempfile.TemporaryDirectory() as eingang, mock.patch.dict(os.environ, {"AMW_AGENT": "CC1"}):
            args = bruecke.argumente({"befehl": "posten", "an": "CC3", "art": "info", "kurz": "f"}, eingang, projekt="P")
            rc, aus, fehler = bruecke.ausfuehren(args)                 # Brücke setzt --von selbst (TL)
        self.assertEqual((rc, fehler), (0, ""))
        self.assertEqual([r[0] for r in self.con.execute("SELECT von FROM nachricht ORDER BY id")], ["TL", "TL"])


if __name__ == "__main__":
    unittest.main()
