"""Dauerlauf (A1759, Wunsch GlassWorld R15, Marcel W2171): kopflos, ohne KI/GPU/Fenster, mit fester Speichergrenze; läuft neben
dem schweren Lauf, seine Grenze zählt in die Vormerkung, der Dienst passt auf, dass er sie hält – und bittet sonst ums Beenden."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import tempfile
import unittest
from unittest import mock

from amw import belegung, betrieb, db, kern


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        self.addCleanup(self.con.close)
        self.p = {}
        for name in ("Glas", "Andere"):
            with db.schreiben(self.con):
                self.p[name] = db.einfuegen(self.con, "projekt", name=name, angelegt_utc=db.jetzt())
            kern.agent_neu(self.con, self.p[name], "TL", rolle="lead")
            kern.agent_neu(self.con, self.p[name], "GW2")
        for ziel, name, wert in ((betrieb, "cpu_laeufe", 1), (betrieb, "speicher_frei_gb", (20.0, 32.0)), (betrieb, "reserve_gb", 3.0)):
            p = mock.patch.object(ziel, name, return_value=wert)
            p.start()
            self.addCleanup(p.stop)
        self.pids = {}
        p = mock.patch.object(belegung, "lauf_pid", side_effect=lambda lid: self.pids.get(lid))
        p.start()
        self.addCleanup(p.stop)

    def dauerlauf(self, projekt="Glas", gb=4.0, **k):
        return betrieb.lauf_start(self.con, self.p[projekt], "GW2", "Spielsimulation Dauer", warten=True, speicher_frei=20.0,
                                  braucht_gb=gb, dauerlauf=True, **k)

    def status(self, lid):
        return self.con.execute("SELECT status FROM lauf WHERE id = ?", (lid,)).fetchone()[0]


class Anmelden(Grund):
    def test_nur_mit_grenze_und_kopflos(self):
        with self.assertRaises(kern.AmwFehler) as e:
            betrieb.lauf_start(self.con, self.p["Glas"], "GW2", "x", warten=True, speicher_frei=20.0, dauerlauf=True)
        self.assertIn("--braucht-gb", str(e.exception))
        for k in ({"schirm": True}, {"gpu": True}):
            with self.assertRaises(kern.AmwFehler):
                self.dauerlauf(**k)

    def test_laeuft_neben_dem_schweren_und_ist_vorgemerkt(self):
        schwer = betrieb.lauf_start(self.con, self.p["Andere"], "GW2", "Gesamtlauf", warten=True, speicher_frei=20.0, braucht_gb=6)
        self.assertEqual(self.status(schwer), "laeuft")                       # die eine CPU-Spur ist belegt …
        d = self.dauerlauf()
        self.assertEqual(self.status(d), "laeuft")                            # … der Dauerlauf läuft trotzdem daneben
        vor = {l["id"]: gb for l, gb in betrieb._vormerkungen(self.con)}
        self.assertEqual(vor.get(d), 4.0)                                     # seine Grenze ist vorgemerkt


class Aufpassen(Grund):
    def test_grenze_ueberschritten_und_speicher_knapp(self):
        d = self.dauerlauf()
        self.pids[d] = 100
        liste = [{"pid": 100, "eltern": 1, "name": "godot", "gb": 3.0}, {"pid": 101, "eltern": 100, "name": "sim", "gb": 2.5}]
        self.assertEqual(betrieb.dauerlauf_pruefen(self.con, liste=liste, frei=12.0), [(d, "grenze")])   # 5,5 > 4 GB
        k = self.con.execute("SELECT art, kurz, text FROM nachricht WHERE kurz LIKE 'Dauerlauf L%'").fetchone()
        self.assertEqual(k["art"], "korrektur")
        self.assertIn("mehr als seine Grenze von 4 GB", k["kurz"])
        self.assertIn("die AMW beendet nichts selbst", k["text"])
        self.assertEqual(betrieb.dauerlauf_pruefen(self.con, liste=liste, frei=12.0), [])           # einmal je Grund
        klein = [{"pid": 100, "eltern": 1, "name": "godot", "gb": 1.0}]
        self.assertEqual(betrieb.dauerlauf_pruefen(self.con, liste=klein, frei=2.0), [(d, "knapp")])  # unter der Reserve

    def test_anzeige_im_rechner(self):
        eigen, fremd = self.dauerlauf(), self.dauerlauf("Andere", gb=2.0)
        self.pids[eigen] = 100
        r = betrieb.dauerlaeufe(self.con, self.p["Glas"], liste=[{"pid": 100, "eltern": 1, "name": "x", "gb": 3.2}])
        self.assertEqual(r, [{"id": eigen, "agent": "GW2", "eigen": True, "grenze_gb": 4.0, "ist_gb": 3.2},
                             {"id": None, "agent": None, "eigen": False, "grenze_gb": 2.0, "ist_gb": None}])   # fremd: ohne Nummer
        self.assertIn("dauerlaeufe", betrieb.auslastung(self.con, self.p["Glas"]))


if __name__ == "__main__":
    unittest.main()
