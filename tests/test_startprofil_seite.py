"""Startprofile in der Seite (A1865): „Starten / fortsetzen“ fragt nach, und ein Ordner, der jede Sitzung als anderen Agenten
anmeldet, wird nicht gestartet (Meldung „Zwilling“) – es öffnet sich kein Terminal. Bilder PC + Handy über AMW_RUNDGANG_BILDER."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os

from amw import kern, steuerung
from tests.rundgang import Rundgang


class StartZwilling(Rundgang):
    def daten(self):                                                     # TL (Lead) legt schon das Gerüst an
        kern.agent_neu(self.con, self.pid, "CC1")
        ordner = os.path.join(self.ordner.name, "fremder-ordner")
        os.makedirs(os.path.join(ordner, ".claude"))
        with open(os.path.join(ordner, ".claude", "settings.local.json"), "w", encoding="utf-8") as f:
            json.dump({"env": {"AMW_AGENT": "CCamw"}}, f)                 # meldet jede Sitzung als CCamw an
        steuerung.profil_setzen(self.con, self.pid, "Entwickler", "CC1", ordner=ordner)

    # Team als Baum zeigen, auf die Karte von CC1 warten, ihr Menü öffnen und „Starten / fortsetzen“ wählen
    MENUE = ("window.confirm = window.confirm_test || (() => true); [...document.querySelectorAll('.tm-schalter button')][0].click();"
             " (function los() { const b = [...document.querySelectorAll('.tm-knoten[data-k=CC1] button')].find(x => x.textContent === '⋯');"
             " if (!b) return setTimeout(los, 100); b.click();"
             " [...document.querySelectorAll('.menue button')].find(x => x.textContent.startsWith(t('m_start'))).click(); })()")
    ZWILLING = "[...document.querySelectorAll('.toast')].some(x => x.textContent.includes('Zwilling'))"

    def test_start_mit_rueckfrage_und_zwilling(self):
        self.oeffnen("start", "document.querySelector('#team')")
        self.tab.js("window.confirm_test = x => { window.__frage = x; return true; }")
        self.tab.js(self.MENUE)
        self.warten(self.ZWILLING)
        self.assertIn("CC1", self.tab.js("window.__frage || ''"))                 # erst die Rückfrage, dann der Versuch
        self.assertIn("meldet jede Sitzung als CCamw an", self.tab.js("[...document.querySelectorAll('.toast')].map(x => x.textContent).join(' ')"))

    def test_bilder(self):
        for g in ("pc", "handy"):
            for th in ("hell", "dunkel"):
                fehler = self.besuchen("start", "start-zwilling", bereit="document.querySelector('#team')",
                                       tun=self.MENUE, danach=self.ZWILLING, g=g, t=th)
                self.assertEqual(fehler, [], f"{g} {th}")
