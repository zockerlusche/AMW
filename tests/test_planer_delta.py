"""A2027: Planer im Delta-Modus – ein geändertes, schon geplantes Thema bekommt nur die Änderung vorgeschlagen (neue Pakete,
„aendern“/„verwerfen“ nur für nicht begonnene), und der Mensch gibt das Delta als einen Block frei (feinplan_freigabe)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import db, kern, planer, planer_delta, themen

PLAN = {
    "meilensteine": [{"schluessel": "M1", "titel": "Anmelden online", "endet_mit": "vorfuehrung"}],
    "pakete": [
        {"schluessel": "P1", "meilenstein": "M1", "titel": "Anmeldung mit Firmen-Konto", "auftrag": "SSO-Anmeldung bauen.",
         "groesse": "M", "art": "sicherheit", "ausfuehrung": "agent", "fertig_quelle": "release"},
        {"schluessel": "P2", "meilenstein": "M1", "titel": "Abmelden", "auftrag": "Abmelden-Knopf.",
         "groesse": "S", "art": "oberflaeche", "ausfuehrung": "agent", "fertig_quelle": "commit"},
        {"schluessel": "P3", "meilenstein": "M1", "titel": "Passwort vergessen", "auftrag": "Mail mit Link.",
         "groesse": "S", "art": "oberflaeche", "ausfuehrung": "agent", "fertig_quelle": "commit"}]}


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
            self.pid = db.einfuegen(self.con, "projekt", name="Produkt", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid, "Co")
        kern.projekt_einstellen(self.con, self.pid, "TL", co_entwickler="Co")
        self.tid = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", self.tid, "Anmelden mit Firmen-Konto.\nAbmelden oben rechts.\nPasswort vergessen per Mail.")
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, PLAN)
        a = planer.uebernehmen(self.con, self.pid, "TL", self.tid)
        self.p1, self.p2, self.p3 = (int(str(a[k])[1:]) for k in ("P1", "P2", "P3"))
        with db.schreiben(self.con):                                    # P1 fertig, P2 läuft, P3 nicht begonnen
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc1234' WHERE id = ?", (self.p1,))
            self.con.execute("UPDATE aufgabe SET status = 'laeuft' WHERE id = ?", (self.p2,))

    def aendern(self, text="Anmelden mit Firmen-Konto und Passkey.\nAbmelden oben rechts.\nPasswort vergessen entfällt."):
        themen.bearbeiten(self.con, self.pid, kern.ENTWICKLER, self.tid, text)

    def delta_plan(self, **mehr):
        d = {"meilensteine": [{"schluessel": "M1", "bestehend": 1}],
             "pakete": [{"schluessel": "N1", "meilenstein": "M1", "titel": "Passkey nachrüsten", "auftrag": "Passkey zur Anmeldung.",
                         "groesse": "S", "art": "sicherheit", "ausfuehrung": "agent", "fertig_quelle": "commit"}],
             "verwerfen": [{"paket": f"A{self.p3}", "grund": "Passwort vergessen entfällt"}]}
        d.update(mehr)
        return d

    def post(self, an):
        return [(r["art"], r["kurz"], r["text"]) for r in self.con.execute(
            "SELECT n.art, n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? AND n.von = 'AMW'"
            " ORDER BY n.id", (an,))]


class Kontext(Grund):
    def test_erst_nach_der_aenderung_mit_unterschied_und_gruppen(self):
        self.assertIsNone(planer_delta.kontext(self.con, self.pid, self.tid))      # nur freigegeben, nicht geändert
        self.aendern()
        d = planer_delta.kontext(self.con, self.pid, self.tid)
        assert d is not None
        self.assertEqual((d["art"], d["alt"]["fassung"], d["neu"]["fassung"]), ("geaendert", 1, 2))
        self.assertEqual(d["pakete"], {self.p1: "fertig", self.p2: "zu_ende", self.p3: "stoppen"})
        text = planer_delta.datei(self.con, self.pid, d)
        self.assertIn("-Passwort vergessen per Mail.", text)
        self.assertIn("+Passwort vergessen entfällt.", text)
        self.assertIn(f"- A{self.p3} [nicht begonnen – stoppen] Passwort vergessen", text)
        self.assertIn("Auftrag: Mail mit Link.", text)

    def test_planer_bekommt_aenderung_und_delta_auftrag(self):
        self.aendern()
        gesehen = {}

        def laufen(p, auftrag, *_a, **_k):
            gesehen["auftrag"] = auftrag
            gesehen["datei"] = open(os.path.join(p["klon"], "aenderung.md"), encoding="utf-8").read()
            return {"rc": 0, "ergebnis": {"result": json.dumps(self.delta_plan()), "total_cost_usd": 0.1}}
        from amw import arbeiter
        with mock.patch.object(arbeiter, "laufen", side_effect=laufen):
            aus = planer.planen(self.con, self.pid, themen.finden(self.con, self.pid, self.tid), 2, "sonnet")
        self.assertIn("DELTA-MODUS", gesehen["auftrag"])
        self.assertIn("aenderung.md", gesehen["auftrag"])
        self.assertIn("Unterschied", gesehen["datei"])
        self.assertEqual(aus["delta"]["art"], "geaendert")
        e = planer.entwurf_eintragen(self.con, self.pid, self.tid, 2, aus["ergebnis"], delta=aus["delta"])
        ent = (planer.letzter_entwurf(self.con, self.pid, self.tid) or {}).get("entwurf") or {}
        self.assertEqual(ent["delta"]["neu"], 2)
        self.assertTrue(e)


class Pruefen(Grund):
    def setUp(self):
        super().setUp()
        self.aendern()
        self.d = planer_delta.kontext(self.con, self.pid, self.tid)

    def test_nacharbeit_nur_ausdruecklich_und_nur_fertige(self):
        """A2059 (TH158 F4→F5): ein fertiges Paket ist nicht von selbst „Nacharbeit nötig“ – nur, wenn der Delta-Planer es in
        "nacharbeit" nennt (mit Grund); laufende und nicht begonnene gehen dort nicht."""
        ohne = planer.pruefen(self.delta_plan(), self.con, self.pid, self.tid, delta=self.d)
        self.assertEqual(ohne["nacharbeit"], [])
        self.assertFalse([z for z in planer_delta.zeilen(ohne) if "Nacharbeit" in z])          # fertiges p1 erscheint nicht als Nacharbeit
        mit = planer.pruefen(self.delta_plan(nacharbeit=[{"paket": f"A{self.p1}", "grund": "Anmeldung braucht den Passkey"}]),
                             self.con, self.pid, self.tid, delta=self.d)
        self.assertEqual(mit["nacharbeit"], [{"paket": self.p1, "grund": "Anmeldung braucht den Passkey"}])
        self.assertIn(f"  Nacharbeit nötig A{self.p1} – Anmeldung braucht den Passkey", planer_delta.zeilen(mit))
        for paket, erwartet in ((self.p2, "Nacharbeit nur für fertige"), (self.p3, "Nacharbeit nur für fertige"),
                                (99999, "kein betroffenes Paket")):
            with self.assertRaises(planer.PlanFehler) as f:
                planer.pruefen(self.delta_plan(nacharbeit=[{"paket": f"A{paket}", "grund": "x"}]), self.con, self.pid, self.tid, delta=self.d)
            self.assertIn(erwartet, " | ".join(f.exception.fehler))
        with self.assertRaises(planer.PlanFehler) as f:
            planer.pruefen(self.delta_plan(nacharbeit=[{"paket": f"A{self.p1}"}]), self.con, self.pid, self.tid, delta=self.d)
        self.assertIn("grund fehlt", " | ".join(f.exception.fehler))
        self.assertIn("nacharbeit", planer_delta.AUFTRAG)

    def test_aendern_und_verwerfen_nur_nicht_begonnene(self):
        e = planer.pruefen(self.delta_plan(aendern=[{"paket": f"A{self.p3}", "titel": "x", "grund": "y"}], verwerfen=[]),
                           self.con, self.pid, self.tid, delta=self.d)
        self.assertEqual(e["aendern"][0]["paket"], self.p3)
        for paket, erwartet in ((self.p1, "fertig – Planer prüft, ob betroffen"), (self.p2, "laufend – zu Ende bauen"),
                                (99999, "kein betroffenes Paket")):
            with self.assertRaises(planer.PlanFehler) as f:
                planer.pruefen(self.delta_plan(verwerfen=[{"paket": f"A{paket}", "grund": "weg"}]), self.con, self.pid, self.tid,
                               delta=self.d)
            self.assertIn(erwartet, " | ".join(f.exception.fehler))
        with self.assertRaises(planer.PlanFehler) as f:
            planer.pruefen(self.delta_plan(aendern=[{"paket": f"A{self.p3}", "grund": "y"}]), self.con, self.pid, self.tid, delta=self.d)
        self.assertIn("titel oder auftrag nötig", " | ".join(f.exception.fehler))

    def test_nur_aenderungen_ohne_neue_pakete(self):
        e = planer.pruefen({"verwerfen": [{"paket": f"A{self.p3}", "grund": "entfällt"}]}, self.con, self.pid, self.tid, delta=self.d)
        self.assertEqual((e["pakete"], len(e["verwerfen"])), ([], 1))
        with self.assertRaisesRegex(planer.PlanFehler, "unbekannte Felder: verwerfen"):       # ohne Delta gibt es das nicht
            planer.pruefen({**copy.deepcopy(PLAN), "verwerfen": []}, self.con, self.pid, self.tid)
        with self.assertRaisesRegex(planer.PlanFehler, "meilensteine: mindestens einer"):
            planer.pruefen({}, self.con, self.pid, self.tid, delta=self.d)


class Nachbessern(Grund):
    """A2076: über den echten Weg – die Planer-Attrappe antwortet mit TEXT (Prosa + JSON), wie claude -p."""
    def lauf(self, *antworten, kosten=0.1):
        from amw import arbeiter
        self.gesehen = []

        def laufen(p, auftrag, *_a, **_k):
            x = {}
            for name in ("erlaubt", "nachbessern", "befehle"):
                datei = os.path.join(p["klon"], name + ".md")
                x[name] = None
                if os.path.exists(datei):
                    with open(datei, encoding="utf-8") as f:
                        x[name] = f.read()
            self.gesehen.append({"auftrag": auftrag, **x})
            a = antworten[len(self.gesehen) - 1]
            if isinstance(a, Exception):
                raise a
            return {"rc": 0, "ergebnis": {"result": "Hier der Plan:\n```json\n" + json.dumps(a, ensure_ascii=False) + "\n```\nFertig.", "total_cost_usd": kosten}}
        u = mock.patch.dict(os.environ)
        u.start()
        self.addCleanup(u.stop)
        os.environ.pop("AMW_PLANER_AUS", None)
        from amw import schalter
        with db.schreiben(self.con):
            schalter._setzen(self.con, self.pid, "an")
            planer._ereignis(self.con, self.pid, "AMW", planer.ANGESTOSSEN, self.tid, fassung=2, modell="sonnet")
        with mock.patch.object(arbeiter, "laufen", side_effect=laufen):
            planer.ausfuehren(self.con, self.pid, self.tid, 2)
        e = planer.letzter_entwurf(self.con, self.pid, self.tid)
        assert e is not None
        return e

    def falsch(self):                                                   # das laufende Paket P2 als Nacharbeit (L3452)
        return self.delta_plan(nacharbeit=[{"paket": f"A{self.p2}", "grund": "Passkey"}])

    def test_erst_falsch_dann_richtig_sind_zwei_laeufe(self):
        self.aendern()
        e = self.lauf(self.falsch(), self.delta_plan())
        self.assertEqual(len(self.gesehen), 2)
        self.assertNotIn("fehler", e)
        self.assertTrue(e["entwurf"]["delta"])
        self.assertEqual(e["usd"], 0.2)                                 # beide Läufe zählen
        self.assertIsNone(self.gesehen[0]["nachbessern"])
        self.assertIn("NACHBESSERN", self.gesehen[1]["auftrag"])
        self.assertIn("Nacharbeit nur für fertige Pakete", self.gesehen[1]["nachbessern"])
        self.assertIn("Passkey nachrüsten", self.gesehen[1]["nachbessern"])       # die erste Antwort liegt dabei

    def test_ohne_fund_ein_lauf(self):
        self.aendern()
        e = self.lauf(self.delta_plan())
        self.assertEqual((len(self.gesehen), "fehler" in e, e["usd"]), (1, False, 0.1))

    def test_zweimal_falsch_merkt_die_aenderung_und_meldet_dem_lead(self):
        self.aendern()
        e = self.lauf(self.falsch(), self.falsch())
        self.assertEqual(len(self.gesehen), 2)
        self.assertIn("Nacharbeit nur für fertige Pakete", " ".join(e["fehler"]))
        self.assertEqual(e["delta"]["neu"], 2)
        art, kurz, text = self.post("TL")[-1]
        self.assertEqual(art, "meldung")
        self.assertIn("passt nicht zum Schema", kurz)
        self.assertIn("Auch die eine automatische Nachbesserung passte nicht.", text)

    def test_vor_dem_zweiten_lauf_gilt_die_tagesgrenze(self):
        self.aendern()
        kern.projekt_einstellen(self.con, self.pid, "TL", planer_tagesgrenze_usd="0.1")
        e = self.lauf(self.falsch(), self.delta_plan())
        self.assertEqual(len(self.gesehen), 1)
        self.assertEqual(e["usd"], 0.1)
        self.assertIn("Tagesgrenze", self.post("TL")[-1][2])

    def test_zweiter_lauf_geht_nicht_kosten_und_funde_bleiben(self):
        self.aendern()
        e = self.lauf(self.falsch(), RuntimeError("weg"))
        self.assertEqual(e["usd"], 0.1)
        self.assertIn("Planer-Lauf: RuntimeError: weg", e["fehler"][0])
        self.assertIn("Nacharbeit nur für fertige Pakete", " ".join(e["fehler"][1:]))

    def test_planer_bekommt_die_erlaubten_je_gruppe(self):
        self.aendern()
        self.lauf(self.delta_plan())
        teile = self.gesehen[0]["erlaubt"].split("## ")
        je = {t.split(" ", 1)[0]: t for t in teile[1:]}
        self.assertIn(f"A{self.p3} Passwort vergessen", je["nicht"])
        self.assertIn(f"A{self.p2} Abmelden", je["läuft"])
        self.assertIn("neues Paket danach", je["läuft"])
        self.assertIn(f"A{self.p1} Anmeldung", je["fertig"])
        self.assertIn("erlaubt.md", self.gesehen[0]["auftrag"])
        self.assertIn("`*-c *`", self.gesehen[0]["befehle"])                      # (6): gesperrte Abnahme-Befehle
        self.assertIn("befehle.md", self.gesehen[0]["auftrag"])

    def test_ueberarbeiten_gibt_die_funde_mit(self):
        from amw import planhinweis
        self.aendern()
        self.lauf(self.falsch(), self.falsch())
        planhinweis.hinweis(self.con, self.pid, kern.ENTWICKLER, f"TH{self.tid}", "Abmelden so lassen")
        d = planhinweis.dateien(self.con, self.pid, f"TH{self.tid}")
        self.assertIn("Abmelden so lassen", d["hinweise.md"])
        self.assertIn("Nacharbeit nur für fertige Pakete", d["hinweise.md"])


class Freigabe(Grund):
    def setUp(self):
        super().setUp()
        self.aendern()
        d = planer_delta.kontext(self.con, self.pid, self.tid)
        self.eid = planer.entwurf_eintragen(self.con, self.pid, self.tid, 2, self.delta_plan(
            aendern=[], verwerfen=[{"paket": f"A{self.p3}", "grund": "Passwort vergessen entfällt"}]), delta=d)

    def test_meldung_an_den_lead_als_block(self):
        k, t = self.post("TL")[-1][1:]
        self.assertIn(f"Delta TH{self.tid}", k)
        self.assertIn("1 neu, 0 ändern, 1 verwerfen – Freigabe als Block", k)
        self.assertIn("Freigabe als ein Block", t)
        self.assertIn(f"verwerfen A{self.p3} – Passwort vergessen entfällt", t)

    def test_der_mensch_gibt_den_block_frei(self):
        with self.assertRaisesRegex(kern.AmwFehler, r"feinplan_freigabe = mensch"):
            planer.uebernehmen(self.con, self.pid, "TL", self.tid)
        with self.assertRaisesRegex(kern.AmwFehler, "als ein Block freigegeben, nicht geändert"):
            planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid, geaendert="{}")
        from amw import cli
        aus = io.StringIO()
        mensch = {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}          # wie im Terminal des Menschen
        with contextlib.redirect_stdout(aus), mock.patch.dict(os.environ, mensch):
            rc = cli.main(["thema", "plan-ja", f"TH{self.tid}", "--projekt", "Produkt", "--von", kern.ENTWICKLER])
        self.assertFalse(rc, aus.getvalue())
        self.assertIn("Delta freigegeben – angelegt M1 → M1, N1 → A", aus.getvalue())
        self.assertIn(f"verworfen A{self.p3}", aus.getvalue())
        self.assertEqual(self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (self.p3,)).fetchone()[0], "verworfen")
        neu = self.con.execute("SELECT id, bogen_id FROM aufgabe WHERE titel = 'Passkey nachrüsten'").fetchone()
        self.assertEqual(neu["bogen_id"], self.con.execute("SELECT bogen_id FROM aufgabe WHERE id = ?", (self.p1,)).fetchone()[0])
        self.assertTrue(planer.erledigt(self.con, self.pid, self.eid))
        self.assertEqual(planer_delta.letzte(self.con, self.pid, self.tid)["verworfen"], [f"A{self.p3}"])

    def test_inzwischen_begonnen_bleibt_unberuehrt(self):
        """P593: Zwischen Entwurf und Ja startet das Paket, das verworfen werden sollte – es bleibt, wie es ist; die Anwendung nennt
        es, der Lead bekommt eine Meldung."""
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'laeuft' WHERE id = ?", (self.p3,))
        a = planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.assertIn("N1", a)                                                   # die neuen Pakete kommen trotzdem
        self.assertEqual(self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (self.p3,)).fetchone()[0], "laeuft")
        d = planer_delta.letzte(self.con, self.pid, self.tid)
        self.assertEqual((d["verworfen"], d["uebersprungen"]), ([], [f"A{self.p3} läuft inzwischen"]))
        self.assertIn(f"A{self.p3} läuft inzwischen", self.post("TL")[-1][2])

    def test_aendern_setzt_titel_und_auftrag(self):
        d = planer_delta.kontext(self.con, self.pid, self.tid)
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 2, {"aendern": [
            {"paket": f"A{self.p3}", "titel": "Passwort zurücksetzen", "auftrag": "Link mit Passkey.", "grund": "neu gefasst"}]}, delta=d)
        planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid)
        r = self.con.execute("SELECT titel, auftrag, status FROM aufgabe WHERE id = ?", (self.p3,)).fetchone()
        self.assertEqual((r["titel"], r["auftrag"]), ("Passwort zurücksetzen", "Link mit Passkey."))
        self.assertNotEqual(r["status"], "verworfen")

    def test_co_und_lead_bei_feinplan_freigabe_co_lead(self):
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, feinplan_freigabe="co+lead")
        with self.assertRaisesRegex(kern.AmwFehler, "Co-Entwickler und der Lead"):
            planer.uebernehmen(self.con, self.pid, "CC1", self.tid)
        self.assertEqual(planer.uebernehmen(self.con, self.pid, "Co", self.tid), {"ja_fehlt": "Lead"})
        self.assertFalse(planer.erledigt(self.con, self.pid, self.eid))
        a = planer.uebernehmen(self.con, self.pid, "TL", self.tid)
        self.assertIn("N1", a)
        self.assertTrue(planer.erledigt(self.con, self.pid, self.eid))


class BlockGrund(Grund):
    def setUp(self):
        super().setUp()
        from amw import schalter
        u = mock.patch.dict(os.environ, {"AMW_PLANER_AUS": "1"})
        u.start()
        self.addCleanup(u.stop)
        with db.schreiben(self.con):
            schalter._setzen(self.con, self.pid, "an")
        self.m1 = self.con.execute("SELECT bogen_id FROM aufgabe WHERE id = ?", (self.p1,)).fetchone()[0]
        self.aendern()

    def paket(self, ms):
        return {"schluessel": "N1", "meilenstein": ms, "titel": "Passkey nachrüsten", "auftrag": "Passkey zur Anmeldung.", "groesse": "S",
                "art": "mechanisch", "ausfuehrung": "p", "fertig_quelle": "commit", "abnahme_befehl": "python -m unittest tests.test_passkey",
                "bereiche": "app/passkey.py"}

    def entwurf(self, neu=True, **mehr):
        d = planer_delta.kontext(self.con, self.pid, self.tid)
        plan = {"meilensteine": [{"schluessel": "M2", "titel": "Passkey", "endet_mit": "vorfuehrung"} if neu else {"schluessel": "M1", "bestehend": 1}],
                "pakete": [self.paket("M2" if neu else "M1")], **mehr}
        eid = planer.entwurf_eintragen(self.con, self.pid, self.tid, 2, plan, delta=d)
        self.assertNotIn("fehler", planer.letzter_entwurf(self.con, self.pid, self.tid) or {})
        return eid

    def zustand(self, bid, art):
        from amw import planansicht
        return bool((planansicht._zustaende(self.con, self.pid).get((bid, art)) or {}).get("an"))

    def bogen(self, titel="Passkey"):
        return self.con.execute("SELECT * FROM bogen WHERE titel = ?", (titel,)).fetchone()

    def neues_paket(self):
        from amw import arbeitspaket
        a = self.con.execute("SELECT id FROM aufgabe WHERE titel = 'Passkey nachrüsten'").fetchone()[0]
        return arbeitspaket.lesen(self.con, a)["zustand"]

    def m1_frei(self, aktiv=True):
        from amw import feinplanung, planansicht
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "grob")
        (feinplanung.plan_starten if aktiv else lambda c, p, v, b: planansicht.freigeben(c, p, v, b, "plan"))(
            self.con, self.pid, kern.ENTWICKLER, self.m1)


class BlockStart(BlockGrund):
    """A2080: das Ja zu einer Konzeptänderung ist ein Block – es gibt frei und startet."""
    def test_neuer_meilenstein_laeuft_nach_dem_ja(self):
        eid = self.entwurf()
        planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid)
        b = self.bogen()
        self.assertEqual(b["status"], "aktiv")
        self.assertTrue(self.zustand(b["id"], "grob") and self.zustand(b["id"], "plan"))
        self.assertEqual(self.neues_paket(), "startklar")
        ja = [json.loads(r[0]) for r in self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'meilenstein_frei' AND bogen_id = ?", (b["id"],))]
        self.assertEqual([(x["art"], x["quelle"], x["durch"]) for x in ja], [("grob", "delta", [kern.ENTWICKLER]), ("plan", "delta", [kern.ENTWICKLER])])
        jid = self.con.execute("SELECT id FROM plan_ereignis WHERE art = ? ORDER BY id DESC", (planer.JA,)).fetchone()[0]
        self.assertEqual({x["ja"] for x in ja}, {jid})
        with self.assertRaisesRegex(kern.AmwFehler, "schon angenommen"):                 # ein zweites Ja legt nichts doppelt an
            planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid, eid=eid)
        self.assertEqual(self.con.execute("SELECT count(*) FROM bogen WHERE titel = 'Passkey'").fetchone()[0], 1)

    def test_bestehender_plan_bleibt_frei_und_das_neue_paket_startklar(self):
        self.m1_frei()
        self.entwurf(neu=False)
        planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.assertTrue(self.zustand(self.m1, "plan"))
        self.assertTrue(self.zustand(self.m1, "grob"))
        self.assertEqual(self.neues_paket(), "startklar")

    def nachbar(self):
        """Ein p-Paket in M1, das der Lead zurückhält (Zustand entwurf, alle Angaben da)."""
        from amw import arbeitspaket, fertigquelle, planung
        aid = planung.schritt_setzen(self.con, self.pid, "TL", titel="Zurückgehalten", auftrag="später", bogen_id=self.m1, groesse="S",
                                     art="mechanisch", pruefbefehl="python -m unittest tests.test_y", dateibereich="app/y.py")
        arbeitspaket.setzen(self.con, self.pid, "TL", aid, art="p", modell="sonnet")
        themen.verweise_setzen(self.con, self.pid, "TL", aid, [self.tid])
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="TL", art=fertigquelle.ART, aufgabe_id=aid,
                         text=json.dumps({"art": "commit"}))
        return aid

    def plan_stand(self):
        from amw import reihenfolge
        return [tuple(r) for r in self.con.execute("SELECT id, text FROM plan_ereignis WHERE art = ? AND bogen_id = ?", (reihenfolge.PLAN_STAND, self.m1))]

    def test_nachbar_paket_und_plan_stand_bleiben_unberuehrt(self):
        from amw import arbeitspaket, planansicht, reihenfolge
        aid = self.nachbar()
        a = self.con.execute("SELECT * FROM aufgabe WHERE id = ?", (aid,)).fetchone()
        self.assertEqual(reihenfolge.fehlende_felder(self.con, self.pid, a), [])          # könnte starten – der Lead hält es zurück
        self.m1_frei()
        vorher_zustand = arbeitspaket.lesen(self.con, aid)["zustand"]
        arbeitspaket.zustand_setzen(self.con, self.pid, "TL", aid, "entwurf", grund="zurückgehalten")   # der Lead nimmt es nach dem Start zurück
        self.assertEqual((vorher_zustand, arbeitspaket.lesen(self.con, aid)["zustand"]), ("startklar", "entwurf"))
        self.assertTrue((planansicht._zustaende(self.con, self.pid)[(self.m1, "plan")])["an"])
        stand = self.plan_stand()
        self.assertTrue(stand)
        self.entwurf(neu=False)
        planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.assertEqual(self.neues_paket(), "startklar")
        self.assertEqual(arbeitspaket.lesen(self.con, aid)["zustand"], "entwurf")
        self.assertEqual(self.plan_stand(), stand)

    def test_reines_aendern_startet_nichts(self):
        from amw import arbeitspaket, reihenfolge, verteilen
        aid = self.nachbar()
        self.m1_frei()
        arbeitspaket.zustand_setzen(self.con, self.pid, "TL", aid, "entwurf", grund="zurückgehalten")
        stand = self.plan_stand()
        self.entwurf(neu=False, meilensteine=[], pakete=[], aendern=[{"paket": f"A{self.p3}", "titel": "Passwort zurücksetzen", "auftrag": "Link mit Passkey.", "grund": "neu"}])
        with mock.patch.object(reihenfolge, "starten") as starten, mock.patch.object(verteilen, "verteilen") as vert:
            planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.assertFalse(starten.called or vert.called)
        self.assertEqual(arbeitspaket.lesen(self.con, aid)["zustand"], "entwurf")
        self.assertEqual(self.plan_stand(), stand)
        self.assertTrue(self.zustand(self.m1, "plan"))                                    # der freie Plan bleibt frei

    def test_fehlende_angaben_stehen_beim_lead_und_auf_der_seite(self):
        from amw import delta_start, projektweg_seite, reihenfolge
        self.m1_frei()
        for neu in (True, False):
            with self.subTest(neuer_meilenstein=neu):
                self.entwurf(neu=neu)
                with mock.patch.object(reihenfolge, "fehlende_felder", side_effect=lambda c, p, a: ["Bereiche"] if a["titel"] == "Passkey nachrüsten" else []):
                    planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid)
                    bid = self.bogen()["id"] if neu else self.m1
                    self.assertEqual(delta_start.unvollstaendig(self.con, self.pid).get(bid), ["Passkey nachrüsten"])
                    m = [x for x in projektweg_seite.daten(self.con, self.pid)["fein"]["meilensteine"] if x["bogen"] == bid][0]
                    self.assertEqual(m["start_fehlt"], ["Passkey nachrüsten"])
                kurz, text = self.post("TL")[-1][1:]
                self.assertIn("starten noch nicht", kurz)
                self.assertIn("Passkey nachrüsten: Bereiche", text)
                self.assertEqual(delta_start.unvollstaendig(self.con, self.pid), {})      # ergänzt: der Satz ist weg
                with db.schreiben(self.con):
                    self.con.execute("UPDATE aufgabe SET status = 'verworfen', beleg = 'Probe' WHERE titel = 'Passkey nachrüsten'")

    def test_war_der_plan_offen_bleibt_er_offen(self):
        self.entwurf(neu=False)                                                          # M1 nie freigegeben
        planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.assertFalse(self.zustand(self.m1, "plan"))
        self.assertNotEqual(self.neues_paket(), "startklar")

    def test_war_der_plan_geaendert_bleibt_er_offen(self):
        self.m1_frei()
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET titel = 'Abmelden neu' WHERE id = ?", (self.p2,))
        self.assertFalse(self.zustand(self.m1, "plan"))
        self.entwurf(neu=False)
        planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.assertFalse(self.zustand(self.m1, "plan"))

    def test_fremde_aenderung_waehrend_des_ja_wird_nicht_mit_freigegeben(self):
        self.m1_frei()
        self.entwurf(neu=False)
        echt = planer_delta.anwenden

        def anwenden(*a, **k):
            with db.schreiben(self.con):
                self.con.execute("UPDATE aufgabe SET auftrag = 'heimlich anders' WHERE id = ?", (self.p2,))
            return echt(*a, **k)
        with mock.patch.object(planer_delta, "anwenden", side_effect=anwenden):
            planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.assertFalse(self.zustand(self.m1, "plan"))
        art, kurz, text = self.post("TL")[-1]
        self.assertIn("nicht frei oder nicht gestartet", kurz)
        self.assertIn(f"A{self.p2}", text)

    def test_geplanter_meilenstein_mit_freiem_plan_bleibt_frei_startet_aber_nicht(self):
        self.m1_frei(aktiv=False)
        self.entwurf(neu=False)
        planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.assertTrue(self.zustand(self.m1, "plan"))
        self.assertEqual(self.con.execute("SELECT status FROM bogen WHERE id = ?", (self.m1,)).fetchone()[0], "geplant")

    def test_vier_rechte_faelle_bei_neuem_meilenstein(self):
        from amw import delta_start
        for grob, plan, darf in (("mensch", "mensch", False), ("mensch", "co+lead", False), ("co+lead", "mensch", False), ("co+lead", "co+lead", True)):
            with self.subTest(grob=grob, plan=plan):
                kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, grobplan_freigabe=grob, feinplan_freigabe=plan)
                eid = self.entwurf()
                e = (planer.letzter_entwurf(self.con, self.pid, self.tid) or {})["entwurf"]
                self.assertEqual(delta_start.wer(self.con, self.pid, e), ["Co", "TL"] if darf else [kern.entwickler_name(self.con, self.pid)])
                if not darf:
                    for wer in ("Co", "TL"):
                        with self.assertRaisesRegex(kern.AmwFehler, "der Mensch"):
                            planer.uebernehmen(self.con, self.pid, wer, self.tid)
                    self.assertFalse(planer.erledigt(self.con, self.pid, eid))
                    self.assertIsNone(self.con.execute("SELECT 1 FROM plan_ereignis WHERE art = ?", (planer_delta.STIMME,)).fetchone())
                    continue
                self.assertEqual(planer.uebernehmen(self.con, self.pid, "Co", self.tid), {"ja_fehlt": "Lead"})
                self.assertIsNone(self.bogen())
                planer.uebernehmen(self.con, self.pid, "TL", self.tid)
                self.assertEqual(self.bogen()["status"], "aktiv")
                f = [json.loads(r[0]) for r in self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'meilenstein_frei' AND bogen_id = ?",
                                                                (self.bogen()["id"],))]
                self.assertEqual([(x["durch"], x["regel_von"]) for x in f], [(["Co", "TL"], "B2913")] * 2)

    def test_ein_einzelnes_altes_ja_zaehlt_nicht_fuer_einen_neuen_entwurf(self):
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, grobplan_freigabe="co+lead", feinplan_freigabe="co+lead")
        self.entwurf()
        planer.uebernehmen(self.con, self.pid, "Co", self.tid)
        self.entwurf()
        self.assertEqual(planer.uebernehmen(self.con, self.pid, "TL", self.tid), {"ja_fehlt": "Co-Entwickler"})

    def test_bestehender_meilenstein_co_lead_ohne_grob_recht(self):
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, grobplan_freigabe="mensch", feinplan_freigabe="co+lead")
        self.m1_frei()
        self.entwurf(neu=False)
        planer.uebernehmen(self.con, self.pid, "Co", self.tid)
        planer.uebernehmen(self.con, self.pid, "TL", self.tid)
        self.assertTrue(self.zustand(self.m1, "plan"))

    def test_start_scheitert_steht_da_und_laesst_sich_nachholen(self):
        from amw import delta_start, reihenfolge
        eid = self.entwurf()
        with mock.patch.object(reihenfolge, "starten", side_effect=kern.AmwFehler("kein Platz")):
            planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid)
        b = self.bogen()
        self.assertEqual(b["status"], "geplant")
        self.assertEqual(delta_start.wartende(self.con, self.pid)[b["id"]]["fehler"], "kein Platz")
        self.assertIn("kein Platz", self.post("TL")[-1][2])
        with self.assertRaisesRegex(kern.AmwFehler, "schon angenommen"):
            planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid, eid=eid)
        with self.assertRaisesRegex(kern.AmwFehler, "der Mensch"):
            delta_start.nachholen(self.con, self.pid, "TL", b["id"])
        delta_start.nachholen(self.con, self.pid, kern.ENTWICKLER, b["id"])
        self.assertEqual(self.bogen()["status"], "aktiv")
        self.assertEqual(delta_start.wartende(self.con, self.pid), {})
        with self.assertRaisesRegex(kern.AmwFehler, "wartet nicht"):
            delta_start.nachholen(self.con, self.pid, kern.ENTWICKLER, b["id"])

    def test_altfall_ohne_freigabe_wartet_und_startet_nach_dem_klick(self):
        from amw import aktionen, delta_start, planansicht
        self.entwurf()
        with mock.patch.object(delta_start, "nach_dem_ja", return_value=None):           # wie vor A2080
            planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid)
        b = self.bogen()
        self.assertEqual((b["status"], self.zustand(b["id"], "plan")), ("geplant", False))
        self.assertEqual(list(delta_start.wartende(self.con, self.pid)), [b["id"]])
        planansicht.zurueck(self.con, self.pid, kern.ENTWICKLER, b["id"], "grob", "so nicht")
        self.assertEqual(delta_start.wartende(self.con, self.pid), {})                   # zurückgegeben: wartet nicht auf ihn
        with db.schreiben(self.con):
            self.con.execute("DELETE FROM plan_ereignis WHERE art = 'meilenstein_frei' AND bogen_id = ?", (b["id"],))
        aktionen.ausfuehren(self.con, self.pid, "/api/projektweg/delta-starten", {"bogen": b["id"]})
        self.assertEqual(self.bogen()["status"], "aktiv")
        self.assertTrue(self.zustand(b["id"], "grob") and self.zustand(b["id"], "plan"))

    def test_abbruch_beim_anlegen_startet_nichts(self):
        from amw import delta_start, projektweg_seite
        self.entwurf()
        with mock.patch.object(themen, "verweise_setzen", side_effect=kern.AmwFehler("Platte voll")):
            with self.assertRaisesRegex(kern.AmwFehler, "Platte voll"):
                planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.assertEqual(self.bogen()["status"], "geplant")
        self.assertEqual(delta_start.wartende(self.con, self.pid), {})                   # halb Angelegtes startet niemand mit einem Klick
        x = projektweg_seite._teilweise(self.con, self.pid, {self.tid: "Anmeldung"})
        self.assertEqual([(y["thema"], y["gruende"][0]["art"]) for y in x], [(self.tid, "teil_angelegt")])
        with self.assertRaisesRegex(kern.AmwFehler, "schon angenommen"):
            planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid)


class AbbruchBeimAnwenden(BlockGrund):
    """A2085: planer_delta.anwenden scheitert mittendrin – über planer.uebernehmen, mit und ohne neue Pakete."""
    def setUp(self):
        super().setUp()
        from amw import planung
        self.weitere = []
        for i in range(4):
            aid = planung.schritt_setzen(self.con, self.pid, "TL", titel=f"Altpaket {i}", auftrag="alt", bogen_id=self.m1, groesse="S", art="mechanisch")
            themen.verweise_setzen(self.con, self.pid, "TL", aid, [self.tid])
            self.weitere.append(aid)

    def scheitert(self, bei, neu):
        """Entwurf mit vier Änderungen (neu: dazu ein neues Paket); das Setzen des bei-ten Pakets scheitert."""
        from amw import planung
        mehr = {"aendern": [{"paket": f"A{a}", "titel": f"Neu {i}", "auftrag": "neu", "grund": "Passkey"} for i, a in enumerate(self.weitere)]}
        if not neu:
            mehr.update(meilensteine=[], pakete=[])
        eid = self.entwurf(neu=False, **mehr)
        echt, n = planung.schritt_setzen, [0]

        def setzen(con, pid, von, *a, **k):
            if k.get("aid") in self.weitere:
                n[0] += 1
                if n[0] == bei:
                    raise kern.AmwFehler("Platte voll")
            return echt(con, pid, von, *a, **k)
        with mock.patch.object(planung, "schritt_setzen", setzen):
            with self.assertRaisesRegex(kern.AmwFehler, "Platte voll"):
                planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid)
        return eid

    def titel(self):
        return [self.con.execute("SELECT titel FROM aufgabe WHERE id = ?", (a,)).fetchone()[0] for a in self.weitere]

    def ja(self):
        return [json.loads(r[0]) for r in self.con.execute("SELECT text FROM plan_ereignis WHERE art = ?", (planer.JA,))][1:]   # ohne das erste Ja (setUp)

    def test_erstes_paket_ohne_neue_nimmt_das_ja_zurueck(self):
        echt = planer._anlegen

        def anlegen(con, pid, *a, **k):                                     # ein Ereignis dazwischen: sonst trägt das Ja zufällig die Nummer der Marke
            with db.schreiben(con):
                db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="TL", art="probe", text="{}")
            return echt(con, pid, *a, **k)
        with mock.patch.object(planer, "_anlegen", anlegen):
            eid = self.scheitert(1, neu=False)
        self.assertEqual(self.ja(), [])
        self.assertFalse(planer.erledigt(self.con, self.pid, eid))
        self.assertEqual(self.titel(), [f"Altpaket {i}" for i in range(4)])
        planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid, eid=eid)                   # ein neues Ja geht
        self.assertEqual(self.titel(), [f"Neu {i}" for i in range(4)])
        self.assertTrue(planer.erledigt(self.con, self.pid, eid))

    def test_drittes_paket_ohne_neue_ist_vermerkt_und_gemeldet(self):
        from amw import projektweg_seite
        eid = self.scheitert(3, neu=False)
        a = self.weitere
        j = self.ja()[-1]
        self.assertEqual((j["abgebrochen"], j["geaendert"], j["offen"]), ("Platte voll", [f"A{a[0]}", f"A{a[1]}"], [f"A{a[2]}", f"A{a[3]}"]))
        art, kurz, text = self.post("TL")[-1]
        self.assertIn("nur teilweise", kurz)
        self.assertIn(f"Schon geändert: A{a[0]}, A{a[1]}", text)
        self.assertIn(f"noch offen: A{a[2]}, A{a[3]}", text)
        x = projektweg_seite._teilweise(self.con, self.pid, {self.tid: "Anmeldung"})
        self.assertEqual([g["art"] for g in x[0]["gruende"]], ["teil_geaendert", "teil_offen", "teil_lead"])
        self.assertIn("„Altpaket 2“, „Altpaket 3“", x[0]["gruende"][1]["x"]["x"])
        with self.assertRaisesRegex(kern.AmwFehler, "schon angenommen"):
            planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid, eid=eid)

    def test_erstes_paket_mit_neuem_bleibt_vermerkt(self):
        self.scheitert(1, neu=True)                                                                  # das neue Paket ist schon angelegt
        j = self.ja()[-1]
        self.assertEqual((j["geaendert"], len(j["offen"])), ([], 4))
        self.assertTrue(any(v.startswith("A") for v in j["angelegt"].values()))
        self.assertIn("nur teilweise", self.post("TL")[-1][1])

    def test_drittes_paket_mit_neuem_bleibt_vermerkt(self):
        self.scheitert(3, neu=True)
        j = self.ja()[-1]
        self.assertEqual((len(j["geaendert"]), len(j["offen"])), (2, 2))
        self.assertTrue(any(v.startswith("A") for v in j["angelegt"].values()))

    def halb(self, ziel, name, bei=1):
        """Der bei-te Aufruf von ziel.name scheitert, während das Ja das eine neue Paket in einem bestehenden Meilenstein anlegt."""
        eid = self.entwurf(neu=False)
        echt, n = getattr(ziel, name), [0]

        def scheitert(*a, **k):
            n[0] += 1
            if n[0] == bei:
                raise kern.AmwFehler("Platte voll")
            return echt(*a, **k)
        with mock.patch.object(ziel, name, scheitert):
            with self.assertRaisesRegex(kern.AmwFehler, "Platte voll"):
                planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid)
        return eid

    def pruefe_halb(self, eid):
        aid = self.con.execute("SELECT id FROM aufgabe WHERE titel = 'Passkey nachrüsten'").fetchall()
        self.assertEqual(len(aid), 1)
        j = self.ja()[-1]
        self.assertEqual((j["abgebrochen"], j["unfertig"], j["angelegt"]["N1"]), ("Platte voll", ["N1"], f"A{aid[0][0]}"))
        self.assertIn(f"N1 → A{aid[0][0]} (vielleicht unvollständig)", self.post("TL")[-1][2])
        with self.assertRaisesRegex(kern.AmwFehler, "schon angenommen"):                             # kein doppeltes Paket
            planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid, eid=eid)
        self.assertEqual(len(self.con.execute("SELECT id FROM aufgabe WHERE titel = 'Passkey nachrüsten'").fetchall()), 1)

    def test_erstes_neues_paket_halb_angelegt_arbeitspaket(self):
        from amw import arbeitspaket
        self.pruefe_halb(self.halb(arbeitspaket, "setzen"))

    def test_erstes_neues_paket_halb_angelegt_zweite_transaktion(self):
        from amw import planung
        echt, n = db.schreiben, [0]

        def schreiben(con):
            if n[0] >= 0 and con.execute("SELECT 1 FROM aufgabe WHERE titel = 'Passkey nachrüsten'").fetchone():
                n[0] = -1                                                                            # die Aufgabe ist da, die Werte fehlen noch
                raise kern.AmwFehler("Platte voll")
            return echt(con)
        eid = self.entwurf(neu=False)
        with mock.patch.object(planung.db, "schreiben", schreiben):
            with self.assertRaisesRegex(kern.AmwFehler, "Platte voll"):
                planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.pruefe_halb(eid)

    def test_halb_angelegter_neuer_meilenstein(self):
        from amw import planung
        eid = self.entwurf()
        with mock.patch.object(planung, "bogen_zeile", side_effect=kern.AmwFehler("Platte voll")):   # der Meilenstein ist da, seine Nummer noch nicht notiert
            with self.assertRaisesRegex(kern.AmwFehler, "Platte voll"):
                planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid)
        j = self.ja()[-1]
        self.assertEqual((j["unfertig"], j["offen_neu"]), (["M2"], ["Passkey nachrüsten"]))
        with self.assertRaisesRegex(kern.AmwFehler, "schon angenommen"):
            planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid, eid=eid)

    def test_noch_nicht_angelegte_neue_pakete_stehen_da(self):
        from amw import planung, projektweg_seite
        fuenf = [{**self.paket("M1"), "schluessel": f"N{i}", "titel": t, "bereiche": f"app/passkey_{i}.py"} for i, t in enumerate(   # A2133: je eine Datei
            ("Schlüssel speichern", "Anzeige im Profil", "Gerät entfernen", "Mail bei neuem Gerät", "Hilfe schreiben"))]
        self.entwurf(neu=False, pakete=fuenf)
        echt, n = planung.schritt_setzen, [0]

        def setzen(*a, **k):
            n[0] += 1
            if n[0] == 3:
                raise kern.AmwFehler("Platte voll")
            return echt(*a, **k)
        with mock.patch.object(planung, "schritt_setzen", setzen):
            with self.assertRaisesRegex(kern.AmwFehler, "Platte voll"):
                planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid)
        j = self.ja()[-1]
        self.assertEqual((j["offen_neu"], j["unfertig"]), (["Gerät entfernen", "Mail bei neuem Gerät", "Hilfe schreiben"], []))
        self.assertIn("Noch nicht angelegt: „Gerät entfernen“, „Mail bei neuem Gerät“, „Hilfe schreiben“", self.post("TL")[-1][2])
        x = projektweg_seite._teilweise(self.con, self.pid, {self.tid: "Anmeldung"})[0]["gruende"]
        self.assertIn("„Gerät entfernen“, „Mail bei neuem Gerät“", next(g for g in x if g["art"] == "teil_offen")["x"]["x"])

    def test_verwerfen_scheitert_nach_einer_aenderung(self):
        a = self.weitere
        self.entwurf(neu=False, meilensteine=[], pakete=[], aendern=[{"paket": f"A{a[0]}", "titel": "Neu 0", "auftrag": "neu", "grund": "Passkey"}],
                     verwerfen=[{"paket": f"A{a[1]}", "grund": "entfällt"}])
        with mock.patch.object(kern, "aufgabe_status", side_effect=kern.AmwFehler("gesperrt")):
            with self.assertRaisesRegex(kern.AmwFehler, "gesperrt"):
                planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.tid)
        j = self.ja()[-1]
        self.assertEqual((j["geaendert"], j["verworfen"], j["offen"]), ([f"A{a[0]}"], [], [f"A{a[1]}"]))


if __name__ == "__main__":
    unittest.main()
