"""Rolle und Zuständigkeit per Befehl ändern (1.35.0) – und: ein Chat-Lead bekommt die Brücke seines Projekts erst, wenn der
bisherige Lead (ein Agent mit eigener Sitzung) eine andere Rolle hat; sonst liefen die Befehle unter dessen Namen."""
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from amw import bruecke, cli, db, kern


class Rolle(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.addCleanup(self.ordner.cleanup)
        umgebung = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        umgebung.start()
        self.addCleanup(umgebung.stop)
        for k in ("AMW_PROJEKT", "AMW_AGENT"):
            os.environ.pop(k, None)
        self.con = db.anlegen()
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            db.einfuegen(self.con, "projekt", name="Erstes", angelegt_utc=db.jetzt())
            self.pid = db.einfuegen(self.con, "projekt", name="Werkzeug", angelegt_utc=db.jetzt())
        for k, r in (("Bauer", "lead"), ("Helfer", None)):
            kern.agent_neu(self.con, self.pid, k, rolle=r)

    def cli(self, *args):
        aus, fehler = io.StringIO(), io.StringIO()
        with redirect_stdout(aus), redirect_stderr(fehler):
            rc = cli.main(list(args) + ["--projekt", "Werkzeug"])
        return rc, aus.getvalue() + fehler.getvalue()

    def rolle(self, kennung):
        return self.con.execute("SELECT rolle, grenzen FROM agent WHERE projekt_id = ? AND kennung = ?", (self.pid, kennung)).fetchone()

    def test_lead_aendert_rolle_und_zustaendigkeit(self):
        rc, aus = self.cli("agent", "profil", "Helfer", "--rolle", "Grafik", "--grenzen", "nur Bilder, kein Code", "--von", "Bauer")
        self.assertEqual(rc, 0, aus)
        self.assertEqual(tuple(self.rolle("Helfer")), ("Grafik", "nur Bilder, kein Code"))
        self.assertIn("rolle          Grafik", aus)
        rc, aus = self.cli("agent", "profil", "Helfer", "--rolle", "", "--von", "Bauer")              # leer = keine Rolle
        self.assertEqual((rc, self.rolle("Helfer")["rolle"]), (0, None))
        self.assertEqual(self.rolle("Helfer")["grenzen"], "nur Bilder, kein Code")                   # nicht genannt = bleibt

    def test_agent_ohne_lead_rolle_darf_nicht(self):
        rc, aus = self.cli("agent", "profil", "Bauer", "--rolle", "Hilfe", "--von", "Helfer")
        self.assertEqual(rc, 1)
        self.assertEqual(self.rolle("Bauer")["rolle"], "lead")

    def test_einziger_lead_gibt_die_rolle_nicht_selbst_ab(self):
        rc, aus = self.cli("agent", "profil", "Bauer", "--rolle", "Entwicklung", "--von", "Bauer")
        self.assertEqual(rc, 1)
        self.assertIn("einzige Lead", aus)
        self.assertEqual(self.rolle("Bauer")["rolle"], "lead")
        kern.agent_einstellen(self.con, self.pid, kern.ENTWICKLER, "Bauer", rolle="Entwicklung")     # der Mensch darf
        self.assertEqual(self.rolle("Bauer")["rolle"], "Entwicklung")

    def test_chat_lead_uebernimmt_die_bruecke(self):
        von = lambda: next(b["von"] for b in bruecke.bruecken(self.con) if b["pid"] == self.pid)
        self.assertEqual(von(), "Bauer")
        self.assertEqual(self.cli("agent", "neu", "TL", "--rolle", "lead", "--von", "Bauer")[0], 0)   # Chat-Lead kommt dazu
        self.assertEqual(von(), "Bauer")                                                             # noch der erste Lead
        rc, aus = self.cli("agent", "profil", "Bauer", "--rolle", "Entwicklung", "--von", "Bauer")   # jetzt gibt es einen zweiten Lead
        self.assertEqual(rc, 0, aus)
        self.assertEqual((von(), kern.lead(self.con, self.pid)), ("TL", "TL"))
        # TL schreibt über die Brücke an den früheren Lead – vorher „kein Empfänger“ (Absender = Empfänger)
        args = bruecke.argumente({"befehl": "posten", "an": "Bauer", "art": "auftrag", "kurz": "bitte bauen"}, von="TL", projekt="Werkzeug")
        aus = io.StringIO()
        with redirect_stdout(aus), redirect_stderr(aus):
            self.assertEqual(cli.main(args), 0, aus.getvalue())
        n = self.con.execute("SELECT von FROM nachricht ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(n["von"], "TL")


if __name__ == "__main__":
    unittest.main()
