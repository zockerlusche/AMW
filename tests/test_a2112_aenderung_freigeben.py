"""A2112 (Marcel 25.11.): das Ja zu einer Konzeptänderung heißt im Projektweg und in Planung › Meilensteine gleich; ist der Plan eines
laufenden Ziel-Meilensteins seit der Freigabe geändert, sagt die Karte, dass der Lead startet; online steht, dass man am PC freigibt."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import unittest
from unittest import mock

from amw import delta_start, feinplanung, grobplan, kern, planansicht, planer, planer_delta, planung, projektweg_seite, themen
from tests import test_projektweg_seite as pws
from tests.rundgang import OnlineRundgang, Rundgang

PLANUNG = "document.querySelector('.pm-entwurf button[data-h=plan-ja]')"
WEG = "[...document.querySelectorAll('.pjw-ansicht button')].find(b => b.textContent.startsWith('Änderung TH'))"


def aenderung_an_laufendem(con, pid, geaendert=True):
    """M1 läuft, die Änderung zielt auf M1. geaendert: nach der Freigabe kam ein Paket dazu, der Plan gilt nicht mehr als frei."""
    t = pws.demo(con, pid, "fein")
    m1 = con.execute("SELECT * FROM bogen WHERE titel = 'Welt sichtbar'").fetchone()
    feinplanung.plan_starten(con, pid, kern.ENTWICKLER, m1["id"])
    for (aid,) in con.execute("SELECT id FROM aufgabe WHERE titel IN ('Speichern und Laden', 'Tests für Speichern')").fetchall():
        themen.verweise_setzen(con, pid, "TL", aid, [f"TH{t[2]}"])
    themen.bearbeiten(con, pid, kern.ENTWICKLER, t[2], "Die Welt bleibt erhalten, auch nach einem Neustart, mit drei Speicherplätzen.")
    plan = {"meilensteine": [{"schluessel": "M1", "bestehend": m1["nr"], "titel": m1["titel"]}],
            "pakete": [{"schluessel": "P1", "meilenstein": "M1", "titel": "Speicherplatz wählen", "auftrag": "Drei Plätze anbieten.", "groesse": "S",
                        "art": "mechanisch", "ausfuehrung": "p", "fertig_quelle": "commit", "abnahme_befehl": "python -m unittest tests.test_platz",
                        "bereiche": "scripts/speicher.gd"}]}
    planer.entwurf_eintragen(con, pid, t[2], 2, plan, modell="sonnet", usd=0.05, delta=planer_delta.kontext(con, pid, t[2]))
    e = planer.letzter_entwurf(con, pid, t[2])
    assert e and not e.get("fehler"), e
    if geaendert:
        planung.schritt_setzen(con, pid, "TL", titel="Nebenbei dazu", bogen_id=m1["id"], groesse="S", art="mechanisch", agent="CC1")
    return t[2], m1["id"]


def starter(test):
    for ziel in (grobplan, planer):
        p = mock.patch.object(ziel, "STARTER", lambda *a, **k: 4711)
        p.start()
        test.addCleanup(p.stop)


def weg_oeffnen(test):
    test.oeffnen("projektweg", "document.querySelector('.pjw-schritt')")
    test.tab.js("zustand.pwSicht = 2; zustand.pwOffen = true; void zeige('projektweg', true)")
    test.warten(WEG)


def planung_oeffnen(test):
    test.oeffnen("planung", "document.querySelector('#inhalt')")
    test.tab.js("zustand.planReiter = 'meilensteine'; void zeige('planung', true)")
    test.warten(PLANUNG)
    test.tab.js("document.querySelector('.pm-entwurf').open = true")


class Daten(pws.Grund):
    def ja(self):
        fein = projektweg_seite.daten(self.con, self.pid)["fein"]["delta"]
        namen = {r["id"]: r["name"] for r in self.con.execute("SELECT id, name FROM thema WHERE projekt_id = ?", (self.pid,))}
        pa = planansicht.entwuerfe(self.con, self.pid, namen)["entwuerfe"]
        self.assertEqual([x["ja"] for x in fein], [x["ja"] for x in pa])                # beide Seiten: dieselben Angaben
        return pa[0]["ja"]

    def test_neuer_meilenstein_startet(self):
        pws.wartende_aenderung(self.con, self.pid)
        j = self.ja()
        self.assertEqual((j["pakete"], j["neuer_ms"], j["startet"], j["lead_startet"]), (1, True, True, False))

    def test_laufendes_ziel_mit_freiem_plan_startet(self):
        aenderung_an_laufendem(self.con, self.pid, geaendert=False)
        j = self.ja()
        self.assertEqual((j["neuer_ms"], j["startet"], j["lead_startet"]), (False, True, False))

    def test_laufendes_ziel_mit_geaendertem_plan_startet_der_lead(self):
        t, _ = aenderung_an_laufendem(self.con, self.pid)
        j = self.ja()
        self.assertEqual((j["neuer_ms"], j["startet"], j["lead_startet"], [z["neu"] for z in j["ziele"]]), (False, False, True, [False]))
        with mock.patch.object(kern, "lead", return_value=None):                        # ohne Lead verspricht die Karte nichts
            e = planer.letzter_entwurf(self.con, self.pid, t) or {}
            self.assertFalse(planansicht.aenderung_ja(self.con, self.pid, e["entwurf"])["lead_startet"])

    def test_was_die_karte_sagt_stimmt(self):
        """Bei geändertem Plan erneuert das Ja nichts und startet nichts (delta_start)."""
        t, m1 = aenderung_an_laufendem(self.con, self.pid)
        planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, t)
        self.assertFalse(planansicht._zustaende(self.con, self.pid)[(m1, "plan")]["an"])
        text = self.con.execute("SELECT text FROM plan_ereignis WHERE art = ? ORDER BY id DESC", (delta_start.START,)).fetchone()[0]
        self.assertIn('"erneuert": []', text)


class SeiteKnopf(Rundgang):
    """Dieselbe Änderung, zwei Seiten, derselbe Knopf – geklickt auf beiden."""
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        starter(self)
        self.t = pws.wartende_aenderung(self.con, self.pid)

    def status(self):
        r = self.con.execute("SELECT status FROM bogen WHERE titel = 'Drei Speicherplätze'").fetchone()
        return r and r[0]

    def test_gleicher_text_und_klick_in_planung(self):
        weg_oeffnen(self)
        text = self.tab.js(WEG + ".textContent")
        planung_oeffnen(self)
        self.assertEqual(self.tab.js(PLANUNG + ".textContent"), text)
        self.assertIn("freigeben und starten (1 Paket, neuer Meilenstein)", text)
        self.assertEqual(self.tab.js("document.querySelector('.pm-entwuerfe-kopf').textContent"), "Entwürfe des Planers (1)")
        self.tab.js(PLANUNG + ".click(); 1")
        self.warten("!document.querySelector('#inhalt .pm-entwurf')")
        self.assertEqual(self.status(), "aktiv")

    def test_klick_im_projektweg(self):
        weg_oeffnen(self)
        self.tab.js(WEG + ".click(); 1")
        self.warten("!document.querySelector('.pjw-delta')")
        self.assertEqual(self.status(), "aktiv")


class SeiteLeadStartet(Rundgang):
    """Änderung an einem laufenden Meilenstein, dessen Plan seit der Freigabe geändert ist."""
    SATZ = "Nach dem Ja startet der Lead."

    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        starter(self)
        self.t, self.m1 = aenderung_an_laufendem(self.con, self.pid)

    def test_beide_seiten_sagen_es_und_der_klick_legt_an(self):
        weg_oeffnen(self)
        text = self.tab.js(WEG + ".textContent")
        self.assertIn("freigeben (1 Paket in M", text)
        self.assertNotIn("starten", text)
        self.assertEqual(self.tab.js("document.querySelector('.pjw-delta .pjw-danach').textContent"), self.SATZ)
        planung_oeffnen(self)
        self.assertEqual(self.tab.js(PLANUNG + ".textContent"), text)
        self.assertEqual(self.tab.js("document.querySelector('.pm-entwurf .pjw-danach').textContent"), self.SATZ)
        self.tab.js(PLANUNG + ".click(); 1")
        self.warten("!document.querySelector('#inhalt .pm-entwurf')")
        self.assertTrue(self.con.execute("SELECT 1 FROM aufgabe WHERE titel = 'Speicherplatz wählen' AND bogen_id = ?", (self.m1,)).fetchone())

    def test_rundgang(self):
        auf = "(() => { const d = document.querySelector('.pm-entwurf'); if (d) d.open = true; return d && d.querySelector('.pjw-danach'); })()"
        for g in ("pc", "handy"):                         # am iPad laufen die Paketkarten im Projektweg schon ohne A2112 über
            for th in ("hell", "dunkel"):
                self.assertEqual(self.besuchen("projektweg", "a2112-projektweg", bereit="document.querySelector('.pjw-schritt')", g=g, t=th,
                                               tun="zustand.pwSicht = 2; zustand.pwOffen = true; void zeige('projektweg', true)",
                                               danach="document.querySelector('.pjw-delta .pjw-danach')"), [], f"{g} {th}")
                self.tab.js("document.querySelector('.pjw-delta .pjw-danach').scrollIntoView({block: 'end'})")
                self.pruefen("a2112-projektweg-unten", g, th)
                self.assertEqual(self.besuchen("planung", "a2112-planung", bereit="document.querySelector('#inhalt')", g=g, t=th,
                                               tun="zustand.planReiter = 'meilensteine'; void zeige('planung', true)", danach=auf), [], f"{g} {th}")
                self.stabil("document.querySelector('.pm-entwurf')")                                      # die Seite zeichnet nach dem Wechsel noch einmal
                self.tab.js("document.querySelector('.pm-entwurf').open = true; document.querySelector('.pm-entwurf').scrollIntoView({block: 'center'})")
                self.warten(PLANUNG + ".offsetHeight > 0")
                self.pruefen("a2112-planung-entwurf", g, th)


class SeiteOnline(OnlineRundgang):
    """Online gibt man nichts frei: beide Seiten sagen „freigeben am PC“, ein Knopf fehlt."""
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        starter(self)
        self.t, self.m1 = aenderung_an_laufendem(self.con, self.pid)

    def test_hinweis_auf_beiden_seiten(self):
        self.oeffnen("start")
        self.tab.js("zustand.pwSicht = 2; zustand.pwOffen = true; void zeige('projektweg', true)")
        self.warten("document.querySelector('.pjw-delta .pjw-nur-pc')")
        self.assertEqual(self.tab.js("document.querySelector('.pjw-delta .pjw-nur-pc').textContent"), "freigeben am PC")
        self.assertFalse(self.tab.js(f"!!{WEG}"))
        self.tab.js("zustand.planReiter = 'meilensteine'; void zeige('planung', true)")
        self.warten("document.querySelector('.pm-entwurf')")
        self.assertIn("freigeben am PC", self.tab.js("document.querySelector('.pm-entwurf').textContent"))
        self.assertFalse(self.tab.js(f"!!{PLANUNG}"))


if __name__ == "__main__":
    unittest.main()
