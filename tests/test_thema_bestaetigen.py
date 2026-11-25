"""A2130 (F5359, Antwort A): „gilt weiter“ nach „neu prüfen“ legt ein freigegebenes Thema nicht wieder dem Menschen vor. Bestätigt
Pfleger oder Lead ohne Textänderung, bleibt es freigegeben; die Bestätigung steht als Ereignis am Thema und hebt „neu prüfen“ auf,
bis wieder ein Beschluss kommt. Nur für genau die Fassung, die der Mensch zuletzt selbst freigegeben hat – sonst wie bisher."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import unittest

from amw import db, kern, themen, workbench
from tests.test_themen_bereich import Grund as Basis, T


class Grund(Basis):
    def frei(self, i):
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.um(i)

    def gilt_weiter(self, i, von="CC1"):
        themen.bestaetigen(self.con, self.pid, von, self.tid)
        self.um(i)

    def bestaetigungen(self):
        return [e for e in themen._ereignisse(self.con, self.pid, self.tid) if e.get("bestaetigt")]

    def fuer_dich(self):
        return [x["id"] for x in workbench._themen_fuer_dich(self.con, self.pid)]

    def neu_pruefen(self):
        """Freigegeben (1), danach ein neuer Beschluss (2)."""
        self.vorlage(0)
        self.frei(1)
        bid = self.beschluss(2)
        self.assertEqual(self.st()["status"], "pruefen")
        return bid


class BleibtFrei(Grund):                                                             # Regel 1
    def test_bestaetigt_bleibt_freigegeben_mit_ereignis(self):
        for von in ("CC1", "TL"):                                                    # Pfleger wie Lead
            with self.subTest(von):
                self.setUp()
                self.neu_pruefen()
                self.gilt_weiter(3, von)
                s = self.st()
                self.assertEqual((s["status"], s["grund"], s["fassung"], s["freigegeben"]), ("frei", None, 1, 1))
                self.assertEqual(self.fuer_dich(), [])
                self.assertEqual([(e["von"], e["zeit_utc"], e["fassung"], e["bestaetigt"]) for e in self.bestaetigungen()],
                                 [(von, T[3], 1, True)])

    def test_ohne_neuen_beschluss_bestaetigt_bleibt_freigegeben(self):
        self.vorlage(0)
        self.frei(1)
        self.gilt_weiter(2)
        self.assertEqual(self.st()["status"], "frei")

    def test_eigene_bearbeitung_gilt_als_freigabe(self):                              # F5358 A
        self.vorlage(0)
        themen.bearbeiten(self.con, self.pid, kern.ENTWICKLER, self.tid, "Mein Text.", erwartet=1)
        self.um(1)
        self.beschluss(2)
        self.gilt_weiter(3)
        self.assertEqual((self.st()["status"], self.st()["freigegeben"]), ("frei", 2))

    def test_tor_konzept_schliesst_wieder(self):
        self.neu_pruefen()
        self.assertFalse(themen.tor(self.con, self.pid)["konzept_zu"])
        schon = len(themen.tor_ereignisse(self.con, self.pid))
        self.gilt_weiter(3)
        self.assertTrue(themen.tor(self.con, self.pid)["konzept_zu"])
        e = themen.tor_ereignisse(self.con, self.pid)
        self.assertEqual((len(e), e[0]["von"], e[0]["themen"]), (schon + 1, "CC1", [{"thema": self.tid, "fassung": 1}]))


class WartetWeiter(Grund):                                                           # Regel 2
    def test_nie_freigegeben(self):
        self.vorlage(0)
        self.beschluss(1)
        self.gilt_weiter(2)
        self.assertEqual(self.st()["status"], "dich")
        self.assertEqual(self.fuer_dich(), [self.tid])

    def test_neue_fassung_nach_der_freigabe(self):
        self.vorlage(0)
        self.frei(1)
        self.vorlage(2, "Neuer Text.")
        self.beschluss(3)
        self.gilt_weiter(4)
        s = self.st()
        self.assertEqual((s["status"], s["fassung"], s["freigegeben"]), ("dich", 2, 1))
        self.frei(5)                                                                 # erst die Freigabe des Menschen …
        self.beschluss(6)
        self.gilt_weiter(7)
        self.assertEqual((self.st()["status"], self.st()["freigegeben"]), ("frei", 2))   # … macht auch sie bestätigbar

    def test_neue_fassung_nach_der_bestaetigung(self):
        self.neu_pruefen()
        self.gilt_weiter(3)
        self.vorlage(4, "Neuer Text.")
        self.assertEqual((self.st()["status"], self.st()["fassung"]), ("dich", 2))

    def test_nach_zurueck(self):
        self.vorlage(0)
        self.frei(1)
        themen.zurueck(self.con, self.pid, kern.ENTWICKLER, self.tid, "anders")       # dieselbe Fassung, einmal freigegeben
        self.um(2)
        self.gilt_weiter(3)
        self.assertEqual(self.st()["status"], "dich")

    def test_zurueck_nach_der_bestaetigung(self):
        self.neu_pruefen()
        self.gilt_weiter(3)
        themen.zurueck(self.con, self.pid, kern.ENTWICKLER, self.tid, "anders")
        self.um(4)
        self.assertEqual(self.st()["status"], "arbeit")


class NeuerBeschluss(Grund):                                                         # Regel 3
    def test_beschluss_nach_der_bestaetigung_wieder_neu_pruefen(self):
        self.neu_pruefen()
        self.gilt_weiter(3)
        b2 = self.beschluss(4, "Zweitfaktor")
        self.assertEqual((self.st()["status"], self.st()["grund"]), ("pruefen", f"B{b2} · 01.11."))
        self.assertEqual(self.fuer_dich(), [])
        self.gilt_weiter(5)                                                           # und wieder bestätigt
        self.assertEqual(self.st()["status"], "frei")
        b3 = self.beschluss(6, "Passwort")
        self.assertEqual((self.st()["status"], self.st()["grund"]), ("pruefen", f"B{b3} · 01.11."))


class Rechte(Grund):                                                                 # Regel 4
    def co_lead(self):
        kern.agent_neu(self.con, self.pid, "CO")
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, co_entwickler="CO", thema_freigabe="co+lead")

    def test_niemand_bekommt_ein_neues_recht(self):
        kern.agent_neu(self.con, self.pid, "CC2")
        self.neu_pruefen()
        with self.assertRaisesRegex(kern.AmwFehler, "nur der Pfleger"):
            themen.bestaetigen(self.con, self.pid, "CC2", self.tid)
        for von in ("CC1", "TL"):
            with self.assertRaisesRegex(kern.AmwFehler, "nur der Mensch"):
                themen.freigeben(self.con, self.pid, von, self.tid)
        self.assertEqual(self.st()["status"], "pruefen")
        frei = lambda: [e["id"] for e in themen._ereignisse(self.con, self.pid, self.tid) if e["art"] == "thema_freigegeben"]
        vorher = frei()
        self.gilt_weiter(3)
        self.assertEqual(frei(), vorher)                                              # die Bestätigung ist keine Freigabe
        self.assertEqual(themen.handlungen(self.st()), ("zurueck", "bearbeiten", "markieren"))

    def test_freigabe_von_co_und_lead_wartet_nach_bestaetigung_wie_bisher(self):
        self.co_lead()
        self.vorlage(0)
        themen.ja_geben(self.con, self.pid, "CO", self.tid)
        self.assertEqual(themen.ja_geben(self.con, self.pid, "TL", self.tid)["status"], "frei")
        self.um(1)
        self.beschluss(2)
        self.assertEqual(self.st()["status"], "pruefen")
        self.gilt_weiter(3)
        self.assertEqual(self.st()["status"], "dich")                                 # nie vom Menschen freigegeben

    def test_mensch_gibt_bei_co_lead_frei(self):
        self.co_lead()
        self.neu_pruefen()
        self.assertEqual(self.st()["ja_fehlt"], ["Co-Entwickler", "Lead"])
        self.gilt_weiter(3)
        s = self.st()
        self.assertEqual(s["status"], "frei")
        self.assertNotIn("ja_fehlt", s)
        with self.assertRaisesRegex(kern.AmwFehler, "da steht keine Freigabe an"):
            themen.ja_geben(self.con, self.pid, "TL", self.tid)

    def test_nur_mensch_bleibt(self):
        self.co_lead()
        self.vorlage(0)
        themen.nur_mensch_setzen(self.con, self.pid, "CC1", self.tid)
        self.um(0)
        self.gilt_weiter(1)                                                           # nie freigegeben: wartet weiter auf ihn
        s = self.st()
        self.assertEqual((s["status"], s["nur_mensch"]), ("dich", True))
        with self.assertRaisesRegex(kern.AmwFehler, "bleibt beim Menschen"):
            themen.ja_geben(self.con, self.pid, "TL", self.tid)
        self.frei(2)
        self.beschluss(3)
        self.gilt_weiter(4)
        s = self.st()
        self.assertEqual((s["status"], s["nur_mensch"]), ("frei", True))


class AlteEreignisse(Grund):                                                         # Regel 5
    def alt(self, i, bestaetigt=True):
        """So schrieb es bestaetigen vor A2130: Ereignis „vorgelegt“ mit bestaetigt: true und Zeit am Thema."""
        with db.schreiben(self.con):
            self.con.execute("UPDATE thema SET bestaetigt_utc = ?, bestaetigt_von = 'CC1' WHERE id = ?", (T[i], self.tid))
            if bestaetigt:
                db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=T[i], von="CC1", art="thema_vorgelegt",
                             text=json.dumps({"thema": self.tid, "fassung": 1, "bestaetigt": True}))

    def test_altes_ereignis_genauso(self):
        self.neu_pruefen()
        self.alt(3)
        self.assertEqual((self.st()["status"], self.fuer_dich()), ("frei", []))
        bid = self.beschluss(4)
        self.assertEqual((self.st()["status"], self.st()["grund"]), ("pruefen", f"B{bid} · 01.11."))

    def test_bestaetigung_ohne_ereignis_genauso(self):                                # vor A1896: nur die Zeit am Thema
        self.neu_pruefen()
        self.alt(3, bestaetigt=False)
        self.assertEqual(self.st()["status"], "frei")

    def test_altes_ereignis_nach_zurueck_wartet(self):
        self.vorlage(0)
        self.frei(1)
        themen.zurueck(self.con, self.pid, kern.ENTWICKLER, self.tid, "anders")
        self.um(2)
        self.alt(3)
        self.assertEqual(self.st()["status"], "dich")


class GleicheSekunde(Grund):
    """Alles in einer Sekunde: es gilt die Ereignis-Nummer."""
    def alles(self, *schritte):
        for s in schritte:
            s()
        self.um(1)
        with db.schreiben(self.con):
            self.con.execute("UPDATE beschluss SET angelegt_utc = ?", (T[1],))
        return self.st()["status"]

    def pflegen(self):
        themen.pflegen(self.con, self.pid, "CC1", self.tid, "Text.")

    def freigabe(self):
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)

    def zurueckgeben(self):
        themen.zurueck(self.con, self.pid, kern.ENTWICKLER, self.tid, "anders")

    def bestaetigung(self):
        themen.bestaetigen(self.con, self.pid, "CC1", self.tid)

    def test_freigabe_dann_bestaetigung(self):
        self.assertEqual(self.alles(self.pflegen, self.freigabe, self.bestaetigung), "frei")

    def test_bestaetigung_dann_freigabe(self):
        self.assertEqual(self.alles(self.pflegen, self.bestaetigung, self.freigabe), "frei")

    def test_freigabe_zurueck_bestaetigung(self):
        self.assertEqual(self.alles(self.pflegen, self.freigabe, self.zurueckgeben, self.bestaetigung), "dich")

    def test_freigabe_bestaetigung_zurueck(self):
        self.assertEqual(self.alles(self.pflegen, self.freigabe, self.bestaetigung, self.zurueckgeben), "arbeit")

    def test_freigabe_neue_fassung_bestaetigung(self):
        self.assertEqual(self.alles(self.pflegen, self.freigabe, self.pflegen, self.bestaetigung), "dich")

    def test_beschluss_vor_und_nach_der_bestaetigung(self):
        self.vorlage(0)
        self.frei(0)
        self.beschluss(1)
        self.assertEqual(self.alles(self.bestaetigung), "frei")                       # vorher da: mit bestätigt
        b2 = self.beschluss(1, "Zweitfaktor")                                         # danach, in derselben Sekunde
        self.assertEqual((self.st()["status"], self.st()["grund"]), ("pruefen", f"B{b2} · 01.11."))


if __name__ == "__main__":
    unittest.main()
