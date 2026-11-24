"""A2041 (D1531 §8, V6): eine Reihenfolge für Anzeige und Start – der Disponent startet p-Pakete in der Folge, die die AMW
anzeigt (reihenfolge.berechnen: aktiver Meilenstein zuerst, dann der längste Rest-Pfad, dann Rang), nicht mehr nur nach Rang
und Nummer. Die Regeln des Wächters gelten weiter: Pakete mit offenen Vorgängern fehlen."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import arbeitspaket, db, kern, planung, reihenfolge, waechter


class EineReihenfolge(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db"), "LOCALAPPDATA": os.path.join(self.ordner.name, "lad")})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        self.aktiv = planung.bogen_neu(self.con, self.pid, "TL", "Jetzt", abnahme="Bericht")
        self.spaeter = planung.bogen_neu(self.con, self.pid, "TL", "Später", abnahme="Bericht")
        planung.bogen_status(self.con, self.pid, "TL", self.aktiv, "aktiv")

    def paket(self, titel, bogen=None, rang=None, groesse="S"):
        aid = planung.schritt_setzen(self.con, self.pid, "TL", titel=titel, bogen_id=bogen, groesse=groesse, art="mechanisch")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET pruefbefehl = 'python -m unittest tests.test_x', dateibereich = ?, rang = coalesce(?, rang) WHERE id = ?",
                             (f"web/{aid}/", rang, aid))
        arbeitspaket.setzen(self.con, self.pid, "TL", aid, art="p")
        arbeitspaket.zustand_setzen(self.con, self.pid, "TL", aid, "startklar")
        return aid

    def start(self):
        return [x["id"] for x in waechter.reihenfolge(self.con, self.pid)]

    def anzeige(self):
        return [z["aid"] for z in reihenfolge.berechnen(self.con, self.pid) if z["zustand"] == "startklar"]

    def test_aktiver_meilenstein_vor_kleinem_rang(self):
        ohne = self.paket("Ohne Meilenstein", rang=1)
        spaet = self.paket("Später", bogen=self.spaeter, rang=2)
        jetzt = self.paket("Jetzt dran", bogen=self.aktiv, rang=50)
        self.assertEqual(self.start(), [jetzt, spaet, ohne])                     # vorher: nach Rang [ohne, spaet, jetzt]
        self.assertEqual(self.start(), self.anzeige())                           # Anzeige und Start sind eins

    def test_laengster_rest_pfad_zuerst(self):
        kurz = self.paket("Kurz", bogen=self.aktiv, rang=1)
        lang = self.paket("Mit Nachfolger", bogen=self.aktiv, rang=9)
        folge = self.paket("Folge", bogen=self.aktiv, rang=2, groesse="L")
        with db.schreiben(self.con):
            db.einfuegen(self.con, "abhaengigkeit", vor=lang, nach=folge)
        self.assertEqual(self.start(), [lang, kurz])                               # Folge fehlt (Vorgänger offen)
        self.assertEqual(self.start(), self.anzeige())
        self.assertEqual(waechter.reihenfolge(self.con, self.pid)[0]["platz"], 1)

    def test_befehl_nennt_den_platz(self):
        self.paket("Jetzt dran", bogen=self.aktiv)
        from amw import cli
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus):
            cli.main(["waechter", "reihenfolge", "--projekt", "Spiel", "--von", "TL"])
        self.assertIn("(Platz 1 der Reihenfolge, Rang", aus.getvalue())

    def test_ohne_berechnung_wie_bisher(self):
        b = self.paket("B", rang=1)
        a = self.paket("A", rang=3)
        with mock.patch.object(reihenfolge, "berechnen", side_effect=RuntimeError("kaputt")):
            self.assertEqual(self.start(), [b, a])                               # Rang, dann Nummer


if __name__ == "__main__":
    unittest.main()
