"""A1938 (K2, TH155/TH165, #30215): Fertig-Quelle je Aufgabe (commit | thema | frist | ja) und Prüfquelle je Kriterium (lauf |
pruefung | thema | tests) – die AMW hakt ab, schließt selbst und schreibt Beleg und Zusammenfassung; nie ein Befehl im Dienst."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import datetime
import io
import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from amw import cli, db, fertigquelle, kern, planung, themen

JETZT = datetime.datetime(2026, 11, 30, 12, 0, tzinfo=datetime.timezone.utc)


class Fertig(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad})
        u.start()
        self.addCleanup(u.stop)
        for k in ("AMW_AGENT", "AMW_PROJEKT"):
            os.environ.pop(k, None)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Produkt", angelegt_utc=db.jetzt())
        for k, r in (("TL", "lead"), ("CC1", None), ("CC2", None)):
            kern.agent_neu(self.con, self.pid, k, rolle=r)
        self.aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Konzept schreiben", "CC1")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.aid, "start")

    def a(self):
        return self.con.execute("SELECT * FROM aufgabe WHERE id = ?", (self.aid,)).fetchone()

    def runde(self, jetzt=JETZT):
        return fertigquelle.runde(self.con, jetzt=jetzt, immer=True)

    def test_lesen(self):
        self.assertEqual(fertigquelle.quelle_lesen("Thema TH12"), {"art": "thema", "thema": 12})
        self.assertEqual(fertigquelle.quelle_lesen("frist 7 nach v1.160.0"), {"art": "frist", "tage": 7, "version": "1.160.0"})
        self.assertEqual(fertigquelle.pruefquelle_lesen("lauf  python  -m unittest"), {"art": "lauf", "befehl": "python -m unittest"})
        self.assertEqual(fertigquelle.pruefquelle_lesen("tests 50"), {"art": "tests", "mindestens": 50})
        for falsch in ("dokument D5", "frist 0 nach 1.0.0", "thema 12", "irgendwas"):
            with self.assertRaises(ValueError, msg=falsch):
                fertigquelle.quelle_lesen(falsch)
        with self.assertRaises(ValueError):
            fertigquelle.pruefquelle_lesen("befehl rm -rf /")

    def test_rechte(self):
        with self.assertRaisesRegex(kern.AmwFehler, "Lead, Mensch oder der Bearbeiter"):
            fertigquelle.setzen(self.con, self.pid, "CC2", self.aid, "ja")
        fertigquelle.setzen(self.con, self.pid, "CC1", self.aid, "ja")                            # der Bearbeiter
        self.assertEqual(fertigquelle.lesen(self.con, self.aid), {"art": "ja"})
        fertigquelle.setzen(self.con, self.pid, "TL", self.aid, "commit")                         # das neueste gilt
        self.assertEqual(fertigquelle.lesen(self.con, self.aid), {"art": "commit"})
        self.assertEqual(self.runde(), [])                                                         # commit/ja: nie im Dienst
        self.assertEqual(self.a()["status"], "laeuft")

    def test_thema_freigegeben_schliesst(self):
        tid = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", tid, "Text.")
        fertigquelle.setzen(self.con, self.pid, "TL", self.aid, f"thema TH{tid}")
        self.assertEqual(self.runde(), [])
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, tid)
        self.assertEqual(self.runde(), [f"A{self.aid}: fertig (TH{tid} Fassung 1)"])
        a = self.a()
        self.assertEqual((a["status"], a["beleg"]), ("fertig", f"TH{tid} Fassung 1"))
        self.assertIn("Thema TH%d ist freigegeben" % tid, a["zusammenfassung"])
        self.assertTrue(self.con.execute("SELECT 1 FROM nachricht WHERE kurz LIKE ?", (f"A{self.aid} fertig%",)).fetchone())

    def release(self, version, zeit):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "release", projekt_id=self.pid, art="version", version=version, zeit_utc=zeit, titel="x",
                         eingetragen_von="TL")

    def test_frist_ohne_fehler_schliesst(self):
        self.release("1.0.0", "2026-11-20T12:00:00Z")
        fertigquelle.setzen(self.con, self.pid, "TL", self.aid, "frist 7 nach 1.0.0")
        self.assertEqual(self.runde(jetzt=JETZT - datetime.timedelta(days=4)), [])                # noch nicht 7 Tage
        b = kern.aufgabe_neu(self.con, self.pid, "TL", f"Weiter mit A{self.aid}", "CC2")         # Verweis, aber nicht „behoben“
        self.assertEqual(self.runde(), [f"A{self.aid}: fertig (1.0.0 + 7 Tage)"])
        self.assertIn("7 Tage nach 1.0.0 ohne Revert", self.a()["zusammenfassung"])
        self.assertIsNotNone(b)

    def test_frist_fehler_halten_offen(self):
        self.release("1.0.0", "2026-11-20T12:00:00Z")
        fertigquelle.setzen(self.con, self.pid, "TL", self.aid, "frist 7 nach 1.0.0")
        b = kern.aufgabe_neu(self.con, self.pid, "TL", f"Fehler in A{self.aid} beheben", "CC2")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET hinweis_gruppe = 'behoben', angelegt_utc = '2026-11-23T00:00:00Z' WHERE id = ?", (b,))
            rot = db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=self.aid, zweig="z", sha="a" * 40, bauer="CC1",
                               pruefer="TL", ergebnis="rot", angefragt_utc="2026-11-22T10:00:00Z", ergebnis_utc="2026-11-22T10:00:00Z")
        self.assertEqual(fertigquelle.frist_fehler(self.con, self.pid, self.a(), "2026-11-20T12:00:00Z"),
                         [f"A{b} behebt einen Fehler darin", f"P{rot} rot"])
        self.assertEqual(self.runde(), [])
        self.assertEqual(self.a()["status"], "laeuft")
        self.assertEqual(fertigquelle.frist_fehler(self.con, self.pid, self.a(), "2026-11-25T00:00:00Z"), [])   # vor dem Release

    def test_frist_revert_in_main(self):
        repo = os.path.join(self.ordner.name, "repo")
        g = lambda *x: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", repo, *x], check=True,
                                      capture_output=True, text=True).stdout.strip()
        os.makedirs(repo)
        g("init", "-q", "-b", "main")
        with open(os.path.join(repo, "a.txt"), "w") as f:
            f.write("a\n")
        g("add", "-A")
        g("commit", "-q", "-m", f"A{self.aid}: Konzept")
        g("revert", "--no-edit", "HEAD")
        kern.projekt_ordner_setzen(self.con, self.pid, repo)
        self.assertEqual(len(fertigquelle.frist_fehler(self.con, self.pid, self.a(), "2000-01-01T00:00:00Z")), 1)

    def lauf(self, befehl, rc=0, ergebnis="", ende="2099-01-01T00:00:00Z"):
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="CC1", beschreibung="x", status="fertig", rc=rc,
                                angemeldet_utc=ende, ende_utc=ende, aufgabe_id=self.aid, befehl=json.dumps(befehl), ergebnis=ergebnis)

    def test_kriterien_mit_pruefquelle(self):
        planung.schritt_setzen(self.con, self.pid, "TL", aid=self.aid, kriterien=["Tests laufen", "geprüft", "viele Tests", "von Hand"])
        for nr, q in ((1, "lauf python -m unittest tests.test_x"), (2, "pruefung"), (3, "tests 10")):
            fertigquelle.pruefquelle_setzen(self.con, self.pid, "TL", self.aid, nr, q)
        self.lauf(["python  -m unittest  tests.test_x"], rc=1)                                     # rot zählt nicht
        self.lauf(["python -m unittest tests.test_y"])                                             # anderer Befehl
        self.lauf(["python -m unittest tests.test_x"], ende="2000-01-01T00:00:00Z")                 # vor dem Beginn
        self.assertEqual(self.runde(), [])
        l1 = self.lauf(["python   -m unittest tests.test_x"])
        l2 = self.lauf(["egal"], ergebnis="Ran 12 tests in 1.0s\nOK")
        aus = self.runde()
        self.assertEqual(aus, [f"A{self.aid}: Kriterium 1 abgehakt (L{l1} rc 0)", f"A{self.aid}: Kriterium 3 abgehakt (L{l2}: 12 Tests, rc 0)"])
        with db.schreiben(self.con):
            p = db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=self.aid, zweig="z", sha="b" * 40, bauer="CC1",
                             pruefer="TL", ergebnis="gruen", angefragt_utc="2099-01-01T00:00:00Z", ergebnis_utc="2099-01-01T00:00:00Z")
        self.assertEqual(self.runde(), [f"A{self.aid}: Kriterium 2 abgehakt (P{p} grün auf bbbbbbbb)"])
        k = json.loads(self.a()["kriterien"])
        self.assertEqual([x["erfuellt"] for x in k], [True, True, True, False])                     # ohne Quelle: Ja des Leads
        self.assertEqual(self.a()["status"], "laeuft")                                             # Kriterien schließen nicht
        self.assertEqual(self.con.execute("SELECT count(*) FROM plan_ereignis WHERE art = ?", (fertigquelle.ABGEHAKT,)).fetchone()[0], 3)

    def test_offenes_urteil_wird_nicht_uebergangen(self):
        """P429 (TH155 Pkt 3): Fertig-Quelle eingetreten, ein Kriterium ohne Quelle offen → offen + eine Frage an den Lead; nach
        seinem Ja → fertig. Ein offenes Kriterium mit Quelle wartet still."""
        tid = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", tid, "Text.")
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, tid)
        planung.schritt_setzen(self.con, self.pid, "TL", aid=self.aid, kriterien=["liest sich gut", "geprüft"])
        fertigquelle.pruefquelle_setzen(self.con, self.pid, "TL", self.aid, 2, "pruefung")
        fertigquelle.setzen(self.con, self.pid, "TL", self.aid, f"thema TH{tid}")
        self.assertEqual(self.runde(), [])                                                         # Fakt „pruefung“ fehlt: still
        self.assertEqual(self.a()["status"], "laeuft")
        with db.schreiben(self.con):
            db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=self.aid, zweig="z", sha="d" * 40, bauer="CC1",
                         pruefer="TL", ergebnis="gruen", angefragt_utc="2099-01-01T00:00:00Z", ergebnis_utc="2099-01-01T00:00:00Z")
        aus = self.runde()
        self.assertEqual(aus[-1], f"A{self.aid}: wartet auf das Ja des Leads (1 Kriterien)")
        self.assertEqual(self.a()["status"], "laeuft")
        fragen = self.con.execute("SELECT n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE n.art = 'frage'"
                                  " AND e.agent = 'TL' AND n.kurz LIKE ?", (f"A{self.aid} bereit zur Abnahme%",)).fetchall()
        self.assertEqual(len(fragen), 1)
        self.assertIn("Ja des Leads fehlt für: liest sich gut", fragen[0]["kurz"])
        self.assertIn(f"amw aufgabe kriterium {self.aid} 1", fragen[0]["text"])
        self.assertEqual(self.runde(), [])                                                         # einmal je Stand
        planung.kriterium(self.con, self.pid, "TL", self.aid, 1)                                   # das Ja des Leads
        self.assertEqual(self.runde(), [f"A{self.aid}: fertig (TH{tid} Fassung 1)"])
        self.assertEqual(self.a()["status"], "fertig")

    def test_takt(self):
        fertigquelle._ZULETZT["t"] = 0.0
        fertigquelle.runde(self.con)
        with mock.patch.object(fertigquelle, "kriterium_erfuellt", side_effect=AssertionError):
            self.assertEqual(fertigquelle.runde(self.con), [])                                    # höchstens alle 15 min

    def test_befehlszeile(self):
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}), \
                contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            self.assertEqual(cli.main(["--projekt", "Produkt", "--von", "TL", "aufgabe", "aendern", str(self.aid),
                                       "--kriterium", "Tests laufen", "--fertig-wenn", "frist 7 nach 1.0.0"]), 0)
            self.assertEqual(cli.main(["--projekt", "Produkt", "--von", "TL", "aufgabe", "kriterium", str(self.aid), "1",
                                       "--quelle", "tests 5"]), 0)
            self.assertEqual(cli.main(["--projekt", "Produkt", "--von", "TL", "aufgabe", "zeige", str(self.aid)]), 0)
        t = aus.getvalue()
        self.assertIn(f"A{self.aid}: fertig wenn frist 7 Tage nach 1.0.0 ohne Fehler", t)
        self.assertIn("1. [ ] Tests laufen  · Quelle: tests 5", t)
        self.assertIn("fertig_wenn: frist 7 Tage nach 1.0.0 ohne Fehler", t)


if __name__ == "__main__":
    unittest.main()
