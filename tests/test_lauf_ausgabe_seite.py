"""A2044 in der Seite: Ein eigener Lauf im Zeitstrahl „Was der Rechner heute gemacht hat“ öffnet seine Ausgabe, die sich im Takt
nachlädt, solange er läuft; das Mitlesen eines Headless-Platzes lädt ebenfalls selbst nach (ohne „Neu laden“). Rundgang
PC/Handy hell/dunkel (Bilder für die Prüfbitte über AMW_RUNDGANG_BILDER)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os

from amw import arbeiter, db, platz
from tests.rundgang import Rundgang

OEFFNEN = ("(function los() { const d = document.querySelector('#rechner-heute'); if (!d) return setTimeout(los, 100);"
           " d.open = true; const b = document.querySelector('#rechner-heute .rh-lauf.klickbar'); if (!b) return setTimeout(los, 100);"
           " b.click(); })()")
DIALOG = "document.querySelector('.dialog .pk-mitlesen')"


class LaufAusgabe(Rundgang):
    def daten(self):
        self.datei = os.path.join(self.ordner.name, "l_gesamt.txt")
        with open(self.datei, "w", encoding="utf-8") as f:
            f.write("# AMW L1 · Gesamtlauf\nGesamtlauf parallel: 210 Module auf 6 Prozesse\n........\n")
        with db.schreiben(self.con):
            self.con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?",
                             (json.dumps({"platz_wurzel": os.path.join(self.ordner.name, "plaetze"), "plaetze": 1}), self.pid))
            self.lid = db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="CC1", beschreibung="Gesamtlauf Stapel 1.179.0",
                                    status="laeuft", angemeldet_utc=db.jetzt(), start_utc=db.jetzt(), ergebnis_datei=self.datei)
            db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="CC1", beschreibung="ohne Datei", status="laeuft",
                         angemeldet_utc=db.jetzt(), start_utc=db.jetzt())
        p = platz.plaetze(self.con, self.pid)[0]
        os.makedirs(arbeiter.ordner(p), exist_ok=True)
        self.jsonl = os.path.join(arbeiter.ordner(p), "lauf.jsonl")
        with open(self.jsonl, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "system", "subtype": "init", "model": "claude-sonnet-5-5", "permissionMode": "dontAsk"}) + "\n")

    def test_ausgabe_laedt_im_takt_bis_zum_ende(self):
        self.oeffnen("planung", "document.querySelector('#rechner-heute .rh-lauf')")
        self.assertEqual(self.tab.js("document.querySelectorAll('#rechner-heute .rh-lauf.klickbar').length"), 1)   # nur mit Datei
        self.tab.js(OEFFNEN)
        self.warten(f"{DIALOG} && {DIALOG}.innerText.includes('210 Module')")
        self.assertIn("läuft", self.tab.js("document.querySelector('.dialog p.leise').innerText"))
        with open(self.datei, "a", encoding="utf-8") as f:
            f.write("Ran 1882 tests in 1375.031s\n")
        self.warten(f"{DIALOG}.innerText.includes('Ran 1882 tests')", 10)          # ohne Klick: der Takt holt es
        with db.schreiben(self.con):
            self.con.execute("UPDATE lauf SET status = 'fertig', rc = 0, ende_utc = ? WHERE id = ?", (db.jetzt(), self.lid))
        self.warten("document.querySelector('.dialog p.leise').innerText.includes('rc 0')", 10)
        self.assertFalse(self.tab.js("[...document.querySelectorAll('.dialog button')].some(b => /Neu laden|Reload/.test(b.textContent))"))

    def test_mitlesen_laedt_selbst_nach(self):
        self.oeffnen("arbeit", "document.querySelector('#inhalt .reiter')")
        self.tab.js("zustand.arbeit.sicht = 'pakete'; zeige('arbeit'); (function los() { const b = [...document.querySelectorAll('.pk-platz button')]"
                    ".find(x => x.textContent.startsWith(t('pk_mitlesen'))); if (!b) return setTimeout(los, 100); b.click(); })()")
        self.warten("document.querySelector('.pk-mitlesen .pk-ml.start')")
        self.assertFalse(self.tab.js("[...document.querySelectorAll('.dialog button')].some(b => b.textContent === t('pk_ml_neu'))"))
        with open(self.jsonl, "a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read",
                                                                               "input": {"file_path": "amw/betrieb.py"}}]}}) + "\n")
        self.warten("document.querySelector('.pk-mitlesen').innerText.includes('amw/betrieb.py')", 10)

    def test_rundgang(self):
        for g in ("pc", "handy"):
            for th in ("hell", "dunkel"):
                fehler = self.besuchen("planung", "lauf-ausgabe", bereit="document.querySelector('#rechner-heute .rh-lauf')", tun=OEFFNEN,
                                       danach=f"{DIALOG} && {DIALOG}.innerText.includes('210 Module')", g=g, t=th)
                self.assertEqual(fehler, [], f"{g} {th}")
