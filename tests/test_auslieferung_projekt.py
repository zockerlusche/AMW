"""A1933 (Mehrprojekt 9): `release ausliefern` für ein Projekt, das nicht die AMW ist – Prüfungen und Merge-OK wie bisher,
Projektordner auf main und sauber, Sicherung nur mit release_sicherung = an, Fast-Forward, Tag (Nummer nach release_modus),
Push und Release-Notiz nach veroeffentlichen; Dienst, Schema, Versionszeile und Web-Abzug entfallen. Nur der Lead des
Projekts oder der Mensch (ein Tag kann im Projekt Workflows starten). Wegwerf-Projekt mit eigenem origin."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
from unittest import mock

from amw import auslieferung, betrieb, buendel, cli, kern, veroeffentlichung
from amw.auslieferung import _laufen
from tests.test_buendel import Basis
from tests.test_mergeliste import g, schreiben

KOPF = "# Changelog\n\n"
ALT = "## [1.4.2] - 2026-10-01\n\n### Added\n- Alt.\n"


class Projekt(Basis):
    def setUp(self):
        super().setUp()
        schreiben(self.repo, "CHANGELOG.md", KOPF + "## [Unreleased]\n\n" + ALT)
        g(self.repo, "add", "-A")
        g(self.repo, "commit", "-q", "-m", "changelog")
        g(self.repo, "tag", "v1.4.2")
        self.fern = os.path.join(self.ordner.name, "fern.git")
        g(self.ordner.name, "init", "-q", "--bare", self.fern)
        g(self.repo, "remote", "add", "origin", self.fern)
        g(self.repo, "push", "-q", "origin", "main", "v1.4.2")
        for k, v in (("release_modus", "tag"), ("changelog_format", "keepachangelog"), ("version_datei", "")):
            kern.projekt_einstellen(self.con, self.pid, "TL", **{k: v})
        self.befehle = []
        self.a = self.paket("plus", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"}, 1, hinweis="Plus stimmt.", gruppe="behoben")
        buendel.buendeln(self.con, self.pid, "TL", starten=False)
        rc, self.lid = buendel.lauf_und_meldung(self.con, self.pid, "buendel-1.4.3", warte=lambda s: None)
        self.assertEqual(rc, 0)
        betrieb.freigabe_merge(self.con, self.pid, "TL", self.a, "buendel-1.4.3")

    def extern(self, befehl, ordner):
        self.befehle.append(befehl)
        if befehl[0] == "gh":
            return 0, "angelegt"
        return _laufen(befehl, ordner)

    def kette(self, von="TL"):
        return auslieferung.Kette(self.con, self.pid, von, self.repo, extern=self.extern, ausgabe=lambda _: None, amw=False,
                                  start_version=lambda: self.fail("Dienst gefragt"))

    def fern_tags(self):
        return sorted(g(self.fern, "tag", "--list").split())

    def test_meilenstein_lokal_ohne_dienst_und_web(self):
        sha = g(self.repo, "rev-parse", "buendel-1.4.3")
        r = self.kette().ausliefern("buendel-1.4.3", gesamtlauf=self.lid)
        self.assertEqual((r["version"], r["sha"], r["web_lauf"], r["release"]), ("1.4.3", sha, None, None))
        self.assertEqual(g(self.repo, "rev-parse", "main"), sha)                                       # Fast-Forward
        self.assertIn("v1.4.3", g(self.repo, "tag", "--list").split())
        self.assertEqual(self.fern_tags(), ["v1.4.2"])                                                 # noch nicht gepusht
        self.assertFalse(any("dienst" in " ".join(b) or b[0] == "gh" for b in self.befehle), self.befehle)
        self.assertIsNone(self.con.execute("SELECT 1 FROM release WHERE projekt_id = ?", (self.pid,)).fetchone())   # keine Versionszeile
        self.assertTrue(self.con.execute("SELECT 1 FROM plan_ereignis WHERE art = ? AND projekt_id = ?",
                                         (veroeffentlichung.LOKAL, self.pid)).fetchone())
        self.assertEqual(self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (self.a,)).fetchone()[0], "fertig")

    def test_sofort_push_und_release_notiz(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", veroeffentlichen="sofort")
        sha = self.kette().ausliefern("buendel-1.4.3", gesamtlauf=self.lid)["sha"]
        self.assertEqual(self.fern_tags(), ["v1.4.2", "v1.4.3"])
        self.assertEqual(g(self.fern, "rev-parse", "main"), sha)
        gh = [b for b in self.befehle if b[0] == "gh"]
        self.assertEqual(gh[0][:4], ["gh", "release", "create", "v1.4.3"])

    def test_nur_lead_oder_mensch(self):
        main = g(self.repo, "rev-parse", "main")
        with self.assertRaisesRegex(auslieferung.Stopp, "Stopp bei „Wer liefert aus“.*nicht CC1.*erledigt: noch nichts"):
            self.kette("CC1").ausliefern("buendel-1.4.3", gesamtlauf=self.lid)
        self.assertEqual((g(self.repo, "rev-parse", "main"), g(self.repo, "tag", "--list").split()), (main, ["v1.4.2"]))

    def test_projektordner_muss_main_und_sauber_sein(self):
        main = g(self.repo, "rev-parse", "main")
        schreiben(self.repo, "lib/rechnen.py", "halb fertig\n")                                      # ungesicherte Änderung
        with self.assertRaisesRegex(auslieferung.Stopp, "Stopp bei „Arbeitsbaum“.*ungesicherte Änderungen"):   # wie bei der AMW
            self.kette().ausliefern("buendel-1.4.3", gesamtlauf=self.lid)
        g(self.repo, "checkout", "-q", "--", "lib/rechnen.py")
        g(self.repo, "checkout", "-q", "-b", "nebenbei")
        with self.assertRaisesRegex(auslieferung.Stopp, "Stopp bei „Projektordner“: .* ist auf nebenbei .*erledigt: noch nichts"):
            self.kette().ausliefern("buendel-1.4.3", gesamtlauf=self.lid)
        self.assertEqual(g(self.repo, "rev-parse", "main"), main)

    def test_sicherung_nur_wenn_eingestellt(self):
        k = self.kette()
        k.ausliefern("buendel-1.4.3", gesamtlauf=self.lid)
        self.assertFalse(any(s.startswith("Sicherung") for s in k.erledigt), k.erledigt)
        g(self.repo, "tag", "-d", "v1.4.3")
        g(self.repo, "reset", "-q", "--hard", "v1.4.2")
        kern.projekt_einstellen(self.con, self.pid, "TL", release_sicherung="an")
        k = self.kette()
        k.ausliefern("buendel-1.4.3", gesamtlauf=self.lid)
        self.assertTrue(any(s.startswith("Sicherung") for s in k.erledigt), k.erledigt)

    def test_notizen_aus_dem_changelog_des_projekts(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", veroeffentlichen="sofort")
        self.kette().ausliefern("buendel-1.4.3", gesamtlauf=self.lid)
        neu, text = veroeffentlichung.notizen(self.repo, ["1.4.3"], changelog="CHANGELOG.md")
        self.assertEqual(neu, "1.4.3")
        self.assertIn("## [1.4.3] - ", text)
        self.assertIn("### Fixed\n- Plus stimmt.", text)

    def test_cli_nur_aus_dem_eigenen_terminal(self):
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_AGENT": "", "CLAUDECODE": "1", "CLAUDE_CODE_MESSAGING_SOCKET": ""}), \
                contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "Spiel", "--von", "Entwickler", "release", "ausliefern", "--zweig", "buendel-1.4.3",
                           "--gesamtlauf", f"L{self.lid}"])
        self.assertNotEqual(rc, 0)
        self.assertIn("nicht aus einer Agenten-Sitzung", aus.getvalue())
        self.assertEqual(g(self.repo, "tag", "--list").split(), ["v1.4.2"])


if __name__ == "__main__":
    import unittest
    unittest.main()
