"""Bündeln automatisch (A1876, D1306, CCamwTL #29279): freigegebene p-Pakete im eigenen Arbeitsbaum aufsetzen, Konflikt → E8
(Nachfolger bleiben draußen), Versions-Commit mit Nummer nach KR1 und CHANGELOG aus den Hinweisen, Diff-Tor, neutrale
git-Umgebung, GRÜN/Merge-OK gehen per patch-id mit."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os

from amw import arbeitspaket, betrieb, buendel, db, kern, mergeliste
from tests.test_mergeliste import Grund, g, schreiben


class Basis(Grund):
    def setUp(self):
        super().setUp()
        schreiben(self.repo, "amw/__init__.py", '__version__ = "1.2.3"\n')
        schreiben(self.repo, "CHANGELOG.md", "# Änderungen\n\nKopf bleibt oben.\n\n## 1.2.3 – 01.11.2026 · Alt\n- alt\n")
        g(self.repo, "add", "-A")
        g(self.repo, "commit", "-q", "-m", "version")
        self.plaetze(4)
        for k, v in (("version_datei", "amw/__init__.py"), ("changelog_datei", "CHANGELOG.md"),
                     ("gesamtlauf_befehl", "python -c pass")):
            kern.projekt_einstellen(self.con, self.pid, "TL", **{k: v})

    def paket(self, titel, dateien, nr, hinweis=None, gruppe=None):
        aid, kopf, _ = self.bereit(titel, dateien, nr)
        if hinweis:
            with db.schreiben(self.con):
                self.con.execute("UPDATE aufgabe SET hinweis = ?, hinweis_gruppe = ? WHERE id = ?", (hinweis, gruppe, aid))
        r = mergeliste.freigeben(self.con, self.pid, "TL", [aid])
        self.assertTrue(r[0]["ok"], r)
        return aid

    def datei(self, sha, rel):
        return g(self.repo, "show", f"{sha}:{rel}")


class Buendeln(Basis):
    def test_zwei_pakete_ein_buendel_mit_version_und_changelog(self):
        a = self.paket("plus reparieren", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"}, 1,
                       hinweis="Plus rechnet jetzt richtig.", gruppe="neu")
        b = self.paket("minus dazu", {"lib/minus.py": "def minus(a, b):\n    return a - b\n"}, 2)
        r = buendel.buendeln(self.con, self.pid, "TL", starten=False)
        self.assertEqual((r["version"], r["zweig"], [p["id"] for p in r["drin"]], r["raus"]), ("1.3.0", "buendel-1.3.0", [a, b], []))
        self.assertEqual(g(self.repo, "rev-parse", "buendel-1.3.0"), r["sha"])
        self.assertEqual(g(self.repo, "log", "-1", "--format=%s|%an", r["sha"]), "1.3.0: Bündel (2 Pakete)|AMW-Bündel")
        self.assertEqual(g(self.repo, "diff", "--name-only", f"{r['sha']}~1", r["sha"]).split(), ["CHANGELOG.md", "amw/__init__.py"])
        self.assertIn("return a + b", self.datei(r["sha"], "lib/rechnen.py"))
        self.assertIn("def minus", self.datei(r["sha"], "lib/minus.py"))
        self.assertEqual(self.datei(r["sha"], "amw/__init__.py"), '__version__ = "1.3.0"')
        log = self.datei(r["sha"], "CHANGELOG.md")
        self.assertTrue(log.startswith("# Änderungen\n\nKopf bleibt oben.\n\n## 1.3.0 – "), log[:80])
        self.assertIn("· Gebündelte Pakete\n- **Neu:** Plus rechnet jetzt richtig.\n\n## 1.2.3", log)
        self.assertNotIn("minus dazu", log)                                                    # ohne Hinweis keine Zeile
        self.assertEqual(g(self.repo, "rev-parse", "--abbrev-ref", "HEAD"), "main")             # Live-Ordner unberührt
        self.assertTrue(os.path.isdir(r["ordner"]) and r["ordner"].endswith("buendel"))
        for aid in (a, b):                                                                      # GRÜN + Merge-OK gingen mit
            self.assertTrue(betrieb.merge_ok(self.con, self.pid, aid, "buendel-1.3.0"), aid)
        self.assertEqual(len(r["uebernommen"]), 2, r["uebernommen"])
        e = json.loads(self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'buendel'").fetchone()[0])
        self.assertEqual((e["version"], e["drin"]), ("1.3.0", [a, b]))

    def test_patch_und_intern_ohne_hinweis(self):
        self.paket("Tests für plus", {"tests_plus.py": "x = 1\n"}, 1)
        r = buendel.buendeln(self.con, self.pid, "TL", titel="Tests", starten=False)
        self.assertEqual(r["version"], "1.2.4")
        self.assertIn("## 1.2.4 – ", self.datei(r["sha"], "CHANGELOG.md"))
        self.assertIn("· Tests\n- **Intern:** 1 Paket(e) ohne sichtbare Änderung", self.datei(r["sha"], "CHANGELOG.md"))

    def test_konflikt_geht_nach_e8_und_nachfolger_bleiben(self):
        a = self.paket("plus A", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"}, 1)
        b = self.paket("plus B", {"lib/rechnen.py": "def plus(a, b):\n    return b + a  # anders\n"}, 2)
        c = self.paket("nach B", {"lib/mal.py": "def mal(a, b):\n    return a * b\n"}, 3)
        with db.schreiben(self.con):
            self.con.execute("INSERT INTO abhaengigkeit (vor, nach) VALUES (?, ?)", (b, c))
        r = buendel.buendeln(self.con, self.pid, "TL", starten=False)
        self.assertEqual([p["id"] for p in r["drin"]], [a])
        raus = {p["id"]: p["grund"] for p in r["raus"]}
        self.assertEqual(raus[b], "Konflikt (E8)")
        self.assertIn(f"kommt nach A{b}", raus[c])
        self.assertEqual(arbeitspaket.lesen(self.con, b)["zustand"], "wartet_interaktiv")
        self.assertEqual(arbeitspaket.lesen(self.con, c)["zustand"], "merge_reihe")             # bleibt für später
        m = self.con.execute("SELECT e.agent FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE n.kurz LIKE ?",
                             (f"A{b}: Konflikt beim Bündeln%",)).fetchall()
        self.assertEqual([x[0] for x in m], ["TL"])
        self.assertEqual(g(self.repo, "status", "--porcelain"), "")
        self.assertEqual(g(r["ordner"], "status", "--porcelain", "--untracked-files=no"), "")   # kein halber cherry-pick

    def test_diff_tor_haelt_fremde_dateien_auf(self):
        self.paket("plus", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"}, 1)
        kern.projekt_einstellen(self.con, self.pid, "TL", buendel_schritt=json.dumps(
            {"befehl": 'python -c "open(\'lib/rechnen.py\', \'a\').write(\'# fremd\\n\'); open(\'stand.txt\', \'w\').write(\'x\')"',
             "dateien": ["stand.txt"]}))
        with self.assertRaisesRegex(buendel.BuendelFehler, "Diff-Tor.*lib/rechnen.py"):
            buendel.buendeln(self.con, self.pid, "TL", starten=False)
        self.assertNotEqual(g(self.repo, "branch", "--list", "buendel-*"), "buendel-1.2.4")    # nichts committet, kein Zweig
        self.assertEqual(g(self.repo, "branch", "--list", "buendel-*"), "")

    def test_nacharbeit_mit_erlaubter_datei(self):
        self.paket("plus", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"}, 1)
        kern.projekt_einstellen(self.con, self.pid, "TL", buendel_schritt=json.dumps(
            {"befehl": 'python -c "import os; open(\'web/VERSION\', \'w\').write(os.environ[\'AMW_DB\'][-10:])"', "dateien": ["web/*"]}))
        r = buendel.buendeln(self.con, self.pid, "TL", starten=False)
        self.assertEqual(self.datei(r["sha"], "web/VERSION"), "schritt.db")                    # nie die Live-Datenbank
        self.assertEqual(sorted(g(self.repo, "diff", "--name-only", f"{r['sha']}~1", r["sha"]).split()),
                         ["CHANGELOG.md", "amw/__init__.py", "web/VERSION"])

    def test_hooks_des_projekts_laufen_nicht(self):
        hooks = os.path.join(self.repo, ".git", "hooks")
        os.makedirs(hooks, exist_ok=True)
        with open(os.path.join(hooks, "pre-commit"), "w", encoding="utf-8", newline="\n") as f:
            f.write("#!/bin/sh\necho gelaufen > \"$(git rev-parse --show-toplevel)/HOOK.txt\"\nexit 1\n")
        self.paket("plus", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"}, 1)
        r = buendel.buendeln(self.con, self.pid, "TL", starten=False)
        self.assertTrue(r["sha"])
        self.assertFalse(os.path.exists(os.path.join(r["ordner"], "HOOK.txt")))

    def test_wer_darf_und_was_fehlt(self):
        self.paket("plus", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"}, 1)
        with self.assertRaisesRegex(kern.AmwFehler, "Lead oder der Mensch"):
            buendel.buendeln(self.con, self.pid, "CC1", starten=False)
        kern.projekt_einstellen(self.con, self.pid, "TL", version_datei="")
        with self.assertRaisesRegex(buendel.BuendelFehler, "version_datei"):
            buendel.buendeln(self.con, self.pid, "TL", starten=False)
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "TL", version_datei="../aussen.py")
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "CC1", changelog_datei="x.md")


class GesamtlaufUndRelease(Basis):
    def test_gruen_mit_lead_als_pruefer_meldung_und_release_nur_mit_seinem_ok(self):
        from amw import auslieferung
        a = self.paket("plus", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"}, 1, hinweis="Plus stimmt.", gruppe="neu")
        gestartet = []
        r = buendel.buendeln(self.con, self.pid, "TL", starten=lambda pid, z: gestartet.append((pid, z)) or 4711)
        self.assertEqual((gestartet, r["starter"]), ([(self.pid, "buendel-1.3.0")], 4711))          # Gesamtlauf im eigenen Prozess
        runden = []

        def warte(s):
            runden.append(s)
            self.assertLess(len(runden), 50, "Lauf kommt nicht dran")
        rc, lid = buendel.lauf_und_meldung(self.con, self.pid, "buendel-1.3.0", warte=warte)
        self.assertEqual(rc, 0)
        l = self.con.execute("SELECT status, rc, ergebnis FROM lauf WHERE id = ?", (lid,)).fetchone()
        self.assertEqual((l["status"], l["rc"]), ("fertig", 0))
        self.assertIn(f"Stand {r['sha']} sauber", l["ergebnis"])                                   # daran erkennt die Kette den Lauf
        p = self.con.execute("SELECT * FROM pruefung WHERE sha = ? AND zweig = 'buendel-1.3.0'", (r["sha"],)).fetchone()
        self.assertEqual((p["ergebnis"], p["pruefer"], p["bauer"], p["aufgabe_id"]), ("gruen", "TL", "AMW", a))
        m = self.con.execute("SELECT n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = 'TL'"
                             " AND n.kurz LIKE 'Bündel 1.3.0 bereit%'").fetchone()
        self.assertIsNotNone(m)
        self.assertIn("amw/__init__.py", m["text"])                                                # Versions-Diff (--stat)
        self.assertIn("- **Neu:** Plus stimmt.", m["text"])                                        # CHANGELOG-Abschnitt
        self.assertIn(f"amw release ausliefern --zweig buendel-1.3.0 --gesamtlauf L{lid}", m["text"])
        k = auslieferung.Kette(self.con, self.pid, "TL", self.repo, ausgabe=lambda _: None)
        with self.assertRaisesRegex(auslieferung.Stopp, "Merge-OK: keins für A"):                  # übernommenes OK zählt nicht
            k.pruefen("buendel-1.3.0", gesamtlauf=lid)
        betrieb.freigabe_merge(self.con, self.pid, "TL", a, "buendel-1.3.0")                       # der Lead gibt frei
        v = k.pruefen("buendel-1.3.0", gesamtlauf=lid)
        self.assertEqual((v["version"], v["sha"], v["lauf"]), ("1.3.0", r["sha"], lid))

    def test_rot_kein_gruen(self):
        self.paket("plus", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"}, 1)
        kern.projekt_einstellen(self.con, self.pid, "TL", gesamtlauf_befehl='python -c "raise SystemExit(3)"')
        r = buendel.buendeln(self.con, self.pid, "TL", starten=False)
        rc, lid = buendel.lauf_und_meldung(self.con, self.pid, r["zweig"], warte=lambda s: None)
        self.assertEqual(rc, 3)
        self.assertIsNone(self.con.execute("SELECT 1 FROM pruefung WHERE sha = ? AND bauer = 'AMW' AND zweig = ?",
                                           (r["sha"], r["zweig"])).fetchone())
        self.assertIsNotNone(self.con.execute("SELECT 1 FROM nachricht WHERE kurz LIKE ?", (f"Bündel 1.2.4: Gesamtlauf L{lid} rot%",)).fetchone())


class Einstieg(Basis):
    def test_fehler_im_eigenen_prozess_geht_an_den_lead(self):
        buendel.main([str(self.pid), "buendel-9.9.9"])                                         # gibt es nicht
        m = self.con.execute("SELECT kurz, text FROM nachricht WHERE kurz LIKE 'Bündel buendel-9.9.9: Gesamtlauf nicht möglich%'").fetchone()
        self.assertIsNotNone(m)
        self.assertIn("kein Bündel buendel-9.9.9", m["text"])


class Teile(Basis):
    def test_version_und_changelog(self):
        self.assertEqual((buendel.naechste_version('v = "2.9.9"', False), buendel.naechste_version("2.9.9", True)), ("2.9.10", "2.10.0"))
        with self.assertRaises(buendel.BuendelFehler):
            buendel.naechste_version("ohne Nummer", False)
        self.assertEqual(buendel.changelog_einfuegen("# K\n\ntext\n", "## 1.0.1 – x\n- y\n"), "# K\n\ntext\n\n## 1.0.1 – x\n- y\n")
        p = [{"hinweis": "B.", "hinweis_gruppe": "behoben"}, {"hinweis": "N.", "hinweis_gruppe": "neu"}, {"hinweis": None, "hinweis_gruppe": None}]
        self.assertEqual(buendel.changelog_abschnitt("1.1.0", "21.11.2026", "T", p), "## 1.1.0 – 21.11.2026 · T\n- **Neu:** N.\n- **Behoben:** B.\n")


if __name__ == "__main__":
    import unittest
    unittest.main()
