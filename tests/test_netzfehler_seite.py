"""A2037 (D1515 v2 §2.3): Ein Lese-Abruf der Seite, der als Netzfehler scheitert (fetch wirft TypeError), wird einmal nach
kurzer Pause wiederholt – der Inhalt kommt. Ein zweiter Netzfehler zeigt den Fehler wie bisher; HTTP-Fehler und Schreiben
(POST) wiederholt die Seite nie. Echter Browser (Edge ohne Fenster) an der Workbench mit Test-Datenbank."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import unittest

from tests import rundgang

# fetch der Seite ersetzen: die ersten `n` Aufrufe, deren Adresse `teil` enthält, scheitern als Netzfehler; gezählt wird je Art
FALLE = """(n, teil) => {
  window.__echt = window.__echt || window.fetch;
  window.__zahl = {lesen: 0, schreiben: 0};
  let rest = n;
  window.fetch = (u, o) => {
    if (String(u).includes(teil)) {
      window.__zahl[(o && o.method === "POST") ? "schreiben" : "lesen"]++;
      if (rest-- > 0) return Promise.reject(new TypeError("Failed to fetch"));
    }
    return window.__echt(u, o);
  };
}"""


@unittest.skipUnless(rundgang.EDGE, "Edge nicht installiert")
class Netzfehler(rundgang.Rundgang):
    def falle(self, n, teil):
        self.tab.js(f"({FALLE})({n}, {teil!r})")

    def lauf(self, ausdruck):
        """Führt einen Abruf aus: {"ok": bool, "fehler": Text, "ms": Dauer, "zahl": Zähler}."""
        return self.tab.js(f"""(async () => {{ const t0 = performance.now(); let ok = false, fehler = null;
            try {{ await ({ausdruck}); ok = true; }} catch (e) {{ fehler = String(e && e.message || e); }}
            return {{ok, fehler, ms: performance.now() - t0, zahl: window.__zahl}}; }})()""")

    def test_ein_netzfehler_wird_einmal_wiederholt(self):
        self.oeffnen("start")
        self.falle(1, "probe=a2037")
        r = self.lauf("abrufen('/api/start?probe=a2037')")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["zahl"]["lesen"], 2)                          # erster scheitert, zweiter bringt den Inhalt
        self.assertGreaterEqual(r["ms"], 250)                            # nach kurzer Pause, nicht sofort

    def test_zweiter_netzfehler_zeigt_den_fehler_wie_bisher(self):
        self.oeffnen("start")
        self.falle(2, "probe=a2037")
        r = self.lauf("abrufen('/api/start?probe=a2037')")
        self.assertFalse(r["ok"])
        self.assertIn("Failed to fetch", r["fehler"])
        self.assertEqual(r["zahl"]["lesen"], 2)                          # genau eine Wiederholung, keine zweite

    def test_http_fehler_nie_wiederholt(self):
        self.oeffnen("start")
        self.falle(0, "/api/gibt-es-nicht")
        r = self.lauf("abrufen('/api/gibt-es-nicht')")
        self.assertFalse(r["ok"])
        self.assertEqual(r["zahl"]["lesen"], 1)                          # Antwort mit Status: kein zweiter Versuch

    def test_schreiben_nie_wiederholt(self):
        self.oeffnen("start")
        self.falle(1, "/api/halt")
        r = self.lauf("schicken('/api/halt', {})")
        self.assertFalse(r["ok"])
        self.assertIn("Failed to fetch", r["fehler"])
        self.assertEqual((r["zahl"]["schreiben"], r["zahl"]["lesen"]), (1, 0))

    def test_seite_zeigt_den_inhalt_nach_einem_netzfehler(self):
        """Der Fall aus L3238: der Wechsel auf eine Ansicht trifft einen Netzfehler – die Seite zeigt trotzdem den Inhalt."""
        self.oeffnen("start")
        self.falle(1, "/api/wissen")
        self.tab.js("location.hash = '#wissen'")
        self.warten("document.querySelector('#inhalt h1') && !document.querySelector('#inhalt').innerText.includes('Failed to fetch')"
                    " && window.__zahl.lesen >= 2")
        self.assertNotIn("Failed to fetch", self.tab.js("document.querySelector('#inhalt').innerText"))


if __name__ == "__main__":
    unittest.main()
