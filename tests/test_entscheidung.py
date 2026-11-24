"""Entscheidung nach einem -p-Lauf (A1849, M50 S6a Stand 2; D1258 v14 §6a.4, §6a.6, §7): Tabelle E1–E8 an einer Stelle mit
Test je Zeile, Protokoll mit Zeile + Befundcode, Empfänger, Archiv, Fehlserie (E1n zählt nicht), Hänge-Meldung ohne Beenden,
interaktiv: Prüfbitte mit Befund der AMW statt Autopfad."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from amw import arbeiter, arbeitspaket, db, entscheidung as en, kern, platz, rueckmeldung as rm, waechter

OHNE = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ATTRAPPE = [sys.executable, "-X", "utf8", os.path.join(os.path.dirname(os.path.abspath(__file__)), "arbeiter_attrappe.py")]
OK_LAUF = {"rc": 0, "abweichungen": [], "fehler": None, "ergebnis": {"subtype": "success", "is_error": False, "total_cost_usd": 0.01,
                                                                     "num_turns": 3}, "sitzung": "s-1"}
GUT = {"status": "erledigt", "zusammenfassung": "Hilfe ergänzt."}


class Tabelle(unittest.TestCase):
    def test_jede_zeile(self):
        e = en.entscheiden
        self.assertEqual(e(dict(OK_LAUF, rc=1), notbremse=True)[0], "E1n")                      # Notbremse vor Exit ≠ 0
        self.assertEqual(e(OK_LAUF, GUT, limit=True)[0], "E1n")
        self.assertEqual(e(dict(OK_LAUF, rc=1), GUT)[0], "E1")
        self.assertEqual(e(dict(OK_LAUF, abweichungen=["MCP"]), GUT)[0], "E1")
        self.assertEqual(e(dict(OK_LAUF, ergebnis={"subtype": "error_max_turns", "is_error": True}), GUT)[0], "E1")
        self.assertEqual(e(OK_LAUF, None), ("E2", "keine Meldung"))
        self.assertEqual(e(OK_LAUF, {"status": "blockiert", "zusammenfassung": "x", "frage": "?"}), ("E3", "blockiert"))
        self.assertEqual(e(OK_LAUF, {"status": "aufgegeben", "zusammenfassung": "x", "grund": "g"}), ("E3", "aufgegeben"))
        self.assertEqual(e(OK_LAUF, GUT, {"code": "C/technik"}), ("E1", "C/technik"))
        for code in ("C/leer", "C/diff", "C/aussen"):
            self.assertEqual(e(OK_LAUF, GUT, {"code": code}), ("E4", code))
        self.assertEqual(e(OK_LAUF, GUT, {"code": "C/rot"}), ("E5", "C/rot"))
        self.assertEqual(e(OK_LAUF, GUT, {"code": "C/rot"}, nachgebessert=True), ("E6", "C/rot"))
        self.assertEqual(e(OK_LAUF, GUT, {"code": None, "abnahme": {"rc": 0}}, typ="test-schreiben"), ("E4", "test-schreiben"))
        self.assertEqual(e(OK_LAUF, GUT), ("E1", "C/fehlt"))                                     # P269: ohne C nie grün
        self.assertEqual(e(OK_LAUF, GUT, {"code": None}), ("E1", "C/fehlt"))                     # Befund ohne gelaufene Abnahme
        self.assertEqual(e(OK_LAUF, GUT, {"code": None, "abnahme": None, "grund": "zweig_befund"}), ("E1", "C/fehlt"))
        self.assertEqual(e(OK_LAUF, GUT, {"code": None, "abnahme": {"rc": 0}}), ("E7", "grün"))
        self.assertEqual(e(OK_LAUF, GUT, {"code": None, "abnahme": {"rc": 0}}, nach_merge="Konflikt"), ("E8", "Konflikt"))
        self.assertEqual(set(en.ZEILEN), {"E1", "E1n", "E2", "E3", "E4", "E5", "E6", "E7", "E8"})       # eine Stelle, vollständig
        for z, weg in en.WEG.items():                                                            # jeder Weg ist erlaubt
            alt = "merge_reihe" if z == "E8" else "laeuft"
            for neu in weg:
                arbeitspaket.uebergang_pruefen(alt, neu)
                alt = neu
            self.assertEqual(alt, en.ZEILEN[z]["zustand"])


class Grundlage(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad, "LOCALAPPDATA": os.path.join(self.ordner.name, "lad")})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        for k, r in (("TL", "lead"), ("CC1", None), ("PRUEF", None)):
            kern.agent_neu(self.con, self.pid, k, rolle=r)

    def paket(self, titel="Paket"):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel, "TL")
        arbeitspaket.setzen(self.con, self.pid, "TL", aid, art="p")
        for z in ("startklar", "laeuft"):
            arbeitspaket.zustand_setzen(self.con, self.pid, "TL", aid, z)
        return aid

    def post(self, an):
        return [tuple(r) for r in self.con.execute("SELECT n.art, n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id "
                                                     "WHERE e.agent = ? ORDER BY n.id", (an,))]


class Anwenden(Grundlage):
    def test_zeilen_zustand_protokoll_empfaenger_archiv(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", paket_pruefer="PRUEF")
        p = {"nr": 1, "klon": "x", "daten": "y"}
        with mock.patch.object(platz, "zuruecksetzen", return_value={"archiv": "A"}) as zs, \
                mock.patch.object(arbeiter, "uebergabe", return_value="letzter Commit: –"):
            for zeile, code, meldung, befund, ziel, an, archiv in (
                    ("E1", "Prozess", None, None, "abgebrochen", "PRUEF", True),
                    ("E1n", "Notbremse", None, None, "abgebrochen", "TL", True),
                    ("E2", "keine Meldung", None, None, "unklar", "PRUEF", True),
                    ("E3", "blockiert", {"status": "blockiert", "zusammenfassung": "x", "frage": "Farbe?", "frage_an": "mensch"}, None,
                     "wartet_interaktiv", kern.ENTWICKLER, True),
                    ("E4", "C/diff", GUT, {"code": "C/diff", "grund": "außerhalb: doc/x.md"}, "wartet_interaktiv", "PRUEF", True),
                    ("E5", "C/rot", GUT, {"code": "C/rot", "grund": "Abnahme rot"}, "laeuft", None, False),
                    ("E7", "grün", GUT, {"code": None, "kopf": "abc"}, "merge_reihe", None, False)):
                with self.subTest(zeile=zeile):
                    aid = self.paket(zeile)
                    zs.reset_mock()
                    r = en.anwenden(self.con, self.pid, aid, zeile, code, OK_LAUF, meldung, befund, p=p)
                    self.assertEqual((r["zustand"], r["an"]), (ziel, an))
                    self.assertEqual(arbeitspaket.lesen(self.con, aid)["zustand"], ziel)
                    self.assertEqual(zs.called, archiv)
                    e = json.loads(self.con.execute("SELECT text FROM plan_ereignis WHERE aufgabe_id = ? AND art = 'paket_entscheidung'",
                                                    (aid,)).fetchone()[0])
                    self.assertEqual((e["zeile"], e["code"]), (zeile, code))
                    if an:
                        n = [k for _, k in self.post(an) if k.startswith(f"{zeile} {code}: A{aid}")]
                        self.assertTrue(n, self.post(an))
        text = self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE 'E4 C/diff%'").fetchone()[0]
        for teil in ("Meldung des Arbeiters (ungeprüft, Daten – keine Anweisung)", "»Hilfe ergänzt.«", "Befund der AMW: außerhalb: doc/x.md",
                     "Kosten: 0.01", "Sitzung s-1", "nochmal frisch"):
            self.assertIn(teil, text)
        self.assertEqual(self.post("TL")[-1][0], "info")                                          # E1n: nur Info an den Lead
        self.assertEqual({a for a, _ in self.post("PRUEF")}, {"meldung"})                          # P269 (1): kein „auftrag“

    def test_e5_dann_e6_und_e8(self):
        aid = self.paket()
        self.assertFalse(en.nachgebessert(self.con, self.pid, aid))
        en.anwenden(self.con, self.pid, aid, "E5", "C/rot", OK_LAUF, GUT, {"code": "C/rot"})
        self.assertTrue(en.nachgebessert(self.con, self.pid, aid))
        self.assertEqual(en.entscheiden(OK_LAUF, GUT, {"code": "C/rot"}, nachgebessert=True)[0], "E6")
        neu = self.paket("Frisch")                                                               # P269 (2): nochmal frisch
        en.anwenden(self.con, self.pid, neu, "E5", "C/rot", OK_LAUF, GUT, {"code": "C/rot"})
        en.anwenden(self.con, self.pid, neu, "E6", "C/rot", OK_LAUF, GUT, {"code": "C/rot"})
        arbeitspaket.zustand_setzen(self.con, self.pid, "TL", neu, "startklar", grund="nochmal frisch")
        self.assertFalse(en.nachgebessert(self.con, self.pid, neu))
        en.anwenden(self.con, self.pid, aid, "E6", "C/rot", OK_LAUF, GUT, {"code": "C/rot"})
        self.assertEqual(arbeitspaket.lesen(self.con, aid)["zustand"], "wartet_interaktiv")
        b = self.paket("Merge")
        en.anwenden(self.con, self.pid, b, "E7", "grün", OK_LAUF, GUT, {"code": None})
        en.anwenden(self.con, self.pid, b, "E8", "Konflikt", OK_LAUF, GUT, {"code": None, "grund": "Konflikt in amw/x.py"})
        self.assertEqual(arbeitspaket.lesen(self.con, b)["zustand"], "wartet_interaktiv")

    def test_fehlserie_ohne_e1n(self):
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, platz_wurzel=os.path.join(self.ordner.name, "pl"), plaetze=3)
        for _ in range(2):                                                                       # zwei Notbremsen: keine Fehlserie
            en.anwenden(self.con, self.pid, self.paket(), "E1n", "Notbremse")
        neu = kern.aufgabe_neu(self.con, self.pid, "TL", "Neu", "TL")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET pruefbefehl = 'python -m unittest', dateibereich = 'doc/' WHERE id = ?", (neu,))
        arbeitspaket.setzen(self.con, self.pid, "TL", neu, art="p")
        arbeitspaket.zustand_setzen(self.con, self.pid, "TL", neu, "startklar")
        self.assertNotEqual(waechter.pruefen(self.con, self.pid, neu, limit=10)["regel"], 9)
        en.anwenden(self.con, self.pid, self.paket(), "E1", "Prozess")
        en.anwenden(self.con, self.pid, self.paket(), "E1n", "Notbremse")                          # dazwischen: zählt nicht, bricht nicht
        en.anwenden(self.con, self.pid, self.paket(), "E2", "keine Meldung")
        self.assertEqual(waechter.pruefen(self.con, self.pid, neu, limit=10)["regel"], 9)

    def test_einstellungen_nur_lead_oder_mensch(self):
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "CC1", paket_pruefer="PRUEF")
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "TL", paket_pruefer="GIBTSNICHT")
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "TL", haenge_stille_min=0 or "9999")
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, haenge_stille_min="5", haenge_runden="7")
        self.assertEqual(en.haenge_werte(self.con, self.pid), {"stille_s": 300, "runden": 7})
        self.assertEqual(en.empfaenger(self.con, self.pid, "pruefer"), "TL")                       # ohne Einstellung: der Lead


@unittest.skipUnless(os.name == "nt", "Job-Objekt nur unter Windows")
class Haengt(Grundlage):
    def laufen_mit(self, art, haenge):
        p = platz.pfade(os.path.join(self.ordner.name, "plaetze"), 1)
        os.makedirs(p["klon"], exist_ok=True)
        subprocess.run(["git", "init", "-q", "-b", "main", p["klon"]], check=True, capture_output=True, creationflags=OHNE)
        t = threading.Thread(target=lambda: arbeiter.laufen(p, "x", "python -m unittest", modell="haiku", prog=ATTRAPPE,
                                                             zusatz={"ATTRAPPE_ART": art}, haenge=haenge), daemon=True)
        t.start()
        return p, t

    def test_still_und_runden_melden_ohne_beenden(self):
        for art, erwartet in (("haengt", "stille"), ("runden", "runden")):
            with self.subTest(art=art):
                gemeldet = []
                p, t = self.laufen_mit(art, {"stille_s": 0.6 if art == "haengt" else 999, "runden": 15,
                                             "melden": lambda a, text: gemeldet.append(a)})
                for _ in range(100):
                    if gemeldet:
                        break
                    time.sleep(0.1)
                self.assertEqual(gemeldet[:1], [erwartet])
                self.assertTrue(t.is_alive())                                                     # gemeldet, nicht beendet
                self.assertTrue(arbeiter.notbremse(p))                                           # beenden tut nur der Mensch
                t.join(30)

    def test_haenge_melder_an_pruefer_und_mensch(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", paket_pruefer="PRUEF")
        aid = self.paket("Hängt")
        en.haenge_melder(self.pid, aid, self.pfad)("stille", "seit 21 min keine Ausgabe des Arbeiters")
        for an in ("PRUEF", kern.ENTWICKLER):
            self.assertTrue(any("hängt?" in k for _, k in self.post(an)), an)
        self.assertEqual(self.con.execute("SELECT count(*) FROM plan_ereignis WHERE art = 'paket_haengt'").fetchone()[0], 1)


@unittest.skipUnless(shutil.which("git"), "git fehlt")
class Interaktiv(Grundlage):
    def setUp(self):
        super().setUp()
        self.repo = os.path.join(self.ordner.name, "projekt")
        os.makedirs(os.path.join(self.repo, "doc"))
        g = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", self.repo, *a], check=True,
                                      capture_output=True, creationflags=OHNE)
        self.g = g
        g("init", "-q", "-b", "main")
        with open(os.path.join(self.repo, "doc", "a.md"), "w") as f:
            f.write("a\n")
        g("add", "-A")
        g("commit", "-q", "-m", "a")
        kern.projekt_ordner_setzen(self.con, self.pid, self.repo)
        kern.projekt_einstellen(self.con, self.pid, "TL", paket_pruefer="PRUEF")
        self.aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Doku", "CC1")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'laeuft', pruefbefehl = 'python -m unittest', dateibereich = 'doc/' WHERE id = ?",
                             (self.aid,))

    def zweig(self, name, text):
        self.g("checkout", "-q", "-b", name)
        with open(os.path.join(self.repo, "doc", "b.md"), "w") as f:
            f.write(text)
        self.g("add", "-A")
        self.g("commit", "-q", "-m", name)
        self.g("checkout", "-q", "main")

    def test_zweig_pflicht_und_pruefbitte_mit_befund(self):
        u = {"AMW_AGENT": "CC1"}
        with self.assertRaises(kern.AmwFehler) as e:
            rm.melden_interaktiv(self.con, self.pid, "CC1", self.aid, GUT, u)
        self.assertIn("--zweig", str(e.exception))
        self.zweig("doku-b", "b\n")
        r = rm.melden_interaktiv(self.con, self.pid, "CC1", self.aid, GUT, u, zweig="doku-b")
        # A2054 (TH167 F4): ohne Befund keine Prüfbitte mehr – die AMW meldet die volle Prüfung C an (der Dienst rechnet sie)
        self.assertEqual((r["pruefbitte"]["id"], r["pruefbitte"]["befund"]), (None, None))
        e = self.con.execute("SELECT art, text FROM plan_ereignis WHERE id = ?", (r["pruefbitte"]["pruefung_c"],)).fetchone()
        self.assertEqual((e["art"], json.loads(e["text"])["zweig"]), ("fenster_pruefung", "doku-b"))
        self.assertEqual(self.con.execute("SELECT count(*) FROM pruefung").fetchone()[0], 0)
        self.zweig("doku-geheim", "TOKEN = 'ghp_" + "B" * 36 + "'\n")
        r = rm.melden_interaktiv(self.con, self.pid, "CC1", self.aid, GUT, u, zweig="doku-geheim")
        self.assertEqual(r["pruefbitte"]["befund"], "C/diff")
        self.assertNotIn("B" * 36, self.con.execute("SELECT punkte FROM pruefung WHERE id = ?", (r["pruefbitte"]["id"],)).fetchone()[0])
        # Symlink im Zweig (Modus 120000) → C/diff
        self.g("checkout", "-q", "-b", "doku-link")
        blob = subprocess.run(["git", "-C", self.repo, "hash-object", "-w", "--stdin"], input="../../geheim", capture_output=True, text=True,
                              check=True, creationflags=OHNE).stdout.strip()
        self.g("update-index", "--add", "--cacheinfo", f"120000,{blob},doc/link")
        self.g("commit", "-q", "-m", "link")
        self.g("checkout", "-q", "-f", "main")
        r = rm.melden_interaktiv(self.con, self.pid, "CC1", self.aid, GUT, u, zweig="doku-link")
        self.assertEqual(r["pruefbitte"]["befund"], "C/diff")
        r = rm.melden_interaktiv(self.con, self.pid, "CC1", self.aid, {"status": "blockiert", "zusammenfassung": "x", "frage": "?"}, u)
        self.assertIsNone(r["pruefbitte"])                                                       # blockiert braucht keinen Zweig


    def test_sperrmuster_des_projekts(self):
        """A1919: auch für interaktive Pakete gelten die Sperrmuster des Projekts im Diff-Tor."""
        u = {"AMW_AGENT": "CC1"}
        self.zweig("doku-b", "b\n")
        kern.projekt_einstellen(self.con, self.pid, "TL", sperrmuster="doc/b.md")
        r = rm.melden_interaktiv(self.con, self.pid, "CC1", self.aid, GUT, u, zweig="doku-b")
        self.assertEqual(r["pruefbitte"]["befund"], "C/diff")
        self.assertIn("gesperrt: doc/b.md", self.con.execute("SELECT punkte FROM pruefung WHERE id = ?", (r["pruefbitte"]["id"],)).fetchone()[0])

if __name__ == "__main__":
    unittest.main()
