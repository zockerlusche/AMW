"""A1997: Wartet ein Agent nur noch auf einen anderen Agenten und kommt von dem nichts (warten_agent_min, Vorgabe 60) oder ist
seither eine Version live, bekommt der Lead einmal „CC1 wartet seit … auf CC2 (A…) – Grund noch aktuell?“, beim Release
auch der Wartende einen Weckruf. Feste Uhr; Befund 23.11. (A1993 wartete 3 h auf CCamw2)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import tempfile
import time
import unittest

from amw import db, kern, warten_agent

T0 = 1_795_000_000                                            # feste Uhr


def utc(sek):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(sek))


class WartenAufAgent(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        for k, r in (("TL", "lead"), ("CC1", None), ("CC2", None)):
            kern.agent_neu(self.con, self.pid, k, rolle=r)
        self.a = kern.aufgabe_neu(self.con, self.pid, "TL", "Eigener Stapel nach der Auslieferung", agent="CC1")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "start")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "wartet", auf="CC2")
        with db.schreiben(self.con):                          # Grund zur festen Zeit T0
            self.con.execute("UPDATE wartegrund SET angelegt_utc = ? WHERE aufgabe_id = ?", (utc(T0), self.a))

    def tearDown(self):
        self.con.close()
        self.ordner.cleanup()

    def post(self, agent, von="AMW"):
        return [r["kurz"] for r in kern.offene(self.con, self.pid, agent) if r["von"] == von]

    def zeit_der_letzten(self, sek):
        with db.schreiben(self.con):
            self.con.execute("UPDATE nachricht SET zeit_utc = ? WHERE id = (SELECT max(id) FROM nachricht)", (utc(sek),))

    def test_funkstille_meldet_den_lead_einmal(self):
        self.assertEqual(warten_agent.runde(self.con, T0 + 59 * 60), [])              # unter 60 min: nichts
        self.assertEqual(len(warten_agent.runde(self.con, T0 + 61 * 60)), 1)
        lead = self.post("TL")
        self.assertEqual(len(lead), 1)
        self.assertIn(f"CC1 wartet seit {utc(T0)[11:16]} UTC auf CC2 (A{self.a}) – Grund noch aktuell?", lead[0])
        self.assertEqual(self.post("CC1"), [])                                       # ohne Release kein Weckruf
        self.assertEqual(warten_agent.runde(self.con, T0 + 3 * 3600), [])            # einmal je Funkstille

    def test_nachricht_des_erwarteten_setzt_die_frist_neu(self):
        kern.posten(self.con, self.pid, "CC2", "CC1", "info", "Stapel läuft noch")   # ohne --aufgabe: Grund bleibt offen
        self.zeit_der_letzten(T0 + 30 * 60)
        self.assertEqual(warten_agent.runde(self.con, T0 + 80 * 60), [])             # 50 min seit der Nachricht
        self.assertEqual(len(warten_agent.runde(self.con, T0 + 91 * 60)), 1)
        self.assertIn(f"Seit {utc(T0 + 30 * 60)[11:16]} UTC", self.con.execute(
            "SELECT text FROM nachricht WHERE von = 'AMW' ORDER BY id DESC LIMIT 1").fetchone()[0])

    def test_release_weckt_sofort_lead_und_wartenden(self):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "release", projekt_id=self.pid, art="version", version="1.169.0", zeit_utc=utc(T0 + 600),
                         titel="Stapel CC2", eingetragen_von="CC2")
        self.assertEqual(len(warten_agent.runde(self.con, T0 + 20 * 60)), 1)        # vor den 60 min
        self.assertIn("Grund noch aktuell?", self.post("TL")[0])
        cc1 = self.post("CC1")
        self.assertEqual(len(cc1), 1)
        self.assertIn(f"1.169.0 ist live – du wartest auf CC2 (A{self.a})", cc1[0])
        self.assertEqual(warten_agent.runde(self.con, T0 + 30 * 60), [])            # einmal je Version
        self.assertEqual(warten_agent.runde(self.con, T0 + 61 * 60), [])            # Release schon gemeldet, keine zweite

    def test_aelteres_release_zaehlt_nicht(self):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "release", projekt_id=self.pid, art="version", version="1.168.0", zeit_utc=utc(T0 - 600),
                         titel="vorher", eingetragen_von="CC2")
        self.assertEqual(warten_agent.runde(self.con, T0 + 20 * 60), [])

    def test_nicht_nur_auf_agenten_keine_meldung(self):
        b = kern.aufgabe_neu(self.con, self.pid, "TL", "Zweites Stück", agent="CC1")
        self.assertEqual(warten_agent.runde(self.con, T0 + 2 * 3600), [])            # B ist startklar → CC1 hat Arbeit
        kern.aufgabe_status(self.con, self.pid, "CC1", b, "start")
        self.assertEqual(warten_agent.runde(self.con, T0 + 2 * 3600), [])            # läuft
        kern.aufgabe_status(self.con, self.pid, "CC1", b, "wartet", auf="Entwickler")
        self.assertEqual(warten_agent.runde(self.con, T0 + 2 * 3600), [])            # wartet (auch) auf den Menschen
        self.assertEqual(self.post("TL"), [])

    def test_grund_erledigt_keine_meldung(self):
        kern.posten(self.con, self.pid, "CC2", "CC1", "info", "1.169.0 live, du kannst", aufgabe_id=self.a)
        self.assertEqual(warten_agent.runde(self.con, T0 + 2 * 3600), [])

    def test_einstellung(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", warten_agent_min=120)
        self.assertEqual(warten_agent.runde(self.con, T0 + 90 * 60), [])
        self.assertEqual(len(warten_agent.runde(self.con, T0 + 121 * 60)), 1)
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "TL", warten_agent_min=1)


if __name__ == "__main__":
    unittest.main()
