"""A2102: Wer auf einen Prüfpunkt warten würde – die Sicht hinter einem Paket im Plan: was beim Menschen warten würde, was schon
begonnen hat und zu Ende läuft und wie viele Pakete weiterlaufen. Nur lesend."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import tempfile
import unittest
from unittest import mock

from amw import arbeitspaket, db, kern, planung, zwischenpruefung


class Zwischenpruefung(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        u.start()
        self.addCleanup(u.stop)
        for k in ("AMW_AGENT", "AMW_PROJEKT"):
            os.environ.pop(k, None)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        self.pid = self.projekt("Spiel")
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        # a → b → c → d, daneben unabhängig: frei
        self.a = self.paket("a")
        self.b = self.paket("b", [self.a])
        self.c = self.paket("c", [self.b])
        self.d = self.paket("d", [self.c])
        self.frei = self.paket("frei")

    def projekt(self, name):
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "projekt", name=name, angelegt_utc=db.jetzt())

    def paket(self, titel, nach=None, pid=None, **werte):
        return planung.schritt_setzen(self.con, pid or self.pid, "TL", titel=titel, nach=nach, **werte)

    def setze(self, aid, **werte):
        with db.schreiben(self.con):
            self.con.execute(f"UPDATE aufgabe SET {', '.join(k + ' = ?' for k in werte)} WHERE id = ?", (*werte.values(), aid))

    def sicht(self, aid):
        return zwischenpruefung.wartende(self.con, self.pid, aid)

    def test_eine_stufe(self):
        self.assertEqual(self.sicht(self.c), {"wartet": [self.d], "laeuft_schon": [], "weiter": 4})

    def test_mehrere_stufen(self):
        # das Paket selbst wartet nicht auf den Prüfpunkt dahinter: a und „frei“ laufen weiter
        self.assertEqual(self.sicht(self.a), {"wartet": [self.b, self.c, self.d], "laeuft_schon": [], "weiter": 2})

    def test_nichts_dahinter(self):
        self.assertEqual(self.sicht(self.d), {"wartet": [], "laeuft_schon": [], "weiter": 5})

    def test_zwei_wege_zum_selben_paket_zaehlen_einmal(self):
        planung.abhaengigkeit_setzen(self.con, self.pid, "TL", self.d, [self.a, self.b])
        self.assertEqual(self.sicht(self.a)["wartet"], [self.b, self.c, self.d])

    def test_reihenfolge_rang_dann_nummer(self):
        self.setze(self.d, rang=10)
        self.assertEqual(self.sicht(self.a)["wartet"], [self.d, self.b, self.c])

    def test_kreis_endet_und_das_paket_wartet_nicht_auf_sich(self):
        with db.schreiben(self.con):                  # abhaengigkeit_setzen verhindert Kreise – hier an ihr vorbei
            db.einfuegen(self.con, "abhaengigkeit", vor=self.d, nach=self.a)
            db.einfuegen(self.con, "abhaengigkeit", vor=self.c, nach=self.b)
        self.assertEqual(self.sicht(self.a), {"wartet": [self.b, self.c, self.d], "laeuft_schon": [], "weiter": 2})
        self.assertEqual(self.sicht(self.b), {"wartet": [self.a, self.c, self.d], "laeuft_schon": [], "weiter": 2})

    def test_schon_laufend_wartet_nicht_seine_nachfolger_schon(self):
        kern.aufgabe_status(self.con, self.pid, "TL", self.b, "start")
        self.assertEqual(self.sicht(self.a), {"wartet": [self.c, self.d], "laeuft_schon": [self.b], "weiter": 2})

    def test_begonnen_und_blockiert_zaehlt_als_begonnen(self):
        self.setze(self.c, status="blockiert", begonnen_utc="2026-11-02T08:00:00Z")
        self.setze(self.d, status="blockiert")        # nie begonnen
        self.assertEqual(self.sicht(self.a), {"wartet": [self.b, self.d], "laeuft_schon": [self.c], "weiter": 2})

    def test_p_paket_nach_zustand(self):
        arbeitspaket.setzen(self.con, self.pid, "TL", self.b, art="p", modell="sonnet")
        self.assertEqual(self.sicht(self.a)["wartet"], [self.b, self.c, self.d])
        for zustand, wartet, laeuft in (("startklar", [self.b, self.c, self.d], []), ("merge_reihe", [self.c, self.d], [self.b]),
                                        ("gemergt", [self.c, self.d], [])):
            with db.schreiben(self.con):
                self.con.execute("UPDATE paket SET zustand = ? WHERE aufgabe_id = ?", (zustand, self.b))
            self.assertEqual(self.sicht(self.a), {"wartet": wartet, "laeuft_schon": laeuft, "weiter": 2}, zustand)

    def test_fertige_und_verworfene_fallen_heraus_dahinter_geht_es_weiter(self):
        self.setze(self.b, status="fertig", beleg="abc123")
        self.setze(self.frei, status="verworfen", beleg="–")
        self.assertEqual(self.sicht(self.a), {"wartet": [self.c, self.d], "laeuft_schon": [], "weiter": 1})

    def test_schon_fertiges_paket_ist_erlaubt(self):
        self.setze(self.a, status="fertig", beleg="abc123")
        self.assertEqual(self.sicht(self.a), {"wartet": [self.b, self.c, self.d], "laeuft_schon": [], "weiter": 1})

    def test_anderes_projekt(self):
        anderes = self.projekt("Anderes")
        kern.agent_neu(self.con, anderes, "TL2", rolle="lead")
        fremd = self.paket("fremd", pid=anderes)
        with self.assertRaises(kern.AmwFehler):
            self.sicht(fremd)
        self.assertEqual(self.sicht(self.a)["weiter"], 2)                  # fremde Pakete zählen nicht mit

    def test_unbekannt(self):
        for x in (9999, 0, None):
            with self.assertRaises(kern.AmwFehler):
                self.sicht(x)

    def test_datenbank_bleibt_unveraendert(self):
        kern.aufgabe_status(self.con, self.pid, "TL", self.b, "start")
        arbeitspaket.setzen(self.con, self.pid, "TL", self.c, art="p", modell="sonnet")
        vorher, zaehler = list(self.con.iterdump()), self.con.total_changes
        self.sicht(self.a)
        with self.assertRaises(kern.AmwFehler):
            self.sicht(9999)
        self.assertEqual(self.con.total_changes, zaehler)
        self.assertFalse(self.con.in_transaction)
        self.assertEqual(list(self.con.iterdump()), vorher)


if __name__ == "__main__":
    unittest.main()
