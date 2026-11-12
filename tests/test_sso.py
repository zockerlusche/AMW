"""Firmen-Anmeldung (Stufe R2, OpenID Connect) – die echte Online-Seite (php -S) gegen einen nachgestellten Anbieter
(tests/oidc_attrappe.py, wie Microsoft Entra ID), ohne echtes Konto. Abgedeckt: ganzer Ablauf mit PKCE, state und nonce;
Signatur, Aussteller, Empfänger, Ablauf; nur angelegte Benutzer; Bindung an das Firmenkonto beim ersten Mal und was sie
löst (neue E-Mail, neu freischalten); gesperrt; ohne Rolle „Zugang wird geprüft“ und Meldung an den Admin; Geheimnis
oder Zertifikat nur in der Konfiguration beim Webhoster; Einstellungen am PC."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import http.cookiejar
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

from amw import abgleich, aktionen, benutzer, db, kern

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHP = shutil.which("php")
try:
    from tests import oidc_attrappe
except ImportError:                                  # ohne cryptography: Tests überspringen
    oidc_attrappe = None


class OhneWeiterleitung(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def freier_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@unittest.skipUnless(PHP and oidc_attrappe, "PHP oder cryptography fehlt")
class Firmenanmeldung(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.online = os.path.join(cls.ordner.name, "online.db")
        cls.konfig = os.path.join(cls.ordner.name, "amw-konfig.php")
        cls.port = freier_port()
        env = {**os.environ, "AMW_KONFIG": cls.konfig}
        cls.php_server = subprocess.Popen([PHP, "-d", "extension=pdo_sqlite", "-d", "extension=mbstring", "-d", "extension=curl",
                                           "-d", "extension=openssl", "-d", f"session.save_path={cls.ordner.name}",
                                           "-S", f"127.0.0.1:{cls.port}", "-t", os.path.join(WURZEL, "web")],
                                          env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", cls.port), 0.2).close()
                break
            except OSError:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.php_server.terminate()
        cls.php_server.wait(10)
        cls.ordner.cleanup()

    def setUp(self):
        for p in (self.online, os.path.join(self.ordner.name, "amw.db")):
            if os.path.exists(p):
                os.remove(p)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        self.sp = abgleich.SqliteSpeicher(self.online)
        self.sp.ausfuehren([(s, []) for s in abgleich.SCHEMA])
        abgleich.nachruesten(self.sp)
        self.anbieter = oidc_attrappe.Anbieter()
        self.addCleanup(self.anbieter.stop)
        self.konfig_schreiben(sso_geheimnis=self.anbieter.geheimnis)
        abgleich.sso_setzen(self.sp, {"an": True, "aussteller": "https://platzhalter.example/v2.0", "client_id": "amw-test"})
        self.aussteller_setzen()
        benutzer.neu(self.con, kern.ENTWICKLER, "marie", "bearbeiter", email="marie@firma.example", projekte=[self.pid])
        self.hochladen()

    # --- Helfer ------------------------------------------------------------------------------------------------

    def konfig_schreiben(self, **mehr):
        d = {"sqlite": self.online.replace(os.sep, "/"), "benutzer": "chef",
             "passwort_hash": "$2y$10$abcdefghijklmnopqrstuuJ6p3Q9J0wHk1x8Z2b4c6d8e0f2g4h6i", **mehr}
        php = "<?php return " + json.dumps(d).replace("{", "[").replace("}", "]").replace('":', '" =>') + ";\n"
        with open(self.konfig, "w", encoding="utf-8") as f:
            f.write(php.replace("$", "\\$"))

    def aussteller_setzen(self):
        """sso_setzen verlangt https; für die Probe am PC (http://127.0.0.1) direkt in den Speicher."""
        self.sp.ausfuehren([("UPDATE zustand SET wert = ? WHERE schluessel = 'sso'",
                             [json.dumps({"an": True, "aussteller": self.anbieter.aussteller, "client_id": "amw-test"})])])

    def hochladen(self):
        for b in benutzer.fuer_online(self.con):
            self.sp.ausfuehren([(benutzer.ONLINE_EINTRAGEN, [b["name"], b["anzeige"], b["email"], b["rolle"], b["gesperrt"], b["projekte"], db.jetzt()])])

    def browser(self):
        jar = http.cookiejar.CookieJar()
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), OhneWeiterleitung()), jar

    def holen(self, oeffner, url):
        try:
            r = oeffner.open(url, timeout=30)
            return r.status, r.headers, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read().decode("utf-8", "replace")

    def seite(self, pfad=""):
        return f"http://127.0.0.1:{self.port}/{pfad}"

    def anmelden(self, oeffner=None, aendern=None):
        """Ganzer Weg: Knopf → Anbieter → zurück → Workbench. Rückgabe (Status der Rückkehr, Text, Browser)."""
        oeffner = oeffner or self.browser()[0]
        code, kopf, _ = self.holen(oeffner, self.seite("sso.php"))
        self.assertEqual(code, 303, "Start leitet zum Anbieter")
        ziel = kopf["Location"]
        self.assertTrue(ziel.startswith(self.anbieter.aussteller.rsplit("/v2.0", 1)[0]), ziel)
        code, kopf, _ = self.holen(oeffner, ziel)                     # der Benutzer meldet sich beim Anbieter an
        self.assertEqual(code, 302)
        zurueck = kopf["Location"]
        if aendern:
            zurueck = aendern(zurueck)
        code, _, text = self.holen(oeffner, zurueck)
        return code, text, oeffner

    def zeile(self, name="marie"):
        z = self.sp.ausfuehren([("SELECT sso_kennung, sitzung_nr, angemeldet_utc, passwort_hash FROM benutzer WHERE name = ?", [name])])[0]
        return dict(zip(("sso_kennung", "sitzung_nr", "angemeldet_utc", "passwort_hash"), z[0])) if z else None

    def api(self, oeffner, weg="/api/start"):
        return self.holen(oeffner, self.seite("api.php?weg=" + urllib.parse.quote(weg)))

    # --- der normale Weg -----------------------------------------------------------------------------------------

    def test_ganzer_ablauf_mit_pkce_state_nonce(self):
        code, text, oeffner = self.anmelden()
        self.assertEqual(code, 200, text)
        self.assertIn('http-equiv="refresh"', text)                   # eigener Schritt: das Strict-Cookie kommt dann mit
        z = self.zeile()
        self.assertEqual(z["sso_kennung"], self.anbieter.aussteller + "|sub-marie")
        self.assertIsNone(z["passwort_hash"])
        start = [q for w, q in self.anbieter.anfragen if w.endswith("/authorize")][0]
        self.assertEqual((start["code_challenge_method"], start["scope"], start["response_mode"]), ("S256", "openid profile email", "query"))
        self.assertTrue(start["state"] and start["nonce"] and len(start["code_challenge"]) == 43)
        self.assertEqual(start["redirect_uri"], self.seite("sso.php"))
        token = [q for w, q in self.anbieter.anfragen if w.endswith("/token")][0]
        self.assertGreaterEqual(len(token["code_verifier"]), 43)
        code, _, text = self.api(oeffner)                              # angemeldet: die Seite antwortet (ohne Daten vom PC 404)
        self.assertNotEqual(code, 401, text)
        code, _, text = self.holen(oeffner, self.seite())
        self.assertNotIn('name="passwort"', text)                      # keine Anmeldeseite mehr

    def test_knopf_nur_wenn_eingeschaltet_und_geheimnis_da(self):
        oeffner = self.browser()[0]
        self.assertIn('href="sso.php"', self.holen(oeffner, self.seite())[2])
        self.konfig_schreiben()                                        # kein Geheimnis beim Webhoster
        self.assertNotIn('href="sso.php"', self.holen(self.browser()[0], self.seite())[2])
        self.konfig_schreiben(sso_geheimnis=self.anbieter.geheimnis)
        self.sp.ausfuehren([("UPDATE zustand SET wert = ? WHERE schluessel = 'sso'",
                             [json.dumps({"an": False, "aussteller": self.anbieter.aussteller, "client_id": "amw-test"})])])
        self.assertNotIn('href="sso.php"', self.holen(self.browser()[0], self.seite())[2])
        code, _, text = self.holen(self.browser()[0], self.seite("sso.php"))
        self.assertIn("nicht eingerichtet", text)

    def test_zweites_mal_ueber_die_kennung_auch_mit_neuer_email_beim_anbieter(self):
        self.assertEqual(self.anmelden()[0], 200)
        self.anbieter.benutzer["email"] = "marie.muster@firma.example"   # Namensänderung beim Anbieter, sub bleibt
        code, text, oeffner = self.anmelden()
        self.assertEqual(code, 200, text)
        self.assertNotEqual(self.api(oeffner)[0], 401)

    def test_entra_ohne_email_nimmt_preferred_username(self):
        self.anbieter.fehler["ohne_email"] = True
        self.anbieter.benutzer["preferred_username"] = "MARIE@firma.example"
        self.assertEqual(self.anmelden()[0], 200)

    def test_keycloak_mehrere_empfaenger_mit_azp(self):
        """Keycloak schickt aud als Liste (z. B. mit „account“) und azp = Client-ID – das gilt; ein fremdes azp nicht."""
        self.anbieter.fehler["aud"] = ["amw-test", "account"]
        self.anbieter.benutzer["azp"] = "amw-test"
        self.assertEqual(self.anmelden()[0], 200)
        self.anbieter.benutzer.update(azp="andere-app", sub="sub-x")
        self.assertIn("azp", self.anmelden()[1])

    def test_mit_zertifikat_statt_geheimnis(self):
        privat = oidc_attrappe.schluessel()
        zert, schl = oidc_attrappe.zertifikat(privat)
        self.anbieter.zert_pem = zert
        self.konfig_schreiben(sso_zertifikat=zert, sso_schluessel=schl)
        code, text, _ = self.anmelden()
        self.assertEqual(code, 200, text)
        token = [q for w, q in self.anbieter.anfragen if w.endswith("/token")][0]
        self.assertNotIn("client_secret", token)

    # --- wer nicht hineinkommt ------------------------------------------------------------------------------------

    def test_nicht_angelegt(self):
        self.anbieter.benutzer.update(sub="sub-fremd", email="fremd@firma.example")
        code, text, oeffner = self.anmelden()
        self.assertIn("fremd@firma.example", text)
        self.assertIn("nicht freigeschaltet", text)
        self.assertEqual(self.api(oeffner)[0], 401)
        self.assertEqual(self.sp.ausfuehren([("SELECT count(*) FROM versuch WHERE ok = 0", [])])[0][0][0], 1)   # zählt in die Sperre

    def test_gesperrt_und_sperren_beendet_die_sitzung(self):
        code, _, oeffner = self.anmelden()
        self.assertEqual(code, 200)
        benutzer.aendern(self.con, kern.ENTWICKLER, "marie", gesperrt=True)
        self.hochladen()
        self.assertEqual(self.api(oeffner)[0], 401)
        self.assertIn("nicht freigeschaltet oder gesperrt", self.anmelden()[1])

    def test_neue_email_am_pc_loest_die_bindung(self):
        code, _, oeffner = self.anmelden()
        self.assertEqual(code, 200)
        benutzer.aendern(self.con, kern.ENTWICKLER, "marie", email="marie.neu@firma.example")
        self.hochladen()
        self.assertIsNone(self.zeile()["sso_kennung"])
        self.assertEqual(self.api(oeffner)[0], 401)                    # Sitzung endet bei der nächsten Anfrage
        self.assertIn("nicht freigeschaltet", self.anmelden()[1])     # Konto meldet noch die alte Adresse
        self.anbieter.benutzer["email"] = "marie.neu@firma.example"
        self.assertEqual(self.anmelden()[0], 200)

    def test_neu_freischalten_loest_die_bindung(self):
        code, _, oeffner = self.anmelden()
        self.assertEqual(code, 200)
        benutzer.freischalten(self.con, kern.ENTWICKLER, "marie", self.sp)
        self.assertIsNone(self.zeile()["sso_kennung"])
        self.assertEqual(self.api(oeffner)[0], 401)

    def test_bindung_an_ein_konto_und_kein_zweites(self):
        self.assertEqual(self.anmelden()[0], 200)
        self.anbieter.benutzer.update(sub="sub-anderes-konto")          # anderes Konto, gleiche E-Mail
        self.assertIn("nicht freigeschaltet", self.anmelden()[1])

    def test_ohne_rolle_wartet_und_admin_bekommt_meldung(self):
        benutzer.neu(self.con, kern.ENTWICKLER, "tom", email="tom@firma.example")
        self.hochladen()
        self.anbieter.benutzer.update(sub="sub-tom", email="tom@firma.example")
        code, _, oeffner = self.anmelden()
        self.assertEqual(code, 200)
        text = self.holen(oeffner, self.seite())[2]
        self.assertIn("Dein Zugang wird geprüft", text)
        self.assertIn("Firmenkonto", text)
        self.assertEqual(self.api(oeffner)[0], 403)
        weg, daten = self.sp.ausfuehren([("SELECT weg, daten FROM eingang", [])])[0][0]
        self.assertEqual((weg, json.loads(daten)), ("/api/benutzer/eingerichtet", {"_benutzer": "tom", "weg": "firmenkonto"}))
        aktionen.ausfuehren(self.con, self.pid, weg, json.loads(daten), kanal="netz")      # so führt der PC es aus
        n = self.con.execute("SELECT kurz, text FROM nachricht WHERE von = 'AMW' ORDER BY id DESC").fetchone()
        self.assertIn("tom wartet auf Freigabe", n[0])
        self.assertIn("Firmenkonto (tom@firma.example)", n[1])
        self.assertEqual(self.anmelden()[0], 200)                       # zweites Mal: keine neue Meldung
        self.assertEqual(self.sp.ausfuehren([("SELECT count(*) FROM eingang", [])])[0][0][0], 1)

    # --- Prüfung des Tokens und des Ablaufs --------------------------------------------------------------------------

    def test_falsche_tokens(self):
        for fehler, erwartet in (({"fremd_signiert": True}, "Signatur"), ({"alg": "none"}, "nicht erlaubt"),
                                 ({"iss": "https://boese.example/v2.0"}, "Aussteller"), ({"aud": "andere-app"}, "nicht für diese Seite"),
                                 ({"exp": -3600}, "abgelaufen"), ({"nonce": "fremd"}, "nonce")):
            with self.subTest(fehler=fehler):
                self.anbieter.fehler = fehler
                code, text, oeffner = self.anmelden()
                self.assertIn(erwartet, text)
                self.assertEqual(self.api(oeffner)[0], 401)
                self.assertIsNone(self.zeile()["sso_kennung"])

    def test_falscher_state_anderer_browser_und_code_nur_einmal(self):
        code, text, _ = self.anmelden(aendern=lambda u: u.replace("state=", "state=x"))
        self.assertIn("gehört nicht zu dieser Anmeldung", text)
        oeffner, _ = self.browser()                                     # Antwort landet in einem anderen Browser (Login-CSRF)
        _, kopf, _ = self.holen(oeffner, self.seite("sso.php"))
        _, kopf, _ = self.holen(oeffner, kopf["Location"])
        code, _, text = self.holen(self.browser()[0], kopf["Location"])
        self.assertIn("anderen Browser", text)
        code, _, text = self.holen(oeffner, kopf["Location"])           # der echte Browser: Vorgang noch da, Code schon verbraucht?
        self.assertEqual(code, 200)                                     # nein – der fremde Browser kam nie bis zum Anbieter
        code, _, text = self.holen(oeffner, kopf["Location"])           # dieselbe Antwort noch einmal: Vorgang ist weg
        self.assertIn("anderen Browser", text)

    def test_anbieter_meldet_fehler_und_geheimnis_falsch(self):
        oeffner = self.browser()[0]
        self.holen(oeffner, self.seite("sso.php"))
        code, _, text = self.holen(oeffner, self.seite("sso.php?error=access_denied&error_description=AADSTS50105"))
        self.assertIn("access_denied AADSTS50105", text)
        self.konfig_schreiben(sso_geheimnis="falsches-geheimnis")
        self.assertIn("invalid_client", self.anmelden()[1])

    def test_aussteller_muss_stimmen_und_common_geht_nicht(self):
        self.anbieter.fehler["discovery_issuer"] = "https://login.microsoftonline.com/{tenantid}/v2.0"
        self.assertIn("Mandanten-ID", self.holen(self.browser()[0], self.seite("sso.php"))[2])
        self.anbieter.fehler["discovery_issuer"] = "https://anders.example/v2.0"
        self.assertIn("Aussteller passt nicht", self.holen(self.browser()[0], self.seite("sso.php"))[2])

    # --- Geheimnis eintragen (Online-Seite) und Einstellungen (PC) ------------------------------------------------------

    def test_geheimnis_nur_system_admin_und_nur_in_der_konfiguration(self):
        oeffner, _ = self.browser()
        self.assertIn("nur ein System-Admin", self.holen(oeffner, self.seite("sso.php?einrichten"))[2])
        self.assertEqual(self.anmelden(oeffner)[0], 200)                # marie ist Bearbeiterin
        self.assertIn("nur ein System-Admin", self.holen(oeffner, self.seite("sso.php?einrichten"))[2])
        benutzer.aendern(self.con, kern.ENTWICKLER, "marie", rolle="system_admin")
        self.hochladen()
        code, _, text = self.holen(oeffner, self.seite("sso.php?einrichten"))
        self.assertIn("erreichbar, Aussteller stimmt", text)
        self.assertIn("Geheimnis (Client-Secret)", text)
        self.assertNotIn(self.anbieter.geheimnis, text)                 # nie angezeigt
        csrf = text.split('name="csrf" value="')[1].split('"')[0]
        anfrage = urllib.request.Request(self.seite("sso.php?einrichten"), data=urllib.parse.urlencode(
            {"art": "geheimnis", "geheimnis": "neues-geheimnis-123456", "csrf": csrf}).encode(), method="POST")
        try:
            oeffner.open(anfrage, timeout=30)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 303)
        with open(self.konfig, encoding="utf-8") as f:
            self.assertIn("neues-geheimnis-123456", f.read())
        roh = b""
        for p in (self.online, os.path.join(self.ordner.name, "amw.db")):
            with open(p, "rb") as f:
                roh += f.read()
        self.assertNotIn(b"neues-geheimnis-123456", roh)
        self.assertNotIn(self.anbieter.geheimnis.encode(), roh)
        self.assertEqual(abgleich.sso_einstellungen(self.sp)["zugang"], "geheimnis")
        self.assertTrue(abgleich.sso_einstellungen(self.sp)["rueckweg"].endswith("/sso.php"))

    def test_einstellungen_am_pc(self):
        with self.assertRaises(ValueError):
            abgleich.sso_setzen(self.sp, {"aussteller": "http://login.example/v2.0"})        # nur https
        with self.assertRaises(ValueError):
            abgleich.sso_setzen(self.sp, {"aussteller": "https://login.microsoftonline.com/common/v2.0"})
        with self.assertRaises(ValueError):
            abgleich.sso_setzen(self.sp, {"an": True, "aussteller": "", "client_id": ""})
        d = abgleich.sso_setzen(self.sp, {"aussteller": "https://login.microsoftonline.com/1111-2222/v2.0/", "client_id": " abc "})
        self.assertEqual((d["aussteller"], d["client_id"]), ("https://login.microsoftonline.com/1111-2222/v2.0", "abc"))
        with self.assertRaises(aktionen.Ungueltig):
            aktionen.einstellen(self.con, self.pid, "sso", {"an": False}, "netz", self.sp)    # nicht von unterwegs
        self.assertFalse(aktionen.einstellen(self.con, self.pid, "sso", {"an": False}, "seite", self.sp)["sso"]["an"])
        with self.assertRaises(kern.AmwFehler):
            benutzer.neu(self.con, kern.ENTWICKLER, "zwilling", email="MARIE@firma.example")   # E-Mail nur einmal
        with self.assertRaises(kern.AmwFehler):
            benutzer.aendern(self.con, kern.ENTWICKLER, "marie", email="keine-mail")


if __name__ == "__main__":
    unittest.main()
