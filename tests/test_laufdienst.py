"""Läufe überleben den Warte-Prozess (A1640) und die AMW lernt ihren Bedarf (A1641): der Dienst rechnet einen dran gekommenen
Lauf selbst, wenn der Warte-Prozess im Fenster des Agenten tot ist – genau den gespeicherten Befehl im gespeicherten Ordner,
ohne Geheimnisse aus der Umgebung; „ist dran“ weckt bei solchen Läufen nicht mehr; ohne Angabe gilt der gemessene Bedarf."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

from amw import belegung, betrieb, db, kern, laufdienst

TOT = 2 ** 22 + 7          # eine PID, die es nicht gibt


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        umgebung = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        umgebung.start()
        self.addCleanup(umgebung.stop)
        self.con = db.anlegen()
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        with db.schreiben(self.con):                                       # sein Arbeitsordner (TL-Auflage 2)
            self.con.execute("UPDATE agent SET ordner = ? WHERE kennung = 'CC1'", (self.ordner.name,))
        mock.patch.object(laufdienst, "PRUEF_S", 0.2).start()
        self.addCleanup(mock.patch.stopall)
        self.dienst = laufdienst.Laufdienst(self.con, starten=lambda ziel, *args: ziel(*args))   # im Test: gleich ausführen

    def py(self, code):
        return [sys.executable, "-c", code]

    def lauf(self, befehl, waechter=TOT, ordner=None, **kw):
        datei = os.path.join(self.ordner.name, "aus.txt")
        lid = betrieb.lauf_start(self.con, self.pid, "CC1", "Probe", warten=True, speicher_frei=32.0, braucht_gb=kw.pop("braucht_gb", 1),
                                 befehl=befehl, ordner=ordner or self.ordner.name, ergebnis_datei=datei, waechter=waechter, **kw)
        return lid, datei

    def zeile(self, lid):
        return self.con.execute("SELECT * FROM lauf WHERE id = ?", (lid,)).fetchone()

    def an_cc1(self):
        return [(r["art"], r["kurz"]) for r in self.con.execute(
            "SELECT n.art, n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = 'CC1' ORDER BY n.id")]


class Uebernehmen(Grund):
    def test_warte_prozess_tot_der_dienst_rechnet_genau_den_befehl(self):
        lid, datei = self.lauf(self.py("import os, sys; print('im Ordner', os.getcwd()); sys.exit(3)"))
        self.assertEqual(self.zeile(lid)["status"], "laeuft")
        self.assertEqual(json.loads(self.zeile(lid)["befehl"])[0], sys.executable)
        self.dienst.runde()
        z = self.zeile(lid)
        self.assertEqual((z["status"], z["rc"], z["ausfuehrer"]), ("fertig", 3, "dienst"))
        with open(datei, encoding="utf-8") as f:
            aus = f.read()
        self.assertIn(f"im Ordner {self.ordner.name}", aus)
        self.assertIn("gerechnet vom Dienst", aus)
        self.assertIn(datei, z["ergebnis"])
        self.assertTrue(any(a == "meldung" and f"L{lid} fertig, rc 3 – vom Dienst gerechnet" in k for a, k in self.an_cc1()), self.an_cc1())

    def test_lebender_warte_prozess_startet_selbst_und_nie_doppelt(self):
        lid, _ = self.lauf(self.py("print(1)"), waechter=os.getpid())
        self.dienst.runde()
        self.assertIsNone(self.zeile(lid)["ausfuehrer"])                 # der Dienst lässt ihn in Ruhe
        self.assertTrue(betrieb.lauf_uebernehmen(self.con, lid, "agent"))
        self.assertFalse(betrieb.lauf_uebernehmen(self.con, lid, "dienst"))
        self.assertEqual(self.zeile(lid)["ausfuehrer"], "agent")

    def test_fensterlaeufe_uebernimmt_der_dienst_nicht(self):
        with mock.patch.object(betrieb.schirm_mod, "sperrgrund", return_value=None):
            lid, _ = self.lauf(self.py("print(1)"), schirm=True)
        self.dienst.runde()
        self.assertIsNone(self.zeile(lid)["ausfuehrer"])

    def test_umgebung_ohne_geheimnisse_und_kennung(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_MESSAGING_TOKEN": "geheim-123", "AMW_AGENT": "CC1"}):
            lid, datei = self.lauf(self.py("import os; print('T=%s A=%s' % (os.environ.get('CLAUDE_CODE_MESSAGING_TOKEN'), os.environ.get('AMW_AGENT')))"))
            self.dienst.runde()
        with open(datei, encoding="utf-8") as f:
            aus = f.read()
        self.assertIn("T=None A=None", aus)
        self.assertNotIn("geheim-123", aus + json.dumps(dict(self.zeile(lid))))

    def test_frist_beendet_den_befehl(self):
        lid, _ = self.lauf(self.py("import time; time.sleep(60)"), frist_min=0.02)
        self.dienst.runde()
        z = self.zeile(lid)
        self.assertEqual((z["status"], z["rc"]), ("abgebrochen", laufdienst.RC_FRIST))

    def test_nach_neustart_ohne_prozess_endet_der_lauf_mit_hinweis(self):
        lid, _ = self.lauf(self.py("print(1)"))
        betrieb.lauf_uebernehmen(self.con, lid, "dienst")                 # ein früherer Dienst hatte ihn
        laufdienst.Laufdienst(self.con, starten=lambda ziel, *args: ziel(*args)).runde()
        z = self.zeile(lid)
        self.assertEqual(z["status"], "abgebrochen")
        self.assertIn("Dienst neu gestartet", z["ergebnis"])


class Auflagen(Grund):
    """TL D982: (1) nur im Terminal, (2) nur im Arbeitsordner des Agenten, (3) nicht bei entfernt/Halt, (4) im Verlauf."""

    def nicht_ausgefuehrt(self, lid, wort):
        self.dienst.runde()
        z = self.zeile(lid)
        self.assertEqual(z["status"], "abgebrochen")
        self.assertIn("nicht ausgeführt", z["ergebnis"])
        self.assertIn(wort, z["ergebnis"])
        self.assertTrue(any("abgebrochen" in k for _, k in self.an_cc1()))

    def test_ordner_ausserhalb_und_umweg_ueber_punktpunkt(self):
        with tempfile.TemporaryDirectory() as fremd:
            lid, _ = self.lauf(self.py("print('nie')"), ordner=fremd)
            self.nicht_ausgefuehrt(lid, "liegt nicht im Arbeitsordner")
        lid, _ = self.lauf(self.py("print('nie')"), ordner=os.path.join(self.ordner.name, "..", os.path.basename(self.ordner.name) + "x"))
        self.nicht_ausgefuehrt(lid, "liegt nicht im Arbeitsordner")
        unter = os.path.join(self.ordner.name, "sub")
        os.makedirs(unter)
        lid, _ = self.lauf(self.py("print('ja')"), ordner=os.path.join(unter, "..", "sub"))   # Umweg, der drin bleibt: erlaubt
        self.dienst.runde()
        self.assertEqual(self.zeile(lid)["status"], "fertig")

    def test_zusatzordner_zaehlt(self):
        with tempfile.TemporaryDirectory() as zusatz:
            with db.schreiben(self.con):
                self.con.execute("UPDATE agent SET zusatzordner = ? WHERE kennung = 'CC1'", (json.dumps([zusatz]),))
            lid, _ = self.lauf(self.py("print('ok')"), ordner=zusatz)
            self.dienst.runde()
            self.assertEqual(self.zeile(lid)["status"], "fertig")

    def test_halt_und_entfernt(self):
        lid, _ = self.lauf(self.py("print('nie')"))
        with mock.patch.object(kern, "halt_gilt", return_value=True):
            self.nicht_ausgefuehrt(lid, "HALT gilt")
        lid, _ = self.lauf(self.py("print('nie')"))
        with db.schreiben(self.con):
            self.con.execute("UPDATE agent SET entfernt_utc = ? WHERE kennung = 'CC1'", (db.jetzt(),))
        self.dienst.runde()
        z = self.zeile(lid)
        self.assertEqual(z["status"], "abgebrochen")
        self.assertIn("entfernt", z["ergebnis"])
        an_tl = [r[0] for r in self.con.execute("SELECT n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = 'TL'")]
        self.assertTrue(any(f"L{lid} abgebrochen" in k for k in an_tl), an_tl)             # entfernt: der Lead erfährt es

    def test_nur_im_terminal(self):
        from amw import bruecke, cli
        with self.assertRaises(ValueError):
            bruecke.argumente({"args": ["lauf", "ausfuehren", "--beschreibung", "x", "--", "echo hi"]}, self.ordner.name, von="CC1", projekt="P")
        marke = cli.KANAL.set("bruecke")
        try:
            rc = cli.main(["lauf", "ausfuehren", "--beschreibung", "x", "--projekt", "P", "--von", "CC1", "--", "echo", "hi"])
        finally:
            cli.KANAL.reset(marke)
        self.assertEqual(rc, 1)
        self.assertEqual(self.con.execute("SELECT count(*) FROM lauf WHERE befehl IS NOT NULL").fetchone()[0], 0)

    def test_im_verlauf_steht_wer_was_wo_und_rc(self):
        from amw import verlauf
        lid, _ = self.lauf(self.py("import sys; sys.exit(5)"))
        self.dienst.runde()
        e = [x for x in verlauf.verlauf(self.con, self.pid, "2000-01-01T00:00:00Z") if f"L{lid}" in json.dumps(x, ensure_ascii=False)]
        text = json.dumps(e, ensure_ascii=False)
        self.assertIn("vom Dienst gerechnet", text)
        self.assertIn("rc 5", text)
        self.assertIn("CC1", text)
        self.assertIn(os.path.basename(self.ordner.name), text)


class Lernen(Grund):
    def fertig(self, befehl, spitze):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="CC1", beschreibung="alt", status="fertig", angemeldet_utc=db.jetzt(),
                         befehl=json.dumps(befehl), spitze_gb=spitze)

    def test_ohne_angabe_gilt_der_gemessene_bedarf(self):
        for i, s in enumerate((2.0, 3.0, 2.5, 9.0, 2.2)):
            self.fertig(["git", "subtree", "split", f"web-18{i}0"], s)
        self.fertig(["andere", "sache"], 20.0)
        lid = betrieb.lauf_start(self.con, self.pid, "CC1", "neu", warten=True, speicher_frei=32.0,
                                 befehl=["git", "subtree", "split", "web-1900"], waechter=TOT)
        self.assertEqual(self.zeile(lid)["braucht_gb"], 3.0)             # Median 2,5 × 1,2 = 3,0
        lid = betrieb.lauf_start(self.con, self.pid, "CC1", "unbekannt", warten=True, speicher_frei=32.0, befehl=["ganz", "neu"], waechter=TOT)
        self.assertIsNone(self.zeile(lid)["braucht_gb"])                 # noch nichts gemessen: die Grenze gilt

    def test_spitze_wird_gemessen(self):
        lid, _ = self.lauf(self.py("print(1)"), waechter=os.getpid())
        belegung.lauf_merken(lid, os.getpid())
        self.addCleanup(belegung.lauf_vergessen, lid)
        with mock.patch.object(belegung, "prozesse", return_value=[]), mock.patch.object(belegung, "baum_gb", side_effect=[1.5, 4.25, 2.0]):
            for _ in range(3):
                self.dienst.spitzen()
        self.assertEqual(self.zeile(lid)["spitze_gb"], 4.25)


class Wecken(Grund):
    def test_ist_dran_weckt_bei_ausfuehren_nicht(self):
        belegt = betrieb.lauf_start(self.con, self.pid, "TL", "belegt", speicher_frei=32.0, braucht_gb=1)   # CPU-Spuren voll
        belegt2 = betrieb.lauf_start(self.con, self.pid, "CC1", "auch", speicher_frei=32.0, braucht_gb=1, befehl=self.py("1"), waechter=os.getpid())
        lid, _ = self.lauf(self.py("print(1)"), waechter=os.getpid())
        self.assertEqual(self.zeile(lid)["status"], "angemeldet")
        betrieb.lauf_ende(self.con, self.pid, "TL", belegt, 0)
        betrieb.lauf_ende(self.con, self.pid, "CC1", belegt2, 0)
        self.assertEqual(self.zeile(lid)["status"], "laeuft")
        dran = [(a, k) for a, k in self.an_cc1() if f"L{lid}" in k]
        self.assertEqual(dran, [("info", f"L{lid} läuft: Probe")])        # Info, kein „jetzt starten“-Weckruf


if __name__ == "__main__":
    unittest.main()
