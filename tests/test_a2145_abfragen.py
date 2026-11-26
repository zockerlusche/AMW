"""A2145: Einzelabfragen gebündelt (N+1) – gleiche Ergebnisse, die Zahl der Abfragen hängt nicht mehr an der Zahl der Aufgaben, Pakete oder
Themen. Gezählt wird jede Anweisung an die Datenbank (set_trace_callback); verglichen wird bei 20 und bei 400 Stück, keine Zeitgrenzen."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import tempfile
import unittest

from amw import arbeitspaket, aufwand, db, eignung, einmal, kern, planer, planung, themen, zwischenpruefung


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

    def zaehlen(self, con, tun, nur=None):
        """(Ergebnis, Zahl der Anweisungen) für tun() – mit nur: nur Anweisungen, die diesen Text enthalten."""
        n = [0]
        con.set_trace_callback(lambda s: n.__setitem__(0, n[0] + (nur is None or nur in s)))
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


class ThemenEreignisse(Basis):
    """Commit 3: themen._ereignisse und planer._ereignisse lasen plan_ereignis je Thema (und Art) – LIKE '{"thema": <tid>,%'."""
    ARTEN = ("thema_vorgelegt", "thema_ja", planer.ENTWURF, planer.JA, planer.NICHTS, planer.ANGESTOSSEN, "anderes")

    def bestand(self, n):
        con, pid = self.neu(f"themen{n}")
        with db.schreiben(con):
            fremd = db.einfuegen(con, "projekt", name="Q", angelegt_utc=db.jetzt())
            for i in range(1, n + 1):
                for j, art in enumerate(self.ARTEN):
                    if (i + j) % 3:
                        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=z(i), von="TL", art=art,
                                     text=f'{{"thema": {i}, "fassung": {j}, "liste": [1, 2]}}')
                db.einfuegen(con, "plan_ereignis", projekt_id=fremd, zeit_utc=z(i), von="TL", art="thema_ja", text=f'{{"thema": {i}, "fremd": 1}}')
            for text in ('{"thema": 12}', '{"thema": 120, "x": 1}', '{"thema": 5, kaputt', '{"THEMA": 7, "gross": 1}', '{"thema": "3", "s": 1}',
                         '{"thema": 012, "null": 1}', 'kein json'):
                db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=z(1), von="TL", art="thema_ja", text=text)
                db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=z(1), von="TL", art=planer.ENTWURF, text=text)
        return con, pid

    def alle(self, con, pid, n):
        return [(themen._ereignisse(con, pid, t), [planer._ereignisse(con, pid, t, a) for a in self.ARTEN]) for t in range(1, n + 1)]

    def test_gleich_und_unabhaengig_von_der_menge(self):
        zahlen = {}
        for n in (20, 400):
            con, pid = self.bestand(n)
            ohne = self.alle(con, pid, n)
            with einmal.merken(con, schnappschuss=True):
                mit, zahlen[n] = self.zaehlen(con, lambda: self.alle(con, pid, n))
            self.assertEqual(mit, ohne)
            self.assertTrue(ohne[6][0] and ohne[6][1][2])                 # der Bestand trifft wirklich etwas (auch Thema 7, groß geschrieben)
        self.assertEqual(zahlen[20], zahlen[400], zahlen)
        self.assertLessEqual(zahlen[400], 3, zahlen)

    def test_geliefert_ist_eine_kopie(self):
        con, pid = self.bestand(20)
        with einmal.merken(con, schnappschuss=True):
            planer._ereignisse(con, pid, 8, planer.ENTWURF)[0]["liste"].append(99)
            themen._ereignisse(con, pid, 8)[0]["von"] = "verändert"
            self.assertEqual(planer._ereignisse(con, pid, 8, planer.ENTWURF)[0]["liste"], [1, 2])
            self.assertEqual(themen._ereignisse(con, pid, 8)[0]["von"], "TL")

    def test_nichts_ja_ohne_weitere_felder_mit_und_ohne_merker(self):
        """Lead #33760: tore.nichts_bestaetigen schreibt genau {"thema": N} – planer._ereignisse findet es seit A2140, mit Merker ebenso;
        themen._ereignisse sucht wie bisher nur Texte mit Komma."""
        import json
        from amw import tore
        con, pid = self.bestand(20)
        with db.schreiben(con):
            eid = db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=z(2), von="TL", art=planer.ENTWURF, text='{"thema": 8, "x": 1}')
            ja = db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=z(3), von="CC1", art=tore.NICHTS_JA, text=json.dumps({"thema": 8}))
            for text in ('{"thema": 8 }', '{"thema": 8}x', '{"Thema": 8}'):                # anderes trifft auch ohne Merker nicht
                db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=z(3), von="CC1", art=tore.NICHTS_JA, text=text)
        ohne = (planer._ereignisse(con, pid, 8, tore.NICHTS_JA), themen._ereignisse(con, pid, 8), planer.geklaert(con, pid, 8, eid))
        with einmal.merken(con, schnappschuss=True):
            mit = (planer._ereignisse(con, pid, 8, tore.NICHTS_JA), themen._ereignisse(con, pid, 8), planer.geklaert(con, pid, 8, eid))
        self.assertEqual(mit, ohne)
        self.assertEqual([x["id"] for x in ohne[0]], [ja])
        self.assertTrue(ohne[2])
        self.assertNotIn(ja, [x["id"] for x in ohne[1]])

    def test_geschriebenes_sofort_sichtbar(self):
        con, pid = self.bestand(20)
        with einmal.merken(con):
            vorher_t, vorher_p = len(themen._ereignisse(con, pid, 9)), len(planer._ereignisse(con, pid, 9, planer.JA))
            with db.schreiben(con):
                themen._ereignis(con, pid, "TL", "ja", 9, fassung=3)
                self.assertEqual(len(themen._ereignisse(con, pid, 9)), vorher_t + 1)     # in der Transaktion: einzeln gelesen
                planer._ereignis(con, pid, "TL", planer.JA, 9, eid=1)
            self.assertEqual(len(themen._ereignisse(con, pid, 9)), vorher_t + 1)
            self.assertEqual(planer._ereignisse(con, pid, 9, planer.JA)[-1]["eid"], 1)
            self.assertEqual(len(planer._ereignisse(con, pid, 9, planer.JA)), vorher_p + 1)


class Eignung(Basis):
    """Commit 4: eignung._zeilen fragte je fertiger Aufgabe nach einer roten Prüfung (123 Abfragen in AMW, in sechs Ansichten).
    messung.zeiten in derselben Schleife bleibt, wie es ist (Vorgabe des Leads)."""

    def bestand(self, n):
        con, pid = self.neu(f"eignung{n}")
        gid = kern.agent_zeile(con, pid, "CC1")["id"]
        with db.schreiben(con):
            fremd = db.einfuegen(con, "projekt", name="Q", angelegt_utc=db.jetzt())
            rot = set()
            for i in range(n):
                aid = db.einfuegen(con, "aufgabe", projekt_id=pid, titel=f"T{i}", agent="CC1", angelegt_von="TL", angelegt_utc=z(3 * i),
                                   status="fertig", beleg="abc1234", begonnen_utc=z(3 * i), fertig_utc=z(3 * i + 2),
                                   art=("text", "fehlersuche", "konzept")[i % 3], groesse=("S", "M", "L")[i % 3])
                for j, erg in enumerate(("gruen", "rot", "offen")):
                    if (i + j) % 4 == 0:
                        db.einfuegen(con, "pruefung", projekt_id=pid if i % 5 else fremd, aufgabe_id=aid, zweig="z", sha="abc", bauer="CC1",
                                     pruefer="TL", ergebnis=erg, angefragt_utc=z(3 * i))
                        if erg == "rot":
                            rot.add(aid)
            sid = db.einfuegen(con, "sitzung", agent_id=gid, gestartet_utc=z(0), modell="Opus 5.5", denkstufe="high")
            for i in range(3 * n):
                db.einfuegen(con, "verbrauch", sitzung_id=sid, agent="CC1", zeit_utc=z(i)[:-3] + "30Z", kosten_usd=0.5 * i)
        return con, pid, rot

    def test_gleich_und_unabhaengig_von_der_menge(self):
        zahlen = {}
        for n in (20, 400):
            con, pid, rot = self.bestand(n)
            zeilen, zahlen[n] = self.zaehlen(con, lambda: eignung._zeilen(con, pid), nur="ergebnis = 'rot'")
            inter = [x for x in zeilen if x["quelle"] == "interaktiv"]
            self.assertGreater(len(inter), n // 2)
            self.assertTrue(rot and any(x["aufgabe"] in rot for x in inter))
            self.assertEqual({x["aufgabe"]: x["ohne"] for x in inter}, {x["aufgabe"]: x["aufgabe"] not in rot for x in inter})
        self.assertEqual(zahlen[20], zahlen[400], zahlen)
        self.assertLessEqual(zahlen[400], 1, zahlen)


class Paketzeile(Basis):
    """Commit 5: arbeitspaket._zeile las die Paketzeile je Aufgabe (3582 Abfragen in neun Ansichten)."""

    def bestand(self, n):
        con, pid = self.neu(f"paket{n}")
        with db.schreiben(con):
            ids = [db.einfuegen(con, "aufgabe", projekt_id=pid, titel=f"T{i}", agent="CC1", angelegt_von="TL", angelegt_utc=z(i)) for i in range(n)]
            for i, aid in enumerate(ids):
                if i % 3:                        # jede dritte ohne Paketzeile (Standardwerte)
                    db.einfuegen(con, "paket", aufgabe_id=aid, art=("agent", "sitzung", "p")[i % 3], modell="opus" if i % 2 else None,
                                 ressourcen='["gpu"]' if i % 4 == 1 else None, geaendert_utc=z(i))
        return con, pid, ids

    def alle(self, con, ids):
        return [(arbeitspaket._zeile(con, a), arbeitspaket.lesen(con, a)) for a in ids + [999999]]

    def test_gleich_und_unabhaengig_von_der_menge(self):
        zahlen = {}
        for n in (20, 400):
            con, _, ids = self.bestand(n)
            ohne = self.alle(con, ids)
            with einmal.merken(con, schnappschuss=True):
                mit, zahlen[n] = self.zaehlen(con, lambda: self.alle(con, ids), nur="FROM paket")
                self.assertEqual(arbeitspaket._zeile(con, str(ids[1])), ohne[1][0])     # Nummer als Text: einzeln, wie SQLite vergleicht
            self.assertEqual(mit, ohne)
            self.assertIsNone(ohne[0][0])
        self.assertEqual(zahlen[20], zahlen[400], zahlen)
        self.assertLessEqual(zahlen[400], 1, zahlen)

    def test_kopie_und_geschriebenes_sofort_sichtbar(self):
        con, pid, ids = self.bestand(20)
        def zeile(aid):
            z = arbeitspaket._zeile(con, aid)
            assert z is not None
            return z
        with einmal.merken(con):
            zeile(ids[1])["ressourcen"].append("bildschirm")
            self.assertEqual(zeile(ids[1])["ressourcen"], ["gpu"])
            self.assertIsNone(arbeitspaket._zeile(con, ids[0]))
            arbeitspaket.setzen(con, pid, "TL", ids[0], modell="sonnet")
            self.assertEqual(zeile(ids[0])["modell"], "sonnet")
            arbeitspaket.setzen(con, pid, "TL", ids[1], modell="haiku")
            self.assertEqual(arbeitspaket.lesen(con, ids[1])["modell"], "haiku")


if __name__ == "__main__":
    unittest.main()
