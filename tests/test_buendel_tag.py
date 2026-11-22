"""A1923 (TH160 F2, Mehrprojekt 5): Release-Modus je Projekt – release_modus = datei | tag, changelog_format = amw |
keepachangelog. Bei tag: Nummer aus dem höchsten Tag vX.Y.Z, kein Versions-Commit an einer Datei, „## [Unreleased]“ →
„## [X.Y.Z] - JJJJ-MM-TT“; den Tag setzt das Bündel nie (das bleibt release ausliefern durch Lead bzw. Mensch)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime
import unittest

from amw import buendel, kern
from tests.test_buendel import Basis
from tests.test_mergeliste import g, schreiben

KOPF = "# Changelog\n\nAll notable changes.\n\n"
UNREL = "## [Unreleased]\n\n### Fixed\n- Von Hand eingetragen.\n\n"
ALT = "## [1.4.2] - 2026-10-01\n\n### Added\n- Alt.\n"


class Einzeln(unittest.TestCase):
    def test_version_aus_tags(self):
        self.assertEqual(buendel.version_aus_tags(["v1.4.2", "v1.10.0", "1.9.9", "probe", "v2.0.0-rc1", ""]), "1.10.0")
        self.assertEqual(buendel.version_aus_tags([]), "0.0.0")
        self.assertEqual(buendel.naechste_version(buendel.version_aus_tags([]), True), "0.1.0")

    def test_keep_a_changelog(self):
        p = [{"hinweis": "Neues Ding.", "hinweis_gruppe": "neu"}, {"hinweis": "Fehler weg.", "hinweis_gruppe": "behoben"},
             {"hinweis": None, "hinweis_gruppe": None}]
        t = buendel.kac_einfuegen(KOPF + UNREL + ALT, "1.5.0", "2026-11-22", p)
        self.assertEqual(t, KOPF + "## [Unreleased]\n\n## [1.5.0] - 2026-11-22\n\n### Added\n- Neues Ding.\n\n"
                                   "### Fixed\n- Von Hand eingetragen.\n- Fehler weg.\n\n" + ALT)
        ohne = buendel.kac_einfuegen(KOPF + ALT, "1.4.3", "2026-11-22", [{"hinweis": None, "hinweis_gruppe": None}])
        self.assertEqual(ohne, KOPF + "## [Unreleased]\n\n## [1.4.3] - 2026-11-22\n\n### Changed\n"
                                      "- Intern: 1 Paket(e) ohne sichtbare Änderung (Tests und Pflege).\n\n" + ALT)


class Tag(Basis):
    def setUp(self):
        super().setUp()
        schreiben(self.repo, "CHANGELOG.md", KOPF + UNREL + ALT)
        g(self.repo, "add", "-A")
        g(self.repo, "commit", "-q", "-m", "changelog")
        g(self.repo, "tag", "v1.4.2")
        for k, v in (("release_modus", "tag"), ("changelog_format", "keepachangelog"), ("version_datei", "")):
            kern.projekt_einstellen(self.con, self.pid, "TL", **{k: v})

    def test_nummer_aus_dem_tag_nur_changelog_kein_tag(self):
        self.paket("plus reparieren", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"}, 1, hinweis="Plus stimmt.", gruppe="neu")
        r = buendel.buendeln(self.con, self.pid, "TL", starten=False)
        self.assertEqual((r["version"], r["zweig"]), ("1.5.0", "buendel-1.5.0"))           # aus v1.4.2, nicht aus amw/__init__.py
        self.assertEqual(g(self.repo, "diff", "--name-only", f"{r['sha']}~1", r["sha"]).split(), ["CHANGELOG.md"])
        self.assertEqual(self.datei(r["sha"], "amw/__init__.py"), '__version__ = "1.2.3"')   # keine Versionsdatei angefasst
        log = self.datei(r["sha"], "CHANGELOG.md")
        heute = datetime.date.today().isoformat()
        self.assertTrue(log.startswith(KOPF + f"## [Unreleased]\n\n## [1.5.0] - {heute}\n\n### Added\n- Plus stimmt.\n\n"
                                              "### Fixed\n- Von Hand eingetragen.\n\n## [1.4.2]"), log[:300])
        self.assertEqual(g(self.repo, "tag", "--list").split(), ["v1.4.2"])                 # den Tag setzt das Bündel nie

    def test_hoechster_tag_zaehlt(self):
        g(self.repo, "tag", "v1.4.3")                                                        # z. B. von Hand gesetzt
        g(self.repo, "tag", "alt-1.9.0")                                                     # kein Versions-Tag
        self.paket("Tests", {"tests_plus.py": "x = 1\n"}, 1)
        r = buendel.buendeln(self.con, self.pid, "TL", starten=False)
        self.assertEqual(r["version"], "1.4.4")

    def test_meldung_mit_dem_abschnitt(self):
        self.paket("plus", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"}, 1, hinweis="Plus stimmt.", gruppe="behoben")
        buendel.buendeln(self.con, self.pid, "TL", starten=False)
        rc, lid = buendel.lauf_und_meldung(self.con, self.pid, "buendel-1.4.3", warte=lambda s: None)
        self.assertEqual(rc, 0)
        m = self.con.execute("SELECT n.text FROM nachricht n WHERE n.kurz LIKE 'Bündel 1.4.3 bereit%'").fetchone()
        self.assertIn("## [1.4.3] - ", m["text"])
        self.assertIn("### Fixed\n- Von Hand eingetragen.\n- Plus stimmt.", m["text"])

    def test_kette_liest_die_version_und_stoppt_vor_dem_ersten_schritt_nach_aussen(self):
        """#29877 (Zuschnitt A): die Kette liest Nummer und Notizen aus dem CHANGELOG; ausliefern stoppt klar, bis Mehrprojekt 9
        (A1933) die Kette für Projekte mit eigener Versionsquelle bringt – kein Tag, main unverändert."""
        from amw import auslieferung, betrieb
        a = self.paket("plus", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"}, 1, hinweis="Plus stimmt.", gruppe="behoben")
        buendel.buendeln(self.con, self.pid, "TL", starten=False)
        rc, lid = buendel.lauf_und_meldung(self.con, self.pid, "buendel-1.4.3", warte=lambda s: None)
        betrieb.freigabe_merge(self.con, self.pid, "TL", a, "buendel-1.4.3")
        k = auslieferung.Kette(self.con, self.pid, "TL", self.repo, ausgabe=lambda _: None)
        v = k.pruefen("buendel-1.4.3", gesamtlauf=lid)
        self.assertEqual(v["version"], "1.4.3")                                              # aus [1.4.3], nicht aus amw/__init__.py
        titel, text = k.notizen(v["sha"], "1.4.3")
        self.assertEqual(titel, "1.4.3")
        self.assertIn("### Fixed\n- Von Hand eingetragen.\n- Plus stimmt.", text)
        main = g(self.repo, "rev-parse", "main")
        with self.assertRaisesRegex(auslieferung.Stopp, "Stopp bei „Projekt“: Version 1.4.3 .*Mehrprojekt 9 .*erledigt: noch nichts"):
            k.ausliefern("buendel-1.4.3", gesamtlauf=lid)
        self.assertEqual((g(self.repo, "rev-parse", "main"), g(self.repo, "tag", "--list").split()), (main, ["v1.4.2"]))

    def test_eigene_versionsdatei(self):
        from amw import auslieferung
        kern.projekt_einstellen(self.con, self.pid, "TL", release_modus="datei", version_datei="pyproject.toml")
        schreiben(self.repo, "pyproject.toml", '[project]\nname = "spiel"\nversion = "2.0.1"\n')
        g(self.repo, "add", "-A")
        g(self.repo, "commit", "-q", "-m", "pyproject")
        k = auslieferung.Kette(self.con, self.pid, "TL", self.repo, ausgabe=lambda _: None)
        self.assertEqual(k.version_an("main"), "2.0.1")
        self.assertFalse(k.nur_amw())
        kern.projekt_einstellen(self.con, self.pid, "TL", version_datei="amw/__init__.py")
        self.assertEqual((k.version_an("main"), k.nur_amw()), ("1.2.3", True))                # wie die AMW: Kette wie bisher

    def test_datei_ist_vorgabe_und_braucht_die_versionsdatei(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", release_modus="datei")
        with self.assertRaisesRegex(buendel.BuendelFehler, "version_datei"):
            buendel.einstellungen(self.con, self.pid)
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "TL", release_modus="git")
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "CC1", release_modus="tag")                 # nur Lead oder Mensch


if __name__ == "__main__":
    unittest.main()
