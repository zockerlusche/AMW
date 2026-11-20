"""Lead-Wechsel (A1887, B2904): die Führung geht in einem Schritt an einen anderen Agenten – nie zwei Leads, nie keiner; der
bisherige Chat-Lead wird Co-Entwickler (Wortlaut, Beschlüsse, Fragen direkt an den Menschen, Dokumente) und behält den
Dateiaustausch unter seinem Namen. Weckrufe, Fragen an den Lead und Leerlauf gehen danach an den neuen Lead."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import tempfile
import unittest
from unittest import mock

from amw import betrieb, bruecke, db, kern, wartegrund, wissen


class LeadWechsel(unittest.TestCase):
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
            db.einfuegen(self.con, "projekt", name="Erstes", angelegt_utc=db.jetzt())       # das erste Projekt hat eine eigene Brücke
            self.pid = db.einfuegen(self.con, "projekt", name="Produkt", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead", arbeitsweise="chat")
        kern.agent_neu(self.con, self.pid, "PL", fachgebiet="Prüfen")
        kern.agent_neu(self.con, self.pid, "CC1")

    def leads(self):
        return [r[0] for r in self.con.execute("SELECT kennung FROM agent WHERE projekt_id = ? AND rolle = 'lead'", (self.pid,))]

    def brueckenabsender(self):
        return next(b["von"] for b in bruecke.bruecken(self.con) if b["pid"] == self.pid)

    def wechsel(self, von="TL", **k):
        return kern.lead_wechsel(self.con, self.pid, von, "PL", **{"co": "TL", "grund": "B2904", **k})

    def test_in_einem_schritt_mit_protokoll_und_info(self):
        self.assertEqual((kern.lead(self.con, self.pid), self.brueckenabsender()), ("TL", "TL"))
        self.assertEqual(self.wechsel(zustaendig="Planen, prüfen", fasst_nicht_an="Löschen"), (["TL"], "PL"))
        self.assertEqual(self.leads(), ["PL"])                                                  # nie zwei, nie keiner
        self.assertEqual(kern.lead(self.con, self.pid), "PL")
        self.assertFalse(kern.ist_lead(self.con, self.pid, "TL"))
        self.assertTrue(kern.ist_co(self.con, self.pid, "TL"))
        z = self.con.execute("SELECT zustaendig, fasst_nicht_an FROM agent WHERE kennung = 'PL'").fetchone()
        self.assertEqual(tuple(z), ("Planen, prüfen", "Löschen"))
        self.assertIn("TL → PL (Co-Entwickler: TL) – B2904",
                      self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'lead_wechsel'").fetchone()[0])
        an = {r[0] for r in self.con.execute("SELECT e.agent FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id"
                                             " WHERE n.kurz LIKE 'Lead-Wechsel%'")}
        self.assertEqual(an, {"PL", kern.ENTWICKLER})                                           # TL schickt sie selbst

    def test_wer_darf(self):
        for von, k in (("CC1", {}), ("TL", {"grund": " "}), ("TL", {"co": "PL"}), ("TL", {"co": "XY"})):
            with self.assertRaises(kern.AmwFehler):
                self.wechsel(von=von, **k)
        self.assertEqual(self.leads(), ["TL"])                                                  # nichts halb geändert
        with self.assertRaises(kern.AmwFehler):
            kern.lead_wechsel(self.con, self.pid, "TL", "GIBTSNICHT", grund="x")
        kern.lead_wechsel(self.con, self.pid, kern.ENTWICKLER, "PL", grund="Marcel am PC")       # der Mensch darf auch
        self.assertEqual(self.leads(), ["PL"])
        self.assertIsNone(kern.co_entwickler(self.con, self.pid))                               # ohne --co kein Co-Entwickler
        with self.assertRaisesRegex(kern.AmwFehler, "schon der Lead"):
            kern.lead_wechsel(self.con, self.pid, "PL", "PL", grund="x")

    def test_weckrufe_und_fragen_gehen_an_den_neuen_lead(self):
        self.wechsel()
        kern.agent_einstellen(self.con, self.pid, kern.ENTWICKLER, "PL", arbeitsweise="terminal")
        self.assertEqual(wartegrund.leer_lead(self.con, self.pid), "PL")                       # Leerlauf ohne leerlauf_lead
        fid = kern.frage_neu(self.con, self.pid, "CC1", "tl", "Welche Reihenfolge?", [("A", "erst X"), ("B", "erst Y")], "A", "X ist kleiner")
        an = {r[0] for r in self.con.execute("SELECT e.agent FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id"
                                             " WHERE n.kurz LIKE ?", (f"%F{fid}%",))}
        self.assertEqual(an, {"PL"})
        self.assertEqual(self.brueckenabsender(), "TL")                                         # Dateiaustausch bleibt bei TL

    def test_ohne_co_bruecke_beim_neuen_lead(self):
        self.wechsel(co=None)
        self.assertEqual(self.brueckenabsender(), "PL")

    def test_co_entwickler_darf_wortlaut_beschluss_und_fragt_direkt(self):
        self.wechsel()
        wid = wissen.wortlaut_neu(self.con, self.pid, "TL", "ich folge deiner Empfehlung", "chat-tl")
        self.assertTrue(wid)
        self.assertTrue(wissen.beschluss_neu(self.con, self.pid, "TL", "Probe", "So gilt es.", "Marcel im Chat"))
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, agentenfragen="lead")
        f_co = kern.frage_neu(self.con, self.pid, "TL", "entwickler", "Konzept A oder B?", [("A", "A"), ("B", "B")], "A", "einfacher", geprueft="keine Treffer")
        f_cc = kern.frage_neu(self.con, self.pid, "CC1", "entwickler", "Name?", [("A", "x"), ("B", "y")], "A", "kurz", geprueft="keine Treffer")
        an = dict(self.con.execute("SELECT id, an FROM frage WHERE id IN (?, ?)", (f_co, f_cc)).fetchall())
        self.assertEqual((an[f_co], an[f_cc]), ("entwickler", "tl"))                            # Co direkt, Coder über den Lead

    def test_co_entwickler_plant_und_prueft_nicht(self):
        self.wechsel()
        aid = kern.aufgabe_neu(self.con, self.pid, "PL", "Etwas", "CC1")
        for tun in (lambda: betrieb.freigabe_merge(self.con, self.pid, "TL", aid),
                    lambda: kern.projekt_einstellen(self.con, self.pid, "TL", paket_pruefer="CC1"),
                    lambda: kern.agent_einstellen(self.con, self.pid, "TL", "CC1", fachgebiet="Code"),
                    lambda: wissen._nur_lead(self.con, self.pid, "TL", "Regeln ändern")):
            with self.assertRaises(kern.AmwFehler):
                tun()
        with self.assertRaises(kern.AmwFehler):
            wissen.wortlaut_neu(self.con, self.pid, "CC1", "x", "chat")                          # ein Coder weiterhin nicht

    def cli(self, *args, env=None):
        import contextlib
        import io
        from amw import cli
        aus = io.StringIO()
        mensch = {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}          # wie im Terminal des Menschen
        with mock.patch.dict(os.environ, {**mensch, **(env or {})}), contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "Produkt", *args])
        return rc, aus.getvalue()

    def test_entwickler_nur_im_eigenen_terminal(self):                                          # P293: kein Agent macht sich zum Lead
        for args in (("agent", "lead", "CC1", "--grund", "x"), ("agent", "profil", "CC1", "--rolle", "lead"),
                     ("agent", "neu", "CC9", "--rolle", "lead")):
            for env in ({"CLAUDECODE": "1"}, {"AMW_AGENT": "CC1"}, {"CLAUDE_CODE_MESSAGING_SOCKET": r"\\.\pipe\x"}):
                rc, aus = self.cli(*args, "--von", "Entwickler", env=env)
                self.assertNotEqual(rc, 0, (args, env))
                if "AMW_AGENT" not in env:                                               # dort weist schon _von ab
                    self.assertIn("nicht aus einer Agenten-Sitzung", aus)
        self.assertEqual(self.leads(), ["TL"])
        self.assertIsNone(self.con.execute("SELECT 1 FROM agent WHERE kennung = 'CC9'").fetchone())
        rc, aus = self.cli("agent", "neu", "CC9", "--rolle", "lead", "--von", "CC1")                # ein Coder legt keinen Lead an
        self.assertNotEqual(rc, 0)
        self.assertIn("nur der Lead oder der Mensch", aus)
        rc, aus = self.cli("agent", "lead", "PL", "--grund", "Marcel am PC", "--von", "Entwickler")  # im Terminal des Menschen: ja
        self.assertEqual(rc, 0, aus)
        self.assertEqual(self.leads(), ["PL"])

    def test_befehlszeile(self):
        import contextlib
        import io
        from amw import cli
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus):
            cli.main(["--projekt", "Produkt", "--von", "TL", "agent", "lead", "PL", "--co", "TL", "--grund", "B2904",
                      "--zustaendig", "Lead: planen", "--nicht", "Löschen"])
        self.assertIn("PL führt jetzt das Projekt (vorher: TL); TL ist Co-Entwickler", aus.getvalue())
        self.assertEqual(self.leads(), ["PL"])


if __name__ == "__main__":
    unittest.main()
