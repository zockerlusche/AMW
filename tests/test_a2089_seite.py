"""A2089: Seite und Suche nennen Meilensteine mit der Projektnummer. Interne Nummer und Projektnummer sind hier immer verschieden (ein
fremdes Projekt hat die ersten), sonst prüfte der Test nichts."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import base64
import json
import re
import unittest
import zlib

from amw import abgleich, db, kern, meilensteine, planung, workbench
from tests import test_a2079_meilensteinnummer
from tests.rundgang import Rundgang


class Suche(test_a2079_meilensteinnummer.Grund):
    def refs(self, such, projekt="Neu"):
        return [(x["art"], x["ref"]) for x in workbench.daten_suche(self.con, self.pid[projekt], {"q": [such]})]

    def test_findet_den_meilenstein_und_seine_nachrichten(self):
        mit, _ = kern.posten(self.con, self.pid["Neu"], "TL", "CC1", "info", "Stand dazu", bezug="M5")          # intern 5 = M2
        ohne, _ = kern.posten(self.con, self.pid["Neu"], "TL", "CC1", "info", "etwas anderes", bezug="M6")       # intern 6 = M3
        for such in ("M2", "m2"):
            r = self.refs(such)
            self.assertIn(("meilenstein", "M2"), r)
            self.assertIn(("nachricht", f"#{mit}"), r)
            self.assertNotIn(("nachricht", f"#{ohne}"), r)
            self.assertNotIn(("meilenstein", "M3"), r)
        self.assertEqual([x for x in self.refs("M5") if x[0] == "meilenstein"], [])                               # die interne Nummer findet nichts
        self.assertIn(("meilenstein", "M2"), self.refs("M2", "Alt"))                                              # je Projekt

    def test_nach_titel(self):
        self.assertIn(("meilenstein", "M3"), self.refs("Neu 3"))
        self.assertNotIn(("meilenstein", "M3"), self.refs("Alt 3"))

    def test_befehl(self):
        text = self.ok("suche", "M2", "--art", "meilenstein")
        self.assertIn("M2", text)
        self.assertIn("Neu 2", text)

    def test_online_index(self):
        kern.posten(self.con, self.pid["Neu"], "TL", "CC1", "info", "Stand dazu", bezug="M5")
        kern.posten(self.con, self.pid["Neu"], "TL", "CC1", "info", "ohne Bezug")
        idx = json.loads(zlib.decompress(base64.b64decode(abgleich.suchindex(self.con, self.pid["Neu"])["gepackt"])))
        ms = {e[1]: e for e in idx if e[0] == "meilenstein"}
        self.assertEqual(sorted(ms), ["M1", "M2", "M3", "M4"])
        self.assertTrue(ms["M2"][3].startswith("M2 "))                                                            # api.php sucht in Titel und Text
        self.assertEqual({e[2]: e[3] for e in idx if e[0] == "nachricht"}, {"Stand dazu": "M2", "ohne Bezug": ""})

    def test_suchbezug(self):
        self.assertEqual(meilensteine.suchbezug(self.con, self.pid["Neu"], "M2"), "M5")
        for x in ("M99", "2", "Meilenstein", "", None):
            self.assertIsNone(meilensteine.suchbezug(self.con, self.pid["Neu"], x))


class Startdaten(test_a2079_meilensteinnummer.Grund):
    def test_zuordnung_nur_des_eigenen_projekts(self):
        self.assertEqual(workbench.daten_start(self.con, self.pid["Neu"])["bogen_nr"], {"4": 1, "5": 2, "6": 3, "7": 4})
        self.assertEqual(workbench.daten_start(self.con, self.pid["Alt"])["bogen_nr"], {"1": 1, "2": 2, "3": 3})

    def test_federfuehrung_auf_der_kachel(self):
        kern.federfuehrung_setzen(self.con, self.pid["Neu"], "TL", "bogen", 5, "CC1")
        a = next(a for a in workbench.daten_start(self.con, self.pid["Neu"])["agenten"] if a["kennung"] == "CC1")
        self.assertEqual(a["fuehrt"], ["M2"])
        self.assertIn("Du führst jetzt M2: Neu 2", kern.offene(self.con, self.pid["Neu"], "CC1")[0]["kurz"])
        self.assertIn("M2 Neu 2", kern.kontext(self.con, self.pid["Neu"], "CC1"))


class Seite(Rundgang):
    def daten(self):
        with db.schreiben(self.con):
            fremd = db.einfuegen(self.con, "projekt", name="Fremd", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, fremd, "TL", rolle="lead")
        for i in range(60):                                                  # interne Nummern weit weg von den Projektnummern
            planung.bogen_neu(self.con, fremd, "TL", f"Fremd {i}", ziel="Z", abnahme="V")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.b = [planung.bogen_neu(self.con, self.pid, "TL", f"Bauen {i}", ziel="Z", abnahme="V") for i in (1, 2, 3)]
        self.assertGreater(min(self.b), 50)
        planung.bogen_status(self.con, self.pid, "TL", self.b[1], "aktiv")
        self.a = planung.schritt_setzen(self.con, self.pid, "TL", titel="Paket", bogen_id=self.b[1], agent="CC1")

    def test_planung_und_start_ohne_interne_nummer(self):
        verboten = re.compile("|".join(rf"(?:Meilenstein |\b[MB]){x}\b" for x in self.b))
        for sicht, bereit in (("start", "document.querySelector('.ls-fort:not(.platz)') && document.querySelector('.ls-ablauf')"), ("planung", "document.querySelector('main').innerText.includes('Bauen 2')"),
                              ("dokumente", "document.querySelector('main select')")):
            self.oeffnen(sicht, bereit)
            text = self.tab.js("document.querySelector('main').innerText + [...document.querySelectorAll('main [title], main option')].map(x => ' ' + (x.title || '') + ' ' + x.textContent).join(' ')")
            self.assertIsNone(verboten.search(text), (sicht, verboten.search(text)))
            self.assertNotIn("M?", text, sicht)
            self.assertIn("M2", text, sicht)

    def test_aufgabe_nennt_die_projektnummer(self):
        self.oeffnen("planung", "document.querySelector('main').innerText.includes('Bauen 2')")
        self.tab.js(f"aufgabeDialog({self.a})")
        self.warten("[...document.querySelectorAll('.dialog')].some(d => d.textContent.includes('Paket'))")
        text = self.tab.js("[...document.querySelectorAll('.dialog')].map(d => d.textContent).join(' ')")
        self.assertIn("M2", text)
        self.assertNotIn(f"Meilenstein {self.b[1]}", text)


if __name__ == "__main__":
    unittest.main()
