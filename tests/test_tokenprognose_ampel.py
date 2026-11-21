"""Token-Pause in der Ampel: ampel_mit_pause (grün/gelb/rot gegen das Zieldatum, *_mit vor dem Rohwert), mit_pause
(ergänzt die Prognose-Daten, ohne Lage bleibt alles, wie es war) und als_daten (Zeiten als ISO-Text, None bleibt None)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import copy
import datetime
import unittest

from amw import tokenprognose as tp

UTC = datetime.timezone.utc


def t(tag, stunde=0, minute=0):
    return datetime.datetime(2026, 11, tag, stunde, minute, tzinfo=UTC)


JETZT = t(1)


def lage():
    """Leer am 3., Reset am 8., danach je Woche 2 Tage Arbeit und 5 Tage Pause."""
    return {"wert": 60.0, "gemessen_utc": t(1), "reset_utc": t(8), "letzter_reset_utc": t(1) - datetime.timedelta(days=7),
            "tempo": 20.0, "tempo_vorsichtig": 25.0, "arbeitstage": 5, "leer_utc": t(3), "pause_tage": 5.0,
            "arbeitstage_je_woche": 2.0, "pause_je_woche": 5.0, "unsicher": None}


class AmpelMitPause(unittest.TestCase):
    def test_gruen_wenn_das_sichere_datum_haelt(self):
        p = {"p50": "2026-11-10", "p85": "2026-11-15"}
        self.assertEqual(tp.ampel_mit_pause(p, "2026-11-15"), "gruen")
        self.assertEqual(tp.ampel_mit_pause(p, "2026-11-20"), "gruen")

    def test_gelb_wenn_nur_das_wahrscheinliche_haelt(self):
        p = {"p50": "2026-11-10", "p85": "2026-11-15"}
        self.assertEqual(tp.ampel_mit_pause(p, "2026-11-10"), "gelb")
        self.assertEqual(tp.ampel_mit_pause(p, "2026-11-14"), "gelb")

    def test_rot_wenn_auch_das_wahrscheinliche_nicht_haelt(self):
        p = {"p50": "2026-11-10", "p85": "2026-11-15"}
        self.assertEqual(tp.ampel_mit_pause(p, "2026-11-09"), "rot")

    def test_ohne_zieldatum_keine_ampel(self):
        p = {"p50": "2026-11-10", "p85": "2026-11-15"}
        self.assertIsNone(tp.ampel_mit_pause(p, None))
        self.assertIsNone(tp.ampel_mit_pause(p, ""))

    def test_mit_pause_geht_vor_dem_rohwert(self):
        # ohne Pause wäre es grün; mit Pause hält nur das wahrscheinliche Datum
        p = {"p50": "2026-11-10", "p85": "2026-11-12", "p50_mit": "2026-11-13", "p85_mit": "2026-11-20"}
        self.assertEqual(tp.ampel_mit_pause(p, "2026-11-15"), "gelb")
        self.assertEqual(tp.ampel_mit_pause(p, "2026-11-12"), "rot")
        self.assertEqual(tp.ampel_mit_pause(p, "2026-11-20"), "gruen")

    def test_nur_ein_mit_wert_der_andere_bleibt_roh(self):
        p = {"p50": "2026-11-10", "p85": "2026-11-12", "p85_mit": "2026-11-20"}
        self.assertEqual(tp.ampel_mit_pause(p, "2026-11-15"), "gelb")      # p85_mit zählt, p50 roh
        p = {"p50": "2026-11-10", "p85": "2026-11-12", "p50_mit": "2026-11-16"}
        self.assertEqual(tp.ampel_mit_pause(p, "2026-11-12"), "gruen")     # p85 roh hält
        self.assertEqual(tp.ampel_mit_pause(p, "2026-11-11"), "rot")       # p50_mit hält nicht


class MitPause(unittest.TestCase):
    def test_ohne_lage_unveraendert(self):
        for leer in (None, {}):
            prognose = [{"p50": "2026-11-20", "p85": "2026-11-30"}, {"p50": "2026-12-05"}]
            vorher = copy.deepcopy(prognose)
            self.assertIsNone(tp.mit_pause(leer, prognose, JETZT))
            self.assertEqual(prognose, vorher)

    def test_vor_leer_keine_pause(self):
        prognose = [{"p50": "2026-11-02", "p85": "2026-11-02"}]
        tp.mit_pause(lage(), prognose, JETZT)
        self.assertEqual(prognose, [{"p50": "2026-11-02", "p85": "2026-11-02"}])

    def test_ergaenzt_pause_und_mit_daten_rohwerte_bleiben(self):
        # p50 am 4.: einen Tag nach „leer“ → Pause bis zum Reset (5 Tage); p85 am 6.: dazu eine Folgewoche (10 Tage)
        prognose = [{"p50": "2026-11-04", "p85": "2026-11-06"}]
        tp.mit_pause(lage(), prognose, JETZT)
        self.assertEqual(prognose, [{"p50": "2026-11-04", "p85": "2026-11-06", "pause_tage": 5,
                                     "p50_mit": "2026-11-09", "p85_mit": "2026-11-16"}])

    def test_ohne_p85_nur_p50(self):
        prognose = [{"p50": "2026-11-04"}]
        tp.mit_pause(lage(), prognose, JETZT)
        self.assertEqual(prognose, [{"p50": "2026-11-04", "pause_tage": 5, "p50_mit": "2026-11-09"}])

    def test_ungueltiges_datum_bleibt_ohne_pause(self):
        prognose = [{"p50": None}, {"p50": "kein Datum"}]
        tp.mit_pause(lage(), prognose, JETZT)
        self.assertEqual(prognose, [{"p50": None}, {"p50": "kein Datum"}])


class AlsDaten(unittest.TestCase):
    def test_none_bleibt_none(self):
        self.assertIsNone(tp.als_daten(None))
        self.assertIsNone(tp.als_daten({}))

    def test_zeiten_als_iso_text_rest_unveraendert(self):
        roh = lage()
        roh["leer_utc"] = datetime.datetime(2026, 11, 3, 14, 5, 9, 123456, tzinfo=UTC)
        daten = tp.als_daten(roh)
        self.assertEqual(daten["gemessen_utc"], "2026-11-01T00:00:00Z")
        self.assertEqual(daten["reset_utc"], "2026-11-08T00:00:00Z")
        self.assertEqual(daten["letzter_reset_utc"], "2026-10-25T00:00:00Z")
        self.assertEqual(daten["leer_utc"], "2026-11-03T14:05:09Z")
        for k in ("wert", "tempo", "tempo_vorsichtig", "arbeitstage", "pause_tage", "arbeitstage_je_woche",
                  "pause_je_woche", "unsicher"):
            self.assertEqual(daten[k], roh[k])
        self.assertEqual(set(daten), set(roh))

    def test_fehlende_zeiten_bleiben_none(self):
        roh = lage()
        roh.update(reset_utc=None, letzter_reset_utc=None, leer_utc=None, unsicher="kein_tempo", tempo=None)
        daten = tp.als_daten(roh)
        self.assertIsNone(daten["reset_utc"])
        self.assertIsNone(daten["letzter_reset_utc"])
        self.assertIsNone(daten["leer_utc"])
        self.assertIsNone(daten["tempo"])
        self.assertEqual(daten["gemessen_utc"], "2026-11-01T00:00:00Z")

    def test_eingabe_bleibt_unveraendert(self):
        roh = lage()
        vorher = copy.deepcopy(roh)
        tp.als_daten(roh)
        self.assertEqual(roh, vorher)


if __name__ == "__main__":
    unittest.main()
