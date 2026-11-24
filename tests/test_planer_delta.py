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


if __name__ == "__main__":
    unittest.main()
