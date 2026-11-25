"""A1928 (TH158) in der Seite: unter „Für dich“ steht ein fertiger Meilenstein, der auf die Abnahme wartet – „M… ist fertig –
abnehmen“ mit Knopf „Abnehmen“ (am PC). Bilder PC/Handy hell/dunkel über AMW_RUNDGANG_BILDER."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json

from amw import db, veroeffentlichung
from tests.rundgang import Rundgang


class Abnahme(Rundgang):
    def daten(self):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc="2026-11-22T01:00:00Z", von="CCamw",
                         art=veroeffentlichung.LOKAL, text=json.dumps({"version": "1.154.0", "sha": "d507c67"}))
            self.bogen = db.einfuegen(self.con, "bogen", projekt_id=self.pid, nr=50, titel="AMW 2.0 Stufe 1 – Mischbetrieb",
                                      status="fertig", angelegt_von="TL", angelegt_utc="2026-11-01T08:00:00Z",
                                      fertig_utc="2026-11-22T02:00:00Z")

    ZEILE = "document.querySelector('.ab-zeile')"

    def test_fuer_dich_mit_knopf(self):
        self.oeffnen("start", self.ZEILE)
        text = self.tab.js(f"{self.ZEILE}.textContent")
        self.assertIn("„AMW 2.0 Stufe 1 – Mischbetrieb“ ist fertig – abnehmen", text)
        self.assertNotEqual(self.bogen, 50)                                  # A2089: die Projektnummer, nicht die interne
        self.assertEqual(self.tab.js(f"{self.ZEILE}.querySelector('.ref').textContent"), "M50")
        self.assertIn("Danach veröffentlicht die AMW", text)
        self.assertEqual(self.tab.js(f"{self.ZEILE}.querySelector('button')?.textContent"), "Abnehmen")
        self.assertEqual(self.tab.js(f"{self.ZEILE}.dataset.bogen"), str(self.bogen))

    def test_bilder(self):
        for g in ("pc", "handy"):
            for th in ("hell", "dunkel"):
                self.assertEqual(self.besuchen("start", "fuer-dich-abnehmen", bereit=self.ZEILE, g=g, t=th), [], f"{g} {th}")
