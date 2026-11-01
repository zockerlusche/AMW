"""Tests für die Workbench-Schnittstelle: Lesen, Antworten, Schutz der Schreibwege."""
import http.client
import json
import os
import socket
import tempfile
import unittest

from amw import db, kern, workbench


def freier_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Workbench(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.alt_db = os.environ.get("AMW_DB")
        os.environ["AMW_DB"] = os.path.join(self.ordner.name, "amw.db")
        con = db.anlegen()
        with db.schreiben(con):
            self.pid = db.einfuegen(con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(con, self.pid, "TL", rolle="lead")
        self.fid = kern.frage_neu(con, self.pid, "TL", "entwickler", "Probe?", [("A", "ja"), ("B", "nein")], "A", "weil")
        con.close()
        self.port = freier_port()
        self.srv = workbench.starten(self.port)
        seite = self.anfrage("GET", "/")[1]
        self.token = seite.split('const TOKEN = "', 1)[1].split('"', 1)[0]

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        if self.alt_db is None:
            os.environ.pop("AMW_DB", None)
        else:
            os.environ["AMW_DB"] = self.alt_db
        self.ordner.cleanup()

    def anfrage(self, methode, weg, daten=None, kopf=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        body = json.dumps(daten).encode() if daten is not None else None
        c.request(methode, weg, body=body, headers={"Content-Type": "application/json", **(kopf or {})})
        r = c.getresponse()
        text = r.read().decode("utf-8")
        c.close()
        return r.status, text

    def test_start_und_fragen(self):
        status, text = self.anfrage("GET", "/api/start")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(text)["zaehler"]["fragen"], 1)
        fragen = json.loads(self.anfrage("GET", "/api/fragen")[1])
        self.assertEqual(fragen[0]["empfehlung"], "A")

    def test_kachel_zaehlt_nur_was_handlung_braucht(self):
        from amw import betrieb
        con = db.verbinde()
        kern.agent_neu(con, self.pid, "CC1")
        kern.posten(con, self.pid, "TL", "CC1", "info", "Lob an alle")              # Info weckt nicht → zählt nicht
        kern.posten(con, self.pid, "TL", "CC1", "auftrag", "Bitte bauen")
        betrieb.pruefbitte(con, self.pid, "TL", "CC1", "tl-x", "abcdef1234")
        con.close()
        cc1 = next(a for a in json.loads(self.anfrage("GET", "/api/start")[1])["agenten"] if a["kennung"] == "CC1")
        self.assertEqual(cc1["offen"], 2)
        d = json.loads(self.anfrage("GET", "/api/agent?kennung=CC1")[1])
        self.assertEqual(len(d["an_ihn"]), 3)                                   # die Übersicht zeigt alles
        self.assertEqual(len(d["pruefungen"]), 1)                               # offene Prüfbitte erscheint

    def test_schreiben_nur_mit_schluessel(self):
        status, _ = self.anfrage("POST", f"/api/frage/{self.fid}/antwort", {"art": "option", "wert": "A"})
        self.assertEqual(status, 403)
        status, _ = self.anfrage("POST", f"/api/frage/{self.fid}/antwort", {"art": "option", "wert": "A"},
                                 {"X-AMW-Token": self.token, "Origin": "http://boese.example"})
        self.assertEqual(status, 403)
        status, text = self.anfrage("POST", f"/api/frage/{self.fid}/antwort", {"art": "option", "wert": "B"},
                                    {"X-AMW-Token": self.token})
        self.assertEqual((status, json.loads(text)["status"]), (200, "beantwortet"))

    def test_halt_ueber_seite(self):
        status, _ = self.anfrage("POST", "/api/halt", {"fuer": "alle", "text": "Pause"}, {"X-AMW-Token": self.token})
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(self.anfrage("GET", "/api/start")[1])["halt"]), 1)
        status, text = self.anfrage("POST", "/api/weiter", {"fuer": "alle"}, {"X-AMW-Token": self.token})
        self.assertEqual(json.loads(text)["aufgehoben"], 1)

    def test_nachricht_an_agent(self):
        status, text = self.anfrage("POST", "/api/nachricht", {"an": "TL", "art": "auftrag", "kurz": "Bitte prüfen"},
                                    {"X-AMW-Token": self.token})
        self.assertEqual((status, json.loads(text)["an"]), (200, ["TL"]))
        status, _ = self.anfrage("POST", "/api/nachricht", {"an": "TL", "art": "stopp", "kurz": "x"},
                                 {"X-AMW-Token": self.token})
        self.assertEqual(status, 400)

    def test_fremder_host_abgewiesen(self):
        status, _ = self.anfrage("GET", "/api/start", kopf={"Host": "boese.example"})
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
