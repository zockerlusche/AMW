"""Themen-Bereich (A1896, D1319, W2429–W2431, Einordnung D1326 Teil A): ein Status je Thema nach festem Vorrang, abgeleitet aus
Fassungen, Beschlüssen und festen Ereignissen (B2907, ohne Schemaänderung); die Freigabe zeigt auf eine Fassungsnummer; nur die
gerade möglichen Handlungen; die Handlungen des Menschen sind gegen Agenten gesperrt (Workbench nur am PC, Terminal nur des
Menschen, auch über MCP); Speichern nur gegen die erwartete Fassung; Notiz/Freigabe an den Pfleger; „Für dich“ und Zählung ohne
Markierte. F5358–F5360: bis zu Marcels Antwort die Empfehlung A."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import aktionen, db, kern, themen, workbench

T = ["2026-11-01T08:%02d:00Z" % i for i in range(10)]                  # feste Zeiten, je Schritt eine


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

    def um(self, i):
        """Alles, was dieser Schritt eben geschrieben hat (Zeit „jetzt“), auf die feste Zeit T[i] setzen."""
        with db.schreiben(self.con):
            self.con.execute("UPDATE plan_ereignis SET zeit_utc = ? WHERE art LIKE 'thema_%' AND zeit_utc > '2026-11-10'", (T[i],))
            self.con.execute("UPDATE thema_fassung SET zeit_utc = ? WHERE zeit_utc > '2026-11-10'", (T[i],))
            self.con.execute("UPDATE thema SET bestaetigt_utc = ? WHERE bestaetigt_utc > '2026-11-10'", (T[i],))

    def st(self):
        return themen.status(self.con, themen.finden(self.con, self.pid, self.tid))

    def vorlage(self, i, text="Anmeldung mit Firmen-Konto."):
        themen.pflegen(self.con, self.pid, "CC1", self.tid, text)
        self.um(i)

    def beschluss(self, i, stichwort="SSO Pflicht"):
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "beschluss", projekt_id=self.pid, zeit_utc=T[i], stichwort=stichwort, regel="x", quelle="W1",
                                thema="Anmeldung", angelegt_von="TL", angelegt_utc=T[i])

    def post(self, an):
        return [(r["art"], r["kurz"]) for r in self.con.execute(
            "SELECT n.art, n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? AND n.von = 'AMW' ORDER BY n.id", (an,))]


class Vorrang(Grund):
    def test_ohne_text_in_arbeit(self):
        self.assertEqual((self.st()["status"], self.st()["fassung"]), ("arbeit", None))

    def test_vorlage_wartet_auf_dich_mit_ereignis(self):
        self.vorlage(0)
        self.assertEqual((self.st()["status"], self.st()["text"], self.st()["fassung"]), ("dich", "wartet auf dich", 1))
        self.assertEqual(self.con.execute("SELECT count(*) FROM plan_ereignis WHERE art = 'thema_vorgelegt'").fetchone()[0], 1)

    def test_freigabe_zeigt_auf_die_fassung(self):
        self.vorlage(0)
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.um(1)
        self.assertEqual((self.st()["status"], self.st()["freigegeben"]), ("frei", 1))
        self.vorlage(2, "Neu: auch mit Zweitfaktor.")                                       # neuere Fassung → wieder bei dir
        self.assertEqual((self.st()["status"], self.st()["fassung"], self.st()["freigegeben"]), ("dich", 2, 1))

    def test_neu_pruefen_mit_grund_als_wert_und_nicht_fuer_dich(self):
        self.vorlage(0)
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.um(1)
        bid = self.beschluss(2)
        s = self.st()
        self.assertEqual((s["status"], s["grund"]), ("pruefen", f"B{bid} · 01.11."))      # D1326 A10 / Auflage (c)
        self.assertEqual(workbench._themen_fuer_dich(self.con, self.pid), [])               # F5359 A: erst die KI
        themen.bestaetigen(self.con, self.pid, "CC1", self.tid)                               # der Pfleger: gilt weiter
        self.um(3)
        self.assertEqual(self.st()["status"], "dich")

    def test_vorlage_durch_neuen_beschluss_ueberholt_in_arbeit(self):
        self.vorlage(0)
        self.beschluss(1)
        self.assertEqual(self.st()["status"], "arbeit")

    def test_zurueck_in_arbeit_neue_vorlage_wieder_bei_dir(self):
        self.vorlage(0)
        themen.zurueck(self.con, self.pid, kern.ENTWICKLER, self.tid, "Zweitfaktor nur online")
        self.um(1)
        self.assertEqual(self.st()["status"], "arbeit")
        self.vorlage(2)
        self.assertEqual(self.st()["status"], "dich")

    def test_gleiche_sekunde_spaeteres_ereignis_gilt(self):
        themen.pflegen(self.con, self.pid, "CC1", self.tid, "Text")
        themen.zurueck(self.con, self.pid, kern.ENTWICKLER, self.tid, "anders")
        self.assertEqual(self.st()["status"], "arbeit")

    def test_markiert_geht_vor_und_zaehlt_nicht(self):
        self.vorlage(0)
        themen.markieren(self.con, self.pid, kern.ENTWICKLER, self.tid)
        s = self.st()
        self.assertTrue(s["markiert"])
        self.assertEqual(themen.rang(s), 0)
        self.assertEqual(workbench._themen_fuer_dich(self.con, self.pid), [])
        self.assertEqual(self.con.execute("SELECT count(*) FROM thema").fetchone()[0], 1)            # nichts gelöscht (B2894)

    def test_rang_folgt_dem_vorrang(self):
        r = lambda st, m=False: themen.rang({"status": st, "markiert": m})
        self.assertEqual([r("arbeit", True), r("dich"), r("pruefen"), r("frei"), r("arbeit")], [0, 1, 2, 3, 4])


class Handlungen(Grund):
    def test_je_status_nur_moegliche(self):
        self.assertEqual(themen.handlungen(self.st()), ("bearbeiten", "markieren"))
        self.vorlage(0)
        self.assertEqual(themen.handlungen(self.st()), ("freigeben", "zurueck", "bearbeiten", "markieren"))
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.assertEqual(themen.handlungen(self.st()), ("zurueck", "bearbeiten", "markieren"))
        with self.assertRaisesRegex(kern.AmwFehler, "das geht gerade nicht"):
            themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        themen.markieren(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.assertEqual(themen.handlungen(self.st()), ("entmarkieren",))
        themen.markieren(self.con, self.pid, kern.ENTWICKLER, self.tid, an=False)
        self.assertFalse(self.st()["markiert"])

    def test_eigene_bearbeitung_bleibt_freigegeben(self):                                     # F5358 A
        self.vorlage(0)
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.um(1)
        s = themen.bearbeiten(self.con, self.pid, kern.ENTWICKLER, self.tid, "Mein Text.", erwartet=1)
        self.assertEqual((s["status"], s["fassung"], s["freigegeben"]), ("frei", 2, 2))
        self.assertEqual(self.post("CC1")[-1][0], "info")                                     # Hinweis an die KI, kein Auftrag

    def test_speichern_nur_gegen_erwartete_fassung(self):
        self.vorlage(0)
        self.vorlage(1, "Inzwischen neuer.")
        with self.assertRaisesRegex(kern.AmwFehler, "inzwischen Fassung 2"):
            themen.bearbeiten(self.con, self.pid, kern.ENTWICKLER, self.tid, "alt", erwartet=1)
        self.assertEqual(self.st()["fassung"], 2)

    def test_zurueck_nur_mit_notiz_und_nachrichten_an_den_pfleger(self):
        self.vorlage(0)
        with self.assertRaisesRegex(kern.AmwFehler, "nur mit Notiz"):
            themen.zurueck(self.con, self.pid, kern.ENTWICKLER, self.tid, " ")
        themen.zurueck(self.con, self.pid, kern.ENTWICKLER, self.tid, "Zweitfaktor nur online")
        self.assertEqual(self.post("CC1")[-1], ("auftrag", "Thema „Anmeldung“ zurück: Zweitfaktor nur online"))
        self.um(1)
        self.vorlage(2)
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.assertEqual(self.post("CC1")[-1], ("info", "Thema „Anmeldung“ freigegeben (Fassung 2)"))

    def test_mensch_legt_thema_an(self):                                                      # F5360 A
        tid = themen.anlegen_mensch(self.con, self.pid, kern.ENTWICKLER, "Online-Seite", "Nur lesen am Handy.")
        s = themen.status(self.con, themen.finden(self.con, self.pid, tid))
        self.assertEqual((s["status"], s["fassung"]), ("arbeit", 1))
        self.assertIn("Neues Thema", self.post("TL")[-1][1])
        with self.assertRaisesRegex(kern.AmwFehler, "nur der Mensch"):
            themen.anlegen_mensch(self.con, self.pid, "TL", "Noch eins", "")


class Rechte(Grund):
    def test_nur_der_mensch(self):
        self.vorlage(0)
        for von in ("TL", "CC1"):
            for tun in (lambda v: themen.freigeben(self.con, self.pid, v, self.tid), lambda v: themen.markieren(self.con, self.pid, v, self.tid),
                        lambda v: themen.zurueck(self.con, self.pid, v, self.tid, "x"), lambda v: themen.bearbeiten(self.con, self.pid, v, self.tid, "x")):
                with self.assertRaisesRegex(kern.AmwFehler, "nur der Mensch"):
                    tun(von)
        with db.schreiben(self.con), self.assertRaisesRegex(kern.AmwFehler, "nur der Mensch"):
            themen._ereignis(self.con, self.pid, "CC1", "freigegeben", self.tid, fassung=1)          # auch direkt nicht

    def test_workbench_nur_am_pc(self):
        self.vorlage(0)
        with self.assertRaisesRegex(aktionen.Ungueltig, "nur am PC"):
            aktionen.ausfuehren(self.con, self.pid, "/api/thema/freigeben", {"thema": self.tid}, kanal="netz")
        r = aktionen.ausfuehren(self.con, self.pid, "/api/thema/freigeben", {"thema": self.tid}, kanal="seite")
        self.assertEqual(r["status"], "frei")

    def cli(self, *args, env=None):
        from amw import cli
        aus = io.StringIO()
        mensch = {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}
        with mock.patch.dict(os.environ, {**mensch, **(env or {})}), contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "Produkt", *args])
        return rc, aus.getvalue()

    def test_befehl_nur_im_terminal_des_menschen(self):
        self.vorlage(0)
        rc, aus = self.cli("thema", "freigeben", f"TH{self.tid}", "--von", "Entwickler", env={"CLAUDECODE": "1"})
        self.assertNotEqual(rc, 0)
        self.assertIn("nur der Mensch in seinem eigenen Terminal", aus)
        rc, aus = self.cli("thema", "freigeben", f"TH{self.tid}", "--von", "CC1", env={"CLAUDECODE": "1"})
        self.assertNotEqual(rc, 0)
        self.assertEqual(self.st()["status"], "dich")
        rc, aus = self.cli("thema", "freigeben", f"TH{self.tid}", "--von", "Entwickler")
        self.assertEqual(rc, 0, aus)
        self.assertEqual(self.st()["status"], "frei")

    def test_mcp_kennt_keine_handlung_des_menschen(self):
        from amw import mcp_server
        namen = set(mcp_server.WERKZEUGE)
        self.assertTrue({"thema_status", "thema_zeige", "thema_pflegen"} <= namen)
        self.assertFalse({n for n in namen if n.startswith("thema_") and any(w in n for w in ("freigeb", "zurueck", "markier", "bearbeit"))})


class Unterschied(Grund):
    def test_neue_vorlage_nach_eigener_bearbeitung_zeigt_unterschied(self):           # F5358 Ergänzung (#29401)
        self.vorlage(0)
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.um(1)
        themen.bearbeiten(self.con, self.pid, kern.ENTWICKLER, self.tid, "Mein Text.", erwartet=1)
        self.um(2)
        self.assertIsNone(themen.seite(self.con, self.pid, self.tid)["freigegeben_text"])     # freigegeben: nichts zu vergleichen
        self.vorlage(3, "Mein Text.\n\nDazu: Zweitfaktor nur online.")
        s = themen.seite(self.con, self.pid, self.tid)
        self.assertEqual((s["zustand"]["status"], s["zustand"]["fassung"], s["zustand"]["freigegeben"]), ("dich", 3, 2))
        self.assertEqual(s["freigegeben_text"], {"nr": 2, "text": "Mein Text."})


class Anzeige(Grund):
    def test_fuer_dich_und_seite(self):
        self.assertEqual(workbench._themen_fuer_dich(self.con, self.pid), [])
        self.vorlage(0)
        self.assertEqual([(x["id"], x["status"]) for x in workbench._themen_fuer_dich(self.con, self.pid)], [(self.tid, "dich")])
        s = themen.seite(self.con, self.pid, self.tid)
        self.assertEqual((s["zustand"]["status"], s["handlungen"]), ("dich", ["freigeben", "zurueck", "bearbeiten", "markieren"]))
        l = themen.liste(self.con, self.pid)[0]
        self.assertEqual((l["zustand"]["status"], l["neu_erlaubt"]), ("dich", True))


if __name__ == "__main__":
    unittest.main()
