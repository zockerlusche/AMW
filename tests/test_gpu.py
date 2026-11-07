"""Fremde GPU-Last (1.30.1): melden ohne Fehlalarm – nur bei Dauerlast ohne angemeldeten Lauf, Entwickler weg, höchstens
einmal je Stunde; die AMW beendet nichts."""
import os
import tempfile
import unittest

from amw import db, gpu, kern


class Wache(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
            self.pid2 = db.einfuegen(self.con, "projekt", name="Q", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid2, "QL", rolle="lead")
        self.last, self.weg = 90, 900
        self.w = gpu.Wache(self.con, messen=lambda: (self.last, [("python.exe", 6144), ("ollama.exe", 512)]),
                           leerlauf=lambda: self.weg)

    def tearDown(self):
        self.con.close()
        self.ordner.cleanup()

    def runden(self, n, t=10000):
        aus = []
        for i in range(n):
            aus += self.w.runde(jetzt=t + i * 30)
        return aus

    def test_dauerlast_ohne_lauf_meldet_alle_leads_einmal_je_stunde(self):
        self.assertEqual(self.runden(2), [])                                  # erst nach 3 Messungen
        aus = self.runden(1, t=10060)
        self.assertEqual([a.split(":")[0] for a in aus], ["TL", "QL"])
        self.assertIn("python.exe (6.0 GB)", aus[0])
        self.assertEqual(self.runden(6, t=10100), [])                         # Pause 1 h
        self.assertEqual(len(self.runden(3, t=10060 + 3601)), 2)

    def test_kein_alarm_bei_lauf_kurzer_spitze_oder_entwickler_am_pc(self):
        self.weg = 60
        self.assertEqual(self.runden(5), [])                                  # Entwickler am PC: seine Last
        self.weg, self.last = 900, 20
        self.assertEqual(self.runden(5), [])                                  # unter der Grenze
        self.last = 90
        with db.schreiben(self.con):
            db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="TL", beschreibung="KI", status="laeuft", gpu=1,
                         angemeldet_utc=db.jetzt(), start_utc=db.jetzt())
        self.assertEqual(self.runden(5), [])                                  # angemeldeter GPU-Lauf
        self.con.execute("UPDATE lauf SET status = 'fertig'")
        self.w.hoch = 0
        self.assertEqual(self.runden(2), [])
        self.last = 10
        self.assertEqual(self.runden(1), [])                                  # Spitze vorbei: zählt neu
        self.last = 90
        self.assertEqual(self.runden(2), [])

    def test_ohne_nvidia_smi_still(self):
        w = gpu.Wache(self.con, messen=lambda: None, leerlauf=lambda: 900)
        self.assertEqual([w.runde(jetzt=1e6 + i) for i in range(5)], [[]] * 5)


if __name__ == "__main__":
    unittest.main()
