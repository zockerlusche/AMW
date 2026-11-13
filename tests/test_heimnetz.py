"""Workbench aus dem Heimnetz (A1643, Marcel 13.11.): Einstellung dieses PCs „heimnetz“ (privater Bereich in CIDR, Vorgabe aus).
Ist sie an, lauscht die Workbench auf allen Adressen, nimmt aber nur Anfragen vom PC selbst und aus dem Bereich an; Host und
Origin müssen localhost bzw. eine IP aus dem Bereich sein (nie ein Name – DNS-Rebinding). Aus = wie bisher, nur 127.0.0.1."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import ipaddress
import json
import os
import unittest
import urllib.error
import urllib.request

from amw import abgleich, db, einstellungen, workbench
from tests.test_aktualisieren import Grund, freier_port

NETZ = ipaddress.ip_network("192.168.178.0/24")


class Einstellung(unittest.TestCase):
    def test_nur_private_netze(self):
        pruefe = einstellungen.FELDER["heimnetz"][1]
        self.assertEqual(einstellungen.FELDER["heimnetz"][0], "")                               # Vorgabe: aus
        self.assertEqual(pruefe(""), "")
        self.assertEqual(pruefe(" 192.168.178.20/24 "), "192.168.178.0/24")                     # auf den Bereich normalisiert
        for ok in ("10.0.0.0/8", "172.20.0.0/16", "192.168.0.0/16"):
            self.assertEqual(pruefe(ok), ok)
        for falsch in ("8.8.8.0/24", "0.0.0.0/0", "192.0.0.0/8", "172.32.0.0/16", "fd00::/8", "kein netz", "192.168.178.0/33"):
            with self.assertRaises(ValueError, msg=falsch):
                pruefe(falsch)
        self.assertIn("heimnetz", einstellungen.NEUSTART)                                        # wirkt nach Neustart des Dienstes


class Regeln(unittest.TestCase):
    def test_zugelassen(self):
        self.assertTrue(workbench.zugelassen("127.0.0.1", None))
        self.assertTrue(workbench.zugelassen("::1", None))
        self.assertFalse(workbench.zugelassen("192.168.178.30", None))                           # aus: nur der PC
        self.assertTrue(workbench.zugelassen("192.168.178.30", NETZ))
        self.assertTrue(workbench.zugelassen("::ffff:192.168.178.30", NETZ))
        self.assertFalse(workbench.zugelassen("192.168.179.5", NETZ))                            # Fritzbox-Gastnetz bleibt draußen
        self.assertFalse(workbench.zugelassen("10.0.0.5", NETZ))
        self.assertFalse(workbench.zugelassen("unsinn", NETZ))

    def test_host_und_origin(self):
        self.assertTrue(workbench.host_ok("127.0.0.1:8780", 8780, None))
        self.assertTrue(workbench.host_ok("localhost:8780", 8780, None))
        self.assertFalse(workbench.host_ok("192.168.178.20:8780", 8780, None))
        self.assertTrue(workbench.host_ok("192.168.178.20:8780", 8780, NETZ))
        self.assertFalse(workbench.host_ok("192.168.178.20:9999", 8780, NETZ))                    # anderer Port
        self.assertFalse(workbench.host_ok("192.168.179.20:8780", 8780, NETZ))
        self.assertFalse(workbench.host_ok("boese.example:8780", 8780, NETZ))                     # Name: nie (DNS-Rebinding)
        self.assertFalse(workbench.host_ok(None, 8780, NETZ))


class Server(Grund):
    def anfrage(self, port, host, methode="GET", origin=None):
        rq = urllib.request.Request(f"http://127.0.0.1:{port}/api/start", method=methode, headers={"Host": host},
                                    data=b"{}" if methode == "POST" else None)
        if origin:
            rq.add_header("Origin", origin)
        try:
            with urllib.request.urlopen(rq, timeout=10) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def test_aus_wie_bisher(self):
        port = freier_port()
        srv = workbench.starten(port, netz=None)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        self.assertEqual(srv.server_address[0], "127.0.0.1")
        self.assertEqual(self.anfrage(port, f"127.0.0.1:{port}"), 200)
        self.assertEqual(self.anfrage(port, f"192.168.178.20:{port}"), 403)

    def test_an_lauscht_ueberall_prueft_host(self):
        port = freier_port()
        srv = workbench.starten(port, netz=NETZ)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        self.assertEqual(srv.server_address[0], "0.0.0.0")
        self.assertEqual(self.anfrage(port, f"127.0.0.1:{port}"), 200)                          # am PC wie bisher
        self.assertEqual(self.anfrage(port, f"192.168.178.20:{port}"), 200)                     # Handy ruft die PC-Adresse auf
        self.assertEqual(self.anfrage(port, f"boese.example:{port}"), 403)
        self.assertEqual(self.anfrage(port, f"192.168.178.20:{port}", "POST", origin="http://boese.example"), 403)

    def test_leitstand_zeigt_heimnetz_nur_am_pc(self):
        einstellungen.speichern({"heimnetz": "192.168.178.0/24"})
        self.addCleanup(lambda: einstellungen.speichern({"heimnetz": ""}))
        self.assertEqual(workbench.daten_start(self.con, self.pid)["heimnetz"], "192.168.178.0/24")
        self.assertIsNone(abgleich.ansichten(self.con, self.pid)["/api/start"]["heimnetz"])          # online nicht
        self.assertEqual(str(workbench.heimnetz()), "192.168.178.0/24")
        with open(os.path.join(os.path.dirname(__file__), "..", "amw", "workbench.html"), encoding="utf-8") as f:
            html = f.read()
        for x in ('e_heimnetz: "Aus dem Heimnetz erreichbar"', 'e_heimnetz: "Reachable from the home network"',
                  "Jedes Gerät in diesem Netz hat volle Rechte ohne Anmeldung.", "Every device in this network has full rights without signing in.",
                  're_heimnetz: "Heimnetz offen: {x} – jedes Gerät dort hat volle Rechte."', 'pcFeld("heimnetz"'):
            self.assertIn(x, html)
        self.assertTrue(json.loads(json.dumps(workbench.daten_einstellungen(self.con, self.pid)["pc"]))["heimnetz"])


if __name__ == "__main__":
    unittest.main()
