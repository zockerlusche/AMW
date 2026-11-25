"""Meilenstein-Karte für den Menschen (A1777, B2816): „Vorziehen“ eins nach vorn mit Meldung an den Lead; die Daten der
Karte – woran jede offene Aufgabe hängt (Frage an den Menschen, Lauf mit Platz in der Schlange, Prüfbitte), „verschoben
aus …“ und aus dem Meilenstein Weggezogenes."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import tempfile
import unittest

from amw import aktionen, db, kern, planung, wartegrund, workbench


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Eins", angelegt_utc=db.jetzt())
            self.fremd = db.einfuegen(self.con, "projekt", name="Zwei", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")

    def bogen(self, titel):
        return planung.bogen_neu(self.con, self.pid, "TL", titel, ziel="z", abnahme="a")

    def aufgabe(self, titel, bid, agent="CC1"):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel, agent=agent)
        planung.schritt_setzen(self.con, self.pid, "TL", aid=aid, bogen_id=bid)
        return aid

    def reihe(self):
        return [r[0] for r in self.con.execute("SELECT id FROM bogen WHERE projekt_id = ? ORDER BY nr, id", (self.pid,))]

    def an_lead(self):
        return [r[0] for r in self.con.execute("SELECT n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id"
                                               " WHERE e.agent = 'TL' ORDER BY n.id")]


class Vorziehen(Grund):
    def test_eins_nach_vorn_ueber_fertige_hinweg_mit_meldung(self):
        b1, b2, b3 = self.bogen("Eins"), self.bogen("Zwei"), self.bogen("Drei")
        planung.bogen_status(self.con, self.pid, "TL", b1, "fertig")
        r = aktionen.planen(self.con, self.pid, "bogen", {"aktion": "vorziehen", "bogen": b3})
        self.assertEqual(r, {"bogen": b3, "vor": b2})
        self.assertEqual(self.reihe(), [b1, b3, b2])
        self.assertTrue(any("M2 „Drei“ vorgezogen" in k and "vor M3 " in k for k in self.an_lead()))     # neu durchgezählt: Drei = M2, Zwei = M3
        art = self.con.execute("SELECT art, text FROM plan_ereignis WHERE bogen_id = ? ORDER BY id DESC LIMIT 1", (b3,)).fetchone()
        self.assertEqual((art["art"], art["text"]), ("bogen_vorziehen", "vor M3"))
        with self.assertRaisesRegex(aktionen.Ungueltig, "schon vorn"):     # davor nur noch der fertige
            aktionen.planen(self.con, self.pid, "bogen", {"aktion": "vorziehen", "bogen": b3})

    def test_nur_der_mensch_und_nur_offene(self):
        b1, b2 = self.bogen("Eins"), self.bogen("Zwei")
        with self.assertRaisesRegex(kern.AmwFehler, "Knopf des Menschen"):
            planung.bogen_vorziehen(self.con, self.pid, "TL", b2)
        planung.bogen_status(self.con, self.pid, "TL", b2, "verworfen")
        with self.assertRaisesRegex(kern.AmwFehler, "verworfen"):
            planung.bogen_vorziehen(self.con, self.pid, kern.ENTWICKLER, b2)
        self.assertEqual(self.reihe(), [b1, b2])


class Karte(Grund):
    def test_woran_offene_aufgaben_haengen(self):
        bid = self.bogen("Karte")
        frage_a, lauf_a, pruef_a = self.aufgabe("Symbol", bid), self.aufgabe("Schlange", bid), self.aufgabe("Knopf", bid)
        fid = kern.frage_neu(self.con, self.pid, "TL", "entwickler", "Wie soll das Symbol aussehen?", [("A", "rund")], "A", "weil",
                             geprueft="keine Treffer")
        with db.schreiben(self.con):
            jetzt = db.jetzt()
            vorher = db.einfuegen(self.con, "lauf", projekt_id=self.fremd, agent="X1", beschreibung="fremder Lauf", status="angemeldet",
                                  angemeldet_utc=jetzt)
            lid = db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="CC1", beschreibung="Gesamtlauf vor der Auslieferung",
                               status="angemeldet", angemeldet_utc=jetzt)
            wartegrund.anlegen(self.con, self.pid, "CC1", frage_a, f"F{fid}")
            wartegrund.anlegen(self.con, self.pid, "CC1", lauf_a, f"L{lid}")
            self.con.execute("UPDATE aufgabe SET status = 'wartet' WHERE id IN (?, ?)", (frage_a, lauf_a))
            db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=pruef_a, zweig="z", sha="abc1234", bauer="CC1", pruefer="TL",
                         angefragt_utc=jetzt)
        self.assertLess(vorher, lid)
        b = next(x for x in workbench.daten_planung(self.con, self.pid)["boegen"] if x["id"] == bid)
        s = {x["id"]: x for x in b["schritte"]}
        g = s[frage_a]["gruende"][0]
        self.assertEqual((g["art"], g["bezug"], g["an_dich"], g["kurz"]), ("frage", f"F{fid}", True, "Wie soll das Symbol aussehen?"))
        g = s[lauf_a]["gruende"][0]
        self.assertEqual((g["bezug"], g["kurz"], g["status"], g["platz"], g["von"], g["vor_fremd"]),
                         (f"L{lid}", "Gesamtlauf vor der Auslieferung", "angemeldet", 2, 2, 1))
        self.assertNotIn("Zwei", str(g))                                          # fremdes Projekt nur als Zahl
        self.assertEqual((s[pruef_a]["pruefung"]["pruefer"], s[pruef_a]["gruende"]), ("TL", []))
        for x in s.values():
            self.assertTrue(x["angelegt_utc"])

    def test_verschoben_aus_und_weggezogen(self):
        alt, neu = self.bogen("Alt"), self.bogen("Neu")
        aid = self.aufgabe("Wandert", alt)
        planung.schritt_setzen(self.con, self.pid, "TL", aid=aid, bogen_id=neu)
        boegen = {x["id"]: x for x in workbench.daten_planung(self.con, self.pid)["boegen"]}
        a = next(x for x in boegen[neu]["schritte"] if x["id"] == aid)
        self.assertEqual(a["verschoben_aus"]["bogen"], alt)
        self.assertEqual([(w["id"], w["nach"]) for w in boegen[alt]["weg"]], [(aid, neu)])
        self.assertEqual(boegen[neu]["weg"], [])
        planung.schritt_setzen(self.con, self.pid, "TL", aid=aid, bogen_id=alt)        # zurück: nicht mehr „weggezogen“
        boegen = {x["id"]: x for x in workbench.daten_planung(self.con, self.pid)["boegen"]}
        self.assertEqual(boegen[alt]["weg"], [])
        self.assertEqual(next(x for x in boegen[alt]["schritte"] if x["id"] == aid)["verschoben_aus"]["bogen"], neu)

    def test_verschiebung_aus_keinem_meilenstein_zaehlt_nicht(self):
        bid = self.bogen("Ziel")
        aid = self.aufgabe("Neu dazu", bid)                                          # „– → bid“: kein „verschoben aus“
        b = next(x for x in workbench.daten_planung(self.con, self.pid)["boegen"] if x["id"] == bid)
        self.assertIsNone(next(x for x in b["schritte"] if x["id"] == aid)["verschoben_aus"])
        self.assertEqual(workbench._verschoben("– → 5"), (None, 5))
        self.assertEqual(workbench._verschoben("3 → None"), (3, None))


if __name__ == "__main__":
    unittest.main()
