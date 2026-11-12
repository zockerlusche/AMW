"""Eigener Online-Speicher (Stufe R3a): libSQL-Server (sqld) im Firmennetz statt Turso.

- Adressen: Turso wie bisher; eigener Server https://name[:port], http:// nur im Firmennetz.
- Schlüssel: Ed25519 über cryptography oder openssl, Token prüfbar mit dem öffentlichen Schlüssel; ohne beides eine klare
  Meldung. `amw speicher schluessel` trägt den Zugang ein und schreibt nur den öffentlichen Schlüssel als Datei.
- Mit echtem sqld (nur wenn AMW_SQLD auf die Linux-Datei sqld zeigt; gestartet in WSL): PC-Abgleich, Einstellen am PC
  und die PHP-Seite (`speicher_url`) sprechen mit dem Server; falscher Schlüssel → 401.
"""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import base64
import contextlib
import io
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from amw import abgleich, aktionen, cli, kern, schluessel

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHP = shutil.which("php")
SQLD = os.environ.get("AMW_SQLD", "")
try:
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
except ImportError:
    load_pem_public_key = None


def b64_roh(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def lesen(pfad):
    with open(pfad, encoding="utf-8") as f:
        return json.load(f)


def gueltig(pem, token):
    kopf, rumpf, sig = token.split(".")
    load_pem_public_key(pem.encode()).verify(b64_roh(sig), f"{kopf}.{rumpf}".encode())     # wirft, wenn falsch
    return json.loads(b64_roh(kopf)), json.loads(b64_roh(rumpf))


class Adressen(unittest.TestCase):
    def test_turso_und_eigener_server(self):
        self.assertEqual(abgleich.speicher_adresse("turso", "libsql://x-y.turso.io/"), "libsql://x-y.turso.io")
        with self.assertRaises(ValueError):
            abgleich.speicher_adresse("turso", "https://amw-db.firma.lan")
        self.assertEqual(abgleich.speicher_adresse("libsql", "https://amw-db.firma.lan:8443/"), "https://amw-db.firma.lan:8443")
        self.assertEqual(abgleich.speicher_adresse("libsql", "libsql://amw-db.firma.lan"), "https://amw-db.firma.lan")
        self.assertEqual(abgleich.speicher_adresse("libsql", "http://192.168.1.5:8080"), "http://192.168.1.5:8080")
        self.assertEqual(abgleich.speicher_adresse("libsql", "http://amw-db.firma.lan"), "http://amw-db.firma.lan")   # Name im Firmennetz
        for falsch in ("http://93.184.216.34:8080", "https://a.lan/pfad", "https://nutzer:pw@a.lan", "ftp://a.lan", "a.lan"):
            with self.subTest(falsch=falsch), self.assertRaises(ValueError):
                abgleich.speicher_adresse("libsql", falsch)

    def test_einstellen_prueft_vor_dem_speichern(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"LOCALAPPDATA": d}):
            with self.assertRaises(aktionen.Ungueltig) as f:
                aktionen.turso_einstellen({"art": "libsql", "url": "http://93.184.216.34", "token": "x"})
            self.assertIn("http:// nur im Firmennetz", str(f.exception))
            with self.assertRaises(aktionen.Ungueltig):
                aktionen.turso_einstellen({"art": "libsql", "url": "https://a.lan", "token": "x", "ca": os.path.join(d, "fehlt.pem")})
            self.assertFalse(os.path.exists(abgleich.zugang_pfad()))                 # nichts gespeichert


@unittest.skipUnless(load_pem_public_key, "cryptography fehlt")
class Schluessel(unittest.TestCase):
    def test_mit_cryptography(self):
        pem, token = schluessel.erzeugen(("pc", "seite"), weg="cryptography")
        self.assertIn("BEGIN PUBLIC KEY", pem)
        self.assertNotIn("PRIVATE", pem)
        kopf, rumpf = gueltig(pem, token["seite"])
        self.assertEqual((kopf["alg"], rumpf["a"], rumpf["amw"]), ("EdDSA", "rw", "seite"))
        self.assertNotIn("id", rumpf)                         # „id“ wählt beim Server die Datenbank (404)
        self.assertNotEqual(token["pc"], token["seite"])

    @unittest.skipUnless(schluessel.openssl_pfad(), "openssl fehlt")
    def test_mit_openssl(self):
        pem, token = schluessel.erzeugen(("pc",), weg="openssl")
        self.assertEqual(gueltig(pem, token["pc"])[1]["a"], "rw")

    def test_ohne_beides_klare_meldung(self):
        with mock.patch.object(schluessel, "_mit_cryptography", side_effect=ImportError), \
             mock.patch.object(schluessel, "openssl_pfad", return_value=None):
            with self.assertRaises(kern.AmwFehler) as f:
                schluessel.erzeugen()
        self.assertIn("cryptography", str(f.exception))
        self.assertIn("openssl", str(f.exception))

    def test_befehl_traegt_zugang_ein_und_schreibt_nur_den_oeffentlichen(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"LOCALAPPDATA": d}):
            aus = io.StringIO()
            with contextlib.redirect_stdout(aus):
                self.assertEqual(cli.main(["speicher", "schluessel", "--url", "https://amw-db.firma.lan"]), 0)
            z = lesen(abgleich.zugang_pfad())
            self.assertEqual((z["art"], z["url"], z["abgleich"]), ("libsql", "https://amw-db.firma.lan", False))
            with open(os.path.join(d, "amw", "amw-speicher-oeffentlich.pem"), encoding="ascii") as f:
                pem = f.read()
            gueltig(pem, z["token"])
            zeilen = aus.getvalue().splitlines()
            seite = zeilen[next(i for i, x in enumerate(zeilen) if x.startswith("Schlüssel für die Online-Seite")) + 1].strip()
            self.assertEqual(gueltig(pem, seite)[1]["amw"], "seite")
            self.assertEqual(sorted(os.listdir(os.path.join(d, "amw"))), ["amw-speicher-oeffentlich.pem", "turso.json"])
            with contextlib.redirect_stderr(io.StringIO()) as fehler:                                    # zweites Mal nur mit --ersetzen
                self.assertEqual(cli.main(["speicher", "schluessel", "--url", "https://b.lan"]), 1)
            self.assertIn("--ersetzen", fehler.getvalue())
            self.assertEqual(lesen(abgleich.zugang_pfad())["url"], "https://amw-db.firma.lan")


def sqld_starten(pub, port, protokoll):
    """sqld in WSL mit dem öffentlichen Schlüssel pub (Windows-Pfad) auf port; Rückgabe für sqld_stoppen."""
    wsl = lambda p: "/mnt/" + p[0].lower() + p[2:].replace("\\", "/")
    db = f"/tmp/amw-test-{os.getpid()}-{port}.sqld"
    log = open(protokoll, "w")                                                              # bei Fehlern hilfreich
    srv = subprocess.Popen(["wsl.exe", "-d", os.environ.get("AMW_WSL", "Ubuntu"), "--", "timeout", "600", wsl(SQLD),
                            "--db-path", db, "--http-listen-addr", f"0.0.0.0:{port}", "--auth-jwt-key-file", wsl(pub)],
                           stdout=log, stderr=subprocess.STDOUT)
    return srv, db, log


def sqld_stoppen(laufend):
    srv, db, log = laufend
    subprocess.run(["wsl.exe", "-d", os.environ.get("AMW_WSL", "Ubuntu"), "--", "pkill", "-f", db], timeout=30)
    srv.wait(30)
    log.close()
    subprocess.run(["wsl.exe", "-d", os.environ.get("AMW_WSL", "Ubuntu"), "--", "rm", "-rf", db], timeout=30)


@unittest.skipUnless(SQLD and load_pem_public_key and shutil.which("wsl.exe"), "AMW_SQLD (Linux-Datei sqld) und WSL nötig")
class EchterServer(unittest.TestCase):
    """sqld 0.24.x in WSL-Ubuntu mit JWT-Prüfung – das echte Gegenstück zu Turso."""
    @classmethod
    def setUpClass(cls):
        cls.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.pem, cls.token = schluessel.erzeugen(("pc", "seite"))
        pub = os.path.join(cls.ordner.name, "pub.pem")
        with open(pub, "w", encoding="ascii", newline="\n") as f:
            f.write(cls.pem)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            cls.port = s.getsockname()[1]
        cls.laufend = sqld_starten(pub, cls.port, os.path.join(cls.ordner.name, "sqld.log"))
        cls.url = f"http://127.0.0.1:{cls.port}"
        for _ in range(120):
            try:
                abgleich.TursoSpeicher(cls.url, cls.token["pc"]).ausfuehren([("SELECT 1", [])])
                break
            except OSError:
                time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        sqld_stoppen(cls.laufend)
        cls.ordner.cleanup()

    def test_pc_einstellen_und_seite(self):
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": self.ordner.name}):
            r = aktionen.turso_einstellen({"art": "libsql", "url": self.url, "token": self.token["pc"], "abgleich": True})
            self.assertEqual((r["art"], r["schluessel_gespeichert"]), ("libsql", True))
            sp = abgleich.speicher_aus_zugang()
        self.assertTrue({"ansicht", "eingang", "benutzer"} <= {z[0] for z in sp.ausfuehren([("SELECT name FROM sqlite_master", [])])[0]})
        sp.ausfuehren([("INSERT INTO zustand (schluessel, wert) VALUES ('vom_pc', 'hallo') ON CONFLICT(schluessel) DO UPDATE SET wert = excluded.wert", [])])
        with self.assertRaises(OSError) as f:
            abgleich.TursoSpeicher(self.url, schluessel.erzeugen(("x",))[1]["x"]).ausfuehren([("SELECT 1", [])])
        self.assertIn("401", str(f.exception))
        if not PHP:
            self.skipTest("PHP fehlt")
        for token, erwartet in ((self.token["seite"], "hallo"), ("falsch", "401")):
            konfig = os.path.join(self.ordner.name, "amw-konfig.php")
            with open(konfig, "w", encoding="utf-8") as f:
                f.write(f"<?php return ['speicher_url' => '{self.url}', 'speicher_token' => '{token}', 'benutzer' => 'chef', 'passwort_hash' => 'x'];\n")
            probe = os.path.join(self.ordner.name, "probe.php")
            with open(probe, "w", encoding="utf-8") as f:
                f.write("<?php require getenv('AMW_LIB'); try { echo zustand_lesen('vom_pc'); } catch (RuntimeException $e) { echo $e->getCode(); }\n")
            r = subprocess.run([PHP, "-d", "extension=curl", "-d", "extension=openssl", "-d", "extension=mbstring", probe], capture_output=True,
                               text=True, timeout=60, env={**os.environ, "AMW_KONFIG": konfig,
                                                           "AMW_LIB": os.path.join(WURZEL, "web", "inc", "lib.php").replace(os.sep, "/")})
            self.assertEqual(r.stdout.strip(), erwartet, r.stderr)


if __name__ == "__main__":
    unittest.main()
