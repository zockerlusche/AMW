"""A2124: Ein Agent wird nur geweckt, wenn das Zusammensetzen einen Konflikt ergibt oder der Gesamtlauf nach dem Teilen ein schuldiges
Paket nennt – dann genau der Bauer des Pakets mit genau diesem Befund, einmal je Stand. Das Paket bleibt mit diesem Stand draußen, bis es
einen neuen hat. p-Paket (Headless, kein Resume in Stufe 1): E8 an den Paket-Prüfer."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
from unittest import mock

from amw import arbeitspaket, betrieb, buendel, buendel_auslieferung as ba, buendel_zusammensetzen as bz, db, kern, wartegrund
from tests.test_a2123_buendel_ohne_agent import Grund as AGrund
from tests.test_buendel_zusammensetzen import T1, T2, T3

KONFLIKT_A = {"lib/x.py": "def f():\n    return 2\n"}
KONFLIKT_B = {"lib/x.py": "def f():\n    return 3\n"}


class Grund(AGrund):
    def setUp(self):
        super().setUp()
        kern.agent_neu(self.con, self.pid, "CC2")
        kern.agent_neu(self.con, self.pid, "CC3")

    def fenster_von(self, titel, zeit, bauer, *staende, besitzer="CC1"):
        """Fenster-Paket: die Aufgabe gehört `besitzer`, gebaut und zur Prüfung gestellt hat es `bauer`."""
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel, besitzer)
        kopf = self.commit(f"fenster-A{aid}", *staende)
        with db.schreiben(self.con):
            db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=aid, zweig=f"fenster-A{aid}", sha=kopf, bauer=bauer,
                         pruefer="TL", ergebnis="gruen", angefragt_utc=zeit, ergebnis_utc=zeit)
        return aid, kopf

    def post(self, kennung):
        """(art, kurz, text) aller Nachrichten der AMW an `kennung`."""
        return [tuple(r) for r in self.con.execute(
            "SELECT n.art, n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? AND n.von = 'AMW'"
            " ORDER BY n.id", (kennung,))]

    def zu(self, kennung, aid):
        return [p for p in self.post(kennung) if f"A{aid}" in p[1]]


class Konflikt(Grund):
    def test_genau_der_bauer_mit_genau_dem_befund(self):
        self.an()
        a = self.p_paket("Erst", T1, KONFLIKT_A)
        b, kopf = self.fenster_von("Dann", T2, "CC2", KONFLIKT_B, besitzer="CC3")
        c = self.p_paket("Daneben", T3, {"lib/c.py": "C = 1\n"})
        self.assertEqual(self.los(), "ausgeliefert")
        (art, kurz, text), = self.post("CC2")                                                 # der Bauer der Prüfung, einmal
        self.assertEqual(art, "auftrag")
        self.assertIn(f"A{b}: Bündel – Konflikt in lib/x.py", kurz)
        self.assertIn(f"amw aufgabe start {b}", kurz)
        self.assertIn(f"Stand {kopf[:8]} (Zweig fenster-A{b})", text)
        self.assertIn("Dateien: lib/x.py", text)
        self.assertIn(f"Davor im Bündel: A{a}", text)
        self.assertIn("neuen Stand", text)
        self.assertEqual(self.post("CC3"), [])                                                # nicht der Besitzer, nicht die anderen
        self.assertEqual(self.post("CC1"), [])
        self.assertEqual(self.zu("TL", b), [])                                                # der Lead bekommt den Befund nicht
        e, = self.ereignisse(ba.BEFUND)
        self.assertEqual((e["aufgabe"], e["art"], e["an"], e["kopf"]), (b, "konflikt", "CC2", kopf))
        self.assertEqual(sorted(self.ereignisse()[0]["aufgaben"]), sorted([a, c]))

    def test_derselbe_stand_bleibt_draussen_bis_zum_neuen(self):
        b, kopf = self.fenster_von("Dann", T2, "CC2", KONFLIKT_B)
        self.p_paket("Erst", T1, KONFLIKT_A)
        self.assertEqual(self.los(), "bereit")
        with db.schreiben(self.con):                                                          # Bündel 1.2.4 ist durch (wie die Kette)
            self.con.execute("DELETE FROM plan_ereignis WHERE art = 'buendel'")
        k = next(p for p in bz.kandidaten(self.con, self.pid) if p["id"] == b)
        self.assertEqual(k["befund"], "konflikt")
        r = bz.zusammensetzen(self.con, self.pid, gebaut=ba.GEBAUT)
        grund, = [x["grund"] for x in r["raus"] if x["id"] == b]
        self.assertIn("Befund (Konflikt) auf diesem Stand", grund)
        bz._zurueck(self.repo, r["ordner"], self.daten(), r["basis"])
        self.assertEqual(ba.befund(self.con, self.pid, {"aufgabe": b, "kopf": kopf, "agent": "CC1"}, "konflikt", {"kopf": kopf}), None)
        self.assertEqual(len(self.post("CC2")), 1)                                            # kein zweiter Weckruf zum selben Befund
        self.assertEqual(len(self.ereignisse(ba.BEFUND)), 1)
        neu = self.commit(f"neu-A{b}", {"lib/x.py": "def f():\n    return 2\n", "lib/b.py": "B = 1\n"})   # nachgebessert, neue Prüfung
        with db.schreiben(self.con):
            db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=b, zweig=f"neu-A{b}", sha=neu, bauer="CC2", pruefer="TL",
                         ergebnis="gruen", angefragt_utc=T3, ergebnis_utc=T3)
        self.assertIsNone(next(p for p in bz.kandidaten(self.con, self.pid) if p["id"] == b)["befund"])

    def daten(self):
        return os.path.join(os.path.dirname(buendel.arbeitsbaum(self.con, self.pid)), "buendel-daten")

    def test_runde_zaehlt_ein_paket_mit_befund_nicht(self):
        self.an()
        b, kopf = self.fenster_von("Dann", T2, "CC2", KONFLIKT_B)
        with mock.patch.object(ba, "ist_amw", return_value=True):
            ba.befund(self.con, self.pid, {"aufgabe": b, "kopf": kopf, "agent": "CC1", "dateien": ["lib/x.py"]}, "konflikt", {"kopf": kopf})
        gestartet = []
        self.assertEqual(ba.runde(self.con, starten=lambda pid: gestartet.append(pid) or 1), [])
        self.assertEqual(gestartet, [])

    def test_bauer_entfernt_dann_der_lead(self):
        b, kopf = self.fenster_von("Dann", T2, "CC2", KONFLIKT_B)
        with db.schreiben(self.con):
            self.con.execute("UPDATE agent SET entfernt_utc = ? WHERE kennung = 'CC2'", (db.jetzt(),))
        self.assertEqual(ba.befund(self.con, self.pid, {"aufgabe": b, "kopf": kopf, "agent": "CC1"}, "konflikt", {"kopf": kopf}), "TL")
        self.assertEqual(len(self.zu("TL", b)), 1)


class Rot(Grund):
    def test_schuldiges_fenster_paket_weckt_seinen_bauer(self):
        self.an()
        a = self.p_paket("Gut", T1, {"lib/a.py": "A = 1\n"})
        b, kopf = self.fenster_von("Böse", T2, "CC2", {"lib/boese.py": "B = 1\n"})
        self.assertEqual(self.los(), "ausgeliefert")
        (art, kurz, text), = self.post("CC2")
        self.assertEqual(art, "auftrag")
        self.assertIn(f"A{b}: Bündel – Gesamtlauf rot, dein Stand ist schuldig", kurz)
        self.assertIn(f"Gesamtlauf rot, beim Teilen als schuldig gefunden: Stand {kopf[:8]}", text)
        self.assertIn("Meldung: Gesamtlauf L", text)
        self.assertEqual(self.post("CC1"), [])
        self.assertEqual(self.zu("TL", a) + self.zu("TL", b), [])
        e, = self.ereignisse(ba.BEFUND)
        self.assertEqual((e["aufgabe"], e["art"], e["an"]), (b, "rot", "CC2"))


class PPaket(Grund):
    def test_p_paket_mit_konflikt_geht_nach_e8_an_den_pruefer(self):
        self.an()
        self.p_paket("Erst", T1, KONFLIKT_A)
        b = self.p_paket("Dann", T2, KONFLIKT_B)
        self.assertEqual(self.los(), "ausgeliefert")
        self.assertEqual(arbeitspaket.lesen(self.con, b)["zustand"], "wartet_interaktiv")
        e = [r[0] for r in self.con.execute("SELECT text FROM plan_ereignis WHERE aufgabe_id = ? AND art = 'paket_entscheidung'"
                                            " ORDER BY id DESC LIMIT 1", (b,))]
        self.assertIn('"zeile": "E8"', e[0])
        (art, kurz, text), = self.zu("TL", b)                                                 # der Paket-Prüfer (hier der Lead)
        self.assertIn("E8 Bündel/konflikt", kurz)
        self.assertIn("Dateien: lib/x.py", text)
        self.assertEqual(self.post("CC1"), [])
        self.assertEqual(self.ereignisse(ba.BEFUND)[0]["an"], "TL")
        self.assertNotIn(b, [p["id"] for p in bz.kandidaten(self.con, self.pid)])            # nicht mehr in der Merge-Reihe


class GruenImBuendel(Grund):
    """F5397 (CCamwTL #33890): nach GRÜN wartet die Aufgabe still auf das Bündel (stapel:buendel) statt des Weckrufs – nur mit
    buendel_ausliefern = an; bei aus bleibt alles wie heute."""

    def warten_auf_pruefung(self):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Fenster", "CC2")
        kopf = self.commit(f"fenster-A{aid}", {"lib/f.py": "F = 1\n"})
        with db.schreiben(self.con):
            prid = db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=aid, zweig=f"fenster-A{aid}", sha=kopf, bauer="CC2",
                                pruefer="TL", ergebnis="offen", angefragt_utc=db.jetzt())
            self.con.execute("UPDATE aufgabe SET status = 'wartet' WHERE id = ?", (aid,))
            wartegrund.anlegen(self.con, self.pid, "CC2", aid, f"P{prid}")
        return aid, kopf, prid

    def test_gruen_bei_an_weckt_nicht(self):
        self.an()
        aid, kopf, prid = self.warten_auf_pruefung()
        betrieb.pruefung_ergebnis(self.con, self.pid, "TL", prid, "gruen")
        post = self.post("CC2") + [tuple(r) for r in self.con.execute(
            "SELECT n.art, n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = 'CC2'")]
        self.assertFalse([p for p in post if p[0] != "info"], post)                         # nur Information, kein Weckruf
        self.assertFalse([p for p in post if "alle Gründe erledigt" in p[1]])
        self.assertEqual([g["bezug"] for g in wartegrund.offene(self.con, aid)], [ba.BUENDEL_GRUND])
        self.assertEqual(wartegrund.sorte(*[(g["art"], g["bezug"]) for g in wartegrund.offene(self.con, aid)][0]), "wartet_stapel")
        self.assertIsNone(wartegrund.haelt_fest(self.con, self.pid, "CC2"))                  # frei für das nächste Paket
        self.assertEqual(wartegrund.startklar_wecken(self.con, self.pid), [])
        an = ba.befund(self.con, self.pid, {"aufgabe": aid, "kopf": kopf, "agent": "CC2", "dateien": ["lib/f.py"]}, "konflikt",
                       {"kopf": kopf})
        self.assertEqual(an, "CC2")
        self.assertEqual(wartegrund.offene(self.con, aid), [])                                # das Warten auf das Bündel ist zu Ende
        weck = [p for p in self.post("CC2") if p[0] != "info"]
        self.assertEqual(len(weck), 1)                                                        # genau ein Weckruf: der Befund
        self.assertIn("Konflikt in lib/f.py", weck[0][1])
        self.assertIsNone(ba.befund(self.con, self.pid, {"aufgabe": aid, "kopf": kopf, "agent": "CC2"}, "konflikt", {"kopf": kopf}))
        self.assertEqual(len([p for p in self.post("CC2") if p[0] != "info"]), 1)

    def test_bei_aus_wie_heute(self):
        aid, _, prid = self.warten_auf_pruefung()
        betrieb.pruefung_ergebnis(self.con, self.pid, "TL", prid, "gruen")
        self.assertEqual(wartegrund.offene(self.con, aid), [])
        weck = [p for p in self.post("CC2") if "alle Gründe erledigt" in p[1]]
        self.assertEqual(len(weck), 1)
        self.assertEqual(weck[0][0], "meldung")
        gruen = [r[0] for r in self.con.execute("SELECT n.art FROM nachricht n WHERE n.von = 'TL' AND n.kurz LIKE ?", (f"P{prid} GRUEN%",))]
        self.assertEqual(gruen, ["meldung"])

    def test_rot_bei_an_wie_heute(self):
        self.an()
        aid, _, prid = self.warten_auf_pruefung()
        betrieb.pruefung_ergebnis(self.con, self.pid, "TL", prid, "rot", bemerkung="fehlt")
        self.assertEqual(wartegrund.offene(self.con, aid), [])
        self.assertTrue([p for p in self.post("CC2") if "alle Gründe erledigt" in p[1]])

    def test_gruen_auf_einen_buendel_zweig_wie_heute(self):
        self.an()
        aid, kopf, prid = self.warten_auf_pruefung()
        with db.schreiben(self.con):
            self.con.execute("UPDATE pruefung SET zweig = 'buendel-1.2.4' WHERE id = ?", (prid,))
        betrieb.pruefung_ergebnis(self.con, self.pid, "TL", prid, "gruen")
        self.assertEqual(wartegrund.offene(self.con, aid), [])
        self.assertTrue([p for p in self.post("CC2") if "alle Gründe erledigt" in p[1]])
