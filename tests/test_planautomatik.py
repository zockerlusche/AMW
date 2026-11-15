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


class GitHubMerge(Grund):
    """A1738 (2): gemergte PRs mit „A1234“ und grünen Prüfungen setzen die Aufgabe fertig – nur wo die Betriebsart die
    Verbindung zulässt, höchstens alle 5 Minuten je Projekt, ohne Token in der AMW (gh hält die Anmeldung)."""

    def setUp(self):
        super().setUp()
        self.repo = os.path.join(self.ordner.name, "projekt")
        os.makedirs(self.repo)
        kern.projekt_ordner_setzen(self.con, self.pid, self.repo)
        planautomatik._gh_zuletzt.clear()
        self.addCleanup(planautomatik._gh_zuletzt.clear)
        self.aufrufe = []
        self.prs = []
        if not self._testMethodName.startswith("test_anlass"):          # PR-Logik: Abfrage immer fällig (Anlass eigene Tests)
            p = mock.patch.object(planautomatik, "github_faellig", return_value="Test")
            p.start()
            self.addCleanup(p.stop)

    def laufen(self, befehl, ordner):
        import json
        self.aufrufe.append(befehl)
        if befehl[:2] == ["git", "-C"]:
            return 0, "https://github.com/firma/spiel.git\n"
        return 0, json.dumps(self.prs)

    def art(self, art):
        p = mock.patch("amw.einstellungen.wert", side_effect=lambda k, *x: art if k == "betriebsart" else None)
        p.start()
        self.addCleanup(p.stop)

    def test_gemergt_und_gruen_setzt_fertig(self):
        self.art("cloud")
        a, rot, geraet = self.aufgabe(), self.aufgabe(titel="CI rot"), self.aufgabe(titel="Am Gerät bestätigen")
        kern.aufgabe_status(self.con, self.pid, "CC1", geraet, "wartet", auf="Entwickler")
        self.prs = [{"number": 12, "title": f"A{a}: Karte neu", "body": f"fertig: A{geraet}", "mergedAt": "2026-11-15T07:00:00Z",
                     "mergeCommit": {"oid": "abcdef1234567"}, "statusCheckRollup": [{"conclusion": "SUCCESS"}, {"state": "SUCCESS"}]},
                    {"number": 13, "title": f"A{rot}: Fix", "body": "", "mergeCommit": {"oid": "1111111"},
                     "statusCheckRollup": [{"conclusion": "FAILURE"}]}]
        aus = planautomatik.github_projekt(self.con, self.pid, laufen=self.laufen, jetzt=1000.0)
        self.assertEqual([x["aufgabe"] for x in aus], [a])
        z = self.con.execute("SELECT status, beleg, zusammenfassung FROM aufgabe WHERE id = ?", (a,)).fetchone()
        self.assertEqual((z["status"], z["beleg"]), ("fertig", "abcdef1"))
        self.assertIn("PR #12 gemergt (2026-11-15)", z["zusammenfassung"])
        self.assertEqual((self.status(rot), self.status(geraet)), ("wartet", "wartet"))   # CI rot · wartet auf den Entwickler
        self.assertIn(f"A{a} ← PR #12 (abcdef1).",
                      self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE 'Fertig nach Merge%'").fetchone()[0])

    def test_nur_ausdruecklich_genannte_aufgaben(self):
        """TL P186: bloßes Erwähnen („Vorarbeit für A1235“, „siehe A1200“) setzt nichts fertig – nur A-Nummern am Anfang des
        Titels oder im Text hinter einem Schlüsselwort."""
        f = planautomatik.aufgaben_im_pr
        self.assertEqual(f("A1234: Karte neu", ""), {1234})
        self.assertEqual(f("[A1234] Karte", ""), {1234})
        self.assertEqual(f("A1234, A1235: zwei", ""), {1234, 1235})
        self.assertEqual(f("A1234", None), {1234})
        self.assertEqual(f("Karte", "fertig: A1300"), {1300})
        self.assertEqual(f("Karte", "Closes A1301 und A1302"), {1301, 1302})
        self.assertEqual(f("Vorarbeit für A1235", "siehe A1200"), set())
        self.assertEqual(f("xA1234: nein", "A1234 wird später erledigt"), set())
        self.art("cloud")
        a, b = self.aufgabe(), self.aufgabe(titel="Nur erwähnt")
        self.prs = [{"number": 20, "title": f"Vorarbeit für A{b}", "body": f"fertig: A{a}", "mergeCommit": {"oid": "2222222"},
                     "statusCheckRollup": []}]
        planautomatik.github_projekt(self.con, self.pid, laufen=self.laufen, jetzt=1000.0)
        self.assertEqual((self.status(a), self.status(b)), ("fertig", "wartet"))

    def gh(self, jetzt):
        n = len([b for b in self.aufrufe if b[0] == "gh"])
        planautomatik.github_projekt(self.con, self.pid, laufen=self.laufen, jetzt=jetzt)
        return len([b for b in self.aufrufe if b[0] == "gh"]) > n

    def test_anlass_nicht_mehr_alle_5_minuten(self):
        """A1783 (Marcel 15.11. 19:09/19:15): ohne Anlass keine Abfrage – auch nicht nach 5 Minuten; nach dem Start des Dienstes
        kein Schwall."""
        import time as zeit
        self.art("cloud")
        self.aufgabe()
        t0 = zeit.time()
        self.assertFalse(self.gh(t0))                                         # Start: ab jetzt
        self.assertFalse(self.gh(t0 + 301))                                   # früher: alle 5 min
        self.assertFalse(self.gh(t0 + 3700))                                  # stündlich nur mit offenen Aufgaben mit Zweig

    def test_anlass_merge_ok_lauf_und_meldung(self):
        import time as zeit
        self.art("cloud")
        a = self.aufgabe()
        t0 = zeit.time() - 600
        self.assertFalse(self.gh(t0))
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="TL", art="merge_ok", aufgabe_id=a)
        self.assertTrue(self.gh(t0 + 120))                                    # Merge-OK → nachsehen
        self.assertFalse(self.gh(t0 + 150))                                   # höchstens einmal je Minute, kein neuer Anlass
        kern.posten(self.con, self.pid, "CC1", "TL", "info", "PR #4 gemergt")
        self.assertFalse(self.gh(t0 + 170))                                   # < 1 min seit der letzten Abfrage
        self.assertTrue(self.gh(t0 + 400))                                    # Meldung „gemergt“ → nachsehen

    def test_anlass_stuendlich_nur_mit_offenen_aufgaben_mit_zweig(self):
        import time as zeit
        from amw import betrieb
        self.art("cloud")
        a = self.aufgabe()
        t0 = zeit.time() - 2 * 3600
        self.assertFalse(self.gh(t0))
        betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "a-zweig", "abc1234def", "Punkte", a, ohne_bild="Test") \
            if "ohne_bild" in betrieb.pruefbitte.__code__.co_varnames else betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "a-zweig", "abc1234def", "Punkte", a)
        with db.schreiben(self.con):                                          # die Prüfbitte ist kein Anlass – nur „offen mit Zweig“
            self.con.execute("UPDATE nachricht SET zeit_utc = '2000-01-01T00:00:00Z'")
        self.assertTrue(self.gh(t0 + 3700))

    def test_nur_dieser_pc_fragt_github_nie(self):
        self.art("pc")
        self.aufgabe()
        self.assertEqual(planautomatik.github_projekt(self.con, self.pid, laufen=self.laufen, jetzt=1000.0), [])
        self.assertFalse([b for b in self.aufrufe if b[0] == "gh"])

    def test_ohne_projektordner_nichts(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE projekt SET einstellungen = '{}' WHERE id = ?", (self.pid,))
        self.art("cloud")
        self.assertEqual(planautomatik.github_projekt(self.con, self.pid, laufen=self.laufen, jetzt=1000.0), [])
        self.assertEqual(self.aufrufe, [])


class MeilensteinFertig(Grund):
    """A1742 (Marcel W2153; GlassWorld: B0/B1/B3 standen tagelang auf geplant): sind alle Aufgaben fertig, schlägt die AMW das
    Abschließen vor – oder schließt selbst ab; die Versions-Pflicht bleibt Voraussetzung."""

    def bogen(self, *stati):
        from amw import planung
        bid = planung.bogen_neu(self.con, self.pid, "TL", "Karte", ziel="z", abnahme="a")
        for i, st in enumerate(stati):
            a = self.aufgabe(titel=f"Schritt {i}")
            planung.schritt_setzen(self.con, self.pid, "TL", aid=a, bogen_id=bid)
            with db.schreiben(self.con):
                self.con.execute("UPDATE aufgabe SET status = ?, beleg = 'x', fertig_utc = ? WHERE id = ?",
                                 (st, db.jetzt() if st != "wartet" else None, a))
        return bid

    def bstatus(self, bid):
        return self.con.execute("SELECT status FROM bogen WHERE id = ?", (bid,)).fetchone()[0]

    def test_vorschlag_einmal_je_stand(self):
        offen, alle = self.bogen("fertig", "wartet"), self.bogen("fertig", "verworfen")
        self.assertEqual(planautomatik.meilenstein_projekt(self.con, self.pid), [(alle, "vorschlag")])
        self.assertEqual(self.bstatus(alle), "geplant")                                   # nur ein Vorschlag
        m = self.con.execute("SELECT art, kurz, text FROM nachricht WHERE kurz LIKE 'Meilenstein%abschließen?'").fetchone()
        self.assertEqual(m["art"], "meldung")
        self.assertIn(f"amw bogen status {alle} fertig", m["text"])
        self.assertEqual(planautomatik.meilenstein_projekt(self.con, self.pid), [])   # nicht noch einmal
        self.assertEqual(self.bstatus(offen), "geplant")

    def test_automatisch_und_versions_pflicht(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", meilenstein_fertig="automatisch", versionen="empfohlen")
        bid = self.bogen("fertig", "fertig")
        self.assertEqual(planautomatik.meilenstein_projekt(self.con, self.pid), [(bid, "fertig")])
        self.assertEqual(self.bstatus(bid), "fertig")
        kern.projekt_einstellen(self.con, self.pid, "TL", versionen="pflicht")
        bid2 = self.bogen("fertig")
        self.assertEqual(planautomatik.meilenstein_projekt(self.con, self.pid), [(bid2, "vorschlag")])   # Version fehlt
        self.assertEqual(self.bstatus(bid2), "geplant")
        self.assertIn("Automatisch ging es nicht", self.con.execute(
            "SELECT text FROM nachricht WHERE kurz LIKE ? ORDER BY id DESC", (f"Meilenstein {bid2}%",)).fetchone()[0])

    def test_aus_ohne_planung_automatisch(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", plan_automatik="aus")
        self.bogen("fertig")
        self.assertEqual(planautomatik.meilenstein_projekt(self.con, self.pid), [])


if __name__ == "__main__":
    unittest.main()
