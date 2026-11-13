"""Lokale KIs nur bei Bedarf (A1649, Marcel F5314 = A): die AMW startet eine KI erst für einen Auftrag und beendet sie nach
ki_leerlauf_min ohne Auftrag – nur einen Prozess, den sie selbst gestartet hat (PID + Startzeit). KIs in ki_immer_an hält sie
wie früher am Laufen."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import subprocess
import sys
import unittest
from unittest import mock

from amw import db, einstellungen, ki, workbench
from tests.test_ki import Grund


class Einstellung(unittest.TestCase):
    def test_felder(self):
        self.assertEqual(einstellungen.FELDER["ki_leerlauf_min"][0], 30)
        self.assertEqual(einstellungen.FELDER["ki_immer_an"][0], [])                    # Vorgabe: alle nur bei Bedarf
        pruefe = einstellungen.FELDER["ki_immer_an"][1]
        self.assertEqual(pruefe(" Ollama, comfyui ,ollama"), ["comfyui", "ollama"])
        self.assertEqual(pruefe(["ComfyUI"]), ["comfyui"])
        self.assertEqual(pruefe(""), [])
        with self.assertRaises(ValueError):
            pruefe("nicht erlaubt!")
        with self.assertRaises(ValueError):
            einstellungen.FELDER["ki_leerlauf_min"][1](1)


class Bedarf(Grund):
    def setUp(self):
        super().setUp()
        ki.ki_setzen(self.con, "Bauer", "comfy", "bild", "comfyui", "http://127.0.0.1:9", startbefehl="start.bat")
        self.kid = ki.ki_zeile(self.con, "comfy")["id"]
        self.beendet = []

    def merken(self, name="comfy", pid=4711, beginn=99, seit=1000.0):
        d = ki.gestartet_laden()
        d[name] = {"pid": pid, "beginn": beginn, "seit": seit}
        ki.gestartet_schreiben(d)

    def runde(self, jetzt, beginn=lambda pid: 99, immer=frozenset()):
        return ki.leerlauf_beenden(self.con, jetzt=jetzt, beginn=beginn, beenden_mit=self.beendet.append, immer=immer, minuten=30)

    def test_startet_nicht_mehr_von_selbst(self):
        self.con.execute("UPDATE ki SET zustand = 'aus'")
        with mock.patch.object(ki, "_starten") as start:
            self.assertEqual(ki.hochholen(self.con, {}, jetzt=1000, immer=set()), [])
            start.assert_not_called()
            self.assertEqual(ki.hochholen(self.con, {}, jetzt=1000, immer={"comfy"}), ["comfy antwortet nicht – gestartet"])

    def test_starten_merkt_pid_und_startzeit(self):
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(p.wait)
        self.addCleanup(p.kill)
        with mock.patch.object(ki.ueberwachung, "starten", return_value=p):
            ki._starten(ki.ki_zeile(self.con, "comfy"), jetzt=5000)
        g = ki.gestartet_laden()["comfy"]
        self.assertEqual((g["pid"], g["seit"]), (p.pid, 5000))
        self.assertEqual(g["beginn"], ki._prozess_beginn(p.pid))
        self.assertIsNotNone(g["beginn"])
        self.assertTrue(os.path.exists(os.path.join(os.path.dirname(db.db_pfad()), "ki-gestartet.json")))
        p.kill()
        p.wait()
        self.assertIsNone(ki._prozess_beginn(p.pid))                                     # beendet: keine Startzeit mehr

    def test_nach_leerlauf_beendet(self):
        self.merken(seit=1000.0)
        self.assertEqual(self.runde(1000 + 29 * 60), [])                                 # noch keine 30 min
        self.assertEqual(self.beendet, [])
        aus = self.runde(1000 + 30 * 60)
        self.assertEqual(self.beendet, [4711])
        self.assertIn("comfy: 30 min ohne Auftrag – beendet", aus[0])
        self.assertNotIn("comfy", ki.gestartet_laden())
        self.assertEqual(ki.ki_zeile(self.con, "comfy")["zustand"], "aus")

    def test_letzter_auftrag_zaehlt(self):
        self.merken(seit=1000.0)
        lid = db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="Bauer", beschreibung="x", status="fertig", angemeldet_utc=db.jetzt())
        with db.schreiben(self.con):
            db.einfuegen(self.con, "ki_auftrag", projekt_id=self.pid, ki_id=self.kid, lauf_id=lid, auftraggeber="Bauer", prompt="p", seed=1,
                         zustand="fertig", angelegt_utc="2026-01-01T00:00:00Z", ende_utc="2026-01-01T00:10:00Z")
        ende = ki._utc_sek("2026-01-01T00:10:00Z")
        self.assertEqual(self.runde(ende + 29 * 60), [])
        self.assertEqual(len(self.runde(ende + 30 * 60)), 1)

    def test_nie_bei_wartendem_auftrag_belegt_oder_immer_an(self):
        self.merken(seit=0.0)
        lid = db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="Bauer", beschreibung="x", status="angemeldet", angemeldet_utc=db.jetzt())
        with db.schreiben(self.con):
            aid = db.einfuegen(self.con, "ki_auftrag", projekt_id=self.pid, ki_id=self.kid, lauf_id=lid, auftraggeber="Bauer", prompt="p", seed=1,
                               zustand="wartet", angelegt_utc=db.jetzt())
        self.assertEqual(self.runde(10 ** 10), [])                                       # Auftrag wartet: KI wird gleich gebraucht
        self.con.execute("UPDATE ki_auftrag SET zustand = 'fertig' WHERE id = ?", (aid,))
        self.con.execute("UPDATE ki SET zustand = 'belegt'")
        self.assertEqual(self.runde(10 ** 10), [])
        self.con.execute("UPDATE ki SET zustand = 'an'")
        self.assertEqual(self.runde(10 ** 10, immer={"comfy"}), [])                       # immer an: nie
        self.assertEqual(self.beendet, [])
        self.assertIn("comfy", ki.gestartet_laden())

    def test_fremder_oder_neu_vergebener_prozess_nie(self):
        self.merken(seit=0.0, beginn=99)
        self.assertEqual(self.runde(10 ** 10, beginn=lambda pid: 12345), [])              # PID gehört jetzt einem anderen Prozess
        self.assertEqual(self.beendet, [])
        self.assertNotIn("comfy", ki.gestartet_laden())                                  # vergessen, nie mehr angefasst
        self.merken(seit=0.0)
        self.assertEqual(self.runde(10 ** 10, beginn=lambda pid: None), [])               # schon beendet
        self.assertEqual(self.beendet, [])
        self.assertEqual(self.runde(10 ** 10), [])                                       # nichts gemerkt = nichts beenden
        self.assertEqual(self.beendet, [])

    def test_uebersicht_zeigt_betrieb(self):
        self.merken()
        with mock.patch.object(ki, "immer_an", return_value=set()):
            k = ki.uebersicht(self.con, self.pid)["kis"][0]
        self.assertEqual((k["betrieb"], k["von_amw"], k["leerlauf_min"]), ("bedarf", True, 30))
        with mock.patch.object(ki, "immer_an", return_value={"comfy"}):
            self.assertEqual(ki.uebersicht(self.con, self.pid)["kis"][0]["betrieb"], "immer")
        with open(os.path.join(os.path.dirname(workbench.__file__), "workbench.html"), encoding="utf-8") as f:
            html = f.read()
        for x in ('ki_bedarf: "nur bei Bedarf"', 'ki_bedarf: "only when needed"', 'pcFeld("ki_leerlauf_min"', 'pcFeld("ki_immer_an"',
                  'e_ki_immer: "Lokale KIs immer an"', 'e_ki_immer: "Local AIs always on"'):
            self.assertIn(x, html)


if __name__ == "__main__":
    unittest.main()
