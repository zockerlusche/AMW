"""A2143: Daten-Schnittstelle der künftigen Startseite „Leitstand“ (amw/leitstand_daten.py) – nur lesend, gebündelte Abfragen, feste Uhr,
Text in Menschensprache (Nummern nur dazu, nie JSON, keine Meilenstein-Nummern)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

from amw import arbeitspaket as ap, db, kern, leitstand_daten, planung, waechter

JETZT = datetime.datetime(2026, 11, 24, 10, 0, tzinfo=datetime.timezone.utc)
SCHLUESSEL = {"fortschritt", "zuletzt", "jetzt", "als_naechstes", "entscheidungen", "haengt", "zeitplan"}


def um(minuten):
    return (JETZT + datetime.timedelta(minutes=minuten)).strftime("%Y-%m-%dT%H:%M:%SZ")


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        self.pid = self.projekt("Laden", plaetze=1)

    def projekt(self, name, plaetze=0, **einst):
        if plaetze:
            einst.update(platz_wurzel=os.path.join(self.ordner.name, "plaetze"), plaetze=plaetze)
        with db.schreiben(self.con):
            pid = db.einfuegen(self.con, "projekt", name=name, angelegt_utc=db.jetzt(), einstellungen=json.dumps(einst))
        kern.agent_neu(self.con, pid, "TL", rolle="lead")
        for k in ("CC1", "CC2"):
            kern.agent_neu(self.con, pid, k)
        return pid

    def meilenstein(self, titel, pid=None, ziel=None, status="aktiv"):
        bid = planung.bogen_neu(self.con, pid or self.pid, "TL", titel, ziel="Z", abnahme="Vorführung", zieldatum=ziel)
        if status != "geplant":
            planung.bogen_status(self.con, pid or self.pid, "TL", bid, status)
        return bid

    def paket(self, titel, agent=None, pid=None, bogen=None, p=False, nach=None, **spalten):
        """Größe S = 60 Minuten."""
        pid = pid or self.pid
        aid = planung.schritt_setzen(self.con, pid, "TL", titel=titel, groesse="S", art="mechanisch", nach=nach,
                                     **({"agent": agent} if agent else {}), **({"bogen_id": bogen} if bogen else {}))
        if p:
            ap.setzen(self.con, pid, "TL", aid, art="p")
        if spalten:
            self.setzen(aid, **spalten)
        return aid

    def setzen(self, aid, **f):
        with db.schreiben(self.con):
            self.con.execute(f"UPDATE aufgabe SET {', '.join(k + ' = ?' for k in f)} WHERE id = ?", (*f.values(), aid))

    def zustand(self, aid, zustand):
        with db.schreiben(self.con):
            self.con.execute("UPDATE paket SET zustand = ? WHERE aufgabe_id = ?", (zustand, aid))
            self.con.execute("UPDATE aufgabe SET status = ? WHERE id = ?", (ap.spiegel(zustand), aid))

    def fertig(self, titel, minute, **kw):
        return self.paket(titel, status="fertig", fertig_utc=um(minute), beleg="abc1234", **kw)

    def ereignis(self, art, zeit, text, aufgabe=None, pid=None, von="AMW", bogen=None):
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "plan_ereignis", projekt_id=pid or self.pid, zeit_utc=zeit, von=von, art=art, aufgabe_id=aufgabe, bogen_id=bogen,
                                text=text if isinstance(text, str) else json.dumps(text, ensure_ascii=False))

    def version(self, version, minute, aufgaben=None, pid=None):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "release", projekt_id=pid or self.pid, art="version", version=version, zeit_utc=um(minute),
                         titel="intern A99", aufgaben=aufgaben, eingetragen_von="TL")

    def lauf(self, beschreibung, seit, erwartet=None, agent="CC1", pid=None, status="laeuft", aufgabe=None):
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "lauf", projekt_id=pid or self.pid, agent=agent, beschreibung=beschreibung, status=status, angemeldet_utc=um(-seit),
                                start_utc=um(-seit), erwartet_min=erwartet, aufgabe_id=aufgabe)

    def d(self, pid=None):
        return leitstand_daten.daten(self.con, pid or self.pid, jetzt=JETZT)


class Leer(Grund):
    def test_leeres_projekt(self):
        d = self.d()
        self.assertEqual(set(d), SCHLUESSEL)
        self.assertEqual(d["fortschritt"], {"fertig": 0, "gesamt": 0, "prozent": 0, "p50": None, "p85": None, "ziel": None, "verzug_tage": None})
        self.assertEqual([d[k] for k in ("zuletzt", "jetzt", "als_naechstes", "entscheidungen")], [[], [], [], []])

    def test_ohne_jetzt_und_als_json(self):
        self.paket("Anmeldung", "CC1")
        json.dumps(leitstand_daten.daten(self.con, self.pid))

    def test_nur_lesend(self):
        self.paket("Anmeldung", "CC1", bogen=self.meilenstein("Bauen"))
        vorher = self.con.total_changes
        self.d()
        self.assertEqual(self.con.total_changes, vorher)
        self.assertFalse(self.con.in_transaction)


class Fortschritt(Grund):
    def test_ueber_die_aktiven_meilensteine(self):
        a, b = self.meilenstein("Eins", ziel="2026-12-01"), self.meilenstein("Zwei", ziel="2026-12-24")
        c = self.meilenstein("Später", status="geplant", ziel="2027-03-01")
        self.fertig("A", -60, bogen=a)
        self.fertig("B", -50, bogen=b)
        self.paket("C", bogen=b)
        self.paket("weg", bogen=b, status="verworfen", beleg="x")
        self.paket("geplant", bogen=c)
        self.paket("ohne Meilenstein")
        f = self.d()["fortschritt"]
        self.assertEqual((f["fertig"], f["gesamt"], f["prozent"], f["ziel"]), (2, 3, 66, "2026-12-24"))
        self.assertGreaterEqual(f["p85"], f["p50"])

    def test_verzug_je_meilenstein_gegen_sein_ziel(self):
        a, b = self.meilenstein("Eins", ziel="2026-12-01"), self.meilenstein("Zwei", ziel="2026-12-24")
        ohne = self.meilenstein("Ohne Ziel")
        prog = {"schritte": {}, "boegen": {a: {"p50": "2026-12-03", "p85": "2026-12-05"}, b: {"p50": "2026-12-20", "p85": "2026-12-22"},
                                           ohne: {"p50": "2027-06-01", "p85": "2027-07-01"}}}
        with mock.patch("amw.planung.prognose", return_value=prog):
            f = self.d()["fortschritt"]
        self.assertEqual((f["p50"], f["p85"], f["ziel"], f["verzug_tage"]), ("2027-06-01", "2027-07-01", "2026-12-24", 2))
        prog["boegen"][a].update(p50_mit="2026-12-10", p85_mit="2026-12-12")           # Token-Pause zählt mit
        with mock.patch("amw.planung.prognose", return_value=prog):
            self.assertEqual(self.d()["fortschritt"]["verzug_tage"], 9)

    def test_alles_fertig_hundert_prozent_ohne_prognose(self):
        a = self.meilenstein("Eins", ziel="2026-12-01")
        self.fertig("A", -60, bogen=a)
        f = self.d()["fortschritt"]
        self.assertEqual((f["prozent"], f["p50"], f["ziel"], f["verzug_tage"]), (100, None, "2026-12-01", None))


class Zuletzt(Grund):
    def test_reihenfolge_arten_und_wer(self):
        m = self.meilenstein("Bauen")
        a = self.fertig("Anmeldung", -50, agent="CC1", bogen=m)
        b = self.fertig("Texte", -40, bogen=m, p=True)
        c = self.fertig("Pflege", -30, agent="CC2")                                     # ohne Meilenstein
        self.version("1.4.0", -20)
        with db.schreiben(self.con):
            self.con.execute("UPDATE bogen SET status = 'fertig', fertig_utc = ? WHERE id = ?", (um(-10), m))
        self.ereignis("bogen_status", um(-10), "aktiv → fertig", von=kern.ENTWICKLER, bogen=m)
        self.assertEqual([(x["art"], x["titel"], x["nummer"], x["wer"], x["zeit_utc"]) for x in self.d()["zuletzt"]], [
            ("paket", "Anmeldung", f"A{a}", "CC1", um(-50)), ("paket", "Texte", f"A{b}", "Headless", um(-40)),
            ("paket", "Pflege", f"A{c}", "CC2", um(-30)), ("version", "Version 1.4.0", "1.4.0", "AMW", um(-20)),
            ("meilenstein", "Bauen", None, kern.ENTWICKLER, um(-10))])

    def test_mensch_heisst_wie_eingestellt(self):
        pid = self.projekt("Mit Name", entwickler_name="Kim")
        a = self.fertig("Bild", -5, agent="CC1", pid=pid)
        self.ereignis("aufgabe_abschluss", um(-5), "x", a, pid, von=kern.ENTWICKLER)
        self.assertEqual([x["wer"] for x in self.d(pid)["zuletzt"]], ["Kim"])

    def test_nur_die_letzten_zehn_aelteste_zuerst(self):
        m = self.meilenstein("Bauen")
        for i in range(14):                                                              # gemischt mit und ohne Meilenstein, nicht nach Nummer
            self.fertig(f"T{i}", -i, bogen=m if i % 2 else None)
        self.assertEqual([x["titel"] for x in self.d()["zuletzt"]], [f"T{i}" for i in range(9, -1, -1)])

    def test_verworfen_und_wieder_geoeffnet_nicht(self):
        m = self.meilenstein("Bauen")
        self.paket("weg", bogen=m, status="verworfen", fertig_utc=um(-5), beleg="x")
        self.ereignis("bogen_status", um(-9), "aktiv → fertig", von="TL", bogen=m)        # der Meilenstein ist wieder aktiv
        self.assertEqual(self.d()["zuletzt"], [])

    def test_zweimal_abgenommen_steht_einmal(self):
        m = self.meilenstein("Bauen")
        with db.schreiben(self.con):
            self.con.execute("UPDATE bogen SET status = 'fertig' WHERE id = ?", (m,))
        self.ereignis("bogen_status", um(-9), "aktiv → fertig", von="TL", bogen=m)
        self.ereignis("bogen_status", um(-2), "aktiv → fertig", von="TL", bogen=m)
        self.assertEqual([x["zeit_utc"] for x in self.d()["zuletzt"]], [um(-2)])


class Jetzt(Grund):
    def test_fenster_headless_lauf(self):
        a = self.paket("Anmeldung", "CC1", status="laeuft", begonnen_utc=um(-15))
        b = self.paket("Texte", p=True, begonnen_utc=um(-30))
        self.zustand(b, "laeuft")
        l = self.lauf("Kurzsuite", 10, erwartet=40, agent="CC2")
        self.lauf("wartet noch", 10, status="angemeldet")
        self.assertEqual(self.d()["jetzt"], [
            {"art": "fenster", "wer": "CC1", "titel": "Anmeldung", "nummer": f"A{a}", "seit_utc": um(-15), "erwartet_min": 60, "ueber": False, "anteil": 0.25},
            {"art": "headless", "wer": "Headless", "titel": "Texte", "nummer": f"A{b}", "seit_utc": um(-30), "erwartet_min": 60, "ueber": False, "anteil": 0.5},
            {"art": "lauf", "wer": "CC2", "titel": "Kurzsuite", "nummer": f"L{l}", "seit_utc": um(-10), "erwartet_min": 40, "ueber": False, "anteil": 0.25}])

    def test_ueber_der_zeit(self):
        self.paket("Anmeldung", "CC1", status="laeuft", begonnen_utc=um(-90))
        b = self.paket("Texte", p=True, begonnen_utc=um(-61))
        self.zustand(b, "laeuft")
        self.lauf("Kurzsuite", 41, erwartet=40)
        self.lauf("ohne Erwartung", 500)
        self.assertEqual([(x["titel"], x["ueber"], x["anteil"]) for x in self.d()["jetzt"]],
                         [("Anmeldung", True, 1.0), ("Texte", True, 1.0), ("Kurzsuite", True, 1.0), ("ohne Erwartung", False, 0.0)])

    def test_genau_in_der_zeit_ist_nicht_darueber(self):
        self.paket("Anmeldung", "CC1", status="laeuft", begonnen_utc=um(-60))
        x = self.d()["jetzt"][0]
        self.assertEqual((x["ueber"], x["anteil"]), (False, 1.0))

    def test_headless_in_der_abnahme_belegt_noch_bereit_zum_merge_nicht(self):
        a, b = self.paket("In der Abnahme", p=True, begonnen_utc=um(-20)), self.paket("Bereit", p=True, begonnen_utc=um(-50))
        self.zustand(a, "abnahme")
        self.zustand(b, "merge_reihe")
        d = self.d()
        self.assertEqual([x["titel"] for x in d["jetzt"]], ["In der Abnahme"])
        self.assertEqual(d["als_naechstes"], [])                                        # beide haben schon angefangen

    def test_neuer_start_zaehlt_ab_dem_neuen_start(self):
        a = self.paket("Texte", p=True, begonnen_utc=um(-3000))
        self.zustand(a, "laeuft")
        self.ereignis("headless_start", um(-3000), {"aufgabe": a}, a)
        self.ereignis("headless_start", um(-6), {"aufgabe": a}, a)
        x = self.d()["jetzt"][0]
        self.assertEqual((x["seit_utc"], x["ueber"], x["anteil"]), (um(-6), False, 0.1))

    def test_je_agent_eins_und_der_mensch_nicht(self):
        self.paket("Erstes", "CC1", status="laeuft", begonnen_utc=um(-5), rang=1)
        self.paket("Zweites", "CC1", status="laeuft", begonnen_utc=um(-9), rang=2)
        self.paket("Ansehen", kern.ENTWICKLER, status="laeuft", begonnen_utc=um(-9))
        self.assertEqual([x["titel"] for x in self.d()["jetzt"]], ["Erstes"])


class AlsNaechstes(Grund):
    def test_gleiche_startminute_eine_gruppe(self):
        m = self.meilenstein("Bauen")                                                  # A2006: nur aktive Meilensteine kommen als Nächstes
        self.paket("läuft", "CC1", status="laeuft", begonnen_utc=um(-30), bogen=m)
        b = self.paket("danach bei CC1", "CC1", bogen=m)
        c = self.paket("Headless jetzt", p=True, bogen=m)
        e = self.paket("CC2 jetzt", "CC2", bogen=m)
        f = self.paket("Frei", nach=[c], bogen=m)
        g = self.d()["als_naechstes"]
        self.assertEqual([(x["start_utc"], sorted(p["nummer"] for p in x["pakete"])) for x in g],
                         [(um(0), sorted([f"A{c}", f"A{e}"])), (um(30), [f"A{b}"]), (um(60), [f"A{f}"])])
        je = {p["titel"]: p for x in g for p in x["pakete"]}
        self.assertEqual(je["Headless jetzt"], {"titel": "Headless jetzt", "nummer": f"A{c}", "wer": "Headless", "dauer_min": 60, "wartet_auf": None,
                                             "wartet_mensch": False, "wartet_grund": None})
        self.assertEqual((je["CC2 jetzt"]["wer"], je["Frei"]["wer"]), ("CC2", None))

    def test_hoechstens_acht_gruppen(self):
        m = self.meilenstein("Bauen")
        for i in range(11):
            self.paket(f"T{i}", "CC1", bogen=m)
        g = self.d()["als_naechstes"]
        self.assertEqual([x["start_utc"] for x in g], [um(60 * i) for i in range(8)])

    def test_wartet_auf_aus_dem_zeitplan(self):
        a = self.paket("Hinter dem Prüfpunkt", "CC1", bogen=self.meilenstein("Bauen"))
        with mock.patch("amw.zwischenpruefung.dahinter", return_value={a: 1}):
            self.assertEqual(self.d()["als_naechstes"][0]["pakete"][0]["wartet_auf"], kern.ENTWICKLER)


class Entscheidungen(Grund):
    def test_nur_das_eigene_projekt_als_satz(self):
        """A2006 (Lead #34119): je Projekt nur seine Entscheidungen – über alle Projekte zeigt die Gesamtsicht (A2014)."""
        q = self.projekt("Schule")
        a, b, c = self.paket("Anmeldung"), self.paket("Texte", pid=q), self.paket("Kasse")
        self.ereignis("headless_start", um(-30), {"aufgabe": a, "platz": 1, "grund": "Platz 1", "von": "AMW"}, a)
        self.ereignis("verteilt", um(-20), {"aufgabe": b, "agent": "CC2", "grund": "Rang 5"}, b, q)
        self.ereignis("waechter", um(-10), f"A{c} nicht gestartet, Regel 4: alle Arbeitsplätze belegt – 1 von 1 belegt", c)
        zeilen = lambda pid: [(x["zeit_utc"], x["projekt"], x["text"], x["nummer"]) for x in self.d(pid)["entscheidungen"]]
        self.assertEqual(zeilen(self.pid), [(um(-10), "Laden", "Laden: „Kasse“ nicht gestartet – belegt", f"A{c}"),
                                            (um(-30), "Laden", "Laden: „Anmeldung“ als Headless gestartet", f"A{a}")])
        self.assertEqual(zeilen(q), [(um(-20), "Schule", "Schule: „Texte“ an CC2 verteilt", f"A{b}")])

    def test_nur_die_letzten_zehn_neueste_zuerst(self):
        a = self.paket("Anmeldung")
        for i in range(13):
            self.ereignis("verteilt", um(-100 + i), {"agent": f"CC{i}"}, a)
        self.assertEqual([x["text"] for x in self.d()["entscheidungen"]], [f"Laden: „Anmeldung“ an CC{i} verteilt" for i in range(12, 2, -1)])

    def test_darf_starten_und_anderes_zaehlt_nicht(self):
        a = self.paket("Anmeldung")
        self.ereignis("waechter", um(-5), f"A{a} darf starten – Wochenlimit unbekannt – Start erlaubt", a)
        self.ereignis("verteil_vorschlag", um(-4), f"CC1:{a}", a)
        self.assertEqual(self.d()["entscheidungen"], [])

    def test_von_hand_kaputtes_json_und_ohne_paket(self):
        a = self.paket("Anmeldung")
        self.ereignis("headless_start", um(-5), {"aufgabe": a, "von": "TL"}, a)
        self.ereignis("verteilt", um(-4), "{kaputt", a)
        self.ereignis("waechter", um(-3), "A9 nicht gestartet, Regel 99: {\"x\": 1}")
        self.assertEqual([x["text"] for x in self.d()["entscheidungen"]],
                         ["Laden: ein Paket nicht gestartet – gesperrt", "Laden: „Anmeldung“ verteilt", "Laden: „Anmeldung“ von Hand als Headless gestartet"])
        self.assertIsNone(self.d()["entscheidungen"][0]["nummer"])

    def test_je_regel_ein_wort(self):
        self.assertEqual(set(leitstand_daten.WARUM), set(waechter.REGELN))
        for wort in leitstand_daten.WARUM.values():
            self.assertRegex(wort, r"^[^\W\d_]+$")


class Getrennt(Grund):
    def test_ein_fremdes_projekt_kommt_nirgends_vor(self):
        q = self.projekt("Schule", plaetze=1)
        m = self.meilenstein("Fremder Meilenstein", pid=q, ziel="2026-12-01")
        self.fertig("Fremd fertig", -9, pid=q, bogen=m)
        self.fertig("Fremd ohne Meilenstein", -8, pid=q)
        self.paket("Fremd wartet", "CC1", pid=q, bogen=m)
        self.paket("Fremd läuft", "CC2", pid=q, status="laeuft", begonnen_utc=um(-5))
        self.zustand(self.paket("Fremd Headless", pid=q, p=True, begonnen_utc=um(-5)), "laeuft")
        self.version("9.9.9", -7, pid=q)
        self.lauf("Fremder Lauf", 3, pid=q)
        d = self.d()
        self.assertEqual(d["fortschritt"]["gesamt"], 0)
        self.assertEqual([d[k] for k in ("zuletzt", "jetzt", "als_naechstes", "entscheidungen")], [[], [], [], []])   # A2006: auch keine Entscheidungen
        fremd = self.d(q)
        self.assertEqual((len(fremd["zuletzt"]), len(fremd["jetzt"]), len(fremd["als_naechstes"])), (3, 3, 1))


class Sprache(Grund):
    def test_keine_meilenstein_nummern_kein_platz_kein_json(self):
        m = self.meilenstein("Bauen", ziel="2026-12-01")
        self.fertig("Anmeldung", -50, agent="CC1", bogen=m)
        a = self.paket("Texte", p=True, bogen=m, begonnen_utc=um(-5))
        self.zustand(a, "laeuft")
        self.ereignis("headless_start", um(-5), {"aufgabe": a, "platz": 1, "grund": "Platz 1 in der Reihenfolge"}, a)
        self.ereignis("waechter", um(-4), f"A{a} nicht gestartet, Regel 4: alle Arbeitsplätze belegt", a)
        self.paket("Danach", p=True, bogen=m)
        self.setzen(self.paket("Plakat", "CC2", bogen=m), status="wartet", wartet_auf="Freigabe der Druckerei", angelegt_utc=um(-2000))  # A2149
        fertig = self.meilenstein("Planen")
        with db.schreiben(self.con):
            self.con.execute("UPDATE bogen SET status = 'fertig' WHERE id = ?", (fertig,))
        self.ereignis("bogen_status", um(-2), "aktiv → fertig", von="TL", bogen=fertig)
        d = self.d()
        self.assertTrue(all(d[k] for k in SCHLUESSEL))

        def texte(x):
            if isinstance(x, dict):
                return [t for k, v in x.items() if k != "nummer" for t in texte(v)]
            return [t for v in x for t in texte(v)] if isinstance(x, list) else [x] if isinstance(x, str) else []
        for t in texte(d):
            self.assertNotRegex(t, r"\bM\d|\bA\d|[Pp]latz|[{}]|Regel")


class Leistung(Grund):
    def fuellen(self, n):
        """n offene und n fertige Pakete in einem Meilenstein, dazu Entscheidungen, Läufe und laufende Pakete im selben Verhältnis."""
        m = self.meilenstein("Bauen", ziel="2026-12-01")
        with db.schreiben(self.con):
            for i in range(n):
                gemeinsam = dict(projekt_id=self.pid, angelegt_von="TL", angelegt_utc=um(-900), bogen_id=m if i % 3 else None, groesse="S", art="mechanisch")
                a = db.einfuegen(self.con, "aufgabe", titel=f"offen {i}", agent=None if i % 4 == 0 else f"CC{1 + i % 2}", **gemeinsam)
                b = db.einfuegen(self.con, "aufgabe", titel=f"fertig {i}", agent="CC1", status="fertig", fertig_utc=um(-i), beleg="abc1234", **gemeinsam)
                if i % 4 == 0:
                    db.einfuegen(self.con, "paket", aufgabe_id=a, art="p", zustand="laeuft" if i == 0 else "startklar", geaendert_utc=um(-1))
                    self.con.execute("UPDATE aufgabe SET status = ? WHERE id = ?", ("laeuft" if i == 0 else "wartet", a))
                db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=um(-i), von="AMW", art="headless_start", aufgabe_id=b, text="{}")
                if i % 5 == 0:
                    db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="CC1", beschreibung="x", status="laeuft", angemeldet_utc=um(-5), start_utc=um(-5))
                    db.einfuegen(self.con, "release", projekt_id=self.pid, art="version", version=f"1.{i}", zeit_utc=um(-i), titel="x", aufgaben=f"A{b}",
                                 eingetragen_von="TL")

    def zaehlen(self):
        """(SQL-Befehle, die leitstand_daten selbst absetzt; alle) – wer den Befehl absetzt, steht im Aufruf darüber."""
        eigene, alle = [], []
        datei, dbdatei = (os.path.normcase(os.path.abspath(str(m.__file__))) for m in (leitstand_daten, db))

        def spur(sql):
            alle.append(sql)
            f = sys._getframe(1)
            while f is not None and os.path.normcase(os.path.abspath(f.f_code.co_filename)) == dbdatei:
                f = f.f_back                                   # A2144: execute() der Verbindung steht in db.py, gemeint ist sein Aufrufer
            if f is not None and os.path.normcase(os.path.abspath(f.f_code.co_filename)) == datei:
                eigene.append(sql)
        self.con.set_trace_callback(spur)
        try:
            d = self.d()
        finally:
            self.con.set_trace_callback(None)
        return d, eigene, alle

    def test_hoechstens_zwoelf_und_gleich_viele_bei_20_und_400(self):
        self.fuellen(20)
        _, klein, alle_klein = self.zaehlen()
        self.fuellen(380)
        d, gross, alle_gross = self.zaehlen()
        self.assertEqual((len(d["zuletzt"]), len(d["als_naechstes"]), len(d["entscheidungen"])), (10, 8, 10))
        self.assertGreater(len(klein), 3)                                               # die Zählung greift wirklich
        self.assertGreater(len(alle_gross), len(alle_klein))                            # die aufgerufenen Funktionen zählen nicht mit
        self.assertLessEqual(len(gross), 12)
        self.assertEqual(len(klein), len(gross))


if __name__ == "__main__":
    unittest.main()
