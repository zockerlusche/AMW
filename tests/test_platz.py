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
        kopf = g(p["klon"], "rev-parse", "HEAD")                                                # der halbe Commit
        r = platz.zuruecksetzen(p, aufgabe=7)
        self.assertTrue(r["sauber"])
        self.assertEqual(g(p["klon"], "rev-parse", "HEAD"), g(self.repo, "rev-parse", "main"))
        self.assertFalse(os.path.exists(os.path.join(p["klon"], "neu.txt")))
        self.assertFalse(os.path.exists(os.path.join(p["daten"], "tmp", "rest.txt")))
        self.assertTrue(os.path.exists(os.path.join(p["lad"], "amw", "einstellungen.json")))   # Port bleibt eingerichtet
        self.assertTrue(os.path.exists(os.path.join(self.repo, "a.txt")))                     # die Quelle unberührt
        # A1861 / B2894: nichts gelöscht – alles liegt im Archiv
        arch = r["archiv"]
        self.assertTrue(arch.endswith("-A7") and os.path.dirname(arch).endswith("_archiv"), arch)
        self.assertIn("kaputt", open(os.path.join(arch, "ungesichert.patch"), encoding="utf-8").read())      # geänderte Datei
        self.assertTrue(os.path.exists(os.path.join(arch, "commits.bundle")))                                 # halber Commit
        self.assertIn(kopf, g(p["klon"], "bundle", "list-heads", os.path.join(arch, "commits.bundle")))        # Commit gesichert
        self.assertTrue(os.path.exists(os.path.join(arch, "dateien", "fremd.tmp")))                            # fremde Datei verschoben
        self.assertTrue(os.path.exists(os.path.join(arch, "index.lock")))                                     # Sperre verschoben
        self.assertTrue(os.path.exists(os.path.join(arch, "daten", "tmp", "rest.txt")))                        # Datenordner verschoben
        self.assertIsNone(platz.zuruecksetzen(p)["archiv"])                                                   # sauber: kein leeres Archiv

    def test_sichern_fehlgeschlagen_nichts_zurueckgesetzt(self):
        """P244 (Pflicht): schlägt das Sichern fehl, läuft kein checkout -f – die Änderung bleibt im Platz."""
        self.einrichten(1)
        p = platz.plaetze(self.con, self.pid)[0]
        platz.vorbereiten(p, self.repo, "paket")
        with open(os.path.join(p["klon"], "a.txt"), "w") as f:
            f.write("wichtig\n")
        echt = platz._roh
        with mock.patch.object(platz, "_roh", lambda o, *a: (1, b"") if a[:1] == ("diff",) else echt(o, *a)):
            with self.assertRaises(platz.PlatzFehler) as e:
                platz.zuruecksetzen(p)
        self.assertIn("nichts zurückgesetzt", str(e.exception))
        self.assertEqual(open(os.path.join(p["klon"], "a.txt")).read(), "wichtig\n")        # nicht verloren
        with mock.patch.object(platz, "_git", side_effect=platz.PlatzFehler("bundle kaputt")):
            g(p["klon"], "add", "a.txt")
            g(p["klon"], "commit", "-q", "-m", "halb")
            with self.assertRaises(platz.PlatzFehler):
                platz.zuruecksetzen(p)
        self.assertEqual(open(os.path.join(p["klon"], "a.txt")).read(), "wichtig\n")

    def test_aufraeumen_nach_paketende(self):
        """B2894: ist das Paket fertig, wandert sein Archiv nach _loeschen – nie gelöscht; offene bleiben im Archiv."""
        self.einrichten(1)
        p = platz.plaetze(self.con, self.pid)[0]
        platz.vorbereiten(p, self.repo, "paket")
        fertig = kern.aufgabe_neu(self.con, self.pid, "TL", "Fertig", "TL")
        offen = kern.aufgabe_neu(self.con, self.pid, "TL", "Offen", "TL")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'x', fertig_utc = ? WHERE id = ?", (db.jetzt(), fertig))
        for aid in (fertig, offen):
            with open(os.path.join(p["klon"], f"rest{aid}.txt"), "w") as f:
                f.write("x")
            platz.zuruecksetzen(p, aufgabe=aid)
        w = os.path.dirname(p["klon"])
        self.assertEqual(len(platz.aufraeumen(self.con, self.pid, w)), 1)
        self.assertTrue(any(n.endswith(f"-A{fertig}") for n in os.listdir(os.path.join(w, "_loeschen"))))
        self.assertTrue(any(n.endswith(f"-A{offen}") for n in os.listdir(os.path.join(w, "_archiv"))))
        self.assertGreater(platz.groesse(os.path.join(w, "_loeschen")), 0)
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus):
            cli.main(["platz", "liste", "--projekt", "Spiel", "--von", "TL"])
        self.assertIn("zum Löschen", aus.getvalue())
        self.assertIn("leeren kann nur der Mensch", aus.getvalue())

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

    def test_a1911_klon_mit_zeilenenden_des_projekts(self):
        """P326-Hinweis: Der Klon checkte mit dem Systemwert core.autocrlf=true aus (CRLF), das Projekt sagt false (LF); der
        Arbeiter ruft git ohne System-Konfiguration auf (false) und sah so Dateien, die er anfasste, ganz als geändert."""
        from amw import pruefung_c
        cfg = os.path.join(self.ordner.name, "gitconfig-pc")
        with open(cfg, "w", encoding="utf-8", newline="\n") as f:
            f.write("[core]\n\tautocrlf = true\n")                                          # wie der Systemwert auf dem PC
        u = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": cfg})
        u.start()
        self.addCleanup(u.stop)
        pruefung_c._AUTOCRLF_PROJEKT.clear()
        self.addCleanup(pruefung_c._AUTOCRLF_PROJEKT.clear)
        g(self.repo, "config", "core.autocrlf", "false")
        roh = lambda p: open(os.path.join(p["klon"], "a.txt"), "rb").read()
        self.einrichten(1)
        p = platz.plaetze(self.con, self.pid)[0]
        platz.vorbereiten(p, self.repo, "paket-7")                                          # neuer Klon: gleich wie das Projekt
        self.assertEqual((roh(p), g(p["klon"], "config", "--local", "core.autocrlf")), (b"a\n", "false"))
        g(p["klon"], "config", "--unset", "core.autocrlf")                                  # Klon wie vor A1911
        os.remove(os.path.join(p["klon"], "a.txt"))
        g(p["klon"], "checkout", "--", "a.txt")
        self.assertEqual(roh(p), b"a\r\n")
        platz.vorbereiten(p, self.repo, "paket-8")                                          # nächstes Paket: angeglichen
        self.assertEqual((roh(p), g(p["klon"], "config", "--local", "core.autocrlf")), (b"a\n", "false"))
        self.assertTrue(platz.sauber(p))
        with open(os.path.join(p["klon"], "a.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write("a\n")                                                                  # gleicher Inhalt neu geschrieben
        arbeiter = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)  # git wie beim Arbeiter
        r = subprocess.run(["git", "-C", p["klon"], "diff", "--quiet", "HEAD"], env=arbeiter, capture_output=True, creationflags=OHNE)
        self.assertEqual(r.returncode, 0)
        self.assertFalse(platz.zeilenenden_angleichen(p["klon"], self.repo))                # schon gleich: nichts neu geschrieben


if __name__ == "__main__":
    unittest.main()
