"""A2117 (Marcel 25.11.: „zweimal anklicken“): ein Klick auf Abnehmen wirkt beim ersten Mal – auch wenn die Workbench zwischendurch neu
gestartet ist und wenn die Seite gerade still neu zeichnet; ein Doppelklick gibt genau ein Ereignis; bei einem Fehler steht ein Satz ohne
Technik da und der Knopf geht wieder. PC und Handy."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import time
import unittest
from unittest import mock

from amw import grobplan, kern, planer, workbench
from tests.rundgang import Rundgang
from tests.test_projektweg_seite import demo

KNOPF = "[...document.querySelectorAll('.pjw-ansicht > .pjw-kopf button')].find(b => /abnehmen/.test(b.textContent))"
ZULETZT = "document.querySelector('.pjw-ansicht .pjw-a-zuletzt')?.textContent.includes('Zuletzt abgenommen')"


class Klick(Rundgang):
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        for ziel in (grobplan, planer):
            p = mock.patch.object(ziel, "STARTER", lambda *a, **k: 4711)
            p.start()
            self.addCleanup(p.stop)
        demo(self.con, self.pid, "abschluss")

    def neu_starten(self):
        """Der Dienst startet neu: dieselbe Adresse, ein neues Zeichen."""
        self.srv.shutdown()
        self.srv.server_close()
        self.srv = workbench.starten(self.port)
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def seite(self, g, t="dunkel"):
        self.groesse(g)
        self.oeffnen("projektweg", "document.querySelector('.pjw-schritt[data-schritt=abschluss]')")
        self.thema(t)                                                                    # die Bilder heißen, wie sie aussehen
        self.tab.js("zustand.pwSicht = 4; zustand.pwOffen = true; zeige('projektweg', true)")
        self.warten(KNOPF)

    def ereignisse(self):
        self.con.commit()
        return [tuple(r) for r in self.con.execute("SELECT art, von FROM plan_ereignis WHERE art = 'bogen_status' AND text LIKE '%fertig%'")]

    def fertig(self):
        self.con.commit()
        return self.con.execute("SELECT status FROM bogen WHERE titel = 'Welt sichtbar'").fetchone()[0]

    def test_klick_nach_neustart_am_pc(self):
        self._neustart("pc", "hell")

    def test_klick_nach_neustart_am_pc_dunkel(self):
        self._neustart("pc", "dunkel")

    def test_klick_nach_neustart_am_handy(self):
        self._neustart("handy", "hell")

    def test_klick_nach_neustart_am_handy_dunkel(self):
        self._neustart("handy", "dunkel")

    def _neustart(self, g, t):
        self.seite(g, t)
        self.neu_starten()
        self.tab.js(KNOPF + ".click()")
        self.warten(ZULETZT)
        self.assertEqual(self.fertig(), "fertig")
        self.assertEqual(len(self.ereignisse()), 1)
        self.assertTrue(self.tab.js("!!document.getElementById('neu-laden')"))          # die Seite ist alt: die Leiste steht noch da
        self.assertEqual(self.pruefen("a2117-neustart", g, t), [])

    def test_agent_anlegen_und_speichern_nach_neustart(self):
        """Marcel 25.11.: Einstellungen › Agenten – Anlegen wirkte erst beim zweiten Mal."""
        self.groesse("pc")
        self.oeffnen("einstellungen", "document.querySelector('.ae-neu button')")
        self.neu_starten()
        self.tab.js("document.querySelector('.ae-neu input').value = 'CC7'; document.querySelector('.ae-neu button').click()")
        self.warten("document.querySelector('.ae-form[data-k=CC7]')")
        self.con.commit()
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM agent WHERE kennung = 'CC7'").fetchone()[0], 1)
        self.neu_starten()
        self.tab.js("document.querySelectorAll('.toast').forEach(x => x.remove()); const z = [...document.querySelectorAll('.ae-form textarea')][0]; z.value = 'Seiten'; document.querySelector('.ae-form .ae-knoepfe button').click()")
        self.warten("[...document.querySelectorAll('.toast')].some(x => /espeichert/.test(x.textContent))")
        self.con.commit()
        self.assertEqual(self.con.execute("SELECT zustaendig FROM agent WHERE kennung = 'CC7'").fetchone()[0], "Seiten")

    def test_doppelklick_gibt_ein_ereignis(self):
        self.seite("pc")
        self.tab.js(f"const b = {KNOPF}; b.click(); b.click(); b.click()")
        self.warten(ZULETZT)
        self.assertEqual(len(self.ereignisse()), 1)

    def test_klick_auf_den_neu_gezeichneten_knopf_gibt_kein_zweites(self):
        """Zeichnet die Seite mitten in der Anfrage neu, ist der neue Knopf an – der zweite Klick schickt trotzdem nichts."""
        self.seite("pc")
        self.zaehlen()
        self.tab.js(f"const b = {KNOPF}; b.click(); b.disabled = false; b.click()")
        self.warten(ZULETZT)
        self.assertEqual(self.tab.js("window.__post"), 1)
        self.assertEqual(len(self.ereignisse()), 1)

    def zaehlen(self, gestoert="false"):
        """Zählt, was geschickt wird; `gestoert`: das Holen des neuen Zeichens scheitert."""
        self.tab.js("window.__post = 0; window.__fetch = window.fetch; window.fetch = (u, o) => { if (o && o.method === 'POST') window.__post++;"
                    f" return {gestoert} && u === '/' ? Promise.reject(new TypeError('x')) : window.__fetch(u, o) }}")

    def test_fehler_satz_ohne_technik_und_knopf_wieder_da(self):
        self.seite("pc", "hell")
        self.tab.js("window.__fetch = window.fetch; window.fetch = (u, o) => o && o.method === 'POST' ? Promise.reject(new TypeError('Failed to fetch')) : window.__fetch(u, o)")
        self.tab.js(KNOPF + ".click()")
        self.warten("document.querySelector('.toast')")
        text = self.tab.js("document.querySelector('.toast').textContent")
        self.assertIn("Keine Verbindung", text)
        self.assertNotIn("fetch", text)
        self.assertEqual(self.pruefen("a2117-fehler", "pc", "hell"), [])
        self.assertFalse(self.tab.js(KNOPF + ".disabled"))
        self.assertEqual(self.fertig(), "aktiv")
        self.assertEqual(self.ereignisse(), [])
        self.tab.js("window.fetch = window.__fetch")
        self.tab.js(KNOPF + ".click()")                                                  # der zweite Versuch geht
        self.warten(ZULETZT)

    def test_neustart_ohne_frisches_zeichen_wie_bisher(self):
        self.seite("pc")
        self.neu_starten()
        self.zaehlen("true")
        self.tab.js(KNOPF + ".click()")
        self.warten("document.getElementById('neu-laden')")
        self.warten(f"!{KNOPF}.disabled")
        self.assertEqual(self.tab.js("window.__post"), 1)                                # ohne frisches Zeichen schickt sie nicht noch einmal
        self.assertEqual(self.fertig(), "aktiv")
        self.assertFalse(self.tab.js(KNOPF + ".disabled"))

    def test_nicht_zeichnen_waehrend_gedrueckt(self):
        """Zwischen Drücken und Loslassen ersetzt ein stilles Neuzeichnen den Knopf nicht: der Klick kommt an."""
        self.seite("pc")
        pos = self.tab.js(f"(() => {{ const r = {KNOPF}.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }})()")
        self.tab.senden("Input.dispatchMouseEvent", type="mousePressed", x=pos[0], y=pos[1], button="left", clickCount=1)
        self.tab.js("window.__zeige = 0; const alt = zeige; zeige = (...a) => { window.__zeige++; return alt(...a); };"
                    "window.__vorher = " + KNOPF + "; pwStand = null; frischZeichnen(true)")     # als hätte sich etwas geändert
        self.bleibt_stehen()
        self.assertEqual(self.tab.js("window.__zeige"), 0)                               # auch nicht begonnen: andere Seiten leeren sich zuerst
        self.tab.senden("Input.dispatchMouseEvent", type="mouseReleased", x=pos[0], y=pos[1], button="left", clickCount=1)
        self.assertFalse(self.tab.js("haeltGedrueckt()"))                                # losgelassen: sofort wieder frei, nicht erst nach 3 s
        self.warten(ZULETZT)
        self.assertEqual(len(self.ereignisse()), 1)

    def test_antwort_kommt_waehrend_gedrueckt(self):
        """Das Neuzeichnen lädt schon, dann wird gedrückt: die Antwort zeichnet erst nach dem Loslassen."""
        self.seite("pc")
        pos = self.tab.js(f"(() => {{ const r = {KNOPF}.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }})()")
        self.tab.js("window.__fetch = window.fetch; window.fetch = (u, o) => String(u).includes('/api/projektweg')"
                    " ? new Promise(r => setTimeout(r, 500)).then(() => window.__fetch(u, o)) : window.__fetch(u, o)")
        self.tab.js("window.__vorher = " + KNOPF + "; pwStand = null; frischZeichnen(true)")
        self.tab.senden("Input.dispatchMouseEvent", type="mousePressed", x=pos[0], y=pos[1], button="left", clickCount=1)
        self.bleibt_stehen()
        self.tab.senden("Input.dispatchMouseEvent", type="mouseReleased", x=pos[0], y=pos[1], button="left", clickCount=1)
        self.warten(ZULETZT)
        self.assertEqual(len(self.ereignisse()), 1)

    def bleibt_stehen(self):
        time.sleep(1.0)
        self.assertTrue(self.tab.js(f"window.__vorher === {KNOPF}"), "der Knopf wurde ersetzt, solange er gedrückt war")


if __name__ == "__main__":
    unittest.main()
