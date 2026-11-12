"""Versionshinweise ohne KI: Satz für Nutzer und Gruppe beim Abschließen, Entwurf aus den fertigen Aufgaben seit der
letzten Version (mit Vorschlag aus der Zusammenfassung, wenn der Satz fehlt), Eintragen einer Version, Daten der Seite."""
import os
import tempfile
import unittest

from amw import db, kern, versionshinweise, wissen, workbench


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")

    def fertig(self, titel, zusammenfassung, **mehr):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel, agent="CC1")
        kern.aufgabe_status(self.con, self.pid, "CC1", aid, "start")
        kern.aufgabe_status(self.con, self.pid, "CC1", aid, "fertig", beleg="abc1234", zusammenfassung=zusammenfassung, **mehr)
        return aid


class Entwurf(Grund):
    def test_satz_und_gruppe_vom_agenten_gehen_vor(self):
        a = self.fertig("Export als CSV", "csv.py mit Spaltenkopf (Fix 1a2b3c4)", hinweis="Listen lassen sich als CSV-Datei speichern.", gruppe="neu")
        b = self.fertig("Absturz beim Speichern behoben", "Speichern bricht bei leerem Namen sauber ab, Release 1.2.3")
        c = self.fertig("Doku aufgeräumt", "Nicht umgesetzt, Entscheidung des Leads")
        e = versionshinweise.entwurf(self.con, self.pid)
        self.assertEqual(e["neu"], [{"id": a, "text": "Listen lassen sich als CSV-Datei speichern.", "vorschlag": False}])
        self.assertEqual(e["behoben"], [{"id": b, "text": "Speichern bricht bei leerem Namen sauber ab", "vorschlag": True}])
        self.assertNotIn(c, [x["id"] for g in e.values() for x in g])                          # nichts ausgeliefert
        text = versionshinweise.als_text(e)
        self.assertEqual(text, "### Neu\n- Listen lassen sich als CSV-Datei speichern.\n\n### Behoben\n- Speichern bricht bei leerem Namen sauber ab")
        self.assertIn(f"(A{a})", versionshinweise.als_text(e, mit_aufgaben=True))
        with self.assertRaises(kern.AmwFehler):
            self.fertig("x", "y", gruppe="sonstiges")

    def test_version_eintragen_uebernimmt_den_entwurf_und_beginnt_neu(self):
        a = self.fertig("Filter", "Filter nach Datum", hinweis="Die Liste lässt sich nach Datum filtern.", gruppe="verbessert")
        rid, _ = wissen.release_version(self.con, self.pid, "TL", "1.1.0", "Filter")
        r = self.con.execute("SELECT text_oeffentlich, aufgaben FROM release WHERE id = ?", (rid,)).fetchone()
        self.assertEqual(r["text_oeffentlich"], "### Verbessert\n- Die Liste lässt sich nach Datum filtern.")
        self.assertEqual(r["aufgaben"], f"A{a}")
        self.assertEqual(versionshinweise.als_text(versionshinweise.entwurf(self.con, self.pid)), "")     # danach leer
        self.fertig("Mehr", "Neue Ansicht", hinweis="Neue Ansicht für Termine.", gruppe="neu")
        rid2, _ = wissen.release_version(self.con, self.pid, "TL", "1.2.0", "Termine", oeffentlich="### Neu\n- Eigener Text.")
        self.assertEqual(self.con.execute("SELECT text_oeffentlich FROM release WHERE id = ?", (rid2,)).fetchone()[0], "### Neu\n- Eigener Text.")
        d = workbench.daten_versionshinweise(self.con, self.pid)
        self.assertEqual([v["version"] for v in d["versionen"]], ["1.2.0", "1.1.0"])
        self.assertEqual(sum(len(v) for v in d["entwurf"].values()), 0)

    def test_satz_bereinigt_interne_verweise(self):
        self.assertEqual(versionshinweise.satz("STARTSEITE: Team als Baum (W9999, #99999), live geprüft. Rest"), "Startseite: Team als Baum.")
        self.assertEqual(versionshinweise.satz(""), "")


if __name__ == "__main__":
    unittest.main()
