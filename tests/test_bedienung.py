"""Bedienbarkeits-Durchgang (A1292): Dokumente nach Art/Zeitraum/Reihenfolge, einheitliche Dialoge, ehrliche Zahlen.

- Schnittstelle: Wissen zählt alle Einträge (nicht nur die gezeigten), Betrieb nennt die Speicher-Grenze des Projekts.
- Seite (Edge ohne Fenster, nur wenn Edge da ist): Art-Chips mit Zahl filtern, Titel-Reihenfolge, Zeitraum; Enter im
  einzeiligen Feld schickt den Dialog ab; ein ✕ je Dialog; Sprungleiste der Einstellungen ohne doppelte Marke.
"""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
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
        self.oeffnen("planung", "document.querySelector('.kopf .kopf-aktion')?.textContent === 'Neuer Meilenstein'")   # nicht der Knopf der alten Sicht

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
        self.warten("document.querySelectorAll('.mehr-liste button').length === 7")              # mit „Nachrichten“ (1.74.0)
        self.assertTrue(self.tab.js("[...document.querySelectorAll('.mehr-liste button')].some(b => b.textContent.includes('Nachrichten'))"))
        self.tab.js("[...document.querySelectorAll('.mehr-liste button')].find(b => b.textContent.includes('Verlauf')).click()")
        self.warten("zustand.sicht === 'verlauf' && document.getElementById('mehr').classList.contains('an')")

    def test_nachrichten_reiter_und_startkarte(self):
        """Nachrichten: Eingang · Gesendet · Fragen als eine Leiste (auch auf der Fragen-Seite); Startseite nur eine Karte mit Sprung;
        zurückziehen mit Rückfrage; Bezug als Chip."""
        aid = db.einfuegen(self.con, "aufgabe", projekt_id=self.pid, titel="Linien", agent="CC1", status="laeuft", einstufung="aktiv",
                           angelegt_utc=db.jetzt(), angelegt_von="TL")
        self.con.commit()
        n1 = kern.posten(self.con, self.pid, kern.ENTWICKLER, "CC1", "auftrag", "Bitte Linien aufräumen", aufgabe_id=aid)[0]
        kern.posten(self.con, self.pid, "CC1", kern.ENTWICKLER, "info", "Mache ich")
        self.oeffnen("start", "document.querySelector('.nr-start')")
        self.assertIn("Mache ich", self.tab.js("document.querySelector('.nr-start').innerText"))
        self.tab.js("document.querySelector('.nr-start').click()")
        self.warten("zustand.sicht === 'nachrichten' && document.querySelector('.nr-reiter button.an')")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.nr-reiter button')].map(b => b.classList.contains('an'))"), [True, False, False])
        self.assertIn("Mache ich", self.tab.js("document.querySelector('.nr-liste').innerText"))
        self.tab.js("document.querySelectorAll('.nr-reiter button')[1].click()")
        self.warten(f"document.querySelector('.nr-liste') && document.querySelector('.nr-liste').innerText.includes('Bitte Linien aufräumen')")
        self.assertIn(f"A{aid} Linien", self.tab.js("document.querySelector('.nr-liste .nr-chip').innerText"))
        self.assertIn("Mache ich", self.tab.js("document.querySelector('.nr-gespraech').innerText"))      # Antwort hängt am Faden
        self.tab.js("window.confirm = () => true; [...document.querySelectorAll('.nr-gespraech button')].find(b => b.innerText.toUpperCase().includes('ZURÜCKZIEHEN')).click()")
        self.warten("document.querySelector('.nr-eintrag.weg')")
        self.assertEqual(self.con.execute("SELECT bemerkung FROM empfang WHERE nachricht_id = ?", (n1,)).fetchone()[0], kern.ZURUECKGEZOGEN)
        self.tab.js("document.querySelectorAll('.nr-reiter button')[2].click()")
        self.warten("zustand.sicht === 'fragen' && document.querySelector('.nr-reiter button.an')")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.nr-reiter button')].map(b => b.classList.contains('an'))"), [False, False, True])

    def test_baum_zeigt_beziehungen_nur_fuer_die_karte_unter_der_maus(self):
        """Team-Baum: dauerhaft nur die Äste; Prüf-/Warte-Linien einer Karte erst mit der Maus darauf, Rest abgeblendet."""
        from amw import betrieb
        betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "zweig", "abc1234def5678", "Probe")
        self.oeffnen("start", "document.querySelector('#team')")
        self.tab.js("[...document.querySelectorAll('.tm-schalter button')][0].click()")
        self.warten("document.querySelector('.tm-baum') && document.querySelectorAll('.tm-linien path').length")
        self.assertEqual(self.tab.js("document.querySelectorAll('.tm-linien .tm-bogen').length"), 0)          # ohne Maus: keine
        self.tab.js("document.querySelector('.tm-knoten[data-k=CC1]').dispatchEvent(new MouseEvent('mouseenter'))")
        self.warten("document.querySelectorAll('.tm-linien .tm-bogen.stark').length === 1")
        self.assertTrue(self.tab.js("document.querySelector('.tm-knoten[data-k=CC1]').classList.contains('im-fokus')"))
        self.tab.js("document.querySelector('.tm-knoten[data-k=CC1]').dispatchEvent(new MouseEvent('mouseleave'))")
        self.warten("document.querySelectorAll('.tm-linien .tm-bogen').length === 0")

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
        self.assertEqual(self.tab.js("document.querySelectorAll('#leitstand > div').length"), 5)       # Arbeit, Bildschirm, Sitzungen, Dienst, Rechner
        self.assertNotIn("im Eingang", self.tab.js("document.querySelector('#leitstand').innerText"))   # leerer Eingang: kein Hinweis
        rechner = self.tab.js("document.querySelector('#ls-rechner').innerText")
        self.assertIn("Frei", rechner)                                                                 # kein Lauf angemeldet
        self.assertIn("gemeinsamen Warteschlange", rechner)
        self.assertNotIn("Aus diesem Projekt", rechner)                                                # nichts Eigenes: der Satz entfällt
        # ein Programm außerhalb der Warteschlange belegt lange viel Arbeitsspeicher: Name, Größe, seit wann
        import datetime
        from unittest import mock
        from amw import belegung
        seit = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=40)
        with mock.patch.object(belegung, "prozesse", lambda: [{"pid": 5, "eltern": 1, "name": "llama-server", "gb": 16.4, "seit": seit}]), \
                mock.patch.object(belegung, "_gemerkt", [0.0, None, []]):
            self.tab.js("zeige('start', true)")
            self.warten("document.querySelector('#ls-rechner').innerText.includes('dauerhaft belegt')")
            rechner = self.tab.js("document.querySelector('#ls-rechner').innerText")
            self.assertIn("Frei · 16,4 GB dauerhaft belegt", rechner)
            self.assertRegex(rechner, r"Außerhalb der Warteschlange belegt: llama-server \(lokale KI\) 16,4 GB seit [\d., ]*\d\d:\d\d\. Beenden kannst nur du")
            self.assertRegex(rechner, r"\d+(,\d)? GB Arbeitsspeicher frei")                                # Zahlen mit Komma
        # ein Laufwerk wird knapp: Hauptzeile, Satz mit Zahlen, Feld rot; in den Einstellungen Laufwerke und Aufräumvorschläge
        import collections
        from amw import platte
        Platz = collections.namedtuple("Platz", "total used free")
        with mock.patch.object(platte.shutil, "disk_usage", lambda pfad: Platz(500 * 2 ** 30, 480 * 2 ** 30, 20 * 2 ** 30)):
            self.tab.js("zeige('start', true)")
            self.warten("document.querySelector('#ls-rechner').innerText.includes('fast voll')")
            rechner = self.tab.js("document.querySelector('#ls-rechner').innerText")
            self.assertRegex(rechner, r"Frei · Laufwerk \S+ fast voll")
            self.assertRegex(rechner, r"Laufwerk \S+ noch 20 GB frei \(4 %\)\.")
            self.oeffnen("einstellungen", "document.querySelector('#e-laufwerke')")
            self.assertRegex(self.tab.js("document.querySelector('#e-laufwerke').innerText"), r"^\S+ 20 von 500 GB frei \(4 %\)$")
            self.assertIn('class="rot"', self.tab.js("document.querySelector('#e-laufwerke').outerHTML"))
            zeile = self.tab.js("[...document.querySelectorAll('.feld')].find(f => f.querySelector('label')?.textContent === 'Aufräumvorschläge').innerText")
            self.assertIn("Keine", zeile)
            self.assertIn("Die AMW löscht nichts", zeile)
        self.tab.js("zeige('start', true)")                                                            # zurück zur Startseite
        self.warten("document.querySelector('#ls-rechner') && document.querySelector('#leitstand button')")
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
        self.warten("document.querySelector('.np-regelwerk summary') && document.querySelectorAll('.np-rw-regel').length === 23")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('#np-regeln option')].map(o => o.value)"), ["grund", "kopie:P", ""])
        self.assertEqual(self.tab.js("document.querySelector('.np-regelwerk summary').textContent"), "19 von 23 Regeln gewählt – ansehen und anpassen")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.np-rw-regel')].filter(x => !x.querySelector('input').checked).map(x => x.dataset.nr)"),
                         ["W1", "W2", "W3", "W4"])                                              # wahlweise: nicht vorgewählt
        self.tab.js("[...document.querySelectorAll('.dialog input[type=checkbox], dialog input[type=checkbox], .einst input[type=checkbox]')]"
                    ".find(x => !x.closest('.np-regelwerk')).click()")                           # „Lead als Chat“
        self.warten("document.querySelector('.np-regelwerk summary').textContent.startsWith('20 von 23')")   # die Takt-Regel kommt dazu
        self.assertTrue(self.tab.js("document.querySelector('.np-rw-regel[data-nr=W4] input').checked"))
        self.assertEqual(self.tab.js("document.querySelectorAll('.np-rw-regel .gr-warum').length"), 23)      # jede Regel mit Warum oder Erfahrung
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

    def test_token_pause_als_eigenes_stueck_in_der_planung(self):
        """Übersicht: der Balken bekommt hinten das Stück Token-Pause (Zeichen, eigene Farbe, Schraffur); am Datum „+n T →“;
        Wochenlimit mit Rechenweg im Kopf der Übersicht und im Leitstand."""
        from tests.test_tokenprognose import plan_mit_verbrauch
        plan_mit_verbrauch(self.con, self.pid)
        self.oeffnen("planung", "document.querySelector('.ueb-token') && document.querySelector('#token-woche')")
        self.assertEqual(self.tab.js("document.querySelectorAll('.ueb-token').length"), 1)
        self.assertEqual(self.tab.js("document.querySelector('.ueb-token b').textContent"), "\u29d7")                  # nicht nur Farbe: Zeichen …
        self.assertIn("repeating-linear-gradient", self.tab.js("getComputedStyle(document.querySelector('.ueb-token')).backgroundImage"))   # … und Schraffur
        self.assertTrue(self.tab.js("(() => { const b = document.querySelector('.ueb-block').getBoundingClientRect(), k = document.querySelector('.ueb-token').getBoundingClientRect();"
                                    " return Math.abs(k.left - b.right) < 2 && k.width > 4; })()"))                    # hängt hinten am Balken
        stueck = self.tab.js("document.querySelector('.tk-stueck').textContent")
        self.assertRegex(stueck, "^ \u29d7 \\+\\d+ T \u2192 \u2248 \\d\\d\\.\\d\\d\\.$")
        woche = self.tab.js("document.querySelector('#token-woche').innerText")
        for teil in ("88 % verbraucht", "voraussichtlich aufgebraucht", "Reset", "Gilt für das ganze Konto"):
            self.assertIn(teil, woche)
        rechenweg = self.tab.js("document.querySelector('#token-woche').title")
        for teil in ("Verbrauch je Tag:", "Prozentpunkte (wahrscheinlich)", "Danach je Woche:", "Ein Reset zählt nicht als Verbrauch"):
            self.assertIn(teil, rechenweg)
        self.assertIn("Pause durch das Wochenlimit", self.tab.js("document.querySelector('.ueb-legende').innerText"))
        hell = self.tab.js("getComputedStyle(document.documentElement).getPropertyValue('--token').trim()")
        self.tab.js("thema(document.documentElement.dataset.thema === 'hell' ? 'dunkel' : 'hell')")
        self.assertNotEqual(hell, self.tab.js("getComputedStyle(document.documentElement).getPropertyValue('--token').trim()"))   # hell und dunkel eigene Farbe
        self.oeffnen("start", "document.querySelector('#ls-token')")
        self.assertIn("88 % verbraucht", self.tab.js("document.querySelector('#ls-token').innerText"))
        self.assertIn("Wochenlimit", self.tab.js("document.querySelector('#ls-token').textContent"))   # (in der Anzeige groß geschrieben)
        self.assertEqual(self.tab.js("document.querySelectorAll('#leitstand > div').length"), 6)       # … dazu Rechner und Wochenlimit
        # Ampel mit Pause: hält der Termin nur ohne Pause, steht „(mit Pause)“ am Datum
        from amw import db, planung
        bid = self.con.execute("SELECT id FROM bogen WHERE projekt_id = ? ORDER BY id DESC", (self.pid,)).fetchone()[0]
        p85 = planung.prognose(self.con, self.pid, laeufe=600)["boegen"][bid]["p85"]
        with db.schreiben(self.con):
            self.con.execute("UPDATE bogen SET zieldatum = ? WHERE id = ?", (p85, bid))
        self.oeffnen("planung", "document.querySelector('.ueb-token') && [...document.querySelectorAll('.sehrleise')].some(x => x.textContent.trim() === '(mit Pause)')")

    def test_rechner_heute_als_eigener_zeitstrahl(self):
        """Planung: unter der Übersicht der Tagesablauf des Rechners – eigene Läufe mit Nummer und Agent, fremde nur als
        „anderes Projekt“, Wartende gestrichelt hinter „jetzt“, Dauer-Belegung als durchgehender Balken; einklappbar."""
        import datetime
        from unittest import mock
        from amw import belegung, db
        jetzt = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
        mitternacht = datetime.datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        faktor = min(1.0, (jetzt - mitternacht).total_seconds() / 3600 / 1.6)     # kurz nach Mitternacht: alles in den heutigen Minuten
        iso = lambda minuten: (jetzt + datetime.timedelta(minutes=minuten * (faktor if minuten < 0 else 1))).strftime("%Y-%m-%dT%H:%M:%SZ")
        with db.schreiben(self.con):
            fremd = db.einfuegen(self.con, "projekt", name="Fremd", angelegt_utc=db.jetzt())
            lauf = lambda pid, agent, text, status, start=None, ende=None, **mehr: db.einfuegen(
                self.con, "lauf", projekt_id=pid, agent=agent, beschreibung=text, status=status, angemeldet_utc=iso(-90), start_utc=start, ende_utc=ende, **mehr)
            l1 = lauf(self.pid, "CC1", "Gesamtlauf", "fertig", iso(-60), iso(-40), braucht_gb=8)
            lauf(fremd, "X1", "Geheimer Build", "laeuft", iso(-10), erwartet_min=30, braucht_gb=4)
            l3 = lauf(self.pid, "CC1", "Browser-Tests", "angemeldet", erwartet_min=15)
        seit = jetzt - datetime.timedelta(minutes=50)
        with mock.patch.object(belegung, "prozesse", lambda: [{"pid": 5, "eltern": 1, "name": "llama-server", "gb": 16.4, "seit": seit}]), \
                mock.patch.object(belegung, "_gemerkt", [0.0, None, []]):
            self.oeffnen("planung", "document.querySelector('#rechner-heute .rh-lauf')")
            balken = self.tab.js("[...document.querySelectorAll('#rechner-heute .rh-lauf')].map(b => [b.className.replace('rh-lauf ', ''), b.textContent])")
            self.assertEqual(balken[0], ["dauer", "llama-server · 16,4 GB"])
            self.assertEqual(balken[1], ["fertig eigen", f"L{l1} CC1 · 8 GB"])
            self.assertEqual(balken[2][0], "laeuft")
            self.assertTrue(balken[2][1].startswith("anderes Projekt"))
            self.assertEqual(balken[3][0], "wartet eigen")
            self.assertTrue(balken[3][1].startswith(f"L{l3} CC1"))
            self.assertNotIn("Geheim", self.tab.js("document.querySelector('#inhalt').innerHTML"))            # von fremden Läufen kein Inhalt
            lage = self.tab.js("(() => { const x = s => document.querySelector('#rechner-heute ' + s).getBoundingClientRect();"
                               " const j = x('.ueb-heute'), w = x('.rh-lauf.wartet'), f = x('.rh-lauf.fertig'), d = x('.rh-lauf.dauer'), fl = x('.rh-flaeche');"
                               " return [f.right < j.left, w.left >= j.left - 1, Math.abs(d.right - fl.right) < 3]; })()")
            self.assertEqual(lage, [True, True, True])                                                       # fertig vor „jetzt“, wartend dahinter, Dauer bis zum Rand
            self.assertEqual(self.tab.js("getComputedStyle(document.querySelector('#rechner-heute .rh-lauf.wartet')).borderTopStyle"), "dashed")
            kopf = self.tab.js("document.querySelector('#rechner-heute summary').textContent")
            self.assertIn("1 wartet", kopf)
            self.assertIn("Stunden belegt", kopf)
            self.assertFalse(self.tab.js("document.documentElement.scrollWidth > innerWidth"))
            self.tab.js("document.querySelector('#rechner-heute summary').click()")                          # einklappen – bleibt beim Neuzeichnen zu
            self.warten("!document.querySelector('#rechner-heute').open")
            self.tab.js("sichtPlanung()")
            self.warten("document.querySelector('#rechner-heute') && !document.querySelector('#rechner-heute').open")

    def test_dazwischenschieben_in_der_aufgabe(self):
        """Aufgabe eines Agenten, der gerade an einer anderen arbeitet: Knopf „Dazwischenschieben“ mit Erklärung."""
        from amw import kern
        lauf = kern.aufgabe_neu(self.con, self.pid, "TL", "Laufendes Stück", agent="CC1")
        neu = kern.aufgabe_neu(self.con, self.pid, "TL", "Eilig", agent="CC1")
        kern.aufgabe_status(self.con, self.pid, "CC1", lauf, "start")
        self.oeffnen("start", "typeof aufgabeDialog === 'function'")
        self.tab.js(f"aufgabeDialog({neu})")
        self.warten("[...document.querySelectorAll('button')].some(b => b.textContent === 'Dazwischenschieben')")
        self.assertIn(f"CC1 arbeitet gerade an A{lauf}", self.tab.js("document.querySelector('.dialog-hg .dialog').innerText"))
        self.tab.js("document.querySelectorAll('.dialog-hg').forEach(x => x.remove())")
        self.tab.js(f"aufgabeDialog({lauf})")                                                      # das laufende Stück selbst: kein Knopf
        self.warten("document.querySelector('.dialog-hg .dialog')")
        self.assertFalse(self.tab.js("[...document.querySelectorAll('.dialog-hg button')].some(b => b.textContent === 'Dazwischenschieben')"))

    def test_benutzer_anlegen_in_den_einstellungen(self):
        """Einstellungen › Benutzer der Online-Seite: anlegen – ohne Rolle wartet er auf Freigabe."""
        self.oeffnen("einstellungen", "document.querySelector('#e-benutzer #bn-neu-name')")
        self.tab.js("document.querySelector('#bn-neu-name').value = 'probe'; document.querySelector('#bn-anlegen').click()")
        self.warten("document.querySelector('#e-benutzer [data-name=probe]')")
        self.assertIn("wartet auf Freigabe", self.tab.js("document.querySelector('#e-benutzer [data-name=probe] select').selectedOptions[0].textContent"))
        from amw import benutzer
        self.assertIsNone(benutzer.finden(self.con, "probe")["rolle"])

    def test_versionshinweise_mit_entwurf(self):
        """Seite Versionshinweise: oben der Entwurf der nächsten Version (Satz des Agenten, Vorschlag gekennzeichnet)."""
        from amw import kern
        a = kern.aufgabe_neu(self.con, self.pid, "TL", "Export", agent="CC1")
        kern.aufgabe_status(self.con, self.pid, "CC1", a, "start")
        kern.aufgabe_status(self.con, self.pid, "CC1", a, "fertig", beleg="abc1234", zusammenfassung="csv.py",
                            hinweis="Listen lassen sich als CSV-Datei speichern.", gruppe="neu")
        self.oeffnen("releases", "document.querySelector('.vh-version')")
        text = self.tab.js("document.querySelector('#inhalt').innerText")
        self.assertIn("Nächste Version – Entwurf", text)
        self.assertIn("Listen lassen sich als CSV-Datei speichern.", text)
        self.assertNotIn(f"A{a}", self.tab.js("document.querySelector('.vh-version').innerText"))     # „Für alle“: ohne Nummern
        self.tab.js("[...document.querySelectorAll('.reiter button')].find(b => b.textContent === 'Mit Aufgaben').click()")
        self.warten(f"document.querySelector('.vh-version').innerText.includes('A{a}')")

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
        self.assertEqual(texte, ["Betriebsart", "Speicher und Synchronisierung", "Online-Seite", "Benutzer der Online-Seite", "Benachrichtigungen aufs Handy", "Dieser PC", "Projekt", "Agenten"])
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.einst > .karte > h3 .wirkt')].map(x => x.textContent)"),
                         ["Gilt für diesen PC", "Gilt für PC und Online-Seite", "Gilt für die Online-Seite", "Gilt für die Online-Seite",
                          "Gilt für diesen PC", "Gilt für diesen PC", "Gilt für dieses Projekt"])
        # Betriebsart: drei Karten, genau eine gewählt; darunter die Liste der Verbindungen (mindestens die Workbench selbst)
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.ba-karte')].map(k => k.dataset.art)"), ["pc", "server", "cloud"])
        self.assertEqual(self.tab.js("document.querySelectorAll('.ba-karte.an').length"), 1)
        self.warten("document.querySelector('.ba-liste td')")
        self.assertTrue(self.tab.js("[...document.querySelectorAll('.ba-liste td')].some(z => z.textContent.startsWith('127.0.0.1:'))"))
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.pruef[data-pruef]')].map(x => x.dataset.pruef)"), ["speicher", "seite"])   # Prüf-Knöpfe (nicht gedrückt: kein Netz im Test)
        self.assertTrue(self.tab.js("[...document.querySelectorAll('.einst .feld')].some(f => f.textContent.includes('Port') && f.textContent.includes('Neustart des Dienstes'))"))
        self.assertFalse(self.tab.js("/null|undefined/.test(document.querySelector('.einst').innerText)"))


if __name__ == "__main__":
    unittest.main()
