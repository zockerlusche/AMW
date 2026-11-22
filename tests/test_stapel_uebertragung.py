"""A1932 (22.11., stapel2 #29812): Ein gestapeltes Release mit mehreren Aufgaben auf einem SHA wird nur im Betreff neu
geschrieben (gleicher Baum, gleiche patch-id). Die Übertragung (A1814) schreibt je Aufgabe eine Prüfzeile – nicht nur für die
erste, weil das Ziel danach „schon grün“ war –, und eine vom Lead gesetzte Ausnahme vom Gesamtlauf bleibt gültig, wenn das
neuere Merge-OK nur übertragen ist und der Baum gleich bleibt."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import unittest

from amw import auslieferung, betrieb, kern
from tests import test_auslieferung as ta


class Stapel(unittest.TestCase):
    setUp_kette, g, stand, extern, kette = ta.Kette.setUp, ta.Kette.g, ta.Kette.stand, ta.Kette.extern, ta.Kette.kette

    def setUp(self):
        self.setUp_kette()
        self.a = kern.aufgabe_neu(self.con, self.pid, "TL", "Erstes im Stapel", "CC1")
        self.b = kern.aufgabe_neu(self.con, self.pid, "TL", "Zweites im Stapel", "CC1")
        for aid in (self.a, self.b):                                                       # beide auf genau demselben SHA
            betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "neu", self.sha, "x", aid)
            prid = self.con.execute("SELECT max(id) FROM pruefung").fetchone()[0]
            betrieb.pruefung_ergebnis(self.con, self.pid, "TL", prid, "gruen")
            betrieb.freigabe_merge(self.con, self.pid, "TL", aid, "neu", ausnahme="Baum bitgleich mit dem grünen Lauf")
        baum = self.g("rev-parse", f"{self.sha}^{{tree}}")                                 # nur der Betreff anders
        self.sha2 = self.g("commit-tree", baum, "-p", "main", "-m", "1.1.0: Neues Ding (Betreff ohne fremde Nummer)")
        self.g("branch", "neu2", self.sha2)

    def test_je_aufgabe_eine_zeile_und_ausnahme_bleibt(self):
        v = self.kette().pruefen("neu2")                                                   # ohne Gesamtlauf: nur mit Ausnahme
        self.assertEqual(v["sha"], self.sha2)
        self.assertIn("Baum bitgleich", v["ausnahme"])
        for aid in (self.a, self.b):
            r = self.con.execute("SELECT zweig FROM pruefung WHERE aufgabe_id = ? AND sha = ? AND ergebnis = 'gruen'",
                                 (aid, self.sha2)).fetchone()
            self.assertIsNotNone(r, f"A{aid}: keine Zeile auf dem neuen Stand")
            self.assertEqual(r["zweig"], "neu2")
            self.assertTrue(betrieb.merge_ok(self.con, self.pid, aid, "neu2"))
        self.assertEqual(self.kette().staende(self.sha2), [])

    def test_uebertragung_je_aufgabe(self):
        aus = self.kette().uebertragen(self.sha2, "neu2")
        self.assertEqual(sorted(int(z.split(":")[0][1:]) for z in aus), sorted([self.a, self.b]))
        zeilen = self.con.execute("SELECT aufgabe_id FROM pruefung WHERE sha = ? AND ergebnis = 'gruen'", (self.sha2,)).fetchall()
        self.assertEqual(sorted(r[0] for r in zeilen), sorted([self.a, self.b]))          # vorher: nur die erste Aufgabe

    def test_ausnahme_nur_bei_gleichem_baum(self):
        self.kette().pruefen("neu2")                                                       # überträgt (AMW-OK auf neu2)
        self.assertIsNotNone(betrieb.gesamtlauf_ausnahme(self.con, self.pid, self.a, baum_gleich=lambda s: True))
        self.assertIsNone(betrieb.gesamtlauf_ausnahme(self.con, self.pid, self.a, baum_gleich=lambda s: False))
        self.assertIsNone(betrieb.gesamtlauf_ausnahme(self.con, self.pid, self.a))         # ohne Baumvergleich wie bisher
        betrieb.freigabe_merge(self.con, self.pid, "TL", self.a, "neu2")                   # ein OK des Leads ohne Ausnahme zählt
        self.assertIsNone(betrieb.gesamtlauf_ausnahme(self.con, self.pid, self.a, baum_gleich=lambda s: True))


if __name__ == "__main__":
    unittest.main()
