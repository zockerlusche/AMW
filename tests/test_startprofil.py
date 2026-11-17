"""Startprofile (A1865, B2897): Start wie das Startskript (erst fortsetzen, sonst neu mit fester ID), Prüfungen vor dem Start
(Ordner fehlt, Zwilling) und: starten nur der Mensch – nie ein Agent, nie aus einer Claude-Sitzung, nie online."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import base64
import contextlib
import io
import json
import os
from unittest import mock

from amw import aktionen, db, kern, steuerung
from tests.test_steuerung import Grund


class Startprofil(Grund):
    def setUp(self):
        super().setUp()
        self.arbeit = os.path.join(self.ordner.name, "arbeit")
        os.makedirs(self.arbeit)
        steuerung.profil_setzen(self.con, self.pid, "Entwickler", "CC1", ordner=self.arbeit, startsatz="Du bist CC1.")
        self.aid = self.con.execute("SELECT id FROM agent WHERE kennung = 'CC1'").fetchone()[0]

    def zeile(self, args):
        return base64.b64decode(args[-1]).decode("utf-16-le")

    def einstellungen(self, env):
        os.makedirs(os.path.join(self.arbeit, ".claude"), exist_ok=True)
        with open(os.path.join(self.arbeit, ".claude", "settings.local.json"), "w", encoding="utf-8") as f:
            json.dump({"env": env, "hooks": {}}, f)

    def test_fortsetzen_mit_rueckfall_wie_das_startskript(self):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "sitzung", agent_id=self.aid, claude_sitzung="s-42", gestartet_utc=db.jetzt(), zustand="beendet",
                         beendet_utc=db.jetzt())
        self.assertIn("setzt Sitzung s-42", self.starten())
        z = self.zeile(self.gestartet[0])
        self.assertIn("'--resume' 's-42'", z)
        self.assertIn("if ($LASTEXITCODE -ne 0) {", z)                            # Sitzung weg: neu mit fester ID …
        rueck = z.split("if ($LASTEXITCODE -ne 0) {", 1)[1]
        self.assertIn("'--session-id'", rueck)
        self.assertIn("'Du bist CC1.'", rueck)                                    # … und dem Startsatz
        self.assertNotIn("Du bist CC1", z.split("if ($LASTEXITCODE", 1)[0])
        p = steuerung.profil(self.con, self.pid, "CC1")
        self.assertNotIn("LASTEXITCODE", steuerung.befehl(p, "s-1"))               # nur fortsetzen: wie bisher

    def test_ordner_fehlt(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE agent SET ordner = ? WHERE id = ?", (os.path.join(self.ordner.name, "weg"), self.aid))
        with self.assertRaisesRegex(kern.AmwFehler, "gibt es nicht"):
            self.starten()
        self.assertEqual(self.gestartet, [])

    def test_zwilling_ordner_meldet_einen_anderen_an(self):
        self.einstellungen({"AMW_AGENT": "CCamw"})
        with self.assertRaisesRegex(kern.AmwFehler, "Zwilling"):
            self.starten()
        self.einstellungen({"AMW_PROJEKT": "GlassWorld"})
        with self.assertRaisesRegex(kern.AmwFehler, "Projekt GlassWorld"):
            self.starten()
        self.einstellungen({"AMW_AGENT": "CC1", "AMW_PROJEKT": "P"})              # passt: eigener Ordner
        self.assertIn("startet neu", self.starten())

    def test_zwilling_fremder_live_ordner(self):
        with db.schreiben(self.con):
            fremd = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, fremd, "GW1")
        gw1 = self.con.execute("SELECT id FROM agent WHERE kennung = 'GW1'").fetchone()[0]
        kern.agent_neu(self.con, self.pid, "CC2")
        cc2 = self.con.execute("SELECT id FROM agent WHERE kennung = 'CC2' AND projekt_id = ?", (self.pid,)).fetchone()[0]
        with db.schreiben(self.con):                                              # gleiches Projekt, gleicher Ordner: erlaubt
            db.einfuegen(self.con, "sitzung", agent_id=cc2, claude_sitzung="s-cc2", gestartet_utc=db.jetzt(), arbeitsordner=self.arbeit,
                         claude_pid=os.getpid())
        self.assertIn("startet neu", self.starten())
        with db.schreiben(self.con):
            db.einfuegen(self.con, "sitzung", agent_id=gw1, claude_sitzung="s-gw1", gestartet_utc=db.jetzt(), arbeitsordner=self.arbeit,
                         claude_pid=os.getpid())
        with self.assertRaisesRegex(kern.AmwFehler, "GW1 aus Projekt Spiel"):
            self.starten()

    def cli(self, *args, env=None):
        from amw import cli
        aus = io.StringIO()
        umgebung = {"AMW_DB": os.path.join(self.ordner.name, "t.db"), "AMW_AGENT": "", "CLAUDE_CODE_MESSAGING_SOCKET": "", **(env or {})}
        with mock.patch.dict(os.environ, umgebung), contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus), \
                mock.patch.object(steuerung, "starten", return_value="CC1 startet neu (Probe)") as st:
            rc = cli.main(list(args))
        return rc, aus.getvalue(), st.call_count

    def test_nur_der_mensch_startet(self):
        rc, aus, n = self.cli("agent", "starten", "CC1", "--von", "TL")
        self.assertEqual((rc, n), (1, 0))                                                   # ein Agent (auch der Lead): nein
        self.assertIn("nur der Mensch", aus)
        rc, aus, n = self.cli("agent", "starten", "CC1", "--von", "Entwickler", env={"AMW_AGENT": "CC1"})
        self.assertEqual((rc, n), (1, 0))                                                   # aus einer Agenten-Sitzung: nein
        self.assertEqual(self.cli("agent", "starten", "CC1", "--von", "Entwickler",
                                  env={"CLAUDE_CODE_MESSAGING_SOCKET": r"\\.\pipe\x"})[2], 0)   # aus einer Claude-Sitzung: nein
        rc, aus, n = self.cli("agent", "starten", "CC1", "--von", "Entwickler")
        self.assertEqual((rc, n), (0, 1), aus)                                              # der Mensch im eigenen Terminal: ja

    def test_online_nie(self):
        with mock.patch.object(steuerung, "starten", side_effect=AssertionError("darf nicht laufen")):
            with self.assertRaisesRegex(aktionen.Ungueltig, "nur am PC"):
                aktionen.ausfuehren(self.con, self.pid, "/api/agent/start", {"kennung": "CC1"}, kanal="netz")
