"""Tests für Agenten steuern: Profil, Befehl, Starten/Beenden (ohne echte Prozesse), Absturz-Neustart, Startskript."""
import base64
import os
import tempfile
import time
import unittest
from unittest import mock

from amw import db, kern, steuerung


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        p = mock.patch.dict(os.environ, {"LOCALAPPDATA": self.ordner.name})
        p.start()
        self.addCleanup(p.stop)
        self.gestartet = []

    def tearDown(self):
        self.con.close()
        self.ordner.cleanup()

    def profil(self, **k):
        return steuerung.profil_setzen(self.con, self.pid, "Entwickler", "CC1", ordner=self.ordner.name, **k)

    def zeile(self, args):
        return base64.b64decode(args[-1]).decode("utf-16-le")

    def starten(self, **k):
        return steuerung.starten(self.con, self.pid, "CC1", ausfuehren=lambda a, f, o: self.gestartet.append(a), **k)


class Profil(Grund):
    def test_pruefung_und_nur_lead(self):
        with self.assertRaises(kern.AmwFehler):
            steuerung.profil_setzen(self.con, self.pid, "CC1", "CC1", denkstufe="high")       # Agent selbst: nein
        with self.assertRaises(kern.AmwFehler):
            self.profil(denkstufe="riesig")
        with self.assertRaises(kern.AmwFehler):
            self.profil(zusatzordner="C:/gibt/es/nicht")
        p = self.profil(denkstufe="high", rechte="umgehen", zusatzordner=self.ordner.name, startsatz="Du bist CC1.")
        self.assertEqual((p["denkstufe"], p["rechte"], p["zusatzordner"]), ("high", "umgehen", [self.ordner.name]))

    def test_befehl_neu_mit_session_id_fortsetzen_mit_resume(self):
        p = self.profil(denkstufe="high", rechte="umgehen", startsatz="Du bist CC1. Lies 'amw lesen'.")
        neu = steuerung.befehl(steuerung.profil(self.con, self.pid, "CC1"), None, "1111-2222")
        self.assertIn("$env:AMW_AGENT = 'CC1'", neu)
        self.assertIn("'--session-id' '1111-2222'", neu)
        self.assertIn("'--remote-control' 'CC1'", neu)
        self.assertIn("'--dangerously-skip-permissions'", neu)
        self.assertIn("'Du bist CC1. Lies ''amw lesen''.'", neu)          # PowerShell-Quoting
        fort = steuerung.befehl(p, "abcd-ef", None)
        self.assertIn("'--resume' 'abcd-ef'", fort)
        self.assertNotIn("Du bist CC1", fort)                              # Startsatz nur bei neuer Sitzung


class Starten(Grund):
    def test_starten_neu_dann_fortsetzen_nie_doppelt(self):
        with self.assertRaises(kern.AmwFehler):
            self.starten()                                                 # ohne Ordner im Profil
        self.profil()
        text = self.starten()
        self.assertIn("startet neu", text)
        self.assertIn("--session-id", self.zeile(self.gestartet[0]))
        aid = self.con.execute("SELECT id FROM agent WHERE kennung = 'CC1'").fetchone()[0]
        with db.schreiben(self.con):
            db.einfuegen(self.con, "sitzung", agent_id=aid, claude_sitzung="s-42", gestartet_utc=db.jetzt(),
                         zustand="beendet", beendet_utc=db.jetzt())
        self.assertIn("setzt Sitzung s-42", self.starten())
        self.assertIn("'--resume' 's-42'", self.zeile(self.gestartet[1]))
        with db.schreiben(self.con):
            db.einfuegen(self.con, "sitzung", agent_id=aid, claude_sitzung="s-43", gestartet_utc=db.jetzt(), claude_pid=os.getpid())
        with self.assertRaises(kern.AmwFehler):
            self.starten()                                                 # läuft schon (eigene PID lebt)

    def test_beenden_vermerkt_bewusst(self):
        aid = self.con.execute("SELECT id FROM agent WHERE kennung = 'CC1'").fetchone()[0]
        with db.schreiben(self.con):
            db.einfuegen(self.con, "sitzung", agent_id=aid, claude_sitzung="s-1", gestartet_utc=db.jetzt(),
                         schluessel_datei="x.json", claude_pid=os.getpid())
        getroffen = []
        steuerung.beenden(self.con, self.pid, "CC1", beenden_mit=getroffen.append)
        self.assertEqual(getroffen, [os.getpid()])
        self.assertEqual(self.con.execute("SELECT ereignis, ereignis_text FROM sitzung").fetchone()[:], ("beendet", "amw"))

    def test_prozessabfragen(self):
        self.assertTrue(steuerung.lebt(os.getpid()))
        self.assertFalse(steuerung.lebt(0))
        self.assertIn(os.getpid(), steuerung.prozesse())
        self.assertEqual(steuerung.eltern(os.getpid()), os.getppid())


class Neustart(Grund):
    def setUp(self):
        super().setUp()
        self.profil(neustart_auto=True)
        self.aid = self.con.execute("SELECT id FROM agent WHERE kennung = 'CC1'").fetchone()[0]

    def sitzung(self, **k):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "sitzung", agent_id=self.aid, claude_sitzung="s-9", gestartet_utc=db.jetzt(),
                         zustand="beendet", beendet_utc=db.jetzt(), claude_pid=999999, fenster_pid=os.getpid(), **k)

    def neustarter(self):
        return steuerung.Neustarter(self.con, starter=lambda c, p, k: self.gestartet.append(k) or "ok")

    def test_absturz_fenster_lebt_wird_fortgesetzt_hoechstens_dreimal(self):
        self.sitzung()
        n = self.neustarter()
        for _ in range(5):
            n.runde()
        self.assertEqual(self.gestartet, ["CC1"] * steuerung.NEUSTARTS_JE_STUNDE)
        tl = self.con.execute("SELECT count(*) FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id WHERE e.agent = 'TL'"
                              " AND n.kurz LIKE 'CC1 war abgestürzt%'").fetchone()[0]
        self.assertEqual(tl, 3)

    def test_bewusst_beendet_oder_fenster_zu_nie(self):
        self.sitzung(ereignis="beendet", ereignis_text="prompt_input_exit")
        self.assertEqual(self.neustarter().kandidaten(self.pid), [])
        self.con.execute("UPDATE sitzung SET ereignis = NULL, ereignis_text = NULL, fenster_pid = 999998")   # Fenster zu
        self.assertEqual(self.neustarter().kandidaten(self.pid), [])
        self.con.execute("UPDATE sitzung SET fenster_pid = NULL")                                            # unbekannt
        self.assertEqual(self.neustarter().kandidaten(self.pid), [])

    def test_nur_mit_auto_neustart_und_soll_an(self):
        self.sitzung()
        self.profil(neustart_auto=False)
        self.assertEqual(self.neustarter().kandidaten(self.pid), [])
        self.profil(neustart_auto=True)
        self.con.execute("UPDATE agent SET soll = 'aus' WHERE kennung = 'CC1'")
        self.assertEqual(self.neustarter().kandidaten(self.pid), [])

    def test_alter_absturz_nicht_mehr(self):
        self.sitzung()
        alt = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))
        self.con.execute("UPDATE sitzung SET beendet_utc = ?", (alt,))
        self.assertEqual(self.neustarter().kandidaten(self.pid), [])


class Startskript(Grund):
    def test_alle_mit_profil_und_soll_an(self):
        with self.assertRaises(kern.AmwFehler):
            steuerung.startskript(self.con, self.pid)
        self.profil(denkstufe="medium")
        text = steuerung.startskript(self.con, self.pid)
        self.assertIn("new-tab --title CC1", text)
        self.assertIn("-EncodedCommand", text)
        self.assertNotIn("--title TL", text)                               # TL ohne Profil-Ordner


if __name__ == "__main__":
    unittest.main()
