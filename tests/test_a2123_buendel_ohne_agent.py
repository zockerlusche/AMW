"""A2123: Gesamtlauf und lokales Ausliefern eines Bündels ohne Agent – der echte Weg mit temporärem Repo: Zusammensetzen (A2120),
Version (A2121), Gesamtlauf über die Lauf-Schlange, grün → Freigabe der AMW mit Marke und Release-Kette, rot → teilen (A2122), Konflikt →
Paket draußen, gebaute Dateien kein Konflikt, Abbruch → main unverändert, kein Wartungsmodus, Meldung. Vorgaben CCamwTL #33743."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
from unittest import mock

from amw import auslieferung, betrieb, buendel, buendel_auslieferung as ba, db, kern, waechter
from tests.test_buendel_zusammensetzen import T1, T2, T3, Grund as ZGrund

BOESE = "python -c \"import os, sys; sys.exit(3 if os.path.exists('lib/boese.py') else 0)\""


class Grund(ZGrund):
    def setUp(self):
        super().setUp()
        self.schreiben({"amw/__init__.py": '__version__ = "1.2.3"\n', "CHANGELOG.md": "# Änderungen\n\n## 1.2.3 – 01.11.2026 · Alt\n- alt\n"})
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "version")
        self.main = self.git("rev-parse", "main")
        for k, v in (("version_datei", "amw/__init__.py"), ("changelog_datei", "CHANGELOG.md"), ("gesamtlauf_befehl", BOESE)):
            kern.projekt_einstellen(self.con, self.pid, "TL", **{k: v})
        w = mock.patch.object(waechter, "_datei", lambda: os.path.join(self.ordner.name, "waechter.json"))
        w.start()
        self.addCleanup(w.stop)
        self.ausgeliefert = []

    def an(self):
        with db.schreiben(self.con):                              # Einschalten nur durch den Menschen (NUR_MENSCH_WAHL)
            e = json.loads(self.con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (self.pid,)).fetchone()[0] or "{}")
            e[ba.SCHALTER] = "an"
            self.con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?", (json.dumps(e), self.pid))

    def kette(self, zweig, lid):
        """Die echte Kette prüft alle Vorbedingungen (auch die Marke); Fast-Forward und Tag wie sie, ohne Dienst-Neustart."""
        k = auslieferung.Kette(self.con, self.pid, "AMW", self.repo, ausgabe=lambda _: None, amw=False)
        v = k.pruefen(zweig, gesamtlauf=lid)
        self.git("merge", "--ff-only", "-q", v["sha"])
        self.git("tag", f"v{v['version']}", v["sha"])
        self.ausgeliefert.append((zweig, v["version"], v["sha"]))

    def los(self, **mehr):
        with mock.patch.object(ba, "ist_amw", return_value=True):
            return ba.ausfuehren(self.con, self.pid, kette=mehr.pop("kette", self.kette), warte=lambda s: None, **mehr)

    def ereignisse(self, art=ba.ART):
        return [json.loads(r[0]) for r in self.con.execute("SELECT text FROM plan_ereignis WHERE art = ? ORDER BY id", (art,))]

    def an_lead(self):
        return [r[0] for r in self.con.execute("SELECT n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = 'TL'"
                                               " ORDER BY n.id")]


class Gruen(Grund):
    def test_ausgeliefert_mit_version_marke_und_kette(self):
        self.an()
        a = self.p_paket("Plus", T1, {"lib/a.py": "A = 1\n"})
        b = self.p_paket("Minus", T2, {"lib/b.py": "B = 1\n"})
        self.assertEqual(self.los(), "ausgeliefert")
        (zweig, version, sha), = self.ausgeliefert
        self.assertEqual((zweig, version), ("buendel-1.2.4", "1.2.4"))
        self.assertEqual(self.git("rev-parse", "main"), sha)
        self.assertEqual(self.git("show", f"{sha}:lib/a.py"), "A = 1")
        self.assertIn("## 1.2.4", self.git("show", f"{sha}:CHANGELOG.md"))
        self.assertEqual(self.git("show", "--name-only", "--format=", sha).split(), ["CHANGELOG.md", "amw/__init__.py"])   # nur Versionsdateien
        p = {r["aufgabe_id"]: r for r in self.con.execute("SELECT * FROM pruefung WHERE sha = ? AND bauer = 'AMW'", (sha,))}
        self.assertEqual(sorted(p), sorted([a, b]))
        self.assertEqual({r["pruefer"] for r in p.values()}, {"AMW"})
        self.assertTrue(betrieb.merge_ok(self.con, self.pid, a, zweig))
        self.assertTrue(ba.marke(self.con, self.pid, zweig, sha))
        self.assertEqual([e["schritt"] for e in self.ereignisse()], ["zusammengesetzt", "gesamtlauf", "freigabe", "ausgeliefert"])
        self.assertIsNone(waechter.zustand()["wartung"])
        self.assertIsNone(buendel.offenes_buendel(self.con, self.pid))                       # buendel_ende geschrieben

    def test_ohne_schalter_endet_bei_bereit(self):
        a = self.p_paket("Plus", T1, {"lib/a.py": "A = 1\n"})
        self.assertEqual(self.los(), "bereit")
        self.assertEqual((self.ausgeliefert, self.git("rev-parse", "main")), ([], self.main))
        self.assertFalse(betrieb.merge_ok(self.con, self.pid, a, "buendel-1.2.4"))             # das OK gibt der Lead
        self.assertTrue(any(k.startswith("Bündel 1.2.4 bereit") for k in self.an_lead()))
        self.assertNotIn("freigabe", [e["schritt"] for e in self.ereignisse()])

    def test_andere_projekte_enden_bei_bereit(self):
        self.an()
        self.p_paket("Plus", T1, {"lib/a.py": "A = 1\n"})
        self.assertEqual(ba.ausfuehren(self.con, self.pid, kette=self.kette, warte=lambda s: None), "bereit")


class Marke(Grund):
    def test_merge_ok_der_amw_ohne_marke_weist_die_kette_ab(self):
        a = self.p_paket("Plus", T1, {"lib/a.py": "A = 1\n"})
        self.assertEqual(self.los(), "bereit")
        lid = self.ereignisse()[-1]["lauf"]
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="AMW", art="merge_ok", aufgabe_id=a,
                         text="buendel-1.2.4")
        k = auslieferung.Kette(self.con, self.pid, "AMW", self.repo, ausgabe=lambda _: None, amw=False)
        with self.assertRaisesRegex(auslieferung.Stopp, "Merge-OK: keins für A"):
            k.pruefen("buendel-1.2.4", gesamtlauf=lid)


class Rot(Grund):
    def test_geteilt_gruenes_ausgeliefert_schuldiges_als_befund(self):
        self.an()
        a = self.p_paket("Gut", T1, {"lib/a.py": "A = 1\n"})
        b = self.p_paket("Böse", T2, {"lib/boese.py": "B = 1\n"})
        self.assertEqual(self.los(), "ausgeliefert")
        (zweig, version, sha), = self.ausgeliefert
        self.assertEqual(self.git("show", f"{sha}:lib/a.py"), "A = 1")
        self.assertNotIn("lib/boese.py", self.git("ls-tree", "-r", "--name-only", sha))
        befund, = self.ereignisse(ba.BEFUND)
        self.assertEqual((befund["aufgabe"], befund["art"]), (b, "rot"))
        g = next(e for e in self.ereignisse() if e["schritt"] == "geteilt")
        self.assertEqual((g["frei"], g["befunde"]), ([a], [b]))
        self.assertLessEqual(len(g["laeufe"]), ba.TEILUNGEN_MAX)

    def test_hoechstens_drei_teilungslaeufe(self):
        self.an()
        for i, t in enumerate((T1, T2, T3, "2026-11-25T11:00:00Z")):
            self.p_paket(f"P{i}", t, {f"lib/p{i}.py": "X = 1\n"})
        self.p_paket("Böse", "2026-11-25T12:00:00Z", {"lib/boese.py": "B = 1\n"})
        laeufe = []
        with mock.patch.object(ba, "TEILUNGEN_MAX", 1):
            orig = buendel.gesamtlauf_rechnen
            with mock.patch.object(buendel, "gesamtlauf_rechnen", lambda *x, **k: laeufe.append(1) or orig(*x, **k)):
                self.assertEqual(self.los(), "abgebrochen")
        self.assertEqual(len(laeufe), 2)                                                     # das Bündel und ein Teilungslauf
        self.assertEqual(self.git("rev-parse", "main"), self.main)
        self.assertTrue(any(k.startswith("Bündel ohne Agent abgebrochen") for k in self.an_lead()))


class Konflikt(Grund):
    def test_paket_mit_konflikt_bleibt_draussen_rest_geht(self):
        self.an()
        a = self.p_paket("Erst", T1, {"lib/x.py": "def f():\n    return 2\n"})
        b = self.p_paket("Dann", T2, {"lib/x.py": "def f():\n    return 3\n"})
        c = self.p_paket("Daneben", T3, {"lib/c.py": "C = 1\n"})
        self.assertEqual(self.los(), "ausgeliefert")
        sha = self.ausgeliefert[0][2]
        self.assertEqual(self.git("show", f"{sha}:lib/x.py"), "def f():\n    return 2")
        self.assertEqual(self.git("show", f"{sha}:lib/c.py"), "C = 1")
        befund, = self.ereignisse(ba.BEFUND)
        self.assertEqual((befund["aufgabe"], befund["art"], befund["dateien"]), (b, "konflikt", ["lib/x.py"]))
        self.assertEqual(sorted(self.ereignisse()[0]["aufgaben"]), sorted([a, c]))

    def test_konflikt_nur_in_gebauten_dateien_ist_keiner(self):
        self.an()
        for titel, t, x in (("Seite A", T1, "A"), ("Seite B", T2, "B")):                     # Seiten-Pakete liest der Lead
            aid = self.p_paket(titel, t, {f"lib/{x.lower()}.py": f"{x} = 1\n", "web/inc/seite.html": f"<p>{x}</p>\n"})
            self.merge_ereignis(aid, f"paket-A{aid}")
        self.assertEqual(self.los(), "ausgeliefert")
        self.assertEqual(self.ereignisse(ba.BEFUND), [])
        self.assertEqual(len(self.ereignisse()[0]["aufgaben"]), 2)

    def test_versions_commit_im_paket_kommt_nicht_mit_und_gleicher_kopf_einmal(self):
        self.an()
        a = self.p_paket("Stapel", T1, {"lib/a.py": "A = 1\n"}, {"amw/__init__.py": '__version__ = "9.9.9"\n'})
        self.git("checkout", "-q", f"paket-A{a}")
        self.git("commit", "-q", "--amend", "-m", "9.9.9: alter Stapel")
        kopf = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "main")
        for aid in (a,):
            self.entscheidung(aid, T1, zeile="E7", kopf=kopf, quelle="projekt")
        b = kern.aufgabe_neu(self.con, self.pid, "TL", "Gleicher Stand", "CC1")
        self.pruefung(b, f"paket-A{a}", kopf, T2)
        self.assertEqual(self.los(), "ausgeliefert")
        sha = self.ausgeliefert[0][2]
        self.assertIn('"1.2.4"', self.git("show", f"{sha}:amw/__init__.py"))
        self.assertEqual(sorted(self.ereignisse()[0]["aufgaben"]), sorted([a, b]))


class Abbruch(Grund):
    def test_kette_bricht_ab_main_bleibt_keine_wartung_meldung(self):
        self.an()
        self.p_paket("Plus", T1, {"lib/a.py": "A = 1\n"})

        def kaputt(zweig, lid):
            waechter.wartung_an("Auslieferung der AMW", kette=os.getpid())
            raise auslieferung.Stopp("Stopp bei „Dienst neu“: meldet nicht 1.2.4")
        self.assertEqual(self.los(kette=kaputt), "abgebrochen")
        self.assertEqual(self.git("rev-parse", "main"), self.main)
        self.assertIsNone(waechter.zustand()["wartung"])
        k = next(x for x in self.an_lead() if x.startswith("Bündel ohne Agent abgebrochen"))
        self.assertIn("Dienst neu", k)
        self.assertIsNone(buendel.offenes_buendel(self.con, self.pid))
        self.assertEqual(self.ereignisse()[-1]["zweig"], "buendel-1.2.4")

    def test_pause_zwischendurch_beendet_ihn(self):
        self.an()
        self.p_paket("Plus", T1, {"lib/a.py": "A = 1\n"})
        orig = buendel.gesamtlauf_rechnen

        def mit_pause(*x, **k):
            waechter.pause_an("von Hand")
            return orig(*x, **k)
        with mock.patch.object(buendel, "gesamtlauf_rechnen", mit_pause):
            self.assertEqual(self.los(), "abgebrochen")
        self.assertEqual((self.ausgeliefert, self.git("rev-parse", "main")), ([], self.main))

    def test_fremde_wartung_haelt_ihn_an_und_bleibt(self):
        self.an()
        self.p_paket("Plus", T1, {"lib/a.py": "A = 1\n"})
        waechter.wartung_an("von Hand")
        self.assertEqual(self.los(), "abgebrochen")
        self.assertEqual((waechter.zustand()["wartung"] or {}).get("grund"), "von Hand")


class Anstossen(Grund):
    def test_hindernisse_und_wer_darf(self):
        self.p_paket("Plus", T1, {"lib/a.py": "A = 1\n"})
        with self.assertRaisesRegex(kern.AmwFehler, "Lead oder der Mensch"):
            ba.anstossen(self.con, self.pid, "CC1", "x", starten=lambda pid: 1)
        waechter.wartung_an("von Hand")
        with self.assertRaisesRegex(kern.AmwFehler, "Wartungsmodus"):
            ba.anstossen(self.con, self.pid, "TL", "x", starten=lambda pid: 1)
        waechter.wartung_aus()
        self.assertEqual(ba.anstossen(self.con, self.pid, "TL", "x", starten=lambda pid: 4711), {"starter": 4711, "ausliefern": False})

    def test_runde_nur_mit_schalter(self):
        self.p_paket("Plus", T1, {"lib/a.py": "A = 1\n"})
        gestartet = []
        self.assertEqual(ba.runde(self.con, starten=gestartet.append), [])
        self.an()
        self.assertEqual(len(ba.runde(self.con, starten=gestartet.append)), 1)              # noch nie ausgeliefert: fällig
        self.assertEqual(gestartet, [self.pid])

    def test_schalter_setzt_nur_der_mensch(self):
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "TL", **{ba.SCHALTER: "an"})
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, **{ba.SCHALTER: "an"})
        self.assertEqual(kern.projekt_wahl(self.con, self.pid, ba.SCHALTER), "an")
