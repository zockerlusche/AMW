"""Seite „Nachrichten“ (Stufe N1): Eingang und Gesendet mit Stand je Empfänger, „gelesen“ beim Listen von `amw lesen`,
zurückziehen solange niemand gelesen hat."""
import contextlib
import io
import os
import tempfile
import unittest

from amw import aktionen, cli, db, kern, workbench


class Nachrichten(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
            self.aid = db.einfuegen(self.con, "aufgabe", projekt_id=self.pid, titel="Team-Baum", agent="CC1", status="laeuft",
                                    einstufung="aktiv", angelegt_utc=db.jetzt(), angelegt_von="TL")
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        for k in ("CC1", "CC2"):
            kern.agent_neu(self.con, self.pid, k)
        E = kern.ENTWICKLER
        self.n1 = kern.posten(self.con, self.pid, E, "CC1", "auftrag", "Linien aufräumen", aufgabe_id=self.aid)[0]
        self.n2 = kern.posten(self.con, self.pid, E, "CC1,CC2", "info", "Heute keine Läufe mit Fenster")[0]
        self.n3 = kern.posten(self.con, self.pid, "CC1", E, "info", "Stand: fertig", antwort_auf=self.n1)[0]

    def amw(self, *args):
        aus = io.StringIO()
        old = os.environ.get("AMW_DB")
        os.environ["AMW_DB"] = self.pfad
        try:
            with contextlib.redirect_stdout(aus):
                cli.main(list(args))
        finally:
            if old is None:
                os.environ.pop("AMW_DB", None)
            else:
                os.environ["AMW_DB"] = old
        return aus.getvalue()

    def gesendet(self, nid):
        return next(x for x in workbench.daten_nachrichten(self.con, self.pid)["gesendet"] if x["id"] == nid)

    def test_gesendet_mit_stand_bezug_und_antwort(self):
        g = self.gesendet(self.n1)
        self.assertEqual(g["bezug"]["text"], f"A{self.aid} Team-Baum")
        self.assertEqual([(e["agent"], e["stand"]) for e in g["empfaenger"]], [("CC1", "gesendet")])
        self.assertEqual([a["id"] for a in g["antworten"]], [self.n3])
        e = workbench.daten_nachrichten(self.con, self.pid)
        self.assertEqual([x["id"] for x in e["eingang"]], [self.n3])
        self.assertEqual(e["zaehler"]["eingang_offen"], 1)

    def test_amw_lesen_setzt_gelesen(self):
        self.amw("lesen", "--von", "CC1", "--projekt", "P")
        self.assertEqual([e["stand"] for e in self.gesendet(self.n1)["empfaenger"]], ["gelesen"])
        self.assertIn(f"#{self.n1}", self.amw("lesen", "--von", "CC1", "--projekt", "P"))       # bleibt bis erledigt in der Liste
        self.amw("erledigt", str(self.n1), "--von", "CC1", "--projekt", "P")
        self.assertEqual([e["stand"] for e in self.gesendet(self.n1)["empfaenger"]], ["erledigt"])

    def test_zurueckziehen_nur_solange_niemand_gelesen_hat(self):
        self.amw("lesen", "--von", "CC1", "--projekt", "P")                                   # CC1 hat n2 gesehen, CC2 nicht
        with self.assertRaises(kern.AmwFehler) as e:
            kern.zurueckziehen(self.con, self.pid, kern.ENTWICKLER, self.n2)
        self.assertIn("CC1 schon gelesen", str(e.exception))
        n4 = kern.posten(self.con, self.pid, kern.ENTWICKLER, "CC2", "auftrag", "doch nicht")[0]
        self.assertTrue(self.gesendet(n4)["zurueckziehbar"])
        r = aktionen.ausfuehren(self.con, self.pid, "/api/nachricht/zurueckziehen", {"id": n4})
        self.assertEqual(r["zurueckgezogen"], n4)
        g = self.gesendet(n4)
        self.assertTrue(g["zurueckgezogen"])
        self.assertEqual([e["stand"] for e in g["empfaenger"]], ["zurueckgezogen"])
        self.assertNotIn(f"#{n4}", self.amw("lesen", "--von", "CC2", "--projekt", "P"))       # beim Empfänger weg
        with self.assertRaises(kern.AmwFehler):
            kern.zurueckziehen(self.con, self.pid, kern.ENTWICKLER, self.n3)                   # nicht von dir
        with self.assertRaises(kern.AmwFehler):
            kern.zurueckziehen(self.con, self.pid, "TL", n4)


    def test_bezug_gesetzt_geerbt_und_geprueft(self):
        b = lambda nid: self.con.execute("SELECT bezug FROM nachricht WHERE id = ?", (nid,)).fetchone()[0]
        self.assertEqual((b(self.n1), b(self.n3), b(self.n2)), (f"A{self.aid}", f"A{self.aid}", None))   # aus Aufgabe, geerbt, keiner
        n = kern.posten(self.con, self.pid, "CC1", "TL", "info", "zum Agenten", bezug="@CC2")[0]
        self.assertEqual(b(n), "@CC2")
        n = kern.posten(self.con, self.pid, kern.ENTWICKLER, "CC1", "info", "per Kürzel", bezug=f"a{self.aid}")[0]
        self.assertEqual(self.con.execute("SELECT bezug, aufgabe_id FROM nachricht WHERE id = ?", (n,)).fetchone()[:], (f"A{self.aid}", self.aid))
        for falsch in ("X5", "A999", "@Niemand", "A1x"):
            with self.assertRaises(kern.AmwFehler):
                kern.posten(self.con, self.pid, kern.ENTWICKLER, "CC1", "info", "falsch", bezug=falsch)
        r = aktionen.ausfuehren(self.con, self.pid, "/api/nachricht", {"an": "CC1", "art": "info", "kurz": "Antwort", "antwort_auf": self.n3})
        self.assertEqual(b(r["nachricht"]), f"A{self.aid}")                                  # Antwort von der Seite erbt
        g = self.gesendet(self.n1)["bezug"]
        self.assertEqual((g["kuerzel"], g["art"], g["id"], g["text"]), (f"A{self.aid}", "A", self.aid, f"A{self.aid} Team-Baum"))
        self.assertIn("Bezug A", self.amw("lesen", str(self.n1), "--von", "CC1", "--projekt", "P"))

    def test_migration_29_zieht_alte_bezuege_nach(self):
        from importlib import resources
        sql = (resources.files("amw") / "migration_29.sql").read_text(encoding="utf-8")
        c = self.con
        c.execute("DROP INDEX nachricht_bezug")
        c.execute("DROP INDEX nachricht_antwort")
        c.execute("ALTER TABLE nachricht DROP COLUMN bezug")
        c.executescript(sql)
        b = lambda nid: c.execute("SELECT bezug FROM nachricht WHERE id = ?", (nid,)).fetchone()[0]
        self.assertEqual((b(self.n1), b(self.n3), b(self.n2)), (f"A{self.aid}", f"A{self.aid}", None))


    def test_antwort_an_den_menschen_findet_den_faden(self):
        auf = lambda nid: self.con.execute("SELECT antwort_auf, bezug FROM nachricht WHERE id = ?", (nid,)).fetchone()[:]
        h = []
        n = kern.posten(self.con, self.pid, "CC2", "Entwickler", "info", "Läufe verschoben", hinweise=h)[0]
        self.assertEqual(auf(n), (self.n2, None))                                              # letzte an CC2: n2
        self.assertIn(f"Antwort auf #{self.n2}", h[0])
        n = kern.posten(self.con, self.pid, "CC2", "Entwickler", "info", "noch etwas")[0]
        self.assertEqual(auf(n)[0], None)                                                      # n2 ist schon beantwortet
        n4 = kern.posten(self.con, self.pid, kern.ENTWICKLER, "CC2", "auftrag", "Speichern prüfen", aufgabe_id=self.aid)[0]
        n = kern.posten(self.con, self.pid, "CC2", "Entwickler", "info", "geprüft")[0]
        self.assertEqual(auf(n), (n4, f"A{self.aid}"))                                         # erbt auch den Bezug
        n5 = kern.posten(self.con, self.pid, kern.ENTWICKLER, "CC2", "auftrag", "noch eins")[0]
        n = kern.posten(self.con, self.pid, "CC2", "Entwickler,TL", "info", "an zwei")[0]
        self.assertEqual(auf(n)[0], None)                                                      # nicht nur an den Menschen
        out = self.amw("posten", "--von", "CC2", "--projekt", "P", "--an", "Entwickler", "--art", "info", "--kurz", "neu", "--neuer-faden")
        self.assertNotIn("Antwort auf", out)
        self.assertIn(f"Antwort auf #{n5}", self.amw("posten", "--von", "CC2", "--projekt", "P", "--an", "Entwickler", "--art", "info", "--kurz", "zu n5"))


    def test_antwort_auf_frage_traegt_den_bezug_der_frage(self):
        r = kern.frage_neu(self.con, self.pid, "CC1", "entwickler", "Blau oder Grün?", [("A", "Blau"), ("B", "Grün")], "A", "passt",
                           aufgabe_id=self.aid, geprueft="keine Treffer")
        fid = r if isinstance(r, int) else r[0]
        kern.frage_antworten(self.con, self.pid, fid, "option", "A", "workbench")
        g = [x for x in workbench.daten_nachrichten(self.con, self.pid)["gesendet"] if x["kurz"].startswith(f"Antwort zu F{fid}")]
        self.assertEqual(len(g), 1)
        self.assertEqual((g[0]["bezug"]["kuerzel"], [e["agent"] for e in g[0]["empfaenger"]]), (f"F{fid}", ["CC1"]))
        self.assertEqual(self.con.execute("SELECT aufgabe_id FROM nachricht WHERE id = ?", (g[0]["id"],)).fetchone()[0], self.aid)
        self.assertFalse(g[0]["zurueckziehbar"])                                             # Antwort auf eine Frage: nicht zurückziehen
        with self.assertRaises(kern.AmwFehler):
            kern.zurueckziehen(self.con, self.pid, kern.ENTWICKLER, g[0]["id"])


    def test_ueber_alle_projekte(self):
        with db.schreiben(self.con):
            p2 = db.einfuegen(self.con, "projekt", name="Q", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, p2, "QL", rolle="lead")
        n = kern.posten(self.con, p2, kern.ENTWICKLER, "QL", "auftrag", "in Q")[0]
        kern.posten(self.con, p2, "QL", kern.ENTWICKLER, "info", "aus Q")
        d = workbench.daten_nachrichten_alle(self.con)
        uid = dict(self.con.execute("SELECT name, uid FROM projekt").fetchall())
        self.assertEqual(d["gesendet"][0]["id"], n)                                            # neueste zuerst, über Projekte
        self.assertEqual({x["projekt"] for x in d["gesendet"]}, {uid["P"], uid["Q"]})
        self.assertEqual(d["zaehler"]["eingang_offen"], sum(workbench.daten_nachrichten(self.con, x)["zaehler"]["eingang_offen"] for x in (self.pid, p2)))
        self.assertIn("aus Q", [x["kurz"] for x in d["eingang"]])
        start = workbench.daten_start(self.con, self.pid)["zaehler"]                            # Menü zählt dasselbe wie der Eingang
        self.assertEqual(start["nachrichten"], d["zaehler"]["eingang_offen"])
        self.assertEqual(start["an_dich"], workbench.daten_nachrichten(self.con, self.pid)["zaehler"]["eingang_offen"])
        with db.schreiben(self.con):                                                            # ältere Info ohne Bezug zählt nicht mehr
            self.con.execute("UPDATE nachricht SET zeit_utc = '2020-01-01T00:00:00Z' WHERE kurz = 'aus Q'")
        self.assertEqual(workbench.daten_start(self.con, p2)["zaehler"]["an_dich"], 0)
        self.assertEqual(workbench.daten_nachrichten(self.con, p2)["zaehler"]["eingang_offen"], 0)
        self.assertEqual(workbench.daten_nachrichten(self.con, self.pid)["gesendet"][0]["projekt"], uid["P"])


if __name__ == "__main__":
    unittest.main()
