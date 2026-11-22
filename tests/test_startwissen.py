"""A1943 (K9, #30726/#30728): Bereichs-Wissen beim Schließen, Projekt-Landkarte, Startwissen mit festem Budget, amw paket holen
(nimmt, zeigt, legt Arbeitsbaum nur an) und amw paket fertig (Tests-Hinweis, Prüfbitte, wartet, Messung)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from amw import cli, db, kern, startwissen


def g(ordner, *args):
    return subprocess.run(["git", "-C", ordner, *args], check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip()


def schreiben(ordner, rel, text):
    p = os.path.join(ordner, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad})
        u.start()
        self.addCleanup(u.stop)
        for k in ("AMW_AGENT", "AMW_PROJEKT"):
            os.environ.pop(k, None)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.repo = os.path.join(self.ordner.name, "repo")
        os.makedirs(self.repo)
        g(self.repo, "init", "-q", "-b", "main")
        g(self.repo, "config", "user.email", "t@t")
        g(self.repo, "config", "user.name", "t")
        schreiben(self.repo, "amw/rechnen.py", '"""Rechnen: plus und minus für die Kasse."""\n\ndef plus(a, b):\n    return a + b\n')
        schreiben(self.repo, "amw/anzeige.py", '"""Anzeige der Summen."""\n')
        schreiben(self.repo, "tests/test_rechnen.py", "from amw import rechnen\n")
        schreiben(self.repo, "tests/test_sonst.py", "import os\n")
        g(self.repo, "add", "-A")
        g(self.repo, "commit", "-q", "-m", "Anfang")
        kern.projekt_ordner_setzen(self.con, self.pid, self.repo)

    def aufgabe(self, titel, **k):
        return kern.aufgabe_neu(self.con, self.pid, "TL", titel, agent="CC1", **k)

    def commit(self, aid, rel, text):
        schreiben(self.repo, rel, text)
        g(self.repo, "add", "-A")
        g(self.repo, "commit", "-q", "-m", f"A{aid}: Änderung an {rel}")
        return g(self.repo, "rev-parse", "HEAD")

    def cli(self, *args):
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main([*args, "--projekt", "P"])
        return rc, aus.getvalue()


class Wissen(Grund):
    def test_bereich_beim_schliessen_und_startwissen_im_budget(self):
        a = self.aufgabe("plus genauer")
        sha = self.commit(a, "amw/rechnen.py", '"""Rechnen."""\ndef plus(a, b):\n    return round(a + b, 2)\n')
        kern.aufgabe_status(self.con, self.pid, "CC1", a, "start")
        kern.aufgabe_status(self.con, self.pid, "CC1", a, "fertig", beleg=sha[:7], zusammenfassung="plus rundet",
                            hinweis="Summen werden auf Cent gerundet.", gruppe="behoben")
        w = json.loads(self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'bereich_wissen' AND aufgabe_id = ?", (a,)).fetchone()[0])
        self.assertEqual(w, {"dateien": ["amw/rechnen.py"], "satz": "Summen werden auf Cent gerundet."})
        b = self.aufgabe("minus in rechnen.py ergänzen")                                      # nennt die Datei im Titel
        t = startwissen.startwissen(self.con, self.pid, b)
        self.assertIn(f"- amw/rechnen.py (A{a}): Summen werden auf Cent gerundet.", t)
        self.assertIn("Projekt-Landkarte:", t)
        self.assertIn("amw/anzeige.py – Anzeige der Summen.", t)
        self.assertLessEqual(len(startwissen.startwissen(self.con, self.pid, b, budget=120)), 120)   # Budget: Landkarte zuerst gekürzt
        self.assertIn("Summen werden auf Cent gerundet", startwissen.startwissen(self.con, self.pid, b, budget=120))
        z = self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'startwissen' AND aufgabe_id = ? ORDER BY id DESC", (b,)).fetchone()
        self.assertLessEqual(json.loads(z[0])["zeichen"], 120)

    def test_tests_zu_geaenderten_modulen(self):
        self.assertEqual(startwissen.tests_zu(self.repo, ["amw/rechnen.py", "doc/x.md"]), ["test_rechnen"])
        self.assertEqual(startwissen.tests_zu(self.repo, ["tests/test_sonst.py"]), ["test_sonst"])


class Befehle(Grund):
    def test_holen_legt_baum_an_und_fertig_stellt_pruefbitte(self):
        a = self.aufgabe("plus genauer", rang=10)
        self.aufgabe("später", rang=20)
        wurzel = os.path.join(self.ordner.name, "baeume")
        os.makedirs(wurzel)
        with self.assertRaises(kern.AmwFehler):                                              # nie im Projektordner
            kern.projekt_einstellen(self.con, self.pid, "TL", baum_wurzel=os.path.join(self.repo, "x"))
        kern.projekt_einstellen(self.con, self.pid, "TL", baum_wurzel=wurzel)
        with db.schreiben(self.con):
            db.einfuegen(self.con, "sitzung", agent_id=self.con.execute("SELECT id FROM agent WHERE kennung = 'CC1'").fetchone()[0],
                         claude_sitzung="s1", gestartet_utc=db.jetzt())
        rc, aus = self.cli("paket", "holen", "--von", "CC1")
        self.assertEqual(rc, 0, aus)
        self.assertIn(f"A{a} → laeuft · plus genauer", aus)
        baum = os.path.join(wurzel, f"a{a}")
        self.assertTrue(os.path.isdir(baum), aus)
        self.assertEqual(g(baum, "rev-parse", "--abbrev-ref", "HEAD"), f"a{a}")
        rc, aus = self.cli("paket", "holen", "--von", "CC1")                                   # eins nach dem anderen
        self.assertIn("läuft noch", aus)
        schreiben(baum, "amw/rechnen.py", '"""Rechnen."""\ndef plus(a, b):\n    return round(a + b, 2)\n')
        g(baum, "add", "-A")
        g(baum, "commit", "-q", "-m", f"A{a}: plus rundet")
        sha = g(baum, "rev-parse", "HEAD")
        rc, aus = self.cli("paket", "fertig", str(a), "--sha", sha, "--punkte", "test_rechnen grün", "--von", "CC1")
        self.assertEqual(rc, 0, aus)
        self.assertIn("Tests zu den geänderten Dateien: test_rechnen", aus)
        self.assertIn("an TL", aus)
        r = self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (a,)).fetchone()
        self.assertEqual(r["status"], "wartet")
        p = self.con.execute("SELECT pruefer, zweig, sha FROM pruefung WHERE aufgabe_id = ?", (a,)).fetchone()
        self.assertEqual(tuple(p), ("TL", f"a{a}", sha))
        m = json.loads(self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'k9_paket' AND aufgabe_id = ?", (a,)).fetchone()[0])
        self.assertTrue(m["holen"])
        self.assertGreaterEqual(m["befehle"], 2)                                               # holen, holen, fertig – gezählt
        self.assertTrue(os.path.isdir(baum))                                                   # nie entfernt
        self.assertEqual(startwissen.messung(self.con, self.pid)["mit"], [m["befehle"]])


if __name__ == "__main__":
    unittest.main()
