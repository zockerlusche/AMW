"""A1962 (TH167 Fassung 3 Pkt 7, Marcel W2463): Prüfung C Schritt 7 – pyright über das ganze Projekt im Paket-Stand und im
Start-Commit; nur NEUE Fehler (Regel, Datei, Text – ohne Zeile) → C/rot, Ausgabe für den neuen Lauf; Programm fehlt/Zeitlimit →
C/technik; läuft auch bei roter Abnahme; Einstellung sprachpruefung auto (mit pyrightconfig.json) | pyright | aus."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import unittest
from unittest import mock

from amw import pruefung_c as c
from tests.test_pruefung_c import Grund, g

FEHLER = ("reportAttributeAccessIssue", "lib/a.py", 'Cannot access attribute "x"')


class Vergleich(unittest.TestCase):
    def test_nur_neue_ohne_zeilennummer(self):
        basis = [(*FEHLER, 3), ("reportCallIssue", "lib/b.py", "Expected 1 argument", 9)]
        kopf = [(*FEHLER, 12), ("reportCallIssue", "lib/b.py", "Expected 1 argument", 20),        # nur verschoben – nicht neu
                (*FEHLER, 30),                                                                       # gleicher Fehler ein zweites Mal
                ("reportAssignmentType", "lib/c.py", 'Type "str" is not assignable', 2)]
        self.assertEqual(c.sprach_vergleich(kopf, basis), [(*FEHLER, 30), ("reportAssignmentType", "lib/c.py", 'Type "str" is not assignable', 2)])
        self.assertEqual(c.sprach_vergleich(basis, kopf), [])                                        # weniger Fehler: nichts Neues

    def test_auto_nur_mit_konfiguration(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(c.sprache_an("auto", d))
            self.assertTrue(c.sprache_an("pyright", d))
            open(os.path.join(d, "pyrightconfig.json"), "w").write("{}")
            self.assertTrue(c.sprache_an("auto", d))
            self.assertFalse(c.sprache_an("aus", d))


class PfadSuche(unittest.TestCase):
    """A1967: pyright und node nur über absolute PATH-Einträge – nicht aus dem aktuellen Ordner, nicht über leere/relative."""
    def setUp(self):
        import tempfile
        self._d = tempfile.TemporaryDirectory()
        self.addCleanup(self._d.cleanup)
        self.d = self._d.name
        self.echt, self.paket = os.path.join(self.d, "echt"), os.path.join(self.d, "paket")
        for o in (self.echt, self.paket, os.path.join(self.paket, "lib")):
            os.makedirs(o)
        ext = ".cmd" if os.name == "nt" else ""
        for o in (self.echt, self.paket, os.path.join(self.paket, "lib")):
            for n in ("node" + (".exe" if os.name == "nt" else ""), "pyright" + ext):
                p = os.path.join(o, n)
                open(p, "w").write("x")
                os.chmod(p, 0o755)
        alt = os.getcwd()
        os.chdir(self.paket)
        self.addCleanup(os.chdir, alt)

    def test_aktueller_ordner_wird_nicht_genommen(self):
        self.assertIsNone(c.programm_im_pfad("node", ""))                              # leerer PATH: nichts, auch nicht cwd
        self.assertIsNone(c.programm_im_pfad("pyright", os.pathsep.join(["", ".", "lib", "  "])))
        pfad = os.pathsep.join(["", ".", "lib", self.echt])
        for n in ("node", "pyright"):
            gefunden = c.programm_im_pfad(n, pfad)
            assert gefunden is not None, n
            self.assertEqual(os.path.dirname(gefunden), self.echt, n)

    def test_pyright_programm_aus_dem_echten_ordner(self):
        js = os.path.join(self.echt, "node_modules", "pyright")
        os.makedirs(js)
        open(os.path.join(js, "index.js"), "w").write("")
        with mock.patch.dict(os.environ, {"PATH": os.pathsep.join([".", self.echt])}):
            prog = c.pyright_programm()
        assert prog is not None
        self.assertEqual([os.path.dirname(prog[0]), prog[1]], [self.echt, os.path.join(js, "index.js")])
        with mock.patch.dict(os.environ, {"PATH": "."}):                               # nur cwd im PATH: fehlt
            self.assertIsNone(c.pyright_programm())


class MitPrüfungC(Grund):
    def setUp(self):
        super().setUp()
        self.reparieren()                                                    # Abnahme grün – geprüft wird hier Schritt 7

    def pruefen_mit(self, kopf, basis=(), technik=None, sprache="pyright"):
        def falsch(q, frist, werkzeuge=None):                                 # 1. Aufruf: Paket-Stand, 2.: Start-Commit
            ist_basis = falsch.n > 0
            falsch.n += 1
            return {"fehler": list(basis if ist_basis else kopf), "version": "1.1.414", "technik": technik, "dauer_s": 1.0, "rc": 1}
        falsch.n = 0
        with mock.patch.object(c, "_pyright", side_effect=falsch) as m:
            b = c.pruefen(self.p, self.projekt, self.basis, 7, self.befehl, ["lib/"], None, 120, regression=None, sprache=sprache)
        return b, m

    def test_neuer_fehler_rot_mit_ausgabe(self):
        b, m = self.pruefen_mit(kopf=[(*FEHLER, 4)])
        self.assertEqual((b["code"], m.call_count), ("C/rot", 2))                                  # Paket-Stand und Start-Commit
        self.assertEqual(b["sprache"]["neu"], [[*FEHLER, 4]])
        self.assertIn("1 neue Fehler gegenüber dem Start-Commit", b["sprache"]["ausgabe"])
        self.assertIn(f"- lib/a.py:4 [reportAttributeAccessIssue] {FEHLER[2]}", b["sprache"]["ausgabe"])
        self.assertEqual(b["grund"], "Sprachprüfung: 1 neue Fehler (pyright)")

    def test_alter_fehler_bleibt_gruen(self):
        b, _ = self.pruefen_mit(kopf=[(*FEHLER, 8)], basis=[(*FEHLER, 2)])
        self.assertIsNone(b["code"], b.get("grund"))
        self.assertEqual(b["sprache"]["neu"], [])

    def test_absturz_technik(self):
        b, _ = self.pruefen_mit(kopf=[], technik="pyright endete mit 2")
        self.assertEqual((b["code"], b["sprache"]["befund"]), ("C/technik", "C/technik"))

    def test_programm_fehlt_nur_hinweis(self):
        """Vorab-Prüfung 1.164.0 (3): fehlt pyright auf dem PC, bleibt grün grün – mit Hinweis im Befund."""
        with mock.patch.object(c, "pyright_programm", return_value=None):
            b = c.pruefen(self.p, self.projekt, self.basis, 7, self.befehl, ["lib/"], None, 120, regression=None, sprache="pyright")
        self.assertIsNone(b["code"], b.get("grund"))
        self.assertIn("pyright fehlt", b["grund"])
        self.assertEqual(b["sprache"]["hinweis"], c.PYRIGHT_FEHLT)

    def test_konfiguration_gesperrt(self):
        from amw import abnahme
        self.assertTrue(abnahme.gesperrt(["pyrightconfig.json"]))
        self.assertTrue(abnahme.gesperrt(["unter/pyrightconfig.json"]))

    def test_aus_und_auto_ohne_konfiguration(self):
        for modus in ("aus", "auto"):
            b, m = self.pruefen_mit(kopf=[(*FEHLER, 4)], sprache=modus)
            self.assertIsNone(b["code"], modus)
            self.assertEqual((m.call_count, b["sprache"]), (0, None))

    def test_laeuft_auch_bei_roter_abnahme(self):
        self.schreiben(self.p["klon"], "lib/rechnen.py", "def plus(a, b):\n    return a * b + 1\n")   # Abnahme rot
        b, m = self.pruefen_mit(kopf=[(*FEHLER, 4)])
        self.assertEqual((b["code"], m.call_count), ("C/rot", 2))
        self.assertEqual(b["abnahme"]["befund"], "C/rot")
        self.assertIn("Sprachprüfung: 1 neue Fehler", b["grund"])
        self.assertIn("lib/a.py:4", b["sprache"]["ausgabe"])


@unittest.skipUnless(c.pyright_programm(), "pyright fehlt auf diesem PC")
class EchtesPyright(Grund):
    def test_neuer_typfehler_echt(self):
        """Ein echter Lauf: der Start-Commit hat einen alten Fehler, das Paket bringt einen neuen – nur der neue zählt."""
        self.schreiben(self.projekt, "pyrightconfig.json", '{"include": ["lib"], "typeCheckingMode": "basic"}\n')
        self.schreiben(self.projekt, "lib/alt.py", "x: int = 'alt'\n")
        g(self.projekt, "add", "-A")
        g(self.projekt, "commit", "-q", "-m", "mit Konfiguration")
        self.basis = g(self.projekt, "rev-parse", "HEAD")
        g(self.p["klon"], "pull", "-q")
        self.reparieren()
        self.schreiben(self.p["klon"], "lib/neu.py", "def f() -> int:\n    return 'neu'\n")
        b = c.pruefen(self.p, self.projekt, self.basis, 7, self.befehl, ["lib/"], None, 300, regression=None, sprache="auto")
        self.assertEqual(b["code"], "C/rot", b.get("grund"))
        self.assertEqual([x[1] for x in b["sprache"]["neu"]], ["lib/neu.py"])
        self.assertEqual((b["sprache"]["fehler_start"], b["sprache"]["fehler_paket"]), (1, 2))
        self.assertTrue(b["sprache"]["version"])

    def test_untergeschobenes_programm_ersetzt_die_pruefung_nicht(self):
        """Vorab-Prüfung 1.164.0 (4): eine pyright.cmd oder node.cmd im Paket, die „alles gut“ meldet, wird nicht ausgeführt."""
        self.schreiben(self.projekt, "pyrightconfig.json", '{"include": ["lib"], "typeCheckingMode": "basic"}\n')
        g(self.projekt, "add", "-A")
        g(self.projekt, "commit", "-q", "-m", "mit Konfiguration")
        self.basis = g(self.projekt, "rev-parse", "HEAD")
        g(self.p["klon"], "pull", "-q")
        self.reparieren()
        self.schreiben(self.p["klon"], "lib/neu.py", "def f() -> int:\n    return 'neu'\n")
        leer = '@echo {"version": "falsch", "generalDiagnostics": [], "summary": {}}\r\n@exit /b 0\r\n'
        for name in ("pyright.cmd", "node.cmd"):
            self.schreiben(self.p["klon"], name, leer)
        b = c.pruefen(self.p, self.projekt, self.basis, 7, self.befehl, ["lib/", "pyright.cmd", "node.cmd"], None, 300, regression=None,
                      sprache="auto")
        self.assertEqual(b["code"], "C/diff")                                  # 1. das Diff-Tor sperrt *.cmd ohnehin
        self.assertIn("gesperrt", b["grund"])
        q = dict(self.p, tmp=os.path.join(self.p["daten"], "tmp-probe"))       # 2. der Starter selbst: im Ordner liegende
        r = c._pyright(q, 300)                                                 #    pyright.cmd/node.cmd werden nicht benutzt
        self.assertIsNone(r["technik"], r)
        self.assertNotEqual(r["version"], "falsch")
        self.assertEqual([x[1] for x in r["fehler"]], ["lib/neu.py"])


if __name__ == "__main__":
    unittest.main()
