"""A1985 (Befund 23.11., #30876): die Versionszeile der Release-Kette trägt die Hinweise GENAU dieses Stands (vorher die der
vorigen Auslieferung, weil sie vor dem Schließen der Aufgaben eingetragen wurde); die Zusammenfassung der Kette („Ausgeliefert
in …“) wird nie zum Satz; amw release berichtigen (Lead) setzt den Text einer eingetragenen Version neu."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import unittest

from amw import betrieb, db, kern, versionshinweise, wissen
from tests import test_auslieferung as ta


class Versionszeile(unittest.TestCase):
    setUp, g, stand, extern, kette, gesamtlauf = (ta.Kette.setUp, ta.Kette.g, ta.Kette.stand, ta.Kette.extern, ta.Kette.kette,
                                                  ta.Kette.gesamtlauf)

    def text(self, version):
        return self.con.execute("SELECT text_oeffentlich, aufgaben FROM release WHERE art = 'version' AND version = ?", (version,)).fetchone()

    def test_zeile_traegt_den_hinweis_dieses_stands(self):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Neues Ding", "CC1")
        betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "neu", self.sha, "x", aid, gruppe="neu", hinweis="Das neue Ding ist da.")
        betrieb.pruefung_ergebnis(self.con, self.pid, "TL", self.con.execute("SELECT max(id) FROM pruefung").fetchone()[0], "gruen")
        betrieb.freigabe_merge(self.con, self.pid, "TL", aid)
        self.gesamtlauf()
        self.kette().ausliefern("neu")
        r = self.text("1.1.0")
        self.assertIn("Das neue Ding ist da.", r["text_oeffentlich"] or "")              # nicht erst in der nächsten Version
        self.assertEqual(r["aufgaben"], f"A{aid}")
        self.assertEqual(versionshinweise.als_text(versionshinweise.entwurf(self.con, self.pid)), "")   # danach leer
        kern.projekt_ordner_setzen(self.con, self.pid, self.repo)                              # main hat jetzt „## 1.1.0“
        wissen.release_berichtigen(self.con, self.pid, "TL", "1.1.0", aus_changelog=True)
        self.assertIn("Neues Ding für alle.", self.text("1.1.0")["text_oeffentlich"])

    def test_satz_der_kette_wird_nie_zum_hinweis(self):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Liste nach Datum sortieren", "CC1")
        kern.aufgabe_status(self.con, self.pid, "AMW", aid, "fertig", beleg="abc1234", automatik=True,
                            zusammenfassung="Ausgeliefert in 1.165.0 (main 51ecb013).")
        with db.schreiben(self.con):                                                           # wie vor A1954: ohne Hinweis
            self.con.execute("UPDATE aufgabe SET hinweis = NULL, hinweis_gruppe = NULL WHERE id = ?", (aid,))
        texte = [x["text"] for g in versionshinweise.entwurf(self.con, self.pid).values() for x in g]
        self.assertEqual(texte, ["Liste nach Datum sortieren"])

    def test_berichtigen_aus_dem_changelog_nur_lead(self):
        wissen.release_version(self.con, self.pid, "TL", "1.0.1", "Falsch", oeffentlich="### Neu\n- Inhalt der vorigen Version")
        self.g("switch", "-q", "main")
        kern.projekt_ordner_setzen(self.con, self.pid, self.repo)
        with self.assertRaisesRegex(kern.AmwFehler, "kein Abschnitt"):
            wissen.release_berichtigen(self.con, self.pid, "TL", "1.0.1", aus_changelog=True)
        with self.assertRaises(kern.AmwFehler):
            wissen.release_berichtigen(self.con, self.pid, "CC1", "1.0.1", oeffentlich="x")
        wissen.release_berichtigen(self.con, self.pid, "TL", "1.0.1", oeffentlich="### Behoben\n- Richtiger Text.", aufgaben="A7")
        self.assertEqual(tuple(self.text("1.0.1")), ("### Behoben\n- Richtiger Text.", "A7"))
        e = json.loads(self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'release_berichtigt'").fetchone()[0])
        self.assertEqual((e["version"], e["alt_text"]), ("1.0.1", "### Neu\n- Inhalt der vorigen Version"))
        wissen.release_version(self.con, self.pid, "TL", "1.0.2", "Anfang")                     # CHANGELOG auf main hat „## 1.0.0“
        with self.assertRaisesRegex(kern.AmwFehler, "kein Abschnitt"):
            wissen.release_berichtigen(self.con, self.pid, "TL", "1.0.2", aus_changelog=True)


if __name__ == "__main__":
    unittest.main()
