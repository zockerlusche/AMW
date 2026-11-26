"""A2169 (Marcel über TL #34255, „die Leichen kommen immer wieder“): Eine Prüfbitte schließt mit ihrem Paket. Wird eine neuere Prüfbitte
derselben Aufgabe grün (vom Prüfer oder von der AMW wie bei Prüfung C), oder wird die Aufgabe fertig (auch über die Kette) oder verworfen,
schließt die AMW die übrigen offenen mit Grund – ohne Weckruf, nur ein Eintrag im Protokoll. Eine Prüfbitte, die länger als 24 h offen ist,
meldet die AMW dem Lead einmal."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import tempfile
import time
import unittest

from amw import betrieb, db, kern, wartegrund


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Speichern bauen", "CC1")
        self.andere = kern.aufgabe_neu(self.con, self.pid, "TL", "Anderes Paket", "CC1")

    def bitte(self, aid=None, zweig="a1", sha="1" * 40, zeit=None, pruefer="TL"):
        with db.schreiben(self.con):
            prid = db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=aid or self.aid, zweig=zweig, sha=sha, bauer="CC1",
                                pruefer=pruefer, angefragt_utc=zeit or db.jetzt())
            wartegrund.anlegen(self.con, self.pid, "CC1", aid or self.aid, f"P{prid}")
        return prid

    def p(self, prid):
        return self.con.execute("SELECT ergebnis, bemerkung FROM pruefung WHERE id = ?", (prid,)).fetchone()

    def an_cc1(self):
        return [r[0] for r in self.con.execute("SELECT n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = 'CC1'")]

    def protokoll(self):
        return [json.loads(r[0]) for r in self.con.execute("SELECT text FROM plan_ereignis WHERE art = ? ORDER BY id", (betrieb.VERALTET_ART,))]


class Neuere(Grund):
    def test_neuere_gruen_schliesst_die_aelteren_ohne_weckruf(self):
        fremd = self.bitte(aid=self.andere)                                                        # älter als die neue, aber andere Aufgabe
        alt = self.bitte(sha="1" * 40)
        neu = self.bitte(zweig="a1-b", sha="2" * 40)
        spaeter = self.bitte(zweig="a1-c", sha="3" * 40)
        vorher = len(self.an_cc1())
        betrieb.pruefung_ergebnis(self.con, self.pid, "TL", neu, "gruen")
        self.assertEqual(tuple(self.p(alt)), ("rot", f"veraltet – ersetzt durch P{neu} (grün)"))
        self.assertEqual(self.p(spaeter)["ergebnis"], "offen")                                    # nur die älteren
        self.assertEqual(self.p(fremd)["ergebnis"], "offen")                                      # nur dieselbe Aufgabe
        self.assertEqual(self.protokoll(), [{"pruefung": alt, "grund": f"ersetzt durch P{neu} (grün)", "neu": neu}])
        neu_an = self.an_cc1()[vorher:]
        self.assertFalse([k for k in neu_an if f"P{alt}" in k])                                   # kein Weckruf zur alten
        self.assertNotIn(f"pruefung:P{alt}", [g["bezug"] for g in wartegrund.offene(self.con, self.aid)])

    def test_gruen_der_amw_wie_pruefung_c(self):
        alt = self.bitte()
        neu = self.bitte(zweig="paket-A1", sha="4" * 40, pruefer="AMW")                         # so legt Prüfung C sie an (fensterpruefung)
        betrieb.pruefung_ergebnis(self.con, self.pid, "AMW", neu, "gruen", "Prüfung C grün")
        self.assertEqual(self.p(alt)["ergebnis"], "rot")

    def test_rot_schliesst_nichts(self):
        alt = self.bitte()
        neu = self.bitte(zweig="a1-b", sha="2" * 40)
        betrieb.pruefung_ergebnis(self.con, self.pid, "TL", neu, "rot", "fehlt")
        self.assertEqual(self.p(alt)["ergebnis"], "offen")


class Abschluss(Grund):
    def test_fertig_ueber_die_kette_ausgeliefert_ueber(self):
        alt = self.bitte()
        gruen = self.bitte(zweig="st66", sha="5" * 40)
        with db.schreiben(self.con):
            self.con.execute("UPDATE pruefung SET ergebnis = 'gruen', ergebnis_utc = ? WHERE id = ?", (db.jetzt(), gruen))
        noch = self.bitte(zweig="st65", sha="6" * 40)
        kern.aufgabe_status(self.con, self.pid, "AMW", self.aid, "fertig", beleg="abc1234", automatik=True)   # wie die Release-Kette
        for prid in (alt, noch):
            self.assertEqual(tuple(self.p(prid)), ("rot", f"veraltet – ausgeliefert über P{gruen}"))
        self.assertEqual(self.p(gruen)["ergebnis"], "gruen")
        self.assertEqual([x["pruefung"] for x in self.protokoll()], [alt, noch])                   # nur die offenen, nie die grüne

    def test_verworfen(self):
        alt = self.bitte()
        kern.aufgabe_status(self.con, self.pid, "TL", self.aid, "verwerfen", beleg="A99")
        self.assertEqual(tuple(self.p(alt)), ("rot", "veraltet – Paket verworfen"))

    def test_fertig_ohne_gruene(self):
        alt = self.bitte()
        kern.aufgabe_status(self.con, self.pid, "AMW", self.aid, "fertig", beleg="abc1234", automatik=True)
        self.assertEqual(self.p(alt)["bemerkung"], "veraltet – Paket fertig")


class Alt(Grund):
    def test_nach_24_stunden_einmal_an_den_lead(self):
        jetzt = time.time()
        iso = lambda s: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(s))                       # noqa: E731
        alt = self.bitte(zeit=iso(jetzt - 25 * 3600))
        self.bitte(aid=self.andere, zeit=iso(jetzt - 3600))
        self.assertEqual(betrieb.pruefungen_alt(self.con, self.pid, jetzt), [f"P{alt} seit über 24 h offen"])
        m = self.con.execute("SELECT n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = 'TL'"
                             " AND n.kurz LIKE '%seit über 24 h offen'").fetchone()
        self.assertEqual(m["kurz"], "1 Prüfbitte seit über 24 h offen")
        self.assertIn(f"P{alt} · A{self.aid}", m["text"])
        self.assertEqual(betrieb.pruefungen_alt(self.con, self.pid, jetzt + 3600), [])           # einmal je Prüfbitte
        self.assertEqual(self.an_cc1(), [])                                                       # der Bauer wird nicht geweckt


if __name__ == "__main__":
    unittest.main()
