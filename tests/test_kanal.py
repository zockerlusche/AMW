"""Entwickler-Kanal – entfernt (A1758, Marcel 15.11. 09:31; vorher 1.30.0): Leads anderer Projekte sprechen nicht mit dem
Entwickler der AMW, sondern über die Lead-Runde mit dem AMW-Lead. Wer ihn trotzdem anschreibt, bekommt den Weg genannt."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import cli, db, dienst, einstellungen, kern, planung


class Kanal(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.pfad = os.path.join(self.ordner.name, "t.db")
        self.con = db.anlegen(self.pfad)
        umgebung = mock.patch.dict(os.environ, {"LOCALAPPDATA": self.ordner.name, "AMW_DB": self.pfad})
        umgebung.start()
        self.addCleanup(umgebung.stop)
        for k in ("AMW_PROJEKT", "AMW_AGENT"):
            os.environ.pop(k, None)
        with db.schreiben(self.con):
            self.amw = db.einfuegen(self.con, "projekt", name="AMW", angelegt_utc=db.jetzt())
            self.gw = db.einfuegen(self.con, "projekt", name="GlassWorld", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.amw, "CCamw", rolle="lead")
        kern.agent_neu(self.con, self.gw, "TL", rolle="lead")
        kern.agent_neu(self.con, self.gw, "GW1")

    def tearDown(self):
        self.con.close()
        self.ordner.cleanup()

    def an(self):
        einstellungen.speichern({"produkt_entwickler": "CCamw"})

    def cli(self, *args):
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus):
            rc = cli.main(list(args))
        return rc, aus.getvalue()

    def test_ohne_einstellung_bleiben_projekte_getrennt(self):
        with self.assertRaises(kern.AmwFehler):
            kern.posten(self.con, self.gw, "TL", "CCamw", "frage", "Fehler in der AMW?")
        with self.assertRaises(kern.AmwFehler):
            kern.posten(self.con, self.gw, "CCamw", "TL", "info", "hallo")
        with self.assertRaises(LookupError):
            db.projekt_fuer(self.con, "GlassWorld", "CCamw")

    def test_fremder_lead_bekommt_den_weg_ueber_die_lead_runde(self):
        self.an()                                                  # Einstellung gesetzt – der Kanal bleibt trotzdem zu
        with self.assertRaises(kern.AmwFehler) as e:
            kern.posten(self.con, self.gw, "TL", "CCamw", "frage", "Spec-Karte zeigt den Verfasser")
        self.assertIn("Den Entwickler-Kanal gibt es nicht mehr", str(e.exception))
        self.assertIn("amw runde schreiben --an AMW --kurz", str(e.exception))
        with self.assertRaises(kern.AmwFehler):                    # und er schreibt nicht in fremde Projekte
            kern.posten(self.con, self.gw, "CCamw", "TL", "info", "hallo")
        with self.assertRaises(LookupError):
            db.projekt_fuer(self.con, "GlassWorld", "CCamw")
        _, namen = kern.posten(self.con, self.amw, "Entwickler", "CCamw", "auftrag", "Logo einbauen")   # im eigenen Projekt wie immer
        self.assertEqual(namen, ["CCamw"])

    def test_liest_und_wird_geweckt_nur_im_eigenen_projekt(self):
        self.an()
        kern.posten(self.con, self.amw, "Entwickler", "CCamw", "auftrag", "Logo einbauen")
        rc, aus = self.cli("lesen", "--von", "CCamw")
        self.assertEqual(rc, 0)
        self.assertNotIn("alle Projekte", aus)
        aid = self.con.execute("SELECT id FROM agent WHERE kennung = 'CCamw'").fetchone()[0]
        with db.schreiben(self.con):
            db.einfuegen(self.con, "sitzung", agent_id=aid, claude_sitzung="s-1", gestartet_utc=db.jetzt(), zustand="aktiv",
                         schluessel_datei=os.path.join(self.ordner.name, "CCamw.json"))
        self.assertIsNone(dienst.aktive_sitzung(self.con, self.gw, "CCamw"))           # aus GlassWorld weckt nichts mehr
        self.assertIsNotNone(dienst.aktive_sitzung(self.con, self.amw, "CCamw"))

    def test_leads_kennen_den_weg(self):
        self.an()
        zeilen = planung.kontext_zeilen(self.con, self.gw, "TL")
        self.assertFalse(any("Entwickler-Kanal" in z for z in zeilen))
        self.assertTrue(any("über die Lead-Runde an den AMW-Lead" in z and "--an AMW" in z for z in zeilen))
        self.assertFalse(any("Lead-Runde an den AMW-Lead" in z for z in planung.kontext_zeilen(self.con, self.gw, "GW1")))
        self.assertFalse(any("Lead-Runde an den AMW-Lead" in z for z in planung.kontext_zeilen(self.con, self.amw, "CCamw")))


if __name__ == "__main__":
    unittest.main()
