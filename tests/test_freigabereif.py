"""A1897: „freigabereif“ von selbst (grüner Gesamtlauf auf einem grün geprüften Stand ohne Merge-OK → Meldung an den Prüfer),
info mit Bitte um Handlung an den Lead abweisen, gemeinsam geprüfter Stand belegt keine Versionsnummer, Lead nachwecken."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from amw import betrieb, db, kern, versionsnummer
from tests import test_dienst as td

SHA = "a" * 40
ANDERER = "b" * 40


class Basis(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"LOCALAPPDATA": self.ordner.name})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "PR")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Etwas", "CC1")

    def pruefung(self, sha=SHA, ergebnis="gruen"):
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=self.aid, zweig="a1", sha=sha, bauer="CC1",
                                pruefer="PR", ergebnis=ergebnis, angefragt_utc=db.jetzt())

    def gesamtlauf(self, rc=0, sha=SHA, beschreibung="Gesamtlauf 1.0.1 a1"):
        lid = betrieb.lauf_start(self.con, self.pid, "CC1", beschreibung, schwer=False)
        betrieb.lauf_ende(self.con, self.pid, "CC1", lid, rc, f"rc {rc} · Stand {sha} sauber · Ausgabe: x")
        return lid

    def an(self, kurz_anfang):
        return [(r[0], r[1]) for r in self.con.execute(
            "SELECT e.agent, n.art FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE n.kurz LIKE ? ORDER BY e.agent",
            (kurz_anfang + "%",))]


class Freigabereif(Basis):
    def test_gruener_gesamtlauf_meldet_dem_pruefer(self):
        prid = self.pruefung()
        lid = self.gesamtlauf()
        self.assertEqual(self.an(f"A{self.aid} freigabereif"), [("CC1", "info"), ("PR", "meldung")])
        text = self.con.execute("SELECT kurz FROM nachricht WHERE kurz LIKE ?", (f"A{self.aid} freigabereif%",)).fetchone()[0]
        self.assertEqual(text, f"A{self.aid} freigabereif: P{prid} grün, Gesamtlauf L{lid} grün auf genau {SHA[:8]} – Merge-OK:"
                               f" amw freigabe merge {self.aid} --zweig a1")
        self.gesamtlauf()                                                                         # eine Meldung je Stand
        self.assertEqual(len(self.an(f"A{self.aid} freigabereif")), 2)

    def test_anderer_stand_merge_ok_oder_kein_gesamtlauf_keine_meldung(self):
        self.pruefung(ANDERER)
        self.gesamtlauf()                                                                         # anderer SHA
        self.gesamtlauf(beschreibung="Proben test_x")                                             # kein Gesamtlauf
        self.assertEqual(self.an(f"A{self.aid} freigabereif"), [])
        self.pruefung()
        betrieb.freigabe_merge(self.con, self.pid, "TL", self.aid, "a1")                          # schon Merge-OK
        self.gesamtlauf()
        self.assertEqual(self.an(f"A{self.aid} freigabereif"), [])

    def test_rot_meldet_rot(self):
        self.pruefung()
        lid = self.gesamtlauf(rc=1)
        self.assertEqual(self.an(f"A{self.aid}: Gesamtlauf L{lid} rot"), [("CC1", "meldung"), ("PR", "meldung")])
        self.assertEqual(self.an(f"A{self.aid} freigabereif"), [])

    def test_pruefung_erst_nach_dem_lauf(self):
        self.gesamtlauf()
        prid = self.pruefung(ergebnis="offen")
        betrieb.pruefung_ergebnis(self.con, self.pid, "PR", prid, "gruen")
        self.assertEqual(self.an(f"A{self.aid} freigabereif"), [("CC1", "info"), ("PR", "meldung")])


class BitteAlsInfo(Basis):
    def test_info_mit_bitte_an_den_lead_abgewiesen(self):
        with self.assertRaisesRegex(kern.AmwFehler, r"Bitte um Handlung → --art frage \(weckt\)"):
            kern.posten(self.con, self.pid, "CC1", "TL", "info", "A1 fertig – bitte Merge-OK geben")
        with self.assertRaisesRegex(kern.AmwFehler, "Bitte um Handlung"):
            kern.posten(self.con, self.pid, "CC1", "TL,PR", "info", "Stand", text="Merge-OK?")
        kern.posten(self.con, self.pid, "CC1", "TL", "frage", "A1 fertig – bitte Merge-OK geben")      # als Frage: ja
        kern.posten(self.con, self.pid, "CC1", "TL", "info", "1.0.1 live")                           # reine Info: ja
        kern.posten(self.con, self.pid, "CC1", "PR", "info", "bitte prüfen")                         # nicht an den Lead: ja

    def test_info_zu_einer_aufgabe_die_auf_den_lead_wartet(self):
        from amw import wartegrund
        with db.schreiben(self.con):
            wartegrund.anlegen(self.con, self.pid, "CC1", self.aid, "TL")
        with self.assertRaisesRegex(kern.AmwFehler, "Bitte um Handlung"):
            kern.posten(self.con, self.pid, "CC1", "TL", "info", "Stand", aufgabe_id=self.aid)


@unittest.skipUnless(shutil.which("git"), "git fehlt")
class GemeinsamerStand(Basis):
    def g(self, *args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", self.repo, *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def version(self, v, betreff):
        os.makedirs(os.path.join(self.repo, "amw"), exist_ok=True)
        with open(os.path.join(self.repo, "amw", "__init__.py"), "w", encoding="utf-8") as f:
            f.write(f'__version__ = "{v}"\n')
        self.g("add", "-A")
        self.g("commit", "-q", "-m", betreff)
        return self.g("rev-parse", "HEAD")

    def test_zweite_aufgabe_auf_demselben_stand_belegt_nicht(self):
        self.repo = os.path.join(self.ordner.name, "repo")
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True, capture_output=True)
        self.version("1.0.0", "basis")
        kern.projekt_ordner_setzen(self.con, self.pid, self.repo)
        self.g("switch", "-q", "-c", "x")
        sha = self.version("1.0.1", "A1 + A2")
        self.pruefung(sha, "offen")                                                               # A1 (self.aid) belegt 1.0.1
        a2 = kern.aufgabe_neu(self.con, self.pid, "TL", "Zwei", "CC1")
        self.assertEqual(versionsnummer.pruefen(self.con, self.pid, sha, a2), "1.0.1")           # gleicher Stand: frei
        self.g("commit", "-q", "--amend", "-m", "nur Betreff anders")
        self.assertEqual(versionsnummer.pruefen(self.con, self.pid, self.g("rev-parse", "HEAD"), a2), "1.0.1")   # gleicher Baum
        with open(os.path.join(self.repo, "neu.txt"), "w") as f:
            f.write("x")
        self.g("add", "-A")
        self.g("commit", "-q", "-m", "mehr")
        with self.assertRaisesRegex(kern.AmwFehler, "schon vergeben"):                            # anderer Baum: belegt
            versionsnummer.pruefen(self.con, self.pid, self.g("rev-parse", "HEAD"), a2)


class Nachwecken(unittest.TestCase):
    setUp, tearDown, anmelden = td.Wecker.setUp, td.Wecker.tearDown, td.Wecker.anmelden   # ohne die Tests dort erneut

    def zurueck(self, minuten):
        t = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - minuten * 60))
        with db.schreiben(self.con):
            self.con.execute("UPDATE empfang SET geweckt_utc = ?, status = 'offen' WHERE agent = 'TL'", (t,))
            self.con.execute("UPDATE nachricht SET zeit_utc = ?", (t,))

    def test_lead_still_einmal_nachwecken(self):
        self.anmelden("TL")
        n, _ = kern.posten(self.con, self.pid, "CC1", "TL", "frage", "Merge-OK für A1?")
        self.d.zustellen()
        self.assertEqual(len(self.gesendet), 1)
        self.zurueck(5)
        self.assertEqual(self.d.nachwecken(), [])                                                 # noch keine 10 min
        self.zurueck(11)
        self.assertEqual(self.d.nachwecken(), [f"TL: #{n}"])
        self.assertTrue(self.gesendet[-1][1].startswith("Nachgeweckt"))
        self.assertIn(f"#{n}", self.gesendet[-1][1])
        self.assertEqual(self.d.nachwecken(), [])                                                 # höchstens einmal je Nachricht

    def test_nicht_wenn_gelesen_oder_geantwortet_oder_kein_lead(self):
        self.anmelden("TL")
        self.anmelden("CC2")
        kern.posten(self.con, self.pid, "CC1", "TL", "frage", "A?")
        kern.posten(self.con, self.pid, "CC1", "CC2", "frage", "B?")                               # CC2 ist kein Lead
        self.d.zustellen()
        self.zurueck(11)
        with db.schreiben(self.con):
            self.con.execute("UPDATE empfang SET geweckt_utc = ? WHERE agent = 'CC2'", ("2000-01-01T00:00:00Z",))
        kern.posten(self.con, self.pid, "TL", "CC1", "antwort", "gleich")                          # TL hat seitdem gesendet
        self.assertEqual(self.d.nachwecken(), [])
        with db.schreiben(self.con):
            self.con.execute("DELETE FROM empfang WHERE agent = 'CC1'")
            self.con.execute("UPDATE nachricht SET zeit_utc = '2000-01-01T00:00:00Z' WHERE von = 'TL'")
            self.con.execute("UPDATE empfang SET status = 'gelesen' WHERE agent = 'TL'")           # gelesen
        self.assertEqual(self.d.nachwecken(), [])


if __name__ == "__main__":
    unittest.main()
