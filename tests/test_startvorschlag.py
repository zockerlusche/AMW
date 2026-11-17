"""Startvorschläge (A1867, D1258 §6b): die AMW schlägt „X starten?“ unter „Für dich“ vor – Grund: Paket der Art sitzung dran,
Absturz mit Arbeit, Arbeit ohne laufende Sitzung. Bestätigen startet (mit Protokoll), „Nicht jetzt“ ruht 12 h; ohne Bestätigung und
online startet nichts."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import tempfile
import unittest
from unittest import mock

from amw import aktionen, arbeitspaket as ap, db, kern, steuerung, workbench


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        p = mock.patch.dict(os.environ, {"LOCALAPPDATA": self.ordner.name})
        p.start()
        self.addCleanup(p.stop)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Eins", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        steuerung.profil_setzen(self.con, self.pid, kern.ENTWICKLER, "CC1", ordner=self.ordner.name)
        self.cc1 = self.con.execute("SELECT id FROM agent WHERE kennung = 'CC1'").fetchone()[0]

    def vorschlaege(self):
        return [(v["kennung"], v["grund"], v["aufgabe"]) for v in steuerung.startvorschlaege(self.con, self.pid)]

    def sitzung(self, **k):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "sitzung", agent_id=self.cc1, claude_sitzung="s-1", gestartet_utc=db.jetzt(), **k)


class Vorschlaege(Grund):
    def test_ohne_arbeit_kein_vorschlag(self):
        self.assertEqual(self.vorschlaege(), [])

    def test_arbeit_ohne_sitzung(self):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Etwas tun", agent="CC1")
        self.assertEqual(self.vorschlaege(), [("CC1", "arbeit", aid)])

    def test_absturz_und_bewusstes_ende(self):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Etwas tun", agent="CC1")
        self.sitzung(zustand="beendet", beendet_utc=db.jetzt(), ereignis="fehler", ereignis_text="api_error")
        self.assertEqual(self.vorschlaege(), [("CC1", "absturz", aid)])
        with db.schreiben(self.con):
            self.con.execute("UPDATE sitzung SET ereignis = 'beendet', ereignis_text = 'prompt_input_exit'")
        self.assertEqual(self.vorschlaege(), [("CC1", "arbeit", aid)])            # bewusst beendet: kein Absturz

    def test_paket_art_sitzung_geht_vor(self):
        kern.aufgabe_neu(self.con, self.pid, "TL", "Normale Arbeit", agent="CC1")
        sid = kern.aufgabe_neu(self.con, self.pid, "TL", "Neue Sitzung nötig", agent="CC1", rang=1)
        ap.setzen(self.con, self.pid, "TL", sid, art="sitzung")
        self.assertEqual(self.vorschlaege(), [("CC1", "sitzung", sid)])

    def test_laufend_aus_chat_kein_vorschlag(self):
        kern.aufgabe_neu(self.con, self.pid, "TL", "Etwas tun", agent="CC1")
        self.sitzung(zustand="aktiv", claude_pid=os.getpid())                     # läuft (eigene PID lebt)
        self.assertEqual(self.vorschlaege(), [])
        with db.schreiben(self.con):
            self.con.execute("DELETE FROM sitzung")
            self.con.execute("UPDATE agent SET soll = 'aus' WHERE id = ?", (self.cc1,))
        self.assertEqual(self.vorschlaege(), [])                                  # vom Menschen abgeschaltet
        with db.schreiben(self.con):
            self.con.execute("UPDATE agent SET soll = 'an', arbeitsweise = 'chat' WHERE id = ?", (self.cc1,))
        self.assertEqual(self.vorschlaege(), [])                                  # Chat startet der Mensch selbst

    def test_ansicht_startet_nie_von_selbst(self):
        kern.aufgabe_neu(self.con, self.pid, "TL", "Etwas tun", agent="CC1")
        with mock.patch.object(steuerung, "starten", side_effect=AssertionError("ohne Bestätigung kein Start")):
            d = workbench.daten_start(self.con, self.pid)
        self.assertEqual([v["kennung"] for v in d["startvorschlaege"]], ["CC1"])


class Antworten(Grund):
    def tun(self, weg, daten, kanal="seite"):
        return aktionen.ausfuehren(self.con, self.pid, weg, daten, kanal=kanal)

    def test_nicht_jetzt_ruht_mit_protokoll(self):
        kern.aufgabe_neu(self.con, self.pid, "TL", "Etwas tun", agent="CC1")
        self.tun("/api/agent/startvorschlag_nein", {"kennung": "CC1"})
        self.assertEqual(self.vorschlaege(), [])
        self.assertEqual([r[0] for r in self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'startvorschlag_nein'")], ["CC1"])
        with db.schreiben(self.con):                                              # nach der Ruhezeit wieder da
            self.con.execute("UPDATE plan_ereignis SET zeit_utc = '2000-01-01T00:00:00Z' WHERE art = 'startvorschlag_nein'")
        self.assertEqual(len(self.vorschlaege()), 1)

    def test_bestaetigen_startet_mit_protokoll(self):
        with mock.patch.object(steuerung, "starten", return_value="CC1 startet neu (Probe)") as st:
            r = self.tun("/api/agent/start", {"kennung": "CC1", "vorschlag": "läuft nicht, hat aber Arbeit"})
        self.assertEqual((st.call_count, r["text"]), (1, "CC1 startet neu (Probe)"))
        self.assertIn("CC1: läuft nicht", self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'startvorschlag_ja'").fetchone()[0])

    def test_online_weder_starten_noch_ablehnen(self):
        with mock.patch.object(steuerung, "starten", side_effect=AssertionError("nie online")):
            with self.assertRaisesRegex(aktionen.Ungueltig, "nur am PC"):
                self.tun("/api/agent/start", {"kennung": "CC1", "vorschlag": "x"}, kanal="netz")
        with self.assertRaisesRegex(aktionen.Ungueltig, "am PC"):
            self.tun("/api/agent/startvorschlag_nein", {"kennung": "CC1"}, kanal="netz")


if __name__ == "__main__":
    unittest.main()
