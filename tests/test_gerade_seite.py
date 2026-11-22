"""A1953 in der Seite: „Arbeitet gerade an“ abgeleitet – auf der Kachel mit Quelle und Alter im Tooltip, veraltet grau mit
„veraltet?“; in der Übersicht des Agenten Quelle, Alter und Ergänzung. Rundgang PC/Handy (Bilder über AMW_RUNDGANG_BILDER)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime

from amw import db, kern
from tests.rundgang import Rundgang


def vor(minuten):
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minuten)).strftime("%Y-%m-%dT%H:%M:%SZ")


class GeradeSeite(Rundgang):
    def daten(self):                                                     # TL (Lead) legt schon das Gerüst an
        for k in ("CCamw", "CCamw2"):
            kern.agent_neu(self.con, self.pid, k)
        with db.schreiben(self.con):
            ids = {r[1]: r[0] for r in self.con.execute("SELECT id, kennung FROM agent WHERE projekt_id = ?", (self.pid,))}
            neu = lambda titel, agent: db.einfuegen(self.con, "aufgabe", projekt_id=self.pid, titel=titel, agent=agent, status="laeuft",   # noqa: E731
                                                     einstufung="aktiv", angelegt_utc=vor(60), begonnen_utc=vor(40), angelegt_von="TL")
            self.a1 = neu("Gesamtlauf parallel", "CCamw")
            self.a2 = neu("Ansicht Grobplanung", "CCamw2")
            db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="CCamw", beschreibung="Messlauf 3 von 3", status="laeuft",
                         angemeldet_utc=vor(12), start_utc=vor(11), aufgabe_id=self.a1)
            db.einfuegen(self.con, "sitzung", agent_id=ids["CCamw"], claude_sitzung="s1", gestartet_utc=vor(90), letzter_puls_utc=vor(1),
                         taetigkeit="wartet auf das Ergebnis", taetigkeit_utc=vor(5), aufgabe_id=self.a1)
            db.einfuegen(self.con, "sitzung", agent_id=ids["CCamw2"], claude_sitzung="s2", gestartet_utc=vor(120), letzter_puls_utc=vor(45),
                         taetigkeit="A1900 alte Sache", taetigkeit_utc=vor(100))

    BEREIT = "document.querySelector('#team')"

    def test_kachel_und_uebersicht(self):
        self.oeffnen("start", self.BEREIT)
        team = self.tab.js("document.querySelector('#team').innerText")
        self.assertIn("Gesamtlauf parallel", team)
        self.assertIn("veraltet?", team)                                                      # CCamw2: seit 45 min kein Puls
        self.assertNotIn("A1900 alte Sache", team)                                           # andere Aufgabe: keine Ergänzung
        self.tab.js("agentDialog('CCamw')")
        self.warten("document.querySelector('.abschnitt.macht .eintrag')")
        macht = self.tab.js("document.querySelector('.abschnitt.macht').textContent")
        for teil in ("L", "Messlauf 3 von 3", "wartet auf das Ergebnis", "laufender Lauf", "vor 11 min"):
            self.assertIn(teil, macht)
        self.assertNotIn("veraltet?", macht)

    def test_rundgang(self):
        self.ueberall("start", "gerade-kachel", bereit=self.BEREIT,
                      tun="document.getElementById('team').scrollIntoView({block: 'start'})", danach=self.BEREIT)
        for g in ("pc", "handy"):
            fehler = self.besuchen("start", "gerade-uebersicht", bereit=self.BEREIT, tun="agentDialog('CCamw')",
                                   danach="document.querySelector('.abschnitt.macht .eintrag')", g=g, t="hell")
            self.assertEqual(fehler, [], g)
