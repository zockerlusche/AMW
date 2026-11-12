"""Tests für den Bildschirm-Schalter (B2419): Zustand, Rechte, automatisches Zugehen, Lauf-Schlange, Workbench, Brücke."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import io
import os
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

from amw import aktionen, betrieb, bruecke, cli, db, kern, schirm


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        for k, r in (("TL", "lead"), ("CC1", None), ("CC2", None)):
            kern.agent_neu(self.con, self.pid, k, rolle=r)
        with db.schreiben(self.con):                         # lebende Sitzungen: die Schlange überspringt sonst
            for k in ("CC1", "CC2"):
                aid = self.con.execute("SELECT id FROM agent WHERE kennung = ?", (k,)).fetchone()[0]
                db.einfuegen(self.con, "sitzung", agent_id=aid, gestartet_utc=db.jetzt())
        for name, wert in (("leerlauf_s", 600), ("fernsitzung", None), ("vordergrund", None)):   # PC ruhig, keine Fernsitzung
            p = mock.patch.object(schirm, name, return_value=wert)
            p.start()
            self.addCleanup(p.stop)
        schirm._eingabe["erste"] = None                      # Zustand des Dienstes je Test frisch

    def tearDown(self):
        self.con.close()
        self.ordner.cleanup()

    def frei(self, **k):
        return schirm.setzen(self.con, self.pid, "TL", True, "Entwickler 21:51: weg", **k)

    def status(self, lid):
        return self.con.execute("SELECT status FROM lauf WHERE id = ?", (lid,)).fetchone()[0]

    def an(self, agent):
        return [(n["art"], n["kurz"]) for n in kern.offene(self.con, self.pid, agent)]


class Zustand(Grund):
    def test_ab_werk_zu_und_rechte(self):
        self.assertEqual(schirm.zustand(self.con)["frei"], 0)
        self.assertIn("noch nie", schirm.text(schirm.zustand(self.con)))
        with self.assertRaises(kern.AmwFehler):
            schirm.setzen(self.con, self.pid, "CC1", True, "ich will")              # Agent gibt nicht frei
        with self.assertRaises(kern.AmwFehler):
            schirm.setzen(self.con, self.pid, "TL", True, "")                       # ohne Grund nicht
        self.assertEqual(self.frei()["frei"], 1)
        self.assertEqual(schirm.setzen(self.con, self.pid, "CC1", False, "Entwickler ist da")["frei"], 0)   # zu darf jeder
        schirm.setzen(self.con, self.pid, "CC2", False, "nochmal")                  # schon zu: keine neue Zeile
        self.assertEqual([z["frei"] for z in schirm.verlauf(self.con)], [0, 1])
        with self.assertRaises(Exception):
            self.con.execute("DELETE FROM schirm")

    def test_bis_uhrzeit(self):
        z = self.frei(bis="07:00")
        self.assertGreater(z["bis_utc"], z["seit_utc"])
        with self.assertRaises(kern.AmwFehler):
            schirm.bis_utc("morgen früh")


class Automatik(Grund):
    def test_neue_fernsitzung_schliesst(self):
        self.frei()
        self.assertEqual(schirm.pruefen(self.con, tv=time.time() - 3600), [])        # Sitzung von vorher: aus ihr freigegeben
        aus = schirm.pruefen(self.con, tv=time.time() + 5)
        self.assertTrue(aus and aus[0].startswith("Bildschirm zu: Fernsitzung seit"))
        self.assertEqual(schirm.zustand(self.con)["von"], "AMW")

    def test_eingabe_erst_nach_der_gnadenfrist(self):
        self.frei()
        t = time.time()
        self.assertEqual(schirm.pruefen(self.con, leerlauf=5, jetzt=t + 60, vg=""), [])      # Klick auf „frei“, Weggehen
        self.assertEqual(schirm.zustand(self.con)["frei"], 1)
        aus = schirm.pruefen(self.con, leerlauf=10, jetzt=t + 300, vg="")                     # Eingabe 290 s nach dem Freigeben
        self.assertIn("bis eine zweite folgt", aus[0])                                      # eine allein schließt nicht
        aus = schirm.pruefen(self.con, leerlauf=2, jetzt=t + 330, vg="explorer.exe")         # zweite, spätere Eingabe
        self.assertTrue(aus and aus[0].startswith("Bildschirm zu: Eingabe am PC") and "Vordergrund: explorer.exe" in aus[0])

    def test_einzelne_eingabe_schliesst_nicht(self):
        # 07.11. 20:34 und 08.11. 11:20: niemand am PC, eine Eingabe schloss den Bildschirm (Fehlalarm)
        self.frei()
        t = time.time()
        self.assertIn("bis eine zweite folgt", schirm.pruefen(self.con, leerlauf=10, jetzt=t + 300, vg="")[0])
        self.assertEqual(schirm.pruefen(self.con, leerlauf=40, jetzt=t + 330, vg=""), [])    # dieselbe Eingabe, nichts Neues
        self.assertEqual(schirm.zustand(self.con)["frei"], 1)
        self.assertEqual(schirm.pruefen(self.con, leerlauf=37, jetzt=t + 330, vg=""), [])    # Zucken über 3 s: zählt als eins
        self.assertEqual(schirm.zustand(self.con)["frei"], 1)
        aus = schirm.pruefen(self.con, leerlauf=5, jetzt=t + 600, vg="")                     # viel später: wieder nur eine
        self.assertIn("bis eine zweite folgt", aus[0])
        self.assertEqual(schirm.zustand(self.con)["frei"], 1)

    def test_eingaben_eines_schirm_laufs_schliessen_nicht(self):
        # 04.11. 23:02: der Fenster-Lauf L209 klickte selbst – Windows hielt das für den Entwickler, der Bildschirm ging zu
        self.frei()
        t = time.time()
        with db.schreiben(self.con):
            lid = db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="CC1", beschreibung="Proben mit Fenster", schirm=1,
                               status="laeuft", angemeldet_utc=schirm._utc(t + 200), start_utc=schirm._utc(t + 200))
        self.assertEqual(schirm.pruefen(self.con, leerlauf=1, jetzt=t + 300), [])                # Eingabe während des Laufs
        with db.schreiben(self.con):
            self.con.execute("UPDATE lauf SET status = 'fertig', ende_utc = ? WHERE id = ?", (schirm._utc(t + 310), lid))
        self.assertEqual(schirm.pruefen(self.con, leerlauf=60, jetzt=t + 370), [])               # letzte Eingabe 10 s vor Ende
        self.assertEqual(schirm.zustand(self.con)["frei"], 1)
        schirm.pruefen(self.con, leerlauf=5, jetzt=t + 400, vg="")                               # danach: wieder der Mensch …
        aus = schirm.pruefen(self.con, leerlauf=3, jetzt=t + 430, vg="")                         # … und bleibt da
        self.assertTrue(aus and aus[0].startswith("Bildschirm zu: Eingabe am PC"))

    def test_wortlaut_schliesst_nicht(self):
        # 04.11.: der Entwickler schrieb vom Handy, der Lead erfasste es als Wortlaut – der Bildschirm ging zu Unrecht zu
        self.frei()
        with db.schreiben(self.con):
            db.einfuegen(self.con, "wortlaut", projekt_id=self.pid, zeit_utc="2999-01-01T00:00:00Z", text="bin unterwegs",
                         kanal="chat-tl", erfasst_von="TL", erfasst_utc=db.jetzt())
        self.assertEqual(schirm.pruefen(self.con), [])
        self.assertEqual(schirm.zustand(self.con)["frei"], 1)

    def test_bis_uhrzeit_schliesst(self):
        z = self.frei(bis="2099-01-01 07:00")
        self.assertEqual(schirm.pruefen(self.con, jetzt=time.time() + 60), [])
        self.assertIn("abgelaufen", schirm.pruefen(self.con, jetzt=schirm._sek(z["bis_utc"]) + 1)[0])


class Schlange(Grund):
    def start(self, agent, **k):
        return betrieb.lauf_start(self.con, self.pid, agent, "Lauf " + agent, speicher_frei=20, **k)

    def test_schirm_lauf_wartet_auf_freigabe_und_ruhe(self):
        with self.assertRaises(kern.AmwFehler) as e:
            self.start("CC1", schirm=True)
        self.assertIn("Bildschirm ZU", str(e.exception))
        l1 = self.start("CC1", schirm=True, warten=True)
        self.assertEqual(self.status(l1), "angemeldet")
        self.assertIn("Bildschirm ZU", betrieb.wartegrund(self.con, self.pid, betrieb.lauf_zeile(self.con, self.pid, l1), 20))
        self.assertEqual(betrieb.warteschlange(self.con, self.pid, 20), [])
        self.frei()
        with mock.patch.object(schirm, "leerlauf_s", return_value=30):               # frei, aber jemand am PC
            self.assertEqual(betrieb.warteschlange(self.con, self.pid, 20), [])
        self.assertEqual(betrieb.warteschlange(self.con, self.pid, 20), [l1])
        self.assertIn(f"L{l1} ist dran", self.an("CC1")[-1][1])

    def test_wartender_schirm_lauf_haelt_laeufe_ohne_fenster_nicht_auf(self):
        l1 = self.start("CC1", schirm=True, warten=True)
        l2 = self.start("CC2")                                                       # schwer, ohne Fenster: läuft sofort
        self.assertEqual((self.status(l1), self.status(l2)), ("angemeldet", "laeuft"))
        l3 = self.start("CC2", warten=True)
        betrieb.lauf_ende(self.con, self.pid, "CC2", l2, 0, speicher_frei=20)
        self.assertEqual((self.status(l1), self.status(l3)), ("angemeldet", "laeuft"))

    def test_zugehen_meldet_laufende_und_wartende(self):
        self.frei()
        l1 = self.start("CC1", schirm=True)
        l2 = self.start("CC2", schirm=True, warten=True)
        schirm.setzen(self.con, None, "AMW", False, "Fernsitzung seit 06:36", quelle="automatik")
        self.assertIn(("korrektur", f"Bildschirm zu – L{l1} jetzt beenden: Fernsitzung seit 06:36"), self.an("CC1"))
        self.assertTrue(any(a == "meldung" and f"L{l2}" in k for a, k in self.an("CC2")))
        self.assertEqual(schirm.pruefen(self.con), [])                                # Nachfrist läuft noch
        spaeter = time.time() + schirm.NACHFRIST_S + 5
        self.assertEqual(schirm.pruefen(self.con, jetzt=spaeter), [f"L{l1} läuft trotz Bildschirm zu: Lead gemeldet"])
        self.assertEqual(schirm.pruefen(self.con, jetzt=spaeter), [])                  # nur einmal
        self.assertTrue(any(f"L{l1} läuft trotz Bildschirm zu" in k for _, k in self.an("TL")))


class Seite(Grund):
    def test_workbench_eingabe_schliesst_und_online_nur_zu(self):
        self.frei()
        aktionen.ausfuehren(self.con, self.pid, "/api/nachricht", {"an": "CC1", "art": "auftrag", "kurz": "vom Handy"},
                            kanal="netz")
        self.assertEqual(schirm.zustand(self.con)["frei"], 1)                      # online: unterwegs, bleibt frei
        kern.projekt_einstellen(self.con, self.pid, "TL", entwickler_name="Chris")
        aktionen.ausfuehren(self.con, self.pid, "/api/nachricht", {"an": "CC1", "art": "auftrag", "kurz": "los"})
        z = schirm.zustand(self.con)
        self.assertEqual((z["frei"], z["quelle"]), (0, "automatik"))
        self.assertIn("Chris ist da (Workbench", z["grund"])
        with self.assertRaises(aktionen.Ungueltig):
            aktionen.ausfuehren(self.con, self.pid, "/api/schirm", {"frei": True, "grund": "x"}, kanal="netz")
        r = aktionen.ausfuehren(self.con, self.pid, "/api/schirm", {"frei": True, "grund": "AFK", "bis": "07:00"})
        self.assertEqual((r["schirm"]["frei"], r["schirm"]["quelle"]), (1, "workbench"))
        r = aktionen.ausfuehren(self.con, self.pid, "/api/schirm", {"frei": False}, kanal="netz")
        self.assertEqual((r["schirm"]["frei"], r["schirm"]["quelle"]), (0, "netz"))

    def test_kontext_nennt_den_schirm(self):
        self.assertIn("Bildschirm ZU", kern.kontext(self.con, self.pid, "CC1"))


class Befehle(Grund):
    def cli(self, *args):
        aus = io.StringIO()
        with redirect_stdout(aus), mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "t.db")}):
            rc = cli.main([*args, "--projekt", "P"])
        return rc, aus.getvalue()

    def test_schirm_und_lauf_warte(self):
        rc, aus = self.cli("schirm", "frei", "--grund", "AFK", "--von", "TL")
        self.assertEqual(rc, 0)
        self.assertIn("Bildschirm FREI", aus)
        self.assertEqual(self.cli("schirm", "frei", "--grund", "AFK", "--von", "CC1")[0], 1)
        rc, aus = self.cli("schirm", "zeige", "--verlauf", "--von", "CC1")
        self.assertIn("dürfen starten", aus)
        self.cli("schirm", "zu", "--von", "CC1")
        l1 = betrieb.lauf_start(self.con, self.pid, "CC1", "Fenster", schirm=True, warten=True, speicher_frei=20)
        rc, aus = self.cli("lauf", "zeige", str(l1), "--von", "CC1")
        self.assertIn("Platz 1 von 1 – Bildschirm ZU", aus)
        rc, aus = self.cli("lauf", "warte", str(l1), "--hoechstens", "0.0001", "--von", "CC1")
        self.assertEqual(rc, 3)
        self.assertIn("wartet: Platz 1", aus)
        betrieb.lauf_ende(self.con, self.pid, "CC1", l1, None, abgebrochen=True)
        self.assertEqual(self.cli("lauf", "warte", str(l1), "--von", "CC1")[0], 2)
        l2 = betrieb.lauf_start(self.con, self.pid, "CC1", "ohne Fenster", speicher_frei=20)
        self.assertEqual(self.cli("lauf", "warte", str(l2), "--von", "CC1")[0], 0)

    def test_bruecke(self):
        self.assertEqual(bruecke.argumente({"befehl": "schirm", "aktion": "frei", "grund": "Entwickler 21:51"})[-4:],
                         ["--quelle", "bruecke", "--von", "TL"])
        with self.assertRaises(ValueError):
            bruecke.argumente({"befehl": "lauf", "aktion": "warte", "id": 3})
        with self.assertRaises(ValueError):
            bruecke.argumente({"befehl": "schirm", "aktion": "frei", "quelle": "workbench"})
        # beschluss: --quelle ist die inhaltliche Quelle und geht durch (Fehler #16846)
        a = bruecke.argumente({"befehl": "beschluss", "aktion": "neu", "kurz": "x", "quelle": "Entwickler 04.11. 11:35"})
        self.assertIn("Entwickler 04.11. 11:35", a)
        self.assertEqual(a.count("--quelle"), 1)


class Messen(unittest.TestCase):
    def test_messwerte_ohne_absturz(self):
        l = schirm.leerlauf_s()
        self.assertTrue(l is None or l >= 0)
        p = schirm.programme()
        self.assertIsInstance(p, dict)
        if p:                                                                         # unter Windows: wir selbst laufen
            self.assertTrue(any(n.startswith("python") for n in p))
            eigen = os.getpid()
            self.assertLess(abs(schirm.startzeit(eigen) - time.time()), 3600)

    def test_fernsitzung_zuerst_gesehen_und_nur_wenn_eingestellt(self):
        schirm._gesehen.clear()
        with mock.patch.object(schirm, "programme", return_value={"fernwartung_sitzung.exe": [4711]}), \
             mock.patch.object(schirm, "startzeit", return_value=None):              # Windows verweigert die Startzeit
            with mock.patch.object(schirm.einstellungen, "wert", return_value=""):
                self.assertIsNone(schirm.fernsitzung())                              # nichts eingestellt: aus
            with mock.patch.object(schirm.einstellungen, "wert", return_value="fernwartung_sitzung.exe"):
                erst = schirm.fernsitzung()
                self.assertIsNotNone(erst)
                self.assertEqual(schirm.fernsitzung(), erst)                         # bleibt beim ersten Sehen
        with mock.patch.object(schirm, "programme", return_value={}), \
             mock.patch.object(schirm.einstellungen, "wert", return_value="fernwartung_sitzung.exe"):
            self.assertIsNone(schirm.fernsitzung())
        self.assertEqual(schirm._gesehen, {})


class AusloeserAus(Grund):
    """Bildschirm-Freigabe: jeder Auslöser einzeln abschaltbar – aus heißt: schließt nicht UND misst nicht."""
    def einstellen(self, **aus):
        from amw import einstellungen
        echt = einstellungen.wert
        p = mock.patch.object(einstellungen, "wert", side_effect=lambda k: (not aus[k]) if k in aus else echt(k))
        p.start()
        self.addCleanup(p.stop)

    def nie_messen(self, *namen):
        for n in namen:                                  # wer misst, obwohl abgeschaltet, lässt den Test scheitern
            p = mock.patch.object(schirm, n, side_effect=AssertionError(f"{n} gemessen, obwohl abgeschaltet"))
            p.start()
            self.addCleanup(p.stop)

    def test_eingabe_am_pc_aus(self):
        self.einstellen(schirm_zu_eingabe=True)
        self.nie_messen("leerlauf_s", "vordergrund")
        self.frei()
        t = time.time()
        self.assertEqual(schirm.pruefen(self.con, jetzt=t + 300), [])
        self.assertEqual(schirm.pruefen(self.con, jetzt=t + 330), [])
        self.assertEqual(schirm.zustand(self.con)["frei"], 1)
        self.assertIsNone(schirm.sperrgrund(self.con))                                   # Läufe mit Fenster: keine Ruhe-Prüfung
        aus = schirm.pruefen(self.con, tv=t + 5)                                         # Fernsitzung wirkt weiter
        self.assertTrue(aus and aus[0].startswith("Bildschirm zu: Fernsitzung"))

    def test_fernsitzung_aus(self):
        self.einstellen(schirm_zu_fernsitzung=True)
        self.nie_messen("fernsitzung")
        self.frei()
        self.assertEqual(schirm.pruefen(self.con), [])                                   # PC ruhig (leerlauf 600 s)
        self.assertEqual(schirm.pruefen(self.con, tv=time.time() + 5), [])               # auch eine übergebene Sitzung zählt nicht
        self.assertEqual(schirm.zustand(self.con)["frei"], 1)

    def test_workbench_aus(self):
        self.einstellen(schirm_zu_workbench=True)
        self.frei()
        aktionen.ausfuehren(self.con, self.pid, "/api/nachricht", {"an": "CC1", "art": "info", "kurz": "hallo"}, kanal="seite")
        self.assertEqual(schirm.zustand(self.con)["frei"], 1)
        self.assertFalse(schirm.entwickler_da(self.con, "Workbench"))

    def test_vorgabe_alles_an(self):
        from amw import einstellungen
        for k in ("schirm_zu_eingabe", "schirm_zu_fernsitzung", "schirm_zu_workbench"):
            self.assertIs(einstellungen.FELDER[k][0], True, k)


class OnlineFreigeben(Grund):
    """Bildschirm online freigeben: nur System-Admin (Zugang der Seite oder Benutzer mit der Rolle), Uhrzeit freiwillig, Name im Grund."""
    def netz(self, wer, daten):
        return aktionen.ausfuehren(self.con, self.pid, "/api/schirm", dict(daten, _benutzer=wer), kanal="netz")

    def test_zugang_der_seite_mit_uhrzeit(self):
        from amw import benutzer
        kern.projekt_einstellen(self.con, self.pid, "TL", entwickler_name="Chris")
        r = self.netz(benutzer.ZUGANG, {"frei": True, "grund": "unterwegs"})                  # ohne bis: frei ohne Ende
        self.assertEqual((r["schirm"]["frei"], r["schirm"]["bis_utc"]), (1, None))
        self.netz(benutzer.ZUGANG, {"frei": False})
        r = self.netz(benutzer.ZUGANG, {"frei": True, "grund": "unterwegs", "bis": "23:30"})
        self.assertEqual((r["schirm"]["frei"], r["schirm"]["quelle"]), (1, "netz"))
        self.assertIn("online von Chris", r["schirm"]["grund"])
        self.assertIsNotNone(r["schirm"]["bis_utc"])

    def test_nur_system_admin(self):
        from amw import benutzer
        benutzer.neu(self.con, kern.ENTWICKLER, "sam", "system_admin")
        benutzer.neu(self.con, kern.ENTWICKLER, "bert", "bearbeiter", projekte=["P"])
        with self.assertRaises(aktionen.Ungueltig) as e:
            self.netz("bert", {"frei": True, "grund": "x", "bis": "23:30"})
        self.assertIn("nur ein System-Admin", str(e.exception))
        r = self.netz("sam", {"frei": True, "grund": "x", "bis": "23:30"})
        self.assertIn("online von sam", r["schirm"]["grund"])
        r = self.netz("bert", {"frei": False})                                                    # belegen darf jeder
        self.assertEqual(r["schirm"]["frei"], 0)
