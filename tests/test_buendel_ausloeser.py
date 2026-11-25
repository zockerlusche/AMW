"""A2119 (TH158 F5, TL #32140): Bündel-Auslöser – n abgenommene Pakete bereit, x Stunden seit der letzten Auslieferung, Leerlauf
(kein Agent mit startklarem Paket) oder ein bereites Paket blockiert andere Arbeit. Reine Funktion; n und x je Projekt."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime
import json
import os
import tempfile
import unittest

from amw import buendel_ausloeser as ba
from amw import db, kern

JETZT = datetime.datetime(2026, 11, 25, 12, 0, tzinfo=datetime.timezone.utc)


def vor(**wie):
    return JETZT - datetime.timedelta(**wie)


class Entscheiden(unittest.TestCase):
    def lage(self, bereit=(1,), letzte: datetime.datetime | str | None = vor(hours=1), startklar=("CC1",), blockierend=(), **mehr):
        """Vorgabe: ein Paket bereit, vor 1 h ausgeliefert, CC1 hat Arbeit, nichts blockiert – also kein Auslöser."""
        return ba.entscheiden(bereit=bereit, letzte_auslieferung=letzte, agenten_startklar=startklar, jetzt=JETZT,
                              blockierend=blockierend, **mehr)

    def test_vorgaben(self):
        self.assertEqual((ba.N_VORGABE, ba.X_VORGABE_H), (4, 3))

    def test_ohne_ausloeser_wird_gewartet(self):
        e = self.lage()
        self.assertEqual((e["buendeln"], e["gruende"]), (False, []))
        self.assertIn("1 von 4", e["text"])

    def test_n_pakete_bereit(self):
        self.assertFalse(self.lage(bereit=[1, 2, 3])["buendeln"])
        e = self.lage(bereit=[1, 2, 3, 4])
        self.assertEqual((e["buendeln"], e["gruende"]), (True, ["anzahl"]))
        self.assertEqual(self.lage(bereit=[1, 2, 3, 4, 5])["gruende"], ["anzahl"])

    def test_dasselbe_paket_zaehlt_einmal(self):
        self.assertFalse(self.lage(bereit=[1, 1, 2, 2])["buendeln"])

    def test_x_stunden_seit_der_letzten_auslieferung(self):
        self.assertFalse(self.lage(letzte=vor(hours=2, minutes=59, seconds=59))["buendeln"])
        e = self.lage(letzte=vor(hours=3))                                   # genau x: fällig
        self.assertEqual((e["buendeln"], e["gruende"]), (True, ["zeit"]))

    def test_noch_nie_ausgeliefert_gilt_als_faellig(self):
        self.assertEqual(self.lage(letzte=None)["gruende"], ["zeit"])

    def test_auslieferung_in_der_zukunft_ist_nicht_faellig(self):            # verstellte Uhr
        self.assertFalse(self.lage(letzte=JETZT + datetime.timedelta(hours=5))["buendeln"])

    def test_zeit_auch_als_gespeicherter_text(self):
        self.assertEqual(self.lage(letzte="2026-11-25T09:00:00Z")["gruende"], ["zeit"])
        self.assertFalse(self.lage(letzte="2026-11-25 09:00:01")["buendeln"])

    def test_zeit_ohne_zeitzone_ist_ein_fehler(self):
        with self.assertRaises(ValueError):
            self.lage(letzte=datetime.datetime(2026, 11, 25, 9, 0))
        with self.assertRaises(ValueError):
            self.lage(letzte="gestern")

    def test_leerlauf_heisst_kein_agent_mit_startklarem_paket(self):
        e = self.lage(startklar=[])
        self.assertEqual((e["buendeln"], e["gruende"]), (True, ["leerlauf"]))
        self.assertFalse(self.lage(startklar=["CC2"])["buendeln"])           # ein einziger genügt

    def test_blockierter_stand_geht_frueher(self):
        e = self.lage(bereit=[7, 8], blockierend=[8])
        self.assertEqual((e["buendeln"], e["gruende"], e["blockierend"]), (True, ["blockiert"], [8]))
        self.assertIn("A8", e["text"])

    def test_blockierendes_das_nicht_bereit_ist_loest_nichts_aus(self):      # ein Bündel brächte es nicht nach main
        e = self.lage(bereit=[7], blockierend=[99])
        self.assertEqual((e["buendeln"], e["blockierend"]), (False, []))

    def test_alle_gruende_in_fester_reihenfolge(self):
        e = self.lage(bereit=[1, 2, 3, 4], letzte=vor(hours=9), startklar=[], blockierend=[2])
        self.assertEqual(e["gruende"], ["anzahl", "zeit", "leerlauf", "blockiert"])
        for wort in ("4 Pakete bereit", "seit der letzten Auslieferung", "Leerlauf", "A2"):
            self.assertIn(wort, e["text"])

    def test_ohne_bereites_paket_nie(self):
        e = self.lage(bereit=[], letzte=None, startklar=[], blockierend=[2])
        self.assertEqual((e["buendeln"], e["gruende"]), (False, []))

    def test_n_und_x_gelten_wie_uebergeben(self):
        self.assertEqual(self.lage(bereit=[1, 2], n=2)["gruende"], ["anzahl"])
        self.assertFalse(self.lage(bereit=[1, 2, 3, 4], n=5)["buendeln"])
        self.assertEqual(self.lage(letzte=vor(minutes=30), x_h=0.5)["gruende"], ["zeit"])
        self.assertFalse(self.lage(letzte=vor(hours=5), x_h=6)["buendeln"])

    def test_rein_die_eingaben_bleiben(self):
        bereit, startklar, blockierend = [3, 1], [], [1]
        a = self.lage(bereit=bereit, startklar=startklar, blockierend=blockierend)
        self.assertEqual(a, self.lage(bereit=bereit, startklar=startklar, blockierend=blockierend))
        self.assertEqual((bereit, startklar, blockierend), ([3, 1], [], [1]))

    def test_auch_generatoren(self):
        self.assertEqual(self.lage(bereit=(x for x in (1, 2, 3, 4)), startklar=(x for x in ("CC1",)))["gruende"], ["anzahl"])
        self.assertEqual(self.lage(startklar=(x for x in ()))["gruende"], ["leerlauf"])


class Einstellungen(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
            self.anderes = db.einfuegen(self.con, "projekt", name="Q", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")

    def roh(self, text):
        with db.schreiben(self.con):
            self.con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?", (text, self.pid))

    def test_vorgabe(self):
        self.assertEqual(ba.einstellung(self.con, self.pid), {"n": 4, "x_h": 3})

    def test_je_projekt(self):
        self.assertEqual(ba.einstellen(self.con, self.pid, "TL", n=6, x_h="1,5"), {"n": 6, "x_h": 1.5})
        self.assertEqual(ba.einstellung(self.con, self.pid), {"n": 6, "x_h": 1.5})
        self.assertEqual(ba.einstellung(self.con, self.anderes), {"n": 4, "x_h": 3})

    def test_nur_eins_aendern_und_leer_ist_vorgabe(self):
        ba.einstellen(self.con, self.pid, kern.ENTWICKLER, n="2", x_h=8)
        self.assertEqual(ba.einstellen(self.con, self.pid, "TL", n=""), {"n": 4, "x_h": 8})
        self.assertEqual(ba.einstellen(self.con, self.pid, "TL", x_h=None), {"n": 4, "x_h": 3})
        self.assertEqual(json.loads(self.con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (self.pid,)).fetchone()[0]), {})

    def test_andere_einstellungen_bleiben(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", takt_min=10)
        ba.einstellen(self.con, self.pid, "TL", n=5)
        kern.projekt_einstellen(self.con, self.pid, "TL", takt_min=20)
        e = json.loads(self.con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (self.pid,)).fetchone()[0])
        self.assertEqual((e["takt_min"], e[ba.N], ba.einstellung(self.con, self.pid)["n"]), (20, 5, 5))

    def test_nur_lead_oder_mensch(self):
        with self.assertRaises(kern.AmwFehler):
            ba.einstellen(self.con, self.pid, "CC1", n=1)
        self.assertEqual(ba.einstellung(self.con, self.pid)["n"], 4)

    def test_unsinn_wird_abgewiesen_und_nichts_gespeichert(self):
        for werte in ({"n": 0}, {"n": -1}, {"n": 2.5}, {"n": "viele"}, {"n": 51}, {"n": True}, {"n": "inf"}, {"x_h": 0}, {"x_h": -1},
                      {"x_h": "nan"}, {"x_h": "inf"}, {"x_h": 169}, {"x_h": "bald"}, {"x_h": False}, {"n": 5, "x_h": 0}):
            with self.subTest(werte=werte), self.assertRaises(kern.AmwFehler):
                ba.einstellen(self.con, self.pid, "TL", **werte)
            self.assertEqual(ba.einstellung(self.con, self.pid), {"n": 4, "x_h": 3}, werte)

    def test_kaputte_gespeicherte_werte_fallen_auf_die_vorgabe(self):
        for text in (json.dumps({ba.N: "x", ba.X: 0}), "kein json", "[1]", json.dumps({ba.N: None, ba.X: []})):
            self.roh(text)
            self.assertEqual(ba.einstellung(self.con, self.pid), {"n": 4, "x_h": 3}, text)

    def test_unbekanntes_projekt(self):
        self.assertEqual(ba.einstellung(self.con, 999), {"n": 4, "x_h": 3})
        with self.assertRaises(kern.AmwFehler):
            ba.einstellen(self.con, 999, kern.ENTWICKLER, n=2)

    def test_passt_zur_entscheidung(self):
        ba.einstellen(self.con, self.pid, "TL", n=1)
        e = ba.entscheiden(bereit=[1], letzte_auslieferung=JETZT, agenten_startklar=["CC1"], jetzt=JETZT, **ba.einstellung(self.con, self.pid))
        self.assertEqual(e["gruende"], ["anzahl"])


if __name__ == "__main__":
    unittest.main()
