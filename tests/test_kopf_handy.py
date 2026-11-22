"""Kopf am Handy, solange die Projektliste noch lädt (A1903, L2908: „Knopf ohne Namen“ – button#projekt-chip): Der Projekt-
Knopf hat bis dahin das Attribut hidden, die Handy-Regel display: inline-flex hob es auf – ein leerer, sichtbarer Knopf. Unter
Last kam /api/projekte spät, der Rundgang fand ihn. Hier hält der Test die Antwort auf /api/projekte zurück, bis er den
Zwischenzustand geprüft hat (A1960: vorher eine feste Verzögerung – unter Last war die Liste manchmal schon da, L3025)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import unittest

from amw import kern
from tests.rundgang import Rundgang

# A1960: /api/projekte antwortet erst, wenn der Test window.__projekteFreigeben() ruft – kein Zeitrennen mehr
ANHALTEN = ("(() => { const f = window.fetch; let frei; const tor = new Promise(ok => { frei = ok; });"
            " window.__projekteFreigeben = () => frei();"
            " window.fetch = (u, ...r) => String(u).includes('/api/projekte') ? tor.then(() => f(u, ...r)) : f(u, ...r); })()")
SICHTBAR = "(() => { const c = document.querySelector('#projekt-chip'); return getComputedStyle(c).display !== 'none' && c.offsetWidth > 0; })()"


class KopfHandy(Rundgang):
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")

    def setUp(self):
        super().setUp()
        self.tab.senden("Page.addScriptToEvaluateOnNewDocument", source=ANHALTEN)

    def test_projekt_knopf_erst_mit_namen(self):
        for t in ("hell", "dunkel"):
            with self.subTest(t=t):
                self.groesse("handy")
                self.oeffnen("wissen", "document.querySelector('#projekt-chip')")
                self.assertTrue(self.tab.js("document.querySelector('#projekt-chip').hidden"))      # Liste lädt noch
                self.assertFalse(self.tab.js(SICHTBAR))                                            # also nicht zu sehen
                self.assertEqual(self.pruefen("kopf-laedt", "handy", t), [])                       # kein „Knopf ohne Namen“
                self.tab.js("window.__projekteFreigeben()")                                        # jetzt darf die Liste kommen
                self.warten("!document.querySelector('#projekt-chip').hidden", 10)
                self.assertTrue(self.tab.js(SICHTBAR))
                self.assertIn("P", self.tab.js("document.querySelector('#projekt-chip').getAttribute('aria-label')"))


if __name__ == "__main__":
    unittest.main()
