"""A2081: je Anfrage, Dienst-Runde und Synchronisierung wird dasselbe nur einmal gerechnet (amw/einmal.py) – gültig nur, solange sich
die Datenbank nicht ändert, nie nach Zeit. Vorher rechnete /api/planung die Kosten 217-mal (9 s) und eine Runde der Synchronisierung
67 s. Die Antworten bleiben gleich; Zähltests scheitern auf 1.187.0/1.188.0."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import sqlite3
import tempfile
import unittest
import urllib.request
from unittest import mock

from amw import abgleich, aufwand, db, einmal, empfehlung, kern, planung, projektweg_seite, reihenfolge, themen, workbench
from tests.rundgang import freier_port


def z(stunde, minute=0):
    return f"2026-11-12T{stunde:02d}:{minute:02d}:00Z"


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad})
        u.start()
        self.addCleanup(u.stop)
        alt = abgleich.VERZEICHNIS["projekte"]
        abgleich.VERZEICHNIS["projekte"] = []
        self.addCleanup(abgleich.VERZEICHNIS.__setitem__, "projekte", alt)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid, "CC2")

    def bestand(self):
        """Zwei Agenten mit je sechs fertigen und zwei offenen Aufgaben in einem Meilenstein, Themen-Verweise, Kosten der Sitzungen."""
        self.t = [themen.neu(self.con, self.pid, "TL", n, pfleger="CC1") for n in ("Anmeldung", "Sicherung", "Anzeige")]
        self.m = planung.bogen_neu(self.con, self.pid, "TL", "Bauen", ziel=f"TH{self.t[0]}")
        planung.bogen_status(self.con, self.pid, "TL", self.m, "aktiv")
        self.ids = []
        for k in ("CC1", "CC2"):
            for i in range(8):
                fertig = i < 6
                with db.schreiben(self.con):
                    aid = db.einfuegen(self.con, "aufgabe", projekt_id=self.pid, titel=f"{k} {i}", agent=k, angelegt_von="TL", angelegt_utc=z(8 + i),
                                       status="fertig" if fertig else "wartet", begonnen_utc=z(8 + i), fertig_utc=z(8 + i, 50) if fertig else None,
                                       groesse="S", art="mechanisch", bogen_id=self.m, beleg="abc1234" if fertig else None)
                themen.verweise_setzen(self.con, self.pid, "TL", aid, [self.t[i % 3]])
                self.ids.append(aid)
            gid = kern.agent_zeile(self.con, self.pid, k)["id"]
            with db.schreiben(self.con):
                for s in range(2):
                    sid = db.einfuegen(self.con, "sitzung", agent_id=gid, gestartet_utc=z(8), modell="Opus 5.5", denkstufe="high")
                    for i in range(16):
                        db.einfuegen(self.con, "verbrauch", sitzung_id=sid, agent=k, zeit_utc=z(8 + i // 2, 5 + 30 * (i % 2) + s), kosten_usd=1.0 + i * 0.7)

    def zaehlen(self, modul, name):
        rufe, echt = [], getattr(modul, name)
        p = mock.patch.object(modul, name, lambda *a, **k: rufe.append(a) or echt(*a, **k))
        p.start()
        self.addCleanup(p.stop)
        return rufe


class Merker(Grund):
    def test_nur_im_block_und_nur_einmal(self):
        n = []
        for _ in range(3):
            einmal.einmal(self.con, "k", lambda: n.append(1) or 7)
        self.assertEqual(len(n), 3)                         # außerhalb: wie bisher
        with einmal.merken(self.con):
            self.assertEqual([einmal.einmal(self.con, "k", lambda: n.append(1) or 7) for _ in range(3)], [7, 7, 7])
        self.assertEqual(len(n), 4)
        self.assertIsNone(self.con.merker)

    def test_aenderung_wird_sofort_sichtbar_eigene_und_fremde(self):
        zahl = lambda: einmal.einmal(self.con, "n", lambda: self.con.execute("SELECT count(*) FROM thema").fetchone()[0])   # noqa: E731
        zweite = db.verbinde(self.pfad)
        self.addCleanup(zweite.close)
        with einmal.merken(self.con):
            self.assertEqual(zahl(), 0)
            themen.neu(self.con, self.pid, "TL", "Eins", pfleger="CC1")
            self.assertEqual(zahl(), 1)
            themen.neu(zweite, self.pid, "TL", "Zwei", pfleger="CC1")
            self.assertEqual(zahl(), 2)

    def test_schreib_transaktion_und_rollback(self):
        zahl = lambda: einmal.einmal(self.con, "n", lambda: self.con.execute("SELECT count(*) FROM thema").fetchone()[0])   # noqa: E731
        with einmal.merken(self.con):
            zahl()
            with self.assertRaises(RuntimeError), db.schreiben(self.con):
                self.con.execute("INSERT INTO thema (projekt_id, name) SELECT projekt_id, 'x' FROM thema WHERE 0")
                db.einfuegen(self.con, "projekt", name="Weg", angelegt_utc=db.jetzt())
                self.assertEqual(einmal.einmal(self.con, "p", lambda: self.con.execute("SELECT count(*) FROM projekt").fetchone()[0]), 2)
                raise RuntimeError
            self.assertEqual(einmal.einmal(self.con, "p", lambda: self.con.execute("SELECT count(*) FROM projekt").fetchone()[0]), 1)

    def test_aenderung_waehrend_der_rechnung_wird_nicht_gemerkt(self):
        zweite = db.verbinde(self.pfad)
        self.addCleanup(zweite.close)
        n = []

        def rechnen():
            n.append(1)
            if len(n) == 1:
                themen.neu(zweite, self.pid, "TL", "Währenddessen", pfleger="CC1")
            return len(n)
        with einmal.merken(self.con):
            self.assertEqual([einmal.einmal(self.con, "k", rechnen) for _ in range(3)], [1, 2, 2])

    def test_kopie_und_fehler(self):
        with einmal.merken(self.con):
            einmal.einmal(self.con, "d", lambda: {"a": 1}, kopie=True)["a"] = 9
            self.assertEqual(einmal.einmal(self.con, "d", lambda: {}, kopie=True), {"a": 1})
            einmal.einmal(self.con, "l", lambda: [{"a": 1}], kopie=True)[0]["a"] = 9
            self.assertEqual(einmal.einmal(self.con, "l", lambda: [], kopie=True), [{"a": 1}])
            with self.assertRaises(ValueError):
                einmal.einmal(self.con, "f", lambda: int("x"))
            self.assertEqual(einmal.einmal(self.con, "f", lambda: 5), 5)

    def test_schnappschuss_fester_stand_danach_der_neue(self):
        zweite = db.verbinde(self.pfad)
        self.addCleanup(zweite.close)
        zahl = lambda: einmal.einmal(self.con, "n", lambda: self.con.execute("SELECT count(*) FROM thema").fetchone()[0])   # noqa: E731
        self.assertEqual(self.con.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        with einmal.merken(self.con, schnappschuss=True):
            self.assertEqual(zahl(), 0)
            themen.neu(zweite, self.pid, "TL", "Eins", pfleger="CC1")           # Schreiben der anderen geht weiter
            self.assertEqual(zahl(), 0)
        self.assertFalse(self.con.in_transaction)
        with einmal.merken(self.con, schnappschuss=True):
            self.assertEqual(zahl(), 1)

    def test_schnappschuss_endet_auch_bei_einem_fehler(self):
        with self.assertRaises(KeyError), einmal.merken(self.con, schnappschuss=True):
            raise KeyError
        self.assertEqual((self.con.in_transaction, self.con.merker, self.con.schnappschuss), (False, None, False))
        themen.neu(self.con, self.pid, "TL", "Danach", pfleger="CC1")            # schreiben geht wieder


class GleicheAntwort(Grund):
    def setUp(self):
        super().setUp()
        self.bestand()

    def test_seiten_mit_und_ohne_merker_gleich(self):
        # time-abhängige Felder: beide Male dieselbe angehaltene Uhr
        for name, f in (("planung", lambda: workbench.daten_planung(self.con, self.pid)), ("projektweg", lambda: projektweg_seite.daten(self.con, self.pid)),
                        ("start", lambda: workbench.daten_start(self.con, self.pid))):
            with self.subTest(name), mock.patch("time.time", lambda: 1795900000.0), mock.patch.object(db, "jetzt", lambda: "2026-11-24T22:00:00Z"), \
                    mock.patch("amw.betrieb.speicher_frei_gb", lambda *a: (32.0, None)):
                ohne = json.dumps(f(), sort_keys=True, default=str)
                with einmal.merken(self.con, schnappschuss=True):
                    mit = json.dumps(f(), sort_keys=True, default=str)
                self.assertEqual(ohne, mit)

    def test_kosten_je_aufgabe_gleich(self):
        ohne = [aufwand.je_aufgabe(self.con, self.pid, a) for a in self.ids]
        self.assertTrue(any(x and x["usd"] > 0 for x in ohne))
        with einmal.merken(self.con):
            self.assertEqual([aufwand.je_aufgabe(self.con, self.pid, a) for a in self.ids], ohne)

    def test_verweise_gleich(self):
        themen.verweise_setzen(self.con, self.pid, "TL", self.ids[0], [self.t[0]], entfernen=True)
        ohne = [themen.verweise(self.con, self.pid, a) for a in self.ids]
        with einmal.merken(self.con):
            self.assertEqual([themen.verweise(self.con, self.pid, a) for a in self.ids], ohne)


class Zaehlen(Grund):
    """Einmal je Anfrage bzw. Runde – Gegenprobe: auf 1.188.0 viele Male."""

    def setUp(self):
        super().setUp()
        self.bestand()

    def pruefen(self, zuordnen, status, reihe):
        self.assertLessEqual(len(zuordnen), 3, "Kosten je Agent mehr als einmal")        # zwei Agenten (und der Lead)
        je = {}
        for a in status:
            je[a[1]["id"]] = je.get(a[1]["id"], 0) + 1
        self.assertTrue(all(n == 1 for n in je.values()), je)
        self.assertLessEqual(len(reihe), 1)

    def test_anfrage_ueber_den_server(self):
        zuordnen, status, reihe = self.zaehlen(aufwand, "_zuordnen"), self.zaehlen(themen, "_status"), self.zaehlen(reihenfolge, "_berechnen")
        port = freier_port()
        srv = workbench.starten(port)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        for weg in ("/api/planung", "/api/projektweg", "/api/start"):
            for x in (zuordnen, status, reihe):
                x.clear()
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{weg}", timeout=30) as r:
                self.assertEqual(r.status, 200)
            with self.subTest(weg):
                self.pruefen(zuordnen, status, reihe)

    def test_synchronisierung_je_projekt(self):
        ab = abgleich.Abgleich(self.con, abgleich.SqliteSpeicher(os.path.join(self.ordner.name, "online.db")), self.pid)
        ab.schema()
        zuordnen, status, reihe, zellen = (self.zaehlen(m, n) for m, n in ((aufwand, "_zuordnen"), (themen, "_status"), (reihenfolge, "_berechnen"),
                                                                          (empfehlung, "_zellen")))
        with mock.patch.object(abgleich, "log") as log:
            ab.hochladen(alle=True)
        self.pruefen(zuordnen, status, reihe)
        self.assertEqual(len(zellen), 1)
        self.assertEqual([c for c in log.warning.call_args_list if "transaction" in str(c)], [])          # keine Ansicht schreibt
        self.assertFalse(self.con.in_transaction)
        o = sqlite3.connect(os.path.join(self.ordner.name, "online.db"))
        self.addCleanup(o.close)
        hoch = {w.split(":", 1)[1] for (w,) in o.execute("SELECT weg FROM ansicht WHERE weg LIKE '%:%'")}
        self.assertTrue({"/api/planung", "/api/projektweg", f"/api/aufgabe?id={self.ids[-1]}"} <= hoch, sorted(hoch)[:20])

    def test_synchronisierung_alle_ansichten_ohne_fehler(self):
        fehler = []
        with einmal.merken(self.con, schnappschuss=True):
            a = abgleich.ansichten(self.con, self.pid, None, fehler)
        self.assertEqual(fehler, [])
        self.assertIn("/api/planung", a)

    def test_dienst_runde_merkt(self):
        """Die Aufsicht des Dienstes läuft im Merker."""
        from amw import dienst
        with open(dienst.__file__, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("with einmal.merken(con):", text)
        self.assertNotIn("merken(con, schnappschuss=True)", text)                 # die Runde schreibt: kein fester Stand


if __name__ == "__main__":
    unittest.main()
