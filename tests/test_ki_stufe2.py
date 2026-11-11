"""KI Stufe 2 (doc/plan-lokale-ki.md §3/§4): KI-Fenster für Aufträge mit --nachts (feste Uhrzeit, Testtermine haben Vorrang,
alle anderen überholen) und Vermerke an KI-Ergebnissen (ausgewählt / verworfen / nachbearbeitet, Schema 21) bis in den
Nachweis, die Workbench, das Handy (Briefkasten) und die Brücke."""
import datetime
import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from amw import aktionen, betrieb, bruecke, db, dokumente, einstellungen, ki, kern, termine, workbench
from test_ki import Grund, Nachbau


def fenster_um(jetzt_offen):
    """Ein Fenster, das jetzt offen bzw. sicher zu ist (Minuten nach Mitternacht, Ortszeit)."""
    t = datetime.datetime.now()
    m = t.hour * 60 + t.minute
    return ((m - 60) % 1440, (m + 60) % 1440) if jetzt_offen else ((m + 120) % 1440, (m + 180) % 1440)


class Fenster(unittest.TestCase):
    def test_einstellung_pruefen(self):
        f = einstellungen.FELDER["ki_fenster"][1]
        self.assertEqual(f("22-06"), "22:00-06:00")
        self.assertEqual(f(" 21:30 – 05:45 "), "21:30-05:45")
        self.assertEqual(f(""), "")
        for falsch in ("25-06", "22-22", "abends", "22:70-06"):
            with self.assertRaises(ValueError, msg=falsch):
                f(falsch)
        self.assertEqual(einstellungen.FELDER["ki_fenster"][0], "22:00-06:00")      # Marcel F5253: feste Uhrzeit 22–06

    def test_im_fenster_ueber_mitternacht(self):
        nacht, tag = (22 * 60, 6 * 60), (10 * 60, 15 * 60)
        um = lambda h, m=0: datetime.datetime(2026, 11, 7, h, m)
        self.assertEqual([ki.im_fenster(um(*x), nacht) for x in ((23,), (2,), (5, 59), (6,), (12,), (21, 59), (22,))],
                         [True, True, True, False, False, False, True])
        self.assertEqual([ki.im_fenster(um(h), tag) for h in (9, 10, 14, 15)], [False, True, True, False])
        self.assertTrue(ki.im_fenster(um(12), None))                  # kein Fenster: nur Testtermine halten auf
        self.assertEqual(ki.fenster_text((22 * 60, 6 * 60)), "22:00–06:00 Uhr")


class Nachts(Grund):
    def setUp(self):
        super().setUp()
        self.ollama()
        ki.recht(self.con, self.pid, "Lead", "ollama", "alle")

    def fenster(self, offen):
        return mock.patch.object(ki, "fenster", return_value=fenster_um(offen))

    def test_wartet_aufs_fenster_und_alle_anderen_ueberholen(self):
        with self.fenster(False):
            lid, aid, laeuft = ki.auftrag(self.con, self.pid, "Lead", "ollama", "viele Texte", "qwen3.5:9b", anzahl=3, nachts=True)
            self.assertFalse(laeuft)                                  # Grafikkarte frei – trotzdem nicht jetzt
            self.assertIn("KI-Fenster", betrieb.wartegrund(self.con, self.pid, self.lauf(lid)))
            self.assertEqual(betrieb.warteschlange(self.con, self.pid), [])
            l2, _, laeuft2 = ki.auftrag(self.con, self.pid, "Bauer", "ollama", "eilt", "qwen3.5:9b")
            self.assertTrue(laeuft2)                                  # überholt den wartenden Nacht-Auftrag
            betrieb.lauf_ende(self.con, self.pid, "Bauer", l2, 0)
            g = betrieb.lauf_start(self.con, self.pid2, "Fremd", "Blender", schwer=False, gpu=True)
            self.assertEqual(self.lauf(lid)["status"], "angemeldet")
            betrieb.lauf_ende(self.con, self.pid2, "Fremd", g, 0)
            self.assertEqual(ki.nachts_wartend(self.con), (1, 90))   # 3 × 30 s aus der Modell-Probe
            p = workbench.daten_planung(self.con, self.pid)["ki_fenster"]
            self.assertEqual((p["wartend"], p["sekunden"]), (1, 90))
            self.assertEqual((p["offen"], p["termin"]), (False, None))
        with self.fenster(True):
            self.assertEqual(betrieb.warteschlange(self.con, self.pid), [lid])
            self.runde()
        a = self.con.execute("SELECT * FROM ki_auftrag WHERE id = ?", (aid,)).fetchone()
        self.assertEqual(a["zustand"], "fertig", a["fehler"])
        gen = [d for m, p, d in Nachbau.anfragen if p == "/api/generate"]
        self.assertTrue(gen and all("nachts" not in g["options"] for g in gen))   # die AMW-Angabe geht nie an die KI
        self.assertEqual(json.loads(ki.herkunft_von(self.con, self.pid, json.loads(a["dokumente"])[0])[0]["parameter"]), {})

    def test_im_offenen_fenster_sofort(self):
        with self.fenster(True):
            _, _, laeuft = ki.auftrag(self.con, self.pid, "Lead", "ollama", "x", "qwen3.5:9b", nachts=True)
        self.assertTrue(laeuft)

    def test_testtermin_hat_vorrang(self):
        am = (datetime.datetime.now() + datetime.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")
        tid = termine.neu(self.con, self.pid2, kern.ENTWICKLER, "Testabend", "test", am)   # anderes Projekt: PC-weit
        with self.fenster(True):
            lid, _, laeuft = ki.auftrag(self.con, self.pid, "Lead", "ollama", "x", "qwen3.5:9b", nachts=True)
            self.assertFalse(laeuft)
            self.assertIn("Testtermin „Testabend“", betrieb.wartegrund(self.con, self.pid, self.lauf(lid)))
            _, _, ohne = ki.auftrag(self.con, self.pid, "Bauer", "ollama", "y", "qwen3.5:9b", anzahl=1)
            self.assertTrue(ohne)                                     # ohne --nachts: der Termin hält nichts auf
            self.assertIsNone(ki.testtermin_vorrang(self.con, datetime.datetime.now(datetime.timezone.utc)
                                                    + datetime.timedelta(hours=5)))   # nach dem Termin
            vorher = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=3)
            self.assertIsNone(ki.testtermin_vorrang(self.con, vorher))   # vor der Vorlaufzeit (4 h)
            termine.absagen(self.con, self.pid2, kern.ENTWICKLER, tid)
            self.assertIsNone(ki.testtermin_vorrang(self.con))
            jetzt = (datetime.datetime.now() - datetime.timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M")
            t0 = termine.neu(self.con, self.pid, kern.ENTWICKLER, "Spontantest", "test", jetzt, vorlauf_h=0)   # ohne Vorlauf (CC2 b)
            self.assertIn("Spontantest", ki.testtermin_vorrang(self.con) or "")
            termine.absagen(self.con, self.pid, kern.ENTWICKLER, t0)

    def test_parameter_nachts_nicht_von_hand(self):
        with self.assertRaises(kern.AmwFehler):
            ki.auftrag(self.con, self.pid, "Lead", "ollama", "x", "qwen3.5:9b", parameter='{"nachts": 1}')


class Vermerk(Grund):
    def setUp(self):
        super().setUp()
        self.ollama()
        _, aid, _ = ki.auftrag(self.con, self.pid, "Lead", "ollama", "Text", "qwen3.5:9b", anzahl=2)
        self.runde()
        self.d1, self.d2 = json.loads(self.con.execute("SELECT dokumente FROM ki_auftrag WHERE id = ?", (aid,)).fetchone()[0])

    def test_regeln(self):
        p = os.path.join(self.ordner.name, "hand.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("von Hand\n")
        ohne = dokumente.ablegen(self.con, self.pid, "Bauer", p, "Notiz", "ergebnis")
        with self.assertRaises(kern.AmwFehler) as e:
            ki.vermerken(self.con, self.pid, "Lead", f"D{ohne}", "ausgewaehlt")
        self.assertIn("keine KI-Herkunft", str(e.exception))
        with self.assertRaises(kern.AmwFehler):                       # nachbearbeitet nur mit Text
            ki.vermerken(self.con, self.pid, "Grafik", self.d1, "nachbearbeitet")
        with self.assertRaises(kern.AmwFehler):                       # kein Agent dieses Projekts
            ki.vermerken(self.con, self.pid, "Fremd", self.d1, "ausgewaehlt")
        with self.assertRaises(kern.AmwFehler):
            ki.vermerken(self.con, self.pid, "Lead", self.d1, "gefaellt")
        with self.assertRaises(kern.AmwFehler):                       # Schlüssel nie in die Datenbank
            ki.vermerken(self.con, self.pid, "Lead", self.d1, "verworfen", "token ghp_" + "a" * 36)
        with self.assertRaises(kern.AmwFehler):                       # fremdes Projekt sieht das Dokument nicht
            ki.vermerken(self.con, self.pid2, "Fremd", self.d1, "ausgewaehlt")

    def test_juengster_entscheid_gilt_und_alles_bleibt(self):
        ki.vermerken(self.con, self.pid, "Grafik", self.d1, "verworfen", "zu dunkel")
        ki.vermerken(self.con, self.pid, kern.ENTWICKLER, f"D{self.d1}", "ausgewaehlt", kanal="workbench")
        ki.vermerken(self.con, self.pid, "Grafik", self.d1, "nachbearbeitet", "Kanten nachgezogen, Hintergrund entfernt")
        vs = ki.vermerke_von(self.con, self.pid, self.d1)
        self.assertEqual([v["art"] for v in vs], ["verworfen", "ausgewaehlt", "nachbearbeitet"])
        wahl, nach = ki.vermerk_stand(vs)
        self.assertEqual((wahl["art"], wahl["von"], len(nach)), ("ausgewaehlt", kern.ENTWICKLER, 1))
        for sql in ("UPDATE ki_vermerk SET art = 'verworfen'", "DELETE FROM ki_vermerk"):
            with self.assertRaises(sqlite3.DatabaseError, msg=sql):
                with db.schreiben(self.con):
                    self.con.execute(sql)
        # Nachweis: Entscheid, Nachbearbeitung, Zählung
        z = {x["dokument"]: x for x in ki.nachweis(self.con, self.pid)}
        self.assertEqual((z[self.d1]["entscheid"], z[self.d2]["entscheid"]), ("ausgewaehlt", None))
        text = ki.nachweis_text(list(z.values()))
        self.assertIn("Ausgewählt: 1 · verworfen: 0 · ohne Entscheid: 1 · von Hand nachbearbeitet: 1", text)
        self.assertIn("Kanten nachgezogen", text)
        self.assertIn("| Entscheid | Nachbearbeitet | Beleg |", text)
        # Workbench: Dokument und Liste
        d = workbench.daten_dokument(self.con, self.pid, {"id": [str(self.d1)]})
        self.assertEqual(len(d["ki_vermerke"]), 3)
        liste = {x["id"]: x for x in workbench.daten_dokumente(self.con, self.pid, {})["dokumente"]}
        self.assertEqual((liste[self.d1]["ki"], liste[self.d2]["ki"]), ("ausgewaehlt", "offen"))

    def test_handy_und_workbench(self):
        r = aktionen.ausfuehren(self.con, self.pid, "/api/dokument/vermerk", {"id": self.d2, "art": "verworfen"}, kanal="netz")
        aktionen.ausfuehren(self.con, self.pid, "/api/dokument/vermerk", {"id": self.d1, "art": "ausgewaehlt"})
        self.assertTrue(r["vermerk"])
        self.assertEqual([tuple(x) for x in self.con.execute("SELECT dokument_id, von, kanal FROM ki_vermerk ORDER BY id")],
                         [(self.d2, kern.ENTWICKLER, "netz"), (self.d1, kern.ENTWICKLER, "workbench")])
        with self.assertRaises(aktionen.Ungueltig):
            aktionen.ausfuehren(self.con, self.pid, "/api/dokument/vermerk", {"id": self.d1, "art": "nachbearbeitet"}, kanal="netz")

    def test_bruecke_setzt_den_kanal(self):
        with tempfile.TemporaryDirectory() as eingang:
            args = bruecke.argumente({"befehl": "ki", "aktion": "vermerk", "kennung": f"D{self.d1}", "art": "ausgewählt"}, eingang,
                                     von="Lead", projekt="P")
            self.assertEqual(args[-2:], ["--von", "Lead"])
            rc, aus, fehler = bruecke.ausfuehren(args)
            self.assertEqual((rc, fehler), (0, ""))                    # Umlaut: kein FEHLER nach dem Schreiben (CC2 #18851)
            self.assertIn(f"D{self.d1} ausgewählt", aus)
            args = bruecke.argumente({"befehl": "ki", "aktion": "modell", "kennung": "comfyui", "wert": "x",   # Modell-URL bleibt
                                      "quelle": "https://huggingface.co/x"}, eingang)
            self.assertIn("https://huggingface.co/x", args)
        # über die Kommandozeile bis in die Datenbank
        from amw import cli
        with mock.patch("sys.stdout"):
            cli.main(["ki", "vermerk", f"D{self.d2}", "--art", "Verworfen", "--von", "Grafik", "--projekt", "P"])
            with self.assertRaises(SystemExit):                          # den Kanal kann niemand selbst angeben
                with mock.patch("sys.stderr"):
                    cli.main(["ki", "vermerk", f"D{self.d2}", "--art", "ausgewaehlt", "--kanal", "bruecke", "--von", "Lead", "--projekt", "P"])
        self.assertEqual([tuple(x) for x in self.con.execute("SELECT von, art, kanal FROM ki_vermerk ORDER BY id")],
                         [("Lead", "ausgewaehlt", "bruecke"), ("Grafik", "verworfen", "cli")])


class Migration(unittest.TestCase):
    def test_20_nach_21(self):
        with tempfile.TemporaryDirectory() as ordner:
            pfad = os.path.join(ordner, "alt.db")
            con = db.anlegen(pfad)
            con.execute("ALTER TABLE regel DROP COLUMN vorlage")      # Herkunft aus dem Grund-Regelwerk kam mit Schema 23
            for sp in ("fachgebiet", "arbeitsweise", "zustaendig", "fasst_nicht_an"):   # Agenten-Einstellungen kamen mit Schema 22
                con.execute(f"ALTER TABLE agent DROP COLUMN {sp}")
            con.execute("DROP TABLE ki_vermerk")
            con.execute("PRAGMA user_version = 20")
            con.close()
            con = db.verbinde(pfad)
            try:
                self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
                namen = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE name LIKE 'ki_vermerk%'")}
                self.assertEqual(namen, {"ki_vermerk", "ki_vermerk_dokument", "ki_vermerk_nie_loeschen", "ki_vermerk_unveraenderlich"})
            finally:
                con.close()


if __name__ == "__main__":
    unittest.main()
