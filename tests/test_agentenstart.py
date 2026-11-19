"""Agentenstart sicher (A1881, D1301): Start nur mit AMW-Hook im Ordner; „gestartet, meldet sich nicht an“ nach ~3 min an Lead
und Mensch; Fortsetzen nur im selben Claude-Projektordner; Fehler des Hooks beim Anmelden sichtbar und protokolliert."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime
import io
import json
import os
from unittest import mock

from amw import db, hook, kern, steuerung
from tests.test_steuerung import Grund, amw_hook


def utc(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class Basis(Grund):
    def setUp(self):
        super().setUp()
        self.arbeit = os.path.join(self.ordner.name, "arbeit")
        os.makedirs(self.arbeit)
        steuerung.profil_setzen(self.con, self.pid, "Entwickler", "CC1", ordner=self.arbeit)
        self.aid = self.con.execute("SELECT id FROM agent WHERE kennung = 'CC1'").fetchone()[0]

    def sitzung(self, **k):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "sitzung", agent_id=self.aid, claude_sitzung=k.pop("claude_sitzung", "s-1"),
                         gestartet_utc=k.pop("gestartet_utc", db.jetzt()), zustand=k.pop("zustand", "beendet"),
                         beendet_utc=db.jetzt(), **k)


class OhneHook(Basis):
    def test_ordner_ohne_hook_startet_nicht(self):
        with self.assertRaises(kern.AmwFehler) as e:
            self.starten()
        self.assertIn("fehlt der AMW-Hook", str(e.exception))
        self.assertIn(f"einrichten agenten-ordner {self.arbeit} --projekt P", str(e.exception))
        self.assertEqual(self.gestartet, [])
        self.assertIsNone(self.con.execute("SELECT 1 FROM plan_ereignis WHERE art = 'agent_start'").fetchone())

    def test_hook_im_ordner_oder_beim_benutzer_reicht(self):
        os.makedirs(os.path.join(self.arbeit, ".claude"))
        with open(os.path.join(self.arbeit, ".claude", "settings.json"), "w", encoding="utf-8") as f:   # nur ein anderer Hook
            json.dump({"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "python fremd.py"}]}]}}, f)
        self.assertFalse(steuerung.amw_hook_da(self.arbeit))
        benutzer = os.environ["CLAUDE_CONFIG_DIR"]
        amw_hook(os.path.dirname(benutzer))                                               # legt <…>/.claude an – nicht der Benutzer
        os.makedirs(benutzer, exist_ok=True)
        with open(os.path.join(os.path.dirname(benutzer), ".claude", "settings.local.json"), encoding="utf-8") as f, \
                open(os.path.join(benutzer, "settings.json"), "w", encoding="utf-8") as g:
            json.dump({"hooks": json.load(f)["hooks"]}, g)                                  # AMW-Hook beim Benutzer
        self.assertTrue(steuerung.amw_hook_da(self.arbeit))
        self.assertIn("startet neu", self.starten())
        os.remove(os.path.join(benutzer, "settings.json"))
        amw_hook(self.arbeit)                                                              # im Ordner (settings.local.json)
        self.assertTrue(steuerung.amw_hook_da(self.arbeit))


class MeldetSichNicht(Basis):
    def setUp(self):
        super().setUp()
        amw_hook(self.arbeit)

    def gestartet_vor(self, minuten):
        self.starten()
        t = utc(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minuten))
        with db.schreiben(self.con):
            self.con.execute("UPDATE plan_ereignis SET zeit_utc = ? WHERE art = 'agent_start'", (t,))
        return t

    def meldungen(self):
        return self.con.execute("SELECT e.agent AS an, n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id"
                                " WHERE n.kurz LIKE '%meldet sich nicht an' ORDER BY n.id, e.agent").fetchall()

    def test_nach_drei_minuten_einmal_an_lead_und_mensch(self):
        jetzt = datetime.datetime.now(datetime.timezone.utc)
        self.gestartet_vor(0)
        self.assertEqual(steuerung.anmeldung_pruefen(self.con, jetzt + datetime.timedelta(minutes=2)), [])   # noch in der Frist
        aus = steuerung.anmeldung_pruefen(self.con, jetzt + datetime.timedelta(minutes=4))
        self.assertEqual(aus, ["CC1 gestartet, meldet sich nicht an"])
        m = self.meldungen()
        self.assertEqual(sorted(x["an"] for x in m), sorted(["TL", kern.ENTWICKLER]))
        self.assertIn(f"Ordner {self.arbeit}", m[0]["text"])
        self.assertIn("einrichten agenten-ordner", m[0]["text"])
        self.assertEqual(steuerung.anmeldung_pruefen(self.con, jetzt + datetime.timedelta(minutes=6)), [])   # nur einmal
        self.assertEqual(len(self.meldungen()), 2)

    def test_angemeldet_oder_zu_alt_keine_meldung(self):
        t = self.gestartet_vor(5)
        self.sitzung(gestartet_utc=t, zustand="aktiv")                                     # hat sich angemeldet
        self.assertEqual(steuerung.anmeldung_pruefen(self.con), [])
        with db.schreiben(self.con):
            self.con.execute("UPDATE sitzung SET zustand = 'beendet', gestartet_utc = '2000-01-01T00:00:00Z'")
            self.con.execute("UPDATE plan_ereignis SET art = 'agent_start_alt' WHERE art = 'agent_start'")
        self.gestartet_vor(40)                                                             # lange her (Dienst war weg)
        self.assertEqual(steuerung.anmeldung_pruefen(self.con), [])

    def test_hook_fehler_steht_in_der_meldung(self):
        t = self.gestartet_vor(5)
        with mock.patch.object(db, "jetzt", return_value=t):
            hook.hook_fehler(RuntimeError("LiveSchutz: Entwicklungsbaum"), "SessionStart CC1")
        steuerung.anmeldung_pruefen(self.con)
        self.assertIn("Hook-Fehler seit dem Start: SessionStart CC1 RuntimeError: LiveSchutz: Entwicklungsbaum",
                      self.meldungen()[0]["text"])


class Fortsetzen(Basis):
    def setUp(self):
        super().setUp()
        amw_hook(self.arbeit)

    def test_nur_im_selben_claude_projektordner(self):
        self.sitzung(claude_sitzung="s-alt", arbeitsordner=os.path.join(self.ordner.name, "anderer"))
        text = self.starten()
        self.assertIn("startet neu", text)
        self.assertIn("nicht fortgesetzt: die letzte Sitzung lief in", text)
        self.assertNotIn("--resume", self.zeile(self.gestartet[-1]))
        self.assertIsNone(steuerung.startbefehle(self.con, self.pid, "CC1")["befehle"]["powershell"]["fortsetzen"])
        self.sitzung(claude_sitzung="s-hier", arbeitsordner=self.arbeit.upper() + os.sep)   # gleicher Ordner, andere Schreibweise
        self.assertIn("setzt Sitzung s-hier fort", self.starten())
        self.assertIn("'--resume' 's-hier'", self.zeile(self.gestartet[-1]))
        self.assertIsNotNone(steuerung.startbefehle(self.con, self.pid, "CC1")["befehle"]["powershell"]["fortsetzen"])

    def test_startskript_setzt_nur_im_selben_ordner_fort(self):
        self.sitzung(claude_sitzung="s-alt", arbeitsordner=os.path.join(self.ordner.name, "anderer"))
        self.assertNotIn("s-alt", steuerung.startskript(self.con, self.pid, ["CC1"], abstand_s=0))
        self.sitzung(claude_sitzung="s-hier", arbeitsordner=self.arbeit)
        self.assertIn("--resume s-hier", steuerung.startskript(self.con, self.pid, ["CC1"], abstand_s=0))

    def test_ohne_bekannten_arbeitsordner_wie_bisher(self):
        self.sitzung(claude_sitzung="s-alt")
        self.assertIn("setzt Sitzung s-alt fort", self.starten())

    def test_claude_projektordner(self):
        self.assertEqual(steuerung.claude_projektordner("F:\\amw"), "f--amw")
        self.assertNotEqual(steuerung.claude_projektordner("F:\\amw"), steuerung.claude_projektordner("F:\\amw-dev2"))


class HookFehler(Basis):
    def test_fehler_beim_anmelden_sichtbar_und_protokolliert(self):
        eingabe = io.StringIO(json.dumps({"hook_event_name": "SessionStart", "source": "startup", "session_id": "s-9"}))
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_AGENT": "CC1"}), mock.patch("sys.stdin", eingabe), mock.patch("sys.stdout", aus), \
                mock.patch.object(db, "verbinde", side_effect=PermissionError("Datenbank gesperrt")):
            self.assertEqual(hook.main(), 0)                                                # hält die Sitzung nie auf
        antwort = json.loads(aus.getvalue())
        self.assertIn("AMW-Hook-Fehler (PermissionError: Datenbank gesperrt)", antwort["systemMessage"])
        self.assertIn("nicht angemeldet", antwort["systemMessage"])
        self.assertEqual(hook.hook_fehler_seit("2000-01-01T00:00:00Z", "SessionStart"),
                         ["SessionStart CC1 PermissionError: Datenbank gesperrt"])


if __name__ == "__main__":
    import unittest
    unittest.main()
