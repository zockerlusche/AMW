"""A2053: Wartegrund als feste Art (TH155) – wartet_pruefung · wartet_stapel · wartet_lauf · wartet_antwort · wartet_paket, ohne
Schemaänderung als Stichwort im Bezug (Lead F5388); Prüfbitte und Ergebnis setzen und schließen „pruefung:P…“, die Auslieferung
„stapel:<zweig>“; Prüfung/Stapel/Lauf geben den Agenten frei, Antwort/Paket erst nach 10 min; „wartet“ ohne Grund mit fertigen
Vorgängern weckt den Besitzer; Leerlauf meldet dem Lead nur, wenn die AMW nicht selbst zuteilt. Je Punkt mit Gegenprobe."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import time
import unittest
from unittest import mock

from amw import betrieb, db, kern, verteilen, wartegrund
from tests.test_verteilen import Grund, utc


class Art(Grund):
    def test_bezuege_und_sorten(self):
        a = self.aufgabe("Etwas bauen")
        with db.schreiben(self.con):
            prid = db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=a, zweig="z", sha="0" * 40, bauer="CC1",
                                pruefer="TL", angefragt_utc=db.jetzt())
        lesen = lambda t, art=None: wartegrund.bezug_lesen(self.con, self.pid, t, art)   # noqa: E731
        self.assertEqual(lesen(f"P{prid}"), ("monitor", f"pruefung:P{prid}"))
        self.assertEqual(lesen(f"pruefung:P{prid}"), ("monitor", f"pruefung:P{prid}"))
        self.assertEqual(lesen("stapel:stapel41"), ("monitor", "stapel:stapel41"))
        self.assertEqual(lesen("TL", "pruefung"), ("monitor", "pruefung:TL"))           # --art schreibt das Stichwort
        self.assertEqual(lesen("TL"), ("agent", "TL"))                                   # Gegenprobe: ohne --art wie bisher
        with self.assertRaisesRegex(kern.AmwFehler, "P999 gibt es nicht"):
            lesen("P999")
        with self.assertRaisesRegex(kern.AmwFehler, "Art „bald“"):
            lesen("TL", "bald")
        s = wartegrund.sorte
        self.assertEqual([s("monitor", f"pruefung:P{prid}"), s("monitor", "stapel:x"), s("lauf", "L3"), s("aufgabe", "A4"),
                          s("agent", "TL"), s("frage", "F1"), s("monitor", "Monitor: Abnahme")],
                         ["wartet_pruefung", "wartet_stapel", "wartet_lauf", "wartet_paket", "wartet_antwort", "wartet_antwort",
                          "wartet_antwort"])
        self.assertEqual([s(None, None, t) for t in ("Prüfung P601", "Stapel 1.181.0 nach CCamw", "Gesamtlauf L3344", "Marcel")],
                         ["wartet_pruefung", "wartet_stapel", "wartet_lauf", "wartet_antwort"])   # Altdaten: grob, sonst sicher

    def test_befehl_mit_art(self):
        from amw import cli
        a = self.aufgabe("Etwas bauen")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET agent = 'CC1', status = 'laeuft' WHERE id = ?", (a,))
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_DB": self.con.execute("PRAGMA database_list").fetchone()[2], "AMW_AGENT": ""}), \
                contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["aufgabe", "wartet", str(a), "--auf", "TL", "--art", "pruefung", "--projekt", "P", "--von", "CC1"])
            rc2 = cli.main(["aufgabe", "aendern", str(a), "--art", "stapel", "--projekt", "P", "--von", "TL"])
        self.assertEqual(rc, 0, aus.getvalue())
        self.assertEqual([g["bezug"] for g in wartegrund.offene(self.con, a)], ["pruefung:TL"])
        self.assertEqual(rc2, 1)                                                          # Wartegrund-Art gehört nicht zu aendern
        self.assertIn("Wartegrund-Art", aus.getvalue())


class Pruefung(Grund):
    def test_pruefbitte_setzt_und_ergebnis_schliesst(self):
        a = self.aufgabe("Etwas bauen")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET agent = 'CC1', status = 'laeuft' WHERE id = ?", (a,))
        with mock.patch.object(betrieb, "voller_sha", lambda con, pid, sha: sha), \
                mock.patch.object(betrieb, "fremde_a_nummern", lambda *x: []), \
                mock.patch("amw.versionsnummer.pruefen", lambda *x: None), \
                mock.patch("amw.pruefstufe.stufe", lambda *x: {}), mock.patch("amw.pruefstufe.regel", lambda *x: "niedrig"), \
                mock.patch("amw.pruefstufe.zeile", lambda info: "Stufe"), mock.patch("amw.pruefstufe.bilder_pruefen", lambda *x: ""), \
                mock.patch("amw.pruefstufe.leerzeichen_warnung", lambda *x: ""), mock.patch("amw.vorpruefung.anstossen", lambda *x: None):
            prid = betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "a1", "1" * 40, "Punkte", a)
        z = self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (a,)).fetchone()[0]
        self.assertEqual((z, wartegrund.offene(self.con, a)), ("laeuft", []))          # L3357: Status bleibt – Nachbessern geht
        kern.aufgabe_status(self.con, self.pid, "CC1", a, "wartet", auf="TL")            # parkt er sie, zählt die offene Prüfung mit
        self.assertEqual(sorted(g["bezug"] for g in wartegrund.offene(self.con, a)), sorted(["TL", f"pruefung:P{prid}"]))
        wartegrund.von_hand(self.con, self.pid, "CC1", a, "TL")
        self.assertIsNone(wartegrund.haelt_fest(self.con, self.pid, "CC1"))              # Prüfung hält nicht fest
        betrieb.pruefung_ergebnis(self.con, self.pid, "TL", prid, "rot", "fehlt")
        self.assertEqual(wartegrund.offene(self.con, a), [])
        self.assertTrue(any(f"A{a}: P{prid} ROT – alle Gründe erledigt" in k for _, k, _ in self.post("CC1")), self.post("CC1"))


class Freigeben(Grund):
    def wartet(self, aid, auf, vor_min=0):
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET agent = 'CC1', status = 'wartet' WHERE id = ?", (aid,))
            wartegrund.anlegen(self.con, self.pid, "CC1", aid, auf)
            self.con.execute("UPDATE wartegrund SET angelegt_utc = ? WHERE aufgabe_id = ?", (utc(time.time() - vor_min * 60), aid))

    def frei(self):
        return [k for k, _ in verteilen.freie_agenten(self.con, self.pid)]

    def test_lauf_gibt_frei_antwort_erst_nach_10_min(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", verteilen_max_offen=3)   # hier geht es um die Warteart, nicht um die Grenze (A2174)
        mein = self.aufgabe("Mein Paket")
        with db.schreiben(self.con):
            lid = db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="CC1", beschreibung="Gesamtlauf", status="laeuft",
                               angemeldet_utc=db.jetzt())
        self.wartet(mein, f"L{lid}")
        self.assertIn("CC1", self.frei())                                                 # Lauf: sofort frei
        andere = self.aufgabe("Noch eins")
        self.wartet(andere, "TL")                                                         # Antwort, frisch
        self.assertNotIn("CC1", self.frei())                                              # Gegenprobe: hält fest
        with db.schreiben(self.con):
            self.con.execute("UPDATE wartegrund SET angelegt_utc = ? WHERE aufgabe_id = ?", (utc(time.time() - 11 * 60), andere))
        self.assertIn("CC1", self.frei())                                                 # nach 10 min frei für anderes

    def test_leerlauf_ohne_meldung_wenn_die_amw_zuteilt(self):
        self.aufgabe("Startklar", art="mechanisch")
        self.assertFalse(wartegrund._bekommt_paket(self.con, self.pid, "CC1"))           # Vorgabe vorschlag: Lead hört weiter davon
        kern.projekt_einstellen(self.con, self.pid, "TL", verteilen="an")
        self.assertTrue(wartegrund._bekommt_paket(self.con, self.pid, "CC1"))
        self.assertFalse(wartegrund._bekommt_paket(self.con, self.pid, "CC2"))           # Grafik passt nicht zu mechanisch


class Startklar(Grund):
    def test_wartet_ohne_grund_weckt_einmal(self):
        a = self.aufgabe("Projektweg-Oberfläche")
        vor = self.aufgabe("Vorgänger")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET agent = 'CC1', status = 'wartet' WHERE id = ?", (a,))
            self.con.execute("INSERT INTO abhaengigkeit (vor, nach, art) VALUES (?, ?, 'FS')", (vor, a))
        self.assertEqual(wartegrund.startklar_wecken(self.con, self.pid), [])             # Gegenprobe: Vorgänger offen
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'x' WHERE id = ?", (vor,))
        self.assertEqual(wartegrund.startklar_wecken(self.con, self.pid), [f"CC1 geweckt: A{a} startklar"])
        self.assertIn(("auftrag", f"A{a} ist startklar – weiter: amw aufgabe start {a}"), [(x, k) for x, k, _ in self.post("CC1")])
        self.assertEqual(wartegrund.startklar_wecken(self.con, self.pid), [])             # nur einmal

    def test_stapel_ausgeliefert_weckt(self):
        a = self.aufgabe("Nach dem Stapel")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET agent = 'CC1', status = 'wartet' WHERE id = ?", (a,))
            wartegrund.anlegen(self.con, self.pid, "CC1", a, "stapel:ccamw-st35")
        from amw import auslieferung
        k = auslieferung.Kette.__new__(auslieferung.Kette)
        k.con, k.pid = self.con, self.pid
        k._stapel_erledigt("anderer")                                                     # Gegenprobe: anderer Zweig
        self.assertEqual(len(wartegrund.offene(self.con, a)), 1)
        k._stapel_erledigt("ccamw-st35")
        self.assertEqual(wartegrund.offene(self.con, a), [])


if __name__ == "__main__":
    unittest.main()
