"""Sperrliste vor dem ersten echten -p-Start (A1872, M50 S3b; Befund D1289, D1258 §5/§6a.3): alles, was einen Arbeiter
abschottet, prüft, startet oder Rechte vergibt, und alle automatisch geladenen Dateien sind für p-Pakete gesperrt – vor dem
Start (Startregel 5) und danach (Diff-Tor, auch in Prüfung C). Die Liste gibt es genau einmal (abnahme.GESPERRT)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import unittest

from amw import abnahme, pruefung_c

PFLICHT = ("amw/arbeiter.py", "amw/waechter.py", "amw/entscheidung.py", "amw/pruefung_c.py", "amw/tokenprognose.py", "amw/db.py",
           "amw/einstellungen.py", "amw/betrieb.py", "amw/laufdienst.py", "amw/belegung.py", "amw/kern.py", "amw/steuerung.py",
           "amw/cli.py", "amw/aktionen.py", "amw/schluessel.py", "amw/versionsnummer.py", "amw/versionshinweise.py", "amw/__main__.py",
           "amw/disponent.py", "amw/rueckmeldung.py", "amw/abnahme.py", "amw/platz.py", "amw/auslieferung.py", "amw/dienst.py",
           "amw/vorlagen/auftrag_p.md", "amw-cli.py", "amw-arbeiter.py", "amw-rueckmeldung.py", "amw-hook.py", "start_dienst.pyw")
AUTOMATISCH = ("sitecustomize.py", "lib/sitecustomize.py", "usercustomize.py", "tests/usercustomize.py", "conftest.py",
               "tests/conftest.py", "a/b/conftest.py", "x.pth", "lib/site/x.pth", "pyproject.toml", "web/pyproject.toml", "setup.cfg",
               "sub/setup.cfg", "tox.ini")
FREI = ("amw/hilfen.py", "amw/messung.py", "doc/hilfe/agenten.md", "web/hilfe/agenten.de.json", "amw/workbench.py")


class Sperrliste(unittest.TestCase):
    def test_pflicht_dateien_gesperrt_vor_und_nach_dem_start(self):
        for pfad in PFLICHT + AUTOMATISCH:
            with self.subTest(pfad=pfad):
                self.assertTrue(abnahme.gesperrt([pfad]), "Diff-Tor")                              # danach (diff_tor, Prüfung C)
                self.assertTrue(abnahme.startregel([pfad]), "Startregel 5")                        # davor (Bereich des Pakets)
                self.assertTrue(abnahme.gesperrt([pfad.upper()]), "Groß/Klein")                    # Windows: CLI.PY ist cli.py

    def test_auch_beim_pakettyp_test_schreiben(self):
        for pfad in PFLICHT + AUTOMATISCH:
            self.assertTrue(abnahme.gesperrt([pfad], abnahme.TEST_SCHREIBEN), pfad)

    def test_ordner_als_bereich_mit_gesperrtem_inhalt(self):
        self.assertTrue(abnahme.startregel(["amw/"]))                                              # amw/ enthält gesperrte Dateien
        self.assertTrue(abnahme.startregel(["amw/vorlagen/"]))

    def test_normale_dateien_bleiben_frei(self):
        for pfad in FREI:
            with self.subTest(pfad=pfad):
                self.assertEqual(abnahme.gesperrt([pfad]), [])
                self.assertEqual(abnahme.startregel([pfad]), [])

    def test_eine_liste_fuer_automatisch_geladene(self):
        """Prüfung C leitet „automatisch geladen“ aus abnahme.GESPERRT ab – keine zweite Liste."""
        for pfad in AUTOMATISCH:
            self.assertTrue(pruefung_c.autogeladen([pfad]), pfad)
        eigene = set(pruefung_c.AUTOGELADEN) - {m for m, _, _ in abnahme.GESPERRT}
        self.assertTrue(all("pytest" in m for m in eigene), eigene)


if __name__ == "__main__":
    unittest.main()
