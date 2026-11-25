"""A2134: „Für dich“ zeigt beim Prüfpunkt den Titel des Pakets davor (PC/Handy, hell/dunkel; Bilder über AMW_RUNDGANG_BILDER)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import unittest

from amw import db, dokumente, kern, planung, zwischenpruefung
from tests.rundgang import Rundgang


class Zeile(Rundgang):
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, entwickler_name="Alex")
        self.b = planung.bogen_neu(self.con, self.pid, "TL", "Spielstände", ziel="Z", abnahme="V")
        planung.bogen_status(self.con, self.pid, "TL", self.b, "aktiv")
        eins = planung.schritt_setzen(self.con, self.pid, "TL", titel="Speichern und Laden mit drei Speicherplätzen", bogen_id=self.b, agent="CC1")
        zwei = planung.schritt_setzen(self.con, self.pid, "TL", titel="Anzeige der Spielstände", bogen_id=self.b, agent="CC1")
        planung.abhaengigkeit_setzen(self.con, self.pid, "TL", zwei, [eins])
        self.p = zwischenpruefung.einfuegen(self.con, self.pid, kern.ENTWICKLER, eins)["paket"]
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc1234', fertig_utc = ? WHERE id = ?", (db.jetzt(), eins))
            self.con.execute("UPDATE aufgabe SET agent = 'CC1', status = 'laeuft', begonnen_utc = ? WHERE id = ?", (db.jetzt(), self.p))
        dokumente.ablegen_inhalt(self.con, self.pid, "CC1", b"Stand liegt in dist/", "stand.md", titel="Stand", art="ergebnis", aufgabe=self.p)

    def zeile(self):
        return f"document.querySelector('.ua-zeile[data-aufgabe=\"{self.p}\"]')"

    def test_titel_davor(self):
        self.oeffnen("start", self.zeile())
        self.assertIn("Stand ist gepackt – testen: „Speichern und Laden mit drei Speicherplätzen“", self.tab.js(self.zeile() + ".innerText"))
        self.tab.js("localStorage.setItem('amw-sprache', 'en')")
        self.oeffnen("start", self.zeile())
        self.assertIn("Build is packed – please test: “Speichern und Laden", self.tab.js(self.zeile() + ".innerText"))

    def test_rundgang(self):
        for g in ("pc", "handy"):
            for th in ("hell", "dunkel"):
                self.assertEqual(self.besuchen("start", "a2134-zeile", bereit=self.zeile(), tun=self.zeile() + ".scrollIntoView({block: 'center'})",
                                               g=g, t=th), [], f"{g} {th}")


if __name__ == "__main__":
    unittest.main()
