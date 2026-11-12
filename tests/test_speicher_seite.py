"""Eigener Online-Speicher (Stufe R3a) in der Workbench am PC: Einstellungen › Speicher und Synchronisierung – Anbieter
wählen, Zertifikat-Feld nur beim eigenen Server, Warnung bei http://, nichts gespeichert, wenn der Server nicht antwortet.
Im echten Browser (Edge ohne Fenster). Mit AMW_FOTO=<Ordner> legt der Test ein Bild der Karte dort ab."""
import base64
import os
import unittest
from unittest import mock

from amw import abgleich
from tests import test_aktualisieren
from tests.test_aktualisieren import EDGE, warte_auf


@unittest.skipUnless(EDGE, "Edge nicht installiert")
class SpeicherKarte(test_aktualisieren.Seite):
    # Aufbau (Workbench + Edge) von dort, die Tests dort nicht noch einmal
    test_antwort_nimmt_die_frage_sofort_aus_der_liste = test_neue_frage_von_aussen_erscheint_ohne_klick = None
    test_ungespeicherte_eingabe_bleibt = None

    def setUp(self):
        super().setUp()
        umgebung = mock.patch.dict(os.environ, {"LOCALAPPDATA": self.ordner.name})
        umgebung.start()
        self.addCleanup(umgebung.stop)

    def test_anbieter_waehlen(self):
        self.tab.senden("Page.navigate", url=f"http://127.0.0.1:{self.port}/#einstellungen")
        warte_auf(self, "document.querySelector('#e-speicher-art')", 10)
        feld = "document.querySelector('#e-speicher-art').closest('.karte')"
        self.assertEqual(self.tab.js("[...document.querySelectorAll('#e-speicher-art option')].map(o => o.value)"), ["turso", "libsql"])
        ca_sichtbar = f"!{feld}.querySelectorAll('.feld')[3].hidden"
        self.assertFalse(self.tab.js(ca_sichtbar))                                     # Turso: kein Zertifikat-Feld
        self.tab.js("const s = document.querySelector('#e-speicher-art'); s.value = 'libsql'; s.dispatchEvent(new Event('change'))")
        self.assertTrue(self.tab.js(ca_sichtbar))
        self.assertIn("firma", self.tab.js(f"{feld}.querySelectorAll('.feld')[1].querySelector('input').placeholder"))
        self.tab.js(f"const u = {feld}.querySelectorAll('.feld')[1].querySelector('input'); u.value = 'http://127.0.0.1:9';"
                    " u.dispatchEvent(new Event('input'))")
        self.assertTrue(self.tab.js(f"!{feld}.querySelector('.bernstein-text').hidden"))   # Warnung bei http://
        self.tab.js(f"{feld}.querySelectorAll('.feld')[2].querySelector('input').value = 'abc';"
                    f" [...{feld}.querySelectorAll('button')].find(b => b.textContent === 'Speichern').click()")
        warte_auf(self, "[...document.querySelectorAll('.toast')].some(t => t.textContent.includes('nichts gespeichert'))", 20)
        self.assertFalse(os.path.exists(abgleich.zugang_pfad()))
        self.foto(feld)

    def foto(self, feld):
        ziel = os.environ.get("AMW_FOTO")
        if not ziel:
            return
        self.tab.senden("Emulation.setDeviceMetricsOverride", width=900, height=1400, deviceScaleFactor=1, mobile=False)
        self.tab.js(f"{feld}.scrollIntoView()")
        r = self.tab.js(f"(() => {{ const b = {feld}.getBoundingClientRect(); return {{x: b.x, y: b.y + scrollY, w: b.width, h: b.height}}; }})()")
        bild = self.tab.senden("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                               clip={"x": r["x"], "y": r["y"], "width": r["w"], "height": r["h"], "scale": 1})
        with open(os.path.join(ziel, "a1598-speicher-eigen.png"), "wb") as f:
            f.write(base64.b64decode(bild["data"]))


if __name__ == "__main__":
    unittest.main()
