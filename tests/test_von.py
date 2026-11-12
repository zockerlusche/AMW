"""Jeder schreibt nur als er selbst (1.34.0): in einer Agenten-Sitzung (AMW_AGENT) muss --von passen; Alias zählt als dieselbe
Kennung; die Brücke und das Terminal ohne AMW_AGENT bleiben wie bisher. 1.84.1: eine Claude-Sitzung ohne AMW_AGENT (Zwilling)
schreibt nicht als ein Agent, der in einer anderen lebenden Sitzung angemeldet ist."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import io
import json
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
        for k in ("AMW_PROJEKT", "AMW_AGENT", "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN"):
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


    def angemeldet(self, kennung, pipe):
        """Schlüsseldatei wie nach dem Anmelden (nur das Postfach zählt hier)."""
        from amw import hook
        datei = hook.schluessel_datei(self.con, self.pid, kennung)
        os.makedirs(os.path.dirname(datei), exist_ok=True)
        with open(datei, "w", encoding="utf-8") as f:
            json.dump({"pipe": pipe, "sitzung": "echt-1234"}, f)
        self.addCleanup(os.remove, datei)

    def zwilling(self, *args, lebt=True):
        """Befehl aus einer Claude-Sitzung ohne AMW_AGENT mit eigenem Postfach; die angemeldete Sitzung lebt (oder nicht)."""
        echt = {"pid": 4711, "art": "interactive", "sitzung": "echt-1234", "pipe": "rohr-echt"}
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_MESSAGING_SOCKET": "rohr-zwilling"}),                 mock.patch("amw.hook.claude_prozess", side_effect=lambda p: echt if lebt and p == "rohr-echt" else None):
            return self.cli(*args)

    def test_zwilling_schreibt_nicht_als_angemeldeter_agent(self):
        self.angemeldet("CC1", "rohr-echt")
        rc, aus = self.zwilling("posten", "--an", "CC3", "--art", "info", "--kurz", "ich bin CC1", "--von", "CC1")
        self.assertEqual(rc, 1)
        self.assertIn("in einer anderen Sitzung angemeldet", aus)
        self.assertIn("PID 4711", aus)
        self.assertIn("amw anmelden --von CC1 --ersetzen", aus)
        for befehl in (("lesen",), ("abmelden",), ("aufgabe", "neu", "--titel", "x")):
            self.assertEqual(self.zwilling(*befehl, "--von", "CC1")[0], 1, befehl)
        self.assertEqual(self.con.execute("SELECT count(*) FROM nachricht").fetchone()[0], 0)
        self.assertEqual(self.con.execute("SELECT count(*) FROM aufgabe").fetchone()[0], 0)

    def test_zwilling_darf_wenn_sitzung_tot_oder_eigene_oder_terminal(self):
        self.angemeldet("CC1", "rohr-echt")
        self.assertEqual(self.zwilling("posten", "--an", "CC3", "--art", "info", "--kurz", "a", "--von", "CC1", lebt=False)[0], 0)
        self.assertEqual(self.zwilling("posten", "--an", "TL", "--art", "info", "--kurz", "b", "--von", "CC3")[0], 0)
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_MESSAGING_SOCKET": "rohr-echt"}),                 mock.patch("amw.hook.claude_prozess", return_value={"pid": 4711, "art": "interactive", "sitzung": "echt-1234"}):
            self.assertEqual(self.cli("posten", "--an", "CC3", "--art", "info", "--kurz", "c", "--von", "CC1")[0], 0)
        with mock.patch("amw.hook.claude_prozess", return_value={"pid": 4711, "art": "interactive", "sitzung": "echt-1234"}):
            self.assertEqual(self.cli("posten", "--an", "CC3", "--art", "info", "--kurz", "d", "--von", "CC1")[0], 0)   # Terminal
        self.assertEqual(self.con.execute("SELECT count(*) FROM nachricht").fetchone()[0], 4)

    def test_zwilling_anmelden_prueft_selbst(self):
        self.angemeldet("CC1", "rohr-echt")
        echt = {"pid": 4711, "art": "interactive", "sitzung": "echt-1234", "pipe": "rohr-echt"}
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_MESSAGING_SOCKET": "rohr-zwilling", "CLAUDE_CODE_MESSAGING_TOKEN": "t"}),                 mock.patch("amw.hook.claude_prozess", side_effect=lambda p: echt if p == "rohr-echt" else None):
            rc, aus = self.cli("anmelden", "--von", "CC1")
        self.assertEqual(rc, 1)
        self.assertIn("ist schon angemeldet und diese Sitzung lebt noch", aus)


if __name__ == "__main__":
    unittest.main()
