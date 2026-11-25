"""A1972 (Marcel W2464, TH156), A2018: Themen-Seite – über der Liste höchstens EINE Zeile und nur, wenn der Mensch handeln muss
(„Wartet auf dich: 1 Thema · 1 Meilenstein“, je mit Sprung); keine Leiste (die Schritte zeigt der Projektweg), keine Zahlenkette, kein „Konzept fertig“, keine Co/Lead-Interna („nichts zu bauen … wartet auf den Co“). Bilder PC/Handy × hell/dunkel, DE/EN
über AMW_RUNDGANG_BILDER."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
from amw import kern, planung, themen, tore
from tests.rundgang import Rundgang

UNTER = ("(() => { const k = document.querySelector('#inhalt .seitenkopf'); const z = [];"
         " for (let e = k.nextElementSibling; e && !e.classList.contains('th-kasten'); e = e.nextElementSibling)"
         " if (e.offsetHeight > 0 && !e.classList.contains('th-stand')) z.push(e.innerText.trim()); return z; })()")       # sichtbare Zeilen zwischen Leiste und Liste


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

    LISTE = "document.querySelector('.th-liste .th-zeile')"
    DICH = "document.querySelector('#inhalt .tore-dich')"

    def test_nur_eine_zeile(self):
        """Regeln 3, 5, 6, 7: Werte statt Sätze, Maschinerie unsichtbar, Anzahl + Sprung, Details auf Klick."""
        self.groesse("pc")
        self.oeffnen("themen", self.LISTE + f" && {self.DICH}")
        self.assertIsNone(self.tab.js("document.querySelector('#inhalt .tore-leiste, #inhalt .tor')"))
        self.assertEqual(self.tab.js(UNTER), ["Wartet auf dich: 1 Thema · 1 Meilenstein"])                 # genau EINE Zeile
        text = self.tab.js("document.querySelector('#inhalt').innerText")
        for weg in ("Konzept ·", "Konzept fertig", "von 2 Themen", "wartet auf den Co", "nichts zu bauen", "Meilensteinen freigegeben"):
            self.assertNotIn(weg, text, weg)

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
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, thema_freigabe="co+lead", grobplan_freigabe="co+lead", feinplan_freigabe="co+lead", abschluss_freigabe="co+lead")         # Meilensteine geben Co und Lead frei
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
        self.tab.js("sprache_setzen('de')")

    def test_bilder(self):
        """Regel 8/9: PC und Handy, hell und dunkel, nichts über den Rand – Grunddesign bleibt (Bilder über AMW_RUNDGANG_BILDER)."""
        rand = ("document.documentElement.scrollWidth > innerWidth + 1 || [...document.querySelectorAll('#inhalt .th-stand, #inhalt .bereich-reihe,"
                " #inhalt .tore-dich')].some(e => e.scrollWidth > e.clientWidth + 1)")
        for g in ("pc", "handy"):
            for th in ("hell", "dunkel"):
                self.assertEqual(self.besuchen("themen", "themen-zeile", bereit=self.LISTE + f" && {self.DICH}", g=g, t=th), [], f"{g} {th}")
                self.assertFalse(self.tab.js(rand), f"{g} {th}")
        self.groesse("pc")
        self.oeffnen("themen", self.LISTE + f" && {self.DICH}")
        self.tab.js("sprache_setzen('en')")
        self.warten(self.DICH + ".innerText.startsWith('Waiting')")
        self.pruefen("themen-zeile-en", "pc", "hell")
        self.tab.js("sprache_setzen('de')")
