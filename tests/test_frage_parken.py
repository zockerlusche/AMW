"""Tests für „Frage parken“ (Schema 10): raus aus der offenen Liste und aus allen Zählern, nicht verloren, wieder
aufnehmbar; mit Zeit und Person, im Verlauf, über CLI, Seite und Netz; Umstellung der alten „GEPARKT …“-Fragen."""
import contextlib
import io
import os
import tempfile
import unittest

from amw import aktionen, cli, db, kern, push, verlauf, workbench


class Parken(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.pfad = os.path.join(self.ordner.name, "t.db")
        self.con = db.anlegen(self.pfad)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1", rolle="bauer")
        kern.agent_neu(self.con, self.pid, "CC2", rolle="pruefer")
        self.f1 = kern.frage_neu(self.con, self.pid, "CC1", "entwickler", "Erste?", [("A", "ja"), ("B", "nein")], "A", "g", geprueft="keine Treffer")
        self.f2 = kern.frage_neu(self.con, self.pid, "CC1", "entwickler", "Zweite?", [("A", "ja")], "A", "g", geprueft="keine Treffer")

    def tearDown(self):
        self.con.close()
        os.environ.pop("AMW_DB", None)
        self.ordner.cleanup()

    def offen(self):
        return [f["id"] for f in workbench.daten_fragen(self.con, self.pid)]

    def test_parken_nimmt_aus_allen_listen_und_zaehlern(self):
        seit = "2000-01-01T00:00:00Z"
        self.assertEqual(kern.frage_parken(self.con, self.pid, "TL", self.f1, grund="Marcel: verfolgen wir gerade nicht"), "geparkt")
        self.assertEqual(self.offen(), [self.f2])
        alle = workbench.daten_fragen(self.con, self.pid, True)
        self.assertEqual([(f["id"], f["geparkt_von"]) for f in alle], [(self.f2, None), (self.f1, "TL")])   # geparkte zuletzt
        start = workbench.daten_start(self.con, self.pid)
        self.assertEqual(([f["id"] for f in start["fragen"]], start["zaehler"]["fragen"]), ([self.f2], 1))
        self.assertEqual([e["schluessel"] for e in push.ereignisse(self.con, self.pid, {"seit_utc": seit, "ereignisse": {}}) if e["ereignis"] == "frage"],
                         [f"frage:{self.f2}"])
        self.assertEqual(verlauf.zusammenfassung(self.con, self.pid, seit)["fragen_offen"], 1)
        self.assertEqual([r["id"] for r in kern.offene_fragen(self.con, self.pid)], [self.f2])
        self.assertEqual([r["id"] for r in kern.offene_fragen(self.con, self.pid, geparkt=True)], [self.f1])
        # im Verlauf der Frage vermerkt, der Fragesteller erfährt es (Info, weckt nicht)
        self.assertEqual(alle[1]["verlauf"][-1]["text"], "Geparkt: Marcel: verfolgen wir gerade nicht")
        n = kern.offene(self.con, self.pid, "CC1")[-1]
        self.assertEqual((n["art"], n["kurz"]), ("info", f"F{self.f1} geparkt: Marcel: verfolgen wir gerade nicht"))
        with self.assertRaises(kern.AmwFehler):
            kern.frage_parken(self.con, self.pid, "TL", self.f1)              # schon geparkt
        # wieder aufnehmen: zurück in der Liste, Zeit und Person leer, Verlauf behält beides
        self.assertEqual(kern.frage_parken(self.con, self.pid, "TL", self.f1, parken=False), "offen")
        self.assertEqual(sorted(self.offen()), sorted([self.f1, self.f2]))
        f = self.con.execute("SELECT geparkt_utc, geparkt_von FROM frage WHERE id = ?", (self.f1,)).fetchone()
        self.assertEqual(tuple(f), (None, None))
        self.assertEqual([v["text"] for v in workbench.daten_fragen(self.con, self.pid)[-1]["verlauf"]][-2:],
                         ["Geparkt: Marcel: verfolgen wir gerade nicht", "Wieder aufgenommen"])

    def test_wer_darf_und_antworten_holt_zurueck(self):
        with self.assertRaises(kern.AmwFehler):
            kern.frage_parken(self.con, self.pid, "CC2", self.f1)              # weder Fragesteller noch Lead
        kern.frage_parken(self.con, self.pid, "CC1", self.f1)                 # der Fragesteller selbst: keine Info an sich
        self.assertEqual(kern.offene(self.con, self.pid, "CC1"), [])
        kern.frage_antworten(self.con, self.pid, self.f1, "option", "A", "seite")   # beantworten geht auch geparkt
        f = self.con.execute("SELECT status, geparkt_utc FROM frage WHERE id = ?", (self.f1,)).fetchone()
        self.assertEqual(tuple(f), ("beantwortet", None))
        with self.assertRaises(kern.AmwFehler):
            kern.frage_parken(self.con, self.pid, "TL", self.f1)              # beantwortet: nichts mehr zu parken

    def test_seite_netz_und_kommandozeile(self):
        self.assertEqual(aktionen.ausfuehren(self.con, self.pid, f"/api/frage/{self.f2}/parken", {"grund": " später "}, "netz"),
                         {"status": "geparkt"})
        r = self.con.execute("SELECT geparkt_von FROM frage WHERE id = ?", (self.f2,)).fetchone()
        self.assertEqual(r[0], "Entwickler")
        with self.assertRaises(aktionen.Ungueltig):                          # doppelt aus dem Briefkasten: kein Stau
            aktionen.ausfuehren(self.con, self.pid, f"/api/frage/{self.f2}/parken", {}, "netz")
        self.assertEqual(aktionen.ausfuehren(self.con, self.pid, f"/api/frage/{self.f2}/aufnehmen", {})["status"], "offen")
        self.con.close()
        os.environ["AMW_DB"] = self.pfad
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus):
            self.assertEqual(cli.main(["--von", "TL", "frage", "parken", str(self.f1), "--grund", "nicht jetzt"]), 0)
            self.assertEqual(cli.main(["--von", "TL", "frage", "liste", "--geparkt"]), 0)
            self.assertEqual(cli.main(["--von", "TL", "frage", "verlauf", str(self.f1)]), 0)
            self.assertEqual(cli.main(["--von", "TL", "frage", "aufnehmen", str(self.f1)]), 0)
        self.assertEqual(cli.main(["--von", "TL", "frage", "parken"]), 1)     # ohne Nummer: Fehler, kein Warten
        text = aus.getvalue()
        self.assertIn(f"F{self.f1} → geparkt", text)
        self.assertIn("(geparkt ", text)
        self.assertIn("[nachtrag]: Geparkt: nicht jetzt", text)
        self.assertIn(f"F{self.f1} → offen", text)
        self.con = db.verbinde(self.pfad)

    def test_umstellung_der_alten_geparkt_fragen(self):
        alt = kern.frage_neu(self.con, self.pid, "TL", "entwickler", "GEPARKT (B12): Altes Thema", [("A", "ja")], "A", "g", geprueft="keine Treffer")
        with db.schreiben(self.con):
            self.con.execute("UPDATE frage SET status = 'beantwortet' WHERE id = ?", (self.f2,))
            self.con.execute("UPDATE frage SET kurz = 'GEPARKT erledigt' WHERE id = ?", (self.f2,))
        for sp in ("geparkt_utc", "geparkt_von"):
            self.con.execute(f"ALTER TABLE frage DROP COLUMN {sp}")
        self.con.execute("DROP TABLE schirm")
        self.con.execute("DROP TABLE wartegrund")                         # … und keine Wartegründe (12)
        self.con.execute("ALTER TABLE frage DROP COLUMN geprueft")
        self.con.execute("ALTER TABLE agent DROP COLUMN alias")                             # Schema 9 kannte den Schirm-Schalter (11) nicht
        self.con.execute("ALTER TABLE sitzung DROP COLUMN taetigkeit_utc")         # … und kein Alter der Tätigkeit (13)
        for t in ("bogen", "aufgabe"):                                          # … und keine Federführung (14)
            self.con.execute(f"ALTER TABLE {t} DROP COLUMN federfuehrend")
        self.con.execute("PRAGMA user_version = 9")
        self.con.close()
        self.con = db.verbinde(self.pfad)
        self.assertEqual(self.con.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
        geparkt = self.con.execute("SELECT id, geparkt_von FROM frage WHERE geparkt_utc IS NOT NULL").fetchall()
        self.assertEqual([tuple(r) for r in geparkt], [(alt, "Entwickler")])   # nur offene, beantwortete bleiben
        self.assertEqual(self.offen(), [self.f1])


if __name__ == "__main__":
    unittest.main()
