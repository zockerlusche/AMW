"""A1966 (Marcel W2465/W2466): Gesamtlauf parallel – Verteilen nach Dauer, Browser-Tests in einem Prozess, Ausgabe wie
unittest (Ran N tests / OK / FAILED), rc, Dauer-Messung außerhalb des Repos."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import io
import json
import os
import tempfile
import time
import unittest
from unittest import mock

from amw import testlauf

GRUEN = "import unittest\n\nclass T(unittest.TestCase):\n" + "".join(f"    def test_{i}(self):\n        pass\n" for i in range(3))
ROT = "import unittest\n\nclass T(unittest.TestCase):\n    def test_rot(self):\n        self.assertEqual(1, 2)\n\n" \
      "    @unittest.skip('weg')\n    def test_weg(self):\n        pass\n"


class Verteilen(unittest.TestCase):
    def test_laengstes_zuerst_an_den_leichtesten_browser_extra(self):
        mods = [(n, f"/x/{n}.py") for n in ("test_a", "test_b", "test_c", "test_d", "test_web1", "test_web2")]
        d = {"test_a": 10, "test_b": 8, "test_c": 3, "test_d": 2, "test_web1": 30, "test_web2": 1}
        g = testlauf.verteilen(mods, 3, d, {"test_web1", "test_web2"})
        self.assertEqual(g[0][:2], ["test_web1", "test_web2"])                       # Browser zusammen, Prozess 0
        self.assertEqual(sorted(g[1] + g[2]), ["test_a", "test_b", "test_c", "test_d"])
        self.assertEqual((g[1], g[2]), (["test_a", "test_d"], ["test_b", "test_c"]))  # 10+2 / 8+3
        self.assertEqual(testlauf.verteilen(mods, 1, d, {"test_web1"})[0][0], "test_web1")   # N = 1: alles in einem
        ohne = testlauf.verteilen(mods[:4], 2, d, set())
        self.assertEqual(ohne, [["test_a", "test_d"], ["test_b", "test_c"]])

    def test_ergebnis_zeile_wie_unittest(self):
        s = {"ran": 5, "failures": 0, "errors": 0, "skipped": 4, "expected_failures": 0, "unexpected_successes": 0}
        self.assertEqual(testlauf.ergebnis_zeile(s), "OK (skipped=4)")
        self.assertEqual(testlauf.ergebnis_zeile(dict(s, failures=1, errors=2)), "FAILED (failures=1, errors=2, skipped=4)")
        self.assertEqual(testlauf.ergebnis_zeile(dict(s, skipped=0)), "OK")

    def test_prozesse_aus_der_umgebung(self):
        with mock.patch.dict(os.environ, {"AMW_TESTPROZESSE": "3"}):
            self.assertEqual(testlauf.prozesse(), 3)
        with mock.patch.dict(os.environ, {"AMW_TESTPROZESSE": "x"}):
            self.assertGreaterEqual(testlauf.prozesse(), 2)


class LaufGrund(unittest.TestCase):
    """Hilfen für Läufe in einem eigenen Ordner – ohne eigene Tests."""

    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.tests = os.path.join(self.ordner.name, "tests")
        os.makedirs(self.tests)
        self.dauer = os.path.join(self.ordner.name, "dauer.json")

    def datei(self, name, text):
        with open(os.path.join(self.tests, name), "w", encoding="utf-8") as f:
            f.write(text)

    def lauf(self, n, **kw):
        aus = io.StringIO()
        rc = testlauf.steuern(n=n, wurzel=self.ordner.name, aus=aus, dauer_datei=self.dauer, **kw)
        return rc, aus.getvalue()


class Lauf(LaufGrund):
    def test_gruen_parallel_gleiche_zahl_wie_seriell_und_dauer_gemessen(self):
        for i in range(4):
            self.datei(f"test_m{i}.py", GRUEN)
        self.datei("hilfe.py", "x = 1\n")                                             # kein Testmodul
        rc, aus = self.lauf(2)
        self.assertEqual(rc, 0, aus)
        self.assertRegex(aus, r"Ran 12 tests in \d+\.\d{3}s\n\nOK\n?$")
        self.assertIn("4 Module auf 2 Prozesse", aus)
        with open(self.dauer, encoding="utf-8") as f:
            self.assertEqual(sorted(json.load(f)), [f"test_m{i}" for i in range(4)])
        rc1, aus1 = self.lauf(1)
        self.assertEqual((rc1, aus1.splitlines()[-1]), (0, "OK"))
        self.assertIn("Ran 12 tests in", aus1)

    def test_rot_mit_fehlerbericht_und_rc_1(self):
        self.datei("test_gut.py", GRUEN)
        self.datei("test_schlecht.py", ROT)
        self.datei("test_kaputt.py", "import gibt_es_nicht_xyz\n")
        rc, aus = self.lauf(3)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL: test_rot (test_schlecht.T.test_rot)", aus)
        self.assertIn("AssertionError: 1 != 2", aus)
        self.assertIn("gibt_es_nicht_xyz", aus)
        self.assertIn("Ran 6 tests in", aus)                                          # 3 + 2 + 1 (Modul lädt nicht)
        self.assertEqual(aus.splitlines()[-1], "FAILED (failures=1, errors=1, skipped=1)")


SCHLAEFT = ("import time\nimport unittest\n\nclass S(unittest.TestCase):\n    def test_vorher(self):\n        print('vor dem Hänger')\n\n"
            "    def test_haengt(self):\n        print('jetzt hänge ich', flush=True)\n        time.sleep(120)\n")


class Zeitgrenze(LaufGrund):
    """A2051: ein hängender Arbeiter wird beendet, sein Modul rot mit Testmethode gemeldet, die restlichen Module laufen weiter."""

    def test_haenger_beendet_rest_laeuft_weiter(self):
        self.datei("test_a_schlaeft.py", SCHLAEFT)
        for i in range(3):
            self.datei(f"test_m{i}.py", GRUEN)
        t0 = time.monotonic()
        rc, aus = self.lauf(1, grenze_s=3, ende=0)                                  # ein Prozess: schlaeft zuerst, dann m0–m2
        self.assertLess(time.monotonic() - t0, 60, aus)                              # nicht 120 s gewartet
        self.assertEqual(rc, 1, aus)
        self.assertIn("!! Zeitgrenze: test_a_schlaeft (test_a_schlaeft.S.test_haengt) in p0", aus)
        self.assertIn("weiter mit 3 Modulen", aus)
        self.assertIn("ERROR: test_a_schlaeft.S.test_haengt (Zeitgrenze: Prozess p0", aus)
        self.assertIn("jetzt hänge ich", aus)                                        # Ausgabe des Arbeiters gerettet (-u)
        for i in range(3):
            self.assertRegex(aus, rf"\[\d/4\] test_m{i} ok \d+\.\ds \(p0\)")         # Fortschritt je Modul
        self.assertIn("Ran 10 tests in", aus)                                        # 9 grün + der Hänger (test_haengt läuft vor test_vorher)
        self.assertEqual(aus.splitlines()[-1], "FAILED (errors=1)")
        with open(self.dauer, encoding="utf-8") as f:
            self.assertNotIn("test_a_schlaeft", json.load(f))                        # keine falsche Dauer gemessen

    def test_gegenprobe_ohne_haenger_keine_zeitgrenze(self):
        self.datei("test_m0.py", GRUEN)
        rc, aus = self.lauf(2, grenze_s=30, ende=0)
        self.assertEqual(rc, 0, aus)
        self.assertNotIn("Zeitgrenze:", aus)
        self.assertIn("[1/1] test_m0 ok", aus)

    def test_frist_haelt_stand_fest_rc_124(self):
        self.datei("test_a_schlaeft.py", SCHLAEFT)
        self.datei("test_m0.py", GRUEN)
        rc, aus = self.lauf(2, grenze_s=600, ende=time.time() + testlauf.RESERVE_S + 4)
        self.assertEqual(rc, 124, aus)
        self.assertIn("=== Frist erreicht – Stand der Arbeiter", aus)
        self.assertIn("Läuft gerade: p", aus)
        self.assertIn("test_a_schlaeft · test_a_schlaeft.S.test_haengt", aus)
        self.assertIn("jetzt hänge ich", aus)
        self.assertTrue(aus.splitlines()[-1].startswith("FAILED"))
        self.assertEqual(testlauf.haenger(aus)[0][:len("Läuft gerade: p")], "Läuft gerade: p")

    def test_zeitgrenze_und_frist_aus_der_umgebung(self):
        with mock.patch.dict(os.environ, {"AMW_TEST_ZEITGRENZE_S": "90", "AMW_LAUF_ENDE": "1700000000"}):
            self.assertEqual((testlauf.zeitgrenze(), testlauf.lauf_ende()), (90.0, 1700000000.0))
        with mock.patch.dict(os.environ, {"AMW_TEST_ZEITGRENZE_S": "x", "AMW_LAUF_ENDE": ""}):
            self.assertEqual((testlauf.zeitgrenze(), testlauf.lauf_ende()), (testlauf.ZEITGRENZE_S, None))
        self.assertEqual(testlauf.haenger("[3/9] test_x ok 1.0s (p1)\nRan 3 tests"),["zuletzt fertig: [3/9] test_x ok 1.0s (p1)"])


class Baum(LaufGrund):
    """A2055: ändert sich der Baum während des Laufs (HEAD oder Dateien, ohne daten/), ist der Lauf kein Beleg: rc 3, FAILED."""

    def git(self, *a):
        import subprocess
        subprocess.run(["git", "-C", self.ordner.name, *a], check=True, capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def setUp(self):
        super().setUp()
        self.datei("test_m0.py", GRUEN)
        with open(os.path.join(self.ordner.name, ".gitignore"), "w", encoding="utf-8") as f:
            f.write("__pycache__/\ndauer.json\n")
        self.git("init", "-q")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x")

    def test_unveraendert_gruen(self):
        rc, aus = self.lauf(1, ende=0)
        self.assertEqual(rc, 0, aus)
        self.assertNotIn("Baum während", aus)

    def test_datei_im_baum_geaendert_kein_beleg(self):
        self.datei("test_m1.py", "import os\nimport unittest\n\nclass B(unittest.TestCase):\n    def test_baut(self):\n"
                                 "        open(os.path.join(os.getcwd(), 'halb.js'), 'w').write('x')\n"
                                 "        os.makedirs(os.path.join(os.getcwd(), 'daten'), exist_ok=True)\n"
                                 "        open(os.path.join(os.getcwd(), 'daten', 'egal.txt'), 'w').write('x')\n")
        vorher = testlauf.baum_stand(self.ordner.name)
        rc, aus = self.lauf(1, ende=0)
        self.assertEqual(rc, testlauf.RC_BAUM, aus)
        self.assertIn("!! Baum während des Laufs geändert: halb.js – dieser Lauf gilt nicht als Beleg", aus)   # daten/ zählt nicht
        self.assertEqual(aus.splitlines()[-1], "FAILED (baum geaendert)")
        self.assertIsNotNone(vorher)
        self.assertIsNone(testlauf.baum_stand(os.path.join(self.ordner.name, "gibt-es-nicht")))   # ohne Git: keine Prüfung


if __name__ == "__main__":
    unittest.main()
