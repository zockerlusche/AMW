"""Knopf „Vorziehen“ (A1764, Marcel 15.11. 12:21 fand ihn nicht): wartende Läufe dieses Projekts in der Rechner-Kachel, vorziehen
über die Workbench – am PC der Mensch, online nur System-Admins (Klasse „system“)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import tempfile
import unittest
from unittest import mock

from amw import aktionen, benutzer, betrieb, db, kern


class Vorziehen(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        self.addCleanup(self.con.close)
        self.p = {}
        for name in ("Eins", "Zwei"):
            with db.schreiben(self.con):
                self.p[name] = db.einfuegen(self.con, "projekt", name=name, angelegt_utc=db.jetzt())
            kern.agent_neu(self.con, self.p[name], "TL", rolle="lead")
            kern.agent_neu(self.con, self.p[name], "CC1")
        for ziel, name, wert in ((betrieb, "cpu_laeufe", 1), (betrieb, "speicher_frei_gb", (32.0, 32.0))):
            q = mock.patch.object(ziel, name, return_value=wert)
            q.start()
            self.addCleanup(q.stop)

    def lauf(self, projekt, text):
        return betrieb.lauf_start(self.con, self.p[projekt], "CC1", text, warten=True, speicher_frei=32.0)

    def test_kachel_zeigt_eigene_und_knopf_zieht_vor(self):
        self.lauf("Zwei", "läuft schon")
        fremd = self.lauf("Zwei", "fremd wartet")
        eigen = self.lauf("Eins", "Gesamtlauf")
        r = betrieb.auslastung(self.con, self.p["Eins"])
        self.assertEqual([(w["id"], w["platz"]) for w in r["eigene_wartend"]], [(eigen, 2)])     # fremde nicht mit Nummer
        aktionen.ausfuehren(self.con, self.p["Eins"], "/api/lauf/vorziehen", {"lauf": eigen})
        self.assertEqual([l["id"] for l in betrieb.wartende(self.con)], [eigen, fremd])
        with self.assertRaises(aktionen.Ungueltig):
            aktionen.ausfuehren(self.con, self.p["Eins"], "/api/lauf/vorziehen", {"lauf": fremd})   # nur Läufe dieses Projekts

    def test_online_nur_system_admin(self):
        self.assertEqual(benutzer.klasse("/api/lauf/vorziehen"), "system")
        with open(os.path.join(os.path.dirname(os.path.dirname(benutzer.__file__)), "web", "inc", "lib.php"), encoding="utf-8") as f:
            self.assertIn("'/api/lauf/vorziehen'", f.read().split("function eingabe_klasse")[1].split("return 'system'")[0])
        with self.assertRaises(aktionen.Ungueltig):
            aktionen.ausfuehren(self.con, self.p["Eins"], "/api/lauf/vorziehen", {"lauf": 1, "_benutzer": "bea"}, kanal="netz")


if __name__ == "__main__":
    unittest.main()
