"""A2051: ein Gesamtlauf hat immer eine Frist (Projekt-Einstellung gesamtlauf_frist_min, Vorgabe 60, 0 = keine); ihr Ende geht als
AMW_LAUF_ENDE an den Befehl (amw.testlauf hört kurz vorher auf und schreibt „Läuft gerade: …“); endet er mit rc 124, erfährt der
Lead, welches Modul und welcher Test zuletzt liefen – über `amw lauf ausfuehren` und wenn der Dienst den Lauf rechnet."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

from amw import betrieb, db, kern, laufdienst

TOT = 2 ** 22 + 7
SKRIPT = """import os, sys
sys.stdout.reconfigure(encoding="utf-8")                       # wie der echte Befehl (python -X utf8)
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ende.txt"), "w") as f:
    f.write(os.environ.get("AMW_LAUF_ENDE", ""))
print("[1/2] test_a ok 0.1s (p1)")
print("Läuft gerade: p0 test_rundgang · test_rundgang.Online.test_seite (still seit 400 s)")
sys.exit(int(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "rc.txt")).read()))
"""


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db"), "LOCALAPPDATA": os.path.join(self.ordner.name, "lad")})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        self.skript = os.path.join(self.ordner.name, "suite.py")
        with open(self.skript, "w", encoding="utf-8") as f:
            f.write(SKRIPT)
        self.befehl = f'"{sys.executable}" suite.py'
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt(),
                                    einstellungen=json.dumps({"gesamtlauf_befehl": self.befehl}))
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        with db.schreiben(self.con):
            self.con.execute("UPDATE agent SET ordner = ? WHERE kennung = 'CC1'", (self.ordner.name,))
        mock.patch.object(laufdienst, "PRUEF_S", 0.2).start()
        self.addCleanup(mock.patch.stopall)

    def an_tl(self):
        return [(r["kurz"], r["text"]) for r in self.con.execute(
            "SELECT n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = 'TL' ORDER BY n.id")]

    def ende(self):
        with open(os.path.join(self.ordner.name, "ende.txt"), encoding="utf-8") as f:
            return f.read()

    def rc(self, rc):
        with open(os.path.join(self.ordner.name, "rc.txt"), "w", encoding="utf-8") as f:
            f.write(str(rc))

    def dienst_lauf(self, rc, **kw):
        self.rc(rc)
        datei = os.path.join(self.ordner.name, "aus.txt")
        lid = betrieb.lauf_start(self.con, self.pid, "CC1", "Gesamtlauf Probe", warten=True, speicher_frei=32.0, braucht_gb=1,
                                 befehl=[self.befehl], ordner=self.ordner.name, ergebnis_datei=datei, waechter=TOT, **kw)
        laufdienst.Laufdienst(self.con, starten=lambda ziel, *args: ziel(*args)).runde()
        return lid


class Frist(Grund):
    def test_vorgabe_und_einstellung(self):
        self.assertEqual(laufdienst.gesamtlauf_frist(self.con, self.pid), 60)
        kern.projekt_einstellen(self.con, self.pid, "TL", gesamtlauf_frist_min=45)
        self.assertEqual(laufdienst.gesamtlauf_frist(self.con, self.pid), 45)
        kern.projekt_einstellen(self.con, self.pid, "TL", gesamtlauf_frist_min=0)
        self.assertEqual(laufdienst.gesamtlauf_frist(self.con, self.pid), 0)                 # 0 = keine Vorgabe-Frist
        self.assertTrue(laufdienst.ist_gesamtlauf(self.con, self.pid, [self.befehl], "x"))
        self.assertFalse(laufdienst.ist_gesamtlauf(self.con, self.pid, [f"{self.befehl} -k nur"], "x"))   # Teil-Lauf

    def test_dienst_gibt_das_ende_mit_und_meldet_rc_124_dem_lead(self):
        lid = self.dienst_lauf(124)
        self.assertGreater(float(self.ende()), 0)                                             # AMW_LAUF_ENDE gesetzt (Vorgabe 60 min)
        m = [k for k in self.an_tl() if f"L{lid} Gesamtlauf an der Frist" in k[0]]
        self.assertEqual(len(m), 1, self.an_tl())
        self.assertIn("Läuft gerade: p0 test_rundgang", m[0][0])
        self.assertIn("test_rundgang.Online.test_seite", m[0][1])

    def test_gegenprobe_gruen_keine_meldung(self):
        self.dienst_lauf(0)
        self.assertFalse([k for k in self.an_tl() if "an der Frist" in k[0]])

    def test_ausfuehren_im_terminal(self):
        from amw import cli
        self.rc(124)
        aus = io.StringIO()
        alt = os.getcwd()
        os.chdir(self.ordner.name)
        self.addCleanup(os.chdir, alt)
        with mock.patch.dict(os.environ, {"AMW_AGENT": "", "AMW_PROJEKT": ""}), contextlib.redirect_stdout(aus):
            rc = cli.main(["lauf", "ausfuehren", "--leicht", "--beschreibung", "Gesamtlauf", "--projekt", "P", "--von", "CC1", "--",
                           self.befehl])
        self.assertEqual(rc, 124, aus.getvalue())
        l = self.con.execute("SELECT * FROM lauf ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(l["frist_min"], 60)                                                    # Vorgabe-Frist gespeichert
        self.assertGreater(float(self.ende()), 0)
        self.assertTrue([k for k in self.an_tl() if f"L{l['id']} Gesamtlauf an der Frist" in k[0]], self.an_tl())


if __name__ == "__main__":
    unittest.main()
