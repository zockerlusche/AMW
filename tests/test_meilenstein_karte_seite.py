"""Meilenstein-Karte in der Seite (A1777): Satz, „was läuft, was hängt“ mit dem Weg zum Eingreifen, Aufgaben mit Mini-Zeitlinie,
„Vorziehen“ nur, wenn ein offener Meilenstein davor steht, Lead-Knöpfe unter „Mehr …“; Rundgang in allen Größen und Themen
(Bilder für die Prüfbitte über AMW_RUNDGANG_BILDER)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime
from amw import db, kern, planung, wartegrund
from tests.rundgang import Rundgang


class Karte(Rundgang):
    def daten(self):                                                     # TL (Lead) legt schon das Gerüst an
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid, "CC2")
        neu = lambda titel: planung.bogen_neu(self.con, self.pid, "TL", titel, ziel="Die AMW nimmt Routine ab", abnahme="alles grün",
                                              zieldatum=(datetime.date.today() + datetime.timedelta(days=21)).isoformat())
        self.alt, self.b, self.danach = neu("Schon erledigt"), neu("Tokens sparen und ruhiger Betrieb"), neu("AMW 2.0")
        a = lambda titel, bid, agent="CC1", **k: (lambda x: (planung.schritt_setzen(self.con, self.pid, "TL", aid=x, bogen_id=bid, **k), x)[1])(
            kern.aufgabe_neu(self.con, self.pid, "TL", titel, agent=agent))
        self.laeuft = a("Meilenstein-Karte neu", self.b)
        self.frage = a("Symbol in der Taskleiste", self.b, "CC2")
        self.lauf = [a(f"Schlange Teil {i}", self.b, "CC2") for i in (1, 2, 3, 4)]
        self.pruef = a("Knopf „Vorziehen“", self.b, "CC2")
        self.fertig = a("Token-Verbrauch messen", self.b, "CC2")
        self.wandert = a("Kam aus AMW 2.0", self.danach, "CC2")
        planung.schritt_setzen(self.con, self.pid, "TL", aid=self.wandert, bogen_id=self.b)
        self.nach = a("Danach dran", self.b, "CC2", nach=[self.pruef])
        fid = kern.frage_neu(self.con, self.pid, "TL", "entwickler", "Wie soll das Symbol aussehen?", [("A", "rund")], "A", "weil",
                             geprueft="keine Treffer")
        with db.schreiben(self.con):
            jetzt = db.jetzt()
            self.con.execute("UPDATE bogen SET status = 'fertig', fertig_utc = ? WHERE id = ?", (jetzt, self.alt))
            self.con.execute("UPDATE bogen SET status = 'aktiv' WHERE id = ?", (self.b,))
            self.lid = db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="CC2", beschreibung="Gesamtlauf vor der Auslieferung",
                                    status="angemeldet", angemeldet_utc=jetzt)
            wartegrund.anlegen(self.con, self.pid, "CC2", self.frage, f"F{fid}")
            for x in self.lauf:
                wartegrund.anlegen(self.con, self.pid, "CC2", x, f"L{self.lid}")
            self.con.execute(f"UPDATE aufgabe SET status = 'wartet', begonnen_utc = ? WHERE id IN ({','.join('?' * 5)})",
                             (jetzt, self.frage, *self.lauf))
            db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=self.pruef, zweig="a1764", sha="abc1234", bauer="CC2",
                         pruefer="TL", angefragt_utc=jetzt)
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc1234', begonnen_utc = ?, fertig_utc = ? WHERE id = ?",
                             (jetzt, jetzt, self.fertig))
        kern.aufgabe_status(self.con, self.pid, "CC1", self.laeuft, "start")

    def karte(self):
        return f"document.querySelector('#bogen-{self.b} .mk-lage')"

    def test_karte_zeigt_fakten_zum_eingreifen(self):
        self.oeffnen("planung", self.karte())
        text = self.tab.js(f"document.querySelector('#bogen-{self.b}').innerText")
        for teil in ("Verantwortlich:", "TL (Lead)", "1 von 10 Aufgaben fertig", "1 läuft", "1 wartet auf dich", "5 blockiert",
                     "1 bei der Prüfung", "1 noch nicht dran",
                     "1 wartet auf dich:", "Frage beantworten", "Wie soll das Symbol aussehen?",
                     f"4 blockiert durch Lauf L{self.lid}", "(Gesamtlauf vor der Auslieferung)", "Platz 1 von 1 in der Schlange", "Lauf vorziehen",
                     "1 bei der Prüfung:", "Prüfbitte P", "Lead anschreiben", "1 läuft:", "CC1",
                     f"verschoben aus Meilenstein {self.danach}", f"1 wartet auf A{self.pruef}", "Offen (9)", "Fertig (1)", "Details"):
            self.assertIn(teil.lower(), text.lower())                              # Knöpfe stehen in Großbuchstaben (CSS)
        # „Vorziehen“ nur, wenn davor ein offener Meilenstein steht; Lead-Knöpfe nur im Menü
        self.assertFalse(self.tab.js(f"!!document.querySelector('#bogen-{self.b} .mk-vorziehen')"))
        self.assertTrue(self.tab.js(f"!!document.querySelector('#bogen-{self.danach} .mk-vorziehen')"))
        self.assertTrue(self.tab.js(f"document.querySelector('#bogen-{self.b} .mk-menue').hidden"))
        self.tab.js(f"document.querySelector('#bogen-{self.b} .mk-mehr > button').click()")
        menue = self.tab.js(f"document.querySelector('#bogen-{self.b} .mk-menue').innerText")
        for teil in ("Für den Lead", "Abschließen", "Bearbeiten"):
            self.assertIn(teil.lower(), menue.lower())
        # offene Aufgaben zuerst: wartet auf dich vor läuft vor Lauf; Mini-Zeitlinie bei allen
        reihe = self.tab.js(f"[...document.querySelectorAll('#bogen-{self.b} .mk-liste > .mk-a')].map(x => +x.id.split('-')[1])")
        self.assertEqual(reihe[:2], [self.frage, self.laeuft])
        self.assertTrue(self.tab.js(f"[...document.querySelectorAll('#bogen-{self.b} .mk-a')].every(x => x.querySelector('.mk-mini'))"))
        # Vorziehen: eins nach vorn, Lead bekommt eine Meldung
        self.tab.js(f"window.confirm = () => true; document.querySelector('#bogen-{self.danach} .mk-vorziehen').click()")
        self.warten(f"!document.querySelector('#bogen-{self.danach} .mk-vorziehen')", 10)
        reihe = [r[0] for r in self.con.execute("SELECT id FROM bogen WHERE projekt_id = ? ORDER BY nr, id", (self.pid,))]
        self.assertEqual(reihe, [self.alt, self.danach, self.b])
        self.assertTrue(self.tab.js(f"!!document.querySelector('#bogen-{self.b} .mk-vorziehen')"))
        self.assertFalse(self.tab.js("document.documentElement.scrollWidth > innerWidth"))

    def test_zeitleiste_farben_und_muster(self):
        self.oeffnen("planung", "document.querySelector('.ueb-block')")
        stil = self.tab.js("(() => { const b = document.querySelector('.ueb-block.aktiv'); return b && getComputedStyle(b).getPropertyValue('--farbe').trim(); })()")
        self.assertEqual(stil.lower(), "#56b4e9")                                  # dunkel: Okabe-Ito Himmelblau
        self.assertTrue(self.tab.js("[...document.querySelectorAll('.ueb-legende .ueb-muster.geplant')].length === 1"))

    def test_rundgang(self):
        zeigen = f"document.getElementById('bogen-{self.b}').scrollIntoView({{block: 'start'}})"
        self.ueberall("planung", "meilenstein-karte", bereit=self.karte(), tun=zeigen)
        self.ueberall("planung", "meilenstein-karte-mehr", bereit=self.karte(),
                      tun=zeigen + f"; document.querySelector('#bogen-{self.b} .mk-mehr > button').click()",
                      danach=f"!document.querySelector('#bogen-{self.b} .mk-menue').hidden")
        self.ueberall("planung", "zeitleiste-farben", bereit="document.querySelector('.ueb-block')")
