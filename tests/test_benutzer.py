"""Mehrere Benutzer (Stufe R1a): Rolle global, Projekte je Benutzer, Prüfung jeder Eingabe von der Online-Seite am PC
(je Rolle: darf / darf nicht), Name des Menschen im Verlauf, Abgleich ohne Passwort und Geheimnis."""
import json
import os
import sqlite3
import tempfile
import unittest

from amw import abgleich, aktionen, benutzer, db, kern


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.a = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
            self.b = db.einfuegen(self.con, "projekt", name="Shop", angelegt_utc=db.jetzt())
        for p in (self.a, self.b):
            kern.agent_neu(self.con, p, "TL", rolle="lead")
            kern.agent_neu(self.con, p, "CC1")
        E = kern.ENTWICKLER
        benutzer.neu(self.con, E, "lea", "leser", projekte=["Spiel"])
        benutzer.neu(self.con, E, "bert", "bearbeiter", projekte=["Spiel"])
        benutzer.neu(self.con, E, "pia", "projekt_admin", projekte=["Spiel"])
        benutzer.neu(self.con, E, "sam", "system_admin")

    def netz(self, name, weg, daten, pid=None):
        d = dict(daten, _benutzer=name)
        return aktionen.ausfuehren(self.con, pid or self.a, weg, d, kanal="netz")


class Rechte(Grund):
    def test_nur_der_mensch_verwaltet_benutzer(self):
        with self.assertRaises(kern.AmwFehler):
            benutzer.neu(self.con, "TL", "x", "leser")
        with self.assertRaises(kern.AmwFehler):
            benutzer.neu(self.con, kern.ENTWICKLER, "mit leer", "leser")
        with self.assertRaises(kern.AmwFehler):
            benutzer.neu(self.con, kern.ENTWICKLER, "lea", "leser")                           # doppelt

    def test_je_rolle_darf_und_darf_nicht(self):
        tabelle = {   # (Benutzer, Klasse, Projekt) → darf?
            ("lea", "arbeiten", "a"): False, ("lea", "lesen", "a"): True,
            ("bert", "arbeiten", "a"): True, ("bert", "arbeiten", "b"): False, ("bert", "projekt", "a"): False,
            ("pia", "projekt", "a"): True, ("pia", "benutzer", "a"): True, ("pia", "system", "a"): False, ("pia", "arbeiten", "b"): False,
            ("sam", "system", "b"): True, ("sam", "arbeiten", "b"): True,
        }
        for (name, klasse, p), soll in tabelle.items():
            ok, grund = benutzer.darf(self.con, name, self.a if p == "a" else self.b, klasse)
            self.assertEqual(ok, soll, (name, klasse, p, grund))
        self.assertEqual(benutzer.darf(self.con, None, self.b, "system"), (True, None))        # der Mensch am PC
        self.assertFalse(benutzer.darf(self.con, "unbekannt", self.a, "lesen")[0])
        benutzer.aendern(self.con, kern.ENTWICKLER, "bert", gesperrt=True)
        self.assertEqual(benutzer.darf(self.con, "bert", self.a, "arbeiten"), (False, "bert ist gesperrt"))

    def test_eingaben_von_der_online_seite_werden_am_pc_geprueft(self):
        with self.assertRaises(aktionen.Ungueltig) as e:                                        # Leser schreibt nichts
            self.netz("lea", "/api/nachricht", {"an": "CC1", "art": "info", "kurz": "hallo"})
        self.assertIn("Leser – dafür braucht es Bearbeiter", str(e.exception))
        with self.assertRaises(aktionen.Ungueltig):                                             # fremdes Projekt
            self.netz("bert", "/api/nachricht", {"an": "CC1", "art": "info", "kurz": "hallo"}, pid=self.b)
        with self.assertRaises(aktionen.Ungueltig):                                             # Einstellungen des PCs nur System-Admin
            self.netz("pia", "/api/einstellungen/pc", {"werte": {}})
        self.assertEqual(benutzer.klasse("/api/einstellungen/projekt"), "projekt")
        self.netz("bert", "/api/nachricht", {"an": "CC1", "art": "info", "kurz": "von Bert"})   # darf
        r = self.con.execute("SELECT von, benutzer FROM nachricht WHERE kurz = 'von Bert'").fetchone()
        self.assertEqual(tuple(r), (kern.ENTWICKLER, "bert"))                                   # Name im Verlauf
        aktionen.ausfuehren(self.con, self.a, "/api/nachricht", {"an": "CC1", "art": "info", "kurz": "am PC", "_benutzer": "lea"}, kanal="seite")
        r = self.con.execute("SELECT benutzer FROM nachricht WHERE kurz = 'am PC'").fetchone()
        self.assertIsNone(r[0])                                                                 # am PC zählt kein Name von außen
        self.assertIsNone(benutzer.AKTUELL.get())                                               # nach der Aktion zurückgesetzt

    def test_abgleich_schreibt_benutzer_ohne_geheimnisse(self):
        online = os.path.join(self.ordner.name, "online.db")
        sp = abgleich.SqliteSpeicher(online) if hasattr(abgleich, "SqliteSpeicher") else None
        if sp is None:
            self.skipTest("kein Test-Speicher")
        sp.ausfuehren([(s, []) for s in abgleich.SCHEMA])
        abgleich.Abgleich(self.con, sp).hochladen(alle=True)
        o = sqlite3.connect(online)
        zeilen = {r[0]: r[1:] for r in o.execute("SELECT name, rolle, projekte, passwort_hash, totp_geheim FROM benutzer")}
        o.close()
        uid_a = self.con.execute("SELECT uid FROM projekt WHERE id = ?", (self.a,)).fetchone()[0]
        self.assertEqual(zeilen["bert"][:2], ("bearbeiter", json.dumps([uid_a])))
        self.assertEqual(zeilen["sam"][2:], (None, None))                                       # nie Passwort oder Geheimnis


if __name__ == "__main__":
    unittest.main()
