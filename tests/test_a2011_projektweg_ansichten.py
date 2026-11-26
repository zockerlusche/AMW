"""A2011 (Kleinprobe A2007, D1481 v4): im Projektweg Reiter für Schritt 3 · Feinplanung (Feinplan · Gesamtplan) und Schritt 4 · Umsetzung
(Pakete · Reihenfolge · Zeitplan) – die bisherigen Ansichten bleiben der erste Reiter; Reihenfolge, Zeitplan und Gesamtplan aus den
vorhandenen Daten, Klick öffnet das Paket, PC und Handy, hell und dunkel."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import unittest

from amw import arbeitspaket, db, kern, planung
from tests.rundgang import OnlineRundgang, Rundgang

OFFEN = "document.querySelector('#inhalt .pjw-seite') && typeof pwMitReitern === 'function'"


def bestand(con, pid):
    kern.agent_neu(con, pid, "CC1")
    kern.agent_neu(con, pid, "CC2")
    jetzt = planung.bogen_neu(con, pid, "TL", "Speichern", ziel="Z", abnahme="Vorführung")
    planung.bogen_status(con, pid, "TL", jetzt, "aktiv")
    spaeter = planung.bogen_neu(con, pid, "TL", "Kasse", ziel="Z", abnahme="Bericht")
    nr = {}
    nr["laeuft"] = planung.schritt_setzen(con, pid, "TL", titel="Spielstand anlegen", bogen_id=jetzt, agent="CC1", groesse="S", art="mechanisch")
    nr["wartet"] = planung.schritt_setzen(con, pid, "TL", titel="Spielstand laden", bogen_id=jetzt, agent="CC2", groesse="S", art="mechanisch")
    nr["blockiert"] = planung.schritt_setzen(con, pid, "TL", titel="Spielstand löschen", bogen_id=jetzt, agent="CC1", groesse="S", art="mechanisch")
    nr["fertig"] = planung.schritt_setzen(con, pid, "TL", titel="Speicherplätze zählen", bogen_id=jetzt, groesse="S", art="mechanisch")
    nr["kasse"] = planung.schritt_setzen(con, pid, "TL", titel="Kasse öffnen", bogen_id=spaeter, groesse="S", art="mechanisch")
    with db.schreiben(con):
        con.execute("UPDATE aufgabe SET status = 'laeuft', begonnen_utc = ? WHERE id = ?", (db.jetzt(), nr["laeuft"]))
        con.execute("UPDATE aufgabe SET status = 'blockiert' WHERE id = ?", (nr["blockiert"],))
        con.execute("UPDATE aufgabe SET status = 'fertig', fertig_utc = ?, beleg = 'abc1234' WHERE id = ?", (db.jetzt(), nr["fertig"]))
    arbeitspaket.setzen(con, pid, "TL", nr["laeuft"], art="agent")
    return nr, {"jetzt": jetzt, "spaeter": spaeter}


def reiter(schritt, wahl):
    return (f"zustand.pwSicht = {schritt}; zustand.pwOffen = true; zustand.pwReiter = {{ {schritt}: {wahl!r} }};"
            " pwStand = null; void zeige('projektweg', true)")


class Seite(Rundgang):
    def daten(self):
        self.nr, self.m = bestand(self.con, self.pid)

    def oeffne(self, schritt, wahl, fertig):
        self.oeffnen("projektweg", OFFEN)
        self.tab.js(reiter(schritt, wahl))
        self.warten(fertig)

    def test_reiter_und_erster_reiter_wie_bisher(self):
        self.oeffne(3, "pakete", "document.querySelector('.pjw-seg [data-reiter=pakete].an')")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.pjw-seg button')].map(b => b.dataset.reiter)"), ["pakete", "reihenfolge", "zeitplan"])
        self.assertTrue(self.tab.js("!!document.querySelector('.pjw-ums')"))                     # die bisherige Umsetzung
        self.oeffne(2, "feinplan", "document.querySelector('.pjw-seg [data-reiter=feinplan].an')")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.pjw-seg button')].map(b => b.dataset.reiter)"), ["feinplan", "gesamtplan"])

    def test_reihenfolge(self):
        self.oeffne(3, "reihenfolge", "document.querySelector('.pjw-rf-zeile')")
        refs = self.tab.js("[...document.querySelectorAll('.pjw-rf-zeile')].map(z => z.dataset.ref)")
        self.assertEqual(refs[0], f"A{self.nr['laeuft']}")                                       # was läuft, steht oben
        self.assertEqual(set(refs), {f"A{self.nr[k]}" for k in ("laeuft", "wartet", "blockiert")})   # fertig und geplanter Meilenstein fehlen
        zeile = self.tab.js(f"document.querySelector('.pjw-rf-zeile[data-ref=A{self.nr['blockiert']}]').innerText")
        self.assertIn("blockiert", zeile)
        self.tab.js(f"document.querySelector('.pjw-rf-zeile[data-ref=A{self.nr['wartet']}]').click()")
        self.warten("[...document.querySelectorAll('.dialog')].some(d => d.textContent.includes('Spielstand laden'))")

    def test_zeitplan(self):
        self.oeffne(3, "zeitplan", "document.querySelector('.pjw-zp-zeile')")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.pjw-zp-zeile > b')].map(b => b.textContent).sort()"), ["CC1", "CC2"])
        self.assertIn("Spielstand löschen", self.tab.js("document.querySelector('.pjw-zp-ohne').innerText"))   # blockiert: ohne Zeit
        self.assertTrue(self.tab.js(f"!!document.querySelector('.pjw-zp-balken[data-ref=A{self.nr['laeuft']}].laeuft')"))

    def test_gesamtplan(self):
        self.oeffne(2, "gesamtplan", "document.querySelector('.pjw-gs-m')")
        texte = self.tab.js("[...document.querySelectorAll('.pjw-gs > .pjw-gs-m')].map(m => m.innerText.replace(/\\s+/g, ' '))")
        self.assertTrue(any("Speichern" in x and "in Arbeit" in x and "1 von 4" in x for x in texte), texte)
        self.assertTrue(any("Kasse" in x and "geplant" in x for x in texte), texte)
        self.tab.js("document.querySelector('.pjw-gs-m > summary').click()")
        self.warten("document.querySelector('.pjw-gs-m[open] .pjw-gs-paket')")

    def test_eigene_adressen(self):
        """Lead #34150: #reihenfolge, #zeitplan und #gesamtplan führen direkt auf den Reiter; im Menü leuchtet „Projektweg“."""
        for adresse, ziel in (("reihenfolge", ".pjw-rf-zeile"), ("zeitplan", ".pjw-zp-zeile"), ("gesamtplan", ".pjw-gs-m")):
            with self.subTest(adresse=adresse):
                self.oeffnen(adresse, f"zustand.sicht === 'projektweg' && document.querySelector('{ziel}')")
                self.assertEqual(self.tab.js("document.querySelector('.pjw-seg .an').dataset.reiter"), adresse)
                self.assertEqual(self.tab.js("[...document.querySelectorAll('nav a[data-sicht].an')].map(a => a.dataset.sicht)"), ["projektweg"])

    def test_bilder(self):
        for schritt, wahl, ort, bereit in ((3, "reihenfolge", "reihenfolge", ".pjw-rf-zeile"), (3, "zeitplan", "zeitplan", ".pjw-zp-zeile"),
                                           (2, "gesamtplan", "gesamtplan", ".pjw-gs-m")):
            self.ueberall("projektweg", f"a2011-{ort}", bereit=OFFEN, tun=reiter(schritt, wahl), danach=f"document.querySelector('{bereit}')")


class Online(OnlineRundgang):
    def daten(self):
        self.nr, self.m = bestand(self.con, self.pid)

    def test_online_reiter(self):
        self.oeffnen("projektweg", OFFEN)
        self.tab.js(reiter(3, "reihenfolge"))
        self.warten("document.querySelector('.pjw-rf-zeile')")
        self.tab.js(reiter(2, "gesamtplan"))
        self.warten("document.querySelector('.pjw-gs-m')")


if __name__ == "__main__":
    unittest.main()
