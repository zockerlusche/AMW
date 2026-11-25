"""Posteingang neu (A1889, Kleinprobe D1310, F5357 A): Nachrichten über alle Projekte dieses PCs – jede Zeile mit Projekt
(Farbmarke + Name) und Projekt-Chips als Filter; Reiter An dich · Mitlesen · Gesendet; An dich zeigt zuerst nur Offenes und
„n offen für dich“ über alle Projekte; rechts der Verlauf als Gespräch (gleicher Bezug, auch Agenten untereinander);
Gelesen hakt im richtigen Projekt ab; Mitlesen ebenfalls über alle Projekte. Fragen bleiben ein eigener Menüpunkt (B2699).
Bilder PC/Handy hell/dunkel über AMW_RUNDGANG_BILDER."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import unittest

from amw import db, kern
from tests.rundgang import Rundgang

E = kern.ENTWICKLER


class Daten:
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        with db.schreiben(self.con):
            self.q = db.einfuegen(self.con, "projekt", name="Zweitprojekt", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.q, "QTL", rolle="lead")
        kern.agent_neu(self.con, self.q, "QC1")
        self.aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Linien aufräumen", "CC1")
        auftrag = kern.posten(self.con, self.pid, E, "CC1", "auftrag", "Bitte Linien aufräumen", bezug=f"A{self.aid}")[0]
        kern.posten(self.con, self.pid, "CC1", "TL", "info", "Prüfbitte an TL gestellt", bezug=f"A{self.aid}")   # Agenten untereinander
        self.mache = kern.posten(self.con, self.pid, "CC1", E, "antwort", "Mache ich", antwort_auf=auftrag)[0]   # A2108: die Antwort auf deinen Auftrag zählt
        alt = kern.posten(self.con, self.pid, "CC1", E, "meldung", "Schon erledigte Meldung")[0]
        with db.schreiben(self.con):
            self.con.execute("UPDATE empfang SET status = 'erledigt', erledigt_utc = ? WHERE nachricht_id = ?", (db.jetzt(), alt))
        self.quer = kern.posten(self.con, self.q, "AMW", E, "meldung", "Meilenstein im Zweitprojekt abschließen?")[0]   # A2108: Meldung der AMW zählt
        kern.posten(self.con, self.q, "QTL", "QC1", "auftrag", "Zwischenstand bitte")


class Posteingang(Daten, Rundgang):
    def offen(self, nid):
        self.con.commit()
        return self.con.execute("SELECT status FROM empfang WHERE nachricht_id = ? AND agent = ?", (nid, E)).fetchone()[0]

    def zeile(self, text):
        return f"[...document.querySelectorAll('.nr-eintrag')].find(e => e.innerText.includes({text!r}))"

    def test_an_dich_ueber_alle_projekte(self):
        self.groesse("pc")
        self.oeffnen("nachrichten", "document.querySelectorAll('.nr-eintrag').length >= 2")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.nr-reiter button')].map(b => b.firstChild.textContent)").__getitem__(slice(0, 3)),
                         ["An dich", "Mitlesen", "Gesendet"])
        self.assertEqual(self.tab.js("document.querySelector('.nr-offen').textContent"), "2 offen für dich")   # P und Zweitprojekt
        liste = self.tab.js("document.querySelector('.nr-liste').innerText")
        for x in ("Mache ich", "Meilenstein im Zweitprojekt abschließen?"):
            self.assertIn(x, liste)
        self.assertNotIn("Schon erledigte Meldung", liste)                                       # Standard: nur Offenes
        self.assertNotIn("Erste Frage?", liste)                                                  # Fragen: eigener Menüpunkt (B2699)
        self.assertEqual(self.tab.js(f"{self.zeile('Zweitprojekt abschließen')}.querySelector('.nr-projekt').textContent.trim()"), "Zweitprojekt")
        self.assertEqual(self.tab.js(f"{self.zeile('Mache ich')}.querySelector('.nr-projekt').textContent.trim()"), "P")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.nr-pchip')].map(b => b.textContent.trim())"), ["Alle Projekte", "P", "Zweitprojekt"])
        self.tab.js("[...document.querySelectorAll('.nr-pchip')].find(b => b.textContent.trim() === 'Zweitprojekt').click()")
        self.warten("!document.querySelector('.nr-liste').innerText.includes('Mache ich')")
        self.assertIn("Zweitprojekt abschließen", self.tab.js("document.querySelector('.nr-liste').innerText"))
        self.tab.js("[...document.querySelectorAll('.nr-pchip')][0].click()")
        self.warten("document.querySelector('.nr-liste').innerText.includes('Mache ich')")
        self.tab.js("document.querySelector('.nr-nur-offen').click()")                          # nur offene aus: Erledigtes dazu
        self.warten("document.querySelector('.nr-liste').innerText.includes('Schon erledigte Meldung')")

    def test_verlauf_als_gespraech(self):
        self.groesse("pc")
        self.oeffnen("nachrichten", "document.querySelectorAll('.nr-eintrag').length >= 2")
        self.assertIn("3 im Verlauf", self.tab.js(f"{self.zeile('Mache ich')}.innerText"))
        self.tab.js(f"{self.zeile('Mache ich')}.click()")
        self.warten("document.querySelector('.nr-gespraech .nr-blase.diese')?.innerText.includes('Mache ich')")
        blasen = self.tab.js("[...document.querySelectorAll('.nr-gespraech .nr-blase')].map(b => b.innerText)")
        self.assertEqual(len(blasen), 3)
        self.assertIn("Bitte Linien aufräumen", blasen[0])                                     # Ältestes oben, von dir
        self.assertIn("dich → CC1", blasen[0])
        self.assertIn("CC1 → TL", blasen[1])                                                     # Agenten untereinander gehört dazu
        self.assertIn("CC1 → dich", blasen[2])
        self.assertTrue(self.tab.js("document.querySelector('.nr-gespraech .nr-blase').classList.contains('ich')"))
        self.warten("document.querySelector('.nr-offen').textContent === '1 offen für dich'")   # antippen = gelesen (A1837)
        self.assertEqual(self.offen(self.mache), "erledigt")
        self.assertIn("Mache ich", self.tab.js("document.querySelector('.nr-liste').innerText"))   # bleibt stehen, bis du gehst

    def test_gelesen_im_anderen_projekt(self):
        self.groesse("pc")
        self.oeffnen("nachrichten", "document.querySelectorAll('.nr-eintrag').length >= 2")
        self.tab.js(f"{self.zeile('Zweitprojekt abschließen')}.click()")                       # schicken(..., p) an das Zweitprojekt
        self.warten("document.querySelector('.nr-gespraech h3')?.textContent.includes('Zweitprojekt abschließen')")
        self.warten("document.querySelector('.nr-offen').textContent === '1 offen für dich'")
        self.assertEqual(self.offen(self.quer), "erledigt")
        self.assertEqual(self.offen(self.mache), "offen")                                        # das andere Projekt bleibt unberührt

    KNOPF = "[...document.querySelectorAll({wo!r} + ' button')].find(b => b.textContent.startsWith({text!r}))"

    def test_knopf_erledigt(self):                                                                # P308 (a): Knopf „Erledigt“ = amw erledigt
        self.groesse("pc")
        self.oeffnen("nachrichten", "document.querySelectorAll('.nr-eintrag').length >= 2")
        self.warten("document.querySelector('.nr-gespraech h3')?.textContent.includes('Zweitprojekt abschließen')")   # neueste automatisch gewählt
        self.assertEqual(self.offen(self.quer), "offen")                                         # gewählt ist noch nicht erledigt
        self.assertFalse(self.tab.js("[...document.querySelectorAll('button')].some(b => b.textContent.startsWith('Gelesen'))"))
        self.tab.js(self.KNOPF.format(wo=".nr-gespraech .aktionen", text="Erledigt") + ".click()")
        self.warten("document.querySelector('.nr-offen').textContent === '1 offen für dich'")
        self.assertEqual(self.offen(self.quer), "erledigt")
        self.assertEqual(self.offen(self.mache), "offen")
        self.assertEqual(self.tab.js(self.KNOPF.format(wo=".nr-sammel", text="Alle erledigt") + ".textContent"), "Alle erledigt (1)")
        self.tab.js(self.KNOPF.format(wo=".nr-sammel", text="Alle erledigt") + ".click()")
        self.warten("document.querySelector('.nr-offen').textContent === '0 offen für dich'")
        self.assertEqual(self.offen(self.mache), "erledigt")

    def test_knopf_erledigt_am_handy(self):
        self.groesse("handy")
        self.oeffnen("nachrichten", "document.querySelectorAll('.nr-eintrag').length >= 2")
        self.assertEqual(self.tab.js(self.KNOPF.format(wo=".nr-sammel", text="Alle erledigt") + ".textContent"), "Alle erledigt (2)")   # beide Projekte
        self.tab.js(self.KNOPF.format(wo=".nr-sammel", text="Alle erledigt") + ".click()")
        self.warten("!document.querySelector('.nr-sammel button')")
        self.assertEqual((self.offen(self.quer), self.offen(self.mache)), ("erledigt", "erledigt"))

    def test_mitlesen_ueber_alle_projekte(self):
        self.groesse("pc")
        self.oeffnen("teamchat", "document.querySelectorAll('.tc-eintrag').length >= 2")
        text = self.tab.js("document.querySelector('.tc-liste').innerText")
        for x in ("Prüfbitte an TL gestellt", "Zwischenstand bitte"):
            self.assertIn(x, text)
        self.assertNotIn("Mache ich", text)                                                      # an dich: nicht Mitlesen
        zeile = "[...document.querySelectorAll('.tc-eintrag')].find(e => e.innerText.includes('Zwischenstand'))"
        self.assertEqual(self.tab.js(f"{zeile}.querySelector('.nr-projekt').textContent.trim()"), "Zweitprojekt")
        self.tab.js("[...document.querySelectorAll('.nr-pchip')].find(b => b.textContent.trim() === 'P').click()")
        self.warten("!document.querySelector('.tc-liste').innerText.includes('Zwischenstand')")

    def test_rundgang(self):
        fehler = []
        for g in ("pc", "handy"):
            for t in ("hell", "dunkel"):
                fehler += self.besuchen("nachrichten", "posteingang", bereit="document.querySelector('.nr-eintrag')", g=g, t=t)
                if g == "pc":                                                                    # am PC mit offenem Verlauf
                    self.tab.js("document.querySelector('.nr-nur-offen').checked && document.querySelector('.nr-nur-offen').click()")   # Gelesenes aus der vorigen Runde zeigen
                    self.warten(f"{self.zeile('Mache ich')}")
                    self.tab.js(f"{self.zeile('Mache ich')}.click()")
                    self.warten("document.querySelector('.nr-gespraech .nr-blase.diese')?.innerText.includes('Mache ich')")
                    fehler += self.pruefen("posteingang-verlauf", g, t)
                else:                                                                            # am Handy: Liste, dann Gespräch
                    self.tippen(".nr-eintrag")
                    self.warten("document.querySelector('.nr-raster').classList.contains('detail')")
                    fehler += self.pruefen("posteingang-gespraech", g, t)
                fehler += self.besuchen("teamchat", "mitlesen", bereit="document.querySelectorAll('.tc-eintrag').length >= 2", g=g, t=t)
        self.assertEqual(fehler, [])


if __name__ == "__main__":
    unittest.main()
