"""A2054 (TH167 Fassung 4, Lead F5389): nur Riskantes zum Lead – je Riskant-Regel eine Gegenprobe (riskant → der Lead liest,
harmlos → die AMW nimmt bei Grün selbst ab); Fenster-Pakete: Prüfung C angemeldet, E7 → Prüfung „grün“ mit Prüfer AMW und Beleg,
riskant → Prüfbitte an den Lead, rot → erst nachbessern, dann der Lead; Versions-Commit nur CHANGELOG/Version/VERSION;
Wochenmeldung; „Lead liest“ als Befehl und Planfeld."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import datetime
import io
import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from amw import betrieb, db, fensterpruefung, kern, riskant, wartegrund

OHNE = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db"), "LOCALAPPDATA": os.path.join(self.ordner.name, "lad")})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.repo = os.path.join(self.ordner.name, "projekt")
        os.makedirs(self.repo)
        self.git("init", "-q", "-b", "main")
        self.schreiben({"lib/x.py": "def f():\n    return 1\n", "tests/test_x.py": "import unittest\n\nclass T(unittest.TestCase):\n"
                        "    def test_a(self):\n        self.assertEqual(1, 1)\n\n    def test_b(self):\n        self.assertTrue(True)\n"})
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "a")
        self.basis = self.git("rev-parse", "HEAD").strip()
        kern.projekt_ordner_setzen(self.con, self.pid, self.repo)
        self.aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Etwas bauen", "CC1")

    def git(self, *a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", self.repo, *a], check=True, capture_output=True,
                              text=True, creationflags=OHNE).stdout

    def schreiben(self, dateien):
        for pfad, text in dateien.items():
            voll = os.path.join(self.repo, pfad)
            os.makedirs(os.path.dirname(voll), exist_ok=True)
            with open(voll, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)

    def zweig(self, name, dateien, weg=()):
        self.git("checkout", "-q", "-b", name, self.basis)
        self.schreiben(dateien)
        for w in weg:
            self.git("rm", "-q", w)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", name)
        kopf = self.git("rev-parse", "HEAD").strip()
        self.git("checkout", "-q", "main")
        return kopf

    def regeln(self, dateien, weg=(), befund=None, name="z"):
        kopf = self.zweig(name, dateien, weg)
        return [r for r, _ in riskant.einordnen(self.con, self.pid, self.aid, riskant.aus_git(["git", "-C", self.repo], self.basis, kopf), befund)]


class Regeln(Grund):
    def test_harmlos_keine_regel(self):
        self.assertEqual(self.regeln({"lib/x.py": "def f():\n    return 2\n", "lib/y.py": "Y = 1\n"}), [])
        self.assertIn("keine Regel getroffen", riskant.beleg([]))
        self.assertIn(riskant.VERSION, riskant.beleg([]))

    def test_je_regel_riskant(self):
        faelle = {
            "server": {"web/api.php": "<?php echo 1;\n"},
            "schutz": {"amw/kern.py": "X = 1\n"},
            "schema": {"lib/m.py": "con.execute('ALTER TABLE x ADD y')\n"},
            "g12": {"lib/x.py": "import shutil\nshutil.rmtree(p)\n"},
            "pruefung": {"amw/testlauf.py": "X = 1\n"},
            "claude_p": {"amw/planer.py": "befehl = ['claude', '-p', 'x']\n"},
            "oberflaeche": {"doc/hilfe/neu.md": "Hilfe\n"},
        }
        for regel, dateien in faelle.items():
            with self.subTest(regel=regel):
                self.assertIn(regel, self.regeln(dateien, name=f"z-{regel}"))
        self.assertIn("aussen", self.regeln({"lib/x.py": "u = 1\n"}, befund={"aussen": [("lib/x.py", "https://x.example")]}, name="z-aussen"))
        self.assertIn("g12", self.regeln({"lib/x.py": "tagesgrenze = 5\n"}, name="z-kosten"))
        self.assertIn("schema", self.regeln({"amw/schema.sql": "CREATE TABLE x (a);\n"}, name="z-schema2"))

    def test_pruefung_selbst_auch_stufe_arbeiter_rueckmeldung(self):
        """A2070 (Lead #32305): wer pruefstufe.py, arbeiter.py oder rueckmeldung.py ändert, ändert die Prüfung – der Lead liest."""
        for pfad in ("amw/pruefstufe.py", "amw/arbeiter.py", "amw/rueckmeldung.py"):
            with self.subTest(pfad=pfad):
                self.assertIn("pruefung", self.regeln({pfad: "X = 1\n"}, name="z-" + pfad.split("/")[1][:-3]))
        self.assertNotIn("pruefung", self.regeln({"lib/stufe.py": "X = 1\n"}, name="z-gegen"))          # Gegenprobe
        self.assertIn("v2", riskant.VERSION)

    def test_tests_geschwaecht(self):
        self.assertIn("tests_geschwaecht", self.regeln({}, weg=("tests/test_x.py",), name="z-weg"))
        self.assertIn("tests_geschwaecht", self.regeln({"tests/test_x.py": "import unittest\n\nclass T(unittest.TestCase):\n"
                                                        "    def test_a(self):\n        pass\n"}, name="z-weniger"))
        self.assertIn("tests_geschwaecht", self.regeln({"tests/test_y.py": "import unittest\n\n@unittest.skip('x')\nclass U(unittest.TestCase):\n"
                                                        "    def test_c(self):\n        self.assertTrue(1)\n"}, name="z-skip"))
        self.assertEqual(self.regeln({"tests/test_y.py": "import unittest\n\nclass U(unittest.TestCase):\n    def test_c(self):\n"
                                      "        self.assertTrue(1)\n"}, name="z-mehr"), [])             # Gegenprobe: neuer Test

    def test_art_lead_liest_auffaellig(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET art = 'sicherheit' WHERE id = ?", (self.aid,))
        self.assertIn("schutz", self.regeln({"lib/x.py": "Z = 1\n"}, name="z-art"))
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET art = NULL WHERE id = ?", (self.aid,))
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="TL", art="lead_liest", aufgabe_id=self.aid,
                         text=json.dumps({"an": True}))
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="AMW", art="paket_entscheidung",
                         aufgabe_id=self.aid, text=json.dumps({"zeile": "E4"}))
        r = self.regeln({"lib/x.py": "Z = 2\n"}, name="z-ll")
        self.assertIn("lead_liest", r)
        self.assertIn("auffaellig", r)


class Fenster(Grund):
    def ereignis(self, kopf, zweig="a1"):
        with db.schreiben(self.con):
            eid = db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="CC1", art=fensterpruefung.ANGEMELDET,
                               aufgabe_id=self.aid, text=json.dumps({"zweig": zweig, "kopf": kopf, "von": "CC1"}))
        return self.con.execute("SELECT * FROM plan_ereignis WHERE id = ?", (eid,)).fetchone()

    def gruen(self, kopf):
        return {"code": None, "kopf": kopf, "basis": self.basis, "geaendert": ["lib/x.py"], "aussen": [], "geheim": [],
                "abnahme": {"befund": None, "ausgabe": "Ran 3 tests in 0.1s\n\nOK"}, "regression": None, "sprache": None}

    def pruefbitte_ohne_git(self):
        return contextlib.ExitStack()

    def test_e7_harmlos_gruen_der_amw_mit_beleg(self):
        kopf = self.zweig("a1", {"lib/x.py": "def f():\n    return 3\n"})
        with db.schreiben(self.con):
            fensterpruefung.warten_auf(self.con, self.pid, "CC1", self.aid)
        r = fensterpruefung.entscheiden(self.con, self.pid, self.aid, self.ereignis(kopf), self.gruen(kopf), lauf=77)
        self.assertEqual((r["zeile"], r["riskant"]), ("E7", []))
        p = self.con.execute("SELECT * FROM pruefung WHERE id = ?", (r["pruefung"],)).fetchone()
        self.assertEqual((p["pruefer"], p["ergebnis"], p["sha"], p["bauer"]), ("AMW", "gruen", kopf, "CC1"))
        for teil in ("Lauf L77", "Abnahme grün (3 Tests)", "Sprachprüfung", "keine Regel getroffen", riskant.VERSION):
            self.assertIn(teil, p["bemerkung"])
        self.assertEqual(wartegrund.offene(self.con, self.aid), [])                               # Grund pruefung:C-A… erledigt

    def test_e7_riskant_pruefbitte_an_den_lead(self):
        kopf = self.zweig("a1", {"lib/x.py": "import shutil\nshutil.rmtree(p)\n"})
        with mock.patch.object(betrieb, "pruefbitte", return_value=91) as pb:
            r = fensterpruefung.entscheiden(self.con, self.pid, self.aid, self.ereignis(kopf), self.gruen(kopf))
        self.assertEqual(r["zeile"], "E7")
        self.assertEqual([x for x, _ in r["riskant"]], ["g12"])
        self.assertEqual(r["pruefung"], 91)
        self.assertIn("g12", pb.call_args[0][6])                                                  # Gründe in den Punkten
        self.assertEqual(self.con.execute("SELECT count(*) FROM pruefung WHERE pruefer = 'AMW'").fetchone()[0], 0)
        an_mensch = self.con.execute("SELECT count(*) FROM empfang WHERE agent = ?", (kern.ENTWICKLER,)).fetchone()[0]
        self.assertGreaterEqual(an_mensch, 1)                                                     # g12: zusätzlich an den Menschen

    def test_rot_erst_nachbessern_dann_lead(self):
        kopf = self.zweig("a1", {"lib/x.py": "def f():\n    return 4\n"})
        rot = dict(self.gruen(kopf), code="C/rot", grund="Abnahme rot", abnahme={"befund": "C/rot", "ausgabe": "FAILED (failures=1)"})
        r = fensterpruefung.entscheiden(self.con, self.pid, self.aid, self.ereignis(kopf), rot)
        self.assertEqual(r["zeile"], "E5")
        auftrag = self.con.execute("SELECT n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = 'CC1'"
                                   " AND n.art = 'auftrag'").fetchone()
        self.assertIn("bitte nachbessern", auftrag["kurz"])
        self.assertIn("FAILED (failures=1)", auftrag["text"])
        with mock.patch.object(betrieb, "pruefbitte", return_value=92):
            r2 = fensterpruefung.entscheiden(self.con, self.pid, self.aid, self.ereignis(kopf), rot)
        self.assertEqual((r2["zeile"], r2["pruefung"]), ("E6", 92))                                # zweites Rot: der Lead liest

    def test_anmelden_und_runde(self):
        kopf = self.zweig("a1", {"lib/x.py": "def f():\n    return 5\n"})
        eid = fensterpruefung.anmelden(self.con, self.pid, self.aid, "a1", "CC1")
        self.assertEqual(json.loads(self.con.execute("SELECT text FROM plan_ereignis WHERE id = ?", (eid,)).fetchone()[0])["kopf"], kopf)
        gestartet = []
        self.assertEqual(len(fensterpruefung.runde(self.con, starten=lambda ziel, *a: gestartet.append(a))), 1)
        self.assertEqual(fensterpruefung.runde(self.con, starten=lambda ziel, *a: gestartet.append(a)), [])   # nicht doppelt
        self.assertEqual(gestartet, [(eid,)])
        with self.assertRaisesRegex(kern.AmwFehler, "Zweig gibt-es-nicht"):
            fensterpruefung.anmelden(self.con, self.pid, self.aid, "gibt-es-nicht", "CC1")


class Pruefen(Grund):
    """Die volle Prüfung C auf einem echten Zweig: frischer Checkout genau des Kopfs, Abnahme – grün und (Gegenprobe) rot."""

    def setUp(self):
        super().setUp()
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET pruefbefehl = 'python -m unittest discover -s tests', dateibereich = 'lib/, tests/'"
                             " WHERE id = ?", (self.aid,))

    def test_gruen_und_rot(self):
        kopf = self.zweig("a-gruen", {"lib/x.py": "def f():\n    return 1\n\nY = 2\n"})
        b = fensterpruefung.pruefen(self.con, self.pid, self.aid, "a-gruen", kopf)
        self.assertIsNone(b["code"], b.get("grund"))
        ab = dict(b["abnahme"] or {})
        self.assertEqual(ab["rc"], 0)
        self.assertIn("Ran 2 tests", ab["ausgabe"])
        kopf = self.zweig("a-rot", {"tests/test_x.py": "import unittest\n\nclass T(unittest.TestCase):\n    def test_a(self):\n"
                                    "        self.assertEqual(1, 2)\n\n    def test_b(self):\n        self.assertTrue(True)\n"})
        b = fensterpruefung.pruefen(self.con, self.pid, self.aid, "a-rot", kopf)
        self.assertEqual(b["code"], "C/rot")
        b = fensterpruefung.pruefen(self.con, self.pid, self.aid, "a-gruen", "0" * 40)          # Kopf weicht ab
        self.assertEqual(b["code"], "C/technik")


class Versionscommit(Grund):
    def kette(self):
        from amw import auslieferung
        k = auslieferung.Kette.__new__(auslieferung.Kette)
        k.con, k.pid, k.repo, k.erledigt = self.con, self.pid, self.repo, []
        k.extern = lambda befehl, ordner: (0, subprocess.run(befehl, cwd=ordner, capture_output=True, text=True, creationflags=OHNE).stdout)
        return k

    def test_nur_changelog_version_versionsdatei(self):
        art = {"modus": "datei", "version_datei": "amw/__init__.py", "changelog": "CHANGELOG.md"}
        kopf = self.zweig("gut", {"CHANGELOG.md": "## 1.0.1\n", "amw/__init__.py": "__version__ = '1.0.1'\n", "web/inc/VERSION": "1.0.1\n"})
        self.assertEqual(self.kette().versions_commits(kopf, art), [])
        kopf = self.zweig("schlecht", {"CHANGELOG.md": "## 1.0.1\n", "amw/__init__.py": "__version__ = '1.0.1'\n", "lib/x.py": "X = 9\n"})
        f = self.kette().versions_commits(kopf, art)
        self.assertEqual(len(f), 1)
        self.assertIn("lib/x.py", f[0])


class Messen(Grund):
    def test_wochenmeldung_einmal_mit_ruecknahme(self):
        jetzt = datetime.datetime(2026, 11, 30, 9, 0, tzinfo=datetime.timezone.utc)               # Montag
        vorige = "2026-11-25T10:00:00Z"
        zweite = kern.aufgabe_neu(self.con, self.pid, "TL", "Noch eins", "CC1")
        with db.schreiben(self.con):
            for aid, zeile in ((self.aid, "E7"), (zweite, "E7"), (zweite, "E8")):
                db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=vorige, von="AMW", art="paket_entscheidung",
                             aufgabe_id=aid, text=json.dumps({"zeile": zeile}))
        self.assertEqual(fensterpruefung.bericht_runde(self.con, jetzt), [f"Bericht 2026-W48 Projekt {self.pid}"])
        m = self.con.execute("SELECT kurz, text FROM nachricht WHERE kurz LIKE 'Woche 2026-W48%'").fetchone()
        self.assertIn("2 von 2 Paketen automatisch abgenommen, 1 danach zurück", m["kurz"])
        self.assertIn(f"A{zweite}", m["text"])
        self.assertEqual(fensterpruefung.bericht_runde(self.con, jetzt), [])                       # einmal je Woche


class LeadLiest(Grund):
    def cli(self, *args, von="TL"):
        from amw import cli
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_AGENT": ""}), contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["paket", *args, "--projekt", "P", "--von", von])
        return rc, aus.getvalue()

    def test_befehl_und_planfeld(self):
        rc, aus = self.cli("lead-liest", str(self.aid))
        self.assertEqual(rc, 0, aus)
        self.assertTrue(riskant.lead_liest(self.con, self.aid))
        rc, aus = self.cli("lead-liest", str(self.aid), "--aus")
        self.assertFalse(riskant.lead_liest(self.con, self.aid))
        rc, aus = self.cli("lead-liest", str(self.aid), von="CC1")
        self.assertEqual(rc, 1)                                                                    # nur Lead oder Mensch
        from amw import planer
        roh = {"nichts_zu_bauen": False, "meilensteine": [{"schluessel": "M1", "titel": "Erst", "endet_mit": "bericht"}],
               "pakete": [{"schluessel": "P1", "meilenstein": "M1", "titel": "Konzepttext", "auftrag": "x", "groesse": "S", "art": "text",
                           "ausfuehrung": "agent", "fertig_quelle": "commit", "nach": [], "interaktiv_grund": "Urteil", "lead_liest": True}]}
        daten = planer.pruefen(roh, self.con, self.pid) if planer.pruefen.__code__.co_argcount >= 3 else planer.pruefen(roh)
        pakete = (daten[0] if isinstance(daten, tuple) else daten)["pakete"]
        self.assertTrue(pakete[0]["lead_liest"])


if __name__ == "__main__":
    unittest.main()
