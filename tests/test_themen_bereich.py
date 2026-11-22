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
import types
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

    def test_a1908_co_entwickler_darf_themen_anlegen(self):
        """#29564: „amw thema neu“ lehnte den Co-Entwickler ab – Themen sind Konzept (W2408/B2905)."""
        from amw import mcp_server
        with self.assertRaisesRegex(kern.AmwFehler, "Lead, Entwickler und der Co-Entwickler"):
            themen.neu(self.con, self.pid, "CC1", "Ohne Rolle")                                   # ohne Rolle: nein
        with self.assertRaisesRegex(kern.AmwFehler, "nur Lead und Entwickler"):
            kern.projekt_einstellen(self.con, self.pid, "CC1", co_entwickler="CC1")             # sich selbst dazu machen: nein
        for env in ({"CLAUDECODE": "1"}, {"CLAUDE_CODE_MESSAGING_SOCKET": r"\\.\pipe\x"}):         # P352: auch nicht als „Entwickler“
            rc, aus = self.cli("projekt", "einstellen", "co_entwickler=CC1", "--von", "Entwickler", env=env)   # aus der Sitzung
            self.assertNotEqual(rc, 0, aus)
            self.assertIn("nicht aus einer Agenten-Sitzung", aus)
        self.assertIsNone(kern.co_entwickler(self.con, self.pid))
        rc, aus = self.cli("projekt", "einstellen", "co_entwickler=CC1", "--von", "Entwickler")    # Terminal des Menschen: ja
        self.assertEqual((rc, kern.co_entwickler(self.con, self.pid)), (0, "CC1"), aus)
        kern.projekt_einstellen(self.con, self.pid, "TL", co_entwickler="")
        kern.projekt_einstellen(self.con, self.pid, "TL", co_entwickler="CC1")
        tid = themen.neu(self.con, self.pid, "CC1", "Konzept Rollen")
        self.assertEqual(themen.finden(self.con, self.pid, tid)["angelegt_von"], "CC1")
        for mehr in ({"pfleger": "CC1"}, {"stil": True}):                                          # Pfleger/Stil bleiben beim Lead
            with self.assertRaisesRegex(kern.AmwFehler, "Pfleger und Stil setzen dürfen Lead und Entwickler"):
                themen.neu(self.con, self.pid, "CC1", "Noch eins", **mehr)
        rc, aus = self.cli("thema", "neu", "Konzept Rechte", "--von", "CC1", env={"AMW_AGENT": "CC1"})   # CLI wie MCP
        self.assertEqual(rc, 0, aus)
        argv = mcp_server.befehlszeile("thema_neu", {"name": "Konzept Speicher"}) + ["--projekt", "Produkt", "--von", "CC1"]
        with mock.patch.dict(os.environ, {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}):
            w = mcp_server.befehl_ausfuehren(argv)
        self.assertEqual(w[0], 0, w)
        self.assertEqual(sorted(r[0] for r in self.con.execute("SELECT name FROM thema WHERE angelegt_von = 'CC1'")),
                         ["Konzept Rechte", "Konzept Rollen", "Konzept Speicher"])
        for tun in (themen.freigeben, themen.markieren):                                          # Freigeben & Co. bleiben beim Menschen
            with self.assertRaisesRegex(kern.AmwFehler, "nur der Mensch"):
                tun(self.con, self.pid, "CC1", tid)
        kern.projekt_einstellen(self.con, self.pid, "TL", co_entwickler="")                       # Rolle weg: wieder nein
        with self.assertRaisesRegex(kern.AmwFehler, "Lead, Entwickler und der Co-Entwickler"):
            themen.neu(self.con, self.pid, "CC1", "Danach")

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


class Tor(Grund):
    """A1913 (D1304 v12 §2, W2449): kein Knopf – das Tor Konzept schließt mit der letzten nötigen Freigabe, vorher weiß die Seite,
    welche Handlung es schlösse; abgeleitet, also wieder offen bei Zurück, neuem Thema, neuer Vorlage oder „neu prüfen“."""
    def setUp(self):
        super().setUp()
        self.zwei = themen.neu(self.con, self.pid, "TL", "Speichern", pfleger="CC1")
        for tid in (self.tid, self.zwei):
            themen.pflegen(self.con, self.pid, "CC1", tid, f"Text {tid}.")
        self.um(0)

    def tor(self, tid=None):
        return themen.tor(self.con, self.pid, tid)

    def geschlossen(self):
        return themen.tor_ereignisse(self.con, self.pid)

    def test_zaehlt_und_schliesst_mit_der_letzten_freigabe(self):
        self.assertEqual(self.tor(), {"tor": "konzept", "konzept_zu": False, "n": 0, "g": 2})
        self.assertEqual(self.tor(self.tid)["schliesst"], [])                           # zwei offen: keine schließt
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.assertEqual(self.tor()["n"], 1)
        self.assertEqual(self.tor(self.zwei)["schliesst"], ["freigeben", "bearbeiten", "markieren"])   # das letzte offene
        self.assertEqual(self.tor(self.tid)["schliesst"], [])                           # das freigegebene schließt nichts
        self.assertEqual(themen.seite(self.con, self.pid, self.zwei)["tor"]["schliesst"], ["freigeben", "bearbeiten", "markieren"])
        self.assertEqual(self.geschlossen(), [])
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.zwei)
        self.assertEqual(self.tor(), {"tor": "grobplanung", "konzept_zu": True, "n": 2, "g": 2})
        e = self.geschlossen()
        self.assertEqual(len(e), 1)
        self.assertEqual((e[0]["tor"], e[0]["von"], e[0]["themen"]),
                         ("konzept", kern.ENTWICKLER, [{"thema": self.tid, "fassung": 1}, {"thema": self.zwei, "fassung": 1}]))
        self.assertEqual(self.tor(self.tid)["schliesst"], [])                           # zu: nichts mehr zu schließen

    def test_wieder_offen_abgeleitet_und_neu_geschlossen(self):
        for tid in (self.tid, self.zwei):
            themen.freigeben(self.con, self.pid, kern.ENTWICKLER, tid)
        self.um(1)
        themen.zurueck(self.con, self.pid, kern.ENTWICKLER, self.zwei, "Noch die Sicherung")   # Zurück öffnet
        self.assertEqual(self.tor(), {"tor": "konzept", "konzept_zu": False, "n": 1, "g": 2})
        self.um(2)
        themen.pflegen(self.con, self.pid, "CC1", self.zwei, "Mit Sicherung.")
        self.um(3)
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.zwei)
        self.assertTrue(self.tor()["konzept_zu"])
        self.assertEqual([x["themen"][1]["fassung"] for x in self.geschlossen()], [2, 1])   # zweimal, mit den Fassungen
        self.um(4)
        self.beschluss(5)                                                                  # „neu prüfen“ öffnet
        self.assertEqual((self.tor()["konzept_zu"], self.tor()["n"]), (False, 1))
        self.beschluss_weg()
        dritt = themen.anlegen_mensch(self.con, self.pid, kern.ENTWICKLER, "Online-Seite", "")   # neues Thema öffnet
        self.assertEqual(self.tor(), {"tor": "konzept", "konzept_zu": False, "n": 2, "g": 3})
        themen.markieren(self.con, self.pid, kern.ENTWICKLER, dritt)                       # markierte zählen nicht: schließt
        self.assertTrue(self.tor()["konzept_zu"])
        self.assertEqual(len(self.geschlossen()), 3)
        self.assertEqual(self.tor(dritt)["schliesst"], [])

    def beschluss_weg(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE beschluss SET status = 'ueberholt' WHERE projekt_id = ?", (self.pid,))

    def test_eigene_bearbeitung_des_letzten_schliesst(self):                               # F5358 A: gilt als Freigabe
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        themen.bearbeiten(self.con, self.pid, kern.ENTWICKLER, self.zwei, "Mein Text.", erwartet=1)
        self.assertTrue(self.tor()["konzept_zu"])
        self.assertEqual(self.geschlossen()[0]["themen"][1], {"thema": self.zwei, "fassung": 2})

    def test_ohne_zaehlende_themen_bleibt_es_offen(self):
        with db.schreiben(self.con):
            pid = db.einfuegen(self.con, "projekt", name="Leer", angelegt_utc=db.jetzt())
        self.assertEqual(themen.tor(self.con, pid), {"tor": "konzept", "konzept_zu": False, "n": 0, "g": 0})   # ohne Themen: offen
        tid = themen.neu(self.con, pid, kern.ENTWICKLER, "Ohne Text")
        self.assertEqual(themen.tor(self.con, pid, tid)["schliesst"], ["bearbeiten"])      # „in Arbeit“: nur dein eigener Text schlösse
        themen.markieren(self.con, pid, kern.ENTWICKLER, tid)
        self.assertEqual(themen.tor(self.con, pid), {"tor": "konzept", "konzept_zu": False, "n": 0, "g": 0})   # nichts zählt: nicht zu
        self.assertEqual(themen.tor(self.con, pid, tid)["schliesst"], [])                  # aufheben: wieder „in Arbeit“
        self.assertEqual(themen.tor_ereignisse(self.con, pid), [])

    def test_befehl_nennt_das_tor(self):
        from amw import cli
        a = types.SimpleNamespace(aktion="status", projekt=None, von=kern.ENTWICKLER, suche=None, name=None)
        with mock.patch.object(cli, "_projekt", return_value=self.pid), contextlib.redirect_stdout(io.StringIO()) as aus:
            cli.cmd_thema(a, self.con)
        self.assertEqual(aus.getvalue().splitlines()[0], "Konzept · 0 von 2 Themen freigegeben")
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        a = types.SimpleNamespace(aktion="freigeben", projekt=None, von=kern.ENTWICKLER, suche=None, notiz=None, name=f"TH{self.zwei}")
        with mock.patch.object(cli, "_projekt", return_value=self.pid), mock.patch.object(cli, "_von", return_value=kern.ENTWICKLER), \
                mock.patch.object(cli, "_aus_agenten_sitzung", return_value=False), contextlib.redirect_stdout(io.StringIO()) as aus:
            cli.cmd_thema(a, self.con)
        self.assertIn("Damit ist das Tor Konzept geschlossen – Grobplanung · Konzept fertig: 2 von 2 Themen freigegeben", aus.getvalue())


if __name__ == "__main__":
    unittest.main()
