"""A2135: gleicher Stand, gleiche Basis, gleiches pyright, gleiche Einstellung → die Sprachprüfung rechnet nur einmal; die anderen übernehmen
den Befund (eigener Eintrag, ohne Lauf) oder warten auf den, der gerade rechnet. „nicht gelaufen“ wird nie übernommen."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import threading
import unittest
from unittest import mock

from amw import belegung, betrieb, db, kern, vorpruefung
from tests import test_a2004_vorpruefung as a2004

OK = {"stand": "ok", "neu": 0, "text": "Sprachprüfung (pyright 1.1): 0 neue Fehler gegenüber dem Start-Commit", "basis": "12345678"}


class Grund(a2004.Grund):
    def setUp(self):
        super().setUp()
        self.modus("pyright")
        kern.agent_neu(self.con, self.pid, "TL2")
        self.gestartet, self.gerechnet, self.laeufe = [], [], []
        self.ergebnis = [OK]                                                            # je Rechnung eins; das letzte gilt weiter

        def rechnen(con, pid, sha, arbeit, werkzeuge=None, basis=None):
            self.gerechnet.append(sha)
            return self.ergebnis.pop(0) if len(self.ergebnis) > 1 else self.ergebnis[0]

        def lauf_start(*a, **k):
            self.laeufe.append(a[3])
            return 100 + len(self.laeufe)
        for ziel, name, wert in ((vorpruefung, "STARTER", lambda pid, prid: self.gestartet.append(prid) or os.getpid()), (vorpruefung, "pruefen", rechnen),
                                 (vorpruefung, "_pyright_version", lambda: "1.1"), (vorpruefung, "WARTEN_S", 0.02), (betrieb, "lauf_start", lauf_start),
                                 (betrieb, "lauf_zeile", lambda *a: {"status": "laeuft"}), (betrieb, "lauf_uebernehmen", lambda *a: True),
                                 (betrieb, "lauf_ende", lambda *a: None), (belegung, "lauf_merken", lambda *a: None), (belegung, "lauf_vergessen", lambda *a: None)):
            p = mock.patch.object(ziel, name, wert)
            p.start()
            self.addCleanup(p.stop)

    def neu(self, sha=None, pruefer="TL"):
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=self.aid, zweig="a12", sha=sha or self.sha, bauer="CC1", pruefer=pruefer,
                                angefragt_utc=db.jetzt())

    def anstossen(self, prid):
        return vorpruefung.anstossen(self.con, self.pid, prid)

    def ausfuehren(self, prid, con=None):
        return vorpruefung.ausfuehren(con or self.con, self.pid, prid)

    def befund(self, prid):
        return vorpruefung.letzter_befund(self.con, self.pid, prid) or {}

    def post(self, an="TL"):
        return [r[0] for r in self.con.execute("SELECT n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? AND n.kurz LIKE '%Sprachprüfung%'"
                                               " ORDER BY n.id", (an,))]


class Einmal(Grund):
    def test_neun_pruefbitten_ein_lauf_neun_befunde_eine_meldung(self):
        ids = [self.neu() for _ in range(9)]
        zeilen = [self.anstossen(i) for i in ids]
        self.assertIn("läuft", zeilen[0])
        self.assertTrue(all(f"wartet auf die von P{ids[0]}" in z for z in zeilen[1:]), zeilen)
        for i in ids:
            self.ausfuehren(i)
        self.assertEqual((len(self.gerechnet), len(self.laeufe)), (1, 1))
        b = [self.befund(i) for i in ids]
        self.assertEqual([x["stand"] for x in b], ["ok"] * 9)
        self.assertEqual([x["uebernommen"] for x in b], [None] + [ids[0]] * 8)
        self.assertTrue(all(x["text"].startswith(f"Übernommen von P{ids[0]}") and OK["text"] in x["text"] for x in b[1:]))
        self.assertEqual({x["lauf"] for x in b}, {101})
        self.assertEqual(self.post(), [f"P{ids[0]} Sprachprüfung: keine neuen Fehler"])

    def test_fertiger_befund_wird_gleich_uebernommen_ohne_prozess(self):
        a, b = self.neu(), self.neu()
        self.anstossen(a)
        self.ausfuehren(a)
        self.assertIn(f"keine neuen Fehler (übernommen von P{a})", self.anstossen(b))
        self.assertEqual((self.gestartet, len(self.gerechnet), self.befund(b)["uebernommen"]), ([a], 1, a))

    def test_wartet_auf_den_der_gerade_rechnet(self):
        a, b = self.neu(), self.neu()
        self.anstossen(a)
        self.anstossen(b)
        fertig = threading.Event()

        def warten():
            con = db.verbinde(os.environ["AMW_DB"])
            try:
                self.ausfuehren(b, con)
            finally:
                con.close()
                fertig.set()
        t = threading.Thread(target=warten)
        t.start()
        self.assertFalse(fertig.wait(0.5))                                              # wartet
        self.assertEqual(self.laeufe, [])
        self.ausfuehren(a)
        self.assertTrue(fertig.wait(20))
        t.join(20)
        self.assertEqual((len(self.laeufe), self.befund(b)["uebernommen"]), (1, a))

    def test_neue_fehler_werden_auch_uebernommen(self):
        self.ergebnis = [{"stand": "neu", "neu": 2, "text": "2 neue Fehler – beheben", "basis": "12345678"}]
        a, b = self.neu(), self.neu()
        self.anstossen(a)
        self.ausfuehren(a)
        self.assertIn(f"2 neue Fehler (übernommen von P{a})", self.anstossen(b))
        self.assertEqual((self.befund(b)["stand"], self.befund(b)["neu"]), ("neu", 2))

    def test_anderer_pruefer_bekommt_seine_meldung(self):
        a, b, c = self.neu(), self.neu(pruefer="TL2"), self.neu(pruefer="TL2")
        self.anstossen(a)
        self.ausfuehren(a)
        self.anstossen(b)
        self.anstossen(c)
        self.assertEqual((len(self.post()), self.post("TL2")), (1, [f"P{b} Sprachprüfung: keine neuen Fehler (übernommen von P{a})"]))


class Selbst(Grund):
    def test_nicht_gelaufen_wird_nie_uebernommen(self):
        self.ergebnis = [{"stand": "nicht_gelaufen", "text": "Sprachprüfung nicht gelaufen: Zeit um"}, OK]
        a, b, c = self.neu(), self.neu(), self.neu()
        for i in (a, b, c):
            self.anstossen(i)
        for i in (a, b, c):
            self.ausfuehren(i)
        self.assertEqual((len(self.gerechnet), [self.befund(i)["stand"] for i in (a, b, c)], self.befund(c)["uebernommen"]),
                         (2, ["nicht_gelaufen", "ok", "ok"], b))

    def test_toter_prozess_haelt_niemanden_auf(self):
        a, b = self.neu(), self.neu()
        with mock.patch.object(vorpruefung, "STARTER", lambda pid, prid: 999999):
            self.anstossen(a)
        with mock.patch("amw.steuerung.lebt", side_effect=lambda p: p == os.getpid()):
            self.assertIn("läuft", self.anstossen(b))
            self.ausfuehren(b)
        self.assertEqual((len(self.gerechnet), self.befund(b)["uebernommen"]), (1, None))

    def test_alter_anstoss_haelt_niemanden_auf(self):
        a, b = self.neu(), self.neu()
        self.anstossen(a)
        with db.schreiben(self.con):
            self.con.execute("UPDATE plan_ereignis SET zeit_utc = '2026-11-01T00:00:00Z' WHERE art = ?", (vorpruefung.ANGESTOSSEN,))
        self.assertIn("läuft", self.anstossen(b))

    def test_die_spaetere_haelt_die_fruehere_nicht_auf(self):
        a, b = self.neu(), self.neu()
        self.anstossen(a)
        self.anstossen(b)
        self.ausfuehren(a)                                                              # liefe sie in eine Warteschleife, hinge der Test
        self.assertEqual(self.befund(a)["uebernommen"], None)

    def test_anderer_stand_andere_basis_anderes_pyright_andere_einstellung(self):
        def rechnet(vorher=None):
            a = self.neu()
            if vorher:
                vorher()
            self.assertIn("läuft", self.anstossen(a))
            self.ausfuehren(a)
            return len(self.gerechnet)
        self.assertEqual(rechnet(), 1)
        sha = self.sha
        self.datei("a.py", "x = 3\n")
        a2004.git(self.repo, "commit", "-q", "-am", "A12: noch eine")
        self.sha = a2004.git(self.repo, "rev-parse", "HEAD")
        self.assertEqual(rechnet(), 2)                                                  # anderer Stand
        self.sha = sha
        with mock.patch.object(vorpruefung, "start_commit", return_value="f" * 40):
            self.assertEqual(rechnet(), 3)                                              # andere Basis
        with mock.patch.object(vorpruefung, "_pyright_version", return_value="1.2"):
            self.assertEqual(rechnet(), 4)                                              # anderes pyright
        self.datei("pyrightconfig.json", "{}\n")
        self.assertEqual(rechnet(lambda: self.modus("auto")), 5)                        # andere Einstellung

    def test_ohne_kennung_rechnet_jede_selbst(self):
        with mock.patch.object(vorpruefung, "_pyright_version", return_value=None):
            for n in (1, 2):
                a = self.neu()
                self.anstossen(a)
                self.ausfuehren(a)
                self.assertEqual((len(self.gerechnet), self.befund(a)["uebernommen"]), (n, None))


if __name__ == "__main__":
    unittest.main()
