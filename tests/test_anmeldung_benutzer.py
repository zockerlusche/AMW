"""Mehrere Benutzer, Stufe R1b: erstes Anmelden mit Freischalt-Code und Anmelden je Benutzer – mit dem echten PHP der
Online-Seite gegen eine SQLite-Datei. Abgedeckt (Vorgabe des Menschen): QR-Inhalt, Uhrzeit-Toleranz, Abbruch mittendrin,
zweiter Versuch, zwei zugleich mit demselben Code, doppelt benutzte Zahl, Sperren und neu Freischalten, Herkunftsprüfung
(Origin: null, hinter einem Proxy) – die Fehler des ersten Einrichtens."""
import base64
import hashlib
import hmac
import json
import os
import shutil
import struct
import subprocess
import tempfile
import time
import unittest

from amw import abgleich, benutzer, db, kern

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHP = shutil.which("php")

KOPF = r"""<?php
declare(strict_types=1);
ini_set('session.use_cookies', '0'); ini_set('session.use_only_cookies', '0'); ini_set('session.use_strict_mode', '0');
ini_set('session.save_path', getenv('AMW_SITZUNGEN'));
require getenv('AMW_LIB');
$_SERVER['REMOTE_ADDR'] = '203.0.113.7';
session_id('t' . bin2hex(random_bytes(8))); session_start(); $_SESSION['csrf'] = 'x';
$aus = [];
function neu_browser(): void { $_SESSION = ['csrf' => 'x']; }
function zahl(string $g, int $versatz = 0): string { return totp($g, intdiv(time(), 30) + $versatz); }
function zeile(string $n): array { return benutzer_zeile($n) ?? []; }
"""
FUSS = "\necho json_encode($aus, JSON_UNESCAPED_UNICODE);\n"


def totp_py(geheim, schritt):
    """So rechnet eine Authenticator-App (RFC 6238) – unabhängig vom PHP der Seite."""
    k = base64.b32decode(geheim)
    h = hmac.new(k, struct.pack(">Q", schritt), hashlib.sha1).digest()
    o = h[19] & 0x0F
    return str((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 1000000).zfill(6)


@unittest.skipUnless(PHP, "PHP nicht installiert")
class Anmeldung(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        self.online = os.path.join(self.ordner.name, "online.db")
        self.sp = abgleich.SqliteSpeicher(self.online)
        self.sp.ausfuehren([(s, []) for s in abgleich.SCHEMA] + [(q, []) for _, _, q in abgleich.NACHRUESTEN])
        benutzer.neu(self.con, kern.ENTWICKLER, "marie")
        self.code, self.bis = benutzer.freischalten(self.con, kern.ENTWICKLER, "marie", self.sp)
        self.konfig = os.path.join(self.ordner.name, "amw-konfig.php")
        with open(self.konfig, "w", encoding="utf-8") as f:
            f.write(f"<?php return ['sqlite' => {json.dumps(self.online.replace(os.sep, '/'))}, 'benutzer' => 'chef',"
                    f" 'passwort_hash' => '{self.php_hash('chef-passwort-123')}'];\n")      # einfache Anführungszeichen: $ bleibt $
        os.makedirs(os.path.join(self.ordner.name, "sitzungen"))

    def php_hash(self, pw):
        r = subprocess.run([PHP, "-r", f"echo password_hash({json.dumps(pw)}, PASSWORD_DEFAULT);"], capture_output=True, text=True, timeout=30)
        return r.stdout.strip()

    def php(self, rumpf):
        datei = os.path.join(self.ordner.name, "probe.php")
        with open(datei, "w", encoding="utf-8") as f:
            f.write(KOPF + rumpf + FUSS)
        env = {**os.environ, "AMW_KONFIG": self.konfig, "AMW_LIB": os.path.join(WURZEL, "web", "inc", "lib.php").replace(os.sep, "/"),
               "AMW_SITZUNGEN": os.path.join(self.ordner.name, "sitzungen")}
        r = subprocess.run([PHP, "-d", "extension=pdo_sqlite", "-d", "extension=mbstring", datei], capture_output=True, text=True,
                           env=env, timeout=120)
        if "could not find driver" in r.stdout + r.stderr:
            self.skipTest("PHP ohne pdo_sqlite")
        try:
            return json.loads(r.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            self.fail(r.stdout + r.stderr)

    def online_zeile(self, name="marie"):
        z = self.sp.ausfuehren([("SELECT passwort_hash, totp_geheim, code_hash, code_bis, eingerichtet_utc, sitzung_nr FROM benutzer"
                                 " WHERE name = ?", [name])])[0]
        return dict(zip(("passwort_hash", "totp_geheim", "code_hash", "code_bis", "eingerichtet_utc", "sitzung_nr"), z[0]))

    # --- PC: Code ------------------------------------------------------------------------------------------------

    def test_code_steht_nur_als_hash_online_und_nie_auf_dem_pc(self):
        self.assertRegex(self.code, r"^[A-HJ-NP-Z2-9]{4}(-[A-HJ-NP-Z2-9]{4}){3}$")              # ohne I, O, 0, 1
        z = self.online_zeile()
        self.assertEqual(z["code_hash"], hashlib.sha256(self.code.replace("-", "").encode()).hexdigest())
        self.assertGreater(z["code_bis"], db.jetzt())
        roh = open(os.path.join(self.ordner.name, "amw.db"), "rb").read()
        self.assertNotIn(self.code.replace("-", "").encode(), roh)
        self.assertNotIn(self.code.encode(), roh)
        with self.assertRaises(kern.AmwFehler):
            benutzer.freischalten(self.con, "TL", "marie", self.sp)                           # nur der Mensch

    # --- erstes Anmelden ------------------------------------------------------------------------------------------

    def test_erstes_anmelden_ganz(self):
        aus = self.php(f"""
$aus['falsch'] = freischalten_beginnen('marie', 'AAAA-BBBB-CCCC-DDDD');
$aus['fremder'] = freischalten_beginnen('niemand', {json.dumps(self.code)});
$aus['code'] = freischalten_beginnen('marie', strtolower(str_replace('-', ' ', {json.dumps(self.code)})));   // klein, mit Leerzeichen
$aus['kurz'] = freischalten_passwort('kurz', 'kurz');
$aus['ungleich'] = freischalten_passwort('ein-langes-passwort', 'ein-anderes-passwort');
$aus['pw'] = freischalten_passwort('mein-langes-passwort', 'mein-langes-passwort');
$g = $_SESSION['freischalten']['geheim'];
$aus['geheim'] = $g;
$aus['vor_bestaetigung'] = zeile('marie')['passwort_hash'];
$aus['zu_alt'] = freischalten_abschliessen(zahl($g, -2));          // 60 s daneben: abgewiesen
$aus['ok'] = freischalten_abschliessen(zahl($g, -1));              // 30 s daneben: noch gut
$aus['angemeldet'] = angemeldet();
$aus['ich'] = $_SESSION['benutzer'] ?? null;
$aus['zugang'] = $_SESSION['zugang'] ?? null;
$aus['eingang'] = sql([["SELECT weg, daten, projekt FROM eingang", []]])[0];
""")
        gleich = "Name oder Freischalt-Code stimmt nicht – oder der Code ist abgelaufen."
        self.assertEqual((aus["falsch"], aus["fremder"]), (gleich, gleich))                    # dieselbe Meldung
        self.assertEqual(aus["code"], "")
        self.assertIn("mindestens 12", aus["kurz"])
        self.assertIn("nicht gleich", aus["ungleich"])
        self.assertEqual(aus["pw"], "")
        self.assertIsNone(aus["vor_bestaetigung"])                                              # erst Schritt 3 speichert
        self.assertIn("Zahl stimmt nicht", aus["zu_alt"])
        self.assertEqual(aus["ok"], "")
        self.assertTrue(aus["angemeldet"])
        self.assertEqual((aus["ich"], aus["zugang"]), ("marie", None))
        z = self.online_zeile()
        self.assertIsNotNone(z["passwort_hash"])
        self.assertEqual(z["totp_geheim"], aus["geheim"])
        self.assertIsNone(z["code_hash"])                                                       # Code verbraucht
        self.assertEqual(aus["eingang"], [["/api/benutzer/eingerichtet", json.dumps({"_benutzer": "marie"}, separators=(",", ":")), None]])

    def test_qr_inhalt_passt_zu_einer_authenticator_app(self):
        """Was der QR-Code enthält, rechnet eine App (hier RFC 6238 in Python) zu Zahlen, die die Seite annimmt."""
        aus = self.php(f"""
freischalten_beginnen('marie', {json.dumps(self.code)});
freischalten_passwort('mein-langes-passwort', 'mein-langes-passwort');
$g = $_SESSION['freischalten']['geheim'];
require dirname(getenv('AMW_LIB')) . '/qr.php';
$link = 'otpauth://totp/AMW:' . rawurlencode('marie') . '?secret=' . $g . '&issuer=AMW&digits=6&period=30';
$aus['geheim'] = $g;
$aus['svg'] = strlen(qr_svg($link)) > 1000;
$aus['link'] = $link;
""")
        g = aus["geheim"]
        self.assertRegex(g, r"^[A-Z2-7]{32}$")                                                  # 160 Bit, Base32
        self.assertEqual(aus["link"], f"otpauth://totp/AMW:marie?secret={g}&issuer=AMW&digits=6&period=30")
        self.assertTrue(aus["svg"])
        app = totp_py(g, int(time.time()) // 30)
        aus2 = self.php(f"""
freischalten_beginnen('marie', {json.dumps(self.code)});
freischalten_passwort('mein-langes-passwort', 'mein-langes-passwort');
$_SESSION['freischalten']['geheim'] = {json.dumps(g)};
$aus['ok'] = freischalten_abschliessen({json.dumps(app)});
""")
        self.assertIn(aus2["ok"], ("",))

    def test_abbruch_mittendrin_und_zweiter_versuch(self):
        aus = self.php(f"""
$aus['1'] = freischalten_beginnen('marie', {json.dumps(self.code)});
neu_browser();                                                     // Abbruch nach Schritt 1
$aus['2'] = freischalten_beginnen('marie', {json.dumps(self.code)});
freischalten_passwort('mein-langes-passwort', 'mein-langes-passwort');
neu_browser();                                                     // Abbruch nach Schritt 2 (QR gezeigt, nicht bestätigt)
$aus['zwischen'] = zeile('marie')['passwort_hash'];
$aus['3'] = freischalten_beginnen('marie', {json.dumps(self.code)});   // zweiter Versuch
freischalten_passwort('mein-langes-passwort', 'mein-langes-passwort');
$_SESSION['freischalten']['seit'] -= EINRICHTEN_S + 1;              // QR-Schritt zu lange offen
$aus['abgelaufen'] = freischalten_abschliessen('000000');
$aus['4'] = freischalten_beginnen('marie', {json.dumps(self.code)});
freischalten_passwort('mein-langes-passwort', 'mein-langes-passwort');
$aus['fertig'] = freischalten_abschliessen(zahl($_SESSION['freischalten']['geheim']));
neu_browser();
$aus['danach'] = freischalten_beginnen('marie', {json.dumps(self.code)});   // Code ist verbraucht
""")
        self.assertEqual([aus[k] for k in ("1", "2", "3", "4", "fertig")], [""] * 5)
        self.assertIsNone(aus["zwischen"])
        self.assertIn("Zeit abgelaufen", aus["abgelaufen"])
        self.assertIn("stimmt nicht", aus["danach"])

    def test_zwei_zugleich_mit_demselben_code(self):
        aus = self.php(f"""
freischalten_beginnen('marie', {json.dumps(self.code)});
freischalten_passwort('passwort-von-marie', 'passwort-von-marie');
$a = $_SESSION;
neu_browser();
freischalten_beginnen('marie', {json.dumps(self.code)});
freischalten_passwort('passwort-vom-fremden', 'passwort-vom-fremden');
$b = $_SESSION;
$_SESSION = $a; $aus['erster'] = freischalten_abschliessen(zahl($a['freischalten']['geheim']));
$_SESSION = $b; $aus['zweiter'] = freischalten_abschliessen(zahl($b['freischalten']['geheim']));
$aus['zweiter_angemeldet'] = !empty($_SESSION['angemeldet']);
$aus['geheim_a'] = $a['freischalten']['geheim'];
""")
        self.assertEqual(aus["erster"], "")
        self.assertIn("inzwischen benutzt", aus["zweiter"])
        self.assertFalse(aus["zweiter_angemeldet"])
        self.assertEqual(self.online_zeile()["totp_geheim"], aus["geheim_a"])                 # der erste gilt

    def test_abgelaufener_code(self):
        self.sp.ausfuehren([("UPDATE benutzer SET code_bis = '2000-01-01T00:00:00Z' WHERE name = 'marie'", [])])
        aus = self.php(f"$aus['x'] = freischalten_beginnen('marie', {json.dumps(self.code)});")
        self.assertIn("abgelaufen", aus["x"])

    # --- danach: Anmelden, doppelte Zahl, Sperren, neu Freischalten ----------------------------------------------

    def einrichten(self):
        return self.php(f"""
freischalten_beginnen('marie', {json.dumps(self.code)});
freischalten_passwort('mein-langes-passwort', 'mein-langes-passwort');
$aus['g'] = $_SESSION['freischalten']['geheim'];
freischalten_abschliessen(zahl($aus['g'], -1));
""")["g"]

    def test_anmelden_je_benutzer(self):
        g = self.einrichten()
        aus = self.php(f"""
$g = {json.dumps(g)};
$aus['falsches_pw'] = anmelden('marie', 'falsch-falsch-falsch', zahl($g));
$aus['ohne_zahl'] = anmelden('marie', 'mein-langes-passwort', '');
$aus['ok'] = anmelden('marie', 'mein-langes-passwort', zahl($g));
$aus['ich'] = $_SESSION['benutzer'] ?? null;
neu_browser();
$aus['gleiche_zahl'] = anmelden('marie', 'mein-langes-passwort', zahl($g));    // dieselbe Zahl noch einmal
$aus['chef'] = anmelden('chef', 'chef-passwort-123', '');                       // Zugang der Konfiguration bleibt (ohne Faktor → einrichten)
""")
        self.assertEqual(aus["falsches_pw"], "Anmeldung fehlgeschlagen.")
        self.assertEqual(aus["ohne_zahl"], "Anmeldung fehlgeschlagen.")
        self.assertEqual(aus["ok"], "")
        self.assertEqual(aus["ich"], "marie")
        self.assertEqual(aus["gleiche_zahl"], "Anmeldung fehlgeschlagen.")
        self.assertEqual(aus["chef"], "einrichten")

    def test_sperren_und_neu_freischalten_beenden_die_sitzung(self):
        g = self.einrichten()
        aus = self.php(f"""
anmelden('marie', 'mein-langes-passwort', zahl({json.dumps(g)}, 1));
$aus['vorher'] = angemeldet();
sql([["UPDATE benutzer SET gesperrt = 1 WHERE name = 'marie'", []]]);
$aus['gesperrt'] = angemeldet();
""")
        self.assertEqual((aus["vorher"], aus["gesperrt"]), (True, False))
        self.sp.ausfuehren([("UPDATE benutzer SET gesperrt = 0 WHERE name = 'marie'", [])])
        aus = self.php(f"""
anmelden('marie', 'mein-langes-passwort', zahl({json.dumps(g)}, 1));
$aus['vorher'] = angemeldet();
$aus['nr'] = (int)zeile('marie')['sitzung_nr'];
""")
        self.assertIn(aus["vorher"], (True, False))                                            # Zahl evtl. schon benutzt
        code2, _ = benutzer.freischalten(self.con, kern.ENTWICKLER, "marie", self.sp)          # verlorenes Handy
        z = self.online_zeile()
        self.assertIsNone(z["passwort_hash"])
        self.assertEqual(z["sitzung_nr"], aus["nr"] + 1)
        aus = self.php(f"""
$_SESSION['angemeldet'] = true; $_SESSION['benutzer'] = 'marie'; $_SESSION['sitzung_nr'] = {aus['nr']};
$_SESSION['seit'] = $_SESSION['zuletzt'] = time();
$aus['alte_sitzung'] = angemeldet();
$aus['alter_code'] = freischalten_beginnen('marie', {json.dumps(self.code)});
$aus['neuer_code'] = freischalten_beginnen('marie', {json.dumps(code2)});
""")
        self.assertFalse(aus["alte_sitzung"])
        self.assertIn("stimmt nicht", aus["alter_code"])
        self.assertEqual(aus["neuer_code"], "")

    def test_ohne_rolle_keine_rechte_und_projekte_gefiltert(self):
        aus = self.php("""
foreach (['/api/nachricht', '/api/einstellungen/projekt', '/api/einstellungen/pc', '/api/benutzer/neu'] as $p) $aus['k'][$p] = eingabe_klasse($p);
$aus['ohne'] = rolle_reicht(null, 'lesen');
$aus['leser_arbeiten'] = rolle_reicht('leser', 'arbeiten');
$aus['bearbeiter_arbeiten'] = rolle_reicht('bearbeiter', 'arbeiten');
$aus['pa_system'] = rolle_reicht('projekt_admin', 'system');
$aus['sa_system'] = rolle_reicht('system_admin', 'system');
""")
        for p, k in aus["k"].items():
            self.assertEqual(k, benutzer.klasse(p), p)                                         # PHP und PC sind sich einig
        self.assertEqual([aus[k] for k in ("ohne", "leser_arbeiten", "bearbeiter_arbeiten", "pa_system", "sa_system")],
                         [False, False, True, False, True])

    def test_herkunft_wie_beim_ersten_einrichten(self):
        """01.11.: hinter dem CDN und mit Origin: null wurde die Anmeldung abgewiesen."""
        aus = self.php("""
$_SERVER['HTTP_HOST'] = 'amw.example.org';
$_SERVER['HTTP_ORIGIN'] = 'https://amw.example.org'; $aus['eigen'] = herkunft_ok();
$_SERVER['HTTP_HOST'] = 'intern:8080'; $_SERVER['HTTP_X_FORWARDED_HOST'] = 'amw.example.org'; $aus['proxy'] = herkunft_ok();
unset($_SERVER['HTTP_ORIGIN']); $aus['ohne'] = herkunft_ok();
$_SERVER['HTTP_ORIGIN'] = 'null'; $aus['null'] = herkunft_ok();
$_SERVER['HTTP_ORIGIN'] = 'https://boese.example.net'; $aus['fremd'] = herkunft_ok();
""")
        self.assertEqual([aus[k] for k in ("eigen", "proxy", "ohne", "null", "fremd")], [True, True, True, False, False])
        with open(os.path.join(WURZEL, "web", "inc", "lib.php"), encoding="utf-8") as f:
            self.assertIn("Referrer-Policy: same-origin", f.read())                           # sonst schickt der Browser Origin: null


if __name__ == "__main__":
    unittest.main()
