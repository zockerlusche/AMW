"""A1947: Planung zeigt die Lücken Thema ↔ Paket als Fakt-Zeile (Zahl, aufgeklappt die Liste) – ohne Lücken keine Zeile.
PC/Handy, Bilder über AMW_RUNDGANG_BILDER."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
from amw import kern, themen
from tests.rundgang import Rundgang


class PlanungLuecken(Rundgang):
    def daten(self):                                                     # TL (Lead) legt schon das Gerüst an
        kern.agent_neu(self.con, self.pid, "CC1")
        self.tid = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", self.tid, "Mit Firmen-Konto.")
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Altes Menü aufräumen", "CC1")

    ZEILE = "document.querySelector('#inhalt .pl-luecken')"

    def test_fakt_zeile_mit_liste(self):
        for g in ("pc", "handy"):
            with self.subTest(g=g):
                self.groesse(g)
                self.oeffnen("planung", self.ZEILE)
                self.assertEqual(self.tab.js(f"{self.ZEILE}.dataset.luecken"), "1/1")
                self.assertEqual(self.tab.js(f"{self.ZEILE}.querySelector('summary').textContent"),
                                 "Lücken: 1 freigegebenes Thema ohne Paket · 1 Paket ohne Thema")
                self.tab.js(f"{self.ZEILE}.open = true")
                text = self.tab.js(f"{self.ZEILE}.innerText")
                self.assertIn(f"TH{self.tid} Anmeldung – freigegeben, kein Paket", text)
                self.assertIn(f"A{self.aid} Altes Menü aufräumen – ohne Thema", text)

    def test_ohne_luecken_keine_zeile(self):
        themen.verweise_setzen(self.con, self.pid, "TL", self.aid, [f"TH{self.tid}"])
        self.oeffnen("planung", "document.querySelector('#inhalt .reiter, #inhalt .leer, #inhalt h1')")
        self.warten("typeof zustand === 'object' && zustand.sicht === 'planung' && document.querySelector('#inhalt .signal')")
        self.assertFalse(self.tab.js(f"!!{self.ZEILE}"))

    def test_bilder(self):
        offen = (f"{self.ZEILE}.open = true", f"{self.ZEILE}.open")
        for g in ("pc", "handy"):
            for th in ("hell", "dunkel"):
                self.assertEqual(self.besuchen("planung", "planung-luecken", bereit=self.ZEILE, tun=offen[0], danach=offen[1], g=g, t=th),
                                 [], f"{g} {th}")
