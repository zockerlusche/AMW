"""A1962 (TH167 Fassung 3 Pkt 7, Marcel W2463): Prüfung C Schritt 7 – pyright über das ganze Projekt im Paket-Stand und im
Start-Commit; nur NEUE Fehler (Regel, Datei, Text – ohne Zeile) → C/rot, Ausgabe für den neuen Lauf; Programm fehlt/Zeitlimit →
C/technik; läuft auch bei roter Abnahme; Einstellung sprachpruefung auto (mit pyrightconfig.json) | pyright | aus."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import shutil
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

    def test_programm_fehlt_technik(self):
        b, _ = self.pruefen_mit(kopf=[], technik="pyright fehlt auf diesem PC")
        self.assertEqual((b["code"], b["sprache"]["befund"]), ("C/technik", "C/technik"))

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


@unittest.skipUnless(shutil.which("pyright"), "pyright fehlt auf diesem PC")
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


if __name__ == "__main__":
    unittest.main()
