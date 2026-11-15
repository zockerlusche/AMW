"""Messen (A1757): Lesen Agenten nach einem Weckruf mit Inhalt trotzdem nach? Die Befehlszeile hält amw lesen/kontext eines
Agenten fest (ohne Inhalt), Betrieb zählt, nach wie vielen Weckrufen innerhalb von 2 Minuten nachgelesen wurde."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import cli, db, kern, nachlesen, workbench


class Nachlesen(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        umgebung = mock.patch.dict(os.environ, {"AMW_DB": self.pfad})
        umgebung.start()
        self.addCleanup(umgebung.stop)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")

    def cli(self, *args):
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            return cli.main(list(args))

    def weckruf(self, zeit):
        nid, _ = kern.posten(self.con, self.pid, "TL", "CC1", "auftrag", f"Bitte prüfen {zeit}")
        with db.schreiben(self.con):
            self.con.execute("UPDATE empfang SET geweckt_utc = ? WHERE nachricht_id = ?", (zeit, nid))

    def test_befehlszeile_merkt_nur_agenten(self):
        self.cli("lesen", "--von", "CC1", "--projekt", "Spiel")
        self.cli("kontext", "--von", "CC1", "--projekt", "Spiel")
        self.cli("lesen", "--von", "Entwickler", "--projekt", "Spiel")
        e = nachlesen.lesen()
        self.assertEqual([(x["p"], x["a"], x["b"]) for x in e], [("Spiel", "CC1", "lesen"), ("Spiel", "CC1", "kontext")])
        self.assertEqual(set(e[0]), {"t", "p", "a", "b"})                     # nie Inhalte

    def test_anteil_nachgelesen_nach_weckrufen(self):
        with open(nachlesen.pfad(), "w", encoding="utf-8") as f:
            for t in ("2026-11-15T08:00:00Z", "2026-11-15T09:00:30Z", "2026-11-15T10:10:00Z"):   # erster Eintrag = Beginn der Messung
                f.write(json.dumps({"t": t, "p": "Spiel", "a": "CC1", "b": "lesen"}) + "\n")
        self.weckruf("2026-11-15T09:00:00Z")                                     # 30 s danach nachgelesen
        self.weckruf("2026-11-15T10:00:00Z")                                     # erst 10 min danach – zählt nicht
        a = nachlesen.auswertung(self.con, self.pid, "2026-11-15T00:00:00Z")
        self.assertEqual((a["weckrufe"], a["nachgelesen"], a["anteil"]), (2, 1, 50.0))
        self.assertIsNone(a["vorher"])                                            # ohne Version 1.98.0 kein Vorher/Nachher
        d = workbench.daten_anlass(self.con, self.pid, {"tage": ["7"]})
        self.assertIn("nachlesen", d)


if __name__ == "__main__":
    unittest.main()
