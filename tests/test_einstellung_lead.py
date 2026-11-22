"""A1951 (Marcel W2460, B2914: „Wir sind Dev und TL“): thema_freigabe und sicherung_ziel setzen Lead oder Mensch – kein anderer
Agent, nie „--von Entwickler“ aus einer Agenten-Sitzung; ändert der Lead, steht es im Protokoll mit Grund. merge_blick und
merge_aussen_pruefung bleiben beim Menschen; Zugangsdaten im Sicherungsziel weiter abgelehnt (G13)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import cli, db, kern


class EinstellungLead(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad})
        u.start()
        self.addCleanup(u.stop)
        for k in ("AMW_AGENT", "AMW_PROJEKT"):
            os.environ.pop(k, None)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Produkt", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")

    def protokoll(self):
        return [json.loads(r[0]) | {"von": r[1]} for r in
                self.con.execute("SELECT text, von FROM plan_ereignis WHERE art = 'einstellung_lead' ORDER BY id")]

    def test_lead_setzt_beide_mit_protokoll(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", thema_freigabe="co+lead", sicherung_ziel="https://github.com/k/r.git")
        self.assertEqual(kern.projekt_wahl(self.con, self.pid, "thema_freigabe"), "co+lead")
        self.assertEqual([(p["schluessel"], p["neu"], p["grund"], p["von"]) for p in self.protokoll()],
                         [("thema_freigabe", "co+lead", "W2460/B2914", "TL"), ("sicherung_ziel", "https://github.com/k/r.git", "W2460/B2914", "TL")])
        kern.projekt_einstellen(self.con, self.pid, "TL", thema_freigabe="co+lead")               # unverändert: kein Eintrag
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, thema_freigabe="mensch")      # der Mensch: wie bisher
        self.assertEqual(len(self.protokoll()), 2)
        self.assertEqual(kern.projekt_wahl(self.con, self.pid, "thema_freigabe"), "mensch")

    def test_coder_nicht_und_merge_blick_nur_mensch(self):
        for k, v in (("thema_freigabe", "co+lead"), ("sicherung_ziel", "https://github.com/k/r.git")):
            with self.assertRaisesRegex(kern.AmwFehler, "nur Lead und Entwickler"):
                kern.projekt_einstellen(self.con, self.pid, "CC1", **{k: v})
        neu = "an" if kern.projekt_wahl(self.con, self.pid, "merge_blick") != "an" else "aus"
        with self.assertRaisesRegex(kern.AmwFehler, "stellt nur der Mensch"):
            kern.projekt_einstellen(self.con, self.pid, "TL", merge_blick=neu)
        with self.assertRaisesRegex(kern.AmwFehler, "keine Zugangsdaten"):                        # G13 gilt auch für den Lead
            kern.projekt_einstellen(self.con, self.pid, "TL", sicherung_ziel="https://u:p@github.com/k/r.git")
        self.assertEqual(self.protokoll(), [])

    def befehl(self, von, wert, sitzung):
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_AGENT": "", "CLAUDECODE": "1" if sitzung else "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}), \
                contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            return cli.main(["--projekt", "Produkt", "--von", von, "projekt", "einstellen", wert]), aus.getvalue()

    def test_befehlszeile(self):
        rc, t = self.befehl("TL", "thema_freigabe=co+lead", sitzung=True)                         # der Lead aus seiner Sitzung
        self.assertEqual(rc, 0, t)
        rc, t = self.befehl("TL", "sicherung_ziel=origin", sitzung=True)
        self.assertEqual((rc, t.strip()), (0, "sicherung_ziel = origin"))
        rc, t = self.befehl("CC1", "thema_freigabe=mensch", sitzung=True)
        self.assertNotEqual(rc, 0)
        self.assertIn("nur der Lead oder der Mensch", t)
        rc, t = self.befehl(kern.ENTWICKLER, "thema_freigabe=mensch", sitzung=True)               # nie --von Entwickler aus einer Sitzung
        self.assertNotEqual(rc, 0)
        self.assertIn("nicht aus einer Agenten-Sitzung", t)
        rc, t = self.befehl(kern.ENTWICKLER, "thema_freigabe=mensch", sitzung=False)              # der Mensch im eigenen Terminal
        self.assertEqual(rc, 0, t)


if __name__ == "__main__":
    unittest.main()
