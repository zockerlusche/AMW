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
        from amw import betrieb
        for _ in range(frist * 2):
            if self.zustand(aid) in ziele:
                return self.zustand(aid)
            betrieb.warteschlange(self.con)                       # wie der Dienst: eingereihte Läufe starten, wenn sie dürfen
            time.sleep(0.5)
        self.fail(f"A{aid} blieb {self.zustand(aid)}")

    def entschieden(self, aid, frist=60):
        for _ in range(frist * 2):
            if self.con.execute("SELECT 1 FROM plan_ereignis WHERE aufgabe_id = ? AND art = 'paket_entscheidung'", (aid,)).fetchone():
                return True
            time.sleep(0.5)
        return False

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
        self.assertTrue(any(f"A{aid} gestartet als Headless 1" in x for x in aus), aus)
        v = disponent.vermerk(self.con, self.pid, aid)
        self.assertEqual(v["basis"], g(self.repo, "rev-parse", "main"))                          # Basis vom Vorbereiten
        self.assertEqual(self.warten(aid, ("merge_reihe", "wartet_interaktiv", "abgebrochen", "unklar")), "merge_reihe")
        self.assertTrue(self.entschieden(aid))                                                     # A2105: danach sichern und archivieren, dann der Entscheid
        e = [json.loads(r[0]) for r in self.con.execute("SELECT text FROM plan_ereignis WHERE aufgabe_id = ? AND art = 'paket_entscheidung'",
                                                        (aid,))]
        self.assertEqual([x["zeile"] for x in e], ["E7"])
        lauf = self.con.execute("SELECT status, beschreibung FROM lauf WHERE aufgabe_id = ?", (aid,)).fetchone()
        self.assertEqual((lauf[0], lauf[1]), ("fertig", f"Prüfung C A{aid}"))                     # über die Lauf-Schlange
        self.assertEqual(self.con.execute("SELECT count(*) FROM plan_ereignis WHERE aufgabe_id = ? AND art = 'kosten'", (aid,)).fetchone()[0], 1)
        self.assertEqual(disponent.belegte_plaetze(self.con, self.pid), {})                       # A2105: Platz frei nach E7
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
        self.assertEqual(self.warten(aid, ("abgebrochen",), 180), "abgebrochen")                 # unter Last (Gesamtlauf) dauert es länger
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
            b = db.einfuegen(self.con, "bogen", projekt_id=self.pid, nr=12, titel="Mischbetrieb", status="aktiv", angelegt_von="TL",
                             angelegt_utc=db.jetzt())
        self.assertNotEqual(b, 12)                                                               # A1878: id ≠ nr, sonst prüft der Test nichts
        aid = self.paket(bogen=b, zustand="entwurf")
        aus = disponent.runde(self.con, prog("bauen"))
        self.assertTrue(any("kein startklares p-Paket in M12 „" in x for x in aus), aus)        # A2089: die Projektnummer, nicht die interne
        self.assertFalse(any(f"M{b} " in x for x in aus), aus)
        self.assertEqual(disponent.runde(self.con, prog("bauen")), [])                             # gleicher Anlass: nicht nochmal
        n = self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE 'Headless frei%'").fetchall()
        self.assertEqual(len(n), 1)
        self.assertIn(f"A{aid} plus reparieren [entwurf]", n[0][0])
        with db.schreiben(self.con):                                                             # alles fertig → neuer Anlass
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'x' WHERE id = ?", (aid,))
        aus = disponent.runde(self.con, prog("bauen"))
        self.assertTrue(any("M12 „Mischbetrieb“: alle p-Pakete fertig" in x for x in aus), aus)

    def vorbereitet(self, aid, basis_falsch=False):
        """Wie starten(): Platz vorbereiten, laeuft, Vermerk – für den Starter im selben Prozess."""
        p = platz.plaetze(self.con, self.pid)[0]
        r = platz.vorbereiten(p, self.repo, f"paket-A{aid}", aufgabe=aid)
        arbeitspaket.zustand_setzen(self.con, self.pid, "AMW", aid, "laeuft")
        with db.schreiben(self.con):
            vid = db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="AMW", art=disponent.VERMERK,
                               aufgabe_id=aid, text=json.dumps({"platz": 1, "basis": r["basis"], "zweig": "z", "starter_pid": None}))
        return p, r["basis"], vid

    def zeilen(self, aid):
        return [json.loads(x[0])["zeile"] + " " + json.loads(x[0])["code"] for x in
                self.con.execute("SELECT text FROM plan_ereignis WHERE aufgabe_id = ? AND art = 'paket_entscheidung' ORDER BY id", (aid,))]

    def test_vermerk_muss_zu_diesem_start_passen(self):
        """P272 (1): Basis und Vermerk kommen als Argument; ein alter oder fremder Vermerk führt nie zu Prüfung C."""
        self.plaetze()
        aid = self.paket()
        p, basis, vid = self.vorbereitet(aid)
        self.assertEqual(disponent.starter(self.pid, aid, 1, prog("bauen"), lauf_schlange=False, basis="0" * 40, vid=vid), "E1")
        self.assertEqual(self.zeilen(aid), ["E1 Vermerk fehlt"])
        b = self.paket()                                                                         # zweiter Start, neue Basis: nur der neue gilt
        p, alt_basis, alt_vid = self.vorbereitet(b)
        arbeitspaket.zustand_setzen(self.con, self.pid, "AMW", b, "unklar")
        arbeitspaket.zustand_setzen(self.con, self.pid, "AMW", b, "startklar")
        g(self.repo, "commit", "-q", "--allow-empty", "-m", "main geht weiter")
        p, neu_basis, neu_vid = self.vorbereitet(b)
        self.assertNotEqual(alt_basis, neu_basis)
        self.assertIsNone(disponent._vermerk_pruefen(self.con, self.pid, b, alt_vid, alt_basis, 1))     # alter Vermerk: nein
        self.assertEqual(disponent._vermerk_pruefen(self.con, self.pid, b, neu_vid, neu_basis, 1)["basis"], neu_basis)
        self.assertEqual(disponent.starter(self.pid, b, 1, prog("bauen"), lauf_schlange=False, basis=neu_basis, vid=neu_vid), "E7")

    def test_sperrmuster_des_projekts_im_diff_tor(self):
        """A1919: die Sperrmuster des Projekts gelten auch in Prüfung C – hier nach dem Start gesetzt (vor dem Start hielte schon
        Regel 5 das Paket an)."""
        self.plaetze()
        aid = self.paket()
        p, basis, vid = self.vorbereitet(aid)
        kern.projekt_einstellen(self.con, self.pid, "TL", sperrmuster="lib/rechnen.py")
        zeile = disponent.starter(self.pid, aid, 1, prog("bauen"), lauf_schlange=False, basis=basis, vid=vid)
        self.assertEqual(zeile, "E4")                                                           # sonst E7
        e = self.con.execute("SELECT text FROM plan_ereignis WHERE aufgabe_id = ? AND art = 'paket_entscheidung'", (aid,)).fetchall()
        self.assertIn('"code": "C/diff"', e[-1][0])
        self.assertTrue(self.con.execute("SELECT 1 FROM nachricht WHERE text LIKE ?", ("%Diff-Tor: gesperrt: lib/rechnen.py%",)).fetchone())

    def test_rueckschritt_tests_und_frist_je_projekt(self):
        """A1920: das Projekt ist nicht die AMW – ohne Einstellung keine Rückschritt-Tests, klar vermerkt (Entscheidung, Merge-Liste);
        mit regression_befehl läuft genau dieser, mit der Frist aus abnahme_frist_min."""
        from amw import mergeliste, pruefung_c
        self.plaetze()
        aid = self.paket()
        p, basis, vid = self.vorbereitet(aid)
        with mock.patch.object(pruefung_c, "pruefen", wraps=pruefung_c.pruefen) as c:
            self.assertEqual(disponent.starter(self.pid, aid, 1, prog("bauen"), lauf_schlange=False, basis=basis, vid=vid), "E7")
        self.assertEqual((c.call_args.kwargs["regression"], c.call_args.kwargs["frist"]), (None, 1800))
        e = json.loads(self.con.execute("SELECT text FROM plan_ereignis WHERE aufgabe_id = ? AND art = 'paket_entscheidung'"
                                        " ORDER BY id DESC LIMIT 1", (aid,)).fetchone()[0])
        self.assertEqual(e["ohne_regression"], pruefung_c.OHNE_REGRESSION)
        self.assertEqual(mergeliste.eintrag(self.con, self.pid, aid, diff=False)["ohne_regression"], pruefung_c.OHNE_REGRESSION)
        b = self.paket()
        kern.projekt_einstellen(self.con, self.pid, "TL", regression_befehl=f'"{sys.executable}" -c "raise SystemExit(1)"',
                                abnahme_frist_min="7")
        p, basis, vid = self.vorbereitet(b)
        with mock.patch.object(pruefung_c, "pruefen", wraps=pruefung_c.pruefen) as c:
            self.assertNotEqual(disponent.starter(self.pid, b, 1, prog("bauen"), lauf_schlange=False, basis=basis, vid=vid), "E7")
        self.assertEqual(c.call_args.kwargs["frist"], 420)
        self.assertIn("raise SystemExit(1)", c.call_args.kwargs["regression"])
        self.assertIn("Regressions-Kurzsuite rot", " ".join(r[0] for r in self.con.execute("SELECT text FROM nachricht WHERE aufgabe_id = ?", (b,))))

    def test_werkzeug_umgebung_des_projekts(self):
        """A1922: Arbeiter und Abnahme in Prüfung C bekommen die Werkzeug-Umgebung des Projekts."""
        from amw import arbeiter, pruefung_c
        self.plaetze()
        kern.projekt_einstellen(self.con, self.pid, "TL", arbeiter_umgebung='{"variablen": ["JAVA_HOME"]}')
        aid = self.paket()
        p, basis, vid = self.vorbereitet(aid)
        with mock.patch.object(arbeiter, "laufen", wraps=arbeiter.laufen) as a, \
                mock.patch.object(pruefung_c, "pruefen", wraps=pruefung_c.pruefen) as c:
            self.assertEqual(disponent.starter(self.pid, aid, 1, prog("bauen"), lauf_schlange=False, basis=basis, vid=vid), "E7")
        self.assertEqual(a.call_args.kwargs["umgebung_projekt"], {"variablen": ["JAVA_HOME"]})
        self.assertEqual(c.call_args.kwargs["werkzeuge"], {"variablen": ["JAVA_HOME"]})

    def test_nachbesserung_prueft_regel_7(self):
        """P272 (2): vor dem E5-Lauf gelten Wartungsmodus und Wochenlimit – im Wartungsmodus kein zweiter Lauf, sondern E6."""
        from amw import waechter
        self.plaetze()
        aid = self.paket(befehl="python -X utf8 -m unittest tests.test_immer_rot")
        with open(os.path.join(self.repo, "tests", "test_immer_rot.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write("import unittest\n\n\nclass T(unittest.TestCase):\n    def test_rot(self):\n        self.fail()\n")
        g(self.repo, "add", "-A")
        g(self.repo, "commit", "-q", "-m", "roter Test")
        p, basis, vid = self.vorbereitet(aid)
        waechter.wartung_an("Auslieferung der AMW")
        self.addCleanup(waechter.wartung_aus)
        self.assertEqual(disponent.starter(self.pid, aid, 1, prog("bauen"), lauf_schlange=False, basis=basis, vid=vid), "E6")
        self.assertEqual(self.zeilen(aid), ["E5 C/rot", "E6 Regel 7"])
        self.assertTrue(self.con.execute("SELECT 1 FROM plan_ereignis WHERE aufgabe_id = ? AND art = 'waechter' AND text LIKE '%Regel 7%'",
                                         (aid,)).fetchone())

    def test_notbremse_eines_anderen_platzes_zaehlt_nicht(self):
        """P272 (a): eine Notbremse auf Platz 2 macht das Paket auf Platz 1 nicht zu E1n."""
        self.plaetze()
        aid = self.paket()
        p, basis, vid = self.vorbereitet(aid)
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc="2099-01-01T00:00:00Z", von="Entwickler", art="notbremse",
                         text="Platz 2: Arbeiter samt Kindprozessen beendet")
        self.assertEqual(disponent.starter(self.pid, aid, 1, prog("bauen"), lauf_schlange=False, basis=basis, vid=vid), "E7")

    def test_notbremse_auf_demselben_headless_zaehlt(self):
        """A2018: der Eintrag heißt jetzt „Headless 1: …“ – auch ohne Aufgabe gilt er für das Paket dort, der alte Wortlaut weiter."""
        for wort in ("Headless", "Platz"):
            with self.subTest(wort=wort), db.schreiben(self.con):
                self.con.execute("DELETE FROM plan_ereignis WHERE art = 'notbremse'")
                db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc="2099-01-01T00:00:00Z", von="Entwickler", art="notbremse",
                             text=f"{wort} 1: Arbeiter samt Kindprozessen beendet")
                self.assertTrue(disponent._notbremse_seit(self.con, self.pid, "2026-01-01T00:00:00Z", 7, 1))
                self.assertFalse(disponent._notbremse_seit(self.con, self.pid, "2026-01-01T00:00:00Z", 7, 11))

    def test_platz_sperre(self):
        """P272 (b): wer den Platz gerade vorbereitet, hält die Sperre – ein zweiter Start nimmt ihn nicht."""
        self.plaetze()
        aid = self.paket()
        p = platz.plaetze(self.con, self.pid)[0]
        with disponent._Platzsperre(p):
            with self.assertRaises(disponent.PlatzBelegt):
                disponent.starten(self.con, self.pid, aid, p, self.repo, prog("bauen"))
        self.assertEqual(self.zustand(aid), "startklar")
        self.assertTrue(os.path.exists(os.path.join(os.path.dirname(p["klon"]), "platz1.sperre")))   # nie gelöscht

    def vermerk_setzen(self, aid, **werte):
        vid = disponent._vermerk_id(self.con, self.pid, aid)
        v = dict(disponent.vermerk(self.con, self.pid, aid), **werte)
        with db.schreiben(self.con):
            self.con.execute("UPDATE plan_ereignis SET text = ? WHERE id = ?", (json.dumps(v), vid))

    def test_fertiger_lauf_ohne_starter_wird_nachgeholt(self):
        """A1877 (i): Der Arbeiter ist fertig, der Starter starb vor der Auswertung (z. B. PC-Neustart) → der Dienst startet einen
        Nachhol-Starter (Prüfung C + Entscheidung aus dem Protokoll) statt E1; der rechnet E7, Meldung und Kosten werden nachgetragen."""
        self.plaetze()
        aid = self.paket()
        p, basis, vid = self.vorbereitet(aid)
        r = arbeiter.laufen(p, "plus soll addieren.", PRUEF, prog=prog("bauen"))                # Arbeiter fertig, nichts ausgewertet
        self.assertEqual(r["rc"], 0)
        self.vermerk_setzen(aid, starter_pid=999999)                                            # Starter tot
        proc = mock.Mock(pid=4242)
        with mock.patch("subprocess.Popen", return_value=proc) as popen:
            aus = disponent.runde(self.con, prog("bauen"))
        self.assertIn(f"A{aid}: Starter weg, Lauf fertig → Prüfung C wird nachgeholt (Starter 4242)", aus)
        befehl = popen.call_args[0][0]
        self.assertIn("--nachholen", befehl)
        self.assertEqual(befehl[befehl.index("--basis") + 1], basis)                              # Basis aus dem Vermerk
        self.assertTrue(disponent.vermerk(self.con, self.pid, aid)["nachholen"])
        self.assertEqual(self.zustand(aid), "laeuft")
        self.assertEqual(disponent.starter(self.pid, aid, 1, prog("kaputt"), lauf_schlange=False, basis=basis, vid=vid, nachholen=True),
                         "E7")                                                                   # kein neuer Arbeiter (Attrappe „kaputt“ liefe nie)
        self.assertEqual(self.zeilen(aid), ["E7 grün"])
        self.assertEqual(self.con.execute("SELECT count(*) FROM plan_ereignis WHERE aufgabe_id = ? AND art = 'kosten'", (aid,)).fetchone()[0], 1)

    def test_nachholen_nur_einmal_und_ohne_protokoll_e1(self):
        """A1877 (i): ohne fertiges Protokoll → E1 wie bisher; ein zweites Mal wird nicht nachgeholt (stirbt auch der Nachhol-Starter)."""
        self.plaetze()
        aid = self.paket()
        p, basis, vid = self.vorbereitet(aid)
        os.makedirs(arbeiter.ordner(p), exist_ok=True)
        with open(os.path.join(arbeiter.ordner(p), "lauf.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "result", "subtype": "success"}) + "\n")
        self.vermerk_setzen(aid, starter_pid=999999, nachholen=True)
        with mock.patch.object(disponent, "_nachholen") as nachholen:
            self.assertIn(f"A{aid}: Starter weg → E1", disponent.runde(self.con, prog("bauen")))
        nachholen.assert_not_called()
        b = self.paket()
        p, basis, vid = self.vorbereitet(b)
        os.remove(os.path.join(arbeiter.ordner(p), "lauf.jsonl")) if os.path.exists(os.path.join(arbeiter.ordner(p), "lauf.jsonl")) else None
        self.vermerk_setzen(b, starter_pid=999999)
        self.assertIn(f"A{b}: Starter weg → E1", disponent.runde(self.con, prog("bauen")))

    def test_frischer_vermerk_ohne_pid_ist_nicht_verwaist(self):
        """A1877 (ii), #29048: zwischen Vermerk und Eintragen der Starter-PID liegt ein kurzes Fenster – in den ersten 60 s nicht E1."""
        self.plaetze()
        aid = self.paket()
        self.vorbereitet(aid)
        self.vermerk_setzen(aid, start_utc=db.jetzt())
        self.assertEqual(disponent.runde(self.con, prog("bauen")), [])
        self.assertEqual(self.zustand(aid), "laeuft")
        self.vermerk_setzen(aid, start_utc="2026-01-01T00:00:00Z")                                # alt und ohne PID: verwaist
        self.assertIn(f"A{aid}: Starter weg → E1", disponent.runde(self.con, prog("bauen")))

    def test_handstart_nur_lead_mensch(self):
        aid = self.paket()
        with self.assertRaises(kern.AmwFehler):
            disponent.handstart(self.con, self.pid, aid, "CC1")
        with self.assertRaises(kern.AmwFehler) as e:                                              # ohne Plätze: Regel 10
            disponent.handstart(self.con, self.pid, aid, "TL")
        self.assertIn("Regel 10", str(e.exception))


if __name__ == "__main__":
    unittest.main()
