"""Leitstand: „Sichern & beenden“ (geordnetes Ende, z. B. vor einem Update) und „Fehlende starten“ – ohne echte Prozesse.
Der Auftrag ist ein Halt für genau diesen Agenten mit Frist; der Wächter beendet die Sitzung, sobald sie abgemeldet ist,
spätestens zur Frist, und hebt den Halt auf. Anstoßen darf das nur der Mensch am PC."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime
import os
import tempfile
import unittest
from unittest import mock

from amw import aktionen, db, kern, steuerung, workbench


class Ende(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "Lead", rolle="lead", arbeitsweise="chat")   # Chat-Lead: kein Ordner, keine Sitzung
        for k in ("Bauer", "Maler", "Ruhe"):
            kern.agent_neu(self.con, self.pid, k)
            steuerung.profil_setzen(self.con, self.pid, "Entwickler", k, ordner=self.ordner.name)
        self.lebend = set()
        p = mock.patch.object(steuerung, "lebt", side_effect=lambda pid: pid in self.lebend)
        p.start()
        self.addCleanup(p.stop)
        self.beendet = []
        self.jetzt = datetime.datetime(2026, 11, 11, 10, 0, tzinfo=datetime.timezone.utc)

    def sitzung(self, kennung, cpid, zustand="aktiv"):
        aid = kern.agent_zeile(self.con, self.pid, kennung)["id"]
        with db.schreiben(self.con):
            sid = db.einfuegen(self.con, "sitzung", agent_id=aid, claude_sitzung=f"s-{cpid}", gestartet_utc=db.jetzt(),
                               schluessel_datei="x.json", claude_pid=cpid, zustand=zustand)
        self.lebend.add(cpid)
        return sid

    def beende(self, cpid):
        self.beendet.append(cpid)
        self.lebend.discard(cpid)

    def pruefen(self, minuten):
        return steuerung.ende_pruefen(self.con, jetzt=self.jetzt + datetime.timedelta(minutes=minuten), beenden_mit=self.beende)

    def post(self, kennung):
        return [(r["art"], r["kurz"]) for r in self.con.execute(
            "SELECT n.art, n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? ORDER BY n.id", (kennung,))]

    def test_frist_ist_eine_projekt_einstellung(self):
        self.assertEqual(steuerung.ende_frist(self.con, self.pid), 5)                         # Vorgabe
        kern.projekt_einstellen(self.con, self.pid, "Lead", ende_frist_min=12)
        self.sitzung("Bauer", 101)
        self.assertEqual(steuerung.ende_anfordern(self.con, self.pid, jetzt=self.jetzt)["bis_utc"], "2026-11-11T10:12:00Z")
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "Lead", ende_frist_min=0)
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "Lead", ende_frist_min=61)

    def test_alle_laufenden_bekommen_den_auftrag_mit_frist(self):
        self.sitzung("Bauer", 101)
        self.sitzung("Maler", 102)
        r = steuerung.ende_anfordern(self.con, self.pid, jetzt=self.jetzt)
        self.assertEqual(r["agenten"], ["Bauer", "Maler"])                         # Lead (Chat) und Ruhe (läuft nicht) nicht
        self.assertEqual(r["bis_utc"], "2026-11-11T10:05:00Z")
        self.assertEqual([e["kennung"] for e in steuerung.ende_offen(self.con, self.pid)], ["Bauer", "Maler"])
        art, kurz = self.post("Bauer")[-1]
        self.assertEqual(art, "stopp")
        self.assertIn("SICHERN UND BEENDEN", kurz)
        self.assertEqual(self.post("Ruhe"), [])
        self.assertEqual(steuerung.ende_anfordern(self.con, self.pid, jetzt=self.jetzt)["agenten"], [])   # kein zweites Mal

    def test_arbeitet_noch_dann_frist(self):
        self.sitzung("Bauer", 101)
        steuerung.ende_anfordern(self.con, self.pid, ["Bauer"], jetzt=self.jetzt)
        self.assertEqual(self.pruefen(2), [])                                       # hat noch Zeit
        self.assertEqual(self.beendet, [])
        aus = self.pruefen(5)
        self.assertEqual(self.beendet, [101])
        self.assertIn("Frist abgelaufen", aus[0])
        self.assertEqual(steuerung.ende_offen(self.con, self.pid), [])              # Halt aufgehoben
        self.assertFalse(kern.halt_gilt(self.con, self.pid, "Bauer"))
        ereignis = self.con.execute("SELECT ereignis, ereignis_text FROM sitzung").fetchone()
        self.assertEqual(tuple(ereignis), ("beendet", "amw"))                       # bewusst – kein Auto-Neustart

    def test_abgemeldet_wird_sofort_beendet(self):
        self.sitzung("Bauer", 101)
        steuerung.ende_anfordern(self.con, self.pid, ["Bauer"], jetzt=self.jetzt)
        kern.abmelden(self.con, self.pid, "Bauer")                                  # der Agent hat gesichert
        aus = self.pruefen(1)
        self.assertEqual(self.beendet, [101])
        self.assertIn("abgemeldet", aus[0])

    def test_selbst_beendet_hebt_nur_den_halt_auf(self):
        self.sitzung("Bauer", 101)
        steuerung.ende_anfordern(self.con, self.pid, ["Bauer"], jetzt=self.jetzt)
        self.lebend.discard(101)                                                    # Fenster geschlossen
        aus = self.pruefen(1)
        self.assertEqual(self.beendet, [])
        self.assertIn("läuft nicht mehr", aus[0])
        self.assertEqual(steuerung.ende_offen(self.con, self.pid), [])

    def test_gewoehnlicher_halt_bleibt_unberuehrt(self):
        self.sitzung("Bauer", 101)
        kern.halt(self.con, self.pid, "Entwickler", "Bauer", "kurz warten")
        self.assertEqual(self.pruefen(600), [])
        self.assertEqual(self.beendet, [])
        self.assertTrue(kern.halt_gilt(self.con, self.pid, "Bauer"))
        start = workbench.daten_start(self.con, self.pid)
        self.assertEqual((len(start["halt"]), start["ende"]), (1, []))

    def test_startseite_trennt_auftrag_und_halt(self):
        self.sitzung("Bauer", 101)
        steuerung.ende_anfordern(self.con, self.pid, ["Bauer"])
        start = workbench.daten_start(self.con, self.pid)
        self.assertEqual(start["halt"], [])                                         # steht nicht als „angehalten“ da
        self.assertEqual([e["kennung"] for e in start["ende"]], ["Bauer"])
        chat = {a["kennung"]: bool(a["chat"]) for a in start["agenten"]}
        self.assertEqual((chat["Lead"], chat["Bauer"]), (True, False))
        self.assertFalse([a for a in start["agenten"] if "ordner" in a])            # der Pfad geht nicht in die Seite

    def test_einzelner_agent_der_nicht_laeuft(self):
        with self.assertRaises(kern.AmwFehler):
            steuerung.ende_anfordern(self.con, self.pid, ["Ruhe"])
        with self.assertRaises(kern.AmwFehler):
            steuerung.ende_anfordern(self.con, self.pid, ["Niemand"])

    def test_nur_am_pc(self):
        self.sitzung("Bauer", 101)
        for weg in ("/api/agent/ende", "/api/agent/start-fehlende", "/api/dienst/neustart"):
            with self.assertRaises(aktionen.Ungueltig):
                aktionen.ausfuehren(self.con, self.pid, weg, {}, kanal="netz")
        self.assertEqual(steuerung.ende_offen(self.con, self.pid), [])
        r = aktionen.ausfuehren(self.con, self.pid, "/api/agent/ende", {"kennung": "Bauer"}, kanal="seite")
        self.assertEqual(r["agenten"], ["Bauer"])

    def test_fehlende_ohne_chat_laufende_und_abgemeldete(self):
        self.sitzung("Bauer", 101)                                                  # läuft
        self.sitzung("Ruhe", 103, zustand="ruht")                                   # abgemeldet, Fenster offen
        self.assertEqual(steuerung.fehlende(self.con, self.pid), ["Maler"])         # Lead ist Chat (kein Ordner)
        gestartet, pausen = [], []
        aus = steuerung.fehlende_starten(lambda: db.verbinde(os.path.join(self.ordner.name, "t.db")), self.pid, ["Maler", "Ruhe"], abstand_s=7,
                                         starte=lambda con, pid, k: gestartet.append(k) or f"{k} startet", warte=pausen.append)
        self.assertEqual((gestartet, pausen, aus), (["Maler", "Ruhe"], [7], ["Maler startet", "Ruhe startet"]))


if __name__ == "__main__":
    unittest.main()
