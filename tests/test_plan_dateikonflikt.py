"""A2133: kein Plan mit derselben Datei in zwei Paketen, die gleichzeitig laufen können – ein Fund mit beiden Schlüsseln und der Datei,
im Planer je Thema und im Feinplaner; nacheinander (auch mittelbar) ist es erlaubt."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import unittest
from unittest import mock

from amw import feinplanung, planer
from tests import test_a2031_feinplanung as a2031


def paket(s, bereiche, nach=(), m="M1", **mehr):
    return {"schluessel": s, "meilenstein": m, "titel": f"Paket {s}", "auftrag": "Bauen.", "groesse": "S", "art": "mechanisch", "ausfuehrung": "agent",
            "interaktiv_grund": "Erkundung", "fertig_quelle": "commit", "nach": list(nach), "bereiche": bereiche, **mehr}


def funde(*pakete, ms=("M1",)):
    try:
        planer.pruefen({"nichts_zu_bauen": False, "meilensteine": [{"schluessel": m, "titel": f"Teil {m}", "endet_mit": "bericht"} for m in ms],
                        "pakete": list(pakete)})
    except planer.PlanFehler as e:
        return e.fehler
    return []


class Planer(unittest.TestCase):
    def test_gleichzeitig_dieselbe_datei(self):
        f = funde(paket("P1", "app/a.py, app/b.py"), paket("P2", "app/c.py; app/b.py"))
        self.assertEqual(len(f), 1, f)
        for teil in ("P1", "P2", "app/b.py"):
            self.assertIn(teil, f[0])
        self.assertNotIn("app/a.py", f[0])

    def test_ordner_und_gross_klein(self):
        for a, b, genannt in (("app/", "app/teil/x.py", "app/teil/x.py"), ("app/teil/*", "app/teil/x.py", "app/teil/x.py"), ("App/A.py", "app/a.py", "a.py")):
            f = funde(paket("P1", a), paket("P2", b))
            self.assertEqual(len(f), 1, (a, b, f))
            self.assertIn(genannt, f[0].lower())

    def test_nacheinander_ist_erlaubt(self):
        self.assertEqual(funde(paket("P1", "app/a.py"), paket("P2", "app/a.py", ["P1"])), [])
        self.assertEqual(funde(paket("P2", "app/a.py", ["P1"]), paket("P1", "app/a.py")), [])                # die Reihenfolge in der Liste ist egal

    def test_mittelbar_ist_erlaubt(self):
        self.assertEqual(funde(paket("P1", "app/a.py"), paket("P2", "app/b.py", ["P1"]), paket("P3", "app/a.py", ["P2"])), [])

    def test_gemeinsamer_vorgaenger_reicht_nicht(self):
        f = funde(paket("P0", "app/z.py"), paket("P1", "app/a.py", ["P0"]), paket("P2", "app/a.py", ["P0"]))
        self.assertEqual(len(f), 1, f)
        self.assertNotIn("P0", f[0])

    def test_jedes_paar_einmal(self):
        f = funde(paket("P1", "app/a.py"), paket("P2", "app/a.py"), paket("P3", "app/a.py, app/a.py"))
        self.assertEqual(len(f), 3, f)

    def test_auch_ueber_meilensteine(self):
        self.assertEqual(len(funde(paket("P1", "app/a.py"), paket("P2", "app/a.py", m="M2"), ms=("M1", "M2"))), 1)

    def test_ohne_bereiche_und_verschiedene_dateien(self):
        self.assertEqual(funde(paket("P1", None), paket("P2", None)), [])
        self.assertEqual(funde(paket("P1", "app/a.py"), paket("P2", "app/b.py")), [])

    def test_im_kreis_bleibt_es_beim_kreis(self):
        f = funde(paket("P1", "app/a.py", ["P2"]), paket("P2", "app/a.py", ["P1"]))
        self.assertTrue(any("Kreis" in x for x in f), f)

    def test_der_planer_kennt_die_regel(self):
        self.assertIn("ändern nie dieselben Dateien", " ".join((planer.__doc__ or "").split()))


class Feinplaner(unittest.TestCase):
    setUp = a2031.Feinplaner.setUp

    def plan(self, nach):
        nr = self.con.execute("SELECT nr FROM bogen WHERE id = ?", (self.m1,)).fetchone()[0]
        ps = [paket("P1", "app/a.py", m=f"M{nr}", thema=f"TH{self.t1}"), paket("P2", "app/a.py", nach, m=f"M{nr}", thema=f"TH{self.t1}")]
        try:
            return feinplanung.pruefen({"pakete": ps}, self.con, self.pid, [self.m1]), None
        except planer.PlanFehler as e:
            return None, e.fehler

    def test_gleichzeitig_und_nacheinander(self):
        e, f = self.plan([])
        self.assertIsNone(e)
        treffer = [x for x in f or [] if "app/a.py" in x]
        self.assertEqual(len(treffer), 1, f)
        self.assertIn("P1", treffer[0])
        self.assertIn("P2", treffer[0])
        e, f = self.plan(["P1"])
        self.assertIsNone(f)
        self.assertTrue(e)


class Nachbesserung(unittest.TestCase):
    """Der Fund geht wie jeder andere in die eine Nachbesserung."""
    def test_einmal_mit_dem_fund(self):
        falsch = json.dumps({"nichts_zu_bauen": False, "meilensteine": [{"schluessel": "M1", "titel": "Teil", "endet_mit": "bericht"}],
                             "pakete": [paket("P1", "app/a.py"), paket("P2", "app/a.py")]})
        gut = json.dumps({"nichts_zu_bauen": False, "meilensteine": [{"schluessel": "M1", "titel": "Teil", "endet_mit": "bericht"}],
                          "pakete": [paket("P1", "app/a.py"), paket("P2", "app/a.py", ["P1"])]})
        rufe = []

        def planen(con, pid, t, fassung, modell, prog=None, zusatz=None, nachbessern=None):
            rufe.append(nachbessern)
            return {"ergebnis": gut if nachbessern else falsch, "usd": 0.1, "fehler": None}
        echt = planer.pruefen
        with mock.patch.object(planer, "planen", planen), mock.patch.object(planer, "pruefen", lambda d, *a, **k: echt(d)),                 mock.patch.object(planer, "tagesgrenze", return_value=None), mock.patch.object(planer, "heute_usd", return_value=0),                 mock.patch.object(planer, "schalter_text", return_value=None), mock.patch.object(planer, "einstellung", return_value="an"),                 mock.patch.dict(os.environ, {"AMW_PLANER_AUS": ""}):
            planer.planen_mit_nachbesserung(None, 1, {"id": 1, "name": "x"}, 1, "sonnet")
        self.assertEqual(len(rufe), 2)
        self.assertTrue(any("app/a.py" in x for x in rufe[1]["funde"]), rufe[1])


if __name__ == "__main__":
    unittest.main()
