"""Tests für Rückblick, Verlauf, Zusammenfassung „seit“ und den täglichen Push-Rückblick."""
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


class Verlauf(Grund):
    def test_ereignisse_aus_vielen_quellen_filter_und_zusammenfassung(self):
        ab = db.jetzt()
        kern.posten(self.con, self.pid, "TL", "CC1", "auftrag", "bitte bauen")
        a = kern.aufgabe_neu(self.con, self.pid, "TL", "Bauen", "CC1")
        kern.aufgabe_status(self.con, self.pid, "CC1", a, "fertig", beleg="abc")
        kern.frage_neu(self.con, self.pid, "TL", "entwickler", "Wie?", [("A", "so")], "A", "weil")
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
        kern.frage_neu(self.con, self.pid, "TL", "entwickler", "Wie?", [("A", "so")], "A", "weil")
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
