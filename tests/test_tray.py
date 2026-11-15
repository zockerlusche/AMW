"""Symbol im Infobereich (A1746): Zustand, Menü und Aktionen als Daten (ohne Fenster – kein Symbol erscheint im Test), dazu
„Ich bin kurz da“: Eingaben schließen den Bildschirm dann nicht, neue Fenster-Läufe warten trotzdem auf Ruhe."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import ctypes
import os
import tempfile
import time
import unittest

from amw import db, kern, schirm, tray


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        schirm.kurz_da(self.con, 0)
        self.addCleanup(lambda: schirm.kurz_da(self.con, 0))


class Menue(Grund):
    def test_belegt_frei_kurz(self):
        self.assertEqual(tray.lage(self.con)["art"], "zu")
        self.assertEqual([e[0] for e in tray.menue("zu")][0], "Für Agenten freigeben")
        self.assertEqual(tray.ausfuehren(self.con, "bis:2h", jetzt=time.time())[:8], "frei bis")
        l = tray.lage(self.con)
        self.assertEqual(l["art"], "frei")
        self.assertIn("Frei für Agenten bis", l["titel"])
        self.assertEqual(tray.menue("frei")[0][0], "Ich bin kurz da")
        tray.ausfuehren(self.con, "kurz:30")
        l = tray.lage(self.con)
        self.assertEqual(l["art"], "kurz")
        self.assertIn("kurz da bis", l["titel"])
        self.assertIn("weg", [e[0] for e in tray.menue("kurz")])
        tray.ausfuehren(self.con, "weg")
        self.assertEqual(tray.lage(self.con)["art"], "frei")
        tray.ausfuehren(self.con, "zu")
        self.assertEqual(tray.lage(self.con)["art"], "zu")

    def test_kurz_da_nur_bei_freiem_bildschirm(self):
        with self.assertRaises(kern.AmwFehler):
            tray.ausfuehren(self.con, "kurz:15")

    def test_symbol_datei_ist_ein_icon(self):
        daten = tray.ico_bytes(tray.FARBEN["frei"])
        self.assertEqual(daten[:6], b"\x00\x00\x01\x00\x01\x00")
        if os.name != "nt":
            return
        pfad = os.path.join(self.ordner.name, "f.ico")
        with open(pfad, "wb") as f:
            f.write(daten)
        u = ctypes.windll.user32
        u.LoadImageW.restype = ctypes.c_void_p
        u.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        h = u.LoadImageW(None, pfad, 1, 0, 0, 0x10 | 0x40)
        self.assertTrue(h)                                                     # Windows liest es als Symbol
        u.DestroyIcon.argtypes = [ctypes.c_void_p]
        u.DestroyIcon(h)


class KurzDa(Grund):
    def test_eingaben_schliessen_nicht_neue_fensterlaeufe_warten(self):
        schirm.setzen(self.con, self.pid, kern.ENTWICKLER, True, "weg")
        t = time.time()
        schirm.kurz_da(self.con, 15, jetzt=t)
        self.assertEqual(schirm.pruefen(self.con, leerlauf=2, jetzt=t + 300), [])     # erste Eingabe
        self.assertEqual(schirm.pruefen(self.con, leerlauf=1, jetzt=t + 320), [])     # zweite: früher zu
        self.assertTrue(schirm.zustand(self.con)["frei"])
        self.assertIn("Ruhe", schirm.sperrgrund(self.con, leerlauf=5))                # neue Fenster-Läufe warten
        self.assertIsNone(schirm.sperrgrund(self.con, leerlauf=schirm.RUHE_S + 1))

    def test_nach_ablauf_wieder_wie_immer_und_zu_beendet_kurz_da(self):
        schirm.setzen(self.con, self.pid, kern.ENTWICKLER, True, "weg")
        t = time.time()
        schirm.kurz_da(self.con, 15, jetzt=t)
        self.assertIsNone(schirm.kurz_da_bis(t + 16 * 60))
        schirm.setzen(self.con, self.pid, kern.ENTWICKLER, False, "da")
        self.assertIsNone(schirm.kurz_da_bis())


if __name__ == "__main__":
    unittest.main()
