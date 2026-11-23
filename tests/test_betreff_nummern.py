"""A1988 (Befund #30955): eine fremde A-Nummer im Betreff („(A1984: bis 20 s)“) hielt die Release-Kette erst beim Ausliefern
an (Stopp „Stände“) – jetzt lehnt die Prüfbitte (und damit amw paket fertig) sie gleich ab und nennt den Commit."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import unittest

from amw import betrieb, kern
from tests import test_versionsnummer as tv


class Betreff(unittest.TestCase):
    setUp, g, stand, commit, bitte = tv.Nummer.setUp, tv.Nummer.g, tv.Nummer.stand, tv.Nummer.commit, tv.Nummer.bitte

    def test_fremde_nummer_im_betreff(self):
        alt = kern.aufgabe_neu(self.con, self.pid, "TL", "Alt", "CC1")
        a = kern.aufgabe_neu(self.con, self.pid, "TL", "Neu", "CC1")
        self.g("switch", "-q", "-c", "a", "main")
        c = self.commit({"a.txt": "x\n"}, f"A{a}: Bremse sofort (vorher A{alt}: bis 20 s); A9999 gibt es nicht")
        self.g("switch", "-q", "main")
        self.assertEqual(betrieb.fremde_a_nummern(self.con, self.pid, c, a), [(c, alt)])           # A9999: keine Aufgabe → egal
        with self.assertRaises(kern.AmwFehler) as e:
            self.bitte("CC1", "a", c, a)
        self.assertIn(f"Commit {c[:8]} nennt A{alt}", str(e.exception))
        self.g("switch", "-q", "-c", "a2", "main")
        c2 = self.commit({"a.txt": "x\n"}, f"A{a}: Bremse sofort (vorher bis 20 s)")               # umformuliert: geht
        self.g("switch", "-q", "main")
        self.assertTrue(self.bitte("CC1", "a2", c2, a))

    def test_stapel_nennt_seine_aufgaben(self):
        a1, a2 = (kern.aufgabe_neu(self.con, self.pid, "TL", t, "CC1") for t in ("Eins", "Zwei"))
        a3 = kern.aufgabe_neu(self.con, self.pid, "TL", "Drei", "CC2")
        self.g("switch", "-q", "-c", "st", "main")
        self.commit({"a.txt": "1\n"}, f"A{a1}: eins")
        self.commit({"b.txt": "2\n"}, f"A{a2}: zwei")
        spitze = self.commit({"amw/__init__.py": '__version__ = "1.1.0"\n'}, f"1.1.0: Stapel – A{a1} + A{a2}")
        self.g("switch", "-q", "main")
        self.assertEqual(betrieb.fremde_a_nummern(self.con, self.pid, spitze, a1), [])               # beide im Versions-Commit
        self.assertTrue(self.bitte("CC1", "st", spitze, a1))
        self.g("switch", "-q", "-c", "st2", "main")
        self.commit({"a.txt": "1\n"}, f"A{a1}: eins, wie A{a3}")                                    # A3 gehört nicht zum Stapel
        spitze2 = self.commit({"amw/__init__.py": '__version__ = "1.2.0"\n'}, f"1.2.0: Stapel – A{a1}")
        self.g("switch", "-q", "main")
        self.assertEqual([n for _, n in betrieb.fremde_a_nummern(self.con, self.pid, spitze2, a1)], [a3])


if __name__ == "__main__":
    unittest.main()
