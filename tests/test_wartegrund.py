"""Tests für Wartegründe und Wecken (B2419 Teil 2, L1–L6) und die Frage-Prüfung gegen die Datenbank (B2422)."""
import io
import os
import tempfile
import time
import unittest
from contextlib import redirect_stdout

from amw import betrieb, cli, db, kern, wartegrund, wissen, workbench


def utc(sek):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(sek))


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
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "start")

    def tearDown(self):
        self.con.close()
        self.ordner.cleanup()

    def frage(self, kurz="Welche Farbe für den Knopf?"):
        return kern.frage_neu(self.con, self.pid, "CC1", "entwickler", kurz, [("A", "rot"), ("B", "blau")], "A", "weil",
                              geprueft="keine Treffer")

    def post(self, agent):
        """Offene Nachrichten (kurz) an einen Agenten."""
        return [r["kurz"] for r in kern.offene(self.con, self.pid, agent)]

    def cli(self, *args):
        os.environ["AMW_DB"] = self.pfad
        aus = io.StringIO()
        try:
            with redirect_stdout(aus):
                rc = cli.main(list(args))
        finally:
            os.environ.pop("AMW_DB", None)
        return rc, aus.getvalue()


class Verweise(Grund):
    """L1: worauf eine Aufgabe wartet, steht als Verweis – ohne wird „wartet“ abgelehnt."""

    def test_wartet_ohne_verweis_abgelehnt(self):
        with self.assertRaises(kern.AmwFehler):
            kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "wartet")
        with self.assertRaises(kern.AmwFehler):                        # Freitext allein reicht nicht (A1238)
            kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "wartet", wartet_auf="Marcels Antwort")
        with self.assertRaises(kern.AmwFehler):
            kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "wartet", auf="Quatsch")
        with self.assertRaises(kern.AmwFehler):
            kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "wartet", auf="F999")
        with self.assertRaises(kern.AmwFehler):
            kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "wartet", auf=f"A{self.a}")

    def test_verweise_lesen(self):
        f = self.frage()
        a2 = kern.aufgabe_neu(self.con, self.pid, "TL", "Vorarbeit", agent="CC2")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "wartet", auf=f"F{f}, a{a2}; CC2,Marcel,Monitor: Fensterlauf")
        self.assertEqual([g["bezug"] for g in wartegrund.offene(self.con, self.a)],
                         [f"F{f}", f"A{a2}", "CC2", "Entwickler", "Monitor: Fensterlauf"])
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "blockiert", auf="CC2")      # doppelt → nicht noch einmal
        self.assertEqual(len(wartegrund.offene(self.con, self.a)), 5)

    def test_neue_aufgabe_braucht_keinen_grund_start_schliesst_gruende(self):
        a2 = kern.aufgabe_neu(self.con, self.pid, "TL", "Neu", agent="CC1")
        self.assertEqual(self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (a2,)).fetchone()[0], "wartet")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "wartet", auf="CC2")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "start")
        self.assertEqual(wartegrund.offene(self.con, self.a), [])
        g = self.con.execute("SELECT erledigt_durch FROM wartegrund WHERE aufgabe_id = ?", (self.a,)).fetchone()
        self.assertEqual(g[0], f"A{self.a} laeuft")


class Wecken(Grund):
    """L2: ein erledigter Grund weckt den Besitzer, Kopie an den Lead."""

    def test_frage_beantwortet_weckt(self):
        f = self.frage()
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "wartet", auf=f"F{f},CC2")
        kern.frage_antworten(self.con, self.pid, f, "option", "B", "seite")
        meldung = [k for k in self.post("CC1") if k.startswith(f"A{self.a}:")]
        self.assertEqual(meldung, [f"A{self.a}: F{f} beantwortet: B) blau – noch offen: CC2"])
        self.assertIn(meldung[0], self.post("TL"))
        art = self.con.execute("SELECT art FROM nachricht WHERE kurz = ?", (meldung[0],)).fetchone()[0]
        self.assertEqual(art, "meldung")                               # weckt

    def test_rueckfrage_erledigt_nichts(self):
        f = self.frage()
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "wartet", auf=f"F{f}")
        kern.frage_antworten(self.con, self.pid, f, "rueckfrage", "Welches Blau?", "seite")
        self.assertEqual(len(wartegrund.offene(self.con, self.a)), 1)

    def test_aufgabe_lauf_agent_marcel(self):
        a2 = kern.aufgabe_neu(self.con, self.pid, "TL", "Vorarbeit", agent="CC2")
        lid = betrieb.lauf_start(self.con, self.pid, "CC3", "Build", speicher_frei=20)
        f = self.frage()
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "wartet", auf=f"A{a2},L{lid},CC3,Marcel")
        kern.aufgabe_status(self.con, self.pid, "CC2", a2, "fertig", beleg="abc123")
        betrieb.lauf_ende(self.con, self.pid, "CC3", lid, 0)
        kern.posten(self.con, self.pid, "CC3", "TL", "info", "fremde Aufgabe")            # ohne --aufgabe: zählt nicht
        self.assertIn("CC3", [g["bezug"] for g in wartegrund.offene(self.con, self.a)])
        kern.posten(self.con, self.pid, "CC3", "CC1", "antwort", "erledigt", aufgabe_id=self.a)
        self.assertEqual([g["bezug"] for g in wartegrund.offene(self.con, self.a)], ["Entwickler"])
        with db.schreiben(self.con):                                    # Marcel beantwortet eine Frage zu dieser Aufgabe
            self.con.execute("UPDATE frage SET aufgabe_id = ? WHERE id = ?", (self.a, f))
        kern.frage_antworten(self.con, self.pid, f, "text", "nimm Blau", "seite")
        self.assertEqual(wartegrund.offene(self.con, self.a), [])
        post = self.post("CC1")
        for teil in (f"A{a2} fertig", f"L{lid} zu Ende (rc 0)", "CC3 hat geschrieben", "Marcel hat"):
            self.assertTrue(any(teil in k for k in post), teil)
        self.assertTrue(any("alle Gründe erledigt – weiter: amw aufgabe start" in k for k in post))

    def test_von_hand_abhaken(self):
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "wartet", auf="Marcel,CC2")
        self.assertEqual(kern.aufgabe_status(self.con, self.pid, "TL", self.a, "wartet", erledigt="Marcel"), "wartet")
        self.assertEqual([g["bezug"] for g in wartegrund.offene(self.con, self.a)], ["CC2"])
        self.assertTrue(any("Entwickler erledigt (TL)" in k for k in self.post("CC1")))
        with self.assertRaises(kern.AmwFehler):
            kern.aufgabe_status(self.con, self.pid, "TL", self.a, "wartet", erledigt="Marcel")
        with self.assertRaises(kern.AmwFehler):                        # nur Besitzer oder Lead
            kern.aufgabe_status(self.con, self.pid, "CC3", self.a, "wartet", erledigt="CC2")

    def test_fertige_aufgabe_weckt_niemanden(self):
        f = self.frage()
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "wartet", auf=f"F{f}")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "verwerfen", beleg="A2 übernimmt")
        kern.frage_antworten(self.con, self.pid, f, "option", "A", "seite")
        self.assertFalse(any(k.startswith(f"A{self.a}:") for k in self.post("CC1")))


class Bezug(Grund):
    """L4 (Bezug prüfen) und L5 (Kopie an den Besitzer)."""

    def test_unbekannt_oder_fertig_abgelehnt_fremd_hinweis(self):
        with self.assertRaises(kern.AmwFehler):
            kern.posten(self.con, self.pid, "CC2", "TL", "info", "x", aufgabe_id=999)
        a2 = kern.aufgabe_neu(self.con, self.pid, "TL", "Alt", agent="CC2")
        kern.aufgabe_status(self.con, self.pid, "CC2", a2, "fertig", beleg="abc")
        with self.assertRaises(kern.AmwFehler):
            kern.posten(self.con, self.pid, "CC2", "TL", "info", "x", aufgabe_id=a2)
        with self.assertRaises(kern.AmwFehler):
            kern.frage_neu(self.con, self.pid, "CC2", "tl", "darf ich?", [], aufgabe_id=a2)
        h = []
        kern.posten(self.con, self.pid, "CC2", "TL", "auftrag", "bitte mergen", aufgabe_id=self.a, hinweise=h)
        self.assertEqual(h, [f"Hinweis: A{self.a} gehört CC1 (Onboarding prüfen) – richtig?"])
        self.assertEqual(self.post("CC1"), [])                           # Merge-Bitte (auftrag): keine Kopie

    def test_kopie_an_besitzer_weckt_nur_wenn_wartet(self):
        rc, aus = self.cli("--von", "CC3", "posten", "--an", "TL", "--art", "info", "--kurz", "gemergt", "--aufgabe", str(self.a))
        self.assertEqual(rc, 0)
        self.assertIn("Kopie an CC1", aus)
        k = self.con.execute("SELECT art, kurz FROM nachricht WHERE von = 'AMW' ORDER BY id DESC").fetchone()
        self.assertEqual((k["art"], k["kurz"]), ("info", f"Kopie zu deiner A{self.a}: CC3 → TL: gemergt"))
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "wartet", auf="CC2")
        kern.posten(self.con, self.pid, "CC3", "TL", "meldung", "Befund dazu", aufgabe_id=self.a)
        k = self.con.execute("SELECT art FROM nachricht WHERE von = 'AMW' ORDER BY id DESC").fetchone()
        self.assertEqual(k["art"], "meldung")
        n = self.con.execute("SELECT count(*) FROM nachricht WHERE von = 'AMW'").fetchone()[0]
        kern.posten(self.con, self.pid, "CC3", "CC1,TL", "info", "an ihn selbst", aufgabe_id=self.a)   # schon Empfänger
        self.assertEqual(self.con.execute("SELECT count(*) FROM nachricht WHERE von = 'AMW'").fetchone()[0], n)


class Leerlauf(Grund):
    """L3: wer frei ist, obwohl Arbeit da ist, wird geweckt; alles wartet auf Marcel → eine Zeile an den Lead."""

    def setUp(self):
        super().setUp()
        self.jetzt = time.time()
        with db.schreiben(self.con):
            for k in ("CC1", "CC2"):
                aid = self.con.execute("SELECT id FROM agent WHERE kennung = ?", (k,)).fetchone()[0]
                db.einfuegen(self.con, "sitzung", agent_id=aid, gestartet_utc=utc(self.jetzt - 7200), schluessel_datei="x.key",
                             ereignis="frei", ereignis_utc=utc(self.jetzt - 40 * 60))

    def test_frei_mit_arbeit_weckt_einmal(self):
        self.assertEqual(wartegrund.leerlauf(self.con, self.jetzt), [f"CC1 geweckt (Leerlauf, A{self.a})"])
        self.assertTrue(self.post("CC1")[0].startswith("Leerlauf: seit 40 min frei, Arbeit liegt vor – A"))
        kern.erledigt(self.con, self.pid, "CC1", [r["id"] for r in kern.offene(self.con, self.pid, "CC1")])
        self.assertEqual(wartegrund.leerlauf(self.con, self.jetzt + 600), [])              # gleiche Ruhephase

    def test_nicht_bei_kurzer_pause_post_oder_wartender_arbeit(self):
        self.assertEqual(wartegrund.leerlauf(self.con, self.jetzt - 15 * 60), [])          # erst 25 min frei
        kern.posten(self.con, self.pid, "TL", "CC1", "info", "lies das")
        self.assertEqual(wartegrund.leerlauf(self.con, self.jetzt), [])                    # ungelesene Post
        kern.erledigt(self.con, self.pid, "CC1", [r["id"] for r in kern.offene(self.con, self.pid, "CC1")])
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "wartet", auf="CC2")
        self.assertEqual(wartegrund.leerlauf(self.con, self.jetzt), [])                    # wartet wirklich
        a2 = kern.aufgabe_neu(self.con, self.pid, "TL", "Danach", agent="CC1")
        with db.schreiben(self.con):
            self.con.execute("INSERT INTO abhaengigkeit (vor, nach, art) VALUES (?, ?, 'FS')", (self.a, a2))
        self.assertEqual(wartegrund.leerlauf(self.con, self.jetzt), [])                    # Vorgänger offen

    def test_alles_wartet_auf_marcel_hoechstens_alle_6h(self):
        f = self.frage()
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "wartet", auf=f"F{f},Marcel")
        self.assertEqual(wartegrund.leerlauf(self.con, self.jetzt), ["Lead: alles wartet auf Marcel"])
        self.assertIn(f"Leerlauf: warten auf Marcel – CC1 (Entwickler, F{f})", [r["kurz"] for r in kern.offene(self.con, self.pid, "TL")])
        self.assertEqual(wartegrund.leerlauf(self.con, self.jetzt + 3600), [])


class Anzeige(Grund):
    """L6 und Ausgaben: Workbench zeigt, was eine Frage aufhält; Kontext und CLI zeigen die Gründe."""

    def test_frage_haelt_aufgabe(self):
        f = self.frage()
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "wartet", auf=f"F{f}")
        d = next(x for x in workbench.daten_fragen(self.con, self.pid) if x["id"] == f)
        self.assertEqual([(x["id"], x["agent"]) for x in d["haelt"]], [(self.a, "CC1")])
        self.assertEqual(d["geprueft"], "keine Treffer")

    def test_kontext_und_cli(self):
        rc, aus = self.cli("--von", "CC1", "aufgabe", "wartet", str(self.a), "--auf", "CC2", "--wartet-auf", "Review")
        self.assertEqual((rc, aus.strip()), (0, f"A{self.a} → wartet · wartet auf CC2"))
        self.assertIn(f"A{self.a} [wartet] Onboarding prüfen (wartet auf CC2; Review)", kern.kontext(self.con, self.pid, "CC1"))
        self.assertIn(f"Wartet auf dich: A{self.a} (CC1)", kern.kontext(self.con, self.pid, "CC2"))
        rc, aus = self.cli("--von", "CC1", "aufgabe", "zeige", str(self.a))
        self.assertIn("wartegrund: CC2", aus)
        rc, aus = self.cli("--von", "CC1", "aufgabe", "start", str(self.a), "--auf", "CC2")
        self.assertEqual(rc, 1)


class Pruefung(Grund):
    """B2422: Fragen an den Entwickler erst nach Prüfung gegen Beschlüsse, Fragen, Regeln."""

    def setUp(self):
        super().setUp()
        self.b = wissen.beschluss_neu(self.con, self.pid, "TL", "Modem heißt DSL-Modem",
                                      "Anker-Geräte tragen die Technik im Namen: Modem → DSL-Modem", "Marcel 04.11. 11:35")

    def test_treffer_gefunden(self):
        t = wissen.treffer(self.con, self.pid, "Wie soll das Modem am Anker heißen?")
        self.assertEqual(t[0]["ref"], f"B{self.b}")
        self.assertEqual(wissen.treffer(self.con, self.pid, "Wie spät ist es?"), [])

    def test_ohne_oder_falsches_geprueft_abgelehnt(self):
        frage = lambda g: kern.frage_neu(self.con, self.pid, "CC1", "entwickler", "Wie soll das Modem am Anker heißen?",
                                         [("A", "Modem"), ("B", "DSL-Modem")], "B", "weil", geprueft=g)
        for g in (None, "", "habe geschaut"):
            with self.assertRaises(kern.AmwFehler) as e:
                frage(g)
            self.assertIn(f"B{self.b}", str(e.exception))
        fid = frage(f"B{self.b} passt nicht, weil es um ISDN geht")
        self.assertEqual(self.con.execute("SELECT geprueft FROM frage WHERE id = ?", (fid,)).fetchone()[0],
                         f"B{self.b} passt nicht, weil es um ISDN geht")
        with self.assertRaises(kern.AmwFehler):                          # ohne Treffer: ein Satz genügt, aber leer nicht
            kern.frage_neu(self.con, self.pid, "CC1", "entwickler", "Wie spät ist es?", [("A", "8")], "A", "g")
        kern.frage_neu(self.con, self.pid, "CC1", "entwickler", "Wie spät ist es?", [("A", "8")], "A", "g", geprueft="keine Treffer")

    def test_an_lead_nur_hinweis(self):
        rc, aus = self.cli("--von", "CC1", "frage", "neu", "--an", "tl", "--kurz", "Wie soll das Modem am Anker heißen?")
        self.assertEqual(rc, 0)
        self.assertIn(f"Vielleicht schon entschieden:\n  B{self.b}", aus)
        rc, aus = self.cli("--von", "CC1", "frage", "neu", "--an", "entwickler", "--kurz", "Wie soll das Modem am Anker heißen?",
                           "--option", "A=Modem", "--empfehlung", "A", "--grund", "g")
        self.assertEqual(rc, 1)


class SucheZeige(Grund):
    """amw suche / amw zeige: nachschlagen statt fragen."""

    def setUp(self):
        super().setUp()
        self.b = wissen.beschluss_neu(self.con, self.pid, "TL", "Modem heißt DSL-Modem",
                                      "Anker-Geräte tragen die Technik im Namen: Modem → DSL-Modem", "Marcel 04.11. 11:35")

    def test_suche_und_zeige(self):
        rc, aus = self.cli("--von", "CC1", "suche", "DSL-Modem")
        self.assertEqual(rc, 0)
        self.assertIn(f"B{self.b}", aus)
        rc, aus = self.cli("--von", "CC1", "zeige", f"B{self.b}", f"A{self.a}")
        self.assertEqual(rc, 0)
        self.assertIn("Quelle: Marcel 04.11. 11:35", aus)
        self.assertIn("titel: Onboarding prüfen", aus)
        rc, aus = self.cli("--von", "CC1", "zeige", "B999")
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
