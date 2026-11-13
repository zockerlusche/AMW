"""Liste und Inhalt getrennt scrollen wie im Mail-Programm (A1628, Marcel 13.11.): Unter Nachrichten scrollten Liste und
geöffnete Nachricht gemeinsam – wer unten in der Liste eine Nachricht öffnete und rechts weiterlas, verlor die Liste.
Jetzt hat am PC jede Spalte ihren eigenen Scrollbereich; die Seite scrollt nicht; die gewählte Zeile bleibt sichtbar.
Einstellungen › Agenten: die Liste bleibt beim Scrollen stehen. Am Handy wie bisher (eine Spalte, Zurück).
Dazu D940 Fund 7: Nachrichten öffnet ohne gemerkte Wahl auf „Eingang“, wenn dort Neues liegt."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import unittest

from amw import kern
from tests.rundgang import Rundgang

LANG = "\n".join(f"Absatz {i}: Ein längerer Bericht über den Stand der Seite, damit rechts gescrollt werden muss." for i in range(60))


class Daten:
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid, "CC2")
        for i in range(40):                                       # 40 Nachrichten an den Menschen: die Liste ist länger als das Fenster
            kern.posten(self.con, self.pid, "CC1" if i % 2 else "CC2", "Entwickler", "info", f"Meldung {i:02d}: Stand der Arbeit",
                        text=LANG)                       # jede lang genug, dass rechts gescrollt werden muss


class Nachrichten(Daten, Rundgang):
    LISTE, RECHTS = "document.querySelector('.nr-liste')", "document.querySelector('.nr-gespraech')"

    def oeffnen_eingang(self, g="pc"):
        self.groesse(g)
        self.oeffnen("nachrichten", "document.querySelectorAll('.nr-eintrag').length >= 40")

    def test_pc_liste_bleibt_stehen_wenn_rechts_gelesen_wird(self):
        self.oeffnen_eingang()
        L, R = self.LISTE, self.RECHTS
        self.assertTrue(self.tab.js("document.querySelector('.nr-raster').classList.contains('geteilt')"))
        self.assertEqual(self.tab.js(f"getComputedStyle({L}).overflowY"), "auto")
        self.assertGreater(self.tab.js(f"{L}.scrollHeight - {L}.clientHeight"), 200)           # die Liste scrollt für sich
        self.assertLessEqual(self.tab.js("document.querySelector('.nr-raster').getBoundingClientRect().bottom"), 900)
        # unten in der Liste die letzte Nachricht wählen – echter Klick
        self.tab.js(f"{L}.scrollTop = {L}.scrollHeight")
        self.warten(f"{L}.scrollTop > 200")
        letzte = self.tab.js(f"{L}.querySelector('.nr-eintrag:last-child .nr-kurz').textContent")
        self.tippen(".nr-eintrag:last-child")
        self.warten(f"{R}.querySelector('h3')?.textContent === {letzte!r}")
        unten = self.tab.js(f"{L}.scrollTop")
        self.assertGreater(unten, 200)                                                           # Klick lässt die Liste, wo sie war
        self.tab.js(f"{R}.scrollTop = {R}.scrollHeight")                                         # rechts weiterlesen
        self.warten(f"{R}.scrollTop > 300")
        self.assertEqual(self.tab.js(f"{L}.scrollTop"), unten)                                   # Liste unverändert
        self.assertEqual(self.tab.js("document.querySelector('#inhalt').scrollTop"), 0)        # die Seite scrollt nicht
        r = self.tab.js(f"(() => {{ const e = {L}.querySelector('.nr-eintrag.an').getBoundingClientRect(), l = {L}.getBoundingClientRect();"
                        " return e.top >= l.top - 1 && e.bottom <= l.bottom + 1; })()")
        self.assertTrue(r, "gewählte Zeile sichtbar")
        erste = self.tab.js(f"{L}.querySelector('.nr-eintrag:first-child .nr-kurz').textContent")
        self.tab.js(f"{L}.scrollTop = 0")
        self.tippen(".nr-eintrag:first-child")                                                   # andere Nachricht: rechts von oben
        self.warten(f"{R}.querySelector('h3')?.textContent === {erste!r}")
        self.assertEqual(self.tab.js(f"{R}.scrollTop"), 0)
        self.assertEqual(self.pruefen("nachrichten-geteilt", "pc", "dunkel"), [])

    def test_pc_fenster_kleiner_spalten_passen_sich_an(self):
        self.tab.senden("Emulation.setDeviceMetricsOverride", width=1280, height=640, deviceScaleFactor=1, mobile=False)
        self.oeffnen("nachrichten", "document.querySelectorAll('.nr-eintrag').length >= 40")
        self.warten("document.querySelector('.nr-raster').getBoundingClientRect().bottom <= 640")
        self.groesse("pc")                                                                       # größer: wächst mit
        self.warten("document.querySelector('.nr-raster').getBoundingClientRect().bottom > 800"
                    " && document.querySelector('.nr-raster').getBoundingClientRect().bottom <= 900")

    def test_handy_wie_bisher(self):
        self.oeffnen_eingang("handy")
        self.assertFalse(self.tab.js("!!document.querySelector('.nr-raster').style.height"))
        L = self.LISTE
        self.assertLessEqual(self.tab.js(f"{L}.scrollHeight - {L}.clientHeight"), 1)                 # keine eigene Scrollleiste: die Seite scrollt
        self.assertGreater(self.tab.js("document.querySelector('#inhalt').scrollHeight - document.querySelector('#inhalt').clientHeight"), 200)
        self.tippen(".nr-eintrag:nth-child(3)")
        self.warten("document.querySelector('.nr-raster').classList.contains('detail') && getComputedStyle(document.querySelector('.nr-zurueck')).display !== 'none'")
        self.assertEqual(self.pruefen("nachrichten-handy", "handy", "hell"), [])

    def test_ohne_gemerkte_wahl_eingang_wenn_neues(self):
        self.groesse("pc")
        self.oeffnen("nachrichten", "document.querySelector('.nr-reiter button.an')")
        self.tab.js("try { Object.keys(localStorage).filter(k => k.includes('amw-nr')).forEach(k => localStorage.removeItem(k)) } catch (e) {}")
        self.oeffnen("nachrichten", "document.querySelector('.nr-reiter button.an')")
        self.assertIn("Eingang", self.tab.js("document.querySelector('.nr-reiter button.an').textContent"))
        self.tab.js("[...document.querySelectorAll('.nr-reiter button')].find(b => b.textContent.startsWith('Gesendet')).click()")   # gemerkt
        self.oeffnen("nachrichten", "document.querySelector('.nr-reiter button.an')")
        self.assertIn("Gesendet", self.tab.js("document.querySelector('.nr-reiter button.an').textContent"))


class Agenten(Daten, Rundgang):
    """Einstellungen › Agenten: die Liste der Agenten bleibt stehen, während man das lange Formular rechts liest."""

    def daten(self):
        super().daten()
        for i in range(3, 12):
            kern.agent_neu(self.con, self.pid, f"CC{i}")

    def test_liste_klebt(self):
        self.groesse("pc")
        self.oeffnen("einstellungen", "document.querySelector('.ae-raster.klebt')")
        self.assertEqual(self.tab.js("getComputedStyle(document.querySelector('.ae-raster > .ae-wahl')).position"), "sticky")
        self.assertEqual(self.pruefen("einstellungen-agenten", "pc", "dunkel"), [])             # Prüfung 5 scrollt die Seite selbst


class Pruefung(Rundgang):
    """Die neue Prüfung des Rundgangs schlägt an, wenn Liste und Inhalt wieder gemeinsam scrollen (der alte Fehler)."""

    def test_schlaegt_an(self):
        self.groesse("pc")
        self.oeffnen("start", "document.querySelector('#team [data-k]')")
        self.tab.js("document.querySelector('#inhalt').append(Object.assign(document.createElement('div'), { className: 'geteilt',"
                    " style: 'display:grid;grid-template-columns:1fr 1fr', innerHTML: '<div style=\"height:2400px\">Liste</div><div style=\"height:3000px\">Inhalt</div>' }))")
        funde = [f[1] for f in self.pruefen("pruefung-geteilt", "pc", "dunkel")]
        self.assertTrue(any("unter den Fensterrand" in f for f in funde), funde)
        self.tab.js("document.querySelector('#inhalt > .geteilt').remove()")
        self.tab.js("document.querySelector('#inhalt').append(Object.assign(document.createElement('div'), { className: 'geteilt',"
                    " style: 'display:grid;grid-template-columns:1fr 1fr;height:300px', innerHTML: '<div style=\"overflow:hidden\"><div style=\"height:900px\">Liste</div></div><div style=\"overflow:auto\"><div style=\"height:900px\">Inhalt</div></div>' }))")
        funde = [f[1] for f in self.pruefen("pruefung-geteilt2", "pc", "dunkel")]
        self.assertTrue(any("ohne eigenen Scrollbereich" in f for f in funde), funde)


if __name__ == "__main__":
    unittest.main()
