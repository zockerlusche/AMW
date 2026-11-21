"""A1892 (Nacharbeit aus P294/P295/A1884): Rechte vergebende Projekt-Einstellungen mit --von Entwickler nur im Terminal des
Menschen; Leerlauf-Weckruf nennt keine p-Pakete; Wochenlimit-Meldung an den Lead mit „Auch du: nichts Neues anfangen“."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import arbeitspaket, db, kern, limithalt, wartegrund


class Grund(unittest.TestCase):
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
            self.pid = db.einfuegen(self.con, "projekt", name="Produkt", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid, "CC2")

    def cli(self, *args, env=None):
        from amw import cli
        aus = io.StringIO()
        mensch = {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}          # wie im Terminal des Menschen
        with mock.patch.dict(os.environ, {**mensch, **(env or {})}), contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "Produkt", *args])
        return rc, aus.getvalue()


class RechteEinstellungen(Grund):
    def test_entwickler_aus_agenten_sitzung_abgewiesen(self):
        for wert in ("paket_pruefer=CC1", "leerlauf_lead=CC1", "limit_halt=80", "merge_blick=alle", "merge_aussen_pruefung=aus"):
            for env in ({"CLAUDECODE": "1"}, {"CLAUDE_CODE_MESSAGING_SOCKET": r"\\.\pipe\x"}):
                rc, aus = self.cli("projekt", "einstellen", wert, "--von", "Entwickler", env=env)
                self.assertNotEqual(rc, 0, (wert, env))
                self.assertIn("nicht aus einer Agenten-Sitzung", aus)
        self.assertEqual(limithalt.schwelle(self.con, self.pid), 95)                               # nichts geändert
        self.assertEqual(kern.projekt_wahl(self.con, self.pid, "merge_blick"), "server")

    def test_mensch_im_terminal_und_lead_erlaubt(self):
        rc, aus = self.cli("projekt", "einstellen", "limit_halt=80", "--von", "Entwickler")
        self.assertEqual(rc, 0, aus)
        self.assertEqual(limithalt.schwelle(self.con, self.pid), 80)
        rc, aus = self.cli("projekt", "einstellen", "leerlauf_lead=CC1", "--von", "TL", env={"CLAUDECODE": "1"})
        self.assertEqual(rc, 0, aus)                                                               # der Lead aus seiner Sitzung
        rc, aus = self.cli("projekt", "einstellen", "paket_pruefer=CC2", "--von", "CC1", env={"CLAUDECODE": "1"})
        self.assertNotEqual(rc, 0)
        self.assertIn("nur der Lead oder der Mensch", aus)

    def test_andere_einstellungen_unveraendert(self):
        rc, aus = self.cli("projekt", "einstellen", "info_ablage_h=12", "--von", "Entwickler", env={"CLAUDECODE": "1"})
        self.assertEqual(rc, 0, aus)


class LeerlaufOhnePPakete(Grund):
    def test_p_pakete_nicht_als_freie_aufgaben(self):
        with db.schreiben(self.con):
            bogen = db.einfuegen(self.con, "bogen", projekt_id=self.pid, nr=1, titel="M", status="aktiv", angelegt_von="TL",
                                 angelegt_utc=db.jetzt())
        frei = kern.aufgabe_neu(self.con, self.pid, "TL", "Für einen Agenten")
        p = kern.aufgabe_neu(self.con, self.pid, "TL", "T1 Tests schreiben")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET bogen_id = ? WHERE id IN (?, ?)", (bogen, frei, p))
        arbeitspaket.setzen(self.con, self.pid, "TL", p, art="p")
        self.assertEqual([a["id"] for a in wartegrund.freie_bogen_aufgaben(self.con, self.pid)], [frei])


class LimitHaltLead(Grund):
    def test_meldung_an_den_lead_mit_auch_du(self):
        limithalt.runde(self.con, {"wert": 96.0, "letzter_reset_utc": "2026-11-21 07:00:00"})
        text = self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE 'Wochenlimit-Halt:%'").fetchone()[0]
        self.assertIn("Auch du: nichts Neues anfangen, nur noch Weckrufe, bei denen sonst etwas kaputtginge.", text)
        self.assertFalse(kern.halt_gilt(self.con, self.pid, "TL"))


if __name__ == "__main__":
    unittest.main()
