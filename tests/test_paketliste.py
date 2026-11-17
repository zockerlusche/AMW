"""Arbeit › Pakete (A1850, M50 S7; D1258 v15 §10): Liste mit Art, Zustand (Zuordnungstabelle), Kosten, Startgrund aus dem Protokoll;
Eingriffe vorziehen / zurückstellen / Pause / Notbremse je mit Protokoll; keine Steuerung online; Plätze = 0 → wie heute."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import abgleich, aktionen, arbeitspaket as ap, db, kern, paketliste, waechter, workbench


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        p = mock.patch.dict(os.environ, {"LOCALAPPDATA": self.ordner.name})      # Pause/Wartung: eigene Datei
        p.start()
        self.addCleanup(p.stop)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Eins", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        self.a = self.paket("Erstes", rang=20)
        self.b = self.paket("Zweites", rang=30)

    def paket(self, titel, rang=50):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel, rang=rang)
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET pruefbefehl = 'python -m unittest tests.abnahme_x', dateibereich = 'amw/x.py' WHERE id = ?", (aid,))
        ap.setzen(self.con, self.pid, "TL", aid, art="p")
        return aid

    def plaetze(self, n):
        with db.schreiben(self.con):
            self.con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?",
                             (json.dumps({"platz_wurzel": os.path.join(self.ordner.name, "plaetze"), "plaetze": n}), self.pid))

    def ereignisse(self, art):
        return [r[0] for r in self.con.execute("SELECT text FROM plan_ereignis WHERE art = ? ORDER BY id", (art,))]


class Liste(Grund):
    def test_plaetze_null_wie_heute(self):
        d = paketliste.daten(self.con, self.pid)
        self.assertTrue(d["aus"])
        self.assertEqual(d["plaetze"], [])
        self.assertEqual([x["id"] for x in d["pakete"]], [self.a, self.b])     # die Liste zeigt sie trotzdem (nur lesen)

    def test_zustand_gruppe_kosten_und_grund_aus_dem_protokoll(self):
        self.plaetze(1)
        ap.zustand_setzen(self.con, self.pid, "TL", self.a, "startklar")
        waechter.protokollieren(self.con, self.pid, self.a, waechter._nein(4, "1 von 1 belegt"))
        for z in ("startklar", "laeuft", "blockiert"):
            ap.zustand_setzen(self.con, self.pid, "AMW", self.b, z)
        ap.zustand_setzen(self.con, self.pid, "AMW", self.b, "wartet_interaktiv", grund="Frage an Marcel")
        with mock.patch.object(waechter, "pruefen", side_effect=AssertionError("eine Ansicht prüft nicht neu")):
            d = paketliste.daten(self.con, self.pid)
        x = {p["id"]: p for p in d["pakete"]}
        self.assertEqual((x[self.a]["zustand"], x[self.a]["gruppe"]), ("startklar", "wartet"))
        self.assertEqual(x[self.a]["grund"]["regel"], 4)
        self.assertIn("alle Arbeitsplätze belegt", x[self.a]["grund"]["text"])
        self.assertEqual((x[self.b]["gruppe"], x[self.b]["dran"]), ("blockiert", "mensch"))
        self.assertEqual(set(d["gruppen"]), set(ap.ZUSTAENDE))                    # Zuordnungstabelle vollständig
        self.assertTrue(set(d["gruppen"].values()) <= {"fertig", "laeuft", "wartet", "blockiert"})

    def test_online_ohne_plaetze_abfrage_und_ohne_mitlesen(self):
        self.plaetze(1)
        a = abgleich.ansichten(self.con, self.pid)
        self.assertIn("/api/pakete", a)
        self.assertEqual(a["/api/pakete"]["plaetze"], [{"nr": 1, "laeuft": None}])
        self.assertFalse(any(k.startswith("/api/paket/mitlesen") for k in a))

    def test_mitlesen_aus_dem_protokoll_des_platzes(self):
        self.plaetze(1)
        from amw import arbeiter, platz
        p = platz.plaetze(self.con, self.pid)[0]
        os.makedirs(arbeiter.ordner(p))
        with open(os.path.join(arbeiter.ordner(p), "lauf.jsonl"), "w", encoding="utf-8") as f:
            for e in ({"type": "system", "subtype": "init", "model": "claude-opus-5-5", "permissionMode": "dontAsk"},
                      {"type": "assistant", "message": {"content": [{"type": "text", "text": "Ich lese zuerst."},
                                                                    {"type": "tool_use", "name": "Read", "input": {"file_path": "amw/x.py"}}]}},
                      {"type": "user", "message": {"content": [{"type": "tool_result", "content": "1\tdef x(): …"}]}},
                      {"type": "result", "subtype": "success", "num_turns": 3, "total_cost_usd": 0.12, "result": "fertig"}):
                f.write(json.dumps(e) + "\n")
            f.write("kaputte Zeile\n")
        z = workbench.daten_mitlesen(self.con, self.pid, {"platz": ["1"]})["zeilen"]
        self.assertEqual([x["art"] for x in z], ["start", "text", "werkzeug", "ergebnis", "ende"])
        self.assertIn("Read amw/x.py", z[2]["text"])
        with self.assertRaises(kern.AmwFehler):
            paketliste.mitlesen(self.con, self.pid, 2)


class Eingriffe(Grund):
    def tun(self, was, daten, kanal="seite"):
        return aktionen.ausfuehren(self.con, self.pid, f"/api/paket/{was}", daten, kanal=kanal)

    def test_vorziehen_mit_protokoll(self):
        self.tun("vorziehen", {"aufgabe": self.b})
        rang = dict(self.con.execute("SELECT id, rang FROM aufgabe WHERE id IN (?, ?)", (self.a, self.b)).fetchall())
        self.assertLess(rang[self.b], rang[self.a])
        self.assertIn(f"A{self.b} vorgezogen", self.ereignisse("paket_vorziehen")[-1])

    def test_zurueckstellen_mit_protokoll(self):
        self.tun("zurueckstellen", {"aufgabe": self.a})
        self.assertEqual(ap.lesen(self.con, self.a)["zustand"], "zurueckgestellt")
        self.assertIn("vom Menschen", ap.verlauf(self.con, self.a)[-1][3])
        with self.assertRaises(aktionen.Ungueltig):                               # zweimal: Übergang nicht erlaubt
            self.tun("zurueckstellen", {"aufgabe": self.a})

    def test_pause_an_und_aus_mit_protokoll(self):
        self.tun("pause", {"an": True})
        self.assertTrue(waechter.zustand()["pause"])
        self.tun("pause", {"an": False})
        self.assertIsNone(waechter.zustand()["pause"])
        self.assertEqual(self.ereignisse("paket_pause"), ["Pause an – keine neuen Starts", "Pause aufgehoben"])

    def test_pause_aus_wirkt_auch_nach_regel_9(self):
        """P271: zwei Pakete enden unklar → Pause (Regel 9); „Pause aus“ in der Workbench → das nächste darf wirklich starten."""
        self.plaetze(1)
        for aid in (self.a, self.b):
            for z in ("startklar", "laeuft", "unklar"):
                ap.zustand_setzen(self.con, self.pid, "AMW", aid, z)
        dritt = self.paket("Drittes", rang=40)
        ap.zustand_setzen(self.con, self.pid, "TL", dritt, "startklar")
        self.assertEqual(waechter.pruefen(self.con, self.pid, dritt, limit=0)["regel"], 9)
        self.tun("pause", {"an": False})
        r = waechter.pruefen(self.con, self.pid, dritt, limit=0)
        self.assertTrue(r["ok"], r)
        self.assertIsNone(waechter.zustand()["pause"])

    def test_notbremse_mit_protokoll(self):
        self.plaetze(1)
        from amw import arbeiter
        with mock.patch.object(arbeiter, "notbremse", return_value=True), mock.patch.dict(
                os.environ, {"AMW_AGENT": "", "CLAUDE_CODE_MESSAGING_SOCKET": "", "CLAUDECODE": ""}):
            r = self.tun("notbremse", {"platz": 1, "aufgabe": self.a})
        self.assertIn("Platz 1", r["text"])
        self.assertIn("Platz 1", self.ereignisse("notbremse")[-1])

    def test_keine_steuerung_online(self):
        for was, daten in (("vorziehen", {"aufgabe": self.a}), ("zurueckstellen", {"aufgabe": self.a}), ("pause", {"an": True}),
                           ("notbremse", {"platz": 1})):
            with self.assertRaisesRegex(aktionen.Ungueltig, "nur am PC"):
                self.tun(was, daten, kanal="netz")
        self.assertIsNone(waechter.zustand()["pause"])
        self.assertEqual(self.ereignisse("paket_vorziehen"), [])


if __name__ == "__main__":
    unittest.main()
