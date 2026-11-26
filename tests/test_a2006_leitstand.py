"""A2006: Leitstand (Startseite) – Daten: Zeitplan je Meilenstein (Ziel gegen voraussichtlich), eigener Abruf /api/leitstand,
online nur die Entscheidungen des eigenen Projekts."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json

from amw import abgleich, db, einmal, workbench
from tests import test_leitstand_daten as _tld
from tests.test_leitstand_daten import Grund, um

OBERGRENZE = 60                 # Abfragen je Abruf am festen Bestand der Leistungsprobe (gemessen 46–47, mit Luft)


class Zeitplan(Grund):
    def test_offene_meilensteine_mit_ziel_und_prognose(self):
        m1 = self.meilenstein("Laden", ziel="2026-11-20")
        m2 = self.meilenstein("Kasse", status="geplant")
        fertig = self.meilenstein("Alt")
        for i in range(3):
            self.paket(f"Laden {i}", "CC1", bogen=m1)
        self.paket("Kasse 1", bogen=m2)
        with db.schreiben(self.con):
            self.con.execute("UPDATE bogen SET status = 'fertig' WHERE id = ?", (fertig,))
        z = self.d()["zeitplan"]
        nr = {r[0]: r[1] for r in self.con.execute("SELECT id, nr FROM bogen")}
        self.assertEqual([x["nr"] for x in z], sorted([nr[m1], nr[m2]]))                          # fertige fehlen
        a = next(x for x in z if x["nr"] == nr[m1])
        self.assertEqual((a["titel"], a["ziel"], a["bereit"]), ("Laden", "2026-11-20", False))
        self.assertTrue(a["start"] and a["p50"] and a["p85"] and a["p50"] <= a["p85"])
        self.assertGreater(a["verzug_tage"], 0)                                                     # Ziel liegt vor heute
        self.assertIsNone(next(x for x in z if x["nr"] == nr[m2])["verzug_tage"])                   # ohne Ziel kein Verzug

    def test_bereit_wenn_alle_pakete_fertig(self):
        m = self.meilenstein("Laden")
        self.fertig("Laden 1", -30, bogen=m)
        self.paket("Laden 2", "CC1", bogen=m)
        vorher = [x["bereit"] for x in self.d()["zeitplan"]]
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', fertig_utc = ?, beleg = 'abc1234' WHERE titel = 'Laden 2'", (um(-1),))
        self.assertEqual(vorher, [False])
        self.assertEqual([x["bereit"] for x in self.d()["zeitplan"]], [True] if self.d()["zeitplan"] else [])


class Abruf(Grund):
    def test_eigener_weg_und_json(self):
        self.paket("Anmeldung", "CC1", bogen=self.meilenstein("Laden"))
        d = workbench.daten_leitstand(self.con, self.pid)
        self.assertEqual(set(d), {"fortschritt", "zuletzt", "jetzt", "als_naechstes", "entscheidungen", "zeitplan"})
        json.dumps(d)
        self.assertNotIn("leitstand", workbench.daten_start(self.con, self.pid))                  # nicht im 15-s-Takt

    def test_online_nur_eigene_entscheidungen(self):
        fremd = self.projekt("Geheim")
        a = self.paket("Eigen", "CC1")
        b = self.paket("Fremd", "CC1", pid=fremd)
        self.ereignis("verteilt", um(-2), {"aufgabe": a, "agent": "CC1", "grund": "Rang"}, aufgabe=a)
        self.ereignis("verteilt", um(-1), {"aufgabe": b, "agent": "CC1", "grund": "Rang"}, aufgabe=b, pid=fremd)
        pc = workbench.daten_leitstand(self.con, self.pid)["entscheidungen"]
        self.assertEqual({e["projekt"] for e in pc}, {"Laden", "Geheim"})                          # am PC alle Projekte
        online = abgleich.ansichten(self.con, self.pid)["/api/leitstand"]["entscheidungen"]
        self.assertEqual({e["projekt"] for e in online}, {"Laden"})
        self.assertNotIn("Geheim", json.dumps(abgleich.ansichten(self.con, self.pid)["/api/leitstand"], ensure_ascii=False))


class Obergrenze(_tld.Leistung):
    """Lead #34060 (3): /api/leitstand fragt die Datenbank gleich oft bei 20 und bei 400 Paketen, mit fester Obergrenze."""
    def test_hoechstens_zwoelf_und_gleich_viele_bei_20_und_400(self):
        self.skipTest("geerbt – läuft in test_leitstand_daten")

    def alle(self):
        n = []
        self.con.set_trace_callback(n.append)
        try:
            with einmal.merken(self.con, schnappschuss=True):              # wie der Dienst je Anfrage (workbench._get, A2081)
                workbench.daten_leitstand(self.con, self.pid)
        finally:
            self.con.set_trace_callback(None)
        return len(n)

    def test_gleich_viele_bei_20_und_400(self):
        """Die Pakete zählen nicht mit (vor der Bündelung: 69 → 542). fuellen legt je Aufruf einen Meilenstein an; je Meilenstein liest
        die Prognose ihr Zieldatum (planung.prognose – die fasst A2006 nicht an), das ist höchstens eine Abfrage mehr."""
        boegen = lambda: self.con.execute("SELECT count(*) FROM bogen").fetchone()[0]
        self.fuellen(20)
        klein, m_klein = self.alle(), boegen()
        self.fuellen(380)
        gross, m_gross = self.alle(), boegen()
        self.assertLessEqual(gross, klein + (m_gross - m_klein))                   # wächst nicht mit den Paketen (das Wochenlimit
        self.assertGreaterEqual(gross, klein - 2)                                  # merkt sich zwischen zwei Abrufen eine Abfrage)
        self.assertLessEqual(gross, OBERGRENZE)


class Gebuendelt(Grund):
    """Die zwei Einzelabfragen hinter /api/leitstand (Reihenfolge des Zeitplans): offene Wartegründe je Aufgabe und Paket-Entscheidungen
    je Paket – mit Merker einmal je Anfrage, Ergebnis gleich, Geschriebenes sofort sichtbar."""
    def test_wartegruende_gleich_und_sofort_sichtbar(self):
        from amw import wartegrund
        a, b = self.paket("Eins"), self.paket("Zwei")
        wartegrund.anlegen(self.con, self.pid, "TL", a, "TL")
        ohne = [list(map(dict, wartegrund.offene(self.con, x))) for x in (a, b)]
        with einmal.merken(self.con):
            self.assertEqual([list(map(dict, wartegrund.offene(self.con, x))) for x in (a, b)], ohne)
            wartegrund.anlegen(self.con, self.pid, "TL", b, "CC1")                 # in derselben Anfrage geschrieben
            self.assertEqual([g["bezug"] for g in wartegrund.offene(self.con, b)], ["CC1"])

    def test_entscheidungen_gleich_und_sofort_sichtbar(self):
        from amw import eignung
        a = self.paket("Eins", p=True)
        zeile = lambda text: self.ereignis("paket_entscheidung", um(-1), {"zeile": text, "code": "E7"}, aufgabe=a)
        zeile("angenommen")
        ohne = eignung._entscheidungen(self.con, a)
        with einmal.merken(self.con):
            self.assertEqual(eignung._entscheidungen(self.con, a), ohne)
            zeile("noch einmal")
            self.assertEqual(eignung._entscheidungen(self.con, a), ohne + [("noch einmal", "E7")])


if __name__ == "__main__":
    import unittest
    unittest.main()
