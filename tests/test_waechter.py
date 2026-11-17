"""Wächter für p-Pakete (A1847, M50 S4): jede Regel 1–10 erlaubt/abgelehnt, Protokoll mit Regelnummer (nur bei Änderung),
Startfolge aus Rang + Abhängigkeiten, Auslieferung setzt Wartungsmodus und wartet auf Laufendes, Plätze = 0 → wie heute."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import arbeitspaket, cli, db, kern, waechter


class Waechter(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad, "LOCALAPPDATA": os.path.join(self.ordner.name, "lad")})
        u.start()
        self.addCleanup(u.stop)
        os.environ.pop("AMW_AGENT", None)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, platz_wurzel=os.path.join(self.ordner.name, "plaetze"), plaetze=1)

    def paket(self, titel="Paket", bereiche="web/hilfe/", befehl="python -m unittest tests.test_x", rang=None, **felder):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel, "TL")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET pruefbefehl = ?, dateibereich = ?, rang = coalesce(?, rang) WHERE id = ?",
                             (befehl, bereiche, rang, aid))
        arbeitspaket.setzen(self.con, self.pid, "TL", aid, art="p", **felder)
        arbeitspaket.zustand_setzen(self.con, self.pid, "TL", aid, "startklar")
        return aid

    def regel(self, aid, limit=10):
        return waechter.pruefen(self.con, self.pid, aid, limit=limit)["regel"]

    def test_darf_starten(self):
        r = waechter.pruefen(self.con, self.pid, self.paket(), limit=10)
        self.assertTrue(r["ok"], r)

    def test_regel_1_ohne_befehl_oder_bereiche(self):
        self.assertEqual(self.regel(self.paket(befehl="")), 1)
        self.assertEqual(self.regel(self.paket(bereiche="")), 1)

    def test_regel_2_bereiche_ueberschneiden_sich(self):
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, plaetze=2)
        a = self.paket(bereiche="web/hilfe/")
        arbeitspaket.zustand_setzen(self.con, self.pid, "TL", a, "laeuft")
        self.assertEqual(self.regel(self.paket(bereiche="web/hilfe/agenten.de.json")), 2)
        self.assertIsNone(self.regel(self.paket(bereiche="doc/hilfe/")))                     # andere Bereiche: erlaubt

    def test_regel_3_schwer_oder_ressourcen(self):
        self.assertEqual(self.regel(self.paket(gewicht="schwer")), 3)
        self.assertEqual(self.regel(self.paket(ressourcen=["gpu"])), 3)

    def test_regel_4_plaetze_voll(self):
        a = self.paket(bereiche="web/a/")
        arbeitspaket.zustand_setzen(self.con, self.pid, "TL", a, "laeuft")
        r = waechter.pruefen(self.con, self.pid, self.paket(bereiche="doc/"), limit=10)
        self.assertEqual((r["regel"], r["warten"]), (4, True))

    def test_regel_5_gesperrte_bereiche(self):
        self.assertEqual(self.regel(self.paket(bereiche="amw/auslieferung.py")), 5)
        self.assertEqual(self.regel(self.paket(bereiche="tests/test_neu.py")), 5)
        self.assertIsNone(self.regel(self.paket(bereiche="tests/test_neu.py", pakettyp="test-schreiben")))

    def test_regel_6_ergebnis_des_starters(self):
        self.assertEqual(waechter.regel6({"ok": False, "grund": "prüft nichts"})["regel"], 6)
        self.assertTrue(waechter.regel6({"ok": True})["ok"])

    def test_regel_7_wartungsmodus(self):
        a = self.paket()
        waechter.wartung_an("Test")
        self.assertEqual(self.regel(a), 7)
        waechter.wartung_aus()
        self.assertIsNone(self.regel(a))

    def test_regel_8_wochenlimit(self):
        a = self.paket()
        self.assertEqual(self.regel(a, limit=80), 8)
        self.assertEqual(self.regel(a, limit=93.5), 8)
        self.assertIsNone(self.regel(a, limit=79.9))
        with mock.patch("amw.tokenprognose.lage_gemerkt", return_value={"wert": 85.0}):
            self.assertEqual(waechter.pruefen(self.con, self.pid, a)["regel"], 8)          # Quelle tokenprognose

    def test_unbekanntes_limit_erlaubt_aber_vermerkt(self):
        """P245: ohne Messung des Wochenlimits darf gestartet werden – im Protokoll steht „Wochenlimit unbekannt“."""
        a = self.paket()
        with mock.patch("amw.tokenprognose.lage_gemerkt", return_value=None):
            r = waechter.pruefen(self.con, self.pid, a)
        self.assertTrue(r["ok"])
        self.assertIn("Wochenlimit unbekannt", r["hinweis"])
        self.assertTrue(waechter.protokollieren(self.con, self.pid, a, r))
        self.assertIn("Wochenlimit unbekannt", waechter.protokoll(self.con, self.pid, a)[0]["text"])

    def test_platz_bleibt_bis_zum_merge_belegt(self):
        """P245: ein Paket in der Merge-Reihe hält seinen Platz (Resume bei Merge-Konflikt nur dort)."""
        a = self.paket(bereiche="web/a/")
        for z in ("laeuft", "abgegeben", "abnahme", "merge_reihe"):
            arbeitspaket.zustand_setzen(self.con, self.pid, "TL", a, z)
        self.assertEqual(self.regel(self.paket(bereiche="doc/")), 4)

    def test_regel_9_zweimal_unklar_pause(self):
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, plaetze=3)
        for i in range(2):
            x = self.paket(bereiche=f"web/{i}/")
            arbeitspaket.zustand_setzen(self.con, self.pid, "TL", x, "laeuft")
            arbeitspaket.zustand_setzen(self.con, self.pid, "TL", x, "unklar")
        a = self.paket(bereiche="doc/")
        self.assertEqual(self.regel(a), 9)
        self.assertTrue(waechter.zustand()["pause"])                                          # Pause bleibt …
        waechter.weiter(self.con)                                                             # … bis Lead/Mensch weiter sagt
        self.assertTrue(waechter.zustand()["pause"] is None)
        r = waechter.pruefen(self.con, self.pid, a, limit=10)                                  # P253: danach darf es wirklich starten
        self.assertTrue(r["ok"], r)
        self.assertIsNone(waechter.zustand()["pause"])
        for i in range(2):                                                                    # zwei NEUE unklare Enden → wieder Pause
            x = self.paket(bereiche=f"neu/{i}/")
            arbeitspaket.zustand_setzen(self.con, self.pid, "TL", x, "laeuft")
            arbeitspaket.zustand_setzen(self.con, self.pid, "TL", x, "abgebrochen")
        self.assertEqual(self.regel(a), 9)
        aus = io.StringIO()                                                                   # auch über die Befehlszeile
        with contextlib.redirect_stdout(aus):
            cli.main(["waechter", "weiter", "--projekt", "Spiel", "--von", "TL"])
        self.assertIsNone(self.regel(a))

    def test_regel_10_ohne_plaetze_wie_heute(self):
        a = self.paket()
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, plaetze=0)
        self.assertEqual(self.regel(a), 10)

    def test_unbekannte_aufgabe_ist_ein_fehler(self):
        """P253: keine Regel 10 („keine Arbeitsplätze“) für eine Nummer, die es nicht gibt."""
        with self.assertRaises(kern.AmwFehler) as e:
            waechter.pruefen(self.con, self.pid, 99999, limit=10)
        self.assertIn("A99999 gibt es nicht", str(e.exception))

    def test_nur_art_p(self):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Normal", "TL")
        r = waechter.pruefen(self.con, self.pid, aid, limit=10)
        self.assertFalse(r["ok"])
        self.assertIsNone(r["regel"])

    def test_protokoll_mit_regelnummer_nur_bei_aenderung(self):
        a = self.paket(befehl="")
        r = waechter.pruefen(self.con, self.pid, a, limit=10)
        self.assertTrue(waechter.protokollieren(self.con, self.pid, a, r))
        self.assertFalse(waechter.protokollieren(self.con, self.pid, a, r))                     # gleiche Antwort: kein zweiter Eintrag
        p = waechter.protokoll(self.con, self.pid, a)
        self.assertEqual(len(p), 1)
        self.assertIn(f"A{a} nicht gestartet, Regel 1", p[0]["text"])
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus):
            cli.main(["waechter", "protokoll", f"A{a}", "--projekt", "Spiel", "--von", "TL"])
            cli.main(["waechter", "pruefen", f"A{a}", "--projekt", "Spiel", "--von", "TL"])
        self.assertIn("Regel 1", aus.getvalue())

    def test_startfolge_rang_und_abhaengigkeiten(self):
        a = self.paket("A", bereiche="web/a/", rang=3)
        b = self.paket("B", bereiche="web/b/", rang=1)
        c = self.paket("C", bereiche="web/c/", rang=2)
        with db.schreiben(self.con):
            db.einfuegen(self.con, "abhaengigkeit", vor=a, nach=c)                             # C erst nach A
        self.assertEqual([x["id"] for x in waechter.reihenfolge(self.con, self.pid)], [b, a])
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'x' WHERE id = ?", (a,))
            self.con.execute("UPDATE paket SET zustand = 'fertig' WHERE aufgabe_id = ?", (a,))
        self.assertEqual([x["id"] for x in waechter.reihenfolge(self.con, self.pid)], [b, c])

    def test_auslieferung_setzt_wartung_und_wartet(self):
        a = self.paket()
        arbeitspaket.zustand_setzen(self.con, self.pid, "TL", a, "laeuft")
        self.assertTrue(waechter.p_laufend(self.con))
        runden = []

        def schlafen(s):
            runden.append(s)
            arbeitspaket.zustand_setzen(self.con, self.pid, "TL", a, "abgegeben")
            arbeitspaket.zustand_setzen(self.con, self.pid, "TL", a, "unklar")               # Laufendes endet
        fertig, rest = waechter.vor_auslieferung(self.con, frist_s=60, warte_s=1, schlafen=schlafen)
        self.assertEqual((fertig, rest), (True, []))
        self.assertEqual(len(runden), 1)
        self.assertTrue(waechter.zustand()["wartung"])                                         # während der Auslieferung: keine Starts
        self.assertEqual(self.regel(self.paket(bereiche="doc/")), 7)
        b = self.paket(bereiche="x/")
        arbeitspaket.zustand_setzen(self.con, self.pid, "TL", b, "laeuft")
        fertig, rest = waechter.vor_auslieferung(self.con, frist_s=0, warte_s=1, schlafen=lambda s: None)
        self.assertEqual((fertig, rest), (False, [b]))                                         # Frist um: Stopp mit Liste


if __name__ == "__main__":
    unittest.main()
