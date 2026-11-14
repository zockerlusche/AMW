"""Profiländerung auf Wort des Entwicklers (A1662): der Lead darf mit --wort W<nr> (frisch, aus diesem Projekt) Profile
ändern – auch über den Dateiaustausch; nie die eigenen Rechte/Fernsteuerung, nie die Rolle; jede Änderung im Verlauf und als
Info an den Menschen."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import datetime
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import cli, db, kern, steuerung


class ProfilAufWort(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        umgebung = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "daten", "amw.db")})
        umgebung.start()
        self.addCleanup(umgebung.stop)
        self.con = db.anlegen()
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
            self.fremd = db.einfuegen(self.con, "projekt", name="Fremd", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC2")
        self.ziel = os.path.join(self.ordner.name, "arbeit")
        os.makedirs(self.ziel)

    def wort(self, stunden=1, pid=None):
        z = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=stunden)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "wortlaut", projekt_id=pid or self.pid, zeit_utc=z, text="Trag CCamw2 den Ordner ein",
                                kanal="chat-tl", erfasst_von="TL", erfasst_utc=db.jetzt())

    def test_mit_frischem_wort_ok_verlauf_und_info(self):
        w = self.wort()
        p = steuerung.profil_setzen(self.con, self.pid, "TL", "CC2", wort=f"W{w}", ordner=self.ziel)
        self.assertEqual(p["ordner"], self.ziel)
        e = self.con.execute("SELECT von, text FROM plan_ereignis WHERE art = 'profil_auf_wort'").fetchall()
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0][0], "TL")
        self.assertIn(f"CC2 · ordner: None → {self.ziel} · W{w}", e[0][1])
        info = self.con.execute("SELECT n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ?",
                                (kern.ENTWICKLER,)).fetchone()
        self.assertIn(f"auf dein Wort W{w}", info[0])
        self.assertIn("Trag CCamw2 den Ordner ein", info[1])

    def test_altes_fremdes_oder_kaputtes_wort_abgewiesen(self):
        for wort in (f"W{self.wort(stunden=25)}", f"W{self.wort(pid=self.fremd)}", "W999", "Ordner bitte"):
            with self.assertRaises(kern.AmwFehler, msg=wort):
                steuerung.profil_setzen(self.con, self.pid, "TL", "CC2", wort=wort, ordner=self.ziel)
        self.assertIsNone(steuerung.profil(self.con, self.pid, "CC2")["ordner"])
        with self.assertRaises(kern.AmwFehler):                                      # Pfad muss es geben
            steuerung.profil_setzen(self.con, self.pid, "TL", "CC2", wort=f"W{self.wort()}", ordner=os.path.join(self.ziel, "fehlt"))

    def test_nur_lead_und_nie_eigene_rechte(self):
        w = f"W{self.wort()}"
        with self.assertRaises(kern.AmwFehler):                                      # ein Agent darf es nicht, auch mit Wort
            steuerung.profil_setzen(self.con, self.pid, "CC2", "CC2", wort=w, ordner=self.ziel)
        for feld in ({"rechte": "umgehen"}, {"fernsteuerung": True}, {"neustart_auto": True}):
            with self.assertRaises(kern.AmwFehler, msg=feld):
                steuerung.profil_setzen(self.con, self.pid, "TL", "TL", wort=w, **feld)
        self.assertEqual(steuerung.profil(self.con, self.pid, "TL")["rechte"], "vorgabe")
        steuerung.profil_setzen(self.con, self.pid, "TL", "TL", wort=w, ordner=self.ziel)   # den eigenen Ordner darf er

    def test_befehlszeile_rolle_nicht_und_dateiaustausch_nur_mit_wort(self):
        w = f"W{self.wort()}"
        basis = ["agent", "profil", "CC2", "--projekt", "P", "--von", "TL"]
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            self.assertNotEqual(cli.main(basis + ["--wort", w, "--rolle", "lead"]), 0)   # Rolle nie über ein Wort
        self.assertIn("nur Profilfelder", aus.getvalue())
        self.assertNotEqual(kern.agent_zeile(self.con, self.pid, "CC2")["rolle"], "lead")
        marke = cli.KANAL.set("bruecke")
        try:
            with contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
                self.assertNotEqual(cli.main(basis + ["--ordner", self.ziel]), 0)        # Dateiaustausch ohne Wort: nein
                self.assertIsNone(steuerung.profil(self.con, self.pid, "CC2")["ordner"])
                self.assertIn(cli.main(basis + ["--ordner", self.ziel, "--wort", w]), (0, None))   # mit Wort: ja
                self.assertIn(cli.main(basis), (0, None))                            # nur ansehen geht immer
        finally:
            cli.KANAL.reset(marke)
        self.assertEqual(steuerung.profil(self.con, self.pid, "CC2")["ordner"], self.ziel)


if __name__ == "__main__":
    unittest.main()
