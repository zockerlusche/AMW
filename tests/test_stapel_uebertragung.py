"""A1932 (22.11., stapel2 #29812): Ein gestapeltes Release mit mehreren Aufgaben auf einem SHA wird nur im Betreff neu
geschrieben (gleicher Baum, gleiche patch-id). Die Übertragung (A1814) schreibt je Aufgabe eine Prüfzeile – nicht nur für die
erste, weil das Ziel danach „schon grün“ war –, und eine vom Lead gesetzte Ausnahme vom Gesamtlauf bleibt gültig, wenn das
neuere Merge-OK nur übertragen ist und der Baum gleich bleibt."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
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



class StapelAusSauberenZweigen(unittest.TestCase):
    """A1964 (#30495, 1.162.0): Stapel aus einem Einzelzweig ohne eigene Version (A1936) plus Versions-Commit; grün auf dem
    Einzelzweig UND auf der Stapel-Spitze. Die Übertragung legt keine Zeile auf den inneren Commit (sie würde das Grün der Spitze
    als neueste Prüfung verdrängen) – die Kette läuft ohne neue Prüfbitten durch. Ohne Grün auf der Spitze überträgt sie wie bisher."""
    setUp_kette, g, stand, extern, kette = ta.Kette.setUp, ta.Kette.g, ta.Kette.stand, ta.Kette.extern, ta.Kette.kette
    gesamtlauf = ta.Kette.gesamtlauf

    def setUp(self):
        self.setUp_kette()
        self.g("switch", "-q", "-c", "einzel", "main")
        with open(os.path.join(self.repo, "inhalt.txt"), "w", encoding="utf-8") as f:
            f.write("Inhalt der Aufgabe\n")
        self.g("add", "inhalt.txt")
        self.g("-c", "commit.gpgsign=false", "commit", "-q", "-m", "A1: Inhalt")
        self.einzel = self.g("rev-parse", "HEAD")
        self.g("switch", "-q", "-c", "stapel", "main")
        self.g("-c", "commit.gpgsign=false", "cherry-pick", self.einzel)
        self.g("-c", "commit.gpgsign=false", "commit", "-q", "--amend", "--no-edit", "--date=2026-01-01T00:00:00")   # neuer SHA, gleiche patch-id
        self.innen = self.g("rev-parse", "HEAD")
        self.assertNotEqual(self.innen, self.einzel)
        self.spitze = self.stand("1.1.0", "Stapel")                                         # Versions-Commit oben drauf
        self.g("switch", "-q", "main")
        self.a = kern.aufgabe_neu(self.con, self.pid, "TL", "Inhalt", "CC1")

    def gruen(self, aid, zweig, sha):
        betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", zweig, sha, "x", aid)
        betrieb.pruefung_ergebnis(self.con, self.pid, "TL", self.con.execute("SELECT max(id) FROM pruefung").fetchone()[0], "gruen")

    def test_gruen_auf_der_spitze_wird_nicht_verdraengt(self):
        self.gruen(self.a, "einzel", self.einzel)
        self.gruen(self.a, "stapel", self.spitze)
        betrieb.freigabe_merge(self.con, self.pid, "TL", self.a, "stapel")
        self.assertEqual(self.kette().uebertragen(self.spitze, "stapel"), [])
        self.assertIsNone(self.con.execute("SELECT 1 FROM pruefung WHERE sha = ?", (self.innen,)).fetchone())
        self.assertEqual(self.kette().staende(self.spitze), [])
        self.sha = self.spitze
        self.gesamtlauf()
        self.assertEqual(self.kette().ausliefern("stapel")["version"], "1.1.0")                # ohne neue Prüfbitten durch

    def test_ohne_gruen_auf_der_spitze_wie_bisher(self):
        self.gruen(self.a, "einzel", self.einzel)
        aus = self.kette().uebertragen(self.spitze, "stapel")
        self.assertEqual(len(aus), 1, aus)
        self.assertTrue(self.con.execute("SELECT 1 FROM pruefung WHERE sha = ? AND ergebnis = 'gruen'", (self.innen,)).fetchone())

class StapelMitAufgeloestemKonflikt(unittest.TestCase):
    """A1974 (Befund 1.165.0, #30707): Stapel aus zwei Einzelzweigen – A mit aufgelöstem Konflikt (anderer Inhalt), B sauber
    übertragen – plus Versions-Commit, dessen Betreff beide Aufgaben nennt. Der Lead gibt Grün für A auf der Spitze. Dann
    überträgt die AMW das Grün von B auf dessen inneren Commit (die Spitze deckt alles darunter), und der Versions-Commit gilt
    als geprüft – keine Prüfbitte je Aufgabe auf der Spitze mehr nötig."""
    setUp_kette, g, stand, extern, kette = ta.Kette.setUp, ta.Kette.g, ta.Kette.stand, ta.Kette.extern, ta.Kette.kette
    gesamtlauf = ta.Kette.gesamtlauf
    gruen = StapelAusSauberenZweigen.gruen

    def datei(self, name, text, betreff):
        with open(os.path.join(self.repo, name), "w", encoding="utf-8") as f:
            f.write(text)
        self.g("add", name)
        self.g("-c", "commit.gpgsign=false", "commit", "-q", "-m", betreff)
        return self.g("rev-parse", "HEAD")

    def setUp(self):
        self.setUp_kette()
        self.a = kern.aufgabe_neu(self.con, self.pid, "TL", "A", "CC1")
        self.b = kern.aufgabe_neu(self.con, self.pid, "TL", "B", "CC1")
        self.g("switch", "-q", "-c", "zweig-a", "main")
        self.einzel_a = self.datei("a.txt", "A wie geprüft\n", f"A{self.a}: a")
        self.g("switch", "-q", "-c", "zweig-b", "main")
        self.einzel_b = self.datei("b.txt", "B\n", f"A{self.b}: b")
        self.g("switch", "-q", "-c", "stapel", "main")
        self.innen_a = self.datei("a.txt", "A wie geprüft – beim Zusammenführen aufgelöst\n", f"A{self.a}: a")   # anderer Inhalt
        self.g("-c", "commit.gpgsign=false", "cherry-pick", self.einzel_b)
        self.innen_b = self.g("rev-parse", "HEAD")
        self.spitze = self.stand("1.1.0", f"Stapel – A{self.a} + A{self.b}")
        self.g("switch", "-q", "main")

    def test_spitze_deckt_den_stapel_und_den_versions_commit(self):
        self.gruen(self.a, "zweig-a", self.einzel_a)
        self.gruen(self.b, "zweig-b", self.einzel_b)
        self.gruen(self.a, "stapel", self.spitze)                                            # Lead prüft den Stapel (wie P482)
        betrieb.freigabe_merge(self.con, self.pid, "TL", self.a, "stapel")
        betrieb.freigabe_merge(self.con, self.pid, "TL", self.b, "zweig-b")                  # geht mit der Übertragung mit
        aus = self.kette().uebertragen(self.spitze, "stapel")
        self.assertEqual(len(aus), 1, aus)                                                    # B: gleicher Inhalt, A: nicht
        self.assertTrue(self.con.execute("SELECT 1 FROM pruefung WHERE aufgabe_id = ? AND sha = ? AND ergebnis = 'gruen'",
                                         (self.b, self.innen_b)).fetchone())
        self.assertEqual(self.kette().staende(self.spitze), [])
        self.sha = self.spitze
        self.gesamtlauf()
        self.assertEqual(self.kette().ausliefern("stapel")["version"], "1.1.0")

    def test_ohne_gruen_auf_der_spitze_haelt_staende(self):
        self.gruen(self.a, "zweig-a", self.einzel_a)
        self.gruen(self.b, "zweig-b", self.einzel_b)
        self.assertEqual(self.kette().uebertragen(self.spitze, "stapel"), [])                 # A ungeprüft darunter: nichts
        self.assertTrue(self.kette().staende(self.spitze))


if __name__ == "__main__":
    unittest.main()
