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
        kern.projekt_einstellen(self.con, self.pid, "TL", veroeffentlichen="sofort")   # A1928: hier die Kette wie bisher (mit Push)
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
        os.makedirs(os.path.join(self.repo, "web"), exist_ok=True)
        dateien = {"amw/__init__.py": f'__version__ = "{version}"\n', "amw/db.py": f"SCHEMA_VERSION = {db.SCHEMA_VERSION}\n",
                   **({"web/VERSION": "1\n"} if version == "1.0.0" else {}),           # web/ nur im ersten Stand (sonst „sichtbar“)
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
        self.assertEqual([b[-4:] for b in self.extern_aufrufe if "dienst" in b], [["dienst", "neustart", "--von", "AMW"]])   # A2039
        w = self.con.execute("SELECT * FROM lauf WHERE id = ?", (r["web_lauf"],)).fetchone()        # Web-Abzug: rechnet die Kette selbst
        self.assertEqual((w["schwer"], w["status"], w["rc"], w["ordner"]), (0, "fertig", 0, self.repo))
        self.assertFalse([b for b in self.extern_aufrufe if "subtree" in b])                          # 1.118.1: kein Split mehr
        self.assertEqual(self.g("rev-parse", "origin/web^{tree}"), self.g("rev-parse", f"{self.sha}:web"))   # web = Stand
        self.assertEqual(self.g("rev-parse", "web-110"), self.g("rev-parse", "origin/web"))
        rel = self.con.execute("SELECT version, titel FROM release WHERE id = ?", (r["release"],)).fetchone()
        self.assertEqual(tuple(rel), ("1.1.0", "Neues Ding"))                                      # Versionszeile ohne TL
        info = self.con.execute("SELECT n.art, n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = 'TL'"
                                " AND n.kurz LIKE 'Version 1.1.0 live%'").fetchall()
        self.assertEqual([tuple(x) for x in info], [("info", "Version 1.1.0 live – Neues Ding")])  # eine Info, weckt nicht
        self.assertTrue(any(n.endswith(".db") for n in os.listdir(os.path.dirname(db.db_pfad())) if n.startswith("sicherung")))

    def test_ausgelieferte_aufgaben_werden_fertig(self):
        """A1738 (Marcel W2153): Die Auslieferung setzt jede Aufgabe fertig, deren grüner, freigegebener Stand enthalten ist –
        mit dem Versionshinweis aus der Prüfbitte; offene Kriterien sperren nicht, der Lead erfährt sie. Wer auf den
        Entwickler wartet (Bestätigung am Gerät), bleibt offen."""
        from amw import planung
        self.aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Neues Ding", "CC1")
        planung.schritt_setzen(self.con, self.pid, "TL", aid=self.aid, kriterien=["Handy-Bild in der Prüfbitte"])
        with self.assertRaises(kern.AmwFehler):                                                    # Hinweis nur mit Aufgabe
            betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "neu", self.sha, "x", None, hinweis="ohne Aufgabe")
        betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "neu", self.sha, "x", self.aid, gruppe="neu", hinweis="Neues Ding für alle.")
        self.assertIn("Versionshinweis (neu): Neues Ding für alle.",
                      self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE 'Prüfbitte%' ORDER BY id DESC").fetchone()[0])
        betrieb.pruefung_ergebnis(self.con, self.pid, "TL", self.con.execute("SELECT max(id) FROM pruefung").fetchone()[0], "gruen")
        betrieb.freigabe_merge(self.con, self.pid, "TL", self.aid)
        geraet = kern.aufgabe_neu(self.con, self.pid, "TL", "Erst am iPad bestätigen", "CC1")
        betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "neu", self.sha, "x", geraet)
        betrieb.pruefung_ergebnis(self.con, self.pid, "TL", self.con.execute("SELECT max(id) FROM pruefung").fetchone()[0], "gruen")
        betrieb.freigabe_merge(self.con, self.pid, "TL", geraet)
        kern.aufgabe_status(self.con, self.pid, "CC1", geraet, "wartet", auf="Entwickler")
        self.gesamtlauf()
        self.kette().ausliefern("neu")
        a = self.con.execute("SELECT * FROM aufgabe WHERE id = ?", (self.aid,)).fetchone()
        self.assertEqual((a["status"], a["beleg"], a["hinweis_gruppe"], a["hinweis"]), ("fertig", self.sha[:7], "neu", "Neues Ding für alle."))
        self.assertIn("Ausgeliefert in 1.1.0", a["zusammenfassung"])
        self.assertIn("Offene Kriterien: Handy-Bild in der Prüfbitte", a["zusammenfassung"])
        self.assertEqual(self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (geraet,)).fetchone()[0], "wartet")
        e = self.con.execute("SELECT von, text FROM plan_ereignis WHERE art = 'auto_fertig'").fetchall()
        self.assertEqual([(x["von"], x["text"][:5]) for x in e], [("AMW", "1.1.0")])
        info = self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE 'Version 1.1.0 live%'").fetchone()[0]
        self.assertIn(f"Fertig gesetzt: A{self.aid}.", info)
        self.assertIn(f"A{self.aid} hat offene Kriterien: Handy-Bild in der Prüfbitte.", info)

    def test_ohne_planung_automatisch_bleibt_alles_von_hand(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", plan_automatik="aus")
        self.gruen()
        self.gesamtlauf()
        self.kette().ausliefern("neu")
        self.assertEqual(self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (self.aid,)).fetchone()[0], "wartet")

    def lad(self):
        u = mock.patch.dict(os.environ, {"LOCALAPPDATA": os.path.join(self.ordner.name, "lad")})
        u.start()
        self.addCleanup(u.stop)

    def web_kaputt(self):
        echt = self.extern
        def extern(befehl, ordner):
            if "commit-tree" in befehl:
                return 1, "TimeoutExpired: zu lange"
            return echt(befehl, ordner)
        self.extern = extern

    def test_wartungsmodus_waehrend_jeder_auslieferung(self):
        """P253: auch ohne laufende p-Pakete keine neuen p-Starts, solange die Kette liefert; am Ende aufgehoben."""
        from amw import waechter
        self.lad()
        self.gruen()
        self.gesamtlauf()
        echt, gesehen = self.extern, []
        def extern(befehl, ordner):
            if befehl[:1] == ["gh"]:
                gesehen.append(bool(waechter.zustand()["wartung"]))
            return echt(befehl, ordner)
        self.extern = extern
        self.kette().ausliefern("neu")
        self.assertTrue(gesehen and all(gesehen))                                                 # während der Kette an
        self.assertIsNone(waechter.zustand()["wartung"])                                          # danach aufgehoben

    def test_wartungsmodus_bleibt_nach_abbruch_mit_hinweis(self):
        """P253: bricht die Kette ab, bleibt der Wartungsmodus an, und die Stopp-Meldung sagt, wie man ihn aufhebt."""
        from amw import waechter
        self.lad()
        self.gruen()
        self.gesamtlauf()
        self.web_kaputt()
        with self.assertRaises(auslieferung.Stopp) as e:
            self.kette().ausliefern("neu")
        self.assertIn("amw waechter weiter", str(e.exception))
        self.assertEqual(waechter.zustand()["wartung"]["grund"], "Auslieferung der AMW")

    def test_zwei_sicherungen_in_einer_minute_und_die_naechste_kette_beendet_die_wartung(self):
        """A2136 (1.196.0, 25.11.): die erste Kette brach an der Sicherung ab und ließ die Wartung an – die zweite hielt sie für von Hand."""
        from amw import waechter
        self.lad()
        self.gruen()
        self.gesamtlauf()
        with mock.patch.object(db, "sichern", side_effect=FileExistsError("gibt es schon")):
            with self.assertRaises(auslieferung.Stopp):
                self.kette().ausliefern("neu")
        self.assertTrue(waechter.zustand()["wartung"])
        db.sichern()                                                                              # gerade von Hand gesichert: gleiche Minute
        self.kette().ausliefern("neu")
        self.assertIsNone(waechter.zustand()["wartung"])

    def test_wartung_einer_noch_laufenden_kette_bleibt(self):
        from amw import waechter
        self.lad()
        with mock.patch("amw.steuerung.lebt", return_value=True):
            waechter.wartung_an("Auslieferung der AMW", kette=os.getpid() + 1)
            self.assertFalse(waechter.wartung_von_kette())
            waechter.wartung_an("Auslieferung der AMW")                                          # derselbe Text, von Hand
            self.assertFalse(waechter.wartung_von_kette())
        with mock.patch("amw.steuerung.lebt", return_value=False):
            waechter.wartung_an("Auslieferung der AMW", kette=os.getpid() + 1)
            self.assertTrue(waechter.wartung_von_kette())
            waechter.wartung_an("Auslieferung der AMW")
            self.assertFalse(waechter.wartung_von_kette())

    def test_wartungsmodus_von_hand_bleibt_wie_er_war(self):
        from amw import waechter
        self.lad()
        waechter.wartung_an("von Hand")
        self.gruen()
        self.gesamtlauf()
        self.kette().ausliefern("neu")
        self.assertEqual(waechter.zustand()["wartung"]["grund"], "von Hand")

    def test_web_abzug_wenn_der_agent_einen_lauf_hat(self):
        """A1952 (#30271, 1.158.0): Der ausliefernde Agent hat gerade einen eigenen Lauf („nie zwei Läufe zugleich“) – der
        Web-Abzug läuft trotzdem (Lauf der Kette, Agent AMW), die Kette geht zu Ende und hebt den Wartungsmodus auf."""
        from amw import betrieb, waechter
        self.lad()
        self.gruen()
        self.gesamtlauf()
        eigen = betrieb.lauf_start(self.con, self.pid, "CC1", "Gesamtlauf nächster Stapel", schwer=False)
        r = self.kette().ausliefern("neu")
        w = self.con.execute("SELECT agent, status, rc FROM lauf WHERE id = ?", (r["web_lauf"],)).fetchone()
        self.assertEqual(tuple(w), (auslieferung.KETTE, "fertig", 0))
        self.assertEqual(self.con.execute("SELECT status FROM lauf WHERE id = ?", (eigen,)).fetchone()[0], "laeuft")   # bleibt
        self.assertIsNone(waechter.zustand()["wartung"])
        self.assertEqual(self.g("rev-parse", "origin/web^{tree}"), self.g("rev-parse", f"{self.sha}:web"))

    def test_web_abzug_scheitert_versionszeilen_stehen_trotzdem(self):
        """A1756 (14.11.: Web-Abzug lief unter Last ins Zeitlimit, danach fehlten die Versionszeilen und der Lead musste sie von
        Hand eintragen): Versionszeile und fertige Aufgaben kommen vor dem Web-Abzug."""
        self.gruen()
        self.gesamtlauf()
        echt = self.extern
        def extern(befehl, ordner):
            if "commit-tree" in befehl:
                return 1, "TimeoutExpired: zu lange"
            return echt(befehl, ordner)
        self.extern = extern
        with self.assertRaises(auslieferung.Stopp) as e:
            self.kette().ausliefern("neu")
        self.assertIn("Web-Abzug", str(e.exception))
        self.assertIn("Versionszeilen und Aufgaben sind schon eingetragen", str(e.exception))
        self.assertIn("Versionszeile R", str(e.exception))                                         # in „erledigt: …“
        self.assertTrue(                                                                           # A1952: der Lead (TL) erfährt es
            self.con.execute("SELECT 1 FROM nachricht WHERE art = 'frage' AND kurz LIKE '%Web-Abzug gescheitert%'").fetchone())
        self.assertEqual(self.con.execute("SELECT version FROM release WHERE art = 'version'").fetchone()[0], "1.1.0")
        self.assertEqual(self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (self.aid,)).fetchone()[0], "fertig")

    def test_web_commit_fast_forward_und_unveraendert(self):
        """1.118.1 (15.11.: der Subtree-Split lief zweimal ins Zeitlimit): ein Commit mit dem Baum <Stand>:web über origin/web –
        Fast-Forward, gleicher Inhalt; ohne Änderung an web/ passiert nichts."""
        lauf = lambda b: auslieferung._laufen(["git", "-c", "user.name=t", "-c", "user.email=t@t", *b[1:]], self.repo)
        alt = self.g("rev-parse", "HEAD")
        self.assertEqual(auslieferung.web_commit(lauf, "1.0.0", alt, "100")[0], 0)                  # erster Abzug: neuer Zweig
        erster = self.g("ls-remote", self.ursprung, "web").split()[0]
        self.assertEqual(auslieferung.web_commit(lauf, "1.0.0", alt, "100"), (0, "web unverändert"))
        with open(os.path.join(self.repo, "web", "VERSION"), "w", encoding="utf-8") as f:
            f.write("2\n")
        self.g("add", "web/VERSION")
        self.g("-c", "commit.gpgsign=false", "commit", "-q", "-m", "web neu")
        neu = self.g("rev-parse", "HEAD")
        self.assertEqual(auslieferung.web_commit(lauf, "1.0.1", neu, "101")[0], 0)
        zweiter = self.g("ls-remote", self.ursprung, "web").split()[0]
        self.g("fetch", "-q", "origin", "web")
        self.assertEqual(self.g("rev-parse", "origin/web^"), erster)                                   # Fast-Forward
        self.assertEqual(self.g("rev-parse", f"{zweiter}^{{tree}}"), self.g("rev-parse", f"{neu}:web"))

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
        self.assertIn("Ohne Gesamtlauf: von TL: L1412", info)                                    # A1961: „von <Lead>“

    def test_ohne_merge_ok_halt_und_ruecknahme_zaehlt(self):
        self.gesamtlauf()
        self.gruen(merge_ok=False)
        self.ohne_aenderung("Merge-OK: keins für A")
        betrieb.freigabe_merge(self.con, self.pid, "TL", self.aid)
        betrieb.freigabe_merge(self.con, self.pid, "TL", self.aid, zurueck=True)                  # zurückgenommen: gilt nicht
        self.ohne_aenderung("Merge-OK: keins für A")
        with self.assertRaises(kern.AmwFehler) as e:                                                # A1754: ein Zweig ohne Prüfung
            betrieb.freigabe_merge(self.con, self.pid, "TL", self.aid, zweig="anderer")           # wird gar nicht erst angenommen
        self.assertIn("passend: neu (GRÜN", str(e.exception))
        self.ohne_aenderung("Merge-OK: keins für A")

    def test_merge_ok_ohne_zweig_nimmt_den_der_gruenen_pruefung(self):
        """A1754 (14.11.: Merge-OK auf b199-2 statt a1675-3 → Auslieferung hing 2 h): ohne --zweig gilt das OK für den Zweig der
        jüngsten grünen Prüfung dieser Aufgabe – und genau den liefert die Kette aus."""
        self.gruen(merge_ok=False)
        betrieb.freigabe_merge(self.con, self.pid, "TL", self.aid)
        self.assertEqual(self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'merge_ok' ORDER BY id DESC").fetchone()[0], "neu")
        self.gesamtlauf()
        self.assertEqual(self.kette().ausliefern("neu")["version"], "1.1.0")

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

    def teillauf(self, befehl, beschreibung="Wiederholung test_kopf_handy (3×)"):
        """A1961: ein grüner Lauf auf genau diesem sauberen Stand mit eigenem Befehl (wie amw lauf ausfuehren ihn ablegt)."""
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="CC1", beschreibung=beschreibung, status="fertig", rc=0,
                                angemeldet_utc=db.jetzt(), befehl=json.dumps([befehl]),
                                ergebnis=f"rc 0 · {betrieb.stand_text(('', self.sha, True))} · Ausgabe: x.txt")

    def test_nur_ein_lauf_der_ganzen_suite_ist_ein_gesamtlauf(self):
        """A1961 (#30422, 1.161.0): ohne --gesamtlauf nahm die Kette L3033 (3× ein Test) als Gesamtlauf. Ein Teil-Lauf zählt nie –
        auch nicht mit „Gesamtlauf“ in der Beschreibung; mit --gesamtlauf wird er abgewiesen; die ganze Suite zählt."""
        self.gruen()
        teil = self.teillauf("cd /d x && python -X utf8 -m unittest tests.test_kopf_handy")
        self.teillauf("python -X utf8 -m unittest " + "discover -s tests -k kopf", beschreibung="Gesamtlauf (nur kopf)")
        self.ohne_aenderung("Gesamtlauf")                                                       # kein Beleg gefunden
        with self.assertRaises(auslieferung.Stopp) as e:
            self.kette().ausliefern("neu", gesamtlauf=f"L{teil}")
        self.assertIn(f"L{teil} ist kein Gesamtlauf", str(e.exception))
        ganz = self.teillauf("cd /d x && set AMW_AGENT= && python -X utf8 -m unittest " + "discover -s tests > aus.txt",
                             beschreibung="Lauf ohne das Wort")
        zeilen = []
        auslieferung.Kette(self.con, self.pid, "CC1", self.repo, extern=self.extern, start_version=lambda: "1.1.0",
                           ausgabe=zeilen.append).ausliefern("neu")
        self.assertIn(f"Gesamtlauf L{ganz}", zeilen[0])

    def test_paralleler_gesamtlauf_zaehlt_wie_der_serielle(self):
        """A1966: python -X utf8 -m amw.testlauf ist dieselbe ganze Suite – ein Arbeiter-Aufruf mit Argumenten nie."""
        from amw import freigabereif
        self.gruen()
        arbeiter = self.teillauf("python -X utf8 -m amw.testlauf --arbeiter m.json b.json", beschreibung="Gesamtlauf Teil")
        self.ohne_aenderung("Gesamtlauf")
        ganz = self.teillauf("cd /d x && set AMW_AGENT= && python -X utf8 -m amw.testlauf", beschreibung="Lauf ohne das Wort")
        zeile = lambda lid: self.con.execute("SELECT * FROM lauf WHERE id = ?", (lid,)).fetchone()   # noqa: E731
        self.assertEqual([freigabereif.ist_gesamtlauf(self.con, self.pid, zeile(x), amw=True) for x in (arbeiter, ganz)], [False, True])
        zeilen = []
        auslieferung.Kette(self.con, self.pid, "CC1", self.repo, extern=self.extern, start_version=lambda: "1.1.0",
                           ausgabe=zeilen.append).ausliefern("neu")
        self.assertIn(f"Gesamtlauf L{ganz}", zeilen[0])

    def test_ausnahme_statt_l_nummer(self):
        """A1961: Mit Merge-OK-Ausnahme und ohne Gesamtlauf nennt die Kette „Ausnahme (von <Lead>: Grund)“ – nie einen Teil-Lauf."""
        self.gruen(merge_ok=False)
        betrieb.freigabe_merge(self.con, self.pid, "TL", self.aid, ausnahme="Wackler test_kopf_handy, sonst grün")
        self.teillauf("python -X utf8 -m unittest tests.test_kopf_handy")
        zeilen = []
        k = auslieferung.Kette(self.con, self.pid, "CC1", self.repo, extern=self.extern, start_version=lambda: "1.1.0", ausgabe=zeilen.append)
        k.ausliefern("neu")
        kopf = zeilen[0]
        self.assertIn("Ausnahme (von TL: Wackler test_kopf_handy, sonst grün)", kopf)
        self.assertNotIn("Gesamtlauf L", kopf)
        e = self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'auslieferung_ausnahme'").fetchone()
        self.assertIn("ohne Gesamtlauf – Ausnahme (von TL: Wackler", e[0])
        info = self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE 'Version 1.1.0 live%'").fetchone()[0]
        self.assertIn("Ohne Gesamtlauf: von TL: Wackler", info)

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
        self.gruen_auf("neu", self.sha, "Zwischen")                                              # A1866: eigene grüne Prüfung
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

    def stapel(self, unten_ergebnis, mit_pruefung=True):
        """Zweig „stapel“: unten A<a> (1.1.0), oben A<b> (1.1.1, grün + Merge-OK) – für A1875."""
        a = kern.aufgabe_neu(self.con, self.pid, "TL", "Unten", "CC1")
        b = kern.aufgabe_neu(self.con, self.pid, "TL", "Oben", "CC1")
        self.g("switch", "-q", "-c", "stapel", "main")
        unten = self.stand("1.1.0", f"A{a} unten")
        oben = self.stand("1.1.1", f"A{b} oben")
        self.g("switch", "-q", "main")
        if mit_pruefung:
            pa = betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "stapel", unten, "x", a)
            betrieb.pruefung_ergebnis(self.con, self.pid, "TL", pa, unten_ergebnis, "Befund")
            if unten_ergebnis == "gruen":
                betrieb.freigabe_merge(self.con, self.pid, "TL", a, "stapel")
        pb = betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "stapel", oben, "x", b)
        betrieb.pruefung_ergebnis(self.con, self.pid, "TL", pb, "gruen")
        betrieb.freigabe_merge(self.con, self.pid, "TL", b, "stapel")
        self.gesamtlauf(sha=oben)
        return a, b

    def test_roter_stand_unter_gruener_spitze_stoppt(self):
        """A1875: ein roter Stand darunter geht nie mit einer grünen Spitze live – Stopp mit Liste, nichts erledigt."""
        a, b = self.stapel("rot")
        with self.assertRaises(auslieferung.Stopp) as e:
            self.kette("1.1.1").ausliefern("stapel")
        self.assertIn(f"Stände: A{a} – neueste Prüfung", str(e.exception))
        self.assertIn("ist rot", str(e.exception))
        self.assertIn("erledigt: noch nichts", str(e.exception))

    def test_aufgabe_ohne_pruefung_im_bereich_stoppt(self):
        a, b = self.stapel(None, mit_pruefung=False)
        with self.assertRaises(auslieferung.Stopp) as e:
            self.kette("1.1.1").ausliefern("stapel")
        self.assertIn(f"Stände: A{a} hat einen Commit", str(e.exception))
        self.assertIn("keine Prüfung", str(e.exception))

    def test_alles_gruen_buendel_wie_heute(self):
        a, b = self.stapel("gruen")
        r = self.kette("1.1.1").ausliefern("stapel")
        self.assertEqual(r["version"], "1.1.1")
        self.assertEqual([b2[3] for b2 in self.extern_aufrufe if b2[0] == "gh"], ["v1.1.0", "v1.1.1"])   # Bündel B2630

    def test_zwischenversion_ohne_eigene_pruefung_kein_release(self):
        """A1866 (17.11.: nach dem Umnummerieren gingen 1.132.0/1.133.0 als eigene Releases mit): eine Versionsnummer im Bereich
        ohne grüne Prüfung auf genau ihrem Stand bekommt kein Tag, kein GitHub-Release, keine Versionszeile – sie geht in der
        obersten auf."""
        self.g("switch", "-q", "neu")
        oben = self.stand("1.1.1", "Neu nummeriert")
        self.g("switch", "-q", "main")
        self.gruen_auf("neu", oben, "Oben")
        self.gesamtlauf(sha=oben)
        aus = []
        k = self.kette("1.1.1")
        k.ausgabe = aus.append
        self.assertEqual(k.ausliefern("neu")["version"], "1.1.1")
        self.assertNotEqual(self.extern(["git", "rev-parse", "-q", "--verify", "refs/tags/v1.1.0"], self.repo)[0], 0)
        self.assertEqual([b[3] for b in self.extern_aufrufe if b[0] == "gh"], ["v1.1.1"])
        self.assertEqual([x[0] for x in self.con.execute("SELECT version FROM release WHERE art = 'version'")], ["1.1.1"])
        self.assertTrue(any("kein eigenes Release: 1.1.0" in z for z in aus), aus)

    def test_zwischenversion_gruen_vor_arbeit_der_naechsten(self):
        """A1878 (#29128: 1.142.0 grün auf b5359ce, danach committete A1867 erst Arbeit – noch unter 1.142.0 – und hob die
        Nummer später): die Zwischenversion bekommt ihr Tag auf dem neuesten GEPRÜFTEN Commit mit ihrer Nummer, statt in der
        obersten aufzugehen – und nicht auf dem Arbeits-Commit der nächsten Aufgabe."""
        self.gruen_auf("neu", self.sha, "Zwischen")                                              # grün auf dem 1.1.0-Stand
        self.g("switch", "-q", "neu")
        arbeit = self.stand("1.1.0", "Arbeit der nächsten Aufgabe")                              # noch Nummer 1.1.0, ungeprüft
        oben = self.stand("1.1.1", "Nächste Aufgabe")
        self.g("switch", "-q", "main")
        self.gruen_auf("neu", oben, "Nächste")
        self.gesamtlauf(sha=oben)
        aus = []
        k = self.kette("1.1.1")
        k.ausgabe = aus.append
        self.assertEqual(k.ausliefern("neu")["version"], "1.1.1")
        self.assertEqual(self.g("rev-parse", "v1.1.0^{commit}"), self.sha)                       # der geprüfte Stand …
        self.assertNotEqual(self.sha, arbeit)                                                    # … nicht der Arbeits-Commit
        self.assertEqual([b[3] for b in self.extern_aufrufe if b[0] == "gh"], ["v1.1.0", "v1.1.1"])
        self.assertEqual([x[0] for x in self.con.execute("SELECT version FROM release WHERE art = 'version' ORDER BY id")], ["1.1.0", "1.1.1"])
        self.assertFalse(any("kein eigenes Release" in z for z in aus), aus)

    def test_zwischenversion_kurzer_sha_zaehlt_nicht(self):
        """P265 (a): eine grüne Prüfung mit sehr kurzem SHA gibt keine fremde Zwischenversion frei (mindestens 7 Zeichen)."""
        self.g("switch", "-q", "neu")
        oben = self.stand("1.1.1", "Neu nummeriert")
        self.g("switch", "-q", "main")
        self.gruen_auf("neu", oben, "Oben")
        with db.schreiben(self.con):                                                             # grüne Prüfung mit 4-Zeichen-SHA
            db.einfuegen(self.con, "pruefung", projekt_id=self.pid, zweig="x", sha=self.sha[:4], bauer="CC1", pruefer="TL",
                         ergebnis="gruen", angefragt_utc=db.jetzt())
        self.gesamtlauf(sha=oben)
        self.kette("1.1.1").ausliefern("neu")
        self.assertNotEqual(self.extern(["git", "rev-parse", "-q", "--verify", "refs/tags/v1.1.0"], self.repo)[0], 0)

    def test_zweig_der_wie_ein_hash_aussieht(self):
        """17.11.: der Zweig „a1848“ war zugleich ein abgekürzter Hash (git warnt „refname is ambiguous“) – die Kette nahm die
        Warnung als Stand. Jetzt löst sie refs/heads/<zweig> auf und nimmt nur die 40-stellige Hex-Zeile."""
        kurz = self.g("rev-parse", "HEAD")[:6]                                                  # ein Name, der auch ein Objekt ist
        self.g("branch", kurz, "neu")
        self.gruen_auf(kurz, self.sha, "Hash-Name")
        self.gesamtlauf()
        self.assertEqual(self.kette().ausliefern(kurz)["sha"], self.sha)

    def test_unerwarteter_fehler_nennt_wartungsmodus(self):
        """A1866 (P257): bricht die Kette nach dem Setzen des Wartungsmodus mit einem Fehler ab, der kein Stopp ist, bleibt er an –
        die Meldung sagt jetzt, wie man ihn aufhebt."""
        from amw import waechter
        self.lad()
        self.gruen()
        self.gesamtlauf()
        echt = self.extern
        def extern(befehl, ordner):
            if befehl[:1] == ["gh"]:
                raise RuntimeError("Netz weg")
            return echt(befehl, ordner)
        self.extern = extern
        with self.assertRaises(auslieferung.Stopp) as e:
            self.kette().ausliefern("neu")
        self.assertIn("Unerwarteter Fehler", str(e.exception))
        self.assertIn("RuntimeError: Netz weg", str(e.exception))
        self.assertIn("amw waechter weiter", str(e.exception))
        self.assertTrue(waechter.zustand()["wartung"])
        tb = self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'auslieferung_fehler'").fetchone()[0]
        self.assertIn("Traceback", tb)                                                          # P265 (c)
        self.assertIn("Netz weg", tb)

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

    def test_reihenfolge_ignoriert_ueberholte_pruefungen(self):
        """Befund CCamw2 14.11.: eine alte grüne Prüfung eines später neu aufgesetzten Stands (1.88.0 lief unter anderem SHA
        live) hielt die Kette an. Überholt ist: Nummer nicht größer als main, Tag vorhanden oder Aufgabe abgeschlossen."""
        self.g("switch", "-q", "-c", "alt", "main")
        alt = self.stand("1.0.0", "Anfang neu aufgesetzt")                                       # gleiche Nummer wie main
        self.g("switch", "-q", "-c", "getaggt", "main")
        getaggt = self.stand("1.0.5", "Schon draußen")
        self.g("tag", "v1.0.5", getaggt)
        self.g("switch", "-q", "-c", "erledigt", "main")
        erledigt = self.stand("1.0.7", "Aufgabe fertig")
        self.g("switch", "-q", "main")
        self.gruen_auf("alt", alt, "Alt")
        self.gruen_auf("getaggt", getaggt, "Getaggt")
        fertig = self.gruen_auf("erledigt", erledigt, "Erledigt")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'x', fertig_utc = ? WHERE id = ?", (db.jetzt(), fertig))
        self.gruen()
        self.gesamtlauf()
        self.assertEqual(self.kette().ausliefern("neu")["version"], "1.1.0")

    def test_reihenfolge_nur_neueste_gruene_pruefung_je_aufgabe(self):
        """17.11.: eine Aufgabe wurde neu aufgesetzt; ihre alte grüne Prüfung (gleicher Zweig, Stand nicht im Ziel) hielt die
        Kette an, obwohl die neuere grüne Prüfung im Ziel steckt. Jetzt zählt je Aufgabe nur die neueste."""
        self.g("switch", "-q", "-c", "paket", "main")
        alt = self.stand("1.1.0", "Vor dem Neuaufsetzen")
        aid = self.gruen_auf("paket", alt, "Paket")                                               # alte Prüfung, grün + Merge-OK
        self.g("reset", "-q", "--hard", "main")                                                   # derselbe Zweig neu aufgesetzt
        neu = self.stand("1.2.0", "Neu aufgesetzt")
        self.g("switch", "-q", "main")
        prid = betrieb.pruefbitte(self.con, self.pid, "CC1", "TL", "paket", neu, "x", aid)
        betrieb.pruefung_ergebnis(self.con, self.pid, "TL", prid, "gruen")
        self.gesamtlauf(sha=neu)
        self.assertEqual(self.kette("1.2.0").ausliefern("paket")["version"], "1.2.0")

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

    def test_unversionierte_datei_haelt_nicht_an(self):
        """A1663: ein vergessener unversionierter Ordner (14.11.: _to_delete/ mit einer leeren Datei) hielt die Kette an –
        jetzt nur ein Hinweis; versionierte Änderungen halten weiter an (test_kein_fast_forward_und_schmutziger_baum)."""
        self.gruen()
        self.gesamtlauf()
        os.makedirs(os.path.join(self.repo, "_to_delete"))
        with open(os.path.join(self.repo, "_to_delete", "leer.db"), "w") as f:
            f.write("")
        ausgaben = []
        k = auslieferung.Kette(self.con, self.pid, "CC1", self.repo, extern=self.extern, start_version=lambda: "1.1.0",
                               ausgabe=ausgaben.append)
        self.assertEqual(k.ausliefern("neu")["version"], "1.1.0")
        self.assertTrue(any("unversioniert" in z and "_to_delete" in z for z in ausgaben))
        self.assertTrue(os.path.exists(os.path.join(self.repo, "_to_delete", "leer.db")))       # die AMW löscht nichts

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

    # --- A1814: Neu-Aufsetzen mit gleichem Inhalt – Grün und Merge-OK gehen mit (git patch-id) ----------------------------

    def neu_aufsetzen(self, aenderung=None):
        """main bekommt einen fremden Commit; „neu“ wird darauf neu aufgesetzt (cherry-pick) – optional mit geändertem Inhalt."""
        with open(os.path.join(self.repo, "fremd.txt"), "w", encoding="utf-8") as f:
            f.write("anderer Stand\n")
        self.g("add", "fremd.txt")
        self.g("-c", "commit.gpgsign=false", "commit", "-q", "-m", "fremd")
        self.g("push", "-q", "origin", "main")
        self.g("switch", "-q", "-c", "neu2", "main")
        self.g("-c", "commit.gpgsign=false", "cherry-pick", self.sha)
        if aenderung:
            with open(os.path.join(self.repo, "amw", "db.py"), "a", encoding="utf-8") as f:
                f.write(aenderung)
            self.g("add", "amw/db.py")
            self.g("-c", "commit.gpgsign=false", "commit", "-q", "--amend", "--no-edit")
        neu = self.g("rev-parse", "HEAD")
        self.g("switch", "-q", "main")
        return neu

    def test_gleicher_inhalt_gruen_und_merge_ok_gehen_mit(self):
        self.gruen_auf("neu", self.sha, "Neues Ding")
        neu = self.neu_aufsetzen()
        self.assertNotEqual(neu, self.sha)
        self.gesamtlauf(sha=neu)
        r = self.kette().ausliefern("neu2")
        self.assertEqual(r["version"], "1.1.0")
        p = self.con.execute("SELECT * FROM pruefung WHERE sha = ?", (neu,)).fetchone()
        self.assertEqual((p["ergebnis"], p["zweig"]), ("gruen", "neu2"))
        self.assertIn("gleicher Inhalt (git patch-id)", p["punkte"])
        self.assertTrue(self.con.execute("SELECT 1 FROM plan_ereignis WHERE art = 'freigabe_uebernommen'").fetchone())

    def test_geaenderter_inhalt_braucht_neue_freigabe_und_alles_steht_in_einer_meldung(self):
        self.gruen_auf("neu", self.sha, "Neues Ding")
        neu = self.neu_aufsetzen("X = 1\n")
        with self.assertRaises(auslieferung.Stopp) as e:
            self.kette().ausliefern("neu2")
        t = str(e.exception)
        self.assertIn("Freigaben", t)
        self.assertIn("keine grüne Prüfung", t)
        self.assertIn("kein grüner Lauf", t)                                                  # zweite Lücke in derselben Meldung
        self.assertFalse(self.con.execute("SELECT 1 FROM pruefung WHERE sha = ?", (neu,)).fetchone())


    def test_neuer_commit_darunter_braucht_eigene_pruefung(self):
        """A1834 (16.11.: 99df76e ging ungeprüft mit): Beim Neu-Aufsetzen kommt unter den geprüften Commit ein neuer Commit.
        Das Grün darf nicht übertragen werden, solange der neue Commit ungeprüft ist; der Stopp nennt ihn. Ist er grün,
        geht das alte Grün mit."""
        self.gruen_auf("neu", self.sha, "Neues Ding")
        self.g("switch", "-q", "-c", "neu3", "main")
        with open(os.path.join(self.repo, "test.txt"), "w", encoding="utf-8") as f:
            f.write("Test-Fix\n")
        self.g("add", "test.txt")
        self.g("-c", "commit.gpgsign=false", "commit", "-q", "-m", "dazwischen")
        mitte = self.g("rev-parse", "HEAD")
        self.g("-c", "commit.gpgsign=false", "cherry-pick", self.sha)
        oben = self.g("rev-parse", "HEAD")
        self.g("switch", "-q", "main")
        self.gesamtlauf(sha=oben)
        with self.assertRaises(auslieferung.Stopp) as e:
            self.kette().ausliefern("neu3")
        self.assertIn("keine grüne Prüfung", str(e.exception))
        self.assertIn(f"ungeprüft: {mitte[:8]}, {oben[:8]}", str(e.exception))
        self.assertFalse(self.con.execute("SELECT 1 FROM pruefung WHERE sha = ?", (oben,)).fetchone())   # nichts übertragen
        self.gruen_auf("neu3", mitte, "Test-Fix")                                            # der neue Commit wird geprüft
        self.assertEqual(self.kette().ausliefern("neu3")["version"], "1.1.0")
        self.assertEqual(self.con.execute("SELECT ergebnis FROM pruefung WHERE sha = ?", (oben,)).fetchone()[0], "gruen")


if __name__ == "__main__":
    unittest.main()
