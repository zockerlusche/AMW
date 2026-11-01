"""Tests für den Wecker im amw-dienst – die Pipe wird nachgebildet, es wird keine echte Sitzung geweckt."""
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import db, dienst, kern, pipe


class Wecker(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid, "CC2")
        self.gesendet = []
        self.lebt = True
        patch_s = mock.patch.object(pipe, "senden", side_effect=lambda p, k, t: self.gesendet.append((p, t)))
        patch_l = mock.patch.object(pipe, "lebt", side_effect=lambda p: self.lebt)
        patch_s.start()
        patch_l.start()
        self.addCleanup(patch_s.stop)
        self.addCleanup(patch_l.stop)
        self.d = dienst.Dienst(self.con)

    def tearDown(self):
        self.con.close()
        self.ordner.cleanup()

    def anmelden(self, kennung, sitzung="s1"):
        datei = os.path.join(self.ordner.name, f"{kennung}.json")
        with open(datei, "w", encoding="utf-8") as f:
            json.dump({"pipe": f"\\\\.\\pipe\\LOCAL\\cc-msg-{kennung}", "schluessel": "geheim", "sitzung": sitzung}, f)
        a = kern.agent_zeile(self.con, self.pid, kennung)
        with db.schreiben(self.con):
            db.einfuegen(self.con, "sitzung", agent_id=a["id"], claude_sitzung=sitzung, schluessel_datei=datei,
                         gestartet_utc=db.jetzt())

    def geweckt(self):
        return {(r[0], r[1]) for r in self.con.execute(
            "SELECT nachricht_id, agent FROM empfang WHERE geweckt_utc IS NOT NULL")}

    def test_weckt_nur_weckende_arten_und_nur_einmal(self):
        self.anmelden("CC1")
        n1, _ = kern.posten(self.con, self.pid, "TL", "CC1", "auftrag", "a")
        kern.posten(self.con, self.pid, "TL", "CC1", "info", "i")
        self.assertEqual(self.d.zustellen(), 1)
        self.assertEqual(self.geweckt(), {(n1, "CC1")})
        self.assertIn(f"#{n1} TL [auftrag] a", self.gesendet[0][1])
        self.assertNotIn("geheim", self.gesendet[0][1])
        self.assertEqual(self.d.zustellen(), 0)

    def test_nicht_angemeldet_bleibt_offen_bis_anmeldung(self):
        n1, _ = kern.posten(self.con, self.pid, "TL", "CC2", "auftrag", "a")
        self.assertEqual(self.d.zustellen(), 0)
        self.anmelden("CC2")
        self.assertEqual(self.d.zustellen(), 1)
        self.assertEqual(self.geweckt(), {(n1, "CC2")})

    def test_halt_laesst_nur_stopp_und_freigabe_durch(self):
        self.anmelden("CC1")
        kern.halt(self.con, self.pid, "TL", "CC1", "Pause")
        n_auftrag, _ = kern.posten(self.con, self.pid, "TL", "CC1", "auftrag", "später")
        self.d.zustellen()
        self.assertEqual([a for _, a in self.geweckt()], ["CC1"])
        self.assertNotIn((n_auftrag, "CC1"), self.geweckt())
        self.assertIn("HALT GILT", self.gesendet[0][1])
        kern.weiter(self.con, self.pid, "TL", "CC1")
        self.d.zustellen()
        self.assertIn((n_auftrag, "CC1"), self.geweckt())

    def test_fehlschlag_bleibt_offen_und_beendet_tote_sitzung(self):
        self.anmelden("CC1")
        kern.posten(self.con, self.pid, "TL", "CC1", "auftrag", "a")
        self.lebt = False
        with mock.patch.object(pipe, "senden", side_effect=pipe.ZustellFehler("weg")):
            self.assertEqual(self.d.zustellen(), 0)
        self.assertEqual(self.geweckt(), set())
        z = self.con.execute("SELECT zustand FROM sitzung").fetchone()[0]
        self.assertEqual(z, "beendet")

    def test_aufsicht_setzt_puls_oder_beendet(self):
        self.anmelden("CC1")
        self.d.aufsicht()
        s = self.con.execute("SELECT zustand, letzter_puls_utc FROM sitzung").fetchone()
        self.assertEqual(s[0], "aktiv")
        self.assertTrue(s[1])
        self.lebt = False
        self.d.aufsicht()
        self.assertEqual(self.con.execute("SELECT zustand FROM sitzung").fetchone()[0], "beendet")


if __name__ == "__main__":
    unittest.main()
