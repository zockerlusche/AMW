"""A1922 (TH160 F2, Mehrprojekt 4): Werkzeug-Umgebung je Projekt für Arbeiter – zusätzliche Variablen (Wert aus der Umgebung
der AMW) und PATH-Einträge (Projekt-Einstellung arbeiter_umgebung, nur Lead oder Mensch). Nie Zugangsdaten-artige Namen, nie
Netz (Proxy), nie was die AMW selbst setzt; die Negativprobe (A1906) läuft mit der Grundumgebung."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

from amw import abnahme, arbeiter, cli, db, kern, platz

SDK = r"C:\Werkzeuge\sdk\bin"


class Pruefen(unittest.TestCase):
    def test_gueltig(self):
        w = arbeiter.werkzeuge_pruefen('{"variablen": ["java_home", "GRADLE_USER_HOME", "JAVA_HOME"], "pfade": ["%s"]}'
                                       % SDK.replace("\\", "\\\\"))
        self.assertEqual(w, {"variablen": ["JAVA_HOME", "GRADLE_USER_HOME"], "pfade": [SDK]})
        self.assertEqual(arbeiter.werkzeuge_pruefen(""), {})

    def test_abgelehnt(self):
        for name in ("GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "API_KEY", "DB_PASSWORD", "NPM_AUTH", "HTTPS_PROXY", "AMW_DB",
                     "PATH", "GIT_DIR", "ANTHROPIC_API_KEY", "CLAUDE_CONFIG_DIR", "TEMP", "1ABC", "A B"):
            with self.assertRaises(ValueError, msg=name):
                arbeiter.werkzeuge_pruefen({"variablen": [name]})
        for pfad in ("relativ\\bin", r"C:\a;C:\b", "C:\\" + "x" * 260):
            with self.assertRaises(ValueError, msg=pfad):
                arbeiter.werkzeuge_pruefen({"pfade": [pfad]})
        for falsch in ('["JAVA_HOME"]', {"variablen": [], "netz": True}, {"variablen": [f"V{i}" for i in range(31)]}):
            with self.assertRaises(ValueError, msg=str(falsch)):
                arbeiter.werkzeuge_pruefen(falsch)


class Umgebung(unittest.TestCase):
    def setUp(self):
        self.o = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.o.cleanup)
        self.p = platz.pfade(os.path.join(self.o.name, "plaetze"), 1)
        os.makedirs(self.p["klon"])
        self.basis = dict(os.environ, JAVA_HOME=r"C:\Java\jdk", GITHUB_TOKEN="geheim", GRADLE_USER_HOME=r"C:\Caches\gradle")

    def test_nur_eingestellte_variablen_und_pfade(self):
        grund = arbeiter.umgebung(self.p, self.basis)
        self.assertNotIn("JAVA_HOME", grund)                                                       # Grundumgebung wie bisher
        u = arbeiter.umgebung(self.p, self.basis, werkzeuge={"variablen": ["JAVA_HOME"], "pfade": [SDK]})
        self.assertEqual(u["JAVA_HOME"], r"C:\Java\jdk")
        self.assertNotIn("GRADLE_USER_HOME", u)
        self.assertNotIn("GITHUB_TOKEN", u)
        self.assertEqual(u["PATH"], grund["PATH"] + os.pathsep + SDK)                              # hinter dem minimalen PATH
        self.assertEqual((u["PYTHONUTF8"], u["GIT_CONFIG_NOSYSTEM"]), ("1", "1"))                 # was die AMW setzt, bleibt

    def test_kommt_im_befehl_an(self):
        u = arbeiter.umgebung(self.p, self.basis, werkzeuge={"variablen": ["JAVA_HOME"]})
        befehl = f'"{sys.executable}" -c "import os; print(os.environ.get(\'JAVA_HOME\'), os.environ.get(\'GITHUB_TOKEN\'))"'
        r = abnahme.ausfuehren(befehl, self.p["klon"], u, 60)
        self.assertEqual(r["rc"], 0, r)
        self.assertIn(r"C:\Java\jdk None", r["ausgabe"])

    def test_gesperrter_name_auch_beim_bauen_abgelehnt(self):
        with self.assertRaises(ValueError):
            arbeiter.umgebung(self.p, self.basis, werkzeuge={"variablen": ["GITHUB_TOKEN"]})


class Einstellung(unittest.TestCase):
    def setUp(self):
        self.o = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.o.cleanup)
        self.pfad = os.path.join(self.o.name, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad, "LOCALAPPDATA": os.path.join(self.o.name, "lad")})
        u.start()
        self.addCleanup(u.stop)
        os.environ.pop("AMW_AGENT", None)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
            self.pid2 = db.einfuegen(self.con, "projekt", name="Anderes", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")

    def test_setzen_und_lesen(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", arbeiter_umgebung=json.dumps({"variablen": ["JAVA_HOME"], "pfade": [SDK]}))
        self.assertEqual(arbeiter.projekt_werkzeuge(self.con, self.pid), {"variablen": ["JAVA_HOME"], "pfade": [SDK]})
        self.assertEqual(arbeiter.projekt_werkzeuge(self.con, self.pid2), {})
        with self.assertRaises(kern.AmwFehler) as f:
            kern.projekt_einstellen(self.con, self.pid, "TL", arbeiter_umgebung='{"variablen": ["NPM_TOKEN"]}')
        self.assertIn("NPM_TOKEN nicht erlaubt", str(f.exception))
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "CC1", arbeiter_umgebung='{"variablen": ["JAVA_HOME"]}')   # nur Lead/Mensch
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, arbeiter_umgebung="")             # leer = Grundumgebung
        self.assertEqual(arbeiter.projekt_werkzeuge(self.con, self.pid), {})

    def test_von_hand_geaendert_gilt_nicht(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?",
                             (json.dumps({"arbeiter_umgebung": {"variablen": ["JAVA_HOME", "GITHUB_TOKEN"]}}), self.pid))
        self.assertEqual(arbeiter.projekt_werkzeuge(self.con, self.pid), {})

    def test_nicht_aus_einer_agenten_sitzung(self):
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_AGENT": "", "CLAUDECODE": "1", "CLAUDE_CODE_MESSAGING_SOCKET": ""}), \
                contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "Spiel", "--von", "Entwickler", "projekt", "einstellen", 'arbeiter_umgebung={"variablen": ["JAVA_HOME"]}'])
        self.assertNotEqual(rc, 0)
        self.assertIn("nicht aus einer Agenten-Sitzung", aus.getvalue())
        self.assertEqual(arbeiter.projekt_werkzeuge(self.con, self.pid), {})


if __name__ == "__main__":
    unittest.main()
