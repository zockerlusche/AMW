"""A1747 (Marcel 14.11.): Läufe ohne --schirm öffneten Godot-Fenster, während Marcel spielte und der Bildschirm zu war; nach
dem Schließen kamen sie wieder. Jetzt erkennt der Dienst das Fenster, meldet es, behandelt den Lauf als Lauf mit Fenster – und
nimmt denselben Lauf danach nur noch mit --schirm an."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import tempfile
import unittest
from unittest import mock

from amw import belegung, betrieb, db, fenster, kern, schirm

PROZESSE = [{"pid": 100, "eltern": 1, "name": "python"}, {"pid": 101, "eltern": 100, "name": "Godot_v4"},
            {"pid": 200, "eltern": 1, "name": "explorer"}]


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC6")
        for ziel, name, wert in ((betrieb, "cpu_laeufe", 2), (betrieb, "speicher_frei_gb", (32.0, 32.0))):
            p = mock.patch.object(ziel, name, return_value=wert)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(belegung, "lauf_pid", side_effect=lambda lid: 100)
        p.start()
        self.addCleanup(p.stop)

    def lauf(self, **k):
        return betrieb.lauf_start(self.con, self.pid, "CC6", "Rundgang Labor", warten=True, speicher_frei=32.0, schwer=False,
                                  befehl=["godot", "--path", "spiel", "res://rundgang_17.tscn"], **k)

    def an(self, agent):
        return [(n["art"], n["kurz"]) for n in kern.offene(self.con, self.pid, agent)]


class FensterOhneSchirm(Grund):
    def test_erkannt_gemeldet_als_fensterlauf_und_danach_nur_mit_schirm(self):
        lid = self.lauf()
        neu = fenster.pruefen(self.con, fenster={101, 200}, liste=PROZESSE, schirm_frei=False)
        self.assertEqual(neu, [(lid, "Godot_v4")])                                 # Kind des Lauf-Prozesses hat ein Fenster
        self.assertEqual(self.con.execute("SELECT schirm FROM lauf WHERE id = ?", (lid,)).fetchone()[0], 1)
        self.assertIn(("korrektur", f"L{lid} öffnet ein Fenster (Godot_v4) – angemeldet ohne --schirm"), self.an("CC6"))
        self.assertIn(("info", f"L{lid} (CC6) öffnet ein Fenster ohne --schirm"), self.an("TL"))
        text = self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE ? AND art = 'korrektur'", (f"L{lid} öffnet%",)).fetchone()[0]
        self.assertIn("bitte den Lauf sofort beenden", text)                          # Bildschirm zu: Bitte um Ende
        self.assertNotIn("Godot", self.con.execute("SELECT group_concat(text) FROM plan_ereignis").fetchone()[0] or "x")   # kein Titel
        self.assertEqual(fenster.pruefen(self.con, fenster={101}, liste=PROZESSE, schirm_frei=False), [])   # einmal reicht
        with self.assertRaises(kern.AmwFehler) as e:                                 # derselbe Lauf (andere Nummer): nur mit --schirm
            betrieb.lauf_start(self.con, self.pid, "CC6", "Rundgang Labor", warten=True, speicher_frei=32.0, schwer=False,
                               befehl=["godot", "--path", "spiel", "res://rundgang_18.tscn"])
        self.assertIn("mit --schirm", str(e.exception))
        self.assertTrue(betrieb.lauf_start(self.con, self.pid, "CC6", "Rundgang Labor", warten=True, speicher_frei=32.0, schwer=False,
                                           schirm=True, befehl=["godot", "--path", "spiel", "res://rundgang_18.tscn"]))
        betrieb.lauf_start(self.con, self.pid, "CC6", "anderer Lauf", warten=True, speicher_frei=32.0, schwer=False,
                           befehl=["godot", "--headless", "--path", "spiel"])                   # ohne Fenster: frei

    def test_fremdes_fenster_zaehlt_nicht(self):
        self.lauf()
        self.assertEqual(fenster.pruefen(self.con, fenster={200}, liste=PROZESSE, schirm_frei=True), [])

    def test_bei_freiem_bildschirm_nur_info(self):
        lid = self.lauf()
        fenster.pruefen(self.con, fenster={101}, liste=PROZESSE, schirm_frei=True)
        self.assertIn(("info", f"L{lid} öffnet ein Fenster (Godot_v4) – angemeldet ohne --schirm"), self.an("CC6"))


class VonAussenGeschlossen(Grund):
    def test_geschlossen_bei_belegtem_bildschirm_sperrt(self):
        lid = self.lauf()
        self.assertFalse(schirm.zustand(self.con)["frei"])
        betrieb.lauf_ende(self.con, self.pid, "CC6", lid, 0xC000013A, speicher_frei=32.0)
        with self.assertRaises(kern.AmwFehler):
            self.lauf()

    def test_normales_ende_oder_freier_bildschirm_sperrt_nicht(self):
        lid = self.lauf()
        betrieb.lauf_ende(self.con, self.pid, "CC6", lid, 1, speicher_frei=32.0)
        lid = self.lauf()
        schirm.setzen(self.con, self.pid, "TL", True, "weg")
        betrieb.lauf_ende(self.con, self.pid, "CC6", lid, -1073741510, speicher_frei=32.0)
        self.lauf()


if __name__ == "__main__":
    unittest.main()
