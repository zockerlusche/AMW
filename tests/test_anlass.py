"""Verbrauch nach Anlass (A1642): Kostenzuwachs je Sitzung gehört zu den Weckrufen im selben Zeitraum (mehrere: geteilt),
sonst zur eigenen Arbeit; Arten und „vermeidbar“; Pareto-Reihenfolge; amw verbrauch pareto."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import anlass, cli, db, kern


class Anlass(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        umgebung = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        umgebung.start()
        self.addCleanup(umgebung.stop)
        for k in ("AMW_PROJEKT", "AMW_AGENT"):
            os.environ.pop(k, None)
        self.con = db.anlegen()
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        aid = self.con.execute("SELECT id FROM agent WHERE kennung = 'CC1'").fetchone()[0]
        with db.schreiben(self.con):
            self.sid = db.einfuegen(self.con, "sitzung", agent_id=aid, gestartet_utc="2026-11-13T08:00:00Z", zustand="aktiv")
        for t, usd in (("08:00", 10.0), ("08:10", 11.0), ("08:20", 13.0), ("08:30", 13.5), ("08:40", 15.5)):
            self.messen(t, usd)

    def messen(self, t, usd):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "verbrauch", sitzung_id=self.sid, agent="CC1", zeit_utc=f"2026-11-13T{t}:00Z", kosten_usd=usd)

    def weck(self, t, von, art, kurz):
        with db.schreiben(self.con):
            nid = kern._posten(self.con, self.pid, von, "CC1", art, kurz)
            nid = nid[0] if isinstance(nid, tuple) else nid                 # _posten liefert (Nummer, Empfänger)
            self.con.execute("UPDATE empfang SET geweckt_utc = ? WHERE nachricht_id = ?", (f"2026-11-13T{t}:00Z", nid))

    def test_zuordnung_teilen_und_eigene_arbeit(self):
        self.weck("08:05", "AMW", "freigabe", "L7 ist dran – jetzt starten: Probe")     # 08:00–08:10: 1,0 $
        self.weck("08:15", "TL", "auftrag", "Bitte bauen")                             # 08:10–08:20: 2,0 $ geteilt …
        self.weck("08:18", "AMW", "meldung", "Leerlauf: seit 30 min frei")              # … mit diesem
        d = anlass.anlaesse(self.con, self.pid, "2026-11-13T00:00:00Z")
        z = {r["anlass"]: r for r in d["zeilen"]}
        self.assertEqual(z["Lauf ist dran"]["usd"], 1.0)
        self.assertEqual(z["Auftrag"]["usd"], 1.0)
        self.assertEqual(z["Leerlauf-Hinweis"]["usd"], 1.0)
        self.assertEqual(z[anlass.EIGENE]["usd"], 2.5)                                # 08:20–08:40 ohne Weckruf
        self.assertEqual(d["gesamt"], 5.5)
        self.assertEqual(d["vermeidbar_usd"], 2.0)
        self.assertEqual((d["weckrufe"], d["vermeidbar_weckrufe"]), (3, 2))
        self.assertEqual(d["zeilen"][0]["anlass"], anlass.EIGENE)                       # Pareto: teuerster zuerst
        self.assertEqual(d["zeilen"][-1]["kumuliert"], 100.0)

    def test_arten(self):
        self.assertEqual(anlass.art("AMW", "meldung", "L5 fertig, rc 0 – vom Dienst gerechnet"), ("Lauf fertig (Dienst)", False))
        self.assertEqual(anlass.art("AMW", "meldung", "A12: L5 zu Ende (rc 0) – weiter"), ("Lauf zu Ende → weiter", False))
        self.assertEqual(anlass.art("CC2", "meldung", "P7 GRUEN: x@1"), ("Prüfergebnis", False))
        self.assertEqual(anlass.art("Entwickler", "stopp", "HALT"), ("vom Menschen: Halt", False))
        self.assertTrue(anlass.art("AMW", "meldung", "Achtung: Lauf L5 von CC1 läuft seit 90 min")[1])

    def test_neue_sitzung_zaehlt_neu(self):
        self.messen("08:50", 1.0)                                                       # Zähler gesunken: neue Sitzung
        d = anlass.anlaesse(self.con, self.pid, "2026-11-13T00:00:00Z")
        self.assertEqual(d["gesamt"], 6.5)

    def test_route_der_workbench(self):
        from amw import workbench
        self.weck("08:05", "AMW", "freigabe", "L7 ist dran – jetzt starten: Probe")
        with mock.patch.object(anlass, "zeitraum", return_value="2026-11-13T00:00:00Z"):
            d = workbench.daten_anlass(self.con, self.pid, {"tage": ["99"]})
        self.assertEqual(d["tage"], 30)                                                 # höchstens 30
        self.assertEqual({r["kennung"] for r in d["zeilen"]}, {"lauf_dran", "eigene"})

    def test_befehl(self):
        self.weck("08:05", "AMW", "freigabe", "L7 ist dran – jetzt starten: Probe")
        aus = io.StringIO()
        with mock.patch.object(anlass, "zeitraum", return_value="2026-11-13T00:00:00Z"), contextlib.redirect_stdout(aus):
            rc = cli.main(["verbrauch", "pareto", "--tage", "1", "--projekt", "P", "--von", "TL"])
        self.assertEqual(rc, 0)
        self.assertIn("vermeidbar · Lauf ist dran", aus.getvalue())
        self.assertIn("5.50 $", aus.getvalue())


if __name__ == "__main__":
    unittest.main()
