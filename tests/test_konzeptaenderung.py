"""A2026: Konzeptänderung – wird ein freigegebenes Thema geändert oder kommt eins dazu, findet die AMW über Thema → Meilenstein
→ Paket die Betroffenen und teilt die Pakete ein: nicht begonnen (stoppen), laufend (zu Ende bauen), fertig (Nacharbeit).
Nicht betroffene Meilensteine bleiben unberührt."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import tempfile
import unittest
from unittest import mock

from amw import arbeitspaket, db, kern, konzeptaenderung, planung, themen


class Konzeptaenderung(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        u.start()
        self.addCleanup(u.stop)
        for k in ("AMW_AGENT", "AMW_PROJEKT"):
            os.environ.pop(k, None)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.th = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        self.anderes = themen.neu(self.con, self.pid, "TL", "Grafik", pfleger="CC1")
        for t, text in ((self.th, "Mit Firmen-Konto."), (self.anderes, "Pixel-Stil.")):
            themen.pflegen(self.con, self.pid, "CC1", t, text)
        with db.schreiben(self.con):                  # die Fassungen liegen vor der Freigabe
            self.con.execute("UPDATE thema_fassung SET zeit_utc = '2026-11-01T08:00:00Z'")
            self.con.execute("UPDATE plan_ereignis SET zeit_utc = '2026-11-01T08:00:00Z'")
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.th)
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.anderes)
        # Meilenstein 1: verweist auf „Anmeldung“ – je ein Paket nicht begonnen, laufend, fertig, dazu ein p-Paket
        self.m1 = planung.bogen_neu(self.con, self.pid, "TL", "Anmelden", abnahme="Vorführung")
        self.offen = self.paket(self.m1, "Abmelden", self.th)
        self.laeuft = self.paket(self.m1, "SSO bauen", self.th)
        self.fertig = self.paket(self.m1, "Login-Seite", self.th)
        self.p = planung.schritt_setzen(self.con, self.pid, "TL", titel="Tests", bogen_id=self.m1, pruefbefehl="python -m unittest")
        arbeitspaket.setzen(self.con, self.pid, "TL", self.p, art="p", modell="sonnet")
        themen.verweise_setzen(self.con, self.pid, "TL", self.p, [f"TH{self.th}"])
        self.fremd = self.paket(self.m1, "Logo", self.anderes)          # gleicher Meilenstein, anderes Thema
        kern.aufgabe_status(self.con, self.pid, "CC1", self.laeuft, "laeuft")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc123', begonnen_utc = '2026-11-02T08:00:00Z' WHERE id = ?", (self.fertig,))
        # Meilenstein 2: nur das andere Thema – darf nie betroffen sein
        self.m2 = planung.bogen_neu(self.con, self.pid, "TL", "Grafik", abnahme="Bilder")
        self.m2_paket = self.paket(self.m2, "Figuren", self.anderes)
        # Meilenstein 3: verworfen, verweist trotzdem auf „Anmeldung“
        self.m3 = planung.bogen_neu(self.con, self.pid, "TL", "Alt", abnahme="–")
        self.m3_paket = self.paket(self.m3, "Altes Login", self.th)
        with db.schreiben(self.con):
            self.con.execute("UPDATE bogen SET status = 'verworfen' WHERE id = ?", (self.m3,))

    def paket(self, bid, titel, tid):
        aid = planung.schritt_setzen(self.con, self.pid, "TL", titel=titel, bogen_id=bid, agent="CC1")
        themen.verweise_setzen(self.con, self.pid, "TL", aid, [f"TH{tid}"])
        return aid

    def stand(self):
        return [tuple(r) for r in self.con.execute("SELECT id, status, wartet_auf, bogen_id FROM aufgabe ORDER BY id")] + \
               [tuple(r) for r in self.con.execute("SELECT id, status FROM bogen ORDER BY id")] + \
               [(a, arbeitspaket.lesen(self.con, a)["zustand"]) for a in (self.p,)]

    def test_geaendertes_thema_findet_meilenstein_und_teilt_ein(self):
        themen.pflegen(self.con, self.pid, "CC1", self.th, "Mit Firmen-Konto und Passkey.")
        aus = konzeptaenderung.aenderung(self.con, self.pid, self.th)
        self.assertEqual(aus["art"], "geaendert")
        self.assertEqual([x["bogen"]["id"] for x in aus["meilensteine"]], [self.m1])
        m = aus["meilensteine"][0]
        self.assertEqual(sorted(m["stoppen"]), sorted([self.offen, self.p]))
        self.assertEqual(m["zu_ende"], [self.laeuft])
        self.assertEqual(m["nacharbeit"], [self.fertig])
        self.assertEqual(m["themen"], [self.th])
        self.assertNotIn(self.fremd, aus["pakete"])                      # Paket mit anderem Thema im selben Meilenstein
        self.assertEqual(aus["pakete"][self.fertig], "nacharbeit")

    def test_nicht_betroffene_meilensteine_bleiben_unberuehrt(self):
        vorher = self.stand()
        themen.pflegen(self.con, self.pid, "CC1", self.th, "Neu.")
        nach_pflege = self.stand()
        aus = konzeptaenderung.aenderung(self.con, self.pid, self.th)
        ids = [x["bogen"]["id"] for x in aus["meilensteine"]]
        self.assertNotIn(self.m2, ids)
        self.assertNotIn(self.m3, ids)                                   # verworfene zählen nicht
        self.assertIn(self.m2, aus["unberuehrt"])
        self.assertNotIn(self.m2_paket, aus["pakete"])
        self.assertNotIn(self.m3_paket, aus["pakete"])
        self.assertEqual(self.stand(), nach_pflege)                      # nur lesen – nichts gesetzt, nichts angehalten
        self.assertEqual([r for r in vorher if r[0] in (self.m2, self.m2_paket)],
                         [r for r in self.stand() if r[0] in (self.m2, self.m2_paket)])

    def test_neues_thema_kommt_dazu(self):
        neu = themen.neu(self.con, self.pid, "TL", "Passkey", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", neu, "Passkey statt Passwort.")
        self.assertIsNone(konzeptaenderung.art(self.con, self.pid, neu))   # noch nicht freigegeben: keine Konzeptänderung
        themen.verweise_setzen(self.con, self.pid, "TL", self.offen, [f"TH{neu}"])
        self.assertEqual(konzeptaenderung.aenderung(self.con, self.pid, neu)["meilensteine"], [])
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, neu)
        aus = konzeptaenderung.aenderung(self.con, self.pid, f"TH{neu}")
        self.assertEqual(aus["art"], "neu")
        self.assertEqual([(x["bogen"]["id"], x["stoppen"], x["zu_ende"], x["nacharbeit"]) for x in aus["meilensteine"]],
                         [(self.m1, [self.offen], [], [])])
        self.assertEqual(set(aus["unberuehrt"]), {self.m2})

    def test_mehrere_themen_und_fertiger_meilenstein(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE bogen SET status = 'fertig' WHERE id = ?", (self.m2,))
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc123' WHERE id = ?", (self.m2_paket,))
        aus = konzeptaenderung.betroffene(self.con, self.pid, [self.th, "Grafik"])
        self.assertEqual([x["bogen"]["id"] for x in aus["meilensteine"]], [self.m1, self.m2])
        self.assertEqual(aus["meilensteine"][0]["themen"], sorted([self.th, self.anderes]))
        self.assertEqual(aus["meilensteine"][1]["nacharbeit"], [self.m2_paket])   # fertig gebaut → Nacharbeit
        self.assertEqual(aus["pakete"][self.fremd], "stoppen")
        self.assertEqual(aus["unberuehrt"], [])

    def test_p_paket_nach_zustand(self):
        a = self.con.execute("SELECT * FROM aufgabe WHERE id = ?", (self.p,)).fetchone()
        self.assertEqual(konzeptaenderung.einteilen(self.con, a), "stoppen")
        for z, g in (("laeuft", "zu_ende"), ("gemergt", "nacharbeit"), ("zurueckgestellt", "stoppen")):
            with mock.patch.object(arbeitspaket, "lesen", return_value={"art": "p", "zustand": z}):
                self.assertEqual(konzeptaenderung.einteilen(self.con, a), g, z)

    def test_verweis_geloest_zaehlt_nicht(self):
        themen.verweise_setzen(self.con, self.pid, "TL", self.offen, [f"TH{self.th}"], entfernen=True)
        aus = konzeptaenderung.betroffene(self.con, self.pid, self.th)
        self.assertNotIn(self.offen, aus["pakete"])

    def test_zeilen(self):
        themen.pflegen(self.con, self.pid, "CC1", self.th, "Neu.")
        z = "\n".join(konzeptaenderung.zeilen(konzeptaenderung.aenderung(self.con, self.pid, self.th)))
        self.assertIn("freigegebenes Thema geändert", z)
        self.assertIn(f"nicht begonnen – stoppen: A{min(self.offen, self.p)}", z)
        self.assertIn(f"laufend – zu Ende bauen: A{self.laeuft}", z)
        self.assertIn(f"fertig – Nacharbeit nötig: A{self.fertig}", z)
        self.assertIn("Unberührt: 1 Meilenstein(e).", z)
        self.assertEqual(konzeptaenderung.zeilen({"meilensteine": []}), ["Keine Meilensteine betroffen."])


if __name__ == "__main__":
    unittest.main()
