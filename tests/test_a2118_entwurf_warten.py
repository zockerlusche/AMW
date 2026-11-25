"""A2118: ein offener Entwurf lässt sich zurückstellen („wartet: <Grund>“, kein Knopf, zählt nicht; der Mensch darf ihn mit Rückfrage doch
freigeben); ein späterer Vermerk „nichts zu bauen“ schließt ältere Entwürfe überall; ein zu langer Grund ist kein Scheitern."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import unittest
from unittest import mock

from amw import cli, db, entwurf_warten, kern, planansicht, planer, planer_delta, projektweg_seite, themen, verlauf_quellen
from tests import test_a2112_aenderung_freigeben as a2112
from tests import test_projektweg_seite as pws
from tests.rundgang import OnlineRundgang, Rundgang

GRUND = "erst nach TH156"


class Grund(pws.Grund):
    def setUp(self):
        super().setUp()
        self.t, self.m1 = a2112.aenderung_an_laufendem(self.con, self.pid)
        kern.projekt_einstellen(self.con, self.pid, "TL", co_entwickler="CC1")
        kern.agent_neu(self.con, self.pid, "CC2")

    def entwuerfe(self):
        namen = {r["id"]: r["name"] for r in self.con.execute("SELECT id, name FROM thema WHERE projekt_id = ?", (self.pid,))}
        return planansicht.entwuerfe(self.con, self.pid, namen)["entwuerfe"]

    def fein(self):
        d = self.daten()
        return d, next(x for x in d["schritte"] if x["schritt"] == "fein")

    def warten(self, von="TL", grund=GRUND):
        return entwurf_warten.zurueckstellen(self.con, self.pid, von, f"TH{self.t}", grund)


class Zurueckstellen(Grund):
    def test_steht_da_zaehlt_aber_nicht(self):
        d, schritt = self.fein()
        self.assertEqual((d["fein"]["delta"][0]["wartet"], schritt["zustand"], schritt["bei_dir"], d["dran"]), (None, "dran", True, "fein"))
        self.warten()
        d, schritt = self.fein()
        self.assertEqual((d["fein"]["delta"][0]["wartet"]["grund"], d["fein"]["delta"][0]["wartet"]["von"]), (GRUND, "TL"))
        self.assertEqual((schritt["bei_dir"], schritt["zustand"]), (False, "erledigt"))
        self.assertNotEqual(d["dran"], "fein")
        self.assertEqual(self.entwuerfe()[0]["wartet"]["grund"], GRUND)
        entwurf_warten.freischalten(self.con, self.pid, "CC1", f"TH{self.t}")                    # der Co schaltet frei
        self.assertEqual((self.entwuerfe()[0]["wartet"], self.fein()[1]["bei_dir"]), (None, True))

    def test_lead_und_co_erst_nach_dem_freischalten_der_mensch_immer(self):
        self.warten()
        with self.assertRaisesRegex(kern.AmwFehler, f"wartet \\({GRUND}\\) – erst freischalten: amw thema entwurf-weiter TH{self.t}"):
            planer.uebernehmen(self.con, self.pid, "TL", self.t)
        self.assertTrue(planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.t))
        self.assertEqual(self.entwuerfe(), [])

    def test_wer_darf_und_grenzen(self):
        for f, muster in ((lambda: self.warten("CC2"), "stellen Lead, Co-Entwickler oder der Mensch zurück"), (lambda: self.warten(grund=" "), "nur mit Grund"),
                          (lambda: self.warten(grund="x" * 201), "höchstens 200 Zeichen"),
                          (lambda: entwurf_warten.freischalten(self.con, self.pid, "TL", f"TH{self.t}"), "wartet nicht")):
            with self.assertRaisesRegex(kern.AmwFehler, muster):
                f()
        self.warten(kern.ENTWICKLER)
        with self.assertRaisesRegex(kern.AmwFehler, "das hebt nur"):
            entwurf_warten.freischalten(self.con, self.pid, "TL", f"TH{self.t}")
        entwurf_warten.freischalten(self.con, self.pid, kern.ENTWICKLER, f"TH{self.t}")
        planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.t)
        with self.assertRaisesRegex(kern.AmwFehler, "keinen offenen Entwurf"):
            self.warten()

    def test_lead_stellt_nicht_ueber_den_menschen_zurueck(self):
        self.warten("TL", "Reihenfolge")
        self.warten(kern.ENTWICKLER, "erst fragen")                                             # der Mensch darf den Grund des Leads ersetzen
        for wer in ("TL", "CC1"):
            with self.assertRaisesRegex(kern.AmwFehler, "das hebt nur"):
                self.warten(wer, "doch anders")
            with self.assertRaisesRegex(kern.AmwFehler, "das hebt nur"):
                entwurf_warten.freischalten(self.con, self.pid, wer, f"TH{self.t}")
        self.assertEqual(self.entwuerfe()[0]["wartet"]["grund"], "erst fragen")
        self.warten(kern.ENTWICKLER, "noch länger")
        entwurf_warten.freischalten(self.con, self.pid, kern.ENTWICKLER, f"TH{self.t}")
        self.warten("CC1", "Co")
        entwurf_warten.freischalten(self.con, self.pid, "TL", f"TH{self.t}")                    # Lead und Co untereinander dürfen es
        self.assertIsNone(self.entwuerfe()[0]["wartet"])

    def test_ein_neuer_entwurf_wartet_nicht(self):
        self.warten()
        e = planer.letzter_entwurf(self.con, self.pid, self.t) or {}
        d = {k: v for k, v in e["entwurf"].items() if k in ("meilensteine", "pakete", "nichts_zu_bauen")}
        planer.entwurf_eintragen(self.con, self.pid, self.t, 2, d, delta=planer_delta.kontext(self.con, self.pid, self.t))
        self.assertEqual([x["wartet"] for x in self.entwuerfe()], [None])

    def test_verlauf_und_befehl(self):
        with mock.patch.dict(os.environ, {"AMW_AGENT": "", "AMW_PROJEKT": ""}):
            def rufen(*a):
                with contextlib.redirect_stdout(io.StringIO()) as o, contextlib.redirect_stderr(io.StringIO()) as f:
                    cli.main(["--projekt", "P", "--von", "TL", "thema", *a])
                return o.getvalue() + f.getvalue()
            self.assertIn("nur mit Grund", rufen("entwurf-warten", f"TH{self.t}"))
            self.assertIn("Entwurf wartet", rufen("entwurf-warten", f"TH{self.t}", "--grund", GRUND))
            self.assertIn("wieder frei zum Ja", rufen("entwurf-weiter", f"TH{self.t}"))
        texte = [e["text"] for e in verlauf_quellen.gesamt(self.con, self.pid, [], lambda e: "fein") if e["art"] == entwurf_warten.ART]
        self.assertEqual(texte, [f"TH{self.t}: Entwurf wartet – {GRUND}", f"TH{self.t}: Entwurf wieder frei zum Ja"])


class Ueberholt(Grund):
    def vermerk(self, aufheben=False):
        themen.nichts_zu_bauen(self.con, self.pid, "TL", f"TH{self.t}", "schon gebaut", aufheben=aufheben)

    def test_vermerk_schliesst_den_aelteren_entwurf(self):
        self.vermerk()
        self.assertEqual((self.entwuerfe(), self.daten()["fein"]["delta"]), ([], []))
        self.vermerk(aufheben=True)                                                             # aufgehoben: er steht wieder da
        self.assertEqual(len(self.entwuerfe()), 1)

    def test_gescheiterter_entwurf_wie_th167(self):
        planer.entwurf_eintragen(self.con, self.pid, self.t, 2, None, fehler=["nichts zu bauen: grund länger als 1000 Zeichen"],
                                 delta=planer_delta.kontext(self.con, self.pid, self.t))
        self.assertEqual(len(self.daten()["fein"]["delta_fehler"]), 1)
        self.vermerk()
        d = self.daten()["fein"]
        self.assertEqual((self.entwuerfe(), d["delta"], d["delta_fehler"]), ([], [], []))

    def test_neuer_entwurf_nach_dem_vermerk_steht_da(self):
        e = planer.letzter_entwurf(self.con, self.pid, self.t) or {}
        d = {k: v for k, v in e["entwurf"].items() if k in ("meilensteine", "pakete", "nichts_zu_bauen")}
        self.vermerk()
        planer.entwurf_eintragen(self.con, self.pid, self.t, 2, d, delta=planer_delta.kontext(self.con, self.pid, self.t))
        self.assertEqual(len(self.entwuerfe()), 1)

    def test_zu_langer_grund_wird_gekuerzt(self):
        r = planer.pruefen({"nichts_zu_bauen": True, "grund": "a" * 1200})
        self.assertEqual((len(r["grund"]), r["grund"][-1]), (1000, "…"))
        self.assertEqual(planer.pruefen({"nichts_zu_bauen": True, "grund": "b" * 1000})["grund"], "b" * 1000)
        with self.assertRaises(planer.PlanFehler):
            planer.pruefen({"nichts_zu_bauen": True, "grund": ""})


class Seite(Rundgang):
    TROTZDEM = "button[data-h=trotzdem]"

    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        a2112.starter(self)
        self.t, self.m1 = a2112.aenderung_an_laufendem(self.con, self.pid)
        entwurf_warten.zurueckstellen(self.con, self.pid, "TL", f"TH{self.t}", GRUND)

    def weg(self):
        self.oeffnen("projektweg", "document.querySelector('.pjw-schritt')")
        self.tab.js("zustand.pwSicht = 2; zustand.pwOffen = true; void zeige('projektweg', true)")
        self.warten("document.querySelector('.pjw-delta .pjw-wartet')")

    def planung(self):
        self.oeffnen("planung", "document.querySelector('#inhalt')")
        self.tab.js("zustand.planReiter = 'meilensteine'; void zeige('planung', true)")
        self.warten("document.querySelector('.pm-entwurf .pjw-wartet')")
        self.stabil("document.querySelector('.pm-entwurf .pjw-wartet')")

    def test_grund_statt_knopf_auf_beiden_seiten(self):
        self.groesse("pc")
        self.weg()
        self.assertEqual(self.tab.js("document.querySelector('.pjw-delta .pjw-wartet summary').textContent"), f"wartet: {GRUND}")
        self.assertFalse(self.tab.js(f"!!{a2112.WEG}"))
        self.assertNotIn("wartet auf dich", self.tab.js("document.querySelector('.pjw-delta').innerText + document.querySelector('.pjw-schritt[data-schritt=fein]').innerText"))
        self.planung()
        self.assertEqual(self.tab.js("document.querySelector('.pm-entwurf .pjw-wartet summary').textContent"), f"wartet: {GRUND}")
        self.assertFalse(self.tab.js(f"!!{a2112.PLANUNG}"))
        self.assertTrue(self.tab.js("document.querySelector('.pm-entwuerfe').classList.contains('ruhig')"))      # keine Farbe, solange keiner dran ist

    def test_trotzdem_freigeben_fragt_nach(self):
        self.groesse("pc")
        self.weg()
        self.tab.js(f"document.querySelector('.pjw-delta .pjw-wartet').open = true; document.querySelector('.pjw-delta {self.TROTZDEM}').click()")
        self.assertIn(GRUND, self.rueckfrage(False))                              # A2146: die Rückfrage der Seite
        self.assertFalse(planer.erledigt(self.con, self.pid, (planer.letzter_entwurf(self.con, self.pid, self.t) or {})["id"]))   # Nein: nichts geschieht
        self.tab.js(f"document.querySelector('.pjw-delta {self.TROTZDEM}').click()")
        self.rueckfrage(True)
        self.warten("!document.querySelector('.pjw-delta')")
        self.assertTrue(planer.erledigt(self.con, self.pid, (planer.letzter_entwurf(self.con, self.pid, self.t) or {})["id"]))

    def test_trotzdem_freigeben_in_der_planung(self):
        self.groesse("pc")
        self.planung()
        self.tab.js(f"document.querySelector('.pm-entwurf').open = true; document.querySelector('.pm-entwurf {self.TROTZDEM}').click()")
        self.rueckfrage(True)
        self.warten("!document.querySelector('#inhalt .pm-entwurf')")

    def test_rundgang(self):
        auf = "(() => { const d = document.querySelector('.pm-entwurf'); if (d) d.open = true; return d && d.querySelector('.pjw-wartet'); })()"
        for g in ("pc", "handy", "ipad"):
            for th in ("hell", "dunkel"):
                self.assertEqual(self.besuchen("projektweg", "a2118-projektweg", bereit="document.querySelector('.pjw-schritt')", g=g, t=th,
                                               tun="zustand.pwSicht = 2; zustand.pwOffen = true; void zeige('projektweg', true)",
                                               danach="document.querySelector('.pjw-delta .pjw-wartet')"), [], f"{g} {th}")
                self.assertEqual(self.besuchen("planung", "a2118-planung", bereit="document.querySelector('#inhalt')", g=g, t=th,
                                               tun="zustand.planReiter = 'meilensteine'; void zeige('planung', true)", danach=auf), [], f"{g} {th}")
                self.stabil("document.querySelector('.pm-entwurf .pjw-wartet')")
                self.tab.js("document.querySelector('.pm-entwurf').open = true; document.querySelector('.pm-entwurf .pjw-wartet').open = true; "
                            "document.querySelector('.pm-entwurf').scrollIntoView({block: 'center'})")
                self.warten("document.querySelector('.pm-entwurf " + self.TROTZDEM + "').offsetHeight > 0")
                self.assertEqual(self.pruefen("a2118-planung-auf", g, th), [], f"{g} {th}")


class SeiteOnline(OnlineRundgang):
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        a2112.starter(self)
        self.t, self.m1 = a2112.aenderung_an_laufendem(self.con, self.pid)
        entwurf_warten.zurueckstellen(self.con, self.pid, "TL", f"TH{self.t}", GRUND)

    def test_online_nur_der_grund(self):
        self.oeffnen("start")
        self.tab.js("zustand.pwSicht = 2; zustand.pwOffen = true; void zeige('projektweg', true)")
        self.warten("document.querySelector('.pjw-delta .pjw-wartet')")
        self.tab.js("document.querySelector('.pjw-delta .pjw-wartet').open = true")
        self.assertIn(f"wartet: {GRUND}", self.tab.js("document.querySelector('.pjw-delta .pjw-wartet').textContent"))
        self.assertIn("freigeben am PC", self.tab.js("document.querySelector('.pjw-delta .pjw-wartet').textContent"))
        self.assertFalse(self.tab.js(f"!!document.querySelector('.pjw-delta {Seite.TROTZDEM}')"))


if __name__ == "__main__":
    unittest.main()
