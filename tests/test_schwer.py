"""Schwere Befehle erkennen und über die Warteschlange des Rechners schicken – die Entscheidung des Hooks, ohne Sitzung."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import io
import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from amw import db, einrichtung, einstellungen, hook, kern, schwer


class Erkennen(unittest.TestCase):
    def test_was_als_schwer_gilt(self):
        for befehl, name in (
                ("python -X utf8 -m unittest discover -s tests", "Test-Suite"),
                ("cd F:/x && env -u A python -m unittest discover -s tests 2>&1 | tail -5", "Test-Suite"),
                ("pytest", "Test-Suite"), ("pytest tests/ -q", "Test-Suite"), ("dotnet test", "Test-Suite"), ("npm test", "Test-Suite"),
                ("npm run test", "Test-Suite"), ("python -m unittest tests.test_bedienung", "Browser-Tests"),
                ("npx playwright test", "Browser-Tests"), ("dotnet build -c Release", "Build"), ("npm run build", "Build"),
                ("godot --headless --path . --import", "Build"), ("git subtree split --prefix web -b web-1", "Web-Abzug")):
            self.assertEqual(schwer.erkennen(befehl), name, befehl)

    def test_was_frei_bleibt(self):
        for befehl in ("python -m unittest tests.test_kern", "python -m unittest tests.test_kern tests.test_rolle",       # einzelne Module
                       "python -m unittest tests.test_bedienung.Seite.test_leitstand", "pytest tests/test_a.py::test_x", "pytest -k schnell",
                       "git status", "dotnet --version", "npm install", "echo dotnet testen", "", None):
            self.assertIsNone(schwer.erkennen(befehl), befehl)

    def test_was_schon_ueber_die_warteschlange_laeuft(self):
        for befehl in ('amw lauf ausfuehren --beschreibung "Tests" -- python -m unittest discover -s tests',
                       "python F:/amw/amw-cli.py lauf ausfuehren --beschreibung T -- pytest", "amw lauf start --beschreibung Build --warten && dotnet build"):
            self.assertIsNone(schwer.erkennen(befehl), befehl)

    def test_eigene_muster_des_projekts_gehen_vor(self):
        eigene = [{"name": "Karten rechnen", "muster": r"\bkarten\.py\b"}, {"name": "kaputt", "muster": "("}, {"muster": "ohne-name"}, "kein dict"]
        self.assertEqual(schwer.erkennen("python werkzeug/karten.py --alle", eigene), "Karten rechnen")
        self.assertEqual(schwer.erkennen("dotnet test", eigene), "Test-Suite")                    # die mitgelieferten gelten weiter
        self.assertIsNone(schwer.erkennen("python werkzeug/anderes.py", eigene))


class Ersatz(unittest.TestCase):
    def test_einfacher_befehl_bleibt_wie_er_ist(self):
        self.assertEqual(schwer.ersatz("python -m unittest discover -s tests", "Test-Suite"),
                         'amw lauf ausfuehren --beschreibung "Test-Suite" -- python -m unittest discover -s tests')

    def test_verketteter_befehl_als_eine_befehlszeile(self):
        self.assertEqual(schwer.ersatz('cd "F:/a b" && pytest | tail -3', "Test-Suite", amw="python F:/amw/amw-cli.py"),
                         'python F:/amw/amw-cli.py lauf ausfuehren --beschreibung "Test-Suite" -- "cd \\"F:/a b\\" && pytest | tail -3"')


class Entscheidung(unittest.TestCase):
    def eingabe(self, befehl, werkzeug="Bash", art="PreToolUse"):
        return {"hook_event_name": art, "tool_name": werkzeug, "tool_input": {"command": befehl}, "session_id": "s"}

    def test_schwerer_befehl_wird_abgewiesen_mit_ersatz(self):
        r = schwer.entscheide(self.eingabe("python -m unittest discover -s tests"))["hookSpecificOutput"]
        self.assertEqual((r["hookEventName"], r["permissionDecision"]), ("PreToolUse", "deny"))
        self.assertIn('amw lauf ausfuehren --beschreibung "Test-Suite" -- python -m unittest discover -s tests', r["permissionDecisionReason"])
        self.assertIn("Warteschlange des Rechners", r["permissionDecisionReason"])
        self.assertIsNotNone(schwer.entscheide(self.eingabe("dotnet build", werkzeug="PowerShell")))

    def test_alles_andere_bleibt_unberuehrt(self):
        self.assertIsNone(schwer.entscheide(self.eingabe("git status")))
        self.assertIsNone(schwer.entscheide(self.eingabe("pytest", werkzeug="Read")))                 # nur Befehle der Shell
        self.assertIsNone(schwer.entscheide(self.eingabe("pytest", art="PostToolUse")))
        self.assertIsNone(schwer.entscheide({"hook_event_name": "PreToolUse", "tool_name": "Bash"}))   # ohne Befehl
        self.assertIsNone(schwer.entscheide(self.eingabe('amw lauf ausfuehren --beschreibung "T" -- pytest')))   # der Ersatz selbst geht durch


class Einbau(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        umgebung = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db"), "LOCALAPPDATA": self.ordner.name,
                                                "AMW_PROJEKT": "P", "AMW_AGENT": "A"})
        umgebung.start()
        self.addCleanup(umgebung.stop)
        self.con = db.anlegen()
        self.addCleanup(lambda: self.con.close())
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "A")

    def eingabe(self, befehl):
        return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": befehl}, "session_id": "s-1"}

    def test_eintrag_fuer_die_agenten_ordner(self):
        soll = einrichtung.hook_einstellungen()["hooks"]["PreToolUse"]
        self.assertEqual(soll[0]["matcher"], "^(Bash|PowerShell)$")
        befehl = soll[0]["hooks"][0]["command"]
        self.assertIn("amw-hook.py", befehl)                                       # daran erkennt „entfernen“ die Einträge der AMW
        self.assertNotIn("async", soll[0]["hooks"][0])                             # er muss vor dem Befehl antworten

    def test_fehlende_datei_sperrt_nichts(self):
        """Rückgabewert 2 hieße für diesen Hook „sperren“ – und genau den liefert Python, wenn es die Datei nicht findet."""
        ohne = subprocess.run([einrichtung.pythonw().replace("pythonw.exe", "python.exe"), os.path.join(self.ordner.name, "fehlt.py")],
                              capture_output=True)
        self.assertEqual(ohne.returncode, 2)                                       # so wäre es ohne die Absicherung
        befehl = einrichtung.befehl_sicher("amw-hook.py").replace("amw-hook.py", "gibt-es-nicht.py")
        sicher = subprocess.run(befehl, shell=True, input="{}", text=True, capture_output=True)
        self.assertEqual((sicher.returncode, sicher.stdout), (0, ""))

    def test_hook_weist_ab_und_nennt_den_befehl_dieser_installation(self):
        antwort = hook.schwere_befehle(self.eingabe("python -m unittest discover -s tests"))
        grund = antwort["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn(f'{kern.BEFEHL} lauf ausfuehren --beschreibung "Test-Suite" -- python -m unittest discover -s tests', grund)
        self.assertIsNone(hook.schwere_befehle(self.eingabe("git status")))

    def test_schalter_am_pc_und_eigene_muster_des_projekts(self):
        self.assertIsNone(hook.schwere_befehle(self.eingabe("python karten.py")))
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, schwere_befehle=[{"name": "Karten rechnen", "muster": r"karten\.py"}])
        self.assertIn("Karten rechnen", hook.schwere_befehle(self.eingabe("python karten.py"))["hookSpecificOutput"]["permissionDecisionReason"])
        einstellungen.speichern({"lauf_hook": False})                             # abgeschaltet: nichts wird abgewiesen
        self.assertIsNone(hook.schwere_befehle(self.eingabe("python karten.py")))
        self.assertIsNone(hook.schwere_befehle(self.eingabe("dotnet test")))
        einstellungen.speichern({"lauf_hook": True})
        for falsch in ([{"name": "x", "muster": "("}], [{"name": "", "muster": "a"}], [{"name": "x", "muster": "a"}] * 21, "kein Muster"):
            with self.assertRaises(kern.AmwFehler):
                kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, schwere_befehle=falsch)
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, schwere_befehle=[])                # leer: Einstellung entfällt
        self.assertNotIn("schwere_befehle", json.loads(self.con.execute("SELECT einstellungen FROM projekt").fetchone()[0]))

    def test_einstieg_antwortet_mit_json_und_endet_immer_mit_null(self):
        for befehl, erwartet in (("dotnet build", "deny"), ("git status", None)):
            aus = io.StringIO()
            with mock.patch("sys.stdin", io.StringIO(json.dumps(self.eingabe(befehl)))), mock.patch("sys.stdout", aus):
                self.assertEqual(hook.main(), 0)
            if erwartet:
                self.assertEqual(json.loads(aus.getvalue())["hookSpecificOutput"]["permissionDecision"], erwartet)
            else:
                self.assertEqual(aus.getvalue(), "")
        aus = io.StringIO()                                                        # kaputte Datenbank: der Befehl läuft, nichts wird gesperrt
        with mock.patch("sys.stdin", io.StringIO(json.dumps(self.eingabe("git status")))), mock.patch("sys.stdout", aus), \
                mock.patch.object(hook, "schwere_befehle", side_effect=RuntimeError("kaputt")):
            self.assertEqual((hook.main(), aus.getvalue()), (0, ""))
        with open(hook.hook_fehler_pfad(), encoding="utf-8") as f:                  # … und der Fehler steht im Protokoll
            self.assertIn("RuntimeError: kaputt", f.read())


if __name__ == "__main__":
    unittest.main()
