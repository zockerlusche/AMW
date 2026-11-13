"""Bedienbarkeits-Rundgang Teil 2 (A1614, CCamw2): Planung, Aufgaben (jeder Reiter, Aufgaben-Dialog), Verlauf,
Versionshinweise, Wissen (jeder Reiter), Dokumente (Dokument-Dialog) – je PC und Handy, hell und dunkel, am PC und online
(Gerüst: tests/rundgang.py)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import unittest

from amw import db, kern, wissen
from tests.rundgang import OnlineRundgang, Rundgang
from tests.test_rundgang import Daten as Grunddaten

ARBEIT = ("listen", "offen", "geparkt", "pool", "erledigt")
WISSEN = ("themen", "beschluesse", "regeln", "wortlaut", "notizen")


class Daten(Grunddaten):
    """Dazu: eine fertige Aufgabe, ein Beschluss mit Wortlaut und Thema, eine Version – damit jede Seite Inhalt hat."""

    def daten(self):
        super().daten()
        self.aid = self.con.execute("SELECT max(id) FROM aufgabe WHERE projekt_id = ?", (self.pid,)).fetchone()[0]
        fertig = kern.aufgabe_neu(self.con, self.pid, "TL", "Knöpfe am Handy groß genug machen", "CC2")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc1234', begonnen_utc = ?, fertig_utc = ? WHERE id = ?",
                             (db.jetzt(), db.jetzt(), fertig))
        wissen.beschluss_neu(self.con, self.pid, "TL", "Knöpfe", "Knöpfe am Handy sind mindestens 32 px hoch", "Marcel",
                             thema="Oberfläche", neues_thema=True, wortlaut_neu=("Knöpfe am Handy groß genug", "chat", db.jetzt()))
        try:
            wissen.release_version(self.con, self.pid, "Entwickler", "1.0.0", "Erste Version", text="Erste Version für alle.")
        except kern.AmwFehler:
            pass                                         # ohne offene Merge-Zeilen: Versionshinweise bleiben leer


def reiter(sicht, wert, fn):
    """JS: Reiter einer Sicht setzen und neu zeichnen."""
    return f"{sicht} = {wert!r}; {fn}()"


class Seiten(Daten, Rundgang):
    """Jede Seite meines Teils in beiden Größen und Themen."""

    def test_planung(self):
        self.ueberall("planung", bereit="document.querySelector('#rechner-heute')")

    def test_aufgaben_jeder_reiter(self):
        for r in ARBEIT:
            with self.subTest(reiter=r):
                self.ueberall("arbeit", f"aufgaben-{r}", bereit="document.querySelector('#inhalt .reiter')",
                              tun=reiter("zustand.arbeit.sicht", r, "sichtArbeit"),
                              danach=f"document.querySelector('#inhalt .reiter button.an') && zustand.arbeit.sicht === {r!r}"
                                     " && document.querySelector('#inhalt .board, #inhalt .liste, #inhalt .leer, #inhalt .karte, #inhalt table')")

    def test_aufgaben_dialog(self):
        self.ueberall("arbeit", "aufgabe-dialog", bereit="document.querySelector('#inhalt .reiter')", tun=f"aufgabeDialog({self.aid})",
                      danach="document.querySelector('.dialog-hg .dialog-zu')")

    def test_verlauf(self):
        self.ueberall("verlauf", bereit="document.querySelector('#inhalt .vl-filter')")

    def test_versionshinweise(self):
        self.ueberall("releases", "versionshinweise", bereit="document.querySelector('#inhalt .vh-version, #inhalt .leer, #inhalt .reiter')")

    def test_wissen_jeder_reiter(self):
        for r in WISSEN:
            with self.subTest(reiter=r):
                self.ueberall("wissen", f"wissen-{r}", bereit="document.querySelector('#inhalt .reiter')",
                              tun=reiter("zustand.wissenReiter", r, "sichtWissen"),
                              danach=f"zustand.wissenReiter === {r!r} && document.querySelector('#inhalt .reiter button.an')")

    def test_thema_dialog(self):
        tid = self.con.execute("SELECT max(id) FROM thema WHERE projekt_id = ?", (self.pid,)).fetchone()[0]
        self.assertTrue(tid)
        self.ueberall("wissen", "thema-dialog", bereit="document.querySelector('#inhalt .reiter')", tun=f"themaDialog({tid})",
                      danach="document.querySelector('.dialog-hg .dialog-zu')")

    def test_dokumente_und_dialog(self):
        self.ueberall("dokumente", bereit="document.querySelector('.dk-karte')")
        for art in ("bild", "mockup"):
            with self.subTest(art=art):
                self.ueberall("dokumente", f"dokument-dialog-{art}", bereit="document.querySelector('.dk-karte')",
                              tun=f"dokumentDialog({self.dok[art]})", danach="document.querySelector('.dialog-hg .dialog-zu')")


class Postfach(Daten, Rundgang):
    """A1629 Stufe 1: Nachrichten ohne Fragen (nur Hinweis), Art je Zeile, mehrere auf einmal erledigen; Team-Chat; Seite Fragen
    mit eigenem Kopf – je PC/Handy × hell/dunkel geprüft, dazu die Bedienung echt geklickt."""

    def daten(self):
        super().daten()
        kern.posten(self.con, self.pid, "CC2", "Entwickler", "info", "Zweite Meldung an dich")
        kern.posten(self.con, self.pid, "AMW", "Entwickler", "meldung", "Laufwerk C: wird knapp")
        kern.posten(self.con, self.pid, "TL", "CC1,CC2", "auftrag", "Bitte die Hilfe ergänzen", text="Mit Bildern.")

    def test_seiten(self):
        self.ueberall("nachrichten", "postfach", bereit="document.querySelector('.nr-eintrag')")
        self.ueberall("teamchat", bereit="document.querySelector('.tc-eintrag')")
        self.ueberall("fragen", "fragen-eigener-kopf", bereit="document.querySelector('#inhalt h1')")

    def test_bedienung(self):
        self.groesse("pc")
        self.tab.js("try { localStorage.clear() } catch (e) {}")
        self.oeffnen("nachrichten", "document.querySelector('.nr-eintrag')")
        txt = self.tab.js("document.querySelector('#inhalt').innerText")
        self.assertIn("Frage an dich offen", txt)                                                 # Hinweis statt Fragen im Postfach
        self.assertFalse(self.tab.js("[...document.querySelectorAll('.nr-reiter button')].some(b => /Fragen/.test(b.textContent))"))
        self.assertTrue(self.tab.js("!!document.querySelector('.nr-eintrag.system .nr-sym')"))   # ⚙ Meldung der Workbench
        offen = self.tab.js("document.querySelectorAll('.nr-wahl').length")
        self.assertGreaterEqual(offen, 2)
        self.tippen(".nr-sammel input[type=checkbox]")                                           # alle offenen markieren
        self.warten(f"(document.querySelector('.nr-sammel .knopf')?.textContent || '').includes('({offen})')")
        self.tippen(".nr-sammel .knopf")                                                         # Erledigt (n)
        self.warten("!document.querySelector('.nr-wahl')")
        self.oeffnen("teamchat", "document.querySelector('.tc-eintrag')")
        self.assertIn("Bitte die Hilfe ergänzen", self.tab.js("document.querySelector('.tc-liste').innerText"))
        self.oeffnen("fragen", "document.querySelector('#inhalt h1')")
        self.assertEqual(self.tab.js("document.querySelector('#inhalt h1').textContent"), "Fragen")


class Kante(Daten, Rundgang):
    """Am Handy enden wischbare Untermenüs im Seitenkopf nicht stumm mitten im Wort: ein Verlauf an der Kante zeigt, dass
    es dort weitergeht (Klassen weiter-r / weiter-l), am PC gibt es keinen."""
    ZEILE = "document.querySelector('.seitenkopf .reiter-zeile')"

    def test_verlauf_an_der_kante(self):
        self.groesse("handy")
        self.oeffnen("arbeit", "document.querySelector('.seitenkopf .reiter-zeile')")
        z = self.ZEILE
        self.tab.js(f"{z}.scrollLeft = 0; {z}.dispatchEvent(new Event('scroll'))")
        self.warten(f"{z}.classList.contains('weiter-r') && !{z}.classList.contains('weiter-l')")
        self.tab.js(f"{z}.scrollLeft = 30; {z}.dispatchEvent(new Event('scroll'))")
        self.warten(f"{z}.classList.contains('weiter-r') && {z}.classList.contains('weiter-l')")
        self.tab.js(f"{z}.scrollLeft = {z}.scrollWidth; {z}.dispatchEvent(new Event('scroll'))")
        self.warten(f"!{z}.classList.contains('weiter-r') && {z}.classList.contains('weiter-l')")
        self.assertIn("linear-gradient", self.tab.js(f"getComputedStyle({z}).maskImage || getComputedStyle({z}).webkitMaskImage"))
        self.groesse("pc")
        self.oeffnen("arbeit", "document.querySelector('.seitenkopf .reiter')")
        self.assertFalse(self.tab.js(f"!!document.querySelector('.seitenkopf .weiter-r, .seitenkopf .weiter-l')"))


class Online(Daten, OnlineRundgang):
    """Die Online-Seite (echtes PHP, angemeldet wie ein Mensch): dieselben Seiten und Dialoge meines Teils."""

    def test_seiten(self):
        self.ueberall("planung", "online-planung", bereit="document.querySelector('#rechner-heute')")
        self.ueberall("arbeit", "online-aufgaben", bereit="document.querySelector('#inhalt .reiter')",
                      tun=reiter("zustand.arbeit.sicht", "offen", "sichtArbeit"),
                      danach="zustand.arbeit.sicht === 'offen' && document.querySelector('#inhalt .board, #inhalt .leer')")
        self.ueberall("verlauf", "online-verlauf", bereit="document.querySelector('#inhalt .vl-filter')")
        self.ueberall("releases", "online-versionshinweise", bereit="document.querySelector('#inhalt .vh-version, #inhalt .leer, #inhalt .reiter')")
        self.ueberall("wissen", "online-wissen", bereit="document.querySelector('#inhalt .reiter')")
        self.ueberall("dokumente", "online-dokumente", bereit="document.querySelector('.dk-karte')")

    def test_dialoge(self):
        self.ueberall("arbeit", "online-aufgabe-dialog", bereit="document.querySelector('#inhalt .reiter')", tun=f"aufgabeDialog({self.aid})",
                      danach="document.querySelector('.dialog-hg .dialog-zu')")
        self.ueberall("dokumente", "online-dokument-dialog", bereit="document.querySelector('.dk-karte')",
                      tun=f"dokumentDialog({self.dok['bild']})", danach="document.querySelector('.dialog-hg .dialog-zu')")


if __name__ == "__main__":
    unittest.main()
