"""Nachbesserungen aus P461 (K6/A1950) und P462 (K4/A1940): das Ja gilt zum gesehenen Stand (Fingerabdruck), Freigabe
wird offen, wenn sich der Plan danach ändert; Verschieben fertiger Meilensteine sauber abgewiesen; „Jetzt starten“ nur Lead/
Mensch; Planer auch bei Freigabe durch Co + Lead; Abnahme-Befehl wie beim Arbeiter geprüft und sichtbar; plan-ja/planen als
Entwickler nur im eigenen Terminal; Ja nur zur aktuellen Fassung eines freigegebenen Themas, nur einmal, bestehender
Meilenstein muss noch offen sein; der Knopf schickt die Entwurfsnummer."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import copy
import io
import os
from unittest import mock

from amw import cli, db, kern, planansicht, planer, planung, themen
from tests import test_planansicht, test_planer
from tests.test_planer import ERGEBNIS


class K6(test_planansicht.Grund):
    def setUp(self):
        super().setUp()
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, thema_freigabe="co+lead")

    def test_ja_gilt_nur_zum_gesehenen_stand(self):
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "grob")
        r = planansicht.freigeben(self.con, self.pid, "Co", self.m1, "plan")
        self.assertEqual(r, {"frei": False, "ja_fehlt": ["Lead"]})
        planung.schritt_setzen(self.con, self.pid, "TL", aid=self.a1, auftrag="SSO und Passkey.")        # Plan ändert sich
        r = planansicht.freigeben(self.con, self.pid, "TL", self.m1, "plan")
        self.assertEqual(r, {"frei": False, "ja_fehlt": ["Co-Entwickler"]})                      # das Ja des Co war zu einem alten Stand
        self.assertEqual(planansicht.freigeben(self.con, self.pid, "Co", self.m1, "plan"), {"frei": True})
        self.assertTrue(self.m(self.m1)["plan"]["frei"])

    def test_aenderung_nach_der_freigabe_oeffnet_sie(self):
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "grob")
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "plan")
        self.assertTrue(self.m(self.m1)["plan"]["frei"])
        planung.schritt_setzen(self.con, self.pid, "TL", titel="Noch ein Paket", bogen_id=self.m1)
        p = self.m(self.m1)["plan"]
        self.assertEqual((p["frei"], p["geaendert"]), (False, True))
        self.assertFalse(self.d()["starten"])
        planung.bogen_aendern(self.con, self.pid, "TL", self.m1, "Anmelden neu")                   # auch der Meilenstein selbst
        g = self.m(self.m1)["grob"]
        self.assertEqual((g["frei"], g["geaendert"]), (False, True))

    def test_status_aendert_den_plan_nicht(self):
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "grob")
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "plan")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'laeuft', agent = 'CC1', begonnen_utc = ? WHERE id = ?", (db.jetzt(), self.a1))
        self.assertTrue(self.m(self.m1)["plan"]["frei"])

    def test_verschieben_fertig_und_starten_nur_lead_oder_mensch(self):
        planung.bogen_status(self.con, self.pid, "TL", self.m2, "verworfen")
        with self.assertRaisesRegex(kern.AmwFehler, "nur geplante und laufende"):
            planansicht.verschieben(self.con, self.pid, "TL", self.m2, "frueher")
        with self.assertRaisesRegex(kern.AmwFehler, "Lead oder der Mensch"):
            planansicht.jetzt_starten(self.con, self.pid, "Co")

    def test_co_und_lead_per_befehl(self):
        def befehl(*args):
            aus = io.StringIO()
            with contextlib.redirect_stdout(aus), contextlib.redirect_stderr(io.StringIO()):
                rc = cli.main(["bogen", *args, "--projekt", "P"])
            return rc, aus.getvalue()
        self.assertIn("fehlt noch: Lead", befehl("freigeben", str(self.m1), "--art", "grob", "--von", "Co")[1])
        self.assertIn("freigegeben", befehl("freigeben", str(self.m1), "--art", "grob", "--von", "TL")[1])
        self.assertNotEqual(befehl("freigeben", str(self.m1), "--art", "plan", "--von", "CC1")[0], 0)   # nur Co, Lead, Mensch


class K4(test_planer.Grund):
    def test_planer_auch_bei_freigabe_durch_co_und_lead(self):
        kern.agent_neu(self.con, self.pid, "Co")
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, co_entwickler="Co", thema_freigabe="co+lead")
        gestartet = []
        with mock.patch.object(planer, "STARTER", lambda pid, tid, fassung: gestartet.append((tid, fassung)) or 1), \
                mock.patch.dict(os.environ, {"AMW_PLANER_AUS": ""}):
            themen.ja_geben(self.con, self.pid, "Co", f"TH{self.tid}")
            self.assertEqual(gestartet, [])
            themen.ja_geben(self.con, self.pid, "TL", f"TH{self.tid}")
        self.assertEqual(gestartet, [(self.tid, 1)])

    def test_abnahme_befehl_wie_beim_arbeiter_und_sichtbar(self):
        for boese in ("python -m unittest && del x", "pytest | tee log", "pytest > aus.txt", "a; b"):
            d = copy.deepcopy(ERGEBNIS)
            d["pakete"][1]["abnahme_befehl"] = boese
            with self.assertRaisesRegex(planer.PlanFehler, "ohne Verkettung oder Umleitung"):
                planer.pruefen(d, self.con, self.pid)
        z = planer.zusammenfassung(planer.pruefen(ERGEBNIS, self.con, self.pid))
        self.assertIn("    Auftrag: SSO-Anmeldung bauen.", z)
        self.assertIn("    Abnahme-Befehl: python -m unittest tests.test_anmeldung", z)

    def test_entwickler_nur_im_eigenen_terminal(self):
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, f"TH{self.tid}")
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, ERGEBNIS)
        for aktion in ("plan-ja", "planen"):
            with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}), contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()) as fehler:
                rc = cli.main(["thema", aktion, f"TH{self.tid}", "--projekt", "Produkt", "--von", "Entwickler"])
            self.assertNotEqual(rc, 0, aktion)
            self.assertIn("nicht aus einer Agenten-Sitzung", fehler.getvalue() + str(rc))

    def test_ja_nur_zur_aktuellen_fassung_und_einmal(self):
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, ERGEBNIS)
        with self.assertRaisesRegex(kern.AmwFehler, "nicht freigegeben"):
            planer.uebernehmen(self.con, self.pid, "TL", self.tid)
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, f"TH{self.tid}")
        themen.pflegen(self.con, self.pid, "CC1", self.tid, "Neue Fassung.")
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, f"TH{self.tid}")
        with self.assertRaisesRegex(kern.AmwFehler, "Fassung 1, TH.* hat jetzt Fassung 2"):
            planer.uebernehmen(self.con, self.pid, "TL", self.tid)
        e = planer.entwurf_eintragen(self.con, self.pid, self.tid, 2, ERGEBNIS)
        planer.uebernehmen(self.con, self.pid, "TL", self.tid, eid=e)
        with self.assertRaisesRegex(kern.AmwFehler, "schon angenommen"):
            planer.uebernehmen(self.con, self.pid, "TL", self.tid, eid=e)

    def test_bestehender_meilenstein_weg_meldung_statt_absturz(self):
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, f"TH{self.tid}")
        b = planung.bogen_neu(self.con, self.pid, "TL", "Alt")
        d = copy.deepcopy(ERGEBNIS)
        d["meilensteine"] = [{"schluessel": "M1", "bestehend": planung.bogen_zeile(self.con, self.pid, b)["nr"]}]
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, d)
        planung.bogen_status(self.con, self.pid, "TL", b, "verworfen")
        with self.assertRaisesRegex(kern.AmwFehler, "gibt es nicht mehr offen"):
            planer.uebernehmen(self.con, self.pid, "TL", self.tid)

    def test_knopf_ja_gilt_dem_gezeigten_entwurf(self):
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, f"TH{self.tid}")
        alt = planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, ERGEBNIS)
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, ERGEBNIS)
        with self.assertRaisesRegex(kern.AmwFehler, "neueren Entwurf"):
            planansicht.entwurf_ja(self.con, self.pid, kern.ENTWICKLER, self.tid, alt)
