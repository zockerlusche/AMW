"""Empfehlung (D1289): wert_pruefen, tabelle_pruefen und passt einzeln – ohne Datenbank, nur die reinen Prüfungen."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import unittest

from amw import empfehlung


class WertPruefen(unittest.TestCase):
    def test_gross_klein_und_leerraum_werden_vereinheitlicht(self):
        self.assertEqual(empfehlung.wert_pruefen("opus/high"), "opus/high")
        self.assertEqual(empfehlung.wert_pruefen("Opus/High"), "opus/high")
        self.assertEqual(empfehlung.wert_pruefen("SONNET/MEDIUM"), "sonnet/medium")
        self.assertEqual(empfehlung.wert_pruefen("  haiku/Low "), "haiku/low")

    def test_alle_modelle_und_stufen_gehen(self):
        for m in empfehlung.MODELLE:
            for s in empfehlung.STUFEN:
                self.assertEqual(empfehlung.wert_pruefen(f"{m.upper()}/{s}"), f"{m}/{s}")

    def test_falsches_modell_valueerror(self):
        for falsch in ("gpt/high", "claude-opus/high", "/high", "opus5/high"):
            with self.subTest(falsch=falsch), self.assertRaises(ValueError):
                empfehlung.wert_pruefen(falsch)

    def test_falscher_denkaufwand_valueerror(self):
        for falsch in ("opus/ultra", "opus/", "opus", "sonnet/hoch", "opus/high/x"):
            with self.subTest(falsch=falsch), self.assertRaises(ValueError):
                empfehlung.wert_pruefen(falsch)

    def test_leer_und_none_valueerror(self):
        for falsch in (None, "", "   ", "/"):
            with self.subTest(falsch=falsch), self.assertRaises(ValueError):
                empfehlung.wert_pruefen(falsch)

    def test_meldung_nennt_wert_und_auswahl(self):
        with self.assertRaises(ValueError) as f:
            empfehlung.wert_pruefen("gpt/high")
        text = str(f.exception)
        self.assertIn("gpt/high", text)
        for m in empfehlung.MODELLE:
            self.assertIn(m, text)
        for s in empfehlung.STUFEN:
            self.assertIn(s, text)


class TabellePruefen(unittest.TestCase):
    def test_nur_abweichungen_vom_standard(self):
        t = {"einfach": {"S": "haiku/low", "M": "opus/medium"}, "heikel": {"XL": "opus/high"}}      # A1930: Startwerte TH159
        self.assertEqual(empfehlung.tabelle_pruefen(t), {"einfach": {"S": "haiku/low"}})

    def test_standard_selbst_ergibt_leere_tabelle(self):
        self.assertEqual(empfehlung.tabelle_pruefen(empfehlung.STANDARD), {})
        self.assertEqual(empfehlung.tabelle_pruefen({}), {})

    def test_standard_in_anderer_schreibweise_ist_keine_abweichung(self):
        self.assertEqual(empfehlung.tabelle_pruefen({"mittel": {"M": "OPUS/Medium"}}), {})

    def test_werte_werden_vereinheitlicht(self):
        self.assertEqual(empfehlung.tabelle_pruefen({"mittel": {"S": "Fable/MAX", "L": " opus/xhigh "}}),
                         {"mittel": {"S": "fable/max", "L": "opus/xhigh"}})

    def test_json_text(self):
        t = json.dumps({"heikel": {"S": "opus/xhigh", "M": "opus/high"}})                         # A1930: heikel = opus/high
        self.assertEqual(empfehlung.tabelle_pruefen(t), {"heikel": {"S": "opus/xhigh"}})
        self.assertEqual(empfehlung.tabelle_pruefen(json.dumps(empfehlung.STANDARD)), {})
        self.assertEqual(empfehlung.tabelle_pruefen(""), {})                # leerer Text wie {}

    def test_json_text_kaputt(self):
        with self.assertRaises(ValueError):                                 # json.JSONDecodeError ist ein ValueError
            empfehlung.tabelle_pruefen("{einfach")

    def test_keine_tabelle(self):
        for falsch in ([], ["einfach"], 5, json.dumps([1, 2])):
            with self.subTest(falsch=falsch), self.assertRaises(ValueError):
                empfehlung.tabelle_pruefen(falsch)

    def test_unbekannte_gruppe(self):
        for falsch in ({"lustig": {"S": "opus/high"}}, {"Einfach": {"S": "opus/high"}}):
            with self.subTest(falsch=falsch), self.assertRaises(ValueError) as f:
                empfehlung.tabelle_pruefen(falsch)
            self.assertIn("Gruppe", str(f.exception))

    def test_gruppe_ohne_zeile(self):
        with self.assertRaises(ValueError):
            empfehlung.tabelle_pruefen({"einfach": "opus/high"})

    def test_unbekannte_groesse(self):
        for falsch in ({"einfach": {"XXL": "opus/high"}}, {"mittel": {"s": "opus/high"}}):
            with self.subTest(falsch=falsch), self.assertRaises(ValueError) as f:
                empfehlung.tabelle_pruefen(falsch)
            self.assertIn("Größe", str(f.exception))

    def test_falscher_wert_in_der_tabelle(self):
        for falsch in ({"einfach": {"S": "gpt/high"}}, {"heikel": {"L": "opus/ultra"}}):
            with self.subTest(falsch=falsch), self.assertRaises(ValueError):
                empfehlung.tabelle_pruefen(falsch)

    def test_eingabe_bleibt_unveraendert(self):
        t = {"einfach": {"S": "Haiku/Low", "M": "sonnet/medium"}}
        empfehlung.tabelle_pruefen(t)
        self.assertEqual(t, {"einfach": {"S": "Haiku/Low", "M": "sonnet/medium"}})


class Passt(unittest.TestCase):
    V = {"modell": "opus", "denkstufe": "high"}

    def test_none_bei_unvollstaendigem_profil(self):
        for profil in (None, {}, {"modell": "opus"}, {"denkstufe": "high"}, {"modell": None, "denkstufe": "high"},
                       {"modell": "opus", "denkstufe": None}, {"modell": "", "denkstufe": "high"},
                       {"modell": "opus", "denkstufe": ""}):
            with self.subTest(profil=profil):
                self.assertIsNone(empfehlung.passt(profil, self.V))

    def test_true_bei_gleichem_profil(self):
        self.assertIs(empfehlung.passt({"modell": "opus", "denkstufe": "high"}, self.V), True)
        self.assertIs(empfehlung.passt({"modell": "claude-opus-5-5", "denkstufe": "high"}, self.V), True)   # Kurzname im langen
        self.assertIs(empfehlung.passt({"modell": "Opus 5.5", "denkstufe": "high"}, self.V), True)          # Groß/Klein beim Modell

    def test_false_bei_abweichung(self):
        self.assertIs(empfehlung.passt({"modell": "sonnet", "denkstufe": "high"}, self.V), False)
        self.assertIs(empfehlung.passt({"modell": "opus", "denkstufe": "medium"}, self.V), False)
        self.assertIs(empfehlung.passt({"modell": "claude-sonnet-5-5", "denkstufe": "low"}, self.V), False)


if __name__ == "__main__":
    unittest.main()
