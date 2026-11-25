"""A2120: abgenommene Pakete (p und Fenster) per git auf main zusammensetzen – Reihenfolge nach Abhängigkeit, dann Abnahmezeit;
Konflikt → sauberer Abbruch mit Befund (Paket, Dateien, Meldung); Release-Kette/git auf main → „Lead liest“, Merge-OK beim Lead."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from amw import arbeitspaket, buendel, buendel_zusammensetzen as bz, db, kern, riskant

OHNE = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@unittest.skipUnless(shutil.which("git"), "git fehlt")
class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        o = self.ordner.name
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(o, "amw.db"), "LOCALAPPDATA": os.path.join(o, "lad")})
        u.start()
        self.addCleanup(u.stop)
        for k in ("AMW_AGENT", "AMW_PROJEKT"):
            os.environ.pop(k, None)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.repo = os.path.join(o, "projekt")
        os.makedirs(self.repo)
        self.git("init", "-q", "-b", "main")
        self.schreiben({"lib/x.py": "def f():\n    return 1\n", "lib/y.py": "Y = 1\n"})
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "basis")
        self.main = self.git("rev-parse", "main")
        kern.projekt_ordner_setzen(self.con, self.pid, self.repo)
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, platz_wurzel=os.path.join(o, "plaetze"), plaetze=1)

    def git(self, *a, ordner=None):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", ordner or self.repo, *a], check=True,
                              capture_output=True, text=True, encoding="utf-8", creationflags=OHNE).stdout.strip()

    def schreiben(self, dateien):
        for rel, text in dateien.items():
            pfad = os.path.join(self.repo, *rel.split("/"))
            os.makedirs(os.path.dirname(pfad), exist_ok=True)
            with open(pfad, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)

    def commit(self, zweig, *staende):
        """Zweig von main mit einem Commit je Stand ({pfad: text}); Rückgabe: Kopf."""
        self.git("checkout", "-q", "-b", zweig, self.main)
        for nr, dateien in enumerate(staende, 1):
            self.schreiben(dateien)
            self.git("add", "-A")
            self.git("commit", "-q", "-m", f"{zweig} {nr}")
        kopf = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "main")
        return kopf

    def entscheidung(self, aid, zeit, **text):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=zeit, von="AMW", art="paket_entscheidung",
                         aufgabe_id=aid, text=json.dumps(text))

    def p_paket(self, titel, zeit, *staende):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel, "CC1")
        arbeitspaket.setzen(self.con, self.pid, "TL", aid, art="p")
        kopf = self.commit(f"paket-A{aid}", *staende)
        for z in ("startklar", "laeuft", "abgegeben", "abnahme", "merge_reihe"):
            arbeitspaket.zustand_setzen(self.con, self.pid, "AMW", aid, z)
        self.entscheidung(aid, zeit, zeile="E7", kopf=kopf, quelle="projekt")
        return aid

    def pruefung(self, aid, zweig, sha, zeit, ergebnis="gruen", pruefer="AMW"):
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=aid, zweig=zweig, sha=sha, bauer="CC1",
                                pruefer=pruefer, ergebnis=ergebnis, angefragt_utc=zeit, ergebnis_utc=None if ergebnis == "offen" else zeit)

    def fenster(self, titel, zeit, *staende):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel, "CC1")
        self.pruefung(aid, f"fenster-A{aid}", self.commit(f"fenster-A{aid}", *staende), zeit)
        return aid

    def nach(self, vor, nach):
        with db.schreiben(self.con):
            self.con.execute("INSERT INTO abhaengigkeit (vor, nach) VALUES (?, ?)", (vor, nach))

    def merge_ereignis(self, aid, zweig, art="merge_ok"):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="TL", art=art, aufgabe_id=aid, text=zweig)

    def los(self):
        return bz.zusammensetzen(self.con, self.pid)

    def drin(self, r):
        return [p["id"] for p in r["drin"]]

    def raus(self, r):
        return {p["id"]: p["grund"] for p in r["raus"]}

    def markierungen(self, aid):
        return self.con.execute("SELECT count(*) FROM plan_ereignis WHERE aufgabe_id = ? AND art = ?", (aid, riskant.LEAD_LIEST)).fetchone()[0]


T1, T2, T3 = "2026-11-25T08:00:00Z", "2026-11-25T09:00:00Z", "2026-11-25T10:00:00Z"


class Zusammensetzen(Grund):
    def test_p_und_fenster_in_der_reihenfolge_der_abnahme(self):
        a = self.p_paket("p spät", T3, {"lib/a.py": "A = 1\n"})
        b = self.fenster("Fenster früh", T1, {"lib/b.py": "B = 1\n"}, {"lib/b.py": "B = 2\n"})    # zwei Commits
        r = self.los()
        self.assertTrue(r["ok"], r)
        self.assertEqual((self.drin(r), r["raus"], r["befund"]), ([b, a], [], None))
        self.assertEqual([(p["art"], p["abnahme"]) for p in r["drin"]], [("fenster", "AMW"), ("p", "AMW")])
        self.assertEqual(self.git("log", "--reverse", "--format=%s", f"{self.main}..{r['sha']}").split("\n"),
                         [f"fenster-A{b} 1", f"fenster-A{b} 2", f"paket-A{a} 1"])
        self.assertEqual(self.git("show", f"{r['sha']}:lib/b.py"), "B = 2")
        self.assertEqual(r["basis"], self.main)
        self.git("merge-base", "--is-ancestor", "main", r["sha"])                                 # steht auf main

    def test_main_und_projektordner_bleiben(self):
        self.p_paket("a", T1, {"lib/a.py": "A = 1\n"})
        self.los()
        self.assertEqual(self.git("rev-parse", "main"), self.main)
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "HEAD"), "main")
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_abhaengigkeit_geht_vor_abnahmezeit(self):
        a = self.fenster("zuerst abgenommen", T1, {"lib/a.py": "A = 1\n"})
        b = self.p_paket("Vorgänger", T3, {"lib/b.py": "B = 1\n"})
        c = self.fenster("unabhängig", T2, {"lib/c.py": "C = 1\n"})
        self.nach(b, a)
        self.assertEqual(self.drin(self.los()), [c, b, a])

    def test_vorgaenger_nicht_dabei_bleibt_mit_nachfolgern_draussen(self):
        offen = kern.aufgabe_neu(self.con, self.pid, "TL", "noch im Bau", "CC1")
        a = self.fenster("a", T1, {"lib/a.py": "A = 1\n"})
        b = self.fenster("b", T2, {"lib/b.py": "B = 1\n"})
        c = self.fenster("c", T3, {"lib/c.py": "C = 1\n"})
        self.nach(offen, a)
        self.nach(a, b)
        r = self.los()
        self.assertEqual(self.drin(r), [c])
        self.assertIn(f"A{offen}", self.raus(r)[a])
        self.assertIn(f"A{a}", self.raus(r)[b])
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'Test' WHERE id = ?", (offen,))
        self.assertEqual(self.drin(self.los()), [a, b, c])

    def test_kreis_haelt_nicht_endlos(self):
        a = self.fenster("a", T1, {"lib/a.py": "A = 1\n"})
        b = self.fenster("b", T2, {"lib/b.py": "B = 1\n"})
        self.nach(a, b)
        self.nach(b, a)
        r = self.los()
        self.assertEqual((self.drin(r), sorted(self.raus(r)), r["sha"]), ([], [a, b], None))

    def test_nur_abgenommenes(self):
        offen = self.fenster("Prüfung wieder offen", T1, {"lib/a.py": "A = 1\n"})
        self.pruefung(offen, f"fenster-A{offen}", self.main, T2, ergebnis="offen")
        rot = self.fenster("danach rot", T1, {"lib/b.py": "B = 1\n"})
        self.pruefung(rot, f"fenster-A{rot}", self.main, T2, ergebnis="rot")
        e4 = self.p_paket("p wieder E4", T1, {"lib/c.py": "C = 1\n"})
        self.entscheidung(e4, T2, zeile="E4", kopf=self.main)
        fertig = self.fenster("fertig", T1, {"lib/d.py": "D = 1\n"})
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'Test' WHERE id = ?", (fertig,))
        self.assertEqual(bz.kandidaten(self.con, self.pid), [])
        r = self.los()
        self.assertEqual((r["ok"], r["drin"], r["sha"]), (True, [], None))

    def test_fremdes_projekt_zaehlt_nicht(self):
        a = self.fenster("a", T1, {"lib/a.py": "A = 1\n"})
        with db.schreiben(self.con):
            zwei = db.einfuegen(self.con, "projekt", name="Zwei", angelegt_utc=db.jetzt())
        self.assertEqual(bz.kandidaten(self.con, zwei), [])
        self.assertEqual([p["id"] for p in bz.kandidaten(self.con, self.pid)], [a])

    def test_genau_der_abgenommene_stand(self):
        a = self.fenster("a", T1, {"lib/a.py": "A = 1\n"})
        self.git("checkout", "-q", f"fenster-A{a}")                                              # danach ungeprüft weitergebaut
        self.schreiben({"lib/a.py": "A = 'ungeprüft'\n"})
        self.git("commit", "-q", "-a", "-m", "ungeprüft")
        self.git("checkout", "-q", "main")
        r = self.los()
        self.assertEqual(self.git("show", f"{r['sha']}:lib/a.py"), "A = 1")

    def test_schon_in_main(self):
        a = self.fenster("per cherry-pick schon drin", T1, {"lib/a.py": "A = 1\n"})
        b = self.fenster("per merge schon drin", T2, {"lib/b.py": "B = 1\n"})
        c = self.fenster("neu", T3, {"lib/c.py": "C = 1\n"})
        self.git("merge", "-q", "--no-ff", "-m", "merge", f"fenster-A{b}")
        self.git("cherry-pick", f"fenster-A{a}")
        r = self.los()
        self.assertEqual((r["ok"], self.drin(r)), (True, [c]), r)
        self.assertIn("schon in main", self.raus(r)[a])
        self.assertIn("schon in main", self.raus(r)[b])

    def test_stand_fehlt_im_repo(self):
        a = kern.aufgabe_neu(self.con, self.pid, "TL", "weg", "CC1")
        self.pruefung(a, "weg", "1" * 40, T1)
        self.assertIn("nicht im Projekt-Repo", self.raus(self.los())[a])

    def test_offenes_buendel_sperrt(self):
        self.fenster("a", T1, {"lib/a.py": "A = 1\n"})
        with mock.patch.object(buendel, "offenes_buendel", return_value={"zweig": "buendel-9.9.9"}):
            with self.assertRaisesRegex(buendel.BuendelFehler, "buendel-9.9.9"):
                self.los()


class Konflikt(Grund):
    def test_abbruch_mit_befund_und_sauberem_baum(self):
        a = self.fenster("erst", T1, {"lib/x.py": "def f():\n    return 2\n"})
        b = self.p_paket("dann", T2, {"lib/x.py": "def f():\n    return 3\n", "lib/neu.py": "N = 1\n"})
        self.fenster("danach", T3, {"lib/c.py": "C = 1\n"})
        r = self.los()
        self.assertFalse(r["ok"])
        self.assertEqual((r["sha"], r["drin"]), (None, []))                                       # kein halbes Bündel
        f = r["befund"]
        self.assertEqual((f["aufgabe"], f["art"], f["zweig"], f["agent"], f["dateien"]), (b, "p", f"paket-A{b}", "CC1", ["lib/x.py"]))
        self.assertIn("CONFLICT", f["meldung"])
        self.assertEqual(f["nach"], [a])                                                          # mit diesen davor stößt es zusammen
        baum = r["ordner"]
        self.assertEqual(self.git("status", "--porcelain", ordner=baum), "")
        self.assertEqual(self.git("rev-parse", "HEAD", ordner=baum), self.main)
        self.assertFalse(os.path.exists(os.path.join(self.git("rev-parse", "--absolute-git-dir", ordner=baum), "CHERRY_PICK_HEAD")))
        self.assertEqual(self.git("rev-parse", "main"), self.main)

    def test_zweiter_commit_eines_fensters_konflikt_und_neuer_anlauf(self):
        a = self.fenster("erst", T1, {"lib/x.py": "def f():\n    return 2\n"})
        b = self.fenster("zwei Commits", T2, {"lib/neu.py": "N = 1\n"}, {"lib/x.py": "def f():\n    return 3\n"})
        self.assertEqual(self.los()["befund"]["aufgabe"], b)
        with db.schreiben(self.con):                                                              # Agent löst: verworfen → neuer Anlauf geht
            self.con.execute("UPDATE aufgabe SET status = 'verworfen', beleg = 'Test' WHERE id = ?", (b,))
        r = self.los()
        self.assertEqual((r["ok"], self.drin(r)), (True, [a]))
        self.assertEqual(self.git("ls-tree", "--name-only", r["sha"], "lib/").split(), ["lib/x.py", "lib/y.py"])   # nichts übrig

    def test_umlaut_im_pfad(self):
        self.fenster("erst", T1, {"lib/grün.py": "A = 1\n"})
        self.fenster("dann", T2, {"lib/grün.py": "A = 2\n"})
        self.assertEqual(self.los()["befund"]["dateien"], ["lib/grün.py"])

    def test_merge_commit_ist_ein_befund(self):
        a = self.fenster("mit Merge", T1, {"lib/a.py": "A = 1\n"})
        self.commit("seite", {"lib/s.py": "S = 1\n"})
        self.git("checkout", "-q", f"fenster-A{a}")
        self.git("merge", "-q", "--no-ff", "-m", "merge seite", "seite")
        kopf = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "main")
        self.pruefung(a, f"fenster-A{a}", kopf, T2)
        r = self.los()
        self.assertEqual((r["ok"], r["befund"]["aufgabe"]), (False, a))
        self.assertIn("Merge-Commit", r["befund"]["meldung"])


class LeadLiest(Grund):
    def test_release_kette_wartet_auf_merge_ok(self):
        a = self.fenster("Kette", T1, {"amw/auslieferung.py": "X = 1\n"})
        b = self.fenster("danach", T2, {"lib/b.py": "B = 1\n"})
        c = self.fenster("harmlos", T3, {"lib/c.py": "C = 1\n"})
        self.nach(a, b)
        r = self.los()
        self.assertEqual(self.drin(r), [c])
        self.assertIn("Merge-OK", self.raus(r)[a])
        self.assertIn(f"A{a}", self.raus(r)[b])
        self.assertTrue(riskant.lead_liest(self.con, a))
        self.assertFalse(riskant.lead_liest(self.con, c))
        self.los()
        self.assertEqual(self.markierungen(a), 1)                                                 # einmal, nicht je Lauf
        self.merge_ereignis(a, f"fenster-A{a}")
        r = self.los()
        self.assertEqual([(p["id"], p["abnahme"]) for p in r["drin"]], [(a, "Lead"), (b, "AMW"), (c, "AMW")])

    def test_merge_ok_fuer_anderen_zweig_gilt_nicht(self):
        a = self.fenster("Kette", T1, {"amw/auslieferung.py": "X = 1\n"})
        self.merge_ereignis(a, "anderer-zweig")
        self.assertEqual(self.drin(self.los()), [])

    def test_git_auf_main_im_code(self):
        faelle = ('git("merge", "--ff-only", sha)\n', 'subprocess.run(["git", "push", "origin", "main"])\n',
                  'git("update-ref", "refs/heads/main", sha)\n', 'git("branch", "-f", "main", sha)\n', 'os.system("git push")\n')
        for nr, zeile in enumerate(faelle):
            with self.subTest(zeile=zeile):
                a = self.fenster(f"git {nr}", T1, {f"lib/g{nr}.py": zeile})
                p = next(x for x in bz.kandidaten(self.con, self.pid) if x["id"] == a)
                self.assertIn("release_main", [x for x, _ in bz.einordnen(self.con, self.pid, self.repo, p)])

    def test_gegenprobe_harmlos(self):
        for nr, dateien in enumerate(({"lib/h.py": 'git("diff", "--stat", "main")\n'}, {"lib/i.py": "push = 1\nmain = 2\n"},
                                      {"tests/test_h.py": 'git("push", "origin", "main")\n'})):
            with self.subTest(dateien=dateien):
                a = self.fenster(f"h {nr}", T1, dateien)
                p = next(x for x in bz.kandidaten(self.con, self.pid) if x["id"] == a)
                self.assertEqual(bz.einordnen(self.con, self.pid, self.repo, p), [])

    def test_pfade_der_kette(self):
        for pfad in ("amw/auslieferung.py", "amw/releasetakt.py", "amw/buendel.py", "amw/buendel_zusammensetzen.py", "amw/mergeliste.py",
                     "amw/veroeffentlichung.py", "amw/versionsnummer.py", "amw/freigabereif.py", "AMW/Auslieferung.py"):
            self.assertTrue(bz.release_main({"geaendert": [pfad], "plus": [], "minus": []}), pfad)
        for pfad in ("amw/hilfen.py", "tests/test_buendel.py", "doc/automatismen.md"):
            self.assertEqual(bz.release_main({"geaendert": [pfad], "plus": [], "minus": []}), "", pfad)
        self.assertTrue(bz.release_main({"geaendert": ["lib/x.py"], "plus": [], "minus": [("lib/x.py", 'git("push", "origin", "main")')]}))

    def test_th167_f4_regeln_gelten_weiter(self):
        a = self.fenster("löscht", T1, {"lib/l.py": "import shutil\nshutil.rmtree(p)\n"})
        b = self.p_paket("vom Lead markiert", T2, {"lib/m.py": "M = 1\n"})
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="TL", art=riskant.LEAD_LIEST,
                         aufgabe_id=b, text=json.dumps({"an": True}))
        r = self.los()
        self.assertEqual((self.drin(r), sorted(self.raus(r))), ([], [a, b]))
        self.assertIn("g12", self.raus(r)[a])
        self.assertIn("lead_liest", self.raus(r)[b])

    def test_ohne_einordnung_nie_selbst(self):
        a = self.fenster("a", T1, {"lib/a.py": "A = 1\n"})
        with mock.patch.object(riskant, "aus_git", side_effect=RuntimeError("kaputt")):
            r = self.los()
        self.assertEqual(self.drin(r), [])
        self.assertIn("kaputt", self.raus(r)[a])

    def test_zurueckgenommenes_ok_haelt_auch_harmloses_draussen(self):
        a = self.fenster("a", T1, {"lib/a.py": "A = 1\n"})
        self.merge_ereignis(a, f"fenster-A{a}", art="merge_ok_zurueck")
        self.assertIn("zurückgenommen", self.raus(self.los())[a])


if __name__ == "__main__":
    unittest.main()
