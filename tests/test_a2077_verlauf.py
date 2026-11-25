"""A2077: der Verlauf des Projektwegs zeigt je Schritt, was geschah – abgeleitet aus dem, was die AMW ohnehin speichert (verlauf_quellen),
auch für den Altbestand: Feinplaner, Konzeptänderung, Zuteilung, Start, Abgabe, Prüfung, fertig, Auslieferung, Abschluss. Je Tatsache
eine Quelle, Gleiches hintereinander eine Zeile, Nummern nur auf Klick, Grenze je Schritt. Vorher stand in Umsetzung nichts."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import abschluss, betrieb, cli, db, kern, planung, projektweg_seite, rueckmeldung, themen, verlauf, verlauf_quellen, wissen


def z(h, m=0, s=0, tag=20):
    return f"2026-11-{tag:02d}T{h:02d}:{m:02d}:{s:02d}Z"


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid, "CC2")
        self.m = planung.bogen_neu(self.con, self.pid, "TL", "Bauen", ziel="Z", abnahme="Vorführung")
        planung.bogen_status(self.con, self.pid, "TL", self.m, "aktiv")

    def paket(self, titel, bogen=None, agent: str | None = "CC1"):
        return planung.schritt_setzen(self.con, self.pid, "TL", titel=titel, bogen_id=bogen or self.m, agent=agent)

    def ohne_meilenstein(self, titel="Pflege"):
        return kern.aufgabe_neu(self.con, self.pid, "TL", titel, "CC1")

    def ereignis(self, art, zeit, von="AMW", aufgabe=None, bogen=None, **d):
        text = d.pop("text", None) or json.dumps(d, ensure_ascii=False)
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=zeit, von=von, art=art, aufgabe_id=aufgabe, bogen_id=bogen, text=text)

    def setzen(self, aid, **f):
        with db.schreiben(self.con):
            self.con.execute(f"UPDATE aufgabe SET {', '.join(k + ' = ?' for k in f)} WHERE id = ?", (*f.values(), aid))

    def v(self, schritt=None):
        return [e for e in projektweg_seite.verlauf_gesamt(self.con, self.pid) if schritt in (None, e["schritt"])]

    def zeilen(self, schritt="umsetzung"):
        return [e["zeile"] for e in self.v(schritt)]


class EchterWeg(Grund):
    """Über die Befehle, wie im Betrieb."""

    def test_fenster_paket_vom_start_bis_zur_auslieferung(self):
        a = self.paket("Anmeldung bauen")
        kern.aufgabe_status(self.con, self.pid, "CC1", a, "start")
        with mock.patch("amw.betrieb.voller_sha", lambda con, pid, sha: sha), mock.patch("amw.betrieb.fremde_a_nummern", lambda *x: []), \
                mock.patch("amw.versionsnummer.pruefen"), mock.patch("amw.pruefstufe.stufe", return_value={"stufe": "mittel", "treffer": [], "gruende": [], "dateien": []}):
            p1 = betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "z", "a" * 40, aufgabe_id=a, ohne_bild="x")
        prid = p1["id"] if isinstance(p1, dict) else p1
        betrieb.pruefung_ergebnis(self.con, self.pid, "TL", prid, "gruen")
        kern.aufgabe_status(self.con, self.pid, "TL", a, "fertig", beleg="abc1234", zusammenfassung="Anmeldung geht")
        wissen.release_merge(self.con, self.pid, "TL", "Anmeldung", "abc1234", aufgaben=f"A{a}")
        wissen.release_version(self.con, self.pid, "TL", "1.0.0", "Erste", kette=True, commit_sha="abc1234")
        t = self.zeilen()
        for satz in ("M1: Meilenstein gestartet", "M1: „Anmeldung bauen“ gestartet", "M1: „Anmeldung bauen“ abgegeben", "M1: Prüfung grün – „Anmeldung bauen“",
                     "M1: „Anmeldung bauen“ fertig", "Version 1.0.0 ausgeliefert: 1 Paket"):
            self.assertEqual(t.count(satz), 1, (satz, t))
        e = {x["zeile"]: x for x in self.v("umsetzung")}
        self.assertEqual(e["M1: „Anmeldung bauen“ gestartet"]["von"], "CC1")
        self.assertEqual(e["M1: Prüfung grün – „Anmeldung bauen“"]["rolle"], "pruefer")
        self.assertEqual(e["M1: Prüfung grün – „Anmeldung bauen“"]["lang"], f"P{prid}")            # Nummern nur auf Klick
        self.assertIn(f"A{a} Anmeldung bauen · abc1234", e["Version 1.0.0 ausgeliefert: 1 Paket"]["lang"])
        for satz in t:
            self.assertNotRegex(satz, r"\bP\d|\bL\d|abc1234")

    def test_headless_abgabe_ueber_die_rueckmeldung(self):
        a = self.paket("Texte", agent=None)
        self.ereignis("headless_start", z(8), aufgabe=a, aufgabe_=a, platz=1)
        rueckmeldung.speichern(self.con, self.pid, "AMW", a, {"status": "erledigt"}, "p")
        self.assertEqual([(e["zeile"], e["von"]) for e in self.v("umsetzung")][:1], [("M1: „Texte“ gestartet", "AMW")])
        self.assertIn(("M1: „Texte“ abgegeben", "Headless"), [(e["zeile"], e["von"]) for e in self.v("umsetzung")])

    def test_abschluss_ueber_eintragen(self):
        for test, erg, fehler, satz in (({"befehl": None, "rc": None}, None, "kein JSON: x", "M1: Prüfung ging nicht – Antwort des Prüfers nicht lesbar"),
                                        ({"befehl": None, "rc": None}, json.dumps({"themen": [], "ziel": {"erfuellt": True, "beleg": "b"}}), None,
                                         "M1: Prüfung erfüllt")):
            abschluss.eintragen(self.con, self.pid, self.m, "s", test, erg, fehler=fehler)
            self.assertIn(satz, self.zeilen("abschluss"))
        with db.schreiben(self.con):
            self.con.execute("UPDATE bogen SET status = 'aktiv' WHERE id = ?", (self.m,))
        self.ereignis("bogen_status", z(12, tag=26), von="TL", bogen=self.m, text="aktiv → fertig")
        self.assertEqual(self.zeilen("abschluss")[-1], "M1: abgeschlossen")

    def test_befehl_verlauf_protokoll(self):
        a = self.paket("Anmeldung bauen")
        kern.aufgabe_status(self.con, self.pid, "CC1", a, "start")
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus), mock.patch("sys.argv", ["amw"]):
            cli.main(["--von", "TL", "verlauf", "--art", "protokoll"])
        self.assertIn("„Anmeldung bauen“ gestartet", aus.getvalue())
        self.assertIn("umsetzung", aus.getvalue())


class JeQuelleEinmal(Grund):
    """Dieselbe Tatsache steht an zwei Stellen – im Verlauf einmal."""

    def test_headless_start_nicht_noch_einmal(self):
        a = self.paket("Neu", agent=None)
        self.ereignis("headless_start", z(8), aufgabe=a)
        self.ereignis("paket_zustand", z(8, 0, 1), aufgabe=a, text="startklar → laeuft: Start auf Platz 1")
        self.setzen(a, begonnen_utc=z(8, 0, 2), status="laeuft")
        self.assertEqual(self.zeilen().count("M1: „Neu“ gestartet"), 1)

    def test_altbestand_ohne_headless_start(self):
        a = self.paket("Alt", agent=None)
        self.ereignis("paket_zustand", z(8), aufgabe=a, text="startklar → laeuft: Start auf Platz 1")
        self.setzen(a, begonnen_utc=z(8), status="laeuft")
        self.assertEqual(self.zeilen().count("M1: „Alt“ gestartet"), 1)

    def test_entscheidung_nur_ohne_pruefung(self):
        a, b = self.paket("Mit"), self.paket("Ohne", agent=None)
        with db.schreiben(self.con):
            db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=a, zweig="z", sha="a" * 40, bauer="CC1", pruefer="AMW", ergebnis="gruen",
                         angefragt_utc=z(9), ergebnis_utc=z(9, 30))
        self.ereignis("paket_entscheidung", z(9, 30), aufgabe=a, zeile="E7")
        self.ereignis("paket_entscheidung", z(10), aufgabe=b, zeile="E7")
        self.ereignis("paket_entscheidung", z(11), aufgabe=b, zeile="E5")
        self.ereignis("paket_entscheidung", z(12), aufgabe=b, zeile="E4")
        t = self.zeilen()
        self.assertEqual([x for x in t if "Mit" in x and "Prüfung" in x], ["M1: Prüfung grün – „Mit“"])
        self.assertNotIn("M1: geprüft und angenommen – „Mit“", t)
        for x in ("M1: geprüft und angenommen – „Ohne“", "M1: Nachbesserung – „Ohne“", "M1: geht an den Lead – „Ohne“"):
            self.assertIn(x, t)

    def test_wieder_geoeffnet_nur_der_letzte_abschluss(self):
        """Lead (a): wie A2072/A2073 am 24.11."""
        a = self.paket("Doppelt")
        kern.aufgabe_status(self.con, self.pid, "TL", a, "fertig", beleg="abc1234", zusammenfassung="x")
        self.setzen(a, status="wartet", fertig_utc=None)
        kern.aufgabe_status(self.con, self.pid, "TL", a, "fertig", beleg="abc1234", zusammenfassung="x")
        self.assertEqual(self.zeilen().count("M1: „Doppelt“ fertig"), 1)

    def test_headless_abgabe_nicht_noch_einmal_aus_der_pruefung(self):
        a = self.paket("Abgabe", agent=None)
        self.ereignis("paket_ergebnis", z(9), aufgabe=a, quelle="p")
        with db.schreiben(self.con):
            db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=a, zweig="z", sha="a" * 40, bauer="AMW", pruefer="TL", ergebnis="gruen",
                         angefragt_utc=z(9, 5), ergebnis_utc=z(9, 30))
        self.assertEqual([(e["zeile"], e["von"]) for e in self.v("umsetzung") if "abgegeben" in e["zeile"]], [("M1: „Abgabe“ abgegeben", "Headless")])

    def test_auto_fertig_ist_kein_zweiter_eintrag(self):
        a = self.paket("Auto")
        kern.aufgabe_status(self.con, self.pid, "TL", a, "fertig", beleg="abc1234", zusammenfassung="x")
        self.ereignis("auto_fertig", db.jetzt(), aufgabe=a, text="x")
        self.assertEqual(len([x for x in self.zeilen() if "Auto" in x and "fertig" in x]), 1)

    def test_pflege_ohne_meilenstein_und_fremde_auslieferung_nicht(self):
        """Lead (b): eine Version ohne Aufgaben mit Meilenstein steht nicht in Umsetzung."""
        a = self.ohne_meilenstein()
        self.setzen(a, begonnen_utc=z(8), status="fertig", fertig_utc=z(9), beleg="abc1234")
        with db.schreiben(self.con):
            db.einfuegen(self.con, "release", projekt_id=self.pid, art="version", version="1.0.1", zeit_utc=z(10), titel="x", aufgaben=f"A{a}", eingetragen_von="TL")
        self.assertEqual([x for x in self.zeilen() if "Pflege" in x or "1.0.1" in x], [])

    def test_zwei_projekte_getrennt(self):
        with db.schreiben(self.con):
            anders = db.einfuegen(self.con, "projekt", name="Q", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, anders, "CC1")
        m = planung.bogen_neu(self.con, anders, kern.ENTWICKLER, "Fremd", ziel="Z", abnahme="V")
        with db.schreiben(self.con):
            db.einfuegen(self.con, "aufgabe", projekt_id=anders, titel="Fremdes", agent="CC1", angelegt_von="TL", angelegt_utc=z(8), status="fertig",
                         begonnen_utc=z(8), fertig_utc=z(9), bogen_id=m)
        self.assertEqual([x for x in self.zeilen() if "Fremd" in x], [])


class Feinplan(Grund):
    def test_fassungen_auch_abgelehnt_mit_grund(self):
        self.ereignis("feinplan_angestossen", z(8), von="TL", bogen=self.m, boegen=[self.m], fassung=1)
        self.ereignis("feinplan_entwurf", z(8, 5), bogen=self.m, boegen=[self.m], fassung=1, fehler=["kein JSON: x"])
        self.ereignis("feinplan_angestossen", z(8, 6), bogen=self.m, boegen=[self.m], fassung=2)
        self.ereignis("feinplan_entwurf", z(8, 9), bogen=self.m, boegen=[self.m], fassung=2, entwurf={"pakete": [{}, {}]}, angelegt={})
        self.assertEqual(self.zeilen("fein"), ["M1: Feinplan Fassung 1: Planer angestoßen", "M1: Feinplan Fassung 1 passte nicht",
                                               "M1: Feinplan Fassung 2: Planer angestoßen", "M1: Feinplan Fassung 2 mit 2 Paketen liegt vor"])
        e = self.v("fein")[1]
        self.assertTrue(e["lang"])                         # der Grund in Menschensprache, auf Klick
        self.assertNotIn("JSON", e["lang"])

    def test_konzeptaenderung(self):
        t = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        self.ereignis("thema_delta_stimme", z(8), von="TL", thema=t, entwurf=1, rolle="lead")
        self.ereignis("thema_delta_angewandt", z(9), von="TL", thema=t, entwurf=1, uebersprungen=["A1"])
        self.ereignis("thema_delta_start", z(10), thema=t, entwurf=1, gestartet=[1], fehler={}, offen={})
        self.ereignis("thema_delta_start", z(11), thema=t, entwurf=1, gestartet=[], fehler={"M1": "x"}, offen={})
        self.assertEqual(self.zeilen("fein"), ["Thema „Anmeldung“: Ja zur Änderung (Lead)", "Thema „Anmeldung“: Änderung angewandt, 1 Paket blieb unverändert",
                                               "Thema „Anmeldung“: Änderung gestartet", "Thema „Anmeldung“: Änderung nicht ganz gestartet"])

    def test_abgebrochenes_ja_und_hinweis_zum_paket(self):
        """Aus A2086: „Plan angenommen“ bei Abbruch, „Hinweis … zu :“."""
        t = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        self.ereignis("thema_plan_ja", z(8), von="TL", thema=t, entwurf=1, angelegt={}, abgebrochen="Fehler")
        self.ereignis("thema_plan_ja", z(9), von="TL", thema=t, entwurf=2, angelegt={})
        self.ereignis("plan_hinweis", z(10), von="TL", text=json.dumps({"thema": t, "plan": f"TH{t}", "bezug": "P6", "text": "Lead liest mit"}))
        self.assertEqual(self.zeilen("fein"), ["Thema „Anmeldung“: Plan nur teilweise angelegt", "Thema „Anmeldung“: Plan angenommen",
                                               "Hinweis an den Planer – Thema „Anmeldung“, zu Paket 6: Lead liest mit"])


class Zusammenfassen(Grund):
    def fertige(self, n, abstand_min=2, titel="Paket"):
        for i in range(n):
            a = self.paket(f"{titel} {i}")
            self.setzen(a, status="fertig", fertig_utc=z(8 + (i * abstand_min) // 60, (i * abstand_min) % 60), beleg="abc1234")

    def test_gleiche_hintereinander_eine_zeile_titel_auf_klick(self):
        self.fertige(5)
        (e,) = [x for x in self.v("umsetzung") if "fertig" in x["zeile"]]
        self.assertEqual(e["zeile"], "M1: 5 Pakete fertig")
        self.assertEqual(e["lang"], " · ".join(f"Paket {i}" for i in range(5)))
        self.assertEqual(e["zeit"], z(8, 8))

    def test_gegenprobe_abstand_wer_und_meilenstein_trennen(self):
        self.fertige(2, abstand_min=11)
        m2 = planung.bogen_neu(self.con, self.pid, "TL", "Zweiter", ziel="Z", abnahme="V")
        a = self.paket("Anderer Meilenstein", m2)
        self.setzen(a, status="fertig", fertig_utc=z(8, 12), beleg="abc1234")
        b = self.paket("Anderer Agent", agent="CC2")
        self.setzen(b, status="fertig", fertig_utc=z(8, 13), beleg="abc1234")
        self.assertEqual([x for x in self.zeilen() if "fertig" in x],
                         ["M1: „Paket 0“ fertig", "M1: „Paket 1“ fertig", "M2: „Anderer Meilenstein“ fertig", "M1: „Anderer Agent“ fertig"])

    def test_gleiche_sekunde_feste_reihenfolge(self):
        """Lead (c): auch über die Quellen hinweg fest – und bei jedem Abruf gleich."""
        a = self.paket("Alles zugleich")
        self.setzen(a, status="fertig", begonnen_utc=z(8), fertig_utc=z(8), beleg="abc1234")
        self.ereignis("verteilt", z(8), aufgabe=a, agent="CC1")
        with db.schreiben(self.con):
            db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=a, zweig="z", sha="a" * 40, bauer="CC1", pruefer="TL", ergebnis="rot",
                         angefragt_utc=z(8), ergebnis_utc=z(8))
        soll = ["M1: „Alles zugleich“ an CC1 zugeteilt", "M1: „Alles zugleich“ gestartet", "M1: „Alles zugleich“ abgegeben",
                "M1: Prüfung rot – „Alles zugleich“", "M1: „Alles zugleich“ fertig"]
        for _ in range(3):
            self.assertEqual([x for x in self.zeilen() if "Alles" in x], soll)

    def test_grenze_je_schritt_nach_dem_zusammenfassen(self):
        """Lead (d): viel Umsetzung verdrängt die anderen Schritte nicht; gezählt wird, was als Zeile erscheint."""
        self.ereignis("feinplan_angestossen", z(1, tag=1), von="TL", bogen=self.m, boegen=[self.m], fassung=1)
        with db.schreiben(self.con):
            for i in range(verlauf_quellen.GRENZE + 30):
                db.einfuegen(self.con, "aufgabe", projekt_id=self.pid, titel=f"T{i}", agent="CC1", angelegt_von="TL", angelegt_utc=z(1), status="fertig",
                             fertig_utc=f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}T08:00:00Z", bogen_id=self.m, beleg="abc1234")
        self.assertEqual(len([x for x in self.v("umsetzung") if "fertig" in x["zeile"] or "Meilenstein" in x["zeile"]]), verlauf_quellen.GRENZE)
        self.assertEqual(self.zeilen("fein"), ["M1: Feinplan Fassung 1: Planer angestoßen"])

    def test_rohzeilen_je_quelle_begrenzt(self):
        with mock.patch.object(verlauf_quellen, "ROH", 3):
            self.fertige(6, abstand_min=20)
            self.assertEqual(len([x for x in self.zeilen() if "fertig" in x]), 3)
            for i in range(6):
                self.ereignis("verteilt", z(20, i * 5), aufgabe=self.paket(f"Zugeteilt {i}"), agent=f"CC{i}")
            self.assertEqual([x for x in self.zeilen() if "zugeteilt" in x],      # die jüngsten, nicht irgendwelche
                             [f"M1: „Zugeteilt {i}“ an CC{i} zugeteilt" for i in (3, 4, 5)])


class AlteEintraegeBleiben(Grund):
    def test_gespeicherte_ereignisse_stehen_weiter_da(self):
        t = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        self.ereignis("thema_freigegeben", z(8), von=kern.ENTWICKLER, thema=t, fassung=1)
        verlauf.ereignis(self.con, self.pid, "agent", "eigens gespeichert", von="CC1", zeit_utc=z(9))
        self.assertEqual(self.zeilen("konzept"), ["Thema „Anmeldung“ freigegeben"])
        self.assertIn("eigens gespeichert", self.zeilen("umsetzung"))


if __name__ == "__main__":
    unittest.main()
