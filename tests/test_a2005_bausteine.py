"""A2005 (F5386 A, TH156 AUFRÄUMEN): die Workbench-Seite in Bausteinen – eine Quelle in amw/workbench/ (Gerüst, Stil-Teile,
Sprachdateien DE/EN, Skript-Bausteine), zusammengesetzt von workbench.seite(). Beleg des Schnitts: die Seite ist byte-gleich zur
letzten amw/workbench.html (SHA-256 unten; entfällt mit dem ersten Umbau eines Bausteins). amw/workbench.html kommt nicht zurück."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import hashlib
import os
import unittest

from amw import workbench

LETZTE_HTML = "a9bf6c2de7655733a4cca7dfc48b07b4c3825b3b262976cdfe9816501f2d2f33"   # amw/workbench.html auf 97de398 (845706 Bytes)


class Bausteine(unittest.TestCase):
    def test_schnitt_byte_gleich(self):
        roh = workbench.seite().encode("utf-8")
        self.assertEqual((len(roh), hashlib.sha256(roh).hexdigest()), (845706, LETZTE_HTML))

    def test_jeder_baustein_genau_einmal_keine_platzhalter(self):
        s = workbench.seite()
        for ordner in ("stil", "skript", "texte"):
            for f in os.listdir(os.path.join(workbench.BAUSTEINE, ordner)):
                stuecke = workbench._lesen(ordner, f).replace("@@TEXTE_EN@@\n", "@@TEXTE_DE@@\n").split("@@TEXTE_DE@@\n")
                for stueck in (x for x in stuecke if len(x) > 40):                       # um die Sprachdateien herum je Stück
                    with self.subTest(baustein=f"{ordner}/{f}"):
                        self.assertEqual(s.count(stueck), 1)
        self.assertNotIn("@@", s.replace("@@ ", ""))                                    # alle Platzhalter ersetzt
        self.assertTrue(s.startswith("<!DOCTYPE") or s.lower().startswith("<!doctype"))

    def test_keine_zweite_quelle(self):
        self.assertFalse(os.path.exists(os.path.join(workbench.HIER, "workbench.html")), "amw/workbench.html ist zurück – die Seite"
                         " lebt in amw/workbench/ (A2005, eine Quelle)")


if __name__ == "__main__":
    unittest.main()
