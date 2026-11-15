"""Planung automatisch (Marcel 15.11., W2153). A1741: Ein Lauf zu einer eigenen, noch nicht begonnenen Aufgabe setzt sie auf
„läuft“ – Aufgabe aus --aufgabe, aus „A1234“ in der Beschreibung oder aus dem Zweig im Ordner des Laufs."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from amw import betrieb, db, kern, planautomatik


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Eins", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        for k in ("CC1", "CC2"):
            kern.agent_neu(self.con, self.pid, k)
        for ziel, name, wert in ((betrieb, "cpu_laeufe", 2), (betrieb, "speicher_frei_gb", (32.0, 32.0))):
            p = mock.patch.object(ziel, name, return_value=wert)
            p.start()
            self.addCleanup(p.stop)

    def aufgabe(self, agent="CC1", titel="Seite bauen"):
        return kern.aufgabe_neu(self.con, self.pid, "TL", titel, agent)

    def lauf(self, agent="CC1", text="Gesamtlauf", **k):
        return betrieb.lauf_start(self.con, self.pid, agent, text, warten=True, speicher_frei=32.0, **k)

    def status(self, aid):
        return self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (aid,)).fetchone()[0]


class LaufStartetAufgabe(Grund):
    def test_mit_aufgabe_beschreibung_oder_zweig(self):
        a = self.aufgabe()
        self.assertEqual(self.status(a), "wartet")
        lid = self.lauf(aufgabe_id=a)
        self.assertEqual(self.status(a), "laeuft")
        e = self.con.execute("SELECT von, text FROM plan_ereignis WHERE art = 'auto_laeuft' AND aufgabe_id = ?", (a,)).fetchone()
        self.assertEqual((e["von"], e["text"]), ("AMW", f"L{lid} (aufgabe)"))
        kern.aufgabe_status(self.con, self.pid, "CC1", a, "fertig", beleg="abc1234")

        b = self.aufgabe(titel="Zweite")
        self.lauf(text=f"Tests A{b} Handy")                                      # aus der Beschreibung
        self.assertEqual(self.status(b), "laeuft")
        kern.aufgabe_status(self.con, self.pid, "CC1", b, "fertig", beleg="abc1234")

        c = self.aufgabe(titel="Dritte")
        repo = os.path.join(self.ordner.name, "repo")
        os.makedirs(repo)
        git = lambda *x: subprocess.run(["git", "-C", repo, *x], capture_output=True, check=True)
        git("init", "-q")
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x")
        git("checkout", "-q", "-b", f"a{c}-2")
        self.lauf(text="Gesamtlauf", ordner=repo)                                 # aus dem Zweig im Ordner des Laufs
        self.assertEqual(self.status(c), "laeuft")
        self.assertEqual(planautomatik.aufgabe_zum_lauf(None, "L12 ohne Nummer", repo), (c, "zweig"))
        self.assertEqual(planautomatik.aufgabe_zum_lauf(None, "BA12 und xA3", None), (None, None))   # nur ein eigenes „A1234“

    def test_nicht_wenn_sie_wartet_auf_jemanden_fremd_ist_oder_schon_etwas_laeuft(self):
        a = self.aufgabe()
        kern.aufgabe_status(self.con, self.pid, "CC1", a, "wartet", auf="TL")    # Prüfung liegt beim Lead
        self.lauf(aufgabe_id=a)
        self.assertEqual(self.status(a), "wartet")

        fremd = self.aufgabe(agent="CC2", titel="Gehört CC2")
        self.lauf(agent="CC1", text=f"Hilfe für A{fremd}")
        self.assertEqual(self.status(fremd), "wartet")

        eins, zwei = self.aufgabe(titel="Eins"), self.aufgabe(titel="Zwei")
        kern.aufgabe_status(self.con, self.pid, "CC1", eins, "start")
        self.lauf(aufgabe_id=zwei)                                                # eins nach dem anderen – Lauf startet trotzdem
        self.assertEqual((self.status(eins), self.status(zwei)), ("laeuft", "wartet"))
        self.assertEqual(self.con.execute("SELECT count(*) FROM lauf WHERE aufgabe_id = ?", (zwei,)).fetchone()[0], 1)

    def test_abschaltbar_je_projekt(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", plan_automatik="aus")
        a = self.aufgabe()
        self.lauf(aufgabe_id=a)
        self.assertEqual(self.status(a), "wartet")


if __name__ == "__main__":
    unittest.main()
