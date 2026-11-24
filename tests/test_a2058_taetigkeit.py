"""A2058: Fensterkosten je Tätigkeit – bei jedem Wechsel (Aufgabe start/wartet/fertig, Prüfbitte, eigener Lauf, roter Lauf,
Auslieferung) eine Marke; jeder Zuwachs des Sitzungs-Zählers gehört zur letzten Marke davor. Die Prognose-Warnung vergleicht nur
„bauen“; `amw messung --kosten` zeigt je Tag und Tätigkeit. Ohne Marke (Gegenprobe) bleibt alles „bauen“ wie bisher."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import aufwand, db, kern, messung, taetigkeit, wartegrund


def z(stunde, minute=0):
    return f"2026-11-24T{stunde:02d}:{minute:02d}:00Z"


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
        with db.schreiben(self.con):
            self.aid = db.einfuegen(self.con, "aufgabe", projekt_id=self.pid, titel="Bauen", agent="CC1", angelegt_von="TL",
                                    angelegt_utc=z(8), status="laeuft", begonnen_utc=z(8))

    def marke(self, zeit, tk, aufgabe=None):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=zeit, von="CC1", art=taetigkeit.ART, aufgabe_id=aufgabe,
                         text=json.dumps({"taetigkeit": tk, "aufgabe": aufgabe}))

    def messen(self, punkte):
        gid = kern.agent_zeile(self.con, self.pid, "CC1")["id"]
        with db.schreiben(self.con):
            sid = db.einfuegen(self.con, "sitzung", agent_id=gid, gestartet_utc=punkte[0][0], modell="Opus 5.5", denkstufe="high")
            for zeit, usd in punkte:
                db.einfuegen(self.con, "verbrauch", sitzung_id=sid, agent="CC1", zeit_utc=zeit, kosten_usd=usd)


class Zuordnen(Grund):
    def test_abschnitte_je_taetigkeit(self):
        self.marke(z(8), "bauen", self.aid)
        self.marke(z(10), "pruefen_lassen", self.aid)
        self.marke(z(11), "stapeln", self.aid)
        self.messen([(z(8, 5), 0.0), (z(9), 4.0), (z(10, 30), 5.0), (z(11, 30), 8.0)])
        a = aufwand.je_aufgabe(self.con, self.pid, self.aid) or {}
        self.assertEqual((a["usd"], a["bauen_usd"]), (8.0, 4.0))
        self.assertEqual(a["taetigkeiten"], {"bauen": 4.0, "pruefen_lassen": 1.0, "stapeln": 3.0})
        m = messung.kosten(self.con, self.pid, self.aid) or {}
        self.assertEqual((m["usd"], m["bauen_usd"]), (8.0, 4.0))                                  # Prognose nur auf „bauen“
        self.assertEqual(taetigkeit.je_tag(self.con, self.pid), {"2026-11-24": {"bauen": 4.0, "pruefen_lassen": 1.0, "stapeln": 3.0}})

    def test_ohne_marke_alles_bauen(self):
        self.messen([(z(8, 5), 0.0), (z(9), 4.0)])
        self.assertEqual(aufwand.je_aufgabe(self.con, self.pid, self.aid), {"usd": 4.0, "modelle": ["Opus 5.5/high"]})   # wie bisher
        self.assertEqual((messung.kosten(self.con, self.pid, self.aid) or {})["bauen_usd"], 4.0)


class Marken(Grund):
    def letzte(self):
        r = self.con.execute("SELECT text FROM plan_ereignis WHERE art = ? ORDER BY id DESC LIMIT 1", (taetigkeit.ART,)).fetchone()
        return json.loads(r[0])["taetigkeit"] if r else None

    def test_wechsel_setzen_marken(self):
        kern.aufgabe_status(self.con, self.pid, "CC1", self.aid, "wartet", auf="TL")
        self.assertEqual(self.letzte(), "warten")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.aid, "start")
        self.assertEqual(self.letzte(), "bauen")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.aid, "wartet", auf="stapel:stapel9")
        self.assertEqual(self.letzte(), "stapeln")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.aid, "start")
        from amw import betrieb
        lid = betrieb.lauf_start(self.con, self.pid, "CC1", "Gesamtlauf", schwer=False, aufgabe_id=self.aid, warten=True, speicher_frei=32.0)
        self.assertEqual(self.letzte(), "warten")
        betrieb.lauf_ende(self.con, self.pid, "CC1", lid, 1, "rot")
        self.assertEqual(self.letzte(), "fehlersuche")
        n = self.con.execute("SELECT count(*) FROM plan_ereignis WHERE art = ?", (taetigkeit.ART,)).fetchone()[0]
        taetigkeit.merken(self.con, self.pid, "CC1", "fehlersuche", self.aid)                     # gleiche Marke: keine neue
        self.assertEqual(self.con.execute("SELECT count(*) FROM plan_ereignis WHERE art = ?", (taetigkeit.ART,)).fetchone()[0], n)
        kern.aufgabe_status(self.con, self.pid, "CC1", self.aid, "fertig", beleg="abc1234")
        self.assertEqual(self.letzte(), "sonstiges")

    def test_befehl(self):
        from amw import cli
        self.marke("2026-11-24T08:00:00Z", "bauen", self.aid)
        self.messen([(db.jetzt(), 0.0), (db.jetzt(), 2.5)])
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_AGENT": ""}), contextlib.redirect_stdout(aus):
            rc = cli.main(["messung", "--kosten", "--projekt", "P", "--von", "TL"])
        self.assertEqual(rc, 0, aus.getvalue())
        self.assertIn("prüfen lassen", aus.getvalue())
        self.assertIn("2.50", aus.getvalue())


if __name__ == "__main__":
    unittest.main()
