"""A2148 (TH157): Nachfolger eines Pakets im Bündel sind startklar. Ein Vorgänger mit Prüfbitte auf einem Bündel-/Stapelzweig (nicht rot)
zählt für Verteilen, „nächster Schritt“ und den Start als erfüllt; der Auftrag nennt den Zweig und „nach dem Live-Gang auf main umsetzen“.
Wird die Prüfbitte oder das Bündel rot, hält die AMW den Nachfolger an und sagt es dem Bauer; ein neuer Stand hebt den Halt auf."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import glob
import json
import os
import shutil
import tempfile
import unittest

from amw import buendel_nachfolger as bn
from amw import db, kern, planung, verteilen
from amw import wartegrund
from tests.test_verteilen import Grund, utc


class Basis(Grund):
    def setUp(self):
        super().setUp()
        self.vor = self.aufgabe("Navigation Teil 1", rang=10)
        self.anderes = self.aufgabe("Bündel-Nachbar", rang=11)
        self.nach = self.aufgabe("Navigation Teil 2", rang=20)
        planung.abhaengigkeit_setzen(self.con, self.pid, "TL", self.nach, [self.vor])
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET agent = 'CC2', status = 'wartet' WHERE id IN (?, ?)", (self.vor, self.anderes))

    def bitte(self, aid, zweig, sha, ergebnis="offen"):
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=aid, zweig=zweig, sha=sha, bauer="CC2", pruefer="TL",
                                ergebnis=ergebnis, angefragt_utc=db.jetzt(), ergebnis_utc=db.jetzt() if ergebnis != "offen" else None)

    def stapel(self, zweig="cc-st62", sha="351eee6aa"):
        """Ein von Hand gestapeltes Bündel: Prüfbitten zu zwei Aufgaben auf demselben Zweig."""
        p = self.bitte(self.vor, zweig, sha)
        self.bitte(self.anderes, zweig, sha)
        return p

    def rot(self, pid_, minuten_her=30):
        with db.schreiben(self.con):
            self.con.execute("UPDATE pruefung SET ergebnis = 'rot', ergebnis_utc = ? WHERE id = ?", (utc(self.jetzt - minuten_her * 60), pid_))

    def kandidaten(self):
        return [a["id"] for a, _ in verteilen.kandidaten(self.con, self.pid)]

    def zuteilen(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", verteilen="an")
        return verteilen.verteilen(self.con, self.pid)

    def halt(self):
        return [(g["bezug"], g["angelegt_von"]) for g in self.con.execute(
            "SELECT * FROM wartegrund WHERE aufgabe_id = ? AND erledigt_utc IS NULL", (self.nach,))]

    def status(self, aid):
        return self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (aid,)).fetchone()[0]


class ImBuendel(Basis):
    def test_ohne_pruefbitte_wartet_der_nachfolger(self):
        self.assertNotIn(self.nach, self.kandidaten())
        self.assertEqual(bn.offen(self.con, self.nach), [self.vor])

    def test_pruefbitte_auf_dem_eigenen_zweig_reicht_nicht(self):
        self.bitte(self.vor, "cc-a2018", "abc1234")                       # nur ein Paket auf dem Zweig: kein Bündel
        self.assertNotIn(self.nach, self.kandidaten())

    def test_stapelzweig_mit_zwei_paketen_zaehlt(self):
        p = self.stapel()
        self.assertIn(self.nach, self.kandidaten())
        self.assertEqual(bn.basis(self.con, self.nach), [{"vor": self.vor, "pruefung": p, "zweig": "cc-st62", "sha": "351eee6aa"}])
        self.assertEqual(planung.offene_vorgaenger(self.con, self.nach), [self.vor])   # für Anzeige und Plan bleibt er offen

    def test_buendelzweig_der_amw_zaehlt_auch_mit_einem_paket(self):
        self.bitte(self.vor, "buendel-1.198.0", "fff0001")
        self.assertIn(self.nach, self.kandidaten())

    def test_wartet_jemand_auf_den_stapel_zaehlt_der_zweig(self):
        self.bitte(self.vor, "cc-st70", "aaa0001")
        with db.schreiben(self.con):
            db.einfuegen(self.con, "wartegrund", projekt_id=self.pid, aufgabe_id=self.anderes, art="monitor", bezug="stapel:cc-st70",
                         angelegt_utc=db.jetzt(), angelegt_von="CC2")
        self.assertIn(self.nach, self.kandidaten())

    def test_rote_pruefbitte_zaehlt_nicht(self):
        p = self.stapel()
        self.rot(p)
        self.assertNotIn(self.nach, self.kandidaten())

    def test_rotes_buendel_zaehlt_nicht(self):
        self.stapel()
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="AMW", art="buendel_befund",
                         aufgabe_id=self.vor, text=json.dumps({"aufgabe": self.vor, "art": "rot"}))
        self.assertNotIn(self.nach, self.kandidaten())

    def test_juengste_bitte_gilt(self):
        p = self.stapel("cc-st61", "055a43f")
        self.rot(p)
        self.stapel("cc-st62", "351eee6")                                 # neuer Stapel nach dem roten
        self.assertEqual(bn.basis(self.con, self.nach)[0]["zweig"], "cc-st62")


class Auftrag(Basis):
    def test_zugeteilt_mit_zweig_und_main_hinweis(self):
        p = self.stapel()
        aus = self.zuteilen()
        self.assertEqual(self.agent_von(self.nach), "CC1", aus)
        _, kurz, text = self.post("CC1", "auftrag")[-1]
        self.assertIn(f"A{self.nach} ist dir zugeteilt", kurz)
        self.assertIn(f"Baut auf: A{self.vor} (P{p}, cc-st62@351eee6a)", text)
        self.assertIn(f"nach dem Live-Gang von A{self.vor} auf main umsetzen", text)
        self.assertEqual(bn.gemerkt(self.con, self.nach)[self.vor]["zweig"], "cc-st62")

    def test_ohne_buendel_kein_zusatz(self):
        with db.schreiben(self.con):
            self.con.execute("DELETE FROM abhaengigkeit")
        self.zuteilen()
        texte = [t for _, k, t in self.post("CC1", "auftrag") if "zugeteilt" in k]
        self.assertTrue(texte)
        self.assertNotIn("Baut auf", texte[-1])

    def test_vorschlag_nennt_den_zweig_auch(self):
        self.stapel()
        verteilen.verteilen(self.con, self.pid)                            # Vorgabe: vorschlag an den Lead
        texte = [t for _, k, t in self.post("TL", "frage") if f"A{self.nach}" in k]
        self.assertTrue(texte)
        self.assertIn("Baut auf: A", texte[-1])

    def test_start_von_hand_und_naechster_schritt(self):
        self.stapel()
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET agent = 'CC1' WHERE id = ?", (self.nach,))
        a = planung.naechster(self.con, self.pid, "CC1")
        self.assertEqual((a or {}).get("id"), self.nach)
        kern.aufgabe_status(self.con, self.pid, "CC1", self.nach, "laeuft")
        self.assertEqual(self.status(self.nach), "laeuft")
        bn.abgleichen(self.con, self.pid, self.jetzt)                      # von Hand gestartet: die Basis wird gemerkt
        self.assertEqual(bn.gemerkt(self.con, self.nach)[self.vor]["sha"], "351eee6aa")

    def test_start_ohne_buendel_bleibt_gesperrt(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET agent = 'CC1' WHERE id = ?", (self.nach,))
        with self.assertRaises(kern.AmwFehler):
            kern.aufgabe_status(self.con, self.pid, "CC1", self.nach, "laeuft")


class Nachhalten(Basis):
    def zugeteilt(self):
        p = self.stapel()
        self.zuteilen()
        kern.aufgabe_status(self.con, self.pid, "CC1", self.nach, "laeuft")
        return p

    def test_rot_haelt_nach_der_nachfrist_an_einmal(self):
        p = self.zugeteilt()
        self.rot(p, minuten_her=5)
        self.assertEqual(bn.abgleichen(self.con, self.pid, self.jetzt), [])   # Zeit für einen neuen Stand
        self.assertEqual(self.halt(), [])
        self.rot(p, minuten_her=bn.NACHFRIST_MIN + 1)
        aus = bn.abgleichen(self.con, self.pid, self.jetzt)
        self.assertEqual(len(aus), 1, aus)
        self.assertEqual(self.halt(), [(f"A{self.vor}", "AMW")])
        self.assertEqual(self.status(self.nach), "wartet")
        self.assertIn(f"A{self.nach} angehalten: Basis A{self.vor} – Prüfbitte P{p} rot", self.post("CC1", "auftrag")[-1][1])
        self.assertTrue(any(f"A{self.nach} angehalten" in k for _, k, _ in self.post("TL", "meldung")))
        self.assertNotIn(self.nach, self.kandidaten())
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET agent = 'CC1' WHERE id = ?", (self.nach,))
        self.assertIsNone(planung.naechster(self.con, self.pid, "CC1"))
        self.assertEqual(bn.abgleichen(self.con, self.pid, self.jetzt), [])   # nicht jede Runde wieder

    def test_neuer_stand_hebt_den_halt_auf(self):
        p = self.zugeteilt()
        self.rot(p, minuten_her=bn.NACHFRIST_MIN + 1)
        bn.abgleichen(self.con, self.pid, self.jetzt)
        p2 = self.stapel("cc-st63", "abcdef12")
        aus = bn.abgleichen(self.con, self.pid, self.jetzt)
        self.assertIn("Halt aufgehoben", aus[0])
        self.assertEqual(self.halt(), [])
        kurz, text = self.post("CC1", "auftrag")[-1][1:]
        self.assertIn("neue Basis", kurz)
        self.assertIn(f"P{p2}", text)
        self.assertIn(f"amw aufgabe start {self.nach}", text)
        self.assertEqual(bn.gemerkt(self.con, self.nach)[self.vor]["zweig"], "cc-st63")
        self.assertEqual(bn.abgleichen(self.con, self.pid, self.jetzt), [])

    def test_neuer_stapel_ohne_rot_sagt_nur_den_zweig(self):
        self.zugeteilt()
        self.stapel("cc-st63", "abcdef12")
        aus = bn.abgleichen(self.con, self.pid, self.jetzt)
        self.assertEqual(len(aus), 1)
        self.assertNotIn("Halt", aus[0])
        self.assertEqual(self.status(self.nach), "laeuft")

    def test_live_gang_sagt_auf_main_umsetzen_einmal(self):
        self.zugeteilt()
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc1234' WHERE id = ?", (self.vor,))
        aus = bn.abgleichen(self.con, self.pid, self.jetzt)
        self.assertEqual(len(aus), 1, aus)
        self.assertIn(f"A{self.vor} ist live – A{self.nach} jetzt auf main umsetzen", self.post("CC1", "auftrag")[-1][1])
        self.assertEqual(bn.abgleichen(self.con, self.pid, self.jetzt), [])
        self.assertEqual(bn.gemerkt(self.con, self.nach), {})

    def test_halt_endet_mit_dem_live_gang(self):
        p = self.zugeteilt()
        self.rot(p, minuten_her=bn.NACHFRIST_MIN + 1)
        bn.abgleichen(self.con, self.pid, self.jetzt)
        with db.schreiben(self.con):                                       # so erledigt kern den Grund beim Abschluss von A<vor>
            wartegrund.erledige(self.con, self.pid, "aufgabe", f"A{self.vor}", "abgeschlossen")
        self.assertEqual(self.halt(), [])

    def test_runde_ruft_den_abgleich(self):
        p = self.zugeteilt()
        self.rot(p, minuten_her=bn.NACHFRIST_MIN + 1)
        aus = verteilen.runde(self.con, self.jetzt)
        self.assertTrue(any("angehalten" in x for x in aus), aus)


class EchteDaten(unittest.TestCase):
    """Auf einer Kopie der jüngsten Sicherung: die neue Auswahl nimmt nichts weg, und jedes zusätzliche Paket hat nur Vorgänger im Bündel."""

    def test_kopie_der_sicherung(self):
        quellen = sorted(glob.glob("F:/amw/daten/sicherung-*.db"), key=os.path.getmtime)
        if not quellen:
            self.skipTest("keine Sicherung auf diesem Rechner")
        ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(ordner.cleanup)
        ziel = os.path.join(ordner.name, "kopie.db")
        shutil.copy2(quellen[-1], ziel)
        con = db.verbinde(ziel)
        self.addCleanup(con.close)
        for p in con.execute("SELECT id FROM projekt").fetchall():
            neu = {a["id"] for a, _ in verteilen.kandidaten(con, p["id"])}
            alt = {r["id"] for r in wartegrund.freie_bogen_aufgaben(con, p["id"])
                   if con.execute("SELECT status FROM aufgabe WHERE id = ?", (r["id"],)).fetchone()[0] == "wartet"
                   and not wartegrund.offene(con, r["id"])
                   and not (con.execute("SELECT wartet_auf FROM aufgabe WHERE id = ?", (r["id"],)).fetchone()[0] or "").strip()
                   and not planung.offene_vorgaenger(con, r["id"])}
            self.assertLessEqual(alt, neu)
            for aid in neu - alt:
                for v in planung.offene_vorgaenger(con, aid):
                    self.assertIsNotNone(bn.im_buendel(con, v), (aid, v))


if __name__ == "__main__":
    unittest.main()
