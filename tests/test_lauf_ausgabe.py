"""A2044 (V4, D1531 §3): das Ende der Ausgabedatei eines Laufs als Abfrage – nur eigene Läufe, nur am PC, begrenzt aufs Ende."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import tempfile
import unittest
from unittest import mock

from amw import betrieb, db, kern, workbench


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
            self.pid2 = db.einfuegen(self.con, "projekt", name="Q", angelegt_utc=db.jetzt())
        self.datei = os.path.join(self.ordner.name, "lauf.txt")

    def lauf(self, pid=None, datei=None, status="laeuft"):
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "lauf", projekt_id=pid or self.pid, agent="CC1", beschreibung="Gesamtlauf", status=status,
                                angemeldet_utc=db.jetzt(), start_utc=db.jetzt(), ergebnis_datei=datei)

    def schreiben(self, text, art="w"):
        with open(self.datei, art + "b") as f:
            f.write(text.encode("utf-8"))


class Ausgabe(Grund):
    def test_ende_der_datei_mit_status(self):
        self.schreiben("# AMW L1\r\nRan 3 tests\r\n...\r\n")
        lid = self.lauf(datei=self.datei)
        a = betrieb.ausgabe(self.con, self.pid, lid)
        self.assertEqual((a["status"], a["zeilen"], a["gekuerzt"]), ("laeuft", ["# AMW L1", "Ran 3 tests", "..."], False))
        self.schreiben("OK\n", "a")
        self.assertEqual(betrieb.ausgabe(self.con, self.pid, lid)["zeilen"][-1], "OK")       # wächst mit

    def test_nur_das_ende_grosse_datei_und_viele_zeilen(self):
        self.schreiben("".join(f"Zeile {i:06d} " + "x" * 80 + "\n" for i in range(2000)))    # ~180 KB
        a = betrieb.ausgabe(self.con, self.pid, self.lauf(datei=self.datei))
        self.assertTrue(a["gekuerzt"])
        self.assertEqual(len(a["zeilen"]), betrieb.AUSGABE_ZEILEN)
        self.assertTrue(a["zeilen"][-1].startswith("Zeile 001999 "))
        self.assertTrue(all(z.startswith("Zeile ") for z in a["zeilen"]))                       # keine angeschnittene Zeile
        self.schreiben("".join(f"{i}\n" for i in range(5)))
        a = betrieb.ausgabe(self.con, self.pid, self.lauf(datei=self.datei), zeilen=3)
        self.assertEqual((a["zeilen"], a["gekuerzt"]), (["2", "3", "4"], True))

    def test_ohne_datei_kaputte_bytes_und_fremde_laeufe(self):
        self.assertEqual(betrieb.ausgabe(self.con, self.pid, self.lauf())["zeilen"], [])                       # schreibt keine Datei
        self.assertEqual(betrieb.ausgabe(self.con, self.pid, self.lauf(datei=self.datei + ".fehlt"))["zeilen"], [])
        with open(self.datei, "wb") as f:
            f.write(b"gut\n\xff\xfe kaputt\n")
        self.assertEqual(betrieb.ausgabe(self.con, self.pid, self.lauf(datei=self.datei))["zeilen"][1], "�� kaputt")
        fremd = self.lauf(pid=self.pid2, datei=self.datei)
        with self.assertRaisesRegex(kern.AmwFehler, f"L{fremd} gibt es nicht"):
            betrieb.ausgabe(self.con, self.pid, fremd)

    def test_abfrage_und_markierung_im_tagesverlauf(self):
        self.schreiben("eins\n")
        lid = self.lauf(datei=self.datei)
        ohne = self.lauf()
        self.assertEqual(workbench.daten_lauf_ausgabe(self.con, self.pid, {"lauf": [str(lid)]})["zeilen"], ["eins"])
        with self.assertRaises(kern.AmwFehler):
            workbench.daten_lauf_ausgabe(self.con, self.pid, {"lauf": ["x"]})
        heute = {x["id"]: x["ausgabe"] for x in betrieb.tagesverlauf(self.con, self.pid)["laeufe"] if x["eigen"]}
        self.assertEqual((heute[lid], heute[ohne]), (True, False))

    def test_nicht_in_der_synchronisierung(self):
        from amw import abgleich
        self.schreiben("geheim\n")
        self.lauf(datei=self.datei)
        a = abgleich.ansichten(self.con, self.pid)
        self.assertFalse(any(k.startswith("/api/lauf/ausgabe") for k in a))
        self.assertNotIn("geheim", str(a))


if __name__ == "__main__":
    unittest.main()
