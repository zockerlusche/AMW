"""A2128: Messung vorher/nachher der Umstellung auf das Bündeln ohne Agent – je Tag Tokens, Wartezeit bis zur Auslieferung,
Neustarts; Vergleich der Zeiträume und die Zahlen für den Abschlussbericht."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime
import json
import os
import tempfile
import unittest

from amw import buendel_messung, db, kern

U = datetime.datetime(2026, 11, 20, 12, 0, tzinfo=datetime.timezone.utc)      # Umstellung
JETZT = U + datetime.timedelta(days=7)


def z(tage, stunden=0, minuten=0):
    return (U + datetime.timedelta(days=tage, hours=stunden, minutes=minuten)).strftime("%Y-%m-%dT%H:%M:%SZ")


class Messung(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")

    def ereignis(self, zeit, art, werte, aid=None):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=zeit, von="AMW", art=art, aufgabe_id=aid,
                         text=json.dumps(werte))

    def paket(self, angelegt, begonnen, abgegeben, fertig):
        """Paket mit Zeiten (UTC-Text); abgegeben = erste Prüfbitte."""
        with db.schreiben(self.con):
            aid = db.einfuegen(self.con, "aufgabe", projekt_id=self.pid, titel="P", agent="CC1", einstufung="aktiv", status="fertig",
                               angelegt_utc=angelegt, angelegt_von="TL", begonnen_utc=begonnen, fertig_utc=fertig)
            db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=aid, zweig="z", sha="s" * 40, bauer="CC1",
                         pruefer="TL", angefragt_utc=abgegeben)
        return aid

    def version(self, nr, zeit):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "release", projekt_id=self.pid, art="version", version=nr, zeit_utc=zeit, titel=nr,
                         eingetragen_von="AMW")

    def kosten(self, zeit, **werte):
        self.ereignis(zeit, "kosten", werte, aid=None)

    def daten(self):
        # vorher: zwei Pakete, je 2 h nach der Abgabe bis zur Auslieferung; drei Versionen, zwei davon in einer Kette (ein Neustart)
        self.paket(z(-5, -2), z(-5, -1), z(-5, 0), z(-5, 2))                  # warten 1 h + 2 h
        self.paket(z(-3, -3), z(-3, -2), z(-3, -1), z(-3, 1))                 # warten 1 h + 2 h
        self.version("1.1.0", z(-5, 2))
        self.version("1.1.1", z(-3, 1))
        self.version("1.1.2", z(-3, 1, 5))                                     # Zwischenversion derselben Kette
        self.kosten(z(-5, 0), usd=2.0, eingabe=1000, cache_schreiben=500, cache_lesen=20000, ausgabe=3500)
        self.kosten(z(-3, 0), usd=1.0, unbekannt=True)                         # Lauf ohne Tokens: Lücke, nicht 0
        # nachher: drei Pakete in einem Bündel, je 30 min nach der Abgabe; eine Version
        for i in range(3):
            self.paket(z(2, -2), z(2, -1, i), z(2, 0, i * 10), z(2, 0, 30 + i * 10))
        self.version("1.2.0", z(2, 0, 50))
        self.kosten(z(2, -1), usd=1.5, eingabe=500, cache_schreiben=0, cache_lesen=9000, ausgabe=500)
        self.ereignis(z(0), buendel_messung.buendel_auslieferung.ART, {"schritt": "angestossen"})
        self.ereignis(z(0), buendel_messung.buendel_auslieferung.ART, {"schritt": "ausgeliefert", "version": "1.2.0"})

    def test_umstellung_ist_die_erste_auslieferung_eines_buendels(self):
        self.assertIsNone(buendel_messung.umstellung(self.con, self.pid))
        with self.assertRaises(kern.AmwFehler):
            buendel_messung.vergleich(self.con, self.pid, jetzt=JETZT)
        self.daten()
        self.ereignis(z(3), buendel_messung.buendel_auslieferung.ART, {"schritt": "ausgeliefert"})
        self.assertEqual(buendel_messung.umstellung(self.con, self.pid), z(0))

    def test_je_tag(self):
        self.daten()
        tage = buendel_messung.je_tag(self.con, self.pid, U - datetime.timedelta(days=7), U, JETZT)
        self.assertGreaterEqual(len(tage), 7)                                  # jeder Tag steht da, auch ohne Daten
        self.assertEqual([t["tag"] for t in tage], sorted(t["tag"] for t in tage))
        mit = [t for t in tage if t["pakete"]]
        self.assertEqual([t["pakete"] for t in mit], [1, 1])
        self.assertEqual([t["warten_median_s"] for t in mit], [3 * 3600, 3 * 3600])
        self.assertEqual([t["nach_abgabe_median_s"] for t in mit], [2 * 3600, 2 * 3600])
        self.assertEqual(sum(t["neustarts"] for t in tage), 2)                 # 1.1.1 und 1.1.2: eine Kette
        self.assertEqual(sum(t["versionen"] for t in tage), 3)
        self.assertEqual(sum(t["tokens"]["summe"] for t in tage), 25000)
        self.assertEqual(sum(t["tokens"]["cache_lesen"] for t in tage), 20000)
        self.assertEqual((sum(t["laeufe"] for t in tage), sum(t["laeufe_ohne_tokens"] for t in tage)), (2, 1))
        self.assertEqual(round(sum(t["usd"] for t in tage), 2), 3.0)

    def test_vergleich_vorher_nachher(self):
        self.daten()
        v = buendel_messung.vergleich(self.con, self.pid, jetzt=JETZT)
        a, b = v["vorher"], v["nachher"]
        self.assertEqual(v["umstellung"], z(0))
        self.assertEqual((a["tage"], b["tage"]), (7.0, 7.0))
        self.assertEqual((a["pakete"], b["pakete"]), (2, 3))
        self.assertEqual((a["tokens"], b["tokens"]), (25000, 10000))
        self.assertEqual((a["tokens_je_tag"], b["tokens_je_tag"]), (3571, 1429))
        self.assertEqual((a["tokens_je_paket"], b["tokens_je_paket"]), (12500, 3333))
        self.assertEqual((a["neustarts"], b["neustarts"]), (2, 1))
        self.assertEqual((a["pakete_je_neustart"], b["pakete_je_neustart"]), (1.0, 3.0))
        self.assertEqual((a["nach_abgabe_median_s"], b["nach_abgabe_median_s"]), (7200, 1800))
        self.assertEqual(v["aenderung"]["nach_abgabe_median_s"], -75)
        self.assertEqual(v["aenderung"]["neustarts_je_tag"], -50)
        self.assertEqual(v["aenderung"]["pakete_je_neustart"], 200)
        self.assertTrue(any("1 von 2 Läufen ohne Token-Angabe" in x for x in v["luecken"]))
        self.assertNotIn("_roh", json.dumps(v))                                # nur fertige Zahlen, JSON-fähig

    def test_nachher_kuerzer_als_vorher_und_umstellung_von_hand(self):
        self.daten()
        v = buendel_messung.vergleich(self.con, self.pid, jetzt=U + datetime.timedelta(days=3))
        self.assertEqual(v["nachher"]["tage"], 3.0)
        self.assertEqual(v["nachher"]["neustarts_je_tag"], 0.33)
        self.assertTrue(any("nachher erst 3.0 von 7.0 Tagen" in x for x in v["luecken"]))
        h = buendel_messung.vergleich(self.con, self.pid, umstellung_utc=z(-4), tage=1, jetzt=JETZT)
        self.assertEqual((h["vorher"]["pakete"], h["nachher"]["pakete"]), (1, 0))
        self.assertIsNone(h["aenderung"]["warten_median_s"])                     # nachher kein Paket: keine Änderung
        self.assertTrue(any("nachher: kein ausgeliefertes Paket" in x for x in h["luecken"]))
        with self.assertRaises(kern.AmwFehler):
            buendel_messung.vergleich(self.con, self.pid, umstellung_utc=z(9), jetzt=JETZT)

    def test_bericht(self):
        self.daten()
        t = buendel_messung.bericht(buendel_messung.vergleich(self.con, self.pid, jetzt=JETZT))
        self.assertIn("| Pakete ausgeliefert | 2 | 3 |", t)
        self.assertIn("| Tokens je Tag | 3.571 | 1.429 (-60 %) |", t)
        self.assertIn("| Pakete je Neustart | 1,00 | 3,00 (+200 %) |", t)
        self.assertIn("| abgegeben → ausgeliefert (Median) | 2 h 00 min | 30 min (-75 %) |", t)
        self.assertIn("Lücken:", t)


if __name__ == "__main__":
    unittest.main()
