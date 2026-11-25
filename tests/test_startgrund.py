"""A2047 (V9, D1531 §9): Beim Headless-Start speichert der Disponent „warum dieses jetzt“ (Platz in der Reihenfolge, deren Grund,
Arbeitsplatz, von wem) als plan_ereignis headless_start – wie „verteilt“ bei Fenster-Agenten; disponent.warum liest beides.
Platz vorbereiten, rot vor Bau und den Starter ersetzt hier eine Attrappe."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import abnahme, arbeitspaket, db, disponent, kern, platz


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, platz_wurzel=os.path.join(self.ordner.name, "plaetze"), plaetze=1)
        self.p = platz.plaetze(self.con, self.pid)[0]
        for ziel, wert in ((platz, ("vorbereiten", {"basis": "abc1234def"})), (abnahme, ("rot_vor_bau", {"ok": True}))):
            m = mock.patch.object(ziel, wert[0], return_value=wert[1])
            m.start()
            self.addCleanup(m.stop)
        proc = mock.Mock(pid=4711)
        m = mock.patch("subprocess.Popen", return_value=proc)
        m.start()
        self.addCleanup(m.stop)

    def paket(self, titel="plus reparieren", rang=50):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel, rang=rang)
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET pruefbefehl = 'python -m unittest tests.x', dateibereich = 'lib/', groesse = 'S',"
                             " art = 'mechanisch' WHERE id = ?", (aid,))
        arbeitspaket.setzen(self.con, self.pid, "TL", aid, art="p")
        arbeitspaket.zustand_setzen(self.con, self.pid, "TL", aid, "startklar")
        return aid

    def gruende(self, aid):
        return [json.loads(r[0]) for r in self.con.execute(
            "SELECT text FROM plan_ereignis WHERE aufgabe_id = ? AND art = ? ORDER BY id", (aid, disponent.START_GRUND))]


class Startgrund(Grund):
    def test_disponent_speichert_platz_in_der_reihe_und_grund(self):
        self.paket("anderes", rang=5)
        aid = self.paket("dieses", rang=1)
        aus = disponent.starten(self.con, self.pid, aid, self.p, self.ordner.name)
        self.assertIn(f"A{aid} gestartet als Headless 1", aus)
        g = self.gruende(aid)
        self.assertEqual(len(g), 1)
        self.assertEqual((g[0]["aufgabe"], g[0]["platz"], g[0]["von"]), (aid, 1, "AMW"))
        self.assertIsInstance(g[0]["reihe"], int)
        self.assertIn(f"Platz {g[0]['reihe']} in der Reihenfolge · startklar · Rest-Pfad", g[0]["grund"])
        self.assertIn("Arbeitsplatz 1 frei, Regeln des Wächters erfüllt", g[0]["grund"])
        w = disponent.warum(self.con, self.pid, aid)
        assert w is not None
        self.assertEqual((w["art"], w["reihe"]), (disponent.START_GRUND, g[0]["reihe"]))

    def test_von_hand_steht_im_grund(self):
        aid = self.paket()
        kern.projekt_ordner_setzen(self.con, self.pid, self.ordner.name)
        from amw import waechter
        with mock.patch.object(waechter, "pruefen", return_value={"ok": True}):
            disponent.handstart(self.con, self.pid, aid, "TL")
        self.assertIn("von Hand gestartet (TL)", self.gruende(aid)[0]["grund"])
        self.assertEqual(self.gruende(aid)[0]["von"], "TL")

    def test_regel6_kein_start_kein_grund(self):
        aid = self.paket()
        with mock.patch.object(abnahme, "rot_vor_bau", return_value={"ok": False, "grund": "prüft nichts"}):
            aus = disponent.starten(self.con, self.pid, aid, self.p, self.ordner.name)
        self.assertIn("Regel 6", aus)
        self.assertEqual(self.gruende(aid), [])
        self.assertIsNone(disponent.warum(self.con, self.pid, aid))

    def test_warum_liest_auch_verteilt(self):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Fenster-Paket")
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="AMW", art="verteilt", aufgabe_id=aid,
                         text=json.dumps({"aufgabe": aid, "agent": "CC1", "grund": "Rang 40"}))
        w = disponent.warum(self.con, self.pid, aid)
        assert w is not None
        self.assertEqual((w["art"], w["agent"], w["grund"]), ("verteilt", "CC1", "Rang 40"))


if __name__ == "__main__":
    unittest.main()
