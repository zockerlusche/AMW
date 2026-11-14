"""Release-Takt (A1656): der Dienst stößt an, was ausgeliefert werden kann – einmal je Stand, im Takt sofort/täglich/
Meilenstein, nie für Stände, die schon in main liegen; ohne Takt nichts."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime
import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from amw import betrieb, db, kern, releasetakt


class Takt(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        umgebung = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "daten", "amw.db")})
        umgebung.start()
        self.addCleanup(umgebung.stop)
        self.con = db.anlegen()
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
            self.bogen = db.einfuegen(self.con, "bogen", projekt_id=self.pid, nr=1, titel="M1", angelegt_von="TL", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.repo = os.path.join(self.ordner.name, "repo")
        os.makedirs(self.repo)
        self.g("init", "-q", "-b", "main")
        self.commit("a.txt", "start")
        with db.schreiben(self.con):
            self.con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?", (json.dumps({"ordner": self.repo}), self.pid))

    def g(self, *args):
        return subprocess.run(["git", "-C", self.repo, "-c", "user.name=t", "-c", "user.email=t@t", *args], capture_output=True,
                              text=True, check=True).stdout.strip()

    def commit(self, name, inhalt):
        with open(os.path.join(self.repo, name), "w", encoding="utf-8") as f:
            f.write(inhalt)
        self.g("add", name)
        self.g("commit", "-q", "-m", inhalt)
        return self.g("rev-parse", "HEAD")

    def fertig_zum_ausliefern(self, titel, mit_lauf=True, bogen=True):
        """Zweig mit eigenem Stand, GRÜN, Merge-OK, grüner Gesamtlauf mit genau diesem Stand."""
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel, "CC1")
        if bogen:
            with db.schreiben(self.con):
                self.con.execute("UPDATE aufgabe SET bogen_id = ? WHERE id = ?", (self.bogen, aid))
        self.g("switch", "-q", "-c", f"z{aid}", "main")
        sha = self.commit(f"{titel}.txt", titel)
        self.g("switch", "-q", "main")
        prid = betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", f"z{aid}", sha, aufgabe_id=aid)
        betrieb.pruefung_ergebnis(self.con, self.pid, "TL", prid, "gruen")
        betrieb.freigabe_merge(self.con, self.pid, "TL", aid)
        if mit_lauf:
            with db.schreiben(self.con):
                db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="CC1", beschreibung="Gesamtlauf", status="fertig", rc=0,
                             angemeldet_utc=db.jetzt(), ergebnis=f"rc 0 · {betrieb.stand_text(('', sha, True))}")
        return aid, sha

    def auftraege(self):
        return [r[0] for r in self.con.execute("SELECT kurz FROM nachricht WHERE kurz LIKE 'Bereit zum Ausliefern%' ORDER BY id")]

    def test_aus_und_sofort_einmal_je_stand(self):
        aid, sha = self.fertig_zum_ausliefern("eins")
        self.fertig_zum_ausliefern("ohne_lauf", mit_lauf=False)                 # ohne passenden Gesamtlauf nie bereit
        self.assertEqual(releasetakt.anstossen(self.con, self.pid), [])         # Vorgabe aus
        kern.projekt_einstellen(self.con, self.pid, "TL", release_takt="sofort")
        self.assertEqual(len(releasetakt.anstossen(self.con, self.pid)), 1)
        self.assertEqual(releasetakt.anstossen(self.con, self.pid), [])         # derselbe Stand nicht noch einmal
        self.assertIn(f"A{aid} z{aid}@{sha[:8]}", self.auftraege()[0])
        text = self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE 'Bereit zum Ausliefern%'").fetchone()[0]
        self.assertIn("Schritten eures Projekts", text)                           # fremdes Repo: kein amw release ausliefern
        empf = self.con.execute("SELECT e.agent FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id"
                                " WHERE n.kurz LIKE 'Bereit zum Ausliefern%'").fetchall()
        self.assertEqual([r[0] for r in empf], ["TL"])                             # ohne Merge-Dienst: der Lead

    def test_schon_in_main_ist_nicht_bereit(self):
        aid, sha = self.fertig_zum_ausliefern("eins")
        self.g("merge", "-q", "--ff-only", f"z{aid}")
        self.assertEqual(releasetakt.bereit(self.con, self.pid), [])

    def test_taeglich_ab_uhrzeit_einmal_am_tag(self):
        self.fertig_zum_ausliefern("eins")
        kern.projekt_einstellen(self.con, self.pid, "TL", release_takt="taeglich", release_zeit="18:00")
        tag = datetime.datetime(2026, 11, 14, 17, 59).astimezone()
        self.assertEqual(releasetakt.anstossen(self.con, self.pid, jetzt=tag), [])
        self.assertEqual(len(releasetakt.anstossen(self.con, self.pid, jetzt=tag.replace(hour=18, minute=1))), 1)
        self.fertig_zum_ausliefern("zwei")
        self.assertEqual(releasetakt.anstossen(self.con, self.pid, jetzt=tag.replace(hour=20)), [])   # heute schon geschaut
        self.assertEqual(len(releasetakt.anstossen(self.con, self.pid, jetzt=tag + datetime.timedelta(days=1, hours=1))), 1)
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "TL", release_zeit="25:00")

    def test_meilenstein_erst_wenn_alle_bereit(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", release_takt="meilenstein")
        self.fertig_zum_ausliefern("eins")
        offen = kern.aufgabe_neu(self.con, self.pid, "TL", "noch offen", "CC1")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET bogen_id = ? WHERE id = ?", (self.bogen, offen))
        self.assertEqual(releasetakt.anstossen(self.con, self.pid), [])
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'verworfen', beleg = 'doppelt' WHERE id = ?", (offen,))
        self.assertEqual(len(releasetakt.anstossen(self.con, self.pid)), 1)


if __name__ == "__main__":
    unittest.main()
