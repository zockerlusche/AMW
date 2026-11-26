"""A2160 (TH157 Ausfälle): Ein Agent (nicht Lead) mit lebender Sitzung und laufendem Paket, der seit `ruhe_min` (Vorgabe 90) weder einen
Commit zur Aufgabe noch einen Lauf, eine Nachricht oder ein Hook-Ereignis hat und nicht gerade arbeitet, bekommt eine Frage der AMW
(„Kommst du voran mit A…?“); der Lead bekommt eine Meldung. Einmal je Paket und Ruhephase, nie im Halt oder in der Pause. Danach greift
A2147 (die Frage weckt). Feste Uhr: jede Runde bekommt ihre Zeit (`jetzt`)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import sqlite3
import time
import unittest
from unittest import mock

from amw import db, dienst, kern, pause, verteilen
from tests import test_dienst as td


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


class Ruhig(unittest.TestCase):
    con: sqlite3.Connection
    pid: int
    d: dienst.Dienst
    gesendet: list
    t0: float
    aid: int
    setUp, tearDown, anmelden = td.Wecker.setUp, td.Wecker.tearDown, td.Wecker.anmelden   # ohne die Tests dort erneut

    def uhr(self, minuten):
        return self.t0 + minuten * 60

    def vorbereiten(self, wer="CC1"):
        self.t0 = time.time()
        self.anmelden(wer)
        self.aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Speichern bauen", wer)
        kern.aufgabe_status(self.con, self.pid, wer, self.aid, "start")

    def an(self, wer, kurz):
        return [r[0] for r in self.con.execute("SELECT n.art FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ?"
                                               " AND n.von = 'AMW' AND n.kurz LIKE ?", (wer, kurz + "%"))]

    def test_nach_der_frist_frage_an_den_agenten_und_meldung_an_den_lead(self):
        self.vorbereiten()
        self.assertEqual(verteilen.ruhig(self.con, self.pid, self.uhr(80)), [])                  # Frist (90 min) läuft noch
        r = verteilen.ruhig(self.con, self.pid, self.uhr(95))
        self.assertEqual(len(r), 1)
        self.assertTrue(r[0].startswith(f"Ruhig CC1: A{self.aid} seit "))
        self.assertIn("(Beginn)", r[0])
        self.assertEqual(self.an("CC1", f"Kommst du voran mit A{self.aid}?"), ["frage"])
        self.assertEqual(self.an("TL", "Ruhig: CC1"), ["meldung"])
        text = self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE 'Kommst du voran%'").fetchone()[0]
        self.assertIn(f"amw aufgabe wartet {self.aid} --auf", text)
        self.assertEqual(verteilen.ruhig(self.con, self.pid, self.uhr(200)), [])                 # einmal je Ruhephase
        self.assertEqual(self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (self.aid,)).fetchone()[0], "laeuft")   # nichts geändert

    def test_die_frage_weckt_den_agenten(self):
        self.vorbereiten()
        verteilen.ruhig(self.con, self.pid, self.uhr(95))
        self.d.zustellen()
        self.assertTrue(any("Kommst du voran" in t for _, t in self.gesendet))                     # A2147 übernimmt ab hier

    def test_neue_aktivitaet_beginnt_eine_neue_ruhephase(self):
        self.vorbereiten()
        self.assertEqual(len(verteilen.ruhig(self.con, self.pid, self.uhr(95))), 1)
        with db.schreiben(self.con):                                                               # er antwortet bei Minute 100
            db.einfuegen(self.con, "nachricht", projekt_id=self.pid, zeit_utc=iso(self.uhr(100)), von="CC1", art="info", kurz="bin dran")
        self.assertEqual(verteilen.ruhig(self.con, self.pid, self.uhr(150)), [])
        r = verteilen.ruhig(self.con, self.pid, self.uhr(195))
        self.assertEqual(len(r), 1)
        self.assertIn("(Nachricht)", r[0])

    def test_commit_zaehlt_als_aktivitaet(self):
        self.vorbereiten()
        with mock.patch.object(verteilen, "_commit_zeit", return_value=iso(self.uhr(60))):
            self.assertEqual(verteilen.ruhig(self.con, self.pid, self.uhr(95)), [])
            self.assertIn("(Commit)", verteilen.ruhig(self.con, self.pid, self.uhr(155))[0])

    def test_lauf_und_sitzung_zaehlen_als_aktivitaet(self):
        self.vorbereiten("CC2")
        with db.schreiben(self.con):
            db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="CC2", beschreibung="Tests", status="fertig",
                         angemeldet_utc=iso(self.uhr(50)), start_utc=iso(self.uhr(50)), ende_utc=iso(self.uhr(70)))
        self.assertEqual(verteilen.ruhig(self.con, self.pid, self.uhr(150)), [])
        with db.schreiben(self.con):
            self.con.execute("UPDATE sitzung SET ereignis = 'halt', ereignis_utc = ? WHERE agent_id = (SELECT id FROM agent WHERE kennung = 'CC2')",
                             (iso(self.uhr(100)),))
        self.assertEqual(verteilen.ruhig(self.con, self.pid, self.uhr(170)), [])
        self.assertIn("(Sitzung)", verteilen.ruhig(self.con, self.pid, self.uhr(191))[0])

    def test_wer_gerade_arbeitet_wird_nicht_gefragt(self):
        self.vorbereiten()
        with mock.patch.object(dienst, "arbeitet_gerade", return_value=True):
            self.assertEqual(verteilen.ruhig(self.con, self.pid, self.uhr(95)), [])

    def test_nie_in_der_pause_und_nie_im_halt(self):
        self.vorbereiten()
        pause.an(self.con, self.pid, "TL", grund="Probe")
        self.assertEqual(verteilen.ruhig(self.con, self.pid, self.uhr(95)), [])
        with mock.patch.object(kern, "halt_gilt", return_value=False):                           # die Pause allein (ohne ihren Halt) reicht
            self.assertEqual(verteilen.ruhig(self.con, self.pid, self.uhr(95)), [])
        pause.aus(self.con, self.pid, "TL")
        kern.halt(self.con, self.pid, "TL", "CC1", "Probe")
        self.assertEqual(verteilen.ruhig(self.con, self.pid, self.uhr(95)), [])
        kern.weiter(self.con, self.pid, "TL", "CC1")
        self.assertEqual(len(verteilen.ruhig(self.con, self.pid, self.uhr(95))), 1)

    def test_lead_und_ohne_sitzung_nicht(self):
        self.vorbereiten("TL")
        self.assertEqual(verteilen.ruhig(self.con, self.pid, self.uhr(95)), [])                  # der Lead nicht
        self.t0 = time.time()
        kern.agent_neu(self.con, self.pid, "CC3")
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Ohne Sitzung", "CC3")
        kern.aufgabe_status(self.con, self.pid, "CC3", aid, "start")
        self.assertEqual(verteilen.ruhig(self.con, self.pid, self.uhr(95)), [])                  # keine lebende Sitzung: das ist der Ausfall

    def test_eigene_frist(self):
        self.vorbereiten()
        kern.projekt_einstellen(self.con, self.pid, "TL", ruhe_min=30)
        self.assertEqual(len(verteilen.ruhig(self.con, self.pid, self.uhr(35))), 1)
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "TL", ruhe_min=5)

    def test_runde_fragt_mit(self):
        self.vorbereiten()
        self.assertTrue(any(x.startswith("Ruhig CC1") for x in verteilen.runde(self.con, self.uhr(95))))


if __name__ == "__main__":
    unittest.main()
