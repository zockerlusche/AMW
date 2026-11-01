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
        k = kern.kontext(self.con, self.pid, "CC1")
        self.assertIn("A1 [wartet] Eigenes", k)
        self.assertIn("Wartet auf dich: A2 (CC2) Fremdes", k)
        self.assertLessEqual(len(k), kern.KONTEXT_MAX)


if __name__ == "__main__":
    unittest.main()
