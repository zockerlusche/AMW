"""A2103: ein Versions-Commit, der mehr als CHANGELOG, Versionsdatei und web/inc/VERSION ändert, fällt schon bei der Prüfbitte und vor dem
Gesamtlauf auf – nicht erst in der Release-Kette nach dem Gesamtlauf (25.11., 1.193.0). Eine Stelle: Kette.versions_commits."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import sys
from unittest import mock

from amw import auslieferung, cli, kern
from tests import test_a2054_nur_riskantes

GUT = {"CHANGELOG.md": "## 1.0.1\n", "amw/__init__.py": "__version__ = '1.0.1'\n", "web/inc/VERSION": "1.0.1\n"}
SCHLECHT = {**GUT, "web/inc/seite.html": "<html></html>\n"}
SUITE = "python -m unittest discover -s tests"
GRUND = r"Versions-Commit \w{8} ändert mehr als CHANGELOG.md, amw/__init__.py, web/inc/VERSION: web/inc/seite.html"


class Grund(test_a2054_nur_riskantes.Grund):
    def setUp(self):
        super().setUp()
        kern.projekt_ordner_setzen(self.con, self.pid, self.repo)
        kern.projekt_einstellen(self.con, self.pid, "TL", gesamtlauf_befehl=SUITE)
        self.schlecht = self.zweig("schlecht", SCHLECHT)
        self.gut = self.zweig("gut", GUT)
        self.ohne = self.zweig("ohne", {"lib/neu.py": "X = 1\n", "web/inc/seite.html": "<html>2</html>\n"})

    def anzahl(self, tabelle):
        return self.con.execute(f"SELECT count(*) FROM {tabelle}").fetchone()[0]

    def amw(self, *a):
        """Wie im Terminal: rc und Ausgabe (ein AmwFehler steht als „FEHLER: …“ da)."""
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main([*a[:2], "--von", "CC1", *a[2:]])
        return rc, aus.getvalue()


class Pruefbitte(Grund):
    def bitte(self, zweig, sha):
        return self.amw("pruefung", "bitte", "--pruefer", "TL", "--zweig", zweig, "--sha", sha, "--punkte", "x", "--ohne-bild", "nichts Sichtbares")

    def test_abbruch_mit_genau_dem_grund(self):
        rc, aus = self.bitte("schlecht", self.schlecht)
        self.assertNotEqual(rc, 0)
        self.assertRegex(aus, GRUND)
        self.assertEqual(self.anzahl("pruefung"), 0)

    def test_derselbe_satz_wie_in_der_kette(self):
        k = auslieferung.Kette(self.con, self.pid, "TL", self.repo, ausgabe=lambda _: None)
        satz = k.versions_commits(self.schlecht, k.release_art())
        self.assertEqual(len(satz), 1)
        self.assertEqual(auslieferung.versions_fehler(self.con, self.pid, self.repo, self.schlecht), satz)
        self.assertIn(satz[0], self.bitte("schlecht", self.schlecht)[1])

    def test_nur_die_drei_dateien_und_ohne_versions_commit_gehen(self):
        for zweig, sha in (("gut", self.gut), ("ohne", self.ohne)):
            with self.subTest(zweig=zweig):
                rc, aus = self.bitte(zweig, sha)
                self.assertEqual(rc, 0, aus)
        self.assertEqual(self.anzahl("pruefung"), 2)

    def test_ohne_ordner_oder_main_bleibt_es_wie_bisher(self):
        self.assertEqual(auslieferung.versions_fehler(self.con, self.pid, None, self.schlecht), [])
        self.assertEqual(auslieferung.versions_fehler(self.con, self.pid, self.ordner.name, self.schlecht), [])      # kein Git-Ordner
        self.git("branch", "-m", "main", "anders")
        self.assertEqual(auslieferung.versions_fehler(self.con, self.pid, self.repo, self.schlecht), [])


class Gesamtlauf(Grund):
    def setUp(self):
        super().setUp()
        alt = os.getcwd()
        self.addCleanup(os.chdir, alt)
        os.chdir(self.repo)
        for wo in ("schlecht", "gut", "ohne"):
            p = os.path.join(self.ordner.name, "baum-" + wo)                                # wie die Entwicklungsbäume: eigene Worktrees
            self.git("worktree", "add", "-q", p, wo)
        self.addCleanup(os.chdir, alt)

    def lauf(self, baum, *mehr, befehl=(SUITE,), aktion="ausfuehren"):
        os.chdir(os.path.join(self.ordner.name, "baum-" + baum))
        ende = ("--", *befehl) if aktion == "ausfuehren" else ()
        try:
            with mock.patch("amw.cli._lauf_warte", return_value=1):                         # nie wirklich rechnen: nur angemeldet
                return self.amw("lauf", aktion, "--leicht", "--beschreibung", "Gesamtlauf " + baum, *mehr, *ende)
        finally:
            os.chdir(self.repo)

    def test_startet_nicht(self):
        rc, aus = self.lauf("schlecht")
        self.assertNotEqual(rc, 0)
        self.assertRegex(aus, "Gesamtlauf nicht gestartet.*" + GRUND)
        self.assertIn("--trotzdem", aus)
        self.assertEqual(self.anzahl("lauf"), 0)

    def test_auch_von_hand_angemeldet(self):
        rc, aus = self.lauf("schlecht", aktion="start")
        self.assertNotEqual(rc, 0)
        self.assertRegex(aus, GRUND)
        self.assertEqual(self.anzahl("lauf"), 0)

    def test_trotzdem_mit_grund_steht_am_lauf(self):
        self.lauf("schlecht", "--trotzdem", "nur messen")
        self.assertEqual([r[0] for r in self.con.execute("SELECT beschreibung FROM lauf")], ["Gesamtlauf schlecht (trotzdem: nur messen)"])
        _, aus = self.lauf("schlecht", "--trotzdem", "  ")                                 # ohne Grund gilt es nicht
        self.assertRegex(aus, GRUND)
        self.assertEqual(self.anzahl("lauf"), 1)

    def test_gute_staende_und_andere_laeufe_bleiben_unberuehrt(self):
        self.lauf("gut", "--trotzdem", "unnötig")
        self.lauf("ohne")
        self.lauf("schlecht", befehl=(sys.executable, "-c", "pass"))                        # kein Gesamtlauf
        self.assertEqual([r[0] for r in self.con.execute("SELECT beschreibung FROM lauf ORDER BY id")], ["Gesamtlauf gut", "Gesamtlauf ohne", "Gesamtlauf schlecht"])

    def test_der_stand_des_befehls_zaehlt_nicht_der_ordner(self):
        ziel = os.path.join(self.ordner.name, "baum-schlecht")
        _, aus = self.lauf("gut", befehl=(f'cd /d "{ziel}" && {SUITE}',))
        self.assertRegex(aus, GRUND)
        self.assertEqual(self.anzahl("lauf"), 0)
