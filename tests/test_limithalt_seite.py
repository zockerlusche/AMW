"""Halt beim Wochenlimit in Einstellungen › Projekt (A1888): Feld mit einem Satz Erklärung, Vorgabe 95 sichtbar, Speichern
übernimmt den Wert; Rundgang PC/Handy (Bilder über AMW_RUNDGANG_BILDER)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
from amw import limithalt
from tests.rundgang import Rundgang


class LimitHaltSeite(Rundgang):
    FINDE = ("[...document.querySelectorAll('#inhalt *')].find(e => e.children.length === 0"
             " && /^(Halt beim Wochenlimit \\(%\\)|Stop at weekly limit \\(%\\))$/.test(e.textContent.trim()))")

    def test_feld_und_rundgang(self):
        for g in ("pc", "handy"):
            for th in ("hell", "dunkel"):
                fehler = self.besuchen("einstellungen", "limit-halt", bereit=self.FINDE,
                                       tun=f"{self.FINDE}.scrollIntoView({{ block: 'center' }})", danach="true", g=g, t=th)
                self.assertEqual(fehler, [], f"{g} {th}")
        zeile = f"{self.FINDE}.closest('tr, .einst-zeile, div').parentElement"
        text = self.tab.js(f"{zeile}.innerText")
        self.assertIn("hält die AMW alle Coder an", text)
        self.assertEqual(self.tab.js(f"{zeile}.querySelector('input[type=number]').value"), "95")
        self.assertEqual(limithalt.schwelle(self.con, self.pid), 95)
