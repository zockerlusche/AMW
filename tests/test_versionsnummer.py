"""Versionsnummer bei der Prüfbitte (A1753): zweimal vergaben zwei Coder dieselbe Nummer – jetzt merkt es die Prüfbitte."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import subprocess
import tempfile
import unittest

from amw import betrieb, db, kern, versionsnummer


class Nummer(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        for k in ("CC1", "CC2"):
            kern.agent_neu(self.con, self.pid, k)
        self.repo = os.path.join(self.ordner.name, "repo")
        os.makedirs(os.path.join(self.repo, "amw"))
        self.g("init", "-q", "-b", "main")
        self.stand("1.0.0")
        self.g("tag", "v1.0.0")
        kern.projekt_ordner_setzen(self.con, self.pid, self.repo)

    def g(self, *args):
        r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def stand(self, version, zweig=None):
        if zweig:
            self.g("switch", "-q", "-c", zweig, "main")
        with open(os.path.join(self.repo, "amw", "__init__.py"), "w", encoding="utf-8") as f:
            f.write(f'__version__ = "{version}"\n')
        with open(os.path.join(self.repo, "x.txt"), "a", encoding="utf-8") as f:
            f.write(f"{version} {zweig}\n")
        self.g("add", "-A")
        self.g("-c", "commit.gpgsign=false", "commit", "-q", "-m", version)
        sha = self.g("rev-parse", "HEAD")
        if zweig:
            self.g("switch", "-q", "main")
        return sha

    def bitte(self, agent, zweig, sha, aufgabe):
        return betrieb.pruefbitte(self.con, self.pid, agent, "TL", zweig, sha, "x", aufgabe)

    def test_doppelt_vergeben_unter_main_und_dieselbe_aufgabe(self):
        a1 = kern.aufgabe_neu(self.con, self.pid, "TL", "Eins", "CC1")
        a2 = kern.aufgabe_neu(self.con, self.pid, "TL", "Zwei", "CC2")
        self.bitte("CC1", "a1", self.stand("1.1.0", "a1"), a1)
        with self.assertRaises(kern.AmwFehler) as e:                                 # CC2 nimmt dieselbe Nummer
            self.bitte("CC2", "a2", self.stand("1.1.0", "a2"), a2)
        self.assertIn("Version 1.1.0 ist schon vergeben (A", str(e.exception))
        self.assertIn("nächste freie Nummer: 1.1.1 oder 1.2.0", str(e.exception))
        with self.assertRaises(kern.AmwFehler) as e:
            self.bitte("CC2", "a2-alt", self.stand("1.0.0", "a2-alt"), a2)
        self.assertIn("liegt nicht über main (1.0.0)", str(e.exception))
        self.bitte("CC1", "a1-2", self.stand("1.1.0", "a1-2"), a1)                  # dieselbe Aufgabe: Nummer bleibt
        self.bitte("CC2", "a2-3", self.stand("1.2.0", "a2-3"), a2)                  # freie Nummer: geht

    def test_ohne_versionsdatei_keine_pruefung(self):
        os.remove(os.path.join(self.repo, "amw", "__init__.py"))
        self.g("add", "-A")
        self.g("-c", "commit.gpgsign=false", "commit", "-q", "-m", "ohne")
        a = kern.aufgabe_neu(self.con, self.pid, "TL", "Eins", "CC1")
        self.assertTrue(self.bitte("CC1", "main", self.g("rev-parse", "HEAD"), a))


from tests.abnahme_versionsnummer import Abnahme as _AbnahmeF1  # noqa: E402


class NeuAufgesetzt(_AbnahmeF1):
    """A1873 (F1): die Abnahme-Fälle laufen auch im Gesamtlauf; dazu der Fall „neueste rot“ (TL entschieden)."""

    def test_neueste_rot_aeltere_gruene_belegt_weiter(self):
        self.pruefung(self.a, self.stand("1.2.0", "a-alt"), "gruen")
        self.pruefung(self.a, self.stand("1.1.0", "a-neu"), "rot")       # die neueste ist rot – sie zählt nicht
        with self.assertRaises(kern.AmwFehler):
            versionsnummer.pruefen(self.con, self.pid, self.stand("1.2.0", "b"), self.b)


if __name__ == "__main__":
    unittest.main()
