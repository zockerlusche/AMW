"""Tests für Datenmodell und Fachlogik (Stufe 1). Aufruf: python -m unittest discover -s tests (in F:\\amw)."""
import json
import os
import sqlite3
import tempfile
import unittest

from amw import db, kern


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1", rolle="bauer")
        kern.agent_neu(self.con, self.pid, "CC2", rolle="pruefer")
        kern.agent_neu(self.con, self.pid, "CC7", rolle="3d", empfaengt_rund=False)

    def tearDown(self):
        self.con.close()
        self.ordner.cleanup()


class Nachrichten(Grund):
    def test_rundschreiben_ohne_absender_und_ohne_abgemeldete(self):
        _, namen = kern.posten(self.con, self.pid, "TL", "alle", "info", "x")
        self.assertEqual(namen, ["CC1", "CC2"])

    def test_unbekannte_art_und_unbekannter_empfaenger(self):
        with self.assertRaises(kern.AmwFehler):
            kern.posten(self.con, self.pid, "TL", "CC1", "befund", "x")
        with self.assertRaises(kern.AmwFehler):
            kern.posten(self.con, self.pid, "TL", "CC9", "info", "x")

    def test_erledigt_mehrere_nur_eigene(self):
        n1, _ = kern.posten(self.con, self.pid, "TL", "CC1,CC2", "auftrag", "a")
        n2, _ = kern.posten(self.con, self.pid, "TL", "CC1", "auftrag", "b")
        self.assertEqual(kern.erledigt(self.con, self.pid, "CC1", [n1, n2]), 2)
        self.assertEqual(len(kern.offene(self.con, self.pid, "CC1")), 0)
        self.assertEqual(len(kern.offene(self.con, self.pid, "CC2")), 1)

    def test_lesen_markiert_gelesen(self):
        nid, _ = kern.posten(self.con, self.pid, "TL", "CC1", "auftrag", "a")
        kern.lesen(self.con, self.pid, "CC1", nid)
        self.assertEqual(kern.offene(self.con, self.pid, "CC1")[0]["status"], "gelesen")

    def test_verlauf_nicht_loeschbar(self):
        nid, _ = kern.posten(self.con, self.pid, "TL", "CC1", "info", "a")
        with self.assertRaises(sqlite3.DatabaseError):
            self.con.execute("DELETE FROM nachricht WHERE id = ?", (nid,))


class Aufgaben(Grund):
    def test_besitz(self):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "t", agent="CC1")
        with self.assertRaises(kern.AmwFehler):
            kern.aufgabe_status(self.con, self.pid, "CC2", aid, "start")
        self.assertEqual(kern.aufgabe_status(self.con, self.pid, "TL", aid, "start"), "laeuft")

    def test_fertig_nur_mit_beleg_auch_per_sql(self):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "t", agent="CC1")
        with self.assertRaises(kern.AmwFehler):
            kern.aufgabe_status(self.con, self.pid, "CC1", aid, "fertig")
        with self.assertRaises(sqlite3.DatabaseError):
            self.con.execute("UPDATE aufgabe SET status = 'fertig' WHERE id = ?", (aid,))
        kern.aufgabe_status(self.con, self.pid, "CC1", aid, "fertig", beleg="abc")
        a = self.con.execute("SELECT status, beleg, fertig_utc FROM aufgabe WHERE id = ?", (aid,)).fetchone()
        self.assertEqual((a["status"], a["beleg"]), ("fertig", "abc"))
        self.assertTrue(a["fertig_utc"])


class Halt(Grund):
    def test_nur_lead_setzt_halt(self):
        with self.assertRaises(kern.AmwFehler):
            kern.halt(self.con, self.pid, "CC1", "alle", "x")

    def test_halt_stoppt_start_und_weiter_hebt_auf(self):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "t", agent="CC1")
        kern.halt(self.con, self.pid, "TL", "alle", "Pause")
        self.assertTrue(kern.halt_gilt(self.con, self.pid, "CC1"))
        arten = [r["art"] for r in kern.offene(self.con, self.pid, "CC1")]
        self.assertEqual(arten, ["stopp"])
        with self.assertRaises(kern.AmwFehler):
            kern.aufgabe_status(self.con, self.pid, "CC1", aid, "start")
        self.assertIn("HALT GILT", kern.kontext(self.con, self.pid, "CC1"))
        self.assertEqual(kern.weiter(self.con, self.pid, "Entwickler", "alle"), 1)
        self.assertFalse(kern.halt_gilt(self.con, self.pid, "CC1"))
        kern.aufgabe_status(self.con, self.pid, "CC1", aid, "start")

    def test_halt_fuer_einen_agenten(self):
        kern.halt(self.con, self.pid, "TL", "CC2", "nur du")
        self.assertTrue(kern.halt_gilt(self.con, self.pid, "CC2"))
        self.assertFalse(kern.halt_gilt(self.con, self.pid, "CC1"))


class Fragen(Grund):
    def test_frage_an_entwickler_braucht_empfehlung_und_grund(self):
        with self.assertRaises(kern.AmwFehler):
            kern.frage_neu(self.con, self.pid, "TL", "entwickler", "x?", [("A", "a"), ("B", "b")])
        with self.assertRaises(kern.AmwFehler):
            kern.frage_neu(self.con, self.pid, "TL", "entwickler", "x?", [("A", "a")], "C", "weil")

    def test_antwort_per_option_benachrichtigt_fragesteller(self):
        fid = kern.frage_neu(self.con, self.pid, "TL", "entwickler", "x?", [("A", "a"), ("B", "b")], "A", "weil")
        self.assertEqual(kern.frage_antworten(self.con, self.pid, fid, "option", "B", "seite"), "beantwortet")
        offen = kern.offene(self.con, self.pid, "TL")
        self.assertEqual(offen[0]["art"], "antwort")
        with self.assertRaises(kern.AmwFehler):
            kern.frage_antworten(self.con, self.pid, fid, "option", "A", "seite")

    def test_rueckfrage_bleibt_offen_und_wortlaut_wird_gespeichert(self):
        fid = kern.frage_neu(self.con, self.pid, "TL", "entwickler", "x?", [("A", "a")], "A", "weil")
        self.assertEqual(kern.frage_antworten(self.con, self.pid, fid, "rueckfrage", "Was heißt a?", "seite"), "offen")
        w = self.con.execute("SELECT text, kanal FROM wortlaut").fetchone()
        self.assertEqual((w["text"], w["kanal"]), ("Was heißt a?", "seite"))
        self.assertEqual(kern.offene(self.con, self.pid, "TL")[0]["art"], "frage")

    def test_frage_an_tl_weckt_lead(self):
        fid = kern.frage_neu(self.con, self.pid, "CC1", "tl", "darf ich?", [])
        self.assertIn(f"F{fid}", kern.offene(self.con, self.pid, "TL")[0]["kurz"])
        self.assertEqual(json.loads(self.con.execute("SELECT optionen FROM frage").fetchone()[0]), [])


class Kontext(Grund):
    def test_kontext_enthaelt_aufgaben_wartende_und_bleibt_kurz(self):
        kern.aufgabe_neu(self.con, self.pid, "TL", "Eigenes", agent="CC1")
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Fremdes", agent="CC2")
        kern.aufgabe_status(self.con, self.pid, "CC2", aid, "blockiert", wartet_auf="CC1 Antwort")
        for i in range(300):
            kern.posten(self.con, self.pid, "TL", "CC1", "info", "lange Zeile " * 20)
        kern.posten(self.con, self.pid, "TL", "CC1", "auftrag", "die neueste")
        k = kern.kontext(self.con, self.pid, "CC1")
        self.assertIn("Offene Nachrichten (301, neueste zuerst): #301 TL [auftrag] die neueste", k)
        self.assertIn("A1 [wartet] Eigenes", k)
        self.assertIn("Wartet auf dich: A2 (CC2) Fremdes", k)
        self.assertLessEqual(len(k), kern.KONTEXT_MAX)


class Verlauf(unittest.TestCase):
    """Gespräch zu einer Frage: Rückfrage, Nachtrag (auch per Antwort auf die Rückfrage), Antwort."""
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.pfad = os.path.join(self.ordner.name, "v.db")
        self.con = db.anlegen(self.pfad)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")

    def tearDown(self):
        self.con.close()
        self.ordner.cleanup()

    def verlauf(self, fid):
        return [(r[0], r[1]) for r in self.con.execute("SELECT von, art FROM frage_verlauf WHERE frage_id = ? ORDER BY id", (fid,))]

    def test_gespraech(self):
        fid = kern.frage_neu(self.con, self.pid, "TL", "entwickler", "Lücke?", [("A", "füllen"), ("B", "lassen")], "A", "weil")
        self.assertEqual(kern.frage_antworten(self.con, self.pid, fid, "rueckfrage", "Ist mit A die Lücke gefüllt?", "seite"), "offen")
        rf = self.con.execute("SELECT nachricht_id FROM frage_verlauf WHERE frage_id = ?", (fid,)).fetchone()[0]
        kern.posten(self.con, self.pid, "TL", "Entwickler", "antwort", "Ja, A füllt beide Lücken", antwort_auf=rf)
        kern.frage_nachtrag(self.con, self.pid, "TL", fid, "Ergänzung: Quellen kommen ab Ä2")
        with self.assertRaises(kern.AmwFehler):
            kern.frage_nachtrag(self.con, self.pid, "CC1", fid, "fremd")
        kern.frage_antworten(self.con, self.pid, fid, "option", "A", "seite")
        self.assertEqual(self.verlauf(fid), [("Entwickler", "rueckfrage"), ("TL", "nachtrag"), ("TL", "nachtrag"), ("Entwickler", "antwort")])
        self.assertEqual(self.con.execute("SELECT text FROM frage_verlauf WHERE art = 'antwort'").fetchone()[0], "A) füllen")
        an_dich = self.con.execute("SELECT count(*) FROM empfang WHERE agent = 'Entwickler'").fetchone()[0]
        self.assertEqual(an_dich, 2)                                  # Antwort auf die Rückfrage + Nachtrag
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute("DELETE FROM frage_verlauf")

    def test_alte_datenbank_wird_umgestellt(self):
        fid = kern.frage_neu(self.con, self.pid, "TL", "entwickler", "Alt?", [("A", "a")], "A", "weil")
        self.con.execute("DROP TABLE frage_verlauf")                 # wie eine Datenbank mit Schema 1
        self.con.execute("UPDATE frage SET antwort_art = 'rueckfrage', antwort = 'Wie gemeint?' WHERE id = ?", (fid,))
        self.con.execute("ALTER TABLE lauf DROP COLUMN rang")          # Schema 2 kannte die Warteschlange nicht
        self.con.execute("PRAGMA user_version = 1")
        self.con.close()
        self.con = db.verbinde(self.pfad)
        self.assertEqual(self.con.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
        self.assertEqual(self.verlauf(fid), [("Entwickler", "rueckfrage")])


if __name__ == "__main__":
    unittest.main()
