"""A1998 (D1430 Lücke 1): Online zeigt ein Projekt vor seinem ersten Abgleich den leeren Zustand „Noch kein Abgleich von diesem
Rechner.“ (EN „No sync from this computer yet.“) – nie die alten Ansichten ohne Projekt-Kennung oder Daten eines anderen
Projekts. Echtes PHP der Seite, echter Browser (Edge ohne Fenster). Mit AMW_FOTO=<Ordner> legt der Test ein Bild ab
(Handy, hell)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import base64
import json
import os
import unittest

from tests import rundgang

ALT = "ALTE-DATEN-AUS-PROJEKT-A"


@unittest.skipUnless(rundgang.EDGE, "Edge nicht installiert")
class KeinAbgleich(rundgang.OnlineRundgang):
    def server_starten(self):
        basis = super().server_starten()
        jetzt = "2026-11-23T10:00:00Z"
        alt = json.dumps({"titel": ALT, "zaehler": {"nachrichten": 99}})
        self.sp.ausfuehren([("INSERT INTO ansicht (weg, inhalt, pruef, stand_utc) VALUES (?, ?, 'x', ?)", [w, alt, jetzt])
                            for w in ("/api/start", "/api/aufgaben?sicht=offen", "/api/fragen")] + [
            ("INSERT INTO projekt (uid, name, farbe, rechner, gesehen_utc, fragen, agenten, halt) VALUES (?, 'B', NULL, 'anderer', ?, 0, 0, 0)",
             ["uid-neu-b", jetzt])])
        return basis

    def zu_b(self, sicht="start", sprache="de"):
        self.besuche = getattr(self, "besuche", 0) + 1
        self.tab.js(f"try {{ localStorage.setItem('amw-sprache', '{sprache}') }} catch (e) {{}}")
        self.tab.senden("Page.navigate", url=f"{self.basis}?projekt=uid-neu-b&r={self.besuche}#{sicht}")
        self.warten("document.readyState === 'complete' && typeof zeige === 'function'", 15)

    def sieht(self, text):
        try:
            self.warten(f"document.body.innerText.includes({json.dumps(text)})", 15)
        except AssertionError:
            self.fail(f"„{text}“ fehlt – Seite zeigt: {self.tab.js('document.body.innerText')[:600]!r}")

    def test_leerer_zustand_statt_fremder_daten(self):
        self.groesse("handy")
        self.zu_b("start")
        self.thema("hell")
        self.sieht("Noch kein Abgleich von diesem Rechner.")
        self.assertNotIn(ALT, self.tab.js("document.body.innerText"))
        # P552 (TH156 Regeln 1, 4, 6): ein Status an einem Ort – kein rotes „Dienst nicht erreichbar“ oben
        self.assertEqual(self.tab.js("document.querySelectorAll('#signale .punkt.rot').length"), 0)
        self.assertNotIn("Dienst nicht erreichbar", self.tab.js("document.body.innerText"))
        for g, t in (("handy", "hell"), ("handy", "dunkel"), ("pc", "hell")):
            self.groesse(g)
            self.thema(t)
            self.assertEqual(self.pruefen(f"kein-abgleich-start-{g}-{t}", g, t), [])
            self.assertEqual(self.tab.js("document.querySelectorAll('#signale .punkt.rot').length"), 0)
            if g == "handy":                                              # „Abmelden“ bleibt rechts oben (A1614)
                self.assertTrue(self.tab.js("(() => { const b = document.querySelector('#abmelden').getBoundingClientRect();"
                                            " return innerWidth - b.right < 40; })()"))
            self.foto(f"a1998-kein-abgleich-{g}-{t}.png")
        for sicht in ("aufgaben", "fragen"):
            self.zu_b(sicht)
            self.sieht("Noch kein Abgleich von diesem Rechner.")
            self.assertNotIn(ALT, self.tab.js("document.body.innerText"))

    def foto(self, name):
        ziel = (os.environ.get("AMW_FOTO") or "").strip()
        if ziel:
            os.makedirs(ziel, exist_ok=True)
            bild = self.tab.senden("Page.captureScreenshot", format="png")["data"]
            with open(os.path.join(ziel, name), "wb") as f:
                f.write(base64.b64decode(bild))

    def test_echter_ausfall_bleibt_rot(self):
        """Antwortet der Webhoster nicht mit „kein Abgleich“ (Netz, 5xx), bleibt das rote Signal – nur der leere Zustand ist ruhig."""
        self.zu_b("start")
        self.sieht("Noch kein Abgleich von diesem Rechner.")
        self.tab.js("window.fetch = () => Promise.reject(new TypeError('Failed to fetch')); kopfLaden()")
        self.warten("document.querySelectorAll('#signale .punkt.rot').length === 1")
        self.assertIn("Dienst nicht erreichbar", self.tab.js("document.querySelector('#signale').innerText"))

    def test_englisch(self):
        self.zu_b("start", sprache="en")
        self.tab.js("typeof sprache_setzen === 'function' && sprache_setzen('en')")
        self.zu_b("aufgaben", sprache="en")
        self.sieht("No sync from this computer yet.")
        self.assertNotIn(ALT, self.tab.js("document.body.innerText"))


if __name__ == "__main__":
    unittest.main()
