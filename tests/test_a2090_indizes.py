"""A2090: Schema 35 – sieben Indizes (nur Indizes, keine Daten): Migration einer gefüllten Datenbank, zweimal, gleich dem neuen Schema;
und die Abfragen, um die es geht, benutzen sie."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import re
import sqlite3
import tempfile
import unittest
from unittest import mock

from amw import db, kern, planung

INDIZES = {"nachricht_aufgabe": "nachricht", "lauf_aufgabe": "lauf", "pruefung_aufgabe": "pruefung", "plan_ereignis_aufgabe": "plan_ereignis",
           "plan_ereignis_bogen": "plan_ereignis", "aufgabe_bogen": "aufgabe", "frage_aufgabe": "frage"}


def indizes(con):
    """Name → Aufbau ohne „IF NOT EXISTS“ und Leerraum (so vergleichbar zwischen Migration und schema.sql)."""
    return {r[0]: re.sub(r"\s+", " ", re.sub(r"IF NOT EXISTS ", "", r[1], flags=re.I))
            for r in con.execute("SELECT name, sql FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL")}


class Migration(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad})
        u.start()
        self.addCleanup(u.stop)
        con = db.anlegen(self.pfad)
        with db.schreiben(con):
            self.pid = db.einfuegen(con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(con, self.pid, "TL", rolle="lead")
        kern.agent_neu(con, self.pid, "CC1")
        self.m = planung.bogen_neu(con, self.pid, "TL", "Bauen", ziel="Z", abnahme="V")
        self.a = planung.schritt_setzen(con, self.pid, "TL", titel="Paket", bogen_id=self.m, agent="CC1")
        kern.posten(con, self.pid, "TL", "CC1", "info", "dazu", aufgabe_id=self.a)
        con.close()

    def alt(self):
        """Die Datenbank auf den Stand vor der Migration bringen: ohne die Indizes, Schema 34."""
        con = sqlite3.connect(self.pfad)
        for n in INDIZES:
            con.execute(f"DROP INDEX {n}")
        con.execute("PRAGMA user_version = 34")
        con.commit()
        zeilen = self.inhalt(con)
        con.close()
        return zeilen

    @staticmethod
    def inhalt(con):
        return {t: con.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall() for (t,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()}

    def test_alt_nach_neu_nur_indizes(self):
        neu = sqlite3.connect(self.pfad)
        soll = indizes(neu)
        neu.close()
        vorher = self.alt()
        con = db.verbinde(self.pfad)
        self.addCleanup(con.close)
        self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
        self.assertEqual(indizes(con), soll)                                     # migriert = neu angelegt, auch im Aufbau
        self.assertLessEqual(set(INDIZES), set(soll))
        roh = sqlite3.connect(self.pfad)
        self.addCleanup(roh.close)
        self.assertEqual(self.inhalt(roh), vorher)                               # keine Zeile anders
        self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_zweimal_hintereinander(self):
        self.alt()
        db.verbinde(self.pfad).close()
        con = sqlite3.connect(self.pfad)
        einmal = indizes(con)
        con.execute("PRAGMA user_version = 34")                                  # abgebrochen nach den Indizes: sie sind schon da
        con.commit()
        con.close()
        con = db.verbinde(self.pfad)
        self.addCleanup(con.close)
        self.assertEqual((indizes(con), con.execute("PRAGMA user_version").fetchone()[0]), (einmal, db.SCHEMA_VERSION))

    def test_datei_enthaelt_nur_indizes(self):
        with open(os.path.join(db.HIER, "migration_35.sql"), encoding="utf-8") as f:
            text = re.sub(r"--[^\n]*", "", f.read())
        anweisungen = [x.strip() for x in text.split(";") if x.strip()]
        self.assertEqual(len(anweisungen), len(INDIZES))
        for x in anweisungen:
            self.assertRegex(x, r"^CREATE INDEX IF NOT EXISTS \w+ ON \w+ \([\w, ]+\)$")

    def test_die_abfragen_benutzen_sie(self):
        con = db.verbinde(self.pfad)
        self.addCleanup(con.close)
        for index, sql in (
                ("nachricht_aufgabe", "SELECT id FROM nachricht WHERE aufgabe_id = 1 AND projekt_id = 1 ORDER BY id DESC LIMIT 30"),
                ("lauf_aufgabe", "SELECT id FROM lauf WHERE aufgabe_id = 1 ORDER BY id DESC LIMIT 20"),
                ("pruefung_aufgabe", "SELECT id FROM pruefung WHERE aufgabe_id = 1 ORDER BY id DESC LIMIT 20"),
                ("plan_ereignis_aufgabe", "SELECT id FROM plan_ereignis WHERE projekt_id = 1 AND aufgabe_id = 1 AND art = 'verteilt' ORDER BY id"),
                ("plan_ereignis_bogen", "SELECT id FROM plan_ereignis WHERE bogen_id = 1 AND art = 'bogen_status' ORDER BY id DESC LIMIT 1"),
                ("aufgabe_bogen", "SELECT count(*), sum(status NOT IN ('fertig', 'verworfen')) FROM aufgabe WHERE bogen_id = 1"),
                ("frage_aufgabe", "SELECT id FROM frage WHERE projekt_id = 1 AND aufgabe_id = 1")):
            plan = " ".join(r[3] for r in con.execute("EXPLAIN QUERY PLAN " + sql))
            self.assertIn(index, plan, sql)
            self.assertNotIn("SCAN", plan, sql)


if __name__ == "__main__":
    unittest.main()
