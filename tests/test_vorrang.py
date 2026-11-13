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
            betrieb.lauf_start(self.con, self.p["Eins"], "Chef", "GPU", warten=True, gpu=True, speicher_frei=32.0, braucht_gb=0.5)   # Schlange nicht leer
            betrieb.lauf_ende(self.con, self.p["Eins"], "C", a, 0, speicher_frei=10.0)
            self.assertEqual((self.status(b), self.status(c)), ("angemeldet", "angemeldet"))
            g = betrieb.wartegrund(self.con, self.p["Eins"], betrieb.lauf_zeile(self.con, self.p["Eins"], c), speicher_frei=10.0)
            self.assertIn(f"vor dir: L{b} (anderes Projekt, Vorrang, wartet auf Arbeitsspeicher: braucht 8 GB, 6.5 GB nutzbar)", g)
            with self.assertRaises(kern.AmwFehler) as f:
                betrieb.lauf_start(self.con, self.p["Eins"], "B", "ohne warten", speicher_frei=10.0, braucht_gb=1)
            self.assertIn("braucht 8 GB, 6.5 GB nutzbar", str(f.exception))


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


class Stufe2(Grund):
    """A1623 V2: Aufrücken nach Wartezeit, Platz freihalten für Vorrang, Meldung an den Menschen."""

    def setUp(self):
        super().setUp()
        self.v, self.auf, self.frei = {"Zwei": "hoch"}, 30, True
        for name, f in (("vorrang", lambda: dict(self.v)), ("aufruecken_min", lambda: self.auf), ("platz_freihalten", lambda: self.frei),
                        ("reserve_gb", lambda: 3.0)):
            p = mock.patch.object(betrieb, name, f)
            p.start()
            self.addCleanup(p.stop)

    def alt(self, lid, minuten):
        with db.schreiben(self.con):
            self.con.execute("UPDATE lauf SET angemeldet_utc = ? WHERE id = ?", (vor_minuten(minuten), lid))

    def test_aufruecken_nach_wartezeit(self):
        self.v = {"Zwei": "niedrig"}
        self.start("Eins", "C")
        b = self.start("Zwei", "A")
        c = self.start("Eins", "A")
        reihe = lambda: [x["id"] for x in betrieb.wartende(self.con)]
        self.alt(b, 20)
        self.assertEqual(reihe(), [c, b])                  # niedrig, noch nicht aufgerückt
        self.alt(b, 40)
        self.assertEqual(reihe(), [c, b])                  # jetzt normal – bei Gleichstand zählt zuerst die Projekt-Stufe (TL #23284)
        self.alt(b, 70)
        self.assertEqual(reihe(), [b, c])                  # hoch: vor jedem normalen – verhungern kann er nicht
        self.assertEqual(betrieb.lauf_stufe(self.con, betrieb.wartende(self.con)[0]), 2)     # höchstens hoch
        g = betrieb.wartegrund(self.con, self.p["Eins"], betrieb.lauf_zeile(self.con, self.p["Eins"], c), speicher_frei=32.0)
        self.assertIn(f"vor dir: L{b} (anderes Projekt, niedriger Vorrang, aufgerückt nach Wartezeit)", g)
        self.auf = 0                                       # aus
        self.assertEqual(reihe(), [c, b])

    def test_echtes_hoch_vor_aufgerueckt_bei_gleichstand(self):
        """TL #23284 (Befund CCamw #23267): Ein normaler Lauf, der nach 30 Minuten auf „hoch“ aufgerückt ist, stand bei
        Gleichstand nach Ankunft vor einem Lauf mit echtem „hoch“. Jetzt: gleiche Stufe → zuerst die Stufe des Projekts."""
        self.start("Eins", "C")                            # belegt die CPU-Spur
        alt = self.start("Eins", "A")                       # normal, kam zuerst
        self.alt(alt, 35)                                   # nach 35 min aufgerückt auf hoch
        neu = self.start("Zwei", "A")                       # echtes hoch, kam später
        self.assertEqual(betrieb.lauf_stufe(self.con, betrieb.wartende(self.con)[0]), 2)
        self.assertEqual([x["id"] for x in betrieb.wartende(self.con)], [neu, alt])
        g = betrieb.wartegrund(self.con, self.p["Eins"], betrieb.lauf_zeile(self.con, self.p["Eins"], alt), speicher_frei=32.0)
        self.assertIn(f"vor dir: L{neu} (anderes Projekt, Vorrang)", g)
        g = betrieb.wartegrund(self.con, self.p["Zwei"], betrieb.lauf_zeile(self.con, self.p["Zwei"], neu), speicher_frei=32.0)
        self.assertNotIn(f"L{alt}", g)                      # der aufgerückte steht nicht vor ihm
        self.auf = 0                                        # ohne Aufrücken ohnehin
        self.assertEqual([x["id"] for x in betrieb.wartende(self.con)], [neu, alt])
        self.auf = 30                                       # aufgerückt bleibt vor anderen normalen
        drei = self.start("Eins", "B")
        self.assertEqual([x["id"] for x in betrieb.wartende(self.con)], [neu, alt, drei])

    def test_neuer_echter_hoch_lauf_wartet_nicht_hinter_aufgeruecktem(self):
        """lauf_start: Ein neuer Lauf mit echtem „hoch“ wartet nicht auf einen nur aufgerückten (gleiche Regel wie wartende())."""
        with mock.patch.object(betrieb, "reserve_gb", return_value=3.0):
            b = betrieb.lauf_start(self.con, self.p["Eins"], "A", "groß", warten=True, speicher_frei=8.0, braucht_gb=8)
            self.assertEqual(self.status(b), "angemeldet")  # wartet auf Speicher und sperrt die CPU-Spur
            self.alt(b, 35)                                 # aufgerückt auf hoch
            c = betrieb.lauf_start(self.con, self.p["Zwei"], "A", "klein", warten=True, speicher_frei=8.0, braucht_gb=2)
            self.assertEqual(self.status(c), "laeuft")      # echtes hoch: der aufgerückte hält ihn nicht auf

    def test_platz_freihalten_fuer_vorrang(self):
        a = betrieb.lauf_start(self.con, self.p["Eins"], "C", "GPU", warten=True, gpu=True, speicher_frei=32.0, braucht_gb=2)
        h = betrieb.lauf_start(self.con, self.p["Zwei"], "A", "GPU", warten=True, gpu=True, speicher_frei=32.0, braucht_gb=6)
        self.assertEqual((self.status(a), self.status(h)), ("laeuft", "angemeldet"))       # wartet auf die Grafikkarte
        n = betrieb.lauf_start(self.con, self.p["Eins"], "B", "CPU", warten=True, speicher_frei=12.0, braucht_gb=4)
        self.assertEqual(self.status(n), "angemeldet")      # 12 − 2 − 3 = 7 ≥ 4, aber 4 + 6 für den Vorrang-Lauf > 7
        g = betrieb.wartegrund(self.con, self.p["Eins"], betrieb.lauf_zeile(self.con, self.p["Eins"], n), speicher_frei=12.0)
        self.assertIn(f"Platz frei gehalten für L{h} (anderes Projekt) mit Vorrang: braucht 6 GB", g)
        self.assertEqual(betrieb.warteschlange(self.con, speicher_frei=12.0), [])
        self.assertEqual(betrieb.warteschlange(self.con, speicher_frei=20.0), [n])          # genug für beide
        betrieb.lauf_ende(self.con, self.p["Eins"], "B", n, 0, speicher_frei=32.0)
        n2 = betrieb.lauf_start(self.con, self.p["Eins"], "B", "CPU", warten=True, speicher_frei=12.0, braucht_gb=4)
        self.assertEqual(self.status(n2), "angemeldet")
        self.frei = False                                  # Schalter aus: wie in V1
        self.assertEqual(betrieb.warteschlange(self.con, speicher_frei=12.0), [n2])

    def test_meldung_nach_20_minuten_einmal(self):
        self.start("Eins", "C")
        h = self.start("Zwei", "A")
        self.alt(h, 10)
        self.assertEqual(betrieb.vorrang_meldungen(self.con), [])
        self.alt(h, 25)
        self.assertEqual(betrieb.vorrang_meldungen(self.con), [f"L{h} mit Vorrang wartet seit 25 Minuten"])
        self.assertEqual(betrieb.vorrang_meldungen(self.con), [])                          # nur einmal
        m = self.con.execute("SELECT * FROM nachricht WHERE kurz LIKE ?", (f"L{h} mit Vorrang%",)).fetchone()
        self.assertEqual((m["projekt_id"], m["von"], m["art"]), (self.p["Zwei"], "AMW", "meldung"))
        self.assertIn("Warum: Platz 1 von 1 (Vorrang für Zwei) – CPU-Spur voll", m["text"])
        self.assertIn(f"amw lauf vorziehen {h}", m["text"])
        self.v = {}
        self.assertEqual(betrieb.vorrang_meldungen(self.con), [])


class KopfPasstNie(Grund):
    """Befund CCamw 13.11.: Ein GlassWorld-Lauf mit Vorrang brauchte 8 + 3 GB, frei waren selbst bei leerem Rechner nur 9,4 GB –
    er passte nie, und weil niemand überholt (und Platz für ihn frei gehalten wurde), stand die ganze Schlange. Jetzt: passt ein
    Lauf auch bei leerer Schlange nicht, sperrt er niemanden; er bleibt vorn und startet, sobald der Speicher reicht."""

    def setUp(self):
        super().setUp()
        for name, f in (("vorrang", lambda: {"Zwei": "hoch"}), ("reserve_gb", lambda: 3.0), ("aufruecken_min", lambda: 30),
                        ("platz_freihalten", lambda: True)):
            p = mock.patch.object(betrieb, name, f)
            p.start()
            self.addCleanup(p.stop)

    def test_kopf_der_nie_passt_sperrt_niemanden(self):
        gross = betrieb.lauf_start(self.con, self.p["Zwei"], "A", "groß", warten=True, speicher_frei=9.4, braucht_gb=8)
        self.assertEqual(self.status(gross), "angemeldet")
        klein = betrieb.lauf_start(self.con, self.p["Eins"], "A", "klein", warten=True, speicher_frei=9.4, braucht_gb=2)
        self.assertEqual(self.status(klein), "laeuft")                                     # früher: wartete hinter dem großen – für immer
        betrieb.lauf_ende(self.con, self.p["Eins"], "A", klein, 0, speicher_frei=9.4)
        self.assertEqual(self.status(gross), "angemeldet")
        g = betrieb.wartegrund(self.con, self.p["Zwei"], betrieb.lauf_zeile(self.con, self.p["Zwei"], gross), speicher_frei=9.4)
        self.assertIn("passt auch bei leerer Schlange nicht", g)
        zwei = betrieb.lauf_start(self.con, self.p["Eins"], "B", "noch einer", warten=True, speicher_frei=9.4, braucht_gb=1)
        self.assertEqual(self.status(zwei), "laeuft")
        betrieb.lauf_ende(self.con, self.p["Eins"], "B", zwei, 0, speicher_frei=20.0)
        self.assertEqual(self.status(gross), "laeuft")                                      # genug frei: der große kommt dran

    def test_laeuft_etwas_wartet_man_wie_bisher(self):
        a = betrieb.lauf_start(self.con, self.p["Eins"], "C", "läuft", warten=True, speicher_frei=32.0, braucht_gb=2)
        gross = betrieb.lauf_start(self.con, self.p["Zwei"], "A", "groß", warten=True, speicher_frei=9.4, braucht_gb=8)
        self.assertEqual((self.status(a), self.status(gross)), ("laeuft", "angemeldet"))
        klein = betrieb.lauf_start(self.con, self.p["Eins"], "A", "klein", warten=True, speicher_frei=9.4, braucht_gb=1)
        self.assertEqual(self.status(klein), "angemeldet")                                 # ein Lauf endet bald – dann passt er vielleicht


class Einstellung(unittest.TestCase):
    def test_pruefung_und_speichern(self):
        pruefe = einstellungen.FELDER["vorrang"][1]
        self.assertEqual(einstellungen.FELDER["vorrang"][0], {})
        self.assertEqual((einstellungen.FELDER["vorrang_aufruecken_min"][0], einstellungen.FELDER["vorrang_platz_freihalten"][0]), (30, True))
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
                  're_vorrang: "Vorrang in der Warteschlange: {x}."', 're_vorrang: "Priority in the queue: {x}."',
                  'e_vr_auf: "Aufrücken nach Wartezeit (Minuten)"', 'e_vr_auf: "Move up after waiting (minutes)"',
                  'e_vr_platz: "Platz freihalten für Vorrang"', 'e_vr_platz: "Keep room for priority"'):
            self.assertIn(x, html)


if __name__ == "__main__":
    unittest.main()
