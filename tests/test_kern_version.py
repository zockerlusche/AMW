"""Reine Hilfsfunktionen aus kern: version_teile (MAJOR.MINOR.PATCH zerlegen) und lead_und_fach (Lead-Schalter und
Fachgebiet aus der früheren Freitext-Rolle). Ohne Datenbank."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import unittest

from amw import kern


class VersionTeile(unittest.TestCase):
    def test_gueltige_form(self):
        self.assertEqual(kern.version_teile("1.78.0"), (1, 78, 0))
        self.assertEqual(kern.version_teile("0.1.0"), (0, 1, 0))
        self.assertEqual(kern.version_teile("10.200.3000"), (10, 200, 3000))

    def test_ergebnis_sind_ganze_zahlen(self):
        teile = kern.version_teile("01.002.0")
        self.assertEqual(teile, (1, 2, 0))
        self.assertTrue(all(isinstance(x, int) for x in teile))

    def test_leerraum_wird_ignoriert(self):
        self.assertEqual(kern.version_teile("  1.78.0  "), (1, 78, 0))
        self.assertEqual(kern.version_teile("\t1.2.3\n"), (1, 2, 3))

    def test_zusatz_nach_bindestrich_oder_plus(self):
        self.assertEqual(kern.version_teile("1.2.3-rc.1"), (1, 2, 3))
        self.assertEqual(kern.version_teile("1.2.3+build5"), (1, 2, 3))

    def test_falsche_form_gibt_none(self):
        for v in ("1.2", "v1.2.3", "1.2.3.4", "1", "", "   ", "a.b.c", "1.2.x", "1..3", "1.2.3 x"):
            with self.subTest(v=v):
                self.assertIsNone(kern.version_teile(v))

    def test_none_gibt_none(self):
        self.assertIsNone(kern.version_teile(None))

    def test_eignet_sich_zum_vergleichen(self):
        self.assertLess(kern.version_teile("1.9.0"), kern.version_teile("1.10.0"))
        self.assertLess(kern.version_teile("1.78.9"), kern.version_teile("2.0.0"))


class LeadUndFach(unittest.TestCase):
    def test_lead(self):
        self.assertEqual(kern.lead_und_fach("Lead"), ("lead", None))
        self.assertEqual(kern.lead_und_fach("lead"), ("lead", None))
        self.assertEqual(kern.lead_und_fach("  LEAD  "), ("lead", None))

    def test_lead_mit_fachgebiet(self):
        self.assertEqual(kern.lead_und_fach("Lead", "Backend"), ("lead", "Backend"))
        self.assertEqual(kern.lead_und_fach("lead", "  Backend  "), ("lead", "Backend"))

    def test_freitext_wird_fachgebiet(self):
        self.assertEqual(kern.lead_und_fach("Frontend"), (None, "Frontend"))
        self.assertEqual(kern.lead_und_fach("  Datenbank  "), (None, "Datenbank"))

    def test_angegebenes_fachgebiet_geht_vor_freitext(self):
        self.assertEqual(kern.lead_und_fach("Frontend", "Backend"), (None, "Backend"))

    def test_nur_fachgebiet(self):
        self.assertEqual(kern.lead_und_fach(None, "Backend"), (None, "Backend"))
        self.assertEqual(kern.lead_und_fach("", "Backend"), (None, "Backend"))

    def test_leer(self):
        self.assertEqual(kern.lead_und_fach(None), (None, None))
        self.assertEqual(kern.lead_und_fach(""), (None, None))
        self.assertEqual(kern.lead_und_fach("   ", "   "), (None, None))

    def test_lead_nur_als_ganzes_wort(self):
        self.assertEqual(kern.lead_und_fach("Lead-Entwickler"), (None, "Lead-Entwickler"))


if __name__ == "__main__":
    unittest.main()
