"""--auf fügt Wartegründe nur hinzu (A1677): bleibt nach --auf ein alter Grund offen, sagt der Befehl das gleich dazu und nennt
den Weg zum Abhaken; --erledigt <alt> --auf <neu> geht in einem Schritt. (Ein Start schließt alle Gründe – der Fall ist eine
wartende Aufgabe, die einen neuen Grund dazubekommt.)"""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import db, kern, wartegrund


class AufFuegtHinzu(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Eins", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid, "PR1")
        self.aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Etwas bauen", agent="CC1")

    def cli(self, *args):
        from amw import cli
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")}), \
                contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main([*args, "--projekt", "Eins", "--von", "CC1"])
        return rc, aus.getvalue()

    def offen(self):
        return [g["bezug"] for g in wartegrund.offene(self.con, self.aid)]

    def test_hinweis_wenn_alter_grund_offen_bleibt(self):
        self.cli("aufgabe", "start", str(self.aid))
        rc, aus = self.cli("aufgabe", "wartet", str(self.aid), "--auf", "TL")
        self.assertEqual(rc, 0, aus)
        self.assertNotIn("Hinweis", aus)                                     # erster Grund: nichts Altes
        rc, aus = self.cli("aufgabe", "wartet", str(self.aid), "--auf", "PR1")
        self.assertEqual(self.offen(), ["TL", "PR1"])
        self.assertIn("Hinweis: --auf fügt Gründe hinzu – von vorher noch offen: TL", aus)
        self.assertIn(f"amw aufgabe wartet {self.aid} --erledigt TL", aus)

    def test_abhaken_und_neu_setzen_in_einem_schritt(self):
        self.cli("aufgabe", "start", str(self.aid))
        self.cli("aufgabe", "wartet", str(self.aid), "--auf", "TL")
        rc, aus = self.cli("aufgabe", "wartet", str(self.aid), "--erledigt", "TL", "--auf", "PR1")
        self.assertEqual(rc, 0, aus)
        self.assertEqual(self.offen(), ["PR1"])
        self.assertNotIn("Hinweis", aus)

    def test_kein_hinweis_bei_gleichem_grund(self):
        self.cli("aufgabe", "start", str(self.aid))
        self.cli("aufgabe", "wartet", str(self.aid), "--auf", "TL")
        rc, aus = self.cli("aufgabe", "wartet", str(self.aid), "--auf", "tl")
        self.assertNotIn("Hinweis", aus)


if __name__ == "__main__":
    unittest.main()
