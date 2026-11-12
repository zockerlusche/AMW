"""Mehrere Benutzer (Stufe R1a): Rolle global, Projekte je Benutzer, Prüfung jeder Eingabe von der Online-Seite am PC
(je Rolle: darf / darf nicht), Name des Menschen im Verlauf, Abgleich ohne Passwort und Geheimnis."""
import json
import os
import sqlite3
import tempfile
import unittest

from amw import abgleich, aktionen, benutzer, db, kern, workbench


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
        self.assertEqual(benutzer.darf(self.con, benutzer.ZUGANG, self.b, "system"), (True, None))   # Zugang der Seite
        self.assertFalse(benutzer.darf(self.con, None, self.b, "lesen")[0])                     # ohne Namen: nichts
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

    def test_ohne_namen_nur_solange_niemand_angelegt_ist(self):
        """Fail-closed: fehlt der Name, hat die Anfrage keine Rechte – außer im Betrieb vor den Benutzern."""
        weg, d = "/api/nachricht", {"an": "CC1", "art": "info", "kurz": "ohne Namen"}
        with self.assertRaises(aktionen.Ungueltig) as e:                                        # Benutzer gibt es (setUp)
            aktionen.ausfuehren(self.con, self.a, weg, dict(d), kanal="netz")
        self.assertIn("Anmeldung fehlt", str(e.exception))
        with self.assertRaises(aktionen.Ungueltig):
            aktionen.ausfuehren(self.con, self.a, weg, dict(d, _benutzer=""), kanal="netz")
        self.netz(benutzer.ZUGANG, weg, dict(d, kurz="vom Zugang"))                             # Zugang der Seite = System-Admin
        self.assertIsNone(self.con.execute("SELECT benutzer FROM nachricht WHERE kurz = 'vom Zugang'").fetchone()[0])
        with self.assertRaises(kern.AmwFehler):
            benutzer.neu(self.con, kern.ENTWICKLER, "@zugang", "system_admin")                 # niemand heißt wie der Zugang
        with db.schreiben(self.con):                                                            # Betrieb vor den Benutzern
            self.con.execute("DELETE FROM benutzer_projekt")
            self.con.execute("DELETE FROM benutzer")
        aktionen.ausfuehren(self.con, self.a, weg, dict(d, kurz="alt"), kanal="netz")
        self.assertIsNotNone(self.con.execute("SELECT 1 FROM nachricht WHERE kurz = 'alt'").fetchone())

    def test_neuer_benutzer_ohne_rolle_hat_keine_rechte(self):
        benutzer.neu(self.con, kern.ENTWICKLER, "neu1")                                          # ohne Rolle, ohne Projekte
        self.assertEqual(benutzer.darf(self.con, "neu1", self.a, "lesen"),
                         (False, "neu1 wartet auf Freigabe – ein Admin vergibt Rolle und Projekte"))
        benutzer.aendern(self.con, kern.ENTWICKLER, "neu1", rolle="bearbeiter", projekte=["Spiel"])   # Freigabe durch den Admin
        self.assertEqual(benutzer.darf(self.con, "neu1", self.a, "arbeiten"), (True, None))

    def test_seite_setzt_den_namen_selbst(self):
        """api.php nimmt keinen Namen vom Aufrufer und schickt ohne Anmeldung nichts weiter (Quelltext-Prüfung)."""
        wurzel = os.path.dirname(os.path.dirname(os.path.abspath(aktionen.__file__)))
        with open(os.path.join(wurzel, "web", "api.php"), encoding="utf-8") as f:
            api = f.read()
        with open(os.path.join(wurzel, "web", "inc", "lib.php"), encoding="utf-8") as f:
            lib = f.read()
        i, j = api.index("unset($daten['_benutzer'])"), api.index("$daten['_benutzer'] = $wer;")
        self.assertLess(i, j)
        self.assertIn("if ($wer === null) antwort(401", api[i:j])
        self.assertIn("$_SESSION['zugang'] = true;", lib)

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



class Verwaltung(Grund):
    """Stufe R1b: Benutzer verwalten nur am PC, Freischalten schreibt online, Meldung an den Menschen nach dem ersten Anmelden."""
    def setUp(self):
        super().setUp()
        self.sp = abgleich.SqliteSpeicher(os.path.join(self.ordner.name, "online.db"))
        self.sp.ausfuehren([(s, []) for s in abgleich.SCHEMA])

    def am_pc(self, was, d):
        return aktionen.ausfuehren(self.con, self.a, f"/api/benutzer/{was}", d, kanal="seite", speicher=self.sp)

    def test_verwalten_am_pc_und_nicht_von_unterwegs(self):
        self.am_pc("neu", {"name": "ben"})
        self.assertIsNone(benutzer.finden(self.con, "ben")["rolle"])
        self.am_pc("aendern", {"name": "ben", "rolle": "bearbeiter", "projekte": [self.a]})
        self.assertEqual(benutzer.finden(self.con, "ben")["projekte"], [self.a])
        aus = self.am_pc("freischalten", {"name": "ben", "stunden": 2})
        self.assertRegex(aus["code"], r"^[A-Z2-9]{4}(-[A-Z2-9]{4}){3}$")
        with self.assertRaises(aktionen.Ungueltig):
            self.am_pc("freischalten", {"name": "ben", "stunden": 500})
        with self.assertRaises(aktionen.Ungueltig) as e:                                        # System-Admin online: trotzdem nein
            self.netz("sam", "/api/benutzer/neu", {"name": "x"})
        self.assertIn("am PC", str(e.exception))
        with self.assertRaises(aktionen.Ungueltig):
            self.netz("bert", "/api/benutzer/aendern", {"name": "bert", "rolle": "system_admin"})   # sich selbst hochstufen
        d = workbench.daten_benutzer(self.con, self.sp)
        ben = next(b for b in d["benutzer"] if b["name"] == "ben")
        self.assertEqual(ben["online"]["stand"], "wartet_code")
        self.assertNotIn(aus["code"], json.dumps(d))                                            # der Code steht nirgends
        self.assertNotIn(aus["code"].replace("-", ""), json.dumps(d))

    def test_meldung_nach_dem_ersten_anmelden(self):
        benutzer.neu(self.con, kern.ENTWICKLER, "neu2")
        aus = self.netz("neu2", "/api/benutzer/eingerichtet", {})
        self.assertEqual(aus, {"gemeldet": True})
        n = self.con.execute("SELECT von, kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id"
                             " WHERE e.agent = ? ORDER BY n.id DESC LIMIT 1", (kern.ENTWICKLER,)).fetchone()
        self.assertEqual(tuple(n), ("AMW", "Neuer Benutzer neu2 wartet auf Freigabe"))
        with self.assertRaises(aktionen.Ungueltig):                                             # nur von der Seite
            aktionen.ausfuehren(self.con, self.a, "/api/benutzer/eingerichtet", {}, kanal="seite")
        benutzer.aendern(self.con, kern.ENTWICKLER, "neu2", gesperrt=True)
        with self.assertRaises(aktionen.Ungueltig):                                             # gesperrt: auch das nicht
            self.netz("neu2", "/api/benutzer/eingerichtet", {})


if __name__ == "__main__":
    unittest.main()
