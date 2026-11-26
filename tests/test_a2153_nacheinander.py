"""A2153 (M14 D1974; TH164 Schritt 3, TH165): „nie gleichzeitig“ und „gleiche Ressource“ wirken – der Feinplan kennt beide Felder,
legt sie an, und weder der Wächter (p-Pakete, auch für den Disponenten) noch die Verteilung an Fenster-Agenten startet ein Paket,
solange eines mit Bezug darauf arbeitet; es wartet mit einem lesbaren Grund (Regel 16)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import tempfile
import time
import unittest
from unittest import mock

from amw import arbeitspaket, db, feinplanung, kern, planer, planung, themen, verteilen, waechter


def utc(sek):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(sek))


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db"),
                                         "LOCALAPPDATA": os.path.join(self.ordner.name, "lad")})
        u.start()
        self.addCleanup(u.stop)
        os.environ.pop("AMW_AGENT", None)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")

    def zustand(self, aid, *folge):
        for z in folge:
            arbeitspaket.zustand_setzen(self.con, self.pid, "TL", aid, z, annahme=z == "merge_reihe")


class Feinplan(Grund):
    """Der echte Weg: Antwort des Feinplaners als Text → geprüft → angelegt → der Wächter hält das zweite an."""
    def setUp(self):
        super().setUp()
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, platz_wurzel=os.path.join(self.ordner.name, "plaetze"), plaetze=2)
        self.th = themen.neu(self.con, self.pid, "TL", "Spielstände", pfleger="CC1")
        self.m1 = planung.bogen_neu(self.con, self.pid, "TL", "Speichern", ziel=f"TH{self.th} Speichern", abnahme="Bericht")
        p = mock.patch.object(feinplanung, "STARTER", lambda _pid, boegen, fassung: 4711)
        p.start()
        self.addCleanup(p.stop)

    def paket(self, s, datei, **mehr):
        return {"schluessel": s, "meilenstein": "M1", "thema": f"TH{self.th}", "titel": f"Speicher {s}", "auftrag": f"Teil {s}.",
                "groesse": "S", "art": "mechanisch", "ausfuehrung": "p", "fertig_quelle": "commit",
                "abnahme_befehl": "python -m unittest tests.test_x", "bereiche": datei, **mehr}

    def antwort(self):
        """Wie der Feinplaner antwortet: JSON als Text, getrennte Dateien – nur die beiden Felder verbinden die Pakete."""
        return json.dumps({"pakete": [self.paket("P1", "web/hilfe/a.de.json", gleiche_ressource="Testdatenbank"),
                                      self.paket("P2", "web/hilfe/b.de.json", nie_gleichzeitig=["P1"], gleiche_ressource="Testdatenbank"),
                                      self.paket("P3", "web/hilfe/c.de.json")],
                           "grund": "P1 und P2 teilen die Testdatenbank"}, ensure_ascii=False)

    def anlegen(self):
        feinplanung.anstossen(self.con, self.pid, [self.m1])
        e = feinplanung.entwurf_eintragen(self.con, self.pid, [self.m1], 1, self.antwort(), modell="opus", usd=0.1)
        self.assertNotIn("fehler", e, e)
        return [int(e["angelegt"][k][1:]) for k in ("P1", "P2", "P3")]

    def test_feinplan_legt_beide_felder_an(self):
        p1, p2, p3 = self.anlegen()
        f1, f2, f3 = (arbeitspaket.lesen(self.con, a) for a in (p1, p2, p3))
        self.assertEqual((f1["nie_gleichzeitig"], f2["nie_gleichzeitig"], f3["nie_gleichzeitig"]), ([], [p1], []))
        self.assertEqual((f1["gleiche_ressource"], f2["gleiche_ressource"], f3["gleiche_ressource"]), ("Testdatenbank", "Testdatenbank", None))

    def test_das_zweite_startet_erst_nach_dem_ersten(self):
        p1, p2, p3 = self.anlegen()
        for a in (p1, p2, p3):
            self.zustand(a, "startklar")
        self.assertTrue(waechter.pruefen(self.con, self.pid, p2, limit=10)["ok"])          # noch läuft keins
        self.zustand(p1, "laeuft")
        r = waechter.pruefen(self.con, self.pid, p2, limit=10)
        self.assertEqual((r["ok"], r["regel"], r["warten"]), (False, 16, True))
        self.assertIn(f"A{p1}", r["grund"])
        self.assertIn("nie gleichzeitig", r["grund"])
        self.assertTrue(waechter.pruefen(self.con, self.pid, p3, limit=10)["ok"])          # ohne Bezug: daneben erlaubt
        self.zustand(p1, "abgegeben", "abnahme")
        self.assertEqual(waechter.pruefen(self.con, self.pid, p2, limit=10)["regel"], 16)   # in der Abnahme arbeitet es noch
        self.zustand(p1, "merge_reihe")
        self.assertTrue(waechter.pruefen(self.con, self.pid, p2, limit=10)["ok"])

    def test_auch_andersherum_und_nur_ueber_die_ressource(self):
        p1, p2, _ = self.anlegen()
        for a in (p1, p2):
            self.zustand(a, "startklar")
        self.zustand(p2, "laeuft")                                                        # P1 nennt P2 nicht, P2 nennt P1
        r = waechter.pruefen(self.con, self.pid, p1, limit=10)
        self.assertEqual(r["regel"], 16)
        self.assertIn(f"A{p2}", r["grund"])
        arbeitspaket.setzen(self.con, self.pid, "TL", p2, nie_gleichzeitig=[])
        r = waechter.pruefen(self.con, self.pid, p1, limit=10)
        self.assertEqual(r["regel"], 16)                                                  # die gleiche Ressource reicht
        self.assertIn("Testdatenbank", r["grund"])

    def test_planer_prueft_die_felder(self):
        roh = json.loads(self.antwort())
        roh["pakete"][1]["nie_gleichzeitig"] = ["P9"]
        with self.assertRaises(planer.PlanFehler) as f:
            feinplanung.pruefen(roh, self.con, self.pid, [self.m1])
        self.assertIn("nie_gleichzeitig", str(f.exception))
        roh["pakete"][1]["nie_gleichzeitig"] = ["P2"]
        with self.assertRaises(planer.PlanFehler) as f:
            feinplanung.pruefen(roh, self.con, self.pid, [self.m1])
        self.assertIn("sich selbst", str(f.exception))

    def test_schema_nennt_beide_felder(self):
        for text in (feinplanung.SCHEMA_TEXT, planer.SCHEMA_TEXT):
            self.assertIn('"nie_gleichzeitig"', text)
            self.assertIn('"gleiche_ressource"', text)


class Verteilen(Grund):
    """Fenster-Agenten: ein freier Agent bekommt kein Paket, solange eines mit Bezug darauf läuft – der Grund steht im Protokoll."""
    def setUp(self):
        super().setUp()
        kern.agent_neu(self.con, self.pid, "CC2")
        kern.projekt_einstellen(self.con, self.pid, "TL", verteilen="an")
        jetzt = time.time()
        with db.schreiben(self.con):
            aid = self.con.execute("SELECT id FROM agent WHERE kennung = 'CC2'").fetchone()[0]
            db.einfuegen(self.con, "sitzung", agent_id=aid, gestartet_utc=utc(jetzt - 7200), schluessel_datei="x.key",
                         ereignis="frei", ereignis_utc=utc(jetzt - 600))
            self.bogen = db.einfuegen(self.con, "bogen", projekt_id=self.pid, nr=1, titel="Stufe 1", status="aktiv", angelegt_von="TL",
                                      angelegt_utc=db.jetzt())

    def aufgabe(self, titel, rang):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel)
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET bogen_id = ?, rang = ? WHERE id = ?", (self.bogen, rang, aid))
        return aid

    def test_wartet_bis_das_andere_fertig_ist(self):
        erst = self.aufgabe("Grafikkarte A", 1)
        dann = self.aufgabe("Grafikkarte B", 2)
        for a in (erst, dann):
            arbeitspaket.setzen(self.con, self.pid, "TL", a, gleiche_ressource="Grafikkarte")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET agent = 'CC1', status = 'laeuft' WHERE id = ?", (erst,))
        self.assertEqual(verteilen.verteilen(self.con, self.pid), [])
        self.assertIsNone(self.con.execute("SELECT agent FROM aufgabe WHERE id = ?", (dann,)).fetchone()[0])
        p = waechter.protokoll(self.con, self.pid, dann)
        self.assertTrue(p and f"A{dann} nicht gestartet, Regel 16" in p[0]["text"] and f"A{erst}" in p[0]["text"], p)
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc1234' WHERE id = ?", (erst,))
        aus = verteilen.verteilen(self.con, self.pid)
        self.assertTrue(aus and aus[0].startswith(f"A{dann} an CC2"), aus)


if __name__ == "__main__":
    unittest.main()
