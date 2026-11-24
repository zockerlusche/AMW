"""A2031 (TH164 F2 Schritt 3): rollende Feinplanung – die AMW stößt die Feinplanung des nächsten Meilensteins selbst an
(nach dem Grobplan für den ersten; sonst sobald der laufende bereit zur Abnahme ist oder sein letztes Paket läuft), einmal je
Meilenstein; „Plan freigeben und starten“ ist ein Klick und geht auch, während der vorige auf seine Abnahme wartet."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import aktionen, arbeitspaket, db, feinplanung, fertigquelle, kern, planansicht, planung, themen

MENSCH = {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid, "Co")
        kern.projekt_einstellen(self.con, self.pid, "TL", co_entwickler="Co")
        self.m1 = planung.bogen_neu(self.con, self.pid, "TL", "Anmelden", abnahme="Vorführung beim Menschen")
        self.m2 = planung.bogen_neu(self.con, self.pid, "TL", "Sicherung", abnahme="Bericht")
        self.m3 = planung.bogen_neu(self.con, self.pid, "TL", "Online", abnahme="Vorführung")
        self.th = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        self.a1 = self.paket("SSO bauen", self.m1, agent="CC1", groesse="M", art="sicherheit")
        self.a2 = self.paket("Tests", self.m1, nach=[self.a1], pruefbefehl="python -m unittest tests.test_x", dateibereich="tests/test_x.py")
        arbeitspaket.setzen(self.con, self.pid, "TL", self.a2, art="p", modell="sonnet")
        self.angestossen = []
        a = mock.patch.object(feinplanung, "ANSTOSSEN", side_effect=lambda _con, _pid, b, grund: self.angestossen.append((b["id"], grund)))
        a.start()
        self.addCleanup(a.stop)

    def paket(self, titel, bid, **felder):
        """Ein voll geplantes Paket (TH165: Ziel, Thema, Fertig-Quelle) – startklar zu planen."""
        aid = planung.schritt_setzen(self.con, self.pid, "TL", titel=titel, bogen_id=bid, auftrag=f"{titel}.", **felder)
        themen.verweise_setzen(self.con, self.pid, "TL", aid, [f"TH{self.th}"])
        fertigquelle.setzen(self.con, self.pid, "TL", aid, "commit")
        return aid

    def grob_alle(self):
        for m in (self.m1, self.m2, self.m3):
            planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, m, "grob")

    def status(self, aid, st):
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = ?, beleg = ? WHERE id = ?", (st, "abc1234" if st == "fertig" else None, aid))

    def bogen(self, bid):
        return self.con.execute("SELECT status FROM bogen WHERE id = ?", (bid,)).fetchone()[0]

    def faellig(self):
        return [r[0] for r in self.con.execute("SELECT bogen_id FROM plan_ereignis WHERE art = ? ORDER BY id", (feinplanung.FAELLIG,))]


class Ausloeser(Grund):
    def test_erst_nach_dem_grobplan_und_nur_der_naechste(self):
        self.assertEqual(feinplanung.projekt(self.con, self.pid), [])                         # Grobplan noch offen
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "grob")
        self.assertEqual(feinplanung.projekt(self.con, self.pid), [])                         # erst wenn alle frei sind
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m2, "grob")
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m3, "grob")
        self.assertEqual(feinplanung.projekt(self.con, self.pid), [])                         # M1 hat Pakete, sein Plan wartet aufs Ja
        self.assertEqual(self.angestossen, [])

    def test_erster_meilenstein_ohne_pakete(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET bogen_id = NULL WHERE bogen_id = ?", (self.m1,))
        self.grob_alle()
        self.assertEqual(feinplanung.projekt(self.con, self.pid), [(self.m1, "erster")])
        self.assertEqual(self.angestossen, [(self.m1, feinplanung.GRUND["erster"])])
        self.assertEqual(feinplanung.projekt(self.con, self.pid), [])                         # einmal je Meilenstein
        self.assertEqual(self.faellig(), [self.m1])

    def test_waehrend_der_laufende_arbeit_hat_nichts(self):
        self.grob_alle()
        feinplanung.plan_starten(self.con, self.pid, kern.ENTWICKLER, self.m1)
        self.status(self.a1, "laeuft")                                                         # a2 wartet noch auf a1
        self.assertIsNone(feinplanung.anlass(self.con, self.pid))
        self.assertEqual(feinplanung.projekt(self.con, self.pid), [])

    def test_letztes_paket_laeuft(self):
        self.grob_alle()
        feinplanung.plan_starten(self.con, self.pid, kern.ENTWICKLER, self.m1)
        self.status(self.a1, "fertig")
        self.status(self.a2, "laeuft")
        self.assertEqual(feinplanung.projekt(self.con, self.pid), [(self.m2, "letztes")])
        self.assertEqual(self.angestossen, [(self.m2, feinplanung.GRUND["letztes"])])
        self.assertEqual(feinplanung.projekt(self.con, self.pid), [])
        self.assertEqual(self.faellig(), [self.m2])                                            # M3 erst nach M2

    def test_bereit_zur_abnahme(self):
        self.grob_alle()
        feinplanung.plan_starten(self.con, self.pid, kern.ENTWICKLER, self.m1)
        self.status(self.a1, "fertig")
        self.status(self.a2, "fertig")
        self.assertEqual(feinplanung.projekt(self.con, self.pid), [(self.m2, "bereit")])

    def test_abschaltbar(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", plan_automatik="aus")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET bogen_id = NULL WHERE bogen_id = ?", (self.m1,))
        self.grob_alle()
        self.assertEqual(feinplanung.projekt(self.con, self.pid), [])

    def test_ohne_attrappe_bekommt_der_lead_den_auftrag(self):
        mock.patch.stopall()
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET bogen_id = NULL WHERE bogen_id = ?", (self.m1,))
        self.grob_alle()
        feinplanung.runde(self.con)
        n = self.con.execute("SELECT n.art, n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = 'TL'"
                             " AND n.von = 'AMW' AND n.kurz LIKE '%fein planen'").fetchall()
        self.assertEqual([tuple(x) for x in n], [("auftrag", "Meilenstein 1 „Anmelden“ jetzt fein planen")])


class PlanStarten(Grund):
    def test_ein_klick_startet(self):
        self.grob_alle()
        r = feinplanung.plan_starten(self.con, self.pid, kern.ENTWICKLER, self.m1)
        self.assertTrue(r["frei"])
        self.assertEqual(self.bogen(self.m1), "aktiv")
        self.assertEqual(r["gestartet"]["startklar"], [self.a1, self.a2])
        self.assertEqual(arbeitspaket.lesen(self.con, self.a2)["zustand"], "startklar")       # p-Paket geht an den Disponenten

    def test_naechster_startet_waehrend_der_vorige_auf_die_abnahme_wartet(self):
        a3 = self.paket("Sichern", self.m2, agent="CC1", groesse="S", art="text")
        self.grob_alle()
        feinplanung.plan_starten(self.con, self.pid, kern.ENTWICKLER, self.m1)
        self.status(self.a1, "fertig")
        self.status(self.a2, "fertig")
        r = feinplanung.plan_starten(self.con, self.pid, kern.ENTWICKLER, self.m2)
        self.assertEqual((self.bogen(self.m1), self.bogen(self.m2)), ("aktiv", "aktiv"))       # M1 wartet aufs Urteil, M2 läuft
        self.assertEqual(r["gestartet"]["startklar"], [a3])

    def test_co_und_lead_erst_mit_dem_zweiten_ja(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", thema_freigabe="co+lead")
        planansicht.freigeben(self.con, self.pid, "Co", self.m1, "grob")
        planansicht.freigeben(self.con, self.pid, "TL", self.m1, "grob")
        r = feinplanung.plan_starten(self.con, self.pid, "Co", self.m1)
        self.assertFalse(r["frei"])
        self.assertEqual(self.bogen(self.m1), "geplant")
        r = feinplanung.plan_starten(self.con, self.pid, "TL", self.m1)
        self.assertTrue(r["frei"])
        self.assertEqual(self.bogen(self.m1), "aktiv")

    def test_workbench_und_befehl(self):
        a3 = self.paket("Sichern", self.m2, agent="CC1", groesse="S", art="text")
        self.grob_alle()
        r = aktionen.ausfuehren(self.con, self.pid, "/api/meilenstein/plan-starten", {"bogen": self.m1}, kanal="seite")
        self.assertEqual((r["frei"], self.bogen(self.m1)), (True, "aktiv"))
        from amw import cli
        aus = io.StringIO()
        with mock.patch.dict(os.environ, MENSCH), contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "P", "bogen", "freigeben", str(self.m2), "--art", "plan", "--starten", "--von", "Entwickler"])
        self.assertEqual(rc, 0, aus.getvalue())
        self.assertIn("gestartet, 1 Pakete startklar", aus.getvalue())
        self.assertEqual(self.bogen(self.m2), "aktiv")
        self.assertTrue(a3)
        with mock.patch.dict(os.environ, MENSCH), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "P", "bogen", "freigeben", str(self.m3), "--art", "grob", "--starten", "--von", "Entwickler"])
        self.assertNotEqual(rc, 0)
        self.assertIn("--starten gibt es nur mit --art plan", aus.getvalue())


if __name__ == "__main__":
    unittest.main()
