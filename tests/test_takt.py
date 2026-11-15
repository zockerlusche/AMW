"""`amw takt` (A1780): ein Durchgang für Chat-Leads in einem Aufruf – statt SQL auf der Lese-Kopie."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import tempfile
import time
import unittest
from unittest import mock

from amw import betrieb, bruecke, cli, db, kern, takt


class Takt(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")

    def cli(self, *args):
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(list(args))
        return rc, aus.getvalue()

    def test_alles_in_einem_durchgang(self):
        lang = "Langer Text " * 60
        nid, _ = kern.posten(self.con, self.pid, "CC1", "TL", "info", "Stand A12", lang)
        auftrag, _ = kern.posten(self.con, self.pid, "CC1", "TL", "frage", "Wie weiter?")
        prid = betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "a12", "abc1234def", "Punkt 1: neue Liste", None, ohne_bild="kein Bild")
        rc, aus = self.cli("takt", "--projekt", "Spiel", "--von", "TL")
        self.assertEqual(rc or 0, 0, aus)
        for teil in ("## Postfach (3)", f"#{nid}", f"ganz: amw lesen {nid}", "## Prüfbitten an dich (1)", f"P{prid}", "Punkt 1: neue Liste",
                     "## Fragen an dich", "## Antworten des Menschen", "## Läufe", "## Auslieferungen"):
            self.assertIn(teil, aus)
        self.assertLess(max(len(z) for z in aus.splitlines()), 330)                       # knapp: Texte gekürzt
        st = dict(self.con.execute("SELECT nachricht_id, status FROM empfang WHERE agent = 'TL'").fetchall())
        self.assertEqual((st[nid], st[auftrag]), ("gelesen", "gelesen"))                  # wie amw lesen
        rc, aus = self.cli("takt", "--projekt", "Spiel", "--von", "TL", "--abhaken")
        self.assertIn("1 Info/Meldung erledigt", aus)
        st = dict(self.con.execute("SELECT nachricht_id, status FROM empfang WHERE agent = 'TL'").fetchall())
        self.assertEqual((st[nid], st[auftrag]), ("erledigt", "gelesen"))                 # Fragen bleiben offen
        self.assertTrue(takt.letzter("Spiel", "TL"))                                       # Stand gemerkt (kein Schema)

    def test_antworten_des_menschen_seit_dem_letzten_takt(self):
        fid = kern.frage_neu(self.con, self.pid, "TL", "entwickler", "Farbe?", [("A", "Blau"), ("B", "Rot")], empfehlung="A", grund="weil",
                             geprueft="nichts", pruefen=False)
        kern.frage_antworten(self.con, self.pid, fid, "option", "A", "seite", kern.ENTWICKLER)
        _, aus = self.cli("takt", "--projekt", "Spiel", "--von", "TL")
        self.assertIn(f"F{fid}", aus)
        self.assertIn("→ A) Blau", aus)
        time.sleep(1.1)                                                                 # Sekunden-Auflösung
        _, aus = self.cli("takt", "--projekt", "Spiel", "--von", "TL")
        self.assertNotIn(f"F{fid} ", aus.split("## Antworten des Menschen")[1].split("##")[0])   # beim nächsten Takt nicht mehr neu
        _, aus = self.cli("frage", "zeige", str(fid), "--projekt", "Spiel", "--von", "TL")
        self.assertIn("A) Blau  ← Empfehlung", aus)

    def test_pruefung_zeige_ganz(self):
        prid = betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "a12", "abc1234def", "x" * 900, None, ohne_bild="kein Bild")
        _, aus = self.cli("pruefung", "zeige", str(prid), "--projekt", "Spiel", "--von", "TL")
        self.assertIn("x" * 900, aus)

    def test_ueber_den_dateiaustausch_erlaubt_und_schnell(self):
        self.assertIn("takt", bruecke.ERLAUBT)
        self.assertLessEqual(bruecke.BEFEHLE_S, 1)
        eingang = os.path.join(self.ordner.name, "eingang-tl")
        os.makedirs(os.path.join(eingang, "befehle"))
        with open(os.path.join(eingang, "befehle", "t1.json"), "w", encoding="utf-8") as f:
            json.dump({"befehl": "takt", "projekt": "Spiel"}, f)
        time.sleep(bruecke.RUHE_S + 0.05)
        self.assertEqual(bruecke.befehle(eingang), 1)
        with open(os.path.join(eingang, "erledigt", "t1.ergebnis.json"), encoding="utf-8") as f:
            e = json.load(f)
        self.assertEqual(e["rc"], 0, e)
        self.assertIn("TAKT Spiel/", e["ausgabe"])



class LeseKopieAus(unittest.TestCase):
    def test_alte_kopie_wird_beiseitegelegt_nicht_geloescht(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            kopie = os.path.join(d, "tl_lesen.db")
            with open(kopie, "w") as f:
                f.write("alt")
            self.assertTrue(bruecke.stilllegen(kopie))
            self.assertFalse(os.path.exists(kopie))                                   # SQL-Leser merken es sofort
            self.assertTrue(os.path.exists(os.path.join(d, "tl_lesen.abgeschaltet.db")))
            with open(os.path.join(d, "tl_lesen.stand"), encoding="utf-8") as f:
                self.assertIn("amw takt", f.read())
            self.assertFalse(bruecke.stilllegen(kopie))                               # einmal reicht


if __name__ == "__main__":
    unittest.main()
