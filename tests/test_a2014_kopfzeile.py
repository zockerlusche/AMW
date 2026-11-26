"""A2014 (Kleinprobe A2010, D1904/D1905, TL #33873): Kopfzeile – Projektwechsel mit „für dich“-Zählern, Gesamtsicht über alle Projekte,
Suche über alles beim Tippen (erst das eigene Projekt, dann die anderen; eine Nummer findet das Ding, ein Klick öffnet es). Keine
Tor-Leiste, keine zweite Statusleiste; Farbe nur am Zähler „für dich“. PC und Handy, hell und dunkel."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import unittest

from amw import db, kern, planung, workbench
from tests.rundgang import Rundgang
from tests.test_a2077_verlauf import Grund


def zweites_projekt(con, name="Shop"):
    with db.schreiben(con):
        pid = db.einfuegen(con, "projekt", name=name, angelegt_utc=db.jetzt())
    kern.agent_neu(con, pid, "TL", rolle="lead")
    kern.agent_neu(con, pid, "CC1")
    return pid


def bestand(con, pid):
    """Eigenes Projekt: ein aktiver Meilenstein mit zwei Paketen (eins fertig), eine offene Frage an dich; zweites Projekt „Shop“ mit
    einem Paket „Export der Bestellungen“ und einer offenen Frage."""
    m = planung.bogen_neu(con, pid, "TL", "Auswertung", ziel="Z", abnahme="Vorführung")
    planung.bogen_status(con, pid, "TL", m, "aktiv")
    a = planung.schritt_setzen(con, pid, "TL", titel="Export nach Excel", bogen_id=m, agent="CC1")
    b = planung.schritt_setzen(con, pid, "TL", titel="Spalten wählen", bogen_id=m, agent="CC1")
    with db.schreiben(con):
        con.execute("UPDATE aufgabe SET status = 'fertig', fertig_utc = ?, beleg = 'abc1234' WHERE id = ?", (db.jetzt(), b))
    kern.frage_neu(con, pid, "TL", "entwickler", "Passkey oder Passwort?", [("A", "ja"), ("B", "nein")], "A", "weil", geprueft="keine Treffer")
    shop = zweites_projekt(con)
    s = planung.schritt_setzen(con, shop, "TL", titel="Export der Bestellungen", agent="CC1")
    kern.frage_neu(con, shop, "TL", "entwickler", "Welche Zahlungsarten?", [("A", "ja"), ("B", "nein")], "A", "weil", geprueft="keine Treffer")
    kern.frage_neu(con, shop, "TL", "entwickler", "Versand ins Ausland?", [("A", "ja"), ("B", "nein")], "A", "weil", geprueft="keine Treffer")
    return {"a": a, "b": b, "shop": shop, "s": s, "m": m}


class Daten(Grund):
    def setUp(self):
        super().setUp()
        self.n = bestand(self.con, self.pid)

    def test_projekte_mit_fuer_dich(self):
        p = {x["name"]: x for x in workbench.daten_projekte(self.con, self.pid)["projekte"]}
        self.assertEqual((p["P"]["fuer_dich"], p["Shop"]["fuer_dich"]), (1, 2))

    def test_gesamtsicht(self):
        p = {x["name"]: x for x in workbench.daten_gesamtsicht(self.con, self.pid)["projekte"]}
        self.assertEqual(p["P"]["fortschritt"]["fertig"], 1)
        self.assertEqual(p["P"]["fortschritt"]["gesamt"], 2)
        self.assertEqual(p["P"]["meilensteine"], [1, 2])                # „Bauen“ aus Grund und „Auswertung“
        self.assertTrue(p["P"]["aktiv"])
        self.assertEqual((p["Shop"]["meilensteine"], p["Shop"]["fuer_dich"]), ([], 2))

    def test_suche_ueber_alle_projekte(self):
        l = workbench.daten_suche(self.con, self.pid, {"q": ["Export"], "alle": ["1"]})
        eigen = [x["ref"] for x in l if not x.get("projekt")]
        andere = [(x["ref"], x["projekt_name"]) for x in l if x.get("projekt")]
        self.assertEqual(eigen, [f"A{self.n['a']}"])
        self.assertEqual(andere, [(f"A{self.n['s']}", "Shop")])
        self.assertEqual([x["ref"] for x in workbench.daten_suche(self.con, self.pid, {"q": ["Export"]})], eigen)   # ohne alle: nur das eigene

    def test_nummer_zuerst(self):
        l = workbench.daten_suche(self.con, self.pid, {"q": [f"A{self.n['a']}"], "alle": ["1"]})
        self.assertEqual(l[0]["ref"], f"A{self.n['a']}")


class Seite(Rundgang):
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        self.n = bestand(self.con, self.pid)

    def liste_auf(self):
        self.oeffnen("start", "document.querySelector('#projekt-chip:not([hidden])')")
        self.tab.js("document.querySelector('#projekt-chip').click()")
        self.warten("document.querySelector('.pw-liste .pw-eintrag')")

    def test_projektwechsel_mit_zaehlern(self):
        self.liste_auf()
        zeilen = self.tab.js("[...document.querySelectorAll('.pw-liste .pw-eintrag')].map(e => e.innerText.replace(/\\s+/g, ' ').trim())")
        n = {x["name"]: x["fuer_dich"] for x in workbench.daten_projekte(self.con, self.pid)["projekte"]}   # dieselbe Zahl wie „Für dich“
        self.assertEqual(n["Shop"], 2)
        self.assertEqual(zeilen[:3], [f"Alle Projekte {n['P'] + 2}", f"P {n['P']}", "Shop 2"])
        signale = self.tab.js("document.querySelector('#signale').innerText")       # keine zweite Statusleiste: nur Abweichungen
        self.assertNotIn("Agenten laufen", signale)
        self.assertNotIn("Arbeitsspeicher", signale)

    def test_gesamtsicht(self):
        self.liste_auf()
        self.tab.js("document.querySelector('.pw-liste .kz-alle').click()")
        self.warten("document.querySelectorAll('.kz-karte').length === 2")
        self.assertEqual(self.tab.js("document.querySelector('#projekt-chip .pk-name').textContent"), "Alle Projekte")
        p = self.tab.js("document.querySelector('.kz-karte').innerText.replace(/\\s+/g, ' ')")
        self.assertIn("für dich", p)
        self.assertIn("Meilenstein 1 · 1 von 2 Paketen", p)
        self.assertIn("Shop", self.tab.js("document.querySelectorAll('.kz-karte')[1].innerText"))
        self.tab.js("document.querySelector('.kz-karte').click()")                # das eigene Projekt: zurück in den Leitstand
        self.warten("zustand.sicht === 'start'")

    def test_suche_beim_tippen(self):
        self.oeffnen("start", "document.querySelector('#suche')")
        self.tab.js("{ const s = document.querySelector('#suche'); s.focus(); s.value = 'Export'; s.dispatchEvent(new Event('input')); }")
        self.warten("document.querySelectorAll('#kz-treffer .kz-tr').length === 2")
        gruppen = self.tab.js("[...document.querySelectorAll('#kz-treffer .kz-gr')].map(g => g.textContent)")
        self.assertEqual(gruppen, ["In P", "Andere Projekte"])
        self.assertIn("Shop", self.tab.js("document.querySelectorAll('#kz-treffer .kz-tr')[1].innerText"))
        self.assertEqual(self.tab.js("document.querySelector('#kz-treffer .kz-tr mark').textContent"), "Export")
        self.tab.js("document.querySelector('#kz-treffer .kz-tr').click()")       # öffnet das Paket selbst (A2115)
        self.warten("[...document.querySelectorAll('.dialog')].some(d => d.textContent.includes('Export nach Excel'))")
        self.tab.js("{ document.querySelectorAll('.dialog-hg').forEach(d => d.remove()); const s = document.querySelector('#suche');"
                    " s.value = ''; s.dispatchEvent(new Event('input')); }")
        self.warten("document.querySelector('#kz-treffer .kz-gr')?.textContent === 'Zuletzt gesucht'")

    def test_nichts_gefunden(self):
        self.oeffnen("start", "document.querySelector('#suche')")
        self.tab.js("{ const s = document.querySelector('#suche'); s.focus(); s.value = 'xyzq'; s.dispatchEvent(new Event('input')); }")
        self.warten("document.querySelector('#kz-treffer .kz-leer')")
        self.assertEqual(self.tab.js("document.querySelector('#kz-treffer').innerText.trim()"), "Nichts gefunden.")

    def test_bilder(self):
        auf = "document.querySelector('#projekt-chip').click()"
        self.ueberall("start", "a2014-wechsel", bereit="document.querySelector('#projekt-chip:not([hidden])')", tun=auf,
                      danach="document.querySelector('.pw-liste .kz-alle')")
        self.ueberall("projekte", "a2014-alle", bereit="document.querySelector('.kz-karte')")
        such = "const s = document.querySelector('#suche'); s.focus(); s.value = 'Export'; s.dispatchEvent(new Event('input'))"
        self.ueberall("start", "a2014-suche", bereit="document.querySelector('#suche')", tun=such, danach="document.querySelectorAll('#kz-treffer .kz-tr').length === 2")


if __name__ == "__main__":
    unittest.main()
