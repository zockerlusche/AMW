"""Bedienbarkeits-Durchgang (A1292): Dokumente nach Art/Zeitraum/Reihenfolge, einheitliche Dialoge, ehrliche Zahlen.

- Schnittstelle: Wissen zählt alle Einträge (nicht nur die gezeigten), Betrieb nennt die Speicher-Grenze des Projekts.
- Seite (Edge ohne Fenster, nur wenn Edge da ist): Art-Chips mit Zahl filtern, Titel-Reihenfolge, Zeitraum; Enter im
  einzeiligen Feld schickt den Dialog ab; ein ✕ je Dialog; Sprungleiste der Einstellungen ohne doppelte Marke.
"""
import json
import os
import subprocess
import time
import unittest
import urllib.request

from amw import db, dokumente, kern, wissen, workbench
from tests.test_aktualisieren import EDGE, Grund, _Tab, freier_port


class Zahlen(Grund):
    def test_wissen_zaehlt_alle_und_betrieb_nennt_die_grenze(self):
        for i in range(63):
            wissen.beschluss_neu(self.con, self.pid, "TL", f"S{i}", f"Regel {i}", "Entwickler")
        d = workbench.daten_wissen(self.con, self.pid, {})
        self.assertEqual(len(d["beschluesse"]), 60)                      # gezeigt: die neuesten 60
        self.assertEqual(d["anzahl"]["beschluesse"], 63)                 # gezählt: alle
        self.assertEqual(workbench.daten_wissen(self.con, self.pid, {"q": ["S1"]})["anzahl"]["beschluesse"], 11)
        self.assertEqual(d["anzahl"]["themen"], 0)
        with db.schreiben(self.con):
            self.con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?", (json.dumps({"speicher_grenze_gb": 6}), self.pid))
        self.assertEqual(workbench.daten_betrieb(self.con, self.pid)["speicher"]["grenze"], 6.0)   # früher fest „8 GB“


@unittest.skipUnless(EDGE, "Edge nicht installiert")
class Seite(Grund):
    def setUp(self):
        super().setUp()
        for name, art, titel in (("b.png", "bild", "Zebra"), ("a.png", "bild", "Affe"), ("r.md", "bericht", "Mitte")):
            pfad = os.path.join(self.ordner.name, name)
            with open(pfad, "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n" if name.endswith(".png") else b"# Bericht")
            dokumente.ablegen(self.con, self.pid, "TL", pfad, titel, art)
            time.sleep(1.05)                                             # verschiedene Zeiten: „neueste zuerst“ eindeutig
        with db.schreiben(self.con):                                     # Affe ist alt: fällt aus „letzte 7 Tage“
            self.con.execute("UPDATE dokument_version SET zeit_utc = '2020-01-01T00:00:00Z' WHERE dokument_id ="
                             " (SELECT id FROM dokument WHERE titel = 'Affe')")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.port = freier_port()
        self.srv = workbench.starten(self.port)
        dt = freier_port()
        self.edge = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--no-first-run", f"--remote-debugging-port={dt}",
                                      f"--user-data-dir={os.path.join(self.ordner.name, 'edge')}", "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ziel = None
        for _ in range(150):
            try:
                ziel = next(z for z in json.load(urllib.request.urlopen(f"http://127.0.0.1:{dt}/json", timeout=2))
                            if z["type"] == "page")
                break
            except Exception:
                time.sleep(0.2)
        self.assertIsNotNone(ziel, "Edge meldet sich nicht")
        self.tab = _Tab(ziel["webSocketDebuggerUrl"])

    def tearDown(self):
        try:
            self.tab.s.close()
        except Exception:
            pass
        self.edge.terminate()
        try:
            self.edge.wait(10)
        except subprocess.TimeoutExpired:
            self.edge.kill()
        self.srv.shutdown()
        self.srv.server_close()
        super().tearDown()

    def oeffnen(self, sicht, bedingung):
        self.tab.senden("Page.navigate", url=f"http://127.0.0.1:{self.port}/#{sicht}")
        self.warten(bedingung)

    def warten(self, bedingung, sekunden=8):
        ende = time.time() + sekunden
        while time.time() < ende:
            try:
                if self.tab.js(f"!!({bedingung})"):
                    return
            except AssertionError:
                pass
            time.sleep(0.15)
        self.fail(f"nach {sekunden} s nicht erfüllt: {bedingung}")

    def titel(self):
        return self.tab.js("[...document.querySelectorAll('.dk-karte b')].map(b => b.textContent)")

    def test_dokumente_nach_art_reihenfolge_und_zeitraum(self):
        self.oeffnen("dokumente", "document.querySelectorAll('.dk-karte').length === 3")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.dk-arten .vl-chip')].map(c => c.textContent)"),
                         ["Alle (3)", "Bild (2)", "Bericht (1)"])
        self.assertEqual(self.titel(), ["Mitte", "Zebra", "Affe"])                 # neueste zuerst (Affe ist alt)
        self.tab.js("[...document.querySelectorAll('.dk-arten .vl-chip')].find(c => c.textContent.startsWith('Bild')).click()")
        self.warten("document.querySelectorAll('.dk-karte').length === 2")
        self.tab.js("{ const s = [...document.querySelectorAll('.dk-filter select')].find(x => [...x.options].some(o => o.value === 'titel'));"
                    "s.value = 'titel'; s.dispatchEvent(new Event('change')) }")
        self.warten("document.querySelector('.dk-karte b')?.textContent === 'Affe'")
        self.assertEqual(self.titel(), ["Affe", "Zebra"])
        self.tab.js("{ const s = [...document.querySelectorAll('.dk-filter select')].find(x => [...x.options].some(o => o.value === '7'));"
                    "s.value = '7'; s.dispatchEvent(new Event('change')) }")
        self.warten("document.querySelectorAll('.dk-karte').length === 1")
        self.assertEqual(self.titel(), ["Zebra"])
        self.assertEqual(self.tab.js("document.querySelector('.kopf .kopf-aktion')?.textContent"), "Hochladen")   # oben, immer gleich
        self.oeffnen("planung", "document.querySelector('.kopf .kopf-aktion')?.textContent === 'Neuer Bogen'")   # nicht der Knopf der alten Sicht

    def test_dialog_enter_schickt_ab_und_hat_ein_kreuz(self):
        self.oeffnen("start", "typeof nachrichtDialog === 'function' && document.querySelector('.kachel')")
        self.tab.js("nachrichtDialog('CC1')")
        self.warten("document.querySelector('.dialog-hg input')")
        self.assertEqual(self.tab.js("document.querySelectorAll('.dialog-hg .dialog-zu').length"), 1)
        self.tab.js("const i = document.querySelector('.dialog-hg input'); i.value = 'per Enter'; i.focus();"
                    "i.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))")
        self.warten("!document.querySelector('.dialog-hg')")
        self.assertEqual(self.con.execute("SELECT kurz FROM nachricht ORDER BY id DESC LIMIT 1").fetchone()[0], "per Enter")
        self.tab.js("agentDialog('CC1')")
        self.warten("document.querySelector('.agent-dialog')")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.dialog-hg button')].filter(b => /[×✕]/.test(b.textContent)).length"), 1)

    def test_neues_projekt_aus_der_projekt_auswahl(self):
        from unittest import mock
        from amw import assistent
        repo = os.path.join(self.ordner.name, "laden")
        os.makedirs(repo)
        self.oeffnen("start", "document.querySelector('#projektwahl .pw')")
        self.tab.js("document.querySelector('#projektwahl .pw').click()")
        self.warten("[...document.querySelectorAll('.pw-liste button')].some(b => b.textContent.includes('Neues Projekt'))")
        self.tab.js("[...document.querySelectorAll('.pw-liste button')].find(b => b.textContent.includes('Neues Projekt')).click()")
        self.warten("document.querySelector('.dialog-hg .einst input')")
        felder = json.dumps(["Laden", repo, "TL", "CC1"])
        self.tab.js(f"{{ const w = {felder}; const i = document.querySelectorAll('.dialog-hg .einst input');"
                    " w.forEach((x, n) => { i[n].value = x; }); }")
        with mock.patch.object(assistent, "STARTSKRIPT", os.path.join(self.ordner.name, "agenten-start.ps1")):
            self.tab.js("document.querySelector('.dialog-hg .knopf.haupt').click()")
            self.warten("document.querySelector('.np-schritte')")
        self.assertTrue(self.tab.js("[...document.querySelectorAll('.np-schritte li')].some(l => l.textContent.includes('Projekt „Laden“ angelegt'))"))
        pid = db.projekt_id(self.con, "Laden")
        self.assertEqual(sorted(r[0] for r in self.con.execute("SELECT kennung FROM agent WHERE projekt_id = ?", (pid,))), ["CC1", "TL"])
        self.tab.js("document.querySelector('.dialog-hg .knopf.haupt').click()")            # „Zum Projekt“
        self.warten("document.querySelector('.pw-name')?.textContent === 'Laden'")

    def test_handy_unten_fuenf_eintraege_und_mehr(self):
        self.tab.senden("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=1, mobile=True)
        self.oeffnen("arbeit", "document.querySelector('#mehr') && document.querySelector('.reiter')")
        sichtbar = "[...document.querySelectorAll('nav a')].filter(a => a.offsetParent !== null).map(a => a.dataset.sicht || a.id)"
        self.assertEqual(self.tab.js(sichtbar), ["start", "fragen", "planung", "arbeit", "mehr"])
        breite = self.tab.js("Math.min(...[...document.querySelectorAll('nav a')].filter(a => a.offsetParent !== null).map(a => a.getBoundingClientRect().width))")
        self.assertGreaterEqual(breite, 48)                                          # Daumen-Ziel
        r = self.tab.js("(() => { const x = document.querySelector('.reiter .rechts select, .reiter .rechts input').getBoundingClientRect();"
                        " return [x.left, x.right, innerWidth]; })()")
        self.assertTrue(r[0] >= 0 and r[1] <= r[2], r)                               # Filter der Aufgaben sichtbar, nicht weggescrollt
        self.tab.js("document.getElementById('mehr').click()")
        self.warten("document.querySelectorAll('.mehr-liste button').length === 6")
        self.tab.js("[...document.querySelectorAll('.mehr-liste button')].find(b => b.textContent.includes('Verlauf')).click()")
        self.warten("zustand.sicht === 'verlauf' && document.getElementById('mehr').classList.contains('an')")

    def test_sprungleiste_der_einstellungen_ohne_doppelte_marke(self):
        self.oeffnen("einstellungen", "document.querySelector('.sprung a')")
        texte = self.tab.js("[...document.querySelectorAll('.sprung a')].map(a => a.textContent)")
        self.assertIn("Dieser PC", texte)
        self.assertFalse([x for x in texte if "dieser PC" in x], texte)


if __name__ == "__main__":
    unittest.main()
