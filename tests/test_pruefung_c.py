"""Prüfung C (A1849, M50 S6a; D1258 v14 §6a.3): eigenes Prüf-Repo, nichts aus .git/config des Platzes, AMW committet als
AMW-Arbeiter, Diff-Tor + Geheimnis + nach außen, frischer Checkout mit minimaler Umgebung, Befundcodes, test-schreiben."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from amw import pruefung_c as c

OHNE = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PY = sys.executable.replace("\\", "/")


def g(ordner, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", ordner, *args], check=True, capture_output=True,
                          text=True, creationflags=OHNE).stdout.strip()


@unittest.skipUnless(shutil.which("git") and os.name == "nt", "git/Windows fehlt")
class PruefungC(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        o = self.ordner.name
        self.projekt = os.path.join(o, "projekt")
        os.makedirs(os.path.join(self.projekt, "lib"))
        os.makedirs(os.path.join(self.projekt, "tests"))
        self.schreiben(self.projekt, "lib/rechnen.py", "def plus(a, b):\n    return a - b\n")      # absichtlich falsch
        self.schreiben(self.projekt, "tests/__init__.py", "")
        self.schreiben(self.projekt, "tests/test_rechnen.py", "import unittest\nfrom lib.rechnen import plus\n\n\nclass T(unittest.TestCase):\n"
                       "    def test_plus(self):\n        self.assertEqual(plus(2, 2), 4)\n")
        self.schreiben(self.projekt, "lib/__init__.py", "")
        self.schreiben(self.projekt, ".gitignore", "*.log\n")
        g(o, "init", "-q", "-b", "main", self.projekt)
        g(self.projekt, "add", "-A")
        g(self.projekt, "commit", "-q", "-m", "basis")
        self.basis = g(self.projekt, "rev-parse", "HEAD")
        self.p = {"nr": 1, "klon": os.path.join(o, "platz1"), "daten": os.path.join(o, "platz1-daten"), "port": 8801}
        self.p.update(db=os.path.join(self.p["daten"], "amw.db"), lad=os.path.join(self.p["daten"], "lad"), tmp=os.path.join(self.p["daten"], "tmp"),
                      claude=os.path.join(self.p["daten"], "claude"))
        subprocess.run(["git", "clone", "-q", "--no-hardlinks", self.projekt, self.p["klon"]], check=True, capture_output=True, creationflags=OHNE)
        self.befehl = f"{PY} -X utf8 -m unittest tests.test_rechnen"

    def schreiben(self, wurzel, rel, text):
        pfad = os.path.join(wurzel, *rel.split("/"))
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def pruefen(self, bereiche=("lib/",), befehl=None, typ=None, frist=120):
        return c.pruefen(self.p, self.projekt, self.basis, 7, befehl or self.befehl, list(bereiche), typ, frist, regression=None)

    def reparieren(self):
        self.schreiben(self.p["klon"], "lib/rechnen.py", "def plus(a, b):\n    return a + b\n")

    def test_leer(self):
        self.assertEqual(self.pruefen()["code"], "C/leer")

    def test_gruen_amw_committet_als_arbeiter(self):
        self.reparieren()
        self.schreiben(self.p["klon"], "lib/notiz.log", "ignoriert\n")                            # .gitignore des Projekts gilt
        b = self.pruefen()
        self.assertIsNone(b["code"], b)
        self.assertEqual(b["geaendert"], ["lib/rechnen.py"])
        r = c.repo(self.p)
        log = subprocess.run(["git", f"--git-dir={r}", "log", "-1", "--format=%an <%ae>|%P", b["kopf"]], capture_output=True, text=True,
                             creationflags=OHNE).stdout.strip()
        self.assertEqual(log, f"AMW-Arbeiter <arbeiter@amw.invalid>|{self.basis}")
        self.assertEqual(subprocess.run(["git", f"--git-dir={r}", "rev-parse", "refs/heads/paket-A7"], capture_output=True, text=True,
                                        creationflags=OHNE).stdout.strip(), b["kopf"])
        self.assertEqual(g(self.p["klon"], "rev-parse", "HEAD"), self.basis)                     # der Klon selbst bleibt unberührt
        self.assertTrue(g(self.p["klon"], "status", "--porcelain"))
        self.assertEqual(b["abnahme"]["rc"], 0)
        self.assertFalse(os.path.normcase(b["abnahme"].get("ordner", "") or "").startswith(os.path.normcase(self.p["klon"])))

    def test_nichts_aus_git_config_des_platzes(self):
        """Steuerdateien im Platz (fsmonitor, Filter, Hooks) werden nie ausgeführt – die AMW nutzt ihr eigenes Prüf-Repo."""
        marke = os.path.join(self.ordner.name, "AUSGEFUEHRT.txt").replace("\\", "/")
        befehl = f'{PY} -c "open(r\'{marke}\', \'w\').write(\'x\')"'
        g(self.p["klon"], "config", "core.fsmonitor", befehl)
        g(self.p["klon"], "config", "filter.boese.clean", befehl)
        g(self.p["klon"], "config", "core.hooksPath", ".githaken")
        self.schreiben(self.p["klon"], ".gitattributes", "*.py filter=boese\n")
        for haken in ("pre-commit", "post-commit", "post-checkout", "reference-transaction"):
            self.schreiben(self.p["klon"], f".git/hooks/{haken}", f"#!/bin/sh\n{befehl}\n")
        self.reparieren()
        b = self.pruefen(bereiche=("lib/", ".gitattributes"))
        self.assertFalse(os.path.exists(marke), "Befehl aus der Konfiguration des Platzes wurde ausgeführt")
        self.assertEqual(b["code"], "C/diff")                                                    # .gitattributes ist gesperrt
        self.assertIn(".gitattributes", [x for x, _ in b["gesperrt"]])

    def test_verweise_nach_aussen_nie_eingesammelt(self):
        """P268: eine Junction (oder ein Hardlink) im Bereich zeigt auf Dateien außerhalb – git add folgte ihr. Jetzt C/diff,
        bevor irgendetwas eingesammelt oder committet wird."""
        aussen = os.path.join(self.ordner.name, "aussen")
        os.makedirs(aussen)
        with open(os.path.join(aussen, "zugang.txt"), "w") as f:
            f.write("geheim-ohne-muster\n")
        self.reparieren()
        ziel = os.path.join(self.p["klon"], "lib", "link")
        subprocess.run(["cmd", "/c", "mklink", "/J", ziel, aussen], check=True, capture_output=True, creationflags=OHNE)
        b = self.pruefen()
        self.assertEqual(b["code"], "C/diff")
        self.assertIn(("lib/link", "Verweis (Symlink/Junction)"), b["verweise"])
        self.assertIsNone(b["kopf"])                                                             # nichts eingesammelt
        self.assertFalse(os.path.exists(os.path.join(c.repo(self.p), "refs", "heads", "paket-A7")))
        os.rmdir(ziel)                                                                           # die Junction selbst (nicht ihr Ziel)
        os.link(os.path.join(aussen, "zugang.txt"), os.path.join(self.p["klon"], "lib", "zugang.txt"))
        b = self.pruefen()
        self.assertEqual(b["code"], "C/diff")
        self.assertIn(("lib/zugang.txt", "Hardlink (weiterer Name derselben Datei)"), b["verweise"])

    def test_diff_tor(self):
        self.reparieren()
        self.schreiben(self.p["klon"], "doc/fremd.md", "x\n")
        b = self.pruefen()
        self.assertEqual((b["code"], b["ausserhalb"]), ("C/diff", ["doc/fremd.md"]))

    def test_automatisch_geladen_und_geheimnis(self):
        self.reparieren()
        self.schreiben(self.p["klon"], "lib/conftest.py", "x = 1\n")
        b = self.pruefen()
        self.assertEqual((b["code"], b["autogeladen"]), ("C/diff", ["lib/conftest.py"]))
        os.replace(os.path.join(self.p["klon"], "lib", "conftest.py"), os.path.join(self.ordner.name, "weg.py"))
        wert = "ghp_" + "A" * 36
        self.schreiben(self.p["klon"], "lib/zugang.py", f"TOKEN = '{wert}'\n")
        b = self.pruefen()
        self.assertEqual(b["code"], "C/diff")
        self.assertIn(("lib/zugang.py", "GitHub-Token"), b["geheim"])
        self.assertNotIn(wert, b["grund"])                                                       # nie der Wert selbst

    def test_nach_aussen(self):
        self.reparieren()
        self.schreiben(self.p["klon"], "lib/hol.py", "import requests\nrequests.get('https://sammler.org/x')\n")
        b = self.pruefen()
        self.assertEqual(b["code"], "C/aussen")
        self.assertIn(("lib/hol.py", "Adresse sammler.org"), b["aussen"])
        self.assertIn(("lib/hol.py", "Netz"), b["aussen"])
        self.assertEqual(c.nach_aussen([("a.py", "url = 'http://localhost:8780/x'"), ("b.py", "u = 'https://x.invalid'")]), [])

    def test_rot_und_technik(self):
        self.schreiben(self.p["klon"], "lib/rechnen.py", "def plus(a, b):\n    return 0\n")      # geändert, aber falsch
        self.assertEqual(self.pruefen()["code"], "C/rot")
        self.assertEqual(self.pruefen(befehl="gibtsnicht-abnahme")["code"], "C/technik")
        self.assertEqual(self.pruefen(befehl=f'{PY} -c "import time; time.sleep(30)"', frist=2)["code"], "C/technik")

    def test_abnahme_ohne_zugaenge_des_menschen(self):
        self.reparieren()
        probe = f'{PY} -c "import os,sys; sys.exit(3 if os.environ.get(\'GH_TOKEN\') or os.environ.get(\'ANTHROPIC_API_KEY\') else 0)"'
        with mock.patch.dict(os.environ, {"GH_TOKEN": "geheim", "ANTHROPIC_API_KEY": "geheim"}):
            b = self.pruefen(befehl=probe)
        self.assertIsNone(b["code"], b)

    def test_test_schreiben_rot_gegen_alt_gruen_gegen_neu(self):
        self.reparieren()
        self.schreiben(self.p["klon"], "tests/test_neu.py", "import unittest\nfrom lib.rechnen import plus\n\n\nclass N(unittest.TestCase):\n"
                       "    def test_drei(self):\n        self.assertEqual(plus(1, 2), 3)\n")
        b = self.pruefen(bereiche=("lib/", "tests/"), befehl=f"{PY} -X utf8 -m unittest tests.test_neu", typ="test-schreiben")
        self.assertIsNone(b["code"], b)
        self.assertGreaterEqual(b["test_schreiben"]["tests"], 1)
        # ein Test, der schon gegen den alten Stand grün ist, prüft nichts
        self.schreiben(self.p["klon"], "tests/test_neu.py", "import unittest\n\n\nclass N(unittest.TestCase):\n    def test_immer(self):\n        pass\n")
        b = self.pruefen(bereiche=("lib/", "tests/"), befehl=f"{PY} -X utf8 -m unittest tests.test_neu", typ="test-schreiben")
        self.assertEqual(b["code"], "C/rot")

    def test_regressions_kurzsuite_fest(self):
        self.assertIn("unittest", c.REGRESSION)
        self.reparieren()
        b = c.pruefen(self.p, self.projekt, self.basis, 7, self.befehl, ["lib/"], None, 120, regression=f'{PY} -c "raise SystemExit(1)"')
        self.assertEqual(b["code"], "C/rot")
        self.assertIn("Regressions-Kurzsuite", b["grund"])


if __name__ == "__main__":
    unittest.main()
