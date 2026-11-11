"""Eine Warteschlange je Rechner – über alle Projekte. Wer zuerst kommt, ist zuerst dran; ein Lead sortiert nur die Läufe
seines Projekts um, der Mensch über alle; über Läufe eines anderen Projekts erfährt man nur die Belegung, nie den Inhalt."""
import os
import tempfile
import unittest
from unittest import mock

from amw import betrieb, db, kern, workbench


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        self.addCleanup(lambda: self.con.close())
        self.p = {}
        for name in ("Eins", "Zwei"):
            with db.schreiben(self.con):
                self.p[name] = db.einfuegen(self.con, "projekt", name=name, angelegt_utc=db.jetzt())
            kern.agent_neu(self.con, self.p[name], "Chef", rolle="lead")
            for k in ("A", "B", "C"):                       # dieselben Kennungen in beiden Projekten
                kern.agent_neu(self.con, self.p[name], k)
                aid = kern.agent_zeile(self.con, self.p[name], k)["id"]
                with db.schreiben(self.con):
                    db.einfuegen(self.con, "sitzung", agent_id=aid, claude_sitzung=f"{name}-{k}", gestartet_utc=db.jetzt(),
                                 schluessel_datei="x.json", zustand="aktiv")
        for ziel, name, wert in ((betrieb, "cpu_laeufe", 1), (betrieb, "speicher_frei_gb", (32.0, 32.0))):
            p = mock.patch.object(ziel, name, return_value=wert)
            p.start()
            self.addCleanup(p.stop)

    def start(self, projekt, agent, text="geheime Beschreibung", **k):
        return betrieb.lauf_start(self.con, self.p[projekt], agent, text, warten=True, speicher_frei=32.0, **k)

    def status(self, lid):
        return self.con.execute("SELECT status FROM lauf WHERE id = ?", (lid,)).fetchone()[0]

    def reihenfolge(self):
        return [l["id"] for l in betrieb.wartende(self.con)]


class Reihenfolge(Grund):
    def test_wer_zuerst_kommt_ist_zuerst_dran_auch_ueber_projekte(self):
        laeuft = self.start("Eins", "A")                     # belegt die einzige Spur für schwere Läufe
        w1 = self.start("Eins", "B")
        w2 = self.start("Zwei", "A")
        w3 = self.start("Eins", "C")
        self.assertEqual((self.status(laeuft), self.reihenfolge()), ("laeuft", [w1, w2, w3]))
        betrieb.lauf_ende(self.con, self.p["Eins"], "A", laeuft, 0, speicher_frei=32.0)
        self.assertEqual((self.status(w1), self.status(w2)), ("laeuft", "angemeldet"))
        betrieb.lauf_ende(self.con, self.p["Eins"], "B", w1, 0, speicher_frei=32.0)
        self.assertEqual((self.status(w2), self.status(w3)), ("laeuft", "angemeldet"))       # Projekt Zwei war vor C angemeldet
        post = self.con.execute("SELECT n.projekt_id, n.art FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = 'A'"
                                " AND n.kurz LIKE ? ", (f"L{w2} ist dran%",)).fetchone()
        self.assertEqual(tuple(post), (self.p["Zwei"], "freigabe"))                          # die Freigabe geht ins richtige Projekt

    def test_ein_neuer_lauf_ueberholt_keinen_wartenden_eines_anderen_projekts(self):
        with mock.patch.object(betrieb, "cpu_laeufe", return_value=2):
            eins = self.start("Eins", "A")
            zwei = self.start("Eins", "B")                   # beide Spuren belegt
            wartet = self.start("Zwei", "A")
            betrieb.lauf_ende(self.con, self.p["Eins"], "A", eins, 0, speicher_frei=0.0)      # Spur frei, aber kein Speicher: wartet weiter
            self.assertEqual(self.status(wartet), "angemeldet")
            with self.assertRaises(kern.AmwFehler) as e:                                       # Projekt Eins will sofort starten
                betrieb.lauf_start(self.con, self.p["Eins"], "C", "neu", speicher_frei=32.0)
            self.assertIn("Warteschlange", str(e.exception))
            self.assertIn("anderes Projekt", str(e.exception))
            self.assertEqual(self.status(zwei), "laeuft")

    def test_gleiche_kennung_in_zwei_projekten_sind_zwei_agenten(self):
        with mock.patch.object(betrieb, "cpu_laeufe", return_value=2):
            a1 = self.start("Eins", "A")
            a2 = self.start("Zwei", "A")                     # derselbe Name, anderes Projekt: eigener Klon, darf laufen
            a3 = self.start("Eins", "A")                     # derselbe Agent im selben Projekt: wartet auf seinen Klon
        self.assertEqual([self.status(x) for x in (a1, a2, a3)], ["laeuft", "laeuft", "angemeldet"])


class Vorziehen(Grund):
    def test_lead_sortiert_nur_die_laeufe_seines_projekts(self):
        self.start("Eins", "A")
        e1, z1, e2, z2 = self.start("Eins", "B"), self.start("Zwei", "A"), self.start("Eins", "C"), self.start("Zwei", "B")
        betrieb.lauf_vorziehen(self.con, self.p["Eins"], "Chef", e2)
        self.assertEqual(self.reihenfolge(), [e2, z1, e1, z2])                  # Eins tauscht seine Plätze, Zwei bleibt, wo es war
        betrieb.lauf_vorziehen(self.con, self.p["Zwei"], "Chef", z2)
        self.assertEqual(self.reihenfolge(), [e2, z2, e1, z1])
        with self.assertRaises(kern.AmwFehler):
            betrieb.lauf_vorziehen(self.con, self.p["Eins"], "Chef", z1)        # fremder Lauf: gibt es für diesen Lead nicht
        with self.assertRaises(kern.AmwFehler):
            betrieb.lauf_vorziehen(self.con, self.p["Eins"], "B", e1)           # nur Lead und Mensch

    def test_der_mensch_zieht_ueber_alle_projekte_vor(self):
        self.start("Eins", "A")
        e1, z1, z2 = self.start("Eins", "B"), self.start("Zwei", "A"), self.start("Zwei", "B")
        betrieb.lauf_vorziehen(self.con, self.p["Zwei"], kern.ENTWICKLER, z2)
        self.assertEqual(self.reihenfolge(), [z2, e1, z1])
        betrieb.lauf_vorziehen(self.con, self.p["Eins"], "Chef", e1)            # ein Lead kommt an ihm nicht vorbei
        self.assertEqual(self.reihenfolge()[0], z2)
        betrieb.lauf_vorziehen(self.con, self.p["Zwei"], kern.ENTWICKLER, z1)   # der zuletzt Vorgezogene steht vorn
        self.assertEqual(self.reihenfolge(), [z1, z2, e1])


class Verschwiegenheit(Grund):
    def test_fremde_laeufe_nur_als_belegung(self):
        fremd = self.start("Zwei", "A", "Bild fuer den Kunden X", gpu=True, erwartet_min=30)
        with self.assertRaises(kern.AmwFehler) as e:
            betrieb.lauf_start(self.con, self.p["Eins"], "B", "eigenes Bild", gpu=True, speicher_frei=32.0)
        text = str(e.exception)
        self.assertIn(f"L{fremd} (anderes Projekt, läuft seit", text)
        self.assertIn("voraussichtlich bis", text)
        for geheim in ("Kunden X", "von A", "Zwei"):
            self.assertNotIn(geheim, text)
        eigen = self.start("Eins", "B", "eigenes Bild", gpu=True)
        self.assertEqual(self.status(eigen), "angemeldet")
        nachbar = self.start("Zwei", "B", "noch ein Geheimnis", gpu=True)
        grund = betrieb.wartegrund(self.con, self.p["Zwei"], betrieb.lauf_zeile(self.con, self.p["Zwei"], nachbar), speicher_frei=32.0)
        self.assertIn(f"vor dir: L{eigen} (anderes Projekt)", grund)             # auch umgekehrt: Zwei sieht von Eins nur die Nummer
        self.assertNotIn("eigenes Bild", grund)
        grund = betrieb.wartegrund(self.con, self.p["Eins"], betrieb.lauf_zeile(self.con, self.p["Eins"], eigen), speicher_frei=32.0)
        self.assertIn("anderes Projekt", grund)
        self.assertNotIn("Kunden X", grund)
        self.assertIn("Platz 1 von 2", grund)                                    # die Schlange des Rechners, nicht die des Projekts

    def test_eigene_laeufe_weiter_mit_agent_und_beschreibung(self):
        self.start("Eins", "A", "Karten rechnen", gpu=True)
        with self.assertRaises(kern.AmwFehler) as e:
            betrieb.lauf_start(self.con, self.p["Eins"], "B", "zweites Bild", gpu=True, speicher_frei=32.0)
        self.assertIn("von A: Karten rechnen", str(e.exception))


class Anzeige(Grund):
    def test_auslastung_des_rechners_im_leitstand(self):
        self.start("Eins", "A", erwartet_min=20)
        self.start("Zwei", "A")
        self.start("Eins", "B")
        a = betrieb.auslastung(self.con, self.p["Eins"])
        self.assertEqual((a["laufen"], a["warten"], a["eigene_laufen"], a["eigene_warten"]), (1, 2, 1, 1))
        self.assertRegex(a["frei_ab_utc"], r"^20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(a["frei_gb"], 32.0)
        z = betrieb.auslastung(self.con, self.p["Zwei"])
        self.assertEqual((z["laufen"], z["warten"], z["eigene_laufen"], z["eigene_warten"]), (1, 2, 0, 1))
        start = workbench.daten_start(self.con, self.p["Zwei"])["rechner"]
        self.assertEqual((start["laufen"], start["warten"]), (1, 2))
        self.assertNotIn("geheime Beschreibung", str(start))                     # nur Zahlen


if __name__ == "__main__":
    unittest.main()
