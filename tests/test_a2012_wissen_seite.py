"""A2012 (Kleinprobe A2008 D1900 v2, TL #33784): Wissen hat vier Reiter – Beschlüsse (Filter Beschlüsse · Regeln · Deine Worte ·
Notizen, Liste links, Eintrag rechts), Dokumente, Nachrichten, Mitlesen (nur lesen). Themen und Versionshinweise stehen beim Projektweg;
alte Adressen leiten um. Dazu je Ort ein Rundgang in allen Größen und Themen (TH156 Regel 1–9: Funde der Bildprüfung)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner

from amw import db, kern, wissen
from tests.rundgang import Rundgang


class Wissen(Rundgang):
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        self.b1 = wissen.beschluss_neu(self.con, self.pid, "TL", "Farbe nur bei Handlungsbedarf",
                                       "Rahmen und Farbe stehen nur dort, wo du etwas tun musst.", "deine Antwort")
        self.b2 = wissen.beschluss_neu(self.con, self.pid, "TL", "Passkey statt Passwort", "Neue Konten melden sich mit Passkey an.", "F9")
        with db.schreiben(self.con):
            db.einfuegen(self.con, "wortlaut", projekt_id=self.pid, zeit_utc=db.jetzt(), kanal="seite", text="Weniger ist mehr.\nIch will sehen, was ich tun muss.",
                         erfasst_von="TL", erfasst_utc=db.jetzt())
        kern.posten(self.con, self.pid, "CC1", "TL", "info", "Nur unter uns: A12 ist grün")

    def reiter(self):
        return self.tab.js("[...document.querySelectorAll('#inhalt .bereich-reiter button')].map(b => b.textContent)")

    def test_vier_reiter_filter_liste_und_eintrag(self):
        self.groesse("pc")
        self.oeffnen("wissen", "document.querySelector('.ws-raster')")
        self.assertEqual(self.reiter(), ["Beschlüsse", "Dokumente", "Nachrichten", "Mitlesen"])
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.ws-seg button')].map(b => b.dataset.f)"), ["beschluesse", "regeln", "wortlaut", "notizen"])
        self.assertEqual(self.tab.js("document.querySelectorAll('.ws-zeile').length"), 2)
        self.assertTrue(self.tab.js("document.querySelector('.ws-zeile').classList.contains('an')"))          # am PC gleich der erste rechts
        self.tab.js("[...document.querySelectorAll('.ws-zeile')].find(z => z.textContent.includes('Farbe')).click()")
        self.warten("document.querySelector('.ws-eintrag').textContent.includes('Rahmen und Farbe stehen nur dort')")
        self.tab.js("document.querySelector('.ws-seg [data-f=wortlaut]').click()")
        self.warten("document.querySelector('.ws-seg .an')?.dataset.f === 'wortlaut' && document.querySelector('.ws-zeile')")
        self.assertEqual(self.tab.js("document.querySelector('.ws-zeile .ws-titel').textContent"), "Weniger ist mehr.")   # erste Zeile als Titel
        self.assertIn("Ich will sehen", self.tab.js("document.querySelector('.ws-eintrag').textContent"))
        self.tab.js("document.querySelector('.ws-seg [data-f=notizen]').click()")
        self.warten("document.querySelector('.ws-leer')")                                                    # ruhiger Leerzustand
        self.assertEqual(self.tab.js("document.querySelector('.ws-leer').textContent"), "Keine Notizen.")

    def test_am_handy_liste_dann_eintrag_mit_zurueck(self):
        self.groesse("handy")
        self.oeffnen("wissen", "document.querySelector('.ws-raster')")
        self.assertFalse(self.tab.js("document.querySelector('.ws-eintrag').offsetParent !== null"))            # erst nur die Liste
        self.tippen(".ws-zeile")
        self.warten("document.querySelector('.ws-raster.detail') && document.querySelector('.ws-liste').offsetParent === null")
        self.tippen(".ws-eintrag .nr-zurueck")
        self.warten("!document.querySelector('.ws-raster.detail')")

    def test_mitlesen_nur_lesen_und_eigener_reiter(self):
        self.groesse("pc")
        self.oeffnen("teamchat", "document.querySelector('.tc-eintrag')")
        self.assertEqual(self.tab.js("document.querySelector('.bereich-reihe .an')?.textContent"), "Mitlesen")
        self.assertFalse(self.tab.js("!!document.querySelector('#inhalt textarea')"))                       # kein Eingabefeld
        self.assertFalse(self.tab.js("!!document.querySelector('#inhalt .nr-reiter')"))                     # keine zweite Reiterzeile
        self.oeffnen("nachrichten", "document.querySelector('.nr-reiter')")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.nr-reiter button')].map(b => b.textContent.replace(/\\d+$/, ''))"),
                         ["An dich", "Gesendet", "Lead-Runde"])

    def test_alte_adressen_und_versionshinweise_beim_projektweg(self):
        self.groesse("pc")
        self.oeffnen("releases", "document.querySelector('.bereich-reihe .an')")
        self.assertEqual(self.tab.js("document.querySelector('.bereich-reihe .an').dataset.s"), "releases")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('nav a[data-sicht].an')].map(a => a.dataset.sicht)"), ["projektweg"])
        self.oeffnen("ergebnisse", "document.querySelector('#inhalt .bereich-reiter')")
        self.assertEqual(self.tab.js("document.querySelector('#inhalt .bereich-reiter .an').textContent"), "Dokumente")
        self.oeffnen("wissen", "document.querySelector('.ws-raster')")
        self.tab.js("zustand.wissenReiter = 'themen'; void zeige('wissen')")                                 # alter Reiter „Themen“
        self.warten("zustand.sicht === 'themen'")

    def test_rundgang(self):
        for ort, sicht, bereit, tun, danach in (
                ("wissen-beschluesse", "wissen", "document.querySelector('.ws-raster')", None, None),
                ("wissen-wortlaut", "wissen", "document.querySelector('.ws-raster')", "document.querySelector('.ws-seg [data-f=wortlaut]').click()",
                 "document.querySelector('.ws-seg .an')?.dataset.f === 'wortlaut'"),
                ("wissen-leer", "wissen", "document.querySelector('.ws-raster')", "document.querySelector('.ws-seg [data-f=notizen]').click()",
                 "document.querySelector('.ws-leer')"),
                ("wissen-mitlesen", "teamchat", "document.querySelector('.tc-eintrag')", None, None),
                ("wissen-dokumente", "dokumente", "document.querySelector('#inhalt .bereich-reiter')", None, None)):   # F5398: Bestand, TH156 1–9
            with self.subTest(ort=ort):
                self.ueberall(sicht, ort, bereit=bereit, tun=tun, danach=danach)
