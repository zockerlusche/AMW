"""Eigener Server im Firmennetz, Stufe R3b: `amw web paket` und http im Firmennetz.

- Passwort-Hash SHA-512-crypt: Prüfwerte aus der Beschreibung, PHP password_verify() nimmt ihn an.
- Paket für https: alle Teile da, keine offenen Platzhalter, Konfiguration ist gültiges PHP mit Speicher, Schlüssel der
  Seite (passt zum öffentlichen Schlüssel im Paket), Admin und nur_https; .htaccess unverändert; Zugang am PC eingetragen
  (Synchronisierung aus), Adresse der Seite eingetragen; zweites Mal nur mit --ersetzen.
- Paket für http im Firmennetz: .htaccess ohne Umleitung auf https, nur_https aus, Vorlagen ohne TLS; im Internet abgelehnt.
- Online-Seite über http (php -S, Name im Firmennetz): Warnung auf der Anmeldeseite; über 127.0.0.1 keine.
- Benachrichtigungen und „Online-Seite testen“: http:// nur im Firmennetz.
- Mit echtem sqld (AMW_SQLD, WSL): Paket bauen, Server mit dem Schlüssel aus dem Paket starten, Seite aus dem Paket mit
  dessen Konfiguration → der Admin meldet sich an und bekommt den QR-Code für den zweiten Faktor (falsches Passwort nicht).
"""
import contextlib
import http.cookiejar
import io
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.parse
import urllib.request
import zipfile
from unittest import mock

from amw import abgleich, cli, kern, paket, push, verbindung
from tests.test_speicher_eigen import SQLD, gueltig, lesen, load_pem_public_key, sqld_starten, sqld_stoppen

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHP = shutil.which("php")
PHP_ERW = ["-d", "extension=pdo_sqlite", "-d", "extension=mbstring", "-d", "extension=curl", "-d", "extension=openssl"]


def freier_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def php_server(ordner, web, konfig, sitzungen):
    port = freier_port()
    p = subprocess.Popen([PHP, *PHP_ERW, "-d", f"session.save_path={sitzungen}", "-S", f"127.0.0.1:{port}", "-t", web],
                         env={**os.environ, "AMW_KONFIG": konfig}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    return p, port


class Hash(unittest.TestCase):
    def test_pruefwerte_der_beschreibung(self):
        self.assertEqual(paket.sha512_crypt("Hello world!", "saltstring", 5000, runden_angeben=False),
                         "$6$saltstring$svn8UoSVapNtMuq1ukKS4tPQd8iKwSMHWjl/O817G3uBnIFNjnQJuesI68u4OTLiBFdcbYEdFCoEOfaS35inz1")
        self.assertEqual(paket.sha512_crypt("Hello world!", "saltstringsaltstring", 10000),
                         "$6$rounds=10000$saltstringsaltst$OW1/O6BYHV6BcXZu8QVeXbDWra3Oeqh0sbHbbMCVNSnCM/UrjmM0Dp8vOuZeHBy/YTBmSK6H9qs/y3RnOaw5v.")
        lang = "x" * 70                                                   # Passwort länger als ein Block
        self.assertNotEqual(paket.sha512_crypt(lang, "a" * 16, 1000), paket.sha512_crypt(lang + "y", "a" * 16, 1000))

    @unittest.skipUnless(PHP, "PHP fehlt")
    def test_php_nimmt_ihn_an(self):
        h = paket.sha512_crypt("Ein Passwort mit Ümlaut 1")
        self.assertTrue(h.startswith("$6$rounds=200000$"))
        with tempfile.TemporaryDirectory() as d:
            probe = os.path.join(d, "p.php")
            with open(probe, "w", encoding="utf-8") as f:
                f.write("<?php $h = file_get_contents(getenv('H')); echo (int)password_verify('Ein Passwort mit Ümlaut 1', $h),"
                        " (int)password_verify('Ein Passwort mit Umlaut 1', $h);\n")
            with open(os.path.join(d, "h.txt"), "w", encoding="ascii") as f:
                f.write(h)
            r = subprocess.run([PHP, probe], capture_output=True, text=True, timeout=60, env={**os.environ, "H": os.path.join(d, "h.txt")})
        self.assertEqual(r.stdout.strip(), "10", r.stderr)


class Adressen(unittest.TestCase):
    def test_seite(self):
        self.assertEqual(paket.seiten_adresse("https://amw.firma.lan/"), "https://amw.firma.lan")
        self.assertEqual(paket.seiten_adresse("http://192.168.1.10:8080"), "http://192.168.1.10:8080")
        for falsch in ("http://93.184.216.34", "https://amw.firma.lan/amw", "ftp://amw.lan", "amw.lan", "https://a:b@amw.lan"):
            with self.subTest(falsch=falsch), self.assertRaises(ValueError):
                paket.seiten_adresse(falsch)

    def test_benachrichtigung_und_link_http_nur_im_firmennetz(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"LOCALAPPDATA": d}):
            push.speichern({"ntfy": {"server": "http://ntfy.firma.lan"}, "link": "http://192.168.1.10"})
            self.assertEqual((push.laden()["ntfy"]["server"], push.laden()["link"]), ("http://ntfy.firma.lan", "http://192.168.1.10"))
            for falsch in ({"ntfy": {"server": "http://93.184.216.34"}}, {"link": "http://93.184.216.34"}):
                with self.subTest(falsch=falsch), self.assertRaises(ValueError):
                    push.speichern(falsch)

    def test_seite_pruefen_ueber_http(self):
        holen = lambda adresse: (200, '{"titel": "x"}')
        r = verbindung.seite("http://192.168.1.10", holen=holen, version=lambda: None)
        self.assertTrue(r["ok"])
        self.assertEqual(r["schritte"][0]["name"], "http")
        r = verbindung.seite("http://93.184.216.34", holen=holen, version=lambda: None)
        self.assertEqual((r["ok"], r["schritte"][0]["name"]), (False, "https"))


class Paket(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.d.cleanup)
        u = mock.patch.dict(os.environ, {"LOCALAPPDATA": self.d.name})
        u.start()
        self.addCleanup(u.stop)

    def bauen(self, *mehr, ziel="p.zip"):
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus):
            rc = cli._web_paket(cli_args(*mehr, ziel=os.path.join(self.d.name, ziel)))
        self.assertEqual(rc, 0)
        return zipfile.ZipFile(os.path.join(self.d.name, ziel)), aus.getvalue()

    def konfig(self, z):
        """Konfiguration aus dem Paket, von PHP ausgewertet."""
        pfad = os.path.join(self.d.name, "k.php")
        with open(pfad, "wb") as f:
            f.write(z.read("amw-paket/konfig/amw-konfig.php"))
        r = subprocess.run([PHP, "-r", "echo json_encode(require getenv('K'));"], capture_output=True, text=True, timeout=60,
                           env={**os.environ, "K": pfad})
        import json
        return json.loads(r.stdout)

    @unittest.skipUnless(PHP and load_pem_public_key, "PHP oder cryptography fehlt")
    def test_https(self):
        z, aus = self.bauen("--seite", "https://amw.firma.lan", "--speicher", "https://amw-db.firma.lan", "--admin", "chef")
        namen = set(z.namelist())
        for n in ("LIESMICH.txt", "web/index.php", "web/api.php", "web/sso.php", "web/.htaccess", "web/inc/lib.php", "web/inc/seite.html",
                  "konfig/amw-konfig.php", "speicher/amw-speicher-oeffentlich.pem", "speicher/docker-compose.yml",
                  "webserver/nginx-amw.conf", "webserver/apache-amw.conf", "beispiel/docker-compose-alles.yml", "beispiel/nginx-docker.conf"):
            self.assertIn("amw-paket/" + n, namen)
        self.assertFalse([n for n in namen if "amw-konfig" in n and not n.startswith("amw-paket/konfig/")])
        for n in namen:
            if n.endswith((".txt", ".conf", ".yml")):
                self.assertNotIn("{{", z.read(n).decode("utf-8"), n)
        with open(os.path.join(WURZEL, "web", ".htaccess"), "rb") as f:
            self.assertEqual(z.read("amw-paket/web/.htaccess"), f.read())
        k = self.konfig(z)
        self.assertEqual((k["benutzer"], k["nur_https"], k["speicher_url"]), ("chef", True, "https://amw-db.firma.lan"))
        self.assertNotIn("speicher_ca", k)
        self.assertIn("Die ZIP ist ein Geheimnis", aus)                          # Pflicht-Hinweis (TL)
        self.assertIn("DIESE ZIP IST EIN GEHEIMNIS", z.read("amw-paket/LIESMICH.txt").decode("utf-8"))
        with open(os.path.join(WURZEL, "amw", "workbench.html"), encoding="utf-8") as f:   # Knöpfe so, wie sie in der Workbench heißen
            knoepfe = re.findall(r'pv_(?:speicher|seite): "([^"]+)"', f.read())
        self.assertEqual(knoepfe, ["Verbindung testen", "Online-Seite testen", "Test connection", "Test online page"])
        liesmich = z.read("amw-paket/LIESMICH.txt").decode("utf-8")
        for knopf in knoepfe:
            self.assertIn(knopf, liesmich)
        self.assertIn("„Verbindung testen“", aus)
        self.assertNotIn("prüfen“", liesmich + aus)
        pem = z.read("amw-paket/speicher/amw-speicher-oeffentlich.pem").decode()
        self.assertEqual(gueltig(pem, k["speicher_token"])[1]["amw"], "seite")
        passwort = re.search(r"Passwort – nur jetzt sichtbar: (\S+)", aus).group(1)
        self.assertEqual(paket.sha512_crypt(passwort, k["passwort_hash"].split("$")[3]), k["passwort_hash"])
        zg = lesen(abgleich.zugang_pfad())
        self.assertEqual((zg["art"], zg["url"], zg["abgleich"]), ("libsql", "https://amw-db.firma.lan", False))
        gueltig(pem, zg["token"])
        self.assertEqual(push.laden()["link"], "https://amw.firma.lan")
        nginx = z.read("amw-paket/webserver/nginx-amw.conf").decode()
        self.assertIn("listen 443 ssl;", nginx)
        self.assertIn("server_name amw-db.firma.lan;", nginx)                   # https vor dem Speicher
        self.assertIn('"127.0.0.1:8080:8080"', z.read("amw-paket/speicher/docker-compose.yml").decode())
        self.assertEqual(z.getinfo("amw-paket/konfig/amw-konfig.php").external_attr >> 16, 0o600)
        with self.assertRaises(kern.AmwFehler) as f:                             # zweites Mal nur mit --ersetzen
            self.bauen("--seite", "https://amw.firma.lan", "--speicher", "https://b.firma.lan", ziel="q.zip")
        self.assertIn("--ersetzen", str(f.exception))
        self.assertFalse(os.path.exists(os.path.join(self.d.name, "q.zip")))
        z2, _ = self.bauen("--seite", "https://amw.firma.lan", "--speicher", "https://b.firma.lan", "--ersetzen", ziel="q.zip")
        self.assertEqual(lesen(abgleich.zugang_pfad())["url"], "https://b.firma.lan")

    @unittest.skipUnless(PHP, "PHP fehlt")
    def test_http_im_firmennetz_und_mit_ca(self):
        ca = os.path.join(self.d.name, "firma.pem")
        with open(ca, "w", encoding="ascii") as f:
            f.write("-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n")
        z, aus = self.bauen("--seite", "http://192.168.1.10", "--speicher", "http://192.168.1.11:8080", "--ca", ca)
        self.assertIn("unverschlüsselt", aus)
        ht = z.read("amw-paket/web/.htaccess").decode()
        self.assertNotIn("RewriteRule ^ https://", ht)
        self.assertIn("RewriteRule ^ - [F,L]", ht)                               # die Sperren bleiben
        k = self.konfig(z)
        self.assertFalse(k["nur_https"])
        self.assertTrue(k["speicher_ca"].replace("\\", "/").endswith("/amw-firmen-ca.pem"))
        self.assertIn("amw-paket/konfig/amw-firmen-ca.pem", z.namelist())
        nginx = z.read("amw-paket/webserver/nginx-amw.conf").decode()
        self.assertIn("listen 80;", nginx)
        self.assertNotIn("/etc/ssl/firma", nginx)
        self.assertIn("<VirtualHost *:80>", z.read("amw-paket/webserver/apache-amw.conf").decode())
        self.assertIn('"8080:8080"', z.read("amw-paket/speicher/docker-compose.yml").decode())
        self.assertEqual(lesen(abgleich.zugang_pfad())["ca"], os.path.abspath(ca))

    def test_abgelehnt(self):
        for mehr, wort in ((["--seite", "http://93.184.216.34", "--speicher", "https://a.lan"], "Firmennetz"),
                           (["--seite", "https://a.lan", "--speicher", "http://93.184.216.34"], "Firmennetz"),
                           (["--seite", "https://a.lan", "--speicher", "https://b.lan", "--admin", "ich du"], "--admin"),
                           (["--seite", "https://a.lan", "--speicher", "https://b.lan", "--ca", "fehlt.pem"], "Zertifikat")):
            with self.subTest(mehr=mehr), self.assertRaises(kern.AmwFehler) as f:
                self.bauen(*mehr)
            self.assertIn(wort, str(f.exception))
        self.assertFalse(os.path.exists(abgleich.zugang_pfad()))
        self.assertFalse(os.path.exists(os.path.join(self.d.name, "p.zip")))


def cli_args(*mehr, ziel):
    """Argumente wie von der Befehlszeile (amw web paket …)."""
    return cli.parser().parse_args(["web", "paket", *mehr, "--ziel", ziel])


@unittest.skipUnless(PHP, "PHP fehlt")
class WarnungBeiHttp(unittest.TestCase):
    def test_anmeldeseite(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            online = os.path.join(d, "online.db")
            sp = abgleich.SqliteSpeicher(online)
            sp.ausfuehren([(s, []) for s in abgleich.SCHEMA])
            konfig = os.path.join(d, "amw-konfig.php")
            with open(konfig, "w", encoding="utf-8") as f:
                f.write(f"<?php return ['sqlite' => '{online.replace(os.sep, '/')}', 'benutzer' => 'chef', 'passwort_hash' => 'x', 'nur_https' => false];\n")
            srv, port = php_server(d, os.path.join(WURZEL, "web"), konfig, d)
            try:
                for host, warnt in (("amw.firma.lan", True), (f"127.0.0.1:{port}", False)):
                    r = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/", headers={"Host": host}), timeout=30)
                    text = r.read().decode("utf-8")
                    self.assertIn('name="passwort"', text)
                    self.assertEqual('id="http-warnung"' in text, warnt, host)
                with open(konfig, "w", encoding="utf-8") as f:                 # nur_https (Vorgabe): Umleitung statt Warnung
                    f.write(f"<?php return ['sqlite' => '{online.replace(os.sep, '/')}', 'benutzer' => 'chef', 'passwort_hash' => 'x'];\n")
                class Halt(urllib.request.HTTPRedirectHandler):
                    def redirect_request(self, *a, **k):
                        return None
                with self.assertRaises(urllib.error.HTTPError) as f:
                    urllib.request.build_opener(Halt()).open(urllib.request.Request(f"http://127.0.0.1:{port}/", headers={"Host": "amw.firma.lan"}), timeout=30)
                self.assertEqual((f.exception.code, f.exception.headers["Location"]), (301, "https://amw.firma.lan/"))
            finally:
                srv.terminate()
                srv.wait(10)


@unittest.skipUnless(SQLD and PHP and load_pem_public_key and shutil.which("wsl.exe"), "AMW_SQLD (Linux-Datei sqld), PHP und WSL nötig")
class PaketMitEchtemServer(unittest.TestCase):
    def test_admin_meldet_sich_an(self):
        d = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(d.cleanup)
        port = freier_port()
        url = f"http://127.0.0.1:{port}"
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": d.name}):
            aus = io.StringIO()
            with contextlib.redirect_stdout(aus):
                cli._web_paket(cli_args("--seite", "https://amw.firma.lan", "--speicher", url, "--admin", "chef",
                                        ziel=os.path.join(d.name, "p.zip")))
            passwort = re.search(r"Passwort – nur jetzt sichtbar: (\S+)", aus.getvalue()).group(1)
            zipfile.ZipFile(os.path.join(d.name, "p.zip")).extractall(d.name)
            p = os.path.join(d.name, "amw-paket")
            laufend = sqld_starten(os.path.join(p, "speicher", "amw-speicher-oeffentlich.pem"), port, os.path.join(d.name, "sqld.log"))
            self.addCleanup(sqld_stoppen, laufend)
            zg = lesen(abgleich.zugang_pfad())
            sp = abgleich.TursoSpeicher(zg["url"], zg["token"])
            for _ in range(120):
                try:
                    sp.ausfuehren([("SELECT 1", [])])
                    break
                except OSError:
                    time.sleep(0.5)
            sp.ausfuehren([(s, []) for s in abgleich.SCHEMA])                       # wie „Verbindung testen“ am PC
        sitzungen = os.path.join(d.name, "s")
        os.makedirs(sitzungen)
        php, wport = php_server(d.name, os.path.join(p, "web"), os.path.join(p, "konfig", "amw-konfig.php"), sitzungen)
        self.addCleanup(lambda: (php.terminate(), php.wait(10)))
        def anmelden(pw):
            oeffner = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            text = oeffner.open(f"http://127.0.0.1:{wport}/", timeout=30).read().decode("utf-8")
            csrf = text.split('name="csrf" value="')[1].split('"')[0]
            daten = urllib.parse.urlencode({"csrf": csrf, "benutzer": "chef", "passwort": pw, "code": ""}).encode()
            return oeffner.open(f"http://127.0.0.1:{wport}/", data=daten, timeout=60).read().decode("utf-8")
        self.assertNotIn('value="einrichten"', anmelden(passwort + "x"))            # falsches Passwort
        text = anmelden(passwort)                                                   # erstes Anmelden: zweiten Faktor einrichten
        self.assertIn('name="schritt" value="einrichten"', text)
        self.assertIn('aria-label="QR-Code"', text)


if __name__ == "__main__":
    unittest.main()
