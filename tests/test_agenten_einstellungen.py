"""Agenten-Einstellungen (Schema 22): Lead als Schalter, Fachgebiet, Arbeitsweise, Zuständig für / Fasst nicht an.
Nur „Terminal“ startet die AMW selbst; ein Chat hat weder Sitzung noch Überwachung."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import tempfile
import unittest
from unittest import mock

from amw import db, kern, steuerung, workbench


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "t.db")
        self.con = db.anlegen(self.pfad)
        self.addCleanup(lambda: self.con.close())
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())

    def zeile(self, kennung):
        return kern.agent_zeile(self.con, self.pid, kennung)


class Felder(Grund):
    def test_lead_ist_ein_schalter_fachgebiet_ein_eigenes_feld(self):
        kern.agent_neu(self.con, self.pid, "Chef", rolle="lead", fachgebiet="Planung", arbeitsweise="chat")
        kern.agent_neu(self.con, self.pid, "Maler", rolle="Grafik", grenzen="nur Bilder")          # frühere Schreibweise
        self.assertEqual((self.zeile("Chef")["rolle"], self.zeile("Chef")["fachgebiet"], self.zeile("Chef")["arbeitsweise"]), ("lead", "Planung", "chat"))
        m = self.zeile("Maler")
        self.assertEqual((m["rolle"], m["fachgebiet"], m["zustaendig"], m["arbeitsweise"]), (None, "Grafik", "nur Bilder", "terminal"))
        self.assertTrue(kern.ist_lead(self.con, self.pid, "Chef"))
        self.assertFalse(kern.ist_lead(self.con, self.pid, "Maler"))
        kern.agent_einstellen(self.con, self.pid, "Chef", "Maler", fachgebiet="Grafik & Karten", zustaendig="Karten-Look,  Sprites",
                              fasst_nicht_an="Spiellogik", arbeitsweise="desktop")
        m = self.zeile("Maler")
        self.assertEqual((m["fachgebiet"], m["zustaendig"], m["fasst_nicht_an"], m["arbeitsweise"]), ("Grafik & Karten", "Karten-Look, Sprites", "Spiellogik", "desktop"))
        for falsch in ({"arbeitsweise": "fax"}, {"fachgebiet": "x" * 41}):
            with self.assertRaises(kern.AmwFehler):
                kern.agent_einstellen(self.con, self.pid, "Chef", "Maler", **falsch)
        with self.assertRaises(kern.AmwFehler):
            kern.agent_neu(self.con, self.pid, "Neu", arbeitsweise="fax")

    def test_pflicht_kontext_nennt_fuehrung_fachgebiet_und_auftrag(self):
        kern.agent_neu(self.con, self.pid, "Chef", rolle="lead", arbeitsweise="chat")
        kern.agent_neu(self.con, self.pid, "Maler", fachgebiet="Grafik")
        kern.agent_einstellen(self.con, self.pid, "Chef", "Maler", zustaendig="Karten-Look", fasst_nicht_an="Spiellogik")
        erste = kern.kontext(self.con, self.pid, "Maler").split("\n")[0]
        for teil in ("Fachgebiet: Grafik", "Zuständig für: Karten-Look", "Fasst nicht an: Spiellogik"):
            self.assertIn(teil, erste)
        self.assertNotIn("Lead", erste)
        self.assertIn("Du führst dieses Projekt (Lead)", kern.kontext(self.con, self.pid, "Chef").split("\n")[0])

    def test_nur_terminal_wird_gestartet(self):
        for k, weise in (("Term", "terminal"), ("App", "desktop"), ("Chat", "chat")):
            kern.agent_neu(self.con, self.pid, k, arbeitsweise=weise)
            steuerung.profil_setzen(self.con, self.pid, "Entwickler", k, ordner=self.ordner.name)
        gestartet = []
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": self.ordner.name}):
            steuerung.starten(self.con, self.pid, "Term", ausfuehren=lambda a, f, o: gestartet.append(a))
            for k, wort in (("App", "Desktop-App"), ("Chat", "als Chat")):
                with self.assertRaises(kern.AmwFehler) as e:
                    steuerung.starten(self.con, self.pid, k, ausfuehren=lambda a, f, o: gestartet.append(a))
                self.assertIn(wort, str(e.exception))
        self.assertEqual(len(gestartet), 1)
        self.assertEqual(steuerung.fehlende(self.con, self.pid), ["Term"])               # App und Chat fehlen nie
        start = {a["kennung"]: (bool(a["chat"]), bool(a["startbar"]), a["arbeitsweise"]) for a in workbench.daten_start(self.con, self.pid)["agenten"]}
        self.assertEqual(start, {"Term": (False, True, "terminal"), "App": (False, False, "desktop"), "Chat": (True, False, "chat")})

    def test_vorschlag_aus_der_bisherigen_arbeit(self):
        kern.agent_neu(self.con, self.pid, "Chef", rolle="lead")
        kern.agent_neu(self.con, self.pid, "Maler")
        self.assertIsNone(workbench.agent_vorschlag(self.con, self.pid, "Maler")["fachgebiet"])       # noch nichts gemacht
        with db.schreiben(self.con):
            bid = db.einfuegen(self.con, "bogen", projekt_id=self.pid, nr=1, titel="Karten-Look", ziel="z", abnahme="a", status="aktiv",
                               angelegt_von="Chef", angelegt_utc=db.jetzt())
            for i, titel in enumerate(("Sprites für Level 1", "Karten-Look: Wasser", "Icon-Satz", "Bild der Startseite", "Texte prüfen")):
                db.einfuegen(self.con, "aufgabe", projekt_id=self.pid, titel=titel, agent="Maler", angelegt_von="Chef", status="fertig", beleg="abc1234",
                             angelegt_utc=db.jetzt(), fertig_utc=f"2026-11-0{i + 1}T10:00:00Z", bogen_id=bid)
        v = workbench.agent_vorschlag(self.con, self.pid, "Maler")
        self.assertEqual((v["fachgebiet"], v["zustaendig"]), ("Grafik", "Karten-Look"))
        self.assertIn("5 fertige Aufgaben", v["grundlage"])
        with self.assertRaises(kern.AmwFehler):
            workbench.agent_vorschlag(self.con, self.pid, "Niemand")


class Umstellung(Grund):
    def test_21_nach_22_uebernimmt_den_bestand(self):
        with db.schreiben(self.con):
            for k, rolle, grenzen, ordner in (("TL", "lead", None, None), ("Chef2", "Lead", None, self.ordner.name), ("Maler", "Grafik", "nur Bilder", self.ordner.name), ("Neu", None, None, None)):
                db.einfuegen(self.con, "agent", projekt_id=self.pid, kennung=k, rolle=rolle, grenzen=grenzen, ordner=ordner, angelegt_utc=db.jetzt())
        for sp in ("braucht_gb", "braucht_vram_gb", "braucht_platte_gb", "rechner"):   # Bedarf und Rechner je Lauf kamen mit Schema 24
            self.con.execute(f"ALTER TABLE lauf DROP COLUMN {sp}")
        for sp in ("hinweis", "hinweis_gruppe"):   # Satz für die Versionshinweise kam mit Schema 26
            self.con.execute(f"ALTER TABLE aufgabe DROP COLUMN {sp}")
        for tab in ("nachricht", "frage_verlauf"):   # wer von den Menschen es war, kam mit Schema 27
            if self.con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (tab,)).fetchone():
                self.con.execute(f"ALTER TABLE {tab} DROP COLUMN benutzer")
        self.con.execute("DROP INDEX IF EXISTS nachricht_bezug")      # Bezug an Nachrichten kam mit Schema 29
        self.con.execute("DROP INDEX IF EXISTS nachricht_antwort")
        self.con.execute("ALTER TABLE nachricht DROP COLUMN bezug")
        for sp in ("groesse", "art"):                     # Größe und Art kamen mit Schema 30
            self.con.execute(f"ALTER TABLE aufgabe DROP COLUMN {sp}")
        self.con.execute("ALTER TABLE agent DROP COLUMN entfernt_utc")      # Agenten entfernen kam mit Schema 28
        self.con.execute("ALTER TABLE regel DROP COLUMN vorlage")      # Herkunft aus dem Grund-Regelwerk kam mit Schema 23
        for sp in ("fachgebiet", "arbeitsweise", "zustaendig", "fasst_nicht_an"):
            self.con.execute(f"ALTER TABLE agent DROP COLUMN {sp}")
        self.con.execute("PRAGMA user_version = 21")
        self.con.close()
        self.con = db.verbinde(self.pfad)
        self.assertEqual(self.con.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
        ist = {r["kennung"]: (r["rolle"], r["fachgebiet"], r["arbeitsweise"], r["zustaendig"]) for r in self.con.execute("SELECT * FROM agent")}
        self.assertEqual(ist, {"TL": ("lead", None, "chat", None),                       # Lead ohne Ordner galt schon als Chat
                               "Chef2": ("lead", None, "terminal", None),                 # „Lead“ in anderer Schreibweise bleibt Lead
                               "Maler": (None, "Grafik", "terminal", "nur Bilder"),       # Freitext-Rolle war das Fachgebiet
                               "Neu": (None, None, "terminal", None)})


if __name__ == "__main__":
    unittest.main()
