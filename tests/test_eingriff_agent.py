"""A2095 (TH164 „Eingriffe“, TH157 „Ausfälle“): einen Agenten herausnehmen und wieder freigeben – nichts Neues, wartende Pakete in den Pool
und neu verteilt, das laufende zu Ende oder mit Übergabe-Notiz zurück; Verlauf, Rechte, Weckrufe, Neustart, Prognose."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import tempfile
import time
import unittest
from unittest import mock

from amw import (aktionen, arbeitsliste, arbeitspaket, cli, db, dienst, herausnehmen, kern, planung, steuerung, verlauf_quellen, verteilen,
                 wartegrund, workbench)

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
            fremd = db.einfuegen(self.con, "projekt", name="Fremd", angelegt_utc=db.jetzt())
            self.pid = db.einfuegen(self.con, "projekt", name="Produkt", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, fremd, "TL", rolle="lead")
        planung.bogen_neu(self.con, fremd, "TL", "Fremd")                       # interne und Projektnummer verschieden
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        for k in ("CC1", "CC2"):
            kern.agent_neu(self.con, self.pid, k)
            with db.schreiben(self.con):
                self.con.execute("UPDATE agent SET soll = 'an' WHERE projekt_id = ? AND kennung = ?", (self.pid, k))
                db.einfuegen(self.con, "sitzung", agent_id=kern.agent_zeile(self.con, self.pid, k)["id"], claude_sitzung=k, gestartet_utc="2026-11-25T08:00:00Z",
                             schluessel_datei="x.json", zustand="aktiv", ereignis="frei", ereignis_utc="2026-11-25T08:00:00Z")
        kern.projekt_einstellen(self.con, self.pid, MENSCH, entwickler_name="Alex", verteilen="an")
        self.bid = planung.bogen_neu(self.con, self.pid, "TL", "Lieferung 1")
        planung.bogen_status(self.con, self.pid, "TL", self.bid, "aktiv")

    def paket(self, titel, agent: str | None = "CC1", **werte):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel, agent)
        planung.schritt_setzen(self.con, self.pid, "TL", aid=aid, bogen_id=self.bid, groesse="M", art="mechanisch", **werte)
        return aid

    def start(self, aid, agent="CC1"):
        kern.aufgabe_status(self.con, self.pid, agent, aid, "start")
        return aid

    def pruefung(self, aid, ergebnis, agent="CC1"):
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=aid, zweig="z", sha="a" * 40, bauer=agent, pruefer="TL",
                                ergebnis=ergebnis, angefragt_utc=db.jetzt())

    def nehmen(self, agent="CC1", laufendes="zu_ende", von=MENSCH, grund="Urlaub"):
        return herausnehmen.nehmen(self.con, self.pid, von, agent, laufendes, grund)

    def agent_von(self, aid):
        return tuple(self.con.execute("SELECT agent, status FROM aufgabe WHERE id = ?", (aid,)).fetchone())

    def post(self, an):
        return [(r["art"], r["kurz"], r["text"] or "") for r in self.con.execute(
            "SELECT n.art, n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE n.projekt_id = ? AND e.agent = ? ORDER BY n.id", (self.pid, an))]


class Herausnehmen(Grund):
    def test_wartende_in_den_pool_und_an_die_anderen(self):
        a, b = self.paket("A"), self.paket("B")
        r = self.nehmen()
        self.assertEqual((r["pool"], r["stueck"], r["bleibt"]), ([a, b], None, []))
        self.assertEqual([self.agent_von(x) for x in (a, b)], [(None, "wartet")] * 2)
        self.assertIn("M1", r["prognose"])
        verteilen.runde(self.con)
        wer = {self.agent_von(x)[0] for x in (a, b)}
        self.assertEqual(wer, {"CC2", None})                                          # einer an CC2, nichts an CC1
        self.assertNotIn("CC1", [k for k, _ in verteilen.freie_agenten(self.con, self.pid)])

    def test_laufendes_zu_ende(self):
        a, b = self.paket("A"), self.paket("B")
        self.start(a)
        r = self.nehmen(laufendes="zu_ende")
        self.assertEqual((r["stueck"], r["pool"], self.agent_von(a)), (a, [b], ("CC1", "laeuft")))
        with db.schreiben(self.con):
            lid = db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="CC1", beschreibung="Test", status="laeuft", angemeldet_utc=db.jetzt())
        kern.aufgabe_status(self.con, self.pid, "CC1", a, "wartet", auf=f"L{lid}")
        herausnehmen.nachziehen(self.con, self.pid)
        self.assertEqual(self.agent_von(a)[0], "CC1")                                 # wartet auf seinen Lauf: bleibt seins
        self.start(a)                                                                 # darf weitermachen
        kern.aufgabe_status(self.con, self.pid, "CC1", a, "wartet", auf="TL")
        self.assertEqual(herausnehmen.nachziehen(self.con, self.pid), [f"A{a} von CC1 zurück in den Pool"])
        self.assertEqual(self.agent_von(a), (None, "wartet"))

    def test_laufendes_zurueck_mit_uebergabe_notiz(self):
        a = self.start(self.paket("A"))
        r = self.nehmen(laufendes="zurueck")
        self.assertEqual((r["pool"], r["stueck"], self.agent_von(a)), ([a], None, (None, "wartet")))
        d = json.loads(self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'uebergabe' AND aufgabe_id = ?", (a,)).fetchone()[0])
        self.assertEqual(d["agent"], "CC1")
        self.assertIn("letzter Commit", d["notiz"])
        art, kurz, text = self.post("CC1")[-1]
        self.assertEqual((art, kurz), ("stopp", "Du bist herausgenommen (von Alex) – nichts Neues anfangen"))
        self.assertIn(f"A{a} geht mit Übergabe-Notiz in den Pool: Stand committen", text)

    def test_gebautes_bleibt_und_geht_bei_rot_in_den_pool(self):
        a, b = self.paket("A"), self.paket("B")
        self.pruefung(a, "offen")
        self.pruefung(b, "gruen")
        r = self.nehmen()
        self.assertEqual((r["pool"], r["bleibt"]), ([], [a, b]))
        self.assertEqual(herausnehmen.nachziehen(self.con, self.pid), [])
        self.pruefung(a, "rot")
        self.assertEqual(herausnehmen.nachziehen(self.con, self.pid), [f"A{a} von CC1 zurück in den Pool"])
        self.assertEqual((self.agent_von(a)[0], self.agent_von(b)[0]), (None, "CC1"))

    def test_headless_bleibt_unberuehrt(self):
        a = self.paket("P")
        arbeitspaket.setzen(self.con, self.pid, "TL", a, art="p")
        self.assertEqual([x["id"] for x in herausnehmen.folgen(self.con, self.pid, "CC1", "zu_ende")["wartend"]], [])
        self.assertEqual((self.nehmen()["pool"], self.agent_von(a)[0]), ([], "CC1"))

    def test_letzter_arbeitsfaehiger_steht_im_ergebnis(self):
        self.nehmen("CC2")
        r = self.nehmen("CC1")
        self.assertTrue(any("niemand" in h or "Lead" in h for h in r["hinweise"]), r["hinweise"])

    def test_auslieferung_und_schwerer_lauf_sperren_nur_zurueck(self):
        self.start(self.paket("A"))
        with mock.patch("amw.waechter.zustand", return_value={"wartung": {"grund": "Auslieferung der AMW"}}):
            with self.assertRaisesRegex(kern.AmwFehler, "gerade wird ausgeliefert"):
                self.nehmen(laufendes="zurueck")
        with db.schreiben(self.con):
            lid = db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="CC1", beschreibung="x", schwer=1, status="laeuft", angemeldet_utc=db.jetzt(), start_utc=db.jetzt())
        with self.assertRaisesRegex(kern.AmwFehler, f"Lauf L{lid} rechnet noch"):
            self.nehmen(laufendes="zurueck")
        self.nehmen(laufendes="zu_ende")
        self.assertEqual(self.con.execute("SELECT status FROM lauf WHERE id = ?", (lid,)).fetchone()[0], "laeuft")     # niemand beendet Läufe


class Sperren(Grund):
    def setUp(self):
        super().setUp()
        self.a, self.b = self.paket("A"), self.paket("B")

    def test_start_naechster_zuweisen(self):
        self.start(self.a)
        self.nehmen()
        self.paket("Neu", agent=None)
        with self.assertRaisesRegex(kern.AmwFehler, r"CC1 ist herausgenommen \(von Alex: Urlaub\) – erst freigeben"):
            planung.naechster(self.con, self.pid, "CC1", nehmen=True)
        for f in (lambda: kern.aufgabe_neu(self.con, self.pid, "TL", "x", "CC1"),
                  lambda: planung.schritt_setzen(self.con, self.pid, "TL", aid=self.b, agent="CC1"),
                  lambda: arbeitsliste.ordnen(self.con, self.pid, "TL", "CC1", [self.b], "eilig")):
            with self.assertRaisesRegex(kern.AmwFehler, "herausgenommen"):
                f()
        planung.schritt_setzen(self.con, self.pid, "TL", aid=self.a, agent="CC1", groesse="S")            # schon seins: ändern geht
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "fertig", beleg="x", zusammenfassung="x")  # sein Stück bleibt bedienbar
        self.assertFalse([x for x in self.post("CC1") if "weiter in deiner Liste" in x[1]])

    def test_leerlauf_und_startklar(self):
        self.pruefung(self.a, "gruen")
        self.nehmen()
        vorher = len(self.post("CC1"))
        with db.schreiben(self.con):
            self.con.execute("UPDATE sitzung SET ereignis = 'frei', ereignis_utc = '2026-11-25T08:00:00Z'")
            self.con.execute("UPDATE empfang SET status = 'erledigt'")
        wartegrund.leerlauf(self.con, time.time())
        self.assertEqual(len(self.post("CC1")), vorher)

    def test_weckruf_nur_zum_laufenden_stueck_und_beim_freigeben_alles(self):
        self.start(self.a)
        self.nehmen()
        with db.schreiben(self.con):
            self.con.execute("UPDATE empfang SET geweckt_utc = ?", (db.jetzt(),))
        kern.posten(self.con, self.pid, "TL", "CC1", "frage", "Zu was anderem?")
        kern.posten(self.con, self.pid, "TL", "CC1", "antwort", "Zu deinem Stück", aufgabe_id=self.a)
        gesendet = []
        d = dienst.Dienst.__new__(dienst.Dienst)
        d.con, d.sperre_bis = self.con, {}
        with mock.patch.object(dienst, "lies_schluessel", return_value=("p", "k")), mock.patch.object(dienst, "arbeitet_gerade", return_value=False), \
                mock.patch.object(dienst.pipe, "senden", side_effect=lambda p, k, t: gesendet.append(t)):
            d.zustellen()
            self.assertIn("Zu deinem Stück", "".join(gesendet))
            self.assertNotIn("Zu was anderem", "".join(gesendet))
            herausnehmen.freigeben(self.con, self.pid, MENSCH, "CC1")
            d.zustellen()
        self.assertIn("Zu was anderem", "".join(gesendet))

    def test_neustart_nur_solange_sein_stueck_laeuft(self):
        self.start(self.a)
        self.nehmen()
        with db.schreiben(self.con):
            self.con.execute("UPDATE agent SET neustart_auto = 1 WHERE kennung = 'CC1'")
            self.con.execute("UPDATE sitzung SET zustand = 'beendet', beendet_utc = ?, fenster_pid = 1, claude_pid = 2", (db.jetzt(),))
        u = steuerung.Neustarter.__new__(steuerung.Neustarter)
        u.con = self.con
        with mock.patch.object(steuerung, "lebt", side_effect=lambda p: p == 1):
            self.assertEqual([k for k, _ in u.kandidaten(self.pid)], ["CC1"])
            kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "fertig", beleg="x", zusammenfassung="x")
            self.assertEqual(u.kandidaten(self.pid), [])

    def test_kontext_sagt_es_ihm(self):
        self.nehmen()
        self.assertIn("DU BIST HERAUSGENOMMEN (von Alex: Urlaub)", kern.kontext(self.con, self.pid, "CC1"))
        self.assertNotIn("HERAUSGENOMMEN", kern.kontext(self.con, self.pid, "CC2"))


class Rechte(Grund):
    def test_wer_darf(self):
        for von, muster in (("CC2", "der Mensch oder der Lead"),):
            with self.assertRaisesRegex(kern.AmwFehler, muster):
                self.nehmen(von=von)
        with self.assertRaisesRegex(kern.AmwFehler, "nur mit Grund"):
            self.nehmen(von="TL", grund=" ")
        with self.assertRaisesRegex(kern.AmwFehler, "führt das Projekt"):
            self.nehmen(agent="TL")
        self.nehmen(von=MENSCH, grund="")
        with self.assertRaisesRegex(kern.AmwFehler, "ist herausgenommen"):
            self.nehmen(von="TL")

    def test_mensch_geht_vor_lead(self):
        self.nehmen(von=MENSCH)
        with self.assertRaisesRegex(kern.AmwFehler, "CC1 hat Alex herausgenommen – das hebt nur Alex auf"):
            herausnehmen.freigeben(self.con, self.pid, "TL", "CC1")
        herausnehmen.freigeben(self.con, self.pid, MENSCH, "CC1")
        self.nehmen(von="TL", grund="krank")
        herausnehmen.freigeben(self.con, self.pid, "TL", "CC1")
        with self.assertRaisesRegex(kern.AmwFehler, "nicht herausgenommen"):
            herausnehmen.freigeben(self.con, self.pid, "TL", "CC1")

    def test_freigegeben_bekommt_wieder_neues(self):
        self.paket("Frei", agent=None)
        self.nehmen("CC1")
        self.nehmen("CC2")
        self.assertEqual(verteilen.freie_agenten(self.con, self.pid), [])
        herausnehmen.freigeben(self.con, self.pid, MENSCH, "CC1")
        self.assertEqual([k for k, _ in verteilen.freie_agenten(self.con, self.pid)], ["CC1"])

    def test_halt_bleibt_etwas_anderes(self):
        self.nehmen()
        kern.halt(self.con, self.pid, "TL", "CC1", "Halt")
        herausnehmen.freigeben(self.con, self.pid, MENSCH, "CC1")
        self.assertTrue(kern.halt_gilt(self.con, self.pid, "CC1"))


class Anzeige(Grund):
    def test_verlauf_und_startdaten(self):
        for t in "AB":
            self.paket(t)
        self.nehmen(von="TL", grund="krank")
        herausnehmen.freigeben(self.con, self.pid, "TL", "CC1", "wieder da")
        e = [(x["rolle"], x["von"], x["text"]) for x in verlauf_quellen.gesamt(self.con, self.pid, [], lambda e: "umsetzung") if x["art"].startswith("agent_")]
        self.assertEqual(e, [("agent", "TL", "CC1 herausgenommen – krank; 2 Pakete in den Pool (M1: 2)"), ("agent", "TL", "CC1 wieder freigegeben – wieder da")])
        self.nehmen(von="TL", grund="krank")
        je = {a["kennung"]: a["heraus"] for a in workbench.daten_start(self.con, self.pid)["agenten"]}
        self.assertEqual((je["CC1"]["von"], je["CC2"]), ("TL", None))

    def test_seite_pc_und_online(self):
        a = self.paket("A")
        for kanal in ("seite", "netz"):
            f = aktionen.ausfuehren(self.con, self.pid, "/api/plan/agent", {"kennung": "CC1", "was": "folgen"}, kanal)
            self.assertEqual([x["id"] for x in f["wartend"]], [a])
        r = aktionen.ausfuehren(self.con, self.pid, "/api/plan/agent", {"kennung": "CC1", "was": "herausnehmen", "laufendes": "zu_ende"}, "netz")
        self.assertEqual(r["pool"], [a])
        self.assertTrue(aktionen.ausfuehren(self.con, self.pid, "/api/plan/agent", {"kennung": "CC1", "was": "freigeben"}, "seite")["ok"])
        for d in ({}, {"kennung": "CC1"}, {"kennung": "CC9", "was": "folgen"}):
            with self.assertRaises(aktionen.Ungueltig):
                aktionen.ausfuehren(self.con, self.pid, "/api/plan/agent", d)

    def test_befehl(self):
        self.paket("A")

        def rufen(*a):
            with contextlib.redirect_stdout(io.StringIO()) as o, contextlib.redirect_stderr(io.StringIO()) as f:
                rc = cli.main(["--projekt", "Produkt", "--von", "TL", "agent", *a])
            return rc, o.getvalue() + f.getvalue()
        self.assertIn("in den Pool: A", rufen("folgen", "CC1")[1])
        self.assertIn("nur mit Grund", rufen("herausnehmen", "CC1")[1])
        self.assertIn("CC1 ist herausgenommen", rufen("herausnehmen", "CC1", "--grund", "krank", "--laufendes", "zu_ende")[1])
        self.assertIn("wieder freigegeben", rufen("freigeben", "CC1")[1])

    def test_verteilen_aus_wird_genannt(self):
        kern.projekt_einstellen(self.con, self.pid, MENSCH, verteilen="aus")
        self.paket("A")
        self.assertTrue(any("Das Verteilen ist aus" in h for h in self.nehmen()["hinweise"]))


if __name__ == "__main__":
    unittest.main()
