"""K8 / A1942 Teil (a): Änderungen von oben nach unten – ändert sich ein Thema (neue Fassung nach der Freigabe, oder Zurück),
zeigt die AMW die betroffenen Meilensteine mit ihren Paketen (nicht begonnen / läuft / fertig) und schlägt dem Lead die
Anpassung vor (neu planen, nicht begonnene anhalten) – angehalten wird nichts von selbst; laufende bauen zu Ende."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import arbeitspaket, cli, db, kern, planansicht, planung, themen


class K8(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        u.start()
        self.addCleanup(u.stop)
        for k in ("AMW_AGENT", "AMW_PROJEKT"):
            os.environ.pop(k, None)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.th = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", self.th, "Mit Firmen-Konto.")
        with db.schreiben(self.con):                  # die Fassung liegt vor der Freigabe und vor dem Meilenstein
            self.con.execute("UPDATE thema_fassung SET zeit_utc = '2026-11-01T08:00:00Z'")
            self.con.execute("UPDATE plan_ereignis SET zeit_utc = '2026-11-01T08:00:00Z'")
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.th)
        self.m = planung.bogen_neu(self.con, self.pid, "TL", "Anmelden", abnahme="Vorführung")
        self.laeuft = planung.schritt_setzen(self.con, self.pid, "TL", titel="SSO bauen", bogen_id=self.m, agent="CC1")
        self.offen = planung.schritt_setzen(self.con, self.pid, "TL", titel="Abmelden", bogen_id=self.m, agent="CC1")
        self.p = planung.schritt_setzen(self.con, self.pid, "TL", titel="Tests", bogen_id=self.m, pruefbefehl="python -m unittest")
        arbeitspaket.setzen(self.con, self.pid, "TL", self.p, art="p", modell="sonnet")
        for a in (self.laeuft, self.offen, self.p):
            themen.verweise_setzen(self.con, self.pid, "TL", a, [f"TH{self.th}"])
        kern.aufgabe_status(self.con, self.pid, "CC1", self.laeuft, "laeuft")
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m, "grob")

    def post(self, an):
        return [(r["art"], r["kurz"], r["text"]) for r in self.con.execute(
            "SELECT n.art, n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? AND n.von = 'AMW'"
            " ORDER BY n.id", (an,))]

    def ms(self):
        return next(x for x in planansicht.daten(self.con, self.pid)["meilensteine"] if x["id"] == self.m)

    def test_betroffen_nach_stand(self):
        b = planansicht.betroffen(self.con, self.pid, self.th)
        self.assertEqual(len(b), 1)
        self.assertEqual((b[0]["bogen"]["id"], sorted(b[0]["offen"]), b[0]["laeuft"]), (self.m, sorted([self.offen, self.p]), [self.laeuft]))
        self.assertEqual(self.ms()["geaendert"], [])                                         # noch nichts geändert

    def test_neue_fassung_meldet_dem_lead_und_zeigt_es_am_meilenstein(self):
        st = lambda a: self.con.execute("SELECT status, wartet_auf FROM aufgabe WHERE id = ?", (a,)).fetchone()
        vorher = tuple(st(self.offen))
        themen.pflegen(self.con, self.pid, "CC1", self.th, "Mit Firmen-Konto und Passkey.")
        art, kurz, text = next(x for x in self.post("TL") if x[1].startswith("Thema geändert: TH"))
        self.assertEqual((art, kurz), ("auftrag", f"Thema geändert: TH{self.th} „Anmeldung“ (Fassung 2) – betrifft 1 Meilenstein(e)"))
        self.assertIn("2 nicht begonnen, 1 laufend", text)
        self.assertIn(f"amw thema anhalten TH{self.th}", text)
        self.assertIn("angehalten wird nichts von selbst", text)
        self.assertEqual(self.ms()["geaendert"], [{"id": self.th, "name": "Anmeldung", "fassung": 2, "offen": sorted([self.offen, self.p])}])
        self.assertEqual(tuple(st(self.offen)), vorher)                                       # nichts von selbst angehalten
        self.assertNotEqual(arbeitspaket.lesen(self.con, self.p)["zustand"], "zurueckgestellt")

    def test_zurueck_meldet_auch(self):
        themen.zurueck(self.con, self.pid, kern.ENTWICKLER, self.th, "Passkey fehlt")
        self.assertTrue(any("(zurück)" in x[1] for x in self.post("TL")))
        self.assertEqual([g["id"] for g in self.ms()["geaendert"]], [self.th])

    def test_anhalten_nur_nicht_begonnene(self):
        themen.pflegen(self.con, self.pid, "CC1", self.th, "Neu.")
        with self.assertRaisesRegex(kern.AmwFehler, "Pakete anhalten dürfen"):
            planansicht.anhalten(self.con, self.pid, "CC1", self.th)
        weg = planansicht.anhalten(self.con, self.pid, kern.ENTWICKLER, self.th, self.m)
        self.assertEqual(sorted(weg), sorted([self.offen, self.p]))
        st = lambda a: self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (a,)).fetchone()[0]
        self.assertEqual((st(self.offen), st(self.laeuft)), ("wartet", "laeuft"))             # laufende bauen zu Ende
        self.assertEqual(arbeitspaket.lesen(self.con, self.p)["zustand"], "zurueckgestellt")
        self.assertIn("Thema TH", self.con.execute("SELECT wartet_auf FROM aufgabe WHERE id = ?", (self.offen,)).fetchone()[0])
        self.assertEqual(planansicht.anhalten(self.con, self.pid, kern.ENTWICKLER, self.th, self.m), [])   # schon angehalten
        self.assertEqual(next(x for x in planansicht.daten(self.con, self.pid)["meilensteine"] if x["id"] == self.m)["geaendert"][0]["offen"], [])

    def test_befehl_anhalten(self):
        themen.pflegen(self.con, self.pid, "CC1", self.th, "Neu.")
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus):
            rc = cli.main(["thema", "anhalten", f"TH{self.th}", "--meilenstein", str(planung.bogen_zeile(self.con, self.pid, self.m)["nr"]),
                           "--projekt", "Spiel", "--von", "TL"])
        self.assertEqual(rc, 0)
        self.assertIn("angehalten: A", aus.getvalue())


if __name__ == "__main__":
    unittest.main()
