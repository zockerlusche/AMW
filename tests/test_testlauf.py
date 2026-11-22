"""A1966 (Marcel W2465/W2466): Gesamtlauf parallel – Verteilen nach Dauer, Browser-Tests in einem Prozess, Ausgabe wie
unittest (Ran N tests / OK / FAILED), rc, Dauer-Messung außerhalb des Repos."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import io
import json
import os
import tempfile
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


class Lauf(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.tests = os.path.join(self.ordner.name, "tests")
        os.makedirs(self.tests)
        self.dauer = os.path.join(self.ordner.name, "dauer.json")

    def datei(self, name, text):
        with open(os.path.join(self.tests, name), "w", encoding="utf-8") as f:
            f.write(text)

    def lauf(self, n):
        aus = io.StringIO()
        rc = testlauf.steuern(n=n, wurzel=self.ordner.name, aus=aus, dauer_datei=self.dauer)
        return rc, aus.getvalue()

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


if __name__ == "__main__":
    unittest.main()
