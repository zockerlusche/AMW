"""A1939 (K3): In der Seite steht eine Aufgabe, die an einem Urteil hängt und bereit ist, unter „Für dich“ (Ja / Zurück / Ansehen);
der Meilenstein zeigt seine Themen und löst Verweise in Ziel und Abnahme auf; keine Spezifikation bei neuen Meilensteinen.
Rundgang PC/Handy hell/dunkel (Bilder über AMW_RUNDGANG_BILDER)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
from amw import db, fertigquelle, kern, planung, themen, urteil
from tests.rundgang import Rundgang


class UrteilSeite(Rundgang):
    def daten(self):                                                     # TL (Lead) legt schon das Gerüst an
        kern.agent_neu(self.con, self.pid, "CC1")
        self.tid = themen.neu(self.con, self.pid, "TL", "Marktlage", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", self.tid, "Wer baut so etwas schon?")
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.b = planung.bogen_neu(self.con, self.pid, "TL", "Konzept AMW 2.0", ziel=f"Konzept steht (TH{self.tid})",
                                   abnahme=f"TH{self.tid} freigegeben")
        with db.schreiben(self.con):
            self.con.execute("UPDATE bogen SET status = 'aktiv' WHERE id = ?", (self.b,))
        self.aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Marktübersicht schreiben", "CC1")
        planung.schritt_setzen(self.con, self.pid, "TL", aid=self.aid, bogen_id=self.b, kriterien=["liest sich gut"])
        themen.verweise_setzen(self.con, self.pid, "TL", self.aid, [f"TH{self.tid}"])
        fertigquelle.setzen(self.con, self.pid, "TL", self.aid, "ja")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.aid, "start")
        urteil.bereit_melden(self.con, self.pid, "CC1", self.aid)

    def zeile(self):
        return f"document.querySelector('.ua-zeile[data-aufgabe=\"{self.aid}\"]')"

    def test_fuer_dich(self):
        self.oeffnen("start", self.zeile())
        text = self.tab.js(self.zeile() + ".innerText")
        for teil in ("„Marktübersicht schreiben“ ist bereit zur Abnahme", "gemeldet von CC1", "1 offenes Kriterium hakt dein Ja ab"):
            self.assertIn(teil, text)
        self.assertEqual(self.tab.js(self.zeile() + ".querySelectorAll('button').length"), 2)

    def test_meilenstein_themen_und_verweise(self):
        self.oeffnen("planung", f"document.querySelector('#bogen-{self.b} .mk-details')")
        self.tab.js(f"document.querySelector('#bogen-{self.b} .mk-details').open = true")
        text = self.tab.js(f"document.querySelector('#bogen-{self.b} .mk-details').innerText")
        self.assertIn(f"→ TH{self.tid} Marktlage · freigegeben · Fassung 1", text)
        self.assertIn(f"TH{self.tid} Marktlage", self.tab.js(f"document.querySelector('#bogen-{self.b} .mk-themen').innerText"))
        self.assertNotIn("Anforderungen", text)                         # neue Meilensteine: keine Spezifikation

    def test_rundgang(self):
        for g in ("pc", "handy"):
            for th in ("hell", "dunkel"):
                self.assertEqual(self.besuchen("start", "fuer-dich-abnahme", bereit=self.zeile(), g=g, t=th), [], f"{g} {th}")
                self.assertEqual(self.besuchen("planung", "meilenstein-themen", bereit=f"document.querySelector('#bogen-{self.b} .mk-details')",
                                               tun=f"document.querySelector('#bogen-{self.b} .mk-details').open = true;"
                                                   f" document.querySelector('#bogen-{self.b} .mk-details').scrollIntoView()",
                                               g=g, t=th), [], f"{g} {th}")
