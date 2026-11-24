"""A2031 (TH164 F2 Schritt 3): rollende Feinplanung – die AMW stößt die Feinplanung des nächsten Meilensteins selbst an
(nach dem Grobplan für den ersten; sonst sobald der laufende bereit zur Abnahme ist oder sein letztes Paket läuft), einmal je
Meilenstein; „Plan freigeben und starten“ ist ein Klick und geht auch, während der vorige auf seine Abnahme wartet."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import aktionen, arbeitspaket, db, feinplanung, fertigquelle, kern, planansicht, planung, themen

MENSCH = {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}


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
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid, "Co")
        kern.projekt_einstellen(self.con, self.pid, "TL", co_entwickler="Co")
        self.m1 = planung.bogen_neu(self.con, self.pid, "TL", "Anmelden", abnahme="Vorführung beim Menschen")
        self.m2 = planung.bogen_neu(self.con, self.pid, "TL", "Sicherung", abnahme="Bericht")
        self.m3 = planung.bogen_neu(self.con, self.pid, "TL", "Online", abnahme="Vorführung")
        self.th = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        self.a1 = self.paket("SSO bauen", self.m1, agent="CC1", groesse="M", art="sicherheit")
        self.a2 = self.paket("Tests", self.m1, nach=[self.a1], pruefbefehl="python -m unittest tests.test_x", dateibereich="tests/test_x.py")
        arbeitspaket.setzen(self.con, self.pid, "TL", self.a2, art="p", modell="sonnet")
        self.angestossen = []
        a = mock.patch.object(feinplanung, "ANSTOSSEN", side_effect=lambda _con, _pid, boegen, grund: self.angestossen.append((boegen[0]["id"], grund)))
        a.start()
        self.addCleanup(a.stop)

    def paket(self, titel, bid, **felder):
        """Ein voll geplantes Paket (TH165: Ziel, Thema, Fertig-Quelle) – startklar zu planen."""
        aid = planung.schritt_setzen(self.con, self.pid, "TL", titel=titel, bogen_id=bid, auftrag=f"{titel}.", **felder)
        themen.verweise_setzen(self.con, self.pid, "TL", aid, [f"TH{self.th}"])
        fertigquelle.setzen(self.con, self.pid, "TL", aid, "commit")
        return aid

    def grob_alle(self):
        for m in (self.m1, self.m2, self.m3):
            planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, m, "grob")

    def status(self, aid, st):
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = ?, beleg = ? WHERE id = ?", (st, "abc1234" if st == "fertig" else None, aid))

    def bogen(self, bid):
        return self.con.execute("SELECT status FROM bogen WHERE id = ?", (bid,)).fetchone()[0]

    def faellig(self):
        return [r[0] for r in self.con.execute("SELECT bogen_id FROM plan_ereignis WHERE art = ? ORDER BY id", (feinplanung.FAELLIG,))]


class Ausloeser(Grund):
    def test_erst_nach_dem_grobplan_und_nur_der_naechste(self):
        self.assertEqual(feinplanung.projekt(self.con, self.pid), [])                         # Grobplan noch offen
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "grob")
        self.assertEqual(feinplanung.projekt(self.con, self.pid), [])                         # erst wenn alle frei sind
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m2, "grob")
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m3, "grob")
        self.assertEqual(feinplanung.projekt(self.con, self.pid), [])                         # M1 hat Pakete, sein Plan wartet aufs Ja
        self.assertEqual(self.angestossen, [])

    def test_erster_meilenstein_ohne_pakete(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET bogen_id = NULL WHERE bogen_id = ?", (self.m1,))
        self.grob_alle()
        self.assertEqual(feinplanung.projekt(self.con, self.pid), [(self.m1, "erster")])
        self.assertEqual(self.angestossen, [(self.m1, feinplanung.GRUND["erster"])])
        self.assertEqual(feinplanung.projekt(self.con, self.pid), [])                         # einmal je Meilenstein
        self.assertEqual(self.faellig(), [self.m1])

    def test_waehrend_der_laufende_arbeit_hat_nichts(self):
        self.grob_alle()
        feinplanung.plan_starten(self.con, self.pid, kern.ENTWICKLER, self.m1)
        self.status(self.a1, "laeuft")                                                         # a2 wartet noch auf a1
        self.assertIsNone(feinplanung.anlass(self.con, self.pid))
        self.assertEqual(feinplanung.projekt(self.con, self.pid), [])

    def test_letztes_paket_laeuft(self):
        self.grob_alle()
        feinplanung.plan_starten(self.con, self.pid, kern.ENTWICKLER, self.m1)
        self.status(self.a1, "fertig")
        self.status(self.a2, "laeuft")
        self.assertEqual(feinplanung.projekt(self.con, self.pid), [(self.m2, "letztes")])
        self.assertEqual(self.angestossen, [(self.m2, feinplanung.GRUND["letztes"])])
        self.assertEqual(feinplanung.projekt(self.con, self.pid), [])
        self.assertEqual(self.faellig(), [self.m2])                                            # M3 erst nach M2

    def test_bereit_zur_abnahme(self):
        self.grob_alle()
        feinplanung.plan_starten(self.con, self.pid, kern.ENTWICKLER, self.m1)
        self.status(self.a1, "fertig")
        self.status(self.a2, "fertig")
        self.assertEqual(feinplanung.projekt(self.con, self.pid), [(self.m2, "bereit")])

    def test_abschaltbar(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", plan_automatik="aus")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET bogen_id = NULL WHERE bogen_id = ?", (self.m1,))
        self.grob_alle()
        self.assertEqual(feinplanung.projekt(self.con, self.pid), [])

    def test_ohne_attrappe_bekommt_der_lead_den_auftrag(self):
        mock.patch.stopall()
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET bogen_id = NULL WHERE bogen_id = ?", (self.m1,))
        self.grob_alle()
        feinplanung.runde(self.con)
        n = self.con.execute("SELECT n.art, n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = 'TL'"
                             " AND n.von = 'AMW' AND n.kurz LIKE '%fein planen'").fetchall()
        self.assertEqual([tuple(x) for x in n], [("auftrag", "Meilenstein 1 „Anmelden“ jetzt fein planen")])


class PlanStarten(Grund):
    def test_ein_klick_startet(self):
        self.grob_alle()
        r = feinplanung.plan_starten(self.con, self.pid, kern.ENTWICKLER, self.m1)
        self.assertTrue(r["frei"])
        self.assertEqual(self.bogen(self.m1), "aktiv")
        self.assertEqual(r["gestartet"]["startklar"], [self.a1, self.a2])
        self.assertEqual(arbeitspaket.lesen(self.con, self.a2)["zustand"], "startklar")       # p-Paket geht an den Disponenten

    def test_naechster_startet_waehrend_der_vorige_auf_die_abnahme_wartet(self):
        a3 = self.paket("Sichern", self.m2, agent="CC1", groesse="S", art="text")
        self.grob_alle()
        feinplanung.plan_starten(self.con, self.pid, kern.ENTWICKLER, self.m1)
        self.status(self.a1, "fertig")
        self.status(self.a2, "fertig")
        r = feinplanung.plan_starten(self.con, self.pid, kern.ENTWICKLER, self.m2)
        self.assertEqual((self.bogen(self.m1), self.bogen(self.m2)), ("aktiv", "aktiv"))       # M1 wartet aufs Urteil, M2 läuft
        self.assertEqual(r["gestartet"]["startklar"], [a3])

    def test_co_und_lead_erst_mit_dem_zweiten_ja(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", grobplan_freigabe="co+lead", feinplan_freigabe="co+lead")   # A2032: je Art
        planansicht.freigeben(self.con, self.pid, "Co", self.m1, "grob")
        planansicht.freigeben(self.con, self.pid, "TL", self.m1, "grob")
        r = feinplanung.plan_starten(self.con, self.pid, "Co", self.m1)
        self.assertFalse(r["frei"])
        self.assertEqual(self.bogen(self.m1), "geplant")
        r = feinplanung.plan_starten(self.con, self.pid, "TL", self.m1)
        self.assertTrue(r["frei"])
        self.assertEqual(self.bogen(self.m1), "aktiv")

    def test_workbench_und_befehl(self):
        a3 = self.paket("Sichern", self.m2, agent="CC1", groesse="S", art="text")
        self.grob_alle()
        r = aktionen.ausfuehren(self.con, self.pid, "/api/meilenstein/plan-starten", {"bogen": self.m1}, kanal="seite")
        self.assertEqual((r["frei"], self.bogen(self.m1)), (True, "aktiv"))
        from amw import cli
        aus = io.StringIO()
        with mock.patch.dict(os.environ, MENSCH), contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "P", "bogen", "freigeben", str(self.m2), "--art", "plan", "--starten", "--von", "Entwickler"])
        self.assertEqual(rc, 0, aus.getvalue())
        self.assertIn("gestartet, 1 Pakete startklar", aus.getvalue())
        self.assertEqual(self.bogen(self.m2), "aktiv")
        self.assertTrue(a3)
        with mock.patch.dict(os.environ, MENSCH), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "P", "bogen", "freigeben", str(self.m3), "--art", "grob", "--starten", "--von", "Entwickler"])
        self.assertNotEqual(rc, 0)
        self.assertIn("--starten gibt es nur mit --art plan", aus.getvalue())


class Feinplaner(unittest.TestCase):
    """Der Feinplaner-Lauf: anstoßen (Attrappe), Entwurf prüfen, Pakete anlegen, neue Fassung, gleichzeitige Meilensteine."""
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        u.start()
        self.addCleanup(u.stop)
        os.environ.pop("AMW_PLANER_AUS", None)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
            from amw import schalter
            schalter._setzen(self.con, self.pid, "an")
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.t1 = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        self.t2 = themen.neu(self.con, self.pid, "TL", "Sicherung", pfleger="CC1")
        self.t3 = themen.neu(self.con, self.pid, "TL", "Hilfe", pfleger="CC1")
        self.m1 = planung.bogen_neu(self.con, self.pid, "TL", "Anmelden", ziel=f"TH{self.t1} Anmeldung mit Firmenkonto",
                                    abnahme="Vorführung")
        self.m2 = planung.bogen_neu(self.con, self.pid, "TL", "Sichern", ziel=f"TH{self.t2} Sicherung", abnahme="Bericht")
        self.m3 = planung.bogen_neu(self.con, self.pid, "TL", "Hilfe", ziel=f"TH{self.t3} Hilfe", abnahme="Bericht")
        self.gestartet = []
        p = mock.patch.object(feinplanung, "STARTER", lambda _pid, boegen, fassung: self.gestartet.append((boegen, fassung)) or 4711)
        p.start()
        self.addCleanup(p.stop)

    def plan(self, m="M1", th=None, **mehr):
        th = th or f"TH{self.t1}"
        return {"pakete": [{"schluessel": "P1", "meilenstein": m, "thema": th, "titel": "Login-Seite bauen", "auftrag": "Seite mit Firmenkonto.",
                            "groesse": "M", "art": "oberflaeche", "ausfuehrung": "agent", "fertig_quelle": "commit",
                            "interaktiv_grund": "Oberfläche"},
                           {"schluessel": "P2", "meilenstein": m, "thema": th, "titel": "Tests für die Anmeldung", "auftrag": "Tests.",
                            "groesse": "S", "art": "mechanisch", "ausfuehrung": "p", "fertig_quelle": "commit", "nach": ["P1"],
                            "abnahme_befehl": "python -m unittest tests.test_anmeldung", "bereiche": "tests/test_anmeldung.py",
                            "pakettyp": "test-schreiben"}], "grund": "erst die Seite, dann die Tests", **mehr}

    def post(self, an="TL"):
        return [(r["art"], r["kurz"]) for r in self.con.execute(
            "SELECT n.art, n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? AND n.von = 'AMW' ORDER BY n.id", (an,))]

    def pakete(self, bid, status=None):
        sql = "SELECT id, titel, status FROM aufgabe WHERE bogen_id = ?" + (" AND status = ?" if status else "") + " ORDER BY id"
        return [tuple(r) for r in self.con.execute(sql, (bid, status) if status else (bid,))]

    def test_sperrliste_beim_planer(self):
        """A2067: der Planer bekommt die gesperrten Bereiche (feste Liste, Testdateien, Muster des Projekts) und die Regel."""
        kern.projekt_einstellen(self.con, self.pid, "TL", sperrmuster="*.cmd")
        ordner = os.path.join(self.ordner.name, "plan")
        os.makedirs(ordner)
        dateien = feinplanung._dateien(self.con, self.pid, feinplanung._zeilen(self.con, self.pid, [self.m1]), None, ordner)
        self.assertIn("sperrliste.md", dateien)
        text = open(os.path.join(ordner, "sperrliste.md"), encoding="utf-8").read()
        for teil in ("`tests/*`", "test-schreiben", "`.claude/*`", "`*.cmd`", "interaktiv_grund"):
            self.assertIn(teil, text)
        self.assertIn("sperrliste.md", feinplanung.AUFTRAG)

    def test_eine_nachbesserung_dann_erst_der_mensch(self):
        """A2067: passt die erste Antwort nicht, geht der Fund einmal an den Planer zurück; Gegenprobe: passt sie, kein zweiter Lauf."""
        schlecht = self.plan()
        schlecht["pakete"][1]["pakettyp"] = None                                                  # p-Paket mit tests/… ohne Testtyp
        laeufe, hinweise = [], []

        def planen(con, pid, zeilen, hinweis, modell, prog=None, zusatz=None):
            laeufe.append(1)
            hinweise.append(hinweis)
            return {"ergebnis": json.dumps(schlecht if len(laeufe) == 1 else self.plan()), "usd": 0.4, "fehler": None}
        meldungen = []
        with mock.patch.object(feinplanung, "planen", planen):
            aus = feinplanung.planen_mit_nachbesserung(self.con, self.pid, [self.m1], feinplanung._zeilen(self.con, self.pid, [self.m1]),
                                                       "erst die Seite", "sonnet", melden=meldungen.append)
        self.assertEqual(len(laeufe), 2)
        self.assertIn("passte nicht", hinweise[1])
        self.assertIn("erst die Seite", hinweise[1])
        self.assertEqual(aus["usd"], 0.8)                                                         # beide Läufe zählen
        self.assertTrue(aus["nachgebessert"])
        self.assertEqual(len(meldungen), 1)
        feinplanung.pruefen(aus["ergebnis"], self.con, self.pid, [self.m1])                       # die zweite passt
        laeufe.clear()
        with mock.patch.object(feinplanung, "planen", lambda *a, **k: (laeufe.append(1), {"ergebnis": json.dumps(self.plan()), "usd": 0.4,
                                                                                         "fehler": None})[1]):
            aus = feinplanung.planen_mit_nachbesserung(self.con, self.pid, [self.m1], feinplanung._zeilen(self.con, self.pid, [self.m1]),
                                                       None, "sonnet")
        self.assertEqual((len(laeufe), aus.get("nachgebessert")), (1, None))

    def test_anstossen_einmal_und_tagesgrenze(self):
        r = feinplanung.anstossen(self.con, self.pid, [self.m1], hinweis="erst die Seite")
        self.assertTrue(r["gestartet"], r)
        self.assertEqual(self.gestartet, [([self.m1], 1)])
        self.assertFalse(feinplanung.anstossen(self.con, self.pid, [self.m1])["gestartet"])     # läuft schon
        an = feinplanung._ereignisse(self.con, self.pid, feinplanung.ANGESTOSSEN)
        self.assertEqual((an[-1]["hinweis"], an[-1]["prozess"]), ("erst die Seite", 4711))
        kern.projekt_einstellen(self.con, self.pid, "TL", planer_tagesgrenze_usd="0.5")
        feinplanung.entwurf_eintragen(self.con, self.pid, [self.m1], 1, None, usd=0.7, fehler="Zeitüberschreitung")
        r = feinplanung.anstossen(self.con, self.pid, [self.m1])
        self.assertFalse(r["gestartet"])
        self.assertIn("Tagesgrenze", r["text"])
        from amw import planer
        self.assertEqual(planer.heute_usd(self.con, self.pid), 0.7)                              # gemeinsame Grenze zählt mit

    def test_entwurf_legt_pakete_an_und_wartet_aufs_ja(self):
        feinplanung.anstossen(self.con, self.pid, [self.m1])
        e = feinplanung.entwurf_eintragen(self.con, self.pid, [self.m1], 1, self.plan(), modell="opus", usd=0.9)
        self.assertEqual(sorted(e["angelegt"]), ["P1", "P2"])
        p1, p2 = (int(e["angelegt"][k][1:]) for k in ("P1", "P2"))
        self.assertEqual(self.pakete(self.m1), [(p1, "Login-Seite bauen", "wartet"), (p2, "Tests für die Anmeldung", "wartet")])
        self.assertEqual(themen.verweise(self.con, self.pid, p2), [self.t1])
        self.assertEqual(fertigquelle.lesen(self.con, p2)["art"], "commit")
        self.assertEqual((arbeitspaket.lesen(self.con, p2)["art"], arbeitspaket.lesen(self.con, p1)["art"]), ("p", "agent"))
        self.assertEqual(planung.vorgaenger(self.con, p2), [p1])
        self.assertEqual(self.post()[-1], ("meldung", "Feinplan M1 Fassung 1: 2 Pakete angelegt – wartet auf das Ja"))
        self.assertIsNone(feinplanung.laeuft(self.con, self.pid, [self.m1]))
        self.assertEqual(self.con.execute("SELECT status FROM bogen WHERE id = ?", (self.m1,)).fetchone()[0], "geplant")   # nichts startet

    def test_neue_fassung_verwirft_die_alte(self):
        e1 = feinplanung.entwurf_eintragen(self.con, self.pid, [self.m1], 1, self.plan())
        r = feinplanung.neu_planen(self.con, self.pid, "TL", self.m1, "Tests zuerst")
        self.assertTrue(r["gestartet"])
        self.assertEqual(self.gestartet[-1], ([self.m1], 1))
        plan2 = self.plan()
        plan2["pakete"][0]["titel"] = "Anmeldeseite mit Firmenkonto"
        e2 = feinplanung.entwurf_eintragen(self.con, self.pid, [self.m1], 2, plan2)
        alt = {int(v[1:]) for v in e1["angelegt"].values()}
        self.assertEqual({a for a, _, _ in self.pakete(self.m1, "verworfen")}, alt)
        self.assertEqual(len(self.pakete(self.m1, "wartet")), 2)
        self.assertIn("Verworfen", self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE 'Feinplan M1 Fassung 2%'").fetchone()[0])
        self.assertTrue(e2["angelegt"])

    def test_pruefen_findet_fehler(self):
        from amw import planer
        f = self.plan(th=f"TH{self.t2}")                                                       # fremdes Thema
        f["unsinn"] = 1
        with self.assertRaises(planer.PlanFehler) as x:
            feinplanung.pruefen(f, self.con, self.pid, [self.m1])
        text = " ".join(x.exception.fehler)
        self.assertIn(f"TH{self.t2} gehört nicht zu M1", text)
        self.assertIn("unbekannte Felder: unsinn", text)
        with self.assertRaises(planer.PlanFehler) as x:
            feinplanung.pruefen(self.plan(), self.con, self.pid, [self.m1, self.m2])            # M2 ohne Paket
        self.assertIn("M2: kein Paket", " ".join(x.exception.fehler))
        e = feinplanung.entwurf_eintragen(self.con, self.pid, [self.m1], 1, "kein json")
        self.assertTrue(e["fehler"])
        self.assertEqual(self.pakete(self.m1), [])
        self.assertIn("passt nicht", self.post()[-1][1])

    def test_fragen_gehen_an_den_lead(self):
        f = self.plan(fragen=[{"frage": "Firmenkonto oder Passwort zuerst?", "optionen": {"A": "Firmenkonto", "B": "Passwort"},
                               "empfehlung": "A", "grund": "die meisten melden sich so an"}])
        feinplanung.entwurf_eintragen(self.con, self.pid, [self.m1], 1, f)
        q = self.con.execute("SELECT * FROM frage ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual((q["von"], q["kurz"]), ("AMW", "Feinplan M1: Firmenkonto oder Passwort zuerst?"))

    def test_gleichzeitige_meilensteine_zusammen(self):
        nr = {b: self.con.execute("SELECT nr FROM bogen WHERE id = ?", (b,)).fetchone()[0] for b in (self.m1, self.m2, self.m3)}
        with db.schreiben(self.con):
            self.con.execute("INSERT INTO plan_ereignis (projekt_id, zeit_utc, von, art, text) VALUES (?, ?, 'TL', 'grobplan_ja', ?)",
                             (self.pid, db.jetzt(), json.dumps({"angelegt": {}, "nach": {}, "gleichzeitig": {f"M{nr[self.m1]}": [f"M{nr[self.m2]}"]}})))
        for m in (self.m1, self.m2, self.m3):
            planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, m, "grob")
        self.assertEqual(feinplanung.projekt(self.con, self.pid), [(self.m1, "erster"), (self.m2, "erster")])
        self.assertEqual(self.gestartet, [(sorted([self.m1, self.m2]), 1)])                    # ein Lauf für beide
        plan = self.plan(m=f"M{nr[self.m1]}")
        plan["pakete"].append({"schluessel": "P3", "meilenstein": f"M{nr[self.m2]}", "thema": f"TH{self.t2}", "titel": "Nachtsicherung",
                               "auftrag": "Jede Nacht.", "groesse": "M", "art": "sicherheit", "ausfuehrung": "agent", "fertig_quelle": "commit",
                               "nach": ["P2"], "interaktiv_grund": "gesperrter Bereich"})
        e = feinplanung.entwurf_eintragen(self.con, self.pid, [self.m1, self.m2], 1, plan)
        self.assertEqual((len(self.pakete(self.m1)), len(self.pakete(self.m2))), (2, 1))
        self.assertEqual(planung.vorgaenger(self.con, int(e["angelegt"]["P3"][1:])), [int(e["angelegt"]["P2"][1:])])

    def test_ohne_planer_plant_der_lead(self):
        os.environ["AMW_PLANER_AUS"] = "1"
        feinplanung._planer_anstossen(self.con, self.pid, [planung.bogen_zeile(self.con, self.pid, self.m1)], "Der Grobplan steht")
        self.assertEqual(self.gestartet, [])
        self.assertEqual(self.post()[-1], ("auftrag", "Meilenstein 1 „Anmelden“ jetzt fein planen"))

    def test_neu_planen_nur_lead_oder_mensch(self):
        with self.assertRaisesRegex(kern.AmwFehler, "Lead oder der Mensch"):
            feinplanung.neu_planen(self.con, self.pid, "CC1", self.m1)
        r = aktionen.ausfuehren(self.con, self.pid, "/api/meilenstein/fein-neu", {"bogen": self.m1, "hinweis": "kleiner"}, kanal="seite")
        self.assertTrue(r["gestartet"])

    def test_einstieg_amw_planer_fein(self):
        from amw import planer
        with mock.patch.object(feinplanung, "ausfuehren") as aus, mock.patch("amw.db.verbinde", return_value=mock.MagicMock()):
            planer.main(["--fein", "--projekt-id", "3", "--boegen", "7,8", "--fassung", "2"])
        self.assertEqual(aus.call_args[0][1:], (3, [7, 8], 2))


if __name__ == "__main__":
    unittest.main()
