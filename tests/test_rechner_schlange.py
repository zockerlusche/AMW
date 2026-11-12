"""Eine Warteschlange je Rechner – über alle Projekte. Wer zuerst kommt, ist zuerst dran; ein Lead sortiert nur die Läufe
seines Projekts um, der Mensch über alle; über Läufe eines anderen Projekts erfährt man nur die Belegung, nie den Inhalt."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
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


class Reserve(Grund):
    def test_reserve_bleibt_frei_fuer_den_menschen_am_rechner(self):
        """Eingelassen wird erst, wenn nach dem Bedarf des Laufs noch die Reserve frei bleibt (Einstellung des Rechners)."""
        with mock.patch.object(betrieb, "reserve_gb", return_value=3.0):
            with self.assertRaises(kern.AmwFehler) as e:                         # Bedarf 8 GB (Grenze des Projekts) + 3 GB Reserve > 10 GB
                betrieb.lauf_start(self.con, self.p["Eins"], "A", "Tests", speicher_frei=10.0)
            self.assertIn("nur 10.0 GB frei, gebraucht 8 GB und 3 GB Reserve", str(e.exception))
            lid = betrieb.lauf_start(self.con, self.p["Eins"], "A", "Tests", speicher_frei=11.0)
            self.assertEqual(self.status(lid), "laeuft")
        betrieb.lauf_ende(self.con, self.p["Eins"], "A", lid, 0, speicher_frei=32.0)
        with mock.patch.object(betrieb, "reserve_gb", return_value=0.0):          # Reserve 0: wie früher, 8 GB frei genügen für 8 GB Bedarf
            self.assertEqual(self.status(betrieb.lauf_start(self.con, self.p["Zwei"], "A", "Tests", speicher_frei=8.0)), "laeuft")
        from amw import einstellungen
        self.assertEqual(einstellungen.FELDER["speicher_reserve_gb"][0], 3.0)     # Vorgabe: 3 GB
        self.assertEqual(einstellungen.FELDER["speicher_reserve_gb"][1]("4,5".replace(",", ".")), 4.5)
        with self.assertRaises(ValueError):
            einstellungen.FELDER["speicher_reserve_gb"][1](-1)


class Vorgemerkt(Grund):
    """Fall aus einem anderen Projekt: Ein schwerer Lauf ohne Grafikkarte lief seit gut 3 Minuten, die Schlange ließ einen
    schweren Lauf mit Grafikkarte daneben ein (gemessen 13,9 GB frei, gebraucht 8 + 3 GB Reserve) – beide brachen wegen
    Speichermangels ab. Der laufende hält seinen Bedarf frei, solange er läuft."""

    def test_grafikkarten_lauf_wartet_auf_den_speicher_des_laufenden(self):
        import datetime
        from amw import belegung
        with mock.patch.object(betrieb, "reserve_gb", return_value=3.0):
            a = betrieb.lauf_start(self.con, self.p["Eins"], "A", "Gleichheits-Läufe", speicher_frei=14.3)
            vor = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=190)).strftime("%Y-%m-%dT%H:%M:%SZ")
            with db.schreiben(self.con):
                self.con.execute("UPDATE lauf SET start_utc = ? WHERE id = ?", (vor, a))         # wie damals: seit 190 s
            b = betrieb.lauf_start(self.con, self.p["Eins"], "B", "Durchstich, echte KI", gpu=True, speicher_frei=13.9, warten=True)
            self.assertEqual(self.status(b), "angemeldet")                                        # früher: sofort eingelassen
            grund = betrieb.wartegrund(self.con, self.p["Eins"], betrieb.lauf_zeile(self.con, self.p["Eins"], b), speicher_frei=13.9)
            self.assertIn(f"nur 13.9 GB frei (8 GB davon für laufende Läufe vorgemerkt: 8 GB für L{a} von A), gebraucht 8 GB und 3 GB Reserve", grund)
            self.assertEqual(betrieb.warteschlange(self.con, speicher_frei=13.9), [])
            # bekannter Prozess (amw lauf ausfuehren): was er schon belegt, steckt in der Messung und ist nicht mehr vorgemerkt
            liste = [{"pid": 50, "eltern": 1, "name": "cmd", "gb": 0.1, "seit": None}, {"pid": 51, "eltern": 50, "name": "godot", "gb": 7.4, "seit": None}]
            with mock.patch.object(belegung, "lauf_pid", lambda lid: 50 if lid == a else None), mock.patch.object(belegung, "prozesse", lambda: liste):
                self.assertEqual(betrieb._vorgemerkt_gb(self.con), 0.5)
                self.assertEqual(betrieb.warteschlange(self.con, speicher_frei=11.0), [])         # 11 − 0,5 − 3 = 7,5 < 8
                self.assertEqual(betrieb.warteschlange(self.con, speicher_frei=13.9), [b])        # 13,9 − 0,5 − 3 = 10,4 ≥ 8
            self.assertEqual(betrieb._vorgemerkt_gb(self.con), 16.0)                              # jetzt laufen beide, Prozesse unbekannt
            betrieb.lauf_ende(self.con, self.p["Eins"], "A", a, 0, speicher_frei=20.0)
            betrieb.lauf_ende(self.con, self.p["Eins"], "B", b, 0, speicher_frei=20.0)
            self.assertEqual(betrieb._vorgemerkt_gb(self.con), 0.0)                               # nach dem Ende: nichts mehr vorgemerkt
        self.assertEqual(belegung.baum_gb([{"pid": 1, "eltern": 0, "name": "x", "gb": 1.0, "seit": None}], 9), None)   # Prozess weg: unbekannt


class WartenderBefehl(Grund):
    """Ein Agent, dessen Sitzung in einem anderen Projekt angemeldet ist (sein Ordner gehört zwei Projekten), meldet mit
    „amw lauf ausfuehren“ einen Lauf an, der warten muss. Der wartende Befehl lebt – die Schlange gibt den Lauf frei."""

    def test_wartender_befehl_gilt_als_lebendig(self):
        import os
        from amw import belegung
        with db.schreiben(self.con):
            self.con.execute("UPDATE sitzung SET zustand = 'beendet'")                         # keine Sitzung im Projekt
        with mock.patch.object(betrieb, "reserve_gb", return_value=0.0):
            vorne = betrieb.lauf_start(self.con, self.p["Eins"], "B", "läuft schon", speicher_frei=32.0, gpu=True)
            lid = betrieb.lauf_start(self.con, self.p["Eins"], "A", "Tests", speicher_frei=32.0, gpu=True, warten=True)
            l = next(x for x in betrieb.wartende(self.con) if x["id"] == lid)                 # so, wie die Schlange ihn sieht
            self.assertFalse(betrieb._lebt(self.con, self.p["Eins"], l))                       # ohne Befehl: wie bisher nicht lebendig
            with mock.patch.object(belegung, "lauf_pid", lambda x: os.getpid() if x == lid else None):
                self.assertTrue(betrieb._lebt(self.con, self.p["Eins"], l))                    # der wartende Befehl lebt
                betrieb.lauf_ende(self.con, self.p["Eins"], "B", vorne, 0, speicher_frei=32.0)
                self.assertEqual(self.status(lid), "laeuft")                                   # und wird freigegeben
            with mock.patch.object(belegung, "lauf_pid", lambda x: 999999999):
                self.assertFalse(betrieb._lebt(self.con, self.p["Eins"], l))                   # Prozess weg: nicht lebendig
        self.assertTrue(belegung.prozess_da(os.getpid()))
        self.assertFalse(belegung.prozess_da(None))


class Bedarf(Grund):
    def test_eigener_bedarf_geht_vor_der_grenze_des_projekts(self):
        with mock.patch.object(betrieb, "reserve_gb", return_value=0.0), mock.patch.object(betrieb, "cpu_laeufe", return_value=4):
            with self.assertRaises(kern.AmwFehler):                               # ohne Angabe: 8 GB (Grenze des Projekts) – 5 GB reichen nicht
                betrieb.lauf_start(self.con, self.p["Eins"], "A", "Tests", speicher_frei=5.0)
            klein = betrieb.lauf_start(self.con, self.p["Eins"], "A", "Tests", speicher_frei=5.0, braucht_gb=2)
            self.assertEqual(self.status(klein), "laeuft")
            z = self.con.execute("SELECT braucht_gb, rechner FROM lauf WHERE id = ?", (klein,)).fetchone()
            self.assertEqual((z["braucht_gb"], z["rechner"]), (2.0, betrieb.rechner()))
            with self.assertRaises(kern.AmwFehler) as e:                          # gerade gestartet: seine 2 GB zählen noch mit
                betrieb.lauf_start(self.con, self.p["Zwei"], "A", "Tests", speicher_frei=5.0, braucht_gb=4)
            self.assertIn("2 GB davon für laufende Läufe vorgemerkt", str(e.exception))
            gross = betrieb.lauf_start(self.con, self.p["Zwei"], "A", "Tests", speicher_frei=5.0, braucht_gb=4, warten=True)
            self.assertEqual(betrieb.warteschlange(self.con, speicher_frei=5.0), [])     # der Wartende wird mit seinem eigenen Bedarf geprüft
            self.assertEqual(betrieb.warteschlange(self.con, speicher_frei=6.0), [gross])
        for falsch in (0, -1, 5000):
            with self.assertRaises(kern.AmwFehler):
                betrieb.lauf_start(self.con, self.p["Eins"], "B", "x", speicher_frei=32.0, braucht_gb=falsch)

    def test_grafikspeicher_und_festplatte_nur_wenn_angemeldet(self):
        with mock.patch.object(betrieb, "vram_frei_gb", return_value=6.0), mock.patch.object(betrieb, "platte_frei_gb", return_value=20.0),                 mock.patch.object(betrieb, "cpu_laeufe", return_value=8):
            ok = betrieb.lauf_start(self.con, self.p["Eins"], "A", "ohne Angabe", speicher_frei=32.0)       # nichts angemeldet: nicht geprüft
            self.assertEqual(self.status(ok), "laeuft")
            with self.assertRaises(kern.AmwFehler) as e:
                betrieb.lauf_start(self.con, self.p["Eins"], "B", "Bild", speicher_frei=32.0, braucht_vram_gb=8)
            self.assertIn("nur 6 GB Grafikspeicher frei, gebraucht 8 GB", str(e.exception))
            with self.assertRaises(kern.AmwFehler) as e:
                betrieb.lauf_start(self.con, self.p["Eins"], "B", "Export", speicher_frei=32.0, braucht_platte_gb=50)
            self.assertIn("nur 20 GB auf der Festplatte frei, gebraucht 50 GB", str(e.exception))
            passt = betrieb.lauf_start(self.con, self.p["Eins"], "B", "Bild", speicher_frei=32.0, braucht_vram_gb=4, braucht_platte_gb=10)
            self.assertEqual(self.status(passt), "laeuft")
        with mock.patch.object(betrieb, "vram_frei_gb", return_value=None), mock.patch.object(betrieb, "cpu_laeufe", return_value=8):   # nicht messbar: hält niemanden auf
            self.assertEqual(self.status(betrieb.lauf_start(self.con, self.p["Zwei"], "A", "Bild", speicher_frei=32.0, braucht_vram_gb=8)), "laeuft")

    def test_die_warteschlange_zaehlt_nur_laeufe_ihres_rechners(self):
        hier = self.start("Eins", "A")                                            # belegt die einzige Spur dieses Rechners
        with db.schreiben(self.con):                                              # derselbe Lauf, als wäre er auf einem anderen PC angemeldet
            self.con.execute("UPDATE lauf SET rechner = 'anderer-pc' WHERE id = ?", (hier,))
        self.assertEqual(betrieb.auslastung(self.con, self.p["Eins"])["laufen"], 0)
        frei = self.start("Zwei", "A")
        self.assertEqual(self.status(frei), "laeuft")                             # die Spur dieses Rechners ist frei
        with db.schreiben(self.con):                                              # Bestand ohne Angabe gilt als dieser Rechner
            self.con.execute("UPDATE lauf SET rechner = NULL WHERE id = ?", (frei,))
        self.assertEqual(self.status(self.start("Eins", "B")), "angemeldet")

    def test_fremder_lauf_nennt_auch_seinen_bedarf(self):
        fremd = self.start("Zwei", "A", "geheim", gpu=True, erwartet_min=15, braucht_gb=4)
        with self.assertRaises(kern.AmwFehler) as e:
            betrieb.lauf_start(self.con, self.p["Eins"], "B", "Bild", gpu=True, speicher_frei=32.0)
        self.assertRegex(str(e.exception), rf"L{fremd} \(anderes Projekt, läuft seit \d\d:\d\d, voraussichtlich bis \d\d:\d\d, 4 GB\)")
        self.assertEqual(betrieb.auslastung(self.con, self.p["Eins"])["angemeldet_gb"], 4.0)


class Umstellung(Grund):
    def test_23_nach_24(self):
        alt = self.start("Eins", "A", "Bestand")
        for sp in ("braucht_gb", "braucht_vram_gb", "braucht_platte_gb", "rechner"):
            self.con.execute(f"ALTER TABLE lauf DROP COLUMN {sp}")
        for sp in ("hinweis", "hinweis_gruppe"):   # Satz für die Versionshinweise kam mit Schema 26
            self.con.execute(f"ALTER TABLE aufgabe DROP COLUMN {sp}")
        for tab in ("nachricht", "frage_verlauf"):   # wer von den Menschen es war, kam mit Schema 27
            if self.con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (tab,)).fetchone():
                self.con.execute(f"ALTER TABLE {tab} DROP COLUMN benutzer")
        self.con.execute("DROP INDEX IF EXISTS nachricht_bezug")      # Bezug an Nachrichten kam mit Schema 29
        self.con.execute("DROP INDEX IF EXISTS nachricht_antwort")
        self.con.execute("ALTER TABLE nachricht DROP COLUMN bezug")
        for sp in ("groesse", "art"):                     # Größe und Art kamen mit Schema 30
            self.con.execute(f"ALTER TABLE aufgabe DROP COLUMN {sp}")
        self.con.execute("ALTER TABLE agent DROP COLUMN entfernt_utc")      # Agenten entfernen kam mit Schema 28
        self.con.execute("PRAGMA user_version = 23")
        pfad = self.con.execute("PRAGMA database_list").fetchone()[2]
        self.con.close()
        self.con = db.verbinde(pfad)
        self.assertEqual(self.con.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
        z = self.con.execute("SELECT status, braucht_gb, rechner FROM lauf WHERE id = ?", (alt,)).fetchone()
        self.assertEqual(tuple(z), ("laeuft", None, None))
        self.assertEqual(betrieb.auslastung(self.con, self.p["Eins"])["laufen"], 1)            # zählt weiter zu diesem Rechner


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


class Tagesverlauf(unittest.TestCase):
    """Zeitstrahl „Rechner – heute“: eigene Läufe mit Inhalt, fremde nur als Zeitraum; Belegung je Tag ohne Doppelzählung."""

    def test_heute_und_je_tag(self):
        import datetime
        from unittest import mock
        from amw import belegung
        ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(ordner.cleanup)
        con = db.anlegen(os.path.join(ordner.name, "t.db"))
        self.addCleanup(con.close)
        utc = datetime.timezone.utc
        mittag = datetime.datetime.now().astimezone().replace(hour=12, minute=0, second=0, microsecond=0).astimezone(utc)   # heute 12 Uhr Ortszeit
        iso = lambda stunden: (mittag + datetime.timedelta(hours=stunden)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with db.schreiben(con):
            a = db.einfuegen(con, "projekt", name="A", angelegt_utc=db.jetzt())
            b = db.einfuegen(con, "projekt", name="B", angelegt_utc=db.jetzt())

            def lauf(pid, agent, text, status, start=None, ende=None, **mehr):
                return db.einfuegen(con, "lauf", projekt_id=pid, agent=agent, beschreibung=text, status=status, angemeldet_utc=iso(-30),
                                    start_utc=start, ende_utc=ende, **mehr)
            l1 = lauf(a, "CC1", "Gesamtlauf", "fertig", iso(-3), iso(-2), braucht_gb=6)
            lauf(b, "GW1", "Geheimer Build", "fertig", iso(-2.5), iso(-1.5), braucht_gb=4)             # überlappt l1 um 30 min
            l3 = lauf(a, "CC1", "Browser-Tests", "laeuft", iso(-0.5), erwartet_min=60)
            lauf(b, "GW1", "Geheim wartet", "angemeldet", erwartet_min=20)
            lauf(a, "CC1", "Gestern", "fertig", iso(-27), iso(-26))
            lauf(a, "CC1", "Anderer Rechner", "fertig", iso(-3), iso(-2), rechner="woanders")
        with mock.patch.object(belegung, "prozesse", lambda: []), mock.patch.object(belegung, "_gemerkt", [0.0, None, []]):
            d = betrieb.tagesverlauf(con, a, jetzt=mittag)
        self.assertEqual([(x["id"], x["eigen"], x["wer"], x["text"], x["status"]) for x in d["laeufe"]],
                         [(l1, True, "CC1", "Gesamtlauf", "fertig"), (None, False, None, None, "fertig"),
                          (l3, True, "CC1", "Browser-Tests", "laeuft"), (None, False, None, None, "wartet")])
        self.assertNotIn("Geheim", json.dumps(d, ensure_ascii=False))                              # von fremden Läufen kein Inhalt
        self.assertEqual((d["laeufe"][0]["gb"], d["laeufe"][1]["gb"], d["laeufe"][3]["erwartet_min"]), (6.0, 4.0, 20.0))
        self.assertEqual((d["laeufe"][3]["start_utc"], d["laeufe"][3]["angemeldet_utc"]), (None, iso(-30)))
        self.assertEqual((d["jetzt_utc"], d["von_utc"], d["bis_utc"]), (iso(0), iso(-12), iso(12)))
        heute, gestern = mittag.astimezone().date().isoformat(), (mittag.astimezone().date() - datetime.timedelta(days=1)).isoformat()
        tage = {x["tag"]: x for x in d["tage"]}
        self.assertEqual((tage[heute]["stunden"], tage[heute]["laeufe"], tage[heute]["eigene"]), (2.0, 3, 2))   # 3–1,5 h davor am Stück + 0,5 h laufend
        self.assertEqual((tage[gestern]["stunden"], tage[gestern]["laeufe"]), (1.0, 1))
        self.assertEqual(betrieb.tagesverlauf(con, a, jetzt=mittag, tage=0)["tage"], [tage[heute]])   # Zeitraum begrenzbar
        d = workbench.daten_planung(con, b)["rechner_heute"]                                       # aus Sicht des anderen Projekts
        self.assertEqual([x["text"] for x in d["laeufe"] if x["eigen"]], ["Geheimer Build", "Geheim wartet"])
        self.assertNotIn("Gesamtlauf", json.dumps(d, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
