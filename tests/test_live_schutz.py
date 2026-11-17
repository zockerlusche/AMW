"""Entwicklungsbäume migrieren und beschreiben die Live-Datenbank nie (A1862, Vorfall: ein Befehl aus einem Entwicklungsbaum
hob die Live-DB vorzeitig auf ein neues Schema). Der Dienst vermerkt neben der Datenbank den Ordner seines Codes; Code aus einem
anderen Ordner ohne ausdrückliches AMW_DB darf nur lesen. Der Dienst selbst, Tests und Plätze (AMW_DB gesetzt) wie bisher."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from amw import db

OHNE = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class LiveSchutz(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        db.anlegen(self.pfad).close()
        self.neu = db.SCHEMA_VERSION + 1                                       # ein „neueres“ Schema mit eigener Migration
        self.mig = os.path.join(self.ordner.name, "code", "amw")
        os.makedirs(self.mig)
        with open(os.path.join(self.mig, f"migration_{self.neu}.sql"), "w", encoding="utf-8") as f:
            f.write("CREATE TABLE probe (x INTEGER);\n")
        ohne = {k: v for k, v in os.environ.items() if k != "AMW_DB"}        # wie ein Entwicklungsbaum ohne AMW_DB
        u = mock.patch.dict(os.environ, ohne, clear=True)
        u.start()
        self.addCleanup(u.stop)

    def vermerk(self, ordner):
        with open(db.vermerk_pfad(self.pfad), "w", encoding="utf-8") as f:
            f.write(ordner)

    def version(self):
        c = sqlite3.connect(self.pfad)
        try:
            return c.execute("PRAGMA user_version").fetchone()[0]
        finally:
            c.close()

    def neueres_schema(self):
        return mock.patch.multiple(db, SCHEMA_VERSION=self.neu, HIER=self.mig)

    def test_fremder_code_migriert_nicht(self):
        self.vermerk(os.path.join(self.ordner.name, "live"))                  # der Dienst läuft woanders
        with self.neueres_schema():
            with self.assertRaises(db.LiveSchutz) as e:
                db.verbinde(self.pfad)
        self.assertIn("migrieren", str(e.exception))
        self.assertIn("AMW_DB", str(e.exception))
        self.assertEqual(self.version(), self.neu - 1)                         # Schema unverändert

    def test_fremder_code_schreibt_nicht_liest_aber(self):
        self.vermerk(os.path.join(self.ordner.name, "live"))
        con = db.verbinde(self.pfad)
        self.addCleanup(con.close)
        self.assertEqual(con.execute("SELECT count(*) FROM projekt").fetchone()[0], 0)        # lesen geht
        with self.assertRaises(db.LiveSchutz):
            with db.schreiben(con):
                db.einfuegen(con, "projekt", name="X", angelegt_utc=db.jetzt())
        with self.assertRaises(sqlite3.DatabaseError):                                          # auch an schreiben() vorbei
            con.execute("INSERT INTO projekt (name, angelegt_utc) VALUES ('X', 'x')")
        with self.assertRaises(sqlite3.DatabaseError):
            con.execute("PRAGMA user_version = 99")
        self.assertEqual(self.version(), db.SCHEMA_VERSION)

    def test_dienst_im_eigenen_ordner_migriert_wie_bisher(self):
        db.vermerken(self.pfad)                                                 # so schreibt ihn der Dienst beim Start
        with open(db.vermerk_pfad(self.pfad), encoding="utf-8") as f:
            self.assertEqual(f.read(), db.CODE)
        self.assertIsNone(db.fremder_code(self.pfad))
        with self.neueres_schema():
            con = db.verbinde(self.pfad)
            con.close()
        self.assertEqual(self.version(), self.neu)
        con = db.verbinde(self.pfad)
        self.addCleanup(con.close)
        with db.schreiben(con):
            db.einfuegen(con, "projekt", name="X", angelegt_utc=db.jetzt())

    def test_ohne_vermerk_oder_mit_amw_db_wie_bisher(self):
        with self.neueres_schema():                                             # ältere Installation: kein Vermerk
            db.verbinde(self.pfad).close()
        self.assertEqual(self.version(), self.neu)
        self.vermerk(os.path.join(self.ordner.name, "live"))
        with mock.patch.dict(os.environ, {"AMW_DB": self.pfad}):                # ausdrücklich gewählt (Tests, Plätze)
            self.assertIsNone(db.fremder_code(self.pfad))
            con = db.verbinde(self.pfad)
            with db.schreiben(con):
                db.einfuegen(con, "projekt", name="X", angelegt_utc=db.jetzt())
            con.close()

    def test_fremder_dienst_uebernimmt_den_vermerk_nicht(self):
        """P252: ein Dienst aus einem anderen Ordner (z. B. während der echte gerade neu startet) startet nicht – der Vermerk des
        echten Dienstes bleibt stehen, sonst wäre danach der Entwicklungsbaum „zu Hause“ und der Live-Ordner fremd."""
        from amw import dienst
        live = os.path.join(self.ordner.name, "live")
        self.vermerk(live)
        with mock.patch.object(db, "db_pfad", return_value=self.pfad), mock.patch.object(dienst, "einrichten_log"),                 mock.patch.object(dienst, "einzige_instanz", return_value=object()), mock.patch.object(dienst, "Dienst") as d:
            self.assertEqual(dienst.main(["--einmal", "--ohne-web"]), 2)
            with self.neueres_schema():                                             # auch wenn er migrieren müsste
                self.assertEqual(dienst.main(["--einmal", "--ohne-web"]), 2)
        d.assert_not_called()
        with open(db.vermerk_pfad(self.pfad), encoding="utf-8") as f:
            self.assertEqual(f.read(), live)                                        # Vermerk unverändert
        self.assertEqual(self.version(), db.SCHEMA_VERSION)

    def test_befehlszeile_aus_fremdem_baum_abgelehnt(self):
        """Wie der Vorfall: amw-cli.py aus einem anderen Ordner landet über die Einstellung db_pfad bei der Live-DB."""
        self.vermerk(os.path.join(self.ordner.name, "live"))
        lad = os.path.join(self.ordner.name, "lad")
        os.makedirs(os.path.join(lad, "amw"))
        with open(os.path.join(lad, "amw", "einstellungen.json"), "w", encoding="utf-8") as f:
            f.write('{"db_pfad": %s}' % __import__("json").dumps(self.pfad))
        u = {k: v for k, v in os.environ.items() if k not in ("AMW_AGENT", "AMW_PROJEKT")}
        u.update(LOCALAPPDATA=lad, PYTHONPATH=db.CODE)
        r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(db.CODE, "amw-cli.py"), "projekt", "neu", "Probe"],
                           env=u, capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL, creationflags=OHNE)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("AMW_DB", r.stdout + r.stderr)
        c = sqlite3.connect(self.pfad)
        self.addCleanup(c.close)
        self.assertEqual(c.execute("SELECT count(*) FROM projekt").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
