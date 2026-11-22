"""A1929 (TH158 Ebene 2, W2453): tägliche Sicherung aller Zweige und Tags an sicherung_ziel – nur der Mensch setzt das Ziel,
keine Zugangsdaten, höchstens ein Versuch je Tag und nur bei geänderten Refs, nie --force/--prune/--mirror (am Ziel wird nichts
überschrieben oder gelöscht), Ereignis und Meldung; `amw sicherung jetzt`. Wegwerf-Repo und Bare-Repo als Ziel."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from amw import cli, db, kern, sicherung

OHNE = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def g(ordner, *a):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", ordner, *a], check=True, capture_output=True,
                          text=True, creationflags=OHNE).stdout.strip()


class Sicherung(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        o = self.ordner.name
        self.pfad = os.path.join(o, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad, "LOCALAPPDATA": os.path.join(o, "lad")})
        u.start()
        self.addCleanup(u.stop)
        for k in ("AMW_AGENT", "AMW_PROJEKT"):
            os.environ.pop(k, None)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.repo = os.path.join(o, "projekt")
        os.makedirs(self.repo)
        g(o, "init", "-q", "-b", "main", self.repo)
        self.commit("a")
        g(self.repo, "branch", "a1")
        g(self.repo, "tag", "v1.0.0")
        kern.projekt_ordner_setzen(self.con, self.pid, self.repo)
        self.ziel = os.path.join(o, "ziel.git")
        g(o, "init", "-q", "--bare", self.ziel)
        g(self.repo, "remote", "add", "sicherung", self.ziel)                                        # Ziel als Remote-Name (git unter
        self.url = "sicherung"                                                                       # Windows mag file:///C:/ nicht)
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, sicherung_ziel=self.url)

    def commit(self, text, datei="x.txt"):
        with open(os.path.join(self.repo, datei), "w") as f:
            f.write(text)
        g(self.repo, "add", "-A")
        g(self.repo, "commit", "-q", "-m", text)
        return g(self.repo, "rev-parse", "HEAD")

    def refs_am_ziel(self):
        return dict(reversed(z.split(" ", 1)) for z in g(self.ziel, "for-each-ref", "--format=%(objectname) %(refname)").splitlines())

    def test_ziel_pruefen(self):
        for gut in ("https://github.com/konto/AMW-Backup.git", "git@github.com:konto/AMW-Backup.git", "ssh://git@github.com/k/r.git",
                    "sicherung", ""):
            sicherung.ziel_pruefen(gut)
        for schlecht in ("https://konto:geheimtoken@github.com/k/r.git", "https://ghp_x@github.com/k/r.git", "C:\\ein pfad", "a b"):
            with self.assertRaises(ValueError, msg=schlecht):
                sicherung.ziel_pruefen(schlecht)

    def test_lead_oder_mensch_setzt_das_ziel(self):
        with self.assertRaisesRegex(kern.AmwFehler, "nur Lead und Entwickler"):                  # A1951: kein Coder
            kern.projekt_einstellen(self.con, self.pid, "CC1", sicherung_ziel="https://github.com/k/r.git")
        with self.assertRaisesRegex(kern.AmwFehler, "keine Zugangsdaten"):
            kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, sicherung_ziel="https://u:p@github.com/k/r.git")
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_AGENT": "", "CLAUDECODE": "1", "CLAUDE_CODE_MESSAGING_SOCKET": ""}), \
                contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "Spiel", "--von", "Entwickler", "projekt", "einstellen", "sicherung_ziel=https://github.com/k/r.git"])
        self.assertNotEqual(rc, 0)
        self.assertEqual(sicherung.ziel(self.con, self.pid), self.url)

    def test_taeglich_und_nur_bei_aenderung(self):
        aus = sicherung.runde(self.con, heute="2026-11-22")
        self.assertEqual(len(aus), 1)
        r = self.refs_am_ziel()
        self.assertEqual(set(r), {"refs/heads/main", "refs/heads/a1", "refs/tags/v1.0.0"})            # alle Zweige und Tags
        e = sicherung.letzte(self.con, self.pid)
        self.assertEqual((e["rc"], e["refs"], e["abgewiesen"]), (0, 3, []))
        self.assertNotIn("@", e["ziel"].split("//")[0])
        self.assertEqual(sicherung.runde(self.con, heute=sicherung._lokaler_tag(e["zeit_utc"])), [])   # am selben Tag nicht noch einmal
        self.assertEqual(sicherung.runde(self.con, heute="2099-01-01"), [])                             # nichts geändert
        neu = self.commit("b")
        self.assertEqual(len(sicherung.runde(self.con, heute="2099-01-01")), 1)
        self.assertEqual(self.refs_am_ziel()["refs/heads/main"], neu)

    def test_nie_ueberschreiben_nie_loeschen(self):
        sicherung.pushen(self.con, self.pid)
        alt = self.refs_am_ziel()["refs/heads/a1"]
        g(self.repo, "checkout", "-q", "--orphan", "neu")                                             # a1 lokal neu aufgesetzt
        self.commit("anders", "y.txt")
        g(self.repo, "branch", "-f", "a1", "neu")
        g(self.repo, "checkout", "-q", "main")
        g(self.repo, "branch", "-D", "neu")
        g(self.repo, "branch", "-c", "main", "a2")                                                   # ein neuer Zweig geht mit
        e = sicherung.pushen(self.con, self.pid)
        self.assertNotEqual(e["rc"], 0)
        self.assertEqual(e["abgewiesen"], ["refs/heads/a1"])
        r = self.refs_am_ziel()
        self.assertEqual(r["refs/heads/a1"], alt)                                                     # nicht überschrieben
        self.assertIn("refs/heads/a2", r)
        m = self.con.execute("SELECT n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = 'TL'"
                             " AND n.kurz LIKE 'Sicherung nach%'").fetchone()
        self.assertIn("refs/heads/a1", m["text"])
        g(self.repo, "branch", "-D", "a2")                                                            # lokal gelöscht …
        sicherung.pushen(self.con, self.pid)
        self.assertIn("refs/heads/a2", self.refs_am_ziel())                                          # … am Ziel bleibt er

    def test_ohne_ziel_nichts(self):
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, sicherung_ziel="")
        self.assertEqual(sicherung.runde(self.con, heute="2026-11-22"), [])
        self.assertEqual(self.refs_am_ziel(), {})

    def test_jetzt_lead_oder_mensch(self):
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}), \
                contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            self.assertNotEqual(cli.main(["--projekt", "Spiel", "--von", "CC1", "sicherung", "jetzt"]), 0)
            self.assertEqual(cli.main(["--projekt", "Spiel", "--von", "TL", "sicherung", "jetzt"]), 0)
        self.assertIn("3 Refs, rc 0", aus.getvalue())
        self.assertEqual(len(self.refs_am_ziel()), 3)


    # --- P408 (Betriebssicherheit im Dienst) -----------------------------------------------------------------------------
    def test_p408_1_nie_eine_anmeldeabfrage(self):
        u = sicherung.umgebung()
        self.assertEqual((u["GIT_TERMINAL_PROMPT"], u["GCM_INTERACTIVE"]), ("0", "never"))
        self.assertIn("BatchMode=yes", u["GIT_SSH_COMMAND"])
        gesehen = []
        echt = subprocess.run

        def lauf(befehl, **kw):
            gesehen.append(kw.get("env") or {})
            return echt(befehl, **kw)
        with mock.patch.object(sicherung.subprocess, "run", side_effect=lauf):
            sicherung.pushen(self.con, self.pid)
        self.assertTrue(gesehen and all(e.get("GIT_TERMINAL_PROMPT") == "0" and e.get("GCM_INTERACTIVE") == "never" for e in gesehen))
        echte_git = sicherung._git

        def ohne_anmeldung(ordner, *a, **k):
            if a and a[0] == "push":
                return 128, "fatal: could not read Username for 'https://github.com': terminal prompts disabled"
            return echte_git(ordner, *a, **k)
        with mock.patch.object(sicherung, "_git", side_effect=ohne_anmeldung):
            e = sicherung.pushen(self.con, self.pid)
        self.assertEqual(e["fehler"], "anmeldung")
        m = self.con.execute("SELECT n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = 'Entwickler'"
                             " AND n.kurz LIKE '%Anmeldung fehlt'").fetchone()
        self.assertIn("einmal im eigenen Terminal", m[0])
        self.assertEqual(sicherung.runde(self.con, heute="2099-01-01")[0][-4:], "rc 0")             # am nächsten Tag wieder versucht

    def test_p408_2_dienst_wartet_nicht(self):
        import threading
        los, gestartet = threading.Event(), threading.Event()

        def warten():
            gestartet.set()
            los.wait(10)
        self.assertTrue(sicherung.im_hintergrund(self.pfad, warten=warten))
        self.assertTrue(gestartet.wait(10))                                                            # läuft, die Runde ist schon zurück
        self.assertFalse(sicherung.im_hintergrund(self.pfad))                                         # höchstens einer zur Zeit
        los.set()
        sicherung._FADEN["faden"].join(30)
        self.assertEqual(len(self.refs_am_ziel()), 3)                                                 # mit eigener Verbindung gerechnet
        self.assertTrue(sicherung.im_hintergrund(self.pfad))
        sicherung._FADEN["faden"].join(30)

    def test_p408_3_abgewiesen_nur_einmal(self):
        sicherung.pushen(self.con, self.pid)
        g(self.repo, "checkout", "-q", "--orphan", "neu")
        self.commit("anders", "y.txt")
        g(self.repo, "branch", "-f", "a1", "neu")
        g(self.repo, "checkout", "-q", "main")
        g(self.repo, "branch", "-D", "neu")
        meldungen = lambda: self.con.execute("SELECT count(*) FROM nachricht WHERE kurz LIKE '%nicht vorspulbar'").fetchone()[0]
        e = sicherung.pushen(self.con, self.pid)
        self.assertEqual((e["abgewiesen"], e["fehler"], meldungen()), (["refs/heads/a1"], None, 1))
        self.assertEqual(sicherung.runde(self.con, heute="2099-01-01"), [])                         # nur Bekanntes, nichts geändert
        sicherung.pushen(self.con, self.pid)
        self.assertEqual(meldungen(), 1)                                                              # nicht noch einmal
        g(self.repo, "checkout", "-q", "--orphan", "neu2")
        self.commit("auch anders", "z.txt")
        g(self.repo, "branch", "-f", "main", "neu2")
        g(self.repo, "checkout", "-q", "main")
        g(self.repo, "branch", "-D", "neu2")
        e = sicherung.pushen(self.con, self.pid)
        self.assertEqual((sorted(e["abgewiesen"]), meldungen()), (["refs/heads/a1", "refs/heads/main"], 2))
        m = self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE '%nicht vorspulbar' ORDER BY id DESC LIMIT 1").fetchone()[0]
        self.assertIn("refs/heads/main", m)
        self.assertNotIn("refs/heads/a1", m)                                                          # nur der neue

if __name__ == "__main__":
    unittest.main()
