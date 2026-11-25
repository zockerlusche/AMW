"""A2082 (B2938): „wartet auf dich“ erst, wenn der Mensch abnehmen kann – fehlt die Prüfung oder ging sie nicht, ist es Sache des
Leads; laufende Meilensteine kommen erst zur Abnahme, wenn Lead oder Mensch sie vorlegen."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import unittest
from unittest import mock

from amw import abschluss, abschlusslage, aktionen, cli, db, feinplanung, kern, planansicht, planautomatik, planung, projektweg_seite
from tests import test_a2029_abschluss, test_a2031_feinplanung, test_projektweg_seite
from tests.rundgang import Rundgang

KEIN_TEST = {"befehl": None, "rc": None}


class Grund(test_a2029_abschluss.Grund):
    def setUp(self):
        super().setUp()
        kern.projekt_einstellen(self.con, self.pid, "TL", plan_automatik="an")

    def b(self):
        return self.con.execute("SELECT * FROM bogen WHERE id = ?", (self.m,)).fetchone()

    def lage(self):
        return abschlusslage.lage(self.con, self.pid, self.b())

    def jetzt(self):
        return abschlusslage.stand(self.con, self.b())

    def ergebnis(self, gut=True, fehler=None, test=None):
        return abschluss.eintragen(self.con, self.pid, self.m, self.jetzt(), test or KEIN_TEST,
                                   json.dumps(self.urteil()) if gut and not fehler else None, fehler=fehler)

    def karte(self):
        d = projektweg_seite.daten(self.con, self.pid)
        return next((x for x in d["abschluss"] if x["bogen"] == self.m), {}), next(s for s in d["schritte"] if s["schritt"] == "abschluss"), d

    def alt_bereit(self):
        """Wie M15/M16: bereit gemeldet, bevor es die Prüfung gab (bzw. ohne Ergebnis)."""
        with mock.patch.object(abschluss, "vor_bereit", return_value="melden"), mock.patch.object(abschlusslage, "melden"), \
                mock.patch.object(abschlusslage, "nur_lead", return_value=False):
            planautomatik.meilenstein_projekt(self.con, self.pid)

    def anzahl(self, an, wort):
        return sum(wort in k for _, k in self.post(an))

    def paket(self, titel="Neu", status="wartet"):
        aid = planung.schritt_setzen(self.con, self.pid, "TL", titel=titel, bogen_id=self.m, agent="CC1")
        if status == "fertig":
            self.fertig(aid)
        return aid

    def fertig(self, aid, zeit="2030-01-01T00:00:00Z"):
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc1234', fertig_utc = ? WHERE id = ?", (zeit, aid))

    def ohne_lead(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE agent SET rolle = NULL WHERE projekt_id = ?", (self.pid,))
        self.assertIsNone(kern.lead(self.con, self.pid))


class WerIstDran(Grund):
    def test_je_lage_mit_lead(self):
        self.alt_bereit()
        for vor, lage, bei_dir, wer in ((lambda: None, "fehlt", False, ["TL"]),
                                        (lambda: self.ergebnis(fehler="kein JSON: x"), "fehler", False, ["TL"]),
                                        (lambda: projektweg_seite.pruefung_starten(self.con, self.pid, "TL", self.m), "laeuft", False, ["TL"]),
                                        (lambda: self.ergebnis(), "abnehmbar", True, [kern.entwickler_name(self.con, self.pid)])):
            vor()
            x, schritt, _ = self.karte()
            self.assertEqual((self.lage(), x["lage"], x["bei_dir"], schritt["bei_dir"], schritt["wer"]), (lage, lage, bei_dir, bei_dir, wer), lage)
            self.assertEqual((x["bereit"], schritt["zustand"]), (True, "dran"), lage)

    def test_nicht_erfuellt_klaert_der_lead(self):
        self.alt_bereit()
        with db.schreiben(self.con):
            abschluss._ereignis(self.con, self.pid, abschluss.ERGEBNIS, bogen=self.m, stand=self.jetzt(), test={"befehl": "x", "lauf": 1, "rc": 1},
                                themen=[{"thema": f"TH{self.t1}", "erfuellt": True}], vorfuehrung=[], ok=False, angelegt={}, grenze=True)
        x, schritt, _ = self.karte()
        self.assertEqual((x["lage"], x["bei_dir"], schritt["wer"]), ("nicht_erfuellt", False, ["TL"]))

    def test_ohne_lead_wie_bisher(self):
        self.alt_bereit()
        self.ohne_lead()
        for vor, lage in ((lambda: None, "fehlt"), (lambda: self.ergebnis(fehler="kein JSON: x"), "fehler")):
            vor()
            x, schritt, _ = self.karte()
            self.assertEqual((x["lage"], x["bei_dir"], schritt["bei_dir"]), (lage, True, True))

    def test_planung_zeigt_dasselbe(self):
        self.alt_bereit()
        m = next(m for m in planansicht.daten(self.con, self.pid)["meilensteine"] if m["id"] == self.m)
        self.assertEqual((m["bereit"], m["lage"], m["bei_dir"], m["laufend"]), (True, "fehlt", False, False))
        self.ergebnis()
        m = next(m for m in planansicht.daten(self.con, self.pid)["meilensteine"] if m["id"] == self.m)
        self.assertEqual((m["lage"], m["bei_dir"]), ("abnehmbar", True))

    def test_altes_ergebnis_zaehlt_nicht_fuer_neue_pakete(self):
        self.runde()
        self.ergebnis()
        self.runde()
        self.assertEqual(self.lage(), "abnehmbar")
        a = self.paket()
        self.assertIsNone(self.lage())                                     # offenes Paket: nicht bereit
        self.fertig(a)
        self.assertEqual(self.lage(), "fehlt")                             # vorher galt das grüne Ergebnis von vorhin weiter
        self.runde()
        self.assertEqual(self.lage(), "laeuft")


class MeldungAnDenLead(Grund):
    def test_altbestand_einmal_je_stand_mit_befehl(self):
        self.alt_bereit()
        for _ in range(3):
            self.runde()
        self.assertEqual(self.anzahl("TL", "Abschlussprüfung fehlt"), 1)
        text = self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE '%Abschlussprüfung fehlt%'").fetchone()[0]
        self.assertIn("amw bogen pruefung-starten M1", text)                   # A2079: die Projektnummer
        self.assertEqual(self.anzahl(kern.ENTWICKLER, "Abschlussprüfung fehlt"), 0)
        self.ohne_lead()
        self.runde()
        self.assertEqual(self.anzahl("TL", "Abschlussprüfung fehlt"), 1)

    def test_gescheitert_mensch_bekommt_nichts_bis_er_abnehmen_kann(self):
        vorher = self.anzahl(kern.ENTWICKLER, "bereit zur Abnahme")
        self.runde()
        self.ergebnis(fehler="kein JSON: x")
        self.assertEqual(self.runde(), [(self.m, "bereit")])
        self.runde()
        self.assertEqual(self.anzahl(kern.ENTWICKLER, "bereit zur Abnahme"), vorher)
        self.assertEqual((self.anzahl("TL", "Abschlussprüfung ging nicht"), self.anzahl("TL", "bereit zur Abnahme")), (1, 0))
        projektweg_seite.pruefung_starten(self.con, self.pid, "TL", self.m)
        self.runde()
        self.ergebnis()
        for _ in range(3):
            self.runde()
        self.assertEqual(self.anzahl(kern.ENTWICKLER, "bereit zur Abnahme"), vorher + 1)        # genau einmal, jetzt mit Prüfung
        self.assertEqual(self.anzahl("TL", "bereit zur Abnahme"), 1)

    def test_gleich_erfuellt_eine_meldung_wie_bisher(self):
        self.runde()
        self.ergebnis()
        for _ in range(3):
            self.runde()
        self.assertEqual((self.anzahl(kern.ENTWICKLER, "bereit zur Abnahme"), self.anzahl("TL", "bereit zur Abnahme")), (1, 1))

    def test_planer_aus_wie_bisher(self):
        with mock.patch.dict("os.environ", {"AMW_PLANER_AUS": "1"}):
            self.assertEqual(self.runde(), [(self.m, "bereit")])
            self.runde()
            x, schritt, _ = self.karte()
        self.assertEqual((self.anzahl(kern.ENTWICKLER, "bereit zur Abnahme"), self.anzahl("TL", "Abschlussprüfung fehlt")), (1, 0))
        self.assertEqual((x["lage"], x["bei_dir"], schritt["bei_dir"]), ("fehlt", True, True))        # Seite und Nachricht sagen dasselbe
        self.assertEqual(self.karte()[0]["bei_dir"], False)                                            # Planer wieder an: der Lead holt nach


class Befehl(Grund):
    def amw(self, *teile, von="TL"):
        aus, fehler = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(aus), contextlib.redirect_stderr(fehler), mock.patch("sys.argv", ["amw"]):
            rc = cli.main(["--von", von, "bogen", *teile])
        return rc, (aus.getvalue() + fehler.getvalue()).strip()

    def test_pruefung_starten_rechte_und_sperre(self):
        self.alt_bereit()
        m = str(self.m)
        self.assertIn("der Mensch oder der Lead", self.amw("pruefung-starten", m, von="CC1")[1])
        self.assertEqual(self.gestartet, [])
        rc, text = self.amw("pruefung-starten", m)
        self.assertEqual((rc or 0, text), (0, "M1 „Anmelden“: Gesamttest und Prüfung gegen das Konzept laufen"))
        self.assertEqual(len(self.gestartet), 1)
        self.assertIn("läuft schon", self.amw("pruefung-starten", m)[1])
        self.ergebnis()
        self.assertIn("schon ein Prüf-Ergebnis", self.amw("pruefung-starten", m)[1])

    def test_pruefung_starten_tagesgrenze(self):
        from amw import planer
        self.alt_bereit()
        with mock.patch.object(planer, "tagesgrenze", lambda *_: 1.0), mock.patch.object(planer, "heute_usd", lambda *_a, **_k: 2.0):
            self.assertIn("nicht gestartet – Prüfung ging nicht", self.amw("pruefung-starten", str(self.m))[1])
        self.assertEqual(self.gestartet, [])

    def test_laufend_und_vorlegen(self):
        m = str(self.m)
        for falsch in (("laufend", m), ("laufend", m, "vielleicht"), ("vorlegen",)):
            self.assertIn("amw bogen " + falsch[0], self.amw(*falsch)[1])
        self.assertIn("nur der Lead oder der Mensch", self.amw("laufend", m, "an", von="CC1")[1])
        self.assertIn("nicht laufend", self.amw("vorlegen", m)[1])
        self.assertIn("M1 „Anmelden“ ist laufend", self.amw("laufend", m, "an")[1])
        self.assertIn("schon laufend", self.amw("laufend", m, "an")[1])
        self.assertIn("· laufend", self.amw("zeigen", m)[1])
        self.assertIn("nur der Lead oder der Mensch", self.amw("vorlegen", m, von="CC1")[1])
        a = self.paket()
        self.assertIn("ein offenes Paket", self.amw("vorlegen", m)[1])
        self.fertig(a)
        self.assertIn("vorgelegt – Gesamttest und Prüfung gegen das Konzept laufen", self.amw("vorlegen", m)[1])
        self.assertIn("schon vorgelegt", self.amw("vorlegen", m)[1])
        self.assertIn("nicht mehr laufend", self.amw("laufend", m, "aus")[1])
        self.assertNotIn("laufend", self.amw("zeigen", m)[1])
        planung.bogen_status(self.con, self.pid, "TL", self.m, "fertig", automatik=True)
        self.assertIn("ist fertig", self.amw("laufend", m, "an")[1])


class Laufend(Grund):
    def an(self, an=True):
        abschlusslage.schalten(self.con, self.pid, "TL", self.m, an)

    def test_ruht_bis_zur_vorlage_dann_dieselbe_pruefung(self):
        self.an()
        self.assertEqual((self.runde(), self.gestartet), ([], []))         # keine Prüfung, kein „bereit“
        self.assertIsNone(self.lage())
        x, schritt, d = self.karte()
        self.assertFalse(schritt["bei_dir"])
        self.assertEqual([(y["bogen"], y["ruht"]) for y in d["laufende"]], [(self.m, True)])
        with self.assertRaisesRegex(kern.AmwFehler, "amw bogen vorlegen"):
            projektweg_seite.pruefung_starten(self.con, self.pid, "TL", self.m)
        with self.assertRaisesRegex(kern.AmwFehler, "noch nicht"):
            planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m, "abschluss")
        abschlusslage.vorlegen(self.con, self.pid, "TL", self.m)
        self.assertEqual((len(self.gestartet), self.lage()), (1, "laeuft"))
        self.runde()
        self.assertEqual(len(self.gestartet), 1)                           # nicht noch einmal
        self.ergebnis()
        self.assertEqual(self.runde(), [(self.m, "bereit")])
        self.assertEqual(self.lage(), "abnehmbar")
        self.assertEqual(self.anzahl(kern.ENTWICKLER, "bereit zur Abnahme"), 1)

    def test_neues_paket_macht_die_vorlage_ungueltig(self):
        self.an()
        abschlusslage.vorlegen(self.con, self.pid, "TL", self.m)
        self.ergebnis()
        self.runde()
        self.assertEqual(self.lage(), "abnehmbar")
        self.paket(status="fertig")
        self.assertIsNone(self.lage())
        self.assertEqual((self.runde(), len(self.gestartet)), ([], 1))
        abschlusslage.vorlegen(self.con, self.pid, "TL", self.m)
        self.assertEqual(len(self.gestartet), 2)

    def test_aus_bei_gueltiger_vorlage_kein_zweiter_lauf(self):
        self.an()
        abschlusslage.vorlegen(self.con, self.pid, "TL", self.m)
        self.ergebnis()
        self.an(False)
        self.assertEqual(self.runde(), [(self.m, "bereit")])
        self.assertEqual((len(self.gestartet), self.lage()), (1, "abnehmbar"))

    def test_aus_ohne_vorlage_normaler_weg(self):
        self.an()
        self.runde()
        self.an(False)
        self.runde()
        self.assertEqual((len(self.gestartet), self.lage()), (1, "laeuft"))

    def test_wieder_an_braucht_eine_neue_vorlage(self):
        self.an()
        abschlusslage.vorlegen(self.con, self.pid, "TL", self.m)
        self.an(False)
        self.an()
        self.assertIsNone(self.lage())

    def test_schalten_wenn_schon_bereit(self):
        """Wie M18: bereit gemeldet mit gescheiterter Prüfung, dann als laufend geschaltet, später vorgelegt."""
        self.runde()
        self.ergebnis(fehler="kein JSON: x")
        self.runde()
        self.an()
        self.assertIsNone(self.lage())
        abschlusslage.vorlegen(self.con, self.pid, "TL", self.m)
        self.assertEqual((len(self.gestartet), self.lage()), (2, "laeuft"))        # ein Fehler zählt nicht als Ergebnis
        self.ergebnis()
        self.runde()
        self.assertEqual((self.lage(), self.anzahl(kern.ENTWICKLER, "bereit zur Abnahme")), ("abnehmbar", 1))

    def test_ohne_fertig_wenn_schliesst_die_amw_ihn_nicht(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE bogen SET abnahme = '' WHERE id = ?", (self.m,))
        kern.projekt_einstellen(self.con, self.pid, "TL", meilenstein_fertig="automatisch")
        self.an()
        self.assertEqual(self.runde(), [])
        self.assertEqual(self.b()["status"], "aktiv")

    def test_zwei_projekte_getrennt(self):
        with db.schreiben(self.con):
            anders = db.einfuegen(self.con, "projekt", name="Q", angelegt_utc=db.jetzt())
        with self.assertRaisesRegex(kern.AmwFehler, "gibt es nicht"):
            abschlusslage.schalten(self.con, anders, kern.ENTWICKLER, self.m, True)


class Feinplanung(test_a2031_feinplanung.Grund):
    """Lead #32660 (c): ein laufender Meilenstein hält die Feinplanung des nächsten nicht auf."""

    def test_laufender_mit_arbeit_haelt_nicht_auf(self):
        self.grob_alle()
        feinplanung.plan_starten(self.con, self.pid, kern.ENTWICKLER, self.m1)
        self.assertIsNone(feinplanung.anlass(self.con, self.pid))          # M1 hat noch Arbeit vor sich
        abschlusslage.schalten(self.con, self.pid, "TL", self.m1, True)
        self.assertEqual(feinplanung.anlass(self.con, self.pid), "erster")  # NUR ein laufender aktiv: der nächste darf geplant werden
        self.assertEqual([m for m, _ in feinplanung.projekt(self.con, self.pid)], [self.m2])

    def test_neben_einem_normalen_zaehlt_nur_der_normale(self):
        self.grob_alle()
        feinplanung.plan_starten(self.con, self.pid, kern.ENTWICKLER, self.m1)
        wartung = planung.bogen_neu(self.con, self.pid, "TL", "Wartung", abnahme="Laufend")
        self.paket("Fehler", wartung, agent="CC1")
        planung.bogen_status(self.con, self.pid, "TL", wartung, "aktiv")
        self.status(self.a1, "fertig")
        self.status(self.a2, "fertig")
        self.assertIsNone(feinplanung.anlass(self.con, self.pid))
        abschlusslage.schalten(self.con, self.pid, "TL", wartung, True)
        self.assertEqual(feinplanung.anlass(self.con, self.pid), "bereit")


class Seite(Rundgang):
    """Je Zustand die Karte im echten Browser, mit Klick."""
    LEAD = True

    def daten(self):
        from amw import grobplan, planer, schalter
        kern.agent_neu(self.con, self.pid, "CC1")
        self.gestartet = []
        for ziel, f in ((grobplan, lambda *a, **k: 4711), (planer, lambda *a, **k: 4711),
                        (abschluss, lambda pid, bid, stand: self.gestartet.append(bid) or 4711)):
            p = mock.patch.object(ziel, "STARTER", f)
            p.start()
            self.addCleanup(p.stop)
        test_projektweg_seite.demo(self.con, self.pid, "abschluss-ohne")
        self.m1 = self.con.execute("SELECT id FROM bogen WHERE titel = 'Welt sichtbar'").fetchone()[0]
        with db.schreiben(self.con):
            schalter._setzen(self.con, self.pid, "an")
            if not self.LEAD:
                self.con.execute("UPDATE agent SET rolle = NULL WHERE projekt_id = ?", (self.pid,))
        p = mock.patch.dict("os.environ", {"AMW_PLANER_AUS": ""})
        p.start()
        self.addCleanup(p.stop)

    def ergebnis(self, **werte):
        b = self.con.execute("SELECT * FROM bogen WHERE id = ?", (self.m1,)).fetchone()
        t = self.con.execute("SELECT id FROM thema ORDER BY id LIMIT 1").fetchone()[0]
        with db.schreiben(self.con):
            abschluss._ereignis(self.con, self.pid, abschluss.ERGEBNIS, **{
                "bogen": self.m1, "stand": abschlusslage.stand(self.con, b), "test": {"befehl": None, "lauf": None, "rc": None}, "ok": True,
                "themen": [{"thema": f"TH{t}", "erfuellt": True, "beleg": "Szene"}], "ziel": {"erfuellt": True, "beleg": "da", "zustand": "erfuellt"}, "vorfuehrung": [], "angelegt": {}, "belege": {"zweig": "main", "sha": "c" * 40, "pakete": []}, **werte})

    def zeigen(self):
        self.oeffnen("projektweg", "document.querySelector('.pjw-schritt')")
        self.tab.js("zustand.pwSicht = 4; zustand.pwOffen = true; zeige('projektweg', true)")
        self.warten("document.querySelector('.pjw-ab-karte') || document.querySelector('.pjw-a-laufend')")

    def text(self, sel=".pjw-ansicht"):
        return self.tab.js(f"document.querySelector('{sel}').innerText")

    def leiste(self):
        return self.tab.js("document.querySelector('.pjw-schritt[data-schritt=abschluss]').innerText")

    def knopf(self, name):
        return f"[...document.querySelectorAll('.pjw-ansicht button')].find(b => b.textContent === t('{name}'))"


class SeiteMitLead(Seite):
    def test_fehlt_neutral_und_klick(self):
        self.zeigen()
        self.assertIn("Prüfung fehlt, der Lead holt sie nach.", self.text())
        self.assertNotIn("wartet auf dich", self.text())
        self.assertNotIn("dein Ja", self.text())
        self.assertNotIn("wartet auf dich", self.leiste())
        self.assertIn("Prüfung fehlt", self.leiste())
        self.assertEqual(self.tab.js("document.querySelectorAll('.pjw-ab-karte .pjw-nein').length"), 0)     # keine Farbe, solange der Lead dran ist
        k = self.knopf("pjw_a_starten")
        self.assertFalse(self.tab.js(f"{k}.classList.contains('haupt')"))                       # normaler Knopf
        oben = "[...document.querySelectorAll('.pjw-ansicht > .pjw-kopf button')].map(b => b.textContent)"
        self.assertNotIn(self.tab.js("t('pjw_a_starten')"), self.tab.js(oben))                     # oben steht nur, was der Mensch tun soll
        self.assertTrue(self.tab.js("!!" + self.knopf("pjw_nacharbeit")))
        self.tab.js(k + ".click()")
        self.warten("document.querySelector('.pjw-ab-karte') && document.querySelector('.pjw-ab-karte').dataset.lage === 'laeuft'")
        self.assertEqual(self.gestartet, [self.m1])
        self.assertIn("Prüfung läuft.", self.text())

    def test_ging_nicht_neutral_und_klick(self):
        self.ergebnis(fehler="kein JSON: x", ok=False, themen=[])
        self.zeigen()
        self.assertIn("Prüfung ging nicht, der Lead klärt es.", self.text())
        self.assertNotIn("wartet auf dich", self.text() + self.leiste())
        self.tab.js(self.knopf("pjw_a_erneut") + ".click()")
        self.warten("document.querySelector('.pjw-ab-karte') && document.querySelector('.pjw-ab-karte').dataset.lage === 'laeuft'")
        self.assertEqual(self.gestartet, [self.m1])

    def test_abnehmbar_wartet_auf_dich_und_klick(self):
        self.ergebnis()
        self.zeigen()
        self.assertIn("wartet auf dich", self.text())
        self.assertIn("dein Ja", self.text())
        self.assertIn("wartet auf dich", self.leiste())
        self.assertEqual(self.tab.js("document.querySelectorAll('.pjw-ab-karte .pjw-nein').length"), 1)     # „dein Ja“
        k = "document.querySelector('.pjw-ansicht button.haupt')"              # A2088: ohne Gesamttest steht der Knopf in der Karte, unter dem Hinweis
        self.assertIn("abnehmen", self.tab.js(k + ".textContent").lower())
        self.tab.js(k + ".click()")
        self.warten("!document.querySelector('.pjw-ab-karte')")
        self.assertEqual(self.con.execute("SELECT status FROM bogen WHERE id = ?", (self.m1,)).fetchone()[0], "fertig")

    def test_laufend_leises_wort_und_englisch(self):
        abschlusslage.schalten(self.con, self.pid, kern.ENTWICKLER, self.m1, True)
        self.zeigen()
        self.assertIn("laufend – kommt zur Abnahme, wenn der Lead ihn vorlegt", self.text())
        self.assertFalse(self.tab.js("!!document.querySelector('.pjw-ab-karte')"))
        self.assertNotIn("wartet auf dich", self.leiste())
        self.tab.js("zustand.pwSicht = 3; zeige('projektweg', true)")
        self.warten("document.querySelector('.pjw-laufend')")
        self.assertIn("laufend", self.text(".pjw-ums h3"))

    def test_rundgang(self):
        for g, th in (("pc", "hell"), ("handy", "dunkel")):
            self.assertEqual(self.besuchen("projektweg", "a2082-fehlt", bereit="document.querySelector('.pjw-schritt')",
                                           tun="zustand.pwSicht = 4; zustand.pwOffen = true; zeige('projektweg', true)",
                                           danach="document.querySelector('.pjw-ab-karte')", g=g, t=th), [], f"{g} {th}")


class SeiteOhneLead(Seite):
    LEAD = False

    def test_wie_bisher(self):
        self.zeigen()
        self.assertIn("wartet auf dich", self.text())
        self.assertTrue(self.tab.js("!!" + self.knopf("pjw_a_starten")))
        self.assertTrue(self.tab.js("document.querySelector('.pjw-ansicht > .pjw-kopf button.haupt') !== null"))


class KnopfGehtWeiter(Grund):
    def test_mensch_darf_pruefung_starten(self):
        self.alt_bereit()
        self.assertEqual(aktionen.ausfuehren(self.con, self.pid, "/api/projektweg/pruefung-starten", {"bogen": self.m}), {"ergebnis": "pruefung"})


if __name__ == "__main__":
    unittest.main()
