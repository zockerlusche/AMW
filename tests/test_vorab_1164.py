"""Vorab-Prüfung des Bündels 1.164.0 (CCamwTL #30602): Sitzungssperre für --von Entwickler bei bogen freigeben|zurueck|bericht
und thema vermerk --bestaetigen; Folgenprüfung entscheidet einmal und nur auf den gesehenen Stand, prüft das Zieldatum mit
Baseline gleich; ein abgebrochenes Anlegen eines Planentwurfs legt beim nächsten Ja nichts doppelt an."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
from unittest import mock

from amw import cli, folgen, kern, planer, planung, themen
from tests import test_folgen, test_planansicht, test_planer
from tests.test_planer import ERGEBNIS


class Sitzungssperre(test_planansicht.Grund):
    def befehl(self, *args):
        fehler = io.StringIO()
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(fehler):
            rc = cli.main([*args, "--projekt", "P", "--von", "Entwickler"])
        return rc, fehler.getvalue()

    def test_als_mensch_nicht_aus_einer_sitzung(self):
        for args in (("bogen", "freigeben", str(self.m1), "--art", "grob"), ("bogen", "zurueck", str(self.m1), "--art", "grob", "--notiz", "x"),
                     ("bogen", "bericht", str(self.m1)), ("thema", "vermerk", f"TH{self.th}", "--bestaetigen")):
            rc, fehler = self.befehl(*args)
            self.assertNotEqual(rc, 0, args)
            self.assertIn("nicht aus einer Agenten-Sitzung", fehler, args)
        self.assertFalse(self.m(self.m1)["grob"]["frei"])


class Folgen(test_folgen.Grund):
    def test_veraltet_ueberschreibt_nichts(self):
        r = folgen.vorschlagen(self.con, self.pid, kern.ENTWICKLER, "meilenstein", self.m, titel="Vorschlag")
        folgen.abschliessen(self.con, self.pid, r["aenderung"], test_folgen.KOSTEN)
        planung.bogen_aendern(self.con, self.pid, "TL", self.m, "Inzwischen vom Lead")                 # Zwischenstand
        self.assertEqual(folgen.entscheiden(self.con, self.pid, kern.ENTWICKLER, r["aenderung"], True), "veraltet")
        self.assertEqual(self.titel(), "Inzwischen vom Lead")
        self.assertIn("nicht übernommen", self.post()[-1][1])
        with self.assertRaisesRegex(kern.AmwFehler, "schon entschieden"):
            folgen.entscheiden(self.con, self.pid, kern.ENTWICKLER, r["aenderung"], False)

    def test_einmal_entschieden_auch_beim_automatischen_gelten(self):
        r = folgen.vorschlagen(self.con, self.pid, kern.ENTWICKLER, "meilenstein", self.m, titel="Neu")
        folgen.entscheiden(self.con, self.pid, kern.ENTWICKLER, r["aenderung"], False)             # verworfen …
        self.assertIsNone(folgen.abschliessen(self.con, self.pid, r["aenderung"], json.dumps(test_folgen.NICHTS)))   # … bleibt es
        self.assertEqual(self.titel(), "Anmelden")

    def test_zieldatum_mit_baseline_gleich_geprueft(self):
        planung.bogen_aendern(self.con, self.pid, "TL", self.m, zieldatum="2026-12-01")
        planung.bogen_status(self.con, self.pid, "TL", self.m, "aktiv")                              # Baseline eingefroren
        with self.assertRaisesRegex(kern.AmwFehler, "Baseline"):
            folgen.vorschlagen(self.con, self.pid, kern.ENTWICKLER, "meilenstein", self.m, zieldatum="2026-12-24")
        r = folgen.vorschlagen(self.con, self.pid, kern.ENTWICKLER, "meilenstein", self.m, zieldatum="2026-12-24", grund="Urlaub")
        self.assertEqual(folgen.abschliessen(self.con, self.pid, r["aenderung"], json.dumps(test_folgen.NICHTS)), "gilt")


class Planer(test_planer.Grund):
    def test_abbruch_beim_anlegen_legt_nichts_doppelt_an(self):
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, f"TH{self.tid}")
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, ERGEBNIS)
        echt = planung.schritt_setzen
        aufrufe = []

        def bricht_beim_zweiten(*a, **k):
            aufrufe.append(1)
            if len(aufrufe) == 2:
                raise kern.AmwFehler("Platte voll")
            return echt(*a, **k)
        with mock.patch.object(planung, "schritt_setzen", side_effect=bricht_beim_zweiten):
            with self.assertRaisesRegex(kern.AmwFehler, "Platte voll"):
                planer.uebernehmen(self.con, self.pid, "TL", self.tid)
        vorher = self.con.execute("SELECT count(*) FROM aufgabe").fetchone()[0]
        with self.assertRaisesRegex(kern.AmwFehler, "schon angenommen"):
            planer.uebernehmen(self.con, self.pid, "TL", self.tid)
        self.assertEqual(self.con.execute("SELECT count(*) FROM aufgabe").fetchone()[0], vorher)
        self.assertIn("nur teilweise angelegt", self.post("TL")[-1][1])
