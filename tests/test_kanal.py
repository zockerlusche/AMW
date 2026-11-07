"""Entwickler-Kanal (1.30.0): der AMW-Produktentwickler (PC-Einstellung) schreibt und empfängt in jedem Projekt,
liest alle Projekte auf einmal und wird aus jedem Projekt geweckt."""
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

    def test_lead_erreicht_den_produktentwickler_und_umgekehrt(self):
        self.an()
        nid, namen = kern.posten(self.con, self.gw, "TL", "CCamw", "frage", "Spec-Karte zeigt den Verfasser")
        self.assertEqual(namen, ["CCamw"])
        self.assertEqual(db.projekt_fuer(self.con, "GlassWorld", "CCamw"), self.gw)
        _, namen = kern.posten(self.con, self.gw, "CCamw", "TL", "antwort", "verstanden", antwort_auf=nid)
        self.assertEqual(namen, ["TL"])
        with self.assertRaises(LookupError):                       # andere Agenten bleiben in ihrem Projekt
            db.projekt_fuer(self.con, "AMW", "GW1")

    def test_lesen_und_erledigen_ueber_alle_projekte(self):
        self.an()
        kern.posten(self.con, self.amw, "Entwickler", "CCamw", "auftrag", "Logo einbauen")
        nid, _ = kern.posten(self.con, self.gw, "TL", "CCamw", "frage", "Spec-Karte zeigt den Verfasser")
        rc, aus = self.cli("lesen", "--von", "CCamw")
        self.assertEqual(rc, 0)
        self.assertIn("[AMW]", aus)
        self.assertIn("[GlassWorld]", aus)
        self.assertIn("2 offen (alle Projekte)", aus)
        rc, aus = self.cli("lesen", str(nid), "--von", "CCamw")
        self.assertIn("Projekt GlassWorld", aus)
        rc, aus = self.cli("erledigt", str(nid), "--von", "CCamw")
        self.assertIn("1 erledigt", aus)
        self.assertEqual(self.con.execute("SELECT status FROM empfang WHERE nachricht_id = ?", (nid,)).fetchone()[0], "erledigt")
        rc, aus = self.cli("lesen", "--von", "TL", "--projekt", "GlassWorld")     # der TL liest wie bisher nur sein Projekt
        self.assertEqual(rc, 0)

    def test_wecken_aus_einem_fremden_projekt_mit_projektname(self):
        self.an()
        aid = self.con.execute("SELECT id FROM agent WHERE kennung = 'CCamw'").fetchone()[0]
        schluessel = os.path.join(self.ordner.name, "CCamw.json")
        with db.schreiben(self.con):
            db.einfuegen(self.con, "sitzung", agent_id=aid, claude_sitzung="s-1", gestartet_utc=db.jetzt(), zustand="aktiv",
                         schluessel_datei=schluessel)
        self.assertIsNotNone(dienst.aktive_sitzung(self.con, self.gw, "CCamw"))
        self.assertIsNone(dienst.aktive_sitzung(self.con, self.gw, "GW1"))
        kern.posten(self.con, self.gw, "TL", "CCamw", "frage", "Spec-Karte zeigt den Verfasser")
        gesendet = []
        with mock.patch.object(dienst, "lies_schluessel", return_value=("pipe", "k")), \
                mock.patch.object(dienst.pipe, "senden", side_effect=lambda p, k, text: gesendet.append(text)):
            d = dienst.Dienst(self.con)
            d.seit = "2000-01-01T00:00:00Z"
            self.assertEqual(d.zustellen(), 1)
        self.assertIn("[GlassWorld] TL [frage] Spec-Karte", gesendet[0])

    def test_leads_kennen_den_kanal(self):
        self.an()
        self.assertTrue(any("Entwickler-Kanal" in z and "CCamw" in z for z in planung.kontext_zeilen(self.con, self.gw, "TL")))
        self.assertFalse(any("Entwickler-Kanal" in z for z in planung.kontext_zeilen(self.con, self.gw, "GW1")))
        self.assertFalse(any("Entwickler-Kanal" in z for z in planung.kontext_zeilen(self.con, self.amw, "CCamw")))


if __name__ == "__main__":
    unittest.main()
