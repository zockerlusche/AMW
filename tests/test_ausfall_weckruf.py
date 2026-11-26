"""A2147 (TH157 Ausfälle): Ein Agent (nicht Lead) mit lebender Sitzung und laufendem Paket beantwortet einen Weckruf nicht, sendet
nichts und arbeitet nicht → der Dienst weckt ihn einmal erneut. Bleibt er danach `ausfall_min` still, geht sein Paket mit
Übergabe-Notiz in den Pool, der Lead bekommt eine Meldung, der Mensch eine Frage. Kein Prozess wird beendet, nichts neu gestartet,
nichts im Halt oder in der Pause. Gegenproben: wer antwortet, liest oder arbeitet, behält sein Paket. Feste Uhr: jede Runde bekommt
ihre Zeit (`jetzt`)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import sqlite3
import time
import unittest

from amw import db, dienst, kern, pause, verteilen
from tests import test_dienst as td


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


class Still(unittest.TestCase):
    con: sqlite3.Connection
    pid: int
    d: dienst.Dienst
    gesendet: list
    t0: float
    aid: int
    n: int
    setUp, tearDown, anmelden = td.Wecker.setUp, td.Wecker.tearDown, td.Wecker.anmelden   # ohne die Tests dort erneut

    def uhr(self, minuten):
        return self.t0 + minuten * 60

    def vorbereiten(self, wer="CC1"):
        self.t0 = time.time()
        self.anmelden(wer)
        self.aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Speichern bauen", wer)
        kern.aufgabe_status(self.con, self.pid, wer, self.aid, "start")
        self.n, _ = kern.posten(self.con, self.pid, "TL", wer, "auftrag", "Bitte den Stand melden")
        self.d.zustellen()
        self.assertEqual(len(self.gesendet), 1)

    def aufgabe(self):
        self.con.commit()
        return self.con.execute("SELECT agent, status FROM aufgabe WHERE id = ?", (self.aid,)).fetchone()

    def nachgeweckt(self):
        self.assertEqual(self.d.nachwecken(self.uhr(5)), [])                                      # noch keine 10 min
        self.assertEqual(self.d.nachwecken(self.uhr(11)), [f"CC1: #{self.n}"])
        self.assertTrue(self.gesendet[-1][1].startswith("Nachgeweckt"))

    def test_erst_nachwecken_dann_nach_der_frist_in_den_pool(self):
        self.vorbereiten()
        self.assertEqual(verteilen.still(self.con, self.pid, self.uhr(42)), [])                  # noch nicht nachgeweckt
        self.nachgeweckt()
        self.assertEqual(self.d.nachwecken(self.uhr(12)), [])                                     # einmal je Nachricht
        self.assertEqual(verteilen.still(self.con, self.pid, self.uhr(20)), [])                  # Frist (30 min) läuft noch
        self.assertEqual(verteilen.still(self.con, self.pid, self.uhr(42)), [f"Still CC1: A{self.aid} zurück in den Pool"])
        self.assertEqual(tuple(self.aufgabe()), (None, "wartet"))
        notiz = json.loads(self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'uebergabe' AND aufgabe_id = ?", (self.aid,)).fetchone()[0])
        self.assertEqual(notiz["agent"], "CC1")
        self.assertIn("letzter Commit", notiz["notiz"])
        m = self.con.execute("SELECT kurz, text FROM nachricht WHERE an = 'TL' AND von = 'AMW' AND kurz LIKE 'Still:%'").fetchone()
        self.assertEqual(m["kurz"], f"Still: CC1 – A{self.aid} zurück in den Pool")
        self.assertIn(f"#{self.n}", m["text"])
        self.assertIn("die AMW startet nie selbst", m["text"])
        self.assertTrue(self.con.execute("SELECT 1 FROM frage WHERE aufgabe_id = ? AND kurz LIKE 'CC1 antwortet nicht%'", (self.aid,)).fetchone())
        self.assertEqual(self.con.execute("SELECT zustand FROM sitzung").fetchone()[0], "aktiv")   # kein Prozess beendet
        self.assertEqual(verteilen.still(self.con, self.pid, self.uhr(80)), [])                  # nur einmal

    def test_wer_antwortet_behaelt_sein_paket(self):
        self.vorbereiten()
        self.nachgeweckt()
        n, _ = kern.posten(self.con, self.pid, "CC1", "TL", "info", "Bin dran")
        with db.schreiben(self.con):
            self.con.execute("UPDATE nachricht SET zeit_utc = ? WHERE id = ?", (iso(self.uhr(15)), n))
        self.assertEqual(verteilen.still(self.con, self.pid, self.uhr(42)), [])
        self.assertEqual(tuple(self.aufgabe()), ("CC1", "laeuft"))

    def test_wer_liest_behaelt_sein_paket(self):
        self.vorbereiten()
        self.nachgeweckt()
        with db.schreiben(self.con):
            self.con.execute("UPDATE empfang SET status = 'gelesen', gelesen_utc = ? WHERE agent = 'CC1'", (iso(self.uhr(15)),))   # selbst gelesen
        self.assertEqual(verteilen.still(self.con, self.pid, self.uhr(42)), [])
        self.assertEqual(tuple(self.aufgabe()), ("CC1", "laeuft"))

    def test_wer_arbeitet_behaelt_sein_paket_und_wird_nicht_nachgeweckt(self):
        self.vorbereiten()
        with db.schreiben(self.con):
            self.con.execute("UPDATE sitzung SET ereignis = 'arbeitet', ereignis_utc = ?, letzter_puls_utc = ?", (iso(self.uhr(11)), iso(self.uhr(11))))
        self.assertEqual(self.d.nachwecken(self.uhr(11)), [])
        self.nachgeweckt_trotzdem()
        with db.schreiben(self.con):
            self.con.execute("UPDATE sitzung SET ereignis = 'arbeitet', ereignis_utc = ?, letzter_puls_utc = ?", (iso(self.uhr(42)), iso(self.uhr(42))))
        self.assertEqual(verteilen.still(self.con, self.pid, self.uhr(42)), [])
        self.assertEqual(tuple(self.aufgabe()), ("CC1", "laeuft"))

    def nachgeweckt_trotzdem(self):
        """Als hätte ihn eine frühere Runde nachgeweckt (zwischendurch stand er)."""
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=iso(self.uhr(11)), von="AMW", art="nachgeweckt", text=str(self.n))

    def test_hook_ereignis_nach_dem_weckruf_ist_eine_reaktion(self):
        self.vorbereiten()
        with db.schreiben(self.con):
            self.con.execute("UPDATE sitzung SET ereignis = 'halt', ereignis_utc = ?", (iso(self.uhr(2)),))   # Prompt angenommen, wieder still
        self.assertEqual(self.d.nachwecken(self.uhr(11)), [])
        self.nachgeweckt_trotzdem()
        self.assertEqual(verteilen.still(self.con, self.pid, self.uhr(42)), [])
        self.assertEqual(tuple(self.aufgabe()), ("CC1", "laeuft"))

    def test_nicht_im_halt(self):
        self.vorbereiten()
        self.nachgeweckt()
        kern.halt(self.con, self.pid, "TL", "CC1", "kurz warten")
        self.assertEqual(verteilen.still(self.con, self.pid, self.uhr(42)), [])
        self.assertEqual(tuple(self.aufgabe()), ("CC1", "laeuft"))

    def test_im_halt_nicht_nachwecken(self):
        self.vorbereiten()
        kern.halt(self.con, self.pid, "TL", "CC1", "kurz warten")
        self.assertEqual([z for z in self.d.nachwecken(self.uhr(11)) if z.startswith("CC1")], [])

    def test_nicht_in_der_pause(self):
        self.vorbereiten()
        self.nachgeweckt()
        pause.an(self.con, self.pid, "TL", grund="Nacht")
        self.assertEqual(verteilen.still(self.con, self.pid, self.uhr(42)), [])
        self.assertEqual([z for z in self.d.nachwecken(self.uhr(80)) if z.startswith("CC1")], [])
        self.assertEqual(tuple(self.aufgabe()), ("CC1", "laeuft"))

    def test_frist_ist_die_einstellung_ausfall_min(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", ausfall_min=60)
        self.vorbereiten()
        self.nachgeweckt()
        self.assertEqual(verteilen.still(self.con, self.pid, self.uhr(42)), [])
        self.assertEqual(verteilen.still(self.con, self.pid, self.uhr(72)), [f"Still CC1: A{self.aid} zurück in den Pool"])

    def test_ohne_laufendes_paket_nicht_nachwecken(self):
        self.t0 = time.time()
        self.anmelden("CC2")
        kern.posten(self.con, self.pid, "TL", "CC2", "auftrag", "x")
        self.d.zustellen()
        self.assertEqual(self.d.nachwecken(self.uhr(11)), [])                                    # wie bisher: nur Lead und wer ein Paket hat

    def test_lead_nie_in_den_pool(self):
        self.t0 = time.time()
        self.anmelden("TL")
        self.aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Plan lesen", "TL")
        kern.aufgabe_status(self.con, self.pid, "TL", self.aid, "start")
        n, _ = kern.posten(self.con, self.pid, "CC1", "TL", "frage", "Merge-OK?")
        self.d.zustellen()
        with db.schreiben(self.con):                                                              # beim Lead zählt wie bisher „offen“
            self.con.execute("UPDATE empfang SET status = 'offen' WHERE agent = 'TL'")
        self.assertEqual(self.d.nachwecken(self.uhr(11)), [f"TL: #{n}"])                         # der Lead wird nachgeweckt wie bisher
        self.assertEqual(verteilen.still(self.con, self.pid, self.uhr(80)), [])
        self.assertEqual(tuple(self.aufgabe()), ("TL", "laeuft"))

    def test_runde_ruft_still(self):
        self.vorbereiten()
        self.nachgeweckt()
        self.assertIn(f"Still CC1: A{self.aid} zurück in den Pool", verteilen.runde(self.con, self.uhr(42)))


if __name__ == "__main__":
    unittest.main()
