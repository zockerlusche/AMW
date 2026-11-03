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

    def test_nachtrag_nur_in_der_frage_und_beim_antworten_erledigt(self):
        con = db.verbinde()
        kern.frage_nachtrag(con, self.pid, "TL", self.fid, "Noch ein Gedanke")
        kern.posten(con, self.pid, "TL", "Entwickler", "meldung", "Bericht")
        d = workbench.daten_start(con, self.pid)
        self.assertEqual([n["kurz"] for n in d["an_dich"]], ["Bericht"])          # Nachtrag steht nur in der Frage
        self.assertEqual(d["fragen"][0]["nachtraege"], 1)
        kern.frage_antworten(con, self.pid, self.fid, "option", "A", "seite")
        offen = con.execute("SELECT count(*) FROM empfang WHERE agent = 'Entwickler' AND status != 'erledigt'").fetchone()[0]
        con.close()
        self.assertEqual(offen, 1)                                                 # nur noch der Bericht

    def test_board_zeigt_woran_agenten_gerade_arbeiten_und_notizen(self):
        from amw import wissen
        con = db.verbinde()
        kern.agent_neu(con, self.pid, "CC1")
        with db.schreiben(con):
            aid = db.einfuegen(con, "aufgabe", projekt_id=self.pid, titel="Bauen", agent="CC1", angelegt_utc=db.jetzt(), angelegt_von="TL", id=1234)
            db.einfuegen(con, "sitzung", agent_id=con.execute("SELECT id FROM agent WHERE kennung = 'CC1'").fetchone()[0],
                         gestartet_utc=db.jetzt(), taetigkeit=f"A{aid} baut")
        wissen.notiz_setzen(con, self.pid, "TL", "stand", "alles gut")
        con.close()
        liste = json.loads(self.anfrage("GET", "/api/aufgaben?sicht=offen")[1])
        self.assertEqual(next(x for x in liste if x["id"] == aid)["jetzt"], "CC1")
        self.assertEqual(json.loads(self.anfrage("GET", "/api/wissen")[1])["notizen"][0]["schluessel"], "stand")

    def test_planung_lesen_bogen_anlegen_und_freigeben(self):
        from amw import planung
        kopf = {"X-AMW-Token": self.token}
        status, text = self.anfrage("POST", "/api/plan/bogen", {"aktion": "neu", "titel": "Login", "abnahme": "Test grün",
                                                                "zieldatum": "2026-12-01"}, kopf)
        self.assertEqual(status, 200, text)
        bid = json.loads(text)["bogen"]
        con = db.verbinde()
        planung.spec_schreiben(con, self.pid, "TL", bid, "anforderungen", "R1 Anmelden")
        planung.spec_vorlegen(con, self.pid, "TL", bid, "anforderungen")
        con.close()
        d = json.loads(self.anfrage("GET", "/api/planung")[1])
        self.assertEqual(d["boegen"][0]["specs"]["anforderungen"]["status"], "vorgelegt")
        self.assertEqual(len(d["wartet"]["spezifikationen"]), 1)
        self.assertEqual(json.loads(self.anfrage("GET", "/api/start")[1])["zaehler"]["freigaben"], 1)
        status, text = self.anfrage("POST", "/api/plan/spec", {"bogen": bid, "teil": "anforderungen", "frei": False}, kopf)
        self.assertEqual(status, 400)                                             # zurück nur mit Kommentar
        status, _ = self.anfrage("POST", "/api/plan/spec", {"bogen": bid, "teil": "anforderungen", "frei": True}, kopf)
        self.assertEqual(status, 200)
        d = json.loads(self.anfrage("GET", "/api/planung")[1])
        self.assertEqual(d["boegen"][0]["specs"]["anforderungen"]["status"], "frei")
        self.assertEqual(d["heute"], __import__("datetime").date.today().isoformat())
        befund = next(x for x in d["pruefung"] if x["code"] == "keine_dod")                 # Plan-Check: Texte + akzeptieren
        self.assertEqual(d["check_texte"]["keine_dod"]["ziel"], "leitbild")
        status, _ = self.anfrage("POST", "/api/plan/check", {"schluessel": befund["schluessel"], "grund": "kommt später"}, kopf)
        self.assertEqual(status, 200)
        d = json.loads(self.anfrage("GET", "/api/planung")[1])
        self.assertEqual(next(x for x in d["pruefung"] if x["code"] == "keine_dod")["akzeptiert"]["grund"], "kommt später")
        self.assertIn("start", d["boegen"][0]["prognose"] or {"start": None})

    def test_skript_der_seite_ist_gueltiges_javascript(self):
        """Ein Syntaxfehler lässt die ganze Seite leer – mit node prüfen, wenn vorhanden."""
        import shutil
        import subprocess
        node = shutil.which("node")
        if not node:
            self.skipTest("node nicht installiert")
        html = open(os.path.join(os.path.dirname(workbench.__file__), "workbench.html"), encoding="utf-8").read()
        skript = html[html.index("<script>") + 8:html.rindex("</script>")]
        datei = os.path.join(self.ordner.name, "seite.js")
        with open(datei, "w", encoding="utf-8") as f:
            f.write(skript)
        r = subprocess.run([node, "--check", datei], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])

    def test_verlauf_heute_beginnt_lokal_um_mitternacht(self):
        import datetime
        con = db.verbinde()
        kern.posten(con, self.pid, "Entwickler", "TL", "info", "gerade eben")
        con.close()
        d = json.loads(self.anfrage("GET", "/api/verlauf?tage=1")[1])
        mitternacht = datetime.datetime.combine(datetime.date.today(), datetime.time.min).astimezone(datetime.timezone.utc)
        self.assertEqual(d["ab"], mitternacht.strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.assertTrue(any(e["text"] == "gerade eben" for e in d["ereignisse"]))

    def test_belegter_port_wird_abgelehnt(self):
        with self.assertRaises(OSError):
            workbench.starten(self.port)

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
        status, text = self.anfrage("POST", f"/api/frage/{self.fid}/antwort", {"art": "option", "wert": "A"},
                                    {"X-AMW-Token": "von-vor-dem-neustart"})
        self.assertEqual((status, json.loads(text).get("neu_laden")), (403, True))   # Seite sagt: neu laden
        status, text = self.anfrage("POST", f"/api/frage/{self.fid}/antwort", {"art": "option", "wert": "A"},
                                    {"X-AMW-Token": self.token, "Origin": "http://boese.example"})
        self.assertEqual((status, json.loads(text).get("neu_laden")), (403, None))    # fremde Herkunft: kein Hinweis
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
