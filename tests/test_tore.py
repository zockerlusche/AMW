"""K7 (A1944, TH154 Fassung 4): die fünf Tore werden abgeleitet – Konzept → Grobplanung (jedes freigegebene Thema in einem
Meilenstein oder „nichts zu bauen“ mit Bestätigung des Co, geplante Meilensteine freigegeben) → Feinplanung („Jetzt starten“) →
Umsetzung (alle Meilensteine fertig; Prognose überschritten → Lead) → Abschluss (Bericht der AMW je Meilenstein, Ja dazu)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
from unittest import mock

from amw import cli, db, kern, planansicht, planung, themen, tore
from tests.test_planansicht import Grund


class Basis(Grund):
    def setUp(self):
        super().setUp()
        themen.pflegen(self.con, self.pid, "CC1", self.th, "Text.")
        kern.projekt_einstellen(self.con, self.pid, "TL", versionen="aus")
        tore.runde(self.con, self.pid)                       # erste Dienst-Runde: Stichtag für Abschlussberichte

    def tor(self, name):
        return next(x for x in tore.stand(self.con, self.pid)["tore"] if x["tor"] == name)

    def befehl(self, *args):
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus), contextlib.redirect_stderr(io.StringIO()):
            rc = cli.main([*args, "--projekt", "P"])
        return rc, aus.getvalue()

    def bis_umsetzung(self):
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.th)
        planung.bogen_status(self.con, self.pid, "TL", self.m2, "verworfen")
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "grob")
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "plan")
        planansicht.jetzt_starten(self.con, self.pid, kern.ENTWICKLER)


class Ableitung(Basis):
    def test_konzept_dann_grobplanung(self):
        s = tore.stand(self.con, self.pid)
        self.assertEqual((s["aktuell"], [x["zu"] for x in s["tore"]]), ("konzept", [False] * 5))
        self.assertEqual(s["zeile"], "Konzept · 0 von 1 Themen freigegeben")
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.th)
        g = self.tor("grobplanung")
        self.assertEqual((g["zu"], g["n"], g["g"], g["mn"], g["mg"]), (False, 1, 1, 0, 2))     # Thema im Meilenstein, 0 von 2 frei
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "grob")
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m2, "grob")
        s = tore.stand(self.con, self.pid)
        self.assertEqual((s["aktuell"], self.tor("grobplanung")["zu"]), ("feinplanung", True))

    def test_thema_ohne_meilenstein_haelt_die_grobplanung(self):
        th2 = themen.neu(self.con, self.pid, "TL", "Online-Seite", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", th2, "Text.")
        for t in (self.th, th2):
            themen.freigeben(self.con, self.pid, kern.ENTWICKLER, t)
        for b in (self.m1, self.m2):
            planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, b, "grob")
        self.assertEqual((self.tor("grobplanung")["zu"], self.tor("grobplanung")["n"]), (False, 1))
        themen.nichts_zu_bauen(self.con, self.pid, "TL", f"TH{th2}", "nur Doku")       # der Lead schreibt den Grund …
        s = tore.stand(self.con, self.pid)
        self.assertFalse(self.tor("grobplanung")["zu"])
        self.assertEqual([x["id"] for x in s["nichts_offen"]], [th2])
        with self.assertRaisesRegex(kern.AmwFehler, "Co-Entwickler oder der Mensch"):
            tore.nichts_bestaetigen(self.con, self.pid, "TL", f"TH{th2}")
        tore.nichts_bestaetigen(self.con, self.pid, "Co", f"TH{th2}")                     # … der Co bestätigt
        self.assertTrue(self.tor("grobplanung")["zu"])
        self.assertEqual(tore.stand(self.con, self.pid)["nichts_offen"], [])

    def test_feinplanung_umsetzung_abschluss(self):
        self.bis_umsetzung()
        s = tore.stand(self.con, self.pid)
        u = self.tor("umsetzung")
        self.assertEqual((s["aktuell"], u["laufend"], u["n"], u["g"]), ("umsetzung", True, 0, 2))
        for a in (self.a1, self.a2):
            with db.schreiben(self.con):
                self.con.execute("UPDATE aufgabe SET status = 'fertig', fertig_utc = ?, beleg = 'abc1234' WHERE id = ?", (db.jetzt(), a))
        planung.bogen_status(self.con, self.pid, "TL", self.m1, "fertig")
        self.assertEqual(tore.stand(self.con, self.pid)["aktuell"], "abschluss")
        with self.assertRaisesRegex(kern.AmwFehler, "Abschlussbericht fehlt"):
            planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "abschluss")
        aus = tore.runde(self.con, self.pid)
        did = tore.bericht(self.con, self.pid, self.m1)
        self.assertTrue(did)
        self.assertIn(f"Abschlussbericht M{self.m1}: D{did}", aus)
        self.assertFalse([x for x in tore.runde(self.con, self.pid) if x.startswith("Abschlussbericht")])   # nur einmal je Meilenstein
        self.assertEqual(len([x for x in self.con.execute("SELECT 1 FROM plan_ereignis WHERE art = 'abschluss_bericht'")]), 1)
        self.assertIn("Abschlussbericht Meilenstein 1", self.post("Entwickler")[-1][1])   # thema_freigabe = mensch: an den Menschen
        ab = self.m(self.m1)["abschluss"]
        self.assertEqual((ab["bericht"], ab["frei"]), (did, False))
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "abschluss")
        s = tore.stand(self.con, self.pid)
        self.assertEqual((s["aktuell"], s["zeile"]), (None, "Abschluss · alle Tore geschlossen"))

    def test_a1972_fuer_dich_nur_was_der_mensch_tun_muss(self):
        """A1972: Themen, die auf dich warten, und Meilensteine, deren Freigabe (grob, Plan, Abschluss) bei dir liegt; bei co+lead
        geben Co und Lead die Meilensteine frei – das ist kein Handlungsbedarf für den Menschen."""
        f = lambda: tore.stand(self.con, self.pid)["fuer_dich"]                     # noqa: E731
        self.assertEqual(f(), {"themen": 1, "meilensteine": 2})                     # Thema vorgelegt; zwei Meilensteine ohne Grob-Ja
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.th)
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "grob")
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m2, "grob")
        self.assertEqual(f(), {"themen": 0, "meilensteine": 1})                     # m1 hat Pakete: der Plan wartet auf dich
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "plan")
        self.assertEqual(f(), {"themen": 0, "meilensteine": 0})
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, thema_freigabe="co+lead")
        planansicht.zurueck(self.con, self.pid, kern.ENTWICKLER, self.m1, "plan", "Tests fehlen")
        self.assertEqual(f()["meilensteine"], 0)

    def test_bericht_gegen_erfolgskriterien_mit_resten_und_lehren(self):
        planung.schritt_setzen(self.con, self.pid, "TL", aid=self.a1, kriterien=["SSO geht", "Abmelden geht"])
        planung.kriterium(self.con, self.pid, "TL", self.a1, 1, True)
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', fertig_utc = ?, beleg = 'abc1234' WHERE id = ?", (db.jetzt(), self.a1))
            self.con.execute("UPDATE aufgabe SET status = 'verworfen', beleg = 'abc1234' WHERE id = ?", (self.a2,))
            db.einfuegen(self.con, "rueckblick", projekt_id=self.pid, bogen_id=self.m1, art="gelernt", text="Erst messen, dann bauen",
                         von="TL", zeit_utc=db.jetzt())
        t = tore.bericht_text(self.con, self.pid, self.m1)
        for teil in ("# Abschlussbericht Meilenstein 1 „Anmelden“", "Endet mit (Erfolgskriterium): Vorführung", "## Erfolgskriterien",
                     "Kriterien erfüllt", "## Reste", f"verworfen: A{self.a2} Tests", "offenes Kriterium", "## Lehren",
                     "gelernt: Erst messen, dann bauen"):
            self.assertIn(teil, t)

    def test_co_und_lead_bestaetigen_den_bericht(self):
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, thema_freigabe="co+lead")
        self.bis_umsetzung()
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', fertig_utc = ?, beleg = 'abc1234' WHERE bogen_id = ?", (db.jetzt(), self.m1))
        planung.bogen_status(self.con, self.pid, "TL", self.m1, "fertig")
        tore.runde(self.con, self.pid)
        self.assertIn("Abschlussbericht", self.post("Co")[-1][1])                              # co+lead: an Co und Lead
        self.assertIn("Abschlussbericht", self.post("TL")[-1][1])
        rc, aus = self.befehl("bogen", "freigeben", str(self.m1), "--art", "abschluss", "--von", "Co")
        self.assertEqual(rc, 0)
        self.assertIn("fehlt noch: Lead", aus)
        self.assertEqual(self.m(self.m1)["abschluss"]["ja_fehlt"], ["Lead"])
        rc, aus = self.befehl("bogen", "freigeben", str(self.m1), "--art", "abschluss", "--von", "TL")
        self.assertIn("freigegeben", aus)
        self.assertTrue(self.tor("abschluss")["zu"])
        rc, aus = self.befehl("bogen", "zurueck", str(self.m1), "--art", "abschluss", "--notiz", "Reste fehlen", "--von", "Co")
        self.assertFalse(self.tor("abschluss")["zu"])                                          # zurück: das Tor ist wieder offen
        self.assertIn("Abschluss", self.post("TL")[-1][1])
        rc, aus = self.befehl("bogen", "bericht", str(self.m1), "--von", "TL")
        self.assertRegex(aus, r"Abschlussbericht D\d+")
        self.assertNotEqual(tore.bericht(self.con, self.pid, self.m1), None)

    def test_tor_wechsel_festgehalten(self):
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.th)
        for b in (self.m1, self.m2):
            planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, b, "grob")
        self.assertEqual(tore.runde(self.con, self.pid), ["Tor Grobplanung geschlossen"])
        self.assertEqual(tore.runde(self.con, self.pid), [])
        planansicht.zurueck(self.con, self.pid, kern.ENTWICKLER, self.m2, "grob", "anders")
        self.assertEqual(tore.runde(self.con, self.pid), ["Tor Grobplanung wieder offen"])
        e = [json.loads(r[0]) for r in self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'tor_stand' ORDER BY id")]
        self.assertEqual([(x["tor"], x["zu"]) for x in e], [("grobplanung", True), ("grobplanung", False)])

    def test_befehl_tore(self):
        rc, aus = self.befehl("bogen", "tore", "--von", "CC1")
        self.assertEqual(rc, 0)
        self.assertTrue(aus.startswith("Konzept · 0 von 1 Themen freigegeben"))
        self.assertIn("● Konzept", aus)
        self.assertIn("○ Abschluss", aus)


class Altbestand(Grund):
    def test_vor_dem_stichtag_fertig_kein_bericht_und_kein_ja(self):
        """Vorab-Prüfung 1.164.0 (2): Meilensteine, die schon vor K7 fertig waren, bekommen keinen Bericht und halten das Tor nicht."""
        themen.pflegen(self.con, self.pid, "CC1", self.th, "Text.")
        kern.projekt_einstellen(self.con, self.pid, "TL", versionen="aus")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', fertig_utc = '2026-01-01T00:00:00Z', beleg = 'abc1234' WHERE bogen_id = ?",
                             (self.m1,))
            self.con.execute("UPDATE bogen SET status = 'fertig', fertig_utc = '2026-01-01T00:00:00Z' WHERE id = ?", (self.m1,))
        self.assertEqual([x for x in tore.runde(self.con, self.pid) if x.startswith("Abschlussbericht")], [])
        self.assertIsNone(tore.bericht(self.con, self.pid, self.m1))
        self.assertEqual(next(x for x in tore.stand(self.con, self.pid)["tore"] if x["tor"] == "abschluss")["g"], 0)
        self.assertIsNone(self.m(self.m1)["abschluss"])
        self.assertEqual(self.post("Entwickler"), [])


class Umsetzung(Basis):
    def test_prognose_ueberschritten_weckt_den_lead_einmal(self):
        self.bis_umsetzung()
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET begonnen_utc = ? WHERE id = ?", (db.jetzt(), self.a1))
        zellen = {("heikel", "M"): {"median": 2.0, "n": 5, "rot": 0}}
        with mock.patch("amw.empfehlung.zellen", return_value=zellen), \
                mock.patch("amw.aufwand.je_aufgabe", return_value={"usd": 2.5}):
            self.assertEqual(tore.prognose_pruefen(self.con, self.pid), [])                     # 2,5 ≤ 1,5 × 2
        with mock.patch("amw.empfehlung.zellen", return_value=zellen), \
                mock.patch("amw.aufwand.je_aufgabe", return_value={"usd": 3.4}):
            self.assertEqual(tore.prognose_pruefen(self.con, self.pid), [f"A{self.a1} über Prognose"])
            self.assertEqual(tore.prognose_pruefen(self.con, self.pid), [])                     # nur einmal je Paket
        art, kurz = self.post("TL")[-1]
        self.assertEqual((art, kurz), ("meldung", f"A{self.a1} über Prognose: 3.40 $ statt ≈ 2.00 $"))


if __name__ == "__main__":
    import unittest
    unittest.main()
