"""Bedienbarkeits-Rundgang Teil 1 (A1614): Vollbild am Handy immer schließbar; Start, Nachrichten, Fragen, Betrieb,
Einstellungen, Agenten-Dialog mit ⋯-Menü und Startbefehl – je PC und Handy, hell und dunkel (Gerüst: tests/rundgang.py).
Weitere Seiten hängen als eigene Testdateien an dasselbe Gerüst."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime
import os
import struct
import unittest
import zlib

from amw import benutzer, db, dokumente, herzschlag, kern
from tests.rundgang import OnlineRundgang, Rundgang


def png(breite=1600, hoehe=1000):
    """Ein echtes (einfarbiges) PNG – damit das Vollbild ein Bild mit Maßen hat."""
    zeile = b"\x00" + b"\x30\x60\x90" * breite
    def stueck(art, daten):
        return struct.pack(">I", len(daten)) + art + daten + struct.pack(">I", zlib.crc32(art + daten) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + stueck(b"IHDR", struct.pack(">IIBBBBB", breite, hoehe, 8, 2, 0, 0, 0))
            + stueck(b"IDAT", zlib.compress(zeile * hoehe, 9)) + stueck(b"IEND", b""))


# Vollbild zu UND sein Eintrag im Verlauf abgebaut: ✕/Esc rufen history.back() – das läuft verzögert; lädt der Test vorher
# schon die nächste Seite, springt der späte „Zurück“ dorthin zurück (Gesamtlauf 1.87.4: Knopf „Vollbild“ kam nie)
VB_ZU = "!document.querySelector('.vb') && !(history.state && history.state.amwVollbild)"


class Daten:
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid, "CC2")
        benutzer.neu(self.con, kern.ENTWICKLER, "neuling")                         # wartet auf Freigabe (Benutzer-Verwaltung)
        jetzt = datetime.datetime.now(datetime.timezone.utc)                       # Betrieb › „Wofür das Geld geht“ (A1642)
        z = lambda m: (jetzt - datetime.timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with db.schreiben(self.con):
            cc1 = self.con.execute("SELECT id FROM agent WHERE kennung = 'CC1'").fetchone()[0]
            sid = db.einfuegen(self.con, "sitzung", agent_id=cc1, gestartet_utc=z(60), zustand="beendet", beendet_utc=z(1))
            for m, usd in ((50, 1.0), (40, 2.5), (30, 3.0), (20, 6.25)):
                db.einfuegen(self.con, "verbrauch", sitzung_id=sid, agent="CC1", zeit_utc=z(m), kosten_usd=usd)
            n = kern._posten(self.con, self.pid, "AMW", "CC1", "freigabe", "L9 ist dran – jetzt starten: ein sehr langer Lauf-Titel zum Umbrechen")
            self.con.execute("UPDATE empfang SET geweckt_utc = ? WHERE nachricht_id = ?", (z(45), n[0] if isinstance(n, tuple) else n))
        herzschlag._zuruecksetzen()                                                 # Betrieb › Dienst (A1655): je Teil ein Herzschlag
        self.addCleanup(herzschlag._zuruecksetzen)
        herzschlag.schlag("hauptschleife", 0.04)
        herzschlag.schlag("dateiaustausch", 0.31)
        herzschlag._stand["dateiaustausch"].update(neustarts=1, neu_zeit=jetzt.timestamp() - 600)   # vor 10 Minuten neu gestartet
        herzschlag.schlag("synchronisierung", 2.6, ConnectionError("Online-Speicher nicht erreichbar"))
        herzschlag.schlag("ki", 0.02)
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Seite bauen mit einem recht langen Titel, der am Handy umbrechen muss", "CC1")
        kern.posten(self.con, self.pid, "CC1", "TL", "info", "Stand: Seite gebaut, Bilder liegen bei", text="Mehr Text\nüber zwei Zeilen")
        kern.posten(self.con, self.pid, "TL", "CC1", "auftrag", "Bitte die Seite fürs Handy prüfen", aufgabe_id=aid)
        kern.posten(self.con, self.pid, "CC1", "Entwickler", "info", "Seite fürs Handy ist fertig – bitte einmal ansehen")
        self.dok = {}
        for name, inhalt, art, titel in (("bild.png", png(), "bild", "Startseite am Handy"),
                                         ("entwurf.html", b"<!doctype html><title>M</title><body style='margin:0'><h1>Mockup</h1>", "mockup", "Entwurf Startseite")):
            pfad = os.path.join(self.ordner.name, name)
            with open(pfad, "wb") as f:
                f.write(inhalt)
            self.dok[art] = dokumente.ablegen(self.con, self.pid, "TL", pfad, titel, art, aufgabe=aid)


class Vollbild(Daten, Rundgang):
    """Marcel 12.11.: Am Handy ein Dokument im Vollbild – das ✕ lag außerhalb des Bildschirms. Jetzt: ✕ fest oben rechts im
    sichtbaren Bereich; Esc, Zurück und ✕ schließen nur das Vollbild (der Dokument-Dialog darunter bleibt)."""

    def vollbild(self, art, g):
        self.groesse(g)
        self.oeffnen("dokumente", "document.querySelector('.dk-karte')")
        self.tab.js(f"dokumentDialog({self.dok[art]})")
        self.warten("[...document.querySelectorAll('.dialog-hg .knopf')].some(k => k.textContent === 'Vollbild')")
        self.tab.js("[...document.querySelectorAll('.dialog-hg .knopf')].find(k => k.textContent === 'Vollbild').click()")
        self.warten("document.querySelector('.vb .vb-zu')")

    def test_bild_und_mockup_am_handy_und_pc_schliessbar(self):
        for art in ("bild", "mockup"):
            for g in ("handy", "pc"):
                with self.subTest(art=art, groesse=g):
                    self.vollbild(art, g)
                    self.assertEqual(self.pruefen(f"vollbild-{art}", g, "dunkel"), [])
                    self.tippen(".vb > .vb-zu")                               # echter Tipp auf das ✕
                    self.warten(VB_ZU)
                    self.assertTrue(self.tab.js("!!document.querySelector('.dialog-hg')"), "Dokument-Dialog bleibt offen")

    def test_esc_und_zurueck_schliessen_nur_das_vollbild(self):
        self.vollbild("bild", "handy")
        self.esc()
        self.warten(VB_ZU)
        self.assertTrue(self.tab.js("!!document.querySelector('.dialog-hg')"))
        self.tab.js("document.querySelector('.dialog-hg').remove()")
        self.vollbild("mockup", "handy")
        self.tab.js("history.back()")                                        # Zurück-Taste bzw. Wischgeste am Handy
        self.warten(VB_ZU)
        self.assertEqual(self.tab.js("location.hash"), "#dokumente")          # bleibt auf der Seite
        self.assertTrue(self.tab.js("!!document.querySelector('.dialog-hg')"))
        self.tippen(".dialog-hg .dialog-zu")
        self.warten("!document.querySelector('.dialog-hg')")
        self.assertEqual(self.tab.js("location.hash"), "#dokumente")


class Seiten(Daten, Rundgang):
    """Jede Seite meines Teils in beiden Größen und Themen."""

    def test_start(self):
        self.ueberall("start", bereit="document.querySelector('#team [data-k]')")

    def test_nachrichten_eingang_und_gesendet(self):
        self.ueberall("nachrichten", "nachrichten-eingang", bereit="document.querySelector('.nr-liste')")
        self.ueberall("nachrichten", "nachrichten-gesendet", bereit="document.querySelector('.nr-liste')",
                      tun="[...document.querySelectorAll('.reiter a, .reiter button')].find(x => /Gesendet|Sent/.test(x.textContent))?.click()",
                      danach="true")

    def test_fragen(self):
        self.ueberall("fragen", bereit="document.querySelector('#inhalt h2, #inhalt .karte')")

    def test_betrieb(self):
        self.ueberall("betrieb", bereit="document.querySelector('#inhalt .karte') && document.querySelector('.anl-anteil')")   # mit „Wofür das Geld geht“
        self.ueberall("betrieb", "betrieb-geld", bereit="document.querySelector('.anl-anteil')",
                      tun="document.querySelector('.anl-anteil').closest('table').scrollIntoView({ block: 'center' })", danach="true")

    def test_dienst_gesundheit(self):
        """A1655: Betrieb › Dienst zeigt je Teil die Farbe; steht ein Teil, warnt die Startseite mit einem Band."""
        self.ueberall("betrieb", "betrieb-dienst", bereit="document.querySelector('.punkt.bernstein') && document.querySelector('.punkt.gruen')"
                      " && !document.getElementById('inhalt').innerText.split(String.fromCharCode(10)).some(z => z.trim() === 'null')",   # kein „null“ als Text
                      tun="[...document.querySelectorAll('#inhalt h2')].find(h => h.textContent.startsWith('Dienst') || h.textContent.startsWith('Service')).scrollIntoView({ block: 'start' })",
                      danach="true")
        herzschlag._stand["hauptschleife"]["zeit"] -= 3600                                  # eine Stunde still: rot
        self.ueberall("start", "start-dienst-rot", bereit="[...document.querySelectorAll('.band-halt b')].some(b => /^(Dienst: Hauptschleife steht|Service: Main loop stalled)$/.test(b.textContent))")

    def test_einstellungen_pruefstufen_und_takt(self):
        """A1656: Einstellungen › Projekt mit Prüfstufen und Release-Takt; die Uhrzeit steht nur bei „täglich“ da."""
        finde = "[...document.querySelectorAll('#inhalt *')].find(e => e.children.length === 0 && /^(Prüfstufen|Review levels)$/.test(e.textContent.trim()))"
        self.ueberall("einstellungen", "einstellungen-release", bereit=finde,
                      tun=f"{finde}.scrollIntoView({{ block: 'center' }})", danach="true")
        zeit = self.tab.js("(() => { const s = [...document.querySelectorAll('#inhalt select')].find(x => x.querySelector('option[value=meilenstein]'));"
                           " const z = s.parentElement.querySelector('input[type=time]');"
                           " const vorher = getComputedStyle(z).display; s.value = 'taeglich'; s.dispatchEvent(new Event('change'));"
                           " return [vorher, getComputedStyle(z).display]; })()")
        self.assertEqual(zeit[0], "none")
        self.assertNotEqual(zeit[1], "none")

    def test_einstellungen(self):
        self.ueberall("einstellungen", bereit="document.querySelector('#inhalt .einst, #inhalt .karte')")


class Agent(Daten, Rundgang):
    """Agenten-Dialog (Übersicht, Gespräch), ⋯-Menü am Agenten und Startbefehl – je Größe und Thema."""
    START = "document.querySelector('#team [data-k]')"

    def test_dialog_uebersicht_und_gespraech(self):
        self.ueberall("start", "agent-uebersicht", bereit=self.START, tun="agentDialog('CC1')", danach="document.querySelector('.agent-dialog')")
        self.ueberall("start", "agent-gespraech", bereit=self.START, tun="agentDialog('CC1', 'gespraech')",
                      danach="document.querySelector('.agent-dialog')")

    def test_menue_am_agenten(self):
        self.ueberall("start", "agent-menue", bereit=self.START + " && document.querySelector('.mehr-knopf')",
                      tun="document.querySelector('.mehr-knopf').click()", danach="document.querySelector('.menue')")

    def test_startbefehl(self):
        self.ueberall("start", "agent-startbefehl", bereit=self.START, tun="startbefehlDialog('CC1')",
                      danach="document.querySelector('.dialog-hg')")


class Pruefer(Rundgang):
    """Der Rundgang selbst: jede Prüfung schlägt an, wenn man den Fehler absichtlich einbaut – sonst wäre „keine Funde“
    nichts wert."""

    def eingebaut(self, js):
        self.groesse("handy")
        self.oeffnen("start", "document.querySelector('#team [data-k]')")
        self.tab.js(js)
        return [f[1] for f in self.pruefen("pruefer", "handy", "dunkel")]

    def test_jede_pruefung_schlaegt_an(self):
        self.assertEqual(self.eingebaut("0"), [])                                        # ohne Einbau: sauber
        self.assertTrue(any("seitwärts" in f for f in self.eingebaut(
            "document.querySelector('#inhalt').append(Object.assign(document.createElement('div'), { style: 'width:2000px;height:5px' }))")))
        self.assertTrue(any("Konsole" in f for f in self.eingebaut("console.error('kaputt')")))
        self.assertTrue(any("außerhalb des Bildschirms" in f for f in self.eingebaut(
            "{ const hg = Object.assign(document.createElement('div'), { className: 'dialog-hg' }); hg.append(Object.assign("
            "document.createElement('div'), { className: 'karte dialog' })); document.body.append(hg); }"
            " setTimeout(() => {}, 0); new Promise(r => setTimeout(r, 50)).then(() => {"
            " document.querySelector('.dialog-hg .dialog-zu').style.cssText = 'position:fixed;top:-80px;left:10px' })")))
        self.assertTrue(any("Knopf ohne Namen" in f for f in self.eingebaut(
            "document.querySelector('#inhalt').append(document.createElement('button'))")))
        self.assertTrue(any("tabindex" in f for f in self.eingebaut(
            "document.querySelector('#inhalt').append(Object.assign(document.createElement('a'), { tabIndex: 3, textContent: 'x', href: '#' }))")))
        self.assertTrue(any("abgeschnitten" in f for f in self.eingebaut(
            "document.querySelector('#inhalt').append(Object.assign(document.createElement('button'), { className: 'klein-knopf',"
            " textContent: 'Ein sehr langer Knopftext, der nicht passt', style: 'width:60px;overflow:hidden;white-space:nowrap' }))")))


class Online(Daten, OnlineRundgang):
    """Die Online-Seite (echtes PHP, angemeldet wie ein Mensch): dieselben Seiten und Dialoge meines Teils."""
    START = "document.querySelector('#team [data-k]')"

    def test_seiten(self):
        self.ueberall("start", "online-start", bereit=self.START)
        self.ueberall("nachrichten", "online-nachrichten", bereit="document.querySelector('.nr-liste')")
        self.ueberall("fragen", "online-fragen", bereit="document.querySelector('#inhalt h2, #inhalt .karte')")
        self.ueberall("einstellungen", "online-einstellungen", bereit="document.querySelector('#inhalt .einst, #inhalt .karte')")

    def test_agent_dialog_und_menue(self):
        self.ueberall("start", "online-agent", bereit=self.START, tun="agentDialog('CC1')", danach="document.querySelector('.agent-dialog')")
        self.ueberall("start", "online-agent-menue", bereit=self.START + " && document.querySelector('.mehr-knopf')",
                      tun="document.querySelector('.mehr-knopf').click()", danach="document.querySelector('.menue')")

    def test_benutzer_online_freischalten(self):
        """A1615 a: Einstellungen › Benutzer auch online; „Freischalten“ zeigt den Code einmal im Dialog (mit ✕ im Bild)."""
        bereit = "document.querySelector('#e-benutzer .bn-zeile[data-name=neuling]')"
        self.ueberall("einstellungen", "online-benutzer", bereit=bereit)
        self.groesse("handy")
        self.oeffnen("einstellungen", bereit)
        self.tab.js("[...document.querySelectorAll('#e-benutzer .bn-zeile[data-name=neuling] button')].find(b => /Freischalten/.test(b.textContent)).click()")
        self.warten("/[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}/.test(document.querySelector('.dialog-hg')?.textContent || '')")
        self.assertEqual(self.pruefen("online-benutzer-code", "handy", "dunkel"), [])
        code = self.tab.js("document.querySelector('.dialog-hg').textContent.match(/[A-Z2-9]{4}(-[A-Z2-9]{4}){3}/)[0]")
        from amw import benutzer
        h = self.sp.ausfuehren([("SELECT code_hash FROM benutzer WHERE name = 'neuling'", [])])[0][0][0]
        self.assertEqual(h, benutzer.code_hash(code))                               # online steht nur der Hash
        self.ab.schritt(False)                                                       # der PC holt die Meldung ab und prüft nach
        st = self.sp.ausfuehren([("SELECT status FROM eingang WHERE weg = '/api/benutzer/code_online'", [])])[0]
        self.assertEqual([x[0] for x in st], ["erledigt"])


if __name__ == "__main__":
    unittest.main()
