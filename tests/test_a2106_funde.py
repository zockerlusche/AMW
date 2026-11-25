"""A2106: Funde der Vorführung mit echtem Arbeiter (D1856) – die Dateien des Versions-Commits zählen nicht als Arbeit des Pakets, der Verlauf
zählt Pakete statt Prüfungen, „bereit zur Abnahme“ kommt je Empfänger einmal, Einzahl, „Fertig, wenn:“ nicht doppelt."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import re
import unittest
from unittest import mock

from amw import abschluss, belege, buendel, db, kern, planung, projektweg_seite, themen
from tests import test_a2077_verlauf, test_a2098_fertig_wenn, test_buendel, test_projektweg_seite
from tests.rundgang import Rundgang
from tests.test_mergeliste import g


class Buendel(test_buendel.Basis):
    """Der echte Weg: zwei Headless-Pakete, ein Bündel der AMW mit Versions-Commit, ausgeliefert nach main."""
    def setUp(self):
        super().setUp()
        self.a = self.paket("plus reparieren", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"}, 1, hinweis="Plus rechnet jetzt richtig.", gruppe="neu")
        self.b = self.paket("minus dazu", {"lib/minus.py": "def minus(a, b):\n    return a - b\n"}, 2)
        r = buendel.buendeln(self.con, self.pid, "TL", starten=False)
        self.sha = r["sha"]
        g(self.repo, "merge", "-q", "--ff-only", r["zweig"])
        th = themen.neu(self.con, self.pid, "TL", "Rechnen", pfleger="CC1")
        self.m = planung.bogen_neu(self.con, self.pid, "TL", "Rechnen", ziel=f"TH{th} Rechnen", abnahme="plus geht; Vorführung")
        with db.schreiben(self.con):                                                        # wie die Auslieferung: Beleg = Versions-Commit
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = ?, bogen_id = ?, fertig_utc = ? WHERE id IN (?, ?)", (self.sha[:7], self.m, db.jetzt(), self.a, self.b))
        for aid in (self.a, self.b):
            themen.verweise_setzen(self.con, self.pid, "TL", aid, [th])
        self.th = th

    def test_nur_die_dateien_des_pakets(self):
        self.assertIn("CHANGELOG.md", g(self.repo, "show", "--name-only", "--format=", self.sha))         # der Versions-Commit ändert ihn
        bef = belege.meilenstein(self.con, self.pid, self.m)
        p = {x["paket"]: x for x in bef["pakete"]}
        self.assertEqual((p[self.a]["befund"], p[self.a]["sha"], p[self.a]["dateien"]), ("ok", self.sha, ["lib/rechnen.py"]))
        self.assertEqual(p[self.b]["dateien"], ["lib/minus.py"])
        self.assertEqual([len(p[x]["commits"]) for x in (self.a, self.b)], [1, 1])
        self.assertEqual(belege.auswerten(bef, [self.th], {"befehl": "x", "rc": 0})["vorbehalte"], [])

    def test_der_pruefer_sieht_sie_auch_nicht(self):
        gesehen = {}

        def attrappe(p, *_a, **_k):
            with open(os.path.join(p["klon"], "pakete.md"), encoding="utf-8") as f:
                gesehen["pakete"] = f.read()
            return {"rc": 0, "abweichungen": [], "ergebnis": {"result": "{}", "total_cost_usd": 0.0}}
        with mock.patch("amw.arbeiter.laufen", attrappe):
            abschluss.pruefer(self.con, self.pid, self.con.execute("SELECT * FROM bogen WHERE id = ?", (self.m,)).fetchone(), {"befehl": None}, bef=belege.meilenstein(self.con, self.pid, self.m))
        self.assertIn("Geänderte Dateien: lib/rechnen.py\n", gesehen["pakete"])
        self.assertNotIn("CHANGELOG.md", gesehen["pakete"])

    def test_beleg_der_kein_versions_commit_ist_zaehlt_mit(self):
        with open(os.path.join(self.repo, "lib", "nach.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write("X = 1\n")
        g(self.repo, "add", "-A")
        g(self.repo, "commit", "-q", "-m", "Nachtrag ohne Nummer")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET beleg = ? WHERE id = ?", (g(self.repo, "rev-parse", "HEAD"), self.a))
        p = next(x for x in belege.meilenstein(self.con, self.pid, self.m)["pakete"] if x["paket"] == self.a)
        self.assertEqual(p["dateien"], ["lib/rechnen.py", "lib/nach.py"])


class Verlauf(test_a2077_verlauf.Grund):
    def pruefung(self, aid, sek, ergebnis="gruen"):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=aid, zweig="z", sha=f"{sek:040d}", bauer="AMW", pruefer="TL", ergebnis=ergebnis,
                         angefragt_utc=test_a2077_verlauf.z(8, 0, sek), ergebnis_utc=test_a2077_verlauf.z(8, 0, sek))

    def test_mehrere_pruefungen_eines_pakets_sind_ein_paket(self):
        a = self.paket("plus reparieren")
        self.ereignis("paket_ergebnis", test_a2077_verlauf.z(8, 0, 5), aufgabe=a, quelle="p")      # Headless: die Abgabe steht einmal da
        for s in (8, 11, 12):                                                               # wie in D1846: Prüfung C, übernommen, Bündel
            self.pruefung(a, s)
        self.assertEqual([x for x in self.zeilen() if "Prüfung grün" in x], ["M1: Prüfung grün – „plus reparieren“"])
        b = self.paket("minus dazu")
        self.ereignis("paket_ergebnis", test_a2077_verlauf.z(8, 0, 6), aufgabe=b, quelle="p")
        self.pruefung(b, 14)
        self.pruefung(a, 15)
        z = [e for e in self.v("umsetzung") if "Prüfung grün" in e["zeile"]]
        self.assertEqual([e["zeile"] for e in z], ["M1: Prüfung grün – 2 Pakete"])
        self.assertEqual((z[0]["lang"].count("plus reparieren"), z[0]["lang"].count("minus dazu")), (1, 1))


class Meldung(test_a2098_fertig_wenn.Grund):
    FERTIG = "Vorführung beim Menschen"

    def test_bereit_zur_abnahme_je_empfaenger_einmal(self):
        """Zwei Nachrichten sind zwei Empfänger (Lead und Mensch) – dieselbe Meldung zweimal an einen gibt es nicht."""
        self.alt_bereit()
        self.laufen(self.mit(beleg="da"))
        for _ in range(4):
            self.runde()
        wer = [r[0] for r in self.con.execute("SELECT e.agent FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE n.kurz LIKE '%bereit zur Abnahme%' ORDER BY e.agent")]
        self.assertEqual(wer, sorted([kern.ENTWICKLER, "TL"]))


class Vorsatz(test_a2098_fertig_wenn.Grund):
    FERTIG = "plus(2, 2) ergibt 4"

    def test_nur_die_anzeige(self):
        e = self.laufen(self.mit(beleg="Fertig, wenn: plus(2, 2) ergibt 4 (lib/rechnen.py Z.2)"))
        self.assertTrue(e["ziel"]["beleg"].startswith("Fertig, wenn: "))                    # der Text des Prüfers bleibt
        self.assertEqual(abschluss.ohne_vorsatz(e["ziel"])["beleg"], "plus(2, 2) ergibt 4 (lib/rechnen.py Z.2)")
        self.alt_bereit()
        x, _, _ = self.karte()
        self.assertEqual(x["pruefung"]["ziel"]["beleg"], "plus(2, 2) ergibt 4 (lib/rechnen.py Z.2)")
        self.assertIn("- „Fertig, wenn“: erfüllt – plus(2, 2) ergibt 4 (lib/rechnen.py Z.2)", abschluss.bericht_teil(self.con, self.pid, self.m))

    def test_faelle(self):
        for vorher, nachher in (("Fertig, wenn: x", "x"), ("„Fertig, wenn“: x", "x"), ("fertig wenn – x", "x"), ("Done when: x", "x"),
                                ("Fertig ist es, wenn x", "Fertig ist es, wenn x"), ("Alles da. Fertig, wenn: x", "Alles da. Fertig, wenn: x")):
            self.assertEqual(abschluss.ohne_vorsatz({"beleg": vorher, "fehlt": None}), {"beleg": nachher, "fehlt": None}, vorher)
        self.assertIsNone(abschluss.ohne_vorsatz(None))


class Einzahl(Rundgang):
    """Jeder Text mit Einzahl nimmt sie genau bei 1 – im Browser, mit dem Skript der Seite."""
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1") if not self.con.execute("SELECT 1 FROM agent WHERE projekt_id = ? AND kennung = 'CC1'", (self.pid,)).fetchone() else None
        test_projektweg_seite.demo(self.con, self.pid, "abschluss-ohne")

    def test_texte(self):
        self.oeffnen("projektweg", "document.querySelector('.pjw-schritt')")
        for k, v, eins, zwei in (("pjw_w_grob_ok", "", "1 Meilenstein · freigegeben", "2 Meilensteine · freigegeben"), ("pjw_w_grob_bestand", "", "Bestand · 1 Meilenstein", "Bestand · 2 Meilensteine"),
                                 ("pjw_laeuft_jetzt", "", "läuft gerade", "laufen gerade"), ("pjw_fertige_pakete", "", "1 fertiges Paket", "2 fertige Pakete"),
                                 ("pjw_test_gruen", ", { l: 3 }", "Gesamttest grün (L3) · 1 Paket", "Gesamttest grün (L3) · 2 Pakete")):
            self.assertEqual([self.tab.js(f"pwN('{k}', {n}{v})") for n in (1, 2)], [eins, zwei], k)
        self.assertEqual(self.tab.js("pwN('pjw_laeuft_jetzt', 0)"), "laufen gerade")



class EinzahlTexte(unittest.TestCase):
    def test_jede_einzahl_hat_beide_sprachen(self):
        wurzel = os.path.join(os.path.dirname(projektweg_seite.__file__), "workbench")
        t = {}
        for s in ("de", "en"):
            with open(os.path.join(wurzel, "texte", f"{s}.json"), encoding="utf-8") as f:
                t[s] = json.load(f)
        with open(os.path.join(wurzel, "skript", "08-wissen.js"), encoding="utf-8") as f:
            schluessel = set(re.findall(r'pwN\("(\w+)"', f.read()))
        self.assertEqual(len(schluessel), 7)
        for k in schluessel:
            for s in t:
                self.assertIn(k + "1", t[s], (k, s))
                self.assertNotIn("{n}", t[s][k + "1"])
