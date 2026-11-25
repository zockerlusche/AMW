"""A2138: Zeitplan und Prognose rechnen die Pause ein – bis zu ihrem Ende beginnt kein Paket, was läuft, läuft zu Ende; ohne Ende ist die
Zeit unbekannt („wartet auf Pause“), beim Prüfpunkt gilt der Name; nach „Pause aus“ wieder wie vorher. Feste Uhr, echter Weg (pause.an/aus)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime
import unittest
from unittest import mock

from amw import db, kern, pause, planung, reihenfolge, waechter, zeitplan, zwischenpruefung
from tests import test_eingriff_pruefpunkt

JETZT = datetime.datetime(2026, 11, 24, 10, 0, tzinfo=datetime.timezone.utc)
HEUTE = JETZT.date()


def um(minuten):
    return (JETZT + datetime.timedelta(minutes=minuten)).strftime("%Y-%m-%dT%H:%M:%SZ")


def tag(n):
    return (HEUTE + datetime.timedelta(days=n)).isoformat()


def mittag(n):
    """Mittags UTC, n Tage nach HEUTE – derselbe Kalendertag auch in Ortszeit."""
    return f"{tag(n)}T11:00:00Z"


class Grund(test_eingriff_pruefpunkt.Grund):
    """Pakete (je M = 3 h): a → b → c bei CC1, frei bei CC2; ein Paket je Tag und Agent."""

    def setUp(self):
        super().setUp()
        u = mock.patch("amw.planung.durchsatz", return_value=[1])
        u.start()
        self.addCleanup(u.stop)

    def an(self, bis=None, pid=None):
        pid = pid or self.pid
        return pause.an(self.con, pid, "TL", bis=bis, grund="Umzug")

    def aus(self):
        return pause.aus(self.con, self.pid, "TL")

    def plan(self, pid=None):
        return {x["aid"]: x for x in zeitplan.berechnen(self.con, pid or self.pid, jetzt=JETZT)["pakete"]}

    def starts(self):
        z = self.plan()
        return [z[x]["start_utc"] for x in (self.a, self.b, self.c, self.frei)]

    def prognose(self, pid=None):
        return planung.prognose(self.con, pid or self.pid, laeufe=20, heute=HEUTE)

    def enden(self):
        g = self.prognose()["schritte"]
        return [g[x]["p50"] for x in (self.a, self.b, self.c, self.frei)]

    def wartet(self, quelle):
        return [quelle[x].get("wartet_auf") for x in (self.a, self.b, self.c, self.frei)]

    def laeuft(self, aid, seit=30):
        self.setze(aid, status="laeuft", begonnen_utc=um(-seit))


class Zeitplan(Grund):
    def test_vor_waehrend_und_nach_der_pause(self):
        vor = self.plan()
        self.assertEqual(self.starts(), [um(0), um(180), um(360), um(0)])
        self.an(um(90))
        z = self.plan()
        self.assertEqual(self.starts(), [um(90), um(270), um(450), um(90)])
        self.assertEqual((z[self.a]["ende_utc"], z[self.a]["gleichzeitig"]), (um(270), [self.frei]))
        self.assertEqual(self.wartet(z), [None] * 4)                                        # mit Ende ist die Zeit bekannt
        self.aus()
        self.assertEqual(self.plan(), vor)

    def test_laufendes_laeuft_zu_ende(self):
        self.laeuft(self.a)
        self.laeuft(self.frei, seit=200)                                                    # überzogen: endet „jetzt“, +20 min
        self.an(um(240))
        z = self.plan()
        self.assertEqual((z[self.a]["start_utc"], z[self.a]["ende_utc"]), (um(-30), um(150)))
        self.assertEqual((z[self.frei]["ende_utc"], z[self.frei]["plus_min"]), (um(0), 20))
        self.assertEqual(z[self.b]["start_utc"], um(240))                                   # a ist vorher fertig: die Pause hält b auf
        self.aus()
        self.an(um(60))
        self.assertEqual(self.plan()[self.b]["start_utc"], um(150))                         # Pause vorher vorbei: a hält b auf

    def test_headless_beginnt_auch_nicht(self):
        h = self.p_paket("Headless")
        for plaetze in ([], ["P1"]):
            with self.subTest(plaetze=plaetze), mock.patch("amw.platz.plaetze", return_value=plaetze):
                self.assertEqual(self.plan()[h]["start_utc"], um(0))
                self.an(um(45))
                self.assertEqual(self.plan()[h]["start_utc"], um(45))
                self.aus()

    def test_ohne_ende_unbekannt_fruehestens(self):
        self.laeuft(self.a)
        vor = self.plan()
        self.an()
        z = self.plan()
        self.assertEqual(self.wartet(z), [None, "Pause", "Pause", "Pause"])                 # Laufendes wartet nicht
        self.assertEqual([(x["start_utc"], x["ende_utc"]) for x in z.values()], [(x["start_utc"], x["ende_utc"]) for x in vor.values()])
        self.assertIn("wartet auf Pause", zeitplan.zeile(z[self.b]))
        self.aus()
        self.assertEqual(self.plan(), vor)

    def test_ende_vorbei(self):
        vor = self.plan()
        for minuten in (-60, 0):                                                            # noch nicht aufgehoben, aber vorbei
            with self.subTest(minuten=minuten):
                self.an(um(minuten))
                self.assertEqual(self.plan(), vor)
                self.aus()

    def test_unlesbares_ende_ist_kein_ende(self):
        self.an("2026-11-24")
        self.assertEqual(self.wartet(self.plan()), ["Pause"] * 4)
        self.assertEqual(self.wartet(self.prognose()["schritte"]), ["Pause"] * 4)


class Prognose(Grund):
    def test_vor_waehrend_und_nach_der_pause(self):
        vor = self.prognose()
        self.assertEqual(self.enden(), [tag(1), tag(2), tag(3), tag(1)])
        self.an(mittag(5))
        self.assertEqual(self.enden(), [tag(6), tag(7), tag(8), tag(6)])
        g = self.prognose()
        self.assertEqual((vor["boegen"][self.bid]["start"], g["boegen"][self.bid]["start"]), (tag(0), tag(5)))
        self.assertEqual((g["boegen"][self.bid]["p50"], g["boegen"][self.bid]["p85"]), (tag(8), tag(8)))
        self.assertEqual(self.wartet(g["schritte"]), [None] * 4)
        self.assertNotIn("wartet_auf", g["boegen"][self.bid])
        self.aus()
        self.assertEqual(self.prognose(), vor)

    def test_zufall_verschiebt_sich_genau_um_die_pause(self):
        with mock.patch("amw.planung.durchsatz", return_value=[0, 1, 3]):
            vor = self.prognose()["schritte"]
            self.an(mittag(5))
            g = self.prognose()["schritte"]
        plus = lambda t: (datetime.date.fromisoformat(t) + datetime.timedelta(days=5)).isoformat()
        for aid in vor:
            for k in ("p50", "p85"):
                self.assertEqual(g[aid][k], plus(vor[aid][k]))

    def test_ampel(self):
        self.setze_ziel(tag(4))
        self.assertEqual(self.prognose()["boegen"][self.bid]["ampel"], "gruen")
        self.an(mittag(5))
        self.assertEqual(self.prognose()["boegen"][self.bid]["ampel"], "rot")

    def setze_ziel(self, datum):
        with db.schreiben(self.con):
            self.con.execute("UPDATE bogen SET zieldatum = ? WHERE id = ?", (datum, self.bid))

    def test_laufendes_laeuft_zu_ende(self):
        self.laeuft(self.a)
        self.an(mittag(5))
        self.assertEqual(self.enden(), [tag(1), tag(6), tag(7), tag(6)])
        self.assertEqual(self.prognose()["boegen"][self.bid]["start"], tag(0))

    def test_laufendes_hinter_wartendem_wird_durch_die_pause_nicht_spaeter(self):
        self.laeuft(self.b)                                                                 # b läuft schon, obwohl a noch offen ist
        vor = self.prognose()["schritte"][self.b]["p50"]
        self.an(mittag(50))
        g = self.prognose()["schritte"]
        self.assertLessEqual(g[self.b]["p50"], vor)
        self.assertEqual(g[self.a]["p50"], tag(51))

    def test_laufendes_hinten_in_der_schlange(self):
        bid2 = planung.bogen_neu(self.con, self.pid, "TL", "Lieferung 2")
        x = self.paket("Später", bogen=bid2)
        self.laeuft(x)                                                                      # steht hinter a, b, c, läuft aber
        self.an(mittag(5))
        self.assertEqual(self.prognose()["schritte"][x]["p50"], tag(1))
        self.assertEqual(self.enden(), [tag(6), tag(7), tag(8), tag(6)])

    def test_ohne_ende_unbekannt_fruehestens(self):
        self.laeuft(self.a)
        vor = self.enden()
        self.an()
        g = self.prognose()
        self.assertEqual(self.wartet(g["schritte"]), [None, "Pause", "Pause", "Pause"])
        self.assertEqual(g["boegen"][self.bid]["wartet_auf"], "Pause")
        self.assertEqual(self.enden(), vor)
        self.aus()
        g = self.prognose()
        self.assertEqual(self.wartet(g["schritte"]), [None] * 4)
        self.assertNotIn("wartet_auf", g["boegen"][self.bid])

    def test_nur_laufendes_wartet_nicht(self):
        bid2 = planung.bogen_neu(self.con, self.pid, "TL", "Lieferung 2")
        self.laeuft(self.paket("Allein", agent="CC2", bogen=bid2))
        self.an()
        self.assertNotIn("wartet_auf", self.prognose()["boegen"][bid2])

    def test_ende_vorbei_oder_heute(self):
        vor = self.prognose()
        for bis in (mittag(-3), mittag(0)):                                                 # die Prognose rechnet in Tagen
            with self.subTest(bis=bis):
                self.an(bis)
                self.assertEqual(self.prognose(), vor)
                self.aus()

    def test_sehr_lange_pause(self):
        self.an(mittag(4000))
        self.assertEqual(self.enden(), [tag(4001), tag(4002), tag(4003), tag(4001)])

    def test_plan_stand_bleibt_abweichung_kommt_und_geht(self):
        with db.schreiben(self.con):
            reihenfolge.plan_stand_merken(self.con, self.pid, "TL", self.bid)
        stand = lambda: [tuple(r) for r in self.con.execute("SELECT id, text FROM plan_ereignis WHERE art = ?", (reihenfolge.PLAN_STAND,))]
        vorher = stand()

        def abw():
            a = reihenfolge.abweichung(self.con, self.pid, self.bid)
            assert a is not None                                                            # der Plan-Stand ist gemerkt
            return a["bogen"]

        heute = datetime.datetime.now().astimezone()                                        # der Plan-Stand rechnet ab dem echten Heute
        ende = heute.replace(hour=12, minute=0, second=0, microsecond=0) + datetime.timedelta(days=4)
        self.assertEqual(abw(), 0)
        self.an(zeitplan._iso(ende))
        self.assertEqual(abw(), 4)
        self.assertEqual(stand(), vorher)
        self.aus()
        self.assertEqual((abw(), stand()), (0, vorher))


class AnderesProjekt(Grund):
    def test_pause_gilt_je_projekt(self):
        kern.agent_neu(self.con, self.fremd, "CC1")
        vor, prog = self.plan(), self.prognose()
        for bis in (None, mittag(5)):
            with self.subTest(bis=bis):
                self.an(bis, pid=self.fremd)
                self.assertEqual((self.plan(), self.prognose()), (vor, prog))
                pause.aus(self.con, self.fremd, "TL")

    def test_pause_hier_laesst_das_andere(self):
        kern.agent_neu(self.con, self.fremd, "CC1")
        bid = self.con.execute("SELECT id FROM bogen WHERE projekt_id = ? ORDER BY id", (self.fremd,)).fetchone()[0]
        x = planung.schritt_setzen(self.con, self.fremd, "TL", titel="Dort", bogen_id=bid, agent="CC1", groesse="M")
        self.an(mittag(5))
        self.assertEqual(self.plan(self.fremd)[x]["start_utc"], um(0))
        self.assertEqual(self.prognose(self.fremd)["schritte"][x]["p50"], tag(1))
        self.aus()
        self.an()
        self.assertIsNone(self.plan(self.fremd)[x]["wartet_auf"])
        self.assertNotIn("wartet_auf", self.prognose(self.fremd)["schritte"][x])

    def test_waechter_pause_allein_ist_keine(self):
        vor = self.plan()
        waechter.pause_an("zweimal hintereinander unklar oder abgebrochen")
        self.assertEqual(self.plan(), vor)


class MitPruefpunkt(Grund):
    def test_ohne_ende_gilt_der_pruefpunkt(self):
        p = self.punkt()["paket"]
        self.an()
        z, g = self.plan(), self.prognose()
        self.assertEqual(self.wartet(z) + [z[p]["wartet_auf"]], ["Pause", "Alex", "Alex", "Pause", "Pause"])
        self.assertEqual(self.wartet(g["schritte"]), ["Pause", "Alex", "Alex", "Pause"])
        self.assertEqual(g["schritte"][p]["wartet_auf"], "Pause")
        self.assertEqual(g["boegen"][self.bid]["wartet_auf"], "Alex")
        self.aus()
        self.assertEqual(self.wartet(self.plan()), [None, "Alex", "Alex", None])
        self.assertEqual(self.wartet(self.prognose()["schritte"]), [None, "Alex", "Alex", None])

    def test_gepackt_wartet_auf_den_menschen(self):
        p = self.punkt()["paket"]
        self.fertig(self.a)
        self.packen(p)
        self.setze(p, status="wartet")                                                      # gepackt, läuft nicht mehr
        self.an()
        self.assertEqual(zwischenpruefung.zustand(self.con, p), "wartet_mensch")
        self.assertEqual(self.plan()[p]["wartet_auf"], "Alex")

    def test_mit_ende_fruehestens_nach_der_pause(self):
        self.punkt()
        self.an(mittag(5))
        z, g = self.plan(), self.prognose()
        self.assertEqual(self.wartet(z), [None, "Alex", "Alex", None])
        self.assertEqual(self.wartet(g["schritte"]), [None, "Alex", "Alex", None])
        for aid, x in z.items():
            self.assertGreaterEqual(x["start_utc"], mittag(5), aid)
            self.assertGreater(g["schritte"][aid]["p50"], tag(5), aid)


if __name__ == "__main__":
    unittest.main()
