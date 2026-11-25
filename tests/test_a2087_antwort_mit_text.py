"""A2087: eine Option mit Text – der Text ging still verloren (F5393, F5394). Und: kein Befehl lässt einen angegebenen Text oder
eine zweite Angabe von --auf still weg."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import aktionen, cli, db, kern


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db"), "AMW_AGENT": "", "AMW_PROJEKT": "", "CLAUDECODE": "",
                                         "CLAUDE_CODE_MESSAGING_SOCKET": ""})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.fid = self.frage()

    def frage(self, an="tl"):
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "frage", projekt_id=self.pid, zeit_utc=db.jetzt(), von="CC1", an=an, kurz="Wie?", status="offen",
                                optionen='[{"kenn": "A", "text": "Klein"}, {"kenn": "B", "text": "Groß"}]', empfehlung="A", blockiert=0)

    def amw(self, *teile, von="TL"):
        aus, fehler = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(aus), contextlib.redirect_stderr(fehler):
            try:
                rc = cli.main(["--projekt", "P", "--von", von, *teile])
            except SystemExit as x:
                rc = x.code
        return rc, (aus.getvalue() + fehler.getvalue()).strip()

    def datei(self, text):
        pfad = os.path.join(self.ordner.name, "t.txt")
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(text)
        return pfad

    def f(self, fid=None):
        return self.con.execute("SELECT * FROM frage WHERE id = ?", (fid or self.fid,)).fetchone()

    def verlauf(self, fid=None):
        return [r[0] for r in self.con.execute("SELECT text FROM frage_verlauf WHERE frage_id = ? AND art = 'antwort' ORDER BY id", (fid or self.fid,))]

    def nachricht(self):
        return tuple(self.con.execute("SELECT kurz, text FROM nachricht WHERE kurz LIKE 'Antwort zu F%' ORDER BY id DESC LIMIT 1").fetchone())

    def wortlaut(self):
        return [tuple(r) for r in self.con.execute("SELECT text, bemerkung FROM wortlaut ORDER BY id")]


LANG = "Weil die Leiste am Handy sonst umbricht. " * 8


class OptionMitText(Grund):
    def test_beides_kommt_an(self):
        rc, aus = self.amw("frage", "antworten", str(self.fid), "--option", "B", "--text", LANG)
        self.assertEqual((rc, aus), (0, f"F{self.fid} → beantwortet"))
        self.assertEqual((self.f()["antwort_art"], self.f()["antwort"]), ("option", "B"))              # die Option bleibt die Antwort
        self.assertEqual(self.verlauf(), [f"B) Groß – {LANG.strip()}"])
        kurz, text = self.nachricht()
        self.assertTrue(kurz.startswith(f"Antwort zu F{self.fid}: B – Weil die Leiste"))
        self.assertIn(LANG.strip(), text)                                                              # ganz
        self.assertEqual(self.wortlaut(), [])                                                          # der Lead, nicht der Mensch

    def test_kurzer_text_steht_auch_im_text_der_nachricht(self):
        self.amw("frage", "antworten", str(self.fid), "--option", "A", "--text", "kurz")
        self.assertEqual(self.nachricht(), (f"Antwort zu F{self.fid}: A – kurz", "A – kurz"))

    def test_aus_einer_datei(self):
        rc, _ = self.amw("frage", "antworten", str(self.fid), "--option", "A", "--text-datei", self.datei("Zeile 1\nZeile 2"))
        self.assertEqual((rc, self.verlauf()), (0, ["A) Klein – Zeile 1\nZeile 2"]))
        fid = self.frage()
        rc, _ = self.amw("frage", "antworten", str(fid), "--text-datei", self.datei("nur Text"))
        self.assertEqual((rc, self.f(fid)["antwort_art"], self.f(fid)["antwort"]), (0, "text", "nur Text"))

    def test_nur_option_und_nur_text_wie_bisher(self):
        self.amw("frage", "antworten", str(self.fid), "--option", "B")
        self.assertEqual((self.verlauf(), self.nachricht()), (["B) Groß"], (f"Antwort zu F{self.fid}: B", None)))
        fid = self.frage()
        self.amw("frage", "antworten", str(fid), "--text", "Mach C")
        self.assertEqual((self.verlauf(fid), self.nachricht(), self.f(fid)["antwort"]), (["Mach C"], (f"Antwort zu F{fid}: Mach C", None), "Mach C"))

    def test_rueckfrage_steht_allein(self):
        for mehr in (("--text", "x"), ("--option", "A"), ("--text-datei", self.datei("x"))):
            rc, aus = self.amw("frage", "antworten", str(self.fid), "--rueckfrage", "Warum?", *mehr)
            self.assertEqual((rc, self.f()["status"]), (1, "offen"), mehr)
            self.assertIn("--rueckfrage steht allein", aus)
        self.assertEqual(self.amw("frage", "antworten", str(self.fid), "--rueckfrage", "Warum?")[0], 0)

    def test_zwei_optionen_und_gar_nichts(self):
        self.assertIn("eine Option", self.amw("frage", "antworten", str(self.fid), "--option", "A", "--option", "B")[1])
        self.assertIn("--option", self.amw("frage", "antworten", str(self.fid))[1])
        self.assertEqual(self.f()["status"], "offen")

    def test_falsche_option_speichert_nichts(self):
        rc, _ = self.amw("frage", "antworten", str(self.fid), "--option", "Z", "--text", "x")
        self.assertEqual((rc, self.f()["status"], self.verlauf()), (1, "offen", []))

    def test_gebuendelte_fragen_bekommen_die_ganze_antwort(self):
        andere = self.frage()
        with mock.patch.object(kern, "frage_gebuendelt", lambda con, pid, fid: [andere] if fid == self.fid else []):
            self.amw("frage", "antworten", str(self.fid), "--option", "B", "--text", "wegen Handy")
        self.assertEqual(self.f(andere)["antwort"], f"Antwort auf F{self.fid}: B) Groß – wegen Handy")


class Seite(Grund):
    """Seite „Fragen“ und online (derselbe Weg): die Anmerkung neben der Option – Wortlaut des Menschen und in der Nachricht."""

    def test_anmerkung_erreicht_den_fragesteller(self):
        fid = self.frage("entwickler")
        aktionen.ausfuehren(self.con, self.pid, f"/api/frage/{fid}/antwort", {"art": "option", "wert": "A", "anmerkung": "  aber erst morgen "})
        self.assertEqual(self.nachricht(), (f"Antwort zu F{fid}: A – aber erst morgen", "A – aber erst morgen"))     # vorher nur „A“
        self.assertEqual(self.verlauf(fid), ["A) Klein – aber erst morgen"])
        self.assertEqual(self.wortlaut(), [("aber erst morgen", f"Anmerkung zur Antwort auf F{fid} (Option A)")])      # einmal

    def test_ohne_anmerkung_und_text(self):
        fid = self.frage("entwickler")
        aktionen.ausfuehren(self.con, self.pid, f"/api/frage/{fid}/antwort", {"art": "option", "wert": "A", "anmerkung": " "})
        self.assertEqual((self.nachricht(), self.wortlaut()), ((f"Antwort zu F{fid}: A", None), []))
        fid = self.frage("entwickler")
        aktionen.ausfuehren(self.con, self.pid, f"/api/frage/{fid}/antwort", {"art": "text", "wert": "Nein", "anmerkung": "egal"})
        self.assertEqual(self.wortlaut(), [("Nein", f"Antwort auf F{fid}")])


class NichtsStill(Grund):
    def test_text_wo_er_nicht_gilt_ist_ein_fehler_und_es_passiert_nichts(self):
        a = kern.aufgabe_neu(self.con, self.pid, "TL", "Paket", "CC1")
        vor = dict(self.con.execute("SELECT * FROM aufgabe WHERE id = ?", (a,)).fetchone())
        for teile in (("aufgabe", "start", str(a), "--text", "x"), ("aufgabe", "fertig", str(a), "--text", "x", "--beleg", "abc1234"),
                      ("aufgabe", "wartet", str(a), "--auf", "TL", "--text-datei", self.datei("x")), ("frage", "parken", str(self.fid), "--text", "x"),
                      ("notiz", "zeige", "k", "--text", "x"), ("release", "liste", "--text", "x"), ("runde", "lesen", "--text", "x"),
                      ("thema", "liste", "--text", "x"), ("termin", "liste", "--text", "x"), ("dokument", "liste", "--text", "x")):
            rc, aus = self.amw(*teile)
            self.assertEqual(rc, 1, (teile, aus))
            self.assertRegex(aus, r"nimmt kein --text(-datei)? – nichts getan", teile)
        self.assertEqual(dict(self.con.execute("SELECT * FROM aufgabe WHERE id = ?", (a,)).fetchone()), vor)
        self.assertEqual(self.f()["geparkt_utc"], None)

    def test_frage_neu_nennt_die_richtige_option(self):
        self.assertIn("--kurz", self.amw("frage", "neu", "--an", "tl", "--text", "Ziel?")[1])

    def test_text_und_datei_zusammen(self):
        rc, aus = self.amw("posten", "--an", "CC1", "--art", "info", "--kurz", "K", "--text", "a", "--text-datei", self.datei("b"))
        self.assertEqual((rc, self.con.execute("SELECT count(*) FROM nachricht").fetchone()[0]), (1, 0))
        self.assertIn("eins von beiden", aus)

    def test_wo_text_gilt_geht_er_weiter(self):
        a = kern.aufgabe_neu(self.con, self.pid, "TL", "Paket", "CC1")
        for teile in (("posten", "--an", "CC1", "--art", "info", "--kurz", "K", "--text", "a"), ("notiz", "setzen", "k", "--text", "v"),
                      ("aufgabe", "nachtrag", str(a), "--titel", "N", "--auftrag", "erst", "--text", "dann", "--text-datei", self.datei("zuletzt"))):
            rc, aus = self.amw(*teile)
            self.assertEqual(rc, 0, (teile, aus))
        self.assertTrue(self.con.execute("SELECT auftrag FROM aufgabe ORDER BY id DESC LIMIT 1").fetchone()[0].endswith("\nerst\ndann\nzuletzt"))

    def test_auf_mehrfach_wird_gesammelt(self):
        """Lead 25.11.: „--auf A2088 --auf A2077“ übernahm still nur den letzten Wert."""
        a, b, c = (kern.aufgabe_neu(self.con, self.pid, "TL", t, "CC1") for t in ("X", "Y", "Z"))
        rc, aus = self.amw("aufgabe", "wartet", str(a), "--auf", f"A{b}", "--auf", f"A{c}", "--wartet-auf", "beide", von="CC1")
        self.assertEqual(rc, 0, aus)
        self.assertEqual({r[0] for r in self.con.execute("SELECT bezug FROM wartegrund WHERE aufgabe_id = ? AND erledigt_utc IS NULL", (a,))},
                         {f"A{b}", f"A{c}"})


if __name__ == "__main__":
    unittest.main()
