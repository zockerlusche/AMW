"""A2040 (D1531 §10, V10): Kosten aus beiden Quellen – Kosten-Zähler der Fenster-Sitzungen UND erfasste Läufe (Headless-Pakete
aus stream-json). Planansicht, Abschlussbericht und Prognose-Warnung lasen nur den Zähler: ein Headless-Paket erschien dort
geschätzt oder gar nicht und weckte den Lead nie. Dazu Summe und Rest je Projekt (bisher, noch, gesamt) als Daten, API und Befehl."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import arbeitspaket, db, kern, messung, planansicht, planung, tore, workbench

ZELLEN = {("einfach", "S"): {"median": 0.5, "n": 6, "rot": 0}, ("mittel", "M"): {"median": 2.0, "n": 6, "rot": 0}}


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
        self.m1 = planung.bogen_neu(self.con, self.pid, "TL", "Anmelden", abnahme="Bericht")
        self.p = planung.schritt_setzen(self.con, self.pid, "TL", titel="Tests schreiben", bogen_id=self.m1, groesse="S", art="mechanisch")
        arbeitspaket.setzen(self.con, self.pid, "TL", self.p, art="p", modell="sonnet")
        self.f = planung.schritt_setzen(self.con, self.pid, "TL", titel="Seite bauen", bogen_id=self.m1, agent="CC1", groesse="M",
                                        art="fehlersuche")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET begonnen_utc = ?, status = 'laeuft' WHERE id IN (?, ?)", (db.jetzt(), self.p, self.f))
        z = mock.patch("amw.empfehlung.zellen", return_value=ZELLEN)
        z.start()
        self.addCleanup(z.stop)

    def headless(self, aid, usd):
        """Wie der Arbeiter nach einem p-Lauf: Kosten aus der stream-json-Ausgabe erfassen."""
        messung.erfassen(self.con, self.pid, "AMW", aid, json_text='{"total_cost_usd": %s, "num_turns": 9, "duration_ms": 60000}' % usd)


class Je_Paket(Grund):
    def test_planansicht_zeigt_headless_gemessen(self):
        self.headless(self.p, 1.25)
        p = next(x for x in planansicht.daten(self.con, self.pid)["meilensteine"][0]["pakete"] if x["id"] == self.p)
        self.assertEqual((p["usd"], p["gemessen"]), (1.25, True))                      # vorher: ≈ 0.50 geschätzt

    def test_beide_quellen_zusammen(self):
        self.headless(self.f, 0.75)                                                        # ein Lauf zum Fenster-Paket (z. B. Prüfung)
        with mock.patch("amw.aufwand.je_aufgabe", return_value={"usd": 2.5, "modelle": ["Opus/high"]}):
            k = messung.kosten(self.con, self.pid, self.f)
        self.assertEqual((k["usd"], k["zaehler_usd"], k["erfasst_usd"], k["modelle"]), (3.25, 2.5, 0.75, ["Opus/high"]))
        self.assertIsNone(messung.kosten(self.con, self.pid, self.p))                     # nichts gemessen
        messung.erfassen(self.con, self.pid, "AMW", self.p, unbekannt=True)
        self.assertEqual(messung.kosten(self.con, self.pid, self.p)["unbekannt"], 1)

    def test_abschlussbericht_nennt_headless_kosten(self):
        self.headless(self.p, 1.25)
        text = tore.bericht_text(self.con, self.pid, self.m1)
        text = text if isinstance(text, str) else str(text)
        self.assertIn("| 1.25 $ |", text)
        self.assertIn("A" + str(self.p) + " kostete 1.25 $ statt ≈ 0.50 $", text)       # Lehre: über der Prognose

    def test_prognose_warnung_auch_fuer_headless(self):
        planung.bogen_status(self.con, self.pid, "TL", self.m1, "aktiv")
        self.headless(self.p, 1.25)                                                        # > 1,5 × 0,50
        self.assertEqual(tore.prognose_pruefen(self.con, self.pid), [f"A{self.p} über Prognose"])
        self.assertEqual(tore.prognose_pruefen(self.con, self.pid), [])                    # einmal


class Je_Projekt(Grund):
    def test_bisher_noch_gesamt(self):
        self.headless(self.p, 0.2)                                                         # offen, Schätzung 0,50 → noch 0,30
        fertig = planung.schritt_setzen(self.con, self.pid, "TL", titel="Alt", bogen_id=self.m1, groesse="S", art="text")
        self.headless(fertig, 1.0)
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc1234' WHERE id = ?", (fertig,))
        planung.schritt_setzen(self.con, self.pid, "TL", titel="Ohne Größe", bogen_id=self.m1)
        k = messung.projekt_kosten(self.con, self.pid)
        self.assertEqual((k["bisher"], k["erfasst_usd"], k["fenster_usd"]), (1.2, 1.2, 0.0))
        self.assertEqual((k["noch"], k["gesamt"], k["offen"], k["ohne_schaetzung"]), (2.3, 3.5, 3, 1))   # 0,30 + 2,00 (Seite)
        self.assertEqual(workbench.daten_kosten(self.con, self.pid), k)

    def test_noch_nie_unter_null(self):
        self.headless(self.p, 5.0)                                                         # teurer als geschätzt
        k = messung.projekt_kosten(self.con, self.pid)
        self.assertEqual(k["noch"], 2.0)                                                   # nur die Seite (M, mittel)

    def test_befehl(self):
        self.headless(self.p, 0.2)
        from amw import cli
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus):
            rc = cli.main(["--projekt", "P", "messung", "--gesamt", "--von", "TL"])
        self.assertEqual(rc, 0, aus.getvalue())
        self.assertIn("Kosten bisher 0.20 $", aus.getvalue())
        self.assertIn("noch ≈ 2.30 $ · gesamt ≈ 2.50 $", aus.getvalue())


if __name__ == "__main__":
    unittest.main()
