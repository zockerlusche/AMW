"""A1956 (TH168 Hebel 7, Marcel W2461): kleiner Startkontext – Kurzregeln statt Wortlaut, ganze Regel per `amw regeln KR<n>`,
ausführliche Anleitungen als Claude-Code-Skills (dünne Verweise auf doc/…), Messung vorher/nachher (basis_hebel7)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from unittest import mock

from amw import cli, db, kern, regelwerk, skills

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        u.start()
        self.addCleanup(u.stop)
        for k in ("AMW_AGENT", "AMW_PROJEKT"):
            os.environ.pop(k, None)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        regelwerk.uebernehmen(self.con, self.pid, kern.ENTWICKLER)          # das ganze Grund-Regelwerk

    def befehl(self, *args):
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus), contextlib.redirect_stderr(io.StringIO()):
            rc = cli.main([*args, "--projekt", "Spiel"])
        return rc, aus.getvalue()


class Kontext(Grund):
    def test_kurz_mit_kurzregeln_statt_wortlaut(self):
        t = kern.kontext(self.con, self.pid, "CC1")
        self.assertLess(len(t.splitlines()), 200)
        zeile = next(z for z in t.splitlines() if z.startswith("Regeln ("))
        n = self.con.execute("SELECT COUNT(*) FROM regel WHERE projekt_id = ?", (self.pid,)).fetchone()[0]
        self.assertGreater(n, 10)
        self.assertTrue(zeile.startswith(f"Regeln ({n}, ganz: `amw regeln KR<n>`): KR1 "), zeile)
        self.assertEqual(len(re.findall(r"\b(?:KR|PR)\d+ ", zeile)), n)               # jede Regel genannt …
        for r in self.con.execute("SELECT text FROM regel WHERE projekt_id = ?", (self.pid,)):
            if len(r["text"]) > 120:
                self.assertNotIn(r["text"], t)                                          # … aber nicht im Wortlaut
        self.assertIn("nur NEUE Meldungen in deinen eigenen Bereichen beheben", zeile)  # Regel aus A1959 (LSP)
        self.assertIn("Vor Commit, Push, Release, Löschen", zeile)                     # wann den Wortlaut nachlesen (Gegenlesen)
        self.assertIn("Skills amw-befehle", t)

    def test_kurzregel_titel(self):
        k = skills.kurzregeln(self.con, self.pid)
        self.assertTrue(all(len(x) <= 64 for x in k), [x for x in k if len(x) > 64])
        self.assertIn("KR1 Versionen (G1)", k)

    def test_genannte_skills_gibt_es(self):
        t = kern.kontext(self.con, self.pid, "CC1")
        namen = {r.split("/")[0] for r in skills.skills()}
        genannt = re.findall(r"\b(amw-[a-z-]*[a-z])\b", t.split("Ausführliche Anleitungen:")[1].splitlines()[0])
        self.assertTrue(genannt)
        for n in genannt:
            self.assertTrue(n in namen or any(x.startswith(n + "-") for x in namen), n)


class Regeln(Grund):
    def test_eine_regel_ganz(self):
        rc, aus = self.befehl("regeln", "KR3", "--von", "CC1")
        self.assertEqual(rc, 0)
        self.assertTrue(aus.startswith("KR3"), aus[:80])
        self.assertNotIn("KR4", aus)
        self.assertEqual(self.befehl("regeln", "3", "--von", "CC1")[1], aus)
        self.assertEqual(len(re.findall(r"^KR\d+", self.befehl("regeln", "--von", "CC1")[1], re.M)),
                         self.con.execute("SELECT COUNT(*) FROM regel WHERE projekt_id = ? AND ebene = 'arbeit'", (self.pid,)).fetchone()[0])
        self.assertNotEqual(self.befehl("regeln", "KR999", "--von", "CC1")[0], 0)
        self.assertNotEqual(self.befehl("regeln", "XY", "--von", "CC1")[0], 0)


class Skills(unittest.TestCase):
    def test_skills_im_repo_passen_zu_den_quellen(self):
        """Je Quelle ein Skill, jeder Skill verweist auf seine Quelle. Der Beschreibungstext darf nachhinken (ein Arbeiter am
        Arbeitsplatz darf .claude/** nicht ändern – eine Doku-Änderung soll ihn nicht rot machen); `amw skills bauen` zieht ihn nach."""
        da = sorted(d for d in os.listdir(os.path.join(WURZEL, ".claude", "skills")) if d.startswith("amw-"))
        self.assertEqual(da, sorted(r.split("/")[0] for r in skills.skills()), "Skills passen nicht zu doc/ – `amw skills bauen`")
        for name, rel in skills.quellen():
            with open(os.path.join(WURZEL, ".claude", "skills", name, "SKILL.md"), encoding="utf-8") as f:
                self.assertIn(f"steht in `{rel}`", f.read(), name)

    def test_form_und_verweise(self):
        namen = set()
        for rel, inhalt in skills.skills().items():
            m = re.match(r"---\nname: ([a-z0-9-]+)\ndescription: (\".*\")\n---\n", inhalt)
            self.assertTrue(m, rel)
            namen.add(m.group(1))
            self.assertEqual(rel, m.group(1) + "/SKILL.md")
            b = json.loads(m.group(2))
            self.assertTrue(20 < len(b) <= 1024, rel)
            quelle = re.search(r"steht in `([^`]+)`", inhalt).group(1)
            self.assertTrue(os.path.isfile(os.path.join(WURZEL, quelle)), quelle)             # der Verweis zeigt auf eine Datei
        self.assertEqual(namen, {"amw-befehle", "amw-automatismen", "amw-fehlerbehebung", "amw-anleitungen", "amw-hilfe"})

    def test_beschreibungen_kurz(self):
        """Name und Beschreibung jedes Skills stehen in jeder Sitzung – zusammen klein halten (sonst frisst das den Gewinn)."""
        gesamt = 0
        for rel, inhalt in skills.skills().items():
            b = json.loads(re.search(r"description: (\".*\")", inhalt).group(1))
            self.assertLessEqual(len(b), 200, rel)
            gesamt += len(b) + len(rel)
        self.assertLess(gesamt, 1200)
        hilfe = skills.skills()["amw-hilfe/SKILL.md"]
        self.assertIn("steht in `doc/hilfe/planung.md`", hilfe)
        self.assertNotIn("README", hilfe)

    def test_anderer_ordner_absolut_nichts_geloescht(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            ziel = os.path.join(d, ".claude", "skills")
            os.makedirs(os.path.join(ziel, "amw-alt"))
            namen, verwaist = skills.bauen(ziel)
            self.assertEqual(verwaist, ["amw-alt"])
            self.assertTrue(os.path.isdir(os.path.join(ziel, "amw-alt")))
            with open(os.path.join(ziel, "amw-befehle", "SKILL.md"), encoding="utf-8") as f:
                quelle = re.search(r"steht in `([^`]+)`", f.read()).group(1)
            self.assertTrue(os.path.isabs(quelle) and os.path.isfile(quelle), quelle)


class Messung(Grund):
    def test_hebel7_und_basis(self):
        rc, aus = self.befehl("messung", "--hebel7", "--von", "CC1")
        self.assertEqual(rc, 0)
        self.assertIn("CC1", aus)
        self.assertRegex(aus, r"CC1 +Kontext +\d+ Zeilen")
        self.assertNotEqual(self.befehl("messung", "--hebel7", "--basis", "--von", "CC1")[0], 0)     # nur Lead oder Mensch
        self.assertEqual(self.befehl("messung", "--hebel7", "--basis", "--von", "TL")[0], 0)
        e = self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'basis_hebel7'").fetchone()
        m = {x["agent"]: x for x in json.loads(e["text"])["agenten"]}
        self.assertEqual(set(m), {"TL", "CC1"})
        self.assertGreater(m["CC1"]["kontext_zeichen"], 100)


if __name__ == "__main__":
    unittest.main()
