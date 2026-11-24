"""A2025: Fortschrittsdaten für gestartete Planer- und Prüfer-Läufe – in der AMW (plan_ereignis art='planer_fortschritt',
ein Eintrag je Lauf, lauf-Nummer als Bezug), gedrosselt geschrieben, je Lauf und als Liste aller laufenden abfragbar."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import db
from amw import planer_fortschritt as pf


class Uhr:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class PlanerFortschritt(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Produkt", angelegt_utc=db.jetzt())
            self.pid2 = db.einfuegen(self.con, "projekt", name="Anderes", angelegt_utc=db.jetzt())
        self.uhr = Uhr()

    def zeilen(self, pid=None):
        return self.con.execute("SELECT * FROM plan_ereignis WHERE projekt_id = ? AND art = ?",
                                (pid or self.pid, pf.ART)).fetchall()

    def st(self, lauf) -> dict:
        s = pf.stand(self.con, self.pid, lauf)
        assert s is not None, f"kein Stand für Lauf {lauf}"
        return s

    def melden(self, lauf, **kw):
        kw.setdefault("uhr", self.uhr)
        return pf.melden(self.con, self.pid, lauf, **kw)

    def test_1_stand_mit_allen_angaben(self):
        self.assertTrue(self.melden(17, art="planer", agent="PL", modell="claude-opus-5-5", einheit="Thema", nr=17, gesamt=50,
                                    dauer_s=600, usd=0.42))
        s = self.st(17)
        self.assertEqual(s["lauf"], 17)
        self.assertEqual(s["art"], "planer")
        self.assertEqual(s["was"], "Thema 17 von 50")
        self.assertEqual(s["agent"], "PL")
        self.assertEqual(s["modell"], "claude-opus-5-5")
        self.assertEqual(s["dauer_s"], 600)
        self.assertAlmostEqual(s["usd"], 0.42)
        self.assertEqual(s["zustand"], "laeuft")
        self.assertIsNone(s["fehler"])
        self.assertEqual(len(self.zeilen()), 1)
        self.assertEqual(self.zeilen()[0]["art"], "planer_fortschritt")

    def test_2_ein_eintrag_je_lauf(self):
        self.melden(5, nr=1, gesamt=3)
        self.uhr.t += 10
        self.melden(5, nr=2, gesamt=3)
        self.uhr.t += 10
        self.melden(6, nr=1, gesamt=2)
        self.assertEqual(len(self.zeilen()), 2)
        self.assertEqual(self.st(5)["was"], "Thema 2 von 3")
        self.assertEqual(self.st(6)["was"], "Thema 1 von 2")
        self.assertIsNone(pf.stand(self.con, self.pid, 7))
        self.assertEqual(self.st(5)["usd"], None)
        self.melden(51, nr=1, gesamt=1)                       # 5 und 51 nicht verwechseln
        self.assertEqual(self.st(5)["was"], "Thema 2 von 3")

    def test_3_gedrosselt_aber_zustandswechsel_sofort(self):
        self.assertTrue(self.melden(9, nr=1, gesamt=50))
        self.uhr.t += 1
        self.assertFalse(self.melden(9, nr=2, gesamt=50))      # zu früh: nicht geschrieben
        self.assertEqual(self.st(9)["was"], "Thema 1 von 50")
        self.uhr.t += pf.TAKT_S
        self.assertTrue(self.melden(9, nr=3, gesamt=50))
        self.assertEqual(self.st(9)["was"], "Thema 3 von 50")
        self.uhr.t += 0.1
        self.assertTrue(self.melden(9, nr=50, gesamt=50, zustand="fertig"))   # Ende immer sofort
        self.assertEqual(self.st(9)["zustand"], "fertig")
        self.uhr.t += 0.1
        self.assertTrue(self.melden(9, nr=1, gesamt=50, sofort=True))

    def test_4_fehler_braucht_klare_meldung(self):
        self.melden(3, agent="PR", modell="m", nr=4, gesamt=10)
        with self.assertRaises(ValueError):
            self.melden(3, zustand="fehler")
        with self.assertRaises(ValueError):
            self.melden(3, zustand="fehler", fehler="   ")
        with self.assertRaises(ValueError):
            self.melden(3, zustand="kaputt")
        self.melden(3, zustand="fehler", fehler="Modell antwortet nicht (Zeitüberschreitung nach 300 s)")
        s = self.st(3)
        self.assertEqual(s["zustand"], "fehler")
        self.assertEqual(s["fehler"], "Modell antwortet nicht (Zeitüberschreitung nach 300 s)")
        self.assertEqual(s["agent"], "PR")                    # frühere Angaben bleiben
        self.assertEqual(s["was"], "Thema 4 von 10")
        self.assertIn("Modell antwortet nicht", pf.zeile(s))

    def test_5_laufende_je_projekt(self):
        self.melden(1, nr=1, gesamt=2)
        self.melden(2, nr=1, gesamt=2)
        self.melden(3, nr=1, gesamt=2)
        self.melden(2, zustand="fertig")
        self.melden(3, zustand="fehler", fehler="kaputt")
        pf.melden(self.con, self.pid2, 4, uhr=self.uhr)
        self.assertEqual([s["lauf"] for s in pf.laufende(self.con, self.pid)], [1])
        self.assertEqual([s["lauf"] for s in pf.laufende(self.con, self.pid2)], [4])
        self.assertEqual(sorted(s["lauf"] for s in pf.alle(self.con, self.pid)), [1, 2, 3])

    def test_6_geschaetzte_dauer_aus_dem_fortschritt(self):
        self.melden(8, nr=0, gesamt=10)
        self.uhr.t += 100
        self.melden(8, nr=5, gesamt=10)
        s = self.st(8)
        self.assertEqual(s["dauer_s"], 200)                   # 5 von 10 in 100 s → ~200 s gesamt
        self.assertEqual(s["seit_s"], 100)

    def test_7_freier_text_und_kosten_summieren_nicht(self):
        self.melden(4, was="Prüfe Abhängigkeiten", usd=0.1)
        self.uhr.t += 10
        self.melden(4, usd=0.3)
        s = self.st(4)
        self.assertEqual(s["was"], "Prüfe Abhängigkeiten")
        self.assertAlmostEqual(s["usd"], 0.3)

    def test_8_text_ist_json_und_geaendert_fuer_den_abgleich(self):
        self.melden(12, nr=1, gesamt=2)
        r = self.zeilen()[0]
        self.assertEqual(json.loads(r["text"])["lauf"], 12)
        with db.schreiben(self.con):
            self.con.execute("UPDATE plan_ereignis SET geaendert_utc = '2000-01-01T00:00:00Z' WHERE id = ?", (r["id"],))
        self.uhr.t += 10
        self.melden(12, nr=2, gesamt=2)
        self.assertNotEqual(self.zeilen()[0]["geaendert_utc"], "2000-01-01T00:00:00Z")

    def test_10_zum_thema_und_schaetzung_aus_frueheren_laeufen(self):
        self.assertIsNone(pf.schaetzung(self.con, self.pid, "planer"))          # ohne Vorbild keine Schätzung
        for lauf, dauer in ((1, 100), (2, 300), (3, 200)):
            self.melden(lauf, art="planer", thema=7)
            self.uhr.t += dauer
            self.melden(lauf, zustand="fertig")
        self.melden(4, art="gegenlesen", thema=7)
        self.uhr.t += 9000
        self.melden(4, zustand="fertig")
        self.melden(5, art="planer", thema=7)
        self.melden(6, art="planer", thema=8)
        self.melden(7, art="planer", thema=7, zustand="fehler", fehler="kaputt")
        self.assertEqual(pf.schaetzung(self.con, self.pid, "planer"), 200)    # Median, nur fertige derselben Art
        self.assertEqual((pf.zum_thema(self.con, self.pid, 7) or {}).get("lauf"), 5)
        self.assertEqual((pf.zum_thema(self.con, self.pid, 8, art="planer") or {}).get("lauf"), 6)
        self.assertIsNone(pf.zum_thema(self.con, self.pid, 7, art="gegenlesen"))
        self.assertIsNone(pf.zum_thema(self.con, self.pid2, 7))
        self.assertEqual(self.st(5)["thema"], 7)

    def test_11_melden_still_haelt_nicht_auf(self):
        with mock.patch.object(pf, "melden", side_effect=RuntimeError("database is locked")):
            self.assertFalse(pf.melden_still(self.con, self.pid, 1, nr=1, gesamt=2))
        self.assertTrue(pf.melden_still(self.con, self.pid, 1, nr=1, gesamt=2, uhr=self.uhr))
        self.assertEqual(self.st(1)["was"], "Thema 1 von 2")

    def test_9_nichts_ausserhalb_des_projekts(self):
        self.assertFalse(hasattr(pf, "LOCALAPPDATA"))
        with open(pf.__file__, encoding="utf-8") as f:
            quelle = f.read()
        self.assertNotIn("LOCALAPPDATA", quelle)
        self.assertNotIn("open(", quelle)


if __name__ == "__main__":
    unittest.main()
