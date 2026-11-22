"""A1925 (W2449, Mehrprojekt 7): Disponent über Projekte – Rangfolge des Menschen (PC-Einstellung projekt_rang), gemeinsame
Grenze für p-Arbeiter (plaetze_pc, Regel 4 mit sichtbarem Warten), Projekt-Schalter (Regel 12), Wochenlimit und limit_halt
für das eine Konto, Kosten je Projekt (amw pc, Wochenbericht). Zwei Projekte; der Start selbst ist eine Attrappe."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import arbeitspaket, cli, db, disponent, einstellungen, kern, waechter


class Projekte(unittest.TestCase):
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
        self.pid = {}
        for name in ("GlassWorld", "AMW"):                                  # Nummer 1 = GlassWorld, 2 = AMW
            with db.schreiben(self.con):
                self.pid[name] = db.einfuegen(self.con, "projekt", name=name, angelegt_utc=db.jetzt())
            p = self.pid[name]
            kern.agent_neu(self.con, p, "TL", rolle="lead")
            kern.agent_neu(self.con, p, "CC1")
            o = os.path.join(self.ordner.name, name)
            os.makedirs(o)
            kern.projekt_ordner_setzen(self.con, p, o)
            kern.projekt_einstellen(self.con, p, kern.ENTWICKLER, platz_wurzel=os.path.join(self.ordner.name, f"plaetze-{name}"), plaetze=2)
        self.gestartet = []
        s = mock.patch.object(disponent, "starten", side_effect=self.starten)
        s.start()
        self.addCleanup(s.stop)

    def starten(self, con, pid, aid, p, quelle, prog=None, umgebung=None):
        self.gestartet.append((pid, aid))
        arbeitspaket.zustand_setzen(con, pid, "AMW", aid, "laeuft")
        return f"A{aid} gestartet"

    def paket(self, name, bereich="lib/"):
        p = self.pid[name]
        aid = kern.aufgabe_neu(self.con, p, "TL", f"Paket {name}", "TL")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET pruefbefehl = 'python -m unittest', dateibereich = ? WHERE id = ?", (bereich, aid))
        arbeitspaket.setzen(self.con, p, "TL", aid, art="p")
        arbeitspaket.zustand_setzen(self.con, p, "TL", aid, "startklar")
        return aid

    def runde(self):
        return disponent.runde(self.con, prog=["attrappe"])

    def test_rangfolge_des_menschen(self):
        self.assertEqual([n for _, n in disponent.projekt_reihe(self.con)], ["GlassWorld", "AMW"])     # ohne Einstellung: Nummer
        einstellungen.speichern({"projekt_rang": "amw, LayerIT, glassworld"})                         # Groß/klein egal, fremde Namen ok
        self.assertEqual([n for _, n in disponent.projekt_reihe(self.con)], ["AMW", "GlassWorld"])
        g, a = self.paket("GlassWorld"), self.paket("AMW")
        self.runde()
        self.assertEqual(self.gestartet, [(self.pid["AMW"], a), (self.pid["GlassWorld"], g)])          # AMW zuerst

    def test_pc_grenze_vorderes_projekt_zuerst_hinteres_wartet_sichtbar(self):
        einstellungen.speichern({"projekt_rang": ["AMW", "GlassWorld"], "plaetze_pc": 1})
        g, a = self.paket("GlassWorld"), self.paket("AMW")
        self.runde()
        self.assertEqual(self.gestartet, [(self.pid["AMW"], a)])
        r = waechter.pruefen(self.con, self.pid["GlassWorld"], g, limit=10)
        self.assertEqual(r["regel"], 4)
        self.assertIn(f"wartet auf einen Platz (PC: 1 von 1 belegt: AMW A{a})", r["grund"])
        self.assertTrue(r["warten"])
        arbeitspaket.zustand_setzen(self.con, self.pid["AMW"], "AMW", a, "abgegeben")
        arbeitspaket.zustand_setzen(self.con, self.pid["AMW"], "AMW", a, "abnahme")
        self.runde()
        self.assertEqual(len(self.gestartet), 1)                                                     # Prüfung C arbeitet noch
        arbeitspaket.zustand_setzen(self.con, self.pid["AMW"], "AMW", a, "merge_reihe")
        self.runde()
        self.assertEqual(self.gestartet[-1], (self.pid["GlassWorld"], g))                             # nach dem Ende: das hintere

    def test_ohne_grenze_wie_bisher(self):
        self.paket("GlassWorld")
        self.paket("AMW")
        self.runde()
        self.assertEqual(len(self.gestartet), 2)

    def test_schalter_aus_und_probe(self):
        for wert in ("aus", "probe"):
            with db.schreiben(self.con):
                self.con.execute("UPDATE projekt SET einstellungen = json_set(einstellungen, '$.schalter', ?) WHERE id = ?",
                                 (wert, self.pid["GlassWorld"]))
            g = self.paket("GlassWorld", bereich=f"{wert}/")
            r = waechter.pruefen(self.con, self.pid["GlassWorld"], g, limit=10)
            self.assertEqual((r["regel"], r["grund"]), (12, f"Projekt ausgeschaltet (Projekt-Schalter aus oder probe) – Schalter {wert}"))
        a = self.paket("AMW")
        self.runde()
        self.assertEqual(self.gestartet, [(self.pid["AMW"], a)])
        self.assertEqual(kern.projekt_schalter(self.con, self.pid["AMW"]), "an")                      # ohne Eintrag: an

    def test_wochenlimit_ein_konto(self):
        g, a = self.paket("GlassWorld"), self.paket("AMW")
        from amw import tokenprognose
        with mock.patch.object(tokenprognose, "lage_gemerkt", return_value={"wert": 85.0}):
            for name, aid in (("GlassWorld", g), ("AMW", a)):
                self.assertEqual(waechter.pruefen(self.con, self.pid[name], aid)["regel"], 8, name)
            self.runde()
        self.assertEqual(self.gestartet, [])

    def test_limit_halt_pc_weit(self):
        from amw import limithalt
        einstellungen.speichern({"limit_halt": 90})
        kern.projekt_einstellen(self.con, self.pid["AMW"], "TL", limit_halt=80)                     # strenger: zählt
        kern.projekt_einstellen(self.con, self.pid["GlassWorld"], "TL", limit_halt=99)              # milder: zählt nicht
        self.assertEqual((limithalt.schwelle(self.con, self.pid["AMW"]), limithalt.schwelle(self.con, self.pid["GlassWorld"])), (80, 90))

    def kosten(self, name, aid, usd, zeit):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid[name], zeit_utc=zeit, von="AMW", art="kosten", aufgabe_id=aid,
                         text=json.dumps({"usd": usd}))

    def test_kosten_je_projekt_und_wochenbericht(self):
        import datetime
        a, g = self.paket("AMW"), self.paket("GlassWorld")
        jetzt = datetime.datetime(2026, 11, 23, 8, 0, tzinfo=datetime.timezone.utc)                    # Montag
        self.kosten("AMW", a, 1.25, "2026-11-18T10:00:00Z")
        self.kosten("AMW", a, 0.75, "2026-11-20T10:00:00Z")
        self.kosten("GlassWorld", g, 3.0, "2026-11-23T07:00:00Z")                                       # schon diese Woche
        self.assertEqual(disponent.kosten_woche(self.con, self.pid["AMW"], "2026-11-16T00:00:00Z", "2026-11-23T00:00:00Z"),
                         {"usd": 2.0, "pakete": 1})
        einstellungen.speichern({"projekt_rang": ["AMW", "GlassWorld"]})
        t = disponent.wochenbericht(self.con, jetzt)
        self.assertEqual(t, "Woche ab 2026-11-16 – p-Pakete je Projekt (Rangfolge):\n1. AMW: 2.00 $ · 1 Paket(e)\n2. GlassWorld: 0.00 $ · 0 Paket(e)")
        m = self.con.execute("SELECT n.projekt_id, n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id"
                             " WHERE e.agent = ? AND n.kurz LIKE 'Wochenbericht%'", (kern.ENTWICKLER,)).fetchall()
        self.assertEqual([(r[0], r[1]) for r in m], [(self.pid["AMW"], "Wochenbericht Arbeitsplätze ab 2026-11-16")])
        self.assertIsNone(disponent.wochenbericht(self.con, jetzt))                                    # einmal je Woche
        t = disponent.wochenbericht(self.con, jetzt + datetime.timedelta(days=7))                       # nächste Woche: GlassWorld
        self.assertIn("2. GlassWorld: 3.00 $ · 1 Paket(e)", t)
        self.assertIsNone(disponent.wochenbericht(self.con, jetzt + datetime.timedelta(days=14)))       # nichts gelaufen: kein Bericht
        self.assertEqual(len(self.con.execute("SELECT 1 FROM nachricht WHERE kurz LIKE 'Wochenbericht%'").fetchall()), 2)

    def cli(self, *argv, sitzung=False):
        aus = io.StringIO()
        umg = {"AMW_AGENT": "", "CLAUDECODE": "1" if sitzung else "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}
        with mock.patch.dict(os.environ, umg), contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "AMW", *argv])
        return rc, aus.getvalue()

    def test_cli_rechte_und_anzeige(self):
        rc, aus = self.cli("--von", "Entwickler", "pc", "einstellen", "projekt_rang=AMW,GlassWorld", sitzung=True)
        self.assertNotEqual(rc, 0)
        self.assertIn("nur der Mensch im eigenen Terminal", aus)
        rc, aus = self.cli("--von", "TL", "pc", "einstellen", "projekt_rang=AMW")                       # auch der Lead nicht
        self.assertNotEqual(rc, 0)
        self.assertEqual(einstellungen.wert("projekt_rang"), [])
        self.assertEqual(self.cli("--von", "Entwickler", "pc", "einstellen", "projekt_rang=AMW,GlassWorld")[0], 0)
        self.assertEqual(self.cli("--von", "TL", "pc", "einstellen", "plaetze_pc=3")[0], 0)            # Lead darf
        rc, aus = self.cli("--von", "CC1", "pc", "einstellen", "plaetze_pc=1")
        self.assertNotEqual(rc, 0)
        rc, aus = self.cli("--von", "Entwickler", "pc", "einstellen", "plaetze_pc=1", sitzung=True)     # Mensch nur im Terminal
        self.assertNotEqual(rc, 0)
        rc, aus = self.cli("--von", "TL", "pc", "einstellen", "port=9999")
        self.assertIn("im Zahnrad", aus)
        self.assertEqual(einstellungen.wert("plaetze_pc"), 3)
        rc, aus = self.cli("--von", "CC1", "pc")
        self.assertEqual(rc, 0)
        self.assertIn("Rangfolge: AMW, GlassWorld", aus)
        self.assertIn("p-Arbeiter: 0 von 3 (plaetze_pc)", aus)
        self.assertIn("1. AMW: Schalter an · 2 Plätze · diese Woche 0.00 $ in 0 Paket(en)", aus)


if __name__ == "__main__":
    unittest.main()
