"""Abnahme-Kette (doc/plan-federfuehrung.md B, TL #18899): Merge-OK des Leads je Aufgabe, nach CC2 GRÜN geht die Merge-Bitte
für genau diesen Stand von selbst an den Merge-Dienst – nie für einen überholten Stand, höchstens einmal, Vorgabe aus."""
import os
import tempfile
import unittest
from unittest import mock

from amw import betrieb, bruecke, db, kern, planung


class Kette(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.addCleanup(self.ordner.cleanup)
        umgebung = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        umgebung.start()
        self.addCleanup(umgebung.stop)
        for k in ("AMW_PROJEKT", "AMW_AGENT"):
            os.environ.pop(k, None)
        self.con = db.anlegen()
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        for k, r in (("TL", "lead"), ("CC1", None), ("CC2", None), ("CC3", None)):
            kern.agent_neu(self.con, self.pid, k, rolle=r)
        self.a = kern.aufgabe_neu(self.con, self.pid, "TL", "Feature bauen", agent="CC1", auftrag="bauen")

    def an(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", abnahme_kette="an", merge_dienst="CC3")

    def gruen(self, sha="abc1234567", zweig="feat", ergebnis="gruen"):
        prid = betrieb.pruefbitte(self.con, self.pid, "CC1", "CC2", zweig, sha, aufgabe_id=self.a)
        return prid, betrieb.pruefung_ergebnis(self.con, self.pid, "CC2", prid, ergebnis)

    def post(self, an, art=None):
        sql = ("SELECT n.art, n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ?"
               + (" AND n.art = ?" if art else "") + " ORDER BY n.id")
        return [dict(r) for r in self.con.execute(sql, (an, art) if art else (an,))]

    def test_vorgabe_aus(self):
        self.assertEqual(kern.projekt_wahl(self.con, self.pid, "abnahme_kette"), "aus")
        self.assertIsNone(self.gruen()[1])
        self.assertEqual(self.post("CC3"), [])
        self.assertIn("Kette ist aus", betrieb.freigabe_merge(self.con, self.pid, "TL", self.a))
        self.assertEqual(self.post("CC3"), [])

    def test_gruen_ohne_ok_fragt_den_lead_dann_geht_die_bitte(self):
        self.an()
        prid, _ = self.gruen()
        frage = [m for m in self.post("TL", "meldung") if "Merge-OK?" in m["kurz"]]
        self.assertEqual(len(frage), 1)
        self.assertIn(f"amw freigabe merge A{self.a}", frage[0]["kurz"])
        self.assertEqual(self.post("CC3"), [])
        text = betrieb.freigabe_merge(self.con, self.pid, "TL", self.a)
        self.assertIn("Merge-Bitte an CC3", text)
        bitte = self.post("CC3", "auftrag")
        self.assertEqual(len(bitte), 1)
        self.assertIn("abc1234567", bitte[0]["text"])                     # genau der Stand, ganz
        self.assertIn(f"P{prid}", bitte[0]["kurz"])
        self.assertTrue(any("Kopie: Merge-Bitte" in m["kurz"] for m in self.post("CC1")))
        self.assertIn("schon raus", betrieb.freigabe_merge(self.con, self.pid, "TL", self.a))   # nie doppelt
        self.assertEqual(len(self.post("CC3", "auftrag")), 1)

    def test_ok_vorher_dann_sofort_nach_gruen(self):
        self.an()
        self.assertIn("sobald eine Prüfung", betrieb.freigabe_merge(self.con, self.pid, kern.ENTWICKLER, self.a))
        _, kette = self.gruen()
        self.assertIn("Merge-Bitte an CC3", kette)
        self.assertEqual(len(self.post("CC3", "auftrag")), 1)
        self.assertFalse([m for m in self.post("TL", "meldung") if "Merge-OK?" in m["kurz"]])

    def test_neuer_stand_heisst_neue_pruefung(self):
        self.an()
        betrieb.freigabe_merge(self.con, self.pid, "TL", self.a)
        p1 = betrieb.pruefbitte(self.con, self.pid, "CC1", "CC2", "feat", "1111111111", aufgabe_id=self.a)
        betrieb.pruefbitte(self.con, self.pid, "CC1", "CC2", "feat", "2222222222", aufgabe_id=self.a)
        kette = betrieb.pruefung_ergebnis(self.con, self.pid, "CC2", p1, "gruen")    # GRÜN kommt spät für den alten Stand
        self.assertIn("überholt", kette)
        self.assertEqual(self.post("CC3"), [])
        self.gruen(sha="3333333333", ergebnis="rot")
        self.assertEqual(self.post("CC3"), [])

    def test_zurueck_und_zweig(self):
        self.an()
        betrieb.freigabe_merge(self.con, self.pid, "TL", self.a, zweig="anders")
        self.gruen(zweig="feat")
        self.assertEqual(self.post("CC3"), [])                              # OK galt nur für den Zweig „anders“
        self.assertIn("Merge-Bitte an CC3", betrieb.freigabe_merge(self.con, self.pid, "TL", self.a))   # für alle Zweige
        self.assertEqual(len(self.post("CC3", "auftrag")), 1)
        betrieb.freigabe_merge(self.con, self.pid, "TL", self.a, zurueck=True)
        self.gruen(sha="def4567890")
        self.assertEqual(len(self.post("CC3", "auftrag")), 1)                 # zurückgenommen: keine neue Bitte
        self.assertEqual(len([m for m in self.post("TL", "meldung") if "Merge-OK?" in m["kurz"]]), 2)

    def test_rechte_und_einstellung(self):
        with self.assertRaises(kern.AmwFehler):
            betrieb.freigabe_merge(self.con, self.pid, "CC1", self.a)
        with self.assertRaises(kern.AmwFehler):
            betrieb.freigabe_merge(self.con, self.pid, "TL", 9999)
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "TL", merge_dienst="Niemand")
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "TL", abnahme_kette="vielleicht")
        kern.projekt_einstellen(self.con, self.pid, "TL", abnahme_kette="an")
        self.assertFalse(betrieb.kette_an(self.con, self.pid))              # ohne Merge-Dienst bleibt sie aus
        self.an()
        self.assertTrue(betrieb.kette_an(self.con, self.pid))

    def test_fertige_aufgabe_bekommt_keine_bitte(self):
        self.an()
        self.gruen()
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc1234' WHERE id = ?", (self.a,))
        self.assertIn("keine Merge-Bitte", betrieb.freigabe_merge(self.con, self.pid, "TL", self.a))
        self.assertEqual(self.post("CC3"), [])

    def test_umbenennen_nimmt_den_merge_dienst_mit(self):
        self.an()
        kern.agent_umbenennen(self.con, self.pid, "TL", "CC3", "CCengine")
        self.assertEqual(betrieb.merge_dienst(self.con, self.pid), "CCengine")
        self.assertIn("Du bist Merge-Dienst", " ".join(planung.kontext_zeilen(self.con, self.pid, "CCengine")))
        betrieb.freigabe_merge(self.con, self.pid, "TL", self.a)
        self.gruen()
        self.assertEqual(len(self.post("CCengine", "auftrag")), 1)

    def test_kontext_cli_und_bruecke(self):
        self.an()
        self.assertIn("Abnahme-Kette an", " ".join(planung.kontext_zeilen(self.con, self.pid, "TL")))
        self.assertIn("Du bist Merge-Dienst", " ".join(planung.kontext_zeilen(self.con, self.pid, "CC3")))
        self.assertNotIn("Merge-Dienst", " ".join(planung.kontext_zeilen(self.con, self.pid, "CC1")))
        from amw import cli
        with mock.patch("sys.stdout"):
            self.assertIn(cli.main(["freigabe", "merge", f"A{self.a}", "--von", "TL", "--projekt", "P"]), (0, None))
        self.assertTrue(betrieb.merge_ok(self.con, self.pid, self.a))
        with tempfile.TemporaryDirectory() as eingang:
            args = bruecke.argumente({"befehl": "freigabe", "aktion": "merge", "id": f"A{self.a}"}, eingang)
            self.assertEqual(args[:3], ["freigabe", "merge", f"A{self.a}"])


if __name__ == "__main__":
    unittest.main()
