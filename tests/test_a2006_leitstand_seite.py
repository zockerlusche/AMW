"""A2006: Leitstand als Startseite – Aufbau von oben nach unten, Nachladen ohne Springen, Karten öffnen ihr Ding, Projektdetails im
Seitenfenster, Steuerung über den Knopf, Leerzustand, PC und Handy, hell und dunkel; die alten Karten und der Team-Baum sind weg."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import unittest

from amw import arbeitspaket, db, kern, planung
from tests.rundgang import OnlineRundgang, Rundgang

FERTIG = "document.querySelector('.ls-fort:not(.platz) .ls-zahl') && document.querySelector('.ls-ablauf')"


def bestand(con, pid):
    kern.agent_neu(con, pid, "CC1")
    m = planung.bogen_neu(con, pid, "TL", "Speichern", ziel="Z", abnahme="Vorführung", zieldatum="2026-01-01")
    planung.bogen_status(con, pid, "TL", m, "aktiv")
    a = planung.schritt_setzen(con, pid, "TL", titel="Spielstand anlegen und laden", bogen_id=m, agent="CC1", groesse="S", art="mechanisch")
    b = planung.schritt_setzen(con, pid, "TL", titel="Spielstand löschen", bogen_id=m, groesse="S", art="mechanisch", nach=[a])
    c = planung.schritt_setzen(con, pid, "TL", titel="Speicherplätze zählen", bogen_id=m, groesse="S", art="mechanisch")
    with db.schreiben(con):
        con.execute("UPDATE aufgabe SET status = 'laeuft', begonnen_utc = ? WHERE id = ?", (db.jetzt(), a))
        con.execute("UPDATE aufgabe SET status = 'fertig', fertig_utc = ?, beleg = 'abc1234' WHERE id = ?", (db.jetzt(), c))
    arbeitspaket.setzen(con, pid, "TL", a, art="agent")
    return {"a": a, "b": b, "c": c, "m": m}


class Seite(Rundgang):
    def daten(self):
        self.nr = bestand(self.con, self.pid)

    def test_aufbau_von_oben_nach_unten(self):
        for g in ("pc", "handy"):
            self.groesse(g)
            self.oeffnen("start", FERTIG)
            reihe = self.tab.js("[...document.querySelectorAll('.ls-fort, .ls-fuer, .ls-agenten, .ls-ressourcen, .ls-ablauf, #steuerung-titel')]"
                                ".map(e => e.className || e.id)")
            self.assertEqual([r.split()[0] for r in reihe], ["ls-fort", "ue-raster", "ls-agenten", "ls-ressourcen", "ls-ablauf", "steuerung-titel"], g)
            self.assertIn("1 von 3", self.tab.js("document.querySelector('.ls-fort').textContent"))
            self.assertEqual(self.tab.js("document.querySelectorAll('.ue-kachel, .tm-baum, .tm-liste, .ue-bogen').length"), 0)   # alte Karten weg

    def test_jetzt_karte_oeffnet_ihr_paket(self):
        self.oeffnen("start", FERTIG + " && document.querySelector('.ls-karte')")
        self.assertEqual(self.tab.js("document.querySelector('.ls-karte').dataset.ref"), f"A{self.nr['a']}")
        self.tab.js("document.querySelector('.ls-karte').click()")
        self.warten("[...document.querySelectorAll('.dialog')].some(d => d.textContent.includes('Spielstand anlegen'))")

    def test_projektdetails_und_steuerung(self):
        self.oeffnen("start", FERTIG)
        self.tab.js("[...document.querySelectorAll('.ls-leiste button')][1].click()")
        self.warten("document.querySelector('#ls-fenster .pjw-fenster') && document.querySelector('#ls-fenster').textContent.includes('M')")
        self.esc()
        self.warten("!document.querySelector('#ls-fenster')")
        self.tab.js("document.querySelector('#zur-steuerung').click()")
        self.warten("document.querySelector('#steuerung-titel').getBoundingClientRect().top < innerHeight")

    def test_nachladen_springt_nicht(self):
        """Die Plätze für Fortschritt und Ablauf stehen schon vor /api/leitstand; im 15-s-Takt kommt er nur bei neuem Stempel neu."""
        self.oeffnen("start", FERTIG)
        n = self.tab.js("performance.getEntriesByType('resource').filter(r => r.name.includes('/api/leitstand')).length")
        self.tab.js("void zeige('start', true)")
        self.warten(FERTIG)
        self.assertEqual(self.tab.js("performance.getEntriesByType('resource').filter(r => r.name.includes('/api/leitstand')).length"), n)

    def test_bilder(self):
        self.ueberall("start", "a2006-leitstand", bereit=FERTIG)


class Leer(Rundgang):
    def daten(self):
        pass

    def test_neues_projekt(self):
        self.oeffnen("start", "document.querySelector('.ls-leer')")
        self.assertIn("Konzept", self.tab.js("document.querySelector('.ls-leer').textContent"))
        self.ueberall("start", "a2006-leer", bereit="document.querySelector('.ls-leer')")


class Online(OnlineRundgang):
    def daten(self):
        self.nr = bestand(self.con, self.pid)

    def test_online_derselbe_leitstand(self):
        self.oeffnen("start", FERTIG)
        self.assertIn("1 von 3", self.tab.js("document.querySelector('.ls-fort').textContent"))


if __name__ == "__main__":
    unittest.main()
