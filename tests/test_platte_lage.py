"""Probe T5 (D1298): platte.meldetext – der Text der Platten-Meldung – und platte.worktree_lage – wann eine Arbeitskopie ein
gemergter, sauberer Worktree ist, den der Agent selbst entfernen darf. Wegwerf-Repos im Temp-Ordner; die AMW führt nichts aus."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import shutil
import subprocess
import tempfile
import unittest

from amw import platte

MIB, GIB = 2 ** 20, 2 ** 30
SCHLUSS = " Die AMW löscht nichts; aufräumen kann nur der Mensch."


def lw(stufe, frei_gb=12.5, frei_prozent=6.3, gesamt_gb=198.4):
    return {"laufwerk": "F:", "frei_gb": frei_gb, "frei_prozent": frei_prozent, "gesamt_gb": gesamt_gb, "stufe": stufe}


class Meldetext(unittest.TestCase):
    def test_gelb_ohne_vorschlag(self):
        self.assertEqual(platte.meldetext(lw("gelb")),
                         "Laufwerk F: wird knapp: noch 12,5 GB frei (6,3 % von 198,4 GB)." + SCHLUSS)

    def test_rot_mit_warnung(self):
        text = platte.meldetext(lw("rot", 3.0, 1.5, 200.0))
        self.assertEqual(text, "Laufwerk F: wird knapp: noch 3,0 GB frei (1,5 % von 200,0 GB)."
                               " Schwere Läufe und Sicherungen können daran scheitern." + SCHLUSS)

    def test_gelb_ohne_warnung(self):
        self.assertNotIn("Schwere Läufe", platte.meldetext(lw("gelb")))

    def test_zahlen_mit_komma(self):
        text = platte.meldetext(lw("gelb", 0.7, 0.4, 1863.0), 1.5 * GIB)
        self.assertIn("noch 0,7 GB frei (0,4 % von 1863,0 GB)", text)
        self.assertIn("Alte Sicherungen belegen 1,5 GB", text)
        self.assertNotRegex(text, r"\d\.\d")                         # nirgends ein Dezimalpunkt

    def test_vorschlag_unter_einem_mib_fehlt(self):
        for b in (0, 1, MIB - 1):
            with self.subTest(bytes=b):
                text = platte.meldetext(lw("gelb"), b)
                self.assertNotIn("Alte Sicherungen", text)
                self.assertEqual(text, platte.meldetext(lw("gelb")))

    def test_vorschlag_ab_einem_mib(self):
        self.assertIn(" Alte Sicherungen belegen 0,0 GB – Vorschläge zeigt `amw rechner`.", platte.meldetext(lw("gelb"), MIB))
        text = platte.meldetext(lw("rot"), 3 * GIB + GIB // 4)
        self.assertIn("Schwere Läufe und Sicherungen können daran scheitern. Alte Sicherungen belegen 3,2 GB"
                      " – Vorschläge zeigt `amw rechner`." + SCHLUSS, text)
        self.assertTrue(text.endswith("`amw rechner`." + SCHLUSS))

    def test_schlusssatz_immer_am_ende(self):
        for stufe in ("gelb", "rot"):
            for b in (0, 5 * GIB):
                with self.subTest(stufe=stufe, bytes=b):
                    text = platte.meldetext(lw(stufe), b)
                    self.assertTrue(text.endswith(SCHLUSS))
                    self.assertEqual(text.count("Die AMW löscht nichts"), 1)


@unittest.skipUnless(shutil.which("git"), "git fehlt")
class WorktreeLage(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.repo = self.neues_repo("repo", "main")

    def git(self, *a, cwd):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false", *a], cwd=cwd,
                              check=True, capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def neues_repo(self, name, zweig):
        repo = os.path.join(self.ordner.name, name)
        os.makedirs(repo)
        self.git("init", "-q", "-b", zweig, cwd=repo)
        self.schreiben(repo, "a.txt", "a")
        self.git("add", "a.txt", cwd=repo)
        self.git("commit", "-q", "-m", "a", cwd=repo)
        return repo

    def schreiben(self, ordner, name, inhalt):
        with open(os.path.join(ordner, name), "w", encoding="utf-8") as f:
            f.write(inhalt)

    def worktree(self, name, zweig, repo=None, commit=True):
        repo = repo or self.repo
        wt = os.path.join(self.ordner.name, "wts", name)
        self.git("worktree", "add", "-q", "-b", zweig, wt, cwd=repo)
        if commit:
            self.schreiben(wt, f"{zweig}.txt", zweig)
            self.git("add", f"{zweig}.txt", cwd=wt)
            self.git("commit", "-q", "-m", zweig, cwd=wt)
        return wt

    def pruefe_treffer(self, w, wt, zweig, repo=None):
        repo = repo or self.repo
        self.assertEqual(set(w), {"haupt", "zweig", "befehl"})
        self.assertTrue(os.path.samefile(w["haupt"], repo))
        self.assertEqual(w["zweig"], zweig)
        q = lambda x: "'" + x.replace("'", "''") + "'"
        self.assertEqual(w["befehl"], f"git -C {q(w['haupt'])} worktree remove {q(wt)}; git -C {q(w['haupt'])} worktree prune")

    def test_klon_mit_git_ordner(self):
        self.assertTrue(os.path.isdir(os.path.join(self.repo, ".git")))
        self.assertIsNone(platte.worktree_lage(self.repo))           # Hauptarbeitskopie: sauber und in main, aber kein Worktree
        klon = os.path.join(self.ordner.name, "klon")
        self.git("clone", "-q", self.repo, klon, cwd=self.ordner.name)
        self.assertIsNone(platte.worktree_lage(klon))

    def test_kein_repo(self):
        leer = os.path.join(self.ordner.name, "leer")
        os.makedirs(leer)
        self.assertIsNone(platte.worktree_lage(leer))
        self.assertIsNone(platte.worktree_lage(os.path.join(self.ordner.name, "gibt-es-nicht")))

    def test_offene_aenderungen(self):
        wt = self.worktree("wt-offen", "offen")
        self.git("merge", "-q", "offen", cwd=self.repo)
        self.assertIsNotNone(platte.worktree_lage(wt))                  # Gegenprobe: sauber und gemergt
        self.schreiben(wt, "offen.txt", "geändert")                     # geänderte Datei
        self.assertIsNone(platte.worktree_lage(wt))
        self.git("checkout", "--", "offen.txt", cwd=wt)
        self.schreiben(wt, "neu.txt", "neu")                            # neue, nicht verfolgte Datei
        self.assertIsNone(platte.worktree_lage(wt))
        self.git("add", "neu.txt", cwd=wt)                              # vorgemerkt, nicht committet
        self.assertIsNone(platte.worktree_lage(wt))

    def test_sauber_und_in_main(self):
        wt = self.worktree("wt-fertig", "fertig")
        self.git("merge", "-q", "fertig", cwd=self.repo)
        self.pruefe_treffer(platte.worktree_lage(wt), wt, "fertig")

    def test_ohne_eigene_commits_schon_in_main(self):
        wt = self.worktree("wt-leer", "leer", commit=False)
        self.pruefe_treffer(platte.worktree_lage(wt), wt, "leer")

    def test_hauptzweig_master(self):
        repo = self.neues_repo("alt", "master")
        wt = self.worktree("wt-alt", "alt-fertig", repo=repo)
        self.git("merge", "-q", "alt-fertig", cwd=repo)
        self.pruefe_treffer(platte.worktree_lage(wt), wt, "alt-fertig", repo=repo)

    def test_losgeloester_head(self):
        wt = os.path.join(self.ordner.name, "wts", "wt-los")
        self.git("worktree", "add", "-q", "--detach", wt, cwd=self.repo)
        self.pruefe_treffer(platte.worktree_lage(wt), wt, "HEAD")

    def test_apostroph_im_pfad(self):
        wt = self.worktree("wt-o'neil", "oneil")
        self.git("merge", "-q", "oneil", cwd=self.repo)
        w = platte.worktree_lage(wt)
        self.pruefe_treffer(w, wt, "oneil")
        self.assertIn("wt-o''neil'", w["befehl"])

    def test_stand_nicht_in_main(self):
        wt = self.worktree("wt-offen", "nicht-gemergt")
        self.assertIsNone(platte.worktree_lage(wt))
        self.schreiben(self.repo, "b.txt", "b")                          # main läuft weiter – der Zweig bleibt ungemergt
        self.git("add", "b.txt", cwd=self.repo)
        self.git("commit", "-q", "-m", "b", cwd=self.repo)
        self.assertIsNone(platte.worktree_lage(wt))

    def test_ohne_hauptzweig(self):
        repo = self.neues_repo("anders", "entwicklung")
        wt = self.worktree("wt-anders", "anders-fertig", repo=repo)
        self.git("merge", "-q", "anders-fertig", cwd=repo)
        self.assertIsNone(platte.worktree_lage(wt))                     # weder main noch master: keine Ausnahme

    def test_liest_nur(self):
        wt = self.worktree("wt-bleibt", "bleibt")
        self.git("merge", "-q", "bleibt", cwd=self.repo)
        self.assertIsNotNone(platte.worktree_lage(wt))
        self.assertTrue(os.path.isfile(os.path.join(wt, ".git")))
        liste = self.git("worktree", "list", "--porcelain", cwd=self.repo).stdout
        self.assertEqual(liste.count("worktree "), 2)                   # Worktree noch da, nichts entfernt


if __name__ == "__main__":
    unittest.main()
