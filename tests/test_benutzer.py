"""Mehrere Benutzer (Stufe R1a): Rolle global, Projekte je Benutzer, Prüfung jeder Eingabe von der Online-Seite am PC
(je Rolle: darf / darf nicht), Name des Menschen im Verlauf, Abgleich ohne Passwort und Geheimnis."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
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



class VerwaltenRechte(Grund):
    """Wer welche Benutzer verwalten darf (A1615 a) – gilt online und am PC gleich."""

    def darf(self, wer, ziel=None, **kw):
        return benutzer.darf_verwalten(self.con, wer, ziel, **kw)[0]

    def test_system_admin_und_der_mensch_alles_ausser_sich_selbst_aussperren(self):
        for wer in (kern.ENTWICKLER, benutzer.ZUGANG, "sam"):
            self.assertTrue(self.darf(wer, "pia", rolle="system_admin"))
            self.assertTrue(self.darf(wer, "lea", gesperrt=True, projekte=[self.a, self.b]))
            self.assertTrue(self.darf(wer, None, neu=True, rolle="leser", projekte=[self.b]))
        self.assertFalse(self.darf("sam", "sam", gesperrt=True))
        self.assertFalse(self.darf("sam", "sam", rolle="leser"))

    def test_projekt_admin_nur_eigene_projekte_und_bis_projekt_admin(self):
        self.assertTrue(self.darf("pia", "bert", rolle="projekt_admin"))
        self.assertTrue(self.darf("pia", "lea", gesperrt=True))
        self.assertFalse(self.darf("pia", "bert", rolle="system_admin"))                      # nie System-Admin
        self.assertFalse(self.darf("pia", "sam", gesperrt=True))                              # System-Admin unantastbar
        self.assertFalse(self.darf("pia", "bert", projekte=[self.a, self.b]))                 # Shop ist nicht ihres
        self.assertFalse(self.darf("pia", "pia", gesperrt=True))
        benutzer.aendern(self.con, kern.ENTWICKLER, "lea", projekte=["Spiel", "Shop"])
        self.assertTrue(self.darf("pia", "lea", projekte=[self.a, self.b]))                   # Shop bleibt, nur Spiel ist ihres
        self.assertFalse(self.darf("pia", "lea", projekte=[self.a]))                          # Shop wegnehmen: nicht ihres
        benutzer.neu(self.con, kern.ENTWICKLER, "fremd", "bearbeiter", projekte=["Shop"])
        self.assertFalse(self.darf("pia", "fremd", gesperrt=True))                            # keins ihrer Projekte
        benutzer.neu(self.con, kern.ENTWICKLER, "neuling")                                    # wartet auf Freigabe
        self.assertTrue(self.darf("pia", "neuling", rolle="bearbeiter", projekte=[self.a]))
        self.assertTrue(self.darf("pia", None, neu=True, rolle="leser", projekte=[self.a]))
        self.assertFalse(self.darf("pia", None, neu=True, rolle="leser", projekte=[]))

    def test_keine_kontouebernahme_durch_projekt_admin(self):
        """TL P126: Ein Projekt-Admin darf ein Konto, das nicht ganz in seinen Projekten liegt oder selbst Projekt-Admin ist,
        weder freischalten (er bekäme den Code) noch sperren noch die Rolle ändern – Projekte aus seinen eigenen gehen weiter."""
        benutzer.neu(self.con, kern.ENTWICKLER, "paul", "projekt_admin", projekte=["Spiel", "Shop"])     # B mit Zusatzprojekt
        benutzer.neu(self.con, kern.ENTWICKLER, "bea", "bearbeiter", projekte=["Spiel", "Shop"])        # Bearbeiter mit Fremdprojekt
        for ziel in ("paul", "bea"):
            self.assertFalse(self.darf("pia", ziel, freischalten=True), ziel)
            self.assertFalse(self.darf("pia", ziel, gesperrt=True), ziel)
            self.assertFalse(self.darf("pia", ziel, rolle="leser"), ziel)
            self.assertTrue(self.darf("pia", ziel, projekte=[self.a, self.b]), ziel)                  # nichts geändert
        benutzer.neu(self.con, kern.ENTWICKLER, "pit", "projekt_admin", projekte=["Spiel"])             # Projekt-Admin ganz in ihren
        self.assertFalse(self.darf("pia", "pit", freischalten=True))
        self.assertFalse(self.darf("pia", "pit", gesperrt=True))
        self.assertTrue(self.darf("pia", "bert", freischalten=True))                                   # Bearbeiter ganz in ihren
        self.assertTrue(self.darf("pia", "neuling" if benutzer.finden(self.con, "neuling") else "lea", freischalten=True))
        self.assertTrue(self.darf("sam", "paul", freischalten=True))                                   # System-Admin: ja

    def test_andere_rollen_und_gesperrte_gar_nicht(self):
        for wer in ("lea", "bert", "niemand", None):
            self.assertFalse(self.darf(wer, "lea", gesperrt=True))
        benutzer.aendern(self.con, kern.ENTWICKLER, "pia", gesperrt=True)
        self.assertFalse(self.darf("pia", "bert", rolle="leser"))


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
        self.netz("sam", "/api/benutzer/neu", {"name": "x"})                                    # online: System-Admin legt an (A1615 a)
        self.assertIsNotNone(benutzer.finden(self.con, "x"))
        with self.assertRaises(aktionen.Ungueltig) as e:                                        # Freischalt-Code online: (noch) nein
            self.netz("sam", "/api/benutzer/freischalten", {"name": "x"})
        self.assertIn("am PC", str(e.exception))
        with self.assertRaises(aktionen.Ungueltig):
            self.netz("bert", "/api/benutzer/aendern", {"name": "bert", "rolle": "system_admin"})   # sich selbst hochstufen
        with self.assertRaises(aktionen.Ungueltig):
            self.netz("pia", "/api/benutzer/aendern", {"name": "ben", "rolle": "system_admin"})     # Projekt-Admin: nie System-Admin
        uid = self.con.execute("SELECT uid FROM projekt WHERE id = ?", (self.a,)).fetchone()[0]
        self.netz("pia", "/api/benutzer/aendern", {"name": "ben", "rolle": "projekt_admin", "projekte": [uid]})   # Projekte als uid
        self.assertEqual((benutzer.finden(self.con, "ben")["rolle"], benutzer.finden(self.con, "ben")["projekte"]), ("projekt_admin", [self.a]))
        with self.assertRaises(aktionen.Ungueltig):
            self.netz("pia", "/api/benutzer/aendern", {"name": "sam", "gesperrt": True})            # System-Admin unantastbar
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
