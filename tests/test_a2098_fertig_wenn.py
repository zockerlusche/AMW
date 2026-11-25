"""A2098: die Abschlussprüfung beurteilt immer auch „fertig, wenn“, nicht nur die Themen. Verlangt es etwas, das kein Code zeigt, und es
gibt keinen Nachweis, ist es „nicht prüfbar“ – keine Nacharbeit, Meldung an den Lead. Der Weg ist der echte (Text-Antwort)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
from unittest import mock

from amw import abschluss, abschlusslage, db, dokumente, kern, planansicht, planung, projektweg_seite, tore
from tests import test_a2088_abschluss

FERTIG = "Bericht: Probe an einer Kopie (Probe durch den anderen Lead)"


class Grund(test_a2088_abschluss.Grund):
    FERTIG: str | None = FERTIG

    def setUp(self):
        super().setUp()
        with db.schreiben(self.con):
            self.con.execute("UPDATE bogen SET abnahme = ? WHERE id = ?", (self.FERTIG, self.m))

    def mit(self, erfuellt=True, **werte):
        return self.text(ziel={"erfuellt": erfuellt, "beleg": None, "fehlt": None, **werte})

    def dokument(self, text=b"Die Probe lief: 5 Verweise gefunden, 5 gesetzt.", **bezug):
        return dokumente.ablegen_inhalt(self.con, self.pid, "CC1", text, "probe.md", titel="Probe an der Kopie", art="bericht", **bezug)


class EchterWeg(Grund):
    def test_erfuellt(self):
        e = self.laufen(self.mit(beleg="D1: die Probe lief"))
        self.assertTrue(e["ok"], e.get("fehler"))
        self.assertEqual((e["ziel"]["zustand"], self.lage(), len(self.auftraege)), ("erfuellt", "bericht", 1))
        self.assertIn(f"Fertig, wenn: {FERTIG}", self.gesehen[0]["meilenstein.md"])
        self.assertIn("- „Fertig, wenn“: erfüllt – D1: die Probe lief", abschluss.bericht_teil(self.con, self.pid, self.m))
        self.assertIn("Erfüllte Themen reichen dafür nicht", self.auftraege[0])

    def test_nicht_erfuellt_mit_nacharbeit(self):
        """Alle Themen erfüllt, „fertig, wenn“ nicht: Meilenstein nicht erfüllt, Nacharbeit wie sonst."""
        e = self.laufen(self.text(ziel={"erfuellt": False, "fehlt": "Die Zählprobe ist nicht gebaut"}, nacharbeit=[self.nach(self.t1)]))
        self.assertEqual((e["ok"], e["ziel"]["zustand"], self.zustaende(e), self.offen()), (False, "nicht_erfuellt", ["erfuellt", "erfuellt"], ["Login bauen"]))
        self.assertEqual((e.get("nicht_pruefbar"), abschluss.wort(e)), (None, "nicht erfüllt"))

    def test_nicht_pruefbar_ohne_nacharbeit(self):
        e = self.laufen(self.mit(False, nicht_pruefbar=True, fehlt="Bericht des anderen Leads"))
        self.assertEqual((e["ok"], e["nicht_pruefbar"], e["angelegt"], self.offen()), (False, True, {}, []))
        self.assertEqual((e["ziel"]["zustand"], [g["art"] for g in e["ziel"]["gruende"]], e["ziel"]["fehlt"]), ("nicht_pruefbar", ["fertig_wenn"], "Bericht des anderen Leads"))
        self.assertEqual((self.zustaende(e), self.lage(), abschluss.wort(e)), (["erfuellt", "erfuellt"], "nicht_pruefbar", "nicht prüfbar"))
        text = self.meldungen("TL", "nicht prüfbar")
        self.assertEqual(len(text), 1)
        for teil in ("der Beleg für „fertig, wenn“ fehlt", FERTIG, "Es fehlt: Bericht des anderen Leads", "amw dokument ablegen", f"bogen pruefung-starten M{self.b()['nr']}"):
            self.assertIn(teil, text[0])
        self.assertNotIn("Ist nur der Beleg falsch", text[0])                               # das gilt fehlenden Commits
        self.assertTrue(abschluss.erneut_moeglich(self.con, self.pid, abschlusslage.ergebnis(self.con, self.pid, self.b())))
        self.assertIn("nicht prüfbar (der Beleg für „fertig, wenn“ fehlt)", "\n".join(abschluss.bericht_teil(self.con, self.pid, self.m)))
        self.assertTrue(planansicht.vorbehalte(self.con, self.pid, self.b())["nur_mensch"])

    def test_vorgeschlagene_nacharbeit_wird_nicht_angelegt(self):
        e = self.laufen(self.text(ziel={"erfuellt": False, "nicht_pruefbar": True, "fehlt": "Bericht"}, nacharbeit=[self.nach(self.t1)]))
        self.assertEqual((e["angelegt"], self.offen(), e["nicht_pruefbar"]), ({}, [], True))

    def test_thema_nicht_erfuellt_und_fertig_wenn_nicht_pruefbar(self):
        """Beides: für das Thema Nacharbeit, „fertig, wenn“ bleibt nicht prüfbar."""
        e = self.laufen(self.text(self.urteil((False, True), [self.nach(self.t1)]), ziel={"erfuellt": False, "nicht_pruefbar": True, "fehlt": "Bericht"}))
        self.assertEqual((self.zustaende(e), e["ziel"]["zustand"], self.offen(), abschluss.wort(e)), (["nicht_erfuellt", "erfuellt"], "nicht_pruefbar", ["Login bauen"], "nicht erfüllt"))

    def test_commit_fehlt_und_kein_nachweis(self):
        self.belege("abc1234", "abc1234")
        e = self.laufen(self.mit(False, nicht_pruefbar=True, fehlt="Bericht"))
        self.assertEqual((self.zustaende(e), e["ziel"]["zustand"]), (["nicht_pruefbar", "nicht_pruefbar"], "nicht_pruefbar"))
        text = self.meldungen("TL", "nicht prüfbar")[0]
        for teil in ("ohne gefundenen Commit", "Ist nur der Beleg falsch", "Es fehlt: Bericht"):
            self.assertIn(teil, text)

    def test_fehlt_das_urteil_bessert_der_pruefer_einmal_nach(self):
        ohne = {k: v for k, v in self.urteil().items() if k != "ziel"}
        e = self.laufen(self.text(ohne), self.mit(beleg="D1"))
        self.assertEqual((e["ok"], len(self.auftraege)), (True, 2))
        self.assertIn("hat ein Ziel bzw. „Fertig, wenn“ – ziel braucht erfuellt", self.auftraege[1])
        e = self.laufen(self.text(ohne), self.text(ohne))
        self.assertIn("ziel braucht erfuellt", e["fehler"])
        self.assertEqual(abschluss.deuten(e["fehler"]), [{"art": "unvollstaendig", "x": {}}])

    def test_widerspruch_ist_ein_fund(self):
        for z in ({"erfuellt": True, "nicht_pruefbar": True, "beleg": "x", "fehlt": "y"}, {"erfuellt": False, "nicht_pruefbar": True, "beleg": "x"},
                  {"erfuellt": False, "nicht_pruefbar": "ja", "fehlt": "y"}):
            with self.subTest(z=z), self.assertRaisesRegex(Exception, "nicht_pruefbar"):
                abschluss._pruefen({**self.urteil(), "ziel": z}, self.con, self.pid, self.b(), False)

    def test_rot_bleibt_rot(self):
        e = self.laufen(self.text(ziel={"erfuellt": False, "nicht_pruefbar": True, "fehlt": "Bericht"}, nacharbeit=[self.nach(self.t1)]),
                        test={"lauf": 7, "rc": 1, "befehl": "x", "ende": ""})
        self.assertEqual((self.offen(), abschluss.wort(e)), (["Login bauen"], "nicht erfüllt"))


class Nachweise(Grund):
    def test_dokumente_und_antworten_liegen_beim_pruefer(self):
        anderer = planung.bogen_neu(self.con, self.pid, "TL", "Anderer", ziel="x", abnahme="y")
        self.dokument(bogen=self.m)
        self.dokument(text=b"Am Paket gemessen: 3 s.", aufgabe=self.a1)
        self.dokument(text=b"gehoert woanders hin", bogen=anderer)
        self.dokument(text=b"z" * 9000, aufgabe=self.a2)
        def status(x):
            with db.schreiben(self.con):
                self.con.execute("UPDATE aufgabe SET status = ? WHERE id = ?", (x, self.a1))
        status("laeuft")                                                                    # gefragt, solange das Paket lief
        fid = kern.frage_neu(self.con, self.pid, "TL", "entwickler", "Gilt die Probe?", [("A", "ja"), ("B", "nein")],
                             empfehlung="A", grund="g", aufgabe_id=self.a1, pruefen=False, geprueft="keine Treffer")
        self.assertIn("## Antworten\n- keine", abschluss._nachweise(self.con, self.pid, self.b()))      # offen ist keine Antwort
        kern.frage_antworten(self.con, self.pid, fid, "option", "A", "seite")
        status("fertig")
        self.laufen(self.mit(beleg="D1"))
        n = self.gesehen[0]["nachweise.md"]
        for teil in ("5 Verweise gefunden", f"[bericht, A{self.a1}, von CC1", "[bericht, Meilenstein, von CC1", "Am Paket gemessen: 3 s.", "Gilt die Probe?", "gekürzt: 6000 von 9000"):
            self.assertIn(teil, n)
        self.assertNotIn("woanders", n)
        self.assertNotIn("- keine", n)
        self.assertNotIn("z" * 6001, n)

    def test_grenze_insgesamt_und_nichts_da(self):
        self.assertEqual(abschluss._nachweise(self.con, self.pid, self.b()).count("- keine"), 2)
        for i in range(12):
            self.dokument(text=bytes(str(i), "ascii") * 5900, bogen=self.m)
        n = abschluss._nachweise(self.con, self.pid, self.b())
        self.assertLess(len(n), abschluss.NACHWEISE_ZEICHEN + 3000)
        self.assertIn("(gekürzt: 0 von", n)
        self.assertEqual(n.count("### D"), 12)                                              # die Titel stehen alle da


class OhneText(Grund):
    FERTIG = None

    def test_ohne_text_entfaellt_es(self):
        with db.schreiben(self.con):                                                        # die Themen stehen im Titel
            self.con.execute("UPDATE bogen SET ziel = '', titel = ? WHERE id = ?", (f"Anmelden TH{self.t1} TH{self.t2}", self.m))
        e = self.laufen(self.text({k: v for k, v in self.urteil().items() if k != "ziel"}))
        self.assertTrue(e["ok"], e.get("fehler"))
        self.assertNotIn("ziel", e)
        self.assertFalse(abschluss.alt(self.con, abschluss.ergebnis(self.con, self.pid, self.m)))


class NurZiel(Grund):
    FERTIG = None

    def test_ziel_ohne_fertig_wenn(self):
        self.assertEqual(abschluss.zielsatz(self.b()), ("ziel", f"TH{self.t1} Anmeldung, TH{self.t2} Sicherung"))
        e = self.laufen(self.mit(beleg="app/login.py"))
        self.assertEqual(e["ziel"]["zustand"], "erfuellt")
        self.assertIn("- Ziel: erfüllt – app/login.py", abschluss.bericht_teil(self.con, self.pid, self.m))


class Vorher(Grund):
    def vorher(self):
        """Ein Ergebnis wie von 1.192.0: Themen erfüllt, „fertig, wenn“ nicht beurteilt."""
        self.laufen(self.mit(beleg="D1"))
        with db.schreiben(self.con):
            r = self.con.execute("SELECT id, text FROM plan_ereignis WHERE art = ? ORDER BY id DESC LIMIT 1", (abschluss.ERGEBNIS,)).fetchone()
            self.con.execute("UPDATE plan_ereignis SET text = ? WHERE id = ?", (json.dumps({k: v for k, v in json.loads(r["text"]).items() if k != "ziel"}), r["id"]))

    def test_zaehlt_wie_eine_pruefung_von_vorher(self):
        self.vorher()
        e = abschlusslage.ergebnis(self.con, self.pid, self.b())
        self.assertEqual(abschluss.alt(self.con, e), "fertig_wenn")
        self.assertTrue(abschluss.erneut_moeglich(self.con, self.pid, e))
        with mock.patch.object(tore, "bericht", return_value=1):
            vb = planansicht.vorbehalte(self.con, self.pid, self.b())
        self.assertEqual((vb["alt"], vb["nur_mensch"], vb["warum"]), ("fertig_wenn", True, "die Prüfung ist von vor dieser Version, „fertig, wenn“ ist nicht beurteilt"))
        self.assertIn("Prüfung von vor dieser Version: „fertig, wenn“ ist nicht beurteilt.", abschluss.bericht_teil(self.con, self.pid, self.m))
        self.assertEqual(projektweg_seite._belege(self.con, e, False)["alt"], "fertig_wenn")
        self.laufen(self.mit(beleg="D1"))                                                   # neu geprüft: nicht mehr
        self.assertFalse(abschluss.alt(self.con, abschlusslage.ergebnis(self.con, self.pid, self.b())))


class Seite(test_a2088_abschluss.Seite):
    """Die Zeile „Fertig, wenn“ auf der Karte wie ein Thema; ihr Text auf Klick."""
    def ziel(self):
        self.auf()
        return "[...document.querySelectorAll('.pjw-ab-karte .pjw-pruefung details')].find(x => x.querySelector('summary').textContent.includes(t('pjw_ziel_fertig')))"

    def test_vorbehalt_ueber_dem_knopf_mit_rueckfrage(self):
        z = self.ziel()
        self.assertEqual(self.tab.js(f"{z}.querySelector('summary').innerText"), "„Fertig, wenn“ erfüllt – Anmeldung und Sicherung sind für die Vorführung da")
        self.assertFalse(self.tab.js(f"{z}.open"))
        self.tab.js(f"{z}.querySelector('summary').click()")
        self.assertEqual(self.tab.js(f"{z}.querySelector('.pjw-zielsatz').innerText"), "Vorführung beim Menschen")


class SeiteNichtPruefbar(Seite):
    def daten(self):
        super().daten()
        with db.schreiben(self.con):
            r = self.con.execute("SELECT id, text FROM plan_ereignis WHERE art = ? ORDER BY id DESC LIMIT 1", (abschluss.ERGEBNIS,)).fetchone()
            e = {**json.loads(r["text"]), "ok": False, "nicht_pruefbar": True,
                 "ziel": {"erfuellt": False, "zustand": "nicht_pruefbar", "gruende": [{"art": "fertig_wenn", "n": 1}], "beleg": None, "fehlt": "der Bericht des Leads"}}
            self.con.execute("UPDATE plan_ereignis SET text = ? WHERE id = ?", (json.dumps(e), r["id"]))

    def test_vorbehalt_ueber_dem_knopf_mit_rueckfrage(self):
        z = self.ziel()
        self.assertEqual(self.tab.js(f"{z}.querySelector('summary').innerText"), "„Fertig, wenn“ nicht prüfbar – der Beleg dafür fehlt")
        self.tab.js(f"{z}.querySelector('summary').click()")
        self.assertIn("Der Prüfer sagt: der Bericht des Leads", self.tab.js(f"{z}.innerText"))
