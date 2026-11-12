"""Tests für die Wünsche der Agenten aus der Umfrage (AMW 1.10.0): lesen/erledigt, Nummern mit Vorsilbe, abmelden,
„alle“, Einzel-Info weckt, Alter der Tätigkeit, Nachtrag, Hinweise, Startskript, Pfade, Aufruf-Fehler, Wartemeldung."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import io
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from amw import betrieb, cli, db, dienst, kern, steuerung, wartegrund


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.pfad = os.path.join(self.ordner.name, "t.db")
        self.con = db.anlegen(self.pfad)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        for k, r in (("TL", "lead"), ("CC1", None), ("CC2", None), ("CC3", None)):
            kern.agent_neu(self.con, self.pid, k, rolle=r)
        self.a = kern.aufgabe_neu(self.con, self.pid, "TL", "Onboarding prüfen", agent="CC1")

    def tearDown(self):
        self.con.close()
        self.ordner.cleanup()

    def sitzung(self, kennung, **werte):
        a = kern.agent_zeile(self.con, self.pid, kennung)
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "sitzung", agent_id=a["id"], gestartet_utc=db.jetzt(), **werte)

    def cli(self, *args):
        os.environ["AMW_DB"] = self.pfad
        aus, fehler = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(aus), redirect_stderr(fehler):
                try:
                    rc = cli.main(list(args))
                except SystemExit as e:
                    rc = e.code
        finally:
            os.environ.pop("AMW_DB", None)
        return rc, aus.getvalue() + fehler.getvalue()


class Lesen(Grund):
    def test_mehrere_nummern_neu_und_verlauf(self):
        n1, _ = kern.posten(self.con, self.pid, "TL", "CC1", "auftrag", "erster")
        n2, _ = kern.posten(self.con, self.pid, "TL", "CC1", "auftrag", "zweiter")
        n3, _ = kern.posten(self.con, self.pid, "TL", "CC1", "auftrag", "dritter")
        rc, aus = self.cli("--von", "CC1", "lesen", str(n1), f"#{n2}")            # mehrere, auch mit #
        self.assertEqual(rc, 0)
        self.assertIn("erster", aus)
        self.assertIn("zweiter", aus)
        rc, aus = self.cli("--von", "CC1", "lesen", "--neu")                       # nur Ungelesenes
        self.assertIn("dritter", aus)
        self.assertNotIn("erster", aus)
        self.assertIn("1 ungelesen", aus)
        kern.erledigt(self.con, self.pid, "CC1", [n1, n2, n3])
        rc, aus = self.cli("--von", "CC1", "lesen", "--verlauf")                   # auch Erledigtes, neueste zuerst
        self.assertLess(aus.index("dritter"), aus.index("erster"))
        self.assertIn("(erledigt)", aus)

    def test_zeile_sagt_wenn_aufgabe_schon_fertig(self):
        kern.posten(self.con, self.pid, "TL", "CC1", "auftrag", "mach", aufgabe_id=self.a)
        kern.aufgabe_status(self.con, self.pid, "TL", self.a, "fertig", beleg="abc")
        rc, aus = self.cli("--von", "CC1", "lesen")
        self.assertIn(f"(A{self.a} schon fertig)", aus)


class Nummern(Grund):
    def test_vorsilben_werden_angenommen(self):
        rc, aus = self.cli("--von", "CC1", "aufgabe", "zeige", f"A{self.a}", "--kurz")
        self.assertEqual(rc, 0, aus)
        self.assertIn(f"A{self.a} [wartet] CC1 · Onboarding prüfen", aus)
        rc, aus = self.cli("--von", "CC1", "aufgabe", "zeige", f"a{self.a}")
        self.assertIn("titel: Onboarding prüfen", aus)
        rc, aus = self.cli("--von", "CC1", "posten", "--an", "TL", "--art", "info", "--kurz", "x", "--aufgabe", f"A{self.a}")
        self.assertEqual(rc, 0, aus)

    def test_keine_nummer_meldet_den_grund_zuerst(self):
        rc, aus = self.cli("--von", "CC1", "aufgabe", "zeige", "Axy")
        self.assertEqual(rc, 2)
        self.assertTrue(aus.startswith("FEHLER: amw aufgabe: argument id: keine Nummer"), aus)

    def test_falscher_wert_nennt_die_erlaubten_in_der_ersten_zeile(self):
        rc, aus = self.cli("--von", "TL", "dokument", "ablegen", "x.md", "--titel", "t", "--art", "plan")
        self.assertEqual(rc, 2)
        erste = aus.splitlines()[0]
        self.assertIn("invalid choice: 'plan'", erste)
        self.assertIn("ergebnis", erste)


class Erledigt(Grund):
    def test_alte_infos_auf_einmal(self):
        alt, _ = kern.posten(self.con, self.pid, "TL", "CC1", "info", "alt")
        with db.schreiben(self.con):
            self.con.execute("UPDATE nachricht SET zeit_utc = '2026-11-01T10:00:00Z' WHERE id = ?", (alt,))
        neu, _ = kern.posten(self.con, self.pid, "TL", "CC1", "info", "neu")
        auftrag, _ = kern.posten(self.con, self.pid, "TL", "CC1", "auftrag", "bleibt")
        rc, aus = self.cli("--von", "CC1", "erledigt", "--info", "--vor", "02.11.2026")
        self.assertIn("1 info erledigt", aus)
        self.assertEqual([r["kurz"] for r in kern.offene(self.con, self.pid, "CC1")], ["neu", "bleibt"])
        rc, aus = self.cli("--von", "CC1", "erledigt", "--info")
        self.assertEqual([r["kurz"] for r in kern.offene(self.con, self.pid, "CC1")], ["bleibt"])
        rc, aus = self.cli("--von", "CC1", "erledigt")
        self.assertEqual(rc, 1)

    def test_meldung_der_amw_geht_mit_der_nachricht(self):
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "start")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "wartet", auf="CC2")
        nid, _ = kern.posten(self.con, self.pid, "CC2", "CC1", "antwort", "erledigt von mir", aufgabe_id=self.a)
        offen = [r["kurz"] for r in kern.offene(self.con, self.pid, "CC1")]
        self.assertEqual(len(offen), 2)                                         # echte Nachricht + „CC2 hat geschrieben“
        kern.erledigt(self.con, self.pid, "CC1", [nid])
        self.assertEqual(kern.offene(self.con, self.pid, "CC1"), [])

    def test_aufgabe_start_raeumt_weiter_meldung_ab(self):
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "start")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "wartet", auf="CC2")
        kern.posten(self.con, self.pid, "CC2", "TL", "info", "fertig von mir", aufgabe_id=self.a)
        self.assertTrue(any("weiter" in r["kurz"] for r in kern.offene(self.con, self.pid, "CC1")))
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "start")
        self.assertEqual(kern.offene(self.con, self.pid, "CC1"), [])
        self.assertTrue(kern.offene(self.con, self.pid, "TL"))                 # die Kopie des Leads bleibt bei ihm


class Abmelden(Grund):
    def test_ruht_weckt_nicht_und_lead_weiss_es(self):
        s = self.sitzung("CC1", schluessel_datei="x.json")
        rc, aus = self.cli("--von", "CC1", "abmelden")
        self.assertEqual(rc, 0, aus)
        z = self.con.execute("SELECT zustand, taetigkeit, beendet_utc FROM sitzung WHERE id = ?", (s,)).fetchone()
        self.assertEqual((z["zustand"], z["taetigkeit"], z["beendet_utc"]), ("ruht", "abgemeldet", None))
        self.assertIsNone(dienst.aktive_sitzung(self.con, self.pid, "CC1"))     # Wecker findet sie nicht mehr
        self.assertEqual(steuerung.Neustarter(self.con).kandidaten(self.pid), [])  # kein automatischer Neustart
        self.assertIn("CC1 hat sich abgemeldet", kern.offene(self.con, self.pid, "TL")[0]["kurz"])
        rc, aus = self.cli("--von", "CC1", "abmelden")
        self.assertEqual(rc, 1)
        self.assertIn("nicht angemeldet", aus)


class Alle(Grund):
    def test_alle_erreicht_laufende_sitzung_trotz_soll_aus_und_meldet_ausgelassene(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE agent SET soll = 'aus' WHERE kennung IN ('CC2', 'CC3')")
        self.sitzung("CC2")                                                    # läuft trotz Soll aus
        hinweise = []
        _, namen = kern.posten(self.con, self.pid, "TL", "alle", "info", "Rundschreiben", hinweise=hinweise)
        self.assertEqual(namen, ["CC1", "CC2"])
        self.assertEqual(hinweise, ["nicht erreicht: CC3 (Soll aus, keine Sitzung)"])


class Wecken(Grund):
    def test_einzel_info_weckt_sammel_info_und_altbestand_nicht(self):
        alt, _ = kern.posten(self.con, self.pid, "TL", "CC1", "info", "vor dem Dienststart")
        with db.schreiben(self.con):
            self.con.execute("UPDATE nachricht SET zeit_utc = '2026-11-01T10:00:00Z' WHERE id = ?", (alt,))
        d = dienst.Dienst(self.con)
        einzeln, _ = kern.posten(self.con, self.pid, "CC3", "CC1", "info", "Merge erledigt")
        kern.posten(self.con, self.pid, "TL", "CC1,CC2", "info", "an zwei")
        offen = self.con.execute(
            "SELECT e.nachricht_id FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id JOIN nachricht_art k"
            " ON k.art = n.art WHERE e.agent = 'CC1' AND (k.weckt = 1 OR (n.zeit_utc >= ? AND " + kern.WECKT_SQL + "))",
            (d.seit,)).fetchall()
        self.assertEqual([r[0] for r in offen], [einzeln])


class Taetigkeit(Grund):
    def test_alter_und_automatisch_nur_wenn_leer_oder_alt(self):
        s = self.sitzung("CC1")
        kern.taetigkeit(self.con, self.pid, "CC1", "A12: Prüfbitte an CC2")
        self.assertIsNotNone(self.con.execute("SELECT taetigkeit_utc FROM sitzung WHERE id = ?", (s,)).fetchone()[0])
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "start")         # eigene, frische Angabe bleibt
        self.assertEqual(self.con.execute("SELECT taetigkeit FROM sitzung WHERE id = ?", (s,)).fetchone()[0],
                         "A12: Prüfbitte an CC2")
        with db.schreiben(self.con):
            self.con.execute("UPDATE sitzung SET taetigkeit_utc = '2026-11-01T10:00:00Z' WHERE id = ?", (s,))
        rc, aus = self.cli("--von", "TL", "agent", "liste")
        self.assertIn("veraltet?", aus)
        betrieb.lauf_start(self.con, self.pid, "CC1", "Proben opa, labor", aufgabe_id=self.a,
                           speicher_frei=30.0)            # fest: sonst hängt der Test am freien Speicher des PCs
        self.assertTrue(self.con.execute("SELECT taetigkeit FROM sitzung WHERE id = ?", (s,)).fetchone()[0]
                        .endswith("Proben opa, labor"))

    def test_freigabe_zeile_kuerzt_an_wortgrenze(self):
        lang = "Abläufe opa, ae1_auftraege, labor, start, worldmap_ae1 mit Fenster und Bildschirmfotos je Ära für die Abnahme"
        k = betrieb.kurzfassung(lang, 60)
        self.assertTrue(k.endswith(" …"))
        self.assertTrue(lang.startswith(k[:-2]))
        self.assertEqual(betrieb.kurzfassung("kurz"), "kurz")


class Nachtrag(Grund):
    def test_fertige_aufgabe_bekommt_nachtrag(self):
        kern.aufgabe_status(self.con, self.pid, "TL", self.a, "fertig", beleg="abc")
        with self.assertRaises(kern.AmwFehler) as f:
            kern.posten(self.con, self.pid, "TL", "CC1", "auftrag", "noch was", aufgabe_id=self.a)
        self.assertIn(f"amw aufgabe nachtrag {self.a}", str(f.exception))
        rc, aus = self.cli("--von", "TL", "aufgabe", "nachtrag", f"A{self.a}", "--titel", "Anker-Licht")
        self.assertEqual(rc, 0, aus)
        neu = self.con.execute("SELECT * FROM aufgabe WHERE id != ? ORDER BY id DESC LIMIT 1", (self.a,)).fetchone()
        self.assertEqual((neu["titel"], neu["agent"]), (f"Nachtrag A{self.a}: Anker-Licht", "CC1"))
        self.assertIn(f"Nachtrag zu A{self.a}", neu["auftrag"])
        with self.assertRaises(kern.AmwFehler):                                  # fremde Aufgabe: nur Besitzer oder Lead
            kern.aufgabe_nachtrag(self.con, self.pid, "CC2", self.a, "x")


class Hinweis(Grund):
    def test_fremde_aufgabe_nur_beim_ersten_mal(self):
        h = []
        kern.posten(self.con, self.pid, "CC3", "CC1", "info", "gemergt", aufgabe_id=self.a, hinweise=h)
        self.assertTrue(any("gehört CC1" in x for x in h))
        h = []
        kern.posten(self.con, self.pid, "CC3", "CC1", "info", "noch einer", aufgabe_id=self.a, hinweise=h)
        self.assertFalse(any("gehört CC1" in x for x in h))


class Startskript(Grund):
    def test_zeitversetzt_und_alle(self):
        for k in ("CC1", "CC2"):
            with db.schreiben(self.con):
                self.con.execute("UPDATE agent SET ordner = 'F:/p' WHERE kennung = ?", (k,))
        with db.schreiben(self.con):
            self.con.execute("UPDATE agent SET soll = 'aus' WHERE kennung = 'CC2'")
        with mock.patch.object(steuerung, "letzte_sitzung", return_value=None):
            nur_an = steuerung.startskript(self.con, self.pid)
            alle = steuerung.startskript(self.con, self.pid, alle=True, abstand_s=15)
        self.assertNotIn("timeout /t", nur_an)
        self.assertNotIn("--title CC2", nur_an)
        self.assertIn("--title CC2", alle)
        self.assertEqual(alle.count("timeout /t 15 /nobreak"), 1)
        self.assertEqual(alle.count(" new-tab --title "), 2)


PNG = bytes([0x89]) + b"PNG" + bytes([13, 10, 26, 10])


class DateienOnline(Grund):
    def ablegen(self, name, inhalt=PNG + b"x"):
        p = os.path.join(self.ordner.name, name)
        with open(p, "wb") as f:
            f.write(inhalt)
        from amw import dokumente
        return dokumente.ablegen(self.con, self.pid, "CC1", p, name)

    def online(self, did):
        return self.con.execute("SELECT online FROM dokument WHERE id = ?", (did,)).fetchone()[0]

    def test_bilder_von_selbst_online_auch_vorhandene(self):
        os.environ["AMW_DB"] = self.pfad
        try:
            alt_bild, alt_text, alt_pdf = self.ablegen("a.png"), self.ablegen("b.md", b"# Text"), self.ablegen("c.pdf", b"%PDF-1.4 x")
            self.assertEqual(kern.projekt_wahl(self.con, self.pid, "dateien_online"), "wunsch")
            self.assertEqual(self.online(alt_bild), 0)                            # Vorgabe: wie bisher nur auf Wunsch
            kern.projekt_einstellen(self.con, self.pid, "TL", dateien_online="bilder")
            self.assertEqual((self.online(alt_bild), self.online(alt_pdf)), (1, 0))
            self.assertEqual(self.online(self.ablegen("d.html", b"<p>m</p>")), 1)   # neue Mockups gleich mit
            kern.projekt_einstellen(self.con, self.pid, "TL", dateien_online="wunsch")
            self.assertEqual(self.online(alt_bild), 1)                            # zurück nimmt nichts herunter
            self.assertEqual(self.online(self.ablegen("e.png", PNG + b"y")), 0)
            with self.assertRaises(kern.AmwFehler):
                kern.projekt_einstellen(self.con, self.pid, "TL", dateien_online="immer")
        finally:
            os.environ.pop("AMW_DB", None)


class LaufAusfuehren(Grund):
    """lauf ausfuehren: einreihen, warten, starten, rc durchreichen, Ende melden; Bildschirm zu/Frist beenden den Befehl."""

    def setUp(self):
        super().setUp()
        self.sitzung("CC1")
        self.aus = os.path.join(self.ordner.name, "aus.txt")
        from amw import schirm                     # sonst hinge der Bildschirm-Test an echter Eingabe am PC (der Mensch tippt)
        p = mock.patch.object(schirm, "leerlauf_s", return_value=600)
        p.start()
        self.addCleanup(p.stop)

    def lauf(self):
        return self.con.execute("SELECT * FROM lauf ORDER BY id DESC LIMIT 1").fetchone()

    def test_rc_durchreichen_und_ergebnis_datei(self):
        rc, aus = self.cli("--von", "CC1", "lauf", "ausfuehren", "--beschreibung", "Probe", "--leicht", "--ergebnis", self.aus,
                           "--", sys.executable, "-c", "print('hallo aus dem Lauf'); import sys; sys.exit(3)")
        self.assertEqual(rc, 3, aus)
        self.assertIn("hallo aus dem Lauf", aus)
        l = self.lauf()
        self.assertEqual((l["status"], l["rc"]), ("fertig", 3))
        self.assertIn("hallo aus dem Lauf", l["ergebnis"])
        with open(self.aus, encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith(f"# AMW L{l['id']} · CC1 · Probe"))
        self.assertIn("# Ende: ", text)
        self.assertIn("rc 3", text.splitlines()[-1])

    def test_frist_beendet_den_baum(self):
        with mock.patch.object(cli, "PRUEF_S", 1):
            t = time.time()
            rc, aus = self.cli("--von", "CC1", "lauf", "ausfuehren", "--beschreibung", "lang", "--leicht", "--frist", "0.03",
                               "--", sys.executable, "-c", "import time; time.sleep(60)")
        self.assertEqual(rc, cli.RC_FRIST, aus)
        self.assertLess(time.time() - t, 30)
        self.assertEqual(self.lauf()["status"], "abgebrochen")

    def test_schirm_zu_beendet_den_befehl(self):
        from amw import schirm
        schirm.setzen(self.con, self.pid, "TL", True, "Entwickler weg")
        def zu():
            time.sleep(2)
            c = db.verbinde(self.pfad)
            schirm.setzen(c, self.pid, "CC2", False, "Entwickler ist da")
            c.close()
        import threading
        threading.Thread(target=zu, daemon=True).start()
        with mock.patch.object(cli, "PRUEF_S", 1):
            rc, aus = self.cli("--von", "CC1", "lauf", "ausfuehren", "--beschreibung", "Fenster", "--schirm", "--leicht",
                               "--", sys.executable, "-c", "import time; time.sleep(60)")
        self.assertEqual(rc, cli.RC_SCHIRM, aus)
        self.assertEqual(self.lauf()["status"], "abgebrochen")

    def test_ohne_befehl_und_wartezeit_um(self):
        rc, aus = self.cli("--von", "CC1", "lauf", "ausfuehren", "--beschreibung", "x")
        self.assertEqual(rc, 1)
        self.assertIn("der Befehl steht nach --", aus)
        rc, aus = self.cli("--von", "CC1", "lauf", "ausfuehren", "--beschreibung", "Fenster", "--schirm", "--leicht",
                           "--hoechstens", "0.001", "--", sys.executable, "-c", "print(1)")   # Bildschirm zu: kommt nie dran
        self.assertEqual(rc, cli.RC_NIE, aus)
        self.assertEqual(self.lauf()["status"], "abgebrochen")


class Federfuehrung(Grund):
    def setUp(self):
        super().setUp()
        from amw import planung
        self.b = planung.bogen_neu(self.con, self.pid, "TL", "Testbuild", abnahme="läuft")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET bogen_id = ? WHERE id = ?", (self.b, self.a))

    def test_zustaendig_kette_und_empfaenger(self):
        self.assertEqual(kern.zustaendig(self.con, self.pid, self.a), "TL")                    # ohne: der Lead
        with self.assertRaises(kern.AmwFehler):
            kern.federfuehrung_setzen(self.con, self.pid, "CC1", "bogen", self.b, "CC3")    # nur Lead/Entwickler
        rc, aus = self.cli("--von", "TL", "bogen", "aendern", str(self.b), "--federfuehrend", "CC3")
        self.assertEqual(rc, 0, aus)
        self.assertEqual(kern.zustaendig(self.con, self.pid, self.a), "CC3")                   # Bogen
        self.assertIn("Du führst jetzt Meilenstein", kern.offene(self.con, self.pid, "CC3")[0]["kurz"])
        kern.federfuehrung_setzen(self.con, self.pid, "TL", "aufgabe", self.a, "CC2")
        self.assertEqual(kern.zustaendig(self.con, self.pid, self.a), "CC2")                   # Aufgabe vor Bogen
        _, namen = kern.posten(self.con, self.pid, "CC1", "zustaendig", "frage", "passt das?", aufgabe_id=self.a)
        self.assertEqual(namen, ["CC2"])
        with self.assertRaises(kern.AmwFehler):
            kern.posten(self.con, self.pid, "CC1", "zustaendig", "frage", "ohne Aufgabe")
        self.assertIn("Du führst", kern.kontext(self.con, self.pid, "CC2"))
        kern.federfuehrung_setzen(self.con, self.pid, "TL", "aufgabe", self.a, "")
        self.assertEqual(kern.zustaendig(self.con, self.pid, self.a), "CC3")

    def test_frage_und_pruefergebnis_gehen_an_den_federfuehrenden(self):
        kern.federfuehrung_setzen(self.con, self.pid, "TL", "bogen", self.b, "CC3")
        fid = kern.frage_neu(self.con, self.pid, "CC1", "zustaendig", "Welche Wand?", [("A", "hell"), ("B", "dunkel")], "A",
                             "weil", aufgabe_id=self.a)
        self.assertTrue(any(f"Frage F{fid}" in r["kurz"] for r in kern.offene(self.con, self.pid, "CC3")))
        self.assertFalse(any(f"Frage F{fid}" in r["kurz"] for r in kern.offene(self.con, self.pid, "TL")))
        prid = betrieb.pruefbitte(self.con, self.pid, "CC1", "CC2", "cc1-x", "abcdef123456", aufgabe_id=self.a)
        betrieb.pruefung_ergebnis(self.con, self.pid, "CC2", prid, "gruen")
        self.assertTrue(any(f"P{prid} GRUEN" in r["kurz"].upper().replace("Ü", "UE") for r in kern.offene(self.con, self.pid, "CC3")))

    def test_eskalation_einmal_an_den_lead(self):
        kern.federfuehrung_setzen(self.con, self.pid, "TL", "bogen", self.b, "CC3")
        nid, _ = kern.posten(self.con, self.pid, "CC1", "zustaendig", "frage", "bitte abnehmen", aufgabe_id=self.a)
        self.assertEqual(kern.eskalieren(self.con, self.pid), [])                               # noch frisch
        with db.schreiben(self.con):
            self.con.execute("UPDATE nachricht SET zeit_utc = '2026-11-01T10:00:00Z' WHERE id = ?", (nid,))
        self.assertEqual(kern.eskalieren(self.con, self.pid), [nid])
        self.assertEqual(kern.eskalieren(self.con, self.pid), [])                               # nur einmal
        self.assertTrue(any(f"Eskalation #{nid}" in r["kurz"] for r in kern.offene(self.con, self.pid, "TL")))


class Arbeitsliste(Grund):
    """B2429: geordnete Liste je Agent, genau eine in Arbeit, die nächste von selbst."""

    def setUp(self):
        super().setUp()
        self.b = kern.aufgabe_neu(self.con, self.pid, "TL", "Zweite", agent="CC1")
        self.c = kern.aufgabe_neu(self.con, self.pid, "TL", "Dritte", agent="CC1")
        from amw import arbeitsliste
        self.al = arbeitsliste

    def ids(self, agent="CC1"):
        return [x["id"] for x in self.al.liste(self.con, self.pid, agent)]

    def test_ordnen_schieben_pool(self):
        idee = kern.aufgabe_neu(self.con, self.pid, "TL", "Idee aus dem Chat")
        from amw import wissen
        wissen.einstufen(self.con, self.pid, "TL", idee, "pool")
        self.assertIn(idee, [x["id"] for x in self.al.pool(self.con, self.pid)])
        with self.assertRaises(kern.AmwFehler):
            self.al.ordnen(self.con, self.pid, "CC1", "CC1", [self.c])                  # nur Lead
        rc, aus = self.cli("--von", "TL", "liste", "ordnen", "CC1", f"A{self.c}", f"A{idee}")
        self.assertEqual(rc, 0, aus)
        self.assertEqual(self.ids(), [self.c, idee, self.a, self.b])                   # Rest dahinter, Idee zugeteilt
        self.assertNotIn(idee, [x["id"] for x in self.al.pool(self.con, self.pid)])
        rc, aus = self.cli("--von", "TL", "liste", "schieben", f"A{self.b}", "--vor", f"A{self.c}")
        self.assertEqual(self.ids(), [self.b, self.c, idee, self.a])
        rc, aus = self.cli("--von", "TL", "liste", "schieben", f"A{self.b}", "--unten")
        self.assertEqual(self.ids()[-1], self.b)
        rc, aus = self.cli("--von", "CC1", "liste", "CC1")
        self.assertIn(f"1. A{self.c}", aus)

    def test_obere_wird_frei_waehrend_untere_laeuft_kommt_danach(self):
        """Eins nach dem anderen: Wird ein oberes Stück frei, während ein unteres läuft, wird das untere erst fertig."""
        kern.aufgabe_status(self.con, self.pid, "CC1", self.b, "start")                 # Pos 2 läuft …
        kern.aufgabe_status(self.con, self.pid, "CC1", self.b, "wartet", auf="Monitor:Prüfung")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.c, "start")                 # … wartet mit Grund, die nächste darf
        with self.assertRaises(kern.AmwFehler) as e:                                    # Pos 1 starten: abgewiesen, nichts still zurückgestellt
            kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "start")
        self.assertIn(f"A{self.c} läuft noch – eins nach dem anderen", str(e.exception))
        self.assertIn("entscheidet das der Mensch", str(e.exception))
        st = {r["id"]: r["status"] for r in self.con.execute("SELECT id, status FROM aufgabe")}
        self.assertEqual((st[self.a], st[self.c]), ("wartet", "laeuft"))
        wartegrund.von_hand(self.con, self.pid, "TL", self.b, "Monitor:Prüfung")        # der Grund von Pos 2 ist erledigt
        with db.schreiben(self.con):
            wartegrund._melden(self.con, self.pid, self.con.execute("SELECT * FROM aufgabe WHERE id = ?", (self.b,)).fetchone(), "Prüfung grün")
        post = [r["kurz"] for r in kern.offene(self.con, self.pid, "CC1")]
        self.assertTrue(any(f"als Nächstes dran, sobald A{self.c} fertig ist" in x for x in post), post)
        kern.aufgabe_status(self.con, self.pid, "CC1", self.c, "fertig", beleg="abc")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "start")                 # jetzt geht es
        self.assertEqual(self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (self.a,)).fetchone()[0], "laeuft")

    def test_laufendes_stueck_bleibt_vorn(self):
        kern.aufgabe_status(self.con, self.pid, "CC1", self.b, "start")                 # Pos 2 läuft
        self.al.ordnen(self.con, self.pid, "TL", "CC1", [self.c, self.a])               # ordnen: das laufende Stück bleibt vorn
        self.assertEqual(self.ids(), [self.b, self.c, self.a])
        self.al.schieben(self.con, self.pid, "TL", self.a, oben=True)                    # ganz nach oben = direkt dahinter
        self.assertEqual(self.ids(), [self.b, self.a, self.c])
        neu = kern.aufgabe_neu(self.con, self.pid, "TL", "Eilig", agent="CC1", rang=1)   # neue Aufgabe mit kleinem Rang: dahinter
        self.assertEqual(self.ids()[:2], [self.b, neu])
        e1 = kern.aufgabe_neu(self.con, self.pid, "TL", "Mensch 1", agent="Entwickler")
        e2 = kern.aufgabe_neu(self.con, self.pid, "TL", "Mensch 2", agent="Entwickler")
        kern.aufgabe_status(self.con, self.pid, "Entwickler", e1, "start")
        kern.aufgabe_status(self.con, self.pid, "Entwickler", e2, "start")             # Aufgaben des Menschen bleiben frei

    def test_fertig_ohne_wartende_weckt_mit_der_naechsten_der_liste(self):
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "start")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "fertig", beleg="abc")
        post = [r["kurz"] for r in kern.offene(self.con, self.pid, "CC1")]
        self.assertTrue(any(f"weiter in deiner Liste: A{self.b} (Pos 1/2)" in x for x in post), post)

    def test_liste_des_entwicklers(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", entwickler_name="Chris")
        e1 = kern.aufgabe_neu(self.con, self.pid, "TL", "Variante wählen", agent="Entwickler")
        e2 = kern.aufgabe_neu(self.con, self.pid, "TL", "Level 1 testen", agent="Chris")             # sein Name geht auch
        self.assertEqual(self.ids(kern.ENTWICKLER), [e1, e2])
        self.al.ordnen(self.con, self.pid, "TL", "Entwickler", [e2])
        self.assertEqual(self.ids(kern.ENTWICKLER), [e2, e1])
        from amw import workbench
        d = workbench.daten_listen(self.con, self.pid)
        self.assertEqual((d["agenten"][0]["kennung"], d["agenten"][0]["name"]), (kern.ENTWICKLER, "Chris"))

    def test_neues_kommt_in_den_eingang_solange_ein_stueck_laeuft(self):
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "start")
        rc, aus = self.cli("--von", "TL", "aufgabe", "neu", "--titel", "Neuer Wunsch", "--agent", "CC1")
        self.assertEqual(rc, 0, aus)
        neu = int(aus.split()[0][1:])
        self.assertIn(f"steht im Eingang, weil CC1 gerade an A{self.a} arbeitet", aus)
        self.assertNotIn(neu, self.ids())                                                # nicht in seiner Liste …
        self.assertIn(neu, [x["id"] for x in self.al.pool(self.con, self.pid)])        # … sondern im Eingang
        from amw import workbench
        self.assertEqual(workbench.daten_start(self.con, self.pid)["eingang"], 1)
        self.al.ordnen(self.con, self.pid, "TL", "CC1", [neu])                           # einplanen: hinter das laufende Stück
        self.assertEqual(self.ids()[:2], [self.a, neu])
        rc, aus = self.cli("--von", "TL", "aufgabe", "neu", "--titel", "Gleich danach", "--agent", "CC1", "--sofort")
        self.assertIn(int(aus.split()[0][1:]), self.ids())                               # --sofort: gleich in die Liste
        rc, aus = self.cli("--von", "CC1", "aufgabe", "neu", "--titel", "Eigene Notiz", "--agent", "CC1")
        self.assertIn(int(aus.split()[0][1:]), self.ids())                               # eigene Aufgabe: kein Eingang
        frei = kern.aufgabe_neu(self.con, self.pid, "TL", "Ohne laufendes Stück", agent="CC2", sofort=False)
        self.assertEqual(self.con.execute("SELECT einstufung FROM aufgabe WHERE id = ?", (frei,)).fetchone()[0], "aktiv")

    def test_dazwischenschieben_nur_der_mensch_und_das_laufende_kommt_danach_wieder(self):
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "start")                 # Pos 1 läuft
        with self.assertRaises(kern.AmwFehler) as e:                                    # ein Agent darf das nicht
            self.al.dazwischen(self.con, self.pid, "CC1", self.c, "eilig")
        self.assertIn("entscheidet der Mensch", str(e.exception))
        with self.assertRaises(kern.AmwFehler):                                         # ohne Grund nicht
            self.al.dazwischen(self.con, self.pid, kern.ENTWICKLER, self.c, " ")
        art, nr = self.al.dazwischen(self.con, self.pid, kern.ENTWICKLER, self.c, "Kunde wartet")
        self.assertEqual((art, nr), ("ausgefuehrt", self.a))
        st = {r["id"]: r["status"] for r in self.con.execute("SELECT id, status FROM aufgabe")}
        self.assertEqual(st[self.a], "wartet")
        self.assertEqual([g["bezug"] for g in wartegrund.offene(self.con, self.a)], [f"A{self.c}"])
        self.assertEqual(self.ids()[:2], [self.c, self.a])                               # eingeschoben vorn, unterbrochenes dahinter
        post = kern.offene(self.con, self.pid, "CC1")
        self.assertTrue(any(f"Dazwischen: A{self.c} vor A{self.a} – Kunde wartet" == r["kurz"] for r in post), [r["kurz"] for r in post])
        self.assertTrue(any("hat A" in r["kurz"] and "dazwischengeschoben" in r["kurz"] for r in kern.offene(self.con, self.pid, "TL")))
        ev = self.con.execute("SELECT art, aufgabe_id, text FROM plan_ereignis WHERE art = 'unterbrochen'").fetchone()
        self.assertEqual(tuple(ev), ("unterbrochen", self.a, f"für A{self.c}: Kunde wartet"))
        kern.aufgabe_status(self.con, self.pid, "CC1", self.c, "start")                 # jetzt läuft die eingeschobene
        kern.aufgabe_status(self.con, self.pid, "CC1", self.c, "fertig", beleg="abc")
        post = [r["kurz"] for r in kern.offene(self.con, self.pid, "CC1")]
        self.assertTrue(any(f"A{self.a}" in x and "weiter: amw aufgabe start" in x for x in post), post)   # das unterbrochene meldet sich
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "start")

    def test_lead_schlaegt_vor_und_ja_fuehrt_aus(self):
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "start")
        rc, aus = self.cli("--von", "TL", "aufgabe", "dazwischen", str(self.c), "--grund", "Sicherheitslücke")
        self.assertEqual(rc, 0, aus)
        self.assertIn("an den Menschen gestellt", aus)
        f = self.con.execute("SELECT id, kurz, empfehlung FROM frage ORDER BY id DESC").fetchone()
        self.assertIn(f"A{self.c} dazwischenschieben? – CC1 arbeitet gerade an A{self.a}", f["kurz"])
        self.assertEqual(self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (self.a,)).fetchone()[0], "laeuft")   # noch nichts geändert
        kern.frage_antworten(self.con, self.pid, f["id"], "option", "A", "workbench")
        self.assertEqual(self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (self.a,)).fetchone()[0], "wartet")
        self.assertEqual(self.ids()[0], self.c)
        kern.aufgabe_status(self.con, self.pid, "CC1", self.c, "start")
        rc, aus = self.cli("--von", "TL", "aufgabe", "dazwischen", str(self.b), "--grund", "auch eilig")
        f2 = self.con.execute("SELECT id FROM frage ORDER BY id DESC").fetchone()[0]
        kern.frage_antworten(self.con, self.pid, f2, "option", "B", "workbench")          # „Nein“: nichts passiert
        self.assertEqual(self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (self.c,)).fetchone()[0], "laeuft")

    def test_untere_starten_waehrend_obere_laeuft_wird_abgewiesen(self):
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "start")
        with self.assertRaises(kern.AmwFehler) as e:
            kern.aufgabe_status(self.con, self.pid, "CC1", self.b, "start")
        self.assertIn(f"A{self.a} läuft noch", str(e.exception))
        self.assertEqual(self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (self.b,)).fetchone()[0], "wartet")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "start")                 # dieselbe noch einmal starten: kein Fehler
        self.assertIn("Deine Liste (3", kern.kontext(self.con, self.pid, "CC1"))


class Termine(Grund):
    """Terminplaner (B2429): Testtermine, Frist „Testbuild fertig“, Ampel, Meldung „bereit“ mit Kurzliste."""

    def setUp(self):
        super().setUp()
        from amw import termine
        self.tm = termine
        from datetime import datetime, timedelta
        self.morgen = (datetime.now() + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)

    def am(self, d):
        return d.strftime("%Y-%m-%d %H:%M")

    def test_woechentlich_frist_und_absagen(self):
        from datetime import timedelta
        with self.assertRaises(kern.AmwFehler):
            self.tm.neu(self.con, self.pid, "CC1", "Test", "test", self.am(self.morgen))           # nur Lead/Entwickler
        rc, aus = self.cli("--von", "TL", "termin", "neu", "--titel", "Entwickler testet", "--art", "test", "--am",
                           self.am(self.morgen), "--woechentlich")
        self.assertEqual(rc, 0, aus)
        v = self.tm.vorkommen(self.con, self.pid, tage=21)
        self.assertEqual(len(v), 3)                                                      # 3 Wochen
        self.assertEqual(self.tm._dt(v[1]["am_utc"]).astimezone().strftime("%H:%M"), "18:00")
        self.assertEqual(self.tm._dt(v[0]["frist_utc"]).astimezone().strftime("%H:%M"), "14:00")   # 4 h Vorlauf
        self.tm.absagen(self.con, self.pid, "TL", 1, am=self.am(self.morgen + timedelta(weeks=1)))
        self.assertEqual(len(self.tm.vorkommen(self.con, self.pid, tage=21)), 2)
        self.assertIn("Nächster Testtermin T1", kern.kontext(self.con, self.pid, "CC1"))
        self.tm.absagen(self.con, self.pid, "TL", 1)
        self.assertEqual(self.tm.vorkommen(self.con, self.pid, tage=21), [])

    def test_bereit_mit_kurzliste_an_den_entwickler(self):
        tid = self.tm.neu(self.con, self.pid, "TL", "Entwickler testet", "test", self.am(self.morgen))
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "start")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "fertig", beleg="abc")
        rc, aus = self.cli("--von", "CC3", "termin", "bereit", f"T{tid}", "--text", "Onboarding neu, bitte Opa-Auftrag testen")
        self.assertEqual(rc, 0, aus)
        m = kern.offene(self.con, self.pid, kern.ENTWICKLER)
        self.assertTrue(any("Testbuild bereit" in r["kurz"] for r in m))
        text = self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE 'Testbuild bereit%'").fetchone()[0]
        self.assertIn(f"A{self.a} (CC1) Onboarding prüfen", text)
        self.assertIn("Opa-Auftrag", text)
        rc, aus = self.cli("--von", "CC3", "termin", "bereit", f"T{tid}", "--text", "nochmal")
        self.assertEqual(rc, 1)                                                          # nur einmal je Vorkommen

    def test_frist_ohne_meldung_weckt_den_lead_einmal(self):
        from datetime import datetime, timedelta, timezone
        tid = self.tm.neu(self.con, self.pid, "TL", "Entwickler testet", "test", self.am(self.morgen))
        frist = self.tm._dt(self.tm.vorkommen(self.con, self.pid)[0]["frist_utc"])
        self.assertEqual(self.tm.runde(self.con, self.pid, jetzt=frist - timedelta(minutes=5)), [])
        self.assertEqual(len(self.tm.runde(self.con, self.pid, jetzt=frist + timedelta(minutes=5))), 1)
        self.assertEqual(self.tm.runde(self.con, self.pid, jetzt=frist + timedelta(minutes=10)), [])
        self.assertTrue(any(f"Frist T{tid}" in r["kurz"] for r in kern.offene(self.con, self.pid, "TL")))

    def test_zeit_lesen(self):
        self.assertTrue(self.tm.zeit_lesen("06.11. 18:00").endswith("Z"))
        with self.assertRaises(kern.AmwFehler):
            self.tm.zeit_lesen("morgen")


class Themen(Grund):
    """Design-Dokument je Thema (B2429): Seite aus geltenden Beschlüssen, Zusammenfassung mit Pfleger, veraltet/bestätigt."""

    def setUp(self):
        super().setUp()
        from amw import themen, wissen
        self.th, self.wi = themen, wissen

    def test_ohne_themen_frei_dann_pflicht_und_aufraeumen(self):
        b1 = self.wi.beschluss_neu(self.con, self.pid, "TL", "Maßstab alt", "1 m = 64 px", "Entwickler")    # noch keine Themen
        tid = self.th.neu(self.con, self.pid, "TL", "3.5 Karte, Maßstab", pfleger="CC1")
        with self.assertRaises(kern.AmwFehler):
            self.wi.beschluss_neu(self.con, self.pid, "TL", "x", "y", "z")                                  # jetzt Pflicht
        with self.assertRaises(kern.AmwFehler):
            self.wi.beschluss_neu(self.con, self.pid, "TL", "x", "y", "z", thema="Gibtsnicht")
        self.wi.beschluss_thema(self.con, self.pid, "TL", b1, "3.5")                                         # Anfang reicht
        h = []
        b2 = self.wi.beschluss_neu(self.con, self.pid, "TL", "Maßstab M80", "1 m = 80 px", "Entwickler", thema=f"TH{tid}",
                                   hinweise=h)
        self.assertTrue(any(f"B{b1}" in x and "ueberholt" in x for x in h))
        rc, aus = self.cli("--von", "TL", "beschluss", "ueberholt", f"B{b1}", "--durch", f"B{b2}")
        self.assertEqual(rc, 0, aus)
        s = self.th.seite(self.con, self.pid, tid)
        self.assertEqual(([b["id"] for b in s["gilt"]], [b["id"] for b in s["ueberholt"]]), ([b2], [b1]))
        b3 = self.wi.beschluss_neu(self.con, self.pid, "TL", "Neu", "n", "q", thema="Lessons", neues_thema=True)
        self.assertEqual(self.con.execute("SELECT thema FROM beschluss WHERE id = ?", (b3,)).fetchone()[0], "Lessons")

    def test_zusammenfassung_veraltet_weckt_pfleger_und_bestaetigen(self):
        tid = self.th.neu(self.con, self.pid, "TL", "Stil, Grafik", pfleger="CC1", stil=True)
        with self.assertRaises(kern.AmwFehler):
            self.th.pflegen(self.con, self.pid, "CC2", tid, "x")                                           # nur Pfleger/Lead
        rc, aus = self.cli("--von", "CC1", "thema", "pflegen", f"TH{tid}", "--text", "Flach, 2D, rechte Winkel.")
        self.assertEqual(rc, 0, aus)
        self.assertEqual(self.th.stand(self.con, self.th.finden(self.con, self.pid, tid))[0], "aktuell")
        time.sleep(1.1)
        b = self.wi.beschluss_neu(self.con, self.pid, "TL", "Wände dunkler", "Wände #333", "Entwickler", thema="Stil")
        self.assertEqual(self.th.stand(self.con, self.th.finden(self.con, self.pid, tid)), ("veraltet", b))
        self.assertTrue(any("Zusammenfassung prüfen" in r["kurz"] for r in kern.offene(self.con, self.pid, "CC1")))
        k = kern.kontext(self.con, self.pid, "CC1")
        self.assertIn("Projekt-Stil: amw thema zeige", k)
        self.assertIn("Du pflegst, veraltet", k)
        self.th.bestaetigen(self.con, self.pid, "CC1", tid)
        self.assertEqual(self.th.stand(self.con, self.th.finden(self.con, self.pid, tid))[0], "aktuell")
        from amw import abgleich, workbench
        self.assertTrue(workbench.daten_thema(self.con, self.pid, tid)["stil"])           # Workbench und online
        self.assertIn(f"/api/thema?id={tid}", abgleich.ansichten(self.con, self.pid))
        rc, aus = self.cli("--von", "CC2", "thema", "zeige", "Stil")
        self.assertIn("GILT JETZT (Fassung 1", aus)
        self.assertIn(f"B{b} ", aus)


class AufgabeAnsicht(Grund):
    """Klick auf eine Aufgabe: ganze Aufgabe (Fragen mit Stand, Dokumente, Verlauf); erledigt/später/Antwort (1.14.1)."""

    def setUp(self):
        super().setUp()
        from amw import aktionen, workbench
        self.akt, self.wb = aktionen, workbench
        self.f1 = kern.frage_neu(self.con, self.pid, "TL", "entwickler", "Reiter?", [("A", "ja")], "A", "weil", geprueft="keine")
        self.f2 = kern.frage_neu(self.con, self.pid, "TL", "entwickler", "Maßstab?", [("A", "ja")], "A", "weil", geprueft="keine")
        self.m = kern.aufgabe_neu(self.con, self.pid, "TL", f"FÜR DICH: Fragen beantworten – F{self.f1}, F{self.f2}",
                                  agent=kern.ENTWICKLER, auftrag="Bitte in der Workbench antworten.")

    def tun(self, was, **d):
        return self.akt.ausfuehren(self.con, self.pid, "/api/aufgabe/" + was, {"id": self.m, **d}, kanal="netz")

    def test_verweise_auch_bereiche(self):
        v = self.wb.verweise("Stile (D94–D97) und F5165, B12-14", "F5165 nochmal")
        self.assertEqual(v, {"F": [5165], "D": [94, 95, 96, 97], "B": [12, 13, 14]})

    def test_ansicht_mit_fragenstand_und_startkarte(self):
        a = self.wb.daten_aufgabe(self.con, self.pid, self.m)
        self.assertTrue(a["fuer_dich"])
        self.assertEqual([f["status"] for f in a["fragen"]], ["offen", "offen"])
        kern.frage_antworten(self.con, self.pid, self.f1, "option", "A", "seite")
        kern.frage_antworten(self.con, self.pid, self.f2, "text", "M80", "seite")
        a = self.wb.daten_aufgabe(self.con, self.pid, self.m)
        self.assertEqual([f["antwort"] for f in a["fragen"]], ["A", "M80"])
        karte = next(x for x in self.wb.daten_start(self.con, self.pid)["planung_wartet"]["eigene"] if x["id"] == self.m)
        self.assertEqual((karte["fragen_n"], karte["fragen_offen"]), (2, 0))      # „alle 2 Fragen beantwortet“
        from amw import abgleich
        self.assertIn(f"/api/aufgabe?id={self.m}", abgleich.ansichten(self.con, self.pid))   # auch online

    def test_erledigt_nur_mit_notiz_und_tl_erfaehrt_es(self):
        from amw.aktionen import Ungueltig
        with self.assertRaises(Ungueltig):
            self.tun("erledigt", text="")
        r = self.tun("erledigt", text="alle drei beantwortet")
        self.assertEqual(r["an"], "TL")
        a = self.con.execute("SELECT status, beleg FROM aufgabe WHERE id = ?", (self.m,)).fetchone()
        self.assertEqual(a["status"], "fertig")
        self.assertIn("alle drei beantwortet", a["beleg"])
        n = self.con.execute("SELECT n.kurz, e.agent FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE n.id = ?",
                             (r["nachricht"],)).fetchone()
        self.assertEqual((n["agent"], n["kurz"]), ("TL", f"A{self.m} erledigt: alle drei beantwortet"))
        r = self.tun("antwort", text="Nachtrag dazu")                     # auch zur abgeschlossenen
        self.assertEqual(r["an"], "TL")

    def test_spaeter_und_fremde_aufgabe(self):
        zweite = kern.aufgabe_neu(self.con, self.pid, "TL", "FÜR DICH: noch was", agent=kern.ENTWICKLER)
        from amw import arbeitsliste
        self.assertEqual(arbeitsliste.liste(self.con, self.pid, kern.ENTWICKLER)[0]["id"], self.m)
        self.tun("spaeter")
        self.assertEqual([x["id"] for x in arbeitsliste.liste(self.con, self.pid, kern.ENTWICKLER)], [zweite, self.m])
        from amw.aktionen import Ungueltig
        with self.assertRaises(Ungueltig):                                    # CC1s Aufgabe: nur Antwort
            self.akt.ausfuehren(self.con, self.pid, "/api/aufgabe/erledigt", {"id": self.a, "text": "x"}, kanal="netz")
        r = self.akt.ausfuehren(self.con, self.pid, "/api/aufgabe/antwort", {"id": self.a, "text": "geht so"}, kanal="netz")
        self.assertEqual(r["an"], "TL")                                       # angelegt vom TL


class Absender(Grund):
    def test_von_muss_ein_agent_sein(self):
        with self.assertRaisesRegex(kern.AmwFehler, "kein Agent"):
            kern.posten(self.con, self.pid, "CC1,TL", "TL", "info", "x")
        rc, aus = self.cli("--von", "CC2,TL", "posten", "--an", "TL", "--art", "info", "--kurz", "x")
        self.assertNotEqual(rc, 0)
        self.assertIn("--von ist dein eigener Name", aus)
        self.assertEqual(self.con.execute("SELECT count(*) FROM nachricht WHERE kurz = 'x'").fetchone()[0], 0)


class Pfade(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "nur Windows")
    def test_git_bash_pfad(self):
        with tempfile.TemporaryDirectory() as d:
            datei = os.path.join(d, "t.txt")
            open(datei, "w").close()
            git = "/" + datei[0].lower() + datei[2:].replace("\\", "/")
            self.assertTrue(os.path.exists(cli.windows_pfad(git)))
        self.assertEqual(cli.windows_pfad("C:/x"), "C:/x")
        self.assertEqual(cli.windows_pfad("relativ/x"), "relativ/x")


class Wartemeldung(unittest.TestCase):
    def test_meldet_nach_der_frist_was_blockiert(self):
        aus = io.StringIO()
        with mock.patch.object(db, "WARTE_MELDUNG_S", 0.2):
            db.wartemeldung_an(aus, takt=0.05)
            with db._warten("sperre"):
                time.sleep(0.5)
        self.assertIn("auf die Datenbank – ein anderer Prozess schreibt gerade", aus.getvalue())

    def test_belegt_gibt_klare_meldung(self):
        with mock.patch.object(cli, "parser") as p:
            p.return_value.parse_args.return_value = mock.Mock(ohne_db=True, f=mock.Mock(
                side_effect=sqlite3.OperationalError("database is locked")))
            fehler = io.StringIO()
            with redirect_stderr(fehler):
                rc = cli.main([])
        self.assertEqual(rc, 3)
        self.assertIn("Datenbank 30 s lang belegt", fehler.getvalue())


if __name__ == "__main__":
    unittest.main()
