"""Tests für die Überwachung: Projekt-Server (Ausfall, Neustart, Grenze) und Stillstand-Warnungen."""
import os
import tempfile
import time
import unittest

from amw import betrieb, db, kern, ueberwachung


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        for k, r in (("TL", "lead"), ("CC1", None)):
            kern.agent_neu(self.con, self.pid, k, rolle=r)

    def tearDown(self):
        self.con.close()
        self.ordner.cleanup()

    def an_tl(self):
        return [r[0] for r in self.con.execute("SELECT n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id"
                                               " WHERE e.agent = 'TL' ORDER BY n.id")]


class Server(Grund):
    def setUp(self):
        super().setUp()
        self.lebt, self.gestartet = True, []
        ueberwachung.server_anmelden(self.con, self.pid, "CC1", "editor", 8766, "pythonw srv.py", None, neustart=True)

    def runde(self):
        return ueberwachung.server_pruefen(self.con, self.pid, pruefen=lambda port: self.lebt,
                                           start=lambda s: self.gestartet.append(s["name"]))

    def zustand(self):
        return self.con.execute("SELECT zustand FROM server WHERE name = 'editor'").fetchone()[0]

    def test_ausfall_melden_erst_in_zweiter_runde_neu_starten(self):
        self.runde()
        self.assertEqual(self.zustand(), "laeuft")
        self.lebt = False
        self.runde()                                         # erste Runde aus: nur melden
        self.assertEqual((self.zustand(), self.gestartet), ("aus", []))
        self.assertIn("Server editor (Port 8766) ist AUS", self.an_tl())
        self.runde()                                         # zweite Runde aus: Neustart
        self.assertEqual(self.gestartet, ["editor"])
        self.lebt = True
        self.runde()
        self.assertIn("Server editor (Port 8766) läuft wieder", self.an_tl())
        self.assertEqual(self.con.execute("SELECT ausfaelle FROM server").fetchone()[0], 1)

    def test_hoechstens_drei_neustarts_je_stunde_dann_meldung(self):
        self.lebt = False
        for _ in range(8):
            self.runde()
        self.assertEqual(len(self.gestartet), ueberwachung.NEUSTARTS_JE_STUNDE)
        self.assertEqual(sum("ich höre auf" in k for k in self.an_tl()), 1)

    def test_ohne_neustart_nur_meldung_und_startbefehl_pflicht(self):
        with self.assertRaises(kern.AmwFehler):
            ueberwachung.server_anmelden(self.con, self.pid, "CC1", "x", 9000, neustart=True)
        ueberwachung.server_anmelden(self.con, self.pid, "CC1", "editor", 8766)     # ändern: kein Neustart mehr
        self.lebt = False
        for _ in range(3):
            self.runde()
        self.assertEqual(self.gestartet, [])
        self.assertTrue(any(w["art"] == "server" for w in ueberwachung.warnungen(self.con, self.pid)))

    def test_abmelden(self):
        ueberwachung.server_abmelden(self.con, self.pid, "CC1", "editor")
        self.assertEqual(self.runde(), [])
        with self.assertRaises(kern.AmwFehler):
            ueberwachung.server_abmelden(self.con, self.pid, "CC1", "editor")


class Stillstand(Grund):
    def setUp(self):
        super().setUp()
        aid = self.con.execute("SELECT id FROM agent WHERE kennung = 'CC1'").fetchone()[0]
        with db.schreiben(self.con):
            db.einfuegen(self.con, "sitzung", agent_id=aid, gestartet_utc=db.jetzt())

    def test_weckruf_ohne_reaktion_warnt_meldung_danach_nicht(self):
        nid, _ = kern.posten(self.con, self.pid, "TL", "CC1", "auftrag", "bitte bauen")
        vor_40 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 40 * 60))
        self.con.execute("UPDATE empfang SET geweckt_utc = ? WHERE nachricht_id = ?", (vor_40, nid))
        w = ueberwachung.warnungen(self.con, self.pid)
        self.assertEqual([x["art"] for x in w], ["stillstand"])
        self.assertIn("CC1 reagiert nicht", w[0]["text"])
        kern.posten(self.con, self.pid, "CC1", "TL", "meldung", "bin dran")       # lebt, nur nicht abgehakt
        self.assertEqual(ueberwachung.warnungen(self.con, self.pid), [])

    def test_lauf_ueber_der_erwarteten_dauer(self):
        lid = betrieb.lauf_start(self.con, self.pid, "CC1", "Build", speicher_frei=20, erwartet_min=10)
        self.assertEqual(ueberwachung.warnungen(self.con, self.pid), [])
        vor_25 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 25 * 60))
        self.con.execute("UPDATE lauf SET start_utc = ? WHERE id = ?", (vor_25, lid))
        self.assertIn(f"L{lid}", ueberwachung.warnungen(self.con, self.pid)[0]["text"])

    def test_waechter_meldet_jede_warnung_einmal_an_den_lead(self):
        lid = betrieb.lauf_start(self.con, self.pid, "CC1", "Build", speicher_frei=20)
        vor_3h = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3 * 3600))
        self.con.execute("UPDATE lauf SET start_utc = ? WHERE id = ?", (vor_3h, lid))
        w = ueberwachung.Waechter(self.con)
        w.runde()
        w.runde()
        self.assertEqual(sum(k.startswith("Achtung: Lauf") for k in self.an_tl()), 1)


if __name__ == "__main__":
    unittest.main()
