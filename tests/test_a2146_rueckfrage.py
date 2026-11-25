"""A2146 (Rest aus A2117): Rückfragen beim Freigeben und Abnehmen sind ein Dialog der Seite statt confirm/prompt – Esc, ✕ und Klick
daneben brechen ab, die Haupthandlung hat den Fokus, am Handy volle Breite. Ein Doppelklick bei Themen-Ja und bei einer Antwort auf
eine Frage schickt einmal. Kommt beim Nachschicken ein Zeichen aus einer neueren Version, bleibt „Neu laden“ stehen. PC und Handy."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import glob
import os
import re
import unittest
from unittest import mock

from amw import db, kern, themen
from tests import test_a2117_klick as k17
from tests import test_urteil_seite as urt
from tests import test_veroeffentlichung_seite as ver
from tests.rundgang import Rundgang

SKRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "amw", "workbench", "skript")
# die Rückfragen auf Freigabe- und Abnahme-Wegen (Textschlüssel)
FRAGEN = ("ab_frage", "ua_frage", "ua_zurueck_frage", "pjw_wartet_frage", "pjw_trotzdem_frage", "pm_start_frage", "th2_tor_frage")
ZAEHLEN = ("window.__post = []; window.__fetch = window.fetch; window.fetch = (u, o) => { if (o && o.method === 'POST') window.__post.push(String(u));"
           " return window.__fetch(u, o); }")
OFFEN = "document.querySelectorAll('.rueckfrage-hg').length"


class Quelle(unittest.TestCase):
    def test_kein_confirm_und_kein_prompt_auf_freigabe_wegen(self):
        gefunden = {k: 0 for k in FRAGEN}
        for datei in glob.glob(os.path.join(SKRIPT, "*.js")):
            with open(datei, encoding="utf-8") as f:
                for nr, zeile in enumerate(f, 1):
                    for k in FRAGEN:
                        if f'"{k}"' in zeile:
                            self.assertFalse(re.search(r"\b(confirm|prompt)\(", zeile), f"{os.path.basename(datei)}:{nr} {k}")
                            gefunden[k] += "rueckfrage(" in zeile
        self.assertTrue(all(gefunden.values()), gefunden)


def posts(test, teil):
    return [u for u in test.tab.js("window.__post") if teil in u]


class Abnahme(Rundgang):
    """„Abnehmen“ eines fertigen Meilensteins unter „Für dich“: die Rückfrage als Dialog."""
    daten = ver.Abnahme.daten
    ZEILE = ver.Abnahme.ZEILE
    KNOPF = ZEILE + ".querySelector('button')"

    def auf(self, g="pc"):
        self.groesse(g)
        self.oeffnen("start", self.ZEILE)
        self.tab.js(ZAEHLEN)

    def test_esc_kreuz_und_daneben_brechen_ab_ja_schickt_einmal(self):
        self.auf()
        for abbrechen in ("window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))",
                          "document.querySelector('.rueckfrage-hg .dialog-zu').click()",
                          "document.querySelector('.rueckfrage-hg').click()",
                          "document.querySelector('.rueckfrage-hg .knopf.still').click()"):
            with self.subTest(abbrechen=abbrechen):
                self.tab.js(self.KNOPF + ".click()")
                self.warten("document.querySelector('.rueckfrage-hg .dialog-zu')")
                self.assertIn("Danach veröffentlicht die AMW", self.tab.js("document.querySelector('.rueckfrage-text').textContent"))
                self.assertTrue(self.tab.js("document.activeElement === document.querySelector('.rueckfrage .knopf.haupt')"))   # Fokus: die Handlung
                self.assertEqual(self.tab.js("document.querySelector('.rueckfrage .knopf.haupt').textContent"), "Abnehmen")
                self.tab.js(abbrechen)
                self.warten("!document.querySelector('.rueckfrage-hg')")
                self.assertEqual(posts(self, "abnehmen"), [])
                self.assertFalse(self.tab.js(self.KNOPF + ".disabled"))
        self.tab.js(f"const b = {self.KNOPF}; b.click(); b.click()")                       # Doppelklick: eine Rückfrage
        self.assertEqual(self.tab.js(OFFEN), 1)
        self.rueckfrage(True)
        self.warten("window.__post.length")
        self.assertEqual(len(posts(self, "/api/bogen/abnehmen")), 1)

    def test_handy_volle_breite_und_bilder(self):
        for g in ("pc", "handy"):
            for t in ("hell", "dunkel"):
                self.auf(g)
                self.thema(t)
                self.tab.js(self.KNOPF + ".click()")
                self.warten("document.querySelector('.rueckfrage .knopf.haupt')")
                if g == "handy":
                    self.assertGreaterEqual(self.tab.js("document.querySelector('.rueckfrage').getBoundingClientRect().width"),
                                            self.tab.js("innerWidth") - 20)
                self.assertEqual(self.pruefen("a2146-rueckfrage", g, t), [], f"{g} {t}")
                self.rueckfrage(False)


class Zurueck(Rundgang):
    """„Zurück“ bei einer Aufgabe, die an einem Urteil hängt: der Grund im Dialog statt prompt."""
    aid: int
    daten = urt.UrteilSeite.daten
    zeile = urt.UrteilSeite.zeile

    def knopf(self, text):
        return f"[...{self.zeile()}.querySelectorAll('button')].find(b => b.textContent === {text!r})"

    def test_grund_im_dialog_leer_geht_nicht_enter_schickt(self):
        self.oeffnen("start", self.zeile())
        self.tab.js(ZAEHLEN)
        self.tab.js(self.knopf("Zurück") + ".click()")
        self.warten("document.querySelector('.rueckfrage input')")
        self.assertTrue(self.tab.js("document.activeElement === document.querySelector('.rueckfrage input')"))
        self.assertTrue(self.tab.js("document.querySelector('.rueckfrage .knopf.haupt').disabled"))          # ohne Grund nicht
        self.tab.js("const f = document.querySelector('.rueckfrage input'); f.value = 'Die Quellen fehlen'; f.dispatchEvent(new Event('input'));"
                    " f.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))")
        self.warten("!document.querySelector('.rueckfrage-hg') && window.__post.length")
        self.assertEqual(len(posts(self, "/api/aufgabe/abnehmen")), 1)
        self.con.commit()
        self.assertNotEqual(self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (self.aid,)).fetchone()[0], "fertig")

    def test_ja_doppelklick_schickt_einmal(self):
        self.oeffnen("start", self.zeile())
        self.tab.js(ZAEHLEN)
        self.tab.js(f"const b = {self.knopf('Ja')}; b.click(); b.click()")
        self.assertEqual(self.tab.js(OFFEN), 1)
        self.rueckfrage(True)
        self.warten("window.__post.length")
        self.assertEqual(len(posts(self, "/api/aufgabe/abnehmen")), 1)
        self.con.commit()
        self.assertEqual(self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (self.aid,)).fetchone()[0], "fertig")


class Einmal(Rundgang):
    """Themen-Ja und Antwort auf eine Frage: ein Doppelklick schickt einmal."""

    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        self.tid = themen.neu(self.con, self.pid, "TL", "Marktlage", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", self.tid, "Wer baut so etwas schon?")
        self.fid = kern.frage_neu(self.con, self.pid, "CC1", "entwickler", "Welche Farbe?", [("A", "blau"), ("B", "grün")], "A", "weil",
                                  pruefen=False)
        with db.schreiben(self.con):
            self.con.execute("UPDATE frage SET an = 'entwickler' WHERE id = ?", (self.fid,))

    def test_themen_ja_doppelklick(self):
        self.oeffnen("themen", "document.querySelector('.th-liste .th-zeile')")
        self.tab.js(f"zustand.themaOffen = {self.tid}; zeige('themen', true)")
        self.warten("document.querySelector('.th-knoepfe button[data-h=freigeben]')")
        self.tab.js(ZAEHLEN)
        self.tab.js("const b = document.querySelector('.th-knoepfe button[data-h=freigeben]'); b.click(); b.click()")
        if self.tab.js(OFFEN):                                                                    # schließt es den Schritt Konzept: eine Rückfrage
            self.assertEqual(self.tab.js(OFFEN), 1)
            self.rueckfrage(True)
        self.warten("window.__post.length")
        self.warten(f"document.querySelector('.th-zeile[data-th=\"{self.tid}\"] .th-status.frei')")
        self.assertEqual(len(posts(self, "/api/thema/freigeben")), 1)

    def test_antwort_doppelklick(self):
        self.oeffnen("fragen", "document.querySelector('.karte.frage .optionen button')")
        self.tab.js(ZAEHLEN)
        self.tab.js("const b = document.querySelector('.karte.frage .optionen button'); b.click(); b.click()")
        self.warten("window.__post.length")
        self.warten(f"!document.querySelector('.karte.frage:not(.weg)')")
        self.assertEqual(len(posts(self, f"/api/frage/{self.fid}/antwort")), 1)

    def test_antwort_bei_fehler_satz_und_knopf_wieder_da(self):
        self.oeffnen("fragen", "document.querySelector('.karte.frage .optionen button')")
        self.tab.js("window.__fetch = window.fetch; window.fetch = (u, o) => o && o.method === 'POST' ? Promise.reject(new TypeError('Failed to fetch')) : window.__fetch(u, o)")
        self.tab.js("document.querySelector('.karte.frage .optionen button').click()")
        self.warten("document.querySelector('.toast')")
        self.assertNotIn("fetch", self.tab.js("document.querySelector('.toast').textContent"))
        self.assertFalse(self.tab.js("document.querySelector('.karte.frage .optionen button').disabled"))


class Version(Rundgang):
    """Beim Nachschicken kommt das neue Zeichen von einem Dienst mit neuerer Version: die Leiste „Neu laden“ bleibt stehen."""
    daten = k17.Klick.daten
    neu_starten = k17.Klick.neu_starten
    seite = k17.Klick.seite

    def test_neuere_version_leiste_bleibt(self):
        self.seite("pc", "hell")
        p = mock.patch("amw.__version__", "9.9.9")
        p.start()
        self.addCleanup(p.stop)
        self.neu_starten()
        self.tab.js(k17.KNOPF + ".click()")
        self.warten(k17.ZULETZT)
        self.assertTrue(self.tab.js("!!document.getElementById('neu-laden')"))
        self.tab.js("kopfAktualisieren()")                                                      # der Takt holt den Kopf neu
        self.stabil("document.getElementById('neu-laden')", ruhe=1.5)


if __name__ == "__main__":
    unittest.main()
