"""A1931 (TH159, #29930): weitere Anbieter je Projekt – freigeben nur der Mensch, nur der Pfad der Schlüsseldatei gespeichert,
apiKeyHelper gibt nur freigegebene Dateien aus, Paket nennt den Anbieter im Modell (anbieter@modell), Regeln 13/3/14, Negativprobe
je Anbieter mit „Schlüssel unsichtbar“; nicht bestanden hält nur die Pakete des Anbieters an."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from amw import anbieter, anbieter_schluessel as schluessel, arbeiter, arbeitspaket, cli, db, disponent, kern, versionsprobe, waechter
from tests import test_arbeiter as ta

GEHEIM = "sk-test-GEHEIM-0123456789abcdef"


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        o = self.ordner.name
        self.pfad = os.path.join(o, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad, "LOCALAPPDATA": os.path.join(o, "lad")})
        u.start()
        self.addCleanup(u.stop)
        for k in ("AMW_AGENT", "AMW_PROJEKT"):
            os.environ.pop(k, None)
        self.freigabe = os.path.join(o, "freigabe.json")
        f = mock.patch.object(anbieter, "FREIGABE", self.freigabe)
        f.start()
        self.addCleanup(f.stop)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        os.makedirs(os.path.join(o, "projekt"))
        kern.projekt_ordner_setzen(self.con, self.pid, os.path.join(o, "projekt"))
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, platz_wurzel=os.path.join(o, "plaetze"), plaetze=2)
        os.makedirs(os.path.join(o, "geheim"))
        self.schluessel = os.path.join(o, "geheim", "minimax.key")
        with open(self.schluessel, "w", encoding="utf-8") as f:
            f.write(GEHEIM + "\n")

    def freigeben(self, name="minimax", lokal=False, url="https://api.minimax.example/anthropic"):
        return anbieter.freigeben(self.con, self.pid, kern.ENTWICKLER, name, url, self.schluessel, lokal, ["MiniMax-M2", "MiniMax-M1"])

    def nirgends_der_schluessel(self):
        for t, sp in (("plan_ereignis", "text"), ("nachricht", "text"), ("nachricht", "kurz"), ("projekt", "einstellungen")):
            for (x,) in self.con.execute(f"SELECT {sp} FROM {t}").fetchall():
                self.assertNotIn(GEHEIM, x or "", f"{t}.{sp}")
        with open(self.freigabe, encoding="utf-8") as f:
            self.assertNotIn(GEHEIM, f.read())


class Freigabe(Grund):
    def test_nur_pfad_gespeichert_und_liste(self):
        name, e = self.freigeben()
        self.assertEqual((name, e["schluessel_datei"], e["modelle"], e["lokal"]), ("minimax", self.schluessel, ["MiniMax-M2", "MiniMax-M1"], False))
        self.assertEqual(anbieter.eintrag(self.con, self.pid, "minimax")["basis_url"], "https://api.minimax.example/anthropic")
        self.assertEqual(anbieter.eintrag(self.con, self.pid, "anthropic"), {"name": "anthropic", "standard": True})   # wie bisher
        self.assertIsNone(anbieter.eintrag(self.con, self.pid, "ollama"))
        with open(self.freigabe, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"pfade": [os.path.normcase(self.schluessel)]})
        self.nirgends_der_schluessel()
        anbieter.entfernen(self.con, self.pid, kern.ENTWICKLER, "minimax")
        with open(self.freigabe, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"pfade": []})

    def test_nur_der_mensch(self):
        with self.assertRaisesRegex(kern.AmwFehler, "nur der Mensch"):
            anbieter.freigeben(self.con, self.pid, "TL", "minimax", "https://x.example", self.schluessel, False, ["m"])
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_AGENT": "", "CLAUDECODE": "1", "CLAUDE_CODE_MESSAGING_SOCKET": ""}), \
                contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "Spiel", "--von", "Entwickler", "anbieter", "freigeben", "minimax", "--url", "https://x.example",
                           "--schluessel-datei", self.schluessel, "--modelle", "m"])
        self.assertNotEqual(rc, 0)
        self.assertIn("nur der Mensch", aus.getvalue())
        self.assertEqual(anbieter.liste(self.con, self.pid), {})

    def test_pruefung_der_angaben(self):
        o = self.ordner.name
        innen = os.path.join(o, "projekt", "k.key")
        open(innen, "w").close()
        for name, url, pfad, lokal, ms, grund in (
                ("anthropic", "https://x.example", self.schluessel, False, ["m"], "Standard"),
                ("Mini Max", "https://x.example", self.schluessel, False, ["m"], "Buchstabe"),
                ("minimax", "http://x.example", self.schluessel, False, ["m"], "https"),
                ("minimax", "https://x.example", "relativ.key", False, ["m"], "absoluter Pfad"),
                ("minimax", "https://x.example", os.path.join(o, "fehlt.key"), False, ["m"], "gibt es nicht"),
                ("minimax", "https://x.example", innen, False, ["m"], "im Projektordner"),
                ("minimax", "https://x.example", self.schluessel, False, [], "mindestens eins")):
            with self.subTest(grund=grund), self.assertRaisesRegex(kern.AmwFehler, grund):
                anbieter.freigeben(self.con, self.pid, kern.ENTWICKLER, name, url, pfad, lokal, ms)
        n, e = anbieter.freigeben(self.con, self.pid, kern.ENTWICKLER, "ollama", "http://localhost:11434", self.schluessel, True, ["qwen"])
        self.assertTrue(e["lokal"])                                                                   # lokal: http://localhost geht


class Helfer(Grund):
    def test_gibt_nur_freigegebene_aus(self):
        self.freigeben()
        aus, fehler = io.StringIO(), io.StringIO()
        self.assertEqual(schluessel.ausgeben(self.schluessel, self.freigabe, aus, fehler), 0)
        self.assertEqual(aus.getvalue(), GEHEIM)
        anderer = os.path.join(self.ordner.name, "geheim", "anderer.key")
        with open(anderer, "w") as f:
            f.write("sk-ANDERER-0123456789")
        aus, fehler = io.StringIO(), io.StringIO()
        self.assertEqual(schluessel.ausgeben(anderer, self.freigabe, aus, fehler), 2)
        self.assertEqual(aus.getvalue(), "")
        self.assertNotIn("ANDERER", fehler.getvalue())
        self.assertEqual(schluessel.ausgeben(self.schluessel, os.path.join(self.ordner.name, "keine.json"), io.StringIO(), io.StringIO()), 2)

    def test_einstieg_als_prozess(self):
        r = subprocess.run([sys.executable, "-I", "-X", "utf8", anbieter.EINSTIEG, self.schluessel], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual((r.returncode, r.stdout, r.stderr.strip()), (2, "", "Schlüsseldatei nicht freigegeben"))   # nicht in der echten Liste

    def test_settings_teil_ohne_schluessel(self):
        _, e = self.freigeben()
        s = anbieter.settings_teil(dict(e, name="minimax"))
        self.assertEqual(s["env"], {"ANTHROPIC_BASE_URL": "https://api.minimax.example/anthropic"})
        self.assertIn(anbieter.EINSTIEG, s["apiKeyHelper"])
        self.assertIn(self.schluessel, s["apiKeyHelper"])
        self.assertNotIn(GEHEIM, json.dumps(s))
        self.assertIsNone(anbieter.settings_teil({"name": "anthropic", "standard": True}))


class Pakete(Grund):
    def setUp(self):
        super().setUp()
        with db.schreiben(self.con):                         # Claude Code 9.9.9 selbst ist geprüft (sonst hielte Regel 11 vorher an)
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="AMW", art=versionsprobe.GEPRUEFT_ART,
                         text=json.dumps({"version": "9.9.9"}))

    def paket(self, modell=None, bereich="lib/"):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Paket", "TL")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET pruefbefehl = 'python -m unittest', dateibereich = ? WHERE id = ?", (bereich, aid))
        arbeitspaket.setzen(self.con, self.pid, "TL", aid, art="p", **({"modell": modell} if modell else {}))
        arbeitspaket.zustand_setzen(self.con, self.pid, "TL", aid, "startklar")
        return aid

    def test_modell_mit_anbieter(self):
        aid = self.paket("MiniMax@MiniMax-M2")
        f = arbeitspaket.lesen(self.con, aid)
        self.assertEqual((f["modell"], f["anbieter"]), ("minimax@MiniMax-M2", "minimax"))
        self.assertEqual(arbeitspaket.lesen(self.con, self.paket(bereich="b/"))["anbieter"], "anthropic")
        with self.assertRaisesRegex(kern.AmwFehler, "anbieter@modell"):
            arbeitspaket.setzen(self.con, self.pid, "TL", aid, modell="1x@")

    def test_regeln_13_3_14(self):
        aid = self.paket("minimax@MiniMax-M2")
        r = waechter.pruefen(self.con, self.pid, aid, limit=10)
        self.assertEqual((r["regel"], r["warten"]), (13, False))
        self.freigeben()
        with mock.patch.object(versionsprobe, "installiert", return_value="9.9.9"):
            r = waechter.pruefen(self.con, self.pid, aid, limit=10)
            self.assertEqual((r["regel"], r["anbieter"], r["version"], r["warten"]), (14, "minimax", "9.9.9", True))
            with db.schreiben(self.con):
                db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="AMW", art=versionsprobe.ANBIETER_GEPRUEFT,
                             text=json.dumps({"anbieter": "minimax", "version": "9.9.9"}))
            self.assertIsNone(waechter.pruefen(self.con, self.pid, aid, limit=10)["regel"])
            self.assertEqual(waechter.pruefen(self.con, self.pid, aid, limit=10)["ok"], True)
        anbieter.freigeben(self.con, self.pid, kern.ENTWICKLER, "ollama", "http://localhost:11434", self.schluessel, True, ["qwen"])
        lokal = self.paket("ollama@qwen", bereich="c/")
        r = waechter.pruefen(self.con, self.pid, lokal, limit=10)
        self.assertEqual(r["regel"], 3)
        self.assertIn("Grafikkarte", r["grund"])

    def test_disponent_stoesst_probe_an_und_macht_weiter(self):
        self.freigeben()
        a = self.paket("minimax@MiniMax-M2")
        b = self.paket(bereich="b/")
        gestartet, gespawnt = [], []
        with mock.patch.object(versionsprobe, "installiert", return_value="9.9.9"), \
                mock.patch.object(versionsprobe, "_spawn", side_effect=lambda *x: gespawnt.append(x) or 4711), \
                mock.patch.object(disponent, "starten", side_effect=lambda con, pid, aid, *r, **k: gestartet.append(aid) or f"A{aid}"):
            aus = disponent.runde(self.con, prog=["x"])
            disponent.runde(self.con, prog=["x"])
        self.assertIn("Anbieter minimax mit Claude Code 9.9.9 nicht geprüft → Negativprobe gestartet (Prozess 4711)", aus)
        self.assertEqual([x[3] for x in gespawnt], ["minimax"])                                     # einmal je Anbieter und Version
        self.assertEqual(gestartet[0], b)                                                             # das andere Paket startet
        self.assertNotIn(a, gestartet)
        self.assertEqual(versionsprobe.proben(self.con, "9.9.9"), [])                                 # die Probe der Version ist eine andere


class Probe(Grund):
    def test_schluessel_unsichtbar(self):
        o = self.ordner.name
        klon = os.path.join(o, "klon")
        os.makedirs(klon)
        prot = os.path.join(o, "lauf.jsonl")
        sett = os.path.join(o, "einstellungen.json")
        with open(sett, "w") as f:
            json.dump(anbieter.settings_teil(dict(self.freigeben()[1], name="minimax")), f)
        with open(prot, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "content": versionsprobe.UMGEBUNG_MARKE + " {'PATH': 'x'}"}) + "\n")
        self.assertEqual(versionsprobe.unsichtbar({"protokoll": prot}, klon, sett, self.schluessel), [])
        with open(prot, "a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "content": "ANTHROPIC_API_KEY=" + GEHEIM}) + "\n")
        g = versionsprobe.unsichtbar({"protokoll": prot}, klon, sett, self.schluessel)
        self.assertEqual(g, ["Schlüssel sichtbar in lauf.jsonl"])
        self.assertNotIn(GEHEIM, " ".join(g))
        os.remove(prot)
        with open(os.path.join(klon, "notiz.txt"), "w") as f:
            f.write(GEHEIM)
        self.assertEqual(versionsprobe.unsichtbar({"protokoll": prot}, klon, sett, self.schluessel),
                         ["Schlüssel sichtbar in notiz.txt", "Schlüssel nicht geprüft: die Umgebung des Bash-Kinds wurde nicht gezeigt"
                          " (Abnahme-Befehl nicht gelaufen)"])

    def test_abschliessen_je_anbieter(self):
        self.freigeben()
        aus = {"ergebnis": "bestanden", "gruende": [], "bericht": "# Probe\n\n" + versionsprobe.RESTRISIKO + "\n", "anbieter": "minimax"}
        versionsprobe.abschliessen(self.con, self.pid, "9.9.9", aus, 7, anbieter="minimax")
        self.assertTrue(versionsprobe.anbieter_geprueft(self.con, "minimax", "9.9.9"))
        self.assertNotIn("9.9.9", versionsprobe.geprueft(self.con))                                  # die Version selbst nicht
        m = self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE 'Anbieter minimax mit Claude Code 9.9.9 geprüft%'").fetchone()
        self.assertIn("Restrisiko", m[0])
        versionsprobe.abschliessen(self.con, self.pid, "9.9.10", {"ergebnis": "nicht bestanden", "gruende": ["Schlüssel sichtbar in lauf.jsonl"],
                                                                  "bericht": "x"}, 8, anbieter="minimax")
        self.assertFalse(versionsprobe.anbieter_geprueft(self.con, "minimax", "9.9.10"))
        self.assertFalse(waechter.zustand()["wartung"])                                              # nur seine Pakete halten an
        self.assertTrue(self.con.execute("SELECT 1 FROM nachricht WHERE kurz LIKE 'Anbieter minimax: Negativprobe nicht bestanden%'").fetchone())
        self.nirgends_der_schluessel()

    def test_bericht_nennt_das_restrisiko(self):
        b = versionsprobe.bericht({"ergebnis": "bestanden", "version": "9.9.9", "anbieter": "minimax", "aufrufe": [], "abgelehnt": set(),
                                   "gruende": []}, None)
        self.assertIn("Anbieter minimax", b)
        self.assertIn(versionsprobe.RESTRISIKO, b)


@unittest.skipUnless(os.name == "nt", "Job-Objekt nur unter Windows")
class Lauf(unittest.TestCase):
    setUp, laufen = ta.Arbeiter.setUp, ta.Arbeiter.laufen

    def test_settings_und_modell_mit_anbieter(self):
        e = {"name": "minimax", "basis_url": "https://api.minimax.example/anthropic", "schluessel_datei": r"C:\geheim\m.key",
             "modelle": ["MiniMax-M2"]}
        r = self.laufen(modell="minimax@MiniMax-M2", anbieter=e)
        self.assertIsNone(r["fehler"])
        with open(os.environ["ATTRAPPE_UMGEBUNG"], encoding="utf-8") as f:
            d = json.load(f)
        argv = d["argv"]
        self.assertEqual(argv[argv.index("--model") + 1], "MiniMax-M2")                               # ohne Präfix
        with open(argv[argv.index("--settings") + 1], encoding="utf-8") as f:
            s = json.load(f)
        self.assertEqual(s["env"], {"ANTHROPIC_BASE_URL": "https://api.minimax.example/anthropic"})
        self.assertIn(r"C:\geheim\m.key", s["apiKeyHelper"])
        self.assertIn("permissions", s)                                                               # die Freigabeliste bleibt
        self.assertNotIn("ANTHROPIC_API_KEY", d["umgebung"])                                          # nie in der Umgebung
        self.assertNotIn("ANTHROPIC_BASE_URL", d["umgebung"])


if __name__ == "__main__":
    unittest.main()
