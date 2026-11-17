"""Messen je Paket (A1844): Wartezeit je Grund (Überlappungen einmal), aktive Zeit, Kosten aus Zähler und erfassten Läufen,
Lücken in Worten; Zuordnung der Zähler-Kosten bevorzugt die nicht wartende Aufgabe."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import datetime
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import aufwand, bruecke, cli, db, kern, messung

T0 = datetime.datetime(2026, 11, 17, 8, 0, tzinfo=datetime.timezone.utc)
z = lambda m: (T0 + datetime.timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ")


class Messung(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")

    def aufgabe(self, titel, angelegt, begonnen, fertig=None, agent="CC1"):
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "aufgabe", projekt_id=self.pid, titel=titel, agent=agent, einstufung="aktiv",
                                status="fertig" if fertig is not None else "laeuft", angelegt_utc=z(angelegt), angelegt_von="TL",
                                begonnen_utc=z(begonnen), fertig_utc=z(fertig) if fertig is not None else None)

    def warten(self, aid, art, bezug, von, bis=None):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "wartegrund", projekt_id=self.pid, aufgabe_id=aid, art=art, bezug=bezug, angelegt_utc=z(von),
                         angelegt_von="CC1", erledigt_utc=z(bis) if bis is not None else None, erledigt_durch="x" if bis is not None else None)

    def test_zeiten_nach_d1258_abschnitt_8(self):
        """Wartezeit = vor dem Start (startklar≈angelegt → begonnen) + Wartegründe beim Bauen (Überlappung einmal)
        + nach der Abgabe (erste Prüfbitte → fertig); aktiv = begonnen → Abgabe ohne Wartegründe."""
        aid = self.aufgabe("Menü", 0, 30, 270)                                      # liegt 30 min, fertig nach 4 h 30
        self.warten(aid, "agent", "TL", 60, 120)                                   # 60 min
        self.warten(aid, "lauf", "L7", 90, 150)                                    # 60 min, 30 davon gleichzeitig
        self.warten(aid, "entwickler", "Entwickler", 300, 400)                     # nach dem Ende: zählt nicht
        with db.schreiben(self.con):
            db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=aid, zweig="z", sha="s" * 40, bauer="CC1",
                         pruefer="TL", angefragt_utc=z(200))                       # abgegeben nach 200 min
        m = messung.zeiten(self.con, self.pid, aid, jetzt=T0 + datetime.timedelta(hours=10))
        self.assertEqual((m["liege_s"], m["abgabe_s"], m["aktiv_s"]), (1800, 70 * 60, (170 - 90) * 60))
        self.assertEqual(m["warten_s"], (30 + 90 + 70) * 60)
        self.assertEqual(m["warten"], {"vor_start": 1800, "agent": 3600, "lauf": 3600, "nach_abgabe": 4200})
        self.assertFalse(m["offen"])

    def test_nie_begonnen_und_abgeschlossen_waechst_nicht(self):
        """L2648: eine Aufgabe, die ohne Beginn abgeschlossen wurde, darf nicht mit der Uhr weiterliegen (sonst lädt der
        Abgleich ihre Ansicht ständig neu hoch)."""
        with db.schreiben(self.con):
            aid = db.einfuegen(self.con, "aufgabe", projekt_id=self.pid, titel="Alt", agent="CC1", einstufung="aktiv", status="fertig",
                               angelegt_utc=z(0), angelegt_von="TL", fertig_utc=z(60))
        a = messung.zeiten(self.con, self.pid, aid, jetzt=T0 + datetime.timedelta(hours=5))
        b = messung.zeiten(self.con, self.pid, aid, jetzt=T0 + datetime.timedelta(hours=9))
        self.assertEqual(a, b)
        self.assertEqual(a["liege_s"], 3600)

    def test_kosten_erfassen_json_und_unbekannt_mit_luecken(self):
        aid = self.aufgabe("Gegenlesen", 0, 1)
        j = {"total_cost_usd": 0.7011, "num_turns": 3, "duration_ms": 241061, "session_id": "s1",
             "usage": {"input_tokens": 6, "cache_read_input_tokens": 70449, "cache_creation_input_tokens": 21772, "output_tokens": 25642,
                       "output_tokens_details": {"thinking_tokens": 15152}},
             "modelUsage": {"claude-opus-5-5": {}}}
        e = messung.erfassen(self.con, self.pid, "CC1", aid, json_text=json.dumps(j))
        self.assertEqual((e["usd"], e["turns"], e["dauer_s"], e["modell"]), (0.7011, 3, 241, "claude-opus-5-5"))
        self.assertEqual((e["eingabe"], e["cache_schreiben"], e["cache_lesen"], e["ausgabe"], e["denken"]),
                         (6, 21772, 70449, 25642, 15152))                           # Rohwerte getrennt (D1258 v2 §8)
        messung.erfassen(self.con, self.pid, "CC1", aid, unbekannt=True, notiz="abgebrochen")
        with self.assertRaises(kern.AmwFehler):
            messung.erfassen(self.con, self.pid, "CC1", aid)                         # ohne Angabe nichts
        m = messung.je_aufgabe(self.con, self.pid, aid)
        self.assertEqual(m["usd"], 0.7)
        self.assertEqual(len(m["erfasst"]), 2)
        self.assertTrue(any("ohne Kostenangabe" in l for l in m["luecken"]))
        self.assertTrue(any("keine Messpunkte" in l for l in m["luecken"]))

    def test_chat_agent_als_luecke_benannt(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE agent SET arbeitsweise = 'chat' WHERE kennung = 'TL'")
        aid = self.aufgabe("Planen", 0, 1, agent="TL")
        self.assertIn("Agent arbeitet als Chat – kein Kosten-Zähler", messung.je_aufgabe(self.con, self.pid, aid)["luecken"])

    def test_zaehler_bevorzugt_die_nicht_wartende_aufgabe(self):
        a = self.aufgabe("A", 0, 0)
        b = self.aufgabe("B", 0, 10)                                               # später begonnen, wartet aber
        self.warten(b, "lauf", "L1", 20, 100)
        aid = self.con.execute("SELECT id FROM agent WHERE kennung = 'CC1'").fetchone()[0]
        with db.schreiben(self.con):
            sid = db.einfuegen(self.con, "sitzung", agent_id=aid, gestartet_utc=z(0))
            for m, usd in ((15, 1.0), (30, 3.0), (110, 4.0)):
                db.einfuegen(self.con, "verbrauch", sitzung_id=sid, agent="CC1", zeit_utc=z(m), kosten_usd=usd)
        self.assertEqual(aufwand.je_aufgabe(self.con, self.pid, a)["usd"], 2.0)    # 15→30: B wartet → A
        self.assertEqual(aufwand.je_aufgabe(self.con, self.pid, b)["usd"], 1.0)    # 30→110: B wartet nicht mehr → B

    def test_befehle_und_dateiaustausch(self):
        aid = self.aufgabe("Menü", 0, 30, 90)
        self.warten(aid, "agent", "TL", 40, 70)
        datei = os.path.join(self.ordner.name, "lauf.json")
        with open(datei, "w", encoding="utf-8") as f:
            json.dump({"total_cost_usd": 1.25, "num_turns": 2}, f)
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_DB": self.pfad}), contextlib.redirect_stdout(aus):
            os.environ.pop("AMW_AGENT", None)
            cli.main(["kosten", "erfassen", "--aufgabe", f"A{aid}", "--json", datei, "--projekt", "Spiel", "--von", "CC1"])
            cli.main(["messung", f"A{aid}", "--projekt", "Spiel", "--von", "CC1"])
            cli.main(["messung", "--projekt", "Spiel", "--von", "CC1"])
        t = aus.getvalue()
        self.assertIn("1.25 $ erfasst", t)
        self.assertIn("aktiv 30 min · wartet 1 h 00 min (vor dem Start 30 min, Agent/Prüfung 30 min) · 1.25 $", t)
        self.assertIn("Summe: 1.25 $", t)
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_DB": self.pfad}), contextlib.redirect_stdout(aus):
            cli.main(["messung", "--vergleich", "--projekt", "Spiel", "--von", "CC1"])
        self.assertIn("letzte 7 Tage", aus.getvalue())
        self.assertIn("7 Tage davor", aus.getvalue())
        self.assertIn("messung", bruecke.ERLAUBT)
        self.assertIn("kosten", bruecke.ERLAUBT)


if __name__ == "__main__":
    unittest.main()
