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


class Zuwachs(Grund):
    """A1739 (Marcel 15.11., W2153): je Meilenstein sichtbar, was seit dem Start dazukam und fertig wurde – sonst wundert man
    sich, warum der Balken nicht kürzer wird."""

    def zeit(self, aid, angelegt, fertig=None):
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET angelegt_utc = ?, status = CASE WHEN ? IS NULL THEN status ELSE 'fertig' END,"
                             " fertig_utc = ?, beleg = CASE WHEN ? IS NULL THEN beleg ELSE 'abc1234' END WHERE id = ?",
                             (angelegt, fertig, fertig, fertig, aid))

    def test_seit_start_hinzugekommen_erledigt_offen(self):
        bid = planung.bogen_neu(self.con, self.pid, "TL", "Karten-Look", ziel="z", abnahme="a")
        alt = [kern.aufgabe_neu(self.con, self.pid, "TL", f"Alt {i}", agent="CC1") for i in range(3)]
        for x in alt:
            planung.schritt_setzen(self.con, self.pid, "TL", aid=x, bogen_id=bid)
            self.zeit(x, "2026-11-01T08:00:00Z")
        with db.schreiben(self.con):                                                # vor dem Start zugeordnet (01.11.)
            self.con.execute("UPDATE plan_ereignis SET zeit_utc = '2026-11-01T09:00:00Z' WHERE art = 'aufgabe_bogen'")
        self.assertIsNone(planung.zuwachs(self.con, planung.bogen_zeile(self.con, self.pid, bid)))     # geplant: noch kein Start
        planung.bogen_status(self.con, self.pid, "TL", bid, "aktiv")
        with db.schreiben(self.con):                                                # Start festnageln: 10.11.
            self.con.execute("UPDATE plan_ereignis SET zeit_utc = '2026-11-10T08:00:00Z' WHERE art = 'bogen_status' AND bogen_id = ?", (bid,))
        self.zeit(alt[0], "2026-11-01T08:00:00Z", fertig="2026-11-11T08:00:00Z")    # nach dem Start erledigt
        self.zeit(alt[1], "2026-11-01T08:00:00Z", fertig="2026-11-09T08:00:00Z")    # vor dem Start erledigt – zählt nicht
        neu = [kern.aufgabe_neu(self.con, self.pid, "TL", f"Neu {i}", agent="CC1") for i in range(2)]
        for x in neu:
            planung.schritt_setzen(self.con, self.pid, "TL", aid=x, bogen_id=bid)   # nach dem Start angelegt
        alt_ohne = kern.aufgabe_neu(self.con, self.pid, "TL", "Alt, später hineingezogen", agent="CC1")
        self.zeit(alt_ohne, "2026-11-01T08:00:00Z")
        planung.schritt_setzen(self.con, self.pid, "TL", aid=alt_ohne, bogen_id=bid)  # hineingezogen: plan_ereignis aufgabe_bogen
        weg = kern.aufgabe_neu(self.con, self.pid, "TL", "Verworfen", agent="CC1")
        planung.schritt_setzen(self.con, self.pid, "TL", aid=weg, bogen_id=bid)
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'verworfen', beleg = 'x' WHERE id = ?", (weg,))
        z = planung.zuwachs(self.con, planung.bogen_zeile(self.con, self.pid, bid))
        self.assertEqual((z["seit"][:10], z["neu"], z["erledigt"], z["offen"]), ("2026-11-10", 3, 1, 4))
        b = next(x for x in workbench.daten_planung(self.con, self.pid)["boegen"] if x["id"] == bid)
        self.assertEqual(b["zuwachs"]["neu"], 3)                                     # kommt in Planung und Übersicht an
        rc, aus = self.cli("bogen", "liste", "--von", "TL", "--projekt", "Eins")
        self.assertIn("seit Start 2026-11-10: +3 neu, 1 erledigt, 4 offen", aus)


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
        for x in ('sj_titel: "Wo stehen wir gerade?"', 'sj_titel: "Where do we stand right now?"', 'ob_titel: "Ohne Meilenstein ({n})"',
                  'ob_titel: "Without milestone ({n})"', 'ue_jetzt: "Jetzt"', 'ue_jetzt: "Now"', 'ue_erkl: "Jeder Balken ist ein Meilenstein',
                  'ue_fertige_zeigen: "Erledigte einblenden ({n})"', 'tl_fertige: "Erledigte Meilensteine ({n})"', 'lg_rahmen: "wahrscheinlicher Rahmen"',
                  'rh_titel: "Was der Rechner heute gemacht hat"',
                  "m.append(standJetzt(d), uebersicht(d)", 'open: zustand.rhAuf ? "" : null'):
            self.assertIn(x, html)


if __name__ == "__main__":
    unittest.main()
