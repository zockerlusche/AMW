"""Seite „Nachrichten“ (Stufe N1): Eingang und Gesendet mit Stand je Empfänger, „gelesen“ beim Listen von `amw lesen`,
zurückziehen solange niemand gelesen hat."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
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


    def test_nur_das_gewaehlte_projekt(self):
        """Marcel 13.11. (B2691): Unter einem Projekt stehen nur seine Nachrichten – keine aus anderen Projekten, kein
        Filter „Alle Projekte“; das Menü zählt nur das gewählte Projekt. Meldungen der Workbench heißen „System“."""
        with db.schreiben(self.con):
            p2 = db.einfuegen(self.con, "projekt", name="Q", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, p2, "QL", rolle="lead")
        kern.posten(self.con, p2, kern.ENTWICKLER, "QL", "auftrag", "in Q")
        kern.posten(self.con, p2, "QL", kern.ENTWICKLER, "info", "aus Q")
        kern.posten(self.con, p2, "AMW", kern.ENTWICKLER, "meldung", "Systemmeldung in Q")
        kern.posten(self.con, self.pid, "AMW", kern.ENTWICKLER, "meldung", "Systemmeldung in P")
        uid = dict(self.con.execute("SELECT name, uid FROM projekt").fetchall())
        for pid, name in ((self.pid, "P"), (p2, "Q")):
            d = workbench.daten_nachrichten(self.con, pid)
            self.assertEqual({x["projekt"] for x in d["eingang"] + d["gesendet"]}, {uid[name]})
            ids = {x["id"] for x in d["eingang"] + d["gesendet"]}
            fremd = self.con.execute(f"SELECT count(*) FROM nachricht WHERE projekt_id != ? AND id IN ({','.join('?' * len(ids))})",
                                     (pid, *ids)).fetchone()[0]
            self.assertEqual(fremd, 0)
            start = workbench.daten_start(self.con, pid)["zaehler"]
            self.assertEqual(start["nachrichten"], workbench.an_dich_zahl(self.con, pid))          # Menü: nur dieses Projekt
            self.assertEqual(start["nachrichten"], d["zaehler"]["eingang_offen"])
        self.assertNotIn("aus Q", [x["kurz"] for x in workbench.daten_nachrichten(self.con, self.pid)["eingang"]])
        self.assertFalse(hasattr(workbench, "daten_nachrichten_alle"))
        with open(os.path.join(os.path.dirname(__file__), "..", "amw", "workbench.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertNotIn("/api/nachrichten?alle=1", html)
        self.assertNotIn("nr_alle_projekte", html.split("async function sichtNachrichten")[1].split("\nasync function ")[0])
        self.assertIn('const wer = k => k === "AMW" ? t("absender_system") : k;', html)
        self.assertEqual(html.count('absender_system: "System"'), 2)                                # DE und EN
        from amw import abgleich                                                                  # Betrieb online: fremde Läufe ohne Namen
        with db.schreiben(self.con):
            db.einfuegen(self.con, "lauf", projekt_id=p2, agent="QL", beschreibung="geheim", schwer=1, schirm=1, gpu=0, status="laeuft",
                         angemeldet_utc=db.jetzt(), start_utc=db.jetzt())
        self.assertEqual([f["projekt"] for f in workbench.daten_betrieb(self.con, self.pid)["fremd"]], ["Q"])      # am PC mit Namen
        self.assertEqual([f["projekt"] for f in abgleich.ansichten(self.con, self.pid)["/api/betrieb"]["fremd"]], [None])


if __name__ == "__main__":
    unittest.main()
