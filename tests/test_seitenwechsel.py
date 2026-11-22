"""Seitenwechsel während des Ladens (A1907, Befund L2882): Was eine Seite vor einem Wechsel angefragt hat und erst danach
ankommt, zeichnet nicht mehr über die gewählte Seite. Die Startseite antwortet hier künstlich langsam (/api/start 1,5 s);
wer währenddessen wechselt – gleich beim ersten Laden oder später –, behält die gewählte Seite. Die Kopfzeile kommt trotzdem.
PC und Handy."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import time
import unittest

from amw import kern, themen
from tests.rundgang import Rundgang

LANGSAM_MS = 1500
# vor jeder Seite: /api/start antwortet langsam, wenn die Adresse „langsam“ enthält oder window.__langsam gesetzt ist; mit
# „nurerst“ nur der erste Abruf (das erste Laden), spätere sind schnell; window.__langsamWeg: ein beliebiger Weg
LANGSAM = ("(() => { const f = window.fetch; window.fetch = (u, ...r) => ((/\\/api\\/start/.test(String(u)) &&"
           " (window.__langsam || location.search.includes('langsam')"
           "  || (location.search.includes('nurerst') && !window.__erst && (window.__erst = true))))"
           " || (window.__langsamWeg && String(u).includes(window.__langsamWeg)))"
           f" ? new Promise(ok => setTimeout(ok, {LANGSAM_MS})).then(() => f(u, ...r)) : f(u, ...r); }})()")
# der Takt mitten im ersten Laden: 300 ms nach dem ersten (langsamen) /api/start zeichnet er still „start“ – sicher, bevor
# das erste Laden fertig ist, auch wenn der Rechner ausgelastet ist (vom Test aus gerufen kam er unter Last zu spät, L2942)
TAKT = ("(() => { const f = window.fetch; window.fetch = (u, ...r) => { if (location.search.includes('takt') && !window.__taktGeplant"
        " && String(u).includes('/api/start')) { window.__taktGeplant = true;"
        " setTimeout(() => { window.__takt = String(zustand.sicht); void zeige('start', true); }, 300); } return f(u, ...r); }; })()")


class Seitenwechsel(Rundgang):
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        kern.posten(self.con, self.pid, "CC1", kern.ENTWICKLER, "info", "Hallo aus dem Test")

    def setUp(self):
        super().setUp()
        self.tab.senden("Page.addScriptToEvaluateOnNewDocument", source=LANGSAM)

    def ueberschrift(self):
        return self.tab.js("document.querySelector('#inhalt h1')?.textContent")

    def bleibt(self, h1, liste):
        time.sleep(LANGSAM_MS / 1000 + 1)                                                       # die Startseite ist längst da
        self.assertEqual(self.ueberschrift(), h1)
        self.assertTrue(self.tab.js(f"!!document.querySelector({liste!r})"))
        self.assertEqual(self.tab.js("location.hash"), "#" + self.tab.js("zustand.sicht"))

    def test_wechsel_beim_ersten_laden(self):
        for g in ("pc", "handy"):
            with self.subTest(g=g):
                self.groesse(g)
                self.tab.senden("Page.navigate", url=f"{self.basis}?langsam=1&g={g}#start")
                self.warten("document.readyState === 'complete' && typeof zeige === 'function'")
                self.tab.js("zeige('themen')")                                                 # Startseite lädt noch
                self.warten("document.querySelector('.th-liste .th-zeile')")
                self.bleibt("Themen", ".th-liste .th-zeile")
                self.assertEqual(self.tab.js("zustand.sicht"), "themen")
                self.warten("!!zustand.start && document.querySelector('#version').textContent.startsWith('v')")   # Kopfzeile kam trotzdem

    def test_takt_beim_ersten_laden_haelt_die_seite_nicht_auf(self):
        """Der Takt zeichnet still „start“, solange das erste Laden noch läuft (L2908: Dokumente kamen nie) – die Seite aus
        der Adresse kommt trotzdem."""
        self.tab.senden("Page.addScriptToEvaluateOnNewDocument", source=TAKT)
        for g in ("pc", "handy"):
            with self.subTest(g=g):
                self.groesse(g)
                self.tab.senden("Page.navigate", url=f"{self.basis}?nurerst=1&takt={g}#themen")
                self.warten("document.readyState === 'complete' && typeof zeige === 'function' && window.__takt !== undefined")
                self.assertNotEqual(self.tab.js("window.__takt"), "themen")   # der Takt kam, bevor das erste Laden die Themen zeigte
                self.warten("document.querySelector('.th-liste .th-zeile')", 10)
                self.bleibt("Themen", ".th-liste .th-zeile")

    def test_wechsel_waehrend_die_startseite_laedt(self):
        for g in ("pc", "handy"):
            with self.subTest(g=g):
                self.groesse(g)
                self.oeffnen("start", "document.querySelector('#inhalt h1')?.textContent === 'Übersicht'")
                self.tab.js("window.__langsam = true; zeige('start'); zeige('nachrichten')")
                self.warten("document.querySelector('.nr-eintrag')")
                self.bleibt("Nachrichten", ".nr-eintrag")
                self.tab.js("window.__langsam = false")

    def test_reiter_wechsel_waehrend_der_vorige_laedt(self):
        """Arbeit: „Listen“ lädt langsam, sofort „Eingang“ (Pool) – das Listen-Ergebnis hängt sich nicht an (A1903-Verdacht)."""
        for g in ("pc", "handy"):
            with self.subTest(g=g):
                self.groesse(g)
                self.oeffnen("arbeit", "document.querySelector('#inhalt .reiter')")
                self.tab.js("window.__langsamWeg = '/api/listen'; zustand.arbeit.sicht = 'listen'; sichtArbeit();"
                            " zustand.arbeit.sicht = 'pool'; sichtArbeit()")
                self.warten("document.querySelector('#inhalt .liste, #inhalt .leer')")
                time.sleep(LANGSAM_MS / 1000 + 1)
                self.assertFalse(self.tab.js("!!document.querySelector('#inhalt .board.listen')"))
                self.assertEqual(self.tab.js("zustand.arbeit.sicht"), "pool")
                self.tab.js("window.__langsamWeg = null")

    def test_dialog_kommt_trotz_neuzeichnen(self):
        """Dialoge holen ohne Lade-Nummer: zeichnet die Seite still neu, während ein Dialog lädt, öffnet er trotzdem."""
        self.groesse("pc")
        self.oeffnen("themen", "document.querySelector('.th-liste .th-zeile')")
        tid = self.con.execute("SELECT id FROM thema ORDER BY id LIMIT 1").fetchone()[0]
        self.tab.js(f"window.__langsamWeg = '/api/thema?id='; themaDialog({tid}); zeige('themen', true)")
        self.warten("document.querySelector('.dialog-hg .dialog-zu')")
        self.tab.js("window.__langsamWeg = null")

    def test_stilles_neuzeichnen_bleibt(self):
        """Das stille Neuzeichnen derselben Seite (Takt, nach einer Aktion) ist kein Wechsel: es kommt an."""
        self.groesse("pc")
        self.oeffnen("themen", "document.querySelector('.th-liste .th-zeile')")
        themen.neu(self.con, self.pid, "TL", "Zweites Thema", pfleger="CC1")
        self.tab.js("zeige('themen', true)")
        self.warten("document.querySelector('.th-liste').innerText.includes('Zweites Thema')")


if __name__ == "__main__":
    unittest.main()
