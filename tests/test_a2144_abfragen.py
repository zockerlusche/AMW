"""A2144: die Zeile „Langsame Anfrage“ nennt Zahl und Zeit der Datenbank-Abfragen und die drei teuersten – nie Werte, nie Texte; Schalter
ohne Neustart; Zusammenfassung aus dienst.log. Gezählt wird nur in einer Anfrage der Workbench."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import http.client
import io
import logging
import os
import re
import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

from amw import abgleich, anfragezeit, cli, db, einmal, einstellungen, kern, workbench
from tests.test_a2035_anfragezeit import freier_port

GEHEIM, GEHEIME_ZAHL = "Streng geheimer Satz", 987654321
ZEILE = re.compile(r"^Langsame Anfrage GET /api/kosten: \d+\.\d s \(200\) – Projekt (\d+), (\d+) Abfragen, Datenbank (\d+\.\d\d) s,"
                   r" Schreibsperre (\d+\.\d\d) s, Rest \(Rechnen\) (\d+\.\d\d) s – teuerste Abfragen: (.+)$")


class Basis(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db"), "LOCALAPPDATA": self.ordner.name})
        u.start()
        self.addCleanup(u.stop)
        einstellungen.speichern({"anfrage_zaehlen": True})
        self.con = db.anlegen()
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.fremd = db.einfuegen(self.con, "projekt", name="Q", angelegt_utc=db.jetzt())
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        with db.schreiben(self.con):
            for i in range(30):
                db.einfuegen(self.con, "wortlaut", projekt_id=self.pid, zeit_utc=db.jetzt(), text=f"{GEHEIM} {i}", kanal="seite",
                             erfasst_von="TL", erfasst_utc=db.jetzt())

    def zeile(self, tun, weg="GET /api/probe", pid=None):
        anfragezeit.start(weg)
        try:
            if pid:
                anfragezeit.projekt(pid)
            tun()
        finally:
            with self.assertLogs("amw.workbench", logging.WARNING):
                z = anfragezeit.ende(200, grenze=0)
        return z or ""


class Zaehlen(Basis):
    def lesen(self):
        con = db.verbinde(nur_lesen=True)
        try:
            for i in range(5):
                con.execute("SELECT id FROM projekt WHERE id = ?", (i,)).fetchone()
            con.execute(f"SELECT w.id FROM wortlaut w JOIN projekt p ON p.id = w.projekt_id WHERE w.text LIKE '%{GEHEIM}%' OR w.id = {GEHEIME_ZAHL}"
                        " OR w.text = ?", (GEHEIM,)).fetchall()
            return [dict(r) for r in con.execute("SELECT kennung FROM agent ORDER BY id")]
        finally:
            con.close()

    def test_zahl_tabellen_und_aufrufer_ohne_werte(self):
        z = self.zeile(self.lesen, pid=self.pid)
        self.assertIn(f"– Projekt {self.pid}, 9 Abfragen, Datenbank ", z)                 # 2 PRAGMA beim Öffnen + 5 + 1 + 1
        self.assertIn("test_a2144_abfragen.lesen", z)
        self.assertIn("wortlaut, projekt", z)
        for verboten in (GEHEIM, "geheim", str(GEHEIME_ZAHL), "LIKE", "SELECT", "%"):
            self.assertNotIn(verboten, z)

    def test_nur_die_drei_teuersten_und_zusammengefasst(self):
        def tun():
            con = db.verbinde(nur_lesen=True)
            for t in ("agent", "aufgabe", "frage", "beschluss", "bogen"):
                for i in range(4):
                    con.execute(f"SELECT count(*) FROM {t} WHERE id > {i}").fetchone()   # andere Zahl im Text: dieselbe Abfrage
            con.close()
        z = self.zeile(tun)
        self.assertEqual(len(re.findall(r"\(4×, ", z)) + z.count(" – PRAGMA") + z.count("PRAGMA"), 3, z)
        self.assertEqual(z.split("teuerste Abfragen: ")[1].split(" – ")[0].count("×"), 3)

    def test_schreibsperre_zaehlt_nicht_als_datenbank(self):
        frei = threading.Event()
        halter = sqlite3.connect(os.environ["AMW_DB"], isolation_level=None, check_same_thread=False)
        halter.execute("BEGIN IMMEDIATE")

        def loesen():
            frei.wait(5)
            time.sleep(0.6)
            halter.execute("ROLLBACK")
        f = threading.Thread(target=loesen)
        f.start()

        def tun():
            con = db.verbinde()
            frei.set()
            with db.schreiben(con):
                con.execute("UPDATE projekt SET name = name WHERE id = ?", (self.pid,))
            con.close()
        z = self.zeile(tun)
        f.join()
        halter.close()
        wert = lambda was: float(re.findall(was + r" (\S+) s", z)[0])
        sperre, bank = wert("Schreibsperre"), wert("Datenbank")
        self.assertGreaterEqual(sperre, 0.4)
        self.assertLess(bank, sperre / 2)

    def test_gleiche_ergebnisse(self):
        def alles(con):
            c = con.cursor()
            a = [tuple(r) for r in con.execute("SELECT id, text FROM wortlaut ORDER BY id")]
            erste = []
            for r in con.execute("SELECT id FROM wortlaut ORDER BY id"):                  # Durchlauf mit Abbruch
                erste.append(r["id"])
                if len(erste) == 3:
                    break
            x = con.execute("SELECT id FROM wortlaut ORDER BY id")
            teile = [x.fetchone()["id"], [r[0] for r in x.fetchmany(2)], len(x.fetchall()), x.fetchone(), next(x, None)]
            leer = con.execute("SELECT id FROM wortlaut WHERE id < 0")
            return a, erste, teile, leer.fetchone(), list(leer), [d[0] for d in x.description], isinstance(c, sqlite3.Cursor)
        ohne = alles(self.con)
        anfragezeit.start("GET /api/probe")
        try:
            con = db.verbinde()
            self.assertEqual(alles(con), ohne)
            self.assertIsInstance(con.execute("SELECT 1 AS x").fetchone(), sqlite3.Row)
            with db.schreiben(con):
                n = con.execute("UPDATE projekt SET name = name WHERE id > 0").rowcount
                con.executemany("UPDATE projekt SET name = ? WHERE id = ?", [("P2", self.pid), ("Q2", self.fremd)])
            self.assertEqual(n, 2)
            self.assertEqual([r[0] for r in con.execute("SELECT name FROM projekt ORDER BY id")], ["Q2", "P2"])
            with self.assertRaises(sqlite3.OperationalError):
                con.execute("SELECT gibtsnicht FROM projekt")
            con.close()
        finally:
            anfragezeit.ende(grenze=999)

    def test_ohne_anfrage_gewoehnlicher_cursor(self):
        self.assertIs(type(self.con.execute("SELECT 1")), sqlite3.Cursor)
        self.assertIs(type(self.con.cursor()), sqlite3.Cursor)
        einstellungen.speichern({"anfrage_zaehlen": False})
        anfragezeit.start("GET /api/probe")
        try:
            self.assertIs(type(self.con.execute("SELECT 1")), sqlite3.Cursor)
        finally:
            anfragezeit.ende(grenze=999)

    def test_anderer_faden_zaehlt_nicht_mit(self):
        """Abgleich und Dienst rechnen in eigenen Fäden: dort nie ein zählender Cursor, auch während eine Anfrage gemessen wird."""
        gesehen = []

        def faden():
            con = db.verbinde(nur_lesen=True)
            gesehen.append(type(con.execute("SELECT 1")))
            abgleich.suchindex(con, self.pid)
            con.close()
        anfragezeit.start("GET /api/probe")
        try:
            t = threading.Thread(target=faden)
            t.start()
            t.join()
            self.assertEqual(anfragezeit._lokal.m["n"], 0)
        finally:
            anfragezeit.ende(grenze=999)
        self.assertEqual(gesehen, [sqlite3.Cursor])

    def test_abgleich_und_mcp_ohne_zaehler(self):
        from amw import mcp_server
        typen = []

        class Spion(db._Verbindung):
            def execute(self, *a):
                c = super().execute(*a)
                typen.append(type(c))
                return c
        with mock.patch.object(db, "_Verbindung", Spion):
            con = db.verbinde(nur_lesen=True)
            with einmal.merken(con, schnappschuss=True):
                abgleich.suchindex(con, self.pid)
                workbench.daten_start(con, self.pid)
            con.close()
            self.assertGreater(len(typen), 50)
            self.assertEqual(set(typen), {sqlite3.Cursor})
            typen.clear()                                                                  # Gegenprobe: in einer Anfrage sieht der Spion den Zähler
            anfragezeit.start("GET /api/probe")
            try:
                con = db.verbinde(nur_lesen=True)
                con.execute("SELECT 1")
                con.close()
            finally:
                anfragezeit.ende(grenze=999)
            self.assertEqual(set(typen), {anfragezeit.Zaehler})
        with open(mcp_server.__file__, encoding="utf-8") as f:                             # der MCP-Server misst keine Anfragen
            self.assertNotIn("anfragezeit", f.read())


class Anfrage(Basis):
    def setUp(self):
        super().setUp()
        self.port = freier_port()
        self.srv = workbench.starten(self.port)
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def anfrage(self, weg):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        c.request("GET", weg)
        r = c.getresponse()
        r.read()
        c.close()
        time.sleep(0.3)                                                                   # die Zeile schreibt der Faden nach der Antwort
        return r.status

    def langsam(self, sekunden=1.2):
        echt = workbench.daten_kosten

        def langsam(con, pid):
            for _ in range(7):
                con.execute("SELECT count(*) FROM wortlaut WHERE text = ? AND id != ?", (GEHEIM, GEHEIME_ZAHL)).fetchone()
            time.sleep(sekunden)
            return echt(con, pid)
        return mock.patch.object(workbench, "daten_kosten", langsam)

    def zeilen(self, tun):
        with self.assertLogs("amw.workbench", logging.WARNING) as l:
            tun()
            logging.getLogger("amw.workbench").warning("Ende")
        return [r.getMessage() for r in l.records if r.getMessage() != "Ende"]

    def test_langsame_genau_eine_zeile_schnelle_keine(self):
        def tun():
            with self.langsam():
                self.assertEqual(self.anfrage("/api/kosten?projekt=P"), 200)
            self.assertEqual(self.anfrage("/api/pause?projekt=P"), 200)
        z = self.zeilen(tun)
        self.assertEqual(len(z), 1, z)
        self.assertRegex(z[0], ZEILE)
        pid, n, bank, _, rest, teuer = ZEILE.findall(z[0])[0]
        self.assertEqual(int(pid), self.pid)
        self.assertGreaterEqual(int(n), 9)
        self.assertGreaterEqual(float(rest), 1.0)                                          # das Schlafen ist Rest, nicht Datenbank
        self.assertLess(float(bank), 1.0)
        self.assertLessEqual(teuer.split(" – ")[0].count("×"), 3)
        for verboten in (GEHEIM, str(GEHEIME_ZAHL), "SELECT", "projekt=P"):
            self.assertNotIn(verboten, z[0])

    def test_schalter_ohne_neustart(self):
        def tun():
            with self.langsam():
                for an in (False, True, False):
                    einstellungen.speichern({"anfrage_zaehlen": an})
                    self.assertEqual(self.anfrage("/api/kosten?projekt=P"), 200)
        self.assertEqual(["Abfragen" in z for z in self.zeilen(tun)], [False, True, False])


class Zusammenfassen(Basis):
    def schreiben(self, name, *zeilen):
        with open(os.path.join(self.ordner.name, name), "w", encoding="utf-8", newline="\n") as f:
            f.write("".join(f"2026-11-25 20:0{i},000 WARNING {z}\n" for i, z in enumerate(zeilen)))

    def probe(self):
        zahl = lambda s, n, b, r: (f"Langsame Anfrage GET /api/planung: {s} s (200) – Projekt {self.pid}, {n} Abfragen, Datenbank {b} s,"
                                   f" Schreibsperre 0.00 s, Rest (Rechnen) {r} s – teuerste Abfragen: lauf 0.20 s (3×, zeitplan.x)")
        self.schreiben("dienst.log.1", zahl("9.0", 900, "5.00", "4.00"), "Langsame Anfrage GET /api/start: 1.4 s (200) – keine gemessenen Teilschritte (Rechnen in Python)")
        self.schreiben("dienst.log", zahl("2.0", 100, "1.00", "0.90"), "etwas anderes", zahl("4.0", 300, "2.00", "1.90"), zahl("3.0", 200, "1.50", "1.40"))

    def test_mediane_je_ansicht_und_projekt(self):
        self.probe()
        d = {(x["weg"], x["projekt"]): x for x in anfragezeit.zusammenfassen(self.ordner.name, 3)}
        x = d[("GET /api/planung", self.pid)]
        self.assertEqual((x["n"], x["dauer"], x["abfragen"], x["bank"], x["rest"]), (3, 3.0, 200, 1.5, 1.4))   # die drei neuesten
        y = d[("GET /api/start", None)]
        self.assertEqual((y["n"], y["dauer"], y["abfragen"]), (1, 1.4, None))                    # alte Zeile: nur die Dauer
        self.assertEqual({(x["weg"], x["projekt"]): x["n"] for x in anfragezeit.zusammenfassen(self.ordner.name, 10)}[("GET /api/planung", self.pid)], 4)

    def ruf(self, *args):
        with redirect_stdout(io.StringIO()) as aus:
            rc = cli.main([*args])
        return rc, aus.getvalue()

    def test_befehl(self):
        self.probe()
        _, t = self.ruf("messung", "--anfragen", "--von", "TL", "--projekt", "P")
        self.assertIn("/api/planung", t)
        self.assertIn(" P ", t)                                                              # der Name nur hier, am PC
        self.assertIn("ohne Zahlen", t)
        self.assertIn("Zählen: an", t)

    def test_befehl_schaltet_nur_lead_oder_mensch(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        _, t = self.ruf("messung", "--anfragen", "--zaehlen", "aus", "--von", "TL", "--projekt", "P")
        self.assertIn("Zählen: aus", t)
        self.assertFalse(einstellungen.wert("anfrage_zaehlen"))
        with mock.patch("sys.stderr", io.StringIO()):
            rc, _ = self.ruf("messung", "--anfragen", "--zaehlen", "an", "--von", "CC1", "--projekt", "P")
        self.assertTrue(rc)
        self.assertFalse(einstellungen.wert("anfrage_zaehlen"))

    def test_leeres_log(self):
        self.assertEqual(anfragezeit.zusammenfassen(self.ordner.name, 5), [])


if __name__ == "__main__":
    unittest.main()
