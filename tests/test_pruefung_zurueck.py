"""A1917 (21.11., P329): ein gegebenes GRÜN mit Grund zurücknehmen – Prüfer, Lead oder Mensch (als Mensch nicht aus einer
Agenten-Sitzung). Nichts wird gelöscht: rot mit „ZURÜCKGENOMMEN …“, Ereignis mit dem GRÜN davor. Danach gilt der Stand nicht
mehr (ist_gruen, Kette), übernommene Kopien fallen mit, ein Merge-OK fällt weg, Bauer und Lead erfahren es."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
from unittest import mock

from amw import auslieferung, betrieb, buendel, cli, db, kern, mergeliste
from tests.test_buendel import Basis


class Zuruecknehmen(Basis):
    def setUp(self):
        super().setUp()
        self.a = self.paket("plus", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"}, 1)
        self.p = self.con.execute("SELECT * FROM pruefung WHERE aufgabe_id = ? AND ergebnis = 'gruen' ORDER BY id LIMIT 1",
                                  (self.a,)).fetchone()

    def cli(self, *args, **env):
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": "", **env}), \
                contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "Spiel", *args])
        return rc, aus.getvalue()

    def test_gruen_zuruecknehmen_mit_kopien_und_merge_ok(self):
        z = mergeliste.zweig(self.a)
        self.assertTrue(betrieb.merge_ok(self.con, self.pid, self.a, z))
        r = buendel.buendeln(self.con, self.pid, "TL", starten=False)                   # übernimmt GRÜN + OK (Kopie „Quelle P…“)
        kopie = self.con.execute("SELECT * FROM pruefung WHERE zweig = ? AND ergebnis = 'gruen'", (r["zweig"],)).fetchone()
        self.assertTrue(kopie and betrieb.ist_gruen(self.con, self.pid, kopie["sha"]))
        with db.schreiben(self.con):                                                    # wie bei einer Prüfbitte eines Agenten
            self.con.execute("UPDATE pruefung SET bauer = 'CC1' WHERE id = ?", (self.p["id"],))
        self.p = self.con.execute("SELECT * FROM pruefung WHERE id = ?", (self.p["id"],)).fetchone()
        with self.assertRaisesRegex(kern.AmwFehler, "nur der Prüfer"):
            betrieb.pruefung_zuruecknehmen(self.con, self.pid, "CC1", self.p["id"], "Fehler im Stand")
        with self.assertRaisesRegex(kern.AmwFehler, "nur mit Grund"):
            betrieb.pruefung_zuruecknehmen(self.con, self.pid, "TL", self.p["id"], "  ")
        text = betrieb.pruefung_zuruecknehmen(self.con, self.pid, "TL", self.p["id"], "CCamw2 meldet: plus rechnet falsch bei None")
        self.assertIn(f"Mit zurückgenommen (Kopien): P{kopie['id']}", text)
        for prid in (self.p["id"], kopie["id"]):
            x = self.con.execute("SELECT ergebnis, bemerkung FROM pruefung WHERE id = ?", (prid,)).fetchone()
            self.assertEqual(x["ergebnis"], "rot")
            self.assertTrue(x["bemerkung"].startswith("ZURÜCKGENOMMEN von TL am "), x["bemerkung"])
            self.assertIsNotNone(betrieb.zurueckgenommen(self.con, self.pid, prid))   # im Verlauf: es war GRÜN
        self.assertIsNone(betrieb.ist_gruen(self.con, self.pid, self.p["sha"]))
        self.assertIsNone(betrieb.ist_gruen(self.con, self.pid, kopie["sha"]))
        self.assertIsNone(betrieb.merge_ok(self.con, self.pid, self.a, z))               # Merge-OK fällt weg
        self.assertIsNone(betrieb.merge_ok(self.con, self.pid, self.a, r["zweig"]))
        m = self.con.execute("SELECT n.kurz, n.text, group_concat(e.agent) FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id"
                             " WHERE n.kurz LIKE ? GROUP BY n.id", (f"P{self.p['id']} zurückgenommen%",)).fetchone()
        self.assertIsNotNone(m)
        self.assertIn("plus rechnet falsch", m[1])
        self.assertIn("CC1", (m[2] or "").split(","))                                    # der Bauer erfährt es (der Lead war es selbst)
        with self.assertRaisesRegex(kern.AmwFehler, "ist rot – zurücknehmen lässt sich nur ein GRÜN"):
            betrieb.pruefung_zuruecknehmen(self.con, self.pid, "TL", self.p["id"], "noch einmal")

    def test_kette_liefert_den_stand_nicht_aus(self):
        r = buendel.buendeln(self.con, self.pid, "TL", starten=False)
        rc, lid = buendel.lauf_und_meldung(self.con, self.pid, r["zweig"], warte=lambda s: None)
        self.assertEqual(rc, 0)
        betrieb.freigabe_merge(self.con, self.pid, "TL", self.a, r["zweig"])
        k = auslieferung.Kette(self.con, self.pid, "TL", self.repo, ausgabe=lambda _: None)
        self.assertEqual(k.pruefen(r["zweig"], gesamtlauf=lid)["sha"], r["sha"])           # vorher: auslieferbar
        gruen = betrieb.ist_gruen(self.con, self.pid, r["sha"])
        betrieb.pruefung_zuruecknehmen(self.con, self.pid, "TL", gruen["id"], "Gesamtlauf hat etwas übersehen")
        with self.assertRaisesRegex(auslieferung.Stopp, "keine grüne Prüfung auf genau"):
            k.pruefen(r["zweig"], gesamtlauf=lid)

    def test_cli_sperre_anzeige_und_pruefer_selbst(self):
        rc, aus = self.cli("pruefung", "zuruecknehmen", str(self.p["id"]), "--grund", "x", "--von", "Entwickler", CLAUDECODE="1")
        self.assertNotEqual(rc, 0)
        self.assertIn("nicht aus einer Agenten-Sitzung", aus)
        self.assertEqual(self.con.execute("SELECT ergebnis FROM pruefung WHERE id = ?", (self.p["id"],)).fetchone()[0], "gruen")
        with db.schreiben(self.con):                                                    # ein Prüfer, der nicht Lead ist
            self.con.execute("UPDATE pruefung SET pruefer = 'PR1' WHERE id = ?", (self.p["id"],))
        rc, aus = self.cli("pruefung", "zuruecknehmen", str(self.p["id"]), "--grund", "Fehler im Stand", "--von", "PR1")
        self.assertEqual(rc, 0, aus)
        self.assertIn("zurückgenommen", aus)
        rc, aus = self.cli("pruefung", "zeige", str(self.p["id"]), "--von", "TL")
        self.assertIn("[rot · zurückgenommen (war GRÜN) am ", aus)
        self.assertIn("ZURÜCKGENOMMEN von ", aus)
        rc, aus = self.cli("pruefung", "liste", "--alle", "--von", "TL")
        self.assertIn(f"P{self.p['id']:<5} [rot · zurückgenommen]", aus)

    def test_ueber_den_connector(self):
        from amw import mcp_server
        argv = mcp_server.befehlszeile("pruefung_zuruecknehmen", {"id": self.p["id"], "grund": "Fehler im Stand"})
        self.assertEqual(argv, ["pruefung", "zuruecknehmen", str(self.p["id"]), "--grund", "Fehler im Stand"])
        with mock.patch.dict(os.environ, {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}):
            rc, aus, fehler = mcp_server.befehl_ausfuehren(argv + ["--projekt", "Spiel", "--von", "TL"])
        self.assertEqual(rc, 0, fehler)
        self.assertEqual(self.con.execute("SELECT ergebnis FROM pruefung WHERE id = ?", (self.p["id"],)).fetchone()[0], "rot")

    def test_mensch_im_eigenen_terminal(self):
        rc, aus = self.cli("pruefung", "zuruecknehmen", str(self.p["id"]), "--grund", "Fehler", "--von", "Entwickler")
        self.assertEqual(rc, 0, aus)
        self.assertEqual(self.con.execute("SELECT ergebnis FROM pruefung WHERE id = ?", (self.p["id"],)).fetchone()[0], "rot")


if __name__ == "__main__":
    import unittest
    unittest.main()
