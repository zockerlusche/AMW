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
        # Projekt, Lead, Agenten, Regelwerk (Vorgabe: Grund-Regelwerk), Ordner, Rechte (erst ungültig), Denkstufe, Remote Control, Hooks, Wächter
        antworten = iter(["Mein Spiel", "", "CC1", "", self.projekt, "xyz", "vorgabe", "", "", "n", "n"])
        text = []
        with mock.patch.object(assistent, "STARTSKRIPT", self.skript):
            assistent.interaktiv(eingabe=lambda _: next(antworten), ausgabe=text.append)
        con = db.verbinde()
        self.assertEqual(con.execute("SELECT name FROM projekt").fetchone()[0], "Mein Spiel")
        self.assertEqual([r[0] for r in con.execute("SELECT kennung FROM agent ORDER BY id")], ["TL", "CC1"])
        self.assertEqual(con.execute("SELECT count(*) FROM regel WHERE vorlage IS NOT NULL").fetchone()[0], 18)   # Grund-Regelwerk übernommen
        self.assertEqual(con.execute("SELECT version FROM release WHERE art = 'version'").fetchone()[0], "0.1.0")
        con.close()
        self.assertIn("Grund-Regelwerk 1: 18 bewährte Regeln", "\n".join(text))
        self.assertFalse(os.path.exists(os.path.join(self.projekt, ".claude")))           # Hooks abgelehnt
        self.assertIn("Workbench öffnen", "\n".join(text))
        self.assertIn("bitte eins von", "\n".join(text))
        self.assertIn("amw dienst vordergrund", "\n".join(text))

    def test_wiederholen_laesst_eigene_profile_stehen_und_lead_bekommt_eins(self):
        from amw import steuerung
        assistent.schnell("Demo", "TL", ["CC1"], self.projekt, startskript=self.skript, ausgabe=lambda x: None)
        con = db.verbinde()
        pid = con.execute("SELECT id FROM projekt").fetchone()[0]
        tl = steuerung.profil(con, pid, "TL")
        self.assertEqual(tl["ordner"], self.projekt)
        self.assertIn("Team-Lead", tl["startsatz"])
        self.assertFalse(tl["fernsteuerung"])                                          # Remote Control nur auf Wunsch
        steuerung.profil_setzen(con, pid, "Entwickler", "CC1", startsatz="MEIN SATZ", rechte="auto")
        con.close()
        assistent.schnell("Demo", "TL", ["CC1"], self.projekt, rechte="vorgabe", startskript=self.skript, ausgabe=lambda x: None)
        con = db.verbinde()
        p = steuerung.profil(con, pid, "CC1")
        con.close()
        self.assertEqual((p["startsatz"], p["rechte"]), ("MEIN SATZ", "auto"))
        with open(self.skript, encoding="utf-8-sig") as f:
            self.assertIn("new-tab --title TL", f.read())

    def test_ungueltiges_wird_vor_dem_anlegen_abgewiesen(self):
        from amw import kern
        with self.assertRaises(kern.AmwFehler):
            assistent.schnell("Demo", "TL", ["CC1"], self.projekt, rechte="xyz", ausgabe=lambda x: None)
        self.assertFalse(os.path.exists(os.environ["AMW_DB"]))

    def test_agenten_ordner_entfernen_und_git_ausnahme(self):
        from amw import einrichtung
        os.makedirs(os.path.join(self.projekt, ".git", "info"))
        datei = os.path.join(self.projekt, ".claude", "settings.local.json")
        os.makedirs(os.path.dirname(datei))
        with open(datei, "w", encoding="utf-8") as f:
            json.dump({"permissions": {"deny": ["Bash(rm *)"]}, "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "eigen"}]}]}}, f)
        aenderungen = einrichtung.agenten_ordner_einrichten(self.projekt)
        self.assertTrue(any("exclude" in x for x in aenderungen))
        with open(os.path.join(self.projekt, ".git", "info", "exclude"), encoding="utf-8") as f:
            self.assertIn(".claude/settings.local.json.vor-amw-*", f.read().split("\n"))   # Sicherung auch
        ausnahme = os.path.join(self.projekt, ".git", "info", "exclude")
        with open(ausnahme, "w", encoding="utf-8") as f:                                # Stand vor 1.0.1
            f.write(".claude/settings.local.json\n")
        self.assertEqual(einrichtung.agenten_ordner_einrichten(self.projekt),
                         ["im Git des Projekts lokal ausgenommen (.git/info/exclude)"])
        with open(ausnahme, encoding="utf-8") as f:
            self.assertIn(".claude/settings.local.json.vor-amw-*", f.read().split("\n"))
        self.assertEqual(einrichtung.agenten_ordner_einrichten(self.projekt), [])
        weg = einrichtung.agenten_ordner_entfernen(self.projekt)
        self.assertTrue(weg)
        with open(datei, encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(d["permissions"]["deny"], ["Bash(rm *)"])                     # Eigenes bleibt
        self.assertEqual(d["hooks"], {"Stop": [{"hooks": [{"type": "command", "command": "eigen"}]}]})
        self.assertNotIn("statusLine", d)
        self.assertEqual(einrichtung.agenten_ordner_entfernen(self.projekt), [])

    def test_fremde_waechter_aufgabe_wird_nicht_angefasst(self):
        from amw import cli, einrichtung
        with mock.patch.object(einrichtung, "aufgabe_ordner", return_value="X:\\andere-amw"), \
                mock.patch.object(einrichtung, "powershell", side_effect=AssertionError("darf nicht laufen")):
            self.assertIn("anderen AMW-Installation", einrichtung.fremde_aufgabe())
            self.assertEqual(cli.main(["dienst", "neustart"]), 1)
            self.assertEqual(cli.main(["dienst", "entfernen", "--ja"]), 1)
        with mock.patch.object(einrichtung, "aufgabe_ordner", return_value=einrichtung.WURZEL):
            self.assertIsNone(einrichtung.fremde_aufgabe())

    def test_sichern(self):
        assistent.schnell("Demo", None, [], ausgabe=lambda x: None)
        ziel = db.sichern()
        self.assertTrue(os.path.exists(ziel))
        with self.assertRaises(FileExistsError):
            db.sichern(ziel)
        self.assertTrue(db.sichern(self.ordner.name).startswith(os.path.join(self.ordner.name, "amw-sicherung-")))
        neu = os.path.join(self.ordner.name, "neu", "Sicherung")                         # ohne .db = Ordner, wird angelegt
        self.assertTrue(db.sichern(neu).startswith(os.path.join(neu, "amw-sicherung-")))


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
