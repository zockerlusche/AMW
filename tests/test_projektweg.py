"""A2023: der Projektweg – fünf Schritte (offen ○, dran ●, erledigt ✓) abgeleitet aus tore.stand, Freigaben gelesen aus
plan_ereignis (Konzept einmal, Grobplan einmal, Feinplan und Abnahme je Meilenstein), Übergänge nur in Reihenfolge,
Wiedereinstieg nach Neustart mit demselben Stand – ohne neue Tabellen und ohne eigenen Speicher."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import unittest

from amw import db, kern, planansicht, planung, projektweg, themen, tore
from tests.test_tore import Basis


class Projektweg(Basis):
    def zustaende(self):
        return [x["zustand"] for x in projektweg.sicht(self.con, self.pid)["schritte"]]

    def fertig_machen(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', fertig_utc = ?, beleg = 'abc1234' WHERE bogen_id = ?",
                             (db.jetzt(), self.m1))
        planung.bogen_status(self.con, self.pid, "TL", self.m1, "fertig")

    def test_anfang_konzept_ist_dran(self):
        s = projektweg.sicht(self.con, self.pid)
        self.assertEqual([x["schritt"] for x in s["schritte"]], ["konzept", "grob", "fein", "umsetzung", "abschluss"])
        self.assertEqual([x["name"] for x in s["schritte"]], ["Konzept", "Grobplan", "Feinplan", "Umsetzung", "Abschluss"])
        self.assertEqual(self.zustaende(), ["dran", "offen", "offen", "offen", "offen"])
        self.assertEqual([x["zeichen"] for x in s["schritte"]], ["●", "○", "○", "○", "○"])
        k = s["schritte"][0]
        self.assertEqual((s["dran"], k["fehlt"], k["wer"]), ("konzept", "0 von 1 Themen freigegeben", ["Entwickler"]))
        self.assertEqual(s["schritte"][1]["fehlt"], s["schritte"][1]["text"])   # offen: was dort noch fehlt
        self.assertEqual(s["schritte"][1]["wer"], [])                       # nur der Schritt, der dran ist, hat ein „wer“
        self.assertIn("● Konzept ○ Grobplan", s["zeile"])
        self.assertIn("dran: Konzept", s["zeile"])

    def test_der_ganze_weg_mit_freigaben(self):
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.th)
        s = projektweg.sicht(self.con, self.pid)
        self.assertEqual(self.zustaende(), ["erledigt", "dran", "offen", "offen", "offen"])
        self.assertEqual(s["freigaben"]["konzept"], {"frei": True})
        self.assertEqual(s["freigaben"]["grob"], {"frei": False, "n": 0, "g": 2})
        self.assertEqual(s["schritte"][1]["wer"], ["Entwickler"])          # alle Themen drin – das Ja fehlt
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "grob")
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m2, "grob")
        s = projektweg.sicht(self.con, self.pid)
        self.assertEqual(self.zustaende(), ["erledigt", "erledigt", "dran", "offen", "offen"])
        self.assertEqual(s["freigaben"]["grob"]["frei"], True)
        self.assertEqual([(f["bogen"], f["frei"]) for f in s["freigaben"]["fein"]], [(self.m1, False)])   # je Meilenstein mit Paketen
        self.assertEqual(s["schritte"][2]["wer"], ["Entwickler"])
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "plan")
        s = projektweg.sicht(self.con, self.pid)
        self.assertEqual([(f["bogen"], f["frei"]) for f in s["freigaben"]["fein"]], [(self.m1, True)])
        self.assertEqual((s["dran"], s["schritte"][2]["wer"]), ("fein", ["TL"]))   # jetzt „Jetzt starten“
        planung.bogen_status(self.con, self.pid, "TL", self.m2, "verworfen")
        planansicht.jetzt_starten(self.con, self.pid, kern.ENTWICKLER)
        s = projektweg.sicht(self.con, self.pid)
        self.assertEqual(self.zustaende(), ["erledigt", "erledigt", "erledigt", "dran", "offen"])
        self.assertEqual((s["schritte"][3]["fehlt"], s["schritte"][3]["wer"]), ("0 von 2 Paketen fertig", ["TL"]))
        self.fertig_machen()
        s = projektweg.sicht(self.con, self.pid)
        self.assertEqual(self.zustaende(), ["erledigt"] * 4 + ["dran"])
        self.assertEqual(s["freigaben"]["abnahme"], [{"bogen": self.m1, "nr": 1, "titel": "Anmelden", "frei": False, "bericht": None}])
        self.assertEqual(s["schritte"][4]["wer"], ["AMW"])                  # erst kommt der Bericht
        tore.runde(self.con, self.pid)
        self.assertEqual(projektweg.sicht(self.con, self.pid)["schritte"][4]["wer"], ["Entwickler"])
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "abschluss")
        s = projektweg.sicht(self.con, self.pid)
        self.assertEqual((self.zustaende(), s["dran"]), (["erledigt"] * 5, None))
        self.assertTrue(s["freigaben"]["abnahme"][0]["frei"])
        self.assertIn("alle Schritte erledigt", s["zeile"])
        self.assertEqual(projektweg.wiedereinstieg(self.con, self.pid)["schritt"], None)

    def test_co_und_lead_sind_dran_bei_co_lead(self):
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, thema_freigabe="co+lead")
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.th)
        self.assertEqual(projektweg.sicht(self.con, self.pid)["schritte"][1]["wer"], ["Co", "TL"])

    def test_zurueck_oeffnet_den_schritt_wieder(self):
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.th)
        for b in (self.m1, self.m2):
            planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, b, "grob")
        self.assertEqual(projektweg.sicht(self.con, self.pid)["dran"], "fein")
        planansicht.zurueck(self.con, self.pid, kern.ENTWICKLER, self.m2, "grob", "Ziel unklar")
        s = projektweg.sicht(self.con, self.pid)
        self.assertEqual((s["dran"], s["freigaben"]["grob"]), ("grob", {"frei": False, "n": 1, "g": 2}))
        self.assertIn("1 von 2 Meilensteinen freigegeben", s["schritte"][1]["fehlt"])

    def test_uebergaenge_nur_in_reihenfolge(self):
        self.assertEqual(projektweg.uebergang_pruefen(self.con, self.pid, "konzept"), "dran")
        with self.assertRaisesRegex(kern.AmwFehler, "Feinplan geht erst nach Konzept"):
            projektweg.uebergang_pruefen(self.con, self.pid, "fein")
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.th)
        self.assertEqual(projektweg.uebergang_pruefen(self.con, self.pid, "Grobplan"), "dran")
        self.assertEqual(projektweg.uebergang_pruefen(self.con, self.pid, "konzept"), "erledigt")
        with self.assertRaisesRegex(kern.AmwFehler, "Abschluss geht erst nach Grobplan – dort fehlt: 1 von 1 Themen"):
            projektweg.uebergang_pruefen(self.con, self.pid, "abschluss")
        with self.assertRaisesRegex(kern.AmwFehler, "gibt es nicht"):
            projektweg.uebergang_pruefen(self.con, self.pid, "Zauberei")

    def test_erledigt_nur_wenn_alles_davor_erledigt(self):
        """Selbst wenn ein späteres Tor zu wäre, zählt der Schritt erst, wenn alle davor erledigt sind."""
        echt = tore.stand(self.con, self.pid)
        verdreht = dict(echt, tore=[dict(x, zu=x["tor"] != "konzept") for x in echt["tore"]])
        from unittest import mock
        with mock.patch("amw.tore.stand", return_value=verdreht):
            self.assertEqual(self.zustaende(), ["dran", "offen", "offen", "offen", "offen"])

    def test_wiedereinstieg_nach_neustart_derselbe_stand_ohne_speicher(self):
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.th)
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "grob")
        tabellen = lambda c: sorted(r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'"))   # noqa: E731
        vorher_tab = tabellen(self.con)
        n_ereignisse = self.con.execute("SELECT count(*) FROM plan_ereignis").fetchone()[0]
        vorher = projektweg.sicht(self.con, self.pid)
        w = projektweg.wiedereinstieg(self.con, self.pid)
        self.assertEqual((w["schritt"], w["name"], w["wer"]), ("grob", "Grobplan", ["Entwickler"]))
        self.assertIn("1 von 2 Meilensteinen freigegeben", w["fehlt"])
        self.assertEqual(self.con.execute("SELECT count(*) FROM plan_ereignis").fetchone()[0], n_ereignisse)   # nur lesen
        self.con.close()                                                    # Neustart: neue Verbindung auf dieselbe Datei
        self.con = db.verbinde(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        self.assertEqual(projektweg.sicht(self.con, self.pid), vorher)
        self.assertEqual(projektweg.wiedereinstieg(self.con, self.pid), w)
        self.assertEqual(tabellen(self.con), vorher_tab)                    # keine neuen Tabellen


if __name__ == "__main__":
    unittest.main()
