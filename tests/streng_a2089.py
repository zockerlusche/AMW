"""A2089, vorläufig: der Textwächter ohne die Ausnahme der acht Module, die ein Headless-Paket umstellt. Wird nicht von allein gefunden (der
Name beginnt nicht mit test_), damit der Gesamtlauf bis dahin nicht rot ist; es ist der Abnahmebefehl des Pakets und kommt danach weg."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import tempfile
import unittest
from unittest import mock

from amw import db, kern, planung
from tests import test_a2089_texte


class Streng(unittest.TestCase):
    def test_headless_module(self):
        for datei in test_a2089_texte.HEADLESS:
            with self.subTest(datei=datei):
                self.assertEqual(test_a2089_texte.offen(datei), [])


class PlanCheck(unittest.TestCase):
    """Die Texte des Plan-Checks sind Vorlagen mit {b} – der Wächter sieht nicht, welche Nummer hineinkommt."""

    def test_nennt_die_projektnummer(self):
        ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(ordner.name, "amw.db")})
        u.start()
        self.addCleanup(u.stop)
        con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(con.close)
        with db.schreiben(con):
            fremd = db.einfuegen(con, "projekt", name="Fremd", angelegt_utc=db.jetzt())
            pid = db.einfuegen(con, "projekt", name="P", angelegt_utc=db.jetzt())
        for p in (fremd, pid):
            kern.agent_neu(con, p, "TL", rolle="lead")
        for i in range(4):
            planung.bogen_neu(con, fremd, "TL", f"Fremd {i}", ziel="Z", abnahme="V")
        bid = planung.bogen_neu(con, pid, "TL", "Bauen", ziel="Z", abnahme="")
        self.assertNotEqual(bid, 1)
        texte = [x["text"] for x in planung.pruefen(con, pid) if x["bogen_id"] == bid]
        self.assertTrue(any("„Bauen“" in t for t in texte), texte)
        for t in texte:
            self.assertNotIn(f"Meilenstein {bid} ", t)
            self.assertNotIn(f"M{bid} ", t)
        self.assertTrue(any(("Meilenstein 1 „Bauen“" in t) or ("M1 „Bauen“" in t) for t in texte), texte)
        self.assertTrue(any(f":B{bid}" in x["schluessel"] for x in planung.pruefen(con, pid)))     # der gespeicherte Schlüssel bleibt intern


if __name__ == "__main__":
    unittest.main()
