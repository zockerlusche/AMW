"""A2140 (TH163/TH164): ein Entwurf zu einer Konzeptänderung hält genau die nicht begonnenen Pakete an, die er ändert oder verwirft – bis
zum Ja, auch ohne Lead. Frei werden sie mit dem Ja, „gilt weiter“, „nichts zu bauen“ und einem neuen Entwurf, der sie nicht mehr nennt.
Von Hand gesetzte Gründe bleiben, Headless startet Angehaltenes nicht, der Verlauf sagt es je einmal."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
from unittest import mock

from amw import (arbeitspaket, cli, db, delta_halt, entwurf_warten, kern, paketliste, planansicht, planer, planer_delta, planung, themen, tore,
                 verlauf_quellen, verteilen, waechter, wartegrund)
from tests import test_planer_delta
from tests.rundgang import Rundgang


class Grund(test_planer_delta.BlockGrund):
    """P1 fertig, P2 läuft, P3 nicht begonnen; dazu p (Headless, startklar) und ein Paket, das der Entwurf nicht nennt."""

    def setUp(self):
        super().setUp()
        self.halt = f"das Ja zur Änderung TH{self.tid}"
        self.p = self.neu("Tests zur Anmeldung", pruefbefehl="python -m unittest tests.test_x", dateibereich="app/x.py")
        arbeitspaket.setzen(self.con, self.pid, "TL", self.p, art="p", modell="sonnet")
        arbeitspaket.zustand_setzen(self.con, self.pid, "TL", self.p, "startklar")
        self.andere = self.neu("Nicht genannt")

    def neu(self, titel, **mehr):
        a = planung.schritt_setzen(self.con, self.pid, "TL", titel=titel, auftrag="x", bogen_id=self.m1, groesse="S", art="mechanisch", **mehr)
        themen.verweise_setzen(self.con, self.pid, "TL", a, [self.tid])
        return a

    def delta(self, aendern=(), verwerfen=()):
        return self.entwurf(neu=False, aendern=[{"paket": f"A{a}", "titel": f"Neu {a}", "auftrag": "Neuer Auftrag.", "grund": "Passkey"} for a in aendern],
                            verwerfen=[{"paket": f"A{a}", "grund": "entfällt"} for a in verwerfen])

    def gruende(self, aid):
        return [g["bezug"] for g in wartegrund.offene(self.con, aid)]

    def verlauf(self):
        return [x["text"] for x in verlauf_quellen._delta(self.con, self.pid) if "Paket" in x["text"] or "verworfen" in x["text"]][::-1]

    def ja(self):
        return planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid)

    def post(self, an="TL"):
        return [r["text"] for r in self.con.execute("SELECT n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ?"
                                                   " AND n.von = 'AMW' ORDER BY n.id", (an,))]


class Anhalten(Grund):
    def test_genau_die_genannten_nicht_begonnenen(self):
        self.assertEqual(delta_halt.gehalten(self.con, self.pid), {})                          # die Textfassung allein hält nichts an
        self.delta([self.p3], [self.p])
        self.assertEqual(delta_halt.gehalten(self.con, self.pid), {self.p3: {self.tid}, self.p: {self.tid}})
        self.assertEqual((self.gruende(self.p3), self.gruende(self.p)), ([self.halt], [self.halt]))
        for a in (self.p1, self.p2, self.andere):
            self.assertEqual(self.gruende(a), [], a)
        self.assertEqual(self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (self.p2,)).fetchone()[0], "laeuft")
        self.assertEqual(arbeitspaket.lesen(self.con, self.p)["zustand"], "startklar")          # nichts umgestellt – beim Lösen ist nichts zurückzustellen
        self.assertEqual(self.verlauf(), [f"2 Pakete angehalten bis zur Freigabe der Änderung TH{self.tid}"])

    def test_auch_ohne_lead(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE agent SET rolle = 'agent' WHERE kennung = 'TL'")
        self.assertFalse(kern.lead(self.con, self.pid))
        self.delta([self.p3])
        self.assertEqual(self.gruende(self.p3), [self.halt])
        self.ja()
        self.assertEqual(self.gruende(self.p3), [])

    def test_entwurf_ohne_wirkung_haelt_nichts_an(self):
        self.entwurf(neu=False)                                                                # nur neue Pakete
        self.assertEqual((delta_halt.gehalten(self.con, self.pid), self.verlauf()), ({}, []))

    def test_der_lead_erfaehrt_es(self):
        self.delta([self.p3], [self.p])
        self.assertIn(f"Bis zum Ja angehalten: A{self.p3}, A{self.p}\nLaufende bauen zu Ende: A{self.p2}\nFreigeben:", self.post()[-1])

    def test_inzwischen_begonnen_wird_nicht_angehalten(self):
        d = planer_delta.kontext(self.con, self.pid, self.tid)
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'laeuft', begonnen_utc = ? WHERE id = ?", (db.jetzt(), self.p3))
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 2, {"verwerfen": [{"paket": f"A{self.p3}", "grund": "x"}]}, delta=d)
        self.assertEqual(self.gruende(self.p3), [])

    def test_einmal_und_ohne_zweite_zeile(self):
        self.delta([self.p3])
        self.assertEqual([delta_halt.abgleichen(self.con, self.pid) for _ in range(3)], [[], [], []])
        self.assertEqual((self.gruende(self.p3), len(self.verlauf())), ([self.halt], 1))


class Loesen(Grund):
    def test_mit_dem_ja_geaenderte_frei_verworfene_verworfen(self):
        self.delta([self.p3], [self.p])
        self.ja()
        self.assertEqual(self.gruende(self.p3), [])
        r = self.con.execute("SELECT titel, status FROM aufgabe WHERE id = ?", (self.p3,)).fetchone()
        self.assertEqual((r["titel"], r["status"]), (f"Neu {self.p3}", "wartet"))
        self.assertEqual(self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (self.p,)).fetchone()[0], "verworfen")
        self.assertEqual(self.verlauf()[1:], [f"Änderung TH{self.tid} freigegeben, 1 Paket wieder frei, 1 verworfen"])
        self.assertEqual(delta_halt.abgleichen(self.con, self.pid), [])
        self.assertEqual(len(self.verlauf()), 2)

    def test_ein_einzelnes_ja_von_zweien_loest_nicht(self):
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, feinplan_freigabe="co+lead")
        self.delta([self.p3])
        planer.uebernehmen(self.con, self.pid, "Co", self.tid)
        delta_halt.abgleichen(self.con, self.pid)
        self.assertEqual(self.gruende(self.p3), [self.halt])
        planer.uebernehmen(self.con, self.pid, "TL", self.tid)
        self.assertEqual(self.gruende(self.p3), [])

    def test_gilt_weiter_vom_pfleger_und_vom_menschen(self):
        for von in ("CC1", kern.ENTWICKLER):
            with self.subTest(von=von):
                self.delta([self.p3])
                self.assertEqual(self.gruende(self.p3), [self.halt])
                if von == kern.ENTWICKLER:                                                     # am selben Tag, andere Sekunde
                    with db.schreiben(self.con):
                        self.con.execute("UPDATE plan_ereignis SET zeit_utc = '2026-01-01T08:00:00Z' WHERE art = ?", (planer.ENTWURF,))
                themen.bestaetigen(self.con, self.pid, von, self.tid)
                self.assertEqual(self.gruende(self.p3), [])
                self.assertEqual(self.verlauf()[-1], f"TH{self.tid} gilt weiter, 1 Paket wieder frei")

    def test_gilt_weiter_vor_dem_entwurf_zaehlt_nicht(self):
        themen.bestaetigen(self.con, self.pid, "CC1", self.tid)
        self.delta([self.p3])
        self.assertEqual(self.gruende(self.p3), [self.halt])

    def test_nichts_zu_bauen_und_aufgehoben_haelt_wieder(self):
        self.delta([self.p3])
        themen.nichts_zu_bauen(self.con, self.pid, "TL", self.tid, "passt schon")
        self.assertEqual(self.gruende(self.p3), [])
        self.assertEqual(self.verlauf()[-1], f"TH{self.tid}: nichts zu bauen, 1 Paket wieder frei")
        themen.nichts_zu_bauen(self.con, self.pid, "TL", self.tid, None, aufheben=True)
        self.assertEqual(self.gruende(self.p3), [self.halt])

    def test_nichts_zu_bauen_bestaetigt(self):
        themen.nichts_zu_bauen(self.con, self.pid, "TL", self.tid, "passt schon")
        self.delta([self.p3])
        self.assertEqual(self.gruende(self.p3), [self.halt])                                   # der Vermerk lag vor dem Entwurf
        tore.nichts_bestaetigen(self.con, self.pid, "Co", self.tid)
        self.assertEqual(self.gruende(self.p3), [])

    def test_neuer_entwurf_nennt_eins_nicht_mehr(self):
        self.delta([self.p3, self.p])
        self.delta([self.p3], [self.andere])
        self.assertEqual(delta_halt.gehalten(self.con, self.pid), {self.p3: {self.tid}, self.andere: {self.tid}})
        self.assertEqual(self.verlauf()[1:], [f"neuer Entwurf zu TH{self.tid}, 1 Paket wieder frei",
                                              f"1 Paket angehalten bis zur Freigabe der Änderung TH{self.tid}"])
        self.assertEqual(delta_halt.abgleichen(self.con, self.pid), [])
        self.ja()
        self.assertEqual(self.verlauf()[-1], f"Änderung TH{self.tid} freigegeben, 1 Paket wieder frei, 1 verworfen")

    def test_neuer_entwurf_nichts_zu_bauen(self):
        self.delta([self.p3])
        d = planer_delta.kontext(self.con, self.pid, self.tid)
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 2, {"nichts_zu_bauen": True, "grund": "nur Wortlaut"}, delta=d)
        self.assertEqual(self.gruende(self.p3), [])

    def test_gescheiterter_lauf_aendert_nichts(self):
        self.delta([self.p3])
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 2, None, fehler="Zeitüberschreitung")
        self.assertEqual(self.gruende(self.p3), [self.halt])

    def test_zurueckgestellter_entwurf_haelt_weiter(self):
        self.delta([self.p3])
        entwurf_warten.zurueckstellen(self.con, self.pid, kern.ENTWICKLER, self.tid, "erst A2017")
        delta_halt.abgleichen(self.con, self.pid)
        self.assertEqual(self.gruende(self.p3), [self.halt])


class AndereGruende(Grund):
    def test_von_hand_gesetzte_bleiben(self):
        kern.aufgabe_status(self.con, self.pid, "TL", self.p3, "wartet", auf="Co", wartet_auf="Absprache")
        self.delta([self.p3])
        self.assertEqual(self.gruende(self.p3), ["Co", self.halt])
        self.ja()
        self.assertEqual(self.gruende(self.p3), ["Co"])
        self.assertEqual(self.con.execute("SELECT wartet_auf FROM aufgabe WHERE id = ?", (self.p3,)).fetchone()[0], "Absprache")

    def test_zwei_themen_halten_dasselbe_paket(self):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "wartegrund", projekt_id=self.pid, aufgabe_id=self.p3, art="monitor", bezug=delta_halt.bezug(999),
                         angelegt_utc=db.jetzt(), angelegt_von="AMW")
        self.delta([self.p3])
        self.ja()
        self.assertEqual(self.gruende(self.p3), [delta_halt.bezug(999)])

    def test_von_hand_loesen_nur_lead_co_mensch_und_nicht_gleich_wieder(self):
        self.delta([self.p3])
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET agent = 'CC1' WHERE id = ?", (self.p3,))
        with self.assertRaisesRegex(kern.AmwFehler, "geben Lead, Co-Entwickler oder der Mensch frei"):
            kern.aufgabe_status(self.con, self.pid, "CC1", self.p3, "wartet", erledigt=f"Änderung TH{self.tid}")
        kern.aufgabe_status(self.con, self.pid, "TL", self.p3, "wartet", erledigt=f"Änderung TH{self.tid}")
        self.assertEqual((self.gruende(self.p3), delta_halt.abgleichen(self.con, self.pid)), ([], []))
        self.delta([self.p3])                                                                  # ein neuer Entwurf nennt es wieder
        self.assertEqual(self.gruende(self.p3), [self.halt])

    def test_weitergefuehrt_und_dann_von_hand_geloest_bleibt_frei(self):
        self.delta([self.p3])
        self.delta([self.p3])
        self.assertEqual(len(self.verlauf()), 1)                                               # weiter angehalten: keine zweite Zeile
        kern.aufgabe_status(self.con, self.pid, "TL", self.p3, "wartet", erledigt=self.halt)
        delta_halt.abgleichen(self.con, self.pid)
        self.assertEqual(self.gruende(self.p3), [])


class Starten(Grund):
    def setUp(self):
        super().setUp()
        u = mock.patch.dict(os.environ, {"LOCALAPPDATA": os.path.join(self.ordner.name, "lad")})
        u.start()
        self.addCleanup(u.stop)
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, platz_wurzel=os.path.join(self.ordner.name, "plaetze"), plaetze=1)
        planung.bogen_status(self.con, self.pid, "TL", self.m1, "aktiv")

    def test_headless_startet_nicht(self):
        self.assertIn(self.p, [x["id"] for x in waechter.reihenfolge(self.con, self.pid)])
        self.delta([self.p])
        self.assertNotIn(self.p, [x["id"] for x in waechter.reihenfolge(self.con, self.pid)])
        a = waechter.pruefen(self.con, self.pid, self.p, limit=10)
        self.assertEqual((a["ok"], a["regel"], a["warten"]), (False, 15, True))
        self.assertIn(self.halt, a["grund"])
        x = next(x for x in paketliste.daten(self.con, self.pid)["pakete"] if x["id"] == self.p)
        self.assertEqual((x["zustand"], x["grund"]["regel"]), ("startklar", 15))
        self.assertIn(self.halt, x["grund"]["text"])
        self.ja()
        self.assertIn(self.p, [x["id"] for x in waechter.reihenfolge(self.con, self.pid)])
        self.assertNotEqual(waechter.pruefen(self.con, self.pid, self.p, limit=10)["regel"], 15)

    def test_von_hand_startet_es_nur_der_mensch(self):
        self.delta([self.p3, self.andere])
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET agent = 'Co' WHERE id IN (?, ?)", (self.p3, self.andere))
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc1234' WHERE id = ?", (self.p2,))
        for von in ("Co", "TL"):
            with self.assertRaisesRegex(kern.AmwFehler, f"A{self.p3} wartet auf {self.halt}"):
                kern.aufgabe_status(self.con, self.pid, von, self.p3, "start")
        kern.aufgabe_status(self.con, self.pid, kern.ENTWICKLER, self.andere, "start")
        self.assertEqual(self.gruende(self.andere), [])
        delta_halt.abgleichen(self.con, self.pid)
        self.assertEqual(self.gruende(self.andere), [])

    def test_naechster_schritt_und_verteilen_lassen_es_aus(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc1234' WHERE id IN (?, ?)", (self.p2, self.p))
        self.delta([self.p3])
        self.assertEqual((planung.naechster(self.con, self.pid, "CC1") or {}).get("id"), self.andere)
        self.assertEqual([a["id"] for a, _ in verteilen.kandidaten(self.con, self.pid)], [self.andere])

    def test_bindet_den_agenten_nicht(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET agent = 'CC1' WHERE id = ?", (self.p3,))
        self.delta([self.p3])
        self.assertIsNone(wartegrund.haelt_fest(self.con, self.pid, "CC1"))

    def test_startklar_weckruf_nach_dem_loesen(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET agent = 'Co', geaendert_utc = '2026-01-01T08:00:00Z' WHERE id = ?", (self.p3,))
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc1234' WHERE id = ?", (self.p2,))
        self.assertIn(f"Co geweckt: A{self.p3} startklar", wartegrund.startklar_wecken(self.con, self.pid))
        self.delta([self.p3])
        self.assertEqual(wartegrund.startklar_wecken(self.con, self.pid), [])
        with db.schreiben(self.con):                                                           # der erste Weckruf ist lange her
            self.con.execute("UPDATE nachricht SET zeit_utc = '2026-01-01T08:00:00Z' WHERE aufgabe_id = ?", (self.p3,))
            self.con.execute("UPDATE plan_ereignis SET text = ? WHERE art = 'startklar_geweckt'", (f"{self.p3}:2026-01-01T08:00:00Z",))
        self.con.execute("CREATE TEMP TABLE beruehrt (aid INTEGER)")                          # das Lösen fasst die Aufgabe an: neuer Weckruf
        self.con.execute(f"CREATE TEMP TRIGGER zaehlen AFTER UPDATE OF geaendert_utc ON aufgabe WHEN NEW.id = {self.p3}"
                         " BEGIN INSERT INTO beruehrt VALUES (NEW.id); END")
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 2, {"nichts_zu_bauen": True, "grund": "x"},
                                 delta=planer_delta.kontext(self.con, self.pid, self.tid))
        self.assertTrue(self.con.execute("SELECT count(*) FROM beruehrt").fetchone()[0])
        self.assertIn(f"Co geweckt: A{self.p3} startklar", wartegrund.startklar_wecken(self.con, self.pid))


class Anzeige(Grund):
    def test_planung_bietet_angehaltene_nicht_zum_anhalten_an(self):
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "grob")
        themen.pflegen(self.con, self.pid, "CC1", self.tid, "Noch einmal neu.")
        g = lambda: [x for m in planansicht.daten(self.con, self.pid)["meilensteine"] for z in m["geaendert"] for x in z["offen"]]
        self.assertIn(self.andere, g())
        with db.schreiben(self.con):
            db.einfuegen(self.con, "wartegrund", projekt_id=self.pid, aufgabe_id=self.andere, art="monitor", bezug=self.halt,
                         angelegt_utc=db.jetzt(), angelegt_von="AMW")
        self.assertNotIn(self.andere, g())

    def test_befehl_zeigt_den_grund(self):
        self.delta([self.p3])
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus):
            cli.main(["aufgabe", "zeige", str(self.p3), "--projekt", "Produkt", "--von", "TL"])
        self.assertIn(self.halt, aus.getvalue())


class Seite(Rundgang):
    """Der Grund steht auf der Meilenstein-Karte, in der Arbeitsliste und im Paket in der Sprache des Nutzers."""

    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        self.th = 12                                                         # ohne Themen zeigt die Planung die Meilenstein-Karten gleich
        self.m = planung.bogen_neu(self.con, self.pid, "TL", "Anmelden", abnahme="Vorführung")
        self.a = planung.schritt_setzen(self.con, self.pid, "TL", titel="Abmelden oben rechts", bogen_id=self.m, agent="CC1")
        self.b = planung.schritt_setzen(self.con, self.pid, "TL", titel="Passwort vergessen", bogen_id=self.m, agent="CC1")
        planung.bogen_status(self.con, self.pid, "TL", self.m, "aktiv")
        with db.schreiben(self.con):
            for a in (self.a, self.b):
                db.einfuegen(self.con, "wartegrund", projekt_id=self.pid, aufgabe_id=a, art="monitor", bezug=delta_halt.bezug(self.th),
                             angelegt_utc=db.jetzt(), angelegt_von="AMW")

    def test_deutsch_und_englisch(self):
        self.groesse("pc")
        for sprache, grund, karte in (("de", f"das Ja zur Änderung TH{self.th}", "2 warten auf "), ("en", f"the yes to the change of TH{self.th}", "2 waiting for ")):
            with self.subTest(sprache=sprache):
                self.oeffnen("planung", f"document.querySelector('#bogen-{self.m} .mk-lage')")
                self.tab.js(f"sprache = '{sprache}'; void zeige('planung', true)")
                self.warten(f"document.querySelector('#bogen-{self.m}')?.textContent.includes({json.dumps(karte + grund)})")
                self.tab.js("zustand.arbeit.sicht = 'listen'; void zeige('arbeit')")
                self.warten(f"[...document.querySelectorAll('.karte.aufgabe .w')].some(x => x.textContent === {json.dumps('⇢ ' + grund)})")
                self.tab.js(f"aufgabeDialog({self.a})")
                self.warten(f"document.querySelector('.dialog')?.textContent.includes({json.dumps('⇢ ' + grund + ' · AMW')})")
                self.esc()

    def test_bild_der_karte(self):
        self.ueberall("planung", "meilenstein-angehalten", bereit=f"document.querySelector('#bogen-{self.m} .mk-lage')")
