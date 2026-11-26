"""A2018 (TH156): das Menü hat fünf Punkte plus „Fragen“ (bis „Für dich“) – PC, Handy und Online-Seite. Jede alte Adresse geht weiter
und gehört zu ihrem neuen Punkt, auch aus Push-Meldungen. Der frühere Abschnitt „Leitstand“ heißt „Steuerung“. Die Zahl am Projektweg
zählt jedes Ding einmal und nur, was der Mensch tun muss."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import re
import unittest
from unittest import mock

from amw import db, kern, planung, push, themen, workbench
from tests.rundgang import PHP, OnlineRundgang, Rundgang
from tests.test_rundgang_2 import Daten
from tests.test_wege import Grund

# alte Adresse → (leuchtender Menüpunkt, gewählter Reiter der Reihe)
ALT = {"start": ("start", None), "projektweg": ("projektweg", "projektweg"), "themen": ("projektweg", "themen"), "planung": ("projektweg", "planung"),
       "arbeit": ("projektweg", "planung"), "verlauf": ("projektweg", "planung"), "fragen": ("fragen", None), "wissen": ("wissen", None),
       "nachrichten": ("wissen", "Nachrichten"), "teamchat": ("wissen", "Nachrichten"), "dokumente": ("wissen", None), "releases": ("wissen", None),
       "betrieb": ("betrieb", "betrieb"), "termine": ("betrieb", "termine"), "einstellungen": ("einstellungen", None)}
MENUE = ["start", "projektweg", "fragen", "wissen", "betrieb", "einstellungen"]
KENNT = "document.querySelector('#inhalt .seitenkopf h1') && zustand.sicht === '%s'"


def alle_adressen(test, sichten, g):
    test.groesse(g)
    for s in sichten:
        punkt, reiter = ALT[s]
        with test.subTest(sicht=s, g=g):
            test.oeffnen(s, KENNT % s)
            test.assertEqual(test.tab.js("[...document.querySelectorAll('nav a[data-sicht].an')].map(a => a.dataset.sicht)"), [punkt])
            an = test.tab.js("(() => { const b = document.querySelector('.bereich-reihe .an'); return b ? (b.dataset.s || b.textContent) : null; })()")
            test.assertEqual(an, reiter)


class Seite(Daten, Rundgang):
    def test_jede_alte_adresse_pc(self):
        alle_adressen(self, ALT, "pc")

    def test_jede_alte_adresse_handy(self):
        alle_adressen(self, [s for s in ALT if s not in ("betrieb", "einstellungen", "termine")], "handy")

    def test_menue_pc_und_handy(self):
        self.groesse("pc")
        self.oeffnen("start", "document.querySelector('#steuerung')")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('nav a[data-sicht]')].map(a => a.dataset.sicht)"), MENUE)
        self.assertEqual(self.tab.js("[...document.querySelectorAll('nav a[data-sicht] [data-t]')].filter(x => !x.hidden).map(x => x.textContent)"),
                         ["Leitstand", "Projektweg", "Fragen", "Wissen", "Betrieb", "Einstellungen"])
        self.tab.js("sprache_setzen('en')")
        self.warten("document.querySelector('#inhalt h1')?.textContent === 'Control room'")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('nav a[data-sicht] [data-t]')].filter(x => !x.hidden).map(x => x.textContent)"),
                         ["Control room", "Project path", "Questions", "Knowledge", "Operations", "Settings"])
        self.tab.js("sprache_setzen('de')")
        self.groesse("handy")
        self.oeffnen("start", "document.querySelector('#steuerung')")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('nav a')].filter(a => a.offsetParent !== null).map(a => a.dataset.sicht || a.id)"),
                         ["start", "projektweg", "fragen", "wissen", "mehr"])

    def test_steuerung_knopf_und_adresse(self):
        self.groesse("pc")
        self.oeffnen("start", "document.querySelector('#zur-steuerung') && document.querySelector('#steuerung button')")
        self.assertEqual(self.tab.js("document.querySelector('#steuerung-titel').textContent"), "Steuerung")
        oben = "document.querySelector('#steuerung-titel').getBoundingClientRect().top"
        self.tab.js("document.querySelector('#zur-steuerung').click()")
        self.warten(f"{oben} < innerHeight - 40")
        self.oeffnen("steuerung", "zustand.sicht === 'start' && document.querySelector('#steuerung')")      # Adresse #steuerung
        self.warten(f"{oben} < innerHeight - 40")
        self.assertNotIn("zum Leitstand", self.tab.js("document.body.innerText"))

    def test_reihe_ohne_zahl_und_umschalten(self):
        self.groesse("pc")
        self.oeffnen("projektweg", "document.querySelector('.bereich-reihe')")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.bereich-reihe button')].map(b => b.textContent)"), ["Projektweg", "Themen", "Planung"])
        self.tab.js("document.querySelector('.bereich-reihe [data-s=planung]').click()")
        self.warten("zustand.sicht === 'planung' && document.querySelector('.bereich-reihe .an')?.dataset.s === 'planung'")
        self.oeffnen("betrieb", "document.querySelector('.bereich-reihe')")
        self.tab.js("document.querySelector('.bereich-reihe [data-s=termine]').click()")
        self.warten("zustand.sicht === 'termine' && ([...document.querySelectorAll('#inhalt .leer')].some(x => x.textContent === t('tm_leer'))"
                    " || document.querySelector('#inhalt .tm-tag'))")                               # die Termine selbst, nicht Reste der Seite davor
        self.oeffnen("planung", "document.querySelector('#inhalt .bereich-reiter')")
        self.assertFalse(self.tab.js("[...document.querySelectorAll('#inhalt .bereich-reiter button')].some(b => b.textContent === 'Termine')"))   # ein Ort

    def test_bilder(self):
        for sicht, ort, bereit in (("start", "leitstand", "document.querySelector('#steuerung')"), ("projektweg", "projektweg", "document.querySelector('.pjw-seite')"),
                                   ("themen", "themen", "document.querySelector('#inhalt .bereich-reihe')"), ("planung", "planung", "document.querySelector('#inhalt .bereich-reiter')"),
                                   ("nachrichten", "nachrichten", "document.querySelector('.nr-reiter')"), ("termine", "termine", "document.querySelector('.bereich-reihe')")):
            for g in ("pc", "handy"):
                for t in ("hell", "dunkel"):
                    self.assertEqual(self.besuchen(sicht, "a2018-" + ort, bereit=bereit, g=g, t=t), [], f"{ort} {g} {t}")
        for t in ("hell", "dunkel"):
            self.assertEqual(self.besuchen("start", "a2018-steuerung", bereit="document.querySelector('#zur-steuerung')", tun="zurSteuerung()",
                                           danach="document.querySelector('#steuerung-titel').getBoundingClientRect().top < innerHeight - 40", g="pc", t=t), [], t)
            self.assertEqual(self.besuchen("start", "a2018-mehr", bereit="document.querySelector('#mehr')", tun="document.getElementById('mehr').click()",
                                           danach="document.querySelector('.mehr-liste')", g="handy", t=t), [], t)


@unittest.skipUnless(PHP, "php nicht installiert")
class Online(Daten, OnlineRundgang):
    def test_jede_alte_adresse_online(self):
        alle_adressen(self, [s for s in ALT if s not in ("einstellungen", "betrieb", "termine")], "pc")
        alle_adressen(self, [s for s in ALT if s not in ("einstellungen",)], "handy")


class Push(unittest.TestCase):
    def test_jeder_push_link_fuehrt_auf_eine_seite(self):
        """Jede Seite, die eine Meldung öffnet, kennt die Workbench – als Menüpunkt oder als Adresse seines Bereichs."""
        with open(push.__file__, encoding="utf-8") as f:
            quelle = f.read()
        ziele = set(re.findall(r'"(start|fragen|planung|themen|nachrichten|projektweg|arbeit|wissen|betrieb|termine)"\)\)?', quelle))
        self.assertTrue({"start", "fragen", "planung"} <= ziele, ziele)
        html = workbench.seite()
        sichten = html.split("const fertig = ({")[1].split("}[sicht]")[0]
        bereich = dict(re.findall(r'(\w+): "(\w+)"', html.split("const BEREICH = {")[1].split("};")[0]))
        for z in ziele:
            self.assertIn(f"{z}: sicht", sichten)
            self.assertIn(bereich.get(z, z), MENUE)


class Zahl(Grund):
    """Die Menüzahl am Projektweg: Themen, Spezifikationen, Pläne und eigene Aufgaben – jedes Ding einmal, nur für den Menschen."""

    def setUp(self):
        super().setUp()
        kern.agent_neu(self.con, self.pid, "CC1")

    def zahl(self):
        return workbench.daten_start(self.con, self.pid)["zaehler"]["projektweg"]

    def thema(self, name):
        t = themen.neu(self.con, self.pid, "TL", name, pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", t, "Text")
        return t

    def test_themen_zaehlen_einmal_und_nur_beim_menschen(self):
        self.assertEqual(self.zahl(), 0)
        a = self.thema("Eins")
        self.thema("Zwei")
        self.assertEqual(self.zahl(), 2)
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, a)
        self.assertEqual(self.zahl(), 1)
        with mock.patch("amw.projektweg._freigebende", return_value=["TL"]):                         # Co und Lead geben frei: nichts für den Menschen
            self.assertEqual(self.zahl(), 0)

    def test_eigene_aufgaben_ohne_geparkte_und_kein_ding_doppelt(self):
        a = kern.aufgabe_neu(self.con, self.pid, "TL", "Schlüssel eintragen", kern.ENTWICKLER)
        b = kern.aufgabe_neu(self.con, self.pid, "TL", "Später", kern.ENTWICKLER)
        self.assertEqual(self.zahl(), 2)
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET einstufung = 'geparkt' WHERE id = ?", (b,))
            self.con.execute("UPDATE aufgabe SET plan_status = 'vorgelegt', verantwortlich = ? WHERE id = ?", (planung.MENSCH, a))
        self.assertEqual(self.zahl(), 1)                                                               # als eigene Aufgabe und als Plan: einmal

    def test_spezifikation_beim_lead_zaehlt_nicht(self):
        wartet = {"spezifikationen": [{"bogen_id": 1, "teil": "entwurf"}], "plaene": [], "eigene": []}
        self.assertEqual(workbench._projektweg_zahl(self.con, self.pid, wartet, []), 1)
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, spec_frei="lead")
        self.assertEqual(workbench._projektweg_zahl(self.con, self.pid, wartet, []), 0)

    def test_startdaten_ohne_viele_abfragen(self):
        """Ohne Offenes kostet die Zahl keine Abfrage; mit Themen nur die Projekt-Einstellung."""
        n = []
        self.con.set_trace_callback(n.append)
        workbench._projektweg_zahl(self.con, self.pid, {"spezifikationen": [], "plaene": [], "eigene": []}, [])
        self.assertEqual(n, [])
        workbench._projektweg_zahl(self.con, self.pid, {"spezifikationen": [], "plaene": [], "eigene": []}, [{"id": 1, "status": "dich"}])
        self.con.set_trace_callback(None)
        self.assertLessEqual(len(n), 4)


if __name__ == "__main__":
    unittest.main()
