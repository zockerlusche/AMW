"""Tests für die Datei-Brücke des TL: Lesekopie ohne WAL, Befehlsdateien als --von TL."""
import json
import os
import sqlite3
import tempfile
import time
import unittest

from amw import bruecke, db, kern


class Bruecke(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.alt_db = os.environ.get("AMW_DB")
        os.environ["AMW_DB"] = os.path.join(self.ordner.name, "amw.db")
        self.con = db.anlegen()
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.eingang = os.path.join(self.ordner.name, "eingang-tl")

    def tearDown(self):
        self.con.close()
        if self.alt_db is None:
            os.environ.pop("AMW_DB", None)
        else:
            os.environ["AMW_DB"] = self.alt_db
        self.ordner.cleanup()

    def einwerfen(self, name, inhalt):
        ordner = os.path.join(self.eingang, "befehle")
        os.makedirs(ordner, exist_ok=True)
        pfad = os.path.join(ordner, name)
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(inhalt, f)
        alt = time.time() - 5
        os.utime(pfad, (alt, alt))

    def ergebnis(self, stamm):
        with open(os.path.join(self.eingang, "erledigt", stamm + ".ergebnis.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_lesekopie_ohne_wal_und_unveraenderlich_lesbar(self):
        kern.posten(self.con, self.pid, "CC1", "TL", "meldung", "hallo")
        stand = bruecke.lese_kopie()
        ziel = os.path.join(self.ordner.name, "tl_lesen.db")
        k = sqlite3.connect(f"file:{ziel}?immutable=1", uri=True)
        self.assertEqual(k.execute("PRAGMA journal_mode").fetchone()[0], "delete")
        self.assertEqual(k.execute("SELECT kurz FROM nachricht WHERE id = ?", (stand,)).fetchone()[0], "hallo")
        k.close()
        bruecke.lese_kopie()                                  # zweites Mal ersetzt die Kopie

    def test_befehl_als_tl_beide_formen(self):
        self.einwerfen("001.json", {"befehl": "posten", "an": "CC1", "art": "auftrag", "kurz": "über die Brücke"})
        self.einwerfen("002.json", {"args": ["wortlaut", "--text", "sync", "--kanal", "chat-tl", "--zeit", "2026-11-01T13:10:00Z"]})
        self.assertEqual(bruecke.befehle(self.eingang), 2)
        n = self.con.execute("SELECT von, art FROM nachricht WHERE kurz = 'über die Brücke'").fetchone()
        self.assertEqual(tuple(n), ("TL", "auftrag"))
        self.assertEqual(self.ergebnis("001")["rc"], 0)
        self.assertEqual(self.con.execute("SELECT text FROM wortlaut").fetchone()[0], "sync")
        self.assertTrue(os.path.exists(os.path.join(self.eingang, "erledigt", "001.json")))
        self.assertFalse(os.listdir(os.path.join(self.eingang, "befehle")))

    def test_unerlaubtes_und_fremder_absender_abgewiesen(self):
        self.einwerfen("a.json", {"befehl": "dienst", "aktion": "entfernen", "ja": True})
        self.einwerfen("b.json", {"befehl": "posten", "an": "CC1", "art": "info", "kurz": "x", "von": "Entwickler"})
        self.einwerfen("c.json", {"befehl": "posten", "an": "CC1", "art": "gibtsnicht", "kurz": "x"})
        bruecke.befehle(self.eingang)
        self.assertIn("nicht erlaubt", self.ergebnis("a")["fehler"])
        self.assertIn("--von", self.ergebnis("b")["fehler"])
        self.assertNotEqual(self.ergebnis("c")["rc"], 0)
        self.assertEqual(self.con.execute("SELECT count(*) FROM nachricht").fetchone()[0], 0)

    def test_halb_geschriebene_datei_wartet(self):
        ordner = os.path.join(self.eingang, "befehle")
        os.makedirs(ordner)
        with open(os.path.join(ordner, "neu.json"), "w", encoding="utf-8") as f:
            f.write('{"befehl": "posten"')                     # gerade erst geschrieben (mtime jetzt)
        self.assertEqual(bruecke.befehle(self.eingang), 0)

    def test_puls_zeigt_tl_als_laufend_und_wird_nie_geweckt(self):
        from amw import dienst, workbench
        self.einwerfen("p.json", {"befehl": "puls", "taetigkeit": "Takt 15:00"})
        bruecke.befehle(self.eingang)
        start = workbench.daten_start(self.con, self.pid)
        tl = next(a for a in start["agenten"] if a["kennung"] == "TL")
        self.assertEqual(tl["zustand"], "aktiv")
        kern.posten(self.con, self.pid, "CC1", "TL", "auftrag", "x")
        self.assertEqual(dienst.Dienst(self.con).zustellen(), 0)          # kein Postfach → kein Weckversuch
        dienst.Dienst(self.con).aufsicht()                                # frischer Puls → bleibt aktiv
        self.assertEqual(self.con.execute("SELECT zustand FROM sitzung").fetchone()[0], "aktiv")

    def test_antwort_an_den_entwickler_sichtbar_und_gelesen(self):
        from amw import aktionen, workbench
        self.einwerfen("e.json", {"befehl": "posten", "an": "Entwickler", "art": "antwort", "kurz": "PONG"})
        bruecke.befehle(self.eingang)
        self.assertEqual(self.ergebnis("e")["rc"], 0)
        an_dich = workbench.daten_start(self.con, self.pid)["an_dich"]
        self.assertEqual([(n["von"], n["kurz"]) for n in an_dich], [("TL", "PONG")])
        aktionen.ausfuehren(self.con, self.pid, "/api/gelesen", {"ids": [an_dich[0]["id"]]})
        self.assertEqual(workbench.daten_start(self.con, self.pid)["an_dich"], [])
        with self.assertRaises(aktionen.Ungueltig):
            aktionen.ausfuehren(self.con, self.pid, "/api/gelesen", {"ids": "1"})

    def test_taetigkeit_und_kachel(self):
        from amw import workbench
        self.einwerfen("t.json", {"befehl": "taetigkeit", "text": "Takt 16:00 – Sync"})
        bruecke.befehle(self.eingang)
        self.assertEqual(self.ergebnis("t")["rc"], 0)
        tl = next(a for a in workbench.daten_start(self.con, self.pid)["agenten"] if a["kennung"] == "TL")
        self.assertEqual((tl["gerade"], tl["gerade_quelle"]), ("Takt 16:00 – Sync", "angabe"))
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Chips umbrechen", agent="CC1")
        kern.posten(self.con, self.pid, "CC1", "TL", "meldung", f"A{aid} Teil 1 fertig", aufgabe_id=aid)
        cc1 = workbench.daten_agent(self.con, self.pid, "CC1")
        self.assertEqual((cc1["gerade_aufgabe"], cc1["gerade_quelle"]), (aid, "meldung"))
        self.assertEqual(cc1["meldungen"][0]["kurz"], f"A{aid} Teil 1 fertig")
        with self.assertRaises(kern.AmwFehler):                       # ohne Sitzung keine Tätigkeit
            kern.taetigkeit(self.con, self.pid, "CC1", "x")


if __name__ == "__main__":
    unittest.main()
