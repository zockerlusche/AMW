"""A1914 (D1304 v12 §4/§6b, F5352, W2423): Zuarbeit frischer -p-Agenten je Thema – gebaut ist das Gegenlesen. Neue Fassung
eines Pflegers → EIN Gegenleser (nur Lesen) über die Lauf-Schlange; seine Einwände gehen an den Pfleger; erst danach wartet
das Thema auf den Menschen, solange sieht er „wird gegengelesen · seit …“. Je Runde (seit der letzten Handlung des Menschen)
ein Gegenleser; Kosten je Lauf; abschaltbar je Projekt (Lead oder Mensch); nie in Tests ohne Attrappe."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import shutil
import sys
import unittest
from unittest import mock

from amw import arbeiter, db, gegenlesen, kern, themen
from tests.test_themen_bereich import Grund

ATTRAPPE = [sys.executable, "-X", "utf8", os.path.join(os.path.dirname(os.path.abspath(__file__)), "arbeiter_attrappe.py")]


class Basis(Grund):
    def setUp(self):
        super().setUp()
        u = mock.patch.dict(os.environ)
        u.start()
        self.addCleanup(u.stop)
        os.environ.pop("AMW_GEGENLESEN_AUS", None)                 # hier ausdrücklich an – gestartet wird nur die Attrappe
        self.gestartet = []
        s = mock.patch.object(gegenlesen, "STARTER", side_effect=lambda *a: self.gestartet.append(a) or 4711)
        s.start()
        self.addCleanup(s.stop)

    def post(self, an, art=None):
        return [(r["art"], r["kurz"], r["text"]) for r in self.con.execute(
            "SELECT n.art, n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? AND n.von = 'AMW'"
            + (" AND n.art = ?" if art else "") + " ORDER BY n.id", (an, *([art] if art else [])))]


class Ablauf(Basis):
    def test_fassung_wartet_erst_nach_dem_gegenlesen_auf_dich(self):
        nr = themen.pflegen(self.con, self.pid, "CC1", self.tid, "Anmeldung mit Firmen-Konto.")
        self.assertEqual(self.gestartet, [(self.pid, self.tid, nr)])                          # genau einer, über den Starter
        s = self.st()
        self.assertEqual((s["status"], s["gegenlesen"]["modell"], s["gegenlesen"]["fassung"]), ("arbeit", "opus", nr))   # A1930: Vorgabe opus
        self.assertTrue(s["gegenlesen"]["seit_utc"])                                         # „wird gegengelesen · seit …“
        self.assertEqual(themen.fuer_dich(self.con, self.pid), [])                           # noch nicht beim Menschen
        gegenlesen.abschliessen(self.con, self.pid, self.tid, nr, {"einwaende": "- Abschnitt 2 widerspricht B1.", "usd": 0.0213,
                                                                   "modell": "haiku"}, lauf=77)
        s = self.st()
        self.assertEqual((s["status"], s["gegenlesen"]), ("dich", None))
        art, kurz, text = self.post("CC1", "auftrag")[-1]
        self.assertIn("Gegenleser zu Fassung 1 – Einwände", kurz)
        self.assertIn("- Abschnitt 2 widerspricht B1.", text)
        self.assertIn("haiku, 0.02 $, L77", text)                                             # Kosten je Lauf
        self.assertIn(f"amw thema pflegen TH{self.tid}", text)
        g = themen.seite(self.con, self.pid, self.tid)["gegengelesen"]
        self.assertEqual((g["fassung"], g["einwaende"], g["usd"], g["lauf"]), (1, "- Abschnitt 2 widerspricht B1.", 0.0213, 77))
        themen.pflegen(self.con, self.pid, "CC1", self.tid, "Anmeldung mit Firmen-Konto, Abschnitt 2 passt jetzt zu B1.")   # Antwort
        self.assertEqual(len(self.gestartet), 1)                                              # je Runde ein Gegenleser
        self.assertEqual(self.st()["status"], "dich")
        themen.zurueck(self.con, self.pid, kern.ENTWICKLER, self.tid, "Bitte kürzer.")       # neue Runde (Handlung des Menschen)
        nr3 = themen.pflegen(self.con, self.pid, "CC1", self.tid, "Kurz: Firmen-Konto.")
        self.assertEqual(self.gestartet[-1], (self.pid, self.tid, nr3))
        self.assertEqual(self.st()["status"], "arbeit")

    def test_keine_einwaende_und_fehler_halten_nicht_auf(self):
        nr = themen.pflegen(self.con, self.pid, "CC1", self.tid, "Text.")
        gegenlesen.abschliessen(self.con, self.pid, self.tid, nr, {"einwaende": "Keine Einwände.", "usd": 0.01, "modell": "haiku"})
        self.assertEqual(self.post("CC1")[-1][:2], ("meldung", "Thema „Anmeldung“: Gegenleser zu Fassung 1 – keine Einwände"))
        themen.zurueck(self.con, self.pid, kern.ENTWICKLER, self.tid, "anders")
        nr = themen.pflegen(self.con, self.pid, "CC1", self.tid, "Anders.")
        gegenlesen.abschliessen(self.con, self.pid, self.tid, nr, {"einwaende": None, "usd": None, "modell": "haiku",
                                                                   "fehler": "claude weg"})
        self.assertEqual(self.st()["status"], "dich")                                         # ein Fehler sperrt das Thema nicht
        self.assertIn("Gegenlesen von Fassung 2 ging nicht", self.post("CC1")[-1][1])
        self.assertIn("claude weg", self.post("CC1")[-1][2])

    def test_starter_geht_nicht(self):
        with mock.patch.object(gegenlesen, "STARTER", side_effect=OSError("kein python")):
            themen.pflegen(self.con, self.pid, "CC1", self.tid, "Text.")
        self.assertEqual(self.st()["status"], "dich")
        self.assertIn("kein python", self.post("CC1")[-1][2])

    def test_haengender_gegenleser_sperrt_nicht_ewig(self):
        themen.pflegen(self.con, self.pid, "CC1", self.tid, "Text.")
        self.assertEqual(self.st()["status"], "arbeit")
        with db.schreiben(self.con):
            self.con.execute("UPDATE plan_ereignis SET zeit_utc = '2026-11-01T08:00:00Z' WHERE art = ?", (gegenlesen.ANGESTOSSEN,))
        self.assertEqual(self.st()["status"], "dich")                                         # nach LAEUFT_H zählt er nicht mehr

    def test_abschaltbar_nur_lead_oder_mensch_und_der_mensch_selbst_nie(self):
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "CC1", themen_gegenlesen="aus")
        with self.assertRaisesRegex(kern.AmwFehler, "opus | haiku | sonnet | aus"):                 # A1930: opus wählbar (Vorgabe)
            kern.projekt_einstellen(self.con, self.pid, "TL", themen_gegenlesen="fable")
        kern.projekt_einstellen(self.con, self.pid, "TL", themen_gegenlesen="aus")
        themen.pflegen(self.con, self.pid, "CC1", self.tid, "Text.")
        self.assertEqual((self.gestartet, self.st()["status"]), ([], "dich"))                  # aus: wie bisher
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, themen_gegenlesen="sonnet")
        themen.zurueck(self.con, self.pid, kern.ENTWICKLER, self.tid, "anders")
        themen.pflegen(self.con, self.pid, "CC1", self.tid, "Anders.")
        self.assertEqual(self.st()["gegenlesen"]["modell"], "sonnet")
        themen.bearbeiten(self.con, self.pid, kern.ENTWICKLER, self.tid, "Mein Text.")       # der Mensch selbst: kein Gegenleser
        self.assertEqual(len(self.gestartet), 1)
        self.assertFalse(gegenlesen.ROLLEN["gliederung"]["gebaut"] or gegenlesen.ROLLEN["machbarkeit"]["gebaut"])   # vorbereitet

    def test_in_tests_ohne_attrappe_nie(self):
        os.environ["AMW_GEGENLESEN_AUS"] = "1"
        themen.pflegen(self.con, self.pid, "CC1", self.tid, "Text.")
        self.assertEqual(self.gestartet, [])


class Lauf(Basis):
    def test_als_lauf_der_schlange_mit_kosten(self):
        nr = themen.pflegen(self.con, self.pid, "CC1", self.tid, "Text.")
        with mock.patch.object(gegenlesen, "lesen", return_value={"einwaende": "- fehlt: Abmelden.", "usd": 0.0187, "fehler": None}):
            gegenlesen.ausfuehren(self.con, self.pid, self.tid, nr)
        l = self.con.execute("SELECT id, status, rc, beschreibung, ergebnis FROM lauf ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual((l["status"], l["rc"]), ("fertig", 0))
        self.assertEqual(l["beschreibung"], f"Gegenlesen TH{self.tid} Fassung 1 (opus, A1914, automatisch)")
        self.assertIn("0.02 $", l["ergebnis"])
        self.assertEqual(themen.seite(self.con, self.pid, self.tid)["gegengelesen"]["lauf"], l["id"])
        self.assertEqual(self.st()["status"], "dich")
        with mock.patch.object(gegenlesen, "lesen", side_effect=RuntimeError("weg")):
            gegenlesen.ausfuehren(self.con, self.pid, self.tid, nr)
        self.assertEqual(self.con.execute("SELECT rc FROM lauf ORDER BY id DESC LIMIT 1").fetchone()[0], 1)
        self.assertIn("RuntimeError: weg", self.post("CC1")[-1][2])


@unittest.skipUnless(os.name == "nt" and shutil.which("git"), "Arbeiter nur unter Windows (Job-Objekt)")
class NurLesen(Basis):
    """Der Gegenleser mit der Attrappe: nur Glob/Grep/Read, --restricted, eigener Ordner mit genau den Dateien, keine Rückmeldung."""

    def lesen(self, art, **env):
        self.beschluss(0)
        nr = themen.pflegen(self.con, self.pid, "CC1", self.tid, "Anmeldung mit Firmen-Konto.")
        datei = os.path.join(self.ordner.name, "aufruf.json")
        aus = gegenlesen.lesen(self.con, self.pid, themen.finden(self.con, self.pid, self.tid), nr, "haiku", prog=ATTRAPPE,
                               zusatz={"ATTRAPPE_ART": art, "ATTRAPPE_UMGEBUNG": datei, **env})
        with open(datei, encoding="utf-8") as f:
            return aus, json.load(f)

    def test_liest_und_antwortet(self):
        aus, aufruf = self.lesen("gegenlesen", ATTRAPPE_ERGEBNIS="- Abschnitt 2 widerspricht B1.")
        self.assertEqual((aus["einwaende"], aus["usd"], aus["fehler"]), ("- Abschnitt 2 widerspricht B1.", 0.001, None))
        a = aufruf["argv"]
        self.assertEqual(a[a.index("--tools") + 1], "Glob,Grep,Read")
        self.assertIn("--restricted", a)
        self.assertEqual((a[a.index("--model") + 1], a[a.index("--permission-mode") + 1]), ("haiku", "dontAsk"))
        self.assertNotIn("--mcp-config", a)                                                  # keine Rückmeldung, kein Connector
        self.assertEqual(aufruf["dateien"], [".git", "beschluesse.md", "thema.md"])         # genau das, und nur im eigenen Ordner
        self.assertIn("Keine Einwände", aufruf["auftrag"])

    def test_dateien_mit_beschluessen_und_freigegebener_fassung(self):
        self.beschluss(0)
        eins = themen.pflegen(self.con, self.pid, "CC1", self.tid, "Erste Fassung.")
        with self.assertRaisesRegex(kern.AmwFehler, "in Arbeit"):                              # liest noch: nicht beim Menschen
            themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        gegenlesen.abschliessen(self.con, self.pid, self.tid, eins, {"einwaende": "Keine Einwände.", "usd": 0.01, "modell": "haiku"})
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        nr = themen.pflegen(self.con, self.pid, "CC1", self.tid, "Zweite Fassung.")
        ordner = os.path.join(self.ordner.name, "lesen")
        os.makedirs(ordner)
        namen = gegenlesen._dateien(self.con, self.pid, themen.finden(self.con, self.pid, self.tid), nr, ordner)
        self.assertEqual(namen, ["beschluesse.md", "freigegeben.md", "thema.md"])
        lies = lambda n: open(os.path.join(ordner, n), encoding="utf-8").read()
        self.assertIn("SSO Pflicht", lies("beschluesse.md"))
        self.assertIn("Erste Fassung.", lies("freigegeben.md"))
        self.assertIn("Zweite Fassung.", lies("thema.md"))

    def test_schreibversuch_bricht_ab(self):
        aus, _ = self.lesen("schreibt")
        self.assertIsNone(aus["einwaende"])
        self.assertIn("Werkzeug außerhalb der Liste", aus["fehler"])

    def test_freigabe_nur_lesen(self):
        f = arbeiter.freigabe_lesen()["permissions"]
        self.assertEqual((f["defaultMode"], f["allow"]), ("dontAsk", ["Glob(./**)", "Grep(./**)", "Read(./**)"]))   # A1970: nur der eigene Ordner
        self.assertTrue({"Bash", "Edit", "Write", "WebFetch", "WebSearch"} <= set(f["deny"]))


if __name__ == "__main__":
    unittest.main()
