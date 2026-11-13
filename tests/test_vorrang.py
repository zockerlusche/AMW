"""Vorrang der Projekte in der Warteschlange (A1623 V1): Einstellung dieses PCs je Projekt hoch | normal | niedrig;
Reihenfolge erst Vorziehen durch den Menschen, dann Vorrang, dann Ankunft; Laufendes bleibt unberührt; Wartegrund nennt
Vorrang und Speicherbedarf des Vordermanns; Läufe ohne eigene Angabe halten die Projekt-Grenze nur beim Anlaufen frei."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime
import os
import unittest
from unittest import mock

from amw import aktionen, betrieb, db, einstellungen, kern
from tests.test_rechner_schlange import Grund


def vor_minuten(n):
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=n)).strftime("%Y-%m-%dT%H:%M:%SZ")


class Vorrang(Grund):
    def setUp(self):
        super().setUp()
        self.v = {"Zwei": "hoch"}
        p = mock.patch.object(betrieb, "vorrang", lambda: dict(self.v))
        p.start()
        self.addCleanup(p.stop)

    def reihe(self):
        return [x["id"] for x in betrieb.wartende(self.con)]

    def test_reihenfolge_vorrang_vor_ankunft_laufendes_bleibt(self):
        a = self.start("Eins", "A")                        # läuft (CPU-Spur: 1 Lauf)
        self.assertEqual(self.status(a), "laeuft")
        b = self.start("Eins", "B")                        # wartet als Erster
        c = self.start("Zwei", "A")                        # kommt später, Projekt mit Vorrang
        self.assertEqual([self.status(x) for x in (a, b, c)], ["laeuft", "angemeldet", "angemeldet"])   # nie abgebrochen
        self.assertEqual(self.reihe(), [c, b])
        g = betrieb.wartegrund(self.con, self.p["Eins"], betrieb.lauf_zeile(self.con, self.p["Eins"], b), speicher_frei=32.0)
        self.assertIn(f"vor dir: L{c} (anderes Projekt, Vorrang)", g)
        self.assertNotIn("Zwei", g)                        # fremde Projektnamen nie im Text an Agenten
        g = betrieb.wartegrund(self.con, self.p["Zwei"], betrieb.lauf_zeile(self.con, self.p["Zwei"], c), speicher_frei=32.0)
        self.assertTrue(g.startswith("Platz 1 von 2 (Vorrang für Zwei)"), g)
        betrieb.lauf_ende(self.con, self.p["Eins"], "A", a, 0, speicher_frei=32.0)
        self.assertEqual(self.status(c), "laeuft")         # der Vorrang-Lauf zuerst
        self.assertEqual(self.status(b), "angemeldet")

    def test_niedrig_nach_normal_und_vorziehen_schlaegt_vorrang(self):
        self.v = {"Zwei": "hoch", "Eins": "niedrig"}
        a = self.start("Zwei", "C")                        # läuft
        b = self.start("Eins", "A")                        # niedrig
        c = self.start("Zwei", "A")                        # hoch
        self.assertEqual(self.reihe(), [c, b])
        self.v = {"Eins": "niedrig"}                       # Zwei jetzt normal: niedrig bleibt dahinter
        self.assertEqual(self.reihe(), [c, b])
        self.v = {}                                        # alle normal: Ankunft
        self.assertEqual(self.reihe(), [b, c])
        self.v = {"Zwei": "hoch"}
        betrieb.lauf_vorziehen(self.con, self.p["Eins"], kern.ENTWICKLER, b)    # der Mensch zieht vor – ganz oben
        self.assertEqual(self.reihe(), [b, c])
        betrieb.lauf_ende(self.con, self.p["Zwei"], "C", a, 0, speicher_frei=32.0)
        self.assertEqual((self.status(b), self.status(c)), ("laeuft", "angemeldet"))

    def test_lead_sortiert_weiter_nur_im_eigenen_projekt(self):
        a = self.start("Eins", "C")
        b1, b2 = self.start("Eins", "A"), self.start("Eins", "B")
        c = self.start("Zwei", "A")
        self.assertEqual(self.reihe(), [c, b1, b2])
        betrieb.lauf_vorziehen(self.con, self.p["Eins"], "Chef", b2)           # Lead: nur unter den eigenen
        self.assertEqual(self.reihe(), [c, b2, b1])
        self.assertTrue(a)

    def test_neuer_vorrang_lauf_wartet_nicht_hinter_normalen(self):
        with mock.patch.object(betrieb, "reserve_gb", return_value=3.0):
            b = betrieb.lauf_start(self.con, self.p["Eins"], "A", "groß", warten=True, speicher_frei=8.0, braucht_gb=8)
            self.assertEqual(self.status(b), "angemeldet")                         # wartet auf Speicher, sperrt die CPU-Spur
            c = betrieb.lauf_start(self.con, self.p["Zwei"], "A", "klein", warten=True, speicher_frei=8.0, braucht_gb=2)
            self.assertEqual(self.status(c), "laeuft")                              # Vorrang: der normale wartende hält ihn nicht auf
            d = betrieb.lauf_start(self.con, self.p["Eins"], "B", "klein", warten=True, speicher_frei=30.0, braucht_gb=1)
            self.assertEqual(self.status(d), "angemeldet")                          # ohne Vorrang: niemand überholt (wie bisher)

    def test_vordermann_nennt_speicherbedarf(self):
        with mock.patch.object(betrieb, "reserve_gb", return_value=3.0):
            a = self.start("Eins", "C")                                             # belegt die CPU-Spur
            b = betrieb.lauf_start(self.con, self.p["Zwei"], "A", "groß", warten=True, speicher_frei=10.0, braucht_gb=8)
            c = betrieb.lauf_start(self.con, self.p["Eins"], "A", "klein", warten=True, speicher_frei=10.0, braucht_gb=1)
            with db.schreiben(self.con):
                self.con.execute("UPDATE lauf SET start_utc = ? WHERE id = ?", (vor_minuten(30), a))   # ohne Angabe, lange gelaufen
            betrieb.lauf_ende(self.con, self.p["Eins"], "C", a, 0, speicher_frei=10.0)
            self.assertEqual((self.status(b), self.status(c)), ("angemeldet", "angemeldet"))
            g = betrieb.wartegrund(self.con, self.p["Eins"], betrieb.lauf_zeile(self.con, self.p["Eins"], c), speicher_frei=10.0)
            self.assertIn(f"vor dir: L{b} (anderes Projekt, Vorrang, wartet auf Arbeitsspeicher: braucht 8 GB, 7 GB nutzbar)", g)
            with self.assertRaises(kern.AmwFehler) as f:
                betrieb.lauf_start(self.con, self.p["Eins"], "B", "ohne warten", speicher_frei=10.0, braucht_gb=1)
            self.assertIn("braucht 8 GB, 7 GB nutzbar", str(f.exception))


class Liste(Grund):
    def test_lauf_liste_zeigt_laufende_und_vorrang(self):
        import contextlib
        import io
        from amw import cli
        a = betrieb.lauf_start(self.con, self.p["Zwei"], "A", "geheim", warten=True, speicher_frei=32.0)     # ohne Angabe: 8 GB vorgemerkt
        b = self.start("Zwei", "B")
        c = self.start("Eins", "A", text="meins")
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "t.db")}), \
                mock.patch.object(betrieb, "vorrang", lambda: {"Zwei": "hoch"}), contextlib.redirect_stdout(aus):
            self.assertEqual(cli.main(["lauf", "liste", "--projekt", "Eins", "--von", "A"]), 0)
        text = aus.getvalue()
        self.assertIn(f"Läuft auf diesem Rechner:\n  L{a} (anderes Projekt, läuft seit", text)
        self.assertIn("· 8 GB vorgemerkt", text)
        self.assertIn(f"1. L{b:<5} –        schwer Vorrang seit", text)
        self.assertIn(f"2. L{c:<5} A        schwer seit", text)
        self.assertNotIn("geheim", text)
        self.assertNotIn("Zwei", text)


class Anlauf(Grund):
    """A1623 c): Ein laufender Lauf ohne eigene Bedarfsangabe hält die Grenze seines Projekts nur beim Anlaufen frei."""

    def test_vormerkung_nur_beim_anlaufen(self):
        a = self.start("Eins", "A")                                  # ohne Angabe: Grenze des Projekts (8 GB)
        self.assertEqual(betrieb._vorgemerkt_gb(self.con), 8.0)
        with db.schreiben(self.con):
            self.con.execute("UPDATE lauf SET start_utc = ? WHERE id = ?", (vor_minuten(betrieb.ANLAUF_MIN - 1), a))
        self.assertEqual(betrieb._vorgemerkt_gb(self.con), 8.0)
        with db.schreiben(self.con):
            self.con.execute("UPDATE lauf SET start_utc = ? WHERE id = ?", (vor_minuten(betrieb.ANLAUF_MIN + 1), a))
        self.assertEqual(betrieb._vorgemerkt_gb(self.con), 0.0)     # steckt jetzt in der Messung
        with db.schreiben(self.con):
            self.con.execute("UPDATE lauf SET braucht_gb = 6 WHERE id = ?", (a,))
        self.assertEqual(betrieb._vorgemerkt_gb(self.con), 6.0)     # eigene Angabe: gilt, solange er läuft

    def test_speichergrund_nennt_wer_vorgemerkt_hat(self):
        with mock.patch.object(betrieb, "reserve_gb", return_value=3.0):
            a = betrieb.lauf_start(self.con, self.p["Zwei"], "A", "x", warten=True, speicher_frei=32.0, gpu=True, braucht_gb=6)
            b = betrieb.lauf_start(self.con, self.p["Eins"], "A", "y", warten=True, speicher_frei=11.0, braucht_gb=4)
            g = betrieb.wartegrund(self.con, self.p["Eins"], betrieb.lauf_zeile(self.con, self.p["Eins"], b), speicher_frei=11.0)
            self.assertIn(f"6 GB davon für laufende Läufe vorgemerkt: 6 GB für L{a} (anderes Projekt", g)
            self.assertNotIn("Zwei", g)


class Einstellung(unittest.TestCase):
    def test_pruefung_und_speichern(self):
        pruefe = einstellungen.FELDER["vorrang"][1]
        self.assertEqual(einstellungen.FELDER["vorrang"][0], {})
        self.assertEqual(pruefe({"GlassWorld": "hoch", "AMW": "normal", "LayerIT": "Niedrig"}), {"GlassWorld": "hoch", "LayerIT": "niedrig"})
        self.assertEqual(pruefe('{"A": "hoch"}'), {"A": "hoch"})
        for falsch in ({"A": "sehr hoch"}, ["A"], {"": "hoch"}):
            with self.assertRaises(ValueError):
                pruefe(falsch)
        einstellungen.speichern({"vorrang": {"GlassWorld": "hoch"}})
        self.assertEqual(betrieb.vorrang(), {"GlassWorld": "hoch"})
        einstellungen.speichern({"vorrang": {}})
        self.assertEqual(betrieb.vorrang(), {})
        self.assertIsNot(einstellungen.laden()["vorrang"], einstellungen.FELDER["vorrang"][0])   # Vorgabe nie geteilt

    def test_nur_am_pc(self):
        con = db.anlegen(os.path.join(os.environ["LOCALAPPDATA"], "vorrang.db"))
        self.addCleanup(con.close)
        with db.schreiben(con):
            pid = db.einfuegen(con, "projekt", name="P", angelegt_utc=db.jetzt())
        with self.assertRaises(aktionen.Ungueltig):
            aktionen.einstellen(con, pid, "pc", {"vorrang": {"P": "hoch"}}, "briefkasten")


class Online(Grund):
    def test_fremde_namen_bleiben_am_pc(self):
        from amw import abgleich, workbench
        with mock.patch.object(betrieb, "vorrang", lambda: {"Zwei": "hoch", "Eins": "niedrig"}):
            lokal = workbench.daten_einstellungen(self.con, self.p["Eins"])
            self.assertEqual(lokal["pc"]["vorrang_projekte"], ["Eins", "Zwei"])
            self.assertEqual(betrieb.auslastung(self.con, self.p["Eins"])["vorrang"],
                             [{"projekt": "Zwei", "stufe": "hoch"}, {"projekt": "Eins", "stufe": "niedrig"}])
            with mock.patch.object(einstellungen, "wert", lambda k: {"Zwei": "hoch", "Eins": "niedrig"} if k == "vorrang" else einstellungen.laden()[k]), \
                    mock.patch.object(einstellungen, "laden", lambda: {**{k: v[0] for k, v in einstellungen.FELDER.items()}, "vorrang": {"Zwei": "hoch", "Eins": "niedrig"}}):
                a = abgleich.ansichten(self.con, self.p["Eins"])
        self.assertEqual(a["/api/einstellungen"]["pc"]["vorrang"], {"Eins": "niedrig"})
        self.assertEqual(a["/api/einstellungen"]["pc"]["vorrang_projekte"], ["Eins"])
        self.assertEqual(a["/api/start"]["rechner"]["vorrang"], [{"projekt": "Eins", "stufe": "niedrig"}])

    def test_zeitstrahl_markiert_vorrang(self):
        self.start("Eins", "A")
        self.start("Zwei", "A")
        with mock.patch.object(betrieb, "vorrang", lambda: {"Zwei": "hoch"}):
            d = betrieb.tagesverlauf(self.con, self.p["Eins"])
        self.assertEqual([(l["eigen"], l["vorrang"]) for l in d["laeufe"]], [(True, None), (False, "hoch")])


class Texte(unittest.TestCase):
    def test_texte_de_en(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "amw", "workbench.html"), encoding="utf-8") as f:
            html = f.read()
        for x in ('e_vorrang: "Vorrang der Projekte"', 'e_vorrang: "Project priority"', 'vr_niedrig: "niedrig"', 'vr_niedrig: "low"',
                  'rh_l_vorrang: "Vorrang (Einstellung dieses PCs)"', 'rh_l_vorrang: "Priority (setting of this PC)"',
                  're_vorrang: "Vorrang in der Warteschlange: {x}."', 're_vorrang: "Priority in the queue: {x}."'):
            self.assertIn(x, html)


if __name__ == "__main__":
    unittest.main()
