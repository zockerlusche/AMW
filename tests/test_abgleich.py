"""Tests für den Abgleich mit dem Online-Speicher – statt Turso eine lokale SQLite-Datei."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import sqlite3
import tempfile
import time
import unittest

from amw import abgleich, db, kern


class Abgleich(unittest.TestCase):
    def setUp(self):
        # Verzeichnis der Projekte anderer Rechner ist modulweit – ein Test davor hinterlässt sonst seine Projekte darin,
        # und die Projektliste ändert sich nach dem ersten Hochladen „von selbst“
        alt = abgleich.VERZEICHNIS["projekte"]
        abgleich.VERZEICHNIS["projekte"] = []
        self.addCleanup(abgleich.VERZEICHNIS.__setitem__, "projekte", alt)
        self.ordner = tempfile.TemporaryDirectory()
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.online = os.path.join(self.ordner.name, "online.db")
        self.ab = abgleich.Abgleich(self.con, abgleich.SqliteSpeicher(self.online), self.pid)
        self.ab.schema()
        self.uid = self.con.execute("SELECT uid FROM projekt WHERE id = ?", (self.pid,)).fetchone()[0]

    def tearDown(self):
        self.con.close()
        self.ordner.cleanup()

    def einwerfen(self, weg, daten):
        o = sqlite3.connect(self.online)
        o.execute("INSERT INTO eingang (zeit_utc, weg, daten) VALUES (?, ?, ?)", (db.jetzt(), weg, json.dumps(daten)))
        o.commit()
        o.close()

    def online_zeilen(self, sql):
        o = sqlite3.connect(self.online)
        try:
            return o.execute(sql).fetchall()
        finally:
            o.close()

    def test_hochladen_nur_bei_aenderung(self):
        n = self.ab.hochladen()
        self.assertEqual(n, len(abgleich.ansichten(self.con, self.pid)) + 1)      # + Suchindex beim ersten Mal
        self.assertEqual(self.ab.hochladen(), 0)
        s1 = abgleich.ansichten(self.con, self.pid)                  # keine Ansicht darf sich von selbst ändern
        time.sleep(1.1)
        s2 = abgleich.ansichten(self.con, self.pid)
        self.assertEqual([w for w in s1 if abgleich._pruef(s1[w]) != abgleich._pruef(s2[w])], [])
        kern.frage_neu(self.con, self.pid, "TL", "entwickler", "Neu?", [("A", "a")], "A", "weil", geprueft="keine Treffer")
        self.assertGreaterEqual(self.ab.hochladen(), 2)          # Start (Zähler) und Fragen
        fragen = json.loads(self.online_zeilen(f"SELECT inhalt FROM ansicht WHERE weg = '{self.uid}:/api/fragen'")[0][0])
        self.assertEqual(fragen[0]["kurz"], "Neu?")

    def test_messwerte_des_rechners_loesen_allein_kein_hochladen_aus(self):
        """Freier Arbeitsspeicher, freier Platz, Größe der Dauer-Belegung, „jetzt“ und die Hochrechnung des Wochenlimits
        ändern sich ständig. Sie dürfen eine Ansicht nicht „geändert“ machen – eine neue Aussage schon."""
        import collections
        import datetime
        from unittest import mock
        from amw import belegung, betrieb, platte, tokenprognose
        from tests.test_tokenprognose import plan_mit_verbrauch
        plan_mit_verbrauch(self.con, self.pid)                                   # Meilenstein, Schritte, Verbrauch: Wochenlimit mit Pause
        with db.schreiben(self.con):
            db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="CC1", beschreibung="Gesamtlauf", status="laeuft",
                         angemeldet_utc=db.jetzt(), start_utc=db.jetzt(), erwartet_min=30)
        Platz = collections.namedtuple("Platz", "total used free")
        GB, start = 2 ** 30, datetime.datetime.now(datetime.timezone.utc)

        def stand(speicher, platz_frei, ki_gb, nach_s, programme=("llama-server",)):
            jetzt = start + datetime.timedelta(seconds=nach_s)
            prozesse = [{"pid": 5 + i, "eltern": 1, "name": n, "gb": ki_gb, "seit": start - datetime.timedelta(hours=2)} for i, n in enumerate(programme)]
            lage = tokenprognose.lage(self.con, jetzt)
            echt = betrieb.tagesverlauf
            with mock.patch.object(betrieb, "speicher_frei_gb", lambda: (speicher, 32.0)), \
                    mock.patch.object(platte.shutil, "disk_usage", lambda pfad: Platz(500 * GB, 0, int(platz_frei * GB))), \
                    mock.patch.object(belegung, "prozesse", lambda: prozesse), mock.patch.object(belegung, "_gemerkt", [0.0, None, []]), \
                    mock.patch.object(tokenprognose, "lage_gemerkt", lambda con, sekunden=60: lage), \
                    mock.patch.object(tokenprognose, "einrechnen", lambda con, prog: None), \
                    mock.patch.object(betrieb, "tagesverlauf", lambda con, pid: echt(con, pid, jetzt=jetzt)):
                return abgleich.ansichten(self.con, self.pid)
        a, b = stand(14.5, 60.0, 16.4, 0), stand(9.1, 59.2, 17.0, 400)
        self.assertNotEqual(a["/api/start"]["rechner"]["frei_gb"], b["/api/start"]["rechner"]["frei_gb"])      # die Werte sind verschieden …
        self.assertNotEqual(a["/api/planung"]["rechner_heute"]["jetzt_utc"], b["/api/planung"]["rechner_heute"]["jetzt_utc"])
        self.assertNotEqual(a["/api/planung"]["token"]["leer_utc"], b["/api/planung"]["token"]["leer_utc"])
        def unterschied(x, y, weg=""):
            if isinstance(x, dict) and isinstance(y, dict):
                return [u for k in sorted(set(x) | set(y)) for u in unterschied(x.get(k), y.get(k), f"{weg}.{k}")]
            if isinstance(x, list) and isinstance(y, list) and len(x) == len(y):
                return [u for i, (p, q) in enumerate(zip(x, y)) for u in unterschied(p, q, f"{weg}[{i}]")]
            return [] if x == y else [f"{weg}: {str(x)[:60]} != {str(y)[:60]}"]
        self.assertEqual([u for w in a for u in unterschied(abgleich._ruhig(a[w]), abgleich._ruhig(b[w]), w)], [])
        self.assertEqual([w for w in a if abgleich._pruef(a[w]) != abgleich._pruef(b[w])], [])                  # … aber keine Ansicht gilt als geändert
        knapp = stand(14.5, 20.0, 16.4, 0)                                                                    # ein Laufwerk wird knapp: das ist eine neue Aussage
        self.assertEqual(sorted(w for w in a if abgleich._pruef(a[w]) != abgleich._pruef(knapp[w])), ["/api/einstellungen", "/api/start"])
        mehr = stand(14.5, 60.0, 16.4, 0, programme=("llama-server", "vmmem"))                                # ein Programm kommt dazu
        self.assertEqual(sorted(w for w in a if abgleich._pruef(a[w]) != abgleich._pruef(mehr[w])), ["/api/planung", "/api/start"])

    def test_briefkasten_wirkt_einmal_und_meldet_zurueck(self):
        fid = kern.frage_neu(self.con, self.pid, "TL", "entwickler", "Probe?", [("A", "ja"), ("B", "nein")], "A", "weil", geprueft="keine Treffer")
        self.einwerfen(f"/api/frage/{fid}/antwort", {"art": "option", "wert": "B"})
        self.einwerfen("/api/nachricht", {"an": "CC1", "art": "stopp", "kurz": "x"})
        self.einwerfen("/api/halt", {"fuer": "alle", "text": "von unterwegs"})
        self.assertEqual(self.ab.eingang(), 3)
        f = self.con.execute("SELECT status, antwort, antwort_kanal FROM frage WHERE id = ?", (fid,)).fetchone()
        self.assertEqual(tuple(f), ("beantwortet", "B", "netz"))
        self.assertTrue(kern.halt_gilt(self.con, self.pid, "CC1"))
        self.assertEqual([r[0] for r in self.online_zeilen("SELECT status FROM eingang ORDER BY id")],
                         ["erledigt", "fehler", "erledigt"])
        self.assertEqual(self.ab.eingang(), 0)

    def test_rueckmeldung_verloren_wird_nicht_doppelt_ausgefuehrt(self):
        self.einwerfen("/api/nachricht", {"an": "CC1", "art": "auftrag", "kurz": "einmal"})
        self.ab.eingang()
        o = sqlite3.connect(self.online)                     # Rückmeldung „verloren“: Zeile steht wieder auf neu
        o.execute("UPDATE eingang SET status = 'neu'")
        o.commit()
        o.close()
        self.ab.eingang()
        self.assertEqual(self.con.execute("SELECT count(*) FROM nachricht WHERE kurz = 'einmal'").fetchone()[0], 1)
        self.assertEqual(self.online_zeilen("SELECT status FROM eingang")[0][0], "erledigt")

    def test_neue_online_datenbank_mit_gleichen_nummern_wird_ausgefuehrt(self):
        self.einwerfen("/api/nachricht", {"an": "CC1", "art": "auftrag", "kurz": "erste DB"})
        self.ab.eingang()
        os.remove(self.online)                               # neue Online-Datenbank: zählt wieder ab 1
        self.ab.schema()
        self.einwerfen("/api/nachricht", {"an": "CC1", "art": "auftrag", "kurz": "zweite DB"})
        self.ab.eingang()
        kurz = [r[0] for r in self.con.execute("SELECT kurz FROM nachricht WHERE kurz LIKE '%DB' ORDER BY id")]
        self.assertEqual(kurz, ["erste DB", "zweite DB"])

    def test_suchindex_gepackt_und_vollstaendig(self):
        import base64, zlib
        kern.frage_neu(self.con, self.pid, "TL", "entwickler", "Brückenfrage?", [("A", "a")], "A", "weil", geprueft="keine Treffer")
        x = abgleich.suchindex(self.con, self.pid)
        eintraege = json.loads(zlib.decompress(base64.b64decode(x["gepackt"])))
        self.assertEqual(x["anzahl"], len(eintraege))
        self.assertIn(["frage", "F" + str(eintraege[0][1][1:]), "Brückenfrage?"], [e[:3] for e in eintraege])
        self.ab.hochladen(alle=True)
        self.assertEqual(len(self.online_zeilen(f"SELECT 1 FROM ansicht WHERE weg = '{self.uid}:/api/suchindex'")), 1)

    def test_ohne_freigabe_kein_abgleich(self):
        alt = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self.ordner.name
        try:
            os.makedirs(os.path.join(self.ordner.name, "amw"), exist_ok=True)
            with open(os.path.join(self.ordner.name, "amw", "turso.json"), "w", encoding="utf-8") as f:
                json.dump({"sqlite": self.online}, f)
            self.assertIsNone(abgleich.speicher_aus_zugang())
            self.assertIsNotNone(abgleich.speicher_aus_zugang(nur_wenn_an=False))
        finally:
            os.environ["LOCALAPPDATA"] = alt

    def test_seite_fuer_webhoster_ist_aktuell(self):
        wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(wurzel, "amw", "workbench.html"), encoding="utf-8") as a, \
                open(os.path.join(wurzel, "web", "inc", "seite.html"), encoding="utf-8") as b:
            self.assertEqual(a.read(), b.read(), "web/inc/seite.html veraltet – `amw web bauen`")
        from amw import __version__
        with open(os.path.join(wurzel, "web", "inc", "VERSION"), encoding="utf-8") as v:
            self.assertEqual(v.read().strip(), __version__, "web/inc/VERSION veraltet – `amw web bauen`")
        with open(os.path.join(wurzel, "CHANGELOG.md"), encoding="utf-8") as c:
            self.assertIn(f"## {__version__} ", c.read(), "CHANGELOG.md ohne Eintrag für die aktuelle Version")

    def test_php_legt_dieselben_tabellen_an(self):
        wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(wurzel, "web", "inc", "lib.php"), encoding="utf-8") as f:
            php = f.read()
        for s in abgleich.SCHEMA:
            self.assertIn(f'"{s}"', php, "ONLINE_SCHEMA in web/inc/lib.php weicht von abgleich.SCHEMA ab")


if __name__ == "__main__":
    unittest.main()
