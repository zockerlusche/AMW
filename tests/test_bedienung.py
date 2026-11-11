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
from tests.test_aktualisieren import EDGE, Grund, Wiederholt, _Tab, edge_beenden, freier_port, warte_auf


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
class Seite(Wiederholt, Grund):
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
        edge_beenden(self.edge)
        self.srv.shutdown()
        self.srv.server_close()
        super().tearDown()

    def oeffnen(self, sicht, bedingung):
        self.tab.senden("Page.navigate", url=f"http://127.0.0.1:{self.port}/#{sicht}")
        self.warten(bedingung)

    def warten(self, bedingung, sekunden=8):
        warte_auf(self, bedingung, sekunden)

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
        self.oeffnen("start", "typeof nachrichtDialog === 'function' && document.querySelector('#team [data-k]')")
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
        self.tab.js(f"{{ const w = {felder}; const i = document.querySelectorAll('.dialog-hg .einst input:not([type=checkbox])');"
                    " w.forEach((x, n) => { i[n].value = x; }); }")
        with mock.patch.object(assistent, "STARTSKRIPT", os.path.join(self.ordner.name, "agenten-start.bat")):
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

    def test_leitstand_und_aktionsmenue(self):
        self.oeffnen("start", "document.querySelector('#leitstand') && document.querySelector('#team .mehr-knopf')")
        # Team: als Baum (du → Lead → Agenten; Vorgabe am breiten Schirm), umschaltbar auf die Liste – die Wahl bleibt
        self.tab.js("[...document.querySelectorAll('.tm-schalter button')][0].click()")
        self.warten("document.querySelector('.tm-baum') && document.querySelectorAll('.tm-linien path').length")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.tm-baum [data-k]')].map(k => k.dataset.k)"), ["*du", "TL", "CC1"])
        self.assertTrue(self.tab.js("document.querySelectorAll('.tm-linien path').length >= 3"))                 # Äste gezeichnet
        self.tab.js("[...document.querySelectorAll('.tm-schalter button')][1].click()")
        self.warten("document.querySelector('.tm-liste') && !document.querySelector('.tm-baum')")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.tm-liste .tm-z[data-k]')].map(k => k.dataset.k)"), ["TL", "CC1"])
        self.tab.js("zeige('start', true)")
        self.warten("document.querySelector('.tm-liste')")
        self.assertEqual(self.tab.js("document.querySelectorAll('#leitstand > div').length"), 5)       # Arbeit, Bildschirm, Sitzungen, Wächter, Rechner
        rechner = self.tab.js("document.querySelector('#ls-rechner').innerText")
        self.assertIn("Frei", rechner)                                                                 # kein Lauf angemeldet
        self.assertIn("gemeinsamen Warteschlange", rechner)
        self.assertNotIn("Aus diesem Projekt", rechner)                                                # nichts Eigenes: der Satz entfällt
        self.assertFalse(self.tab.js("document.querySelector('header').innerText.includes('null')"))   # leere Hinweise sind keine Texte
        self.assertFalse(self.tab.js("!!document.querySelector('#halt-knopf')"))                       # Anhalten steht im Leitstand
        self.assertTrue(self.tab.js("[...document.querySelectorAll('#leitstand button')].some(b => b.textContent === 'Alle anhalten')"))
        self.tab.js("document.querySelector('#team .mehr-knopf').click()")
        self.warten("document.querySelector('.menue')")
        texte = self.tab.js("[...document.querySelectorAll('.menue button')].map(b => b.textContent)")
        self.assertEqual(texte[0], "Nachricht schreiben")
        self.assertTrue(any(x.startswith("Anhalten (nur diesen)") for x in texte), texte)
        self.tab.js("document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
        self.warten("!document.querySelector('.menue')")

    def test_agenten_einstellungen_in_vier_bloecken(self):
        """Zahnrad › Agenten: eine Ansicht je Agent; die Arbeitsweise blendet Sitzung und Überwachung ein oder aus; ein Speichern."""
        sichtbar = "[...document.querySelectorAll('.ae-block')].filter(b => !b.hidden).map(b => b.querySelector('h4').textContent)"
        weise = "(() => { const s = document.querySelector('.ae-block select'); s.value = '%s'; s.dispatchEvent(new Event('change')); })()"
        self.oeffnen("einstellungen", "document.querySelector('#agenten-einstellungen .ae-form')")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.ae-wahl > button .tm-name')].map(b => b.textContent)"), ["TL", "CC1"])
        self.tab.js("[...document.querySelectorAll('.ae-wahl > button')].find(b => b.textContent.includes('CC1')).click()")
        self.warten("document.querySelector('.ae-form').dataset.k === 'CC1'")
        self.assertEqual(self.tab.js(sichtbar), ["Wer", "Auftrag", "Sitzung", "Überwachung"])        # Terminal: alles
        self.tab.js(weise % "chat")
        self.assertEqual(self.tab.js(sichtbar), ["Wer", "Auftrag"])                                  # Chat: weder Sitzung noch Überwachung
        self.tab.js(weise % "desktop")
        self.assertEqual(self.tab.js(sichtbar), ["Wer", "Auftrag", "Überwachung"])                   # Desktop-App: die AMW startet nicht
        self.assertFalse(self.tab.js("document.querySelector('#agenten-einstellungen').innerText.includes('null')"))
        self.tab.js("(() => { const f = document.querySelector('.ae-form'); f.querySelector('input[list]').value = 'Grafik';"
                    " f.querySelectorAll('textarea')[0].value = 'Karten-Look'; f.querySelectorAll('textarea')[1].value = 'Spiellogik';"
                    " f.querySelector('.ae-knoepfe button').click(); })()")
        lesen = lambda: tuple(self.con.execute("SELECT rolle, fachgebiet, arbeitsweise, zustaendig, fasst_nicht_an FROM agent WHERE kennung = 'CC1'").fetchone())
        ende = time.time() + 30
        while time.time() < ende and lesen()[1] != "Grafik":
            time.sleep(0.2)
        self.assertEqual(lesen(), (None, "Grafik", "desktop", "Karten-Look", "Spiellogik"))
        self.warten("document.querySelector('.ae-form') && document.querySelector('.ae-form').dataset.k === 'CC1'"      # die Wahl bleibt nach dem Speichern
                    " && document.querySelector('.ae-wahl > button.an .tm-fach')?.textContent === 'Grafik'")

    def test_grund_regelwerk_im_assistenten_und_in_wissen(self):
        """Neues Projekt: Schritt „Regelwerk“ mit dem Grund-Regelwerk als Vorgabe (Regeln abhaken, Takt-Regel für Chat-Leads);
        Wissen › Regeln zeigt die Grundregeln als eigene Gruppe mit Nummer der Vorlage, „angepasst“ und dem Warum."""
        from amw import regelwerk
        self.oeffnen("start", "typeof projektNeuDialog === 'function' && document.querySelector('#team')")
        self.tab.js("projektNeuDialog()")
        self.warten("document.querySelector('.np-regelwerk summary') && document.querySelectorAll('.np-rw-regel').length === 22")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('#np-regeln option')].map(o => o.value)"), ["grund", "kopie:P", ""])
        self.assertEqual(self.tab.js("document.querySelector('.np-regelwerk summary').textContent"), "18 von 22 Regeln gewählt – ansehen und anpassen")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.np-rw-regel')].filter(x => !x.querySelector('input').checked).map(x => x.dataset.nr)"),
                         ["W1", "W2", "W3", "W4"])                                              # wahlweise: nicht vorgewählt
        self.tab.js("[...document.querySelectorAll('.dialog input[type=checkbox], dialog input[type=checkbox], .einst input[type=checkbox]')]"
                    ".find(x => !x.closest('.np-regelwerk')).click()")                           # „Lead als Chat“
        self.warten("document.querySelector('.np-regelwerk summary').textContent.startsWith('19 von 22')")   # die Takt-Regel kommt dazu
        self.assertTrue(self.tab.js("document.querySelector('.np-rw-regel[data-nr=W4] input').checked"))
        self.assertEqual(self.tab.js("document.querySelectorAll('.np-rw-regel .gr-warum').length"), 22)      # jede Regel mit Warum oder Erfahrung
        self.tab.js("(() => { const s = document.querySelector('#np-regeln'); s.value = ''; s.dispatchEvent(new Event('change')); })()")
        self.assertEqual(self.tab.js("document.querySelectorAll('.np-rw-regel').length"), 0)                 # „ohne“: keine Liste
        regelwerk.uebernehmen(self.con, self.pid, "Entwickler", auswahl=["G1", "G3"], texte={"G3": "Eigener Weg einer Änderung."})
        self.oeffnen("wissen", "document.querySelector('.reiter')")
        self.tab.js("[...document.querySelectorAll('.reiter button, .reiter a')].find(b => /Regeln/.test(b.textContent)).click()")
        self.warten("document.querySelectorAll('.wissen-eintrag.grundregel').length === 2")
        self.assertEqual(self.tab.js("document.querySelector('.gr-titel').childNodes[0].textContent"), "Grundregeln (2)")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.gr-marke')].map(x => x.textContent)"), ["G1", "G3"])
        karten = self.tab.js("[...document.querySelectorAll('.wissen-eintrag.grundregel')].map(k => k.innerText)")
        self.assertIn("Erfahrung:", karten[0])
        self.assertNotIn("ANGEPASST", karten[0].upper().replace("ERFAHRUNG", ""))
        self.assertIn("Warum:", karten[1])
        self.assertIn("ANGEPASST", karten[1].upper())

    def test_logo_oben_mit_untertitel_und_favicon(self):
        self.oeffnen("start", "document.querySelector('#marke-text i')")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('#marke-text i')].map(i => i.textContent).join('')"), "AMW")
        self.assertGreater(self.tab.js("document.querySelector('.marke svg.logo').getBoundingClientRect().width"), 40)
        self.assertTrue(self.tab.js("document.querySelector('link[rel=icon]').href.startsWith('data:image/svg+xml')"))
        self.tab.js("sprache_setzen('en')")
        self.warten("document.getElementById('marke-text').textContent === 'AgentManagementWorkbench'")

    def test_sprungleiste_der_einstellungen_ohne_doppelte_marke(self):
        self.oeffnen("einstellungen", "document.querySelector('.sprung a')")
        texte = self.tab.js("[...document.querySelectorAll('.sprung a')].map(a => a.textContent)")
        self.assertIn("Dieser PC", texte)
        self.assertFalse([x for x in texte if "diesen PC" in x], texte)                 # der Hinweis „Gilt für …“ steht nicht in der Sprungleiste
        # neu gegliedert: erst, was die Installation trägt, dann Projekt und Agenten; je Abschnitt der Wirkungsort
        self.assertEqual(texte, ["Betriebsart", "Speicher und Abgleich", "Online-Seite", "Benachrichtigungen aufs Handy", "Dieser PC", "Projekt", "Agenten"])
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.einst > .karte > h3 .wirkt')].map(x => x.textContent)"),
                         ["Gilt für diesen PC", "Gilt für PC und Online-Seite", "Gilt für die Online-Seite", "Gilt für diesen PC", "Gilt für diesen PC", "Gilt für dieses Projekt"])
        # Betriebsart: drei Karten, genau eine gewählt; darunter die Liste der Verbindungen (mindestens die Workbench selbst)
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.ba-karte')].map(k => k.dataset.art)"), ["pc", "server", "cloud"])
        self.assertEqual(self.tab.js("document.querySelectorAll('.ba-karte.an').length"), 1)
        self.warten("document.querySelector('.ba-liste td')")
        self.assertTrue(self.tab.js("[...document.querySelectorAll('.ba-liste td')].some(z => z.textContent.startsWith('127.0.0.1:'))"))
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.pruef[data-pruef]')].map(x => x.dataset.pruef)"), ["speicher", "seite"])   # Prüf-Knöpfe (nicht gedrückt: kein Netz im Test)
        self.assertTrue(self.tab.js("[...document.querySelectorAll('.einst .feld')].some(f => f.textContent.includes('Port') && f.textContent.includes('Neustart des Wächters'))"))
        self.assertFalse(self.tab.js("/null|undefined/.test(document.querySelector('.einst').innerText)"))


if __name__ == "__main__":
    unittest.main()
