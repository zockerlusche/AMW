"""Seiten aktualisieren sich (Fehler 06.11.: Frage beantwortet → Liste blieb, nur der Zähler im Menü stimmte).

- Schnittstelle: /api/start bringt je Sicht einen Stempel; er ändert sich, wenn sich ihre Daten ändern – auch von außen –,
  und nicht durch Lebenszeichen der Agenten.
- Seite (Edge ohne Fenster über das DevTools-Protokoll, nur wenn Edge da ist): nach der Antwort ist die Frage sofort weg;
  eine neue Frage von außen erscheint ohne Klick; eine ungespeicherte Eingabe bleibt, stattdessen „Neuer Stand“.
"""
import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import unittest
import urllib.request

from amw import db, kern, wissen, workbench

EDGE = next((p for p in (shutil.which("msedge"), r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                         r"C:\Program Files\Microsoft\Edge\Application\msedge.exe") if p and os.path.exists(p)), None)


# Unter Last (andere Rechen-Läufe auf demselben PC) braucht die Seite ein Vielfaches – die Grenzen sind Obergrenzen, der
# Test geht weiter, sobald die Bedingung stimmt. AMW_TEST_ZEIT=1 stellt die knappen Grenzen her.
ZEIT = float(os.environ.get("AMW_TEST_ZEIT", "4"))


def warte_auf(test, bedingung, sekunden):
    grenze = sekunden * ZEIT
    ende = time.time() + grenze
    while time.time() < ende:
        try:
            if test.tab.js(f"!!({bedingung})"):
                return
        except AssertionError:
            pass
        time.sleep(0.15)
    test.fail(f"nach {grenze:.0f} s nicht erfüllt: {bedingung}")


def edge_beenden(prozess):
    """Den Test-Browser mit allen Kindprozessen beenden – sonst halten sie Dateien im Temp-Ordner des Tests fest."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(prozess.pid), "/T", "/F"], capture_output=True)
    else:
        prozess.terminate()
    try:
        prozess.wait(10)
    except subprocess.TimeoutExpired:
        prozess.kill()


class Wiederholt:
    """Reißt die Verbindung zum Test-Browser ab (unter Last stirbt er gelegentlich), wird der Test einmal neu aufgesetzt.
    Eine nicht erfüllte Bedingung ist kein Verbindungsfehler und bleibt ein Fehler."""

    def _callTestMethod(self, method):
        try:
            method()
        except OSError:                              # ConnectionResetError, Zeitüberschreitung am Socket …
            self.tearDown()
            self.setUp()
            method()


def freier_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)   # ein noch offener Rest des Test-Browsers ist kein Testfehler
        self.alt_db = os.environ.get("AMW_DB")
        os.environ["AMW_DB"] = os.path.join(self.ordner.name, "amw.db")
        self.con = db.anlegen()
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        self.fid = kern.frage_neu(self.con, self.pid, "TL", "entwickler", "Erste Frage?", [("A", "ja"), ("B", "nein")], "A",
                                  "weil", geprueft="keine Treffer")

    def tearDown(self):
        self.con.close()
        if self.alt_db is None:
            os.environ.pop("AMW_DB", None)
        else:
            os.environ["AMW_DB"] = self.alt_db
        self.ordner.cleanup()

    def frage(self, kurz):
        return kern.frage_neu(self.con, self.pid, "TL", "entwickler", kurz, [("A", "ja"), ("B", "nein")], "A", "weil",
                              geprueft="keine Treffer")


class Stempel(Grund):
    def stand(self):
        return workbench.daten_start(self.con, self.pid)["stand"]

    def test_jede_sicht_hat_einen_stempel_und_die_seite_kennt_sie(self):
        html = open(os.path.join(os.path.dirname(workbench.__file__), "workbench.html"), encoding="utf-8").read()
        for s in workbench.STAND_SICHTEN:
            self.assertIn(f" {s}: sicht", html)                 # Sicht gibt es in zeige()
        self.assertEqual(set(self.stand()), set(workbench.STAND_SICHTEN))

    def test_antwort_und_aenderung_von_aussen_aendern_den_stempel(self):
        vorher = self.stand()
        time.sleep(1.05)                                     # Stempel auf die Sekunde: eine Sekunde weiter
        kern.frage_antworten(self.con, self.pid, self.fid, "option", "A", "workbench")
        nachher = self.stand()
        self.assertNotEqual(vorher["fragen"], nachher["fragen"])
        self.assertEqual(vorher["wissen"], nachher["wissen"])
        self.frage("Von außen?")                             # ein Agent stellt eine Frage
        self.assertNotEqual(nachher["fragen"], self.stand()["fragen"])
        b = wissen.beschluss_neu(self.con, self.pid, "TL", "Neu", "Regel", "Entwickler")
        self.assertTrue(b)
        self.assertNotEqual(nachher["wissen"], self.stand()["wissen"])

    def test_lebenszeichen_aendert_keine_sicht(self):
        vorher = self.stand()
        time.sleep(1.05)
        aid = self.con.execute("SELECT id FROM agent WHERE kennung = 'TL'").fetchone()[0]
        with db.schreiben(self.con):                         # Sitzung + Puls, wie der Hook sie schreibt
            sid = db.einfuegen(self.con, "sitzung", agent_id=aid, gestartet_utc=db.jetzt(), zustand="aktiv")
            self.con.execute("UPDATE sitzung SET letzter_puls_utc = ? WHERE id = ?", (db.jetzt(), sid))
        self.assertEqual(vorher, self.stand())


class _Tab:
    """Minimaler DevTools-Client (nur stdlib)."""
    def __init__(self, url):
        host, rest = url[len("ws://"):].split("/", 1)
        h, p = host.split(":")
        self.s = socket.create_connection((h, int(p)), timeout=20)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET /{rest} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        puffer = b""
        while b"\r\n\r\n" not in puffer:
            puffer += self.s.recv(4096)
        self.rest, self.n = puffer.split(b"\r\n\r\n", 1)[1], 0

    def _lesen(self, n):
        while len(self.rest) < n:
            self.rest += self.s.recv(1 << 20)
        d, self.rest = self.rest[:n], self.rest[n:]
        return d

    def senden(self, methode, **params):
        self.n += 1
        daten = json.dumps({"id": self.n, "method": methode, "params": params}).encode()
        kopf, laenge = bytearray([0x81]), len(daten)
        if laenge < 126:
            kopf.append(0x80 | laenge)
        elif laenge < 65536:
            kopf.append(0x80 | 126)
            kopf += struct.pack(">H", laenge)
        else:
            kopf.append(0x80 | 127)
            kopf += struct.pack(">Q", laenge)
        maske = os.urandom(4)
        self.s.sendall(bytes(kopf) + maske + bytes(b ^ maske[i % 4] for i, b in enumerate(daten)))
        while True:
            _, b2 = self._lesen(2)
            laenge = b2 & 0x7F
            if laenge == 126:
                laenge = struct.unpack(">H", self._lesen(2))[0]
            elif laenge == 127:
                laenge = struct.unpack(">Q", self._lesen(8))[0]
            m = json.loads(self._lesen(laenge))
            if m.get("id") == self.n:
                return m.get("result", m)

    def js(self, ausdruck):
        r = self.senden("Runtime.evaluate", expression=ausdruck, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in r:
            raise AssertionError(r["exceptionDetails"])
        return r["result"].get("value")


@unittest.skipUnless(EDGE, "Edge nicht installiert")
class Seite(Wiederholt, Grund):
    def setUp(self):
        super().setUp()
        self.port = freier_port()
        self.srv = workbench.starten(self.port)
        dt = freier_port()
        self.edge = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--no-first-run", f"--remote-debugging-port={dt}",
                                      f"--user-data-dir={os.path.join(self.ordner.name, 'edge')}", "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ziel = None
        for _ in range(150):
            try:
                ziel = next(z for z in json.load(urllib.request.urlopen(f"http://127.0.0.1:{dt}/json", timeout=2))
                            if z["type"] == "page")
                break
            except Exception:
                time.sleep(0.2)
        self.assertIsNotNone(ziel, "Edge meldet sich nicht")
        self.tab = _Tab(ziel["webSocketDebuggerUrl"])
        self.tab.senden("Page.navigate", url=f"http://127.0.0.1:{self.port}/#fragen")
        self.warten("document.querySelectorAll('.karte.frage').length === 1")

    def tearDown(self):
        try:
            self.tab.s.close()
        except Exception:
            pass
        edge_beenden(self.edge)
        self.srv.shutdown()
        self.srv.server_close()
        super().tearDown()

    def warten(self, bedingung, sekunden=8):
        warte_auf(self, bedingung, sekunden)

    def takt(self):
        """Ein Takt des 15-s-Intervalls, sofort (Kopf laden, dann Stempel prüfen)."""
        self.tab.js("kopfAktualisieren().then(() => standPruefen())")

    def test_antwort_nimmt_die_frage_sofort_aus_der_liste(self):
        self.tab.js("document.querySelector('.karte.frage .option.empfohlen').click()")
        self.warten("document.querySelectorAll('.karte.frage').length === 0", 3)
        self.warten("document.querySelector('#inhalt .leer') !== null", 4)    # danach frisch gezeichnet: „keine Fragen“
        self.assertEqual(self.con.execute("SELECT status FROM frage WHERE id = ?", (self.fid,)).fetchone()[0], "beantwortet")

    def test_neue_frage_von_aussen_erscheint_ohne_klick(self):
        time.sleep(1.05)
        self.frage("Zweite Frage von außen?")
        self.takt()
        self.warten("document.querySelectorAll('.karte.frage').length === 2")
        self.assertIsNone(self.tab.js("document.getElementById('neuer-stand')"))

    def test_ungespeicherte_eingabe_bleibt(self):
        self.tab.js("document.querySelector('.karte.frage textarea').value = 'halb geschrieben'")
        time.sleep(1.05)
        self.frage("Dritte Frage?")
        self.takt()
        self.warten("document.getElementById('neuer-stand') !== null")
        self.assertEqual(self.tab.js("document.querySelector('.karte.frage textarea').value"), "halb geschrieben")
        self.assertEqual(self.tab.js("document.querySelectorAll('.karte.frage').length"), 1)
        self.tab.js("document.querySelector('#neuer-stand button').click()")              # Knopf: jetzt neu zeichnen
        self.warten("document.querySelectorAll('.karte.frage').length === 2 && !document.getElementById('neuer-stand')")


if __name__ == "__main__":
    unittest.main()
