"""Pakettyp test-ergaenzen (A1895, Befund S8 T2): Tests für bestehenden, unveränderten Code – nur Testdateien (sonst C/diff),
Regel 6 entfällt, grün statt rot-gegen-alt mit mindestens einem wirklich ausgeführten Test, immer E4 (Lead liest)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import shutil
import os
import unittest

from amw import abnahme, arbeitspaket, entscheidung
from tests import test_pruefung_c as tp

PY = tp.PY
TEST_ALT = ("import unittest\nfrom lib.rechnen import plus\n\n\nclass N(unittest.TestCase):\n"
            "    def test_wie_heute(self):\n        self.assertEqual(plus(3, 1), 2)\n")        # beschreibt den heutigen Code (a - b)


@unittest.skipUnless(shutil.which("git") and os.name == "nt", "git/Windows fehlt")
class TestErgaenzen(unittest.TestCase):
    setUp, schreiben, pruefen = tp.PruefungC.setUp, tp.PruefungC.schreiben, tp.PruefungC.pruefen   # ohne die Tests dort erneut

    def neu(self, text=TEST_ALT):
        self.schreiben(self.p["klon"], "tests/test_neu.py", text)
        return self.pruefen(bereiche=("tests/",), befehl=f"{PY} -X utf8 -m unittest tests.test_neu", typ="test-ergaenzen")

    def test_gruen_reicht_fuer_bestehenden_code(self):
        b = self.neu()
        self.assertIsNone(b["code"], b)                                                          # test-schreiben wäre hier C/rot
        self.assertEqual(b["test_ergaenzen"], {"tests": 1, "uebersprungen": 0})
        self.assertEqual(entscheidung.entscheiden({"rc": 0}, {"status": "erledigt"}, b, typ="test-ergaenzen"), ("E4", "test-ergaenzen"))

    def test_nur_testdateien(self):
        self.schreiben(self.p["klon"], "tests/test_neu.py", TEST_ALT)
        self.schreiben(self.p["klon"], "lib/rechnen.py", "def plus(a, b):\n    return a + b\n")   # Code geändert: nicht erlaubt
        b = self.pruefen(bereiche=("lib/", "tests/"), befehl=f"{PY} -X utf8 -m unittest tests.test_neu", typ="test-ergaenzen")
        self.assertEqual(b["code"], "C/diff")
        self.assertIn("test-ergaenzen ändert nur Tests – nicht: lib/rechnen.py", b["grund"])

    def test_uebersprungen_oder_rot_beweist_nichts(self):
        b = self.neu("import unittest\n\n\nclass N(unittest.TestCase):\n    @unittest.skip('später')\n    def test_x(self):\n        pass\n")
        self.assertEqual((b["code"], b["grund"]), ("C/rot", "test-ergaenzen: kein Test ausgeführt (1 übersprungen)"))
        b = self.neu(TEST_ALT.replace("plus(3, 1), 2", "plus(3, 1), 4"))                           # rot: die Abnahme hält an
        self.assertEqual(b["code"], "C/rot")


class Regeln(unittest.TestCase):
    def test_testdateien_frei_feste_sperren_bleiben(self):
        typ = abnahme.TEST_ERGAENZEN
        self.assertEqual(abnahme.gesperrt(["tests/test_a.py"], typ), [])
        self.assertEqual(abnahme.gesperrt(["tests/abschotten.py", "pytest.ini"], typ),
                         [("tests/abschotten.py", "Testkonfiguration"), ("pytest.ini", "Testkonfiguration")])
        self.assertEqual(abnahme.nicht_nur_tests(["tests/test_a.py", "lib/a.py", "tests/abschotten.py"]), ["lib/a.py", "tests/abschotten.py"])
        self.assertEqual(abnahme.startregel(["tests/test_x.py"], typ), [])                         # einzelne Testdatei: startet
        self.assertEqual(abnahme.startregel(["tests/"], typ), [("tests/", "Testkonfiguration")])     # ganzer Ordner: wie bisher nicht
        self.assertEqual(abnahme.startregel(["tests/test_x.py"], None), [("tests/test_x.py", "Testdatei")])   # Typ normal: gesperrt
        self.assertEqual(abnahme.rot_vor_bau(None, "egal", typ), {"ok": True, "grund": "test-ergaenzen: Prüfung nach dem Bau"})
        self.assertIn("test-ergaenzen", arbeitspaket.PAKETTYPEN)
        self.assertEqual(entscheidung.entscheiden({"rc": 0}, {"status": "erledigt"}, {"code": None, "abnahme": {"befund": None}},
                                                  typ="test-schreiben"), ("E4", "test-schreiben"))   # unverändert


if __name__ == "__main__":
    unittest.main()
