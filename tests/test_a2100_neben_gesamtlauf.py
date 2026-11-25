"""A2100: leichte Läufe eines Agenten warten von selbst, solange im selben Projekt ein Gesamtlauf rechnet oder in der Schlange steht;
daneben nur mit --neben „Grund“ (steht im Lauf, Meldung an den Lead) oder sehr kurz ohne Tests. Kein Verhungern."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

from amw import betrieb, cli, db, kern
from tests import test_rechner_schlange

GESAMT = ["cd x && python -X utf8 -m amw.testlauf"]
TESTS = ["python -X utf8 -m unittest tests.test_kern"]


class Grund(test_rechner_schlange.Grund):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(betrieb, "leichte_laeufe", return_value=6)
        p.start()
        self.addCleanup(p.stop)

    def gesamt(self, projekt="Eins", agent="A", **k):
        return self.start(projekt, agent, "Gesamtlauf", schwer=False, befehl=GESAMT, **k)

    def leicht(self, agent="B", projekt="Eins", **k):
        return self.start(projekt, agent, "Teil", **{"schwer": False, "befehl": TESTS, "leise": True, **k})

    def grund(self, lid, projekt="Eins"):
        return betrieb.wartegrund(self.con, self.p[projekt], self.con.execute(
            "SELECT l.*, r.braucht_speicher_gb FROM lauf l LEFT JOIN rezept r ON r.id = l.rezept_id WHERE l.id = ?", (lid,)).fetchone(), 32.0)

    def runde(self):
        return betrieb.warteschlange(self.con, None, 32.0)

    def ende(self, lid, projekt="Eins", agent="A", rc=0):
        return betrieb.lauf_ende(self.con, self.p[projekt], agent, lid, rc, speicher_frei=32.0)


class Warten(Grund):
    def test_wartet_bis_der_gesamtlauf_zu_ende_ist(self):
        g = self.gesamt()
        lid = self.leicht()
        self.assertEqual((self.status(g), self.status(lid)), ("laeuft", "angemeldet"))
        self.assertIn(f"wartet auf L{g} von A: Gesamtlauf rechnet", self.grund(lid))
        self.assertEqual(self.runde(), [])
        pos = betrieb.warteposition(self.con, self.p["Eins"], self.con.execute("SELECT * FROM lauf WHERE id = ?", (lid,)).fetchone())
        self.assertEqual((pos["auf"][0]["lauf"], pos["auf"][0]["laeuft"]), (g, True))
        self.assertEqual(self.ende(g), [lid])
        self.assertEqual(self.status(lid), "laeuft")

    def test_wartet_schon_auf_den_wartenden_gesamtlauf(self):
        g1 = self.gesamt(agent="A")
        g2 = self.gesamt(agent="C")                                                   # wartet auf g1
        lid = self.leicht()
        self.assertEqual(self.status(g2), "angemeldet")
        self.ende(g1)
        self.assertEqual((self.status(g2), self.status(lid)), ("laeuft", "angemeldet"))    # der Gesamtlauf hat Vorrang
        self.assertIn(f"L{g2}", self.grund(lid))
        self.ende(g2, agent="C")
        self.assertEqual(self.status(lid), "laeuft")

    def test_auch_der_spaeter_eingereihte_gesamtlauf_geht_vor(self):
        with mock.patch.object(betrieb, "leichte_laeufe", return_value=1):
            vorn = self.leicht("C")
            lid = self.leicht("B")                                                    # wartet nur auf die leichte Spur
            g = self.gesamt(agent="A")
            self.assertEqual((self.status(vorn), self.status(lid), self.status(g)), ("laeuft", "angemeldet", "angemeldet"))
            self.ende(vorn, agent="C")
            self.assertEqual((self.status(g), self.status(lid)), ("laeuft", "angemeldet"))
            self.ende(g)
            self.assertEqual(self.status(lid), "laeuft")

    def test_danach_in_ihrer_reihenfolge(self):
        g = self.gesamt()
        x, y = self.leicht("B"), self.leicht("C")
        with mock.patch.object(betrieb, "leichte_laeufe", return_value=1):
            self.assertEqual(self.ende(g), [x])
            self.assertEqual(self.ende(x, agent="B"), [y])

    def test_ohne_warten_abgewiesen(self):
        g = self.gesamt()
        with self.assertRaisesRegex(kern.AmwFehler, rf"wartet auf L{g} .*--warten"):
            betrieb.lauf_start(self.con, self.p["Eins"], "B", "Teil", schwer=False, befehl=TESTS, leise=True, speicher_frei=32.0)

    def test_milestone_gesamttest_zaehlt(self):
        g = self.start("Eins", "AMW-Test", "Gesamttest Meilenstein 15", schwer=True, befehl=GESAMT, selbst=True)
        self.assertEqual(self.status(g), "laeuft")
        self.assertEqual(self.status(self.leicht()), "angemeldet")

    def test_von_hand_angemeldet_zaehlt_die_beschreibung(self):
        self.start("Eins", "A", "Gesamtlauf 1.2.3", schwer=False)
        self.assertEqual(self.status(self.leicht()), "angemeldet")


class Unberuehrt(Grund):
    def test_ohne_gesamtlauf_wie_bisher(self):
        a, b = self.leicht("B"), self.leicht("C")
        self.assertEqual([self.status(x) for x in (a, b)], ["laeuft", "laeuft"])
        self.start("Eins", "A", "nach dem Gesamtlauf: Teil", schwer=False, befehl=TESTS)      # nennt ihn nur
        self.ende(b, agent="C")
        self.assertEqual(self.status(self.leicht("C")), "laeuft")

    def test_anderes_projekt(self):
        self.gesamt("Zwei")
        self.assertEqual(self.status(self.leicht()), "laeuft")

    def test_amw_selbst_schwer_fenster_grafik_dauerlauf(self):
        self.gesamt()
        for agent, k in (("AMW", {"schwer": False, "selbst": True}), ("B", {"schwer": True}), ("C", {"schwer": False, "dauerlauf": True, "braucht_gb": 1})):
            self.assertEqual(self.status(self.start("Eins", agent, "x", befehl=TESTS, **{"leise": True, **k})), "laeuft", k)
        with mock.patch("amw.schirm.sperrgrund", return_value=None):
            self.assertEqual(self.status(self.start("Eins", "D", "Fenster", schwer=False, schirm=True, befehl=TESTS, leise=True)), "laeuft")

    def test_gesamtlauf_selbst_wartet_nicht_auf_sich(self):
        g1 = self.gesamt(leise=True)
        g2 = self.gesamt(agent="C", leise=True)
        self.assertEqual(self.status(g1), "laeuft")
        self.assertNotIn("daneben rechnet nichts", self.grund(g2))                    # wartet auf den Platz „gesamt“ wie bisher
        self.ende(g1)
        self.assertEqual(self.status(g2), "laeuft")

    def test_sehr_kurz_ohne_tests(self):
        self.gesamt()
        for befehl, dauer, status in ((["python messen.py"], 2, "laeuft"), (["python messen.py"], 3, "angemeldet"), (["python messen.py"], None, "angemeldet"),
                                      (TESTS, 1, "angemeldet"), (["python t_dev2.py tests.test_x"], 1, "angemeldet"), (["python -m pytest"], 1, "angemeldet")):
            lid = self.leicht(befehl=befehl, erwartet_min=dauer)
            self.assertEqual(self.status(lid), status, (befehl, dauer))
            self.ende(lid, agent="B") if status == "laeuft" else betrieb.lauf_ende(self.con, self.p["Eins"], "B", lid, None, abgebrochen=True)

    def test_wartender_leichter_haelt_niemanden_auf(self):
        g = self.gesamt()
        lid = self.leicht("B")
        amw = self.start("Eins", "AMW", "Gegenlesen", schwer=False, selbst=True)      # gleiche Spur
        self.assertEqual((self.status(lid), self.status(amw)), ("angemeldet", "laeuft"))
        fremd = self.start("Zwei", "B", "Teil", schwer=False, befehl=TESTS, leise=True)
        self.assertEqual(self.status(fremd), "laeuft")
        self.assertEqual(self.status(g), "laeuft")


class KeinVerhungern(Grund):
    def test_gesamtlauf_im_halt_haelt_niemanden_auf(self):
        g1 = self.gesamt()
        g2 = self.gesamt(agent="C")
        lid = self.leicht()
        with mock.patch.object(kern, "halt_gilt", side_effect=lambda con, pid, a: a == "C"):
            self.ende(g1)
            self.assertEqual((self.status(g2), self.status(lid)), ("angemeldet", "laeuft"))

    def test_gesamtlauf_der_nie_passt_haelt_niemanden_auf(self):
        g = self.gesamt(sperre="wartet")
        self.assertEqual((betrieb.gesamt_vor(self.con, self.p["Eins"], 32.0) or {})["id"], g)
        with mock.patch.object(betrieb, "_passt_nie", return_value=True):
            self.assertIsNone(betrieb.gesamt_vor(self.con, self.p["Eins"], 32.0))
            self.assertEqual(self.status(self.leicht()), "laeuft")

    def test_zeitfenster_des_gesamtlaufs(self):
        g = self.gesamt(sperre="erst nachts")
        self.assertEqual(self.status(g), "angemeldet")
        with mock.patch.object(betrieb, "_lebt", side_effect=lambda con, pid, l: l["id"] != g):
            self.assertEqual(self.status(self.leicht()), "laeuft")


class Daneben(Grund):
    def meldungen(self):
        return [(r["kurz"], r["text"]) for r in self.con.execute("SELECT kurz, text FROM nachricht WHERE kurz LIKE '%rechnet neben%'")]

    def test_mit_grund_im_lauf_und_meldung_an_den_lead(self):
        g = self.gesamt()
        lid = self.leicht(neben="Ausfall beheben")
        self.assertEqual(self.status(lid), "laeuft")
        self.assertEqual(self.con.execute("SELECT beschreibung FROM lauf WHERE id = ?", (lid,)).fetchone()[0],
                         f"Teil (neben Gesamtlauf L{g}: Ausfall beheben)")
        (kurz, text), = self.meldungen()
        self.assertEqual(kurz, f"L{lid} von B rechnet neben dem Gesamtlauf L{g}")
        self.assertIn("Ausfall beheben", text)

    def test_ohne_gesamtlauf_bleibt_der_grund_ohne_wirkung(self):
        lid = self.leicht(neben="egal")
        self.assertEqual((self.status(lid), self.meldungen()), ("laeuft", []))
        self.assertEqual(self.con.execute("SELECT beschreibung FROM lauf WHERE id = ?", (lid,)).fetchone()[0], "Teil")

    def test_leerer_grund_abgewiesen(self):
        with self.assertRaisesRegex(kern.AmwFehler, "--neben nur mit Grund"):
            self.leicht(neben="  ")

    def test_eingereiht_mit_grund_wartet_nicht_auf_den_gesamtlauf(self):
        with mock.patch.object(betrieb, "leichte_laeufe", return_value=1):
            vorn = self.leicht("C")
            lid = self.leicht("B", neben="dringend")
            self.assertEqual(self.status(lid), "angemeldet")
            self.ende(vorn, agent="C")
        self.assertEqual(self.status(lid), "laeuft")


class UeberDieBefehlszeile(Grund):
    """Der echte Weg: amw lauf start|ausfuehren mit dem Parser, AMW_DB auf die Testdatenbank."""
    def cli(self, *a):
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "t.db")})
        u.start()
        self.addCleanup(u.stop)
        with contextlib.redirect_stdout(io.StringIO()) as o, contextlib.redirect_stderr(io.StringIO()) as f:
            rc = cli.main(["--projekt", "Eins", "--von", "B", *a])
        return rc, o.getvalue() + f.getvalue()

    def test_start(self):
        g = self.gesamt()
        rc, aus = self.cli("lauf", "start", "--leicht", "--beschreibung", "Teil")
        self.assertTrue(rc)
        self.assertIn(f"wartet auf L{g}", aus)
        rc, aus = self.cli("lauf", "start", "--leicht", "--warten", "--beschreibung", "Teil")
        self.assertIn("eingereiht", aus)
        rc, aus = self.cli("lauf", "start", "--leicht", "--neben", "Ausfall", "--beschreibung", "Teil zwei")
        self.assertIn("läuft", aus)

    def test_ausfuehren_startet_erst_nach_dem_gesamtlauf(self):
        g = self.gesamt()
        with mock.patch.object(cli.time, "sleep", side_effect=lambda s: self._beim_warten(g)):
            rc, aus = self.cli("lauf", "ausfuehren", "--leicht", "--beschreibung", "Teil", "--", sys.executable, "-c", "print('gerechnet')")
        self.assertIn(f"wartet auf L{g}", aus)
        self.assertEqual(rc, 0)
        self.assertIn("gerechnet", aus)
        self.assertLess(aus.index("wartet auf"), aus.index("gerechnet"))

    def _beim_warten(self, g):
        if self.status(g) == "laeuft":
            con = db.verbinde(os.path.join(self.ordner.name, "t.db"))
            try:
                betrieb.lauf_ende(con, self.p["Eins"], "A", g, 0, speicher_frei=32.0)
            finally:
                con.close()


class Kennzeichen(Grund):
    def test_nur_wartende_agentenlaeufe(self):
        self.gesamt()
        lid = self.leicht()
        self.start("Eins", "AMW", "Planer", schwer=False, selbst=True)
        self.assertEqual([json.loads(r[0])["lauf"] for r in self.con.execute("SELECT text FROM plan_ereignis WHERE art = ?", (betrieb.LEISE,))], [lid])


if __name__ == "__main__":
    unittest.main()
