"""Halt beim Wochenlimit (A1888): Schwelle erreicht → Halt aller Coder + Meldung; Einstellung limit_halt (Vorgabe 95, leer = aus,
nur Lead/Mensch); Aufheben von Hand (dann diese Woche kein neuer Halt) und von selbst unter der Schwelle bzw. wenn aus."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import tempfile
import unittest
from unittest import mock

from amw import db, einstellungen, kern, limithalt

WOCHE1, WOCHE2 = "2026-11-14 07:00:00", "2026-11-21 07:00:00"


class LimitHalt(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"LOCALAPPDATA": os.path.join(self.ordner.name, "lad")})   # A1925: eigene PC-Einstellungen
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        for k, r in (("TL", "lead"), ("CC1", None), ("CC2", None), ("CC3", None)):
            kern.agent_neu(self.con, self.pid, k, rolle=r)
        with db.schreiben(self.con):
            self.con.execute("UPDATE agent SET soll = 'aus' WHERE kennung = 'CC3'")

    def runde(self, wert, reset=WOCHE1):
        return limithalt.runde(self.con, {"wert": wert, "letzter_reset_utc": reset})

    def gehalten(self):
        return [k for k in ("TL", "CC1", "CC2", "CC3") if kern.halt_gilt(self.con, self.pid, k)]

    def post(self, an, art):
        return [r["kurz"] for r in self.con.execute("SELECT n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id"
                                                    " WHERE n.von = 'AMW' AND e.agent = ? AND n.art = ? ORDER BY n.id", (an, art))]

    def test_schwelle_erreicht_haelt_alle_coder_und_meldet(self):
        self.assertEqual(self.runde(94.0), [])
        self.assertEqual(self.gehalten(), [])
        self.assertEqual(len(self.runde(95.0)), 1)
        self.assertEqual(self.gehalten(), ["CC1", "CC2"])                       # nicht der Lead, nicht der ausgeschaltete
        self.assertEqual(self.post("CC1", "stopp"), ["HALT: Wochenlimit bei 95 % (Schwelle 95 %)"])
        self.assertIn("Wochenlimit-Halt: Wochenlimit bei 95 % (Schwelle 95 %)", self.post("TL", "meldung"))
        text = self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE 'HALT: Wochenlimit%'").fetchone()[0]
        self.assertIn("sauber beenden", text)
        self.assertEqual(self.runde(97.0), [])                                  # schon angehalten: nichts doppelt
        self.assertEqual(len(limithalt.aktive(self.con, self.pid)), 2)

    def test_einstellung_vorgabe_leer_aus_nur_lead(self):
        self.assertEqual(limithalt.schwelle(self.con, self.pid), 95)
        kern.projekt_einstellen(self.con, self.pid, "TL", limit_halt=90)
        self.assertEqual(limithalt.schwelle(self.con, self.pid), 90)
        self.assertEqual(len(self.runde(91.0)), 1)
        for leer in ("", None, 0, "aus"):                                     # A1925 (E4): das Projekt schaltet nicht ab –
            kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, limit_halt=leer)
            self.assertEqual(limithalt.schwelle(self.con, self.pid), 95, leer)  # es gilt der PC-Wert
        kern.projekt_einstellen(self.con, self.pid, "TL", limit_halt=97)          # weniger streng: zählt nicht
        self.assertEqual(limithalt.schwelle(self.con, self.pid), 95)
        einstellungen.speichern({"limit_halt": 0})                               # PC aus …
        self.assertEqual(limithalt.schwelle(self.con, self.pid), 97)             # … dann gilt das Projekt
        kern.projekt_einstellen(self.con, self.pid, "TL", limit_halt="")
        self.assertIsNone(limithalt.schwelle(self.con, self.pid))
        with self.assertRaisesRegex(kern.AmwFehler, "Prozent 1–100"):
            kern.projekt_einstellen(self.con, self.pid, "TL", limit_halt=101)
        with self.assertRaisesRegex(kern.AmwFehler, "nur Lead und Entwickler"):
            kern.projekt_einstellen(self.con, self.pid, "CC1", limit_halt=80)

    def test_aus_setzt_keinen_halt_und_hebt_auf(self):
        self.runde(99.0)
        einstellungen.speichern({"limit_halt": 0})                               # A1925: aus ist eine PC-Einstellung
        self.assertEqual(self.runde(99.0), [f"P{self.pid}: Halt aufgehoben (Halt beim Wochenlimit ist aus)"])
        self.assertEqual(self.gehalten(), [])
        self.assertEqual(self.runde(99.0), [])

    def test_von_hand_aufheben_dann_diese_woche_kein_neuer_halt(self):
        self.runde(96.0)
        self.assertEqual(kern.weiter(self.con, self.pid, "TL", "alle"), 2)       # amw weiter (Vorgabe alle) hebt sie auf
        self.assertEqual(self.gehalten(), [])
        self.assertEqual(self.runde(98.0), [])                                  # gleiche Woche: bleibt aufgehoben
        self.assertEqual(self.gehalten(), [])
        self.assertEqual(len(self.runde(96.0, reset=WOCHE2)), 1)                 # neue Woche, wieder über der Schwelle
        self.assertEqual(self.gehalten(), ["CC1", "CC2"])

    def test_von_selbst_nach_dem_wochenwechsel(self):
        self.runde(96.0)
        self.assertEqual(self.runde(None), [])                                  # ohne Messung bleibt der Halt
        self.assertEqual(self.gehalten(), ["CC1", "CC2"])
        self.assertEqual(self.runde(3.0, reset=WOCHE2), [f"P{self.pid}: Halt aufgehoben (Wochenlimit bei 3 % – unter 95 %)"])
        self.assertEqual(self.gehalten(), [])
        self.assertEqual(self.post("CC2", "freigabe"), ["WEITER: Wochenlimit bei 3 % – unter 95 %"])
        self.assertEqual(self.post("TL", "info"), ["Halt beim Wochenlimit aufgehoben: Wochenlimit bei 3 % – unter 95 %"])

    def test_fremder_halt_bleibt_unberuehrt(self):
        kern.halt(self.con, self.pid, "TL", "CC1", "Bitte warten")
        self.runde(3.0, reset=WOCHE2)
        self.assertEqual(self.gehalten(), ["CC1"])


if __name__ == "__main__":
    unittest.main()
