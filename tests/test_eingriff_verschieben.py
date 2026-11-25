"""A2094 (TH164 „Eingriffe“): ein Paket früher oder später schieben – gesperrte Stellen mit Grund, Reihenfolge/Zeitplan/Prognose neu,
Plan-Stand bleibt, Disponent/Verteilen/Weckruf halten sich daran, Verfall nachvollziehbar, Verlauf, Rechte."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import random
import shutil
import tempfile
import unittest
from typing import Any
from unittest import mock

from amw import (aktionen, arbeitsliste, arbeitspaket, cli, db, disponent, kern, paket_schieben, planung, reihenfolge, verlauf_quellen,
                 verteilen, waechter, wartegrund, workbench, zeitplan)
from tests import test_disponent

MENSCH = kern.ENTWICKLER


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad, "LOCALAPPDATA": os.path.join(self.ordner.name, "lad")})
        u.start()
        self.addCleanup(u.stop)
        for k in ("AMW_AGENT", "AMW_PROJEKT"):
            os.environ.pop(k, None)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.fremd = fremd = db.einfuegen(self.con, "projekt", name="Fremd", angelegt_utc=db.jetzt())
            self.pid = db.einfuegen(self.con, "projekt", name="Produkt", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, fremd, "TL", rolle="lead")
        for i in range(3):                                                  # interne und Projektnummer der Meilensteine verschieden
            planung.bogen_neu(self.con, fremd, "TL", f"Fremd {i}")
        for k, r in (("TL", "lead"), ("CC1", None), ("CC2", None)):
            kern.agent_neu(self.con, self.pid, k, rolle=r)
        kern.projekt_einstellen(self.con, self.pid, MENSCH, entwickler_name="Alex")
        self.bid = planung.bogen_neu(self.con, self.pid, "TL", "Lieferung 1")
        planung.bogen_status(self.con, self.pid, "TL", self.bid, "aktiv")

    def paket(self, titel, agent: str | None = "CC1", groesse="M", nach=None, bogen: int | None = 0, **werte):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel, agent)
        planung.schritt_setzen(self.con, self.pid, "TL", aid=aid, bogen_id=self.bid if bogen == 0 else bogen, groesse=groesse, nach=nach, **werte)
        return aid

    def p_paket(self, titel, groesse="M", bogen: int | None = 0):
        aid = self.paket(titel, agent=None, groesse=groesse, bogen=bogen, art="mechanisch")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET pruefbefehl = 'python -m unittest tests.test_x', dateibereich = ? WHERE id = ?", (f"web/{aid}/", aid))
        arbeitspaket.setzen(self.con, self.pid, "TL", aid, art="p")
        arbeitspaket.zustand_setzen(self.con, self.pid, "TL", aid, "startklar")
        return aid

    def reihe(self):
        return [z["aid"] for z in reihenfolge.berechnen(self.con, self.pid)]

    def schieben(self, aid, richtung="frueher", von=MENSCH, grund="Kunde wartet"):
        return paket_schieben.verschieben(self.con, self.pid, von, aid, richtung, grund)

    def geht(self, aid, von=MENSCH):
        return paket_schieben.moeglich(self.con, self.pid, aid, von)

    def enden(self):
        return [(json.loads(r["text"])["art"], r["von"]) for r in self.con.execute("SELECT von, text FROM plan_ereignis WHERE art = ? ORDER BY id",
                                                                                     (paket_schieben.ENDE,))]

    def meldungen(self):
        return [(r["kurz"], r["text"]) for r in self.con.execute("SELECT kurz, text FROM nachricht WHERE kurz LIKE '%gilt nicht mehr%'"
                                                                   " OR kurz LIKE '%gelten nicht mehr%' ORDER BY id")]

    def status(self, aid, status):
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = ?, beleg = 'x' WHERE id = ?", (status, aid))


class Schieben(Grund):
    def test_tauscht_mit_dem_nachbarn_und_rechnet_neu(self):
        a, b, c = self.paket("A", groesse="L"), self.paket("B"), self.paket("C", groesse="S")
        self.assertEqual(self.reihe(), [a, b, c])
        r = self.schieben(c)
        self.assertEqual((self.reihe(), r["mit"], r["vorher"]["platz"], r["nachher"]["platz"]), ([a, c, b], b, 3, 2))
        self.assertLess(r["nachher"]["start_utc"], r["vorher"]["start_utc"])                         # der Zeitplan folgt
        self.assertEqual([x["aid"] for x in zeitplan.berechnen(self.con, self.pid)["pakete"]], [a, c, b])
        self.schieben(c)
        self.assertEqual(self.reihe(), [c, a, b])
        self.schieben(c, "spaeter")
        self.assertEqual(self.reihe(), [a, c, b])                                                   # zurück: der Gegengriff ersetzt
        self.assertEqual(self.enden(), [("ersetzt", MENSCH)])
        z = {x["aid"]: x for x in reihenfolge.berechnen(self.con, self.pid)}
        self.assertIn("von Hand später (Alex: Kunde wartet)", z[c]["grund"])
        self.assertNotIn("hand", z[a])

    def test_uebersteht_neue_und_fertige_pakete(self):
        a, b, c = self.paket("A", groesse="L"), self.paket("B"), self.paket("C", groesse="S")
        self.schieben(c)
        neu = self.paket("Neu", groesse="XL")
        self.assertEqual(self.reihe(), [neu, a, c, b])
        self.status(a, "fertig")
        self.assertEqual(self.reihe(), [neu, c, b])
        self.assertEqual(paket_schieben.abgelaufen(self.con, self.pid), [])                          # gilt weiter
        self.assertEqual([x["id"] for x in arbeitsliste.liste(self.con, self.pid, "CC1")], [neu, c, b])

    def test_plan_stand_bleibt_abweichung_und_prognose_neu(self):
        a, b = self.paket("A", groesse="L"), self.paket("B", groesse="S")
        with db.schreiben(self.con):
            reihenfolge.plan_stand_merken(self.con, self.pid, "TL", self.bid)
        stand = lambda: [tuple(r) for r in self.con.execute("SELECT id, text FROM plan_ereignis WHERE art = ?", (reihenfolge.PLAN_STAND,))]
        vorher, prog = stand(), planung.prognose(self.con, self.pid, laeufe=200)["schritte"]
        with mock.patch("amw.planung.durchsatz", return_value=[1]):                                  # ein Paket je Tag: das zweite endet später
            prog = planung.prognose(self.con, self.pid, laeufe=50)["schritte"]
            r = self.schieben(b)
            neu = planung.prognose(self.con, self.pid, laeufe=50)["schritte"]
        self.assertEqual(stand(), vorher)
        self.assertEqual((neu[b]["p50"], neu[a]["p50"]), (prog[a]["p50"], prog[b]["p50"]))
        self.assertEqual((r["vorher"]["paket_p50"], r["nachher"]["paket_p50"]), (prog[b]["p50"], prog[a]["p50"]))
        self.assertIsNotNone(reihenfolge.abweichung(self.con, self.pid, self.bid))

    def test_gesperrt_mit_grund(self):
        laeuft = self.paket("Läuft", groesse="S", agent="CC2")
        kern.aufgabe_status(self.con, self.pid, "CC2", laeuft, "start")
        a = self.paket("Anfang", groesse="L")
        b = self.paket("Mitte", groesse="M", nach=[a])
        c = self.paket("Ende", groesse="S", nach=[b])
        self.assertEqual(self.reihe(), [laeuft, a, b, c])
        g = {x: self.geht(x) for x in (a, b, c)}
        self.assertEqual(g[a]["frueher"]["grund"], "„Läuft“ läuft schon")                            # nie vor ein laufendes
        self.assertEqual(g[a]["spaeter"]["grund"], "„Mitte“ braucht es")
        self.assertEqual(g[b]["frueher"]["grund"], "braucht „Anfang“")
        self.assertEqual(g[c]["spaeter"]["grund"], "steht schon hinten")
        self.assertEqual((g[b]["frueher"]["art"], g[b]["frueher"]["x"]), ("braucht", "Anfang"))
        self.assertEqual({x["grund"] for x in self.geht(laeuft).values()}, {"läuft schon"})
        with self.assertRaisesRegex(kern.AmwFehler, "früher geht nicht: braucht „Anfang“"):
            self.schieben(b)
        ohne = self.paket("Ohne", bogen=None)
        self.assertEqual(self.geht(ohne)["frueher"]["grund"], "gehört zu keinem Meilenstein")
        self.status(c, "fertig")
        self.assertEqual(self.geht(c)["spaeter"]["grund"], "ist schon fertig")
        with self.assertRaisesRegex(kern.AmwFehler, "gibt es nicht"):
            self.geht(99999)

    def test_mittelbare_abhaengigkeit_ueber_einen_anderen_meilenstein(self):
        b2 = planung.bogen_neu(self.con, self.pid, "TL", "Lieferung 2")
        a = self.paket("A", groesse="L")
        fern = self.paket("Fern", nach=[a], bogen=b2, groesse="S")
        c = self.paket("C", groesse="S", nach=[fern])
        self.assertEqual([x for x in self.reihe() if x in (a, c)], [a, c])
        self.assertEqual(self.geht(c)["frueher"]["grund"], "braucht „A“")

    def test_nicht_ueber_die_grenze_des_meilensteins(self):
        a = self.paket("A")
        b2 = planung.bogen_neu(self.con, self.pid, "TL", "Lieferung 2")
        b = self.paket("B", bogen=b2)
        self.assertEqual(self.reihe(), [a, b])
        self.assertEqual(self.geht(a)["spaeter"]["grund"], "steht schon hinten")
        self.assertEqual(self.geht(b)["frueher"]["grund"], "steht schon vorn")

    def test_abgeschlossen_geparkt_anderes_projekt(self):
        a, b = self.paket("A", groesse="L"), self.paket("B")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET einstufung = 'geparkt' WHERE id = ?", (a,))
        self.assertEqual(self.geht(a)["frueher"]["grund"], "ist zurückgestellt")
        with db.schreiben(self.con):
            self.con.execute("UPDATE bogen SET status = 'fertig' WHERE id = ?", (self.bid,))
        self.assertEqual(self.geht(b)["frueher"]["grund"], "der Meilenstein ist abgeschlossen")
        self.assertEqual(paket_schieben.moeglich_alle(self.con, self.pid), {})
        with self.assertRaisesRegex(kern.AmwFehler, "gibt es nicht"):
            paket_schieben.moeglich(self.con, self.fremd, b)


class Rechte(Grund):
    def test_mensch_und_lead(self):
        a, b = self.paket("A", groesse="L"), self.paket("B")
        for k in ("CC1", "CC2"):
            with self.assertRaisesRegex(kern.AmwFehler, "der Mensch oder der Lead"):
                self.schieben(b, von=k)
        with self.assertRaisesRegex(kern.AmwFehler, "nur mit Grund"):
            self.schieben(b, von="TL", grund=" ")
        self.schieben(b, von=MENSCH, grund="")                                                      # der Mensch darf ohne
        self.assertEqual(self.reihe(), [b, a])
        n = self.con.execute("SELECT n.von, e.agent, n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id"
                             " WHERE n.kurz LIKE 'M1: A%früher%'").fetchone()
        self.assertEqual((n["von"], n["agent"]), (MENSCH, "TL"))                                       # der Lead erfährt es
        self.assertIn(f"A{b} früher – jetzt vor A{a}", n["kurz"])

    def test_mensch_geht_vor_lead(self):
        a, b = self.paket("A", groesse="L"), self.paket("B")
        self.schieben(b, von=MENSCH)
        self.assertEqual(self.geht(a, "TL")["frueher"]["grund"], "von Alex so gesetzt")
        with self.assertRaisesRegex(kern.AmwFehler, "von Alex so gesetzt"):
            self.schieben(a, von="TL")
        with self.assertRaisesRegex(kern.AmwFehler, "von Alex so gesetzt"):
            arbeitsliste.ordnen(self.con, self.pid, "TL", "CC1", [a, b], "eilig")
        with self.assertRaisesRegex(kern.AmwFehler, "von Alex so gesetzt"):
            arbeitsliste.schieben(self.con, self.pid, "TL", a, oben=True, grund="eilig")
        self.assertEqual((self.reihe(), self.enden()), ([b, a], []))
        self.assertTrue(self.geht(a)["frueher"]["geht"])                                            # der Mensch darf
        self.schieben(a, von=MENSCH)
        self.assertEqual((self.reihe(), self.enden()), ([a, b], [("ersetzt", MENSCH)]))

    def test_lead_paar_dreht_der_mensch_um(self):
        a, b = self.paket("A", groesse="L"), self.paket("B")
        self.schieben(b, von="TL")
        self.schieben(a, von=MENSCH)
        self.assertEqual(self.reihe(), [a, b])

    def test_handordnung_der_neueste_gilt(self):
        a, b, c = self.paket("A", groesse="L"), self.paket("B"), self.paket("C", groesse="S")
        ids = lambda: [x["id"] for x in arbeitsliste.liste(self.con, self.pid, "CC1")]
        arbeitsliste.ordnen(self.con, self.pid, "TL", "CC1", [c, a, b], "so will es der Lead")
        self.schieben(b)                                                                             # in der Reihenfolge: b vor a
        self.assertEqual((ids(), self.reihe()), ([c, b, a], [b, a, c]))
        self.assertIsNotNone(arbeitsliste.liste(self.con, self.pid, "CC1")[0]["hand"])              # die übrige Handordnung bleibt
        arbeitsliste.ordnen(self.con, self.pid, MENSCH, "CC1", [a, b, c], "doch anders")             # neuer: der Handgriff endet
        self.assertEqual((ids(), self.reihe(), self.enden()), ([a, b, c], [a, b, c], [("ersetzt", MENSCH)]))

    def test_agenten_ohne_gemeinsame_liste(self):
        a, b = self.paket("A", groesse="L", agent="CC1"), self.paket("B", agent="CC2")
        self.schieben(b)
        self.assertEqual(self.reihe(), [b, a])
        self.assertEqual({r["agent"] for r in self.con.execute("SELECT agent FROM aufgabe WHERE id = ?", (b,))}, {"CC2"})   # tauscht nie Agenten


class Halten(Grund):
    """Disponent, Verteilen, Weckruf und „schritt naechster“ folgen dem Handgriff."""
    def start(self):
        return [x["id"] for x in waechter.reihenfolge(self.con, self.pid)]

    def naechster(self, nehmen=False):
        n = planung.naechster(self.con, self.pid, "CC1", nehmen=nehmen)
        return n["id"] if n else None

    def test_startfolge_headless(self):
        a, b, c = self.p_paket("A", "L"), self.p_paket("B"), self.p_paket("C", "S")
        self.assertEqual(self.start(), [a, b, c])
        self.schieben(c)
        self.schieben(c)
        self.assertEqual(self.start(), [c, a, b])

    def test_runden_des_disponenten(self):
        a, b, c = self.p_paket("A", "L"), self.p_paket("B"), self.p_paket("C", "S")
        kern.projekt_einstellen(self.con, self.pid, MENSCH, platz_wurzel=os.path.join(self.ordner.name, "pl"), plaetze=3)
        kern.projekt_ordner_setzen(self.con, self.pid, self.ordner.name)
        self.schieben(c)
        folge = []

        def starten(con, pid, aid, *_a, **_k):
            folge.append(aid)
            arbeitspaket.zustand_setzen(con, pid, "AMW", aid, "laeuft")
            return f"A{aid} gestartet"
        with mock.patch("amw.disponent.starten", starten), mock.patch("amw.waechter.pruefen", return_value={"ok": True}), \
                mock.patch("amw.waechter.protokollieren"), mock.patch("amw.disponent.wochenbericht", return_value=None):
            disponent.runde(self.con)
            self.assertEqual(paket_schieben.abgelaufen(self.con, self.pid), [])                      # nach der ersten Runde gilt er weiter
            danach = self.start()
            disponent.runde(self.con)
            self.assertEqual(paket_schieben.abgelaufen(self.con, self.pid), [f"A{c} vor A{b}: erfuellt"])
            disponent.runde(self.con)
        self.assertEqual((folge, danach), ([a, c, b], [c, b]))
        self.assertEqual(self.meldungen(), [])                                                       # erfüllt: keine Meldung

    def test_vorderes_nicht_startbar_haelt_nichts_auf(self):
        a, b = self.p_paket("A", "L"), self.p_paket("B")
        self.schieben(b)
        with db.schreiben(self.con):
            wartegrund.anlegen(self.con, self.pid, "TL", b, "Entwickler")
        self.assertEqual(self.reihe()[0], b)                                                         # die Stelle bleibt
        with db.schreiben(self.con):
            self.con.execute("UPDATE paket SET zustand = 'blockiert' WHERE aufgabe_id = ?", (b,))
        self.assertEqual(self.start(), [a])                                                          # das hintere startet

    def test_verteilen(self):
        a, b = self.paket("A", agent=None, groesse="L"), self.paket("B", agent=None)
        ids = lambda: [x["id"] for x, _ in verteilen.kandidaten(self.con, self.pid)]
        self.assertEqual(ids(), [a, b])
        self.schieben(b)
        self.assertEqual(ids(), [b, a])

    def test_weckruf_und_naechster(self):
        a, b, c = (self.paket(t, groesse="M", rang=r) for t, r in (("A", 10), ("B", 20), ("C", 30)))
        frei = lambda: [x["id"] for x in wartegrund.freie_arbeit(self.con, self.pid, "CC1")]
        self.assertEqual((frei(), self.naechster()), ([a, b, c], a))
        self.schieben(b)
        self.assertEqual((frei(), self.naechster()), ([b, a, c], b))
        kern.aufgabe_status(self.con, self.pid, "CC1", c, "start")
        kern.aufgabe_status(self.con, self.pid, "CC1", c, "fertig", beleg="x", zusammenfassung="x")
        n = self.con.execute("SELECT kurz FROM nachricht WHERE kurz LIKE '%weiter in deiner Liste%' ORDER BY id DESC").fetchone()
        self.assertIn(f"weiter in deiner Liste: A{b}", n["kurz"])
        self.assertEqual(self.naechster(nehmen=True), b)

    def test_ohne_handgriff_bekommt_niemand_etwas_anderes(self):
        """Zufallsprobe gegen die alten Abfragen: freie_arbeit und naechster liefern ohne geltenden Handgriff genau dasselbe."""
        z = random.Random(7)
        b2 = planung.bogen_neu(self.con, self.pid, "TL", "Lieferung 2")
        planung.bogen_status(self.con, self.pid, "TL", b2, "aktiv")
        ids = []
        for i in range(14):
            nach = [z.choice(ids)] if ids and z.random() < .3 else None
            ids.append(self.paket(f"P{i}", agent=z.choice(["CC1", "CC2", None]), groesse=z.choice("SML"), rang=z.randint(1, 9) * 10, nach=nach,
                                  bogen=z.choice([self.bid, b2, None])))
        wartegrund_alt = lambda k: [r["id"] for r in self.con.execute(
            "SELECT * FROM aufgabe WHERE projekt_id = ? AND agent = ? AND einstufung = 'aktiv' AND status IN ('wartet', 'laeuft', 'blockiert')"
            " ORDER BY rang, id", (self.pid, k)) if not planung.offene_vorgaenger(self.con, r["id"])]
        naechster_alt = lambda k: next((r["id"] for r in self.con.execute(
            "SELECT a.* FROM aufgabe a LEFT JOIN bogen b ON b.id = a.bogen_id WHERE a.projekt_id = ? AND a.status = 'wartet'"
            " AND a.einstufung IN ('aktiv', 'keine_prio') AND (a.agent = ? OR a.agent IS NULL OR a.agent = '')"
            " AND (b.id IS NULL OR b.status = 'aktiv') ORDER BY (b.id IS NULL), b.nr, (a.agent IS NULL), a.rang, a.id", (self.pid, k))
            if not planung.offene_vorgaenger(self.con, r["id"])), None)

        def gleich():
            for k in ("CC1", "CC2"):
                self.assertEqual([x["id"] for x in wartegrund.freie_arbeit(self.con, self.pid, k)], wartegrund_alt(k))
                n = planung.naechster(self.con, self.pid, k)
                self.assertEqual(n["id"] if n else None, naechster_alt(k))
        gleich()
        geht = [(a, m) for a, m in paket_schieben.moeglich_alle(self.con, self.pid).items() if m["frueher"]["geht"]]
        self.assertTrue(geht)
        aid, m = geht[0]
        self.schieben(aid)
        self.status(m["frueher"]["mit"], "fertig")                                                   # der Handgriff gilt nicht mehr
        gleich()
        self.assertEqual(len(paket_schieben.abgelaufen(self.con, self.pid)), 1)
        gleich()


@unittest.skipUnless(shutil.which("git") and os.name == "nt", "git/Windows fehlt")
class EchterStart(unittest.TestCase):
    """Der echte Weg: zwei Runden des Disponenten mit Arbeitsplätzen, Startern und der Arbeiter-Attrappe."""
    con: Any
    pid: Any
    setUp = test_disponent.Disponent.setUp
    plaetze = test_disponent.Disponent.plaetze
    paket = test_disponent.Disponent.paket
    zustand = test_disponent.Disponent.zustand
    warten = test_disponent.Disponent.warten

    def test_zwei_runden(self):
        self.plaetze(2)
        bid = planung.bogen_neu(self.con, self.pid, "TL", "Lieferung", abnahme="V")
        planung.bogen_status(self.con, self.pid, "TL", bid, "aktiv")
        a, b = self.paket(bogen=bid), self.paket(bereiche="lib2/", bogen=bid)
        self.assertEqual([x["id"] for x in waechter.reihenfolge(self.con, self.pid)], [a, b])
        paket_schieben.verschieben(self.con, self.pid, "TL", b, "frueher", "Messung zuerst")
        aus = disponent.runde(self.con, test_disponent.prog("bauen"))
        self.assertTrue(any(f"A{b} gestartet als Headless 1" in x for x in aus), aus)
        self.assertIn("von Hand früher (TL: Messung zuerst)", (disponent.warum(self.con, self.pid, b) or {})["grund"])
        aus = disponent.runde(self.con, test_disponent.prog("bauen"))
        self.assertTrue(any(f"A{a} gestartet als Headless 2" in x for x in aus), aus)
        for aid in (a, b):
            self.warten(aid, ("merge_reihe", "wartet_interaktiv", "abgebrochen", "unklar", "startklar", "zurueckgestellt"))


class Verfall(Grund):
    def vorbereitet(self):
        a, b = self.paket("A", groesse="L"), self.paket("B")
        self.schieben(b)
        return a, b

    def pruefen(self, art, meldet=True, reihe=None):
        self.assertEqual(paket_schieben.geltende(self.con, self.pid), [])                            # wirkt schon vor der Dienst-Runde nicht mehr
        self.assertEqual([x.rsplit(": ", 1)[1] for x in paket_schieben.abgelaufen(self.con, self.pid)], [art])
        self.assertEqual(paket_schieben.abgelaufen(self.con, self.pid), [])                          # einmal
        self.assertEqual(self.enden(), [(art, "AMW")])
        self.assertEqual(len(self.meldungen()), 1 if meldet else 0)

    def test_erfuellt(self):
        _, b = self.vorbereitet()
        kern.aufgabe_status(self.con, self.pid, "CC1", b, "start")
        self.pruefen("erfuellt", meldet=False)

    def test_ueberholt(self):
        a, _ = self.vorbereitet()
        kern.aufgabe_status(self.con, self.pid, "CC1", a, "start")
        self.pruefen("ueberholt")
        kurz, text = self.meldungen()[0]
        self.assertEqual(kurz, "M1: 1 Verschiebung gilt nicht mehr – die AMW ordnet wieder")
        self.assertIn("„B“ früher (Alex: Kunde wartet) – „A“ hat vorher begonnen", text)

    def test_neue_abhaengigkeit(self):
        a, b = self.vorbereitet()
        planung.abhaengigkeit_setzen(self.con, self.pid, "TL", b, [a])
        self.assertEqual(self.reihe(), [a, b])
        self.pruefen("abhaengigkeit")
        self.assertIn("„B“ braucht jetzt „A“", self.meldungen()[0][1])

    def test_anderer_meilenstein(self):
        _, b = self.vorbereitet()
        b2 = planung.bogen_neu(self.con, self.pid, "TL", "Lieferung 2")
        planung.schritt_setzen(self.con, self.pid, "TL", aid=b, bogen_id=b2)
        self.pruefen("meilenstein")

    def test_beide_in_einen_anderen_meilenstein(self):
        a, b = self.vorbereitet()
        b2 = planung.bogen_neu(self.con, self.pid, "TL", "Lieferung 2")
        for x in (a, b):
            planung.schritt_setzen(self.con, self.pid, "TL", aid=x, bogen_id=b2)
        self.pruefen("meilenstein")

    def test_verworfen_und_geparkt(self):
        a, _ = self.vorbereitet()
        self.status(a, "verworfen")
        self.pruefen("weg")

    def test_geparkt(self):
        a, _ = self.vorbereitet()
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET einstufung = 'geparkt' WHERE id = ?", (a,))
        self.pruefen("weg")

    def test_gebuendelt_je_meilenstein(self):
        a, b, c = self.paket("A", groesse="L"), self.paket("B"), self.paket("C", groesse="S")
        b2 = planung.bogen_neu(self.con, self.pid, "TL", "Lieferung 2")
        d, e = self.paket("D", bogen=b2, groesse="L"), self.paket("E", bogen=b2)
        self.schieben(c)
        self.schieben(c)
        self.schieben(e)
        for x in (c, e):
            self.status(x, "verworfen")
        self.assertEqual(len(paket_schieben.abgelaufen(self.con, self.pid)), 3)
        self.assertEqual([k for k, _ in self.meldungen()], ["M1: 2 Verschiebungen gelten nicht mehr – die AMW ordnet wieder",
                                                              "M2: 1 Verschiebung gilt nicht mehr – die AMW ordnet wieder"])
        self.assertEqual(self.reihe(), [a, b, d])

    def test_dienst_runde_ruft_es(self):
        import inspect
        from amw import dienst
        self.assertIn("paket_schieben.abgelaufen(self.con, pid_)", inspect.getsource(dienst))

    def test_ring_der_mensch_gewinnt(self):
        a, b = self.paket("A", groesse="L"), self.paket("B")
        with db.schreiben(self.con):                                          # zwei widersprüchliche Paare (z. B. aus einer alten Sicherung)
            for von, v, h in ((MENSCH, b, a), ("TL", a, b)):
                db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von=von, art=paket_schieben.ART, aufgabe_id=v,
                             bogen_id=self.bid, text=json.dumps({"vor": v, "nach": h, "richtung": "frueher"}))
        self.assertEqual(self.reihe(), [b, a])
        self.assertEqual(paket_schieben.abgelaufen(self.con, self.pid), [f"A{a} vor A{b}: ring"])


class Anzeige(Grund):
    def verlauf(self):
        return [(e["art"], e["rolle"], e["von"], e["text"]) for e in verlauf_quellen.gesamt(self.con, self.pid, [], lambda e: "umsetzung")
                if e["art"].startswith("schieben")]

    def test_verlauf(self):
        a, b = self.paket("A", groesse="L"), self.paket("B")
        self.schieben(b, von="TL", grund="Messung zuerst")
        self.schieben(b, "spaeter", grund="")
        self.assertEqual(self.verlauf(), [("schieben", "agent", "TL", "M1: „B“ früher, vor „A“ – Messung zuerst"),
                                          ("schieben", "mensch", MENSCH, "M1: „B“ später, hinter „A“")])   # ersetzt: keine eigene Zeile
        kern.aufgabe_status(self.con, self.pid, "CC1", b, "start")
        paket_schieben.abgelaufen(self.con, self.pid)
        self.assertEqual(self.verlauf()[-1], ("schieben_ende", "amw", "AMW", "M1: Verschiebung von „B“ gilt nicht mehr – „B“ hat vorher begonnen"))

    def test_planung_der_seite(self):
        a, b = self.paket("A", groesse="L"), self.paket("B")
        s = workbench.daten_planung(self.con, self.pid)["schieben"]
        self.assertEqual((s[b]["frueher"]["geht"], s[b]["frueher"]["mit"], s[a]["frueher"]["grund"]), (True, a, "steht schon vorn"))

    def test_ein_fehler_steht_im_protokoll_und_die_planung_geht_trotzdem(self):
        self.paket("A")
        with mock.patch("amw.paket_schieben.moeglich_alle", side_effect=ValueError("kaputt")), self.assertLogs("amw.workbench", "WARNING") as log:
            d = workbench.daten_planung(self.con, self.pid)
        self.assertEqual(d["schieben"], {})
        self.assertIn("ValueError: kaputt", log.output[0])
        self.assertTrue(d["boegen"])

    def test_aktion_der_seite_pc_und_online(self):
        a, b = self.paket("A", groesse="L"), self.paket("B")
        for kanal, richtung, reihe in (("seite", "frueher", [b, a]), ("netz", "spaeter", [a, b])):
            r = aktionen.ausfuehren(self.con, self.pid, "/api/plan/schieben", {"aufgabe": b, "richtung": richtung}, kanal)
            self.assertEqual((r["ok"], r["richtung"], self.reihe()), (True, richtung, reihe))
        with self.assertRaisesRegex(aktionen.Ungueltig, "steht schon hinten"):
            aktionen.ausfuehren(self.con, self.pid, "/api/plan/schieben", {"aufgabe": b, "richtung": "spaeter"})
        for d in ({}, {"aufgabe": b}, {"aufgabe": b, "richtung": "hoch"}):
            with self.assertRaises(aktionen.Ungueltig):
                aktionen.ausfuehren(self.con, self.pid, "/api/plan/schieben", d)

    def cli(self, *a):
        with contextlib.redirect_stdout(io.StringIO()) as o, contextlib.redirect_stderr(io.StringIO()) as f:
            rc = cli.main(["--projekt", "Produkt", "--von", "TL", *a])
        return rc, o.getvalue() + f.getvalue()

    def test_befehl(self):
        a, b = self.paket("A", groesse="L"), self.paket("B")
        rc, aus = self.cli("aufgabe", "schieben", str(b))
        self.assertIn(f"früher: geht (tauscht mit A{a})", aus)
        self.assertIn("später: gesperrt – steht schon hinten", aus)
        rc, aus = self.cli("aufgabe", "frueher", str(b))
        self.assertTrue(rc)
        self.assertIn("nur mit Grund", aus)
        rc, aus = self.cli("aufgabe", "frueher", str(b), "--grund", "Messung")
        self.assertIn(f"A{b} früher: Platz 2 → 1", aus)
        self.assertEqual(self.reihe(), [b, a])
        rc, aus = self.cli("aufgabe", "spaeter", str(b), "--grund", "zurück")
        self.assertEqual(self.reihe(), [a, b])


class Zufall(Grund):
    def test_nie_gegen_abhaengigkeit_grenze_oder_laufendes(self):
        for saat in range(4):
            z = random.Random(saat)
            with db.schreiben(self.con):
                self.con.execute("UPDATE aufgabe SET status = 'verworfen', beleg = 'x'")
            b2 = planung.bogen_neu(self.con, self.pid, "TL", f"Zwei {saat}")
            ids, von = [], ("TL", MENSCH)
            for i in range(10):
                nach = z.sample(ids, min(len(ids), z.choice([0, 0, 1, 2])))
                ids.append(self.paket(f"P{i}", agent=z.choice(["CC1", "CC2", None]), groesse=z.choice("SML"), nach=nach or None,
                                      bogen=z.choice([self.bid, self.bid, b2])))
            frei = next(x for x in ids if not planung.offene_vorgaenger(self.con, x))
            self.status(frei, "laeuft")
            getan = 0
            for _ in range(25):
                aid, richtung, wer = z.choice(ids), z.choice(paket_schieben.RICHTUNGEN), z.choice(von)
                vorher = self.reihe()
                m = self.geht(aid, wer)[richtung]
                if not m["geht"]:
                    with self.assertRaises(kern.AmwFehler):
                        self.schieben(aid, richtung, wer)
                    self.assertEqual(self.reihe(), vorher)
                    continue
                with mock.patch("amw.paket_schieben._lage", return_value={}):
                    self.schieben(aid, richtung, wer)
                getan += 1
                neu = self.reihe()
                i, j = vorher.index(aid), vorher.index(m["mit"])
                vorher[i], vorher[j] = vorher[j], vorher[i]
                self.assertEqual(neu, vorher, (saat, aid, richtung))                                # genau dieser Tausch, sonst nichts
                bogen = {r["id"]: r["bogen_id"] for r in self.con.execute("SELECT id, bogen_id FROM aufgabe")}
                for x in neu:
                    for v in planung.offene_vorgaenger(self.con, x):
                        if bogen[v] == bogen[x]:
                            self.assertLess(neu.index(v), neu.index(x))
                gruppe = [bogen[x] for x in neu]
                self.assertEqual([g for i, g in enumerate(gruppe) if not i or gruppe[i - 1] != g], list(dict.fromkeys(gruppe)))
                eigene = [x for x in neu if bogen[x] == bogen[frei]]
                self.assertEqual(eigene[0], frei)                                                    # das laufende bleibt vorn
            self.assertGreater(getan, 3, saat)


if __name__ == "__main__":
    unittest.main()
