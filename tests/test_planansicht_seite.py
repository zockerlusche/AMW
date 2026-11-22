"""A1950 (K6) in der Seite: Planung › Meilensteine/Pakete nach der Kleinprobe D1365 – mit Themen startet die Planung auf
„Meilensteine“; Tor-Zeile; Freigeben je Meilenstein und Plan; „Jetzt starten“ erst, wenn alles frei ist; am Handy zuerst die
Liste und nichts über den Rand (W2431). Bilder PC/Handy hell/dunkel über AMW_RUNDGANG_BILDER."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
from amw import arbeitspaket, kern, planansicht, planung, themen
from tests.rundgang import Rundgang


class PlanAnsicht(Rundgang):
    def daten(self):                                                     # TL (Lead) legt schon das Gerüst an
        kern.agent_neu(self.con, self.pid, "CC1")
        th = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        self.m1 = planung.bogen_neu(self.con, self.pid, "TL", "Anmelden und Nachrichten", abnahme="Vorführung")
        self.m2 = planung.bogen_neu(self.con, self.pid, "TL", "Sicherung", abnahme="Bericht")
        a1 = planung.schritt_setzen(self.con, self.pid, "TL", titel="Anmeldung mit Firmen-Konto", bogen_id=self.m1, agent="CC1")
        a2 = planung.schritt_setzen(self.con, self.pid, "TL", titel="Tests für die Anmeldung", bogen_id=self.m1, nach=[a1])
        arbeitspaket.setzen(self.con, self.pid, "TL", a2, art="p", modell="sonnet")
        themen.verweise_setzen(self.con, self.pid, "TL", a1, [f"TH{th}"])

    STAND = "document.querySelector('#inhalt .pm-stand span')?.textContent"
    BEREIT = "document.querySelector('#inhalt .pm-ansicht .th-zeile')"

    def ueber_rand(self):
        return self.tab.js("document.documentElement.scrollWidth > innerWidth + 1 || [...document.querySelectorAll('header, nav, .kopf,"
                           " .pm-stand, .bereich-reiter, .th-kopf')].some(e => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX"
                           " !== 'auto')")

    def test_grob_freigeben_und_tor_zeile(self):
        self.groesse("pc")
        self.oeffnen("planung", self.BEREIT)
        self.assertEqual(self.tab.js("document.querySelector('#inhalt .pm-ansicht').dataset.pm"), "grob")     # mit Themen: Meilensteine
        self.assertEqual(self.tab.js(self.STAND), "Grobplanung · 0 von 2 Meilensteinen freigegeben")
        self.tab.js("document.querySelector('.th-knoepfe button[data-h=freigeben]').click()")
        self.warten(f"{self.STAND} === 'Grobplanung · 1 von 2 Meilensteinen freigegeben'")
        self.warten("document.querySelector('.pm-frei-von')?.textContent.startsWith('Freigegeben von dir')")  # wer, als Fakt

    def test_handy_zuerst_die_liste_nichts_ueber_den_rand(self):
        self.groesse("handy")
        for th in ("hell", "dunkel"):
            self.oeffnen("planung", self.BEREIT)
            self.thema(th)
            self.assertTrue(self.tab.js("getComputedStyle(document.querySelector('#inhalt .th-thema')).display === 'none'"))
            self.assertFalse(self.ueber_rand(), th)

    def test_pakete_und_jetzt_starten(self):
        for bid in (self.m1, self.m2):
            planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, bid, "grob")
        self.groesse("pc")
        self.tab.senden("Page.navigate", url=f"{self.basis}?r=1#planung")
        self.warten("typeof zustand === 'object' && typeof zeige === 'function'")
        self.tab.js("zustand.planReiter = 'pakete'; void zeige('planung', true)")
        self.warten("document.querySelector('#inhalt .pm-ansicht')?.dataset.pm === 'plan' && document.querySelector('.pm-pakete')")
        self.assertEqual(self.tab.js("document.querySelectorAll('.pm-pakete tbody tr:not(.pm-summe)').length"), 2)
        self.assertFalse(self.tab.js("!!document.querySelector('.pm-start-knopf')"))           # erst wenn alles frei
        self.tab.js("document.querySelector('.th-knoepfe button[data-h=freigeben]').click()")
        self.warten("document.querySelector('.pm-start-knopf')")
        self.tab.js("window.confirm = () => true; document.querySelector('.pm-start-knopf').click()")
        self.warten(f"({self.STAND} || '').startsWith('Umsetzung')")
        self.assertEqual(planung.bogen_zeile(self.con, self.pid, self.m1)["status"], "aktiv")

    def test_entwurf_des_planers_ja_legt_an(self):
        """A1940: ein offener Entwurf steht oben in „Meilensteine“; „Ja – anlegen“ legt Meilenstein und Pakete an."""
        from amw import planer
        th = self.con.execute("SELECT id FROM thema LIMIT 1").fetchone()[0]
        planer.entwurf_eintragen(self.con, self.pid, th, 1, {"meilensteine": [{"schluessel": "M1", "titel": "Online anmelden",
                                                                                "endet_mit": "vorfuehrung"}],
                                                             "pakete": [{"schluessel": "P1", "meilenstein": "M1", "titel": "Login-Maske",
                                                                         "auftrag": "Bauen.", "groesse": "S", "art": "oberflaeche",
                                                                         "fertig_quelle": "release"}]}, modell="sonnet", usd=0.21)
        self.groesse("pc")
        self.oeffnen("planung", "document.querySelector('#inhalt .pm-entwurf')")
        self.assertIn("1 Meilenstein(e), 1 Pakete", self.tab.js("document.querySelector('.pm-entwurf summary').textContent"))
        self.tab.js("document.querySelector('.pm-entwurf').open = true; document.querySelector('.pm-entwurf button[data-h=plan-ja]').click()")
        self.warten("!document.querySelector('#inhalt .pm-entwurf') && [...document.querySelectorAll('.pm-zeile')].some(z => z.textContent.includes('Online anmelden'))")

    def test_bilder_entwurf(self):
        from amw import planer
        th = self.con.execute("SELECT id FROM thema LIMIT 1").fetchone()[0]
        planer.entwurf_eintragen(self.con, self.pid, th, 1, {"meilensteine": [{"schluessel": "M1", "titel": "Online anmelden",
                                                                                "endet_mit": "vorfuehrung"}],
                                                             "pakete": [{"schluessel": "P1", "meilenstein": "M1", "titel": "Login-Maske",
                                                                         "auftrag": "Bauen.", "groesse": "S", "art": "oberflaeche",
                                                                         "fertig_quelle": "release"},
                                                                        {"schluessel": "P2", "meilenstein": "M1", "titel": "Tests",
                                                                         "auftrag": "Tests.", "groesse": "S", "art": "mechanisch",
                                                                         "ausfuehrung": "p", "modell": "sonnet", "fertig_quelle": "commit",
                                                                         "nach": ["P1"], "abnahme_befehl": "python -m unittest tests.test_login"}]},
                                 modell="sonnet", usd=0.21)
        for g in ("pc", "handy"):
            for th_ in ("hell", "dunkel"):
                self.assertEqual(self.besuchen("planung", "planung-entwurf", bereit="document.querySelector('#inhalt .pm-entwurf')",
                                               tun="document.querySelector('.pm-entwurf').open = true", danach="document.querySelector('.pm-entwurf').open",
                                               g=g, t=th_), [], f"{g} {th_}")

    def test_bilder(self):
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "grob")
        wahl = lambda r: f"zustand.planReiter = '{r}'; void zeige('planung', true)"
        for g in ("pc", "handy"):
            for th in ("hell", "dunkel"):
                for r in ("meilensteine", "pakete"):
                    ort = f"planung-{r}"
                    tun = wahl(r) + ("; setTimeout(() => document.querySelector('#inhalt .th-zeile')?.click(), 300)" if g == "handy" and r == "pakete" else "")
                    self.assertEqual(self.besuchen("planung", ort, bereit=self.BEREIT, tun=tun,
                                                   danach=f"document.querySelector('#inhalt .pm-ansicht')?.dataset.pm === '{'grob' if r == 'meilensteine' else 'plan'}'",
                                                   g=g, t=th), [], f"{ort} {g} {th}")
