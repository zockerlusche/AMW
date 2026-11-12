"""Tests für die Gesprächsansicht je Agent: Protokoll von hinten lesen, blättern, live anhängen, Einträge einordnen,
Geheimnisse verdecken, „In Claude öffnen“ nur bei laufender Sitzung, online nur auf Wunsch und nur Text."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import abgleich, db, gespraech, kern, workbench

SID = "11111111-2222-3333-4444-555555555555"
SID2 = "66666666-7777-8888-9999-000000000000"


def zeile(**d):
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))


def mensch(text, zeit="2026-11-02T10:00:00Z", **x):
    return zeile(parentUuid=None, isSidechain=False, type="user", message={"role": "user", "content": text}, timestamp=zeit, **x)


def claude(*bloecke, zeit="2026-11-02T10:00:01Z", sidechain=False):
    return zeile(parentUuid="x", isSidechain=sidechain, type="assistant",
                 message={"role": "assistant", "content": list(bloecke)}, timestamp=zeit)


def ergebnis(tid, text, fehler=False):
    return zeile(parentUuid="x", isSidechain=False, type="user", timestamp="2026-11-02T10:00:02Z",
                 message={"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": text, "is_error": fehler}]})


class Gespraech(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.alt = {k: os.environ.get(k) for k in ("AMW_DB", "CLAUDE_CONFIG_DIR")}
        os.environ["AMW_DB"] = os.path.join(self.ordner.name, "amw.db")
        os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(self.ordner.name, "claude")
        self.con = db.anlegen()
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid, "CC2")
        self.arbeitsordner = "F:\\proj ekt"
        self.proto = os.path.join(self.ordner.name, "claude", "projects", "F--proj-ekt", SID + ".jsonl")
        os.makedirs(os.path.dirname(self.proto))
        aid = self.con.execute("SELECT id FROM agent WHERE kennung = 'CC1'").fetchone()[0]
        with db.schreiben(self.con):
            db.einfuegen(self.con, "sitzung", agent_id=aid, claude_sitzung=SID, arbeitsordner=self.arbeitsordner,
                         gestartet_utc="2026-11-02T09:00:00Z", zustand="aktiv")

    def tearDown(self):
        self.con.close()
        for k, v in self.alt.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.ordner.cleanup()

    def schreiben(self, zeilen, modus="w", ende="\n"):
        with open(self.proto, modus, encoding="utf-8", newline="") as f:
            f.write("\n".join(zeilen) + ende)

    def test_einordnen_und_verdecken(self):
        self.schreiben([
            zeile(type="api-request-blob", message={"role": "user", "content": "geheim intern"}),
            zeile(type="ai-title", aiTitle="Agent baut A12", sessionId=SID),
            mensch("Bitte A12 bauen, token=abc123456"),
            claude({"type": "thinking", "thinking": "…"}, {"type": "text", "text": "Mache ich."}),
            claude({"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls -la", "description": "Ordner ansehen"}}),
            ergebnis("t1", "datei.txt sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWX", fehler=True),
            claude({"type": "text", "text": "Unteragent"}, sidechain=True),
            mensch("<task-notification>\n<summary>Lauf fertig</summary>\n</task-notification>", promptSource="system"),
            mensch("Another Claude session sent a message:\nAMW-Weckruf für CC1: 1 neue Nachricht", isMeta=True,
                   origin={"kind": "peer"}),
            mensch("[Image: original 3840x1600]", isMeta=True),
            mensch("<command-name>/compact</command-name><command-args></command-args>"),
            zeile(type="system", subtype="compact_boundary", content="Conversation compacted", timestamp="2026-11-02T10:05:00Z"),
        ])
        r = gespraech.lesen(self.proto)
        arten = [e["art"] for e in r["eintraege"]]
        self.assertEqual(arten, ["mensch", "claude", "werkzeug", "ergebnis", "hinweis", "weckruf", "befehl", "hinweis"])
        self.assertEqual(r["titel"], "Agent baut A12")
        self.assertTrue(r["anfang"])
        e = r["eintraege"]
        self.assertIn("token=•••", e[0]["text"])
        self.assertEqual((e[2]["name"], e[2]["kurz"], e[2]["id"]), ("Bash", "Ordner ansehen", "t1"))
        self.assertTrue(e[3]["fehler"])
        self.assertNotIn("sk-ant", e[3]["text"])
        self.assertEqual(e[4]["text"], "Lauf fertig")
        self.assertIn("1 neue Nachricht", e[5]["text"])
        self.assertEqual(e[6]["text"], "/compact")
        # online: nur Text und Werkzeugnamen – keine Eingaben, keine Ergebnisse
        on = gespraech.lesen(self.proto, online=True)["eintraege"]
        self.assertNotIn("ergebnis", [x["art"] for x in on])
        self.assertTrue(all("eingabe" not in x for x in on))
        self.assertNotIn("geheim intern", json.dumps(on))

    def test_blaettern_live_und_lange_zeilen(self):
        alle = []
        for i in range(60):
            alle.append(mensch(f"Frage {i}"))
            alle.append(claude({"type": "text", "text": f"Antwort {i} " + ("x" * (5000 if i == 30 else 10))}))
        self.schreiben(alle)
        with mock.patch.object(gespraech, "FENSTER", 1024):          # kleine Fenster: lange Zeilen erzwingen das Ausholen
            r = gespraech.lesen(self.proto, anzahl=25)
            self.assertEqual(len(r["eintraege"]), 25)
            self.assertFalse(r["anfang"])
            gesammelt = r["eintraege"]
            while not r["anfang"]:
                r = gespraech.lesen(self.proto, vor=r["vor"], anzahl=25)
                gesammelt = r["eintraege"] + gesammelt
        self.assertEqual([e["text"][:12] for e in gesammelt],
                         [e["text"][:12] for e in gespraech.lesen(self.proto, anzahl=10_000)["eintraege"]])
        self.assertEqual(len(gesammelt), 120)
        ab = gespraech.lesen(self.proto)["ab"]
        self.schreiben([mensch("neu")], "a", ende="")                 # Zeile noch nicht fertig geschrieben
        self.assertEqual(gespraech.lesen(self.proto, ab=ab)["eintraege"], [])
        self.assertEqual(gespraech.lesen(self.proto)["eintraege"][-1]["text"][:9], "Antwort 5")
        with open(self.proto, "a", encoding="utf-8") as f:
            f.write("\n")
        r = gespraech.lesen(self.proto, ab=ab)
        self.assertEqual([e["text"] for e in r["eintraege"]], ["neu"])
        self.assertEqual(gespraech.lesen(self.proto, ab=r["ab"])["eintraege"], [])

    def test_sitzung_gehoert_zum_agenten_und_link_nur_wenn_er_laeuft(self):
        self.schreiben([mensch("hallo")])
        sitzungen = os.path.join(self.ordner.name, "claude", "sessions")
        os.makedirs(sitzungen)
        with open(os.path.join(sitzungen, f"{os.getpid()}.json"), "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "sessionId": SID, "kind": "interactive", "status": "busy",
                       "bridgeSessionId": "session_01ABCDEFGHIJKLMNOP"}, f)
        with mock.patch("amw.steuerung.lebt", return_value=True), mock.patch("amw.betriebsart.aktuell", return_value="pc"):
            self.assertIsNone(gespraech.daten(self.con, self.pid, "CC1")["link"])     # „Nur dieser PC“: kein Link ins Internet
        with mock.patch("amw.steuerung.lebt", return_value=True), mock.patch("amw.betriebsart.aktuell", return_value="cloud"):
            d = gespraech.daten(self.con, self.pid, "CC1")
            self.assertEqual(d["link"], "https://claude.ai/code/session_01ABCDEFGHIJKLMNOP")
            self.assertEqual((d["status"], d["laeuft"], len(d["eintraege"])), ("busy", True, 1))
            self.assertEqual(workbench.daten_agent(self.con, self.pid, "CC1")["claude_link"], d["link"])
            self.assertNotIn("claude_sitzung", workbench.daten_agent(self.con, self.pid, "CC1"))
        with mock.patch("amw.steuerung.lebt", return_value=False):      # abgestürzt: Datei liegt noch, Link nicht
            self.assertIsNone(gespraech.daten(self.con, self.pid, "CC1")["link"])
        with self.assertRaises(kern.AmwFehler):
            gespraech.daten(self.con, self.pid, "CC2", sitzung=SID)
        self.assertIsNone(gespraech.daten(self.con, self.pid, "CC2")["sitzung"])
        with self.assertRaises(LookupError):
            gespraech.daten(self.con, self.pid, "CC9")
        self.assertIsNone(gespraech.protokoll("../../etwas"))

    def test_online_nur_auf_wunsch(self):
        self.schreiben([mensch("hallo"), claude({"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "C:\\a\\b.py"}}),
                        ergebnis("t1", "inhalt")])
        sp = abgleich.SqliteSpeicher(os.path.join(self.ordner.name, "online.db"))
        ab = abgleich.Abgleich(self.con, sp, self.pid)
        ab.schema()
        uid = self.con.execute("SELECT uid FROM projekt WHERE id = ?", (self.pid,)).fetchone()[0]
        weg = f"{uid}:/api/gespraech?kennung=CC1"
        holen = lambda: sp.ausfuehren([("SELECT inhalt FROM ansicht WHERE weg = ?", [weg])])[0]
        self.assertEqual(ab.gespraeche(), 0)
        self.assertEqual(holen(), [])
        sp.ausfuehren([("INSERT INTO zustand (schluessel, wert) VALUES (?, ?)", [f"gespraech:{uid}:CC1", db.jetzt()]),
                       ("INSERT INTO zustand (schluessel, wert) VALUES (?, ?)", [f"gespraech:{uid}:XX", db.jetzt()])])
        self.assertEqual(ab.gespraeche(), 2)                            # Ansicht hoch, Wunsch für Unbekannte weg
        d = json.loads(holen()[0][0])
        self.assertEqual([e["art"] for e in d["eintraege"]], ["mensch", "werkzeug"])
        self.assertEqual(d["eintraege"][1]["kurz"], "C:/a/b.py")
        self.assertNotIn("ab", d)
        self.assertEqual(ab.gespraeche(), 0)                            # unverändert: nichts hochladen
        sp.ausfuehren([("UPDATE zustand SET wert = '2000-01-01T00:00:00Z' WHERE schluessel = ?", [f"gespraech:{uid}:CC1"])])
        ab.gespraeche()
        self.assertEqual(holen(), [])
        self.assertEqual(sp.ausfuehren([("SELECT count(*) FROM zustand WHERE schluessel LIKE 'gespraech:%'", [])])[0], [[0]])


if __name__ == "__main__":
    unittest.main()
