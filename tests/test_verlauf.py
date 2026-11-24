"""Tests für Rückblick, Verlauf, Zusammenfassung „seit“ und den täglichen Push-Rückblick."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import copy
import datetime
import os
import tempfile
import unittest
from unittest import mock

from amw import db, kern, planung, push, verlauf


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        for k, r in (("TL", "lead"), ("CC1", None)):
            kern.agent_neu(self.con, self.pid, k, rolle=r)
        self.bid = planung.bogen_neu(self.con, self.pid, "TL", "Login")

    def tearDown(self):
        self.con.close()
        self.ordner.cleanup()


class Rueckblick(Grund):
    def test_eintraege_und_massnahme_wird_aufgabe_oder_beschluss(self):
        verlauf.rueckblick_neu(self.con, self.pid, "CC1", self.bid, "gut", "Tests früh geschrieben")
        m1 = verlauf.rueckblick_neu(self.con, self.pid, "TL", self.bid, "massnahme", "Spezifikation früher vorlegen")
        m2 = verlauf.rueckblick_neu(self.con, self.pid, "TL", self.bid, "massnahme", "Prüfbefehl je Schritt Pflicht")
        with self.assertRaises(kern.AmwFehler):
            verlauf.rueckblick_neu(self.con, self.pid, "TL", self.bid, "toll", "x")
        aid = verlauf.massnahme_uebernehmen(self.con, self.pid, "CC1", m1, "aufgabe", "CC1")
        self.assertIn("Rückblick", self.con.execute("SELECT auftrag FROM aufgabe WHERE id = ?", (aid,)).fetchone()[0])
        with self.assertRaises(kern.AmwFehler):
            verlauf.massnahme_uebernehmen(self.con, self.pid, "CC1", m1, "aufgabe")       # schon übernommen
        with self.assertRaises(kern.AmwFehler):
            verlauf.massnahme_uebernehmen(self.con, self.pid, "CC1", m2, "beschluss")     # Beschlüsse nur Lead
        b = verlauf.massnahme_uebernehmen(self.con, self.pid, "TL", m2, "beschluss")
        self.assertEqual(self.con.execute("SELECT thema FROM beschluss WHERE id = ?", (b,)).fetchone()[0], "Lessons Learned")
        self.assertEqual([r["art"] for r in verlauf.rueckblicke(self.con, self.pid, self.bid)], ["gut", "massnahme", "massnahme"])


class Projektweg(Grund):
    """A2024: „wer hat was getan“ im Projektweg – Mensch, AMW, Planer, Prüfer, Agent – mit Uhrzeit und Text, zeitlich."""

    def test_eigens_gespeichert_jede_rolle_mit_zeit_und_text(self):
        a = kern.aufgabe_neu(self.con, self.pid, "TL", "Bauen", "CC1")
        werte = [("mensch", None, "Konzept abgeschlossen"), ("amw", None, "Grobplanung gestartet"), ("planer", None, "Plan steht"),
                 ("agent", "CC1", "Test geschrieben"), ("pruefer", "TL", "Prüfung grün")]
        ids = [verlauf.ereignis(self.con, self.pid, r, t, von=v, aufgabe_id=a) for r, v, t in werte]
        self.assertEqual(len(set(ids)), 5)
        weg = verlauf.projektweg(self.con, self.pid)
        self.assertEqual([(e["rolle"], e["text"]) for e in weg], [(r, t) for r, _, t in werte])
        self.assertEqual([e["von"] for e in weg], [kern.ENTWICKLER, "AMW", "Planer", "CC1", "TL"])
        for e in weg:
            self.assertRegex(e["zeit"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
            self.assertEqual(e["aufgabe_id"], a)

    def test_ganzer_weg_in_zeitlicher_reihenfolge(self):
        verlauf.ereignis(self.con, self.pid, "pruefer", "spät", von="TL", zeit_utc="2026-01-03T10:00:00Z")
        verlauf.ereignis(self.con, self.pid, "mensch", "früh", zeit_utc="2026-01-01T08:00:00Z")
        verlauf.ereignis(self.con, self.pid, "agent", "mittel 1", von="CC1", zeit_utc="2026-01-02T09:00:00Z")
        verlauf.ereignis(self.con, self.pid, "amw", "mittel 2", zeit_utc="2026-01-02T09:00:00Z")   # gleiche Sekunde: Eingang zählt
        self.assertEqual([e["text"] for e in verlauf.projektweg(self.con, self.pid)], ["früh", "mittel 1", "mittel 2", "spät"])
        self.assertEqual([e["text"] for e in verlauf.projektweg(self.con, self.pid, ab_utc="2026-01-02T00:00:00Z",
                                                                bis_utc="2026-01-03T00:00:00Z")], ["mittel 1", "mittel 2"])
        self.assertEqual([e["text"] for e in verlauf.projektweg(self.con, self.pid, rolle="agent")], ["mittel 1"])
        with db.schreiben(self.con):
            p2 = db.einfuegen(self.con, "projekt", name="Q", angelegt_utc=db.jetzt())
        verlauf.ereignis(self.con, p2, "mensch", "fremd")
        self.assertNotIn("fremd", [e["text"] for e in verlauf.projektweg(self.con, self.pid)])

    def test_ungueltiges_wird_abgelehnt(self):
        for args, kw in ((("chef", "x"), {}), (("mensch", "  "), {}), (("agent", "x"), {}),
                         (("amw", "x"), {"zeit_utc": "gestern"}), (("amw", "x"), {"aufgabe_id": 999}),
                         (("amw", "x"), {"bogen_id": 999})):
            with self.assertRaises(kern.AmwFehler, msg=str(args)):
                verlauf.ereignis(self.con, self.pid, *args, **kw)
        self.assertEqual(verlauf.projektweg(self.con, self.pid), [])
        with self.assertRaises(kern.AmwFehler):
            verlauf.projektweg(self.con, self.pid, rolle="chef")

    def test_was_die_amw_schon_festhaelt_wird_gelesen_nicht_doppelt(self):
        """Themen, Gegenlesen, Planer und Meilenstein-Freigaben stehen schon in der AMW – der Weg liest sie mit Rolle und Text."""
        from amw import planansicht, planer, themen
        tid = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", tid, "Wer die Seite öffnet, meldet sich an.")
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, tid)
        with db.schreiben(self.con):
            planer._ereignis(self.con, self.pid, "AMW", planer.ANGESTOSSEN, tid, fassung=1, modell="sonnet")
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="TL", art="thema_gegengelesen",
                         text='{"thema": %d, "fassung": 1}' % tid)
        planer.entwurf_eintragen(self.con, self.pid, tid, 1, None, modell="sonnet", fehler=["kein JSON"])
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="TL", art=planansicht.JA,
                         bogen_id=self.bid, text='{"bogen": %d, "art": "grob", "rolle": "lead"}' % self.bid)
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von=kern.ENTWICKLER,
                         art=planansicht.FREI, bogen_id=self.bid, text='{"bogen": %d, "art": "plan", "an": true}' % self.bid)
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="TL", art="bogen_status",
                         bogen_id=self.bid, text="nicht im Projektweg")
        nr = self.con.execute("SELECT nr FROM bogen WHERE id = ?", (self.bid,)).fetchone()[0]
        weg = [(e["rolle"], e["von"], e["text"]) for e in verlauf.projektweg(self.con, self.pid)]
        self.assertIn(("agent", "CC1", f"TH{tid} Fassung 1 vorgelegt"), weg)
        self.assertIn(("mensch", kern.ENTWICKLER, f"TH{tid} freigegeben"), weg)
        self.assertIn(("amw", "AMW", f"TH{tid} Fassung 1: Planer angestoßen"), weg)
        self.assertIn(("pruefer", "TL", f"TH{tid} Fassung 1 gegengelesen"), weg)
        self.assertIn(("planer", "AMW", f"TH{tid} Fassung 1: Planer meldet einen Fehler"), weg)
        self.assertIn(("agent", "TL", f"M{nr}: Ja zu Grobplan (Lead)"), weg)
        self.assertIn(("mensch", kern.ENTWICKLER, f"M{nr}: Feinplan freigegeben"), weg)
        self.assertNotIn("nicht im Projektweg", [t for _, _, t in weg])
        self.assertEqual(len(weg), len({e["id"] for e in verlauf.projektweg(self.con, self.pid)}))
        self.assertEqual([e["zeit"] for e in verlauf.projektweg(self.con, self.pid)],
                         sorted(e["zeit"] for e in verlauf.projektweg(self.con, self.pid)))
        self.assertEqual([t for r, _, t in weg if r == "mensch"],
                         [e["text"] for e in verlauf.projektweg(self.con, self.pid, rolle="mensch")])


class Verlauf(Grund):
    def test_ereignisse_aus_vielen_quellen_filter_und_zusammenfassung(self):
        ab = db.jetzt()
        kern.posten(self.con, self.pid, "TL", "CC1", "auftrag", "bitte bauen")
        a = kern.aufgabe_neu(self.con, self.pid, "TL", "Bauen", "CC1")
        kern.aufgabe_status(self.con, self.pid, "CC1", a, "fertig", beleg="abc")
        kern.frage_neu(self.con, self.pid, "TL", "entwickler", "Wie?", [("A", "so")], "A", "weil", geprueft="keine Treffer")
        planung.bogen_status(self.con, self.pid, "TL", self.bid, "aktiv")
        alle = verlauf.verlauf(self.con, self.pid, ab)
        arten = {x["art"] for x in alle}
        self.assertTrue({"nachricht", "erledigt", "frage", "plan"} <= arten)
        self.assertEqual({x["wer"] for x in verlauf.verlauf(self.con, self.pid, ab, agent="CC1")}, {"CC1"})
        self.assertEqual({x["art"] for x in verlauf.verlauf(self.con, self.pid, ab, arten=["erledigt"])}, {"erledigt"})
        z = verlauf.zusammenfassung(self.con, self.pid, ab)
        self.assertEqual((z["erledigt"], z["fragen_neu"], z["fragen_offen"]), (1, 1, 1))
        self.assertIn("1 erledigt", verlauf.kurztext(z))

    def test_erledigt_zeigt_wer_abgeschlossen_hat(self):
        from amw import cli
        a1 = kern.aufgabe_neu(self.con, self.pid, "TL", "selbst", agent="CC1")
        a2 = kern.aufgabe_neu(self.con, self.pid, "TL", "vom Lead", agent="CC1")
        kern.aufgabe_status(self.con, self.pid, "CC1", a1, "fertig", beleg="abc")
        kern.aufgabe_status(self.con, self.pid, "TL", a2, "fertig", beleg="def")
        ab = "2000-01-01T00:00:00Z"
        wer = {x["ref"]: x["wer"] for x in verlauf.verlauf(self.con, self.pid, ab, arten=["erledigt"])}
        self.assertEqual((wer[f"A{a1}"], wer[f"A{a2}"]), ("CC1", "TL"))
        self.assertFalse([x for x in verlauf.verlauf(self.con, self.pid, ab, arten=["plan"]) if x["zusatz"] == "aufgabe_abschluss"])
        a = cli.parser().parse_args(["aufgabe", "neu", "--titel", "danach", "--abhaengig-von", f"{a1},A{a2}", "--pruefer", "TL"])
        werte, nach = cli._schritt_werte(a)                                            # alter Name = --nach
        self.assertEqual((nach, werte["pruefer"]), ([a1, a2], "TL"))

    def test_seit_online_rechnet_wie_am_pc(self):
        ab = db.jetzt()
        kern.posten(self.con, self.pid, "TL", "entwickler", "info", "für dich")
        for t in ("Eins", "Zwei"):
            a = kern.aufgabe_neu(self.con, self.pid, "TL", t, "CC1")
            kern.aufgabe_status(self.con, self.pid, "CC1", a, "fertig", beleg="abc")
        kern.frage_neu(self.con, self.pid, "TL", "entwickler", "Wie?", [("A", "so")], "A", "weil", geprueft="keine Treffer")
        d = verlauf.seit_daten(self.con, self.pid)
        for grenze in (ab, "2000-01-01T00:00:00Z", "2999-01-01T00:00:00Z"):
            pc = verlauf.zusammenfassung(self.con, self.pid, grenze)
            online = verlauf.seit_zaehlen(d, grenze)
            self.assertEqual({k: pc[k] for k in online}, online, grenze)
        self.assertEqual(verlauf.seit_zaehlen(d, ab)["erledigt"], 2)
        wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(wurzel, "web", "api.php"), encoding="utf-8") as f:
            php = f.read()
        self.assertIn(str(list(verlauf.SEIT_ARTEN)).replace('"', "'"), php.replace("array_fill_keys(", "").replace(", 0)", ""))

    def test_taeglicher_push_rueckblick_einmal_ab_uhrzeit(self):
        cfg = copy.deepcopy(push.VORGABE)                  # nie die echte push.json dieses PCs
        cfg.update(an=True, seit_utc="2000-01-01T00:00:00Z", rueckblick_uhr="00:00")
        heute = datetime.date.today().isoformat()
        keys = [e["schluessel"] for e in push.ereignisse(self.con, self.pid, cfg)]
        self.assertNotIn(f"rueckblick:{heute}", keys)                    # nichts passiert: kein Rückblick voller Nullen
        kern.posten(self.con, self.pid, "TL", "Entwickler", "info", "Hallo")
        keys = [e["schluessel"] for e in push.ereignisse(self.con, self.pid, cfg)]
        self.assertIn(f"rueckblick:{heute}", keys)
        cfg["rueckblick_uhr"] = "23:59"
        with mock.patch.object(push.datetime, "datetime", wraps=datetime.datetime) as dt:
            dt.now.side_effect = lambda tz=None: datetime.datetime(2026, 11, 2, 7, 0, tzinfo=tz)
            keys = [e["schluessel"] for e in push.ereignisse(self.con, self.pid, cfg)]
        self.assertFalse(any(k.startswith("rueckblick:") for k in keys))


if __name__ == "__main__":
    unittest.main()
