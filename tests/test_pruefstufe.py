"""Prüfstufe aus den geänderten Dateien (A1656): Vorgabe-Muster, Muster je Projekt, echtes Git-Repository, Zeile in der
Prüfbitte."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from amw import betrieb, db, kern, pruefstufe


class Einstufen(unittest.TestCase):
    def test_vorgabe(self):
        m = pruefstufe.VORGABE
        self.assertEqual(pruefstufe.einstufen(["amw/migration_33.sql", "amw/workbench.html", "README.md"], m),
                         ("hoch", ["amw/migration_33.sql"]))
        self.assertEqual(pruefstufe.einstufen(["doc/hilfe/dienst.md", "tests/x.py"], m), ("mittel", ["doc/hilfe/dienst.md"]))
        self.assertEqual(pruefstufe.einstufen(["web/hilfe/a.de.json"], m)[0], "mittel")       # * passt auch über / hinweg
        self.assertEqual(pruefstufe.einstufen(["tests/test_x.py", "CHANGELOG.md", "amw/__init__.py"], m), ("niedrig", []))
        self.assertEqual(pruefstufe.einstufen(["tests/test_x.py", "amw/anlass.py"], m), ("mittel", ["amw/anlass.py"]))   # Code = nicht niedrig
        for d in ("amw/kern.py", "amw/hook.py", "amw/schema.sql", "amw/cli.py", "amw/aktionen.py", "amw/workbench.py", "amw/dienst.py",
                  "amw/ki.py", "amw/einstellungen.py", "amw/runde.py", "web/api.php", "web/inc/lib.php", "web/index.php"):   # TL P157
            self.assertEqual(pruefstufe.einstufen([d], m)[0], "hoch", d)
        self.assertEqual(pruefstufe.einstufen(None, m), ("unbekannt", []))

    def test_hoeher(self):
        self.assertEqual(pruefstufe.hoeher("niedrig", "hoch"), "hoch")
        self.assertEqual(pruefstufe.hoeher("mittel", "niedrig"), "mittel")
        self.assertEqual(pruefstufe.hoeher("mittel", "unbekannt"), "unbekannt")

    def test_zeile(self):
        self.assertEqual(pruefstufe.zeile({"stufe": "hoch", "treffer": ["a", "b", "c", "d", "e", "f"], "dateien": []}),
                         "Prüfstufe hoch – a, b, c, d (+2)")
        self.assertIn("2 Datei(en), nur Doku und Tests", pruefstufe.zeile({"stufe": "niedrig", "treffer": [], "dateien": ["x", "y"]}))
        self.assertIn("unbekannt", pruefstufe.zeile({"stufe": "unbekannt", "treffer": [], "dateien": None}))


class MitRepo(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        umgebung = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        umgebung.start()
        self.addCleanup(umgebung.stop)
        self.repo = os.path.join(self.ordner.name, "repo")
        os.makedirs(os.path.join(self.repo, "amw"))
        self.g("init", "-q", "-b", "main")
        self.schreiben("README.md", "x")
        self.g("add", "-A")
        self.g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "start")
        self.g("switch", "-q", "-c", "zweig")
        self.schreiben("amw/bruecke.py", "neu")
        self.schreiben("doc.md", "neu")
        self.g("add", "-A")
        self.g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "zweig")
        self.sha = self.g("rev-parse", "HEAD")
        self.con = db.anlegen()
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")

    def g(self, *args):
        return subprocess.run(["git", "-C", self.repo, *args], capture_output=True, text=True, check=True).stdout.strip()

    def schreiben(self, name, inhalt):
        with open(os.path.join(self.repo, name), "w", encoding="utf-8") as f:
            f.write(inhalt)

    def ordner_setzen(self, **mehr):
        with db.schreiben(self.con):
            self.con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?", (json.dumps({"ordner": self.repo, **mehr}), self.pid))

    def test_stufe_aus_dem_repo_und_in_der_pruefbitte(self):
        self.assertEqual(pruefstufe.stufe(self.con, self.pid, self.sha)["stufe"], "unbekannt")   # ohne Projektordner
        self.ordner_setzen()
        info = pruefstufe.stufe(self.con, self.pid, self.sha)
        self.assertEqual((info["stufe"], info["treffer"], sorted(info["dateien"])), ("hoch", ["amw/bruecke.py"], ["amw/bruecke.py", "doc.md"]))
        prid = betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "zweig", self.sha, punkte="Bitte ansehen")
        text = self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE ?", (f"Prüfbitte P{prid}:%",)).fetchone()[0]
        self.assertTrue(text.startswith("Prüfstufe hoch – amw/bruecke.py"), text)
        self.assertIn("Bitte ansehen", text)

    def test_regel_nur_wenn_eingeschaltet(self):
        """pruefstufen = an: hoch → der Lead prüft; mittel → nicht der Bauer selbst; höher einstufen ja, niedriger nie."""
        self.ordner_setzen()
        hoch = {"stufe": "hoch", "treffer": ["amw/bruecke.py"], "dateien": ["amw/bruecke.py"]}
        mittel = {"stufe": "mittel", "treffer": ["amw/workbench.html"], "dateien": ["amw/workbench.html"]}
        kern.agent_neu(self.con, self.pid, "CC2")
        self.assertEqual(pruefstufe.regel(self.con, self.pid, hoch, "CC1", "CC2"), "hoch")          # aus: nur anzeigen
        kern.projekt_einstellen(self.con, self.pid, "TL", pruefstufen="an")
        with self.assertRaises(kern.AmwFehler) as e:
            pruefstufe.regel(self.con, self.pid, hoch, "CC1", "CC2")
        self.assertIn("--pruefer TL", str(e.exception))
        self.assertEqual(pruefstufe.regel(self.con, self.pid, hoch, "CC1", "TL"), "hoch")
        with self.assertRaises(kern.AmwFehler):
            pruefstufe.regel(self.con, self.pid, mittel, "CC1", "CC1")
        self.assertEqual(pruefstufe.regel(self.con, self.pid, mittel, "CC1", "CC2"), "mittel")
        with self.assertRaises(kern.AmwFehler):                                                 # niedriger einstufen geht nicht
            pruefstufe.regel(self.con, self.pid, mittel, "CC1", "CC2", "niedrig")
        with self.assertRaises(kern.AmwFehler):                                                 # höher: dann prüft der Lead
            pruefstufe.regel(self.con, self.pid, mittel, "CC1", "CC2", "hoch")
        with self.assertRaises(kern.AmwFehler):                                                 # über die Prüfbitte genauso
            betrieb.pruefbitte(self.con, self.pid, "CC1", "CC2", "zweig", self.sha)
        self.assertTrue(betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "zweig", self.sha))

    def test_muster_je_projekt(self):
        self.ordner_setzen(pruef_muster={"hoch": [], "mittel": ["doc.md"]})
        self.assertEqual(pruefstufe.stufe(self.con, self.pid, self.sha)["stufe"], "mittel")       # bruecke.py zählt hier nicht


if __name__ == "__main__":
    unittest.main()
