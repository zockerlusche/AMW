"""A2035: langsame Anfragen der Workbench – ab 1 s genau eine Zeile in dienst.log (Logger amw.workbench) mit Weg, Dauer und
den längsten Teilschritten (DB-Sperre, externe Aufrufe, Abgleich); schnelle Anfragen schreiben nichts."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import http.client
import logging
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from amw import anfragezeit, db, kern, workbench


def freier_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Messen(unittest.TestCase):
    def test_teilschritte_und_grenze(self):
        anfragezeit.einhaengen()
        anfragezeit.start("GET /api/probe")
        subprocess.check_output([sys.executable, "-c", "pass"])           # check_output ruft run: nur einmal gezählt
        with anfragezeit.messen("Abgleich"):
            time.sleep(0.05)
        anfragezeit.teil("DB-Sperre", 0.4)
        with self.assertLogs("amw.workbench", logging.WARNING) as l:
            zeile = anfragezeit.ende(200, grenze=0) or ""
        self.assertEqual(len(l.records), 1)
        self.assertIn("Langsame Anfrage GET /api/probe:", zeile)
        self.assertIn("DB-Sperre 0.4 s", zeile)
        self.assertRegex(zeile, r"Aufruf python(w)? \d+\.\d s(?! \()")         # einmal, nicht „(2×)“
        self.assertIn("Abgleich", zeile)

    def test_ohne_messung_kostet_nichts(self):
        anfragezeit.einhaengen()
        anfragezeit.teil("DB-Sperre", 5)                                    # keine Anfrage im Faden: nichts gemerkt
        self.assertIsNone(anfragezeit.ende())
        self.assertEqual(subprocess.run([sys.executable, "-c", "print(1)"], capture_output=True, text=True).stdout.strip(), "1")


class Workbench(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        u.start()
        self.addCleanup(u.stop)
        con = db.anlegen()
        with db.schreiben(con):
            self.pid = db.einfuegen(con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(con, self.pid, "TL", rolle="lead")
        con.close()
        self.port = freier_port()
        self.srv = workbench.starten(self.port)
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def anfrage(self, weg):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("GET", weg)
        r = c.getresponse()
        r.read()
        c.close()
        return r.status

    def test_langsame_anfrage_eine_zeile_schnelle_keine(self):
        echt = workbench.daten_kosten

        def langsam(con, pid):
            time.sleep(1.2)
            return echt(con, pid)
        with mock.patch.object(workbench, "daten_kosten", langsam), self.assertLogs("amw.workbench", logging.WARNING) as l:
            self.assertEqual(self.anfrage("/api/kosten?projekt=P"), 200)
            time.sleep(0.2)                                                  # die Zeile schreibt der Faden nach der Antwort
            self.assertEqual(self.anfrage("/api/pause?projekt=P"), 200)        # Gegenprobe: schnell → keine Zeile
            time.sleep(0.2)
            logging.getLogger("amw.workbench").warning("Ende")                # assertLogs braucht mindestens eine Zeile
        zeilen = [r.getMessage() for r in l.records if r.getMessage() != "Ende"]
        self.assertEqual(len(zeilen), 1, zeilen)
        self.assertRegex(zeilen[0], r"^Langsame Anfrage GET /api/kosten: 1\.\d s \(200\)")


if __name__ == "__main__":
    unittest.main()
