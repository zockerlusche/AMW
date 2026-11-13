"""Gerüst für den Bedienbarkeits-Rundgang (A1614): jede Seite, jeder Reiter, jedes ⋯-Menü und jeder Dialog in zwei Größen
(PC 1440×900, Handy 390×844) und beiden Themen (hell, dunkel) – mit denselben Prüfungen überall:

- keine Fehler in der Konsole (Fehler, unbehandelte Ablehnungen, console.error),
- nichts ragt waagrecht über den Rand (die Seite scrollt nicht seitwärts, kein sichtbares Element liegt rechts außerhalb),
- jeder offene Dialog und jedes Vollbild hat ein ✕ innerhalb des Bildschirms, das man auch wirklich trifft,
- keine abgeschnittenen Knopf- und Überschrift-Texte (abgeschnitten ohne „…“ = Fehler; mit „…“ ohne Tooltip = Hinweis),
- keine Fokus-Falle: kein tabindex > 0, jeder Knopf hat einen Namen (Text oder aria-label).
- Liste und Inhalt nebeneinander (.geteilt, Nachrichten): jede Spalte scrollt für sich, Scrollen im Inhalt lässt die Liste
  stehen, nichts reicht unter den Fensterrand; bei .klebt bleibt die Liste beim Scrollen der Seite sichtbar (A1628).

Benutzen: eine Testklasse erbt von Rundgang, legt in daten() ihre Beispieldaten an und ruft je Fall
  self.besuchen("<sicht>", bereit="<JS-Bedingung>", tun="<JS, z. B. Dialog öffnen>", ort="<Name im Bericht>")
für jede Größe und jedes Thema (self.ueberall(...)). Fehler lassen den Test scheitern; Hinweise sammelt der Bericht.
Bilder: nur wenn AMW_RUNDGANG_BILDER auf einen Ordner zeigt (Name <ort>-<groesse>-<thema>.png, dazu funde.jsonl mit allen
Funden samt Hinweisen), sonst keine.
Dieses Modul ist kein Test (wird nicht entdeckt); Testdateien importieren es.
"""
import base64
import json
import os
import re
import shutil
import subprocess
import time
import unittest
import urllib.request

from amw import kern, workbench
from tests.test_aktualisieren import EDGE, Grund, Wiederholt, _Tab, edge_beenden, freier_port, warte_auf

GROESSEN = {"pc": dict(width=1440, height=900, deviceScaleFactor=1, mobile=False),
            "handy": dict(width=390, height=844, deviceScaleFactor=2, mobile=True)}
THEMEN = ("hell", "dunkel")

# Läuft vor jedem Skript der Seite: sammelt Fehler, bevor die Seite selbst etwas tut.
FEHLER_FANGEN = """
window.__rundgang = [];
addEventListener('error', e => __rundgang.push('Fehler: ' + (e.message || e.type) + (e.filename ? ' @' + e.filename.split('/').pop() + ':' + e.lineno : '')));
addEventListener('unhandledrejection', e => __rundgang.push('Ablehnung: ' + (e.reason && (e.reason.message || e.reason) || '?')));
(() => { const ce = console.error; console.error = (...a) => { __rundgang.push('console.error: ' + a.map(String).join(' ')); ce.apply(console, a); }; })();
"""

# Prüft den gerade sichtbaren Zustand; Rückgabe: Liste [schwere, was, wo].
PRUEFEN = r"""
(() => {
  const erg = [], B = innerWidth, H = innerHeight;
  const name = e => (e.id ? '#' + e.id : '') + (e.className && typeof e.className === 'string' ? '.' + e.className.trim().split(/\s+/).slice(0, 2).join('.') : '') || e.tagName.toLowerCase();
  const pfad = e => { const t = []; for (let x = e; x && x !== document.body && t.length < 4; x = x.parentElement) t.unshift(x.tagName.toLowerCase() + (x.id ? '#' + x.id : '') + (typeof x.className === 'string' && x.className.trim() ? '.' + x.className.trim().split(/\s+/)[0] : '')); return t.join(' > '); };
  const sichtbar = e => { if (!e.getClientRects().length) return false; const s = getComputedStyle(e); return s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity !== 0; };
  // Seiten-Behälter: scrollen senkrecht (overflow-y) – ihr overflow-x ist dadurch auch „auto“, gemeint ist aber kein Seitwärts.
  // Was darin seitwärts übersteht, ist ein Fehler; nur echte eigene Scroll-Leisten (Tabellen, Sprungleiste) zählen als gewollt.
  const SEITE = '#inhalt, .dialog, .dialog-hg, .menue, main';
  const inScroller = e => { for (let x = e.parentElement; x && x !== document.body; x = x.parentElement) { if (x.matches(SEITE)) continue; const o = getComputedStyle(x).overflowX; if (o === 'auto' || o === 'scroll' || o === 'hidden' || o === 'clip') return true; } return false; };
  for (const f of (window.__rundgang || [])) erg.push(['fehler', 'Konsole: ' + f.slice(0, 200), '']);
  // 1. waagrechter Überlauf: die Seite selbst und jeder sichtbare Seiten-Behälter
  const sw = document.documentElement.scrollWidth;
  if (sw > B + 1) erg.push(['fehler', `Seite scrollt seitwärts (${sw} px statt ${B} px)`, '']);
  for (const x of document.querySelectorAll(SEITE)) if (sichtbar(x) && x.scrollWidth > x.clientWidth + 1 && getComputedStyle(x).overflowX !== 'hidden')
    erg.push(['fehler', `scrollt seitwärts (${x.scrollWidth} px statt ${x.clientWidth} px)`, pfad(x)]);
  let n = 0;
  for (const e of document.body.querySelectorAll('*')) {
    if (n > 8) break;
    const r = e.getBoundingClientRect();
    if (r.width && r.right > B + 1 && r.left < B && sichtbar(e) && !inScroller(e) && getComputedStyle(e).position !== 'fixed') {
      erg.push(['fehler', `ragt rechts über den Rand (${Math.round(r.right)} > ${B})`, pfad(e)]); n++; }
  }
  // 2. Dialoge und Vollbild: ✕ im Bild und treffbar
  const oben = [...document.querySelectorAll('.dialog-hg, .vb')].filter(sichtbar).pop();
  if (oben) {
    const zu = oben.matches('.vb') ? oben.querySelector(':scope > .vb-zu') : oben.querySelector('.dialog-zu');
    if (!zu || !sichtbar(zu)) erg.push(['fehler', 'Dialog ohne sichtbares ✕', pfad(oben)]);
    else { const r = zu.getBoundingClientRect();
      if (r.left < 0 || r.top < 0 || r.right > B || r.bottom > H) erg.push(['fehler', `✕ außerhalb des Bildschirms (${Math.round(r.left)},${Math.round(r.top)})`, pfad(zu)]);
      else { const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        if (!t || !(t === zu || zu.contains(t))) erg.push(['fehler', '✕ verdeckt (Klick trifft ' + (t ? name(t) : 'nichts') + ')', pfad(zu)]); }
      if (r.width < 32 || r.height < 32) erg.push(['hinweis', `✕ klein (${Math.round(r.width)}×${Math.round(r.height)})`, pfad(zu)]); }
  }
  // 3. abgeschnittene Texte (Knöpfe, Überschriften, Reiter, Marken)
  const bereich = oben || document.body;
  for (const e of bereich.querySelectorAll('button, .knopf, .klein-knopf, h2, h3, h4, label, .reiter a, .chip, .vl-chip')) {
    if (!sichtbar(e) || !e.textContent.trim()) continue;
    if (e.scrollWidth > e.clientWidth + 1 && e.clientWidth > 0) {
      const s = getComputedStyle(e);
      if (s.overflowX === 'visible') continue;                        // läuft sichtbar weiter – das fängt Prüfung 1
      if (s.textOverflow === 'ellipsis') { if (!e.title && !e.closest('[title]')) erg.push(['hinweis', 'mit „…“ gekürzt, ohne Tooltip: ' + e.textContent.trim().slice(0, 40), pfad(e)]); }
      else erg.push(['fehler', 'Text abgeschnitten: ' + e.textContent.trim().slice(0, 40), pfad(e)]);
    }
  }
  // 4. Fokus: kein tabindex > 0, Knöpfe mit Namen
  for (const e of bereich.querySelectorAll('[tabindex]')) if (+e.getAttribute('tabindex') > 0 && sichtbar(e)) erg.push(['fehler', 'tabindex > 0 stört die Reihenfolge', pfad(e)]);
  for (const e of bereich.querySelectorAll('button, a[href], [role=button]')) {
    if (!sichtbar(e)) continue;
    if (!(e.textContent.trim() || e.getAttribute('aria-label') || e.title || e.querySelector('img[alt]:not([alt=""]), svg title')))
      erg.push(['fehler', 'Knopf ohne Namen', pfad(e)]);
  }
  // 5. Liste und Inhalt nebeneinander (A1628, wie im Mail-Programm): jede Spalte scrollt für sich – Scrollen im Inhalt
  //    lässt Liste und Seite stehen; nichts reicht unter den Fensterrand. „klebt“: die Liste bleibt beim Scrollen der Seite
  //    sichtbar. Untereinander (Handy) gibt es nichts zu prüfen.
  const m = document.querySelector('#inhalt');
  for (const g of document.querySelectorAll('.geteilt, .nr-raster, .klebt')) {
    const [li, re] = [...g.children].filter(sichtbar);
    if (!sichtbar(g) || !li || !re || Math.abs(li.getBoundingClientRect().top - re.getBoundingClientRect().top) > 1) continue;
    if (g.classList.contains('klebt')) {
      const alt = m.scrollTop;
      m.scrollTop += g.getBoundingClientRect().bottom - innerHeight + 20;             // bis ans Ende des Inhalts scrollen
      const r = li.getBoundingClientRect();
      if (r.bottom < 40 || r.top > innerHeight / 2) erg.push(['fehler', 'Liste verschwindet beim Scrollen der Seite', pfad(li)]);
      m.scrollTop = alt;
      continue;
    }
    const lage = () => [li.scrollTop, Math.round(li.getBoundingClientRect().top), document.scrollingElement.scrollTop, m ? m.scrollTop : 0];
    const vorher = lage(), alt = re.scrollTop;
    re.scrollTop = re.scrollHeight;
    const nachher = lage();
    re.scrollTop = alt;
    if (vorher.some((v, i) => Math.abs(v - nachher[i]) > 1)) erg.push(['fehler', 'Scrollen im Inhalt bewegt die Liste', pfad(g)]);
    if (g.getBoundingClientRect().bottom > innerHeight + 1) erg.push(['fehler', `Spalten reichen unter den Fensterrand (${Math.round(g.getBoundingClientRect().bottom)} > ${innerHeight})`, pfad(g)]);
    for (const s of [li, re]) if (s.scrollHeight > s.clientHeight + 1 && !['auto', 'scroll'].includes(getComputedStyle(s).overflowY))
      erg.push(['fehler', 'Spalte ohne eigenen Scrollbereich', pfad(s)]);
  }
  window.__rundgang = [];
  return erg;
})()
"""


@unittest.skipUnless(EDGE, "Edge nicht installiert")
class Rundgang(Wiederholt, Grund):
    """Ein Test-Browser je Testfall; die Workbench läuft auf einer leeren Test-Datenbank mit den Daten aus daten()."""
    BERICHT = []          # (ort, groesse, thema, schwere, was, wo) über alle Fälle – für die Fundliste

    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")

    def server_starten(self):
        """Startet die Seite und gibt ihre Adresse zurück (mit „/“ am Ende). Hier: die Workbench am PC."""
        self.port = freier_port()
        self.srv = workbench.starten(self.port)
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        return f"http://127.0.0.1:{self.port}/"

    def anmelden(self):
        """Nach dem Start des Browsers: anmelden, falls die Seite das braucht (am PC nicht)."""

    def setUp(self):
        super().setUp()
        self.daten()
        self.basis = self.server_starten()
        dt = freier_port()
        self.edge = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars",
                                      f"--remote-debugging-port={dt}", f"--user-data-dir={os.path.join(self.ordner.name, 'edge')}",
                                      "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(edge_beenden, self.edge)        # auch wenn setUp danach scheitert (Edge meldet sich nicht):
                                                         # sonst bleibt der Browser ohne Eltern liegen (13.11.: 8 Stück)
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
        self.tab.senden("Page.enable")
        self.tab.senden("Page.addScriptToEvaluateOnNewDocument", source=FEHLER_FANGEN)
        self.funde = []
        self.anmelden()

    def tearDown(self):
        try:
            self.tab.s.close()
        except Exception:
            pass
        edge_beenden(self.edge)
        super().tearDown()

    # --- Bausteine -------------------------------------------------------------------------------------------------------
    def groesse(self, g):
        self.tab.senden("Emulation.setDeviceMetricsOverride", **GROESSEN[g])
        self.tab.senden("Emulation.setTouchEmulationEnabled", enabled=GROESSEN[g]["mobile"])

    def thema(self, t):
        self.tab.js(f"try {{ localStorage.setItem('amw-thema', '{t}') }} catch (e) {{}}; typeof thema === 'function' && thema('{t}')")

    def warten(self, bedingung, sekunden=8):
        warte_auf(self, bedingung, sekunden)

    def oeffnen(self, sicht, bereit="true"):
        self.besuche = getattr(self, "besuche", 0) + 1                    # neue Adresse = echtes Neuladen (nur #… lädt nicht neu,
        self.tab.senden("Page.navigate", url=f"{self.basis}?r={self.besuche}#{sicht}")   # Dialoge blieben offen)
        self.warten(f"document.readyState === 'complete' && typeof zeige === 'function' && ({bereit})")

    def pruefen(self, ort, g, t):
        """Prüft den sichtbaren Zustand, merkt die Funde und legt auf Wunsch ein Bild ab. Rückgabe: die Fehler."""
        time.sleep(0.25)                                                 # Übergänge (Einblenden) abwarten
        funde = self.tab.js(PRUEFEN) or []
        for schwere, was, wo in funde:
            self.funde.append((ort, g, t, schwere, was, wo))
            Rundgang.BERICHT.append((ort, g, t, schwere, was, wo))
        ordner = (os.environ.get("AMW_RUNDGANG_BILDER") or "").strip()   # cmd: „set X=… &&“ hängt ein Leerzeichen an
        if ordner:
            os.makedirs(ordner, exist_ok=True)
            bild = self.tab.senden("Page.captureScreenshot", format="png")["data"]
            with open(os.path.join(ordner, f"{re.sub(r'[^A-Za-z0-9_-]+', '_', ort)}-{g}-{t}.png"), "wb") as f:
                f.write(base64.b64decode(bild))
            with open(os.path.join(ordner, "funde.jsonl"), "a", encoding="utf-8") as f:     # Fundliste (auch Hinweise)
                for fund in funde:
                    f.write(json.dumps({"ort": ort, "groesse": g, "thema": t, "schwere": fund[0], "was": fund[1], "wo": fund[2]},
                                       ensure_ascii=False) + "\n")
        return [f for f in funde if f[0] == "fehler"]

    def besuchen(self, sicht, ort=None, bereit="true", tun=None, danach=None, g="pc", t="dunkel"):
        """Sicht öffnen, optional etwas tun (Dialog/Menü öffnen) und warten, bis danach gilt; dann prüfen."""
        self.groesse(g)
        self.oeffnen(sicht, bereit)
        self.thema(t)
        if tun:
            self.tab.js(tun)
            if danach:
                self.warten(danach)
        return self.pruefen(ort or sicht, g, t)

    def ueberall(self, sicht, ort=None, **kw):
        """Wie besuchen(), für jede Größe und jedes Thema; ein Fehler irgendwo lässt den Test scheitern (mit allen Funden)."""
        fehler = []
        for g in GROESSEN:
            for t in THEMEN:
                fehler += [(g, t) + tuple(f[1:]) for f in self.besuchen(sicht, ort, g=g, t=t, **kw)]
        self.assertEqual(fehler, [], f"{ort or sicht}: {len(fehler)} Fehler")

    def esc(self):
        self.tab.senden("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape", windowsVirtualKeyCode=27)
        self.tab.senden("Input.dispatchKeyEvent", type="keyUp", key="Escape", code="Escape", windowsVirtualKeyCode=27)

    def tippen(self, selektor):
        """Echter Klick/Tipp in die Mitte des Elements (trifft, was dort oben liegt – wie ein Finger)."""
        r = self.tab.js(f"(() => {{ const e = document.querySelector({json.dumps(selektor)}); if (!e) return null;"
                        " const r = e.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
        self.assertIsNotNone(r, f"nicht da: {selektor}")
        for typ in ("mousePressed", "mouseReleased"):
            self.tab.senden("Input.dispatchMouseEvent", type=typ, x=r[0], y=r[1], button="left", clickCount=1)


PHP = shutil.which("php")
WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@unittest.skipUnless(PHP, "PHP nicht installiert")
class OnlineRundgang(Rundgang):
    """Dasselbe für die Online-Seite: echtes PHP der Seite (php -S) gegen eine SQLite-Datei, die Ansichten lädt der echte
    Abgleich des PCs hoch; Anmeldung mit Benutzer, Passwort und Zahl aus der App wie ein Mensch im Browser."""
    GEHEIM = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"

    def server_starten(self):
        from amw import abgleich
        online = os.path.join(self.ordner.name, "online.db")
        self.sp = abgleich.SqliteSpeicher(online)
        self.ab = abgleich.Abgleich(self.con, self.sp, self.pid)
        self.ab.schema()
        self.ab.hochladen(alle=True)
        self.sp.ausfuehren([("INSERT INTO zustand (schluessel, wert) VALUES ('totp_geheim', ?)", [self.GEHEIM])])
        konfig = os.path.join(self.ordner.name, "amw-konfig.php")
        hashwert = subprocess.run([PHP, "-r", "echo password_hash('chef-passwort-1', PASSWORD_DEFAULT);"],
                                  capture_output=True, text=True).stdout.strip()
        with open(konfig, "w", encoding="utf-8") as f:
            f.write(f"<?php return ['sqlite' => {json.dumps(online.replace(os.sep, '/'))}, 'benutzer' => 'chef',"
                    f" 'passwort_hash' => '{hashwert}', 'nur_https' => false];\n")
        port = freier_port()
        srv = subprocess.Popen([PHP, "-d", "extension=pdo_sqlite", "-d", "extension=mbstring", "-d", "extension=curl", "-S",
                                f"127.0.0.1:{port}", "-t", os.path.join(WURZEL, "web")], env={**os.environ, "AMW_KONFIG": konfig},
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(srv.wait, 10)
        self.addCleanup(srv.terminate)
        basis = f"http://127.0.0.1:{port}/"
        for _ in range(100):
            try:
                urllib.request.urlopen(basis, timeout=2).read()
                break
            except OSError:
                time.sleep(0.1)
        return basis

    def zahl(self):
        import hashlib, hmac, struct
        h = hmac.new(base64.b32decode(self.GEHEIM), struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest()
        o = h[19] & 0x0F
        return str((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 1000000).zfill(6)

    def anmelden(self):
        self.tab.senden("Page.navigate", url=self.basis)
        self.warten("document.querySelector('input[name=passwort]')")
        self.tab.js("{ const f = document.querySelector('input[name=passwort]').form;"
                    " f.querySelector('[name=benutzer]').value = 'chef'; f.querySelector('[name=passwort]').value = 'chef-passwort-1';"
                    f" f.querySelector('[name=code]').value = '{self.zahl()}'; f.submit(); }}")
        self.warten("typeof zeige === 'function'", 15)
