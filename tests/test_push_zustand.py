"""Tests für Push (Ereignisse, Bündeln, Grenze, Ruhezeit, Wiederholung), Zustands-Hooks, Statusline-Brücke, Einbau."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime
import io
import json
import os
import tempfile
import time
import unittest
from unittest import mock

from amw import db, einrichtung, hook, kern, push, statusline


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        for k, r in (("TL", "lead"), ("CC1", None)):
            kern.agent_neu(self.con, self.pid, k, rolle=r)
        aid = self.con.execute("SELECT id FROM agent WHERE kennung = 'CC1'").fetchone()[0]
        with db.schreiben(self.con):
            self.sid = db.einfuegen(self.con, "sitzung", agent_id=aid, claude_sitzung="s-1", gestartet_utc=db.jetzt())
        p = mock.patch.dict(os.environ, {"LOCALAPPDATA": self.ordner.name, "AMW_DB": os.path.join(self.ordner.name, "t.db")})
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.con.close()
        self.ordner.cleanup()


class Push(Grund):
    def setUp(self):
        super().setUp()
        self.gesendet, self.fehler = [], None
        push.speichern({"ntfy": {"an": True, "topic": "amw-test"}, "link": "https://amw.example/"})
        push.speichern({"an": True})
        self.cfg = push.laden()
        self.cfg["seit_utc"] = "2000-01-01T00:00:00Z"      # alles im Test gilt als neu
        self.cfg["ereignisse"]["rueckblick"] = False        # der tägliche Rückblick käme sonst ab 08:00 dazu (eigener Test)
        s = mock.patch.dict(push.SENDER, {"ntfy": self.senden})
        s.start()
        self.addCleanup(s.stop)

    def senden(self, c, titel, text, prio, link):
        if self.fehler:
            raise self.fehler
        self.gesendet.append((titel, text, prio, link))

    def runde(self, jetzt=None):
        return push.runde(self.con, self.pid, self.cfg, jetzt=jetzt)

    def frage(self, kurz="Wie?"):
        return kern.frage_neu(self.con, self.pid, "TL", "entwickler", kurz, [("A", "ja")], "A", "weil", geprueft="keine Treffer")

    def test_neue_frage_einmal_mit_link_und_ohne_inhalt(self):
        fid = self.frage("Geheimer Inhalt der Frage")
        self.runde()
        self.runde()
        self.assertEqual(len(self.gesendet), 1)
        titel, text, prio, link = self.gesendet[0]
        self.assertEqual((titel, prio, link), (f"AMW: Neue Frage F{fid}", 4, "https://amw.example/#fragen"))
        self.assertNotIn("Geheim", titel + text)

    def test_buendeln_je_art(self):
        for i in range(3):
            self.frage(f"F{i}")
        self.runde()
        self.assertEqual(len(self.gesendet), 1)
        self.assertTrue(self.gesendet[0][0].startswith("AMW: 3 neue Fragen"))

    def test_grenze_je_stunde_sammelt_den_rest(self):
        self.cfg["max_je_stunde"] = 1
        self.frage()
        kern.posten(self.con, self.pid, "TL", "Entwickler", "meldung", "Bericht")
        self.runde()
        self.assertEqual(len(self.gesendet), 1)
        self.assertIn("2 Meldungen", self.gesendet[0][0])
        self.frage("noch eine")
        self.runde()
        self.assertEqual(len(self.gesendet), 1)                     # Stunde voll – wartet

    def test_ruhezeit_nur_dringendes_rest_danach(self):
        self.cfg["ruhe"] = {"an": True, "von": "22:00", "bis": "07:00"}
        nachts, morgens = datetime.datetime(2026, 11, 2, 2, 0), datetime.datetime(2026, 11, 2, 7, 30)
        self.frage()
        kern.halt(self.con, self.pid, "TL", "alle", "Pause")
        self.runde(nachts)
        self.assertEqual([g[2] for g in self.gesendet], [5])         # nur der Halt
        self.runde(morgens)
        self.assertEqual(len(self.gesendet), 2)

    def test_nach_der_ruhezeit_nur_was_noch_gilt(self):
        self.cfg["ruhe"] = {"an": True, "von": "22:00", "bis": "07:00"}
        nachts, morgens = datetime.datetime(2026, 11, 2, 2, 0), datetime.datetime(2026, 11, 2, 7, 30)
        f1, f2, f3 = self.frage("a"), self.frage("b"), self.frage("c")
        self.con.execute("UPDATE frage SET zeit_utc = '2026-01-01T00:00:00Z' WHERE id = ?", (f3,))   # dazu die Erinnerung
        self.runde(nachts)
        self.assertEqual(self.gesendet, [])
        kern.frage_antworten(self.con, self.pid, f1, "option", "A", "seite")       # nachts schon beantwortet
        kern.frage_antworten(self.con, self.pid, f2, "option", "A", "seite")
        self.runde(morgens)
        self.assertEqual(len(self.gesendet), 1)
        self.assertEqual(self.gesendet[0][0], f"AMW: Neue Frage F{f3}")         # nicht „4 neue Fragen“
        weg = self.con.execute("SELECT schluessel, fehler FROM push_versand WHERE ergebnis = 'unterdrueckt' ORDER BY id").fetchall()
        self.assertEqual([w["schluessel"] for w in weg], [f"frage:{f1}", f"frage:{f2}", f"frage:{f3}:erinnerung"])
        self.assertIn("überholt", weg[0]["fehler"])

    def test_vorlaeufiger_fehler_wird_wiederholt_endgueltiger_nicht(self):
        self.fehler = push.Fehler("nicht erreichbar", True)
        self.frage()
        self.runde()
        self.assertEqual(self.con.execute("SELECT ergebnis, versuche FROM push_versand").fetchone()[:], ("fehler", 1))
        self.fehler = None
        self.con.execute("UPDATE push_versand SET geaendert_utc = '2000-01-01T00:00:00Z'")   # Wartezeit vorbei
        self.runde()
        self.assertEqual(self.con.execute("SELECT ergebnis FROM push_versand").fetchone()[0], "gesendet")
        self.fehler = push.Fehler("HTTP 400", False)
        self.frage("zweite")
        self.runde()
        self.runde()
        self.assertEqual(self.con.execute("SELECT ergebnis FROM push_versand ORDER BY id DESC").fetchone()[0], "unterdrueckt")

    def test_aus_oder_ohne_anbieter_nichts(self):
        self.cfg["an"] = False
        self.frage()
        self.assertEqual(self.runde(), [])
        self.assertEqual(self.gesendet, [])

    def test_geheimnisse_nie_in_der_anzeige(self):
        push.speichern({"pushover": {"an": True, "app_token": "geheim-a", "user_key": "geheim-u"}})
        push.speichern({"pushover": {"app_token": ""}})              # leer = gespeicherten Wert behalten
        self.assertEqual(push.laden()["pushover"]["app_token"], "geheim-a")
        text = json.dumps(push.oeffentlich())
        self.assertNotIn("geheim", text)
        self.assertNotIn("amw-test", text)                           # auch der ntfy-Kanal ist geheim

    def test_telegram_token_nie_in_fehlertexten(self):
        with mock.patch.object(push, "_anfrage", side_effect=push.Fehler("HTTP 401 bei /bot123:ABC/sendMessage", False)):
            with self.assertRaises(push.Fehler) as e:
                push.telegram({"bot_token": "123:ABC", "chat_id": "9"}, "t", "x", 3, "")
        self.assertNotIn("123:ABC", str(e.exception))


class Zustand(Grund):
    def ereignis(self, **e):
        hook.ereignis({"session_id": "s-1", **e})
        return self.con.execute("SELECT ereignis, ereignis_text FROM sitzung WHERE id = ?", (self.sid,)).fetchone()[:]

    def test_hook_ereignisse_setzen_den_zustand(self):
        self.assertEqual(self.ereignis(hook_event_name="UserPromptSubmit"), ("arbeitet", None))
        self.assertEqual(self.ereignis(hook_event_name="Notification", notification_type="permission_prompt",
                                       message="Bash erlauben?"), ("wartet_freigabe", "Bash erlauben?"))
        self.assertEqual(self.ereignis(hook_event_name="Notification", notification_type="auth_success"),
                         ("wartet_freigabe", "Bash erlauben?"))      # unwichtige Arten ändern nichts
        self.assertEqual(self.ereignis(hook_event_name="StopFailure", error_type="rate_limit"), ("fehler", "rate_limit"))
        self.assertEqual(self.ereignis(hook_event_name="Stop"), ("frei", None))

    def test_warnung_bei_freigabe_und_fehler(self):
        from amw import ueberwachung
        vor_5 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 300))
        self.con.execute("UPDATE sitzung SET ereignis = 'wartet_freigabe', ereignis_utc = ? WHERE id = ?", (vor_5, self.sid))
        self.assertIn("auf eine Freigabe", ueberwachung.warnungen(self.con, self.pid)[0]["text"])

    def test_statusline_merkt_und_wachter_uebernimmt(self):
        d = {"session_id": "s-1", "model": {"display_name": "Opus"}, "context_window": {"used_percentage": 42},
             "rate_limits": {"five_hour": {"used_percentage": 61.5, "resets_at": 1900000000}}, "cost": {"total_cost_usd": 1.5},
             "transcript_path": "C:/geheim.jsonl"}
        a = statusline.auszug(d)
        self.assertNotIn("transcript", json.dumps(a))
        statusline.merken(a)
        self.assertEqual(statusline.uebernehmen(self.con), 1)
        s = self.con.execute("SELECT kontext_prozent, limit_5h, kosten_usd, modell FROM sitzung WHERE id = ?", (self.sid,)).fetchone()
        self.assertEqual(s[:], (42, 61.5, 1.5, "Opus"))
        self.assertEqual(self.con.execute("SELECT count(*) FROM verbrauch").fetchone()[0], 1)
        self.assertEqual(statusline.uebernehmen(self.con), 0)            # unverändert → nichts

    def test_verbrauch_je_tag_aus_zuwaechsen(self):
        t = time.time()
        for minuten, usd in ((60, 1.0), (40, 2.5), (20, 0.5), (0, 1.0)):      # bei 20: Sitzung neu gezählt
            with db.schreiben(self.con):
                db.einfuegen(self.con, "verbrauch", sitzung_id=self.sid, agent="CC1", kosten_usd=usd,
                             zeit_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t - minuten * 60)))
        v = statusline.verbrauch_tage(self.con, self.pid, 2)
        self.assertAlmostEqual(sum(v["agenten"]["CC1"].values()), 1.5 + 0.5 + 0.5)

    def test_statusline_reicht_bisherige_weiter(self):
        from amw import einstellungen
        einstellungen.speichern({"statusline_weiter": "echo bisher"})
        aus = io.BytesIO()
        with mock.patch("sys.stdin", io.TextIOWrapper(io.BytesIO(b'{"session_id":"s-2"}'))), \
                mock.patch("sys.stdout", io.TextIOWrapper(aus, encoding="utf-8")) as o:
            statusline.main()
            o.flush()
        self.assertIn(b"bisher", aus.getvalue())


class Einbau(Grund):
    def test_zusammenfuehren_ohne_doppel_und_mit_weitergabe(self):
        ordner = os.path.join(self.ordner.name, "projekt")
        os.makedirs(os.path.join(ordner, ".claude"))
        with open(os.path.join(ordner, ".claude", "settings.local.json"), "w", encoding="utf-8") as f:
            json.dump({"hooks": {"SessionStart": [{"matcher": "compact", "hooks": [{"type": "command", "command": "eigen"}]}]},
                       "statusLine": {"type": "command", "command": "meine-zeile.ps1"}}, f)
        erste = einrichtung.agenten_ordner_einrichten(ordner)
        self.assertIn("Statusline-Anbindung", erste)
        self.assertEqual(einrichtung.agenten_ordner_einrichten(ordner), [])       # zweimal = nichts mehr
        with open(os.path.join(ordner, ".claude", "settings.local.json"), encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(len(d["hooks"]["SessionStart"]), 2)                       # eigener Eintrag bleibt
        self.assertTrue(d["hooks"]["Stop"][0]["hooks"][0]["async"])
        self.assertIn("amw-statusline.py", d["statusLine"]["command"])
        from amw import einstellungen
        self.assertEqual(einstellungen.wert("statusline_weiter"), "meine-zeile.ps1")
        self.assertTrue(any(n.startswith("settings.local.json.vor-amw-") for n in os.listdir(os.path.join(ordner, ".claude"))))


if __name__ == "__main__":
    unittest.main()
