"""Verbrauch je Aufgabe und je Agent (A1611 E1): Zuwächse des Kosten-Zählers gehören zur zuletzt begonnenen offenen
Aufgabe; erster Messpunkt zählt nicht, ein gesunkener Zähler zählt neu; gleiche Kennung in zwei Projekten bleibt
getrennt; Median der letzten fertigen; Anzeige in Aufgabe, Agent, Befehlszeile und Workbench (DE+EN)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import re
import tempfile
import unittest
from unittest import mock

from amw import aufwand, db, kern, workbench

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def z(stunde, minute=0):
    return f"2026-11-12T{stunde:02d}:{minute:02d}:00Z"


class Aufwand(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Eins", angelegt_utc=db.jetzt())
            self.pid2 = db.einfuegen(self.con, "projekt", name="Zwei", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid2, "CC1")

    def aufgabe(self, titel, beginn, fertig=None, pid=None):
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "aufgabe", projekt_id=pid or self.pid, titel=titel, agent="CC1", angelegt_von="TL",
                                angelegt_utc=beginn, status="fertig" if fertig else "laeuft", begonnen_utc=beginn, fertig_utc=fertig)

    def messen(self, punkte, modell="Opus 5.5", stufe="high", pid=None):
        """punkte = [(zeit, kosten_usd)] einer neuen Sitzung."""
        gid = kern.agent_zeile(self.con, pid or self.pid, "CC1")["id"]
        with db.schreiben(self.con):
            sid = db.einfuegen(self.con, "sitzung", agent_id=gid, gestartet_utc=punkte[0][0], modell=modell, denkstufe=stufe)
            for zeit, usd in punkte:
                db.einfuegen(self.con, "verbrauch", sitzung_id=sid, agent="CC1", zeit_utc=zeit, kosten_usd=usd)
        return sid

    def test_nacheinander_und_erster_punkt(self):
        a = self.aufgabe("eins", z(8), z(9))
        b = self.aufgabe("zwei", z(9, 30), z(11))
        self.messen([(z(8, 10), 5.0), (z(8, 50), 7.0), (z(9, 40), 10.0), (z(10, 30), 16.0)])
        self.assertEqual(aufwand.je_aufgabe(self.con, self.pid, a), {"usd": 2.0, "modelle": ["Opus 5.5/high"]})   # 5 $ davor zählen nicht
        self.assertEqual(aufwand.je_aufgabe(self.con, self.pid, b)["usd"], 9.0)

    def test_dazwischen_zaehlt_zur_zuletzt_begonnenen(self):
        a = self.aufgabe("lang", z(8), z(12))                 # wartet ab 9, B läuft 9:30–10:30, dann A weiter
        b = self.aufgabe("kurz", z(9, 30), z(10, 30))
        self.messen([(z(8, 5), 0.0), (z(9), 3.0), (z(10), 4.0), (z(10, 20), 6.0), (z(11), 10.0)])
        self.assertEqual(aufwand.je_aufgabe(self.con, self.pid, b)["usd"], 3.0)
        self.assertEqual(aufwand.je_aufgabe(self.con, self.pid, a)["usd"], 7.0)

    def test_gesunkener_zaehler_und_modelle_nach_anteil(self):
        a = self.aufgabe("eins", z(8), z(12))
        self.messen([(z(8, 5), 0.0), (z(9), 2.0)], modell="Sonnet 5.5", stufe="medium")
        self.messen([(z(9, 5), 10.0), (z(10), 14.0), (z(11), 3.0)])     # 4 $, dann neu gezählt: 3 $
        v = aufwand.je_aufgabe(self.con, self.pid, a)
        self.assertEqual(v, {"usd": 9.0, "modelle": ["Opus 5.5/high", "Sonnet 5.5/medium"]})

    def test_projekte_getrennt_und_ohne_messwert(self):
        a = self.aufgabe("eins", z(8), z(12))
        self.messen([(z(8, 5), 0.0), (z(9), 50.0)], pid=self.pid2)      # gleiche Kennung, anderes Projekt
        self.assertIsNone(aufwand.je_aufgabe(self.con, self.pid, a))
        self.assertIsNone(aufwand.je_agent(self.con, self.pid, "CC1"))
        with db.schreiben(self.con):
            nie = db.einfuegen(self.con, "aufgabe", projekt_id=self.pid, titel="neu", agent="CC1", angelegt_von="TL", angelegt_utc=z(7))
        self.assertIsNone(aufwand.je_aufgabe(self.con, self.pid, nie))

    def test_agent_median_laufend_und_anzeige(self):
        ids = [self.aufgabe(f"A{i}", z(8 + i), z(8 + i, 50)) for i in range(4)]
        lauf = self.aufgabe("läuft", z(13))
        punkte, usd = [(z(7, 50), 0.0)], 0.0
        for i, betrag in enumerate([1.0, 2.0, 4.0, 10.0]):
            usd += betrag
            punkte.append((z(8 + i, 30), usd))
        punkte.append((z(13, 30), usd + 0.5))
        self.messen(punkte)
        w = aufwand.je_agent(self.con, self.pid, "CC1")
        self.assertEqual([x["id"] for x in w["aufgaben"]], list(reversed(ids)))       # zuletzt fertige zuerst
        self.assertEqual(w["median"], 3.0)
        self.assertEqual(w["n"], 4)
        self.assertEqual((w["laufend"]["id"], w["laufend"]["usd"]), (lauf, 0.5))
        self.assertEqual(aufwand.je_agent(self.con, self.pid, "CC1", letzte=2)["median"], 7.0)
        self.assertEqual(workbench.daten_aufgabe(self.con, self.pid, ids[3])["verbrauch"]["usd"], 10.0)
        self.assertEqual(workbench.daten_agent(self.con, self.pid, "CC1")["aufwand"]["median"], 3.0)
        from amw import cli
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")}), contextlib.redirect_stdout(aus):
            self.assertEqual(cli.main(["aufgabe", "zeige", str(ids[3]), "--projekt", "Eins", "--von", "TL"]), 0)
            self.assertEqual(cli.main(["agent", "profil", "CC1", "--projekt", "Eins", "--von", "TL"]), 0)
        self.assertIn("verbrauch: 10.00 $ Gegenwert (Opus 5.5/high)", aus.getvalue())
        self.assertIn("Median 3.00 $ je Aufgabe (letzte 4 fertigen", aus.getvalue())
        self.assertIn(f"A{lauf} bisher 0.50 $", aus.getvalue())

    def test_texte_de_und_en(self):
        with open(os.path.join(WURZEL, "amw", "workbench.html"), encoding="utf-8") as f:
            html = f.read()
        for schluessel in ("k_aufwand_titel", "k_aufwand_median", "k_aufwand_eingestellt", "k_aufwand_laeuft", "k_aufwand_leer",
                           "k_aufwand_h", "au_verbrauch", "au_verbrauch_x"):
            self.assertEqual(len(re.findall(rf"\b{schluessel}: \"", html)), 2, schluessel)
        self.assertIn("aufwandAbschnitt(d)", html)


if __name__ == "__main__":
    unittest.main()
