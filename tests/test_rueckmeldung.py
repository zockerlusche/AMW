"""Rückmeldevertrag (A1857, M50 S5b; D1258 v14 §6a): Schema, Connector (stdio, ein Werkzeug, kein Schlüssel), letzte gültige
Meldung, ungeprüft gespeichert, Kosten automatisch, `amw paket ergebnis` nur durch den zugeteilten Agenten, Auftragsvorlage."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from amw import arbeiter, arbeitspaket, cli, db, kern, platz, rueckmeldung as rm

OHNE = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ATTRAPPE = [sys.executable, "-X", "utf8", os.path.join(os.path.dirname(os.path.abspath(__file__)), "arbeiter_attrappe.py")]
GUT = {"status": "erledigt", "zusammenfassung": "Hilfetext ergänzt."}


class Schema(unittest.TestCase):
    def test_gueltig_und_beispiel(self):
        self.assertEqual(rm.pruefen(GUT), [])
        self.assertEqual(rm.pruefen(json.loads(rm.BEISPIEL)), [])                              # Beispiel im Auftrag ist gültig
        self.assertEqual(rm.pruefen({"status": "blockiert", "zusammenfassung": "x", "frage": "Wohin?", "frage_an": "mensch"}), [])
        self.assertEqual(rm.pruefen({"status": "aufgegeben", "zusammenfassung": "x", "grund": "geht nicht", "hinweis": "h"}), [])
        self.assertFalse(rm.SCHEMA["additionalProperties"])

    def test_abgelehnt(self):
        for m, wort in (([], "JSON-Objekt"), ({"status": "erledigt"}, "zusammenfassung fehlt"),
                        ({"zusammenfassung": "x"}, "status fehlt"), ({"status": "fertig", "zusammenfassung": "x"}, "erlaubt"),
                        ({"status": "blockiert", "zusammenfassung": "x"}, "frage Pflicht"),
                        ({"status": "aufgegeben", "zusammenfassung": "x"}, "grund Pflicht"),
                        (dict(GUT, commits=["a1"]), "Unbekannte Felder"), (dict(GUT, frage_an="lead"), "frage_an gehört"),
                        (dict(GUT, zusammenfassung="x" * 500), "länger"), (dict(GUT, status=1), "Text"),
                        (dict(GUT, hinweis="h" * 1999, grund="g" * 1999, frage="f" * 1999,
                              zusammenfassung="z" * 399, frage_an="lead", status="blockiert"), None)):
            with self.subTest(m=str(m)[:40]):
                f = rm.pruefen(m)
                if wort:
                    self.assertTrue(any(wort in x for x in f), f)
        self.assertTrue(any("größer" in x for x in rm.pruefen(dict(GUT, hinweis="ä" * 1999, grund="ö" * 1999, frage="ü" * 1999))
                            + rm.pruefen({**GUT, **{f"x{i}": "y" * 1000 for i in range(25)}})))


class Connector(unittest.TestCase):
    """Der echte Connector über stdio – gestartet wie im Lauf: python -I <absoluter Pfad>, Arbeitsordner = ein fremder Ordner."""

    def sprechen(self, nachrichten, cwd):
        cfg = rm.mcp_config(rm.einstieg())["mcpServers"][rm.NAME]
        ein = "\n".join(json.dumps(n) for n in nachrichten) + "\n"
        r = subprocess.run([cfg["command"], *cfg["args"]], input=ein, capture_output=True, text=True, encoding="utf-8", cwd=cwd,
                           creationflags=OHNE, timeout=60)
        return [json.loads(z) for z in r.stdout.splitlines() if z.strip()]

    def test_ein_werkzeug_annehmen_ablehnen(self):
        with tempfile.TemporaryDirectory() as o:
            os.makedirs(os.path.join(o, "amw"))                                                   # untergeschobenes Paket im Klon
            for name in ("__init__.py", "rueckmeldung.py"):
                with open(os.path.join(o, "amw", name), "w") as f:
                    f.write("raise SystemExit('fremder Code geladen')\n")
            a = self.sprechen([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                               {"jsonrpc": "2.0", "method": "notifications/initialized"},
                               {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                               {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": rm.WERKZEUG, "arguments": GUT}},
                               {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                                "params": {"name": rm.WERKZEUG, "arguments": {"status": "blockiert", "zusammenfassung": "x"}}},
                               {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "lesen", "arguments": {}}}], o)
        self.assertEqual(len(a), 5)                                                               # die Benachrichtigung ohne Antwort
        self.assertEqual(a[0]["result"]["serverInfo"]["name"], rm.NAME)
        werkzeuge = a[1]["result"]["tools"]
        self.assertEqual([w["name"] for w in werkzeuge], [rm.WERKZEUG])                           # genau eins
        self.assertFalse(werkzeuge[0]["inputSchema"]["additionalProperties"])
        self.assertFalse(a[2]["result"]["isError"])
        self.assertTrue(a[3]["result"]["isError"])
        self.assertIn("frage Pflicht", a[3]["result"]["content"][0]["text"])
        self.assertIn("Schema:", a[3]["result"]["content"][0]["text"])                            # Fehler samt Schema
        self.assertIn("error", a[4])                                                              # nichts sonst

    def test_connector_und_vorlage_gesperrt(self):
        from amw import abnahme
        for pfad in ("amw/rueckmeldung.py", "amw/vorlagen/auftrag_p.md", "amw-rueckmeldung.py"):
            self.assertTrue(abnahme.gesperrt([pfad]), pfad)                                       # ein p-Paket ändert sie nie

    def test_config_ohne_schluessel(self):
        c = rm.mcp_config(rm.einstieg())["mcpServers"][rm.NAME]
        self.assertEqual(c["args"][:3], ["-I", "-X", "utf8"])
        self.assertTrue(os.path.isabs(c["args"][3]))
        self.assertEqual(c["env"], {})                                                           # kein Schlüssel, nichts in der Umgebung


class Auswertung(unittest.TestCase):
    def ereignisse(self, *aufrufe):
        e = []
        for i, (m, ok) in enumerate(aufrufe):
            e.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"t{i}", "name": rm.VOLL, "input": m}]}})
            e.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"t{i}", "is_error": not ok}]}})
        return e

    def test_letzte_gueltige(self):
        blockiert = {"status": "blockiert", "zusammenfassung": "x", "frage": "Wohin?"}
        self.assertEqual(rm.auswerten(self.ereignisse((GUT, True), (blockiert, True))), (blockiert, 2))
        self.assertEqual(rm.auswerten(self.ereignisse((GUT, True), ({"status": "x"}, False))), (GUT, 2))   # abgelehnter zählt nicht
        self.assertEqual(rm.auswerten(self.ereignisse(({"status": "fertig", "zusammenfassung": "x"}, True))), (None, 1))  # AMW prüft selbst
        self.assertEqual(rm.auswerten([]), (None, 0))
        ohne_id = [{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": rm.VOLL, "input": GUT}]}},
                   {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": None, "is_error": False}]}}]
        self.assertEqual(rm.auswerten(ohne_id), (None, 0))                                         # P267: ohne id verworfen
        self.assertEqual(rm.auswerten([{"type": "user", "message": {"content": "nur Text"}}, {"type": "system", "message": "nur Text"}] + self.ereignisse((GUT, True))), (GUT, 1))


@unittest.skipUnless(os.name == "nt", "Job-Objekt nur unter Windows")
class Lauf(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.p = platz.pfade(os.path.join(self.ordner.name, "plaetze"), 1)
        os.makedirs(self.p["klon"])
        subprocess.run(["git", "init", "-q", "-b", "main", self.p["klon"]], check=True, capture_output=True, creationflags=OHNE)
        self.aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Hilfe ergänzen", "TL", auftrag="Den Export erklären.")

    def laufen(self, meldungen=(), **zusatz):
        z = {"ATTRAPPE_MELDUNGEN": json.dumps(list(meldungen)), **zusatz}
        return arbeiter.laufen(self.p, "x", "python -m unittest", modell="haiku", prog=ATTRAPPE, zusatz=z,
                               con=self.con, pid=self.pid, aid=self.aid)

    def test_meldung_ungeprueft_gespeichert_und_kosten(self):
        r = self.laufen([GUT, dict({"status": "blockiert", "zusammenfassung": "y", "frage": "Wohin?"}, _ok=False)])
        self.assertEqual(r["abweichungen"], [])
        self.assertEqual((r["meldung"], r["meldeversuche"]), (GUT, 2))                            # der abgelehnte zählt nicht
        e = rm.letzte(self.con, self.pid, self.aid)
        self.assertEqual((e["meldung"], e["quelle"]), (GUT, "p"))
        self.assertIn("ungeprüft", e["vertrauen"])
        k = json.loads(self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'kosten' AND aufgabe_id = ?", (self.aid,)).fetchone()[0])
        self.assertEqual(k["usd"], 0.001)                                                         # Kosten automatisch
        with open(os.path.join(arbeiter.ordner(self.p), "einstellungen.json"), encoding="utf-8") as f:
            self.assertIn(rm.VOLL, json.load(f)["permissions"]["allow"])                          # genau das eine Werkzeug frei

    def test_ohne_gueltige_meldung_keine_und_kosten_trotzdem(self):
        r = self.laufen([])
        self.assertIsNone(r["meldung"])
        self.assertIsNone(rm.letzte(self.con, self.pid, self.aid))
        self.assertEqual(self.con.execute("SELECT count(*) FROM plan_ereignis WHERE art = 'kosten'").fetchone()[0], 1)

    def test_connector_nicht_verbunden_beendet(self):
        r = self.laufen([GUT], ATTRAPPE_MCP_STATUS="failed")
        self.assertTrue(any("nicht verbunden" in a for a in r["abweichungen"]), r["abweichungen"])
        self.assertIsNone(r["meldung"])


    @unittest.skipUnless(os.environ.get("AMW_ECHTER_CLAUDE") == "1", "echter claude -p kostet Tokens – nur mit AMW_ECHTER_CLAUDE=1")
    def test_echt_meldung_kommt_an(self):
        """Mit echtem Claude Code (Haiku): der Connector ist im init verbunden, die Meldung kommt über ergebnis_melden an."""
        auftrag = ("Lege die Datei innen.txt mit dem Inhalt eins an. Melde danach über das Werkzeug ergebnis_melden: "
                   + rm.BEISPIEL.replace("Hilfetext für den Export ergänzt und Test dazu geschrieben.", "innen.txt angelegt."))
        r = arbeiter.laufen(self.p, auftrag, "python -m unittest", modell="haiku", effort="low", con=self.con, pid=self.pid, aid=self.aid)
        self.assertEqual(r["abweichungen"], [])
        self.assertEqual([(m["name"], m["status"]) for m in r["init"]["mcp_servers"]], [(rm.NAME, "connected")])
        self.assertEqual(r["meldung"]["status"], "erledigt")
        self.assertEqual(rm.letzte(self.con, self.pid, self.aid)["meldung"]["status"], "erledigt")


class Interaktiv(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        pfad = os.path.join(self.ordner.name, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": pfad, "AMW_AGENT": "CC1"})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid, "CC2")
        self.aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Seite bauen", "CC1")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'laeuft' WHERE id = ?", (self.aid,))

    def cli(self, *args, stdin=None):
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus), mock.patch("sys.stdin", io.StringIO(stdin or "")):
            cli.cmd_paket(cli.parser().parse_args(["paket", "ergebnis", str(self.aid), *args, "--projekt", "Spiel", "--von", "CC1"]), self.con)
        return aus.getvalue()

    def test_ueber_stdin_und_schalter(self):
        self.assertIn("angenommen", self.cli("--json", "-", stdin=json.dumps(GUT)))
        self.assertEqual(rm.letzte(self.con, self.pid, self.aid)["meldung"], GUT)
        self.assertIn("angenommen", self.cli("--status", "blockiert", "--zusammenfassung", "halb", "--frage", "Welche Farbe?",
                                             "--frage-an", "mensch"))
        e = rm.letzte(self.con, self.pid, self.aid)
        self.assertEqual((e["meldung"]["frage_an"], e["quelle"], e["von"]), ("mensch", "agent", "CC1"))
        with self.assertRaises(kern.AmwFehler):                                                  # JSON als Argument: nein
            self.cli("--json", json.dumps(GUT))
        with self.assertRaises(kern.AmwFehler):                                                  # Schema verletzt
            self.cli("--status", "blockiert", "--zusammenfassung", "x")

    def test_nur_zugeteilt_art_und_laufend(self):
        with self.assertRaises(kern.AmwFehler):                                                  # anderer Agent
            rm.melden_interaktiv(self.con, self.pid, "CC2", self.aid, GUT, {"AMW_AGENT": "CC2"})
        with self.assertRaises(kern.AmwFehler):                                                  # --von stimmt, Sitzung nicht
            rm.melden_interaktiv(self.con, self.pid, "CC1", self.aid, GUT, {"AMW_AGENT": "CC2"})
        with self.assertRaises(kern.AmwFehler):                                                  # ohne Sitzung (AMW_AGENT fehlt)
            rm.melden_interaktiv(self.con, self.pid, "CC1", self.aid, GUT, {})
        arbeitspaket.setzen(self.con, self.pid, "TL", self.aid, art="p")
        with self.assertRaises(kern.AmwFehler) as e:                                              # Art p meldet über den Connector
            rm.melden_interaktiv(self.con, self.pid, "CC1", self.aid, GUT, {"AMW_AGENT": "CC1"})
        self.assertIn("Rückmelde-Zugang", str(e.exception))
        arbeitspaket.setzen(self.con, self.pid, "TL", self.aid, art="sitzung")
        rm.melden_interaktiv(self.con, self.pid, "CC1", self.aid, GUT, {"AMW_AGENT": "CC1"})
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'wartet' WHERE id = ?", (self.aid,))
        with self.assertRaises(kern.AmwFehler):                                                  # läuft nicht
            rm.melden_interaktiv(self.con, self.pid, "CC1", self.aid, GUT, {"AMW_AGENT": "CC1"})

    def test_auftrag_aus_vorlage(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET auftrag = 'Export erklären.', pruefbefehl = 'python -m unittest tests.test_x',"
                             " dateibereich = 'doc/hilfe/' WHERE id = ?", (self.aid,))
        rm.speichern(self.con, self.pid, "CC1", self.aid, dict(GUT, hinweis="GEHEIMER-HINWEIS"), "agent")
        t = rm.auftrag(self.con, self.pid, self.aid)
        for teil in (f"A{self.aid}", "Seite bauen", "Export erklären.", "doc/hilfe/", "python -m unittest tests.test_x",
                     "ergebnis_melden", "Du committest nicht", rm.BEISPIEL):
            self.assertIn(teil, t)
        self.assertNotIn("GEHEIMER-HINWEIS", t)                                                   # hinweis nie in einen Auftrag
        self.assertNotIn("{{", t)


if __name__ == "__main__":
    unittest.main()
