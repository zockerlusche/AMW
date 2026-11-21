"""Themen-Bereich (A1896, D1319, W2429–W2431): ein Status je Thema, abgeleitet aus Fakten (B2907, ohne Schemaänderung);
nur die gerade möglichen Handlungen; Freigeben/Zurück/Löschen markieren nur der Mensch (Workbench am PC, eigenes Terminal);
Notiz und Freigabe gehen als Nachricht an den Pfleger; „Für dich“ zählt die wartenden Themen."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import aktionen, db, kern, themen, workbench

T0, T1, T2, T3 = "2026-11-01T08:00:00Z", "2026-11-01T08:01:00Z", "2026-11-01T08:02:00Z", "2026-11-01T08:03:00Z"


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Produkt", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.tid = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")

    def st(self):
        return themen.status(self.con, themen.finden(self.con, self.pid, self.tid))

    def fassung(self, von="CC1", zeit=T0, text="Anmeldung mit Firmen-Konto."):
        themen.pflegen(self.con, self.pid, "TL" if von == kern.ENTWICKLER else von, self.tid, text)
        with db.schreiben(self.con):
            self.con.execute("UPDATE thema_fassung SET zeit_utc = ?, von = ? WHERE id = (SELECT max(id) FROM thema_fassung)", (zeit, von))

    def letztes_ereignis_um(self, zeit):
        with db.schreiben(self.con):
            self.con.execute("UPDATE plan_ereignis SET zeit_utc = ? WHERE id = (SELECT max(id) FROM plan_ereignis WHERE art LIKE 'thema_%')", (zeit,))

    def beschluss(self, zeit, stichwort="SSO Pflicht"):
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "beschluss", projekt_id=self.pid, zeit_utc=zeit, stichwort=stichwort, regel="x", quelle="W1",
                                thema="Anmeldung", angelegt_von="TL", angelegt_utc=zeit)

    def post(self, an):
        return [(r["art"], r["kurz"]) for r in self.con.execute(
            "SELECT n.art, n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? AND n.von = 'AMW' ORDER BY n.id", (an,))]


class Ableitung(Grund):
    def test_ohne_text_in_arbeit(self):
        self.assertEqual((self.st()["status"], self.st()["fassung"]), ("arbeit", None))

    def test_fassung_eines_agenten_wartet_auf_dich(self):
        self.fassung()
        self.assertEqual((self.st()["status"], self.st()["text"], self.st()["fassung"]), ("dich", "wartet auf dich", 1))

    def test_freigeben_dann_neuer_beschluss_neu_pruefen_mit_grund(self):
        self.fassung(zeit=T0)
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.letztes_ereignis_um(T1)
        self.assertEqual(self.st()["status"], "frei")
        bid = self.beschluss(T2)
        s = self.st()
        self.assertEqual((s["status"], s["grund"]), ("pruefen", f"B{bid} SSO Pflicht"))     # Auflage (c): Grund als Fakt
        with db.schreiben(self.con):                                                          # Pfleger bestätigt: gilt weiter
            self.con.execute("UPDATE thema SET bestaetigt_utc = ?, bestaetigt_von = 'CC1' WHERE id = ?", (T3, self.tid))
        self.assertEqual(self.st()["status"], "dich")

    def test_zurueck_und_text_vom_menschen_in_arbeit(self):
        self.fassung(zeit=T0)
        themen.zurueck(self.con, self.pid, kern.ENTWICKLER, self.tid, "Zweitfaktor nur online")
        self.letztes_ereignis_um(T1)
        self.assertEqual(self.st()["status"], "arbeit")
        self.fassung(zeit=T2)                                                                 # der Pfleger liefert neu
        self.assertEqual(self.st()["status"], "dich")
        themen.bearbeiten(self.con, self.pid, kern.ENTWICKLER, self.tid, "Anmeldung mit Firmen-Konto, Zweitfaktor online.")
        self.assertEqual(self.st()["status"], "arbeit")

    def test_fassung_veraltet_durch_neuen_beschluss_in_arbeit(self):
        self.fassung(zeit=T0)
        self.beschluss(T1)
        self.assertEqual(self.st()["status"], "arbeit")


class Handlungen(Grund):
    def test_je_status_nur_moegliche(self):
        self.assertEqual(themen.handlungen(self.st()), ("bearbeiten", "markieren"))
        self.fassung()
        self.assertEqual(themen.handlungen(self.st()), ("freigeben", "zurueck", "bearbeiten", "markieren"))
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.assertEqual(themen.handlungen(self.st()), ("zurueck", "bearbeiten", "markieren"))
        with self.assertRaisesRegex(kern.AmwFehler, "das geht gerade nicht"):
            themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        themen.markieren(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.assertTrue(self.st()["markiert"])
        self.assertEqual(themen.handlungen(self.st()), ("entmarkieren",))
        themen.markieren(self.con, self.pid, kern.ENTWICKLER, self.tid, an=False)
        self.assertFalse(self.st()["markiert"])
        self.assertEqual(self.con.execute("SELECT count(*) FROM thema").fetchone()[0], 1)            # nichts gelöscht (B2894)

    def test_zurueck_nur_mit_notiz_und_nachrichten_an_den_pfleger(self):
        self.fassung()
        with self.assertRaisesRegex(kern.AmwFehler, "nur mit Notiz"):
            themen.zurueck(self.con, self.pid, kern.ENTWICKLER, self.tid, " ")
        themen.zurueck(self.con, self.pid, kern.ENTWICKLER, self.tid, "Zweitfaktor nur online")
        self.assertEqual(self.post("CC1")[-1], ("auftrag", "Thema „Anmeldung“ zurück: Zweitfaktor nur online"))
        self.fassung(zeit="2099-01-01T00:00:00Z")
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.assertEqual(self.post("CC1")[-1], ("info", "Thema „Anmeldung“ freigegeben (Fassung 2)"))


class Rechte(Grund):
    def test_nur_der_mensch(self):
        self.fassung()
        for von in ("TL", "CC1"):
            with self.assertRaisesRegex(kern.AmwFehler, "nur der Mensch"):
                themen.freigeben(self.con, self.pid, von, self.tid)
            with self.assertRaisesRegex(kern.AmwFehler, "nur der Mensch"):
                themen.markieren(self.con, self.pid, von, self.tid)

    def test_workbench_nur_am_pc(self):
        self.fassung()
        with self.assertRaisesRegex(aktionen.Ungueltig, "nur am PC"):
            aktionen.ausfuehren(self.con, self.pid, "/api/thema/freigeben", {"thema": self.tid}, kanal="netz")
        r = aktionen.ausfuehren(self.con, self.pid, "/api/thema/freigeben", {"thema": self.tid}, kanal="seite")
        self.assertEqual(r["status"], "frei")

    def test_befehl_nur_im_terminal_des_menschen(self):
        from amw import cli
        self.fassung()
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1", "AMW_AGENT": "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}), \
                contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "Produkt", "thema", "freigeben", f"TH{self.tid}", "--von", "Entwickler"])
        self.assertNotEqual(rc, 0)
        self.assertIn("nur der Mensch in seinem eigenen Terminal", aus.getvalue())
        self.assertEqual(self.st()["status"], "dich")


class FuerDich(Grund):
    def test_wartende_themen_unter_fuer_dich(self):
        self.assertEqual(workbench._themen_fuer_dich(self.con, self.pid), [])
        self.fassung()
        f = workbench._themen_fuer_dich(self.con, self.pid)
        self.assertEqual([(x["id"], x["status"]) for x in f], [(self.tid, "dich")])
        themen.markieren(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.assertEqual(workbench._themen_fuer_dich(self.con, self.pid), [])               # markiert zählt nicht

    def test_seite_liefert_status_und_handlungen(self):
        self.fassung()
        s = themen.seite(self.con, self.pid, self.tid)
        self.assertEqual((s["zustand"]["status"], s["handlungen"]), ("dich", ["freigeben", "zurueck", "bearbeiten", "markieren"]))
        self.assertEqual(themen.liste(self.con, self.pid)[0]["zustand"]["status"], "dich")


if __name__ == "__main__":
    unittest.main()
