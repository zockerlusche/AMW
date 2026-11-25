"""A2029 (TH164 F2 Schritt 5): Abschluss je Meilenstein – vor „bereit zur Abnahme“ laufen Gesamttest und Prüfer gegen das
Konzept (einmal je Stand); erfüllt → bereit mit Prüfung und Vorführung im Bericht; nicht erfüllt oder Test rot → die AMW legt
Nacharbeit im selben Meilenstein an und startet sie ohne neues Ja; „Nacharbeit anfordern“ plant mit Hinweis neue Pakete."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import abschluss, db, feinplanung, kern, planautomatik, planer, planung, themen


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        u.start()
        self.addCleanup(u.stop)
        os.environ.pop("AMW_PLANER_AUS", None)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
            from amw import schalter
            schalter._setzen(self.con, self.pid, "an")
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.t1 = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        self.t2 = themen.neu(self.con, self.pid, "TL", "Sicherung", pfleger="CC1")
        self.m = planung.bogen_neu(self.con, self.pid, "TL", "Anmelden", ziel=f"TH{self.t1} Anmeldung, TH{self.t2} Sicherung",
                                   abnahme="Vorführung beim Menschen")
        self.a1 = planung.schritt_setzen(self.con, self.pid, "TL", titel="Login", bogen_id=self.m, agent="CC1")
        self.a2 = planung.schritt_setzen(self.con, self.pid, "TL", titel="Nachtsicherung", bogen_id=self.m, agent="CC1")
        planung.bogen_status(self.con, self.pid, "TL", self.m, "aktiv")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc1234', fertig_utc = ? WHERE bogen_id = ?", (db.jetzt(), self.m))
        self.gestartet = []
        s = mock.patch.object(abschluss, "STARTER", lambda pid, bid, stand: self.gestartet.append((bid, stand)) or 4711)
        s.start()
        self.addCleanup(s.stop)
        f = mock.patch.object(feinplanung, "STARTER", lambda _pid, boegen, fassung: self.gestartet.append(("fein", boegen, fassung)) or 1)
        f.start()
        self.addCleanup(f.stop)

    def runde(self):
        return planautomatik.meilenstein_projekt(self.con, self.pid)

    def stand(self):
        return self.gestartet[0][1]

    def urteil(self, erfuellt=(True, True), nacharbeit=None):
        return {"themen": [{"thema": f"TH{self.t1}", "erfuellt": erfuellt[0], "beleg": "A%d Login" % self.a1, "fehlt": None if erfuellt[0] else "SSO fehlt"},
                           {"thema": f"TH{self.t2}", "erfuellt": erfuellt[1], "beleg": "A%d" % self.a2}],
                "vorfuehrung": ["Seite öffnen", "mit Firmenkonto anmelden"], **({"nacharbeit": nacharbeit} if nacharbeit else {})}

    def post(self, an):
        return [(r["art"], r["kurz"]) for r in self.con.execute(
            "SELECT n.art, n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? AND n.von = 'AMW' ORDER BY n.id", (an,))]

    def offen(self):
        return [r[0] for r in self.con.execute("SELECT titel FROM aufgabe WHERE bogen_id = ? AND status != 'fertig' ORDER BY id", (self.m,))]


class VorDerAbnahme(Grund):
    def test_erst_pruefen_dann_bereit(self):
        self.assertEqual(self.runde(), [])                                                 # nicht „bereit“: die Prüfung läuft
        self.assertEqual(len(self.gestartet), 1)
        self.assertEqual(self.runde(), [])                                                 # einmal je Stand
        self.assertEqual(len(self.gestartet), 1)
        e = abschluss.eintragen(self.con, self.pid, self.m, self.stand(), {"lauf": 7, "rc": 0, "befehl": "python -m unittest"}, self.urteil())
        self.assertTrue(e["ok"])
        self.assertEqual(self.runde(), [(self.m, "bereit")])
        from amw import tore
        text = tore.bericht_text(self.con, self.pid, self.m)
        self.assertIn("## Prüfung gegen das Konzept", text)
        self.assertIn("Gesamttest: L7 · rc 0 · grün", text)
        self.assertIn(f"- TH{self.t1}: erfüllt", text)
        self.assertIn("1. Seite öffnen", text)

    def test_nicht_erfuellt_nacharbeit_ohne_neues_ja(self):
        self.runde()
        n = [{"schluessel": "N1", "meilenstein": "M1", "thema": f"TH{self.t1}", "titel": "SSO ergänzen", "auftrag": "Firmenkonto anbinden.",
              "groesse": "M", "art": "sicherheit", "ausfuehrung": "agent", "fertig_quelle": "commit", "interaktiv_grund": "gesperrter Bereich"}]
        e = abschluss.eintragen(self.con, self.pid, self.m, self.stand(), {"lauf": 7, "rc": 0, "befehl": "x"}, self.urteil((False, True), n))
        self.assertFalse(e["ok"])
        self.assertEqual(self.offen(), ["SSO ergänzen"])
        self.assertEqual(self.runde(), [])                                                 # offenes Paket: nicht bereit
        self.assertIn(("meldung", "Meilenstein 1: Nacharbeit – 1 Paket(e) gestartet"), self.post("TL"))
        self.assertIn(("info", "Meilenstein 1: Nacharbeit – 1 Paket(e) gestartet"), self.post(kern.ENTWICKLER))

    def test_test_rot_ohne_vorschlag_legt_ein_paket_an(self):
        self.runde()
        abschluss.eintragen(self.con, self.pid, self.m, self.stand(), {"lauf": 9, "rc": 1, "befehl": "x"}, self.urteil())
        self.assertEqual(self.offen(), ["Gesamttest rot beheben (L9)"])

    def test_pruefer_ging_nicht_dann_bereit_wie_bisher(self):
        self.runde()
        abschluss.eintragen(self.con, self.pid, self.m, self.stand(), {"befehl": None, "rc": None}, None, fehler="Zeitüberschreitung")
        self.assertEqual(self.runde(), [(self.m, "bereit")])
        self.assertIn(("meldung", "Meilenstein 1: Abschlussprüfung ging nicht"), self.post("TL"))

    def test_ohne_planer_gleich_bereit(self):
        os.environ["AMW_PLANER_AUS"] = "1"
        self.assertEqual(self.runde(), [(self.m, "bereit")])
        self.assertEqual(self.gestartet, [])

    def test_pruefer_muss_jedes_thema_bewerten(self):
        from amw import planer
        u = self.urteil()
        u["themen"] = u["themen"][:1] + [{"thema": "TH999", "erfuellt": True, "beleg": "x"}]
        b = planung.bogen_zeile(self.con, self.pid, self.m)
        with self.assertRaises(planer.PlanFehler) as x:
            abschluss._pruefen(u, self.con, self.pid, b, False)
        self.assertIn(f"nicht bewertet: TH{self.t2}", " ".join(x.exception.fehler))
        with self.assertRaises(planer.PlanFehler) as x:
            abschluss._pruefen(self.urteil((False, True)), self.con, self.pid, b, False)
        self.assertIn("keine nacharbeit", " ".join(x.exception.fehler))


class NurDieEigenen(Grund):
    """A2083: Nacharbeit in einem laufenden Meilenstein startet nur die eigenen Pakete; zurückgehaltene und der Plan-Stand bleiben."""
    def setUp(self):
        super().setUp()
        from amw import arbeitspaket, fertigquelle, reihenfolge
        self.nachbar = planung.schritt_setzen(self.con, self.pid, "TL", titel="Zurückgehalten", auftrag="später", bogen_id=self.m, groesse="S",
                                              art="mechanisch", pruefbefehl="python -m unittest tests.test_y", dateibereich="app/y.py")
        arbeitspaket.setzen(self.con, self.pid, "TL", self.nachbar, art="p", modell="sonnet")
        themen.verweise_setzen(self.con, self.pid, "TL", self.nachbar, [self.t1])
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="TL", art=fertigquelle.ART, aufgabe_id=self.nachbar,
                         text=json.dumps({"art": "commit"}))
            reihenfolge.plan_stand_merken(self.con, self.pid, "TL", self.m)
        a = self.con.execute("SELECT * FROM aufgabe WHERE id = ?", (self.nachbar,)).fetchone()
        self.assertEqual(reihenfolge.fehlende_felder(self.con, self.pid, a), [])                  # könnte starten – der Lead hält es zurück
        self.vorher = self.plan_stand()
        self.assertEqual(len(self.vorher), 1)

    def plan_stand(self):
        from amw import reihenfolge
        return [tuple(r) for r in self.con.execute("SELECT id, text FROM plan_ereignis WHERE art = ? AND bogen_id = ?", (reihenfolge.PLAN_STAND, self.m))]

    def zustand(self, titel):
        from amw import arbeitspaket
        return arbeitspaket.lesen(self.con, self.con.execute("SELECT id FROM aufgabe WHERE titel = ?", (titel,)).fetchone()[0])["zustand"]

    def paket(self, schluessel="N1"):
        return {"schluessel": schluessel, "meilenstein": "M1", "thema": f"TH{self.t1}", "titel": "SSO ergänzen", "auftrag": "Firmenkonto anbinden.", "groesse": "S",
                "art": "mechanisch", "ausfuehrung": "p", "fertig_quelle": "commit", "abnahme_befehl": "python -m unittest tests.test_sso", "bereiche": "app/sso.py"}

    def automatisch(self):
        abschluss.eintragen(self.con, self.pid, self.m, "[Probe]", {"lauf": 7, "rc": 0, "befehl": "x"}, self.urteil((False, True), [self.paket()]))

    def angefordert(self):
        abschluss.nacharbeit(self.con, self.pid, kern.ENTWICKLER, self.m, "Firmenkonto fehlt")
        feinplanung.entwurf_eintragen(self.con, self.pid, [self.m], 1, {"pakete": [self.paket("P1")]})

    def pruefe(self):
        self.assertEqual(self.zustand("SSO ergänzen"), "startklar")
        self.assertEqual(self.zustand("Zurückgehalten"), "entwurf")
        self.assertEqual(self.plan_stand(), self.vorher)

    def test_automatische_nacharbeit(self):
        self.automatisch()
        self.pruefe()

    def test_angeforderte_nacharbeit(self):
        self.angefordert()
        self.pruefe()

    def test_fehlende_angaben_stehen_in_der_meldung(self):
        from amw import reihenfolge
        for weg in (self.automatisch, self.angefordert):
            with self.subTest(weg=weg.__name__), mock.patch.object(reihenfolge, "fehlende_felder", return_value=["Bereiche"]):
                weg()
                text = self.con.execute("SELECT n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = 'TL' AND n.von = 'AMW'"
                                        " AND n.kurz LIKE '%Nacharbeit%' ORDER BY n.id DESC").fetchone()[0]
                self.assertIn("Starten noch nicht, Angaben fehlen", text)
                self.assertIn("SSO ergänzen: Bereiche", text)
            with db.schreiben(self.con):
                self.con.execute("UPDATE aufgabe SET status = 'verworfen', beleg = 'Probe' WHERE titel = 'SSO ergänzen'")


class NacharbeitAnfordern(Grund):
    def test_feinplaner_mit_hinweis_und_sofort_gestartet(self):
        r = abschluss.nacharbeit(self.con, self.pid, kern.ENTWICKLER, self.m, "Die Anmeldung braucht noch das Firmenkonto")
        self.assertTrue(r["gestartet"], r)
        self.assertEqual(self.gestartet[-1], ("fein", [self.m], 1))
        plan = {"pakete": [{"schluessel": "P1", "meilenstein": "M1", "thema": f"TH{self.t1}", "titel": "Firmenkonto anbinden",
                            "auftrag": "SSO.", "groesse": "M", "art": "sicherheit", "ausfuehrung": "agent", "fertig_quelle": "commit",
                            "interaktiv_grund": "gesperrter Bereich"}]}
        e = feinplanung.entwurf_eintragen(self.con, self.pid, [self.m], 1, plan)
        self.assertTrue(e.get("nacharbeit"))
        self.assertEqual(self.offen(), ["Firmenkonto anbinden"])
        self.assertIn(("meldung", "Nacharbeit M1: 1 Pakete angelegt und gestartet"), self.post("TL"))
        text = self.con.execute("SELECT text FROM nachricht WHERE von = 'AMW' AND kurz LIKE 'Nacharbeit M1:%'").fetchone()[0]
        self.assertIn("es braucht kein neues Ja", text)                                    # A2086 (9)
        self.assertNotIn("Ja = Start", text)

    def test_rechte_und_hinweis(self):
        with self.assertRaisesRegex(kern.AmwFehler, "Mensch oder der Lead"):
            abschluss.nacharbeit(self.con, self.pid, "CC1", self.m, "x")
        with self.assertRaisesRegex(kern.AmwFehler, "was fehlt"):
            abschluss.nacharbeit(self.con, self.pid, "TL", self.m, " ")
        planung.bogen_status(self.con, self.pid, "TL", self.m, "fertig", automatik=True)
        with self.assertRaisesRegex(kern.AmwFehler, "laufenden Meilenstein"):
            abschluss.nacharbeit(self.con, self.pid, "TL", self.m, "x")

    def test_befehl_und_einstieg(self):
        from amw import cli, planer
        aus = io.StringIO()
        mensch = {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}
        with mock.patch.dict(os.environ, mensch), contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "P", "bogen", "nacharbeit", str(self.m), "--hinweis", "SSO fehlt", "--von", "Entwickler"])
        self.assertEqual(rc, 0, aus.getvalue())
        self.assertIn("angestoßen", aus.getvalue())
        with mock.patch.object(abschluss, "ausfuehren") as a, mock.patch("amw.db.verbinde", return_value=mock.MagicMock()):
            planer.main(["--abschluss", "--projekt-id", "3", "--bogen", "7", "--stand", "[Stand 1 · x]"])
        self.assertEqual(a.call_args[0][1:], (3, 7, "[Stand 1 · x]"))


class Grenzen(Grund):
    """TL #31785: Kosten- und Schleifenschutz."""
    def n(self, titel):
        return [{"schluessel": "N1", "meilenstein": "M1", "thema": f"TH{self.t1}", "titel": titel, "auftrag": "Nachbessern.",
                 "groesse": "S", "art": "text", "ausfuehrung": "agent", "fertig_quelle": "commit", "interaktiv_grund": "Prüfer-Befund"}]

    def alle_fertig(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'def5678', fertig_utc = ? WHERE bogen_id = ? AND status != 'fertig'",
                             (db.jetzt(), self.m))

    def test_tagesgrenze_gilt_auch_fuer_den_pruefer(self):
        from amw import planer
        kern.projekt_einstellen(self.con, self.pid, "TL", planer_tagesgrenze_usd="0.5")
        abschluss.eintragen(self.con, self.pid, self.m, "[alter Stand]", {"befehl": None, "rc": None}, self.urteil(), usd=0.7)
        self.assertEqual(planer.heute_usd(self.con, self.pid), 0.7)                        # Prüfer-Kosten zählen mit
        self.assertEqual(self.runde(), [(self.m, "bereit")])                               # nicht gestartet, bereit wie bisher
        self.assertEqual(self.gestartet, [])
        e = abschluss.ergebnis(self.con, self.pid, self.m)
        self.assertIsNotNone(e)
        self.assertIn("Tagesgrenze", (e or {})["fehler"])

    def test_hoechstens_zwei_automatische_runden(self):
        titel = {1: "Firmenkonto anbinden", 2: "Fehlermeldung beim Anmelden verbessern", 3: "Sitzung nach Abmeldung beenden"}
        for i in (1, 2):
            self.runde()
            stand = self.gestartet[-1][1]
            e = abschluss.eintragen(self.con, self.pid, self.m, stand, {"befehl": None, "rc": None}, self.urteil((False, True), self.n(titel[i])))
            self.assertTrue(e["angelegt"], i)
            self.alle_fertig()
        self.runde()
        e = abschluss.eintragen(self.con, self.pid, self.m, self.gestartet[-1][1], {"befehl": None, "rc": None},
                                self.urteil((False, True), self.n(titel[3])))
        self.assertEqual((e["angelegt"], e.get("grenze")), ({}, True))                    # keine dritte Runde
        self.assertEqual(self.offen(), [])
        self.assertEqual(self.runde(), [(self.m, "bereit")])
        self.assertIn(("meldung", "Meilenstein 1: nach 2 Nacharbeits-Runden noch offen"), self.post("TL"))
        from amw import tore
        self.assertIn("Nach 2 automatischen Nacharbeits-Runden noch offen", tore.bericht_text(self.con, self.pid, self.m))


class AntwortLesen(Grund):
    """A2072 (Lead #32391): die erste echte Abschlussprüfung (M18) scheiterte mit „oben muss ein Objekt stehen“ – der Prüfer
    liefert Text, _pruefen las ihn nie als JSON. Jetzt: Text lesen, einmal nachbessern, Rohantwort bei Fehlern behalten."""

    def test_text_antwort_wird_als_json_gelesen(self):
        self.runde()
        roh = "Hier mein Urteil:\n```json\n" + json.dumps(self.urteil()) + "\n```"
        e = abschluss.eintragen(self.con, self.pid, self.m, self.stand(), {"befehl": None, "rc": None}, planer.json_aus_text(roh))
        self.assertTrue(e["ok"], e.get("fehler"))
        self.assertEqual([t["erfuellt"] for t in e["themen"]], [True, True])
        self.assertNotIn("roh", e)                                                         # ohne Fehler bleibt die Rohantwort weg

    def test_kein_json_fehler_mit_rohantwort_im_bericht(self):
        from amw import tore
        self.runde()
        e = abschluss.eintragen(self.con, self.pid, self.m, self.stand(), {"befehl": None, "rc": None}, "{nicht: json}",
                                roh="Ich konnte die Dateien nicht lesen. {nicht: json}")
        self.assertIn("kein JSON", e["fehler"])
        self.assertTrue(e["roh"].startswith("Ich konnte die Dateien nicht lesen"))
        self.assertIn("Anfang seiner Antwort: Ich konnte", tore.bericht_text(self.con, self.pid, self.m))

    def test_einmal_nachbessern(self):
        b = planung.bogen_zeile(self.con, self.pid, self.m)
        halb = self.urteil()
        halb["themen"] = halb["themen"][:1]
        antworten, auftraege = [json.dumps(halb), json.dumps(self.urteil())], []

        def attrappe(_con, _pid, _b, _test, prog=None, zusatz=None, nachbessern=None):
            auftraege.append(nachbessern)
            return {"ergebnis": antworten[len(auftraege) - 1], "usd": 0.5, "fehler": None, "roh": antworten[len(auftraege) - 1]}
        with mock.patch.object(abschluss, "pruefer", attrappe):
            aus = abschluss.pruefer_mit_nachbesserung(self.con, self.pid, b, {"befehl": None, "rc": None})
        self.assertEqual(len(auftraege), 2)
        self.assertIsNone(auftraege[0])
        self.assertIn(f"nicht bewertet: TH{self.t2}", " ".join(auftraege[1]))                # die Funde gehen zurück
        self.assertEqual((aus["usd"], aus["nachgebessert"]), (1.0, auftraege[1]))
        self.runde()
        e = abschluss.eintragen(self.con, self.pid, self.m, self.stand(), {"befehl": None, "rc": None}, aus["ergebnis"],
                                nachgebessert=aus["nachgebessert"])
        self.assertTrue(e["ok"])
        self.assertIn("einmal nachgebessert", "\n".join(abschluss.bericht_teil(self.con, self.pid, self.m)))

    def test_passt_gleich_kein_zweiter_lauf(self):
        b = planung.bogen_zeile(self.con, self.pid, self.m)
        aufrufe = []
        with mock.patch.object(abschluss, "pruefer", lambda *a, **k: aufrufe.append(k) or {"ergebnis": json.dumps(self.urteil()),
                                                                                          "usd": 0.5, "fehler": None, "roh": "x"}):
            aus = abschluss.pruefer_mit_nachbesserung(self.con, self.pid, b, {"befehl": None, "rc": None})
        self.assertEqual(len(aufrufe), 1)
        self.assertNotIn("nachgebessert", aus)


class EchterWeg(Grund):
    """A2072 (5, Lead #32394): durch den echten Weg – ausfuehren → pruefer → arbeiter.laufen (Attrappe) → eintragen – mit einer
    Antwort als TEXT, wie claude -p sie liefert (Prosa und JSON im Codeblock). Rot gegen 1.186.0."""

    def laufen(self, *antworten):
        self.auftraege = []

        def attrappe(_p, auftrag, *_a, **_k):
            self.auftraege.append(auftrag)
            return {"rc": 0, "abweichungen": [], "ergebnis": {"result": antworten[len(self.auftraege) - 1], "total_cost_usd": 0.25}}
        with mock.patch("amw.arbeiter.laufen", attrappe):
            return abschluss.ausfuehren(self.con, self.pid, self.m, self.stand())

    def test_prosa_und_json_im_codeblock(self):
        self.runde()
        e = self.laufen("Ich habe alle Dateien gelesen. Hier das Urteil:\n\n```json\n" + json.dumps(self.urteil(), ensure_ascii=False, indent=2)
                        + "\n```\n\nViel Erfolg bei der Vorführung!")
        self.assertTrue(e["ok"], e.get("fehler"))
        self.assertEqual(len(self.auftraege), 1)
        self.assertEqual(self.runde(), [(self.m, "bereit")])

    def test_unpassend_dann_nachgebessert(self):
        self.runde()
        halb = self.urteil()
        halb["themen"] = halb["themen"][:1]
        e = self.laufen("Urteil: " + json.dumps(halb), "```json\n" + json.dumps(self.urteil()) + "\n```")
        self.assertTrue(e["ok"], e.get("fehler"))
        self.assertEqual(len(self.auftraege), 2)
        self.assertIn(f"nicht bewertet: TH{self.t2}", self.auftraege[1])
        self.assertEqual((e["usd"], len(e["nachgebessert"])), (0.5, 1))

    def test_zweimal_unpassend_fehler_mit_rohantwort(self):
        self.runde()
        e = self.laufen("Leider kann ich das nicht beurteilen.", "Immer noch nicht.")
        self.assertIn("kein JSON", e["fehler"])
        self.assertEqual(e["roh"], "Immer noch nicht.")
        self.assertEqual(self.runde(), [(self.m, "bereit")])                               # wie bisher: bereit, Prüfung fehlt

    def test_tagesgrenze_gilt_fuer_die_nachbesserung(self):
        self.runde()
        with mock.patch.object(planer, "tagesgrenze", lambda *_: 1.0), mock.patch.object(planer, "heute_usd", lambda *_a, **_k: 0.9):
            e = self.laufen("kein JSON", "nie gefragt")
        self.assertEqual(len(self.auftraege), 1)
        self.assertIn("Tagesgrenze", e["fehler"])


class GruendeInMenschensprache(Grund):
    """A2072 (P633, TH156): die Karte nennt eine Art je Grund – kein technischer Wortlaut, beide Sprachen."""

    def test_jede_fehlerart(self):
        from amw import workbench
        for fehler, arten in (("kein JSON: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)", ["lesbar"]),
                              ("oben muss ein Objekt stehen", ["lesbar"]),
                              ("nicht bewertet: TH3; nicht erfüllt oder Test rot, aber keine nacharbeit", ["unvollstaendig"]),
                              ("ziel: M18 hat keine Themen – ziel braucht erfuellt (ja/nein) und beleg bzw. fehlt", ["unvollstaendig"]),
                              ("Tagesgrenze der Planer erreicht (5.00 von 5.00 $) – Abschlussprüfung nicht gestartet", ["grenze"]),
                              ("Antwort passte nicht (kein JSON: x) – keine Nachbesserung: Tagesgrenze der Planer erreicht", ["grenze", "lesbar"]),
                              ("Prüfer ließ sich nicht starten: [WinError 2]", ["start"]), ("Frist 1200 s überschritten", ["frist"]),
                              ("kein Ergebnis (rc 1)", ["lauf"]), ("AmwFehler: HALT gilt – keine Läufe starten", ["lauf"]), ("etwas Neues", ["sonst"])):
            self.assertEqual([g["art"] for g in abschluss.deuten(fehler)], arten, fehler)
        self.assertEqual(abschluss.deuten(None), [])
        for sprache in ("de", "en"):
            texte = workbench.texte(sprache)
            for art in [a for a, _ in abschluss._GRUENDE] + ["sonst"]:
                self.assertIn("pjw_ax_" + art, texte)


class ErneutStarten(Grund):
    """A2072 (4): ein Ergebnis mit Fehler zählt nicht als Ergebnis – „Prüfung starten“ (A2064) geht dann erneut."""

    def test_nach_fehler_erneut_starten(self):
        from amw import projektweg_seite
        self.runde()
        abschluss.eintragen(self.con, self.pid, self.m, self.stand(), {"befehl": None, "rc": None}, None, fehler="kein JSON: x")
        self.assertEqual(self.runde(), [(self.m, "bereit")])
        frei = {"abnahme": [{"bogen": self.m, "nr": 1, "titel": "Anmelden", "frei": False, "bericht": None}]}
        karte = projektweg_seite.abschluss(self.con, self.pid, frei)[0]
        self.assertEqual((karte["pruefung"]["fehler"], karte["pruefung_laeuft"]), (True, False))
        self.assertEqual(karte["pruefung"]["gruende"], [{"art": "lesbar", "x": {}}])
        self.assertEqual(projektweg_seite.pruefung_starten(self.con, self.pid, "TL", self.m), {"ergebnis": "pruefung"})
        self.assertEqual(len(self.gestartet), 2)
        karte = projektweg_seite.abschluss(self.con, self.pid, frei)[0]
        self.assertEqual((karte["pruefung"], karte["pruefung_laeuft"]), (None, True))         # läuft – nicht der alte Fehler
        with self.assertRaisesRegex(kern.AmwFehler, "läuft schon"):
            projektweg_seite.pruefung_starten(self.con, self.pid, "TL", self.m)
        abschluss.eintragen(self.con, self.pid, self.m, self.stand(), {"befehl": None, "rc": None}, json.dumps(self.urteil()))
        karte = projektweg_seite.abschluss(self.con, self.pid, frei)[0]
        self.assertTrue(karte["pruefung"]["ok"])
        with self.assertRaisesRegex(kern.AmwFehler, "schon ein Prüf-Ergebnis"):                 # Gegenprobe: gutes Ergebnis bleibt
            projektweg_seite.pruefung_starten(self.con, self.pid, "TL", self.m)


class OhneThemen(Grund):
    """A2072: Meilenstein ohne Themen (M18 Wartung) – der Prüfer urteilt im Feld ziel über Ziel und „fertig wenn“."""

    def setUp(self):
        super().setUp()
        self.w = planung.bogen_neu(self.con, self.pid, "TL", "Wartung", ziel="Fehler aus dem Betrieb beheben", abnahme="Bericht")
        planung.schritt_setzen(self.con, self.pid, "TL", titel="Fehler 1", bogen_id=self.w, agent="CC1")
        self.b = planung.bogen_zeile(self.con, self.pid, self.w)
        self.assertEqual(feinplanung.themen_der(self.con, self.pid, self.b), [])

    def test_ziel_statt_themen(self):
        with self.assertRaises(planer.PlanFehler) as x:
            abschluss._pruefen({"themen": [], "vorfuehrung": []}, self.con, self.pid, self.b, False)
        self.assertIn("hat keine Themen – ziel braucht", " ".join(x.exception.fehler))
        e = abschluss._pruefen({"themen": [], "ziel": {"erfuellt": True, "beleg": "alle Fehler behoben"}}, self.con, self.pid, self.b, False)
        self.assertTrue(e["ok"])
        self.assertEqual(e["ziel"]["beleg"], "alle Fehler behoben")
        with self.assertRaises(planer.PlanFehler) as x:                                   # nicht erfüllt ohne Nacharbeit
            abschluss._pruefen({"themen": [], "ziel": {"erfuellt": False, "fehlt": "Fehler 1 offen"}}, self.con, self.pid, self.b, False)
        self.assertIn("keine nacharbeit", " ".join(x.exception.fehler))

    def test_meilenstein_datei_sagt_es_und_bericht_zeigt_ziel(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            abschluss._dateien(self.con, self.pid, self.b, {"befehl": None}, d)
            with open(os.path.join(d, "meilenstein.md"), encoding="utf-8") as f:
                self.assertIn("keine: urteile im Feld ziel", f.read())
        self.assertIn("Feld ziel", abschluss.AUFTRAG)
        self.assertIn('"ziel"', abschluss.SCHEMA_TEXT)
        abschluss.eintragen(self.con, self.pid, self.w, "s1", {"befehl": None, "rc": None},
                            json.dumps({"themen": [], "ziel": {"erfuellt": True, "beleg": "alle Fehler behoben"}}))
        self.assertIn("- Ziel und „fertig wenn“: erfüllt – alle Fehler behoben", abschluss.bericht_teil(self.con, self.pid, self.w))


if __name__ == "__main__":
    unittest.main()
