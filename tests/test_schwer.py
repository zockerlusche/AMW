"""Schwere Befehle erkennen und über die Warteschlange des Rechners schicken – die Entscheidung des Hooks, ohne Sitzung."""
import unittest

from amw import schwer


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


if __name__ == "__main__":
    unittest.main()
