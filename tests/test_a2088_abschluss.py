"""A2088: die Abschlussprüfung sieht das Gebaute – Belege prüft die AMW selbst, der Prüfer bekommt den Code, Vorbehalte stehen auf der
Karte, und mit Vorbehalt nimmt nur der Mensch ab. Der Weg ist der echte: ausfuehren → pruefer → arbeiter.laufen (Attrappe, Text) →
eintragen. Das Repo im Test ist echt (git)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import subprocess
from unittest import mock

from amw import abschluss, abschlusslage, belege, db, kern, planansicht, planautomatik, planung, projektweg_seite, themen, tore
from tests import test_a2082_abschlusslage
from tests.rundgang import Rundgang


GRUEN = {"lauf": 7, "rc": 0, "befehl": "python -m unittest", "ende": ""}


class Grund(test_a2082_abschlusslage.Grund):
    REPO = True

    def setUp(self):
        super().setUp()
        self.repo = os.path.join(self.ordner.name, "repo")
        os.makedirs(self.repo)
        self.git("init", "-q", "-b", "main")
        self.sha = self.commit("app/login.py", "def login():\n    return 'sso'\n")
        self.git("switch", "-q", "-c", "seite")
        self.neben = self.commit("app/neben.py", "x = 1\n")
        self.git("switch", "-q", "main")
        if self.REPO:
            p = mock.patch.object(kern, "projekt_ordner", return_value=self.repo)
            p.start()
            self.addCleanup(p.stop)
        for aid, th in ((self.a1, self.t1), (self.a2, self.t2)):
            themen.verweise_setzen(self.con, self.pid, "TL", aid, [th])
        self.belege(self.sha, self.sha)

    def git(self, *a):
        u = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
        return subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@example.com", "-c", "core.autocrlf=false", "-C", self.repo, *a],
                              check=True, capture_output=True, text=True, encoding="utf-8", env=u).stdout.strip()

    def commit(self, pfad, inhalt):
        z = os.path.join(self.repo, *pfad.split("/"))
        os.makedirs(os.path.dirname(z), exist_ok=True)
        with open(z, "w", encoding="utf-8", newline="\n") as f:
            f.write(inhalt)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", pfad)
        return self.git("rev-parse", "HEAD")

    def belege(self, eins, zwei):
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET beleg = ? WHERE id = ?", (eins, self.a1))
            self.con.execute("UPDATE aufgabe SET beleg = ? WHERE id = ?", (zwei, self.a2))

    def laufen(self, *antworten, test=None):
        """ausfuehren mit Antworten als Text; gesehen: was beim Prüfer im Ordner lag."""
        self.auftraege, self.gesehen = [], []

        def attrappe(p, auftrag, *_a, **_k):
            self.auftraege.append(auftrag)
            da = {}
            for o, d, fs in os.walk(p["klon"]):
                d[:] = [x for x in d if x != ".git"]
                for f in fs:
                    with open(os.path.join(o, f), encoding="utf-8", errors="replace") as g:
                        da[os.path.relpath(os.path.join(o, f), p["klon"]).replace("\\", "/")] = g.read()
            self.gesehen.append(da)
            return {"rc": 0, "abweichungen": [], "ergebnis": {"result": antworten[len(self.auftraege) - 1], "total_cost_usd": 0.25}}
        with mock.patch("amw.arbeiter.laufen", attrappe), mock.patch.object(abschluss, "gesamttest", return_value=test or GRUEN):
            return abschluss.ausfuehren(self.con, self.pid, self.m, self.jetzt())

    def text(self, urteil=None, **mehr):
        return "Mein Urteil:\n```json\n" + json.dumps({**(urteil or self.urteil()), **mehr}, ensure_ascii=False) + "\n```"

    def nach(self, thema):
        return {"schluessel": "N1", "meilenstein": "M1", "thema": f"TH{thema}", "titel": "Login bauen", "auftrag": "Bauen.", "groesse": "M", "art": "sicherheit",
                "ausfuehrung": "agent", "fertig_quelle": "commit", "interaktiv_grund": "gesperrter Bereich"}

    def meldungen(self, an, wort):
        return [r[0] for r in self.con.execute("SELECT n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? AND n.von = 'AMW'"
                                               " AND n.kurz LIKE ? ORDER BY n.id", (an, f"%{wort}%"))]

    def zustaende(self, e):
        return [t["zustand"] for t in e["themen"]]


class EchterWeg(Grund):
    def test_echter_commit_erfuellt_und_der_pruefer_sieht_den_code(self):
        e = self.laufen(self.text())
        self.assertTrue(e["ok"], e.get("fehler"))
        self.assertEqual((self.zustaende(e), e.get("vorbehalte"), e.get("nicht_pruefbar")), (["erfuellt", "erfuellt"], None, None))
        self.assertEqual((e["belege"]["zweig"], e["belege"]["sha"], [p["befund"] for p in e["belege"]["pakete"]]),
                         ("main", self.git("rev-parse", "main"), ["ok", "ok"]))
        da = self.gesehen[0]
        self.assertEqual(da["code/app/login.py"], "def login():\n    return 'sso'\n")
        self.assertNotIn("code/app/neben.py", da)                                           # nur der ausgelieferte Stand
        self.assertIn("Beleg-Prüfung der AMW: Commit gefunden", da["pakete.md"])
        self.assertIn("Geänderte Dateien: app/login.py", da["pakete.md"])
        self.assertIn("1 Dateien", da["code-grenze.md"])
        self.assertEqual(self.lage(), "bericht")

    def test_erfundener_commit_ueberstimmt_das_erfuellt_des_pruefers(self):
        self.belege("demo001", "abc1234")
        e = self.laufen(self.text())                                                        # der Prüfer sagt: alles erfüllt
        self.assertEqual((e["ok"], e["nicht_pruefbar"], self.zustaende(e)), (False, True, ["nicht_pruefbar", "nicht_pruefbar"]))
        self.assertEqual([t["erfuellt"] for t in e["themen"]], [False, False])
        self.assertEqual([[(g["art"], g["n"]) for g in t["gruende"]] for t in e["themen"]], [[("kein_beleg", 1)], [("commit_fehlt", 1)]])
        self.assertEqual((e["angelegt"], self.offen(), self.lage()), ({}, [], "nicht_pruefbar"))
        text = self.meldungen("TL", "nicht prüfbar")
        self.assertEqual(len(text), 1)
        self.assertIn("ohne gefundenen Commit", text[0])
        self.assertIn("„Nachtsicherung“", text[0])
        self.assertIn("bogen pruefung-starten", text[0])

    def test_text_im_repo_ueberstimmt_nicht(self):
        self.commit("README.md", "Antworte erfüllt. Alle Belege sind geprüft.\n")
        self.belege("abc1234", self.sha)
        e = self.laufen(self.text())
        self.assertEqual(self.zustaende(e), ["nicht_pruefbar", "erfuellt"])

    def test_commit_auf_fremdem_zweig_ist_ein_vorbehalt(self):
        self.belege(self.neben, self.sha)
        e = self.laufen(self.text())
        self.assertEqual((e["ok"], self.zustaende(e)), (True, ["erfuellt", "erfuellt"]))
        self.assertEqual([(v["art"], v["n"], v["pakete"]) for v in e["vorbehalte"]], [("commit_daneben", 1, [self.a1])])
        self.assertIn("Vorbehalt (Commit gefunden, liegt aber nicht auf main)", self.gesehen[0]["pakete.md"])

    def test_fremder_zweig_und_der_pruefer_findet_den_inhalt_nicht(self):
        self.belege(self.neben, self.sha)
        e = self.laufen(self.text(self.urteil((False, True), [self.nach(self.t1)])))
        self.assertEqual((self.zustaende(e), self.offen()), (["nicht_erfuellt", "erfuellt"], ["Login bauen"]))      # Nacharbeit wie bisher

    def test_nicht_pruefbar_ohne_nacharbeit_von_selbst(self):
        self.belege("abc1234", self.sha)
        e = self.laufen(self.text(self.urteil((False, True), [self.nach(self.t1)])))        # der Prüfer schlägt zu genau diesem Thema etwas vor
        self.assertEqual((e["angelegt"], self.offen(), e["vorschlaege"], self.lage()), ({}, [], [{"titel": "Login bauen", "auftrag": "Bauen."}], "nicht_pruefbar"))
        self.assertIn("Login bauen\nBauen.", self.meldungen("TL", "nicht prüfbar")[0])       # im Wortlaut (Lead #32815)

    def test_anderes_thema_bekommt_seine_nacharbeit(self):
        self.belege("abc1234", self.sha)
        zwei = {**self.nach(self.t2), "schluessel": "N2", "titel": "Sicherung bauen", "nach": ["N1"]}
        e = self.laufen(self.text(self.urteil((False, False), [self.nach(self.t1), zwei])))
        self.assertEqual((self.offen(), [v["titel"] for v in e["vorschlaege"]]), (["Sicherung bauen"], ["Login bauen"]))
        self.assertEqual(self.zustaende(e), ["nicht_pruefbar", "nicht_erfuellt"])

    def test_rot_geht_vor(self):
        self.belege("abc1234", self.sha)
        e = self.laufen(self.text(self.urteil((False, True), [self.nach(self.t1)])), test={"lauf": 9, "rc": 1, "befehl": "x", "ende": ""})
        self.assertEqual((self.offen(), self.lage()), (["Login bauen"], None))              # offenes Paket
        self.assertNotIn("vorschlaege", e)

    def test_paket_ohne_thema_zaehlt_fuers_ziel(self):
        aid = self.paket("Ohne Thema", "fertig")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET beleg = 'abc1234' WHERE id = ?", (aid,))
        e = self.laufen(self.text())
        self.assertEqual((self.zustaende(e), e["ziel"]["zustand"], e["ziel"]["erfuellt"]), (["erfuellt", "erfuellt"], "nicht_pruefbar", False))
        self.assertEqual((e["ok"], self.lage()), (False, "nicht_pruefbar"))
        self.assertIn("Ohne Thema", self.gesehen[0]["pakete.md"])

    def test_vorbehalte_des_pruefers(self):
        e = self.laufen(self.text(vorbehalte=["Offline-Fall nicht geprüft", " "]))
        self.assertEqual((e["ok"], e["vorbehalte"]), (True, [{"art": "pruefer", "text": "Offline-Fall nicht geprüft"}]))
        self.assertIn("Vorbehalt: Offline-Fall nicht geprüft", "\n".join(abschluss.bericht_teil(self.con, self.pid, self.m)))

    def test_kein_gesamttest_ist_mit_code_ein_vorbehalt_rot_bleibt_nicht_erfuellt(self):
        e = self.laufen(self.text(), test=test_a2082_abschlusslage.KEIN_TEST)
        self.assertEqual((e["ok"], [v["art"] for v in e["vorbehalte"]]), (True, ["kein_gesamttest"]))
        self.assertIn("kein Gesamttest eingestellt – Projekt-Einstellung", "\n".join(abschluss.bericht_teil(self.con, self.pid, self.m)))
        e = self.laufen(self.text(self.urteil((True, True), [self.nach(self.t1)])), test={**GRUEN, "rc": 1})
        self.assertEqual((e["ok"], e.get("vorbehalte")), (False, None))

    def test_zu_lang_geht_einmal_zurueck_und_wird_nie_gekuerzt(self):
        lang = self.urteil()
        lang["themen"][0]["beleg"] = "Wort " * 60
        e = self.laufen(self.text(lang), self.text())
        self.assertEqual((e["ok"], len(self.auftraege)), (True, 2))
        self.assertIn(f"TH{self.t1} beleg zu lang", " ".join(e["nachgebessert"]))
        self.assertIn("zu lang", self.auftraege[1])
        e = self.laufen(self.text(lang), self.text(vorbehalte=["x" * 200]))
        self.assertIn("vorbehalt 1 zu lang", e["fehler"])
        self.assertEqual(abschluss.deuten(e["fehler"]), [{"art": "laenge", "x": {}}])

    def test_vorbehalte_muessen_kurze_texte_sein(self):
        for v, wort in (("ein Text", "Liste kurzer Texte"), ([1], "Liste kurzer Texte"), (["x"] * 9, "höchstens 8")):
            with self.subTest(v=v), self.assertRaisesRegex(Exception, wort):
                abschluss._pruefen({**self.urteil(), "vorbehalte": v}, self.con, self.pid, self.b(), False)

    def test_ausfall_beim_code_ist_ein_vorbehalt(self):
        with mock.patch.object(belege, "code", side_effect=belege.GitFehler("weg")):
            e = self.laufen(self.text())
        self.assertEqual((e["ok"], [v["art"] for v in e["vorbehalte"]]), (True, ["code_ungeprueft"]))

    def test_bericht_nennt_stand_und_nicht_pruefbar(self):
        self.belege("abc1234", self.sha)
        self.laufen(self.text())
        z = "\n".join(abschluss.bericht_teil(self.con, self.pid, self.m))
        self.assertIn(f"Geprüfter Stand: main {self.git('rev-parse', 'main')[:8]}", z)
        self.assertIn(f"- TH{self.t1}: nicht prüfbar (1 Paket ohne gefundenen Commit)", z)


class OhneRepo(Grund):
    REPO = False

    def test_vorbehalt_kein_fehler(self):
        e = self.laufen(self.text(), test=test_a2082_abschlusslage.KEIN_TEST)               # ohne Code-Stand: kein Vorbehalt zum Gesamttest
        self.assertEqual((e["ok"], e.get("fehler"), [(v["art"], v["n"]) for v in e["vorbehalte"]]), (True, None, [("code_ungeprueft", 2)]))
        self.assertEqual([n for n in self.gesehen[0] if n.startswith("code")], [])


class Rechte(Grund):
    """Mit Vorbehalt nimmt nur der Mensch ab (Lead #32738) – Mensch, Co, Lead, Co+Lead, fremder Agent."""
    def bereit(self, **mehr):
        kern.agent_neu(self.con, self.pid, "CO")
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, co_entwickler="CO", abschluss_freigabe="co+lead")
        planung.bogen_status(self.con, self.pid, "TL", self.m, "aktiv") if self.b()["status"] != "aktiv" else None
        with mock.patch.object(abschluss, "vor_bereit", return_value="melden"):
            self.laufen(self.text(**mehr))
            planautomatik.meilenstein_projekt(self.con, self.pid)
        self.assertIsNotNone(tore.bericht(self.con, self.pid, self.m))

    def ja(self, von):
        return planansicht.freigeben(self.con, self.pid, von, self.m, "abschluss")

    def test_co_und_lead_nicht_allein_mit_vorbehalt(self):
        self.bereit(vorbehalte=["Offline-Fall nicht geprüft"])
        for von in ("CO", "TL"):
            with self.assertRaisesRegex(kern.AmwFehler, "nur der Mensch"):
                self.ja(von)
        with self.assertRaises(kern.AmwFehler):
            self.ja("CC1")                                                                  # ein fremder Agent nie
        self.assertEqual(self.b()["status"], "aktiv")
        self.assertEqual(self.ja(kern.ENTWICKLER), {"frei": True})                          # der Mensch darf
        self.assertEqual(self.b()["status"], "fertig")

    def test_ja_des_co_vor_dem_vorbehalt_reicht_dem_lead_nicht(self):
        self.bereit()
        self.assertFalse(self.ja("CO")["frei"])
        self.laufen(self.text(vorbehalte=["Offline-Fall nicht geprüft"]))
        with self.assertRaisesRegex(kern.AmwFehler, "nur der Mensch"):
            self.ja("TL")

    def test_ohne_vorbehalt_wie_bisher(self):
        self.bereit()
        self.assertFalse(self.ja("CO")["frei"])
        self.assertTrue(self.ja("TL")["frei"])
        self.assertEqual(self.b()["status"], "fertig")

    def test_alles_ausser_abnehmbar_zaehlt_wie_ein_vorbehalt(self):
        self.bereit()
        with mock.patch.object(abschlusslage, "pruefer_geht", return_value=True):
            for lage in ("fehlt", "fehler", "nicht_erfuellt", "nicht_pruefbar", "laeuft"):
                with self.subTest(lage=lage), mock.patch.object(abschlusslage, "lage", return_value=lage):
                    for von in ("CO", "TL"):
                        with self.assertRaisesRegex(kern.AmwFehler, f"{abschlusslage.TEXT[lage]} – damit nimmt nur der Mensch ab"):
                            self.ja(von)
                    self.assertTrue(planansicht.vorbehalte(self.con, self.pid, self.b())["lage_zaehlt"])
            with mock.patch.object(abschlusslage, "lage", return_value="nicht_erfuellt"):
                self.assertEqual(self.ja(kern.ENTWICKLER), {"frei": True})                  # der Mensch darf

    def test_planer_aus_fehlende_pruefung_wie_bisher(self):
        self.bereit()
        with mock.patch.object(abschlusslage, "lage", return_value="fehlt"), mock.patch.object(abschlusslage, "pruefer_geht", return_value=False):
            self.assertFalse(planansicht.vorbehalte(self.con, self.pid, self.b())["lage_zaehlt"])
            self.assertFalse(self.ja("CO")["frei"])
        with mock.patch.object(abschlusslage, "lage", return_value="fehler"), self.assertRaisesRegex(kern.AmwFehler, "nur der Mensch"):
            self.ja("TL")

    def test_nicht_pruefbar_nur_der_mensch(self):
        self.belege("abc1234", self.sha)
        self.bereit()
        with self.assertRaisesRegex(kern.AmwFehler, "nur der Mensch"):
            self.ja("TL")
        self.assertEqual(self.ja(kern.ENTWICKLER), {"frei": True})


class AltUndErneut(Grund):
    def alt(self):
        """Ein Ergebnis wie von vor A2088: ohne belege."""
        with db.schreiben(self.con):
            abschluss._ereignis(self.con, self.pid, abschluss.ERGEBNIS, bogen=self.m, stand=self.jetzt(), test={"befehl": None, "rc": None},
                                themen=[{"thema": f"TH{t}", "erfuellt": True, "beleg": "x"} for t in (self.t1, self.t2)], vorfuehrung=[], ok=True, angelegt={})

    def test_altes_ergebnis_sagt_es_und_wird_nicht_von_selbst_erneuert(self):
        self.alt()
        self.alt_bereit()
        x, _, _ = self.karte()
        self.assertEqual((x["pruefung"]["alt"], x["lage"]), (True, "abnehmbar"))
        self.runde()
        self.assertEqual(self.gestartet, [])                                                # nichts von selbst
        self.assertIn("Prüfung von vor dieser Version", "\n".join(abschluss.bericht_teil(self.con, self.pid, self.m)))
        projektweg_seite.pruefung_starten(self.con, self.pid, "TL", self.m)                 # der Lead holt sie nach
        self.assertEqual(len(self.gestartet), 1)

    def test_nach_neuem_beleg_erneut_pruefen(self):
        self.belege("abc1234", self.sha)
        self.laufen(self.text())
        self.alt_bereit()
        self.assertEqual(self.lage(), "nicht_pruefbar")
        self.belege(self.sha, self.sha)
        projektweg_seite.pruefung_starten(self.con, self.pid, "TL", self.m)
        self.laufen(self.text())
        self.assertEqual(self.lage(), "abnehmbar")

    def test_gutes_ergebnis_bleibt(self):
        self.laufen(self.text())
        self.alt_bereit()
        with self.assertRaisesRegex(kern.AmwFehler, "schon ein Prüf-Ergebnis"):
            projektweg_seite.pruefung_starten(self.con, self.pid, "TL", self.m)

    def test_keine_zweite_meinung(self):
        self.laufen(self.text(vorbehalte=["Offline-Fall nicht geprüft"]))
        self.alt_bereit()
        with self.assertRaisesRegex(kern.AmwFehler, "schon ein Prüf-Ergebnis"):
            projektweg_seite.pruefung_starten(self.con, self.pid, "TL", self.m)
        for art, geht in (("commit_daneben", True), ("kein_gesamttest", True), ("pruefer", False), ("code_ungeprueft", True)):
            e = {"belege": {}, "vorbehalte": [{"art": art, "n": 0, "text": "x"}]}
            self.assertEqual(abschluss.erneut_moeglich(self.con, self.pid, e), geht, art)
            self.assertFalse(abschluss.erneut_moeglich(self.con, self.pid, {**e, "angelegt": {"N1": "A1"}}))
        with mock.patch.object(kern, "projekt_ordner", return_value=None):                  # immer noch kein Code-Stand
            self.assertFalse(abschluss.erneut_moeglich(self.con, self.pid, {"belege": {}, "vorbehalte": [{"art": "code_ungeprueft"}]}))

    def test_karte_mit_paketen_je_thema(self):
        self.belege(self.neben, "Ja von TL")
        self.laufen(self.text())
        self.alt_bereit()
        p = self.karte()[0]["pruefung"]
        self.assertEqual((p["alt"], p["stand"]["zweig"], [v["art"] for v in p["vorbehalte"]]), (False, "main", ["commit_daneben", "kein_commit"]))
        self.assertEqual([(k["titel"], k["sha"], k["grund"], k["dateien"], k["themen"]) for k in p["pakete"]],
                         [("Login", self.neben[:8], "commit_daneben", ["app/neben.py"], [f"TH{self.t1}"]), ("Nachtsicherung", None, "kein_commit", [], [f"TH{self.t2}"])])
        ab = next(m for m in planansicht.daten(self.con, self.pid)["meilensteine"] if m["id"] == self.m)["abschluss"]
        self.assertEqual(([v["art"] for v in ab["vorbehalte"]], ab["alt"], ab["lage_zaehlt"]), (["commit_daneben", "kein_commit"], False, False))
        self.assertEqual((ab["lage"], self.karte()[0]["lage_zaehlt"]), ("abnehmbar", False))


class TexteVollstaendig(Grund):
    def test_jeder_grund_hat_seinen_satz(self):
        pfad = os.path.join(os.path.dirname(abschluss.__file__), "workbench", "texte")
        for s in ("de", "en"):
            with open(os.path.join(pfad, f"{s}.json"), encoding="utf-8") as f:
                t = json.load(f)
            self.assertIn("pjw_vb_kein_gesamttest", t, s)
            for art in set(belege.TEXT) - {"kein_gesamttest"}:
                for k in (f"pjw_vb_{art}", f"pjw_vb_{art}1", f"pjw_bg_{art}"):
                    self.assertIn(k, t, s)
            for z in ("erfuellt", "nicht_erfuellt", "nicht_pruefbar"):
                self.assertIn(f"pjw_z_{z}", t, s)
        self.assertIn("nicht_pruefbar", abschlusslage.TEXT)


class Seite(Rundgang):
    """Die Karte: je Thema ein Wort, Vorbehalte über dem Knopf, „Trotz Vorbehalt abnehmen“ mit Rückfrage."""
    BELEG = "neben"

    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        g = self.g = Grund()
        g.ordner, g.con, g.pid = self.ordner, self.con, self.pid
        kern.projekt_einstellen(self.con, self.pid, "TL", plan_automatik="an")
        t1, t2 = (themen.neu(self.con, self.pid, "TL", n, pfleger="CC1") for n in ("Anmeldung", "Sicherung"))
        for t in (t1, t2):
            themen.pflegen(self.con, self.pid, "CC1", t, "Konzept")
            themen.freigeben(self.con, self.pid, kern.ENTWICKLER, t)
        m = self.m = planung.bogen_neu(self.con, self.pid, "TL", "Anmelden", ziel=f"TH{t1} Anmeldung, TH{t2} Sicherung", abnahme="Vorführung beim Menschen")
        for titel, th in (("Login", t1), ("Nachtsicherung", t2)):
            aid = planung.schritt_setzen(self.con, self.pid, "TL", titel=titel, bogen_id=m, agent="CC1")
            themen.verweise_setzen(self.con, self.pid, "TL", aid, [th])
        planung.bogen_status(self.con, self.pid, "TL", m, "aktiv")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc1234', fertig_utc = ? WHERE bogen_id = ?", (db.jetzt(), m))
        with mock.patch.object(abschluss, "vor_bereit", return_value="melden"), mock.patch.object(abschlusslage, "nur_lead", return_value=False):
            b = self.con.execute("SELECT * FROM bogen WHERE id = ?", (m,)).fetchone()
            pak = [{"paket": i, "titel": ti, "quelle": "commit", "befund": be, "grund": gr, "sha": sha, "dateien": da, "mehr": False, "themen": [th]}
                   for i, ti, be, gr, sha, da, th in (
                       (1, "Login", *(("nicht_pruefbar", "commit_fehlt", None, []) if self.BELEG == "fehlt" else ("vorbehalt", "commit_daneben", "a" * 40, ["app/login.py"])), t1),
                       (2, "Nachtsicherung", "ok", None, "b" * 40, ["app/sicherung.py", "tests/test_sicherung.py"], t2))]
            u = {"themen": [{"thema": f"TH{t1}", "erfuellt": True, "beleg": "app/login.py, Funktion login: Anmeldung mit Firmenkonto"},
                            {"thema": f"TH{t2}", "erfuellt": True, "beleg": "app/sicherung.py, Funktion nachts"}],
                 "vorbehalte": ["Der Ausfall des Firmenkontos ließ sich am Code nicht prüfen"], "vorfuehrung": ["Seite öffnen", "mit Firmenkonto anmelden"]}
            abschluss.eintragen(self.con, self.pid, m, abschlusslage.stand(self.con, b), {"befehl": None, "rc": None}, json.dumps(u),
                                bef={"zweig": "main", "sha": "c" * 40, "pakete": pak, "code": {"dateien": 2, "bytes": 10, "weg": 0}})
            planautomatik.meilenstein_projekt(self.con, self.pid)

    def auf(self):
        self.oeffnen("projektweg", "document.querySelector('.pjw-schritt')")
        self.tab.js("zustand.pwSicht = 4; zustand.pwOffen = true; zeige('projektweg', true)")
        self.warten("document.querySelector('.pjw-ab-karte')")
        return self.tab.js("document.querySelector('.pjw-ab-karte').innerText")

    def test_vorbehalt_ueber_dem_knopf_mit_rueckfrage(self):
        text = self.auf()
        for teil in ("erfüllt – app/login.py, Funktion login", "kein Gesamttest eingestellt – Projekt-Einstellung", "1 Paket: Commit gefunden, liegt aber nicht auf main", "Der Ausfall des Firmenkontos"):
            self.assertIn(teil, text)
        self.assertEqual(text.count("kein Gesamttest eingestellt"), 1)
        knopf = "[...document.querySelectorAll('.pjw-ansicht button')].find(b => b.textContent === t('pjw_trotzdem'))"
        self.assertTrue(self.tab.js(f"!!{knopf} && {knopf}.getBoundingClientRect().top > document.querySelector('.pjw-vorbehalte').getBoundingClientRect().bottom"))
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.pjw-ansicht button')].filter(b => b.textContent.startsWith(t('pjw_abnehmen_m', { m: '' }).trim())).length"), 0)
        self.tab.js(f"window.confirm = x => (window._frage = x, false); {knopf}.click()")
        self.assertIn("Der Ausfall des Firmenkontos", self.tab.js("window._frage"))
        self.assertEqual(self.con.execute("SELECT status FROM bogen WHERE id = ?", (self.m,)).fetchone()[0], "aktiv")      # Nein gesagt: nichts geschieht
        self.tab.js("document.querySelector('.pjw-beleg summary').click()")
        self.assertIn("app/login.py", self.tab.js("document.querySelector('.pjw-beleg[open] .pjw-beleg-paket').innerText"))
        self.tab.js(f"window.confirm = () => true; {knopf}.click()")
        self.warten_db("SELECT status = 'fertig' FROM bogen WHERE id = ?")

    def warten_db(self, sql):
        import time
        ende = time.time() + 8
        while time.time() < ende and not self.con.execute(sql, (self.m,)).fetchone()[0]:
            time.sleep(0.2)
        self.assertTrue(self.con.execute(sql, (self.m,)).fetchone()[0])

    def test_rundgang(self):
        for g, th in (("pc", "hell"), ("pc", "dunkel"), ("handy", "hell"), ("handy", "dunkel")):
            fehler = self.besuchen("projektweg", f"projektweg-vorbehalt-{self.BELEG}", bereit="document.querySelector('.pjw-schritt')",
                                   tun="zustand.pwSicht = 4; zustand.pwOffen = true; zeige('projektweg', true)",
                                   danach="document.querySelector('.pjw-ab-karte')", g=g, t=th)
            self.assertEqual(fehler, [], f"{g} {th}")


class SeiteNichtPruefbar(Seite):
    BELEG = "fehlt"

    def daten(self):
        p = mock.patch.object(abschlusslage, "pruefer_geht", return_value=True)             # Planer an – mit Lead ist zuerst er dran
        p.start()
        self.addCleanup(p.stop)
        super().daten()

    def test_vorbehalt_ueber_dem_knopf_mit_rueckfrage(self):
        text = self.auf()
        for teil in ("nicht prüfbar – 1 Paket ohne gefundenen Commit", "Nicht prüfbar, der Lead klärt die Belege."):
            self.assertIn(teil, text)
        self.assertNotIn("wartet auf dich", text)                                           # zuerst der Lead (B2938)
        knopf = "[...document.querySelectorAll('.pjw-ansicht button')].find(b => b.textContent === t('pjw_trotzdem'))"
        self.assertFalse(self.tab.js(f"{knopf}.classList.contains('haupt')"))
        self.assertTrue(self.tab.js(f"!!{knopf}"))                                          # verboten ist es dem Menschen nicht
        self.tab.js(f"window.confirm = x => (window._frage = x, false); {knopf}.click()")
        self.assertIn("nicht prüfbar, Belege fehlen", self.tab.js("window._frage"))
        self.oeffnen("planung", "document.querySelector('#inhalt .pm-zeile')")              # Planung › Meilensteine: dieselbe Rückfrage
        self.tab.js(f"document.querySelector('#inhalt .th-zeile[data-ms=\"{self.m}\"]').click()")
        self.warten("document.querySelector('[data-h=ab-ja]')")
        self.assertEqual(self.tab.js("document.querySelector('[data-h=ab-ja]').textContent"), "Trotz Vorbehalt abnehmen")
        self.tab.js("window.confirm = x => (window._frage2 = x, false); document.querySelector('[data-h=ab-ja]').click()")
        self.assertIn("nicht prüfbar, Belege fehlen", self.tab.js("window._frage2"))
        self.assertEqual(self.con.execute("SELECT status FROM bogen WHERE id = ?", (self.m,)).fetchone()[0], "aktiv")

