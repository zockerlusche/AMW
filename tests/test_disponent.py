"""Disponent (A1874, M50 S6c): der Dienst startet startklare p-Pakete selbst – Wächter → Platz → rot vor Bau → Starter
(losgelöst) → Arbeiter → Prüfung C (über die Lauf-Schlange) → Entscheidung. Plätze = 0 → nichts. Mit Attrappe statt Claude."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from amw import arbeiter, arbeitspaket, db, disponent, kern, platz

OHNE = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ATTRAPPE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arbeiter_attrappe.py")
PRUEF = "python -X utf8 -m unittest tests.test_rechnen"


def prog(art):
    return [sys.executable, "-X", "utf8", ATTRAPPE, "--attrappe-art", art]


def g(ordner, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", ordner, *args], check=True, capture_output=True,
                          text=True, creationflags=OHNE).stdout.strip()


@unittest.skipUnless(shutil.which("git") and os.name == "nt", "git/Windows fehlt")
class Disponent(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        o = self.ordner.name
        self.pfad = os.path.join(o, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad, "LOCALAPPDATA": os.path.join(o, "lad")})
        u.start()
        self.addCleanup(u.stop)
        for k in ("AMW_AGENT", "AMW_PROJEKT"):
            os.environ.pop(k, None)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.repo = os.path.join(o, "projekt")
        dateien = {"lib/__init__.py": "", "lib/rechnen.py": "def plus(a, b):\n    return a - b\n", "tests/__init__.py": "",
                   "tests/test_rechnen.py": "import unittest\nfrom lib.rechnen import plus\n\n\nclass T(unittest.TestCase):\n"
                                            "    def test_plus(self):\n        self.assertEqual(plus(2, 2), 4)\n"}
        for name in ("test_abschotten", "test_live_schutz", "test_abnahme", "test_hilfen"):          # Regressions-Kurzsuite
            dateien[f"tests/{name}.py"] = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_da(self):\n        pass\n"
        for rel, text in dateien.items():
            pfad = os.path.join(self.repo, *rel.split("/"))
            os.makedirs(os.path.dirname(pfad), exist_ok=True)
            with open(pfad, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        g(o, "init", "-q", "-b", "main", self.repo)
        g(self.repo, "add", "-A")
        g(self.repo, "commit", "-q", "-m", "basis")
        kern.projekt_ordner_setzen(self.con, self.pid, self.repo)

    def plaetze(self, n=1):
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, platz_wurzel=os.path.join(self.ordner.name, "plaetze"), plaetze=n)

    def paket(self, befehl=PRUEF, bereiche="lib/", bogen=None, zustand="startklar"):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "plus reparieren", "CC1", auftrag="plus soll addieren.")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET pruefbefehl = ?, dateibereich = ?, bogen_id = ? WHERE id = ?", (befehl, bereiche, bogen, aid))
        arbeitspaket.setzen(self.con, self.pid, "TL", aid, art="p", modell="haiku", effort="low")
        if zustand != "entwurf":
            arbeitspaket.zustand_setzen(self.con, self.pid, "TL", aid, zustand)
        return aid

    def zustand(self, aid):
        self.con.execute("SELECT 1")                                          # frischer Stand der anderen Verbindung
        return arbeitspaket.lesen(self.con, aid)["zustand"]

    def warten(self, aid, ziele, frist=180):
        for _ in range(frist * 2):
            if self.zustand(aid) in ziele:
                return self.zustand(aid)
            time.sleep(0.5)
        self.fail(f"A{aid} blieb {self.zustand(aid)}")

    def test_ohne_plaetze_nichts(self):
        aid = self.paket()
        with mock.patch("subprocess.Popen") as popen:
            self.assertEqual(disponent.runde(self.con, prog("bauen")), [])
        popen.assert_not_called()
        self.assertEqual(self.zustand(aid), "startklar")

    def test_startet_selbst_bis_e7(self):
        """Ohne Zutun: Runde startet, Starter läuft losgelöst, Arbeiter baut, C über die Lauf-Schlange, E7 → merge_reihe."""
        self.plaetze()
        aid = self.paket()
        aus = disponent.runde(self.con, prog("bauen"))
        self.assertTrue(any(f"A{aid} gestartet auf Platz 1" in x for x in aus), aus)
        v = disponent.vermerk(self.con, self.pid, aid)
        self.assertEqual(v["basis"], g(self.repo, "rev-parse", "main"))                          # Basis vom Vorbereiten
        self.assertEqual(self.warten(aid, ("merge_reihe", "wartet_interaktiv", "abgebrochen", "unklar")), "merge_reihe")
        e = [json.loads(r[0]) for r in self.con.execute("SELECT text FROM plan_ereignis WHERE aufgabe_id = ? AND art = 'paket_entscheidung'",
                                                        (aid,))]
        self.assertEqual([x["zeile"] for x in e], ["E7"])
        lauf = self.con.execute("SELECT status, beschreibung FROM lauf WHERE aufgabe_id = ?", (aid,)).fetchone()
        self.assertEqual((lauf[0], lauf[1]), ("fertig", f"Prüfung C A{aid}"))                     # über die Lauf-Schlange
        self.assertEqual(self.con.execute("SELECT count(*) FROM plan_ereignis WHERE aufgabe_id = ? AND art = 'kosten'", (aid,)).fetchone()[0], 1)
        self.assertEqual(disponent.belegte_plaetze(self.con, self.pid), {1: aid})                 # Platz bleibt bis zum Merge
        self.assertEqual(disponent.runde(self.con, prog("bauen")), [])                             # nichts Neues zu starten

    def test_regel6_zurueckgestellt(self):
        self.plaetze()
        aid = self.paket(befehl="python -c pass")                                                 # schon vor dem Bau grün
        aus = disponent.runde(self.con, prog("bauen"))
        self.assertTrue(any("Regel 6" in x for x in aus), aus)
        self.assertEqual(self.zustand(aid), "zurueckgestellt")
        self.assertTrue(self.con.execute("SELECT 1 FROM nachricht WHERE kurz LIKE ?", (f"A{aid} nicht gestartet, Regel 6%",)).fetchone())

    def test_starter_ueberlebt_und_notbremse_wirkt(self):
        """Der Starter läuft weiter, wenn der Prozess endet, der ihn gestartet hat (wie bei einem Dienst-Neustart); die Notbremse
        wirkt weiter, danach E1n."""
        self.plaetze()
        aid = self.paket()
        helfer = ("import sys; sys.path.insert(0, r'%s'); from amw import db, disponent; c = db.verbinde();"
                  " print(disponent.runde(c, %r))" % (os.path.dirname(os.path.dirname(ATTRAPPE)), prog("haengt")))
        r = subprocess.run([sys.executable, "-X", "utf8", "-c", helfer], capture_output=True, text=True, creationflags=OHNE, timeout=120)
        self.assertIn("gestartet", r.stdout, r.stderr)                                           # der „Dienst“ ist schon wieder weg
        p = platz.plaetze(self.con, self.pid)[0]
        for _ in range(60):
            if disponent._job_besteht(p):
                break
            time.sleep(0.5)
        v = disponent.vermerk(self.con, self.pid, aid)
        self.assertTrue(disponent._lebt(v["starter_pid"]))
        self.assertTrue(disponent._job_besteht(p))
        self.assertEqual(disponent.runde(self.con, prog("bauen")), [])                             # lebt: kein „Starter weg“
        for k in ("AMW_AGENT", "CLAUDECODE", "CLAUDE_CODE_MESSAGING_SOCKET"):
            os.environ.pop(k, None)
        arbeiter.notbremse_ziehen(self.con, self.pid, p, kern.ENTWICKLER, aid)
        self.assertEqual(self.warten(aid, ("abgebrochen",), 60), "abgebrochen")
        e = None
        for _ in range(120):                                                                     # die Entscheidung kommt nach dem Zustand
            e = self.con.execute("SELECT text FROM plan_ereignis WHERE aufgabe_id = ? AND art = 'paket_entscheidung'", (aid,)).fetchone()
            if e:
                break
            time.sleep(0.5)
        self.assertEqual(json.loads(e[0])["zeile"], "E1n")                                         # Notbremse zählt nicht zur Fehlserie

    def test_verwaister_starter_e1(self):
        self.plaetze()
        aid = self.paket()
        p = platz.plaetze(self.con, self.pid)[0]
        platz.vorbereiten(p, self.repo, f"paket-A{aid}", aufgabe=aid)
        arbeitspaket.zustand_setzen(self.con, self.pid, "AMW", aid, "laeuft")
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="AMW", art=disponent.VERMERK,
                         aufgabe_id=aid, text=json.dumps({"platz": 1, "basis": "x", "zweig": "z", "starter_pid": 999999}))
        aus = disponent.runde(self.con, prog("bauen"))
        self.assertIn(f"A{aid}: Starter weg → E1", aus)
        self.assertEqual(self.zustand(aid), "abgebrochen")

    def test_weckruf_einmal_je_anlass(self):
        self.plaetze()
        with db.schreiben(self.con):
            b = db.einfuegen(self.con, "bogen", projekt_id=self.pid, nr=50, titel="Mischbetrieb", status="aktiv", angelegt_von="TL",
                             angelegt_utc=db.jetzt())
        aid = self.paket(bogen=b, zustand="entwurf")
        aus = disponent.runde(self.con, prog("bauen"))
        self.assertTrue(any("kein startklares p-Paket in M50" in x for x in aus), aus)
        self.assertEqual(disponent.runde(self.con, prog("bauen")), [])                             # gleicher Anlass: nicht nochmal
        n = self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE 'Platz frei%'").fetchall()
        self.assertEqual(len(n), 1)
        self.assertIn(f"A{aid} plus reparieren [entwurf]", n[0][0])
        with db.schreiben(self.con):                                                             # alles fertig → neuer Anlass
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'x' WHERE id = ?", (aid,))
        aus = disponent.runde(self.con, prog("bauen"))
        self.assertTrue(any("alle p-Pakete fertig" in x for x in aus), aus)

    def test_handstart_nur_lead_mensch(self):
        aid = self.paket()
        with self.assertRaises(kern.AmwFehler):
            disponent.handstart(self.con, self.pid, aid, "CC1")
        with self.assertRaises(kern.AmwFehler) as e:                                              # ohne Plätze: Regel 10
            disponent.handstart(self.con, self.pid, aid, "TL")
        self.assertIn("Regel 10", str(e.exception))


if __name__ == "__main__":
    unittest.main()
