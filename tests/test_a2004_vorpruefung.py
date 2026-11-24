"""A2004 Punkt 3 (TL #31260): nach jeder Prüfbitte stößt die AMW wie den Stil-Leser eine Sprachprüfung an – pyright auf genau dem
SHA gegen den merge-base mit main, in frischen Checkouts außerhalb des Baums des Bearbeiters; Befund als Meldung an den Prüfer
und an der Prüfbitte. Fällt etwas aus, ist das der Befund „Sprachprüfung nicht gelaufen“ – nie still. pyright selbst ist gemockt
(sprachpruefung), der Weg mit git (Prüf-Repo, merge-base, Checkout) ist echt."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from amw import betrieb, cli, db, kern, pruefung_c, vorpruefung


def git(ordner, *args):
    return subprocess.run(["git", "-C", ordner, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db"), "AMW_SPRACHE_AUS": ""})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.repo = os.path.join(self.ordner.name, "projekt")
        os.makedirs(self.repo)
        git(self.repo, "init", "-q", "-b", "main")
        self.datei("a.py", "x = 1\n")
        git(self.repo, "add", "a.py")
        git(self.repo, "commit", "-q", "-m", "Start")
        self.main = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "checkout", "-q", "-b", "a12")
        self.datei("a.py", "x = 2\n")
        git(self.repo, "commit", "-q", "-am", "A12: Änderung")
        self.sha = git(self.repo, "rev-parse", "HEAD")
        kern.projekt_ordner_setzen(self.con, self.pid, self.repo)
        self.aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Etwas", agent="CC1")
        with db.schreiben(self.con):
            self.prid = db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=self.aid, zweig="a12", sha=self.sha,
                                     bauer="CC1", pruefer="TL", angefragt_utc=db.jetzt())

    def datei(self, name, text):
        with open(os.path.join(self.repo, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def modus(self, wert):
        e = json.loads(self.con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (self.pid,)).fetchone()[0] or "{}")
        e["sprachpruefung"] = wert
        with db.schreiben(self.con):
            self.con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?", (json.dumps(e), self.pid))

    def meldungen(self):
        return [r[0] for r in self.con.execute("SELECT n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id"
                                               " WHERE e.agent = 'TL' AND n.von = 'AMW' AND n.kurz LIKE ? ORDER BY n.id", (f"P{self.prid} %",))]


class Anstossen(Grund):
    def test_nur_mit_konfiguration_oder_pyright(self):
        gestartet = []
        with mock.patch.object(vorpruefung, "STARTER", lambda pid, prid: gestartet.append(prid) or 4711):
            self.assertEqual(vorpruefung.anstossen(self.con, self.pid, self.prid), "")           # auto ohne pyrightconfig.json
            self.modus("aus")
            self.assertEqual(vorpruefung.anstossen(self.con, self.pid, self.prid), "")
            self.modus("auto")
            self.datei("pyrightconfig.json", "{}\n")
            self.assertIn("Sprachprüfung: läuft", vorpruefung.anstossen(self.con, self.pid, self.prid))
        self.assertEqual(gestartet, [self.prid])
        e = json.loads(self.con.execute("SELECT text FROM plan_ereignis WHERE art = ?", (vorpruefung.ANGESTOSSEN,)).fetchone()[0])
        self.assertEqual((e["pruefung"], e["prozess"]), (self.prid, 4711))

    def test_start_geht_nicht_ist_ein_befund(self):
        self.modus("pyright")

        def kaputt(pid, prid):
            raise OSError("kein Python")
        with mock.patch.object(vorpruefung, "STARTER", kaputt):
            self.assertIn("nicht gelaufen", vorpruefung.anstossen(self.con, self.pid, self.prid))
        self.assertEqual(self.meldungen(), [f"P{self.prid} Sprachprüfung nicht gelaufen: Lauf ließ sich nicht starten (kein Python)"])
        self.assertEqual(vorpruefung.letzter_befund(self.con, self.pid, self.prid)["stand"], "nicht_gelaufen")

    def test_jede_pruefbitte_stoesst_an_auch_ein_fehler_wird_sichtbar(self):
        self.modus("pyright")
        with mock.patch.object(vorpruefung, "STARTER", lambda pid, prid: 1):
            p1 = betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "a12", self.sha, "Punkte", self.aid, ohne_bild="nur Code")
        self.assertTrue(self.con.execute("SELECT 1 FROM plan_ereignis WHERE art = ? AND text LIKE ?",
                                         (vorpruefung.ANGESTOSSEN, f'{{"pruefung": {p1},%')).fetchone())
        with mock.patch.object(vorpruefung, "anstossen", side_effect=RuntimeError("kaputt")):
            p2 = betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "a12", self.sha, "Punkte", self.aid, ohne_bild="nur Code")
        self.assertEqual(vorpruefung.letzter_befund(self.con, self.pid, p2)["stand"], "nicht_gelaufen")   # nie still


class Pruefen(Grund):
    def setUp(self):
        super().setUp()
        self.modus("pyright")

    def test_genau_der_stand_gegen_merge_base(self):
        gesehen = {}

        def sprache(p, q, basis, werkzeuge=None):
            gesehen.update(basis=basis, kopf=git(q["klon"], "rev-parse", "HEAD"), inhalt=open(os.path.join(q["klon"], "a.py")).read())
            return {"befund": "C/rot", "neu": [["reportX", "a.py", "neu kaputt", 1]], "ausgabe": "Sprachprüfung (pyright 1.1): 1 neue Fehler – beheben:\n- a.py:1 [reportX] neu kaputt",
                    "version": "1.1", "grund": "1 neue Fehler (pyright)", "dauer_s": 3}
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as arbeit, mock.patch.object(pruefung_c, "sprachpruefung", sprache):
            aus = vorpruefung.pruefen(self.con, self.pid, self.sha, arbeit)
        self.assertEqual(gesehen, {"basis": self.main, "kopf": self.sha, "inhalt": "x = 2\n"})
        self.assertEqual((aus["stand"], aus["neu"]), ("neu", 1))
        self.assertEqual(git(self.repo, "rev-parse", "--abbrev-ref", "HEAD"), "a12")              # Baum des Bearbeiters unberührt
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_ohne_neue_fehler_und_ausfaelle(self):
        faelle = (({"befund": None, "neu": [], "ausgabe": "Sprachprüfung (pyright 1.1): 0 neue Fehler gegenüber dem Start-Commit"}, "ok",
                   "Sprachprüfung: keine neuen Fehler"),
                  ({"befund": None, "neu": [], "ausgabe": "x", "hinweis": pruefung_c.PYRIGHT_FEHLT}, "nicht_gelaufen",
                   "Sprachprüfung nicht gelaufen: Sprachprüfung übersprungen: pyright fehlt"),
                  ({"befund": "C/technik", "neu": [], "ausgabe": "x", "grund": "Zeit um"}, "nicht_gelaufen", "Sprachprüfung nicht gelaufen: Zeit um"))
        for r, stand, zeile in faelle:
            with self.subTest(stand=stand, zeile=zeile), tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as arbeit, \
                    mock.patch.object(pruefung_c, "sprachpruefung", lambda *a, **k: r):
                aus = vorpruefung.pruefen(self.con, self.pid, self.sha, arbeit)
                self.assertEqual(aus["stand"], stand)
                self.assertTrue(vorpruefung.zeile(aus).startswith(zeile), vorpruefung.zeile(aus))

    def test_unbekannter_stand(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as arbeit:
            aus = vorpruefung.pruefen(self.con, self.pid, "b" * 40, arbeit)
        self.assertEqual(aus["stand"], "nicht_gelaufen")
        self.assertIn("steht in keinem Zweig", aus["text"])


class StartCommit(Grund):
    """A2057: Vergleichsbasis = Start-Commit zum Zeitpunkt der Prüfbitte; main rückt vor (Gegenprobe) – es bleibt bei ihm;
    Stand = Basis (schon gemergt) → „kein Vergleich möglich“ statt „keine neuen Fehler“."""

    def setUp(self):
        super().setUp()
        self.modus("pyright")

    def test_basis_bei_der_pruefbitte_gemerkt_main_rueckt_vor(self):
        with mock.patch.object(vorpruefung, "STARTER", lambda pid, prid: 1):
            vorpruefung.anstossen(self.con, self.pid, self.prid)
        self.assertEqual(vorpruefung.gemerkte_basis(self.con, self.pid, self.prid), self.main)
        git(self.repo, "checkout", "-q", "main")
        git(self.repo, "merge", "-q", "--ff-only", "a12")                                        # gemergt: main = geprüfter Stand
        gesehen = {}

        def sprache(p, q, basis, werkzeuge=None):
            gesehen["basis"] = basis
            return {"befund": None, "neu": [], "ausgabe": "Sprachprüfung (pyright 1.1): 0 neue Fehler gegenüber dem Start-Commit"}
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as arbeit, mock.patch.object(pruefung_c, "sprachpruefung", sprache):
            aus = vorpruefung.pruefen(self.con, self.pid, self.sha, arbeit, basis=vorpruefung.gemerkte_basis(self.con, self.pid, self.prid))
        self.assertEqual((gesehen["basis"], aus["stand"]), (self.main, "ok"))                     # gegen den Start-Commit, nicht main
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as arbeit, mock.patch.object(pruefung_c, "sprachpruefung", sprache):
            ohne = vorpruefung.pruefen(self.con, self.pid, self.sha, arbeit)                      # Gegenprobe: ohne Merken = main
        self.assertEqual(ohne["stand"], "kein_vergleich")
        self.assertEqual(vorpruefung.zeile(ohne), "Sprachprüfung: kein Vergleich möglich (Start-Commit = geprüfter Stand)")


class Ausfuehren(Grund):
    def test_schlange_bricht_ab_wird_befund(self):
        with mock.patch.object(betrieb, "lauf_start", return_value=77), mock.patch.object(betrieb, "lauf_zeile", return_value={"status": "abgebrochen"}), \
                mock.patch.object(betrieb, "lauf_ende") as ende, mock.patch("amw.belegung.lauf_merken"), mock.patch("amw.belegung.lauf_vergessen"):
            aus = vorpruefung.ausfuehren(self.con, self.pid, self.prid)
        self.assertEqual(aus["stand"], "nicht_gelaufen")
        self.assertIn("in der Lauf-Schlange nicht drangekommen", aus["text"])
        self.assertEqual(ende.call_args[0][4], 1)                                                    # Lauf endet mit rc 1
        self.assertTrue(self.meldungen()[-1].startswith(f"P{self.prid} Sprachprüfung nicht gelaufen"))

    def test_befund_an_der_pruefbitte(self):
        vorpruefung.abschliessen(self.con, self.pid, self.prid, {"stand": "neu", "neu": 1, "text": "Sprachprüfung (pyright): 1 neue Fehler – beheben:\n- a.py:1 x",
                                                                  "basis": self.main[:8]}, lauf=5)
        self.assertEqual(self.meldungen(), [f"P{self.prid} Sprachprüfung: 1 neue Fehler"])
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus):
            cli.main(["--projekt", "P", "pruefung", "zeige", str(self.prid), "--von", "TL"])
        self.assertIn("Sprachprüfung: 1 neue Fehler\nSprachprüfung (pyright): 1 neue Fehler – beheben:\n- a.py:1 x", aus.getvalue())


if __name__ == "__main__":
    unittest.main()
