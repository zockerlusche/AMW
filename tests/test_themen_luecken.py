"""A1947 (Marcel W2458, Co #30113): Lücken Thema ↔ Paket – freigegebenes Thema ohne Paket und offenes Paket ohne Thema; Vermerke
„nichts zu bauen“ (Lead, Mensch, Co) und „ohne Thema“ (Grund beim Anlegen); Meldung an den Lead einmal je neuer Lücke;
„aufgabe neu“ ohne --thema: Hinweis, mit thema_pflicht=an Abbruch vor dem Anlegen; Planung liefert die Lücken."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import cli, db, kern, themen, workbench


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        u.start()
        self.addCleanup(u.stop)
        for k in ("AMW_AGENT", "AMW_PROJEKT"):
            os.environ.pop(k, None)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.tid = self.thema("Anmeldung")

    def thema(self, name, frei=True):
        tid = themen.neu(self.con, self.pid, "TL", name, pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", tid, f"{name}: so soll es sein.")
        if frei:
            themen.freigeben(self.con, self.pid, kern.ENTWICKLER, tid)
        return tid

    def l(self):
        x = themen.luecken(self.con, self.pid)
        return [t["id"] for t in x["thema_ohne_paket"]], [a["id"] for a in x["paket_ohne_thema"]]

    def cli(self, *args):
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus):
            rc = cli.main([*args, "--projekt", "Spiel"])
        return rc, aus.getvalue()

    def post(self, an):
        return [(r["art"], r["kurz"], r["text"]) for r in self.con.execute(
            "SELECT n.art, n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? AND n.von = 'AMW'"
            " ORDER BY n.id", (an,))]


class Luecken(Grund):
    def test_thema_ohne_paket(self):
        self.thema("Entwurf", frei=False)                                    # nicht freigegeben: keine Lücke
        self.assertEqual(self.l(), ([self.tid], []))
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "SSO bauen", "CC1")
        self.assertEqual(self.l(), ([self.tid], [aid]))                       # Paket ohne Thema
        themen.verweise_setzen(self.con, self.pid, "TL", aid, [f"TH{self.tid}"])
        self.assertEqual(self.l(), ([], []))
        kern.aufgabe_status(self.con, self.pid, "CC1", aid, "fertig", beleg="abc")
        self.assertEqual(self.l(), ([], []))                                  # fertig zählt
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'verworfen' WHERE id = ?", (aid,))
        self.assertEqual(self.l(), ([self.tid], []))                          # verworfen nicht

    def test_vermerke(self):
        with self.assertRaisesRegex(kern.AmwFehler, "Lead, Mensch oder Co-Entwickler"):
            themen.nichts_zu_bauen(self.con, self.pid, "CC1", self.tid, "x")
        with self.assertRaisesRegex(kern.AmwFehler, "Grund fehlt"):
            themen.nichts_zu_bauen(self.con, self.pid, "TL", self.tid, " ")
        themen.nichts_zu_bauen(self.con, self.pid, "TL", self.tid, "Ist schon gebaut (A1896).")
        self.assertEqual(self.l()[0], [])
        self.assertEqual(themen.nichts_vermerkt(self.con, self.pid), {self.tid: "Ist schon gebaut (A1896)."})
        themen.nichts_zu_bauen(self.con, self.pid, kern.ENTWICKLER, self.tid, None, aufheben=True)
        self.assertEqual(self.l()[0], [self.tid])
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Aufräumen", "CC1")
        themen.ohne_thema_vermerken(self.con, self.pid, "TL", aid, "interne Pflege: Aufräumen")
        self.assertEqual(self.l()[1], [])

    def test_ohne_themen_keine_luecken(self):
        with db.schreiben(self.con):
            pid = db.einfuegen(self.con, "projekt", name="Ohne", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, pid, "TL2", rolle="lead")
        kern.aufgabe_neu(self.con, pid, "TL2", "Irgendwas")
        self.assertEqual(themen.luecken(self.con, pid), {"thema_ohne_paket": [], "paket_ohne_thema": []})
        self.assertEqual(themen.luecken_melden(self.con, pid), [])

    def test_meldung_einmal_je_neuer_luecke(self):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "SSO bauen", "CC1")
        self.assertEqual(len(themen.luecken_melden(self.con, self.pid)), 1)
        art, kurz, text = self.post("TL")[-1]
        self.assertEqual((art, kurz), ("frage", "Lücken Thema ↔ Paket: 1 freigegebene(s) Thema/Themen ohne Paket · 1 Paket(e) ohne Thema"))
        self.assertIn(f"TH{self.tid} Anmeldung – freigegeben, aber kein Paket", text)
        self.assertIn(f"A{aid} SSO bauen (CC1, wartet) – ohne Thema", text)
        self.assertEqual(themen.luecken_melden(self.con, self.pid), [])         # nicht wiederholt
        zwei = self.thema("Speichern")
        themen.luecken_melden(self.con, self.pid)
        kurz, text = self.post("TL")[-1][1:]
        self.assertIn("1 freigegebene(s) Thema/Themen ohne Paket", kurz)
        self.assertNotIn("ohne Thema", kurz)                                     # nur die neue Lücke
        self.assertIn(f"TH{zwei} Speichern", text)

    def test_planung_liefert_luecken(self):
        d = workbench.daten_planung(self.con, self.pid)
        self.assertEqual([x["id"] for x in d["luecken"]["thema_ohne_paket"]], [self.tid])


class Anlegen(Grund):
    def test_hinweis_ohne_pflicht_und_verknuepfen(self):
        rc, aus = self.cli("--von", "TL", "aufgabe", "neu", "--titel", "Ohne", "--ohne-bogen")
        self.assertEqual(rc, 0)
        self.assertIn("Hinweis: Zu welchem Thema gehört die Aufgabe?", aus)
        rc, aus = self.cli("--von", "TL", "aufgabe", "neu", "--titel", "Mit", "--ohne-bogen", "--thema", f"TH{self.tid}")
        aid = self.con.execute("SELECT id FROM aufgabe WHERE titel = 'Mit'").fetchone()[0]
        self.assertEqual((rc, themen.verweise(self.con, self.pid, aid)), (0, [self.tid]))
        self.assertIn(f"Thema: TH{self.tid}", aus)

    def test_pflicht_an_bricht_vor_dem_anlegen_ab(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", thema_pflicht="an")
        vorher = self.con.execute("SELECT count(*) FROM aufgabe").fetchone()[0]
        rc, aus = self.cli("--von", "TL", "aufgabe", "neu", "--titel", "Ohne", "--ohne-bogen")
        self.assertNotEqual(rc, 0)
        self.assertEqual(self.con.execute("SELECT count(*) FROM aufgabe").fetchone()[0], vorher)
        rc, aus = self.cli("--von", "TL", "aufgabe", "neu", "--titel", "Pflege", "--ohne-bogen", "--ohne-thema-grund", "Aufräumen")
        self.assertEqual(rc, 0)
        self.assertEqual(self.l()[1], [])                                       # mit Grund: keine Lücke

    def test_befehle_vermerk_und_luecken(self):
        rc, aus = self.cli("--von", "TL", "thema", "luecken")
        self.assertIn("Freigegebene Themen ohne Paket: 1", aus)
        rc, aus = self.cli("--von", "TL", "thema", "vermerk", f"TH{self.tid}", "--nichts-zu-bauen", "--grund", "schon erfüllt")
        self.assertEqual(rc, 0)
        self.assertIn("„nichts zu bauen“ vermerkt", aus)
        rc, aus = self.cli("--von", "TL", "thema", "luecken")
        self.assertIn("Freigegebene Themen ohne Paket: 0", aus)


if __name__ == "__main__":
    unittest.main()
