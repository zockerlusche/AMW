"""A2079: M<nr> ist in Befehlen und Bezügen die Projektnummer (bogen.nr) – nie die interne; nackte Zahl = intern, mit Ausgabe."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import aktionen, cli, db, kern, mcp_server, meilensteine, planung, themen, workbench


class Grund(unittest.TestCase):
    """Wie im Betrieb: interne Nummern laufen über alle Projekte, Projektnummern je Projekt – M2 ist nie die interne 2."""

    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db"), "AMW_AGENT": "", "AMW_PROJEKT": "", "CLAUDECODE": "",
                                         "CLAUDE_CODE_MESSAGING_SOCKET": ""})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        self.pid = {}
        with db.schreiben(self.con):
            for p in ("Alt", "Neu"):
                self.pid[p] = db.einfuegen(self.con, "projekt", name=p, angelegt_utc=db.jetzt())
        for p in self.pid.values():
            kern.agent_neu(self.con, p, "TL", rolle="lead")
            kern.agent_neu(self.con, p, "CC1")
        self.alt = [planung.bogen_neu(self.con, self.pid["Alt"], "TL", f"Alt {i}", ziel="Z", abnahme="V") for i in (1, 2, 3)]
        self.neu = [planung.bogen_neu(self.con, self.pid["Neu"], "TL", f"Neu {i}", ziel="Z", abnahme="V") for i in (1, 2, 3, 4)]
        self.assertEqual((self.alt, self.neu), ([1, 2, 3], [4, 5, 6, 7]))

    def amw(self, *teile, projekt="Neu", von="TL"):
        aus, fehler = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(aus), contextlib.redirect_stderr(fehler):
            try:
                rc = cli.main(["--projekt", projekt, "--von", von, *teile])
            except SystemExit as x:
                rc = x.code
        return rc, (aus.getvalue() + fehler.getvalue()).strip()

    def ok(self, *teile, **k):
        rc, text = self.amw(*teile, **k)
        self.assertEqual(rc, 0, text)
        return text

    def bogen_von(self, aid):
        return self.con.execute("SELECT bogen_id FROM aufgabe WHERE id = ?", (aid,)).fetchone()[0]


class Aufloesen(Grund):
    def test_projektnummer_im_projekt_des_befehls(self):
        self.assertIn("Neu 2", self.ok("bogen", "zeigen", "M2"))
        self.assertIn("Alt 2", self.ok("bogen", "zeigen", "M2", projekt="Alt"))                     # gleiche Nummer, anderes Projekt
        self.assertIn("Neu 2", self.ok("bogen", "zeigen", "m2"))

    def test_nackte_zahl_ist_intern_und_die_ausgabe_nennt_beides(self):
        self.assertIn("M2 (intern 5) [", self.ok("bogen", "zeigen", "5"))
        text = self.ok("bogen", "zeigen", "M2")
        self.assertIn("M2 [", text)
        self.assertNotIn("intern", text.splitlines()[0])

    def test_kollision_wird_nie_umgedeutet(self):
        """M4 gibt es (nr 4 = intern 7) – und die interne 4 gehört M1."""
        self.assertIn("Neu 4", self.ok("bogen", "zeigen", "M4"))
        self.assertIn("Neu 1", self.ok("bogen", "zeigen", "4"))

    def test_interne_nummer_als_m_mit_richtiger_nummer_abgelehnt(self):
        rc, text = self.amw("bogen", "zeigen", "M7")
        self.assertNotEqual(rc, 0)
        self.assertIn("M7 gibt es in diesem Projekt nicht – meinst du M4 „Neu 4“?", text)
        rc, text = self.amw("bogen", "zeigen", "M99")
        self.assertNotEqual(rc, 0)
        self.assertIn("M99 gibt es in diesem Projekt nicht", text)
        self.assertNotIn("meinst du", text)
        self.assertNotIn("Alt", self.amw("bogen", "zeigen", "M3")[1])

    def test_keine_nummer(self):
        rc, text = self.amw("bogen", "zeigen", "Mx")
        self.assertNotEqual(rc, 0)
        self.assertIn("keine Nummer", text)


class Befehle(Grund):
    def test_aufgabe_anlegen_und_umhaengen(self):
        for angabe, bogen in (("M3", 6), ("6", 6)):
            t = self.ok("aufgabe", "neu", "--titel", "T " + angabe, "--auftrag", "x", "--agent", "CC1", "--bogen", angabe, "--ohne-thema-grund", "Test")
            self.assertEqual(self.bogen_von(int(t.split("A", 1)[1].split()[0])), bogen)
        a = planung.schritt_setzen(self.con, self.pid["Neu"], "TL", titel="X", bogen_id=4, agent="CC1")
        self.ok("aufgabe", "aendern", str(a), "--bogen", "M2")
        self.assertEqual(self.bogen_von(a), 5)

    def test_ohne_bogen_nennt_die_projektnummern(self):
        rc, text = self.amw("aufgabe", "neu", "--titel", "T", "--auftrag", "x", "--agent", "CC1")
        self.assertNotEqual(rc, 0)
        self.assertIn("--bogen M1   Neu 1", text)
        self.assertNotIn("--bogen 4", text)

    def test_je_befehl_mit_m_und_mit_zahl(self):
        for angabe, wort in (("M2", "M2"), ("5", "M2 (intern 5)")):
            self.assertTrue(self.ok("bogen", "aendern", angabe, "--ziel", "Z " + angabe).endswith(f"{wort} geändert"), angabe)
            self.assertEqual(self.con.execute("SELECT ziel FROM bogen WHERE id = 5").fetchone()[0], "Z " + angabe)
            self.assertIn("Neu 2", self.ok("bogen", "laufend", angabe, "an" if angabe == "M2" else "aus"))
        self.assertIn("M3 → aktiv", self.ok("bogen", "status", "M3", "aktiv"))
        self.assertEqual(self.con.execute("SELECT status FROM bogen WHERE id = 6").fetchone()[0], "aktiv")
        self.ok("rueckblick", "M2", "--gut", "läuft")
        self.assertEqual(self.con.execute("SELECT bogen_id FROM rueckblick").fetchone()[0], 5)
        self.ok("risiko", "neu", "--titel", "R", "--bogen", "M2")
        self.assertEqual(self.con.execute("SELECT bogen_id FROM risiko").fetchone()[0], 5)
        self.ok("termin", "neu", "--titel", "Frist", "--art", "frist", "--am", "2031-01-01 10:00", "--bogen", "M2")
        self.assertEqual(self.con.execute("SELECT bogen_id FROM termin").fetchone()[0], 5)

    def test_liste_und_neu_nennen_die_projektnummer(self):
        text = self.ok("bogen", "liste")
        self.assertIn("M4 ", text)
        self.assertNotIn("Meilenstein 7", text)
        self.assertIn("M5 angelegt", self.ok("bogen", "neu", "--titel", "Neu 5", "--ziel", "Z", "--abnahme", "V"))

    def test_dokument(self):
        pfad = os.path.join(self.ordner.name, "n.md")
        with open(pfad, "w", encoding="utf-8") as f:
            f.write("# x")
        self.ok("dokument", "ablegen", pfad, "--titel", "N", "--art", "bericht", "--bogen", "M2")
        self.assertEqual(tuple(self.con.execute("SELECT bezug_art, bezug_id FROM dokument").fetchone()), ("bogen", 5))
        text = self.ok("dokument", "liste", "--bogen", "M2")
        self.assertIn("M2", text)
        self.assertNotIn("bogen 5", text)

    def test_thema_anhalten_projektnummer_wie_bisher(self):
        t = themen.neu(self.con, self.pid["Neu"], "TL", "Anmeldung", pfleger="CC1")
        for angabe in ("M2", "2"):
            with mock.patch("amw.planansicht.anhalten", return_value=[]) as halt:
                self.ok("thema", "anhalten", f"TH{t}", "--meilenstein", angabe)
            self.assertEqual(halt.call_args.args[-1], 5, angabe)


class Bezuege(Grund):
    def bezug(self):
        return self.con.execute("SELECT bezug FROM nachricht ORDER BY id DESC LIMIT 1").fetchone()[0]

    def test_posten_projektnummer_gespeichert_wird_die_interne(self):
        self.ok("posten", "--an", "CC1", "--art", "info", "--kurz", "K", "--bezug", "M2")
        self.assertEqual(self.bezug(), "M5")
        self.assertIn("Bezug M2 Neu 2", self.ok("lesen", "1", von="CC1"))

    def test_abgelehnt_mit_hinweis(self):
        rc, text = self.amw("posten", "--an", "CC1", "--art", "info", "--kurz", "K", "--bezug", "M7")
        self.assertNotEqual(rc, 0)
        self.assertIn("meinst du M4", text)

    def test_alter_gespeicherter_bezug_zeigt_die_projektnummer(self):
        kern.posten(self.con, self.pid["Neu"], "TL", "CC1", "info", "alt", bezug="M5")             # so gespeichert wie vor A2079
        self.assertEqual(kern.bezug_text(self.con, "M5"), "M2 Neu 2")
        self.assertEqual(kern.bezug_text(self.con, "M999"), "M999")

    def test_antwort_von_der_seite_deutet_nicht_um(self):
        """Die Seite schickt das gespeicherte Kürzel zurück: M5 bleibt die interne 5 (M2), wird nicht zur Projektnummer 5."""
        nid, _ = kern.posten(self.con, self.pid["Neu"], "CC1", kern.ENTWICKLER, "info", "Frage zum Meilenstein", bezug="M5")
        gezeigt = next(n for n in workbench.daten_nachrichten(self.con, self.pid["Neu"])["eingang"] if n["id"] == nid)["bezug"]
        self.assertEqual((gezeigt["kuerzel"], gezeigt["text"]), ("M5", "M2 Neu 2"))
        aktionen.ausfuehren(self.con, self.pid["Neu"], "/api/nachricht", {"an": "CC1", "art": "info", "kurz": "Antwort", "text": "", "bezug": gezeigt["kuerzel"]})
        self.assertEqual(self.bezug(), "M5")

    def test_andere_kuerzel_unveraendert(self):
        for b in ("A1", "@CC1", "TH2", "P3", None, ""):
            self.assertEqual(meilensteine.bezug(self.con, self.pid["Neu"], b), b)

    def test_innere_aufrufer_bleiben_intern(self):
        """planung.bogen_vorziehen gibt M<intern> als Bezug mit – er muss den richtigen Meilenstein treffen."""
        planung.bogen_status(self.con, self.pid["Neu"], "TL", 4, "aktiv")
        planung.bogen_vorziehen(self.con, self.pid["Neu"], kern.ENTWICKLER, 6)
        self.assertEqual(self.con.execute("SELECT bezug FROM nachricht WHERE bezug LIKE 'M%' ORDER BY id DESC LIMIT 1").fetchone()[0], "M6")


class Mcp(Grund):
    def test_schema_und_befehlszeile(self):
        for name, feld in (("bogen_zeigen", "id"), ("aufgabe_liste", "bogen"), ("aufgabe_neu", "bogen"), ("aufgabe_aendern", "bogen")):
            w = next(x for x in mcp_server.werkzeug_liste() if x["name"] == name)["inputSchema"]["properties"][feld]
            self.assertEqual(w["type"], ["string", "integer"], name)
            self.assertIn("Projektnummer", w["description"])
        for wert in ("M2", 5):
            self.assertIsNone(mcp_server._pruefen("bogen_zeigen", {"id": wert}))
            self.assertEqual(mcp_server.befehlszeile("bogen_zeigen", {"id": wert}), ["bogen", "zeigen", str(wert)])
        self.assertIn("M<nr>", str(mcp_server._pruefen("bogen_zeigen", {"id": [1]})))
        self.assertIn("nicht mit -", str(mcp_server._pruefen("bogen_zeigen", {"id": "--von"})))         # keine Optionen durch die Hintertür
        self.assertIn("muss", str(mcp_server._pruefen("bogen_zeigen", {"id": True})))


if __name__ == "__main__":
    unittest.main()
