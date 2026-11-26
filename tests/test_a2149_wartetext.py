"""A2149: Ein Wartetext von Hand blockiert nie länger als seine Gründe. Ist der letzte Grund erledigt (automatisch oder von Hand), leert
die AMW den Freitext mit (wie beim Start) – das Paket wird wieder Kandidat. Ein Freitext ganz ohne Grund steht nach 24 h im Leitstand
als „hängt ohne Grund“."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime
import json

from amw import db, kern, leitstand_daten, verteilen, wartegrund
from tests.test_verteilen import Grund, utc

TEXT = "Reihenfolge W2491: erst M16 (A2095, A2096)"


class Freitext(Grund):
    def wartet(self, auf="CC2", text=TEXT):
        a = self.aufgabe("Seite bauen")
        kern.aufgabe_status(self.con, self.pid, "TL", a, "wartet", auf=auf, wartet_auf=text)
        return a

    def freitext(self, a):
        return self.con.execute("SELECT wartet_auf FROM aufgabe WHERE id = ?", (a,)).fetchone()[0]

    def kandidat(self, a):
        return a in [x["id"] for x, _ in verteilen.kandidaten(self.con, self.pid)]

    def test_letzter_grund_erledigt_leert_den_freitext_und_macht_kandidat(self):
        a = self.wartet()
        self.assertEqual(self.freitext(a), TEXT)
        self.assertFalse(self.kandidat(a))
        with db.schreiben(self.con):
            self.assertEqual(wartegrund.erledige(self.con, self.pid, "agent", "CC2", "CC2 hat geschrieben"), [a])
        self.assertIsNone(self.freitext(a))
        self.assertTrue(self.kandidat(a))
        e, = [json.loads(r[0]) for r in self.con.execute("SELECT text FROM plan_ereignis WHERE aufgabe_id = ? AND art = ?",
                                                         (a, wartegrund.FREITEXT_GELEERT))]
        self.assertEqual(e, {"text": TEXT, "durch": "CC2 hat geschrieben"})

    def test_noch_ein_grund_offen_der_freitext_bleibt(self):
        a = self.wartet(auf="CC2,CC1")
        with db.schreiben(self.con):
            wartegrund.erledige(self.con, self.pid, "agent", "CC2", "CC2 hat geschrieben")
        self.assertEqual(self.freitext(a), TEXT)
        self.assertFalse(self.kandidat(a))

    def test_von_hand_abgehakt_ebenso(self):
        a = self.wartet()
        kern.aufgabe_status(self.con, self.pid, "TL", a, "wartet", erledigt="CC2")
        self.assertIsNone(self.freitext(a))
        self.assertTrue(self.kandidat(a))

    def test_leise_erledigt_leert_auch(self):
        a = self.wartet()
        with db.schreiben(self.con):
            wartegrund.erledige(self.con, self.pid, "agent", "CC2", "still", leise=True)
        self.assertIsNone(self.freitext(a))

    def test_laufende_aufgabe_behaelt_ihren_text(self):
        a = self.wartet(auf="CC2,CC1")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'laeuft', wartet_auf = 'Notiz' WHERE id = ?", (a,))
            wartegrund.erledige(self.con, self.pid, "agent", "CC2", "x")
            wartegrund.erledige(self.con, self.pid, "agent", "CC1", "x")
        self.assertEqual(self.freitext(a), "Notiz")


class HaengtOhneGrund(Grund):
    def ohne_grund(self, titel, stunden):
        a = self.aufgabe(titel)
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'wartet', wartet_auf = ?, angelegt_utc = ? WHERE id = ?",
                             (TEXT, utc(self.jetzt - stunden * 3600), a))
        return a

    def test_nach_24_stunden_im_leitstand(self):
        alt = self.ohne_grund("Alt", 25)
        self.ohne_grund("Frisch", 23)
        mit = self.ohne_grund("Mit Grund", 30)
        with db.schreiben(self.con):
            wartegrund.anlegen(self.con, self.pid, "TL", mit, "CC2")
        self.assertEqual([x["id"] for x in wartegrund.haengt_ohne_grund(self.con, self.pid, jetzt=self.jetzt)], [alt])
        d = leitstand_daten.daten(self.con, self.pid, jetzt=datetime.datetime.fromtimestamp(self.jetzt, datetime.timezone.utc))
        (h,) = d["haengt"]
        self.assertEqual((h["titel"], h["nummer"], h["wartet_auf"]), ("Alt", f"A{alt}", TEXT))

    def test_seit_dem_letzten_erledigten_grund(self):
        a = self.ohne_grund("Alter Auftrag", 100)
        with db.schreiben(self.con):
            wartegrund.anlegen(self.con, self.pid, "TL", a, "CC2")
            self.con.execute("UPDATE wartegrund SET erledigt_utc = ? WHERE aufgabe_id = ?", (utc(self.jetzt - 2 * 3600), a))
            self.con.execute("UPDATE aufgabe SET wartet_auf = ? WHERE id = ?", (TEXT, a))     # Altdaten: Text blieb stehen
        self.assertEqual(wartegrund.haengt_ohne_grund(self.con, self.pid, jetzt=self.jetzt), [])
        self.assertEqual([x["id"] for x in wartegrund.haengt_ohne_grund(self.con, self.pid, jetzt=self.jetzt + 23 * 3600)], [a])

    def test_ohne_freitext_haengt_nichts(self):
        a = self.ohne_grund("Leer", 30)
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET wartet_auf = '  ' WHERE id = ?", (a,))
        self.assertEqual(wartegrund.haengt_ohne_grund(self.con, self.pid, jetzt=self.jetzt), [])
