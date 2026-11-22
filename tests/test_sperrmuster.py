"""A1919 (TH160 F2, Mehrprojekt 1): Sperrliste = feste AMW-Liste (abnahme.GESPERRT) + Muster je Projekt (Projekt-Einstellung
sperrmuster). Ein Besitzer: abnahme.gesperrt(pfade, typ, projekt) – gilt in Startregel 5 (Wächter) und im Diff-Tor von
Prüfung C für Pakete dieses Projekts. Projekt mit Muster sperrt, anderes Projekt nicht, feste Liste immer."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from amw import abnahme, arbeitspaket, cli, db, kern, pruefung_c, waechter


class Liste(unittest.TestCase):
    def test_muster_zusaetzlich_feste_liste_immer(self):
        m = ["src/sicherheit/*", "*.key"]
        self.assertEqual(abnahme.gesperrt(["src/sicherheit/login.py"], None, m), [("src/sicherheit/login.py", "gesperrt im Projekt (src/sicherheit/*)")])
        self.assertEqual([p for p, _ in abnahme.gesperrt(["Daten/Geheim.KEY"], None, m)], ["Daten/Geheim.KEY"])   # Groß/klein egal
        self.assertEqual(abnahme.gesperrt(["src/spiel/held.py"], None, m), [])
        self.assertEqual(abnahme.gesperrt(["src/sicherheit/login.py"]), [])                                       # ohne Muster frei
        fest = abnahme.gesperrt(["amw/auslieferung.py"], None, [])                                                # feste Liste immer
        self.assertEqual(len(fest), 1)
        self.assertNotIn("im Projekt", fest[0][1])
        self.assertEqual(abnahme.gesperrt(["amw/auslieferung.py"], None, m), fest)                                # fester Grund zuerst

    def test_muster_gelten_auch_fuer_test_pakete(self):
        self.assertEqual(abnahme.gesperrt(["tests/test_neu.py"], abnahme.TEST_SCHREIBEN), [])
        self.assertEqual(len(abnahme.gesperrt(["tests/test_neu.py"], abnahme.TEST_SCHREIBEN, ["tests/test_neu.py"])), 1)

    def test_startregel_ordner(self):
        m = ["src/sicherheit/*"]
        self.assertEqual(abnahme.startregel(["src/sicherheit/"], None, m), [("src/sicherheit/", "gesperrt im Projekt (src/sicherheit/*)")])
        self.assertEqual(abnahme.startregel(["src/"], None, m), [("src/", "gesperrt im Projekt (src/sicherheit/*)")])   # Gesperrtes darin
        self.assertEqual(abnahme.startregel(["src/spiel/"], None, m), [])
        self.assertEqual(abnahme.startregel(["src/sicherheit/"]), [])

    def test_muster_pruefen(self):
        self.assertEqual(abnahme.muster_pruefen('["a/*", "b\\\\c.py", "a/*"]'), ["a/*", "b/c.py"])                 # doppelt, Backslash
        self.assertEqual(abnahme.muster_pruefen("a/*, *.key ,"), ["a/*", "*.key"])
        self.assertEqual(abnahme.muster_pruefen(""), [])
        for falsch in ('{"a": 1}', "/abs/pfad", "../raus/*", "x" * 201):
            with self.assertRaises(ValueError, msg=falsch):
                abnahme.muster_pruefen(falsch)
        with self.assertRaises(ValueError):
            abnahme.muster_pruefen([f"m{i}" for i in range(51)])


class Projekte(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad, "LOCALAPPDATA": os.path.join(self.ordner.name, "lad")})
        u.start()
        self.addCleanup(u.stop)
        os.environ.pop("AMW_AGENT", None)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
            self.pid2 = db.einfuegen(self.con, "projekt", name="Anderes", angelegt_utc=db.jetzt())
        for p in (self.pid, self.pid2):
            kern.agent_neu(self.con, p, "TL", rolle="lead")
            kern.agent_neu(self.con, p, "CC1")
            kern.projekt_einstellen(self.con, p, kern.ENTWICKLER, platz_wurzel=os.path.join(self.ordner.name, f"plaetze{p}"), plaetze=1)
        kern.projekt_einstellen(self.con, self.pid, "TL", sperrmuster='["src/sicherheit/*", "*.key"]')

    def paket(self, pid, bereiche):
        aid = kern.aufgabe_neu(self.con, pid, "TL", "Paket", "TL")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET pruefbefehl = ?, dateibereich = ? WHERE id = ?",
                             ("python -m unittest tests.test_x", bereiche, aid))
        arbeitspaket.setzen(self.con, pid, "TL", aid, art="p")
        arbeitspaket.zustand_setzen(self.con, pid, "TL", aid, "startklar")
        return aid

    def test_einstellung(self):
        self.assertEqual(abnahme.projekt_muster(self.con, self.pid), ["src/sicherheit/*", "*.key"])
        self.assertEqual(abnahme.projekt_muster(self.con, self.pid2), [])
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "CC1", sperrmuster="x/*")                 # nur Lead oder Mensch
        with self.assertRaises(kern.AmwFehler) as f:
            kern.projekt_einstellen(self.con, self.pid, "TL", sperrmuster="../x")
        self.assertIn("sperrmuster:", str(f.exception))
        kern.projekt_einstellen(self.con, self.pid2, kern.ENTWICKLER, sperrmuster="geheim/*")
        self.assertEqual(abnahme.projekt_muster(self.con, self.pid2), ["geheim/*"])
        kern.projekt_einstellen(self.con, self.pid2, "TL", sperrmuster="")                       # leer = entfernt
        self.assertEqual(abnahme.projekt_muster(self.con, self.pid2), [])

    def test_nicht_aus_einer_agenten_sitzung(self):
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_AGENT": "", "CLAUDECODE": "1", "CLAUDE_CODE_MESSAGING_SOCKET": ""}), \
                contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "Spiel", "--von", "Entwickler", "projekt", "einstellen", "sperrmuster="])
        self.assertNotEqual(rc, 0)
        self.assertIn("nicht aus einer Agenten-Sitzung", aus.getvalue())
        self.assertEqual(abnahme.projekt_muster(self.con, self.pid), ["src/sicherheit/*", "*.key"])

    def test_startregel_5_je_projekt(self):
        r = waechter.pruefen(self.con, self.pid, self.paket(self.pid, "src/sicherheit/"), limit=10)
        self.assertEqual(r["regel"], 5)
        self.assertIn("gesperrt im Projekt", r["grund"])
        self.assertIsNone(waechter.pruefen(self.con, self.pid2, self.paket(self.pid2, "src/sicherheit/"), limit=10)["regel"])
        for p in (self.pid, self.pid2):                                                         # feste Liste in jedem Projekt
            self.assertEqual(waechter.pruefen(self.con, p, self.paket(p, "amw/auslieferung.py"), limit=10)["regel"], 5)

    def test_diff_tor_pruefung_c(self):
        quelle = os.path.join(self.ordner.name, "repo")
        os.makedirs(os.path.join(quelle, "src", "sicherheit"))
        git = lambda *a: subprocess.run(["git", "-C", quelle, *a], check=True, capture_output=True, stdin=subprocess.DEVNULL)
        git("init", "-q", "-b", "main")
        git("config", "user.email", "t@t")
        git("config", "user.name", "t")
        open(os.path.join(quelle, "liesmich.txt"), "w").write("a\n")
        git("add", ".")
        git("commit", "-qm", "basis")
        git("checkout", "-qb", "paket")
        open(os.path.join(quelle, "src", "sicherheit", "login.py"), "w").write("x = 1\n")
        git("add", ".")
        git("commit", "-qm", "paket")
        mit = pruefung_c.zweig_befund(quelle, "paket", ["src/"], sperrmuster=abnahme.projekt_muster(self.con, self.pid))
        self.assertEqual([p for p, _ in mit["gesperrt"]], ["src/sicherheit/login.py"])
        self.assertNotEqual(mit["code"], None)
        ohne = pruefung_c.zweig_befund(quelle, "paket", ["src/"], sperrmuster=abnahme.projekt_muster(self.con, self.pid2))
        self.assertEqual(ohne["gesperrt"], [])
        self.assertNotEqual(mit["code"], ohne["code"])
        t = abnahme.diff_tor(quelle, "main", ["src/"], None, ["src/sicherheit/*"])
        self.assertFalse(t["ok"])
        self.assertTrue(abnahme.diff_tor(quelle, "main", ["src/"])["ok"])


if __name__ == "__main__":
    unittest.main()
