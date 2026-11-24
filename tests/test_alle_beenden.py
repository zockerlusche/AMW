"""A2048 (V12, D1531 §4): „Alle speichern & beenden“ als Sammelbefehl über alle Fenster-Agenten (auch über alle Projekte) – nur
der Mensch im eigenen Terminal – und die Rückmeldung je Agent: sichert · abgemeldet · beendet. Ohne echte Prozesse."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import db, kern, steuerung, workbench


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
            self.pid2 = db.einfuegen(self.con, "projekt", name="Q", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "Lead", rolle="lead", arbeitsweise="chat")
        for p, k in ((self.pid, "Bauer"), (self.pid, "Maler"), (self.pid, "Ruhe"), (self.pid2, "Fremd")):
            kern.agent_neu(self.con, p, k)
            steuerung.profil_setzen(self.con, p, "Entwickler", k, ordner=self.ordner.name)
        self.lebend = set()
        m = mock.patch.object(steuerung, "lebt", side_effect=lambda pid: pid in self.lebend)
        m.start()
        self.addCleanup(m.stop)

    def sitzung(self, pid, kennung, cpid, zustand="aktiv"):
        aid = kern.agent_zeile(self.con, pid, kennung)["id"]
        with db.schreiben(self.con):
            sid = db.einfuegen(self.con, "sitzung", agent_id=aid, claude_sitzung=f"s-{cpid}", gestartet_utc=db.jetzt(),
                               schluessel_datei="x.json", claude_pid=cpid, zustand=zustand)
        self.lebend.add(cpid)
        return sid

    def befehl(self, *args, von="Entwickler", sitzung=False):
        from amw import cli
        aus = io.StringIO()
        umgebung = {"AMW_AGENT": "", "CLAUDECODE": "1" if sitzung else "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}
        with contextlib.redirect_stdout(aus), mock.patch.dict(os.environ, umgebung):
            rc = cli.main(["agent", *args, "--projekt", "P", "--von", von])
        return rc, aus.getvalue()


class AlleBeenden(Grund):
    def test_sammelbefehl_und_rueckmeldung(self):
        self.sitzung(self.pid, "Bauer", 101)
        sid = self.sitzung(self.pid, "Maler", 102)
        self.sitzung(self.pid2, "Fremd", 201)
        rc, aus = self.befehl("alle-beenden", "--frist", "10")
        self.assertFalse(rc, aus)
        self.assertIn("P: Bauer, Maler sichern – beendet spätestens", aus)
        self.assertNotIn("Fremd", aus)                                          # ohne --alle-projekte nur dieses Projekt
        st = steuerung.ende_stand(self.con, self.pid)
        self.assertEqual({x["kennung"]: x["zustand"] for x in st["agenten"]}, {"Bauer": "sichert", "Maler": "sichert"})
        self.assertFalse(st["fertig"])
        with db.schreiben(self.con):                                            # Maler meldet sich ab
            self.con.execute("UPDATE sitzung SET zustand = 'ruht' WHERE id = ?", (sid,))
        self.lebend.discard(101)                                                # Bauer ist schon weg
        st = {x["kennung"]: x["zustand"] for x in steuerung.ende_stand(self.con, self.pid)["agenten"]}
        self.assertEqual(st, {"Bauer": "beendet", "Maler": "abgemeldet"})
        steuerung.ende_pruefen(self.con, beenden_mit=lambda p: self.lebend.discard(p))   # der Wächter beendet Maler
        st = steuerung.ende_stand(self.con, self.pid)
        self.assertTrue(st["fertig"])
        rc, aus = self.befehl("ende-stand")
        self.assertIn("P: alle beendet", aus)
        self.assertEqual(workbench.daten_ende_stand(self.con, self.pid)["fertig"], True)

    def test_ueber_alle_projekte(self):
        self.sitzung(self.pid, "Bauer", 101)
        self.sitzung(self.pid2, "Fremd", 201)
        rc, aus = self.befehl("alle-beenden", "--alle-projekte")
        self.assertIn("P: Bauer sichern", aus)
        self.assertIn("Q: Fremd sichern", aus)
        rc, aus = self.befehl("ende-stand", "--alle-projekte")
        self.assertIn("Fremd", aus)
        self.assertIn("sichert (bis", aus)

    def test_nur_der_mensch_im_eigenen_terminal(self):
        self.sitzung(self.pid, "Bauer", 101)
        self.assertTrue(self.befehl("alle-beenden", von="Lead")[0])               # nicht der Lead
        self.assertTrue(self.befehl("alle-beenden", sitzung=True)[0])            # nicht aus einer Agenten-Sitzung
        self.assertEqual(steuerung.ende_stand(self.con, self.pid)["agenten"], [])

    def test_ohne_laufende_sitzung(self):
        rc, aus = self.befehl("alle-beenden")
        self.assertIn("P: keine laufende Sitzung", aus)
        rc, aus = self.befehl("ende-stand")
        self.assertEqual(aus.strip(), "")


if __name__ == "__main__":
    unittest.main()
