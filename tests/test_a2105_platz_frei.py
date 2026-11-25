"""A2105: ein Headless-Platz wird frei, sobald sein Paket angenommen ist (E7) – der geprüfte Kopf liegt im Projekt-Repo, der Platz im
Archiv; das Paket bleibt bereit zum Merge und kommt von dort ins Bündel. Gleiche Bereiche warten bis nach der Auslieferung, und die
Auslieferung setzt nie den Platz eines anderen Pakets zurück."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import shutil
import unittest
from typing import Any
from unittest import mock

from amw import arbeitspaket, betrieb, buendel, db, disponent, entscheidung, kern, mergeliste, planautomatik, platz, planung, pruefung_c, waechter
from tests import test_annehmen, test_buendel, test_disponent
from tests.test_mergeliste import bereit, g, schreiben


class Grund(test_buendel.Basis):
    def setUp(self):
        super().setUp()
        self.plaetze(2)
        for ziel, wert in (("amw.versionsprobe.sperre", None), ("amw.waechter.zustand", {"wartung": None, "pause": None})):
            p = mock.patch(ziel, return_value=wert)
            p.start()
            self.addCleanup(p.stop)

    def neu(self, titel, bereiche, zustand="startklar"):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel, "CC1")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET pruefbefehl = 'python -c pass', dateibereich = ? WHERE id = ?", (bereiche, aid))
        arbeitspaket.setzen(self.con, self.pid, "TL", aid, art="p")
        arbeitspaket.zustand_setzen(self.con, self.pid, "TL", aid, zustand)
        return aid

    def laeuft(self, aid, nr):
        """Wie disponent._starten: Platz vorbereiten, Vermerk, Zustand läuft. Rückgabe (Platz, Basis)."""
        p = platz.plaetze(self.con, self.pid)[nr - 1]
        basis = platz.vorbereiten(p, self.repo, mergeliste.zweig(aid), aufgabe=aid)["basis"]
        arbeitspaket.zustand_setzen(self.con, self.pid, "AMW", aid, "laeuft")
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="AMW", art=disponent.VERMERK,
                         aufgabe_id=aid, text=json.dumps({"platz": nr, "basis": basis, "zweig": mergeliste.zweig(aid)}))
        return p, basis

    def bauen(self, aid, p, basis, dateien):
        for rel, text in dateien.items():
            schreiben(p["klon"], rel, text)
        pruefung_c.basis_holen(p, self.repo, basis)
        return pruefung_c.einsammeln(p, basis, aid, f"A{aid}: gebaut") or ""

    def e7(self, titel, bereiche, dateien, nr):
        """Ein Paket bis zur Annahme durch die AMW – mit echter Prüf-Ablage und entscheidung.anwenden. (aid, Kopf, Platz)."""
        aid = self.neu(titel, bereiche)
        p, basis = self.laeuft(aid, nr)
        kopf = self.bauen(aid, p, basis, dateien)
        entscheidung.anwenden(self.con, self.pid, aid, "E7", "grün", befund={"kopf": kopf}, p=p, quelle=self.repo)
        return aid, kopf, p

    def entscheid(self, aid):
        return json.loads(self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'paket_entscheidung' AND aufgabe_id = ?"
                                           " ORDER BY id DESC", (aid,)).fetchone()[0])

    def belegt(self):
        return disponent.belegte_plaetze(self.con, self.pid)

    def pruefen(self, aid):
        return waechter.pruefen(self.con, self.pid, aid, limit=10)

    def meldungen(self):
        return [(r["kurz"], r["text"]) for r in self.con.execute("SELECT kurz, text FROM nachricht WHERE kurz LIKE '%bleibt belegt%'")]


class Frei(Grund):
    def test_e7_sichert_archiviert_und_gibt_den_platz_frei(self):
        aid, kopf, p = self.e7("plus", "lib/rechnen.py", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"}, 1)
        self.assertEqual(g(self.repo, "rev-parse", f"refs/amw/paket-A{aid}"), kopf)
        d = self.entscheid(aid)
        self.assertEqual((d["zeile"], d["quelle"], d["platz_frei"], d["gesichert"]), ("E7", "projekt", True, f"refs/amw/paket-A{aid}"))
        self.assertTrue(os.path.isdir(d["archiv"]))                                                  # nichts gelöscht
        self.assertEqual(g(p["klon"], "status", "--porcelain"), "")
        self.assertEqual((self.belegt(), arbeitspaket.lesen(self.con, aid)["zustand"]), ({}, "merge_reihe"))
        self.assertEqual(self.meldungen(), [])                                                       # der Normalfall sagt nichts
        e = mergeliste.eintrag(self.con, self.pid, aid)
        self.assertEqual((e["kopf"], e["fehler"], e["platz"], e["geaendert"]), (kopf, None, None, ["lib/rechnen.py"]))
        self.assertIn("return a + b", e["diff"])

    def test_zwei_angenommen_das_dritte_startet_und_das_buendel_hat_alle(self):
        a, _, _ = self.e7("A", "lib/a.py", {"lib/a.py": "a = 1\n"}, 1)
        b, _, _ = self.e7("B", "lib/b.py", {"lib/b.py": "b = 1\n"}, 2)
        c = self.neu("C", "lib/c.py")
        self.assertTrue(self.pruefen(c)["ok"], self.pruefen(c))                                      # vorher Regel 4
        p, basis = self.laeuft(c, 1)
        self.assertEqual(self.belegt(), {1: c})
        kopf = self.bauen(c, p, basis, {"lib/c.py": "c = 1\n"})
        entscheidung.anwenden(self.con, self.pid, c, "E7", "grün", befund={"kopf": kopf}, p=p, quelle=self.repo)
        self.assertEqual(self.belegt(), {})
        for r in mergeliste.freigeben(self.con, self.pid, "TL"):
            self.assertTrue(r["ok"], r)
        r = buendel.buendeln(self.con, self.pid, "TL", starten=False)
        self.assertEqual(([x["id"] for x in r["drin"]], r["raus"]), ([a, b, c], []))
        for x in "abc":
            self.assertEqual(self.datei(r["sha"], f"lib/{x}.py"), f"{x} = 1")
            self.assertTrue(betrieb.merge_ok(self.con, self.pid, {"a": a, "b": b, "c": c}[x], r["zweig"]))

    def test_auslieferung_wartet_nicht_auf_angenommene(self):
        aid, _, _ = self.e7("A", "lib/a.py", {"lib/a.py": "a = 1\n"}, 1)
        self.assertEqual((waechter.laufende(self.con, self.pid), waechter.p_laufend(self.con)), ([], False))
        with mock.patch.object(waechter, "wartung_an"), mock.patch.object(waechter, "zustand", return_value={"wartung": True}):
            self.assertEqual(waechter.vor_auslieferung(self.con, frist_s=0, schlafen=lambda s: None), (True, []))
        self.assertEqual([x["id"] for x in waechter.offene_bereiche(self.con, self.pid)], [aid])


class Bereiche(Grund):
    def test_gleicher_bereich_wartet_bis_nach_der_auslieferung(self):
        a, kopf, _ = self.e7("Plus bauen", "lib/rechnen.py", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"}, 1)
        b, frei = self.neu("B", "lib/"), self.neu("C", "doc/hilfe/")
        r = self.pruefen(b)
        self.assertEqual((r["regel"], r["warten"]), (2, True))
        self.assertIn(f"mit A{a} „Plus bauen“ – angenommen, aber noch nicht ausgeliefert; startet danach", r["grund"])
        self.assertTrue(self.pruefen(frei)["ok"])                                                    # andere Bereiche: startet
        mergeliste.freigeben(self.con, self.pid, "TL", [a])
        g(self.repo, "merge", "-q", "--ff-only", f"paket-A{a}")
        planautomatik.ausgeliefert(self.con, self.pid, "1.2.4", kopf, lambda s: True)
        self.assertTrue(self.pruefen(b)["ok"], self.pruefen(b))

    def test_laufendes_paket_heisst_laeuft_noch(self):
        a = self.neu("A", "lib/")
        self.laeuft(a, 1)
        self.assertIn(f"mit A{a} „A“ – läuft noch", self.pruefen(self.neu("B", "lib/x.py"))["grund"])

    def test_leerer_bereich_haelt_nichts(self):
        a, _, _ = self.e7("A", "lib/a.py", {"lib/a.py": "a = 1\n"}, 1)
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET dateibereich = '' WHERE id = ?", (a,))
        self.assertTrue(self.pruefen(self.neu("B", "lib/a.py"))["ok"])
        self.assertEqual(self.pruefen(self.neu("C", ""))["regel"], 1)

    def test_vorgaenger_zaehlen_weiter(self):
        a, _, _ = self.e7("A", "lib/a.py", {"lib/a.py": "a = 1\n"}, 1)
        b = self.neu("B", "web/b.php")
        planung.abhaengigkeit_setzen(self.con, self.pid, "TL", b, [a])
        self.assertNotIn(b, [x["id"] for x in waechter.reihenfolge(self.con, self.pid)])

    def test_vom_lead_angenommen_zaehlt_bei_den_bereichen(self):
        aid = self.neu("Plus", "lib/plus.py")
        p, basis = self.laeuft(aid, 1)
        kopf = self.bauen(aid, p, basis, {"tests/test_plus.py": "x = 1\n"})
        entscheidung.anwenden(self.con, self.pid, aid, "E4", "riskant", befund={"kopf": kopf}, p=p, quelle=self.repo)
        mergeliste.annehmen(self.con, self.pid, "TL", aid, "gelesen")
        r = self.pruefen(self.neu("B", "lib/"))
        self.assertEqual(r["regel"], 2)
        self.assertEqual(self.belegt(), {})


class Fehler(Grund):
    def vorbereiten(self):
        aid = self.neu("A", "lib/a.py")
        p, basis = self.laeuft(aid, 1)
        return aid, p, self.bauen(aid, p, basis, {"lib/a.py": "a = 1\n"})

    def test_sicherung_scheitert_platz_bleibt_belegt(self):
        aid, p, kopf = self.vorbereiten()
        with mock.patch.object(mergeliste, "kopf_sichern", side_effect=kern.AmwFehler("kein git")):
            entscheidung.anwenden(self.con, self.pid, aid, "E7", "grün", befund={"kopf": kopf}, p=p, quelle=self.repo)
        d = self.entscheid(aid)
        self.assertEqual((d.get("quelle"), d["gesichert"], d["archiv"]), (None, None, None))
        self.assertEqual((self.belegt(), arbeitspaket.lesen(self.con, aid)["zustand"]), ({1: aid}, "merge_reihe"))
        (kurz, text), = self.meldungen()
        self.assertEqual(kurz, f"A{aid} angenommen, Headless 1 bleibt belegt")
        self.assertIn("Stand nicht gesichert: AmwFehler: kein git", text)
        e = mergeliste.eintrag(self.con, self.pid, aid)                                              # gelesen wird wie bisher vom Platz
        self.assertEqual((e["fehler"], e["platz"], e["geaendert"]), (None, 1, ["lib/a.py"]))
        self.assertTrue(mergeliste.freigeben(self.con, self.pid, "TL", [aid])[0]["ok"])

    def test_danach_veraenderter_stand_kommt_nicht_ins_buendel(self):
        """Der Zweig im Prüf-Repo zeigt nicht mehr auf den geprüften Kopf: nicht gesichert, Platz belegt, nicht freigebbar."""
        aid, p, kopf = self.vorbereiten()
        fremd = g(p["klon"], "rev-parse", "origin/main")
        g(pruefung_c.repo(p), "update-ref", f"refs/heads/{mergeliste.zweig(aid)}", fremd)
        entscheidung.anwenden(self.con, self.pid, aid, "E7", "grün", befund={"kopf": kopf}, p=p, quelle=self.repo)
        self.assertEqual(self.belegt(), {1: aid})
        self.assertIn("nicht der Kopf", self.meldungen()[0][1])
        r = mergeliste.freigeben(self.con, self.pid, "TL", [aid])[0]
        self.assertFalse(r["ok"], r)
        with self.assertRaisesRegex(buendel.BuendelFehler, "Kein freigegebenes Paket"):
            buendel.buendeln(self.con, self.pid, "TL", starten=False)

    def test_gesicherter_stand_spaeter_veraendert(self):
        aid, kopf, _ = self.e7("A", "lib/a.py", {"lib/a.py": "a = 1\n"}, 1)
        g(self.repo, "update-ref", f"refs/amw/paket-A{aid}", "main")
        r = mergeliste.freigeben(self.con, self.pid, "TL", [aid])[0]
        self.assertFalse(r["ok"], r)
        self.assertIn("nicht der angenommene Kopf", r["text"])

    def test_aenderungen_am_platz_nach_der_pruefung_kommen_nicht_mit(self):
        aid, p, kopf = self.vorbereiten()
        schreiben(p["klon"], "lib/a.py", "a = 666\n")                                                # nach dem Einsammeln
        entscheidung.anwenden(self.con, self.pid, aid, "E7", "grün", befund={"kopf": kopf}, p=p, quelle=self.repo)
        self.assertTrue(mergeliste.freigeben(self.con, self.pid, "TL", [aid])[0]["ok"])
        r = buendel.buendeln(self.con, self.pid, "TL", starten=False)
        self.assertEqual(self.datei(r["sha"], "lib/a.py"), "a = 1")

    def test_zuruecksetzen_scheitert_platz_bleibt_belegt_und_die_auslieferung_setzt_ihn_zurueck(self):
        aid, p, kopf = self.vorbereiten()
        with mock.patch.object(platz, "zuruecksetzen", side_effect=platz.PlatzFehler("gesperrt")):
            entscheidung.anwenden(self.con, self.pid, aid, "E7", "grün", befund={"kopf": kopf}, p=p, quelle=self.repo)
        self.assertEqual((self.entscheid(aid)["platz_frei"], self.belegt()), (False, {1: aid}))
        self.assertIn("Platz nicht zurückgesetzt: PlatzFehler: gesperrt", self.meldungen()[0][1])
        self.assertTrue(mergeliste.freigeben(self.con, self.pid, "TL", [aid])[0]["ok"])              # gelesen aus dem Projekt-Repo
        aus = mergeliste.ausgeliefert(self.con, self.pid, aid, kopf[:7])
        self.assertIn("Headless 1 frei", aus or "")
        self.assertEqual(self.belegt(), {})

    def test_ohne_platz_bleibt_alles_wie_bisher(self):
        aid, _, kopf = self.vorbereiten()
        entscheidung.anwenden(self.con, self.pid, aid, "E7", "grün", befund={"kopf": kopf})
        self.assertNotIn("quelle", self.entscheid(aid))
        self.assertEqual(self.belegt(), {1: aid})


class Auslieferung(Grund):
    def test_setzt_den_platz_eines_anderen_pakets_nicht_zurueck(self):
        a, kopf, _ = self.e7("A", "lib/a.py", {"lib/a.py": "a = 1\n"}, 1)
        b = self.neu("B", "lib/b.py")
        p, _ = self.laeuft(b, 1)                                                                     # derselbe Platz, mitten im Lauf
        schreiben(p["klon"], "lib/b.py", "mitten im Lauf\n")
        with mock.patch.object(platz, "zuruecksetzen", wraps=platz.zuruecksetzen) as z:
            aus = mergeliste.ausgeliefert(self.con, self.pid, a, kopf[:7])
        z.assert_not_called()
        self.assertEqual((aus, arbeitspaket.lesen(self.con, a)["zustand"]), ("gemergt, fertig", "fertig"))
        with open(os.path.join(p["klon"], "lib", "b.py"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "mitten im Lauf\n")
        self.assertEqual(self.belegt(), {1: b})

    def test_alter_eintrag_ohne_quelle_bleibt_belegt_bis_zur_auslieferung(self):
        aid, kopf, _ = bereit(self.con, self.pid, self.repo, "alt", {"lib/alt.py": "x = 1\n"}, 1)   # wie vor A2105
        self.assertEqual(self.belegt(), {1: aid})
        mergeliste.freigeben(self.con, self.pid, "TL", [aid])
        self.assertIn("Headless 1 frei", mergeliste.ausgeliefert(self.con, self.pid, aid, str(kopf)[:7]) or "")
        self.assertEqual(self.belegt(), {})

    def wartet_nicht(self):
        with mock.patch.object(waechter, "wartung_an"), mock.patch.object(waechter, "zustand", return_value={"wartung": True}):
            return waechter.vor_auslieferung(self.con, frist_s=0, schlafen=lambda s: None)

    def test_wartet_nur_auf_pakete_an_denen_gearbeitet_wird(self):
        for ziel in waechter.ARBEITEND:
            a = self.neu("A", "lib/a.py")
            for z in waechter.ARBEITEND:
                arbeitspaket.zustand_setzen(self.con, self.pid, "AMW", a, z)
                if z == ziel:
                    break
            self.assertEqual((self.wartet_nicht(), waechter.p_laufend(self.con)), ((False, [a]), True), ziel)
            with db.schreiben(self.con):
                self.con.execute("UPDATE paket SET zustand = 'merge_reihe' WHERE aufgabe_id = ?", (a,))      # angenommen, ohne quelle
            self.assertEqual((self.wartet_nicht(), waechter.p_laufend(self.con)), ((True, []), False), ziel)

    def test_altes_e7_haelt_nicht_an_und_die_auslieferung_macht_es_fertig(self):
        """1.194.0 (25.11.): zwei E7 ohne quelle hielten die Auslieferung an, die sie erst frei gemacht hätte."""
        aid, kopf, p = bereit(self.con, self.pid, self.repo, "alt", {"lib/alt.py": "x = 1\n"}, 1)
        self.assertEqual((self.belegt(), self.wartet_nicht()), ({1: aid}, (True, [])))
        mergeliste.freigeben(self.con, self.pid, "TL", [aid])
        g(self.repo, "merge", "-q", "--ff-only", f"paket-A{aid}")
        aus = planautomatik.ausgeliefert(self.con, self.pid, "1.2.4", str(kopf), lambda s: True)
        self.assertIn("Headless 1 frei", aus[0]["paket"])
        self.assertEqual((arbeitspaket.lesen(self.con, aid)["zustand"], self.belegt(), g(p["klon"], "status", "--porcelain")), ("fertig", {}, ""))


class AuslieferungNachE4(Grund):
    """Derselbe Fehler bestand schon bei vom Lead angenommenen Paketen (A1894)."""
    e4 = test_annehmen.Annehmen.e4

    def test_setzt_den_platz_eines_anderen_pakets_nicht_zurueck(self):
        aid, kopf, _ = self.e4()
        mergeliste.annehmen(self.con, self.pid, "TL", aid, "gelesen")
        b = self.neu("B", "lib/b.py")
        self.laeuft(b, 1)
        with mock.patch.object(platz, "zuruecksetzen") as z:
            self.assertEqual(mergeliste.ausgeliefert(self.con, self.pid, aid, str(kopf)[:7]), "gemergt, fertig")
        z.assert_not_called()
        self.assertEqual(self.belegt(), {1: b})


@unittest.skipUnless(shutil.which("git") and os.name == "nt", "git/Windows fehlt")
class EchterWeg(unittest.TestCase):
    """Disponent, Starter und Arbeiter-Attrappe: nach E7 ist der Platz frei, das nächste Paket startet darauf."""
    con: Any
    pid: Any
    repo: Any
    setUp = test_disponent.Disponent.setUp
    plaetze = test_disponent.Disponent.plaetze
    paket = test_disponent.Disponent.paket
    zustand = test_disponent.Disponent.zustand
    warten = test_disponent.Disponent.warten
    entschieden = test_disponent.Disponent.entschieden

    def test_naechstes_paket_startet_auf_dem_freien_platz(self):
        self.plaetze(1)
        a = self.paket()
        self.assertTrue(any(f"A{a} gestartet als Headless 1" in x for x in disponent.runde(self.con, test_disponent.prog("bauen"))))
        self.assertEqual(self.warten(a, ("merge_reihe", "wartet_interaktiv", "abgebrochen", "unklar")), "merge_reihe")
        self.assertTrue(self.entschieden(a))                                                         # der Entscheid folgt dem Zustand
        self.assertEqual(disponent.belegte_plaetze(self.con, self.pid), {})
        gleich, b = self.paket(), self.paket(bereiche="lib2/")
        aus = disponent.runde(self.con, test_disponent.prog("bauen"))
        self.assertTrue(any(f"A{b} gestartet als Headless 1" in x for x in aus), aus)
        self.assertEqual(self.zustand(gleich), "startklar")
        self.assertIn(f"mit A{a}", waechter.protokoll(self.con, self.pid, gleich)[0]["text"])
        self.warten(b, ("merge_reihe", "wartet_interaktiv", "abgebrochen", "unklar", "startklar", "zurueckgestellt"))
        self.assertEqual(g(self.repo, "rev-parse", f"refs/amw/paket-A{a}"),
                         json.loads(self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'paket_entscheidung' AND aufgabe_id = ?",
                                                     (a,)).fetchone()[0])["kopf"])


if __name__ == "__main__":
    unittest.main()
