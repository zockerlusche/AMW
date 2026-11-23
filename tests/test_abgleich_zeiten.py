"""A2001: Seit 17.11. brach die Synchronisierung alle ~2 min ab – Aufgaben aus der Bus-Übernahme (21.10.) tragen Zeiten im alten
Format „2026-10-21 07:08:44“, die Messung (A1844) las nur „…T…Z“. Zeiten liest jetzt db.utc_lesen tolerant an einer Stelle; eine
Ansicht, die trotzdem scheitert, wird übersprungen (der Rest geht hoch), derselbe Fehler nach 3 Runden einmal an den Lead."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime
import os
import tempfile
import unittest
from unittest import mock

from amw import abgleich, db, kern, messung, workbench

UTC = datetime.timezone.utc


class Zeitlesen(unittest.TestCase):
    def test_formate(self):
        soll = datetime.datetime(2026, 10, 21, 7, 8, 44, tzinfo=UTC)
        for text in ("2026-10-21T07:08:44Z", "2026-10-21 07:08:44", "2026-10-21T07:08:44.123Z", "2026-10-21T07:08:44+00:00",
                     "2026-10-21 07:08:44 UTC"):
            self.assertEqual(db.utc_lesen(text), soll, text)
        self.assertEqual(db.utc_lesen("2026-10-21 07:08"), soll.replace(second=0))
        self.assertEqual(db.utc_sek("1970-01-01T00:01:00Z"), 60)
        for falsch in ("", None, "gestern", "21.10.2026 07:08", "2026-10-21T07:08:44+02:00"):
            with self.assertRaises(ValueError, msg=falsch):
                db.utc_lesen(falsch)


class Grund(unittest.TestCase):
    def setUp(self):
        alt = abgleich.VERZEICHNIS["projekte"]
        abgleich.VERZEICHNIS["projekte"] = []
        self.addCleanup(abgleich.VERZEICHNIS.__setitem__, "projekte", alt)
        self.ordner = tempfile.TemporaryDirectory()
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.ab = abgleich.Abgleich(self.con, abgleich.SqliteSpeicher(os.path.join(self.ordner.name, "online.db")), self.pid)
        self.ab.schema()

    def alte_aufgabe(self):
        """Wie A956/A975 aus der Bus-Übernahme: angelegt_utc im Format von SQLite datetime('now')."""
        a = kern.aufgabe_neu(self.con, self.pid, "TL", "Aus dem alten Bus", agent="CC1")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET angelegt_utc = '2026-10-21 07:08:44' WHERE id = ?", (a,))
        return a

    def lead_post(self):
        return [r["kurz"] for r in kern.offene(self.con, self.pid, "TL") if r["von"] == "AMW"]


class AlteZeiten(Grund):
    def test_alte_zeit_bricht_nichts_ab(self):
        a = self.alte_aufgabe()
        m = messung.je_aufgabe(self.con, self.pid, a)                 # vorher: ValueError … does not match format
        self.assertIsNotNone(m)
        self.assertIn("messung", workbench.daten_aufgabe(self.con, self.pid, a))
        fehler = []
        self.assertIn(f"/api/aufgabe?id={a}", abgleich.ansichten(self.con, self.pid, fehler=fehler))
        self.assertEqual(fehler, [])
        self.assertGreater(self.ab.hochladen(alle=True), 0)


class Ueberspringen(Grund):
    def test_eine_kaputte_ansicht_haelt_den_rest_nicht_auf_und_meldet_nach_3_runden_einmal(self):
        a = kern.aufgabe_neu(self.con, self.pid, "TL", "Kaputt", agent="CC1")
        b = kern.aufgabe_neu(self.con, self.pid, "TL", "Heil", agent="CC1")
        echt = workbench.daten_aufgabe

        def kaputt(con, pid, aid):
            if aid == a:
                raise ValueError("time data 'x' does not match format")
            return echt(con, pid, aid)

        with mock.patch.object(workbench, "daten_aufgabe", kaputt), self.assertLogs("amw.abgleich", "WARNING") as logs:
            fehler = []
            ans = abgleich.ansichten(self.con, self.pid, fehler=fehler)
            self.assertNotIn(f"/api/aufgabe?id={a}", ans)
            self.assertIn(f"/api/aufgabe?id={b}", ans)
            self.assertIn("/api/start", ans)
            self.assertEqual(fehler, [(f"/api/aufgabe?id={a}", "ValueError: time data 'x' does not match format")])
            for runde in range(1, 6):
                self.assertGreater(self.ab.hochladen(alle=True), 0)
                self.assertEqual(len(self.lead_post()), 0 if runde < abgleich.FEHLER_RUNDEN else 1, runde)
        self.assertEqual(len([z for z in logs.output if "übersprungen" in z]), 1)          # ins Log nur einmal
        self.assertIn(f"/api/aufgabe?id={a} lässt sich seit 3 Runden nicht bauen", self.lead_post()[0])
        self.ab.hochladen(alle=True)                                        # Fehler weg → Zähler weg
        self.assertEqual(self.ab.fehler, {})

    def test_ohne_liste_fliegt_der_fehler_wie_bisher(self):
        with mock.patch.object(workbench, "daten_themen", side_effect=ValueError("kaputt")):
            with self.assertRaises(ValueError):
                abgleich.ansichten(self.con, self.pid)


if __name__ == "__main__":
    unittest.main()
