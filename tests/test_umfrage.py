"""Tests für die Wünsche der Agenten aus der Umfrage (AMW 1.10.0): lesen/erledigt, Nummern mit Vorsilbe, abmelden,
„alle“, Einzel-Info weckt, Alter der Tätigkeit, Nachtrag, Hinweise, Startskript, Pfade, Aufruf-Fehler, Wartemeldung."""
import io
import os
import sqlite3
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
        betrieb.lauf_start(self.con, self.pid, "CC1", "Proben opa, labor", aufgabe_id=self.a)
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
        with mock.patch.object(steuerung, "profil", return_value={"ordner": "F:/p"}), \
             mock.patch.object(steuerung, "befehl", return_value="claude"), \
             mock.patch.object(steuerung, "letzte_sitzung", return_value=None):
            nur_an = steuerung.startskript(self.con, self.pid)
            alle = steuerung.startskript(self.con, self.pid, alle=True, abstand_s=15)
        self.assertNotIn("Start-Sleep", nur_an)
        self.assertNotIn("starte CC2", nur_an)
        self.assertIn("starte CC2", alle)
        self.assertEqual(alle.count("Start-Sleep -Seconds 15"), 1)
        self.assertEqual(alle.count("Start-Process wt.exe -ArgumentList '-w amw new-tab --title"), 2)


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
