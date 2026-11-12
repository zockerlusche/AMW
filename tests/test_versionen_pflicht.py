"""Grund-Regelwerk G-2: Versionen als Pflicht – Einstellung, Prüfung beim Eintragen, Plan-Check, Meilenstein-Abschluss,
Pflicht-Kontext."""
import os
import tempfile
import unittest

from amw import db, kern, planung, wissen


class Versionen(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")

    def codes(self):
        return {x["code"]: x for x in planung.pruefen(self.con, self.pid)}

    def aufgabe_fertig(self, bogen=None, tage_alt=0):
        with db.schreiben(self.con):
            zeit = "2020-01-01T00:00:00Z" if tage_alt else db.jetzt()
            return db.einfuegen(self.con, "aufgabe", projekt_id=self.pid, titel="Fertig", status="fertig", einstufung="aktiv",
                                angelegt_utc=zeit, angelegt_von="TL", fertig_utc=zeit, bogen_id=bogen)

    def test_vorgabe_empfohlen_nur_hinweis_pflicht_fehler_aus_nichts(self):
        self.assertEqual(kern.projekt_wahl(self.con, self.pid, "versionen"), "empfohlen")
        self.assertEqual(self.codes()["ohne_version_hinweis"]["stufe"], "hinweis")
        kern.projekt_einstellen(self.con, self.pid, "TL", versionen="pflicht")
        c = self.codes()
        self.assertEqual(c["ohne_version"]["stufe"], "fehler")
        self.assertIn("0.1.0", c["ohne_version"]["werte"]["vorschlag"])
        kern.projekt_einstellen(self.con, self.pid, "TL", versionen="aus")
        self.assertFalse({"ohne_version", "ohne_version_hinweis", "unveroeffentlicht"} & set(self.codes()))
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "TL", versionen="immer")

    def test_eintragen_prueft_form_und_reihenfolge(self):
        wissen.release_version(self.con, self.pid, "TL", "1.2.3", "erste")
        for falsch, wort in (("1.2", "Form"), ("v1.3.0", "Form"), ("1.2.3", "gibt es schon"), ("1.2.2", "nicht größer"), ("1.1.9", "nicht größer")):
            with self.assertRaises(kern.AmwFehler) as e:
                wissen.release_version(self.con, self.pid, "TL", falsch, "x")
            self.assertIn(wort if wort != "gibt es schon" else "nicht größer", str(e.exception))
        with self.assertRaises(kern.AmwFehler) as e:
            wissen.release_version(self.con, self.pid, "TL", "1.0.0", "x")
        self.assertIn("1.3.0 oder 1.2.4", str(e.exception))
        wissen.release_version(self.con, self.pid, "TL", "1.10.0-beta.1", "weiter")             # 10 > 2 als Zahl, Zusatz erlaubt
        kern.projekt_einstellen(self.con, self.pid, "TL", versionen="aus")
        wissen.release_version(self.con, self.pid, "TL", "Herbst", "frei")                        # aus: keine Prüfung

    def test_unveroeffentlicht_nach_frist(self):
        wissen.release_version(self.con, self.pid, "TL", "0.1.0", "erste")
        self.aufgabe_fertig()
        self.assertNotIn("unveroeffentlicht", self.codes())                                     # frisch: noch nicht
        with db.schreiben(self.con):
            self.con.execute("UPDATE release SET zeit_utc = '2019-12-01T00:00:00Z'")
        self.aufgabe_fertig(tage_alt=1)
        c = self.codes()["unveroeffentlicht"]
        self.assertEqual((c["stufe"], c["werte"]["n"], c["werte"]["letzte"]), ("warnung", 2, "0.1.0"))
        self.assertIn("0.2.0 / 0.1.1", c["werte"]["vorschlag"])
        kern.projekt_einstellen(self.con, self.pid, "TL", version_frist_tage=365)
        self.assertIn("unveroeffentlicht", self.codes())                                         # 2020 ist länger her als 365 Tage
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "TL", version_frist_tage=0)

    def test_meilenstein_schliesst_bei_pflicht_erst_mit_version(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", versionen="pflicht")
        bid = planung.bogen_neu(self.con, self.pid, "TL", "Etappe", ziel="z", abnahme="a")
        wissen.release_version(self.con, self.pid, "TL", "0.1.0", "erste")
        with db.schreiben(self.con):
            self.con.execute("UPDATE release SET zeit_utc = '2019-12-01T00:00:00Z'")
        self.aufgabe_fertig(bogen=bid)
        with self.assertRaises(kern.AmwFehler) as e:
            planung.bogen_status(self.con, self.pid, "TL", bid, "fertig")
        self.assertIn("keine Version", str(e.exception))
        with self.assertRaises(kern.AmwFehler):
            planung.bogen_status(self.con, self.pid, "TL", bid, "fertig", erzwingen=True)          # nur der Mensch erzwingt
        wissen.release_version(self.con, self.pid, "TL", "0.2.0", "mit Etappe")
        planung.bogen_status(self.con, self.pid, "TL", bid, "fertig")

    def test_mensch_kann_erzwingen_und_empfohlen_sperrt_nicht(self):
        bid = planung.bogen_neu(self.con, self.pid, "TL", "Etappe", ziel="z", abnahme="a")
        self.aufgabe_fertig(bogen=bid)
        planung.bogen_status(self.con, self.pid, "TL", bid, "fertig")                              # empfohlen: keine Sperre
        kern.projekt_einstellen(self.con, self.pid, "TL", versionen="pflicht")
        b2 = planung.bogen_neu(self.con, self.pid, "TL", "Zwei", ziel="z", abnahme="a")
        self.aufgabe_fertig(bogen=b2)
        planung.bogen_status(self.con, self.pid, kern.ENTWICKLER, b2, "fertig", erzwingen=True)

    def test_pflicht_kontext_ohne_version(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", versionen="pflicht")
        k = kern.kontext(self.con, self.pid, "CC1")
        text = k if isinstance(k, str) else chr(10).join(k)
        self.assertIn("noch keine eingetragen", text)
        self.assertIn("Pflicht in diesem Projekt", text)
        wissen.release_version(self.con, self.pid, "TL", "0.1.0", "erste")
        k = kern.kontext(self.con, self.pid, "CC1")
        self.assertIn("aktuell 0.1.0", k if isinstance(k, str) else chr(10).join(k))


if __name__ == "__main__":
    unittest.main()
