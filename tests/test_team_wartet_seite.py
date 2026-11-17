"""Team-Baum in der Seite (A1860, Marcel W2356): „wartet auf dich“ nur, wenn der Mensch wirklich dran ist – wartet der Agent auf
den TL, steht neutral „wartet auf TL“. Rundgang PC/Handy/iPad hell/dunkel (Bilder für die Prüfbitte über AMW_RUNDGANG_BILDER)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
from amw import db, kern
from tests.rundgang import Rundgang


class TeamWartet(Rundgang):
    def daten(self):                                                     # TL (Lead) legt schon das Gerüst an
        for k in ("CCamw", "CCamw2"):
            kern.agent_neu(self.con, self.pid, k)
        with db.schreiben(self.con):
            jetzt = db.jetzt()
            neu = lambda titel, agent, einstufung="aktiv": db.einfuegen(self.con, "aufgabe", projekt_id=self.pid, titel=titel, agent=agent,
                                                                         status="wartet", einstufung=einstufung, angelegt_utc=jetzt,
                                                                         angelegt_von="TL")
            grund = lambda aid, art, bezug: db.einfuegen(self.con, "wartegrund", projekt_id=self.pid, aufgabe_id=aid, art=art, bezug=bezug,
                                                         angelegt_utc=jetzt, angelegt_von="TL")
            grund(neu("Alt im Eingang", "CCamw", "pool"), "entwickler", "Entwickler")    # wie A1629/A1675 bei CCamw
            grund(neu("Arbeitsplätze – Prüfung", "CCamw"), "agent", "TL")
            self.frage_aufgabe = neu("Symbol der Taskleiste", "CCamw2")
        fid = kern.frage_neu(self.con, self.pid, "TL", "entwickler", "Wie soll das Symbol aussehen?", [("A", "rund")], "A", "weil",
                             geprueft="keine Treffer")
        with db.schreiben(self.con):
            db.einfuegen(self.con, "wartegrund", projekt_id=self.pid, aufgabe_id=self.frage_aufgabe, art="frage", bezug=f"F{fid}",
                         angelegt_utc=db.jetzt(), angelegt_von="TL")

    BAUM = "[...document.querySelectorAll('.tm-schalter button')][0].click()"
    BEREIT = "document.querySelector('#team')"

    def karte(self, k):
        return self.tab.js(f"document.querySelector('.tm-knoten[data-k={k}] .tm-wer').textContent")

    def test_etikett_je_karte(self):
        self.oeffnen("start", self.BEREIT)
        self.tab.js(self.BAUM)
        self.warten("document.querySelector('.tm-baum .tm-knoten[data-k=CCamw]')")
        self.assertIn("wartet auf TL", self.karte("CCamw"))
        self.assertNotIn("wartet auf dich", self.karte("CCamw"))
        self.assertIn("wartet auf dich", self.karte("CCamw2"))
        self.assertTrue(self.tab.js("!!document.querySelector('.tm-knoten[data-k=CCamw] .tm-auf-andere')"))

    def test_rundgang(self):
        self.ueberall("start", "team-wartet", bereit=self.BEREIT,
                      tun=self.BAUM + "; document.getElementById('team').scrollIntoView({block: 'start'})",
                      danach="document.querySelector('.tm-baum .tm-knoten[data-k=CCamw]')")
