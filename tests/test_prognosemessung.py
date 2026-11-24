"""A2046 (V8, D1531 §8): Schätzung beim Start, Ist beim Ende je Paket (plan_ereignis prognose_start/prognose_ist) – über die
Aufsichtsrunde, also für jeden Abschlussweg; Trefferquote je Quelle abfragbar."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import db, kern, planung, prognosemessung as pm


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

    def paket(self, groesse="S"):
        return planung.schritt_setzen(self.con, self.pid, "TL", titel=f"Paket {groesse}", groesse=groesse, art="mechanisch", agent="CC1")

    def setzen(self, aid, status, begonnen=None, fertig=None, groesse=None):
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = ?, begonnen_utc = coalesce(?, begonnen_utc), fertig_utc = ?,"
                             " beleg = CASE WHEN ? = 'fertig' THEN 'abc1234' ELSE beleg END, groesse = coalesce(?, groesse) WHERE id = ?",
                             (status, begonnen, fertig, status, groesse, aid))

    def ereignisse(self, art):
        return [json.loads(r[0]) for r in self.con.execute("SELECT text FROM plan_ereignis WHERE art = ? ORDER BY id", (art,))]


class Messen(Grund):
    def test_schaetzung_beim_start_bleibt_ist_beim_ende(self):
        a = self.paket("S")                                                     # Vorgabe S = 1 h
        self.setzen(a, "laeuft", begonnen="2026-11-24T08:00:00Z")
        pm.runde(self.con, self.pid)
        pm.runde(self.con, self.pid)                                            # je Paket einmal
        self.assertEqual(self.ereignisse(pm.START), [{"aufgabe": a, "schaetzung_h": 1.0, "quelle": "Vorgabe S"}])
        self.setzen(a, "laeuft", groesse="M")                                   # die Schätzung ändert sich später – zählt nicht
        self.setzen(a, "fertig", fertig="2026-11-24T09:30:00Z")
        aus = pm.runde(self.con, self.pid)
        self.assertEqual(aus, [f"A{a}: geschätzt 1 h, gebraucht 1.5 h (×1.5)"])
        self.assertEqual(self.ereignisse(pm.IST), [{"aufgabe": a, "schaetzung_h": 1.0, "quelle": "Vorgabe S", "ist_h": 1.5, "faktor": 1.5}])
        self.assertEqual(pm.runde(self.con, self.pid), [])                     # nicht doppelt

    def test_ohne_start_gilt_die_schaetzung_beim_ende(self):
        a = self.paket("M")                                                     # zwischen zwei Runden begonnen und fertig
        self.setzen(a, "fertig", begonnen="2026-11-24T08:00:00Z", fertig="2026-11-24T09:00:00Z")
        pm.runde(self.con, self.pid)
        x = self.ereignisse(pm.IST)[0]
        self.assertEqual((x["schaetzung_h"], x["quelle"], x["faktor"]), (3.0, "Vorgabe M, beim Ende", 0.33))
        self.assertEqual(self.ereignisse(pm.START), [])

    def test_nie_begonnen_oder_verworfen_zaehlt_nicht(self):
        a = self.paket()
        b = self.paket()
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'verworfen', beleg = 'weg', begonnen_utc = '2026-11-24T08:00:00Z',"
                             " fertig_utc = '2026-11-24T08:10:00Z' WHERE id = ?", (b,))
        pm.runde(self.con, self.pid)
        self.assertEqual((self.ereignisse(pm.START), self.ereignisse(pm.IST)), ([], []))
        self.assertTrue(a)


class Quote(Grund):
    def test_trefferquote_je_quelle_und_befehl(self):
        for groesse, ende in (("S", "09:00"), ("S", "09:20"), ("S", "11:00"), ("M", "08:30")):   # ×1, ×1.33, ×3, ×0.17
            a = self.paket(groesse)
            self.setzen(a, "fertig", begonnen="2026-11-24T08:00:00Z", fertig=f"2026-11-24T{ende}:00Z")
        pm.runde(self.con, self.pid)
        q = pm.trefferquote(self.con, self.pid)
        self.assertEqual((q["n"], q["treffer"], q["quote"], q["zu_lang"], q["zu_kurz"]), (4, 2, 0.5, 1, 1))
        self.assertEqual(q["faktor_median"], 1.17)
        self.assertEqual(q["je_quelle"]["Vorgabe"]["n"], 4)
        self.assertEqual(pm.trefferquote(self.con, self.pid, seit_utc="2999-01-01")["n"], 0)
        from amw import cli
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus):
            rc = cli.main(["messung", "--prognose", "--projekt", "P", "--von", "TL"])
        self.assertFalse(rc)
        self.assertIn("Trefferquote 50 % (2 von 4 Paketen im Rahmen 0.67–1.5×)", aus.getvalue())
        self.assertIn("Vorgabe     50 % von   4", aus.getvalue())

    def test_ohne_messung(self):
        from amw import cli
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus):
            cli.main(["messung", "--prognose", "--projekt", "P", "--von", "TL"])
        self.assertIn("Noch keine Messung", aus.getvalue())


if __name__ == "__main__":
    unittest.main()
