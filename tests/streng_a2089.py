"""A2089, vorläufig: der Textwächter ohne die Ausnahme der acht Module, die ein Headless-Paket umstellt. Wird nicht von allein gefunden (der
Name beginnt nicht mit test_), damit der Gesamtlauf bis dahin nicht rot ist; es ist der Abnahmebefehl des Pakets und kommt danach weg."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import unittest

from tests import test_a2089_texte


class Streng(unittest.TestCase):
    def test_headless_module(self):
        for datei in test_a2089_texte.HEADLESS:
            with self.subTest(datei=datei):
                self.assertEqual(test_a2089_texte.offen(datei), [])


if __name__ == "__main__":
    unittest.main()
