"""A2004 in der Seite: Betrieb zeigt die Kennzahl „Anteil Headless (7 Tage)“ mit dem Ziel ≥ 50 % – unter dem Ziel in Bernstein, sonst
ohne Farbe (TH156: Farbe nur bei Handlungsbedarf). Bilder PC/Handy hell/dunkel über AMW_RUNDGANG_BILDER."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
from amw import arbeitspaket, db, kern
from tests.rundgang import Rundgang

KARTE = "document.querySelector('#inhalt .karte[data-k=p-quote]')"


class AnteilP(Rundgang):
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        for i, p in enumerate((True, False, False, False)):
            aid = kern.aufgabe_neu(self.con, self.pid, "TL", f"Paket {i}", "CC1")
            if p:
                arbeitspaket.setzen(self.con, self.pid, "TL", aid, art="p")
            with db.schreiben(self.con):
                self.con.execute("UPDATE aufgabe SET status = 'fertig', begonnen_utc = ?, fertig_utc = ?, beleg = 'x' WHERE id = ?",
                                 (db.jetzt(), db.jetzt(), aid))

    def test_kennzahl_unter_dem_ziel(self):
        for g in ("pc", "handy"):
            for t in ("hell", "dunkel"):
                self.assertEqual(self.besuchen("betrieb", "betrieb-a2004", bereit=KARTE, g=g, t=t), [], f"{g} {t}")
        self.assertEqual(self.tab.js(f"{KARTE}.querySelector('.wert').textContent"), "25 %")
        self.assertEqual(self.tab.js(f"{KARTE}.querySelector('.sehrleise').textContent"), "1 von 4 fertigen Paketen headless · Ziel ≥ 50 %")
        self.assertIn("bernstein", self.tab.js(f"{KARTE}.querySelector('.wert').getAttribute('style')"))
        self.assertFalse(self.tab.js("document.documentElement.scrollWidth > innerWidth + 1"))
