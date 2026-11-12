"""Agenten entfernen (Schema 28): stilllegen und überall ausblenden, Verlauf bleibt lesbar; wieder aufnehmen; endgültig
löschen nur ohne Verlauf; nur der Mensch (online: System-Admin)."""
import os
import tempfile
import unittest

from amw import aktionen, benutzer, db, hook, kern, workbench


class Entfernen(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        for k in ("CC1", "CC2", "Neu"):
            kern.agent_neu(self.con, self.pid, k)
        kern.posten(self.con, self.pid, "CC1", "TL", "info", "von CC1")                     # CC1 hat Verlauf, „Neu“ nicht

    def test_entfernen_blendet_aus_und_verlauf_bleibt(self):
        r = kern.agent_entfernen(self.con, self.pid, kern.ENTWICKLER, "CC1")
        self.assertEqual((r["agent"], r["endet"]), ("CC1", False))
        z = kern.agent_zeile(self.con, self.pid, "CC1")
        self.assertEqual(z["soll"], "aus")
        self.assertIsNotNone(z["entfernt_utc"])
        self.assertNotIn("CC1", [a["kennung"] for a in workbench.daten_start(self.con, self.pid)["agenten"]])      # nicht im Team
        e = {a["kennung"]: a for a in workbench.daten_einstellungen(self.con, self.pid)["agenten"]}
        self.assertTrue(e["CC1"]["entfernt_utc"] and e["CC1"]["verlauf"]["nachrichten"] == 1)                        # Einstellungen: als entfernt
        self.assertNotIn("CC1", kern.empfaenger(self.con, self.pid, "alle", "TL"))
        with self.assertRaises(kern.AmwFehler) as x:
            kern.posten(self.con, self.pid, "TL", "CC1", "auftrag", "noch was")
        self.assertIn("entfernt", str(x.exception))
        self.assertEqual(self.con.execute("SELECT kurz FROM nachricht WHERE von = 'CC1'").fetchone()[0], "von CC1")   # Verlauf lesbar
        self.assertIn("entfernt", hook.anmelden(self.con, self.pid, "CC1", {}) or "")
        with self.assertRaises(kern.AmwFehler):
            kern.agent_einstellen(self.con, self.pid, kern.ENTWICKLER, "CC1", soll="an")                              # erst wieder aufnehmen
        with self.assertRaises(kern.AmwFehler) as x:
            kern.agent_einstellen(self.con, self.pid, kern.ENTWICKLER, "CC1", neu=True)
        self.assertIn("wieder aufnehmen", str(x.exception))

    def test_wieder_aufnehmen(self):
        kern.agent_entfernen(self.con, self.pid, kern.ENTWICKLER, "CC2")
        r = kern.agent_wiederaufnehmen(self.con, self.pid, kern.ENTWICKLER, "CC2")
        self.assertEqual(r["soll"], "aus")
        self.assertIsNone(kern.agent_zeile(self.con, self.pid, "CC2")["entfernt_utc"])
        self.assertIn("CC2", [a["kennung"] for a in workbench.daten_start(self.con, self.pid)["agenten"]])

    def test_loeschen_nur_ohne_verlauf(self):
        with self.assertRaises(kern.AmwFehler) as x:
            kern.agent_loeschen(self.con, self.pid, kern.ENTWICKLER, "CC1")
        self.assertIn("1 nachrichten", str(x.exception))
        self.assertEqual(kern.agent_loeschen(self.con, self.pid, kern.ENTWICKLER, "Neu")["geloescht"], True)
        self.assertIsNone(self.con.execute("SELECT 1 FROM agent WHERE kennung = 'Neu'").fetchone())

    def test_nur_der_mensch_online_system_admin(self):
        for f in (kern.agent_entfernen, kern.agent_wiederaufnehmen, kern.agent_loeschen):
            with self.assertRaises(kern.AmwFehler):
                f(self.con, self.pid, "TL", "CC2")
        benutzer.neu(self.con, kern.ENTWICKLER, "bert", "bearbeiter", projekte=["P"])
        benutzer.neu(self.con, kern.ENTWICKLER, "sam", "system_admin")
        with self.assertRaises(aktionen.Ungueltig):
            aktionen.ausfuehren(self.con, self.pid, "/api/agent/entfernen", {"kennung": "CC2", "_benutzer": "bert"}, kanal="netz")
        r = aktionen.ausfuehren(self.con, self.pid, "/api/agent/entfernen", {"kennung": "CC2", "_benutzer": "sam"}, kanal="netz")
        self.assertEqual(r["agent"], "CC2")
        r = aktionen.ausfuehren(self.con, self.pid, "/api/agent/wiederaufnehmen", {"kennung": "CC2"})          # am PC
        self.assertEqual(r["agent"], "CC2")

    def test_laufende_sitzung_wird_gesichert_und_beendet(self):
        from unittest import mock
        from amw import steuerung
        aid = self.con.execute("SELECT id FROM agent WHERE kennung = 'CC2'").fetchone()[0]
        with db.schreiben(self.con):
            db.einfuegen(self.con, "sitzung", agent_id=aid, gestartet_utc=db.jetzt(), zustand="aktiv")
        with mock.patch.object(steuerung, "_sitzung_mit_prozess", return_value=(None, 4711)):    # Prozess läuft
            r = kern.agent_entfernen(self.con, self.pid, kern.ENTWICKLER, "CC2")
        self.assertTrue(r["endet"])
        self.assertTrue(any("SICHERN UND BEENDEN" in n["kurz"] for n in kern.offene(self.con, self.pid, "CC2")), kern.offene(self.con, self.pid, "CC2"))
        kern.agent_wiederaufnehmen(self.con, self.pid, kern.ENTWICKLER, "CC2")             # ohne Prozess: entfernen klappt trotzdem
        self.assertFalse(kern.agent_entfernen(self.con, self.pid, kern.ENTWICKLER, "CC2")["endet"])


if __name__ == "__main__":
    unittest.main()
