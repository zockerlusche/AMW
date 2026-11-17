"""Abnahme durch die AMW (A1846, M50 S3): gesperrte Pfade je Pfadart inkl. test-schreiben, Abnahme im Job-Objekt mit Zeitlimit
(hängender Test samt Kind beendet), Rot-vor-Bau und Diff-Tor an Beispielzweigen, Markerdatei schützt vor falschem Löschen."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from amw import abnahme, platz

OHNE = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PY = f'"{sys.executable}"'


def g(ordner, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", ordner, *args], check=True, capture_output=True,
                          text=True, creationflags=OHNE).stdout.strip()


def lebt(pid):
    """Läuft der Prozess noch? (Windows: OpenProcess + GetExitCodeProcess, nie os.kill – das würde ihn beenden.)"""
    if os.name != "nt":
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            pass
        return os.path.exists(f"/proc/{pid}")
    import ctypes
    k = ctypes.WinDLL("kernel32")
    h = k.OpenProcess(0x1000, False, pid)                  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    k.GetExitCodeProcess(h, ctypes.byref(code))
    k.CloseHandle(h)
    return code.value == 259                               # STILL_ACTIVE


class Pfade(unittest.TestCase):
    def test_gesperrt_je_pfadart(self):
        for p in (".claude/settings.json", ".git/config", "CLAUDE.md", "web/CLAUDE.md", "amw/auslieferung.py", "amw/abnahme.py",
                  "amw/benutzer.py", "amw/hook.py", "start.ps1", "tests/rundgang.py", "tests/abschotten.py", "pyproject.toml"):
            self.assertTrue(abnahme.gesperrt([p]), p)
            self.assertTrue(abnahme.gesperrt([p], abnahme.TEST_SCHREIBEN), p)        # fest: auch bei test-schreiben
        self.assertTrue(abnahme.gesperrt(["tests/test_neu.py"]))                     # Testdatei: gesperrt …
        self.assertFalse(abnahme.gesperrt(["tests/test_neu.py"], abnahme.TEST_SCHREIBEN))   # … außer bei test-schreiben
        for p in ("amw/cli.py", "web/hilfe/agenten.de.json", "doc/hilfe/agenten.md", "amw\\messung.py", "./amw/x.py"):
            self.assertFalse(abnahme.gesperrt([p]), p)

    def test_gross_klein_und_vollstaendig(self):
        """P242: Windows und Claude Code lesen Claude.md, .Claude/ … – die Liste gilt ohne Rücksicht auf Groß/Klein; dazu die
        Einstiege im Stammordner, Git-Einstellungen und verschachtelte .claude/.git."""
        for p in ("Claude.md", "TESTS/conftest.py", ".Claude/settings.json", "web/Claude.MD", "AMW/Auslieferung.py",
                  "amw-hook.py", "amw-statusline.py", "amw-mcp.py", "amw-cli.py", "start_dienst.pyw", "amw-tray.pyw",
                  ".gitignore", "web/.gitignore", ".gitattributes", "web/.claude/settings.json", "sub/.git/config", "amw/dienst.py"):
            self.assertTrue(abnahme.gesperrt([p], abnahme.TEST_SCHREIBEN), p)
        self.assertTrue(abnahme.im_bereich("WEB/hilfe/a.json", ["web/hilfe/"]))

    def test_startregel_bereiche(self):
        self.assertTrue(abnahme.startregel(["amw/"]))                                 # enthält Auslieferung, Rechte …
        self.assertTrue(abnahme.startregel(["tests/"], abnahme.TEST_SCHREIBEN))       # enthält Testskripte (fest)
        self.assertTrue(abnahme.startregel([".claude/"]))
        self.assertFalse(abnahme.startregel(["web/hilfe/", "amw/messung.py"]))
        self.assertTrue(abnahme.startregel(["tests/test_neu.py"]))
        self.assertFalse(abnahme.startregel(["tests/test_neu.py"], abnahme.TEST_SCHREIBEN))

    def test_im_bereich(self):
        self.assertTrue(abnahme.im_bereich("web/hilfe/a.json", ["web/hilfe/"]))
        self.assertTrue(abnahme.im_bereich("amw/messung.py", ["amw/messung.py"]))
        self.assertTrue(abnahme.im_bereich("web/hilfe/a.de.json", ["web/hilfe/*.json"]))
        self.assertFalse(abnahme.im_bereich("web/inc/x.php", ["web/hilfe/"]))
        self.assertFalse(abnahme.im_bereich("amw/messung2.py", ["amw/messung.py"]))


class Ausfuehren(unittest.TestCase):
    def test_zeitlimit_beendet_den_ganzen_baum(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as o:
            pidfile = os.path.join(o, "kind.pid")
            prog = ("import subprocess, sys, time; "
                    f"k = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], creationflags={OHNE}); "
                    f"open(r'{pidfile}', 'w').write(str(k.pid)); time.sleep(120)")
            t0 = time.monotonic()
            r = abnahme.ausfuehren(f'{PY} -c "{prog}"', o, dict(os.environ), frist=4)
            self.assertTrue(r["zeitlimit"])
            self.assertLess(time.monotonic() - t0, 60)
            kind = int(open(pidfile).read())
            for _ in range(20):
                if not lebt(kind):
                    break
                time.sleep(0.25)
            self.assertFalse(lebt(kind), "Kindprozess läuft nach dem Zeitlimit weiter")

    def test_ohne_job_wird_nichts_ausgefuehrt(self):
        """P242: lässt sich der Prozess nicht ins Job-Objekt nehmen, läuft er nicht (er ist noch angehalten) – Fehler statt Lauf."""
        if os.name != "nt":
            self.skipTest("Job-Objekt nur unter Windows")
        from unittest import mock
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as o:
            marke = os.path.join(o, "lief.txt")
            with mock.patch.object(abnahme, "_in_job", return_value=False):
                r = abnahme.ausfuehren(f'{PY} -c "open(r\'{marke}\', \'w\').write(\'x\')"', o, dict(os.environ), 30)
            self.assertIn("nicht ins Job-Objekt", r["fehler"])
            self.assertIsNone(r["rc"])
            time.sleep(1)
            self.assertFalse(os.path.exists(marke), "der Befehl lief trotzdem")

    def test_gruen_und_rot(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as o:
            self.assertEqual(abnahme.ausfuehren(f'{PY} -c "print(1)"', o, dict(os.environ), 60)["rc"], 0)
            self.assertEqual(abnahme.ausfuehren(f'{PY} -c "import sys; sys.exit(3)"', o, dict(os.environ), 60)["rc"], 3)


@unittest.skipUnless(shutil.which("git"), "git fehlt")
class Beispielzweige(unittest.TestCase):
    """Ein kleines Projekt: wert.txt und eine Abnahme, die grün ist, wenn wert.txt „2“ enthält."""
    ABNAHME = f'{PY} -c "import sys; sys.exit(0 if open(\'wert.txt\').read().strip() == \'2\' else 1)"'

    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.repo = os.path.join(self.ordner.name, "projekt")
        os.makedirs(os.path.join(self.repo, "web"))
        g(self.repo, "init", "-q", "-b", "main")
        for name, inhalt in (("wert.txt", "1\n"), ("web/a.txt", "a\n")):
            with open(os.path.join(self.repo, name), "w") as f:
                f.write(inhalt)
        g(self.repo, "add", ".")
        g(self.repo, "commit", "-q", "-m", "basis")
        self.p = platz.pfade(os.path.join(self.ordner.name, "plaetze"), 1)
        self.basis = platz.vorbereiten(self.p, self.repo, "paket")["basis"]

    def schreiben(self, name, inhalt, commit=True):
        pfad = os.path.join(self.p["klon"], name)
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad, "w") as f:
            f.write(inhalt)
        if commit:
            g(self.p["klon"], "add", name)
            g(self.p["klon"], "commit", "-q", "-m", name)

    def test_rot_vor_bau(self):
        r = abnahme.rot_vor_bau(self.p, self.ABNAHME)
        self.assertTrue(r["ok"], r)                                                   # rot vorher: sie prüft etwas
        self.schreiben("wert.txt", "2\n")                                             # Stand, auf dem sie schon grün ist
        r = abnahme.rot_vor_bau(self.p, self.ABNAHME)
        self.assertFalse(r["ok"])
        self.assertIn("prüft nichts", r["grund"])
        self.assertTrue(abnahme.rot_vor_bau(self.p, self.ABNAHME, abnahme.TEST_SCHREIBEN)["ok"])
        self.assertTrue(abnahme.abnahme(self.p, self.ABNAHME)["gruen"])

    def test_diff_tor(self):
        self.assertFalse(abnahme.diff_tor(self.p["klon"], self.basis, ["web/"])["ok"])          # nichts geändert
        self.schreiben("web/a.txt", "neu\n")
        self.assertTrue(abnahme.diff_tor(self.p["klon"], self.basis, ["web/"])["ok"])
        self.schreiben("wert.txt", "2\n", commit=False)                                         # außerhalb, nicht committet
        r = abnahme.diff_tor(self.p["klon"], self.basis, ["web/"])
        self.assertEqual((r["ok"], r["ausserhalb"]), (False, ["wert.txt"]))
        g(self.p["klon"], "checkout", "--", "wert.txt")
        g(self.p["klon"], "mv", "wert.txt", "web/wert.txt")                                     # P242: Umbenennen aus dem Bereich heraus
        g(self.p["klon"], "commit", "-q", "-m", "mv")
        r = abnahme.diff_tor(self.p["klon"], self.basis, ["web/"])
        self.assertEqual((r["ok"], r["ausserhalb"]), (False, ["wert.txt"]))                     # der alte Name zählt mit
        g(self.p["klon"], "reset", "-q", "--hard", "HEAD~1")
        self.schreiben(".claude/settings.json", "{}", commit=False)                            # neu, gesperrt
        r = abnahme.diff_tor(self.p["klon"], self.basis, ["web/", ".claude/"])
        self.assertFalse(r["ok"])
        self.assertEqual(r["gesperrt"][0][0], ".claude/settings.json")

    def test_test_schreiben_neuer_test_rot_gegen_alten_stand(self):
        test = "tests/test_wert.py"
        self.schreiben(test, "import unittest\nclass T(unittest.TestCase):\n    def test_w(self):\n"
                             "        self.assertEqual(open('wert.txt').read().strip(), '2')\n")
        self.schreiben("wert.txt", "2\n")
        befehl = f"{PY} -m unittest {test.replace('/', '.')[:-3]}"
        self.assertTrue(abnahme.abnahme(self.p, befehl)["gruen"])                              # neuer Stand: grün
        r = abnahme.test_gegen_basis(self.p, befehl, self.basis, [test])
        self.assertTrue(r["ok"], r)                                                             # gegen den alten Code: rot
        self.assertEqual(open(os.path.join(self.p["klon"], "wert.txt")).read().strip(), "2")  # Stand wiederhergestellt
        self.assertTrue(abnahme.diff_tor(self.p["klon"], self.basis, ["tests/test_wert.py", "wert.txt"], abnahme.TEST_SCHREIBEN)["ok"])
        self.assertFalse(abnahme.diff_tor(self.p["klon"], self.basis, ["tests/test_wert.py", "wert.txt"])["ok"])   # sonst gesperrt

    def test_marker_schuetzt(self):
        os.remove(os.path.join(self.p["klon"], ".git", platz.MARKER))
        with self.assertRaises(platz.PlatzFehler):
            platz.zuruecksetzen(self.p)
        open(os.path.join(self.p["klon"], ".git", platz.MARKER), "w").close()
        os.remove(os.path.join(self.p["daten"], platz.MARKER))
        with open(os.path.join(self.p["daten"], "wichtig.txt"), "w") as f:
            f.write("x")
        with self.assertRaises(platz.PlatzFehler):
            platz.zuruecksetzen(self.p)
        self.assertTrue(os.path.exists(os.path.join(self.p["daten"], "wichtig.txt")))          # nichts gelöscht
        with self.assertRaises(platz.PlatzFehler):
            platz.zuruecksetzen(self.p, projektordner=os.path.dirname(self.p["klon"]))         # Platz im „Projektordner“


if __name__ == "__main__":
    unittest.main()
