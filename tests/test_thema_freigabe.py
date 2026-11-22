"""A1937 (K1, B2913, W2457): Themen geben Co-Entwickler und Lead gemeinsam frei (Projekt-Einstellung thema_freigabe = co+lead,
setzen nur der Mensch) – je ein Ja zur aktuellen Fassung; Marcel kann jederzeit selbst freigeben oder zurückholen; Themen, die
Löschen, Kosten, Schema oder Außenwirkung betreffen, bleiben beim Menschen (Merker nur_mensch); die Tor-Zeile zählt nach
derselben Regel; Status und Seite zeigen, wessen Ja fehlt. Ohne Schemaänderung (Ereignisse)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import cli, db, kern, themen


class Freigabe(unittest.TestCase):
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
        for k, r in (("TL", "lead"), ("CO", None), ("CC1", None)):
            kern.agent_neu(self.con, self.pid, k, rolle=r)
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, co_entwickler="CO")
        self.tid = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", "Anmeldung", "Fassung eins.")

    def st(self):
        return themen.status(self.con, themen.finden(self.con, self.pid, self.tid))

    def co_lead(self):
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, thema_freigabe="co+lead")

    def test_vorgabe_mensch(self):
        self.assertEqual(themen.freigabe_regel(self.con, self.pid), "mensch")
        with self.assertRaisesRegex(kern.AmwFehler, "thema_freigabe = mensch"):
            themen.ja_geben(self.con, self.pid, "TL", "Anmeldung")
        self.assertNotIn("ja_fehlt", self.st())
        with self.assertRaises(kern.AmwFehler):                                                   # A1951: kein Coder
            kern.projekt_einstellen(self.con, self.pid, "CC1", thema_freigabe="co+lead")

    def test_co_und_lead_geben_frei(self):
        self.co_lead()
        vorher = themen.tor(self.con, self.pid)["n"]
        self.assertEqual(self.st()["ja_fehlt"], ["Co-Entwickler", "Lead"])
        z = themen.ja_geben(self.con, self.pid, "CO", "Anmeldung")
        self.assertEqual((z["status"], z["ja_fehlt"]), ("dich", ["Lead"]))
        with self.assertRaisesRegex(kern.AmwFehler, "Co-Entwickler und der Lead"):
            themen.ja_geben(self.con, self.pid, "CC1", "Anmeldung")                                 # der Pfleger allein nicht
        z = themen.ja_geben(self.con, self.pid, "TL", "Anmeldung")
        self.assertEqual((z["status"], z["freigegeben"]), ("frei", 1))
        self.assertEqual(themen.tor(self.con, self.pid)["n"], vorher + 1)                         # Tor-Zeile zählt mit
        e = [x for x in themen._ereignisse(self.con, self.pid, self.tid) if x["art"] == "thema_freigegeben"][-1]
        self.assertEqual((e["von"], e["durch"], e["regel_von"]), ("AMW", ["CO", "TL"], "B2913"))
        m = self.con.execute("SELECT n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ?"
                             " AND n.kurz LIKE '%freigegeben von Co und Lead%'", (kern.ENTWICKLER,)).fetchone()
        self.assertIsNotNone(m)                                                                    # Marcel erfährt es
        z = themen.zurueck(self.con, self.pid, kern.ENTWICKLER, "Anmeldung", "so nicht")         # zurückholen geht immer
        self.assertEqual(z["status"], "arbeit")

    def test_neue_fassung_braucht_neue_ja(self):
        self.co_lead()
        themen.ja_geben(self.con, self.pid, "CO", "Anmeldung")
        themen.pflegen(self.con, self.pid, "CC1", "Anmeldung", "Fassung zwei.")
        self.assertEqual(self.st()["ja_fehlt"], ["Co-Entwickler", "Lead"])
        themen.ja_geben(self.con, self.pid, "TL", "Anmeldung")
        self.assertEqual(self.st()["status"], "dich")

    def test_mensch_gibt_weiter_selbst_frei(self):
        self.co_lead()
        self.assertEqual(themen.freigeben(self.con, self.pid, kern.ENTWICKLER, "Anmeldung")["status"], "frei")

    def test_nur_der_mensch(self):
        self.co_lead()
        z = themen.nur_mensch_setzen(self.con, self.pid, "CC1", "Anmeldung")                    # der Pfleger setzt
        self.assertTrue(z["nur_mensch"])
        self.assertNotIn("ja_fehlt", z)
        with self.assertRaisesRegex(kern.AmwFehler, "bleibt beim Menschen"):
            themen.ja_geben(self.con, self.pid, "TL", "Anmeldung")
        with self.assertRaisesRegex(kern.AmwFehler, "nur der Mensch"):
            themen.nur_mensch_setzen(self.con, self.pid, "TL", "Anmeldung", an=False)
        self.assertFalse(themen.nur_mensch_setzen(self.con, self.pid, kern.ENTWICKLER, "Anmeldung", an=False)["nur_mensch"])
        with self.assertRaisesRegex(kern.AmwFehler, "Pfleger, Lead oder Mensch"):
            themen.nur_mensch_setzen(self.con, self.pid, "CO", "Anmeldung")

    def cli(self, *argv, sitzung=True):
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_AGENT": "", "CLAUDECODE": "1" if sitzung else "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}), \
                contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "Produkt", *argv])
        return rc, aus.getvalue()

    def test_befehlszeile(self):
        rc, aus = self.cli("--von", "TL", "thema", "freigeben", "Anmeldung")
        self.assertNotEqual(rc, 0)                                                                 # Vorgabe: nur der Mensch
        self.assertIn("nur der Mensch", aus)
        self.co_lead()
        rc, aus = self.cli("--von", "TL", "thema", "freigeben", "Anmeldung")
        self.assertEqual(rc, 0, aus)
        self.assertIn("Anmeldung: Ja gegeben – wartet auf dich · es fehlt noch: Co-Entwickler", aus)
        rc, aus = self.cli("--von", "TL", "thema", "status")
        self.assertIn("Ja fehlt: Co-Entwickler", aus)
        rc, aus = self.cli("--von", "CO", "thema", "freigeben", "Anmeldung")
        self.assertIn("Anmeldung: Ja gegeben – freigegeben", aus)
        rc, aus = self.cli("--von", "CC1", "thema", "nur_mensch", "Anmeldung")
        self.assertEqual(rc, 0, aus)
        rc, aus = self.cli("--von", "Entwickler", "thema", "nicht_nur_mensch", "Anmeldung")       # aus einer Sitzung: nein
        self.assertNotEqual(rc, 0)
        rc, aus = self.cli("--von", "Entwickler", "thema", "nicht_nur_mensch", "Anmeldung", sitzung=False)
        self.assertEqual(rc, 0, aus)


if __name__ == "__main__":
    unittest.main()
