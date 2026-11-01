"""Tests für Läufe, Prüfungen, Anweisungen, Rezepte, Wortlaut, Beschlüsse, Regeln, Notizen, Release Notes, Parken."""
import os
import sqlite3
import tempfile
import unittest

from amw import betrieb, cli, db, kern, wissen


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        for k, r in (("TL", "lead"), ("CC1", None), ("CC2", None)):
            kern.agent_neu(self.con, self.pid, k, rolle=r)

    def tearDown(self):
        self.con.close()
        self.ordner.cleanup()


class Laeufe(Grund):
    def test_ein_schwerer_lauf_zur_zeit_und_speichergrenze(self):
        l1 = betrieb.lauf_start(self.con, self.pid, "CC1", "Build", speicher_frei=20)
        with self.assertRaises(kern.AmwFehler) as e:
            betrieb.lauf_start(self.con, self.pid, "CC2", "Test", speicher_frei=20)
        self.assertIn(f"L{l1}", str(e.exception))
        betrieb.lauf_start(self.con, self.pid, "CC2", "Lint", schwer=False, speicher_frei=1)   # leicht: keine Grenze
        with self.assertRaises(kern.AmwFehler):
            betrieb.lauf_ende(self.con, self.pid, "CC2", l1, 0)                                   # fremder Lauf
        betrieb.lauf_ende(self.con, self.pid, "CC1", l1, 0, "ok")
        with self.assertRaises(kern.AmwFehler) as e:
            betrieb.lauf_start(self.con, self.pid, "CC2", "Test", speicher_frei=5)
        self.assertIn("GB frei", str(e.exception))

    def test_rezept_bestimmt_schirm_und_grenze(self):
        betrieb.rezept_setzen(self.con, self.pid, "abnahme", "gd_ablaeufe.ps1", "am Schirm", schirm=True, speicher_gb=6)
        betrieb.lauf_start(self.con, self.pid, "CC2", "Abnahme", rezept="abnahme", speicher_frei=7)
        with self.assertRaises(kern.AmwFehler):
            betrieb.lauf_start(self.con, self.pid, "CC1", "zweiter Schirm", rezept="abnahme", speicher_frei=30)
        self.assertEqual(betrieb.rezept_setzen(self.con, self.pid, "abnahme", "neu.ps1"), "geändert")

    def test_halt_blockiert_laeufe(self):
        kern.halt(self.con, self.pid, "TL", "alle", "Pause")
        with self.assertRaises(kern.AmwFehler):
            betrieb.lauf_start(self.con, self.pid, "CC1", "Build", speicher_frei=20)


class Warteschlange(Grund):
    """lauf start --warten : Reihenfolge der Anmeldung, niemand überholt, Freigabe weckt den Agenten."""
    def setUp(self):
        super().setUp()
        kern.agent_neu(self.con, self.pid, "CC3")
        with db.schreiben(self.con):
            for k in ("CC1", "CC2", "CC3"):
                aid = self.con.execute("SELECT id FROM agent WHERE kennung = ?", (k,)).fetchone()[0]
                db.einfuegen(self.con, "sitzung", agent_id=aid, gestartet_utc=db.jetzt())

    def status(self, lid):
        return self.con.execute("SELECT status FROM lauf WHERE id = ?", (lid,)).fetchone()[0]

    def start(self, agent, warten=False, frei=20, **k):
        return betrieb.lauf_start(self.con, self.pid, agent, "Lauf " + agent, speicher_frei=frei, warten=warten, **k)

    def test_reihenfolge_freigabe_und_kein_ueberholen(self):
        l1 = self.start("CC1")
        with self.assertRaises(kern.AmwFehler) as e:
            self.start("CC2")
        self.assertIn("--warten", str(e.exception))
        l2, l3 = self.start("CC2", True), self.start("CC3", True)
        self.assertEqual((self.status(l2), self.status(l3)), ("angemeldet", "angemeldet"))
        self.start("CC1", schwer=False)                                   # leichte Läufe warten nie
        self.assertEqual(betrieb.lauf_ende(self.con, self.pid, "CC1", l1, 0, speicher_frei=20), [l2])
        self.assertEqual((self.status(l2), self.status(l3)), ("laeuft", "angemeldet"))
        frei = kern.offene(self.con, self.pid, "CC2")[0]
        self.assertEqual((frei["art"], frei["von"]), ("freigabe", "AMW"))
        self.assertIn(f"L{l2} ist dran", frei["kurz"])
        self.assertEqual(betrieb.lauf_ende(self.con, self.pid, "CC2", l2, 0, speicher_frei=2), [])   # Speicher knapp
        with self.assertRaises(kern.AmwFehler) as e:                      # der Schnellste überholt nicht mehr
            self.start("CC1")
        self.assertIn(f"L{l3} von CC3", str(e.exception))
        self.assertEqual(betrieb.warteschlange(self.con, self.pid, speicher_frei=20), [l3])   # Wächter-Durchgang

    def test_vorziehen_nur_lead_und_aus_der_schlange_nehmen(self):
        l1 = self.start("CC1")
        l2, l3 = self.start("CC2", True), self.start("CC3", True)
        with self.assertRaises(kern.AmwFehler):
            betrieb.lauf_vorziehen(self.con, self.pid, "CC3", l3)
        betrieb.lauf_vorziehen(self.con, self.pid, "TL", l3)
        self.assertEqual([r["id"] for r in betrieb.wartende(self.con, self.pid)], [l3, l2])
        betrieb.lauf_ende(self.con, self.pid, "CC3", l3, None, speicher_frei=20)   # zurückziehen
        self.assertEqual(self.status(l3), "abgebrochen")
        self.assertEqual(betrieb.lauf_ende(self.con, self.pid, "CC1", l1, 0, speicher_frei=20), [l2])

    def test_agent_ohne_sitzung_wird_uebersprungen(self):
        l1 = self.start("CC1")
        l2, l3 = self.start("TL", True), self.start("CC2", True)             # TL hat hier keine Sitzung
        self.assertEqual(betrieb.lauf_ende(self.con, self.pid, "CC1", l1, 0, speicher_frei=20), [l3])
        self.assertEqual(self.status(l2), "angemeldet")


class Pruefungen(Grund):
    def test_bitte_ergebnis_und_ist_gruen(self):
        prid = betrieb.pruefbitte(self.con, self.pid, "CC1", "CC2", "cc1-x", "abcdef1234", "P1–P3")
        self.assertEqual(kern.offene(self.con, self.pid, "CC2")[0]["art"], "pruefbitte")
        self.assertIsNone(betrieb.ist_gruen(self.con, self.pid, "abcdef1"))
        with self.assertRaises(kern.AmwFehler):
            betrieb.pruefung_ergebnis(self.con, self.pid, "CC1", prid, "gruen")                 # Bauer prüft nicht selbst
        betrieb.pruefung_ergebnis(self.con, self.pid, "CC2", prid, "gruen", "alles da")
        self.assertIsNotNone(betrieb.ist_gruen(self.con, self.pid, "abcdef1"))
        self.assertIn("GRUEN", kern.offene(self.con, self.pid, "CC1")[0]["kurz"])
        with self.assertRaises(kern.AmwFehler):
            betrieb.pruefung_ergebnis(self.con, self.pid, "CC2", prid, "rot")


class Anweisungen(Grund):
    def test_hinweis_erscheint_im_kontext_und_laesst_sich_aufheben(self):
        with self.assertRaises(kern.AmwFehler):
            betrieb.hinweis(self.con, self.pid, "CC1", "alle", "x")
        sid = betrieb.hinweis(self.con, self.pid, "TL", "CC2", "keine Rechen-Jobs bis morgen")
        anweisung = "Geltende Anweisungen: TL: keine Rechen-Jobs"
        self.assertIn(anweisung, kern.kontext(self.con, self.pid, "CC2"))
        self.assertNotIn(anweisung, kern.kontext(self.con, self.pid, "CC1"))
        self.assertEqual(betrieb.sperre_aufheben(self.con, self.pid, "TL", sid), 1)
        self.assertNotIn(anweisung, kern.kontext(self.con, self.pid, "CC2"))


class Wissen(Grund):
    def test_regel_nur_mit_beschluss_und_an_ort_und_stelle(self):
        with self.assertRaises(kern.AmwFehler):
            wissen.regel_setzen(self.con, self.pid, "TL", "arbeit", 1, "Text", 999)
        b1 = wissen.beschluss_neu(self.con, self.pid, "TL", "Regel 1", "erste Fassung", "Entwickler")
        self.assertEqual(wissen.regel_setzen(self.con, self.pid, "TL", "arbeit", 1, "erste Fassung", b1), "angelegt")
        b2 = wissen.beschluss_neu(self.con, self.pid, "TL", "Regel 1 neu", "zweite Fassung", "Entwickler", ersetzt=b1)
        self.assertEqual(wissen.regel_setzen(self.con, self.pid, "TL", "arbeit", 1, "zweite Fassung", b2), "geändert")
        r = self.con.execute("SELECT count(*), text, beleg FROM regel").fetchone()
        self.assertEqual(tuple(r), (1, "zweite Fassung", f"B{b2}"))
        alt = self.con.execute("SELECT status, ersetzt_durch FROM beschluss WHERE id = ?", (b1,)).fetchone()
        self.assertEqual(tuple(alt), ("ueberholt", b2))

    def test_wortlaut_nur_lead_und_unveraenderlich(self):
        with self.assertRaises(kern.AmwFehler):
            wissen.wortlaut_neu(self.con, self.pid, "CC1", "x", "chat-tl")
        wid = wissen.wortlaut_neu(self.con, self.pid, "TL", "Mach weiter.", "chat-tl")
        with self.assertRaises(sqlite3.DatabaseError):
            self.con.execute("UPDATE wortlaut SET text = 'anders' WHERE id = ?", (wid,))

    def test_notiz_und_parken(self):
        self.assertEqual(wissen.notiz_setzen(self.con, self.pid, "TL", "betrieb", "a"), "angelegt")
        self.assertEqual(wissen.notiz_setzen(self.con, self.pid, "TL", "betrieb", "b"), "geändert")
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Idee", agent="CC1")
        wissen.einstufen(self.con, self.pid, "CC1", aid, "geparkt")
        a = self.con.execute("SELECT einstufung, geparkt_von FROM aufgabe WHERE id = ?", (aid,)).fetchone()
        self.assertEqual(tuple(a), ("geparkt", "CC1"))
        with self.assertRaises(kern.AmwFehler):
            wissen.einstufen(self.con, self.pid, "CC2", aid, "aktiv")

    def test_release_merge_und_version(self):
        wissen.release_merge(self.con, self.pid, "CC3", "Fragen-Seite", "aaa111", aufgaben="A1206")
        wissen.release_merge(self.con, self.pid, "CC3", "Wache robust", "bbb222", aufgaben="A1190")
        rid, n = wissen.release_version(self.con, self.pid, "TL", "0.5.0", "Workbench")
        self.assertEqual(n, 2)
        v = self.con.execute("SELECT text_intern, aufgaben FROM release WHERE id = ?", (rid,)).fetchone()
        self.assertIn("- Fragen-Seite", v["text_intern"])
        self.assertEqual(v["aufgaben"], "A1206, A1190")
        with self.assertRaises(kern.AmwFehler):
            wissen.release_version(self.con, self.pid, "TL", "0.5.0", "doppelt")


class Kommandozeile(Grund):
    def test_ist_gruen_liefert_rueckgabecode(self):
        self.con.close()
        os.environ["AMW_DB"] = os.path.join(self.ordner.name, "t.db")
        try:
            self.assertEqual(cli.main(["--von", "CC1", "pruefung", "ist-gruen", "--sha", "fff"]), 3)
            self.assertEqual(cli.main(["--von", "CC1", "pruefung", "bitte", "--pruefer", "CC2", "--zweig", "z",
                                       "--sha", "fff000"]), 0)
            self.assertEqual(cli.main(["--von", "CC2", "pruefung", "gruen", "1"]), 0)
            self.assertEqual(cli.main(["--von", "CC1", "pruefung", "ist-gruen", "--sha", "fff000"]), 0)
        finally:
            os.environ.pop("AMW_DB", None)
            self.con = db.verbinde(os.path.join(self.ordner.name, "t.db"))


class NotizEntfernen(Grund):
    def test_nur_lead_oder_mit_beschluss(self):
        wissen.notiz_setzen(self.con, self.pid, "TL", "alt_1", "x")
        wissen.notiz_setzen(self.con, self.pid, "TL", "alt_2", "y")
        wissen.notiz_setzen(self.con, self.pid, "TL", "bleibt", "z")
        with self.assertRaises(kern.AmwFehler):
            wissen.notiz_entfernen(self.con, self.pid, "CC1", ["alt_1"])
        b = wissen.beschluss_neu(self.con, self.pid, "TL", "Notizen aufräumen", "alt_* weg", "Entwickler")
        weg, fehlt = wissen.notiz_entfernen(self.con, self.pid, "CC1", ["alt_1", "gibtsnicht"], beschluss=b)
        self.assertEqual((weg, fehlt), (["alt_1"], ["gibtsnicht"]))
        self.assertEqual(wissen.notiz_entfernen(self.con, self.pid, "TL", ["alt_2"])[0], ["alt_2"])
        self.assertEqual([r[0] for r in self.con.execute("SELECT schluessel FROM notiz")], ["bleibt"])


if __name__ == "__main__":
    unittest.main()
