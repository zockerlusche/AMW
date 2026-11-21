"""Themen-Bereich in der Seite (A1896): Liste mit je einem Status, Text als Ganzes, nur mögliche Handlungen; am Handy zuerst die
Liste (Auflage a); „neu prüfen“ mit Grund (Auflage c); „Für dich“ springt zum Thema. Bilder vorher (Wissen › Themen) und
nachher (Themen) PC/Handy hell/dunkel über AMW_RUNDGANG_BILDER."""
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
            self.con.execute("UPDATE plan_ereignis SET zeit_utc = '2026-11-01T09:00:00Z' WHERE art = 'thema_freigabe'")
            db.einfuegen(self.con, "beschluss", projekt_id=self.pid, zeit_utc=db.jetzt(), stichwort="Arbeiter melden sich an", regel="x",
                         quelle="W1", thema="Kopflose Arbeiter", angelegt_von="TL", angelegt_utc=db.jetzt())
        themen.neu(self.con, self.pid, "TL", "Online-Seite", pfleger="CC1")

    ZEIGEN = "zustand.themaOffen = null; zeige('themen')"
    LISTE = "document.querySelector('.th-liste .th-zeile')"

    def test_liste_text_handlungen_freigeben(self):
        self.oeffnen("themen", self.LISTE)                                                      # direkt über die Adresse
        self.warten(f"{self.LISTE}?.dataset.th === '{self.warte}'")                           # wartende oben
        self.tab.js(f"{self.LISTE}.click()")
        self.warten("document.querySelector('.th-thema h2')?.textContent === 'Anmeldung'")
        text = self.tab.js("document.querySelector('#inhalt').innerText").lower()
        for teil in ("1 von 4 themen freigegeben", "anmeldung", "firmen-konto", "wartet auf dich"):
            self.assertIn(teil, text)
        self.assertEqual(self.tab.js("document.querySelector('.th-thema h2').textContent"), "Anmeldung")
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.th-knoepfe button')].map(b => b.dataset.h).join(',')"),
                         "freigeben,zurueck,bearbeiten,markieren")
        self.tab.js("document.querySelector('.th-knoepfe button[data-h=freigeben]').click()")
        self.warten(f"document.querySelector('.th-zeile[data-th=\"{self.warte}\"] .th-status.frei')")
        self.assertEqual(themen.status(self.con, themen.finden(self.con, self.pid, self.warte))["status"], "frei")

    def test_fuer_dich_springt_zum_thema(self):
        self.oeffnen("start", "[...document.querySelectorAll('.ue-zeile .ref')].some(r => r.textContent.startsWith('TH'))")
        self.tab.js("[...document.querySelectorAll('.ue-zeile')].find(z => z.querySelector('.ref')?.textContent === 'TH%d')"
                    ".querySelector('button').click()" % self.warte)
        self.warten("document.querySelector('.th-thema h2')?.textContent === 'Anmeldung'")

    def test_rundgang_vorher_nachher(self):
        for g in ("pc", "handy"):
            for th in ("hell", "dunkel"):
                self.assertEqual(self.besuchen("start", "themen-nachher", bereit="typeof zeige === 'function'", tun=self.ZEIGEN,
                                               danach=self.LISTE, g=g, t=th), [], f"nachher {g} {th}")
            if g == "handy":                                             # Auflage (a): am Handy zuerst die Liste, kein Thema offen
                self.assertTrue(self.tab.js("getComputedStyle(document.querySelector('.th-thema')).display === 'none'"))
            self.besuchen("start", "themen-vorher", bereit="typeof zeige === 'function'",
                          tun="zustand.wissenReiter = 'themen'; zeige('wissen')", danach="document.querySelector('#inhalt .reiter')", g=g, t="dunkel")
