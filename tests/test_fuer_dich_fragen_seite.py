"""„Für dich“ mit dem Fragen-Topf (A1990, K10, Kleinprobe D1413, F5370): alle offenen Fragen an dich als eine Gruppe „Fragen n“,
je Frage eine Zeile (F-Nummer, Kurztext, „blockiert“ oder „seit N h“) – ohne „hängt: A…“; ein Klick führt zu den Fragen.
Blockiert ist eine Frage auch, wenn ein Agent an ihr hängt und sonst nichts Startklares hat. Rundgang PC/Handy × hell/dunkel
(Bilder über AMW_RUNDGANG_BILDER)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import time

from amw import db, kern, wartegrund
from tests.rundgang import Rundgang


class FuerDichFragen(Rundgang):
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        f = lambda kurz: kern.frage_neu(self.con, self.pid, "CC1", "entwickler", kurz, [("A", "ja"), ("B", "nein")], "A", "weil",   # noqa: E731
                                        geprueft="keine Treffer")
        self.f1 = f("Welche Farbe bekommt das Warnsymbol?")
        self.f2 = f("Darf der Export auch Notizen enthalten?")
        a = kern.aufgabe_neu(self.con, self.pid, "TL", "Warnsymbol in der Liste", agent="CC1")
        with db.schreiben(self.con):
            vor5 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 5 * 3600 - 60))
            self.con.execute("UPDATE frage SET an = 'entwickler', zeit_utc = ? WHERE id = ?", (vor5, self.f2))
            self.con.execute("UPDATE frage SET an = 'entwickler' WHERE id = ?", (self.f1,))
            wartegrund.anlegen(self.con, self.pid, "CC1", a, f"F{self.f1}")             # CC1 hat sonst nichts → blockiert
            self.con.execute("UPDATE aufgabe SET status = 'wartet' WHERE id = ?", (a,))

    GRUPPE = "document.querySelector('#ue-fragen')"

    def test_gruppe_und_zeilen(self):
        self.oeffnen("start", self.GRUPPE)
        text = self.tab.js(f"{self.GRUPPE}.innerText").lower()                                     # Etikett in Großbuchstaben (CSS)
        offen = self.con.execute("SELECT count(*) FROM frage WHERE projekt_id = ? AND an = 'entwickler' AND status = 'offen'"
                                 " AND geparkt_utc IS NULL", (self.pid,)).fetchone()[0]          # die Grundlage bringt eigene mit
        self.assertTrue(self.tab.js(f"{self.GRUPPE}.querySelector('h4').innerText").endswith(str(offen)))
        zeilen = self.tab.js(f"[...{self.GRUPPE}.querySelectorAll('.ue-zeile')].map(z => z.dataset.frage)")
        self.assertEqual(zeilen[0], str(self.f1))                                                  # blockierte zuerst
        self.assertIn(str(self.f2), zeilen)
        self.assertIn("blockiert", text)
        self.assertIn("seit 5 h", text)
        self.assertIn("neu", text)                                                                 # unter 1 min (nicht „seit 0 h“)
        self.assertNotIn("seit 0", text)
        self.assertFalse(self.tab.js("!!document.querySelector('#ue-fuer_dich h3 .ue-zahl')"))     # F5370: Kopf ohne Zählung
        self.assertEqual(self.tab.js("t('uk_seit_t', {n: 2})"), "seit 2 T")
        self.assertNotIn("hängt", text)
        self.tab.js(f"{self.GRUPPE}.querySelector('.ue-zeile').click()")
        self.warten("zustand.sicht === 'fragen'")                                                  # Details auf Klick

    def test_zahl_zaehlt_alle_offenen(self):
        """A1993: geladen werden höchstens 20 Fragen – die Zahl an „Fragen n“ und „… weitere Fragen“ zählt alle offenen."""
        from amw import workbench
        for i in range(23):
            fid = kern.frage_neu(self.con, self.pid, "CC1", "entwickler", f"Frage {i}?", [("A", "ja")], "A", "weil", geprueft="x")
            with db.schreiben(self.con):
                self.con.execute("UPDATE frage SET an = 'entwickler' WHERE id = ?", (fid,))
        offen = self.con.execute("SELECT count(*) FROM frage WHERE projekt_id = ? AND an = 'entwickler' AND status = 'offen'"
                                 " AND geparkt_utc IS NULL", (self.pid,)).fetchone()[0]
        d = workbench.daten_start(self.con, self.pid)
        self.assertEqual((len(d["fragen"]), d["fragen_anzahl"]), (20, offen))
        self.oeffnen("start", self.GRUPPE)
        self.assertTrue(self.tab.js(f"{self.GRUPPE}.querySelector('h4').innerText").endswith(str(offen)))
        self.assertIn(str(offen - 6), self.tab.js("document.querySelector('#ue-fuer_dich .ue-mehr').innerText"))

    def test_rundgang(self):
        for g in ("pc", "handy"):
            for th in ("hell", "dunkel"):
                self.assertEqual(self.besuchen("start", "fuer-dich-fragen", bereit=self.GRUPPE, g=g, t=th), [], f"{g} {th}")
