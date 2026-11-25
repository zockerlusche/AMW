"""A2074: tote Läufe nach einem Rechner-Neustart (24.11., L3449 stand weiter auf „läuft“) oder ohne Warte-Prozess werden
abgeschlossen und gemeldet; ein abgebrochener Lauf gibt keinen Wartegrund frei; Gesamtläufe bekommen höchstens einen Ersatz, der nur
den eingestellten Gesamtlauf-Befehl rechnet; nach dem Neustart ein Weckruf. Prozesse und Rechnerstart sind Attrappen – kein Test
beendet einen Prozess."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import ast
import datetime
import json
import os
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from amw import abschluss, belegung, betrieb, db, kern, laufabbruch, laufdienst, vorpruefung, wartegrund

UTC = datetime.timezone.utc
WAECHTER, BEFEHL = 70001, 70002


def utc(sek):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(sek))


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db"), "LOCALAPPDATA": self.ordner.name})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen()
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid, "CC2")
        self.jetzt = time.time()
        self.vorher = self.jetzt - 4 * 3600               # Rechnerstart weit vor allen Läufen: die Neustart-Regel greift nicht
        self.leben = {}                                    # Nummer → Startzeit (Sekunden) der lebenden Prozesse
        for name, f in (("prozess_da", lambda n: n in self.leben),
                        ("prozesse", lambda: [{"pid": n, "seit": datetime.datetime.fromtimestamp(s, UTC) if s else None, "eltern": 0,
                                               "name": "python", "gb": 0.0} for n, s in self.leben.items()])):
            m = mock.patch.object(belegung, name, f)
            m.start()
            self.addCleanup(m.stop)
        self.gekillt = []
        for ziel in (mock.patch.object(laufdienst, "_baum_beenden", self.gekillt.append),):
            ziel.start()
            self.addCleanup(ziel.stop)

    def lauf(self, **kw):
        """Ein laufender Lauf, begonnen vor vor_s Sekunden."""
        kw = {"waechter": WAECHTER, "ausfuehrer": "agent", "befehl": ("python -m unittest",), "agent": "CC1", "schirm": 0, "vor_s": 3600,
              "pid_datei": None, **kw}
        waechter, ausfuehrer, befehl, agent, schirm, vor_s, pid_datei = (kw.pop(k) for k in (
            "waechter", "ausfuehrer", "befehl", "agent", "schirm", "vor_s", "pid_datei"))
        with db.schreiben(self.con):
            lid = db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent=agent, beschreibung=kw.pop("beschreibung", "Probe"), status="laeuft",
                               angemeldet_utc=utc(self.jetzt - vor_s), start_utc=utc(self.jetzt - vor_s), schirm=schirm, schwer=1,
                               rechner=betrieb.rechner(), befehl=json.dumps(list(befehl)) if befehl else None, waechter=waechter,
                               ausfuehrer=ausfuehrer, **kw)
        if pid_datei:
            belegung.lauf_merken(lid, pid_datei)
            os.utime(os.path.join(belegung._ordner(), f"{lid}.pid"), (self.jetzt - vor_s, self.jetzt - vor_s))
        return lid

    def runde(self, start=None, faeden=()):
        return laufabbruch.runde(self.con, faeden, start or self.vorher, laufabbruch.Prozesse())

    def z(self, lid):
        return self.con.execute("SELECT * FROM lauf WHERE id = ?", (lid,)).fetchone()

    def post(self, an, voll=False) -> list[tuple]:
        return [(r["art"], r["kurz"]) + ((r["text"],) if voll else ()) for r in self.con.execute(
            "SELECT n.art, n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? AND n.von = 'AMW' ORDER BY n.id",
            (an,))]

    def aufgabe(self, auf, agent="CC1", titel="Bauen"):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel, agent)
        kern.aufgabe_status(self.con, self.pid, agent, aid, "wartet", auf=auf)
        return aid

    def tearDown(self):
        self.assertEqual(self.gekillt, [])                 # KR14: dieser Weg beendet nie einen Prozess


class Erkennen(Grund):
    def test_toter_warte_prozess(self):
        datei = os.path.join(self.ordner.name, "aus.txt")
        with open(datei, "w", encoding="utf-8") as f:
            f.write("# Stand x\n[3/235] test_a ok\n[4/235] test_b ok\nletzte Zeile\n")
        lid = self.lauf(ergebnis_datei=datei, pid_datei=BEFEHL, braucht_gb=8)
        self.assertEqual(self.runde(), [f"L{lid} abgebrochen: Warte-Prozess weg"])
        z = self.z(lid)
        self.assertEqual((z["status"], z["rc"]), ("abgebrochen", None))
        self.assertIn("Modul 4 von 235", z["ergebnis"])
        with open(datei, encoding="utf-8") as f:
            aus = f.read()
        self.assertTrue(aus.startswith("# Stand x\n[3/235] test_a ok\n"))                  # Ausgabe erhalten
        self.assertIn("abgebrochen: Warte-Prozess weg", aus)
        self.assertIsNone(belegung.lauf_pid(lid))
        art, kurz, text = self.post("CC1", True)[0]
        self.assertEqual(art, "auftrag")
        self.assertIn(f"L{lid} abgebrochen (Warte-Prozess weg)", kurz)
        for teil in ("Modul 4 von 235", "letzte Zeile: letzte Zeile", "amw lauf ausfuehren --schwer", "aus-neu.txt", '-- "python -m unittest"'):
            self.assertIn(teil, text)
        self.assertEqual(len(self.post("CC1")), 1)
        self.assertEqual([a for a, _ in self.post("TL")], ["meldung"])

    def test_lebender_warte_prozess_bleibt(self):
        self.leben[WAECHTER] = self.jetzt - 3700
        lid = self.lauf()
        self.assertEqual(self.runde(), [])
        self.assertEqual(self.z(lid)["status"], "laeuft")

    def test_wiederverwendete_nummer(self):
        self.leben[WAECHTER] = self.jetzt - 600            # Prozess jünger als die Anmeldung: ein anderer
        lid = self.lauf()
        self.runde()
        self.assertEqual(self.z(lid)["status"], "abgebrochen")

    def test_startzeit_unlesbar_kein_abbruch_auf_verdacht(self):
        self.leben[WAECHTER] = None
        lid = self.lauf()
        self.assertEqual(self.runde(start=self.jetzt - 60), [])
        self.assertEqual(self.z(lid)["status"], "laeuft")

    def test_start_vor_dem_rechnerstart(self):
        for name, kw in (("agent", {}), ("fenster", {"schirm": 1}), ("ohne befehl", {"befehl": None}), ("von hand", {"befehl": None, "waechter": None, "ausfuehrer": None}),
                         ("dienst", {"ausfuehrer": "dienst"}), ("fenster ungestartet", {"schirm": 1, "ausfuehrer": None})):
            with self.subTest(name):
                lid = self.lauf(**kw)
                self.runde(start=self.jetzt - 1800)
                self.assertEqual(self.z(lid)["status"], "abgebrochen")
                self.assertIn("Rechner-Neustart", self.z(lid)["ergebnis"])

    def test_uhrsprung_schliesst_keinen_lebenden(self):
        """Bedingung B: der errechnete Rechnerstart liegt nach dem Beginn, aber Warte-Prozess bzw. Befehl leben nachweislich."""
        self.leben[WAECHTER] = self.jetzt - 3700
        a = self.lauf()
        self.leben[BEFEHL] = self.jetzt - 3601
        b = self.lauf(waechter=99999, pid_datei=BEFEHL)
        c = self.lauf(waechter=99999, ausfuehrer="dienst", pid_datei=BEFEHL)
        self.runde(start=self.jetzt - 1800)
        self.assertEqual([self.z(x)["status"] for x in (a, b, c)], ["laeuft"] * 3)

    def test_ohne_nummer_nie_warte_prozess_weg(self):
        lid = self.lauf(befehl=None, waechter=None, ausfuehrer=None)
        self.assertEqual(self.runde(), [])
        self.assertEqual(self.z(lid)["status"], "laeuft")

    def test_knapp_vor_dem_start_ist_spielraum(self):
        lid = self.lauf(befehl=None, waechter=None, ausfuehrer=None, vor_s=1800)
        self.runde(start=self.jetzt - 1770)
        self.assertEqual(self.z(lid)["status"], "laeuft")

    def test_fremder_rechner_und_was_der_dienst_uebernimmt_bleiben(self):
        a = self.lauf()
        b = self.lauf(ausfuehrer=None)                     # dran, nicht gestartet: A1640
        c = self.lauf()
        with db.schreiben(self.con):
            self.con.execute("UPDATE lauf SET rechner = 'anderer' WHERE id = ?", (a,))
        self.runde(start=self.jetzt - 60, faeden={c: True})
        self.assertEqual([self.z(x)["status"] for x in (a, b, c)], ["laeuft"] * 3)

    def test_dienst_lauf_prueft_auch_die_startzeit(self):
        """Bedingung C: die Nummer des Befehls lebt, gehört aber einem jüngeren Prozess."""
        self.leben[BEFEHL] = self.jetzt - 60
        lid = self.lauf(ausfuehrer="dienst", pid_datei=BEFEHL)
        laufdienst.Laufdienst(self.con, starten=lambda *a: self.fail("darf nicht aufpassen")).runde()
        self.assertEqual(self.z(lid)["status"], "abgebrochen")


    def test_dienst_lauf_tot_eine_nachricht_je_empfaenger(self):
        """Bedingung F: auch wenn der Dienst ihn rechnete – Besitzer, Wartender und Lead je eine, mit der Liste."""
        lid = self.lauf(ausfuehrer="dienst")
        a = self.aufgabe(f"L{lid}", "CC2")
        laufdienst.Laufdienst(self.con, starten=lambda *x: self.fail("darf nicht aufpassen")).runde()
        self.assertEqual(self.z(lid)["status"], "abgebrochen")
        self.assertEqual(len(wartegrund.offene(self.con, a)), 1)
        for wer in ("CC1", "CC2", "TL"):
            p = [t for _, k, t in self.post(wer, True) if f"L{lid} abgebrochen" in k]
            self.assertEqual(len(p), 1, wer)
            self.assertIn(f"A{a} (CC2)", p[0])


class BefehlLebtNoch(Grund):
    def test_bleibt_laeuft_einmal_melden_dann_abschliessen(self):
        self.leben[BEFEHL] = self.jetzt - 3600
        lid = self.lauf(pid_datei=BEFEHL, frist_min=30)
        self.runde()
        self.runde()
        self.assertEqual(self.z(lid)["status"], "laeuft")
        self.assertEqual([k for _, k in self.post("CC1")], [f"L{lid}: dein Warte-Prozess ist weg, der Befehl läuft noch"])
        self.assertEqual([k for _, k in self.post("TL")], [f"L{lid} läuft ohne Warte-Prozess über seine Frist (30 min)"])
        del self.leben[BEFEHL]
        self.runde()
        z = self.z(lid)
        self.assertEqual((z["status"], z["rc"]), ("abgebrochen", None))                     # nie ein Beleg

    def test_innerhalb_der_frist_erfaehrt_es_der_lead_nicht(self):
        self.leben[BEFEHL] = self.jetzt - 3600
        self.lauf(pid_datei=BEFEHL, frist_min=90)
        self.runde()
        self.assertEqual(self.post("TL"), [])


class Wartegruende(Grund):
    def test_abgebrochen_laesst_offen_und_meldet_gebuendelt(self):
        lid = self.lauf()
        a, b = self.aufgabe(f"L{lid}"), self.aufgabe(f"L{lid}", "CC2", "Prüfen")
        self.runde()
        for x in (a, b):
            self.assertEqual([g["bezug"] for g in wartegrund.offene(self.con, x)], [f"L{lid}"])
        for wer in ("CC1", "CC2", "TL"):
            p = [(k, t) for _, k, t in self.post(wer, True) if f"L{lid}" in k]
            self.assertEqual(len(p), 1, (wer, p))
            self.assertIn(f"A{a} (CC1), A{b} (CC2)", p[0][1])
            self.assertFalse(any("alle Gründe erledigt" in k for _, k in self.post(wer)))

    def test_gewollter_abbruch_haelt_offen(self):
        lid = self.lauf()
        a = self.aufgabe(f"L{lid}", "CC2")
        betrieb.lauf_ende(self.con, self.pid, "CC1", lid, None, "falscher Stand", abgebrochen=True)
        self.assertEqual(len(wartegrund.offene(self.con, a)), 1)
        for wer in ("CC1", "CC2", "TL"):
            self.assertEqual([k for _, k in self.post(wer) if "Grund bleibt offen" in k], [f"L{lid} abgebrochen – A{a}: Grund bleibt offen"])

    def test_rueckgabewert_verloren_haelt_offen(self):
        lid = self.lauf()
        a = self.aufgabe(f"L{lid}")
        betrieb.lauf_ende(self.con, self.pid, "CC1", lid, None, "x", unbekannt=True)
        self.assertEqual(self.z(lid)["status"], "fertig")
        self.assertEqual(len(wartegrund.offene(self.con, a)), 1)
        self.assertTrue(wartegrund.lauf_tot(self.con, self.pid, f"L{lid}"))

    def test_gegenprobe_ende_mit_rc_erledigt_wie_bisher(self):
        for rc in (0, 1):
            lid = self.lauf()
            a = self.aufgabe(f"L{lid}")
            betrieb.lauf_ende(self.con, self.pid, "CC1", lid, rc)
            self.assertEqual(wartegrund.offene(self.con, a), [])
            self.assertTrue(any(f"L{lid} zu Ende (rc {rc}) – alle Gründe erledigt" in k for _, k in self.post("CC1")))

    def test_ersatz_nennen_schliesst_den_alten(self):
        alt = self.lauf()
        a = self.aufgabe(f"L{alt},CC2")
        self.runde()
        self.assertIn("(abgebrochen)", wartegrund.anzeige(self.con, self.pid, wartegrund.offene(self.con, a)[0]))
        self.leben[WAECHTER] = self.jetzt - 3700
        neu = self.lauf()
        kern.aufgabe_status(self.con, self.pid, "CC1", a, "wartet", auf=f"L{neu}")
        self.assertEqual([g["bezug"] for g in wartegrund.offene(self.con, a)], ["CC2", f"L{neu}"])
        self.assertFalse(any("alle Gründe erledigt" in k for _, k in self.post("CC1")))

    def test_auf_einen_abgebrochenen_lauf_wartet_niemand_neu(self):
        lid = self.lauf()
        self.runde()
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Neu", "CC1")
        with self.assertRaisesRegex(kern.AmwFehler, f"L{lid} ist abgebrochen"):
            kern.aufgabe_status(self.con, self.pid, "CC1", aid, "wartet", auf=f"L{lid}")

    def test_erinnerung_einmal_nach_der_frist(self):
        lid = self.lauf()
        a = self.aufgabe(f"L{lid}")
        self.runde()
        self.assertEqual(laufabbruch.erinnern(self.con), [])
        spaeter = self.jetzt + 24 * 3600
        self.assertEqual(laufabbruch.erinnern(self.con, spaeter), [f"A{a} wartet noch auf abgebrochenen L{lid}"])
        self.assertEqual(laufabbruch.erinnern(self.con, spaeter), [])


def git(ordner, *a):
    return subprocess.run(["git", "-C", ordner, "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True, text=True).stdout.strip()


class Ersatz(Grund):
    SUITE = "python -m amw.testlauf"

    def setUp(self):
        super().setUp()
        self.repo = os.path.join(self.ordner.name, "repo")
        os.makedirs(self.repo)
        git(self.repo, "init", "-q", "-b", "main")
        with open(os.path.join(self.repo, "a.txt"), "w", encoding="utf-8") as f:
            f.write("a\n")
        git(self.repo, "add", "a.txt")
        git(self.repo, "commit", "-q", "-m", "eins")
        self.sha = git(self.repo, "rev-parse", "HEAD")
        with db.schreiben(self.con):
            self.con.execute("UPDATE agent SET ordner = ? WHERE kennung = 'CC1'", (self.repo,))
            self.con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?", (json.dumps({"gesamtlauf_befehl": self.SUITE}), self.pid))
        self.datei = os.path.join(self.ordner.name, "aus.txt")

    def toter(self, **kw):
        befehl, stand, sha = kw.pop("befehl", None), kw.pop("stand", "sauber"), kw.pop("sha", None)
        with open(self.datei, "w", encoding="utf-8") as f:
            f.write(f"# AMW L1\n# Befehl: x\n# Stand {sha or self.sha} {stand}\n[2/9] test_x ok\n")
        return self.lauf(befehl=[befehl or f"cd /d {self.repo} && set AMW_PROJEKT= && {self.SUITE}"], ordner=self.repo, ergebnis_datei=self.datei,
                         **{"beschreibung": "Gesamtlauf", **kw})

    def neue(self, ab):
        return self.con.execute("SELECT * FROM lauf WHERE id > ? ORDER BY id", (ab,)).fetchall()

    def test_ersatz_rechnet_nur_den_eingestellten_befehl(self):
        lid = self.toter(befehl=f"cd /d {self.repo} && {self.SUITE} && echo noch-etwas")
        a = self.aufgabe(f"L{lid}")
        self.runde()
        (n,) = self.neue(lid)
        self.assertEqual(json.loads(n["befehl"]), [self.SUITE])                            # Bedingung A: nie der gespeicherte Text
        self.assertEqual((n["ordner"], n["waechter"], n["schirm"]), (self.repo, None, 0))
        self.assertNotIn("AMW_PROJEKT", laufdienst.umgebung())
        self.assertNotIn("AMW_AGENT", laufdienst.umgebung())
        self.assertEqual([g["bezug"] for g in wartegrund.offene(self.con, a)], [f"L{n['id']}"])
        text = self.post("CC1", True)[0][2]
        self.assertIn(f"Ersatz L{n['id']} ist eingereiht oder läuft (vom Dienst gerechnet) – nicht selbst starten", text)
        self.assertNotIn("Neu starten:", text)
        self.assertEqual(len([1 for _, k in self.post("CC1") if f"L{lid} abgebrochen" in k]), 1)

    def test_kein_ersatz(self):
        def geaendert():
            with open(os.path.join(self.repo, "a.txt"), "w", encoding="utf-8") as f:
                f.write("geändert\n")
        anders = os.path.join(self.ordner.name, "anderswo")
        os.makedirs(anders)
        git(anders, "init", "-q", "-b", "main")
        git(anders, "commit", "-q", "--allow-empty", "-m", "fremd")                        # ein echter Stand – nur der Ordner ist ein anderer
        for name, kw, vorher in (("kein Gesamtlauf", {"befehl": "python planer.py"}, None),
                                 ("nur Beschreibung", {"befehl": "echo x", "beschreibung": "Gesamtlauf"}, None),
                                 ("anderer Stand", {"sha": "a" * 40}, None),
                                 ("Stand war geändert", {"stand": "geändert"}, None),
                                 ("cd in einen anderen Ordner", {"befehl": f"cd /d {anders} && {self.SUITE}"}, None),
                                 ("Fenster", {"schirm": 1}, None),
                                 ("Ordner jetzt geändert", {}, geaendert)):
            with self.subTest(name):
                if vorher:
                    vorher()
                lid = self.toter(**kw)
                self.runde()
                self.assertEqual(self.z(lid)["status"], "abgebrochen")
                self.assertEqual(self.neue(lid), [])
                self.assertIn("Neu starten: amw lauf ausfuehren", self.post("CC1", True)[-1][2])

    def test_ohne_eingestellten_befehl_kein_ersatz(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE projekt SET einstellungen = '{}' WHERE id = ?", (self.pid,))
        lid = self.toter()
        self.runde()
        self.assertEqual(self.neue(lid), [])

    def test_neuerer_lauf_rechnet_den_stand_schon(self):
        """Bedingung E: am 24.11. hatte der Besitzer den Ersatz schon selbst gestartet."""
        lid = self.toter()
        self.leben[555] = self.jetzt - 3700
        schon = self.lauf(befehl=[f"cd /d {self.repo} && {self.SUITE}"], ordner=self.repo, waechter=555)
        a = self.aufgabe(f"L{lid}")
        self.runde()
        self.assertEqual([x["id"] for x in self.neue(lid)], [schon])
        self.assertEqual([g["bezug"] for g in wartegrund.offene(self.con, a)], [f"L{schon}"])
        self.assertIn(f"L{schon} rechnet diesen Stand schon – nicht selbst starten", self.post("CC1", True)[0][2])

    def test_ein_ersatz_wird_nicht_noch_einmal_ersetzt(self):
        lid = self.toter()
        self.runde()
        (n,) = self.neue(lid)
        with db.schreiben(self.con):                        # der Dienst rechnete ihn, dann startet der Rechner neu
            self.con.execute("UPDATE lauf SET ausfuehrer = 'agent', status = 'laeuft', start_utc = ?, ergebnis_datei = ? WHERE id = ?",
                             (utc(self.jetzt - 3600), self.datei, n["id"]))
        self.toter_kopf()
        self.runde(start=self.jetzt - 1800)
        self.assertEqual(self.z(n["id"])["status"], "abgebrochen")
        self.assertEqual(self.neue(n["id"]), [])

    def toter_kopf(self):
        with open(self.datei, "w", encoding="utf-8") as f:
            f.write(f"# Stand {self.sha} sauber\n")

    def test_aufgabe_inzwischen_fertig_kein_ersatz(self):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Bauen", "CC1")
        lid = self.toter(aufgabe_id=aid)
        kern.aufgabe_status(self.con, self.pid, "TL", aid, "fertig", beleg="abc1234")
        self.runde()
        self.assertEqual(self.z(lid)["status"], "abgebrochen")
        self.assertEqual(self.neue(lid), [])
        offen = kern.aufgabe_neu(self.con, self.pid, "TL", "Prüfen", "CC1")                    # Gegenprobe: offene Aufgabe
        lid = self.toter(aufgabe_id=offen)
        self.runde()
        self.assertEqual([x["aufgabe_id"] for x in self.neue(lid)], [offen])

    def test_lauf_der_amw_selbst_nur_abschliessen(self):
        lid = self.toter(agent="TL")
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="AMW", art=betrieb.SELBST, text=json.dumps({"lauf": lid}))
        self.runde()
        self.assertEqual(self.z(lid)["status"], "abgebrochen")
        self.assertEqual(self.neue(lid), [])
        self.assertEqual([a for a, _ in self.post("TL")], ["meldung"])
        self.assertIn("Ein Lauf der AMW selbst", self.post("TL", True)[0][2])


class NachNeustart(Grund):
    def setUp(self):
        super().setUp()
        self.start = self.jetzt - 300
        self.a = kern.aufgabe_neu(self.con, self.pid, "TL", "Vorführung", "CC1")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "start")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET begonnen_utc = ? WHERE id = ?", (utc(self.jetzt - 7200), self.a))

    def sitzung(self, vor_s, kennung="CC1"):
        ag = kern.agent_zeile(self.con, self.pid, kennung)["id"]
        with db.schreiben(self.con):
            self.con.execute("UPDATE sitzung SET zustand = 'beendet' WHERE agent_id = ?", (ag,))
            db.einfuegen(self.con, "sitzung", agent_id=ag, gestartet_utc=utc(self.jetzt - vor_s), letzter_puls_utc=db.jetzt(), zustand="aktiv",
                         schluessel_datei="x")

    def weckrufe(self):
        return [t for art, k, t in self.post("CC1", True) if art == "auftrag" and k.startswith("Rechner neu gestartet")]

    def test_einmal_mit_stand_auch_wenn_der_wert_schwankt(self):
        lid = self.lauf()
        self.sitzung(100)
        self.runde(start=self.start)
        self.runde(start=self.start + 2.7)                  # Bedingung D: der errechnete Wert schwankt
        (t,) = self.weckrufe()
        self.assertIn(f"A{self.a} Vorführung", t)
        self.assertIn(f"L{lid} Probe", t)

    def test_neuer_rechnerstart_weckt_wieder(self):
        self.sitzung(290)
        self.runde(start=self.start)
        self.sitzung(10)
        self.runde(start=self.jetzt - 100)
        self.assertEqual(len(self.weckrufe()), 2)

    def test_gegenproben(self):
        self.sitzung(400)                                   # Sitzung von vor dem Start
        self.runde(start=self.start)
        self.assertEqual(self.weckrufe(), [])
        self.runde(start=self.jetzt - 7 * 3600)             # Rechnerstart vor Beginn der Aufgabe: kein Neustart dazwischen
        self.assertEqual(self.weckrufe(), [])

    def test_kompaktierung_lange_nach_dem_start_weckt_nicht(self):
        self.sitzung(3600)
        self.sitzung(5)                                     # dieselbe Arbeit, neue Sitzungszeile
        self.runde(start=self.jetzt - 3700)
        self.assertEqual(self.weckrufe(), [])

    def test_ohne_laufende_aufgabe_kein_weckruf(self):
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "wartet", auf="CC2")
        self.sitzung(100)
        self.runde(start=self.start)
        self.assertEqual(self.weckrufe(), [])


class LaeufeDerAmw(Grund):
    """Bedingung G: bei den Läufen der AMW ist der eingetragene Warte-Prozess der rechnende, kein kurzlebiger Starter."""

    def test_jeder_lauf_der_amw_traegt_den_eigenen_prozess_ein(self):
        ordner, gefunden = os.path.dirname(os.path.abspath(betrieb.__file__)), 0
        for name in sorted(x for x in os.listdir(ordner) if x.endswith(".py")):
            with open(os.path.join(ordner, name), encoding="utf-8") as f:
                baum = ast.parse(f.read())
            for fn in (x for x in ast.walk(baum) if isinstance(x, ast.FunctionDef)):
                rufe = [x for x in ast.walk(fn) if isinstance(x, ast.Call)]
                namen = {ast.unparse(x.func).split(".")[-1] for x in rufe}
                for r in rufe:
                    kw = {k.arg: ast.unparse(k.value) for k in r.keywords}
                    if ast.unparse(r.func).endswith("lauf_start") and kw.get("selbst") == "True":
                        gefunden += 1
                        self.assertEqual(kw.get("waechter"), "os.getpid()", f"{name}:{fn.name}")
                        self.assertTrue({"lauf_uebernehmen", "lauf_ende"} <= namen, f"{name}:{fn.name} rechnet nicht im selben Aufruf")
                        self.assertNotIn("Popen", namen, f"{name}:{fn.name} gibt die Arbeit an einen anderen Prozess")
        self.assertGreaterEqual(gefunden, 8)

    def test_sprachpruefung_rechnet_im_eingetragenen_prozess(self):
        gesehen = []

        def pruefen(con, *_a, **_k):
            l = con.execute("SELECT waechter, ausfuehrer FROM lauf ORDER BY id DESC LIMIT 1").fetchone()
            gesehen.append((l["waechter"], l["ausfuehrer"], os.getpid()))
            return {"stand": "ok", "text": "ok"}
        with db.schreiben(self.con):
            prid = db.einfuegen(self.con, "pruefung", projekt_id=self.pid, bauer="CC1", pruefer="TL", zweig="z", sha="a" * 40, ergebnis="offen",
                                angefragt_utc=db.jetzt())
        with mock.patch.object(vorpruefung, "pruefen", pruefen), mock.patch.object(vorpruefung, "abschliessen"), \
                mock.patch.object(vorpruefung, "gemerkte_basis", return_value=None):
            vorpruefung.ausfuehren(self.con, self.pid, prid)
        self.assertEqual(gesehen, [(os.getpid(), "agent", os.getpid())])

    def test_gesamttest_rechnet_im_eingetragenen_prozess(self):
        gesehen = []

        def rechnen(*_a, **_k):
            l = self.con.execute("SELECT waechter, ausfuehrer FROM lauf ORDER BY id DESC LIMIT 1").fetchone()
            gesehen.append((l["waechter"], l["ausfuehrer"]))
            return mock.Mock(returncode=0)
        with mock.patch.object(kern, "projekt_ordner", return_value=self.ordner.name), \
                mock.patch("amw.freigabereif._gesamtlauf_befehl", return_value="suite"), mock.patch.object(betrieb, "pruefstand", return_value=None), \
                mock.patch.object(abschluss, "_ausgeliefert", return_value=None), mock.patch.object(abschluss.subprocess, "run", rechnen):
            abschluss.gesamttest(self.con, self.pid, {"nr": 1})
        self.assertEqual(gesehen, [(os.getpid(), "agent")])


class Rechnerstart(unittest.TestCase):
    def test_liegt_in_der_vergangenheit_und_schwankt_kaum(self):
        a, b = laufabbruch.rechnerstart(), laufabbruch.rechnerstart()
        if a is None:
            self.skipTest("auf diesem System nicht messbar")
        self.assertLess(a, time.time())
        self.assertLess(abs(a - b), 5)


if __name__ == "__main__":
    unittest.main()
