"""Arbeitsplätze für kopflose Arbeiter (A1855, M50 S1b): eigener Klon (kein gemeinsames .git, keine Hardlinks), eigene Daten
und eigener Port, Live-Datenbank unverändert, Zurücksetzen auch nach Abbruch, ohne Plätze alles wie bisher. Alle Pfade
liegen im Test-Ordner – keine festen Pfade."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from amw import cli, db, kern, platz

CODE = os.path.dirname(os.path.dirname(os.path.abspath(platz.__file__)))
OHNE = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def g(ordner, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", ordner, *args], check=True, capture_output=True,
                          text=True, creationflags=OHNE).stdout.strip()


@unittest.skipUnless(shutil.which("git"), "git fehlt")
class Platz(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        o = self.ordner.name
        self.live = os.path.join(o, "live.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.live})
        u.start()
        self.addCleanup(u.stop)
        os.environ.pop("AMW_AGENT", None)
        self.con = db.anlegen(self.live)
        self.addCleanup(self.con.close)
        self.repo = os.path.join(o, "projekt")
        os.makedirs(self.repo)
        g(self.repo, "init", "-q", "-b", "main")
        with open(os.path.join(self.repo, "a.txt"), "w") as f:
            f.write("a\n")
        g(self.repo, "add", "a.txt")
        g(self.repo, "commit", "-q", "-m", "a")
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.projekt_ordner_setzen(self.con, self.pid, self.repo) if hasattr(kern, "projekt_ordner_setzen") else None
        self.wurzel = os.path.join(o, "plaetze")

    def einrichten(self, n=2):
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, platz_wurzel=self.wurzel, plaetze=n)

    def test_ohne_plaetze_wie_bisher_und_nur_der_mensch_gibt_frei(self):
        self.assertEqual(platz.plaetze(self.con, self.pid), [])
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus):
            cli.main(["platz", "liste", "--projekt", "Spiel", "--von", "TL"])
        self.assertIn("Keine Arbeitsplätze", aus.getvalue())
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "TL", plaetze=1)                  # der Lead nicht
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, platz_wurzel="relativ")
        self.einrichten()
        self.assertEqual([p["nr"] for p in platz.plaetze(self.con, self.pid)], [1, 2])
        self.assertEqual(platz.plaetze(self.con, self.pid)[1]["port"], platz.PORT_BASIS + 2)

    def test_eigener_klon_zweig_ab_main_sauber(self):
        self.einrichten(1)
        p = platz.plaetze(self.con, self.pid)[0]
        r = platz.vorbereiten(p, self.repo, "paket-7")
        self.assertTrue(os.path.isdir(os.path.join(p["klon"], ".git")))                     # Ordner, keine Worktree-Datei
        gemeinsam = g(p["klon"], "rev-parse", "--path-format=absolute", "--git-common-dir")
        self.assertEqual(os.path.normcase(os.path.abspath(gemeinsam)), os.path.normcase(os.path.join(p["klon"], ".git")))
        objekte = [os.path.join(w, f) for w, _, fs in os.walk(os.path.join(p["klon"], ".git", "objects")) for f in fs]
        self.assertTrue(objekte and all(os.stat(x).st_nlink == 1 for x in objekte))        # keine Hardlinks zur Quelle
        self.assertEqual(r["basis"], g(self.repo, "rev-parse", "main"))
        self.assertEqual(g(p["klon"], "rev-parse", "--abbrev-ref", "HEAD"), "paket-7")
        self.assertTrue(platz.sauber(p))
        with open(os.path.join(self.repo, "b.txt"), "w") as f:                               # main geht weiter …
            f.write("b\n")
        g(self.repo, "add", "b.txt")
        g(self.repo, "commit", "-q", "-m", "b")
        r = platz.vorbereiten(p, self.repo, "paket-8")                                      # … der nächste Platz-Lauf startet dort
        self.assertEqual(r["basis"], g(self.repo, "rev-parse", "main"))

    def test_eigene_daten_eigener_port_live_db_unveraendert(self):
        self.einrichten(1)
        p = platz.plaetze(self.con, self.pid)[0]
        platz.vorbereiten(p, self.repo, "paket-1")
        self.con.commit()
        vorher = hashlib.sha256(open(self.live, "rb").read()).hexdigest()
        u = platz.umgebung(p)
        u["PYTHONPATH"] = CODE
        prog = ("from amw import db, einstellungen\n"
                "c = db.anlegen(db.db_pfad())\n"
                "with db.schreiben(c):\n"
                "    db.einfuegen(c, 'projekt', name='Im Platz', angelegt_utc=db.jetzt())\n"
                "print(db.db_pfad()); print(einstellungen.wert('port'))\n")
        r = subprocess.run([sys.executable, "-X", "utf8", "-c", prog], cwd=p["klon"], env=u, capture_output=True, text=True, creationflags=OHNE)
        self.assertEqual(r.returncode, 0, r.stderr)
        pfad, port = r.stdout.split()
        self.assertEqual(os.path.normcase(pfad), os.path.normcase(p["db"]))
        self.assertEqual(int(port), p["port"])
        self.assertNotEqual(int(port), 8780)
        self.assertEqual(hashlib.sha256(open(self.live, "rb").read()).hexdigest(), vorher)   # Live-DB unverändert
        self.assertNotIn("AMW_AGENT", u)
        self.assertTrue(platz.sauber(p))                                                      # Daten liegen neben dem Klon

    def test_zuruecksetzen_nach_abbruch(self):
        self.einrichten(1)
        p = platz.plaetze(self.con, self.pid)[0]
        platz.vorbereiten(p, self.repo, "paket-2")
        with open(os.path.join(p["klon"], "a.txt"), "w") as f:                               # halbe Arbeit
            f.write("kaputt\n")
        with open(os.path.join(p["klon"], "neu.txt"), "w") as f:
            f.write("x\n")
        g(p["klon"], "add", "neu.txt")
        g(p["klon"], "commit", "-q", "-m", "halb")
        with open(os.path.join(p["klon"], "fremd.tmp"), "w") as f:
            f.write("x\n")
        open(os.path.join(p["klon"], ".git", "index.lock"), "w").close()                     # Abbruch mitten in git
        with open(os.path.join(p["daten"], "tmp", "rest.txt"), "w") as f:
            f.write("x\n")
        self.assertFalse(platz.sauber(p))
        self.assertTrue(platz.zuruecksetzen(p))
        self.assertEqual(g(p["klon"], "rev-parse", "HEAD"), g(self.repo, "rev-parse", "main"))
        self.assertFalse(os.path.exists(os.path.join(p["klon"], "neu.txt")))
        self.assertFalse(os.path.exists(os.path.join(p["daten"], "tmp", "rest.txt")))
        self.assertTrue(os.path.exists(os.path.join(p["lad"], "amw", "einstellungen.json")))   # Port bleibt eingerichtet
        self.assertTrue(os.path.exists(os.path.join(self.repo, "a.txt")))                     # die Quelle unberührt

    def test_platz_nie_im_projektordner_und_kein_fremder_ordner(self):
        p = platz.pfade(os.path.join(self.repo, "innen"), 1)
        with self.assertRaises(platz.PlatzFehler):
            platz.vorbereiten(p, self.repo, "x")
        p = platz.pfade(self.wurzel, 1)
        os.makedirs(p["klon"])
        with open(os.path.join(p["klon"], "fremd.txt"), "w") as f:
            f.write("x")
        with self.assertRaises(platz.PlatzFehler):                                          # nicht leer und kein Klon: nichts anfassen
            platz.vorbereiten(p, self.repo, "x")
        self.assertTrue(os.path.exists(os.path.join(p["klon"], "fremd.txt")))


if __name__ == "__main__":
    unittest.main()
