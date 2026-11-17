"""Startvorschlag in der Seite (A1867): „CC1 starten?“ unter „Für dich“ mit Grund und den Knöpfen Starten/Nicht jetzt (am PC);
„Nicht jetzt“ nimmt den Vorschlag weg. Rundgang PC/Handy (Bilder über AMW_RUNDGANG_BILDER). Starten wird nicht geklickt – es
öffnete ein echtes Terminal."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
from amw import kern, steuerung
from tests.rundgang import Rundgang


class Startvorschlag(Rundgang):
    def daten(self):                                                     # TL (Lead) legt schon das Gerüst an
        kern.agent_neu(self.con, self.pid, "CC1")
        steuerung.profil_setzen(self.con, self.pid, kern.ENTWICKLER, "CC1", ordner=self.ordner.name)
        kern.aufgabe_neu(self.con, self.pid, "TL", "Statuszeile kürzer", agent="CC1")

    ZEILE = "document.querySelector('.sv-zeile[data-k=CC1]')"

    def test_vorschlag_und_nicht_jetzt(self):
        self.oeffnen("start", self.ZEILE)
        text = self.tab.js(f"{self.ZEILE}.innerText").lower()
        for teil in ("cc1 starten?", "läuft nicht, hat aber arbeit", "statuszeile kürzer", "starten", "nicht jetzt"):
            self.assertIn(teil, text)
        self.tab.js(f"[...{self.ZEILE}.querySelectorAll('button')].find(b => b.textContent.startsWith(t('sv_nicht_jetzt'))).click()")
        self.warten(f"!{self.ZEILE}")
        self.assertEqual(steuerung.startvorschlaege(self.con, self.pid), [])

    def test_rundgang(self):
        for g in ("pc", "handy"):
            for th in ("hell", "dunkel"):
                self.assertEqual(self.besuchen("start", "startvorschlag", bereit=self.ZEILE, g=g, t=th), [], f"{g} {th}")
