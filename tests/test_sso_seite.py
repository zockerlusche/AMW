"""Firmen-Anmeldung (Stufe R2) in der Workbench am PC: Einstellungen › Benutzer der Online-Seite › Firmen-Anmeldung und die
E-Mail je Benutzer – im echten Browser (Edge ohne Fenster) gegen einen Online-Speicher als SQLite-Datei.
Mit AMW_FOTO=<Ordner> legt der Test ein Bild des Abschnitts dort ab (für die Prüfbitte)."""
import base64
import os
import unittest

from amw import abgleich, benutzer, kern, workbench
from tests import test_aktualisieren
from tests.test_aktualisieren import EDGE, warte_auf


@unittest.skipUnless(EDGE, "Edge nicht installiert")
class FirmenanmeldungAmPc(test_aktualisieren.Seite):
    # Aufbau (Workbench + Edge) von dort, die Tests dort nicht noch einmal
    test_antwort_nimmt_die_frage_sofort_aus_der_liste = test_neue_frage_von_aussen_erscheint_ohne_klick = None
    test_ungespeicherte_eingabe_bleibt = None

    def setUp(self):
        super().setUp()
        self.sp = abgleich.SqliteSpeicher(os.path.join(self.ordner.name, "online.db"))
        self.sp.ausfuehren([(s, []) for s in abgleich.SCHEMA])
        alt_sp, alt_adr = abgleich.speicher_aus_zugang, workbench._seiten_adresse
        abgleich.speicher_aus_zugang = lambda *a, **k: self.sp
        workbench._seiten_adresse = lambda: "https://amw.example.com"
        self.addCleanup(setattr, abgleich, "speicher_aus_zugang", alt_sp)
        self.addCleanup(setattr, workbench, "_seiten_adresse", alt_adr)
        benutzer.neu(self.con, kern.ENTWICKLER, "marie", "bearbeiter", email="marie@firma.example", projekte=[self.pid])

    def oeffnen(self):
        self.tab.senden("Page.navigate", url=f"http://127.0.0.1:{self.port}/#einstellungen")
        warte_auf(self, "document.querySelector('#e-sso #sso-aussteller')", 10)

    def test_einstellen_und_email(self):
        self.oeffnen()
        text = self.tab.js("document.querySelector('#e-sso').innerText")
        self.assertIn("https://amw.example.com/sso.php", text)                          # Umleitungs-URI für den Anbieter
        self.assertIn("noch nicht eingetragen", text)                                    # Geheimnis fehlt beim Webhoster
        self.assertTrue(self.tab.js("document.querySelector('#e-sso a').href.endsWith('/sso.php?einrichten')"))
        self.tab.js("""(() => { const s = (id, v) => { const x = document.getElementById(id); x.value = v; };
            s('sso-aussteller', 'https://login.microsoftonline.com/1111-2222/v2.0'); s('sso-client', 'abc-123');
            document.getElementById('sso-an').checked = true; document.getElementById('sso-speichern').click(); })()""")
        warte_auf(self, "document.querySelector('.toast') !== null", 8)
        d = abgleich.sso_einstellungen(self.sp)
        self.assertEqual((d["an"], d["aussteller"], d["client_id"]), (True, "https://login.microsoftonline.com/1111-2222/v2.0", "abc-123"))
        self.tab.js("document.getElementById('sso-aussteller').value = 'https://login.microsoftonline.com/common/v2.0';"
                    " document.getElementById('sso-speichern').click()")
        warte_auf(self, "[...document.querySelectorAll('.toast')].some(t => t.textContent.includes('Mandanten-ID'))", 8)
        self.assertEqual(abgleich.sso_einstellungen(self.sp)["aussteller"], "https://login.microsoftonline.com/1111-2222/v2.0")
        # E-Mail je Benutzer: steht im Feld und lässt sich ändern
        self.assertEqual(self.tab.js("document.querySelector('[data-name=marie] .bn-email').value"), "marie@firma.example")
        self.tab.js("document.querySelector('[data-name=marie] .bn-email').value = 'marie.neu@firma.example';"
                    " [...document.querySelectorAll('[data-name=marie] button')].find(b => b.textContent === 'Speichern').click()")
        warte_auf(self, "document.querySelector('[data-name=marie] .bn-email')?.value === 'marie.neu@firma.example'", 8)
        for _ in range(40):
            if benutzer.finden(self.con, "marie")["email"] == "marie.neu@firma.example":
                break
            self.tab.js("new Promise(r => setTimeout(r, 100))")
        self.assertEqual(benutzer.finden(self.con, "marie")["email"], "marie.neu@firma.example")
        self.assertFalse(self.tab.js("/null|undefined/.test(document.querySelector('#e-benutzer').innerText)"))
        self.foto()

    def test_englisch(self):
        self.tab.senden("Page.navigate", url=f"http://127.0.0.1:{self.port}/#einstellungen")
        warte_auf(self, "typeof sprache_setzen === 'function'", 10)
        self.tab.js("sprache_setzen('en')")
        self.oeffnen()
        warte_auf(self, "document.querySelector('#e-sso').innerText.includes('Company sign-in')", 8)
        self.assertIn("Redirect URI", self.tab.js("document.querySelector('#e-sso').innerText"))

    def foto(self):
        ziel = os.environ.get("AMW_FOTO")
        if not ziel:
            return
        self.tab.senden("Emulation.setDeviceMetricsOverride", width=900, height=1400, deviceScaleFactor=1, mobile=False)
        self.tab.js("document.querySelector('#e-benutzer').scrollIntoView()")
        r = self.tab.js("(() => { const b = document.querySelector('#e-benutzer').getBoundingClientRect();"
                        " return {x: b.x, y: b.y + scrollY, w: b.width, h: b.height}; })()")
        bild = self.tab.senden("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                               clip={"x": r["x"], "y": r["y"], "width": r["w"], "height": r["h"], "scale": 1})
        with open(os.path.join(ziel, "a1593-einstellungen-sso.png"), "wb") as f:
            f.write(base64.b64decode(bild["data"]))


if __name__ == "__main__":
    unittest.main()
