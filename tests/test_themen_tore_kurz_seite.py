"""A1972 (Marcel W2464, TH156): Themen-Seite – oben nur die fünf Tor-Chips, darunter höchstens EINE Zeile und nur, wenn der Mensch
handeln muss („Wartet auf dich: 1 Thema · 1 Meilenstein“, je mit Sprung); Werte eines Tors auf Klick am Chip; keine Zahlenkette,
kein „Konzept fertig“, keine Co/Lead-Interna („nichts zu bauen … wartet auf den Co“). Bilder PC/Handy × hell/dunkel, DE/EN
über AMW_RUNDGANG_BILDER."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
from amw import kern, planung, themen, tore
from tests.rundgang import Rundgang

UNTER = ("(() => { const k = document.querySelector('#inhalt .th-stand'); const z = [];"
         " for (let e = k.nextElementSibling; e && !e.classList.contains('th-kasten'); e = e.nextElementSibling)"
         " if (e.offsetHeight > 0) z.push(e.innerText.trim()); return z; })()")       # sichtbare Zeilen zwischen Leiste und Liste


class ToreKurz(Rundgang):
    def daten(self):                                                     # TL (Lead) legt schon das Gerüst an
        kern.agent_neu(self.con, self.pid, "CC1")
        self.frei = themen.neu(self.con, self.pid, "TL", "Ziele und Rahmen", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", self.frei, "Leitstand für einen Menschen mit KI-Agenten.")
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.frei)
        self.dich = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", self.dich, "Wer die Online-Seite öffnet, meldet sich mit seinem Firmen-Konto an.")
        themen.nichts_zu_bauen(self.con, self.pid, "TL", f"TH{self.frei}", "nur Rahmen")   # Co/Lead-Intern: nie auf dieser Seite
        self.m1 = planung.bogen_neu(self.con, self.pid, "TL", "Anmelden und Nachrichten", abnahme="Vorführung")

    LISTE = "document.querySelector('.th-liste .th-zeile') && document.querySelector('#inhalt .th-tore .tore-leiste')"
    DICH = "document.querySelector('#inhalt .tore-dich')"

    def test_nur_chips_und_eine_zeile(self):
        """Regeln 3, 5, 6, 7: Werte statt Sätze, Maschinerie unsichtbar, Anzahl + Sprung, Details auf Klick."""
        self.groesse("pc")
        self.oeffnen("themen", self.LISTE + f" && {self.DICH}")
        chips = self.tab.js("[...document.querySelectorAll('#inhalt .th-tore .tor')].map(e => e.tagName + ':' + e.dataset.t + ':' + e.className)")
        self.assertEqual(chips, ["BUTTON:konzept:tor jetzt", "BUTTON:grobplanung:tor spaeter", "BUTTON:feinplanung:tor spaeter",
                                 "BUTTON:umsetzung:tor spaeter", "BUTTON:abschluss:tor spaeter"])
        self.assertEqual(self.tab.js(UNTER), ["Wartet auf dich: 1 Thema · 1 Meilenstein"])                 # genau EINE Zeile
        text = self.tab.js("document.querySelector('#inhalt').innerText")
        for weg in ("Konzept ·", "Konzept fertig", "von 2 Themen", "wartet auf den Co", "nichts zu bauen", "Meilensteinen freigegeben"):
            self.assertNotIn(weg, text, weg)
        self.assertTrue(self.tab.js("document.querySelector('#inhalt .tore-info').hidden"))           # Details erst auf Klick
        self.tab.js("document.querySelector('#inhalt .tor[data-t=konzept]').click()")
        self.assertEqual(self.tab.js("document.querySelector('#inhalt .tore-info').innerText"), "Konzept · 1 von 2 Themen freigegeben")
        self.assertEqual(self.tab.js("document.querySelector('#inhalt .tor[data-t=konzept]').getAttribute('aria-expanded')"), "true")
        self.tab.js("document.querySelector('#inhalt .tor[data-t=grobplanung]').click()")
        self.assertEqual(self.tab.js("document.querySelector('#inhalt .tore-info').innerText"),
                         "Grobplanung · 1 von 1 Themen in Meilensteinen · 0 von 1 Meilensteinen freigegeben")   # „nichts zu bauen“ zählt
        self.tab.js("document.querySelector('#inhalt .tor[data-t=grobplanung]').click()")             # zweiter Klick schließt
        self.assertTrue(self.tab.js("document.querySelector('#inhalt .tore-info').hidden"))

    def test_spruenge(self):
        """Regel 6: „1 Thema“ öffnet das Thema, das auf dich wartet; „1 Meilenstein“ führt zu Planung › Meilensteine."""
        self.groesse("pc")
        self.oeffnen("themen", self.LISTE + f" && {self.DICH}")
        self.tab.js(f"{self.DICH}.querySelector('[data-sprung=themen]').click()")
        self.warten("document.querySelector('.th-thema h2')?.textContent === 'Anmeldung'")
        self.warten(self.DICH)
        self.tab.js(f"{self.DICH}.querySelector('[data-sprung=meilensteine]').click()")
        self.warten("zustand.sicht === 'planung' && document.querySelector('#inhalt .pm-ansicht')")

    def test_ohne_handlungsbedarf_keine_zeile(self):
        """Regel 4/7: muss der Mensch nichts tun, steht unter den Chips nichts – auch nicht, wenn Co und Lead freigeben."""
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, thema_freigabe="co+lead")         # Meilensteine geben Co und Lead frei
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, f"TH{self.dich}")
        self.assertEqual(tore.stand(self.con, self.pid)["fuer_dich"], {"themen": 0, "meilensteine": 0})
        self.groesse("handy")
        self.oeffnen("themen", self.LISTE)
        self.assertEqual(self.tab.js(UNTER), [])
        self.assertIsNone(self.tab.js(self.DICH))

    def test_englisch(self):
        """Regel 8: Deutsch und Englisch."""
        self.groesse("pc")
        self.oeffnen("themen", self.LISTE)
        self.tab.js("sprache_setzen('en')")
        self.warten(self.DICH + " && " + self.DICH + ".innerText.startsWith('Waiting')")
        self.assertEqual(self.tab.js(UNTER), ["Waiting for you: 1 topic · 1 milestone"])
        self.tab.js("document.querySelector('#inhalt .tor[data-t=konzept]').click()")
        self.assertEqual(self.tab.js("document.querySelector('#inhalt .tore-info').innerText"), "Concept · 1 of 2 topics approved")
        self.tab.js("sprache_setzen('de')")

    def test_bilder(self):
        """Regel 8/9: PC und Handy, hell und dunkel, nichts über den Rand – Grunddesign bleibt (Bilder über AMW_RUNDGANG_BILDER)."""
        rand = ("document.documentElement.scrollWidth > innerWidth + 1 || [...document.querySelectorAll('#inhalt .th-stand, #inhalt .tore-leiste,"
                " #inhalt .tore-dich')].some(e => e.scrollWidth > e.clientWidth + 1)")
        auf = "document.querySelector('#inhalt .tor[data-t=konzept]').click()"
        for ort, tun, danach in (("themen-tore", None, None), ("themen-tore-klick", auf, "!document.querySelector('#inhalt .tore-info').hidden")):
            for g in ("pc", "handy"):
                for th in ("hell", "dunkel"):
                    self.assertEqual(self.besuchen("themen", ort, bereit=self.LISTE + f" && {self.DICH}", tun=tun, danach=danach, g=g, t=th),
                                     [], f"{ort} {g} {th}")
                    self.assertFalse(self.tab.js(rand), f"{ort} {g} {th}")
        self.groesse("pc")
        self.oeffnen("themen", self.LISTE + f" && {self.DICH}")
        self.tab.js("sprache_setzen('en')")
        self.warten(self.DICH + ".innerText.startsWith('Waiting')")
        self.pruefen("themen-tore-en", "pc", "hell")
        self.tab.js("sprache_setzen('de')")
