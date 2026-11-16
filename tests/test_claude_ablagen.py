r"""Claude-Ablagen (A1779, 15.11.: ein Scratchpad mit 64 GB Arbeitskopien, C: fast voll): Sitzungsordner unter %TEMP%\claude
messen, über die Sitzungs-ID Projekt/Agent zuordnen, ab 10 GB einmal melden, alte Arbeitskopien mit Befehl vorschlagen –
die AMW löscht nichts."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime
import os
import tempfile
import unittest
from unittest import mock

from amw import db, kern, platte, workbench


class ClaudeAblagen(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"LOCALAPPDATA": os.path.join(self.ordner.name, "lad")})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        aid = kern.agent_neu(self.con, self.pid, "CC1")
        aid = self.con.execute("SELECT id FROM agent WHERE kennung = 'CC1'").fetchone()[0]
        with db.schreiben(self.con):
            db.einfuegen(self.con, "sitzung", agent_id=aid, claude_sitzung="aaaa-1111", gestartet_utc=db.jetzt())
        self.basis = os.path.join(self.ordner.name, "claude")
        sitz = os.path.join(self.basis, "h1", "aaaa-1111", "scratchpad")
        self.kopie = os.path.join(sitz, "arbeitskopie")
        os.makedirs(os.path.join(self.kopie, ".git"))
        with open(os.path.join(self.kopie, "gross.bin"), "wb") as f:
            f.write(b"x" * (2 * 2 ** 20))
        alt = (datetime.datetime.now() - datetime.timedelta(days=3)).timestamp()
        for w, _, ds in os.walk(self.kopie):
            for d in ds:
                os.utime(os.path.join(w, d), (alt, alt))
        os.makedirs(os.path.join(self.basis, "h2", "bbbb-2222"))
        with open(os.path.join(self.basis, "h2", "bbbb-2222", "klein.txt"), "w") as f:
            f.write("x")

    def test_messen_zuordnen_vorschlagen(self):
        e = platte.claude_messen(self.con, self.basis)
        s = e["sitzungen"][0]
        self.assertEqual((s["sitzung"], s["agent"], s["projekt"]), ("aaaa-1111", "CC1", "Spiel"))
        self.assertEqual(len(s["arbeitskopien"]), 1)
        k = s["arbeitskopien"][0]
        self.assertEqual(k["ordner"], self.kopie)
        self.assertGreaterEqual(k["tage"], 2)
        self.assertTrue(k["befehl"].startswith("Remove-Item -LiteralPath '"))
        self.assertNotIn("agent", e["sitzungen"][1])                                 # ohne Zuordnung
        self.assertTrue(os.path.exists(self.kopie))                                  # nichts gelöscht
        self.assertEqual(platte.claude_ablagen()["sitzungen"][0]["sitzung"], "aaaa-1111")
        d = workbench.daten_einstellungen(self.con, self.pid)
        self.assertEqual(d["rechner"]["claude"]["sitzungen"][0]["agent"], "CC1")

    def test_ab_grenze_einmal_an_lead_und_mensch(self):
        with mock.patch.object(platte, "CLAUDE_GRENZE_GB", 0.001):
            platte.claude_messen(self.con, self.basis)
            platte.claude_messen(self.con, self.basis)
        an = [r[0] for r in self.con.execute("SELECT e.agent FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id"
                                             " WHERE n.kurz LIKE 'Claude-Ablage von CC1 (Spiel)%'")]
        self.assertEqual(sorted(an), sorted(["TL", kern.ENTWICKLER]))

    def test_gemergter_worktree_raeumt_der_agent_selbst(self):
        """A1825 (G14-Ausnahme): ein Worktree ohne offene Änderungen, dessen Stand im Hauptzweig steckt, wird dem Agenten der
        Sitzung vorgeschlagen (git worktree remove + prune), einmal; ein nicht gemergter bleibt beim Menschen (Remove-Item)."""
        import shutil
        import subprocess
        if not shutil.which("git"):
            self.skipTest("git fehlt")
        repo = os.path.join(self.ordner.name, "repo")
        g = lambda *a, cwd=repo: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=cwd, check=True,
                                                capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        os.makedirs(repo)
        g("init", "-q", "-b", "main")
        with open(os.path.join(repo, "a.txt"), "w") as f:
            f.write("a")
        g("add", "a.txt")
        g("commit", "-q", "-m", "a")
        sitz = os.path.join(self.basis, "h1", "aaaa-1111", "scratchpad")
        fertig, offen = os.path.join(sitz, "wt-fertig"), os.path.join(sitz, "wt-offen")
        g("worktree", "add", "-q", "-b", "fertig", fertig)
        g("worktree", "add", "-q", "-b", "offen", offen)
        for wt in (fertig, offen):
            with open(os.path.join(wt, "gross.bin"), "wb") as f:
                f.write(os.path.basename(wt).encode() * (2 ** 20 // 4))     # verschieden: sonst gleicher Commit
            g("add", "gross.bin", cwd=wt)
            g("commit", "-q", "-m", "gross", cwd=wt)
        g("merge", "-q", "fertig")                                                   # nur „fertig“ ist gemergt
        alt = (datetime.datetime.now() - datetime.timedelta(days=3)).timestamp()
        for wt in (fertig, offen):
            for w, ds, fs in os.walk(wt):
                for x in ds + fs:
                    os.utime(os.path.join(w, x), (alt, alt))
        platte.claude_messen(self.con, self.basis)
        kopien = {k["ordner"]: k for k in platte.claude_ablagen()["sitzungen"][0]["arbeitskopien"]}
        self.assertEqual((kopien[fertig]["selbst"], kopien[fertig]["zweig"]), ("CC1", "fertig"))
        self.assertIn("worktree remove", kopien[fertig]["befehl"])
        self.assertIn("worktree prune", kopien[fertig]["befehl"])
        self.assertNotIn("selbst", kopien[offen])
        self.assertTrue(kopien[offen]["befehl"].startswith("Remove-Item"))
        platte.claude_messen(self.con, self.basis)                                    # zweite Messung: keine zweite Meldung
        an = [r[0] for r in self.con.execute("SELECT e.agent FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id"
                                             " WHERE n.kurz LIKE 'Deine Arbeitskopie%'")]
        self.assertEqual(an, ["CC1"])
        self.assertTrue(os.path.isdir(fertig))                                        # die AMW selbst löscht nichts

    def test_befehl_mit_hochkomma(self):
        self.assertEqual(platte.befehl_entfernen("C:\a'b"), "Remove-Item -LiteralPath 'C:\a''b' -Recurse -Force")


if __name__ == "__main__":
    unittest.main()
