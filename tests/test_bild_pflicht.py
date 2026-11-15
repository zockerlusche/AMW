"""Prüfbitte mit sichtbarer Änderung nur mit Bild (A1755, B2750): ändert der Stand Seite oder Hilfe, muss an der Aufgabe ein
Bild-Dokument hängen – die Prüfbitte nennt es von selbst; Ausnahme nur mit Grund. In einem Stapel zählt die eigene Änderung."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from amw import betrieb, db, dokumente, kern


class BildPflicht(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        umgebung = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "daten", "amw.db")})
        umgebung.start()
        self.addCleanup(umgebung.stop)
        self.con = db.anlegen()
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.repo = os.path.join(self.ordner.name, "repo")
        os.makedirs(self.repo)
        self.g("init", "-q", "-b", "main")
        self.datei("README.md", "x")
        self.commit("Anfang")
        kern.projekt_ordner_setzen(self.con, self.pid, self.repo)

    def g(self, *args):
        r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def datei(self, pfad, inhalt):
        os.makedirs(os.path.dirname(os.path.join(self.repo, pfad)) or self.repo, exist_ok=True)
        with open(os.path.join(self.repo, pfad), "a", encoding="utf-8") as f:
            f.write(inhalt + "\n")

    def commit(self, text):
        self.g("add", "-A")
        self.g("-c", "commit.gpgsign=false", "commit", "-q", "-m", text)
        return self.g("rev-parse", "HEAD")

    def bild(self, aufgabe):
        pfad = os.path.join(self.ordner.name, f"bild{aufgabe}.png")
        with open(pfad, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        return dokumente.ablegen(self.con, self.pid, "CC1", pfad, "Handy", "bild", aufgabe=aufgabe)

    def text(self, prid):
        return self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE ?", (f"Prüfbitte P{prid}:%",)).fetchone()[0]

    def test_sichtbar_braucht_bild_ausnahme_mit_grund(self):
        a = kern.aufgabe_neu(self.con, self.pid, "TL", "Seite", "CC1")
        self.g("switch", "-q", "-c", "seite")
        self.datei("web/inc/seite.html", "<p>neu</p>")
        sha = self.commit("Seite")
        with self.assertRaises(kern.AmwFehler) as e:
            betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "seite", sha, "x", a)
        self.assertIn("nur mit Bild", str(e.exception))
        self.assertIn(f"--aufgabe {a}", str(e.exception))
        p = betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "seite", sha, "x", a, ohne_bild="nur ein Abstand")
        self.assertIn("Ohne Bild (sichtbar: web/inc/seite.html): nur ein Abstand", self.text(p))
        d = self.bild(a)
        p = betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "seite", sha, "x", a)
        self.assertIn(f"Bilder: D{d} Handy", self.text(p))

    def test_unsichtbar_ohne_bild_und_im_stapel_zaehlt_die_eigene_aenderung(self):
        a1 = kern.aufgabe_neu(self.con, self.pid, "TL", "Seite", "CC1")
        a2 = kern.aufgabe_neu(self.con, self.pid, "TL", "Logik", "CC1")
        self.g("switch", "-q", "-c", "unten")
        self.datei("doc/hilfe/planung.md", "neu")
        unten = self.commit("Hilfe")
        self.bild(a1)
        betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "unten", unten, "x", a1)
        self.g("switch", "-q", "-c", "oben")
        self.datei("amw/planung.py", "x = 1")
        oben = self.commit("Logik")
        self.assertTrue(betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "oben", oben, "x", a2))   # Hilfe kam von unten


if __name__ == "__main__":
    unittest.main()
