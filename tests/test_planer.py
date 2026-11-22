"""K4 / A1940 (Vorbereitung, #30112): Grobplanung aus Themen – Schema des Planer-Ergebnisses, Prüfung mit allen Funden,
Entwurf eintragen (Auftrag an den Lead), Übernehmen erst mit Ja: Meilensteine, Pakete mit Größe/Art/Ausführung/Modell,
Abnahme-Befehl, Abhängigkeiten, Verweis aufs Thema; „nichts zu bauen“ mit Grund. Feste Planer-Ergebnisse, kein echter Lauf."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import copy
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import arbeitspaket, db, kern, planer, planung, themen

ERGEBNIS = {
    "meilensteine": [{"schluessel": "M1", "titel": "Anmelden online", "ziel": "Marcel meldet sich online an.",
                      "abnahme": "Vorführung: Anmeldung mit Firmen-Konto am Handy"}],
    "pakete": [
        {"schluessel": "P1", "meilenstein": "M1", "titel": "Anmeldung mit Firmen-Konto", "auftrag": "SSO-Anmeldung bauen.",
         "groesse": "m", "art": "sicherheit", "ausfuehrung": "agent", "fertig_quelle": "release"},
        {"schluessel": "P2", "meilenstein": "M1", "titel": "Tests für die Anmeldung", "auftrag": "Tests ergänzen.",
         "groesse": "S", "art": "mechanisch", "ausfuehrung": "p", "modell": "sonnet", "effort": "medium", "fertig_quelle": "commit",
         "nach": ["P1"], "abnahme_befehl": "python -m unittest tests.test_anmeldung"},
    ]}


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
            self.pid = db.einfuegen(self.con, "projekt", name="Produkt", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.tid = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", self.tid, "Wer die Online-Seite öffnet, meldet sich mit dem Firmen-Konto an.")

    def post(self, an):
        return [(r["art"], r["kurz"]) for r in self.con.execute(
            "SELECT n.art, n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? AND n.von = 'AMW'"
            " ORDER BY n.id", (an,))]

    def funde(self, daten):
        with self.assertRaises(planer.PlanFehler) as f:
            planer.pruefen(daten, self.con, self.pid)
        return f.exception.fehler


class Schema(Grund):
    def test_gueltig_und_vereinheitlicht(self):
        e = planer.pruefen(json.dumps(ERGEBNIS), self.con, self.pid)                     # auch als JSON-Text
        self.assertFalse(e["nichts_zu_bauen"])
        self.assertEqual([p["groesse"] for p in e["pakete"]], ["M", "S"])                 # Größe groß geschrieben
        self.assertEqual(e["pakete"][0]["modell"], None)
        self.assertEqual(e["pakete"][1]["nach"], ["P1"])

    def test_alle_funde_auf_einmal(self):
        d = copy.deepcopy(ERGEBNIS)
        d["pakete"][0].update(groesse="riesig", art="malen", fertig_quelle="irgendwann", meilenstein="M9")
        d["pakete"][1].update(ausfuehrung="p", abnahme_befehl=None, nach=["P1", "P7"])
        d["extra"] = 1
        f = self.funde(d)
        for teil in ("unbekannte Felder: extra", "groesse „riesig“", "art „malen“", "fertig_quelle „irgendwann“",
                     "Meilenstein „M9“", "p-Paket braucht einen Abnahme-Befehl", "nach „P7“"):
            self.assertTrue(any(teil in x for x in f), (teil, f))

    def test_meilenstein_ohne_pakete(self):
        d = copy.deepcopy(ERGEBNIS)
        d["meilensteine"].append({"schluessel": "M2", "titel": "Leer", "ziel": "x", "abnahme": "y"})
        self.assertIn("neue Meilensteine ohne Pakete: M2", self.funde(d))

    def test_kreis_und_selbst(self):
        d = copy.deepcopy(ERGEBNIS)
        d["pakete"][0]["nach"] = ["P2"]
        self.assertTrue(any("im Kreis: P1 → P2 → P1" in x or "im Kreis: P2 → P1 → P2" in x for x in self.funde(d)))
        d["pakete"][0]["nach"] = ["P1"]
        self.assertTrue(any("hängt von sich selbst ab" in x for x in self.funde(d)))

    def test_verweise_ins_projekt(self):
        d = copy.deepcopy(ERGEBNIS)
        d["pakete"][0]["nach"] = ["A999"]
        d["meilensteine"].append({"schluessel": "M2", "bestehend": 7})
        f = self.funde(d)
        self.assertTrue(any("nach A999 – die Aufgabe gibt es im Projekt nicht" in x for x in f))
        self.assertTrue(any("Meilenstein 7 gibt es im Projekt nicht" in x for x in f))

    def test_nichts_zu_bauen(self):
        self.assertEqual(planer.pruefen({"nichts_zu_bauen": True, "grund": "Nur ein Begriff, schon erfüllt."}),
                         {"nichts_zu_bauen": True, "grund": "Nur ein Begriff, schon erfüllt."})
        self.assertTrue(any("grund fehlt" in x for x in self.funde({"nichts_zu_bauen": True})))
        self.assertTrue(any("aber Meilensteine oder Pakete" in x for x in self.funde({"nichts_zu_bauen": True, "grund": "x",
                                                                                      "pakete": ERGEBNIS["pakete"]})))

    def test_kein_json(self):
        self.assertTrue(self.funde("{kaputt")[0].startswith("kein JSON"))


class Ablauf(Grund):
    def test_entwurf_an_den_lead_und_erst_mit_ja_angelegt(self):
        vorher = self.con.execute("SELECT count(*) FROM aufgabe").fetchone()[0]
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, ERGEBNIS, modell="sonnet", usd=0.42, lauf=7)
        self.assertEqual(self.post("TL")[-1], ("auftrag", "Planentwurf TH%d „Anmeldung“: 1 Meilenstein(e), 2 Pakete – Ja oder ändern" % self.tid))
        self.assertEqual(self.con.execute("SELECT count(*) FROM aufgabe").fetchone()[0], vorher)   # kein Anlegen ohne Ja
        with self.assertRaisesRegex(kern.AmwFehler, "nimmt der Lead an"):
            planer.uebernehmen(self.con, self.pid, "CC1", self.tid)
        a = planer.uebernehmen(self.con, self.pid, "TL", self.tid)
        self.assertEqual(sorted(a), ["M1", "P1", "P2"])
        b = planung.bogen_zeile(self.con, self.pid, self.con.execute("SELECT id FROM bogen WHERE nr = ?", (int(a["M1"][1:]),)).fetchone()[0])
        self.assertEqual((b["titel"], b["ziel"]), ("Anmelden online", "Marcel meldet sich online an."))
        p1, p2 = (self.con.execute("SELECT * FROM aufgabe WHERE id = ?", (int(a[k][1:]),)).fetchone() for k in ("P1", "P2"))
        self.assertEqual((p1["groesse"], p1["art"], p1["bogen_id"]), ("M", "sicherheit", b["id"]))
        self.assertEqual((p2["pruefbefehl"], arbeitspaket.lesen(self.con, p2["id"])["art"], arbeitspaket.lesen(self.con, p2["id"])["modell"]),
                         ("python -m unittest tests.test_anmeldung", "p", "sonnet"))
        self.assertEqual(planung.vorgaenger(self.con, p2["id"]), [p1["id"]])
        self.assertEqual(themen.verweise(self.con, self.pid, p1["id"]), [self.tid])            # mit dem Thema verknüpft (A1915)
        with self.assertRaisesRegex(kern.AmwFehler, "schon angenommen"):
            planer.uebernehmen(self.con, self.pid, "TL", self.tid)

    def test_lead_aendert_vor_dem_ja(self):
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, ERGEBNIS)
        d = copy.deepcopy(ERGEBNIS)
        d["pakete"] = d["pakete"][:1]
        a = planer.uebernehmen(self.con, self.pid, "TL", self.tid, geaendert=d)
        self.assertEqual(sorted(a), ["M1", "P1"])
        d["pakete"][0]["art"] = "malen"
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, ERGEBNIS)
        with self.assertRaises(planer.PlanFehler):                                        # Änderung wird neu geprüft
            planer.uebernehmen(self.con, self.pid, "TL", self.tid, geaendert=d)

    def test_fehlerhafter_entwurf_meldet_funde_und_legt_nichts_an(self):
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, {"pakete": []})
        self.assertEqual(self.post("TL")[-1][0], "meldung")
        self.assertIn("passt nicht zum Schema", self.post("TL")[-1][1])
        with self.assertRaisesRegex(kern.AmwFehler, "passte nicht zum Schema"):
            planer.uebernehmen(self.con, self.pid, "TL", self.tid)

    def test_nichts_zu_bauen_mit_grund_vermerkt(self):
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, {"nichts_zu_bauen": True, "grund": "Ist schon gebaut (A1896)."})
        self.assertIn("nichts zu bauen – stimmt das?", self.post("TL")[-1][1])
        self.assertEqual(planer.uebernehmen(self.con, self.pid, "TL", self.tid), {})
        e = planer._ereignisse(self.con, self.pid, self.tid, planer.NICHTS)
        self.assertEqual(e[-1]["grund"], "Ist schon gebaut (A1896).")

    def test_bestehender_meilenstein_und_vorgaenger_im_projekt(self):
        bid = planung.bogen_neu(self.con, self.pid, "TL", "Schon da")
        nr = planung.bogen_zeile(self.con, self.pid, bid)["nr"]
        alt = kern.aufgabe_neu(self.con, self.pid, "TL", "Vorarbeit")
        d = {"meilensteine": [{"schluessel": "M1", "bestehend": nr}],
             "pakete": [{**ERGEBNIS["pakete"][0], "nach": [f"A{alt}"]}]}
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, d)
        a = planer.uebernehmen(self.con, self.pid, "TL", self.tid)
        self.assertEqual(a["M1"], f"M{nr}")
        aid = int(a["P1"][1:])
        self.assertEqual(self.con.execute("SELECT bogen_id FROM aufgabe WHERE id = ?", (aid,)).fetchone()[0], bid)
        self.assertEqual(planung.vorgaenger(self.con, aid), [alt])


if __name__ == "__main__":
    unittest.main()
