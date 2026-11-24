"""A2042 (D1531 §1/§7, V1): eine Pause für alles – ein Schalter setzt Halt (alle), Wächter-Pause und hält damit auch die
Lauf-Schlange an, mit Ende (--bis); danach hebt die AMW sie selbst auf. Rückmeldung je Agent: wird pausiert · beendet Schritt ·
pausiert; Headless-Pakete und Läufe „läuft zu Ende“."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import datetime
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import aktionen, db, kern, pause, waechter, workbench

MENSCH = {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db"), "LOCALAPPDATA": os.path.join(self.ordner.name, "lad")})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid, "CC2")

    def sitzung(self, kennung, ereignis, puls_vor_s=5):
        g = self.con.execute("SELECT id FROM agent WHERE kennung = ? AND projekt_id = ?", (kennung, self.pid)).fetchone()[0]
        puls = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=puls_vor_s)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with db.schreiben(self.con):
            db.einfuegen(self.con, "sitzung", agent_id=g, gestartet_utc=db.jetzt(), letzter_puls_utc=puls, ereignis=ereignis,
                         ereignis_utc=db.jetzt())

    def cli(self, *args):
        from amw import cli
        aus = io.StringIO()
        with mock.patch.dict(os.environ, MENSCH), contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "P", *args])
        return rc, aus.getvalue()


class Schalter(Grund):
    def test_an_setzt_halt_und_waechter_pause(self):
        r = pause.an(self.con, self.pid, kern.ENTWICKLER, grund="Mittag")
        self.assertTrue(r["an"])
        self.assertTrue(kern.halt_gilt(self.con, self.pid, "CC1"))                          # Halt für alle – hält auch Läufe an
        self.assertTrue(waechter.zustand()["pause"])                                       # keine neuen Headless-Pakete
        with self.assertRaisesRegex(kern.AmwFehler, "schon an"):
            pause.an(self.con, self.pid, kern.ENTWICKLER)
        pause.aus(self.con, self.pid, "TL")
        self.assertFalse(kern.halt_gilt(self.con, self.pid, "CC1"))
        self.assertIsNone(waechter.zustand()["pause"])
        self.assertFalse(pause.zustand(self.con, self.pid)["an"])

    def test_nur_lead_oder_mensch(self):
        with self.assertRaisesRegex(kern.AmwFehler, "Lead oder der Mensch"):
            pause.an(self.con, self.pid, "CC1")

    def test_mit_ende_hebt_die_amw_selbst_auf(self):
        frueher = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        pause.an(self.con, self.pid, "TL", bis=pause.bis_aus("2h"), grund="Umzug")
        self.assertTrue(kern.halt_gilt(self.con, self.pid, "CC1"))
        self.assertEqual(pause.runde(self.con), [])                                         # noch nicht vorbei
        with db.schreiben(self.con):                                                         # die Zeit vergeht
            self.con.execute("UPDATE plan_ereignis SET text = json_set(text, '$.bis', ?) WHERE art = 'pause_an'", (frueher,))
            self.con.execute("UPDATE sperre SET bis_utc = ? WHERE art = 'halt'", (frueher,))
        waechter.pause_an("Pause für alles: Umzug", bis=frueher)
        self.assertFalse(kern.halt_gilt(self.con, self.pid, "CC1"))                         # das Ende gilt sofort
        self.assertIsNone(waechter.zustand()["pause"])
        self.assertEqual(pause.runde(self.con), [(self.pid, "Pause vorbei")])
        self.assertFalse(pause.zustand(self.con, self.pid)["an"])
        weiter = self.con.execute("SELECT count(*) FROM nachricht WHERE kurz = 'WEITER: Pause vorbei'").fetchone()[0]
        self.assertEqual(weiter, 1)

    def test_ende_lesen(self):
        jetzt = datetime.datetime(2026, 11, 24, 6, 0, tzinfo=datetime.timezone.utc)
        self.assertEqual(pause.bis_aus("2h", jetzt), "2026-11-24T08:00:00Z")
        self.assertEqual(pause.bis_aus("90min", jetzt), "2026-11-24T07:30:00Z")
        self.assertIsNone(pause.bis_aus(""))
        with self.assertRaisesRegex(kern.AmwFehler, "HH:MM"):
            pause.bis_aus("bald")


class Rueckmeldung(Grund):
    def test_je_agent_paket_und_lauf(self):
        self.sitzung("CC1", "arbeitet")                                                    # mitten im Schritt
        self.sitzung("CC2", "frei")                                                        # steht
        pause.an(self.con, self.pid, "TL", grund="Test")
        z = {a["kennung"]: a["zustand"] for a in pause.zustand(self.con, self.pid)["agenten"]}
        self.assertEqual((z["CC1"], z["CC2"], z["TL"]), ("wird pausiert", "wird pausiert", "pausiert"))   # stopp noch nicht zugestellt
        with db.schreiben(self.con):
            self.con.execute("UPDATE empfang SET geweckt_utc = ? WHERE agent IN ('CC1', 'CC2')", (db.jetzt(),))
        z = {a["kennung"]: a["zustand"] for a in pause.zustand(self.con, self.pid)["agenten"]}
        self.assertEqual((z["CC1"], z["CC2"]), ("beendet Schritt", "pausiert"))
        self.assertEqual(workbench.daten_pause(self.con, self.pid)["agenten"], pause.zustand(self.con, self.pid)["agenten"])

    def test_workbench_und_befehl(self):
        r = aktionen.ausfuehren(self.con, self.pid, "/api/pause", {"an": True, "bis": "90min", "grund": "Arzt"}, kanal="seite")
        self.assertTrue(r["an"])
        with self.assertRaises(aktionen.Ungueltig):
            aktionen.ausfuehren(self.con, self.pid, "/api/pause", {"an": False}, kanal="datei")
        rc, aus = self.cli("pause", "zeige", "--von", "TL")
        self.assertEqual(rc, 0, aus)
        self.assertIn("– Arzt", aus)
        self.assertIn("CC1", aus)
        rc, aus = self.cli("pause", "aus", "--von", "Entwickler")
        self.assertEqual(rc, 0, aus)
        self.assertFalse(pause.zustand(self.con, self.pid)["an"])
        rc, aus = self.cli("pause", "an", "--bis", "2h", "--grund", "Feierabend", "--von", "TL")
        self.assertEqual(rc, 0, aus)
        self.assertIn("Pause an", aus)


if __name__ == "__main__":
    unittest.main()
