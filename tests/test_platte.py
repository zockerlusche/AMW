"""Festplatte: freier Platz je Laufwerk mit Warnstufen, Meldung an Lead und Mensch (einmal je Stufe), Aufräumvorschläge
für alte Sicherungen nach der Aufbewahrungsregel. Gelöscht wird nie etwas."""
import collections
import datetime
import os
import tempfile
import unittest
from unittest import mock

from amw import betrieb, db, einstellungen, kern, platte, workbench

Platz = collections.namedtuple("Platz", "total used free")
GB = 2 ** 30


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.daten = os.path.join(self.ordner.name, "daten")
        os.makedirs(self.daten)
        umgebung = mock.patch.dict(os.environ, {"LOCALAPPDATA": os.path.join(self.ordner.name, "lokal")})
        umgebung.start()
        self.addCleanup(umgebung.stop)
        pfad = os.path.join(self.daten, "amw.db")
        self.con = db.anlegen(pfad)
        self.addCleanup(self.con.close)
        ort = mock.patch.object(db, "db_pfad", lambda: pfad)
        ort.start()
        self.addCleanup(ort.stop)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")

    def sicherung(self, name, mb=1, dokumente_mb=0):
        with open(os.path.join(self.daten, name), "wb") as f:
            f.write(b"x" * (mb * 2 ** 20))
        if dokumente_mb:
            ablage = os.path.join(self.daten, os.path.splitext(name)[0] + "-dokumente", "a")
            os.makedirs(ablage)
            with open(os.path.join(ablage, "d.bin"), "wb") as f:
                f.write(b"x" * (dokumente_mb * 2 ** 20))


class Laufwerke(Grund):
    def test_stufen_und_leitstand(self):
        frei = [50]
        messen = lambda pfad: Platz(100 * GB, (100 - frei[0]) * GB, frei[0] * GB)
        l = platte.laufwerke(self.con, messen)
        self.assertEqual(len(l), 1)
        self.assertEqual((l[0]["frei_gb"], l[0]["gesamt_gb"], l[0]["frei_prozent"], l[0]["stufe"], l[0]["daten"]), (50.0, 100.0, 50.0, None, True))
        frei[0] = 12
        self.assertEqual(platte.laufwerke(self.con, messen)[0]["stufe"], "gelb")
        frei[0] = 4
        self.assertEqual(platte.laufwerke(self.con, messen)[0]["stufe"], "rot")
        einstellungen.speichern({"platte_gelb_prozent": 3, "platte_rot_prozent": 1})             # einstellbar
        self.assertIsNone(platte.laufwerke(self.con, messen)[0]["stufe"])
        einstellungen.speichern({"platte_gelb_prozent": 15, "platte_rot_prozent": 5})
        with mock.patch.object(platte.shutil, "disk_usage", messen):
            r = betrieb.auslastung(self.con, self.pid)
            self.assertEqual([(x["laufwerk"], x["stufe"], x["frei_gb"]) for x in r["platte"]], [(platte.laufwerk(self.daten), "rot", 4.0)])
            self.assertNotIn("projekte", r["platte"][0])                                         # im Leitstand nur Zahlen
            frei[0] = 60
            self.assertEqual(betrieb.auslastung(self.con, self.pid)["platte"], [])               # genug frei: kein Eintrag
        self.assertEqual(platte.laufwerke(self.con, mock.Mock(side_effect=OSError("weg"))), [])  # nicht messbar: fehlt, kein Fehler

    def test_meldung_einmal_je_stufe_an_lead_und_mensch(self):
        frei = [50]
        wache = platte.Wache(self.con, lambda pfad: Platz(100 * GB, (100 - frei[0]) * GB, frei[0] * GB))
        nachrichten = lambda: [(r["kurz"], sorted(e[0] for e in self.con.execute("SELECT agent FROM empfang WHERE nachricht_id = ?", (r["id"],))))
                               for r in self.con.execute("SELECT id, kurz FROM nachricht ORDER BY id")]
        self.assertEqual(wache.runde(jetzt=1000), [])                                            # genug frei
        frei[0] = 12
        self.assertEqual(wache.runde(jetzt=1100), [])                                            # zu früh: noch keine neue Messung
        texte = wache.runde(jetzt=1000 + platte.PRUEFEN_S)
        self.assertEqual(len(texte), 1)
        self.assertRegex(texte[0], r"^Laufwerk \S+ wird knapp: noch 12,0 GB frei \(12,0 % von 100,0 GB\)\. Die AMW löscht nichts; aufräumen kann nur der Mensch\.$")
        self.assertEqual([wer for _, wer in nachrichten()], [["TL"], [kern.ENTWICKLER]])         # Lead und Mensch, je einmal
        self.assertEqual(wache.runde(jetzt=1000 + 2 * platte.PRUEFEN_S), [])                     # gleiche Stufe: nicht noch einmal
        self.assertEqual(platte.Wache(self.con, wache.messen).runde(jetzt=5000), [])             # auch nicht nach einem Neustart
        frei[0] = 4
        texte = wache.runde(jetzt=1000 + 3 * platte.PRUEFEN_S)
        self.assertIn("Schwere Läufe und Sicherungen können daran scheitern.", texte[0])         # schlechter: neue Meldung
        frei[0] = 40
        self.assertEqual(wache.runde(jetzt=1000 + 4 * platte.PRUEFEN_S), [])                     # erholt: vermerkt, keine Meldung
        frei[0] = 12
        self.assertEqual(len(wache.runde(jetzt=1000 + 5 * platte.PRUEFEN_S)), 1)                 # wieder knapp: meldet wieder
        self.assertEqual(len(nachrichten()), 6)


class Sicherungen(Grund):
    def test_aufbewahrungsregel(self):
        jetzt = datetime.datetime(2026, 11, 11, 12, 0)
        liste = [{"name": f"s{tag:02d}", "zeit": datetime.datetime(2026, 11, tag, 8, 0), "bytes": 100} for tag in range(10, 0, -1)]   # neueste zuerst
        v = platte.aufraeumen(liste, 3, jetzt=jetzt)
        self.assertEqual([x["name"] for x in v], ["s01", "s02", "s03", "s04", "s05", "s06", "s07"])   # die 3 neuesten bleiben; älteste zuerst
        self.assertEqual((v[0]["tage"], v[0]["bytes"]), (10, 100))
        v = platte.aufraeumen(liste, 3, versionen=[datetime.datetime(2026, 11, 5, 9, 0), datetime.datetime(2026, 11, 2, 7, 0)], jetzt=jetzt)
        self.assertEqual([x["name"] for x in v], ["s02", "s03", "s04", "s06", "s07"])                 # je Version bleibt die letzte davor (s05, s01)
        self.assertEqual(platte.aufraeumen(liste, 50, jetzt=jetzt), [])
        self.assertEqual(platte.aufraeumen([], 3), [])

    def test_sicherungen_im_ordner_und_anzeige(self):
        self.sicherung("sicherung-2026-11-01-0800.db", 2, dokumente_mb=1)
        self.sicherung("sicherung-2026-11-03-0900.db", 1)
        self.sicherung("sicherung-P-2026-11-05-1000.db", 1)
        self.sicherung("amw-sicherung-2026-11-07-1100.db", 1)
        self.sicherung("notizen.db", 1)                                                           # keine Sicherung
        liste = platte.sicherungen()
        self.assertEqual([x["name"] for x in liste], ["amw-sicherung-2026-11-07-1100.db", "sicherung-P-2026-11-05-1000.db",
                                                      "sicherung-2026-11-03-0900.db", "sicherung-2026-11-01-0800.db"])
        self.assertEqual(liste[-1]["bytes"], 3 * 2 ** 20)                                         # mit der Dokumente-Ablage daneben
        einstellungen.speichern({"sicherungen_behalten": 2})
        with db.schreiben(self.con):
            db.einfuegen(self.con, "release", projekt_id=self.pid, art="version", version="0.1.0", zeit_utc="2026-11-02T12:00:00Z", titel="Erste",
                         eingetragen_von="TL")
        v = platte.vorschlaege(self.con)
        self.assertEqual([x["name"] for x in v["sicherungen"]], ["sicherung-2026-11-03-0900.db"])   # 2 neueste bleiben, dazu die vor der Version
        self.assertEqual((v["bytes"], v["ordner"]), (2 ** 20, self.daten))
        d = workbench.daten_einstellungen(self.con, self.pid)["rechner"]
        self.assertEqual([x["name"] for x in d["aufraeumen"]["sicherungen"]], ["sicherung-2026-11-03-0900.db"])
        self.assertEqual(len(d["laufwerke"]), 1)
        self.assertTrue(all(os.path.exists(os.path.join(self.daten, x["name"])) for x in liste))  # nichts gelöscht, nichts verschoben


if __name__ == "__main__":
    unittest.main()
