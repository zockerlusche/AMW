"""Grund-Regelwerk G-3: Bestandsprojekte – Abgleich (nur lesend), Bericht an den Lead, einzeln übernehmen ohne zu überschreiben."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest

from amw import aktionen, cli, db, kern, regelwerk, workbench


class Abgleich(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Alt", angelegt_utc=db.jetzt())
            for nr, text in ((1, "Vor jeder Änderung an Daten oder am Schema eine Sicherung anlegen und das Schema auf einer Kopie proben."),
                             (2, "Kaffee nur in der Küche.")):
                db.einfuegen(self.con, "regel", ebene="arbeit", projekt_id=self.pid, nr=nr, text=text, stand_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")

    def amw(self, *args):
        aus = io.StringIO()
        alt = os.environ.get("AMW_DB")
        os.environ["AMW_DB"] = self.pfad
        try:
            with contextlib.redirect_stdout(aus):
                cli.main(list(args))
        finally:
            os.environ.pop("AMW_DB") if alt is None else os.environ.__setitem__("AMW_DB", alt)
        return aus.getvalue()

    def status(self):
        return {x["nr"]: x for x in regelwerk.abgleich(self.con, self.pid)["regeln"]}

    def test_abgleich_findet_aehnliches_und_aendert_nichts(self):
        vorher = self.con.execute("SELECT nr, text FROM regel ORDER BY nr").fetchall()
        st = self.status()
        self.assertEqual((st["G17"]["status"], st["G17"]["ref"]), ("aehnlich", "KR1"))           # Sicherung vor Schema
        self.assertEqual(st["G13"]["status"], "fehlt")
        self.assertEqual(len(st), len(regelwerk.vorlage()["regeln"]))
        self.assertEqual([tuple(r) for r in vorher], [tuple(r) for r in self.con.execute("SELECT nr, text FROM regel ORDER BY nr")])

    def test_uebernehmen_naechste_nummer_beschluss_nie_doppelt(self):
        r = regelwerk.nachziehen(self.con, self.pid, "TL", "g13")
        self.assertEqual(r["regel"], 3)
        z = self.con.execute("SELECT text, vorlage, beleg FROM regel WHERE nr = 3").fetchone()
        self.assertTrue(z["vorlage"].startswith("G13/"))
        self.assertEqual(z["beleg"], f"B{r['beschluss']}")
        self.assertEqual(self.status()["G13"]["status"], "drin")
        with self.assertRaises(kern.AmwFehler):
            regelwerk.nachziehen(self.con, self.pid, "TL", "G13")                                 # schon da
        with self.assertRaises(kern.AmwFehler):
            regelwerk.nachziehen(self.con, self.pid, "CC1", "G14")                                # nur Lead/Mensch
        with self.assertRaises(kern.AmwFehler):
            regelwerk.nachziehen(self.con, self.pid, "TL", "G99")
        r = aktionen.ausfuehren(self.con, self.pid, "/api/regelwerk/uebernehmen", {"nr": "W1"})     # Workbench (Mensch)
        self.assertEqual(r["regel"], 4)
        self.assertEqual(self.con.execute("SELECT text FROM regel WHERE nr = 1").fetchone()[0][:8], "Vor jede")   # unverändert

    def test_ueber_den_dateiaustausch(self):
        """Ein Chat-Lead arbeitet nur über den Dateiaustausch: abgleich und uebernehmen müssen dort gehen (A1615 b) –
        uebernehmen nur als Lead; ein anderer Absender wird von regelwerk selbst abgewiesen."""
        from amw import bruecke
        fehlend = next(nr for nr, x in self.status().items() if x["status"] == "fehlt")
        alt = os.environ.get("AMW_DB")
        os.environ["AMW_DB"] = self.pfad
        try:
            with tempfile.TemporaryDirectory() as eingang:
                rc, aus, fehler = bruecke.ausfuehren(bruecke.argumente({"befehl": "regelwerk", "aktion": "abgleich"}, eingang, von="TL", projekt="Alt"))
                self.assertEqual((rc, fehler), (0, ""), aus)
                self.assertIn(fehlend, aus)
                rc, aus, fehler = bruecke.ausfuehren(bruecke.argumente({"befehl": "regelwerk", "aktion": "uebernehmen", "id": fehlend},
                                                                       eingang, von="CC1", projekt="Alt"))
                self.assertNotEqual(rc, 0)                                       # kein Lead: abgewiesen
                self.assertEqual(self.status()[fehlend]["status"], "fehlt")
                rc, aus, fehler = bruecke.ausfuehren(bruecke.argumente({"befehl": "regelwerk", "aktion": "uebernehmen", "id": fehlend},
                                                                       eingang, von="TL", projekt="Alt"))
                self.assertEqual((rc, fehler), (0, ""), aus)
        finally:
            os.environ.pop("AMW_DB") if alt is None else os.environ.__setitem__("AMW_DB", alt)
        self.assertEqual(self.status()[fehlend]["status"], "drin")

    def test_bericht_als_dokument_an_den_lead(self):
        aus = self.amw("regelwerk", "abgleich", "--ablegen", "--von", "Entwickler", "--projekt", "Alt")
        self.assertRegex(aus, r"D\d+ abgelegt, #\d+ an TL")
        n = self.con.execute("SELECT bezug, kurz FROM nachricht ORDER BY id DESC LIMIT 1").fetchone()
        self.assertTrue(n["bezug"].startswith("D"))
        self.assertIn("fehlen", n["kurz"])
        self.assertIn("G17", self.amw("regelwerk", "abgleich", "--von", "TL", "--projekt", "Alt"))
        self.assertIn("übernommen als KR3", self.amw("regelwerk", "uebernehmen", "G1", "--von", "TL", "--projekt", "Alt"))

    def test_wissen_liefert_den_abgleich(self):
        d = workbench.daten_wissen(self.con, self.pid, {})
        self.assertEqual(d["grundregeln"]["zahl"]["aehnlich"] + d["grundregeln"]["zahl"]["fehlt"], len(regelwerk.vorlage()["regeln"]))


if __name__ == "__main__":
    unittest.main()
