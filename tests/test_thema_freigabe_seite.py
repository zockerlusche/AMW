"""A1937 (K1, B2913): In der Seite zeigt ein Thema, wessen Ja zur Freigabe noch fehlt (thema_freigabe = co+lead), und ob es
nur der Mensch freigibt. Rundgang PC/Handy hell/dunkel (Bilder über AMW_RUNDGANG_BILDER)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
from amw import kern, themen
from tests.rundgang import Rundgang


class ThemaFreigabeSeite(Rundgang):
    def daten(self):                                                     # TL (Lead) legt schon das Gerüst an
        for k in ("CO", "CC1"):
            kern.agent_neu(self.con, self.pid, k)
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, co_entwickler="CO", thema_freigabe="co+lead")
        self.tid = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", self.tid, "Wer die Online-Seite öffnet, meldet sich mit seinem Firmen-Konto an.")
        themen.ja_geben(self.con, self.pid, "CO", self.tid)                                     # Co hat Ja gesagt, der Lead noch nicht
        self.mensch = themen.neu(self.con, self.pid, "TL", "Alte Daten löschen", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", self.mensch, "Archiv nach einem Jahr löschen.")
        themen.nur_mensch_setzen(self.con, self.pid, "CC1", self.mensch)

    LISTE = "document.querySelector('.th-liste .th-zeile')"

    def oeffne(self, tid):
        return (f"document.querySelector('.th-zeile[data-th=\"{tid}\"]').click()")

    def test_ja_fehlt_und_nur_mensch(self):
        self.oeffnen("themen", self.LISTE)
        self.tab.js(self.oeffne(self.tid))
        self.warten("document.querySelector('.th-thema h2')?.textContent === 'Anmeldung'")
        self.assertIn("Ja fehlt noch: Lead", self.tab.js("document.querySelector('.th-thema').innerText"))
        self.tab.js(self.oeffne(self.mensch))
        self.warten("document.querySelector('.th-thema h2')?.textContent === 'Alte Daten löschen'")
        text = self.tab.js("document.querySelector('.th-thema').innerText")
        self.assertIn("Gibst nur du frei (Löschen, Kosten, Schema oder Außenwirkung)", text)
        self.assertNotIn("Ja fehlt noch", text)

    def test_rundgang(self):
        for g in ("pc", "handy"):
            for th in ("hell", "dunkel"):
                fehler = self.besuchen("themen", "thema-ja-fehlt", bereit=self.LISTE, tun=self.oeffne(self.tid),
                                       danach="document.querySelector('.th-thema h2')?.textContent === 'Anmeldung'", g=g, t=th)
                self.assertEqual(fehler, [], f"{g} {th}")
