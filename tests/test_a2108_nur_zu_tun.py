"""A2108 (Marcel 25.11., W2487): an den Menschen zählt nur, was er tun muss. „L… mit Vorrang wartet“ und „A… hängt?“ gehen an den Lead, Zustände
(wartet, bereit zur Abnahme) enden von selbst, Infos und Berichte zählen nie. Über die Schlange und die Dienst-Runde."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import unittest
from unittest import mock

from amw import abschluss, abschlusslage, betrieb, db, dienst, kern, limithalt, planautomatik, planung, tore, veroeffentlichung, workbench
from tests import test_a2098_fertig_wenn, test_rechner_schlange, test_vorrang

E = kern.ENTWICKLER


def offen(con, an, muster):
    return [r[0] for r in con.execute("SELECT n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? AND e.status != 'erledigt' AND n.kurz LIKE ?"
                                      " ORDER BY n.id", (an, muster))]


class Schlange(test_rechner_schlange.Grund):
    def setUp(self):
        super().setUp()
        self.v = {"Zwei": "hoch"}
        p = mock.patch.object(betrieb, "vorrang", lambda: dict(self.v))
        p.start()
        self.addCleanup(p.stop)
        self.start("Eins", "C")
        self.h = self.start("Zwei", "A")
        with db.schreiben(self.con):
            self.con.execute("UPDATE lauf SET angemeldet_utc = ? WHERE id = ?", (test_vorrang.vor_minuten(25), self.h))
        self.muster = f"L{self.h} mit Vorrang%"

    def test_an_den_lead_und_endet_wenn_der_lauf_beginnt(self):
        betrieb.vorrang_meldungen(self.con)
        self.assertEqual((len(offen(self.con, "Chef", self.muster)), offen(self.con, E, self.muster)), (1, []))
        self.assertEqual(workbench.an_dich_zahl(self.con, self.p["Zwei"]), 0)
        betrieb.vorrang_meldungen(self.con)
        self.assertEqual(len(offen(self.con, "Chef", self.muster)), 1)                        # er wartet noch
        with db.schreiben(self.con):
            self.con.execute("UPDATE lauf SET status = 'laeuft', start_utc = ? WHERE id = ?", (db.jetzt(), self.h))
        betrieb.vorrang_meldungen(self.con)
        self.assertEqual(offen(self.con, "Chef", self.muster), [])
        self.assertEqual(self.con.execute("SELECT e.bemerkung FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id WHERE n.kurz LIKE ?", (self.muster,)).fetchone()[0],
                         f"von selbst beendet: L{self.h} läuft")

    def test_endet_auch_wenn_er_aus_der_schlange_faellt_und_ohne_vorrang(self):
        betrieb.vorrang_meldungen(self.con)
        betrieb.lauf_ende(self.con, self.p["Zwei"], "A", self.h, None, abgebrochen=True)
        self.v = {}                                                                         # kein Vorrang mehr eingestellt
        betrieb.vorrang_meldungen(self.con)
        self.assertEqual(offen(self.con, "Chef", self.muster), [])

    def test_ohne_lead_der_mensch_altbestand_bleibt(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE agent SET rolle = NULL WHERE kennung = 'Chef' AND projekt_id = (SELECT id FROM projekt WHERE name = 'Zwei')")
            kern._posten(self.con, self.p["Zwei"], "AMW", E, "meldung", "L7 mit Vorrang wartet seit 20 Minuten")     # von vorher: ohne Bezug
        betrieb.vorrang_meldungen(self.con)
        self.assertEqual(len(offen(self.con, E, self.muster)), 1)
        with db.schreiben(self.con):
            self.con.execute("UPDATE lauf SET status = 'fertig' WHERE id = ?", (self.h,))
        betrieb.vorrang_meldungen(self.con)
        self.assertEqual((offen(self.con, E, self.muster), offen(self.con, E, "L7 mit Vorrang%")), ([], ["L7 mit Vorrang wartet seit 20 Minuten"]))


class Abnahme(test_a2098_fertig_wenn.Grund):
    FERTIG = "Vorführung beim Menschen"
    MUSTER = "Meilenstein%bereit zur Abnahme%"

    def bereit(self):
        self.alt_bereit()
        self.laufen(self.mit(beleg="da"))
        for _ in range(3):
            planautomatik.meilensteine(self.con)

    def test_bleibt_solange_bereit_und_zaehlt(self):
        self.bereit()
        self.assertEqual((len(offen(self.con, E, self.MUSTER)), len(offen(self.con, "TL", self.MUSTER))), (1, 1))
        self.assertEqual(workbench.an_dich_zahl(self.con, self.pid), 1)
        planautomatik.meilensteine(self.con)
        self.assertEqual(len(offen(self.con, E, self.MUSTER)), 1)

    def test_endet_mit_neuem_paket(self):
        self.bereit()
        planung.schritt_setzen(self.con, self.pid, "TL", titel="Nachtrag", bogen_id=self.m, agent="CC1")
        planautomatik.meilensteine(self.con)
        self.assertEqual((offen(self.con, E, self.MUSTER), offen(self.con, "TL", self.MUSTER)), ([], []))
        self.assertEqual(workbench.an_dich_zahl(self.con, self.pid), 0)

    def test_endet_mit_der_abnahme_und_wenn_die_pruefung_fehlt(self):
        self.bereit()
        with mock.patch.object(abschlusslage, "lage", return_value="fehlt"), mock.patch.object(abschlusslage, "pruefer_geht", return_value=True):
            self.assertEqual(len(tore.bereit_beenden(self.con, self.pid)), 1)               # der Lead klärt es – der Mensch hat nichts zu tun
        self.assertEqual(offen(self.con, E, self.MUSTER), [])

    def test_abgenommen(self):
        self.bereit()
        with db.schreiben(self.con):
            self.con.execute("UPDATE bogen SET status = 'fertig' WHERE id = ?", (self.m,))
        planautomatik.meilensteine(self.con)
        self.assertEqual(offen(self.con, E, self.MUSTER), [])

    def test_altbestand_ohne_bezug_bleibt(self):
        with db.schreiben(self.con):
            kern._posten(self.con, self.pid, "AMW", E, "meldung", "Meilenstein 1 „Anmelden“ bereit zur Abnahme (D9)")
        planautomatik.meilensteine(self.con)
        self.assertEqual(len(offen(self.con, E, "%(D9)")), 1)


class Zaehlen(test_a2098_fertig_wenn.Grund):
    def zahl(self):
        return workbench.an_dich_zahl(self.con, self.pid)

    def test_was_zaehlt(self):
        n0, _ = kern.posten(self.con, self.pid, E, "CC1", "auftrag", "Wie weit?")
        for art, von, kw, zaehlt in (("info", "CC1", {}, 0), ("info", "AMW", {}, 0), ("meldung", "CC1", {}, 0), ("meldung", "AMW", {}, 1), ("antwort", "CC1", {}, 0),
                                     ("antwort", "CC1", {"antwort_auf": n0}, 1), ("auftrag", "TL", {}, 1), ("frage", "TL", {}, 1), ("pruefbitte", "TL", {}, 1)):
            with self.subTest(art=art, von=von, **kw):
                vorher = self.zahl()
                with db.schreiben(self.con):
                    kern._posten(self.con, self.pid, von, E, art, f"{art} von {von}", **kw)
                self.assertEqual(self.zahl() - vorher, zaehlt)
        s = workbench.daten_start(self.con, self.pid)
        self.assertEqual((s["zaehler"]["nachrichten"], s["zaehler"]["an_dich"], sum(1 for n in s["an_dich"] if n["zaehlt"])), (5, 5, 5))
        d = workbench.daten_nachrichten(self.con, self.pid)
        self.assertEqual((len(d["eingang"]), sum(x["zaehlt"] for x in d["eingang"]), d["zaehler"]["eingang_offen"]), (9, 5, 5))      # lesbar bleibt alles

    def test_nur_wissen_ist_eine_info(self):
        with mock.patch.object(veroeffentlichung, "offen", side_effect=RuntimeError("x")), mock.patch.object(kern, "projekt_ordner", return_value=self.repo), \
                self.assertRaises(RuntimeError):
            veroeffentlichung.veroeffentlichen(self.con, self.pid, "TL", repo=self.repo)
        with mock.patch.object(dienst, "dienst_projekt", return_value=self.pid), mock.patch("amw.push.sofort", create=True):
            dienst.aufpasser_melden("war 46 min weg")
        self.assertEqual([r[0] for r in self.con.execute("SELECT art FROM nachricht WHERE kurz LIKE 'Dienst: %'")], ["info"])
        self.assertEqual(self.zahl(), 0)

    def test_wochenlimit_der_lead_handelt_der_mensch_weiss_es(self):
        kern.projekt_einstellen(self.con, self.pid, E, limit_halt="90")
        limithalt.runde(self.con, lage={"wert": 95.0, "letzter_reset_utc": "2026-11-23T00:00:00Z"})
        wer = [(r[0], r[1]) for r in self.con.execute("SELECT e.agent, n.art FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE n.kurz LIKE 'Wochenlimit-Halt%' ORDER BY e.agent")]
        self.assertEqual(wer, [(E, "info"), ("TL", "meldung")])
        self.assertEqual(self.zahl(), 0)

    def test_haengt_an_pruefer_und_lead(self):
        from amw import entscheidung
        kern.agent_neu(self.con, self.pid, "PRUEF")
        kern.projekt_einstellen(self.con, self.pid, E, paket_pruefer="PRUEF")
        entscheidung.haenge_melder(self.pid, self.a1, None)("stille", "seit 21 min keine Ausgabe")
        self.assertEqual([len(offen(self.con, an, "%hängt?%")) for an in ("PRUEF", "TL", E)], [1, 1, 0])

    def test_die_pruefung_nutzt_dieselbe_lage(self):
        self.assertIsNotNone(abschluss.ERGEBNIS)
        self.assertEqual(tore.bereit_beenden(self.con, self.pid), [])


if __name__ == "__main__":
    unittest.main()
