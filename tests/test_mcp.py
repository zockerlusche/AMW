"""MCP-Server der AMW (A1781): ein echter Testclient startet `amw-mcp.py` wie die Claude-App (stdio, JSON-RPC 2.0, eine
Nachricht je Zeile) und prüft Handshake, Werkzeugliste mit Pflichtfeldern, Aufrufe und Fehler."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from amw import db, kern, mcp_schluessel, mcp_server

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Client:
    """Kleinster MCP-Client: schreibt Anfragen, liest je Anfrage eine Antwortzeile."""

    def __init__(self, umgebung, projekt="Spiel", von="TL"):
        self.p = subprocess.Popen([sys.executable, os.path.join(WURZEL, "amw-mcp.py"), "--projekt", projekt, "--von", von],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=umgebung,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.n = 0

    def senden(self, methode, params=None, benachrichtigung=False):
        n = {"jsonrpc": "2.0", "method": methode}
        if params is not None:
            n["params"] = params
        if not benachrichtigung:
            self.n += 1
            n["id"] = self.n
        self.p.stdin.write((json.dumps(n) + "\n").encode("utf-8"))
        self.p.stdin.flush()
        if benachrichtigung:
            return None
        return json.loads(self.p.stdout.readline().decode("utf-8"))

    def werkzeug(self, name, args=None, schluessel=True):
        a = dict(args or {})
        if schluessel is True:
            a["schluessel"] = self.schluessel
        elif schluessel:
            a["schluessel"] = schluessel
        return self.senden("tools/call", {"name": name, "arguments": a})["result"]

    def zu(self):
        self.p.stdin.close()
        self.p.wait(30)
        self.p.stdout.close()
        self.p.stderr.close()


class Mcp(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        pfad = os.path.join(self.ordner.name, "amw.db")
        con = db.anlegen(pfad)
        with db.schreiben(con):
            pid = db.einfuegen(con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(con, pid, "TL", rolle="lead")
        kern.agent_neu(con, pid, "CC1")
        self.nid, _ = kern.posten(con, pid, "CC1", "TL", "info", "Stand A12", "Alles grün")
        con.close()
        lad = os.path.join(self.ordner.name, "lad")          # A1826: Schlüssel liegt außerhalb von Repo/DB (hier: Test-Ordner)
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": lad}):
            schluessel = mcp_schluessel.erzeugen("Spiel")
        umgebung = dict(os.environ, AMW_DB=pfad, LOCALAPPDATA=lad)
        umgebung.pop("AMW_AGENT", None)
        self.pfad, self.lad = pfad, lad
        self.c = Client(umgebung)
        self.c.schluessel = schluessel
        self.addCleanup(self.c.zu)

    def test_handshake_liste_und_aufrufe(self):
        r = self.c.senden("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}})
        self.assertEqual(r["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(r["result"]["serverInfo"]["name"], "amw")
        self.assertIn("tools", r["result"]["capabilities"])
        self.c.senden("notifications/initialized", benachrichtigung=True)                 # keine Antwort
        werkzeuge = {w["name"]: w for w in self.c.senden("tools/list")["result"]["tools"]}
        self.assertTrue({"takt", "lesen", "posten", "erledigt", "aufgabe_zeige", "pruefung_urteil", "freigabe_merge", "frage_neu",
                         "runde_lesen", "lauf_vorziehen", "suche", "dokument_zeigen", "schirm"} <= set(werkzeuge))
        self.assertEqual(werkzeuge["posten"]["inputSchema"]["required"], ["schluessel", "an", "art", "kurz"])
        self.assertNotIn("von", werkzeuge["posten"]["inputSchema"]["properties"])      # Identität nicht wählbar
        t = self.c.werkzeug("takt")
        self.assertFalse(t["isError"])
        self.assertIn("TAKT Spiel/TL", t["content"][0]["text"])
        self.assertIn(f"#{self.nid}", t["content"][0]["text"])
        r = self.c.werkzeug("posten", {"an": "CC1", "art": "auftrag", "kurz": "Bitte A12 abschließen"})
        self.assertFalse(r["isError"], r)
        r = self.c.werkzeug("lesen", {"ids": [self.nid]})
        self.assertIn("Alles grün", r["content"][0]["text"])
        self.assertEqual(self.c.senden("ping")["result"], {})

    def test_lead_arbeitet_ueber_werkzeuge(self):
        self.c.senden("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}})
        r = self.c.werkzeug("aufgabe_neu", {"titel": "Menü aufräumen", "agent": "CC1", "ohne_bogen": True, "kriterien": ["7 Punkte"]})
        self.assertFalse(r["isError"], r)
        nr = int(r["content"][0]["text"].split("A", 1)[1].split()[0])
        r = self.c.werkzeug("aufgabe_zeige", {"id": nr})
        self.assertIn("Menü aufräumen", r["content"][0]["text"])
        self.assertIn("7 Punkte", r["content"][0]["text"])
        self.assertIn("Menü aufräumen", self.c.werkzeug("suche", {"text": "Menü"})["content"][0]["text"])
        self.assertFalse(self.c.werkzeug("erledigt", {"ids": [self.nid]})["isError"])
        self.assertIn("nichts offen", self.c.werkzeug("lesen")["content"][0]["text"])
        self.assertFalse(self.c.werkzeug("schirm")["isError"])

    def test_ohne_richtigen_schluessel_keinerlei_wirkung_und_protokoll(self):
        """A1826 (16.11.: der GlassWorld-Lead las über diesen Connector das AMW-Postfach): falscher oder fehlender Schlüssel →
        Ablehnung, nichts gelesen, nichts als gelesen markiert; jeder Aufruf steht im Verlauf."""
        for falsch in ("amw-falsch", None):
            r = self.c.werkzeug("lesen", schluessel=falsch) if falsch else self.c.senden("tools/call", {"name": "lesen", "arguments": {}})["result"]
            self.assertTrue(r["isError"])
            self.assertIn("Abgelehnt: Dieser Connector gehört zu Projekt Spiel (TL)", r["content"][0]["text"])
            self.assertNotIn("Stand A12", r["content"][0]["text"])
        con = db.verbinde(self.pfad)
        self.addCleanup(con.close)
        self.assertEqual(con.execute("SELECT status FROM empfang WHERE nachricht_id = ?", (self.nid,)).fetchone()[0], "offen")
        self.assertFalse(self.c.werkzeug("lesen")["isError"])                               # mit Schlüssel geht es
        protokoll = [r[0] for r in con.execute("SELECT text FROM plan_ereignis WHERE art = 'mcp_aufruf' ORDER BY id")]
        self.assertEqual(protokoll, ["MCP lesen: abgelehnt – falscher oder fehlender Schlüssel"] * 2 + ["MCP lesen: ok"])
        werkzeuge = self.c.senden("tools/list")["result"]["tools"]
        self.assertTrue(all(w["inputSchema"]["required"][0] == "schluessel" for w in werkzeuge))
        self.assertTrue(werkzeuge[0]["description"].startswith("[Projekt Spiel · Zugang von TL]"))

    def test_aufruf_ist_lebenszeichen_des_chat_leads(self):
        """A1831 (16.11.: Chat-Leads standen als „beendet“): jeder angenommene Aufruf setzt den Puls wie der Dateiaustausch;
        abgelehnte nicht. agent liste zeigt einen Chat als „aktiv (Chat)“ bzw. „zuletzt … (Chat)“, nie als „beendet“."""
        import contextlib
        import io
        from amw import cli
        con = db.verbinde(self.pfad)
        self.addCleanup(con.close)
        with db.schreiben(con):
            con.execute("UPDATE agent SET arbeitsweise = 'chat' WHERE kennung = 'TL'")
        sitzung = lambda: con.execute("SELECT s.zustand, s.letzter_puls_utc FROM sitzung s JOIN agent a ON a.id = s.agent_id"
                                      " WHERE a.kennung = 'TL' ORDER BY s.id DESC LIMIT 1").fetchone()
        self.c.werkzeug("lesen", schluessel="amw-falsch")
        self.assertIsNone(sitzung())
        self.assertFalse(self.c.werkzeug("takt")["isError"])
        self.assertEqual(sitzung()["zustand"], "aktiv")

        def liste():
            aus = io.StringIO()
            with mock.patch.dict(os.environ, {"AMW_DB": self.pfad}), contextlib.redirect_stdout(aus):
                cli.main(["agent", "liste", "--projekt", "Spiel", "--von", "Entwickler"])
            return next(z for z in aus.getvalue().splitlines() if z.startswith("TL "))
        self.assertIn("ist aktiv (Chat)", liste())
        with db.schreiben(con):
            con.execute("UPDATE sitzung SET zustand = 'beendet'")
        self.assertRegex(liste(), r"ist zuletzt .+ \(Chat\)")
        self.assertNotIn("beendet", liste())

    def test_fehler_kommen_als_fehler_zurueck(self):
        self.c.senden("initialize", {"protocolVersion": "1999-01-01", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}})
        r = self.c.werkzeug("posten", {"an": "CC1", "art": "auftrag"})
        self.assertTrue(r["isError"])
        self.assertIn("Pflichtfeld fehlt: kurz", r["content"][0]["text"])
        r = self.c.werkzeug("posten", {"an": "CC1", "art": "auftrag", "kurz": "x", "von": "Entwickler"})
        self.assertTrue(r["isError"])
        self.assertIn("unbekanntes Feld: von", r["content"][0]["text"])                 # nicht als jemand anderes
        r = self.c.werkzeug("posten", {"an": "Niemand", "art": "auftrag", "kurz": "x"})
        self.assertTrue(r["isError"])                                                   # Prüfung der Befehlszeile greift
        self.assertEqual(self.c.senden("gibtsnicht")["error"]["code"], -32601)
        self.assertTrue(self.c.werkzeug("loeschen")["isError"])


class Schema(unittest.TestCase):
    def test_jedes_werkzeug_hat_gueltiges_schema(self):
        for w in mcp_server.werkzeug_liste():
            self.assertEqual(w["inputSchema"]["type"], "object")
            self.assertTrue(set(w["inputSchema"]["required"]) <= set(w["inputSchema"]["properties"]))
            self.assertTrue(w["description"])

    def test_jedes_werkzeug_ergibt_eine_gueltige_befehlszeile(self):
        """Für jedes Werkzeug mit allen Feldern: die Befehlszeile versteht der echte Parser – kein Werkzeug zeigt ins Leere."""
        from amw import cli
        beispiel = {"s": "x", "m": "M2", "i": 7, "b": True, "ai": [7, 8], "as": ["x"]}
        for name, (_, _, felder) in mcp_server.WERKZEUGE.items():
            args = {f[0]: (([f[5][0]] if f[1] in ("ai", "as") else f[5][0]) if f[5] else beispiel[f[1]]) for f in felder}
            if name == "frage_neu":
                args.update(optionen=["A=x"], empfehlung="A")
            self.assertIsNone(mcp_server._pruefen(name, args), name)
            argv = mcp_server.befehlszeile(name, args) + ["--projekt", "Spiel", "--von", "TL"]
            with self.subTest(werkzeug=name):
                try:
                    cli.parser().parse_args(argv)
                except SystemExit:
                    self.fail(f"{name}: {argv}")

    def test_haengender_befehl_blockiert_nicht_still(self):
        """TL P205: nach dem Zeitlimit hält der hängende Faden die Sperre – weitere Aufrufe bekommen sofort eine Meldung."""
        import threading
        from unittest import mock
        los = threading.Event()
        def langsam(argv):
            los.wait(10)
            return 0, "spät fertig", ""
        s = mcp_server.Server("Spiel", "TL")
        for name in ("stand", "pruefen"):                                                    # Schlüssel hier nicht das Thema
            p = mock.patch.object(mcp_schluessel, name, return_value={"da": True} if name == "stand" else True)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(s, "protokoll")
        p.start()
        self.addCleanup(p.stop)
        with mock.patch.object(mcp_server, "befehl_ausfuehren", side_effect=langsam), mock.patch.object(mcp_server, "FRIST_S", 0.3):
            r = s.werkzeug("takt", {})
            self.assertTrue(r["isError"])
            self.assertIn("Zeitlimit", r["content"][0]["text"])
            r = s.werkzeug("lesen", {})
            self.assertTrue(r["isError"])
            self.assertIn("vorige Befehl (takt) hängt seit", r["content"][0]["text"])   # sofort, nicht nach weiteren 0,3 s
            los.set()
            for _ in range(50):
                if not s.sperre.locked():
                    break
                time.sleep(0.05)
            r = s.werkzeug("lesen", {})
            self.assertFalse(r["isError"], r)                                          # danach geht es weiter

    def test_keine_optionen_durch_die_hintertuer(self):
        self.assertIn("darf nicht mit -", mcp_server._pruefen("zeige", {"refs": ["--von"]}))
        self.assertIn("darf nicht mit -", mcp_server._pruefen("suche", {"text": "--projekt"}))


if __name__ == "__main__":
    unittest.main()
