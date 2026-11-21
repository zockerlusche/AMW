"""A1868: versionsnummer.version_im_stand (Quellen VERSION, amw/__init__.py, package.json; ungültige Form und unbekannter
Stand → None) und versionsnummer.pruefen mit einer Nummer, die schon als Tag existiert (Vorschlag CCamwTL D1289)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import subprocess
import tempfile
import unittest

from amw import db, kern, versionsnummer


class Repo(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.repo = os.path.join(self.ordner.name, "repo")
        os.makedirs(self.repo)
        self.g("init", "-q", "-b", "main")

    def g(self, *args):
        r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=self.repo, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def commit(self, dateien, zweig=None, weg=()):
        """Schreibt die Dateien (Pfad → Inhalt), entfernt die in weg, committet; gibt den SHA zurück."""
        if zweig:
            self.g("switch", "-q", "-c", zweig, "main")
        for pfad, inhalt in dateien.items():
            voll = os.path.join(self.repo, *pfad.split("/"))
            os.makedirs(os.path.dirname(voll), exist_ok=True)
            with open(voll, "w", encoding="utf-8", newline="\n") as f:
                f.write(inhalt)
        for pfad in weg:
            os.remove(os.path.join(self.repo, *pfad.split("/")))
        with open(os.path.join(self.repo, "x.txt"), "a", encoding="utf-8") as f:   # jeder Commit ändert etwas
            f.write(f"{zweig} {sorted(dateien)}\n")
        self.g("add", "-A")
        self.g("-c", "commit.gpgsign=false", "commit", "-q", "-m", "stand")
        sha = self.g("rev-parse", "HEAD")
        if zweig:
            self.g("switch", "-q", "main")
        return sha


class VersionImStand(Repo):
    def v(self, sha):
        return versionsnummer.version_im_stand(self.repo, sha)

    def test_quelle_version_datei(self):
        sha = self.commit({"VERSION": "2.3.4\n"})
        self.assertEqual(self.v(sha), "2.3.4")

    def test_quelle_amw_init(self):
        sha = self.commit({"amw/__init__.py": '"""Paket."""\n__version__ = \'1.149.1\'\n'})
        self.assertEqual(self.v(sha), "1.149.1")

    def test_quelle_package_json(self):
        sha = self.commit({"package.json": json.dumps({"name": "x", "version": "0.7.12"})})
        self.assertEqual(self.v(sha), "0.7.12")

    def test_reihenfolge_version_vor_init_vor_package(self):
        sha = self.commit({"VERSION": "3.0.0\n", "amw/__init__.py": '__version__ = "2.0.0"\n',
                           "package.json": json.dumps({"version": "1.0.0"})})
        self.assertEqual(self.v(sha), "3.0.0")
        sha = self.commit({"amw/__init__.py": '__version__ = "2.0.0"\n'}, weg=("VERSION",))
        self.assertEqual(self.v(sha), "2.0.0")

    def test_ungueltige_form_faellt_auf_naechste_quelle(self):
        sha = self.commit({"VERSION": "eins-zwei\n", "amw/__init__.py": '__version__ = "1.2"\n',
                           "package.json": json.dumps({"version": "4.5.6"})})
        self.assertEqual(self.v(sha), "4.5.6")

    def test_ungueltige_form_ueberall_none(self):
        sha = self.commit({"VERSION": "1.2\n", "amw/__init__.py": '__version__ = "v1.2.3"\n',
                           "package.json": json.dumps({"version": "neu"})})
        self.assertIsNone(self.v(sha))

    def test_package_json_kaputt_oder_ohne_version_none(self):
        sha = self.commit({"package.json": "{ kein json"})
        self.assertIsNone(self.v(sha))
        sha = self.commit({"package.json": json.dumps({"name": "x"})})
        self.assertIsNone(self.v(sha))
        sha = self.commit({"package.json": json.dumps(["1.0.0"])})
        self.assertIsNone(self.v(sha))

    def test_ohne_versionsdatei_none(self):
        sha = self.commit({"README.md": "nichts\n"})
        self.assertIsNone(self.v(sha))

    def test_unbekannter_stand_none(self):
        self.commit({"VERSION": "1.0.0\n"})
        self.assertIsNone(self.v("0" * 40))
        self.assertIsNone(self.v("gibt-es-nicht"))

    def test_kein_repository_none(self):
        leer = os.path.join(self.ordner.name, "leer")
        os.makedirs(leer)
        self.assertIsNone(versionsnummer.version_im_stand(leer, "main"))


class PruefenTag(Repo):
    def setUp(self):
        super().setUp()
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        self.commit({"amw/__init__.py": '__version__ = "1.0.0"\n'})
        self.g("tag", "v1.0.0")
        kern.projekt_ordner_setzen(self.con, self.pid, self.repo)

    def test_nummer_schon_als_tag_vergeben(self):
        # v1.1.0 hängt an einem Stand außerhalb von main (z. B. ausgeliefert, aber main noch nicht nachgezogen)
        self.g("tag", "v1.1.0", self.commit({"amw/__init__.py": '__version__ = "1.1.0"\n'}, "alt"))
        sha = self.commit({"amw/__init__.py": '__version__ = "1.1.0"\n'}, "neu")
        with self.assertRaises(kern.AmwFehler) as e:
            versionsnummer.pruefen(self.con, self.pid, sha, None)
        self.assertIn("Version 1.1.0 ist schon vergeben (Tag v1.1.0)", str(e.exception))
        self.assertIn("nächste freie Nummer: 1.1.1 oder 1.2.0", str(e.exception))

    def test_vorschlag_nach_hoechstem_tag(self):
        self.g("tag", "v1.1.0", self.commit({"amw/__init__.py": '__version__ = "1.1.0"\n'}, "alt"))
        self.g("tag", "v1.4.2", self.commit({"amw/__init__.py": '__version__ = "1.4.2"\n'}, "alt2"))
        sha = self.commit({"amw/__init__.py": '__version__ = "1.1.0"\n'}, "neu")
        with self.assertRaises(kern.AmwFehler) as e:
            versionsnummer.pruefen(self.con, self.pid, sha, None)
        self.assertIn("(Tag v1.1.0)", str(e.exception))
        self.assertIn("nächste freie Nummer: 1.4.3 oder 1.5.0", str(e.exception))

    def test_freie_nummer_trotz_tags_geht(self):
        self.g("tag", "v1.1.0", self.commit({"amw/__init__.py": '__version__ = "1.1.0"\n'}, "alt"))
        sha = self.commit({"amw/__init__.py": '__version__ = "1.2.0"\n'}, "neu")
        self.assertEqual(versionsnummer.pruefen(self.con, self.pid, sha, None), "1.2.0")

    def test_tag_ohne_versionsform_zaehlt_nicht(self):
        self.g("tag", "vorlaeufig")
        self.g("tag", "v-test")
        sha = self.commit({"amw/__init__.py": '__version__ = "1.0.1"\n'}, "neu")
        self.assertEqual(versionsnummer.pruefen(self.con, self.pid, sha, None), "1.0.1")


if __name__ == "__main__":
    unittest.main()
