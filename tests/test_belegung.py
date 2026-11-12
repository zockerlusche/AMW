"""Dauer-Belegung: Programme außerhalb der Warteschlange, die lange viel Arbeitsspeicher halten – erkennen, benennen,
Läufe aus der Warteschlange ausnehmen. Die Prozesslisten sind nachgestellt; ein Test liest die echte Liste (nur lesen)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime
import os
import tempfile
import unittest
from unittest import mock

from amw import belegung, betrieb, db, einstellungen, kern

UTC = datetime.timezone.utc
JETZT = datetime.datetime(2026, 11, 11, 18, 0, tzinfo=UTC)


def p(pid, name, gb, minuten, eltern=1):
    return {"pid": pid, "eltern": eltern, "name": name, "gb": gb, "seit": JETZT - datetime.timedelta(minutes=minuten)}


class Erkennen(unittest.TestCase):
    def test_gross_und_lange_da(self):
        liste = [p(10, "llama-server", 16.4, 240), p(11, "vmmem", 6.0, 3000), p(12, "python", 5.0, 3),          # zu jung
                 p(13, "msedge", 1.5, 500), p(14, "msedge", 1.5, 500), p(15, "msedge", 1.5, 500),                # viele kleine: nein
                 p(16, "Memory Compression", 9.0, 9000), p(0, "", 8.0, 9000), p(17, "devenv", 4.2, 90), p(18, "devenv", 4.4, 60)]
        d = belegung.dauer(liste, 4.0, jetzt=JETZT)
        self.assertEqual([(x["name"], x["art"], x["gb"], x["prozesse"]) for x in d],
                         [("llama-server", "ki", 16.4, 1), ("devenv", "programm", 8.6, 2), ("vmmem", "vm", 6.0, 1)])
        self.assertEqual(d[0]["seit_utc"], "2026-11-11T14:00:00Z")
        self.assertEqual(d[1]["seit_utc"], "2026-11-11T16:30:00Z")                               # der ältere der beiden
        self.assertEqual(belegung.dauer(liste, 20.0, jetzt=JETZT), [])
        self.assertEqual([belegung.art(n) for n in ("ollama", "Ollama_llama_server", "VBoxHeadless", "godot")], ["ki", "ki", "vm", "programm"])

    def test_laeufe_aus_der_warteschlange_zaehlen_nicht(self):
        liste = [p(20, "cmd", 0.01, 30), p(21, "python", 6.0, 30, eltern=20), p(22, "msedge", 5.0, 29, eltern=21),   # Lauf samt Kindern
                 p(30, "llama-server", 16.0, 30)]
        self.assertEqual([x["name"] for x in belegung.dauer(liste, 4.0, jetzt=JETZT)], ["llama-server", "python", "msedge"])
        self.assertEqual([x["name"] for x in belegung.dauer(liste, 4.0, jetzt=JETZT, ohne={20})], ["llama-server"])

    def test_gemerkte_laeufe(self):
        with tempfile.TemporaryDirectory() as ordner, mock.patch.dict(os.environ, {"LOCALAPPDATA": ordner}):
            self.assertEqual(belegung.lauf_prozesse(), set())                                    # Ordner fehlt: nichts, kein Fehler
            belegung.lauf_merken(7, 4711)
            belegung.lauf_merken(8, 4712)
            self.assertEqual(belegung.lauf_prozesse(), {4711, 4712})
            self.assertEqual(belegung.lauf_prozesse({8}), {4712})                                # nur was noch läuft
            belegung.lauf_vergessen(7)
            belegung.lauf_vergessen(7)                                                           # doppelt: kein Fehler
            self.assertEqual(belegung.lauf_prozesse(), {4712})

    def test_nennen(self):
        d = [{"name": "llama-server", "gb": 16.4, "seit_utc": "2020-01-02T03:04:00Z"}, {"name": "vmmem", "gb": 6.0, "seit_utc": "kaputt"},
             {"name": "x", "gb": 5.0, "seit_utc": "2020-01-02T03:04:00Z"}]
        text = belegung.nennen(d)
        self.assertRegex(text, r"^llama-server \(16,4 GB, seit 02\.01\. \d\d:04\), vmmem \(6,0 GB, seit \?\) und 1 weitere$")

    @unittest.skipUnless(os.name == "nt", "Prozessliste nur unter Windows")
    def test_echte_prozessliste_nur_lesen(self):
        liste = belegung.prozesse()
        ich = next(x for x in liste if x["pid"] == os.getpid())
        self.assertEqual(ich["eltern"], os.getppid())
        self.assertTrue(ich["name"].lower().startswith("python"), ich["name"])
        self.assertTrue(0.001 < ich["gb"] < 4)
        self.assertLess(abs((datetime.datetime.now(UTC) - ich["seit"]).total_seconds()), 3600)


class ImBetrieb(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        umgebung = mock.patch.dict(os.environ, {"LOCALAPPDATA": self.ordner.name})
        umgebung.start()
        self.addCleanup(umgebung.stop)
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "CC1")
        belegung._gemerkt[:] = [0.0, None, []]
        self.addCleanup(lambda: belegung._gemerkt.__setitem__(slice(None), [0.0, None, []]))

    def test_leitstand_und_einstellung(self):
        liste = [p(30, "llama-server", 16.4, 30), p(31, "vmmem", 4.5, 30)]
        for x in liste:
            x["seit"] = datetime.datetime.now(UTC) - datetime.timedelta(minutes=30)
        with mock.patch.object(belegung, "prozesse", lambda: liste):
            r = betrieb.auslastung(self.con, self.pid)
            self.assertEqual(([x["name"] for x in r["dauer"]], r["dauer_gb"]), (["llama-server", "vmmem"], 20.9))
            einstellungen.speichern({"dauer_ab_gb": 10})
            self.assertEqual([x["name"] for x in betrieb.auslastung(self.con, self.pid)["dauer"]], ["llama-server"])
            einstellungen.speichern({"dauer_ab_gb": 0})                                          # ausgeschaltet
            r = betrieb.auslastung(self.con, self.pid)
            self.assertEqual((r["dauer"], r["dauer_gb"]), ([], None))

    def test_wartegrund_nennt_das_programm(self):
        liste = [p(30, "llama-server", 16.4, 30)]
        liste[0]["seit"] = datetime.datetime.now(UTC) - datetime.timedelta(minutes=30)
        with db.schreiben(self.con):
            aid = kern.agent_zeile(self.con, self.pid, "CC1")["id"]
            db.einfuegen(self.con, "sitzung", agent_id=aid, claude_sitzung="s", gestartet_utc=db.jetzt(), schluessel_datei="x.json", zustand="aktiv")
        lid = betrieb.lauf_start(self.con, self.pid, "CC1", "Gesamtlauf", warten=True)
        l = betrieb.lauf_zeile(self.con, self.pid, lid)
        with mock.patch.object(belegung, "prozesse", lambda: liste), mock.patch.object(betrieb, "speicher_frei_gb", lambda: (4.3, 32.0)):
            grund = betrieb.wartegrund(self.con, self.pid, l)
            self.assertIn("nur 4.3 GB frei", grund)
            self.assertRegex(grund, r"außerhalb der Warteschlange belegt: llama-server \(16,4 GB, seit \d\d:\d\d\) \(beenden kann das nur der Mensch\)")
            self.assertNotIn("llama", betrieb.wartegrund(self.con, self.pid, l, speicher_frei=4.3))   # vorgegebener Wert: ohne Messung des Rechners
        with mock.patch.object(belegung, "prozesse", lambda: liste), mock.patch.object(betrieb, "speicher_frei_gb", lambda: (30.0, 32.0)):
            belegung._gemerkt[:] = [0.0, None, []]
            self.assertNotIn("llama", betrieb.wartegrund(self.con, self.pid, l))                 # genug frei: kein Hinweis


if __name__ == "__main__":
    unittest.main()
