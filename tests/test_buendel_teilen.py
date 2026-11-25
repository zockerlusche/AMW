"""A2122: rotes Bündel teilen – halbieren, bis das schuldige Paket feststeht. Der Prüfer (Gesamtlauf) ist hier simuliert."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import copy
import unittest

from amw import buendel_teilen as bt
from amw.buendel_zusammensetzen import RELEASE_MAIN


def paket(nr, **mehr):
    return {"id": nr, "titel": f"Paket {nr}", "art": "p", "zweig": f"paket-A{nr}", "kopf": f"{nr:040x}", "agent": "CC1", "gruende": [], **mehr}


def pakete(n):
    return [paket(nr) for nr in range(1, n + 1)]


class Pruefer:
    """Simulierter Gesamtlauf: rot, wenn eine der schuldigen Mengen ganz dabei ist."""
    def __init__(self, *schuldig, basis_rot=False):
        self.schuldig = [{s} if isinstance(s, int) else set(s) for s in schuldig]
        self.basis_rot = basis_rot
        self.laeufe = []

    def __call__(self, teil):
        ids = [p["id"] for p in teil]
        self.laeufe.append(ids)
        rot = [sorted(s) for s in self.schuldig if s <= set(ids)]
        if self.basis_rot or rot:
            return {"ok": False, "meldung": f"FAILED {rot} in {ids}"}
        return {"ok": True, "meldung": "OK"}


class Grund(unittest.TestCase):
    def ids(self, liste):
        return [p["id"] for p in liste]

    def schuldig(self, r):
        return [b["aufgabe"] for b in r["befunde"]]

    def jedes_genau_einmal(self, reihe, r):
        self.assertEqual(sorted(self.ids(r["frei"]) + self.schuldig(r) + self.ids(r["wartet"])), sorted(self.ids(reihe)), r)


class Schuldiges(Grund):
    def test_jede_stelle_in_jeder_groesse(self):
        for n in range(1, 10):
            for s in range(1, n + 1):
                with self.subTest(n=n, schuldig=s):
                    reihe, pruefer = pakete(n), Pruefer(s)
                    r = bt.teilen(reihe, pruefer)
                    self.assertEqual((r["status"], self.schuldig(r), r["wartet"]), (bt.GETEILT, [s], []))
                    self.assertEqual(self.ids(r["frei"]), [x for x in range(1, n + 1) if x != s])
                    self.assertEqual([x["pakete"] for x in r["laeufe"]], pruefer.laeufe)

    def test_halbiert_statt_einzeln(self):
        for s in range(1, 33):
            pruefer = Pruefer(s)
            bt.teilen(pakete(32), pruefer)
            self.assertLessEqual(len(pruefer.laeufe), 5 + 2, s)              # log2(32) + Probe (main oder Wiederholung) + Rest

    def test_erster_lauf_ist_die_haelfte(self):
        pruefer = Pruefer(6)
        bt.teilen(pakete(8), pruefer)
        self.assertEqual(pruefer.laeufe[0], [1, 2, 3, 4])                    # das Ganze ist schon rot gelaufen

    def test_befund_nennt_paket_und_meldung_seines_laufs(self):
        r = bt.teilen(pakete(4), Pruefer(3))
        self.assertEqual(r["befunde"], [{"aufgabe": 3, "titel": "Paket 3", "art": "p", "zweig": "paket-A3", "kopf": f"{3:040x}",
                                         "agent": "CC1", "meldung": "FAILED [[3]] in [1, 2, 3]", "nach": [1, 2], "lead_liest": False}])

    def test_befund_auch_mit_kargem_paket(self):
        f = bt.teilen([{"id": 1, "gruende": []}], Pruefer(1))["befunde"][0]
        self.assertEqual((f["aufgabe"], f["titel"], f["agent"]), (1, None, None))

    def test_meldung_fehlt(self):
        r = bt.teilen(pakete(1), lambda teil: {"ok": not teil})
        self.assertIn("ohne Meldung", r["befunde"][0]["meldung"])


class Mehrere(Grund):
    def test_alle_paare(self):
        for a in range(1, 7):
            for b in range(a + 1, 7):
                with self.subTest(a=a, b=b):
                    reihe = pakete(6)
                    r = bt.teilen(reihe, Pruefer(a, b))
                    self.assertEqual((r["status"], self.schuldig(r)), (bt.GETEILT, [a, b]))
                    self.jedes_genau_einmal(reihe, r)

    def test_alle_schuldig(self):
        r = bt.teilen(pakete(4), Pruefer(1, 2, 3, 4))
        self.assertEqual((r["status"], self.schuldig(r), r["frei"], r["freigabe"]), (bt.GETEILT, [1, 2, 3, 4], [], None))

    def test_nur_zusammen_rot_trifft_das_spaetere(self):
        r = bt.teilen(pakete(6), Pruefer((2, 5)))                            # jede Hälfte für sich wäre grün
        self.assertEqual((self.schuldig(r), self.ids(r["frei"])), ([5], [1, 2, 3, 4, 6]))
        self.assertIn(2, r["befunde"][0]["nach"])

    def test_die_freigegebene_menge_ist_genau_so_gelaufen(self):
        for schuldig in ((1,), (4,), (8,), (1, 8), (3, 4), ((1, 2), 5), ((2, 7), (3, 6)), (2, 4, 6, 8)):
            with self.subTest(schuldig=schuldig):
                r = bt.teilen(pakete(8), Pruefer(*schuldig))
                self.assertEqual(r["status"], bt.GETEILT)
                self.assertIn({"pakete": self.ids(r["frei"]), "ok": True}, [{k: x[k] for k in ("pakete", "ok")} for x in r["laeufe"]])


class Abhaengigkeit(Grund):
    def test_nachfolger_des_schuldigen_warten_auch_mittelbar(self):
        reihe, pruefer = pakete(6), Pruefer(2)
        r = bt.teilen(reihe, pruefer, vor={4: [2], 6: [4], 5: [1]})
        self.assertEqual((self.schuldig(r), self.ids(r["frei"]), self.ids(r["wartet"])), ([2], [1, 3, 5], [4, 6]))
        self.assertIn("A2", r["wartet"][0]["grund"])
        self.assertIn("A4", r["wartet"][1]["grund"])

    def test_nie_ein_lauf_ohne_den_vorgaenger(self):
        vor = {3: [1], 4: [2], 5: [4], 7: [3], 8: [5]}
        for s in range(1, 9):
            pruefer = Pruefer(s)
            bt.teilen(pakete(8), pruefer, vor=vor)
            for lauf in pruefer.laeufe:
                self.assertEqual(lauf, sorted(lauf))                         # Reihenfolge des Bündels
                for p in lauf:
                    self.assertLessEqual(set(vor.get(p, ())), set(lauf), (s, lauf))

    def test_vorgaenger_ausserhalb_zaehlt_nicht(self):
        r = bt.teilen(pakete(3), Pruefer(1), vor={2: [99]})
        self.assertEqual(self.ids(r["frei"]), [2, 3])


class LeadLiest(Grund):
    KETTE = [(RELEASE_MAIN, "Release-Kette: amw/auslieferung.py")]

    def test_gruenes_paket_der_kette_ist_markiert_und_der_lead_gibt_frei(self):
        reihe = pakete(4)
        reihe[0]["gruende"] = self.KETTE
        r = bt.teilen(reihe, Pruefer(3))
        self.assertEqual([(p["id"], p["lead_liest"]) for p in r["frei"]], [(1, True), (2, False), (4, False)])
        self.assertEqual(r["freigabe"], "Lead")
        self.assertEqual(r["lead_liest"], [{"aufgabe": 1, "gruende": self.KETTE}])

    def test_ohne_kette_gibt_die_amw_frei(self):
        r = bt.teilen(pakete(4), Pruefer(3))
        self.assertEqual((r["freigabe"], r["lead_liest"]), ("AMW", []))

    def test_schuldiges_paket_der_kette_ist_markiert_haelt_den_rest_aber_nicht_auf(self):
        reihe = pakete(4)
        reihe[2]["gruende"] = self.KETTE
        r = bt.teilen(reihe, Pruefer(3))
        self.assertTrue(r["befunde"][0]["lead_liest"])
        self.assertEqual((r["freigabe"], [x["aufgabe"] for x in r["lead_liest"]]), ("AMW", [3]))

    def test_wartendes_paket_der_kette_ist_markiert(self):
        reihe = pakete(3)
        reihe[2]["gruende"] = self.KETTE
        r = bt.teilen(reihe, Pruefer(1), vor={3: [1]})
        self.assertEqual([(p["id"], p["lead_liest"]) for p in r["wartet"]], [(3, True)])

    def test_andere_regel_markiert_nicht(self):
        reihe = pakete(2)
        reihe[0]["gruende"] = [("g12", "löscht")]
        self.assertEqual(bt.teilen(reihe, Pruefer(2))["lead_liest"], [])

    def test_ohne_einordnung_liest_der_lead(self):
        for nicht in ({"gruende": None}, {"gruende": [("einordnung", "nicht möglich: kaputt")]}):
            r = bt.teilen([paket(1, **nicht), paket(2)], Pruefer(2))
            self.assertEqual(([x["aufgabe"] for x in r["lead_liest"]], r["freigabe"]), ([1], "Lead"))
        ohne = paket(1)
        del ohne["gruende"]
        self.assertEqual(bt.teilen([ohne, paket(2)], Pruefer(2))["freigabe"], "Lead")


class NieFalschBeschuldigt(Grund):
    def nichts_frei(self, reihe, r, status):
        self.assertEqual((r["status"], r["frei"], r["freigabe"]), (status, [], None))
        self.jedes_genau_einmal(reihe, r)
        self.assertTrue(r["meldung"])
        for p in r["wartet"]:
            self.assertTrue(p["grund"])

    def test_main_selbst_rot(self):
        reihe = pakete(5)
        r = bt.teilen(reihe, Pruefer(basis_rot=True))
        self.nichts_frei(reihe, r, bt.BASIS_ROT)
        self.assertEqual(r["befunde"], [])
        self.assertIn([], [x["pakete"] for x in r["laeufe"]])

    def test_main_wird_hoechstens_einmal_geprueft(self):
        pruefer = Pruefer(1, 2, 3)
        bt.teilen(pakete(3), pruefer)
        self.assertEqual(pruefer.laeufe.count([]), 1)

    def test_rot_laesst_sich_nicht_wiederholen(self):
        for n in (1, 2, 5, 8):                                               # sonst träfe es immer das letzte Paket
            reihe = pakete(n)
            r = bt.teilen(reihe, Pruefer())
            self.nichts_frei(reihe, r, bt.WACKELIG)
            self.assertEqual(r["befunde"], [])

    def test_lauf_ohne_ergebnis_haelt_an(self):
        for antwort in ({"ok": None, "meldung": "abgebrochen"}, None, True, {}, {"ok": 1}, {"ok": "gruen"}, "rot"):
            with self.subTest(antwort=antwort):
                reihe, laeufe = pakete(4), []

                def pruefer(teil):
                    laeufe.append(teil)
                    return antwort
                r = bt.teilen(reihe, pruefer)
                self.nichts_frei(reihe, r, bt.UNKLAR)
                self.assertEqual((r["befunde"], len(laeufe)), ([], 1))

    def test_fehler_im_pruefer_haelt_an(self):
        def pruefer(teil):
            raise OSError("Platte voll")
        reihe = pakete(4)
        r = bt.teilen(reihe, pruefer)
        self.nichts_frei(reihe, r, bt.UNKLAR)
        self.assertIn("Platte voll", r["meldung"])

    def test_fester_befund_bleibt_bei_spaeterem_abbruch(self):
        echt = Pruefer(2)

        def pruefer(teil):
            if [p["id"] for p in teil] == [1, 3, 4]:                         # der letzte Lauf: alles ohne das schuldige
                return {"ok": None, "meldung": "weg"}
            return echt(teil)
        reihe = pakete(4)
        r = bt.teilen(reihe, pruefer)
        self.nichts_frei(reihe, r, bt.UNKLAR)
        self.assertEqual(self.schuldig(r), [2])

    def test_abbruch_des_menschen_geht_durch(self):
        def pruefer(teil):
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            bt.teilen(pakete(2), pruefer)


class Eingaben(Grund):
    def test_unsinn_wird_abgewiesen_ohne_lauf(self):
        for reihe, vor in (([], {}), ([paket(1), paket(1)], {}), (pakete(2), {1: [2]}), (pakete(2), {1: [1]})):
            pruefer = Pruefer(1)
            with self.subTest(reihe=reihe, vor=vor), self.assertRaises(ValueError):
                bt.teilen(reihe, pruefer, vor=vor)
            self.assertEqual(pruefer.laeufe, [])

    def test_rein_die_eingaben_bleiben(self):
        reihe, vor = pakete(5), {4: [2]}
        vorher = copy.deepcopy((reihe, vor))

        def pruefer(teil):
            ok = all(p["id"] != 2 for p in teil)
            for p in teil:
                p["id"] = 0                                                  # ein Prüfer, der seine Liste verändert
            teil.clear()
            return {"ok": ok, "meldung": "x"}
        r = bt.teilen(reihe, pruefer, vor=vor)
        self.assertEqual((reihe, vor), vorher)
        self.assertEqual((self.schuldig(r), self.ids(r["frei"])), ([2], [1, 3, 5]))

    def test_generator(self):
        self.assertEqual(self.schuldig(bt.teilen((p for p in pakete(3)), Pruefer(3))), [3])


if __name__ == "__main__":
    unittest.main()
