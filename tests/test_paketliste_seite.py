"""Arbeit › Pakete in der Seite (A1850): Liste mit Grund und „wer ist dran“, Zuordnungstabelle, Knöpfe am PC, Mitlesen; Rundgang
PC/Handy hell/dunkel (Bilder für die Prüfbitte über AMW_RUNDGANG_BILDER)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os

from amw import arbeiter, arbeitspaket as ap, db, kern, platz, waechter
from tests.rundgang import Rundgang


class Pakete(Rundgang):
    def daten(self):                                                     # TL (Lead) legt schon das Gerüst an
        with db.schreiben(self.con):
            self.con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?",
                             (json.dumps({"platz_wurzel": os.path.join(self.ordner.name, "plaetze"), "plaetze": 1}), self.pid))

        def paket(titel, rang):
            aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel, rang=rang)
            with db.schreiben(self.con):
                self.con.execute("UPDATE aufgabe SET pruefbefehl = 'python -m unittest tests.abnahme_x', dateibereich = 'amw/x.py' WHERE id = ?",
                                 (aid,))
            ap.setzen(self.con, self.pid, "TL", aid, art="p")
            return aid
        self.wartet = paket("Statuszeile kürzer", 10)
        ap.zustand_setzen(self.con, self.pid, "TL", self.wartet, "startklar")
        waechter.protokollieren(self.con, self.pid, self.wartet, waechter._nein(4, "1 von 1 belegt"))
        self.laeuft = paket("Hilfe-Suche schneller", 20)
        for z in ("startklar", "laeuft"):
            ap.zustand_setzen(self.con, self.pid, "AMW", self.laeuft, z)
        self.dich = paket("Neues Symbol", 30)
        for z in ("startklar", "laeuft", "blockiert"):
            ap.zustand_setzen(self.con, self.pid, "AMW", self.dich, z)
        ap.zustand_setzen(self.con, self.pid, "AMW", self.dich, "wartet_interaktiv", grund="Frage an Marcel: welche Farbe?")
        self.entwurf = paket("Kleiner Textfehler", 40)
        p = platz.plaetze(self.con, self.pid)[0]
        os.makedirs(arbeiter.ordner(p), exist_ok=True)
        with open(os.path.join(arbeiter.ordner(p), "lauf.jsonl"), "w", encoding="utf-8") as f:
            for e in ({"type": "system", "subtype": "init", "model": "claude-opus-5-5", "permissionMode": "dontAsk"},
                      {"type": "assistant", "message": {"content": [{"type": "text", "text": "Ich lese zuerst die Suche."},
                                                                    {"type": "tool_use", "name": "Read", "input": {"file_path": "amw/hilfen.py"}}]}},
                      {"type": "user", "message": {"content": [{"type": "tool_result", "content": "1\t\"\"\"Hilfen …"}]}}):
                f.write(json.dumps(e) + "\n")

    ZEIGEN = "zustand.arbeit.sicht = 'pakete'; zeige('arbeit')"
    BEREIT = "true"
    LISTE = "document.querySelector('.pk-liste')"

    def oeffnen_pakete(self):
        self.oeffnen("arbeit", "document.querySelector('#inhalt .reiter')")
        self.tab.js(self.ZEIGEN)
        self.warten(self.LISTE)

    def test_liste_grund_und_knoepfe(self):
        self.oeffnen_pakete()
        text = self.tab.js("document.querySelector('#inhalt').innerText").lower()
        for teil in ("startet nicht: alle arbeitsplätze belegt", "du bist dran", "frage an marcel", "platz 1", "mitlesen"):
            self.assertIn(teil, text)
        zeile = lambda a: f"document.querySelector('.pk-zeile[data-a=\"{a}\"]')"
        self.assertTrue(self.tab.js(f"{zeile(self.wartet)}.classList.contains('gruppe-wartet')"))
        self.assertTrue(self.tab.js(f"{zeile(self.laeuft)}.classList.contains('gruppe-laeuft')"))
        self.assertTrue(self.tab.js(f"{zeile(self.dich)}.classList.contains('gruppe-blockiert')"))
        self.assertEqual(self.tab.js(f"{zeile(self.entwurf)}.querySelectorAll('.pk-knoepfe button').length"), 2)   # vorziehen + zurückstellen
        self.assertEqual(self.tab.js(f"{zeile(self.laeuft)}.querySelectorAll('.pk-knoepfe button').length"), 0)    # läuft: kein Eingriff
        self.assertTrue(self.tab.js("!!document.querySelector('#pk-pause')"))
        self.tab.js("[...document.querySelectorAll('.pk-platz button')].find(b => b.textContent.startsWith(t('pk_mitlesen'))).click()")
        self.warten("document.querySelector('.pk-mitlesen .pk-ml.werkzeug')")
        self.assertIn("Read amw/hilfen.py", self.tab.js("document.querySelector('.pk-mitlesen').innerText"))

    def test_rundgang(self):
        for g in ("pc", "handy"):
            for th in ("hell", "dunkel"):
                fehler = self.besuchen("arbeit", "pakete", bereit="document.querySelector('#inhalt .reiter')", tun=self.ZEIGEN,
                                       danach=self.LISTE, g=g, t=th)
                self.assertEqual(fehler, [], f"{g} {th}")
        offen = (self.ZEIGEN + "; (function los() { const b = [...document.querySelectorAll('.pk-platz button')]"
                 ".find(x => x.textContent.startsWith(t('pk_mitlesen'))); if (!b) return setTimeout(los, 100); b.click(); })()")
        for g in ("pc", "handy"):
            fehler = self.besuchen("arbeit", "pakete-mitlesen", bereit="document.querySelector('#inhalt .reiter')", tun=offen,
                                   danach="document.querySelector('.pk-mitlesen .pk-ml.werkzeug')", g=g, t="dunkel")
            self.assertEqual(fehler, [], f"mitlesen {g}")
