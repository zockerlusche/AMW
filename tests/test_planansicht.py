"""A1950 (K6, TH164): Daten und Handlungen der Ansichten Grob- und Feinplanung – Meilensteine mit ihren Themen (aus den Paketen),
Pakete mit Wer/Nach/Prüfung/Kosten, Freigabe je Meilenstein und je Plan durch Co, Lead oder Mensch (wer, als Fakt), Zurück mit
Notiz an den Lead, Früher/Später, „Jetzt starten“ erst wenn alles freigegeben ist; Tor-Zeile grob → fein → Umsetzung."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import tempfile
import unittest
from unittest import mock

from amw import arbeitspaket, db, kern, planansicht, planung, themen, workbench


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid, "Co")
        kern.projekt_einstellen(self.con, self.pid, "TL", co_entwickler="Co")
        self.th = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        self.m1 = planung.bogen_neu(self.con, self.pid, "TL", "Anmelden", abnahme="Vorführung")
        self.m2 = planung.bogen_neu(self.con, self.pid, "TL", "Sicherung", abnahme="Bericht")
        self.a1 = planung.schritt_setzen(self.con, self.pid, "TL", titel="SSO bauen", bogen_id=self.m1, agent="CC1", groesse="M", art="sicherheit")
        self.a2 = planung.schritt_setzen(self.con, self.pid, "TL", titel="Tests", bogen_id=self.m1, nach=[self.a1])
        arbeitspaket.setzen(self.con, self.pid, "TL", self.a2, art="p", modell="sonnet")
        themen.verweise_setzen(self.con, self.pid, "TL", self.a1, [f"TH{self.th}"])

    def d(self):
        return planansicht.daten(self.con, self.pid)

    def m(self, bid):
        return next(x for x in self.d()["meilensteine"] if x["id"] == bid)

    def post(self, an):
        return [(r["art"], r["kurz"]) for r in self.con.execute(
            "SELECT n.art, n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? AND n.von = 'AMW' ORDER BY n.id", (an,))]


class Daten(Grund):
    def test_meilensteine_mit_themen_und_paketen(self):
        d = self.d()
        self.assertEqual((d["tor"], d["grob_zu"], d["starten"], d["hat_themen"]), ("grob", False, False, True))
        m = self.m(self.m1)
        self.assertEqual((m["endet_mit"], m["themen"]), ("Vorführung", [{"id": self.th, "name": "Anmeldung"}]))   # aus den Paketen
        p1, p2 = m["pakete"]
        self.assertEqual((p1["wer"], p1["pruefung"], p2["wer"], p2["nach"], p2["pruefung"]), ("CC1", "–", "-p sonnet", [self.a1], "AMW"))
        self.assertEqual(self.m(self.m2)["pakete"], [])
        self.assertEqual(workbench.daten_planung(self.con, self.pid)["planansicht"]["tor"], "grob")

    def test_kosten_geschaetzt_aus_der_zelle(self):
        with mock.patch("amw.empfehlung.zellen", return_value={("heikel", "M"): {"median": 1.8, "n": 5, "rot": 0}}):
            m = self.m(self.m1)
        self.assertEqual((m["pakete"][0]["usd"], m["pakete"][0]["gemessen"], m["pakete"][1]["usd"], m["summe"]), (1.8, False, None, 1.8))

    def test_ohne_meilenstein(self):
        th2 = themen.neu(self.con, self.pid, "TL", "Online-Seite", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", th2, "Text.")
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, th2)
        self.assertEqual([x["id"] for x in self.d()["ohne_meilenstein"]], [th2])


class Handlungen(Grund):
    def test_freigabe_grob_dann_plan_wer_als_fakt(self):
        with self.assertRaisesRegex(kern.AmwFehler, "Co, Lead oder der Mensch"):
            planansicht.freigeben(self.con, self.pid, "CC1", self.m1, "grob")
        with self.assertRaisesRegex(kern.AmwFehler, "erst den Meilenstein freigeben"):
            planansicht.freigeben(self.con, self.pid, "TL", self.m1, "plan")
        planansicht.freigeben(self.con, self.pid, "Co", self.m1, "grob")                         # Co darf (B2913/B2914)
        g = self.m(self.m1)["grob"]
        self.assertEqual((g["frei"], g["von"]), (True, "Co"))
        with self.assertRaisesRegex(kern.AmwFehler, "schon freigegeben"):
            planansicht.freigeben(self.con, self.pid, "TL", self.m1, "grob")
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m2, "grob")
        self.assertEqual(self.d()["tor"], "fein")
        with self.assertRaisesRegex(kern.AmwFehler, "noch keine Pakete"):
            planansicht.freigeben(self.con, self.pid, "TL", self.m2, "plan")
        planansicht.freigeben(self.con, self.pid, "TL", self.m1, "plan")
        self.assertTrue(self.d()["starten"])                                                   # M2 ist „später“, zählt nicht

    def test_zurueck_mit_notiz_an_den_lead(self):
        planansicht.freigeben(self.con, self.pid, "TL", self.m1, "grob")
        with self.assertRaisesRegex(kern.AmwFehler, "nur mit Notiz"):
            planansicht.zurueck(self.con, self.pid, kern.ENTWICKLER, self.m1, "grob", " ")
        planansicht.zurueck(self.con, self.pid, kern.ENTWICKLER, self.m1, "grob", "Erst die Sicherung")
        g = self.m(self.m1)["grob"]
        self.assertEqual((g["frei"], g["notiz"]), (False, "Erst die Sicherung"))
        self.assertEqual(self.post("TL")[-1], ("auftrag", "Meilenstein 1 „Anmelden“ zurück (Meilenstein): Erst die Sicherung"))

    def test_frueher_spaeter(self):
        planansicht.verschieben(self.con, self.pid, "Co", self.m2, "frueher")
        self.assertEqual([m["id"] for m in self.d()["meilensteine"]], [self.m2, self.m1])
        with self.assertRaisesRegex(kern.AmwFehler, "ganz vorn"):
            planansicht.verschieben(self.con, self.pid, "TL", self.m2, "frueher")
        with self.assertRaisesRegex(kern.AmwFehler, "Reihenfolge ändern"):
            planansicht.verschieben(self.con, self.pid, "CC1", self.m2, "spaeter")

    def test_jetzt_starten_erst_wenn_alles_frei(self):
        with self.assertRaisesRegex(kern.AmwFehler, "erst, wenn alle"):
            planansicht.jetzt_starten(self.con, self.pid, "TL")
        for bid in (self.m1, self.m2):
            planansicht.freigeben(self.con, self.pid, "TL", bid, "grob")
        planansicht.freigeben(self.con, self.pid, "TL", self.m1, "plan")
        self.assertEqual(planansicht.jetzt_starten(self.con, self.pid, "TL"), [1])
        self.assertEqual((self.m(self.m1)["status"], self.m(self.m2)["status"], self.d()["tor"]), ("aktiv", "geplant", "umsetzung"))


if __name__ == "__main__":
    unittest.main()
