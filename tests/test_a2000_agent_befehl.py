"""A2000 (B2917): Agenten entfernen und wieder aufnehmen auch per Befehl (nur der Mensch im eigenen Terminal); ein entfernter
Agent ist nie Lead; einen Lead entfernt man erst nach der Übergabe; agent lead nennt den Grund und setzt mit --co allein den
Co-Entwickler, wenn der neue schon Lead ist; co_entwickler nimmt keinen entfernten Agenten."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import cli, db, kern


class AgentBefehl(unittest.TestCase):
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
            db.einfuegen(self.con, "projekt", name="Erstes", angelegt_utc=db.jetzt())
            self.pid = db.einfuegen(self.con, "projekt", name="Produkt", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead", arbeitsweise="chat")
        kern.agent_neu(self.con, self.pid, "PL")
        kern.agent_neu(self.con, self.pid, "CC1")

    def cli(self, *args, env=None):
        aus = io.StringIO()
        mensch = {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}          # wie im Terminal des Menschen
        with mock.patch.dict(os.environ, {**mensch, **(env or {})}), contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "Produkt", *args])
        return rc, aus.getvalue()

    def entfernt(self, k):
        return kern.agent_zeile(self.con, self.pid, k)["entfernt_utc"] is not None

    def alt_entfernt(self, k):
        """Stand vor A2000 (B2917/GlassWorld): ein Lead wurde entfernt und behielt die Rolle."""
        with db.schreiben(self.con):
            self.con.execute("UPDATE agent SET entfernt_utc = ?, soll = 'aus' WHERE projekt_id = ? AND kennung = ?",
                             (db.jetzt(), self.pid, k))

    def test_1_entfernen_und_wiederaufnehmen_per_befehl(self):
        rc, aus = self.cli("agent", "entfernen", "CC1", "--von", "Entwickler")
        self.assertEqual(rc, 0, aus)
        self.assertIn("CC1 ist entfernt", aus)
        self.assertIn("amw agent wiederaufnehmen CC1", aus)
        self.assertTrue(self.entfernt("CC1"))
        rc, aus = self.cli("agent", "wiederaufnehmen", "CC1", "--von", "Entwickler")
        self.assertEqual(rc, 0, aus)
        self.assertIn("CC1 ist wieder aufgenommen", aus)
        self.assertFalse(self.entfernt("CC1"))

    def test_1_nur_der_mensch_im_eigenen_terminal(self):
        rc, aus = self.cli("agent", "entfernen", "CC1", "--von", "TL")                            # der Lead nicht
        self.assertNotEqual(rc, 0)
        self.assertIn("nur der Mensch", aus)
        for env in ({"CLAUDECODE": "1"}, {"CLAUDE_CODE_MESSAGING_SOCKET": r"\\.\pipe\x"}):         # nie aus einer Agenten-Sitzung
            for aktion in ("entfernen", "wiederaufnehmen"):
                rc, aus = self.cli("agent", aktion, "CC1", "--von", "Entwickler", env=env)
                self.assertNotEqual(rc, 0, (aktion, env))
                self.assertIn("nicht aus einer Agenten-Sitzung", aus)
        self.assertFalse(self.entfernt("CC1"))
        rc, aus = self.cli("agent", "entfernen", "--von", "Entwickler")
        self.assertNotEqual(rc, 0)
        self.assertIn("amw agent entfernen <Agent>", aus)

    def test_1_hilfe_und_befehlsreferenz(self):
        self.assertIn("entfernen ¦ wiederaufnehmen AGENT (der Mensch; wiederaufnehmen auch der Lead mit --wort W<nr>)",
                      cli.befehle_markdown())
        wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for datei, text in (("doc/befehle.md", "wiederaufnehmen AGENT"), ("doc/hilfe/agenten.md", "amw agent wiederaufnehmen"),
                            ("doc/hilfe/en/agenten.md", "amw agent wiederaufnehmen")):
            with open(os.path.join(wurzel, datei), encoding="utf-8") as f:
                self.assertIn(text, f.read(), datei)

    def test_2_entfernter_agent_ist_nie_lead(self):
        self.alt_entfernt("TL")
        self.assertIsNone(kern.lead(self.con, self.pid))
        self.assertFalse(kern.ist_lead(self.con, self.pid, "TL"))
        with self.assertRaises(kern.AmwFehler):                                                  # führt auch nicht mehr
            kern.lead_wechsel(self.con, self.pid, "TL", "PL", grund="x")
        kern.lead_wechsel(self.con, self.pid, kern.ENTWICKLER, "PL", grund="B2917")               # der Mensch übergibt
        self.assertEqual(kern.lead(self.con, self.pid), "PL")
        self.assertEqual([r[0] for r in self.con.execute("SELECT kennung FROM agent WHERE projekt_id = ? AND rolle = 'lead'",
                                                         (self.pid,))], ["PL"])                  # alte Rolle aufgeräumt

    def test_3_lead_entfernen_abgelehnt(self):
        rc, aus = self.cli("agent", "entfernen", "TL", "--von", "Entwickler")
        self.assertNotEqual(rc, 0)
        self.assertIn("erst die Führung übergeben: amw agent lead", aus)
        self.assertFalse(self.entfernt("TL"))
        kern.lead_wechsel(self.con, self.pid, kern.ENTWICKLER, "PL", grund="x")
        self.assertTrue(kern.agent_entfernen(self.con, self.pid, kern.ENTWICKLER, "TL")["agent"])   # danach geht es

    def test_4_lead_nennt_den_grund(self):
        kern.agent_entfernen(self.con, self.pid, kern.ENTWICKLER, "CC1")
        rc, aus = self.cli("agent", "lead", "CC1", "--grund", "x", "--von", "Entwickler")
        self.assertNotEqual(rc, 0)
        self.assertIn("CC1 ist entfernt", aus)
        self.assertIn("amw agent wiederaufnehmen CC1", aus)
        rc, aus = self.cli("agent", "lead", "PL", "--co", "CC1", "--grund", "x", "--von", "Entwickler")
        self.assertNotEqual(rc, 0)
        self.assertIn("Co-Entwickler: CC1 ist entfernt", aus)
        self.assertEqual(kern.lead(self.con, self.pid), "TL")                                     # nichts halb geändert
        rc, aus = self.cli("agent", "lead", "GIBTSNICHT", "--grund", "x", "--von", "Entwickler")
        self.assertIn("gibt es in diesem Projekt nicht", aus)

    def test_4_schon_lead_setzt_nur_den_co(self):
        """B2917: der neue Lead führt schon, der alte (entfernte) wird wieder aufgenommen und soll Co-Entwickler werden."""
        kern.lead_wechsel(self.con, self.pid, kern.ENTWICKLER, "PL", grund="x")
        kern.agent_entfernen(self.con, self.pid, kern.ENTWICKLER, "TL")
        kern.agent_wiederaufnehmen(self.con, self.pid, kern.ENTWICKLER, "TL")
        rc, aus = self.cli("agent", "lead", "PL", "--co", "TL", "--grund", "B2917", "--von", "Entwickler")
        self.assertEqual(rc, 0, aus)
        self.assertIn("PL bleibt Lead; TL ist Co-Entwickler", aus)
        self.assertEqual((kern.lead(self.con, self.pid), kern.co_entwickler(self.con, self.pid)), ("PL", "TL"))
        self.assertIn("PL bleibt Lead, Co-Entwickler: TL – B2917",
                      self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'lead_wechsel' ORDER BY id DESC").fetchone()[0])
        with self.assertRaisesRegex(kern.AmwFehler, "schon der Lead"):                           # ohne --co weiter abgelehnt
            kern.lead_wechsel(self.con, self.pid, "PL", "PL", grund="x")
        with self.assertRaises(kern.AmwFehler):                                                  # Co nie der Lead selbst
            kern.lead_wechsel(self.con, self.pid, "PL", "PL", co="PL", grund="x")

    def test_5_co_entwickler_nimmt_keinen_entfernten(self):
        kern.agent_entfernen(self.con, self.pid, kern.ENTWICKLER, "CC1")
        with self.assertRaisesRegex(kern.AmwFehler, "CC1 ist entfernt – erst wieder aufnehmen"):
            kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, co_entwickler="CC1")
        self.assertIsNone(kern.co_entwickler(self.con, self.pid))
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, co_entwickler="PL")          # ein aktiver geht
        self.assertEqual(kern.co_entwickler(self.con, self.pid), "PL")

    def wort(self, stunden=1):
        import datetime
        z = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=stunden)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "wortlaut", projekt_id=self.pid, zeit_utc=z, text="mach du das",
                                kanal="chat-tl", erfasst_von="TL", erfasst_utc=db.jetzt())

    def test_6_lead_nimmt_auf_frisches_wort_wieder_auf(self):
        kern.agent_entfernen(self.con, self.pid, kern.ENTWICKLER, "CC1")
        with self.assertRaisesRegex(kern.AmwFehler, "oder der Lead auf ein frisches Wort"):          # ohne Wort nicht
            kern.agent_wiederaufnehmen(self.con, self.pid, "TL", "CC1")
        alt = self.wort(stunden=30)
        with self.assertRaisesRegex(kern.AmwFehler, "älter als 24 Stunden – für das Wiederaufnehmen"):
            kern.agent_wiederaufnehmen(self.con, self.pid, "TL", "CC1", wort=f"W{alt}")
        w = self.wort()
        with self.assertRaises(kern.AmwFehler):                                                  # ein Coder auch mit Wort nicht
            kern.agent_wiederaufnehmen(self.con, self.pid, "PL", "CC1", wort=f"W{w}")
        self.assertTrue(self.entfernt("CC1"))
        rc, aus = self.cli("agent", "wiederaufnehmen", "CC1", "--wort", f"W{w}", "--von", "TL", env={"CLAUDECODE": "1"})
        self.assertEqual(rc, 0, aus)                                                             # auch aus seiner Sitzung
        self.assertFalse(self.entfernt("CC1"))
        self.assertIn(f"CC1 wieder aufgenommen · W{w}", self.con.execute(
            "SELECT text FROM plan_ereignis WHERE art = 'wiederaufnahme_auf_wort'").fetchone()[0])
        info = self.con.execute("SELECT n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ?"
                                " AND n.kurz LIKE '%wieder aufgenommen%'", (kern.ENTWICKLER,)).fetchone()
        self.assertIn(f"TL hat CC1 wieder aufgenommen (auf dein Wort W{w})", info[0])

    def test_6_entfernen_und_loeschen_bleiben_beim_menschen(self):
        w = self.wort()
        for f in (kern.agent_entfernen, kern.agent_loeschen):
            with self.assertRaisesRegex(kern.AmwFehler, "nur der Mensch"):
                f(self.con, self.pid, "TL", "CC1")
        rc, aus = self.cli("agent", "entfernen", "CC1", "--wort", f"W{w}", "--von", "TL")
        self.assertNotEqual(rc, 0)
        self.assertFalse(self.entfernt("CC1"))

    def test_6_lead_wechsel_mit_co_auf_wort(self):
        """B2917: der Lead nimmt den alten Lead auf dein Wort wieder auf und macht ihn zum Co-Entwickler."""
        kern.lead_wechsel(self.con, self.pid, kern.ENTWICKLER, "PL", grund="x")
        kern.agent_entfernen(self.con, self.pid, kern.ENTWICKLER, "TL")
        w = self.wort()
        kern.agent_wiederaufnehmen(self.con, self.pid, "PL", "TL", wort=f"W{w}")
        rc, aus = self.cli("agent", "lead", "PL", "--co", "TL", "--grund", "mach du das", "--wort", f"W{w}", "--von", "PL")
        self.assertEqual(rc, 0, aus)
        self.assertEqual((kern.lead(self.con, self.pid), kern.co_entwickler(self.con, self.pid)), ("PL", "TL"))
        self.assertIn(f"(auf Wort W{w})", self.con.execute(
            "SELECT text FROM plan_ereignis WHERE art = 'lead_wechsel' ORDER BY id DESC").fetchone()[0])
        with self.assertRaisesRegex(kern.AmwFehler, "älter als 24 Stunden – für einen Lead-Wechsel"):
            kern.lead_wechsel(self.con, self.pid, "PL", "CC1", grund="x", wort=f"W{self.wort(stunden=30)}")


if __name__ == "__main__":
    unittest.main()
