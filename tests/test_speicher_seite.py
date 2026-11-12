"""Eigener Online-Speicher (Stufe R3a) in der Workbench am PC: Einstellungen › Speicher und Synchronisierung – Anbieter
wählen, Zertifikat-Feld nur beim eigenen Server, Warnung bei http://, nichts gespeichert, wenn der Server nicht antwortet.
Stufe R3b: Warnung an der Adresse der Online-Seite bei http://, Betriebsart „server“, Anmeldeseite über http.
Im echten Browser (Edge ohne Fenster). Mit AMW_FOTO=<Ordner> legt der Test ein Bild der Karte dort ab."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import base64
import os
import shutil
import socket
import subprocess
import time
import unittest
from unittest import mock

from amw import abgleich
from tests import test_aktualisieren
from tests.test_aktualisieren import EDGE, warte_auf

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHP = shutil.which("php")


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

    def test_seite_ueber_http_und_betriebsart(self):
        """R3b: Warnung an der Adresse der Seite bei http://, Betriebsart „server“ nennt den Weg, Anmeldeseite über http warnt."""
        self.tab.senden("Page.navigate", url=f"http://127.0.0.1:{self.port}/#einstellungen")
        warte_auf(self, "document.querySelector('#e-speicher-art')", 10)
        warnung = "[...document.querySelectorAll('.bernstein-text')].find(x => x.textContent.includes('Passwörter und Codes'))"
        self.assertTrue(self.tab.js(f"{warnung}.hidden"))
        for adresse, zu_sehen in (("http://192.168.1.10", True), ("https://amw.firma.lan", False)):
            self.tab.js(f"{{ const i = {warnung}.previousElementSibling; i.value = '{adresse}'; i.dispatchEvent(new Event('input')) }}")
            self.assertEqual(self.tab.js(f"!{warnung}.hidden"), zu_sehen, adresse)
        self.tab.js(f"{{ const i = {warnung}.previousElementSibling; i.value = 'http://192.168.1.10'; i.dispatchEvent(new Event('input')) }}")
        server = "document.querySelector('.ba-karte[data-art=server]')"
        self.assertIn("amw web paket", self.tab.js(f"{server}.innerText"))
        self.assertNotIn("später", self.tab.js(f"{server}.innerText"))
        self.foto(f"{server}.closest('.karte')", "a1598-betriebsart-server.png")
        self.foto(f"{warnung}.closest('.karte')", "a1598-seite-http.png")
        if not PHP:
            return
        online = os.path.join(self.ordner.name, "online.db")
        abgleich.SqliteSpeicher(online).ausfuehren([(s, []) for s in abgleich.SCHEMA])
        konfig = os.path.join(self.ordner.name, "amw-konfig.php")
        with open(konfig, "w", encoding="utf-8") as f:
            f.write(f"<?php return ['sqlite' => '{online.replace(os.sep, '/')}', 'benutzer' => 'chef', 'passwort_hash' => 'x', 'nur_https' => false];\n")
        with socket.socket() as s:                     # 127.0.0.2: auch dieser Rechner, aber nicht „lokal“ für die Seite
            s.bind(("127.0.0.2", 0))
            port = s.getsockname()[1]
        php = subprocess.Popen([PHP, "-d", "extension=pdo_sqlite", "-d", "extension=mbstring", "-d", f"session.save_path={self.ordner.name}",
                                "-S", f"127.0.0.2:{port}", "-t", os.path.join(WURZEL, "web")], env={**os.environ, "AMW_KONFIG": konfig},
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (php.terminate(), php.wait(10)))
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.2", port), 0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        self.tab.senden("Page.navigate", url=f"http://127.0.0.2:{port}/")
        warte_auf(self, "document.querySelector('#http-warnung') !== null", 10)
        self.assertIn("Unverschlüsselte Verbindung", self.tab.js("document.querySelector('#http-warnung').innerText"))
        self.foto("document.querySelector('form')", "a1598-anmeldung-http.png", breite=520)

    def foto(self, feld, name="a1598-speicher-eigen.png", breite=900):
        ziel = os.environ.get("AMW_FOTO")
        if not ziel:
            return
        self.tab.senden("Emulation.setDeviceMetricsOverride", width=breite, height=1400, deviceScaleFactor=1, mobile=False)
        self.tab.js(f"{feld}.scrollIntoView()")
        r = self.tab.js(f"(() => {{ const b = {feld}.getBoundingClientRect(); return {{x: b.x, y: b.y + scrollY, w: b.width, h: b.height}}; }})()")
        bild = self.tab.senden("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                               clip={"x": r["x"], "y": r["y"], "width": r["w"], "height": r["h"], "scale": 1})
        with open(os.path.join(ziel, name), "wb") as f:
            f.write(base64.b64decode(bild["data"]))


if __name__ == "__main__":
    unittest.main()
