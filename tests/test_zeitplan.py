"""A2045 (V7, D1531 §8): Zeitplan je Paket – Start und Ende aus Reihenfolge, Dauer und freien Plätzen; „gleichzeitig“ = gleiche
Startminute; „+n min“, wenn Laufendes länger dauert als geplant. Feste Uhr, Dauer nach Vorgabe (S 1 h, M 3 h)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import datetime
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import arbeitspaket as ap, db, kern, planung, workbench, zeitplan

JETZT = datetime.datetime(2026, 11, 24, 10, 0, tzinfo=datetime.timezone.utc)


def um(minuten):
    return (JETZT + datetime.timedelta(minutes=minuten)).strftime("%Y-%m-%dT%H:%M:%SZ")


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
            self.con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?",
                             (json.dumps({"platz_wurzel": os.path.join(self.ordner.name, "plaetze"), "plaetze": 1}), self.pid))
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        for k in ("CC1", "CC2"):
            kern.agent_neu(self.con, self.pid, k)

    def paket(self, titel, agent=None, groesse="S", p=False, nach=None, laeuft_seit=None):
        aid = planung.schritt_setzen(self.con, self.pid, "TL", titel=titel, groesse=groesse, art="mechanisch", nach=nach,
                                     **({"agent": agent} if agent else {}))
        if p:
            with db.schreiben(self.con):
                self.con.execute("UPDATE aufgabe SET pruefbefehl = 'python -m unittest tests.x', dateibereich = 'amw/x.py' WHERE id = ?",
                                 (aid,))
            ap.setzen(self.con, self.pid, "TL", aid, art="p")
        if laeuft_seit is not None:
            with db.schreiben(self.con):
                self.con.execute("UPDATE aufgabe SET status = 'laeuft', begonnen_utc = ? WHERE id = ?", (um(-laeuft_seit), aid))
        return aid

    def plan(self):
        return {x["aid"]: x for x in zeitplan.berechnen(self.con, self.pid, jetzt=JETZT)["pakete"]}


class Zeitplan(Grund):
    def test_start_ende_plaetze_agenten_vorgaenger_gleichzeitig(self):
        a = self.paket("läuft bei CC1", "CC1", laeuft_seit=30)
        b = self.paket("danach bei CC1", "CC1", groesse="M")
        c = self.paket("Headless 1", p=True)
        d = self.paket("Headless 2", p=True)
        e = self.paket("CC2 nach C", "CC2", nach=[c])
        f = self.paket("ohne Agent")
        z = self.plan()
        self.assertEqual((z[a]["start_utc"], z[a]["ende_utc"], z[a]["plus_min"]), (um(-30), um(30), 0))
        self.assertEqual((z[b]["start_utc"], z[b]["ende_utc"], z[b]["dauer_min"]), (um(30), um(210), 180))   # nach A beim selben Agenten
        self.assertEqual((z[c]["start_utc"], z[c]["ende_utc"]), (um(0), um(60)))                            # ein Platz: C zuerst (Nachfolger)
        self.assertEqual((z[d]["start_utc"], z[d]["ende_utc"]), (um(60), um(120)))                          # dann D
        self.assertEqual((z[e]["start_utc"], z[e]["nach"]), (um(60), [c]))                                  # wartet auf C
        self.assertEqual((z[f]["start_utc"], z[f]["hinweis"]), (um(0), "ohne Agent"))
        self.assertEqual(sorted(z[d]["gleichzeitig"]), [e])                                                 # gleiche Startminute
        self.assertEqual(sorted(z[c]["gleichzeitig"]), [f])
        self.assertEqual(z[a]["gleichzeitig"], [])                                                          # Laufendes nicht
        self.assertEqual((z[c]["art"], z[a]["art"]), ("headless", "fenster"))

    def test_ueberzogen_plus_minuten_und_nachfolger_ruecken(self):
        a = self.paket("zu lang", "CC1", laeuft_seit=90)                      # S = 60 min, läuft seit 90 → +30
        b = self.paket("danach", "CC1")
        z = self.plan()
        self.assertEqual((z[a]["ende_utc"], z[a]["plus_min"]), (um(0), 30))
        self.assertEqual(z[b]["start_utc"], um(0))
        self.assertIn("+30 min", zeitplan.zeile(z[a], ortszeit=lambda t: t[11:16]))

    def test_ohne_platz_und_zwei_plaetze(self):
        c = self.paket("H1", p=True)
        d = self.paket("H2", p=True)
        with db.schreiben(self.con):
            self.con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?",
                             (json.dumps({"platz_wurzel": os.path.join(self.ordner.name, "plaetze"), "plaetze": 2}), self.pid))
        z = self.plan()
        self.assertEqual((z[c]["start_utc"], z[d]["start_utc"]), (um(0), um(0)))                            # zwei Plätze: beide sofort
        self.assertEqual(z[c]["gleichzeitig"], [d])
        with db.schreiben(self.con):
            self.con.execute("UPDATE projekt SET einstellungen = '{}' WHERE id = ?", (self.pid,))
        z = self.plan()
        self.assertEqual(z[c]["hinweis"], "kein Platz")

    def test_api_und_befehl(self):
        self.paket("eins", "CC1")
        d = workbench.daten_zeitplan(self.con, self.pid)
        self.assertEqual((d["plaetze"], len(d["pakete"])), (1, 1))
        from amw import cli
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus):
            rc = cli.main(["bogen", "zeitplan", "--projekt", "P", "--von", "TL"])
        self.assertFalse(rc)
        self.assertIn("1 Headless-Platz/Plätze", aus.getvalue())
        self.assertIn("· 60 min · CC1 · eins", aus.getvalue())


if __name__ == "__main__":
    unittest.main()
