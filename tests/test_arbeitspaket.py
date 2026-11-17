"""Arbeitspakete (A1845, D1258 v4 §3/§4): Felder mit Standardwerten, Zustandsautomat nur für Art p (erlaubte und verbotene
Übergänge), Spiegelung auf den Status der Aufgabe; Art agent hat keinen Automaten."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import unittest

from amw import arbeitspaket as ap


class Felder(unittest.TestCase):
    def test_standard_ohne_zeile_ist_agent(self):
        f = ap.mit_standard(None)
        self.assertEqual((f["art"], f["gewicht"], f["modell"], f["effort"], f["pakettyp"], f["ressourcen"], f["zustand"]),
                         ("agent", "leicht", "claude-opus-5-5", "high", "normal", [], None))
        self.assertEqual(f["standard"], sorted(ap.STANDARD))

    def test_art_p_beginnt_als_entwurf(self):
        f = ap.mit_standard({"art": "p", "effort": "medium"})
        self.assertEqual((f["zustand"], f["effort"]), ("entwurf", "medium"))
        self.assertNotIn("effort", f["standard"])

    def test_pruefen_vereinheitlicht_und_lehnt_ab(self):
        self.assertEqual(ap.felder_pruefen({"ressourcen": "GPU, bildschirm,gpu", "nie_gleichzeitig": "A12, 7;a12"}),
                         {"ressourcen": ["bildschirm", "gpu"], "nie_gleichzeitig": [7, 12]})
        for falsch in ({"art": "q"}, {"gewicht": "mittel"}, {"effort": "max"}, {"pakettyp": "x"}, {"ressourcen": "drucker"},
                       {"nie_gleichzeitig": "B3"}, {"modell": " "}, {"farbe": "rot"}):
            with self.assertRaises(ap.Ungueltig, msg=falsch):
                ap.felder_pruefen(falsch)

    def test_warnungen_nur_bei_p(self):
        self.assertEqual(ap.warnungen(ap.mit_standard(None), None, None), [])
        w = ap.warnungen(ap.mit_standard({"art": "p", "ressourcen": ["gpu"]}), "", None)
        self.assertEqual(len(w), 3)
        self.assertEqual(ap.warnungen(ap.mit_standard({"art": "p"}), "python -m unittest tests.test_x", "amw/x.py"), [])


class Automat(unittest.TestCase):
    def test_hauptweg_geht_durch(self):
        for alt, neu in zip(ap.HAUPTWEG, ap.HAUPTWEG[1:]):
            ap.uebergang_pruefen(alt, neu)

    def test_verbotene_uebergaenge(self):
        for alt, neu in (("entwurf", "laeuft"), ("laeuft", "fertig"), ("abgegeben", "merge_reihe"), ("startklar", "abgegeben"),
                         ("fertig", "entwurf"), ("wartet_interaktiv", "laeuft"), ("gemergt", "laeuft"), ("laeuft", "laeuft")):
            with self.assertRaises(ap.Ungueltig, msg=f"{alt} → {neu}"):
                ap.uebergang_pruefen(alt, neu)
        with self.assertRaisesRegex(ap.Ungueltig, "unbekannter Zustand"):
            ap.uebergang_pruefen("entwurf", "irgendwas")

    def test_jeder_zustand_erreichbar_und_fertig_ist_ende(self):
        self.assertEqual(set(ap.UEBERGAENGE), set(ap.ZUSTAENDE))
        self.assertTrue(all(z in ap.ZUSTAENDE for ziele in ap.UEBERGAENGE.values() for z in ziele))
        erreicht, offen = {ap.START}, [ap.START]
        while offen:
            for z in ap.UEBERGAENGE[offen.pop()]:
                if z not in erreicht:
                    erreicht.add(z)
                    offen.append(z)
        self.assertEqual(erreicht, set(ap.ZUSTAENDE))
        self.assertEqual(ap.UEBERGAENGE["fertig"], set())
        for z in ap.ZUSTAENDE:                                          # aus jedem Nicht-Endzustand kommt man wieder weg
            self.assertTrue(z == "fertig" or ap.UEBERGAENGE[z], z)

    def test_rueckwege_nach_konzept(self):
        ap.uebergang_pruefen("abnahme", "laeuft")                       # Abnahme rot: einmal zurück an den Arbeiter (§7)
        ap.uebergang_pruefen("merge_reihe", "laeuft")                   # Merge-Konflikt: Resume mit Fehlerausgabe
        ap.uebergang_pruefen("blockiert", "wartet_interaktiv")          # Stufe 1: Frage → wartet auf interaktiv

    def test_spiegel_auf_den_aufgabenstatus(self):
        erwartet = {"entwurf": "wartet", "startklar": "wartet", "laeuft": "laeuft", "abgegeben": "wartet", "abnahme": "wartet",
                    "merge_reihe": "wartet", "gemergt": "wartet", "fertig": "fertig", "blockiert": "blockiert", "unklar": "blockiert",
                    "wartet_interaktiv": "blockiert", "abgebrochen": "blockiert", "zurueckgestellt": "wartet"}
        self.assertEqual({z: ap.spiegel(z) for z in ap.ZUSTAENDE}, erwartet)
        self.assertTrue(set(erwartet.values()) <= {"wartet", "laeuft", "blockiert", "fertig"})   # passt in aufgabe.status

    def test_art_wechsel_nur_ohne_arbeiter(self):
        ap.art_wechsel_pruefen("p", "agent", "wartet_interaktiv")       # hochgestuft an einen interaktiven Agenten
        with self.assertRaises(ap.Ungueltig):
            ap.art_wechsel_pruefen("p", "agent", "laeuft")
        ap.art_wechsel_pruefen("agent", "p", None)


if __name__ == "__main__":
    unittest.main()
