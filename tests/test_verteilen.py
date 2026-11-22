"""A1927 (TH157): Verteilen an interaktive Agenten – ein freier Agent bekommt das nächste passende startklare Paket nach dem Plan
(Rang, kritischer Pfad); vorschlag (Vorgabe) / an / aus je Projekt; Ausfall: Paket zurück in den Pool mit Übergabe-Notiz, der
Mensch bekommt eine Frage zum Neustart, gestartet wird nie von selbst."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import tempfile
import time
import unittest

from amw import arbeitspaket, db, kern, verteilen


def utc(sek):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(sek))


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        for k, fach in (("CC1", "Code"), ("CC2", "Grafik")):
            kern.agent_neu(self.con, self.pid, k, fachgebiet=fach)
        self.jetzt = time.time()
        with db.schreiben(self.con):
            for k in ("CC1", "CC2"):
                aid = self.con.execute("SELECT id FROM agent WHERE kennung = ?", (k,)).fetchone()[0]
                db.einfuegen(self.con, "sitzung", agent_id=aid, gestartet_utc=utc(self.jetzt - 7200), schluessel_datei="x.key",
                             ereignis="frei", ereignis_utc=utc(self.jetzt - (40 if k == "CC1" else 20) * 60))
            self.bogen = db.einfuegen(self.con, "bogen", projekt_id=self.pid, nr=1, titel="Stufe 1", status="aktiv", angelegt_von="TL",
                                      angelegt_utc=db.jetzt())

    def aufgabe(self, titel, rang=50, art=None, groesse=None, bogen=True):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel)
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET bogen_id = ?, rang = ?, art = ?, groesse = ? WHERE id = ?",
                             (self.bogen if bogen else None, rang, art, groesse, aid))
        return aid

    def post(self, an, art=None):
        return [(r["art"], r["kurz"], r["text"]) for r in self.con.execute(
            "SELECT n.art, n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? AND n.von = 'AMW'"
            + (" AND n.art = ?" if art else "") + " ORDER BY n.id", (an, *([art] if art else [])))]

    def agent_von(self, aid):
        return self.con.execute("SELECT agent FROM aufgabe WHERE id = ?", (aid,)).fetchone()[0]


class Verteilen(Grund):
    def test_vorschlag_ist_die_vorgabe_einmal_je_paar(self):
        a = self.aufgabe("Liste schneller machen", art="fehlersuche")
        self.assertEqual(verteilen.einstellung(self.con, self.pid), "vorschlag")
        aus = verteilen.verteilen(self.con, self.pid)
        self.assertEqual(len(aus), 1)
        self.assertIn(f"Vorschlag A{a} an CC1", aus[0])                                 # CC1 am längsten frei, Code passt
        self.assertIsNone(self.agent_von(a))                                             # nur vorgeschlagen
        art, kurz, text = self.post("TL", "frage")[-1]
        self.assertEqual(kurz, f"Vorschlag: A{a} an CC1? (Liste schneller machen)")
        self.assertIn(f"amw aufgabe aendern {a} --agent CC1", text)
        self.assertEqual(verteilen.verteilen(self.con, self.pid), [])                    # nicht jede Runde wieder

    def test_an_teilt_zu_nach_rang_und_kritischem_pfad(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", verteilen="an")
        spaet = self.aufgabe("Später", rang=10, art="mechanisch")
        kurz = self.aufgabe("Allein", rang=5, art="mechanisch")
        lang = self.aufgabe("Mit Nachfolgern", rang=5, art="mechanisch")
        n1, n2 = self.aufgabe("Nachfolger 1", rang=60), self.aufgabe("Nachfolger 2", rang=60)
        with db.schreiben(self.con):
            self.con.execute("INSERT INTO abhaengigkeit (vor, nach, art) VALUES (?, ?, 'FS')", (lang, n1))
            self.con.execute("INSERT INTO abhaengigkeit (vor, nach, art) VALUES (?, ?, 'FS')", (n1, n2))
        self.assertEqual([a["id"] for a, _ in verteilen.kandidaten(self.con, self.pid)][:3], [lang, kurz, spaet])   # n1/n2: Vorgänger offen
        aus = verteilen.verteilen(self.con, self.pid)
        self.assertEqual(self.agent_von(lang), "CC1")                                    # Rang gleich → längere Kette zuerst
        self.assertIsNone(self.agent_von(kurz))                                          # CC2 (Grafik) passt nicht zu „mechanisch“
        self.assertEqual(len(aus), 1)
        art, kurz_text, text = self.post("CC1", "auftrag")[-1]
        self.assertEqual(kurz_text, f"A{lang} ist dir zugeteilt: Mit Nachfolgern")
        self.assertIn("kritischer Pfad: 2 offene Nachfolger", text)
        self.assertIn("Fach-Treffer „code“ im Fachgebiet Code (Art mechanisch)", text)          # #29773 (3): beide Treffer
        self.assertIn("Größe: Aufgabe ohne Größe oder Art – keine Empfehlung", text)
        self.assertIn(f"Verteilt: A{lang} an CC1", [k for _, k, _ in self.post("TL", "meldung")])
        self.assertEqual(verteilen.verteilen(self.con, self.pid), [])                    # CC1 hat jetzt Arbeit, CC2 passt nicht

    def test_passt_groesse_und_fachgebiet(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", verteilen="an")
        with db.schreiben(self.con):
            self.con.execute("UPDATE agent SET modell = 'sonnet', denkstufe = 'low' WHERE kennung = 'CC1'")
        heikel = self.aufgabe("Rechte prüfen", rang=1, art="sicherheit", groesse="L")      # Empfehlung opus/high
        ergebnis, gruende = verteilen.passt(self.con, self.pid, "CC1",
                                            self.con.execute("SELECT * FROM aufgabe WHERE id = ?", (heikel,)).fetchone())
        self.assertEqual((ergebnis, gruende[0]), ("schwach", f"A{heikel} bräuchte opus/high, CC1 hat sonnet/low"))
        knopf = self.aufgabe("Knopf zeichnen", rang=2, art="oberflaeche")
        verteilen.verteilen(self.con, self.pid)
        self.assertIsNone(self.agent_von(heikel))                                        # schwächer: nie selbst zuteilen …
        art, kurz, text = self.post("TL", "frage")[-1]                                   # … sondern dem Lead vorschlagen
        self.assertEqual(kurz, f"Vorschlag: A{heikel} an CC1? – A{heikel} bräuchte opus/high, CC1 hat sonnet/low")
        self.assertIn("TH159", text)
        self.assertEqual(self.agent_von(knopf), "CC2")                                   # CC1 bleibt beim Plan; CC2 (Grafik) passt
        verteilen.verteilen(self.con, self.pid)
        self.assertEqual(len([k for _, k, _ in self.post("TL", "frage") if "bräuchte" in k]), 1)   # nicht jede Runde wieder
        kern.projekt_einstellen(self.con, self.pid, "TL", verteilen_fach=json.dumps({"oberflaeche": ["grafik"]}))
        self.assertEqual(verteilen.fach_tabelle(self.con, self.pid)["oberflaeche"], ["grafik"])
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "TL", verteilen_fach=json.dumps({"tanzen": ["x"]}))
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "CC1", verteilen="an")      # nur Lead oder Mensch

    def test_fach_tabelle_nicht_aus_einer_agenten_sitzung(self):
        import contextlib
        import io
        from unittest import mock
        from amw import cli
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "t.db"), "AMW_AGENT": "", "CLAUDECODE": "1",
                                          "CLAUDE_CODE_MESSAGING_SOCKET": ""}), contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "P", "--von", "Entwickler", "projekt", "einstellen", 'verteilen_fach={"konzept": ["code"]}'])
        self.assertNotEqual(rc, 0)
        self.assertIn("nicht aus einer Agenten-Sitzung", aus.getvalue())
        self.assertEqual(verteilen.fach_tabelle(self.con, self.pid)["konzept"], ["konzept"])
        aus = io.StringIO()                                                               # P374 (1): auch verteilen selbst
        with mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "t.db"), "AMW_AGENT": "", "CLAUDECODE": "1",
                                          "CLAUDE_CODE_MESSAGING_SOCKET": ""}), contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "P", "--von", "Entwickler", "projekt", "einstellen", "verteilen=an"])
        self.assertNotEqual(rc, 0)
        self.assertIn("nicht aus einer Agenten-Sitzung", aus.getvalue())
        self.assertEqual(verteilen.einstellung(self.con, self.pid), "vorschlag")

    def test_kein_leerlauf_weckruf_bei_offenem_vorschlag(self):
        """P374 (2): solange zu einem Agenten ein Vorschlag offen ist, kommt kein zweiter Weckruf „hat nichts zu tun“."""
        from amw import wartegrund
        with db.schreiben(self.con):
            self.con.execute("UPDATE agent SET arbeitsweise = 'terminal'")
            self.con.execute("UPDATE sitzung SET ereignis_utc = ?", (utc(self.jetzt - 15 * 60),))
        a = self.aufgabe("Liste schneller machen", art="fehlersuche")
        verteilen.verteilen(self.con, self.pid)                                          # Vorschlag A… an CC1 (CC2: Grafik passt nicht)
        self.assertEqual(verteilen.offener_vorschlag(self.con, self.pid, "CC1"), a)
        wartegrund.leerlauf(self.con, self.jetzt)
        weckrufe = [k for _, k, _ in self.post("TL") if k.startswith("Leerlauf:") and "nichts zu tun" in k]
        self.assertEqual(weckrufe, ["Leerlauf: CC2 hat nichts zu tun"])                  # CC1 nicht, CC2 schon
        with db.schreiben(self.con):                                                     # vergeben → Vorschlag nicht mehr offen
            self.con.execute("UPDATE aufgabe SET agent = 'CC2' WHERE id = ?", (a,))
        self.assertIsNone(verteilen.offener_vorschlag(self.con, self.pid, "CC1"))

    def test_nur_freie_terminal_agenten_keine_p_pakete_nichts_bei_aus(self):
        p = self.aufgabe("Paket", rang=1, art="mechanisch")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET pruefbefehl = 'python -m unittest x', dateibereich = 'a/' WHERE id = ?", (p,))
        arbeitspaket.setzen(self.con, self.pid, "TL", p, art="p")
        self.assertEqual(verteilen.kandidaten(self.con, self.pid), [])                    # p-Pakete führt der Arbeiter aus
        a = self.aufgabe("Normal", rang=2, art="mechanisch")
        eigene = kern.aufgabe_neu(self.con, self.pid, "TL", "Läuft schon", agent="CC1")
        kern.aufgabe_status(self.con, self.pid, "CC1", eigene, "start")
        self.assertEqual([k for k, _ in verteilen.freie_agenten(self.con, self.pid)], ["CC2"])   # CC1 arbeitet
        kern.projekt_einstellen(self.con, self.pid, "TL", verteilen="aus")
        self.assertEqual(verteilen.verteilen(self.con, self.pid), [])
        self.assertIsNone(self.agent_von(a))


class Ausfall(Grund):
    def setUp(self):
        super().setUp()
        self.a = kern.aufgabe_neu(self.con, self.pid, "TL", "Halb fertig", agent="CC1")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.a, "start")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET begonnen_utc = ? WHERE id = ?", (utc(self.jetzt - 3600), self.a))

    def beenden(self, vor_min):
        with db.schreiben(self.con):
            self.con.execute("UPDATE sitzung SET zustand = 'beendet', beendet_utc = ?, taetigkeit = 'Tests für die Liste'"
                             " WHERE agent_id = (SELECT id FROM agent WHERE kennung = 'CC1')", (utc(self.jetzt - vor_min * 60),))

    def test_sitzung_beendet_paket_zurueck_mit_uebergabe_und_frage(self):
        self.assertEqual(verteilen.ausfall(self.con, self.pid, self.jetzt), [])           # Sitzung lebt
        self.beenden(10)
        self.assertEqual(verteilen.ausfall(self.con, self.pid, self.jetzt), [])           # erst 10 min: Zeit für einen Neustart
        self.beenden(45)
        self.assertEqual(verteilen.ausfall(self.con, self.pid, self.jetzt), [f"Ausfall CC1: A{self.a} zurück in den Pool"])
        r = self.con.execute("SELECT agent, status FROM aufgabe WHERE id = ?", (self.a,)).fetchone()
        self.assertEqual((r["agent"], r["status"]), (None, "wartet"))
        art, kurz, text = self.post("TL")[-1]
        self.assertEqual(kurz, f"Ausfall: CC1 – A{self.a} zurück in den Pool")
        self.assertIn("zuletzt: Tests für die Liste", text)
        self.assertIn("letzter Commit:", text)
        f = self.con.execute("SELECT an, kurz, empfehlung FROM frage ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual((f["an"], f["empfehlung"]), ("entwickler", "A"))
        self.assertIn("Sitzung von CC1 neu starten?", f["kurz"])
        self.assertEqual(verteilen.ausfall(self.con, self.pid, self.jetzt + 600), [])     # nur einmal

    def test_ausfall_min_einstellbar_und_lead_nie(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", ausfall_min=60)
        self.beenden(45)
        self.assertEqual(verteilen.ausfall(self.con, self.pid, self.jetzt), [])
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "TL", ausfall_min=2)
        tl = kern.aufgabe_neu(self.con, self.pid, "TL", "Plan", agent="TL")
        kern.aufgabe_status(self.con, self.pid, "TL", tl, "start")
        self.assertNotIn(f"A{tl}", " ".join(verteilen.ausfall(self.con, self.pid, self.jetzt + 7200)))


if __name__ == "__main__":
    unittest.main()
