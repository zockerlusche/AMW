"""Planung „Wo stehen wir“ (A1639): Stand jetzt (aktiver Meilenstein, Fortschritt, nächstes Zieldatum, wer an was arbeitet),
Aufgaben ohne Meilenstein sichtbar, neue Aufgabe fragt nach dem Meilenstein (--bogen; bewusst ohne: --ohne-bogen, nur Lead)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import db, kern, planung, workbench


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Eins", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")

    def cli(self, *args):
        from amw import cli
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_DB": self.pfad}), contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(list(args))
        return rc, aus.getvalue()


class Daten(Grund):
    def test_laeuft_und_ohne_meilenstein(self):
        bid = planung.bogen_neu(self.con, self.pid, "TL", "Karten-Look", ziel="z", abnahme="a")
        mit = kern.aufgabe_neu(self.con, self.pid, "TL", "Im Meilenstein", agent="CC1")
        planung.schritt_setzen(self.con, self.pid, "TL", aid=mit, bogen_id=bid)
        ohne = kern.aufgabe_neu(self.con, self.pid, "TL", "Ohne Meilenstein", agent="CC1")
        fertig = kern.aufgabe_neu(self.con, self.pid, "TL", "Schon fertig")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc1234' WHERE id = ?", (fertig,))
        kern.aufgabe_status(self.con, self.pid, "CC1", ohne, "start")
        d = workbench.daten_planung(self.con, self.pid)
        self.assertEqual([x["id"] for x in d["ohne_bogen"]], [ohne])                 # Fertiges nicht, Zugeordnetes nicht
        self.assertEqual([(x["id"], x["agent"], x["bogen_id"]) for x in d["laeuft"]], [(ohne, "CC1", None)])   # auch ohne Meilenstein


class NeueAufgabe(Grund):
    def test_fragt_nach_dem_meilenstein(self):
        rc, aus = self.cli("aufgabe", "neu", "--titel", "Vorher", "--von", "TL", "--projekt", "Eins")
        self.assertEqual(rc, 0, aus)                                                # ohne offenen Meilenstein: wie bisher
        bid = planung.bogen_neu(self.con, self.pid, "TL", "Karten-Look", ziel="z", abnahme="a")
        rc, aus = self.cli("aufgabe", "neu", "--titel", "Neu", "--von", "TL", "--projekt", "Eins")
        self.assertNotEqual(rc, 0)
        self.assertIn(f"--bogen {bid}   B{bid} Karten-Look (geplant)", aus)
        self.assertIn(f"Vorschlag: --bogen {bid}", aus)
        self.assertIn("--ohne-bogen", aus)
        self.assertEqual(self.con.execute("SELECT count(*) FROM aufgabe WHERE titel = 'Neu'").fetchone()[0], 0)
        rc, aus = self.cli("aufgabe", "neu", "--titel", "Neu", "--von", "TL", "--projekt", "Eins", "--ohne-bogen")
        self.assertEqual(rc, 0, aus)                                                # bewusst ohne
        rc, aus = self.cli("aufgabe", "neu", "--titel", "Vom Coder", "--von", "CC1", "--projekt", "Eins")
        self.assertEqual(rc, 0, aus)                     # ein Coder darf keinen Meilenstein setzen: steht unter „Ohne Meilenstein“
        rc, aus = self.cli("aufgabe", "neu", "--titel", "Zugeordnet", "--von", "TL", "--projekt", "Eins", "--bogen", str(bid))
        self.assertEqual(rc, 0, aus)
        self.assertEqual(self.con.execute("SELECT bogen_id FROM aufgabe WHERE titel = 'Zugeordnet'").fetchone()[0], bid)
        planung.bogen_status(self.con, self.pid, "TL", bid, "aktiv")
        b2 = planung.bogen_neu(self.con, self.pid, "TL", "Später", ziel="z", abnahme="a")
        rc, aus = self.cli("aufgabe", "neu", "--titel", "Wieder", "--von", "Entwickler", "--projekt", "Eins")
        self.assertIn(f"Vorschlag: --bogen {bid}", aus)                             # der aktive zuerst
        self.assertIn(f"B{b2} Später (geplant)", aus)


class Seite(unittest.TestCase):
    def test_texte_und_teile(self):
        with open(os.path.join(os.path.dirname(workbench.__file__), "workbench.html"), encoding="utf-8") as f:
            html = f.read()
        for x in ('sj_titel: "Stand jetzt"', 'sj_titel: "Where we stand"', 'ob_titel: "Ohne Meilenstein ({n})"',
                  'ob_titel: "Without milestone ({n})"', 'ue_jetzt: "Jetzt {x}"', 'ue_jetzt: "Now {x}"',
                  'ue_fertige_zeigen: "Fertige zeigen ({n})"', 'tl_fertige: "Fertige Meilensteine ({n})"',
                  "m.append(standJetzt(d), uebersicht(d)", 'open: zustand.rhAuf ? "" : null'):
            self.assertIn(x, html)


if __name__ == "__main__":
    unittest.main()
