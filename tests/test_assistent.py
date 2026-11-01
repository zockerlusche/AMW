"""Tests für die geführte Einrichtung (amw einrichten) und die Sicherung (amw sichern)."""
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import assistent, db


class Einrichten(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.projekt = os.path.join(self.ordner.name, "projekt")
        os.makedirs(self.projekt)
        p = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db"),
                                         "LOCALAPPDATA": os.path.join(self.ordner.name, "lokal")})
        p.start()
        self.addCleanup(p.stop)
        self.skript = os.path.join(self.ordner.name, "start.ps1")

    def tearDown(self):
        self.ordner.cleanup()

    def test_schnell_legt_alles_an_und_ist_wiederholbar(self):
        erste = assistent.schnell("Demo", "TL", ["CC1", "CC2"], self.projekt, "auto", "high", startskript=self.skript, ausgabe=lambda x: None)
        self.assertTrue(any("Datenbank angelegt" in s for s in erste))
        con = db.verbinde()
        agenten = {r["kennung"]: r for r in con.execute("SELECT kennung, rolle, ordner, rechte, denkstufe FROM agent")}
        con.close()
        self.assertEqual(agenten["TL"]["rolle"], "lead")
        self.assertEqual((agenten["CC1"]["ordner"], agenten["CC1"]["rechte"], agenten["CC1"]["denkstufe"]), (self.projekt, "auto", "high"))
        with open(os.path.join(self.projekt, ".claude", "settings.local.json"), encoding="utf-8") as f:
            self.assertIn("amw-hook.py", json.dumps(json.load(f)))
        with open(self.skript, encoding="utf-8-sig") as f:
            self.assertIn("new-tab --title CC1", f.read())
        zweite = assistent.schnell("Demo", "TL", ["CC1", "CC2"], self.projekt, "auto", "high", startskript=self.skript, ausgabe=lambda x: None)
        self.assertFalse(any("angelegt" in s and "Agent" in s for s in zweite))           # nichts doppelt
        self.assertIn("war schon eingerichtet", " ".join(zweite))

    def test_interaktiv_mit_vorgaben(self):
        antworten = iter(["Mein Spiel", "", "CC1", self.projekt, "vorgabe", "", "n", "n"])
        text = []
        with mock.patch.object(assistent, "STARTSKRIPT", self.skript):
            assistent.interaktiv(eingabe=lambda _: next(antworten), ausgabe=text.append)
        con = db.verbinde()
        self.assertEqual(con.execute("SELECT name FROM projekt").fetchone()[0], "Mein Spiel")
        self.assertEqual([r[0] for r in con.execute("SELECT kennung FROM agent ORDER BY id")], ["TL", "CC1"])
        con.close()
        self.assertFalse(os.path.exists(os.path.join(self.projekt, ".claude")))           # Hooks abgelehnt
        self.assertIn("Workbench öffnen", "\n".join(text))

    def test_sichern(self):
        assistent.schnell("Demo", None, [], ausgabe=lambda x: None)
        ziel = db.sichern()
        self.assertTrue(os.path.exists(ziel))
        with self.assertRaises(FileExistsError):
            db.sichern(ziel)
        self.assertTrue(db.sichern(self.ordner.name).startswith(os.path.join(self.ordner.name, "amw-sicherung-")))


class Doku(unittest.TestCase):
    def test_befehlsreferenz_aktuell(self):
        from amw import cli
        wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(wurzel, "doc", "befehle.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), cli.befehle_markdown(), "doc/befehle.md veraltet – `amw befehle > doc/befehle.md`")

    def test_verweise_in_der_doku_gibt_es(self):
        import re
        wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dateien = [os.path.join(wurzel, "README.md")] + [os.path.join(wurzel, "doc", n) for n in os.listdir(os.path.join(wurzel, "doc"))
                                                        if n.endswith(".md")]
        for d in dateien:
            with open(d, encoding="utf-8") as f:
                for ziel in re.findall(r"\]\(([^)#:]+\.md)", f.read()):
                    self.assertTrue(os.path.exists(os.path.join(os.path.dirname(d), ziel)), f"{os.path.basename(d)} → {ziel}")


if __name__ == "__main__":
    unittest.main()
