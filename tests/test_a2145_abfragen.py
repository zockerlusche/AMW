"""A2145: Einzelabfragen gebündelt (N+1) – gleiche Ergebnisse, die Zahl der Abfragen hängt nicht mehr an der Zahl der Aufgaben, Pakete oder
Themen. Gezählt wird jede Anweisung an die Datenbank (set_trace_callback); verglichen wird bei 20 und bei 400 Stück, keine Zeitgrenzen."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import tempfile
import unittest

from amw import aufwand, db, kern


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


if __name__ == "__main__":
    unittest.main()
