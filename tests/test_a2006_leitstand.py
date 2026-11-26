"""A2006: Leitstand (Startseite) – Daten: Zeitplan je Meilenstein (Ziel gegen voraussichtlich), eigener Abruf /api/leitstand,
online nur die Entscheidungen des eigenen Projekts."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json

from amw import abgleich, db, workbench
from tests.test_leitstand_daten import Grund, um


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


if __name__ == "__main__":
    import unittest
    unittest.main()
