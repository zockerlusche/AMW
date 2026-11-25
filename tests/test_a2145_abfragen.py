"""A2145: Einzelabfragen gebündelt (N+1) – gleiche Ergebnisse, die Zahl der Abfragen hängt nicht mehr an der Zahl der Aufgaben, Pakete oder
Themen. Gezählt wird jede Anweisung an die Datenbank (set_trace_callback); verglichen wird bei 20 und bei 400 Stück, keine Zeitgrenzen."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import tempfile
import unittest

from amw import aufwand, db, einmal, kern, planung, zwischenpruefung


def z(i):
    """Zeitpunkt i Minuten nach dem 12.11. 00:00 (UTC)."""
    return f"2026-11-12T{i // 60:02d}:{i % 60:02d}:00Z"


class Basis(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)

    def neu(self, name):
        con = db.anlegen(os.path.join(self.ordner.name, f"{name}.db"))
        self.addCleanup(con.close)
        with db.schreiben(con):
            pid = db.einfuegen(con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(con, pid, "TL", rolle="lead")
        kern.agent_neu(con, pid, "CC1")
        return con, pid

    def zaehlen(self, con, tun):
        """(Ergebnis, Zahl der Anweisungen) für tun()."""
        n = [0]
        con.set_trace_callback(lambda _s: n.__setitem__(0, n[0] + 1))
        try:
            return tun(), n[0]
        finally:
            con.set_trace_callback(None)


class Aufwand(Basis):
    """Commit 1: aufwand._zuordnen las die Wartegründe je Aufgabe einzeln (LayerIT: 951 Abfragen je Aufruf)."""

    def bestand(self, n):
        con, pid = self.neu(f"aufwand{n}")
        gid = kern.agent_zeile(con, pid, "CC1")["id"]
        with db.schreiben(con):
            ids = []
            for i in range(n):                 # je Aufgabe 3 Minuten, jede dritte wartet eine Minute, jede fünfte bleibt offen
                ids.append(db.einfuegen(con, "aufgabe", projekt_id=pid, titel=f"T{i}", agent="CC1", angelegt_von="TL", angelegt_utc=z(3 * i),
                                        status="laeuft" if i % 5 == 0 else "fertig", begonnen_utc=z(3 * i),
                                        fertig_utc=None if i % 5 == 0 else z(3 * i + 2)))
                if i % 3 == 0:
                    db.einfuegen(con, "wartegrund", projekt_id=pid, aufgabe_id=ids[-1], art="agent", bezug="TL", angelegt_utc=z(3 * i),
                                 angelegt_von="TL", erledigt_utc=z(3 * i + 1))
            sid = db.einfuegen(con, "sitzung", agent_id=gid, gestartet_utc=z(0), modell="Opus 5.5", denkstufe="high")
            for i in range(3 * n):
                db.einfuegen(con, "verbrauch", sitzung_id=sid, agent="CC1", zeit_utc=z(i)[:-3] + "30Z", kosten_usd=0.5 * i)
        return con, pid, ids

    def test_zahl_unabhaengig_von_der_menge(self):
        zahlen = {}
        for n in (20, 400):
            con, pid, _ = self.bestand(n)
            _, zahlen[n] = self.zaehlen(con, lambda: aufwand.je_agent(con, pid, "CC1"))
        self.assertEqual(zahlen[20], zahlen[400], zahlen)
        self.assertLessEqual(zahlen[400], 10, zahlen)

    def test_wartende_aufgabe_hat_nachrang(self):
        """Die gebündelte Abfrage ordnet wie vorher: während A wartet, geht der Zuwachs an die ältere B, danach wieder an A."""
        con, pid = self.neu("nachrang")
        gid = kern.agent_zeile(con, pid, "CC1")["id"]
        with db.schreiben(con):
            b = db.einfuegen(con, "aufgabe", projekt_id=pid, titel="B", agent="CC1", angelegt_von="TL", angelegt_utc=z(0), status="fertig",
                             begonnen_utc=z(0), fertig_utc=z(100))
            a = db.einfuegen(con, "aufgabe", projekt_id=pid, titel="A", agent="CC1", angelegt_von="TL", angelegt_utc=z(10), status="fertig",
                             begonnen_utc=z(10), fertig_utc=z(100))
            andere = db.einfuegen(con, "aufgabe", projekt_id=pid, titel="ohne Grund", agent="CC1", angelegt_von="TL", angelegt_utc=z(200),
                                  status="laeuft", begonnen_utc=z(200))
            db.einfuegen(con, "wartegrund", projekt_id=pid, aufgabe_id=a, art="agent", bezug="TL", angelegt_utc=z(20), angelegt_von="TL",
                         erledigt_utc=z(40))
            db.einfuegen(con, "wartegrund", projekt_id=pid, aufgabe_id=a, art="lauf", bezug="L1", angelegt_utc=z(60), angelegt_von="TL")
            sid = db.einfuegen(con, "sitzung", agent_id=gid, gestartet_utc=z(0), modell="Opus 5.5", denkstufe="high")
            for zeit, usd in ((5, 0.0), (15, 1.0), (30, 3.0), (50, 7.0), (70, 15.0), (210, 16.0)):
                db.einfuegen(con, "verbrauch", sitzung_id=sid, agent="CC1", zeit_utc=z(zeit), kosten_usd=usd)
        w = aufwand._zuordnen(con, pid, "CC1", aufwand._aufgaben(con, pid, "CC1"), "")
        self.assertEqual(round(w[a]["usd"], 2), 5.0)             # 15 → A (1), 50 → A (4); 30 und 70: A wartet → B
        self.assertEqual(round(w[b]["usd"], 2), 10.0)            # 30 → B (2), 70 → B (8)
        self.assertEqual(round(w[andere]["usd"], 2), 1.0)
        self.assertTrue(w[a]["naeherung"])                     # bei 15 und 50 waren A und B beide aktiv


class Vorgaenger(Basis):
    """Commit 2: planung.vorgaenger und offene_vorgaenger fragten je Paket (bis 1239 Abfragen in der Planung)."""

    def bestand(self, n):
        con, pid = self.neu(f"vorg{n}")
        with db.schreiben(con):
            ids = [db.einfuegen(con, "aufgabe", projekt_id=pid, titel=f"T{i}", agent="CC1", angelegt_von="TL", angelegt_utc=z(i),
                                status=("fertig", "verworfen", "wartet", "laeuft")[i % 4]) for i in range(n)]
            for i in range(n - 1, 1, -1):     # absichtlich nicht nach vor sortiert angelegt; SS und FF mischen
                con.execute("INSERT INTO abhaengigkeit (vor, nach, art) VALUES (?, ?, ?)", (ids[i - 1], ids[i], ("FS", "SS", "FS", "FF")[i % 4]))
                con.execute("INSERT INTO abhaengigkeit (vor, nach, art) VALUES (?, ?, 'FS')", (ids[i - 2], ids[i]))
                if i % 7 == 0:
                    con.execute("INSERT INTO abhaengigkeit (vor, nach, art) VALUES (?, ?, 'FS')", (ids[0], ids[i]))
        return con, pid, ids

    def alle(self, con, ids):
        return [(planung.vorgaenger(con, a), planung.offene_vorgaenger(con, a)) for a in ids]

    def test_gleich_und_unabhaengig_von_der_menge(self):
        zahlen = {}
        for n in (20, 400):
            con, _, ids = self.bestand(n)
            ohne = self.alle(con, ids)                               # ohne Merker: einzeln wie bisher
            with einmal.merken(con, schnappschuss=True):             # wie eine Anfrage der Seite
                mit, zahlen[n] = self.zaehlen(con, lambda: self.alle(con, ids))
            self.assertEqual(mit, ohne)
            self.assertTrue(any(len(o) > 1 for _, o in ohne))        # der Bestand prüft auch die Reihenfolge
        self.assertEqual(zahlen[20], zahlen[400], zahlen)
        self.assertLessEqual(zahlen[400], 3, zahlen)

    def test_geschriebenes_sofort_sichtbar(self):
        """Vorgabe des Leads: abhaengigkeit_setzen und die Kanten eines Prüfpunkts sind in derselben Anfrage/Runde sofort gelesen."""
        con, pid, ids = self.bestand(20)
        a, b, c = ids[3], ids[17], ids[18]                     # ids[3] läuft, ids[17] ist verworfen
        with einmal.merken(con):                               # Runde: kein fester Stand
            vorher = planung.vorgaenger(con, c)
            self.assertNotIn(a, vorher)
            planung.abhaengigkeit_setzen(con, pid, "TL", c, [a])
            self.assertEqual(planung.vorgaenger(con, c), sorted(vorher + [a]))
            self.assertIn(a, planung.offene_vorgaenger(con, c))
            planung.abhaengigkeit_setzen(con, pid, "TL", c, [a], entfernen=True)
            self.assertEqual(planung.vorgaenger(con, c), vorher)
            with db.schreiben(con):                            # Prüfpunkt-Kanten: in der Transaktion des Aufrufers
                self.assertEqual(zwischenpruefung._kanten_setzen(con, [(a, b)]), [(a, b)])
                self.assertIn(a, planung.vorgaenger(con, b))   # in der Schreib-Transaktion: einzeln gelesen, schon sichtbar
            self.assertIn(a, planung.vorgaenger(con, b))
            self.assertIn(a, planung.offene_vorgaenger(con, b))
            with db.schreiben(con):
                con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc1234' WHERE id = ?", (a,))
            self.assertNotIn(a, planung.offene_vorgaenger(con, b))   # Status des Vorgängers geändert: neu gelesen


if __name__ == "__main__":
    unittest.main()
