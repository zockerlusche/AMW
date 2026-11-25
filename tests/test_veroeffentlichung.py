"""A1928 (TH158): Releases in drei Ebenen. `release ausliefern` ist lokal live (Fast-Forward, lokaler Tag, Dienst,
Versionszeile, Web-Abzug – ohne Push von main/Tags und ohne GitHub-Release). Veröffentlicht wird, wenn der Mensch einen fertigen
Meilenstein abnimmt: einmal, Push von main und allen offenen Tags, ein GitHub-Release mit allen CHANGELOG-Abschnitten.
veroeffentlichen = sofort: wie früher."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import unittest
from unittest import mock

from amw import aktionen, auslieferung, cli, db, kern, planung, veroeffentlichung, workbench
from tests import test_auslieferung as ta


class Ebenen(unittest.TestCase):
    setUp_kette, g, stand, extern, kette, gruen, gesamtlauf = (ta.Kette.setUp, ta.Kette.g, ta.Kette.stand, ta.Kette.extern, ta.Kette.kette,
                                                               ta.Kette.gruen, ta.Kette.gesamtlauf)        # die Kette ohne ihre Tests erneut

    def setUp(self):
        self.setUp_kette()
        kern.projekt_einstellen(self.con, self.pid, "TL", veroeffentlichen="meilenstein")      # die Vorgabe
        kern.projekt_ordner_setzen(self.con, self.pid, self.repo)

    def fern(self, ref):
        r = __import__("subprocess").run(["git", "rev-parse", "-q", "--verify", ref], cwd=self.ursprung, capture_output=True, text=True)
        return r.stdout.strip() or None

    def bogen_fertig(self):
        with db.schreiben(self.con):
            bid = db.einfuegen(self.con, "bogen", projekt_id=self.pid, nr=7, titel="Stufe 7", status="fertig", angelegt_von="TL",
                               angelegt_utc=db.jetzt(), fertig_utc=db.jetzt())
        return bid

    def lauf(self, befehl, ordner):                                                            # gh nachgemacht, git echt
        self.extern_aufrufe.append(befehl)
        if befehl[0] == "gh":
            with open(befehl[befehl.index("--notes-file") + 1], encoding="utf-8") as f:
                self.notizen = f.read()
            return 0, "https://example.invalid/release"
        return veroeffentlichung._laufen(befehl, ordner)

    def test_lokal_live_ohne_push_und_github_release(self):
        self.assertEqual(veroeffentlichung.modus(self.con, self.pid), "meilenstein")
        vorher = self.fern("main")
        self.gruen()
        self.gesamtlauf()
        r = self.kette().ausliefern("neu")
        self.assertEqual((r["version"], self.g("rev-parse", "main")), ("1.1.0", self.sha))      # lokal: Fast-Forward
        self.assertEqual(self.g("rev-parse", "v1.1.0^{commit}"), self.sha)                    # lokaler Tag
        self.assertEqual(self.fern("main"), vorher)                                       # nicht gepusht
        self.assertIsNone(self.fern("refs/tags/v1.1.0"))
        self.assertFalse([b for b in self.extern_aufrufe if b[0] == "gh"])                    # kein GitHub-Release
        self.assertEqual(self.g("rev-parse", "origin/web^{tree}"), self.g("rev-parse", f"{self.sha}:web"))   # Web-Abzug bleibt
        self.assertTrue(self.con.execute("SELECT 1 FROM plan_ereignis WHERE art = 'lokal_live' AND text LIKE '%1.1.0%'").fetchone())
        info = self.con.execute("SELECT kurz, text FROM nachricht WHERE kurz LIKE 'Version 1.1.0 %'").fetchone()
        self.assertEqual(info["kurz"], "Version 1.1.0 lokal live – Neues Ding")
        self.assertIn("veröffentlicht wird bei der Abnahme des Meilensteins", info["text"])
        self.assertEqual(veroeffentlichung.offen(self.repo), ["v1.1.0"])

    def test_abnehmen_veroeffentlicht_einmal_und_fuer_dich(self):
        self.gruen()
        self.gesamtlauf()
        self.kette().ausliefern("neu")
        self.assertEqual(veroeffentlichung.zur_abnahme(self.con, self.pid), [])               # noch kein fertiger Meilenstein
        bid = self.bogen_fertig()
        self.assertEqual([b["id"] for b in veroeffentlichung.zur_abnahme(self.con, self.pid)], [bid])
        self.assertEqual([b["id"] for b in workbench.daten_start(self.con, self.pid)["zur_abnahme"]], [bid])   # „Für dich“
        with self.assertRaisesRegex(kern.AmwFehler, "nur der Mensch"):
            veroeffentlichung.abnehmen(self.con, self.pid, "TL", bid, lauf=self.lauf)
        text = veroeffentlichung.abnehmen(self.con, self.pid, kern.ENTWICKLER, bid, lauf=self.lauf)
        self.assertIn("M7 abgenommen", text)                                        # A2089: die Projektnummer
        self.assertEqual(self.fern("main"), self.sha)                                     # jetzt gepusht
        self.assertEqual(self.fern("refs/tags/v1.1.0^{commit}"), self.sha)
        gh = [b for b in self.extern_aufrufe if b[0] == "gh"]
        self.assertEqual(len(gh), 1)
        self.assertIn("v1.1.0", gh[0])
        self.assertIn("**Neu:** Neues Ding für alle.", self.notizen)
        self.assertEqual(veroeffentlichung.zur_abnahme(self.con, self.pid), [])               # erledigt
        self.assertEqual(veroeffentlichung.offen(self.repo), [])
        an = {r[0] for r in self.con.execute("SELECT e.agent FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id"
                                               " WHERE n.kurz LIKE 'Veröffentlicht: 1.1.0%'")}
        self.assertEqual(an, {"TL", kern.ENTWICKLER})

    def test_mehrere_versionen_ein_release(self):
        self.g("tag", "v1.1.0", self.sha)
        self.g("merge", "-q", "--ff-only", self.sha)
        with open(os.path.join(self.repo, "CHANGELOG.md"), "w", encoding="utf-8", newline="") as f:
            f.write("# Änderungen\n\n## 1.2.0 – 22.11.2026 · Zweites\n- **Neu:** Zweites.\n\n## 1.1.0 – 13.11.2026 · Neues Ding\n"
                    "- **Neu:** Neues Ding für alle.\n\n## 1.0.0 – alt\n- alt\n")
        self.g("add", "CHANGELOG.md")
        self.g("-c", "commit.gpgsign=false", "commit", "-q", "-m", "1.2.0")
        self.g("tag", "v1.2.0")
        self.assertEqual(veroeffentlichung.offen(self.repo), ["v1.1.0", "v1.2.0"])
        text = veroeffentlichung.veroeffentlichen(self.con, self.pid, kern.ENTWICKLER, lauf=self.lauf)
        self.assertEqual(text, "Veröffentlicht: 1.2.0 (mit 1.1.0) – main und Tags gepusht, ein GitHub-Release mit allen Abschnitten")
        gh = [b for b in self.extern_aufrufe if b[0] == "gh"]
        self.assertEqual([b[3] for b in gh], ["v1.2.0"])                                     # EIN Release, die neueste Nummer
        self.assertIn("## 1.2.0 – 22.11.2026 · Zweites", self.notizen)
        self.assertIn("## 1.1.0 – 13.11.2026 · Neues Ding", self.notizen)
        self.assertLess(self.notizen.index("## 1.2.0"), self.notizen.index("## 1.1.0"))       # neueste zuerst
        self.assertIsNotNone(self.fern("refs/tags/v1.1.0"))
        self.assertIsNotNone(self.fern("refs/tags/v1.2.0"))

    def test_nur_fertige_und_nicht_aus_einer_sitzung_nicht_online(self):
        with db.schreiben(self.con):
            bid = db.einfuegen(self.con, "bogen", projekt_id=self.pid, nr=8, titel="Offen", status="aktiv", angelegt_von="TL",
                               angelegt_utc=db.jetzt())
        with self.assertRaisesRegex(kern.AmwFehler, "nur ein fertiger Meilenstein"):
            veroeffentlichung.abnehmen(self.con, self.pid, kern.ENTWICKLER, bid, lauf=self.lauf)
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_AGENT": "", "CLAUDECODE": "1", "CLAUDE_CODE_MESSAGING_SOCKET": ""}), \
                contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "P", "--von", "Entwickler", "bogen", "abnehmen", str(bid)])
        self.assertNotEqual(rc, 0)
        self.assertIn("nicht aus einer Agenten-Sitzung", aus.getvalue())
        with self.assertRaisesRegex(aktionen.Ungueltig, "am PC"):
            aktionen.ausfuehren(self.con, self.pid, "/api/bogen/abnehmen", {"bogen": bid}, kanal="netz")
        with mock.patch.dict(os.environ, {"AMW_AGENT": "", "CLAUDECODE": "1", "CLAUDE_CODE_MESSAGING_SOCKET": ""}), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "P", "--von", "Entwickler", "projekt", "einstellen", "veroeffentlichen=sofort"])
        self.assertNotEqual(rc, 0)                                                            # gesperrt wie Rechte
        self.assertEqual(veroeffentlichung.modus(self.con, self.pid), "meilenstein")

    def test_sofort_wie_frueher_und_keine_abnahme_noetig(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", veroeffentlichen="sofort")
        self.gruen()
        self.gesamtlauf()
        self.kette().ausliefern("neu")
        self.assertEqual(self.fern("main"), self.sha)
        self.assertTrue([b for b in self.extern_aufrufe if b[0] == "gh"])
        self.bogen_fertig()
        self.assertEqual(veroeffentlichung.zur_abnahme(self.con, self.pid), [])               # nichts abzunehmen


if __name__ == "__main__":
    unittest.main()
