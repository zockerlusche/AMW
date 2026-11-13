"""Online: Was der Mensch erledigt hat, bleibt weg – auch in den Sekunden, in denen der PC die Eingabe schon ausgeführt,
die neue Ansicht aber noch nicht hochgeladen hat (vorher: verschwindet → taucht wieder auf → verschwindet). Mit dem echten
PHP der Seite gegen eine SQLite-Datei: Ansicht /api/start mit zwei Nachrichten an den Menschen, „gelesen“ im Briefkasten."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from amw import abgleich

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHP = shutil.which("php")


@unittest.skipUnless(PHP, "PHP nicht installiert")
class Briefkasten(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.online = os.path.join(self.ordner.name, "online.db")
        self.sp = abgleich.SqliteSpeicher(self.online)
        self.sp.ausfuehren([(s, []) for s in abgleich.SCHEMA])
        abgleich.nachruesten(self.sp)
        self.konfig = os.path.join(self.ordner.name, "amw-konfig.php")
        with open(self.konfig, "w", encoding="utf-8") as f:
            f.write(f"<?php return ['sqlite' => {json.dumps(self.online.replace(os.sep, '/'))}, 'benutzer' => 'p', 'passwort_hash' => 'x'];\n")

    def eingang(self, status, zeit, erledigt=None, projekt="P1", ids=(5,)):
        self.sp.ausfuehren([("INSERT INTO eingang (zeit_utc, weg, daten, status, erledigt_utc, projekt) VALUES (?, '/api/gelesen', ?, ?, ?, ?)",
                             [zeit, json.dumps({"ids": list(ids)}), status, erledigt, projekt])])

    def wirkt(self, stand):
        datei = os.path.join(self.ordner.name, "probe.php")
        with open(datei, "w", encoding="utf-8") as f:
            f.write("<?php require getenv('AMW_LIB'); echo json_encode(briefkasten_wirkt('P1', " + json.dumps(stand) + "));")
        env = {**os.environ, "AMW_KONFIG": self.konfig, "AMW_LIB": os.path.join(WURZEL, "web", "inc", "lib.php").replace(os.sep, "/")}
        r = subprocess.run([PHP, "-d", "extension=pdo_sqlite", "-d", "extension=mbstring", datei], capture_output=True, text=True, env=env, timeout=60)
        if "could not find driver" in r.stdout + r.stderr:
            self.skipTest("PHP ohne pdo_sqlite")
        try:
            return [json.loads(d)["ids"] for _, d in json.loads(r.stdout.strip().splitlines()[-1])]
        except (ValueError, IndexError):
            self.fail(r.stdout + r.stderr)

    def test_erledigt_aber_ansicht_noch_alt_bleibt_weg(self):
        stand = "2026-11-12T06:07:40Z"                              # Ansicht mit Nachricht 5, hochgeladen vor dem Klick
        self.eingang("neu", "2026-11-12T06:07:45Z")
        self.assertEqual(self.wirkt(stand), [[5]])                  # im Briefkasten: ausgeblendet (wie bisher)
        self.sp.ausfuehren([("UPDATE eingang SET status = 'erledigt', erledigt_utc = '2026-11-12T06:07:56Z'", [])])
        self.assertEqual(self.wirkt(stand), [[5]])                  # PC hat ausgeführt, neue Ansicht noch nicht oben: weiter weg
        self.assertEqual(self.wirkt("2026-11-12T06:08:01Z"), [])    # neue Ansicht da (ohne Nachricht 5): nichts mehr zu tun

    def test_fehler_und_andere_projekte_wirken_nicht(self):
        stand = "2026-11-12T06:00:00Z"
        self.eingang("fehler", "2026-11-12T06:01:00Z", "2026-11-12T06:01:05Z", ids=(7,))     # am PC abgewiesen: wieder zeigen
        self.eingang("neu", "2026-11-12T06:02:00Z", projekt="P2", ids=(8,))                  # anderes Projekt
        self.eingang("neu", "2026-11-12T06:03:00Z", projekt=None, ids=(9,))                  # ohne Projekt (alte Seite): gilt
        self.eingang("erledigt", "2026-11-12T05:58:00Z", "2026-11-12T05:59:00Z", ids=(4,))   # schon vor der Ansicht erledigt
        self.assertEqual(self.wirkt(stand), [[9]])



@unittest.skipUnless(PHP, "PHP nicht installiert")
class GanzerWeg(unittest.TestCase):
    """Gemeldeter Ablauf: Einstellungen › Agent › „Zuständig für“ speichern → Seite neu laden, bevor der PC es
    ausgeführt hat → der Wert muss stehen; danach meldet die Seite „gespeichert“ bzw. einen Fehler mit Grund. Echter
    Webhoster-Code (php -S) gegen eine SQLite-Datei, echter Abgleich des PCs."""
    def setUp(self):
        import base64, http.cookiejar, re, socket, time, urllib.request
        from amw import db, kern
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        online = os.path.join(self.ordner.name, "online.db")
        self.sp = abgleich.SqliteSpeicher(online)
        self.ab = abgleich.Abgleich(self.con, self.sp, self.pid)
        self.ab.schema()
        self.ab.hochladen(alle=True)
        geheim = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
        self.sp.ausfuehren([("INSERT INTO zustand (schluessel, wert) VALUES ('totp_geheim', ?)", [geheim])])
        konfig = os.path.join(self.ordner.name, "amw-konfig.php")
        hashwert = subprocess.run([PHP, "-r", "echo password_hash('chef-passwort-1', PASSWORD_DEFAULT);"], capture_output=True, text=True).stdout.strip()
        with open(konfig, "w", encoding="utf-8") as f:
            f.write(f"<?php return ['sqlite' => {json.dumps(online.replace(os.sep, '/'))}, 'benutzer' => 'chef', 'passwort_hash' => '{hashwert}', 'nur_https' => false];\n")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        env = {**os.environ, "AMW_KONFIG": konfig}
        self.srv = subprocess.Popen([PHP, "-d", "extension=pdo_sqlite", "-d", "extension=mbstring", "-d", "extension=curl", "-S", f"127.0.0.1:{self.port}",
                                     "-t", os.path.join(WURZEL, "web")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.srv.terminate)
        self.basis = f"http://127.0.0.1:{self.port}/"
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        for _ in range(50):
            try:
                seite = self.op.open(self.basis).read().decode()
                break
            except OSError:
                time.sleep(0.2)
        csrf = re.search(r'name="csrf" value="([^"]+)"', seite).group(1)
        import hashlib, hmac, struct
        h = hmac.new(base64.b32decode(geheim), struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest()
        o = h[19] & 0x0F
        zahl = str((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 1000000).zfill(6)
        import urllib.parse
        html = self.op.open(self.basis, urllib.parse.urlencode({"benutzer": "chef", "passwort": "chef-passwort-1", "code": zahl, "csrf": csrf}).encode()).read().decode()
        self.token = re.search(r"([0-9a-f]{64})", html).group(1)

    def hole(self, weg):
        return json.loads(self.op.open(self.basis + "api.php?weg=" + weg).read().decode())

    def schicke(self, weg, daten):
        import urllib.request
        rq = urllib.request.Request(self.basis + "api.php?weg=" + weg, data=json.dumps(daten).encode(), method="POST",
                                    headers={"Content-Type": "application/json", "X-AMW-Token": self.token, "Origin": self.basis.rstrip("/")})
        return json.loads(self.op.open(rq).read().decode())

    def tl(self):
        return next(a for a in self.hole("/api/einstellungen")["agenten"] if a["kennung"] == "TL")

    def test_wert_bleibt_stehen_und_wird_bestaetigt(self):
        import time
        r = self.schicke("/api/einstellungen/agent", {"kennung": "TL", "zustaendig": "Führt das ganze Projekt", "fachgebiet": "Planung"})
        self.assertTrue(r["unterwegs"] and r["eingang"] > 0)
        self.assertEqual(self.tl()["zustaendig"], "Führt das ganze Projekt")                    # neu geladen, PC noch nicht dran
        self.assertEqual([x["status"] for x in self.hole(f"/api/eingang?ids={r['eingang']}")], ["neu"])
        self.ab.letzt_hoch = time.time()                                                       # gerade erst hochgeladen …
        self.assertTrue(self.ab.schritt(False))                                                # … trotzdem sofort nach der Aktion
        self.assertEqual([x["status"] for x in self.hole(f"/api/eingang?ids={r['eingang']}")], ["erledigt"])
        self.assertEqual(self.tl()["zustaendig"], "Führt das ganze Projekt")                    # jetzt aus der neuen Ansicht
        self.assertEqual(self.con.execute("SELECT zustaendig FROM agent WHERE kennung = 'TL'").fetchone()[0], "Führt das ganze Projekt")
        self.assertEqual(self.hole("/api/eingang?ids=999999"), [])                             # fremde Nummern: nichts

    def test_fehler_mit_grund_und_neuer_agent_sofort_sichtbar(self):
        r = self.schicke("/api/einstellungen/agent", {"kennung": "CC9", "neu": True, "fachgebiet": "Test"})
        self.assertIn("CC9", [a["kennung"] for a in self.hole("/api/einstellungen")["agenten"]])  # gleich in der Liste
        doppelt = self.schicke("/api/einstellungen/agent", {"kennung": "TL", "neu": True})
        self.ab.schritt(False)
        st = {x["id"]: x for x in self.hole(f"/api/eingang?ids={r['eingang']},{doppelt['eingang']}")}
        self.assertEqual(st[r["eingang"]]["status"], "erledigt")
        self.assertEqual(st[doppelt["eingang"]]["status"], "fehler")
        self.assertIn("gibt es schon", st[doppelt["eingang"]]["fehler"])


    def test_nachrichten_nur_das_gewaehlte_projekt(self):
        """Seite „Nachrichten“ online: nur das oben gewählte Projekt (Marcel 13.11., B2691) – ‚alle=1‘ legt nichts mehr
        zusammen, das Menü zählt nur dieses Projekt; Geschriebenes im Briefkasten steht beim richtigen Projekt."""
        from amw import db, kern
        with db.schreiben(self.con):
            p2 = db.einfuegen(self.con, "projekt", name="Q", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, p2, "QL", rolle="lead")
        kern.posten(self.con, self.pid, kern.ENTWICKLER, "CC1", "auftrag", "in P")
        kern.posten(self.con, p2, kern.ENTWICKLER, "QL", "auftrag", "in Q")
        kern.posten(self.con, p2, "QL", kern.ENTWICKLER, "info", "Antwort aus Q")
        self.ab.hochladen(alle=True)
        ab2 = abgleich.Abgleich(self.con, self.sp, p2)
        ab2.hochladen(alle=True)
        uid = {n: u for n, u in self.con.execute("SELECT name, uid FROM projekt")}
        nur_p = "&projekt=" + uid["P"]
        for weg in ("/api/nachrichten", "/api/nachrichten?alle=1"):                              # alle=1: wie ohne
            d = self.hole(weg + nur_p)
            self.assertEqual([(x["kurz"], x["projekt"]) for x in d["gesendet"]], [("in P", uid["P"])])
            self.assertEqual(d["eingang"], [])
            self.assertEqual(d["zaehler"]["eingang_offen"], 0)
        self.assertEqual(self.hole("/api/start" + nur_p)["zaehler"]["nachrichten"], 0)          # Menü: nur Projekt P
        d = self.hole("/api/nachrichten&projekt=" + uid["Q"])
        self.assertEqual([x["kurz"] for x in d["eingang"]], ["Antwort aus Q"])
        self.assertEqual(self.hole("/api/start&projekt=" + uid["Q"])["zaehler"]["nachrichten"], 1)
        import urllib.request
        rq = urllib.request.Request(self.basis + "api.php?weg=/api/nachricht&projekt=" + uid["Q"], method="POST",
                                    data=json.dumps({"an": "QL", "art": "info", "kurz": "unterwegs nach Q"}).encode(),
                                    headers={"Content-Type": "application/json", "X-AMW-Token": self.token, "Origin": self.basis.rstrip("/")})
        self.assertTrue(json.loads(self.op.open(rq).read().decode())["unterwegs"])
        self.assertEqual([x for x in self.hole("/api/nachrichten" + nur_p)["gesendet"] if x.get("unterwegs")], [])   # nicht unter P
        u = [x for x in self.hole("/api/nachrichten&projekt=" + uid["Q"])["gesendet"] if x.get("unterwegs")]
        self.assertEqual([(x["kurz"], x["empfaenger"][0]["stand"]) for x in u], [("unterwegs nach Q", "unterwegs")])


if __name__ == "__main__":
    unittest.main()
