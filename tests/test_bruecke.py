"""Tests für die Datei-Brücke des TL: Lesekopie ohne WAL, Befehlsdateien als --von TL."""
import json
import os
import sqlite3
import tempfile
import time
import unittest
from unittest import mock

from amw import bruecke, db, kern


class Bruecke(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        p = mock.patch.dict(os.environ, {"LOCALAPPDATA": self.ordner.name})   # Dienst.aufsicht() schickt sonst echte Pushes
        p.start()
        self.addCleanup(p.stop)
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
        self.einwerfen("d.json", {"befehl": "agent", "aktion": "beenden", "kennung": "CC1"})
        bruecke.befehle(self.eingang)
        self.assertIn("nur am PC", self.ergebnis("d")["fehler"])
        self.assertIn("nicht erlaubt", self.ergebnis("a")["fehler"])
        self.assertIn("--von", self.ergebnis("b")["fehler"])
        self.assertNotEqual(self.ergebnis("c")["rc"], 0)
        self.assertEqual(self.con.execute("SELECT count(*) FROM nachricht").fetchone()[0], 0)

    def test_planung_ueber_die_bruecke_freigabe_bleibt_beim_menschen(self):
        from amw import planung
        os.makedirs(os.path.join(self.eingang, "plan"))
        with open(os.path.join(self.eingang, "plan", "anf.md"), "w", encoding="utf-8") as f:
            f.write("R1 Anmelden geht")
        geheim = os.path.join(self.ordner.name, "geheim.json")
        with open(geheim, "w", encoding="utf-8") as f:
            f.write("SCHLUESSEL")
        self.einwerfen("1.json", {"befehl": "leitbild", "aktion": "setzen", "ziel": "Spiel fertig", "prinzip": ["Klar|Ist es klar?"]})
        self.einwerfen("2.json", {"befehl": "bogen", "aktion": "neu", "titel": "Etappe 1", "ziel": "Login", "zieldatum": "2026-12-01"})
        self.einwerfen("3.json", {"befehl": "spec", "aktion": "schreiben", "bogen": 1, "teil": "anforderungen", "datei": "plan/anf.md"})
        self.einwerfen("4.json", {"befehl": "spec", "aktion": "vorlegen", "bogen": 1, "teil": "anforderungen"})
        self.einwerfen("5.json", {"befehl": "spec", "aktion": "frei", "bogen": 1, "teil": "anforderungen"})
        self.einwerfen("6.json", {"befehl": "spec", "aktion": "schreiben", "bogen": 1, "teil": "entwurf", "datei": geheim})
        self.einwerfen("7.json", {"befehl": "spec", "aktion": "schreiben", "bogen": 1, "teil": "entwurf", "datei": "../geheim.json"})
        self.einwerfen("8.json", {"befehl": "aufgabe", "aktion": "neu", "titel": "Login bauen", "bogen": 1, "agent": "CC1",
                                  "pruefer": "TL"})
        bruecke.befehle(self.eingang)
        for n in "1234":
            self.assertEqual(self.ergebnis(n)["rc"], 0, self.ergebnis(n))
        self.assertIn("nur der Entwickler", self.ergebnis("5")["fehler"])
        self.assertIn("nur aus eingang-tl", self.ergebnis("6")["fehler"])
        self.assertIn("nur aus eingang-tl", self.ergebnis("7")["fehler"])
        self.assertEqual(self.ergebnis("8")["rc"], 0, self.ergebnis("8"))
        self.assertEqual(planung.leitbild(self.con, self.pid)["ziel"], "Spiel fertig")
        s = planung.spec(self.con, 1, "anforderungen")
        self.assertEqual((s["text"], s["status"]), ("R1 Anmelden geht", "vorgelegt"))
        self.assertNotIn("SCHLUESSEL", planung.spec(self.con, 1, "entwurf")["text"] or "")
        self.assertEqual(tuple(self.con.execute("SELECT bogen_id, agent, pruefer FROM aufgabe").fetchone()), (1, "CC1", "TL"))

    def test_plan_check_ueber_die_bruecke_akzeptieren(self):
        from amw import planung
        bid = planung.bogen_neu(self.con, self.pid, "TL", "Etappe")
        self.einwerfen("k1.json", {"befehl": "plan", "aktion": "akzeptieren", "schluessel": f"bogen_ohne_zieldatum:B{bid}",
                                   "grund": "Termin offen"})
        self.einwerfen("k2.json", {"befehl": "plan", "aktion": "pruefen"})
        bruecke.befehle(self.eingang)
        self.assertEqual(self.ergebnis("k1")["rc"], 0, self.ergebnis("k1"))
        aus = self.ergebnis("k2")["ausgabe"]
        self.assertIn("Bedeutet:", aus)
        self.assertIn("1 bewusst akzeptiert", aus)
        self.assertNotIn(f"[bogen_ohne_zieldatum:B{bid}]", aus)

    def test_fehlerhafter_befehl_haelt_die_warteschlange_nicht_an(self):
        # 02.11.: „frage neu“ mit --text statt --kurz blieb als Datenbankfehler hängen, alles dahinter stand still
        self.einwerfen("a.json", {"args": ["frage", "neu", "--an", "entwickler", "--text", "Ziel?", "--option", "A=x",
                                           "--empfehlung", "A", "--grund", "g"]})
        self.einwerfen("b.json", {"befehl": "posten", "an": "CC1", "art": "info", "kurz": "danach"})
        self.assertEqual(bruecke.befehle(self.eingang), 2)
        a = self.ergebnis("a")
        self.assertEqual(a["rc"], 1)
        self.assertIn("--kurz", a["fehler"])
        self.assertEqual(self.ergebnis("b")["rc"], 0)
        self.assertEqual(self.con.execute("SELECT count(*) FROM frage").fetchone()[0], 0)
        self.assertEqual(os.listdir(os.path.join(self.eingang, "befehle")), [])

    def test_unerwarteter_fehler_und_eingabe_werden_zum_ergebnis(self):
        from unittest import mock
        self.einwerfen("a.json", {"befehl": "posten", "an": "CC1", "art": "info", "kurz": "x"})
        self.einwerfen("b.json", {"befehl": "posten", "an": "CC1", "art": "info", "kurz": "y"})
        with mock.patch("amw.kern.posten", side_effect=[sqlite3.IntegrityError("NOT NULL"), (1, ["CC1"])]):
            self.assertEqual(bruecke.befehle(self.eingang), 2)
        self.assertEqual(self.ergebnis("a")["rc"], 1)
        self.assertIn("IntegrityError", self.ergebnis("a")["fehler"])
        with mock.patch("amw.cli.cmd_posten", side_effect=lambda a, con: input("?")):     # fragt nach → EOF, kein Warten
            rc, _, fehler = bruecke.ausfuehren(["posten", "--an", "CC1", "--art", "info", "--kurz", "z", "--von", "TL"])
        self.assertEqual(rc, 1)
        self.assertIn("EOFError", fehler)

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
