"""Release-Kette als ein Befehl (A1644): Vorbedingungen (GRÜN, Gesamtlauf, Fast-Forward, sauberer Baum, neuer Tag) halten die
Kette an, bevor sich etwas ändert; sonst Sicherung → main → Tag → Dienst (Version, Schema) → Push → GitHub-Release →
Web-Abzug als leichter Lauf der Kette → Versionszeile → eine Info. Mit echten Git-Repositories (Ursprung + Arbeitskopie); nur „gh“
und der Neustart des Dienstes sind nachgebildet."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from amw import auslieferung, betrieb, db, kern, wissen

GIT = shutil.which("git")


@unittest.skipUnless(GIT, "git nicht installiert")
class Kette(unittest.TestCase):
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
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.ursprung = os.path.join(self.ordner.name, "ursprung.git")
        self.repo = os.path.join(self.ordner.name, "repo")
        self.g("init", "-q", "--bare", "-b", "main", self.ursprung, ordner=self.ordner.name)
        self.g("clone", "-q", self.ursprung, self.repo, ordner=self.ordner.name)
        with db.schreiben(self.con):
            self.con.execute("UPDATE agent SET ordner = ? WHERE kennung = 'CC1'", (self.repo,))
        self.stand("1.0.0", "Anfang")
        self.g("push", "-q", "origin", "main")
        self.g("switch", "-q", "-c", "neu")
        self.sha = self.stand("1.1.0", "Neues Ding")
        self.g("switch", "-q", "main")
        self.extern_aufrufe = []

    def g(self, *args, ordner=None):
        r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=ordner or self.repo,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def stand(self, version, titel):
        os.makedirs(os.path.join(self.repo, "amw"), exist_ok=True)
        dateien = {"amw/__init__.py": f'__version__ = "{version}"\n', "amw/db.py": f"SCHEMA_VERSION = {db.SCHEMA_VERSION}\n",
                   "CHANGELOG.md": f"# Änderungen\n\n## {version} – 13.11.2026 · {titel}\n- **Neu:** {titel} für alle.\n\n## 0.1.0 – alt\n- alt\n"}
        for pfad, inhalt in dateien.items():
            with open(os.path.join(self.repo, pfad), "w", encoding="utf-8", newline="") as f:
                f.write(inhalt)
        self.g("add", *dateien)
        self.g("-c", "commit.gpgsign=false", "commit", "-q", "-m", f"{version}: {titel}")
        return self.g("rev-parse", "HEAD")

    def extern(self, befehl, ordner):
        self.extern_aufrufe.append(befehl)
        if befehl[0] == "gh":
            notizen = befehl[befehl.index("--notes-file") + 1]
            with open(notizen, encoding="utf-8") as f:
                self.notizen = f.read()
            return 0, "https://example.invalid/release"
        if "dienst" in befehl:
            return 0, "Dienst neu gestartet"
        if "web" in befehl or "origin/web" in befehl or any(str(x).startswith("web-") for x in befehl):
            return 0, ""                                                     # Web-Abzug: im Test-Repo gibt es keinen web-Ordner
        return auslieferung._laufen(befehl, ordner)

    def kette(self, version="1.1.0"):
        return auslieferung.Kette(self.con, self.pid, "CC1", self.repo, extern=self.extern, start_version=lambda: version, ausgabe=lambda _: None)

    def gruen(self, merge_ok=True):
        self.aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Neues Ding", "CC1")
        betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "neu", self.sha, "x", self.aid)
        prid = self.con.execute("SELECT max(id) FROM pruefung").fetchone()[0]
        betrieb.pruefung_ergebnis(self.con, self.pid, "TL", prid, "gruen")
        if merge_ok:
            betrieb.freigabe_merge(self.con, self.pid, "TL", self.aid)

    def gesamtlauf(self, sha=None, sauber=True):
        """Ein grüner Lauf, der beim Start diesen Stand gemerkt hat (wie amw lauf ausfuehren ihn ins Ergebnis schreibt)."""
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="CC1", beschreibung=f"Gesamtlauf 1.1.0 {self.sha[:7]}",
                                status="fertig", rc=0, angemeldet_utc=db.jetzt(),
                                ergebnis=f"rc 0 · {betrieb.stand_text(('', sha or self.sha, sauber))} · Ausgabe: x.txt")

    def test_ganze_kette(self):
        self.gruen()
        self.gesamtlauf()
        r = self.kette().ausliefern("neu")
        self.assertEqual(r["version"], "1.1.0")
        self.assertEqual(self.g("rev-parse", "main"), self.sha)                                   # Fast-Forward
        self.assertEqual(self.g("rev-parse", "v1.1.0^{commit}"), self.sha)                        # Tag
        self.assertEqual(self.g("rev-parse", "main", ordner=self.ursprung), self.sha)             # gepusht
        self.assertEqual(self.g("rev-parse", "v1.1.0^{commit}", ordner=self.ursprung), self.sha)
        self.assertIn("**Neu:** Neues Ding für alle.", self.notizen)                              # Notizen aus dem CHANGELOG
        self.assertTrue(any(b[0] == "gh" and "v1.1.0" in b for b in self.extern_aufrufe))
        w = self.con.execute("SELECT * FROM lauf WHERE id = ?", (r["web_lauf"],)).fetchone()        # Web-Abzug: rechnet die Kette selbst
        self.assertEqual((w["schwer"], w["status"], w["rc"], w["ordner"]), (0, "fertig", 0, self.repo))
        self.assertIn(["git", "subtree", "split", "--prefix", "web", "-b", "web-110"], self.extern_aufrufe)
        self.assertIn(["git", "push", "origin", "web-110:web"], self.extern_aufrufe)
        rel = self.con.execute("SELECT version, titel FROM release WHERE id = ?", (r["release"],)).fetchone()
        self.assertEqual(tuple(rel), ("1.1.0", "Neues Ding"))                                      # Versionszeile ohne TL
        info = self.con.execute("SELECT n.art, n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = 'TL'"
                                " AND n.kurz LIKE 'Version 1.1.0 live%'").fetchall()
        self.assertEqual([tuple(x) for x in info], [("info", "Version 1.1.0 live – Neues Ding")])  # eine Info, weckt nicht
        self.assertTrue(any(n.endswith(".db") for n in os.listdir(os.path.dirname(db.db_pfad())) if n.startswith("sicherung")))

    def ohne_aenderung(self, wort, **kw):
        with self.assertRaises(auslieferung.Stopp) as e:
            self.kette().ausliefern("neu", **kw)
        self.assertIn(wort, str(e.exception))
        self.assertIn("erledigt: noch nichts", str(e.exception))
        self.assertNotEqual(self.g("rev-parse", "main"), self.sha)                                # nichts verändert
        self.assertEqual(self.con.execute("SELECT count(*) FROM release").fetchone()[0], 0)

    def test_ohne_gruen_ohne_gesamtlauf_halt_vor_jeder_aenderung(self):
        self.gesamtlauf()
        self.ohne_aenderung("keine grüne Prüfung")
        with db.schreiben(self.con):                                                               # Läufe löscht man nicht (Verlauf)
            self.con.execute("UPDATE lauf SET ergebnis = 'rc 0 · Stand 0000000 sauber'")              # anderer Stand
        self.gruen()
        self.ohne_aenderung("Gesamtlauf")
        with self.assertRaises(kern.AmwFehler):                                                     # Ausnahme nie vom Coder
            betrieb.freigabe_merge(self.con, self.pid, "CC1", self.aid, ausnahme="ich finde das reicht")
        betrieb.freigabe_merge(self.con, self.pid, "TL", self.aid, ausnahme="L1412 + Gesamtlauf auf dem Vorgänger")   # nur vom Lead
        r = self.kette().ausliefern("neu")
        self.assertEqual(r["version"], "1.1.0")
        info = self.con.execute("SELECT n.text FROM nachricht n WHERE n.kurz LIKE 'Version 1.1.0 live%'").fetchone()[0]
        self.assertIn("Ohne Gesamtlauf: TL: L1412", info)

    def test_ohne_merge_ok_halt_und_ruecknahme_zaehlt(self):
        self.gesamtlauf()
        self.gruen(merge_ok=False)
        self.ohne_aenderung("kein Merge-OK für A")
        betrieb.freigabe_merge(self.con, self.pid, "TL", self.aid)
        betrieb.freigabe_merge(self.con, self.pid, "TL", self.aid, zurueck=True)                  # zurückgenommen: gilt nicht
        self.ohne_aenderung("kein Merge-OK für A")
        betrieb.freigabe_merge(self.con, self.pid, "TL", self.aid, zweig="anderer")               # OK nur für einen anderen Zweig
        self.ohne_aenderung("kein Merge-OK für A")

    def test_ausnahme_endet_mit_neuem_merge_ok(self):
        self.gruen(merge_ok=False)
        betrieb.freigabe_merge(self.con, self.pid, "TL", self.aid, ausnahme="Grund")
        self.assertIsNotNone(betrieb.gesamtlauf_ausnahme(self.con, self.pid, self.aid))
        betrieb.freigabe_merge(self.con, self.pid, "TL", self.aid)                                  # neues OK ohne Ausnahme
        self.assertIsNone(betrieb.gesamtlauf_ausnahme(self.con, self.pid, self.aid))
        self.ohne_aenderung("Gesamtlauf")

    def test_gesamtlauf_zaehlt_nur_mit_genau_diesem_sauberen_stand(self):
        """TL #24259: Ein Lauf hieß „… 3723c57“, lief aber auf 08aa4e1 – die Beschreibung allein beweist nichts."""
        self.gruen()
        anderer = self.g("rev-parse", "main")
        lid = self.gesamtlauf(sha=anderer)                                                   # Beschreibung passt, Stand nicht
        self.ohne_aenderung("genau")
        with self.assertRaises(auslieferung.Stopp) as e:
            self.kette().ausliefern("neu", gesamtlauf=f"L{lid}")
        self.assertIn("nicht genau", str(e.exception))
        self.gesamtlauf(sauber=False)                                                          # richtiger Stand, aber geändert
        self.ohne_aenderung("genau")
        self.gesamtlauf()                                                                      # so zählt er
        self.assertEqual(self.kette().ausliefern("neu")["version"], "1.1.0")

    def test_pruefstand_folgt_dem_cd_und_merkt_aenderungen(self):
        self.assertEqual(betrieb.pruefstand([f"cd /d {self.repo} && echo x"], self.ordner.name)[1:], (self.g("rev-parse", "HEAD"), True))
        self.assertIsNone(betrieb.pruefstand(["echo x"], self.ordner.name))                  # kein Git-Ordner
        with open(os.path.join(self.repo, "CHANGELOG.md"), "a", encoding="utf-8") as f:
            f.write("geändert\n")
        self.assertFalse(betrieb.pruefstand(["echo x"], self.repo)[2])
        self.assertIn("geändert", betrieb.stand_text(betrieb.pruefstand(["echo x"], self.repo)))

    def test_kurzer_sha_in_der_pruefbitte(self):
        """Befund 14.11.: Prüfbitten mit kurzem SHA („39ca74a“) fand die Kette nie. Neue Prüfbitten speichern den vollen Stand
        (Projektordner), ältere mit kurzem SHA zählen trotzdem."""
        with db.schreiben(self.con):
            self.con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?", (json.dumps({"ordner": self.repo}), self.pid))
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Kurz", "CC1")
        prid = betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "neu", self.sha[:7], "x", aid)
        self.assertEqual(self.con.execute("SELECT sha FROM pruefung WHERE id = ?", (prid,)).fetchone()[0], self.sha)   # voll gespeichert
        with db.schreiben(self.con):
            self.con.execute("UPDATE pruefung SET sha = ?, ergebnis = 'gruen' WHERE id = ?", (self.sha[:7], prid))     # wie eine alte Prüfbitte
        self.assertTrue(betrieb.ist_gruen(self.con, self.pid, self.sha))
        with db.schreiben(self.con):
            self.con.execute("UPDATE pruefung SET sha = ? WHERE id = ?", (self.sha[:5], prid))                         # zu kurz: zählt nicht
        self.assertIsNone(betrieb.ist_gruen(self.con, self.pid, self.sha))

    def test_pruefstufe_niedrig_ohne_pruefbitte(self):
        """A1656 (TL 14.11.): nur Doku/Tests (+ Versionsnummer) geht mit „pruefstufen = an“ ohne Prüfbitte – aber nur mit
        Merge-OK und einem echten grünen Gesamtlauf auf genau dem Stand, nie mit der Ausnahme."""
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Nur Doku", "CC1")
        betrieb.freigabe_merge(self.con, self.pid, "TL", aid)
        self.ohne_aenderung("keine grüne Prüfung")                                           # Stufen aus: wie bisher
        kern.projekt_einstellen(self.con, self.pid, "TL", pruefstufen="an")
        self.ohne_aenderung("--aufgabe")
        betrieb.freigabe_merge(self.con, self.pid, "TL", aid, ausnahme="geht schon")
        with self.assertRaises(auslieferung.Stopp) as e:
            self.kette().ausliefern("neu", aufgabe=aid)
        self.assertIn("Gesamtlauf", str(e.exception))                                         # Ausnahme zählt hier nicht
        self.gesamtlauf()
        r = self.kette().ausliefern("neu", aufgabe=aid)
        self.assertEqual(r["version"], "1.1.0")

    def gruen_auf(self, zweig, sha, titel):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel, "CC1")
        prid = betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", zweig, sha, "x", aid)
        betrieb.pruefung_ergebnis(self.con, self.pid, "TL", prid, "gruen")
        betrieb.freigabe_merge(self.con, self.pid, "TL", aid, zweig)
        return aid

    def test_zwischenversion_wird_mit_getaggt_und_eingetragen(self):
        """TL #24530: 1.94.1 ging über die Kette, 1.94.0 darunter blieb ohne Versionszeile. Jetzt bekommt jede Zwischenversion
        im selben Stand Tag, GitHub-Release (nicht „neueste“) und Versionszeile – aufsteigend vor der obersten."""
        self.g("switch", "-q", "neu")
        oben = self.stand("1.1.1", "Kleiner Nachtrag")
        self.g("switch", "-q", "main")
        self.gruen_auf("neu", oben, "Nachtrag")
        self.gesamtlauf(sha=oben)
        r = self.kette("1.1.1").ausliefern("neu")
        self.assertEqual(r["version"], "1.1.1")
        self.assertEqual(self.g("rev-parse", "v1.1.0^{commit}"), self.sha)                       # Zwischenversion getaggt
        self.assertEqual(self.g("rev-parse", "v1.1.0^{commit}", ordner=self.ursprung), self.sha)  # und gepusht
        gh = [b for b in self.extern_aufrufe if b[0] == "gh"]
        self.assertEqual([(b[3], b[-1]) for b in gh], [("v1.1.0", "--latest=false"), ("v1.1.1", "--latest")])
        self.assertEqual([x[0] for x in self.con.execute("SELECT version FROM release WHERE art = 'version' ORDER BY id")], ["1.1.0", "1.1.1"])

    def test_reihenfolge_kleinere_gruene_version_zuerst(self):
        self.gruen_auf("neu", self.sha, "Kleiner")                                                 # 1.1.0 grün + Merge-OK, nicht draußen
        self.g("switch", "-q", "-c", "anders", "main")
        anders = self.stand("1.2.0", "Größer")
        self.g("switch", "-q", "main")
        self.gruen_auf("anders", anders, "Größer")
        self.gesamtlauf(sha=anders)
        with self.assertRaises(auslieferung.Stopp) as e:
            self.kette("1.2.0").ausliefern("anders")
        self.assertIn("Reihenfolge", str(e.exception))
        self.assertIn("1.1.0", str(e.exception))
        self.assertIn("erledigt: noch nichts", str(e.exception))

    def test_version_nachtragen_nur_kleiner_und_mit_tag(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?", (json.dumps({"ordner": self.repo}), self.pid))
        wissen.release_version(self.con, self.pid, "TL", "1.2.0", "Später")
        with self.assertRaises(kern.AmwFehler) as e:                                               # Tag fehlt
            wissen.release_version(self.con, self.pid, "TL", "1.1.0", None, nachtrag=True)
        self.assertIn("Git-Tag v1.1.0", str(e.exception))
        self.g("tag", "v1.1.0", self.sha)
        with self.assertRaises(kern.AmwFehler):                                                    # nur der Lead
            wissen.release_version(self.con, self.pid, "CC1", "1.1.0", None, nachtrag=True)
        with self.assertRaises(kern.AmwFehler):                                                    # nicht größer als die letzte
            wissen.release_version(self.con, self.pid, "TL", "1.3.0", None, nachtrag=True)
        wissen.release_version(self.con, self.pid, "TL", "1.1.0", None, nachtrag=True)
        r = self.con.execute("SELECT titel, text_oeffentlich, commit_sha FROM release WHERE version = '1.1.0'").fetchone()
        self.assertEqual((r[0], r[2]), ("Neues Ding", self.sha[:7]))                               # Titel und Text aus dem CHANGELOG
        self.assertIn("Neues Ding für alle", r[1])
        self.assertEqual(kern.versions_stand(self.con, self.pid)["letzte"], "1.2.0")              # die höchste bleibt die letzte

    def test_kein_fast_forward_und_schmutziger_baum(self):
        self.gruen()
        self.gesamtlauf()
        with open(os.path.join(self.repo, "dreck.txt"), "w") as f:
            f.write("x")
        self.g("add", "dreck.txt")
        self.ohne_aenderung("ungesicherte Änderungen")
        self.g("rm", "-q", "--cached", "dreck.txt")
        os.remove(os.path.join(self.repo, "dreck.txt"))
        self.stand("1.0.1", "Dazwischen")                                                          # main ist weitergelaufen
        self.ohne_aenderung("kein Vorfahre")

    def test_dienst_meldet_falsche_version_stopp_mit_stand(self):
        self.gruen()
        self.gesamtlauf()
        with mock.patch.object(auslieferung, "DIENST_WARTEN_S", 0), mock.patch.object(auslieferung.time, "sleep"):
            with self.assertRaises(auslieferung.Stopp) as e:
                self.kette(version="1.0.0").ausliefern("neu")
        self.assertIn("Dienst neu", str(e.exception))
        self.assertIn("Tag v1.1.0", str(e.exception))                                            # was schon erledigt ist
        self.assertEqual(self.g("rev-parse", "main", ordner=self.ursprung), self.g("rev-parse", "main~1"))   # nicht gepusht

    def test_nur_im_terminal(self):
        from amw import bruecke
        with self.assertRaises(ValueError):
            bruecke.argumente({"args": ["release", "ausliefern", "--zweig", "neu"]}, self.ordner.name, von="TL", projekt="P")


if __name__ == "__main__":
    unittest.main()
