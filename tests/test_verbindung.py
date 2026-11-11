"""Einstellungen neu gegliedert: Prüf-Knöpfe (Online-Speicher, Online-Seite) ohne Netz, Vorgaben und Neustart-Kennzeichen
je Feld, Sprache als Vorgabe, Schalter „In Claude öffnen“."""
import os
import re
import sqlite3
import tempfile
import unittest
from unittest import mock

from amw import abgleich, db, einstellungen, kern, verbindung, workbench


class Pruefungen(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)

    def speicher(self, tabellen):
        pfad = os.path.join(self.ordner.name, "s.db")
        con = sqlite3.connect(pfad)
        for t in tabellen:
            con.execute(f"CREATE TABLE {t} (x)")
        con.commit()
        con.close()
        return abgleich.SqliteSpeicher(pfad)

    def test_speicher_angemeldet_und_tabellen_da(self):
        r = verbindung.speicher(self.speicher(verbindung.TABELLEN))
        self.assertTrue(r["ok"])
        self.assertEqual([(s["name"], s["ok"]) for s in r["schritte"]], [("anmelden", True), ("tabellen", True)])

    def test_speicher_ohne_tabellen_nennt_was_fehlt(self):
        r = verbindung.speicher(self.speicher(["zustand"]))
        self.assertFalse(r["ok"])
        self.assertEqual((r["schritte"][1]["name"], r["schritte"][1]["wert"]), ("tabellen", "eingang, projekt"))

    def test_speicher_nicht_eingerichtet_oder_nicht_erreichbar(self):
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": self.ordner.name}):                  # keine Zugangsdatei
            self.assertEqual(verbindung.speicher()["schritte"], [{"name": "zugang", "ok": False, "wert": None}])

        class Kaputt:
            def ausfuehren(self, anweisungen):
                raise OSError("Turso HTTP 401")
        r = verbindung.speicher(Kaputt())
        self.assertEqual(r["schritte"], [{"name": "anmelden", "ok": False, "wert": "Turso HTTP 401"}])

    def test_version_der_seite_steht_im_online_speicher(self):
        sp = self.speicher([])
        con = sqlite3.connect(sp.pfad)
        con.execute("CREATE TABLE zustand (schluessel TEXT PRIMARY KEY, wert TEXT)")
        con.commit()
        self.assertIsNone(verbindung.seiten_version(sp))                                   # noch niemand angemeldet
        con.execute("INSERT INTO zustand VALUES ('web_version', '1.46.0')")
        con.commit()
        con.close()
        self.assertEqual(verbindung.seiten_version(sp), "1.46.0")

        class Kaputt:
            def ausfuehren(self, anweisungen):
                raise OSError("weg")
        self.assertIsNone(verbindung.seiten_version(Kaputt()))                             # nicht erreichbar: kein Schritt, kein Fehler
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(verbindung.__file__))), "web", "inc", "lib.php"), encoding="utf-8") as f:
            php = f.read()
        self.assertIn("VALUES ('web_version', ?)", php)                                    # die Seite hinterlegt sie beim Anmelden
        self.assertIn("} catch (Throwable $e) {}", php)                                    # … und die Anmeldung hängt nie daran

    def test_die_tabellen_der_pruefung_legt_der_abgleich_an(self):
        schema = " ".join(abgleich.SCHEMA)
        for t in verbindung.TABELLEN:
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {t} ", schema)

    def test_seite(self):
        seiten = {"https://a.example/": (200, "<html>"), "https://a.example" + verbindung.HILFE_PROBE: (200, '{"titel": "x"}')}
        namen = lambda r: [(s["name"], s["ok"]) for s in r["schritte"]]
        self.assertEqual(namen(verbindung.seite("")), [("adresse", False)])
        self.assertEqual(namen(verbindung.seite("http://a.example")), [("https", False)])            # nie unverschlüsselt
        r = verbindung.seite("https://a.example/", holen=lambda u: seiten[u], version=lambda: None)
        self.assertEqual((r["ok"], namen(r)), (True, [("https", True), ("antwort", True), ("amw", True)]))    # Version noch nicht hinterlegt: kein Schritt
        from amw import __version__
        r = verbindung.seite("https://a.example/", holen=lambda u: seiten[u], version=lambda: __version__)
        self.assertEqual((r["ok"], namen(r)[-1], r["schritte"][-1]["wert"]), (True, ("version", True), __version__))
        r = verbindung.seite("https://a.example/", holen=lambda u: seiten[u], version=lambda: "1.0.0")
        self.assertEqual((r["ok"], namen(r)[-1], r["schritte"][-1]["wert"]), (False, ("version", False), f"1.0.0, dieser PC: {__version__}"))
        alt = dict(seiten, **{"https://a.example" + verbindung.HILFE_PROBE: (404, "")})             # antwortet, aber keine AMW-Seite
        r = verbindung.seite("https://a.example", holen=lambda u: alt[u])
        self.assertEqual((r["ok"], namen(r)), (False, [("https", True), ("antwort", True), ("amw", False)]))
        r = verbindung.seite("https://a.example", holen=lambda u: (503, ""))
        self.assertEqual(namen(r), [("https", True), ("antwort", False)])

        def weg(u):
            raise OSError("getaddrinfo failed")
        r = verbindung.seite("https://a.example", holen=weg)
        self.assertEqual(namen(r), [("https", True), ("verbindung", False)])
        with self.assertRaises(LookupError):
            verbindung.pruefen("irgendwas")


class Felder(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        umgebung = mock.patch.dict(os.environ, {"LOCALAPPDATA": self.ordner.name, "AMW_DB": os.path.join(self.ordner.name, "t.db")})
        umgebung.start()
        self.addCleanup(umgebung.stop)
        self.con = db.anlegen()
        self.addCleanup(lambda: self.con.close())
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "Chef", rolle="lead")

    def test_neustart_liste_deckt_alles_was_der_waechter_nur_beim_start_liest(self):
        with open(os.path.join(os.path.dirname(einstellungen.__file__), "dienst.py"), encoding="utf-8") as f:
            quelle = f.read()
        gelesen = set(re.findall(r'\be\["([a-z_]+)"\]', quelle))
        self.assertTrue(gelesen)                                                   # der Test sieht die Stellen noch
        self.assertLessEqual(gelesen, set(einstellungen.NEUSTART), "im Wächter gelesen, aber nicht als ‚Neustart nötig‘ gekennzeichnet")
        self.assertLessEqual(set(einstellungen.NEUSTART), set(einstellungen.FELDER))

    def test_einstellungen_liefern_vorgaben_neustart_und_adresse(self):
        d = workbench.daten_einstellungen(self.con, self.pid)
        self.assertEqual(d["vorgaben"]["pc"]["aufsicht_s"], 30)
        self.assertNotIn("rechner", d["vorgaben"]["pc"])                           # hängt am Rechner – kein Vergleichswert
        self.assertEqual(d["vorgaben"]["web"]["leerlauf_min"], 30)
        self.assertIn("takt_min", d["vorgaben"]["projekt"])
        self.assertIn("port", d["neustart"])
        self.assertEqual(d["seite"], {"adresse": ""})
        from amw import push
        push.speichern({"link": "https://amw.example.de"})
        self.assertEqual(workbench.daten_einstellungen(self.con, self.pid)["seite"]["adresse"], "https://amw.example.de")

    def test_sprache_als_vorgabe(self):
        self.assertEqual(workbench.daten_start(self.con, self.pid)["sprache_vorgabe"], "auto")
        einstellungen.speichern({"sprache": "EN"})
        self.assertEqual(workbench.daten_start(self.con, self.pid)["sprache_vorgabe"], "en")
        with self.assertRaises(ValueError):
            einstellungen.speichern({"sprache": "fr"})

    def test_schalter_in_claude_oeffnen(self):
        self.assertTrue(einstellungen.wert("claude_link"))                         # Vorgabe: an, wie bisher
        einstellungen.speichern({"claude_link": False})
        self.assertFalse(einstellungen.wert("claude_link"))
        from amw import gespraech
        einstellungen.speichern({"betriebsart": "cloud"})
        self.assertFalse(gespraech.link_zeigen())                                  # ausgeschaltet
        einstellungen.speichern({"claude_link": True})
        self.assertTrue(gespraech.link_zeigen())
        einstellungen.speichern({"betriebsart": "pc"})                             # der Link führt ins Internet
        self.assertFalse(gespraech.link_zeigen())


if __name__ == "__main__":
    unittest.main()
