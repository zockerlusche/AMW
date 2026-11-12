"""Startbefehl je Agent zum Kopieren (A1610): fortsetzen/neu, PowerShell/cmd, alle Angaben, feste neue Sitzungs-ID, keine
Geheimnisse, nur Terminal-Agenten."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import tempfile
import unittest

from amw import db, kern, steuerung, workbench


class Startbefehl(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Mein Projekt", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead", arbeitsweise="chat")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.arbeit = os.path.join(self.ordner.name, "mit leer")
        self.zusatz = os.path.join(self.ordner.name, "zusatz")
        os.makedirs(self.arbeit), os.makedirs(self.zusatz)
        steuerung.profil_setzen(self.con, self.pid, kern.ENTWICKLER, "CC1", ordner=self.arbeit, zusatzordner=[self.zusatz],
                                modell="opus", denkstufe="high", rechte="auto", startsatz='Lies "amw lesen" & arbeite')

    def sitzung(self, sid):
        aid = kern.agent_zeile(self.con, self.pid, "CC1")["id"]
        with db.schreiben(self.con):
            db.einfuegen(self.con, "sitzung", agent_id=aid, claude_sitzung=sid, gestartet_utc=db.jetzt(), zustand="beendet")

    def test_neu_ohne_sitzung_mit_allen_angaben(self):
        s = steuerung.startbefehle(self.con, self.pid, "CC1")
        self.assertIsNone(s["befehle"]["powershell"]["fortsetzen"])
        ps, cmd = s["befehle"]["powershell"]["neu"], s["befehle"]["cmd"]["neu"]
        for teil in ("--session-id", s["neue_sitzung"], "--effort", "high", "--model", "opus", "--add-dir", self.zusatz, "AMW_AGENT", "Mein Projekt"):
            self.assertIn(teil, ps)
            self.assertIn(teil, cmd)
        self.assertIn(f"Set-Location '{self.arbeit}'", ps)                                    # Pfad mit Leerzeichen gequotet
        self.assertIn(f'cd /d "{self.arbeit}"', cmd)
        self.assertIn("'Lies \"amw lesen\" & arbeite'", ps)
        self.assertIn('"Lies \\"amw lesen\\" & arbeite"', cmd)
        self.assertEqual(s["neue_sitzung"], steuerung.startbefehle(self.con, self.pid, "CC1")["neue_sitzung"])   # fest

    def test_fortsetzen_mit_letzter_sitzung_ohne_startsatz(self):
        alt = steuerung.startbefehle(self.con, self.pid, "CC1")["neue_sitzung"]
        self.sitzung("11111111-2222-3333-4444-555555555555")
        s = steuerung.startbefehle(self.con, self.pid, "CC1")
        f = s["befehle"]["powershell"]["fortsetzen"]
        self.assertIn("--resume 11111111-2222-3333-4444-555555555555", f)
        self.assertNotIn("Lies", f)
        self.assertEqual(s["letzte"]["sitzung"], "11111111-2222-3333-4444-555555555555")
        self.assertNotEqual(s["neue_sitzung"], alt)                                            # nach Benutzung eine neue

    def test_gleich_wie_die_amw_selbst_startet(self):
        self.sitzung("abc")
        s = steuerung.startbefehle(self.con, self.pid, "CC1")
        p = steuerung.profil(self.con, self.pid, "CC1")
        selbst = steuerung.befehl(p, "abc")
        for teil in ("--resume", "abc", "--effort", "--model", "--add-dir"):
            self.assertIn(teil, selbst)
            self.assertIn(teil, s["befehle"]["powershell"]["fortsetzen"])

    def test_chat_und_ohne_ordner_ohne_befehl(self):
        self.assertEqual(steuerung.startbefehle(self.con, self.pid, "TL")["grund"], "chat")
        kern.agent_neu(self.con, self.pid, "CC2")
        s = steuerung.startbefehle(self.con, self.pid, "CC2")
        self.assertEqual((s["grund"], s["befehle"]), ("kein_ordner", None))

    def test_in_den_einstellungen_und_ohne_geheimnisse(self):
        d = workbench.daten_einstellungen(self.con, self.pid)
        a = next(x for x in d["agenten"] if x["kennung"] == "CC1")
        text = repr(a["start"]).lower()
        for wort in ("token", "passwort", "schluessel", "secret"):
            self.assertNotIn(wort, text)
        self.assertEqual(d, workbench.daten_einstellungen(self.con, self.pid))                  # Ansicht ändert sich nicht von selbst


if __name__ == "__main__":
    unittest.main()
