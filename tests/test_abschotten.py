"""Automatismus statt Gebot: Jede Testdatei importiert tests.abschotten als Erstes – sonst schlägt dieser Test fehl."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import ast
import glob
import os
import unittest

HIER = os.path.dirname(os.path.abspath(__file__))
ZEILE = "import tests.abschotten"


class Abschotten(unittest.TestCase):
    def test_jede_testdatei_importiert_es_zuerst(self):
        fehlt = []
        for p in sorted(glob.glob(os.path.join(HIER, "test_*.py"))):
            with open(p, encoding="utf-8") as f:
                baum = ast.parse(f.read())
            importe = [n for n in baum.body if isinstance(n, (ast.Import, ast.ImportFrom))]
            if not importe or ast.unparse(importe[0]) != ZEILE:
                fehlt.append(os.path.basename(p))
        self.assertEqual(fehlt, [], f"als ersten Import „{ZEILE}  # noqa: F401“ ergänzen")

    def test_zugangs_ordner_ist_der_eigene(self):
        self.assertEqual(os.environ["LOCALAPPDATA"], tests.abschotten.ORDNER)
        self.assertIn("amw-test-lokal-", tests.abschotten.ORDNER)


if __name__ == "__main__":
    unittest.main()
