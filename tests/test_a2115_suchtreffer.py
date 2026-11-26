"""A2115: jeder Treffer der Suche mit Nummer öffnet das Ding selbst (PC, Handy, online); genaue Treffer stehen oben; Nummern im Text
einer Nachricht oder eines Berichts öffnen es ebenfalls."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import base64
import json
import os
import unittest
import zlib

from amw import abgleich, db, dokumente, kern, planung, themen, wissen, workbench
from tests.rundgang import OnlineRundgang, Rundgang
from tests.test_aktualisieren import Grund

Z = "2026-01-01T00:00:00Z"
FREMD = {"dokument": dict(titel="F", art="bericht", status="aktuell", angelegt_von="X", angelegt_utc=Z),
         "aufgabe": dict(titel="F", angelegt_von="X", angelegt_utc=Z),
         "frage": dict(an="entwickler", von="X", zeit_utc=Z, kurz="F"),
         "beschluss": dict(zeit_utc=Z, stichwort="F", regel="r", quelle="q", angelegt_von="X", angelegt_utc=Z),
         "wortlaut": dict(zeit_utc=Z, text="F", kanal="seite", erfasst_von="X", erfasst_utc=Z),
         "thema": dict(name="F", angelegt_von="X", angelegt_utc=Z),
         "lauf": dict(agent="X", beschreibung="F", angemeldet_utc=Z),
         "pruefung": dict(zweig="F", sha="s", bauer="X", pruefer="Y", angefragt_utc=Z),
         "nachricht": dict(zeit_utc=Z, von="X", art="info", kurz="F")}


def bestand(con, pid, ordner):
    """Eigener Bestand mit großen, je Art verschiedenen Nummern; nr: je Kürzel die Nummer."""
    with db.schreiben(con):
        fremd = db.einfuegen(con, "projekt", name="Fremd", angelegt_utc=Z)
        for i, (tabelle, spalten) in enumerate(FREMD.items()):              # ein fremder Eintrag davor: die eigenen Nummern fangen hoch an
            db.einfuegen(con, tabelle, id=1713 + 100 * i, projekt_id=fremd, **spalten)
    kern.agent_neu(con, pid, "CC1")
    nr = {}
    b = planung.bogen_neu(con, pid, "TL", "Speicherstand", ziel="Z", abnahme="V")
    nr["M"] = con.execute("SELECT nr FROM bogen WHERE id = ?", (b,)).fetchone()[0]
    planung.bogen_status(con, pid, "TL", b, "aktiv")
    nr["A"] = planung.schritt_setzen(con, pid, "TL", titel="Speichern bauen", bogen_id=b, agent="CC1")
    nr["F"] = kern.frage_neu(con, pid, "TL", "entwickler", "Wie viele Speicherplätze?", [("A", "drei"), ("B", "fünf")], "A", "weil",
                             geprueft="keine Treffer")
    nr["B"] = wissen.beschluss_neu(con, pid, "TL", "Speicherplätze", "Es gibt drei.", "Entwickler")
    with db.schreiben(con):
        nr["W"] = db.einfuegen(con, "wortlaut", projekt_id=pid, zeit_utc=Z, text="Drei Plätze reichen mir.", kanal="seite",
                               erfasst_von="TL", erfasst_utc=Z)
        nr["L"] = db.einfuegen(con, "lauf", projekt_id=pid, agent="CC1", beschreibung="Speichertests", angemeldet_utc=Z, status="fertig", rc=0)
        nr["P"] = db.einfuegen(con, "pruefung", projekt_id=pid, zweig="speichern", sha="abc1234", bauer="CC1", pruefer="TL", angefragt_utc=Z,
                               aufgabe_id=nr["A"])
    nr["TH"] = themen.neu(con, pid, "TL", "Spielstände")
    pfad = os.path.join(ordner, "bericht.md")
    with open(pfad, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"# Bericht\n\nGebaut in A{nr['A']}, siehe **B{nr['B']}** und `A{nr['A']}`. Taste F5, Papier A4, Pfad /A{nr['A']}, Version B{nr['B']}.2.\n")
    nr["D"] = dokumente.ablegen(con, pid, "CC1", pfad, "Bericht zum Speichern", "bericht")["id"]
    nr["#"], _ = kern.posten(con, pid, "TL", "Entwickler", "info", f"Fertig, siehe D{nr['D']}", text=f"Bericht D{nr['D']}, Aufgabe A{nr['A']}.")
    nr["team"], _ = kern.posten(con, pid, "TL", "CC1", "info", "Nur unter uns")
    return nr, b


class Daten(Grund):
    def setUp(self):
        super().setUp()
        self.nr, self.b = bestand(self.con, self.pid, self.ordner.name)

    def suche(self, such):
        return workbench.daten_suche(self.con, self.pid, {"q": [such]})

    def test_genau_zuerst_und_nichts_doppelt(self):
        n = self.nr["D"]
        for such in (f"D{n}", str(n), f"d {n}"):
            t = self.suche(such)
            self.assertEqual((t[0]["art"], t[0]["ref"], t[0]["genau"]), ("dokument", f"D{n}", True), such)
            refs = [(x["art"], x["ref"]) for x in t]
            self.assertEqual(len(refs), len(set(refs)), refs)
        t = self.suche(f"D{n}")
        self.assertIn(("nachricht", f"#{self.nr['#']}"), [(x["art"], x["ref"]) for x in t[1:]])          # danach wie heute: der Text
        self.assertFalse(any(x.get("genau") for x in t[1:]))

    def test_einstelliger_meilenstein_und_mindestlaenge(self):
        t = self.suche(f"M{self.nr['M']}")
        self.assertEqual((t[0]["ref"], t[0]["genau"]), (f"M{self.nr['M']}", True))
        self.assertEqual([x["ref"] for x in t if x["art"] == "meilenstein"], [f"M{self.nr['M']}"])
        self.assertEqual(self.suche(str(self.nr["M"])), [])                                               # eine Ziffer allein ist zu kurz
        self.assertEqual(self.suche("xyzq"), [])

    def test_pruefung_nennt_ihre_aufgabe(self):
        self.assertEqual(self.suche(f"P{self.nr['P']}")[0]["aufgabe"], self.nr["A"])

    def test_wissen_findet_die_nummer(self):
        d = workbench.daten_wissen(self.con, self.pid, {"q": [f"b{self.nr['B']}"]})
        self.assertEqual(([x["id"] for x in d["beschluesse"]], d["anzahl"]["beschluesse"]), ([self.nr["B"]], 1))
        d = workbench.daten_wissen(self.con, self.pid, {"q": [f"W{self.nr['W']}"]})
        self.assertEqual(([x["id"] for x in d["wortlaut"]], d["anzahl"]["wortlaut"]), ([self.nr["W"]], 1))

    def test_suchindex_hat_alles(self):
        idx = json.loads(zlib.decompress(base64.b64decode(abgleich.suchindex(self.con, self.pid)["gepackt"])))
        refs = {e[1] for e in idx}
        for k, n in self.nr.items():
            self.assertIn(("#" if k == "team" else k) + str(n), refs)
        self.assertNotIn("D1713", refs)                                                                   # fremdes Projekt
        self.assertEqual([e[6] for e in idx if e[0] == "pruefung"], [self.nr["A"]])
        with db.schreiben(self.con):
            self.con.execute("UPDATE dokument SET status = 'geloescht' WHERE id = ?", (self.nr["D"],))
        idx = json.loads(zlib.decompress(base64.b64decode(abgleich.suchindex(self.con, self.pid)["gepackt"])))
        self.assertNotIn(f"D{self.nr['D']}", {e[1] for e in idx})


class Wege(Rundgang):
    """Je Kürzel: was danach zu sehen ist – am PC und online dasselbe, online außer der Ausgabe eines Laufs."""
    DIALOG = "[...document.querySelectorAll('.dialog')].some(d => d.textContent.includes({!r}))"
    OK = {"D": DIALOG.format("Bericht zum Speichern"), "A": DIALOG.format("Speichern bauen"), "P": DIALOG.format("Speichern bauen"),
          "M": "zustand.sicht === 'planung' && document.querySelector('.tl-bogen.blink')",
          "TH": "zustand.sicht === 'themen' && document.querySelector('.th-thema')?.textContent.includes('Spielstände')",
          "F": "zustand.sicht === 'fragen' && document.querySelector('.karte.blink')?.textContent.includes('Wie viele')",
          "B": "zustand.sicht === 'wissen' && document.querySelector('.karte.blink')?.textContent.includes('Es gibt drei')",
          "W": "zustand.sicht === 'wissen' && document.querySelector('.karte.blink')?.textContent.includes('Drei Plätze')",
          "#": "zustand.sicht === 'nachrichten' && document.querySelector('.nr-blase.diese')?.textContent.includes('Fertig, siehe')",
          "team": "zustand.sicht === 'teamchat' && document.querySelector('.tc-eintrag.blink')?.textContent.includes('Nur unter uns')"}

    def daten(self):
        self.nr, self.b = bestand(self.con, self.pid, self.ordner.name)

    def finden(self, such):
        self.oeffnen("start", "document.querySelector('#inhalt') && zustand.start")
        self.tab.js(f"void suchen({such!r})")
        self.warten("document.querySelector('.suche-genau .zeile')")
        return self.tab.js("document.querySelector('.liste .zeile').dataset.ref")

    def ref(self, k):
        return ("#" if k == "team" else k) + str(self.nr[k])

    def klick(self, k):
        self.assertEqual(self.finden(self.ref(k)), self.ref(k))
        self.tippen(".suche-genau .zeile")
        self.warten(self.OK[k], 12)
        self.assertEqual(self.tab.js("document.querySelectorAll('.toast.fehler').length"), 0, k)


class Pc(Wege):
    def test_jede_art_oeffnet(self):
        for g in ("pc", "handy"):
            self.groesse(g)
            for k in self.OK:
                with self.subTest(g=g, k=k):
                    self.klick(k)

    def test_zahl_ohne_kuerzel(self):
        for g in ("pc", "handy"):
            self.groesse(g)
            self.assertEqual(self.finden(str(self.nr["D"])), f"D{self.nr['D']}")
            self.tippen(".suche-genau .zeile")
            self.warten(self.OK["D"])

    def test_tastatur(self):
        self.finden(f"A{self.nr['A']}")
        self.tab.js("document.querySelector('.suche-genau .zeile').focus()")
        for typ in ("keyDown", "keyUp"):
            self.tab.senden("Input.dispatchKeyEvent", type=typ, key="Enter", code="Enter", windowsVirtualKeyCode=13)
        self.warten(self.OK["A"])

    def test_lauf_zeigt_seine_ausgabe(self):
        self.finden(f"L{self.nr['L']}")
        self.tippen(".suche-genau .zeile")
        self.warten(f"[...document.querySelectorAll('.dialog h3')].some(h => h.textContent.includes('L{self.nr['L']}'))")

    def test_was_es_nicht_gibt(self):
        for ref in ("F999999", "B999999", "W999999", "TH999999", "M999999", "P999999", "#999999"):
            self.oeffnen("start", "document.querySelector('#inhalt') && zustand.start")
            self.tab.js(f"void refOeffnen({ref!r})")
            self.warten(f"document.body.textContent.includes('{ref} lässt sich hier nicht öffnen')")
            self.assertEqual(self.tab.js("zustand.sicht"), "start", ref)

    def test_verweis_in_der_nachricht(self):
        self.oeffnen("nachrichten", "document.querySelector('.nr-blase a.verweis[data-ref]')")
        texte = self.tab.js("[...document.querySelectorAll('.nr-blase.diese a.verweis[data-ref]')].map(a => a.textContent)")
        self.assertEqual(texte, [f"D{self.nr['D']}", f"D{self.nr['D']}", f"A{self.nr['A']}"])
        self.tab.js("document.querySelector('.nr-blase.diese a.verweis[data-ref]').click()")
        self.warten(self.OK["D"])

    def test_verweis_im_bericht(self):
        self.oeffnen("dokumente", "document.querySelector('#inhalt')")
        self.tab.js(f"void dokumentDialog({self.nr['D']})")
        self.warten("document.querySelector('.dialog .md a.verweis[data-ref]')")
        # nicht im Code, nicht in Pfad und Version, nicht F5 und A4
        self.assertEqual(self.tab.js("[...document.querySelectorAll('.dialog .md a.verweis[data-ref]')].map(a => a.textContent)"),
                         [f"A{self.nr['A']}", f"B{self.nr['B']}"])
        self.tab.js("[...document.querySelectorAll('.dialog .md a.verweis[data-ref]')][1].click()")                  # Seite statt Dialog: der Dialog geht zu
        self.warten(self.OK["B"])
        self.assertEqual(self.tab.js("document.querySelectorAll('.dialog').length"), 0)

    def test_geschriebenes_im_dialog_geht_nicht_still_verloren(self):
        self.oeffnen("start", "document.querySelector('#inhalt') && zustand.start")
        self.tab.js(f"window.confirm = x => {{ window.__gefragt = x; return false; }}; void aufgabeDialog({self.nr['A']})")
        self.warten("document.querySelector('.dialog textarea')")
        self.tab.js(f"document.querySelector('.dialog textarea').value = 'Notiz'; void refOeffnen('B{self.nr['B']}')")
        self.warten("window.__gefragt === 'Änderungen verwerfen?'")
        self.assertEqual(self.tab.js("[zustand.sicht, document.querySelector('.dialog textarea').value]"), ["start", "Notiz"])

    def test_bilder(self):
        such = f"document.querySelector('.suche-genau .zeile') && document.querySelectorAll('.liste').length > 1"
        self.ueberall("start", "a2115-suche", bereit="document.querySelector('#inhalt') && zustand.start",
                      tun=f"void suchen('D{self.nr['D']}')", danach=such)
        self.ueberall("nachrichten", "a2115-nachricht", bereit="document.querySelector('.nr-eintrag')",
                      tun="document.querySelector('.nr-eintrag').click()", danach="document.querySelector('.nr-blase a.verweis[data-ref]')")


class Online(Wege, OnlineRundgang):
    def test_dieselbe_nummer(self):
        n = self.nr["D"]
        for g in ("pc", "handy"):
            self.groesse(g)
            for such in (f"D{n}", str(n)):
                self.assertEqual(self.finden(such), f"D{n}")
                self.tippen(".suche-genau .zeile")
                self.warten(self.OK["D"])

    def test_jede_art_oeffnet(self):
        for k in self.OK:
            with self.subTest(k=k):
                self.klick(k)

    def test_lauf_fuehrt_zum_betrieb(self):
        self.finden(f"L{self.nr['L']}")
        self.tippen(".suche-genau .zeile")
        self.warten("zustand.sicht === 'betrieb'")

    def test_text_findet_weiter_und_nicht_mehr(self):
        self.oeffnen("start", "document.querySelector('#inhalt') && zustand.start")
        refs = self.tab.js("(async () => (await abrufen('/api/suche?q=speicher')).map(x => x.ref))()")
        self.assertIn(f"D{self.nr['D']}", refs)
        self.assertIn(f"A{self.nr['A']}", refs)
        self.assertFalse([r for r in refs if r[0] in "LP" or r.startswith("TH")], refs)                  # nur über die Nummer, wie am PC


if __name__ == "__main__":
    unittest.main()
