"""Abnahme (Kandidat F1, A1856): Eine Versionsnummer belegt nur die NEUESTE offene oder grüne Prüfung einer anderen Aufgabe.
Vorfall 17.11.: A1862 wurde neu aufgesetzt (1.131.3); ihre alte grüne Prüfung P248 (1.132.0) belegte die Nummer weiter, A1865 musste
auf 1.133.0 ausweichen. Gleiche Fehlerklasse wie auslieferung.reihenfolge (A1862: „je Aufgabe zählt nur die neueste grüne Prüfung“).
Absichtlich NICHT test_*.py: der Gesamtlauf (unittest discover) findet ihn nicht, nur `python -m unittest tests.abnahme_versionsnummer`.
"""
import tests.abschotten  # noqa: F401 – immer als erster Import
import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from amw import db, kern, versionsnummer


class Abnahme(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen()
        self.addCleanup(self.con.close)
        self.repo = os.path.join(self.ordner.name, "repo")
        os.makedirs(self.repo)
        self.g("init", "-q", "-b", "main")
        self.g("config", "user.email", "t@t.invalid")
        self.g("config", "user.name", "T")
        self.main = self.stand("1.0.0")
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt(),
                                    einstellungen=json.dumps({"ordner": self.repo}))
        self.assertEqual(os.path.normcase(kern.projekt_ordner(self.con, self.pid)), os.path.normcase(self.repo))
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        self.a = kern.aufgabe_neu(self.con, self.pid, "TL", "A", "TL")
        self.b = kern.aufgabe_neu(self.con, self.pid, "TL", "B", "TL")

    def g(self, *args):
        return subprocess.run(["git", "-C", self.repo, *args], capture_output=True, text=True, check=True).stdout.strip()

    def stand(self, version, zweig=None):
        if zweig:
            self.g("switch", "-q", "-c", zweig, "main")
        os.makedirs(os.path.join(self.repo, "amw"), exist_ok=True)
        with open(os.path.join(self.repo, "amw", "__init__.py"), "w", encoding="utf-8") as f:
            f.write(f'__version__ = "{version}"\n')
        self.g("add", "-A")
        self.g("commit", "-q", "-m", version)
        sha = self.g("rev-parse", "HEAD")
        if zweig:
            self.g("switch", "-q", "main")
        return sha

    def pruefung(self, aufgabe, sha, ergebnis):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=aufgabe, zweig=f"z{aufgabe}", sha=sha, bauer="CC",
                         pruefer="TL", ergebnis=ergebnis, angefragt_utc=db.jetzt())

    def test_alte_gruene_pruefung_einer_neu_aufgesetzten_aufgabe_belegt_nichts(self):
        self.pruefung(self.a, self.stand("1.2.0", "a-alt"), "gruen")     # A, erster Stand: 1.2.0 grün (wie P248)
        self.pruefung(self.a, self.stand("1.1.0", "a-neu"), "offen")     # A neu aufgesetzt: jetzt 1.1.0 (wie P252/P254)
        b = self.stand("1.2.0", "b")                                      # B nimmt die frei gewordene 1.2.0
        self.assertEqual(versionsnummer.pruefen(self.con, self.pid, b, self.b), "1.2.0")

    def test_neueste_pruefung_belegt_weiter(self):
        self.pruefung(self.a, self.stand("1.1.0", "a-alt"), "gruen")
        self.pruefung(self.a, self.stand("1.2.0", "a-neu"), "offen")     # die neueste trägt 1.2.0 – die bleibt belegt
        with self.assertRaises(kern.AmwFehler):
            versionsnummer.pruefen(self.con, self.pid, self.stand("1.2.0", "b"), self.b)


if __name__ == "__main__":
    unittest.main()
