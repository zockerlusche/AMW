"""Themen-Bereich in der Seite (A1896): Liste mit je einem Status, Text als Ganzes, nur mögliche Handlungen; am Handy zuerst die
Liste (Auflage a); „neu prüfen“ mit Grund (Auflage c); „Für dich“ springt zum Thema; Unterschied zur Freigabe. Bilder
(Themen) PC/Handy hell/dunkel über AMW_RUNDGANG_BILDER – die Vorher-Bilder (Wissen › Themen) liegen als Dokumente vor."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
from amw import db, kern, themen
from tests.rundgang import Rundgang


class ThemenSeite(Rundgang):
    def daten(self):                                                     # TL (Lead) legt schon das Gerüst an
        kern.agent_neu(self.con, self.pid, "CC1")
        self.warte = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", self.warte, "Wer die Online-Seite öffnet, meldet sich mit seinem Firmen-Konto an.\n\n"
                                                             "Am PC braucht es keinen zweiten Faktor.")
        frei = themen.neu(self.con, self.pid, "TL", "Ziele und Rahmen", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", frei, "Leitstand für einen Menschen mit KI-Agenten.")
        with db.schreiben(self.con):
            self.con.execute("UPDATE thema_fassung SET zeit_utc = '2026-11-01T08:00:00Z' WHERE thema_id = ?", (frei,))
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, frei)
        pruef = themen.neu(self.con, self.pid, "TL", "Kopflose Arbeiter", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", pruef, "Kleine Pakete baut ein Arbeiter ohne Aufsicht.")
        with db.schreiben(self.con):
            self.con.execute("UPDATE thema_fassung SET zeit_utc = '2026-11-01T08:00:00Z' WHERE thema_id = ?", (pruef,))
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, pruef)
        with db.schreiben(self.con):
            self.con.execute("UPDATE plan_ereignis SET zeit_utc = CASE art WHEN 'thema_vorgelegt' THEN '2026-11-01T08:00:00Z'"
                             " ELSE '2026-11-01T09:00:00Z' END WHERE art IN ('thema_vorgelegt', 'thema_freigegeben')")
            db.einfuegen(self.con, "beschluss", projekt_id=self.pid, zeit_utc=db.jetzt(), stichwort="Arbeiter melden sich an", regel="x",
                         quelle="W1", thema="Kopflose Arbeiter", angelegt_von="TL", angelegt_utc=db.jetzt())
        themen.neu(self.con, self.pid, "TL", "Online-Seite", pfleger="CC1")
        self.geaendert = themen.neu(self.con, self.pid, "TL", "Nachrichten", pfleger="CC1")     # F5358: neue Vorlage nach der Freigabe
        themen.pflegen(self.con, self.pid, "CC1", self.geaendert, "An dich getrennt von Mitlesen.")
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.geaendert)
        themen.pflegen(self.con, self.pid, "CC1", self.geaendert, "An dich getrennt von Mitlesen.\n\nFragen bleiben ein eigener Menüpunkt.")

    LISTE = "document.querySelector('.th-liste .th-zeile')"

    def test_unterschied_zur_freigabe(self):
        self.oeffnen("themen", self.LISTE)
        self.tab.js(f"document.querySelector('.th-zeile[data-th=\"{self.geaendert}\"]').click()")
        self.warten("document.querySelector('.th-knoepfe button[data-h=unterschied]')")
        self.tab.js("document.querySelector('.th-knoepfe button[data-h=unterschied]').click()")
        self.warten("document.querySelector('.th-kasten .th-dazu')")
        self.assertEqual(self.tab.js("document.querySelector('.th-kasten .th-dazu').textContent"), "Fragen bleiben ein eigener Menüpunkt.")
        self.assertFalse(self.tab.js("!!document.querySelector('.th-kasten .th-weg')"))

    def test_liste_text_handlungen_freigeben(self):
        self.oeffnen("themen", self.LISTE)                                                      # direkt über die Adresse
        self.warten(f"{self.LISTE}?.dataset.th === '{self.warte}'")                           # wartende oben
        self.tab.js(f"{self.LISTE}.click()")
        self.warten("document.querySelector('.th-thema h2')?.textContent === 'Anmeldung'")
        text = self.tab.js("document.querySelector('#inhalt').innerText").lower()
        for teil in ("wartet auf dich: 2 themen", "anmeldung", "firmen-konto", "wartet auf dich"):   # A1972: Zeile statt Zahlenkette
            self.assertIn(teil, text)
        self.assertEqual(self.tab.js("document.querySelector('.th-thema h2').textContent"), "Anmeldung")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.th-knoepfe button')].map(b => b.dataset.h).join(',')"),
                         "freigeben,zurueck,bearbeiten,markieren")
        self.tab.js("document.querySelector('.th-knoepfe button[data-h=freigeben]').click()")
        self.warten(f"document.querySelector('.th-zeile[data-th=\"{self.warte}\"] .th-status.frei')")
        self.assertEqual(themen.status(self.con, themen.finden(self.con, self.pid, self.warte))["status"], "frei")

    def test_neu_pruefen_ruhig_mit_grund_in_der_liste(self):
        """P306 (1)+(2): „neu prüfen“ ist Arbeit der KI – ruhig grau wie „in Arbeit“, Farbe hat nur „wartet auf dich“; der Grund
        steht auch in der Listenzeile."""
        self.oeffnen("themen", self.LISTE)
        zeile = "document.querySelector('.th-zeile .th-status.pruefen').closest('.th-zeile')"
        self.warten(f"document.querySelector('.th-zeile .th-status.pruefen')")
        self.assertRegex(self.tab.js(f"{zeile}.querySelector('.th-grund-zeile')?.textContent || ''"), r"^wegen: B\d+ · \d\d\.\d\d\.$")
        farbe = "c => getComputedStyle(document.querySelector('.th-zeile .th-status.' + c)).color"
        self.assertEqual(self.tab.js(f"({farbe})('pruefen')"), self.tab.js(f"({farbe})('arbeit')"))
        self.assertNotEqual(self.tab.js(f"({farbe})('dich')"), self.tab.js(f"({farbe})('arbeit')"))

    def test_fuer_dich_springt_zum_thema(self):
        self.oeffnen("start", "[...document.querySelectorAll('.ue-zeile .ref')].some(r => r.textContent.startsWith('TH'))")
        self.tab.js("[...document.querySelectorAll('.ue-zeile')].find(z => z.querySelector('.ref')?.textContent === 'TH%d')"
                    ".querySelector('button').click()" % self.warte)
        self.warten("document.querySelector('.th-thema h2')?.textContent === 'Anmeldung'")

    def test_rundgang_vorher_nachher(self):
        for g in ("pc", "handy"):
            for th in ("hell", "dunkel"):
                # direkt über die Adresse (echtes Neuladen, kein Thema offen): über „start“ + zeige('themen') überschrieb die
                # langsam geladene Startseite unter Last die Themen wieder (L2882, sichtStart zeichnet nach await neu)
                self.assertEqual(self.besuchen("themen", "themen-nachher", bereit=self.LISTE, g=g, t=th), [], f"nachher {g} {th}")
            if g == "handy":                                             # Auflage (a): am Handy zuerst die Liste, kein Thema offen
                self.assertTrue(self.tab.js("getComputedStyle(document.querySelector('.th-thema')).display === 'none'"))


class ThemenTor(Rundgang):
    """A1913 (W2449): Kein Knopf zum Abschließen: das Freigeben des letzten offenen Themas fragt vorher „Damit ist der Schritt Konzept
    abgeschlossen“ – erst danach gilt es. Wo das Projekt steht, zeigt der Projektweg (A2018). Bilder vorher/nachher über AMW_RUNDGANG_BILDER."""

    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        frei = themen.neu(self.con, self.pid, "TL", "Ziele und Rahmen", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", frei, "Leitstand für einen Menschen mit KI-Agenten.")
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, frei)
        self.letzt = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", self.letzt, "Wer die Online-Seite öffnet, meldet sich mit seinem Firmen-Konto an.")
        weg = themen.neu(self.con, self.pid, "TL", "Altes Menü", pfleger="CC1")
        themen.markieren(self.con, self.pid, kern.ENTWICKLER, weg)                    # zählt nicht

    DICH = "document.querySelector('#inhalt .tore-dich')"
    OFFEN = ("document.querySelector('.th-zeile[data-th=\"%d\"]').click()",
             "document.querySelector('.th-thema h2')?.textContent === 'Anmeldung' && document.querySelector('.th-knoepfe button[data-h=freigeben]')")

    def test_letzte_freigabe_fragt_und_schliesst_das_tor(self):
        schon = len(themen.tor_ereignisse(self.con, self.pid))       # in daten() schloss das erste Thema allein das Tor schon einmal
        self.oeffnen("themen", f"document.querySelector('.th-liste .th-zeile') && {self.DICH}")
        self.assertIsNone(self.tab.js("document.querySelector('#inhalt .tor')"))
        self.assertEqual(self.tab.js(f"{self.DICH}.innerText"), "Wartet auf dich: 1 Thema")
        self.tab.js(self.OFFEN[0] % self.letzt)
        self.warten(self.OFFEN[1])
        self.tab.js("window.__fragen = []; window.confirm = x => { window.__fragen.push(x); return false; };"
                    " document.querySelector('.th-knoepfe button[data-h=freigeben]').click()")
        self.assertEqual(self.tab.js("window.__fragen"), ["Damit ist der Schritt Konzept abgeschlossen. Als Nächstes kommt die Grobplanung."])
        self.assertEqual(themen.status(self.con, themen.finden(self.con, self.pid, self.letzt))["status"], "dich")   # abgebrochen
        self.tab.js("window.confirm = x => { window.__fragen.push(x); return true; };"
                    " document.querySelector('.th-knoepfe button[data-h=freigeben]').click()")
        self.warten(f"!{self.DICH} && document.querySelector('.th-zeile[data-th=\"{self.letzt}\"] .th-status.frei')")
        self.assertIsNone(self.tab.js(self.DICH))                                     # nichts mehr für dich: keine Zeile
        self.assertEqual(len(themen.tor_ereignisse(self.con, self.pid)), schon + 1)
        self.assertEqual(self.tab.js("window.__fragen.length"), 2)

    def test_zurueck_ohne_frage(self):
        """Zurückgeben schließt nie – keine Frage."""
        self.oeffnen("themen", "document.querySelector('.th-liste .th-zeile')")
        self.tab.js(self.OFFEN[0] % self.letzt)
        self.warten(self.OFFEN[1])
        self.tab.js("window.__fragen = []; window.confirm = x => { window.__fragen.push(x); return true; };"
                    " document.querySelector('.th-knoepfe button[data-h=zurueck]').click()")
        self.warten("document.querySelector('.th-kasten textarea')")
        self.tab.js("document.querySelector('.th-kasten textarea').value = 'Noch die Sicherung';"
                    " document.querySelector('.th-kasten .klein-knopf.haupt').click()")
        self.warten(f"document.querySelector('.th-zeile[data-th=\"{self.letzt}\"] .th-status.arbeit')")
        self.assertEqual(self.tab.js("window.__fragen"), [])

    def test_bilder(self):
        liste = "document.querySelector('.th-liste .th-zeile')"
        for ort in ("themen-tor-offen", "themen-tor-zu"):
            if ort == "themen-tor-zu":
                themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.letzt)
            for g in ("pc", "handy"):
                for th in ("hell", "dunkel"):
                    tun, danach = (self.OFFEN[0] % self.letzt, self.OFFEN[1]) if ort == "themen-tor-offen" else (None, None)
                    self.assertEqual(self.besuchen("themen", ort, bereit=liste, tun=tun, danach=danach, g=g, t=th), [], f"{ort} {g} {th}")


class ThemenGegenlesen(Rundgang):
    """A1914: liest ein Gegenleser, steht in Liste und Thema nur der Status als Fakt („wird gegengelesen · seit …“, in Arbeit);
    danach das Ergebnis zum Aufklappen (Fassung, Modell, Kosten, Einwände). Bilder über AMW_RUNDGANG_BILDER."""

    def daten(self):
        from amw import gegenlesen
        kern.agent_neu(self.con, self.pid, "CC1")
        self.liest = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", self.liest, "Wer die Online-Seite öffnet, meldet sich mit seinem Firmen-Konto an.")
        self.fertig = themen.neu(self.con, self.pid, "TL", "Nachrichten", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", self.fertig, "An dich getrennt von Mitlesen.")
        with db.schreiben(self.con):
            for tid in (self.liest, self.fertig):
                db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="AMW", art=gegenlesen.ANGESTOSSEN,
                             text='{"thema": %d, "fassung": 1, "rolle": "gegenlesen", "modell": "haiku"}' % tid)
        gegenlesen.abschliessen(self.con, self.pid, self.fertig, 1, {"einwaende": "- Abschnitt 1: „Mitlesen“ ist nicht erklärt.\n"
                                                                     "- Fehlt: was mit Fragen geschieht.", "usd": 0.0213, "modell": "haiku"}, lauf=7)

    ZEILE = "document.querySelector('.th-zeile[data-th=\"%d\"]')"

    def test_status_als_fakt_und_ergebnis(self):
        self.oeffnen("themen", "document.querySelector('.th-liste .th-zeile')")
        zeile = self.ZEILE % self.liest
        self.warten(f"{zeile}?.querySelector('.th-grund-zeile')")
        self.assertRegex(self.tab.js(f"{zeile}.querySelector('.th-grund-zeile').textContent"), r"^wird gegengelesen · seit \d\d:\d\d$")
        self.assertTrue(self.tab.js(f"!!{zeile}.querySelector('.th-status.arbeit')"))
        self.tab.js(f"{self.ZEILE % self.fertig}.click()")
        self.warten("document.querySelector('.th-thema h2')?.textContent === 'Nachrichten'")
        self.warten("document.querySelector('.th-gegengelesen summary')")
        self.assertEqual(self.tab.js("document.querySelector('.th-gegengelesen summary').textContent"),
                         "Gegengelesen: Fassung 1 · haiku · 0.02 $")
        self.assertIn("nicht erklärt", self.tab.js("document.querySelector('.th-gegengelesen').textContent"))
        self.assertTrue(self.tab.js("!!document.querySelector('.th-knoepfe button[data-h=freigeben]')"))   # danach: bei dir

    def test_bilder(self):
        liste = "document.querySelector('.th-liste .th-zeile')"
        offen = (f"{self.ZEILE % self.liest}.click()", "document.querySelector('.th-thema h2')?.textContent === 'Anmeldung'")
        auf = (f"{self.ZEILE % self.fertig}.click()",
               "document.querySelector('.th-gegengelesen summary') && (document.querySelector('.th-gegengelesen').open = true)")
        for g in ("pc", "handy"):
            for th in ("hell", "dunkel"):
                for ort, (tun, danach) in (("themen-gegenlesen-liest", offen), ("themen-gegenlesen-ergebnis", auf)):
                    self.assertEqual(self.besuchen("themen", ort, bereit=liste, tun=tun, danach=danach, g=g, t=th), [], f"{ort} {g} {th}")
