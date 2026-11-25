"""A2002 (TL #31197, TH154/TH155): ein Meilenstein, der mit einem Urteil endet (Vorführung, Bericht, Probe – Abnahme-Text mehr als
„alle Pakete fertig“), schließt nie von selbst. Sind alle Pakete fertig, ist er „bereit zur Abnahme“ (Abschlussbericht, eine
Meldung an Lead und Co je Stand); fertig wird er erst mit dem Ja zum Abschluss. Ohne Urteil: wie bisher."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
from amw import db, kern, planansicht, planautomatik, planung, tore
from tests.test_tore import Basis


class Urteil(Basis):
    def setUp(self):
        super().setUp()
        kern.projekt_einstellen(self.con, self.pid, "TL", meilenstein_fertig="automatisch")
        self.bis_umsetzung()                                                        # m1 („Vorführung“) aktiv

    def fertig(self, *aids):
        with db.schreiben(self.con):
            for a in aids:
                self.con.execute("UPDATE aufgabe SET status = 'fertig', fertig_utc = ?, beleg = 'abc1234' WHERE id = ?", (db.jetzt(), a))

    def status(self, bid):
        return self.con.execute("SELECT status, fertig_utc FROM bogen WHERE id = ?", (bid,)).fetchone()

    def meldungen(self, an):
        return [k for art, k in self.post(an) if "bereit zur Abnahme" in k]

    def test_was_ist_ein_urteil(self):
        for text, urteil in (("Vorführung", True), ("Bericht: Probe an einer Kopie", True), ("Probe durch den Lead", True),
                             ("K1–K6 live; Marcel nimmt die Ansichten ab.", True), ("alle Pakete fertig", False),
                             ("Alle Aufgaben sind erledigt.", False), ("", False), (None, False), ("–", False),
                             ("all tasks done", False)):
            with self.subTest(text=text):
                self.assertEqual(planautomatik.mit_urteil({"abnahme": text}), urteil)

    def test_bereit_statt_fertig_einmal_je_stand(self):
        self.fertig(self.a1, self.a2)
        self.assertEqual(planautomatik.meilenstein_projekt(self.con, self.pid), [(self.m1, "bereit")])
        self.assertEqual(self.status(self.m1)["status"], "aktiv")                                # nicht fertig – das Urteil fehlt
        self.assertTrue(tore.bericht(self.con, self.pid, self.m1))                               # Bericht entsteht schon jetzt
        for wer in ("TL", "Co"):                                                                  # Lead und Co je eine Meldung
            self.assertEqual(len(self.meldungen(wer)), 1, wer)
        self.assertEqual(len(self.meldungen(kern.ENTWICKLER)), 1)                                 # thema_freigabe = mensch: auch du
        self.assertEqual(planautomatik.meilenstein_projekt(self.con, self.pid), [])               # nicht noch einmal
        self.assertEqual(len(self.meldungen("TL")), 1)
        m = self.m(self.m1)
        self.assertTrue(m["bereit"])
        self.assertEqual((m["abschluss"]["bericht"], m["abschluss"]["frei"]), (tore.bericht(self.con, self.pid, self.m1), False))
        self.assertFalse(self.tor("umsetzung")["zu"])                                             # läuft noch bis zum Ja
        self.assertIn("bereit zur Abnahme – fertig mit dem Ja zum Abschluss",
                      tore.bericht_text(self.con, self.pid, self.m1))
        self.assertFalse(self.con.execute("SELECT 1 FROM nachricht WHERE kurz LIKE '%abschließen?%'").fetchone())

    def test_ja_des_menschen_macht_fertig(self):
        with self.assertRaisesRegex(kern.AmwFehler, "noch nicht bereit zur Abnahme"):          # Pakete offen
            planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "abschluss")
        self.fertig(self.a1, self.a2)
        planautomatik.meilenstein_projekt(self.con, self.pid)
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "abschluss")
        st = self.status(self.m1)
        self.assertEqual(st["status"], "fertig")
        self.assertTrue(st["fertig_utc"])
        self.assertTrue(self.m(self.m1)["abschluss"]["frei"])
        self.assertEqual(tore.stand(self.con, self.pid)["aktuell"], None)                         # alle Tore zu
        self.assertEqual(len([1 for _ in self.con.execute("SELECT 1 FROM plan_ereignis WHERE art = 'abschluss_bericht'")]), 1)
        tore.runde(self.con, self.pid)                                                            # kein zweiter Bericht danach
        self.assertEqual(len([1 for _ in self.con.execute("SELECT 1 FROM plan_ereignis WHERE art = 'abschluss_bericht'")]), 1)

    def test_co_und_lead_je_ein_ja(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", thema_freigabe="co+lead", grobplan_freigabe="co+lead", feinplan_freigabe="co+lead", abschluss_freigabe="co+lead")
        self.fertig(self.a1, self.a2)
        planautomatik.meilenstein_projekt(self.con, self.pid)
        self.assertEqual(self.meldungen(kern.ENTWICKLER), [])                                    # co+lead: nicht an dich
        r = planansicht.freigeben(self.con, self.pid, "Co", self.m1, "abschluss")
        self.assertFalse(r["frei"])
        self.assertEqual(self.status(self.m1)["status"], "aktiv")                                # ein Ja reicht nicht
        planansicht.freigeben(self.con, self.pid, "TL", self.m1, "abschluss")
        self.assertEqual(self.status(self.m1)["status"], "fertig")

    def test_versions_pflicht_haelt_das_ja_auf(self):
        self.fertig(self.a1, self.a2)
        planautomatik.meilenstein_projekt(self.con, self.pid)
        kern.projekt_einstellen(self.con, self.pid, "TL", versionen="pflicht")
        with self.assertRaisesRegex(kern.AmwFehler, "wartet auf die Auslieferung von A"):
            planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "abschluss")
        self.assertEqual(self.status(self.m1)["status"], "aktiv")
        self.assertFalse(self.m(self.m1)["abschluss"]["frei"])                                   # nichts halb freigegeben

    def test_neues_paket_neuer_stand(self):
        self.fertig(self.a1, self.a2)
        planautomatik.meilenstein_projekt(self.con, self.pid)
        a3 = planung.schritt_setzen(self.con, self.pid, "TL", titel="Nacharbeit", bogen_id=self.m1, agent="CC1")
        self.assertFalse(self.m(self.m1)["bereit"])                                               # wieder offen
        self.assertIsNone(self.m(self.m1)["abschluss"])
        self.assertEqual(planautomatik.meilenstein_projekt(self.con, self.pid), [])
        self.fertig(a3)
        self.assertEqual(planautomatik.meilenstein_projekt(self.con, self.pid), [(self.m1, "bereit")])
        self.assertEqual(len(self.meldungen("TL")), 2)                                            # neuer Stand, neuer Bericht
        self.assertEqual(len([1 for _ in self.con.execute("SELECT 1 FROM plan_ereignis WHERE art = 'abschluss_bericht'")]), 2)

    def test_zurueckgesetzt_schliesst_nicht_sofort_wieder(self):
        """(5) Der Lead setzt einen zu früh geschlossenen Meilenstein mit amw bogen status <id> aktiv zurück."""
        self.fertig(self.a1, self.a2)
        planung.bogen_status(self.con, self.pid, "TL", self.m1, "fertig")                       # Altstand: zu früh fertig
        planung.bogen_status(self.con, self.pid, "TL", self.m1, "aktiv")
        self.assertEqual(planautomatik.meilenstein_projekt(self.con, self.pid), [(self.m1, "bereit")])
        self.assertEqual(self.status(self.m1)["status"], "aktiv")
        self.assertTrue(self.m(self.m1)["bereit"])

    def test_ohne_urteil_wie_bisher(self):
        planung.bogen_aendern(self.con, self.pid, "TL", self.m1, abnahme="alle Pakete fertig")
        self.fertig(self.a1, self.a2)
        self.assertEqual(planautomatik.meilenstein_projekt(self.con, self.pid), [(self.m1, "fertig")])
        self.assertEqual(self.status(self.m1)["status"], "fertig")
        self.assertFalse(self.m(self.m1)["bereit"])


if __name__ == "__main__":
    import unittest
    unittest.main()
