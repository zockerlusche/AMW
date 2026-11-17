"""Liste „bereit zum Merge“ mit einer Freigabe über alle (A1858, M50 S6b; D1258 v17 §6.5, §6a.5; TL #29096): diff --stat und
gekürzter Diff aus dem Prüf-Repo, Freigabe holt genau den einen Ref ins Projekt + GRÜN „Prüfung C (AMW) + Freigabe“ + Merge-OK,
Blick nach merge_blick, Außen-Prüfung nach merge_aussen_pruefung (nur der Mensch stellt beides), nach der Auslieferung
merge_reihe → gemergt → fertig und Platz frei; Art agent und Plätze = 0 wie heute."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from amw import arbeitspaket, betrieb, db, disponent, kern, mergeliste, planautomatik, platz, pruefung_c

OHNE = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def g(ordner, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", ordner, *args], check=True, capture_output=True,
                          text=True, creationflags=OHNE).stdout.strip()


def schreiben(wurzel, rel, text):
    pfad = os.path.join(wurzel, *rel.split("/"))
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def projekt_repo(con, pid, repo):
    """Kleines Projekt-Repo (lib/, web/api.php) als Projektordner eintragen."""
    for rel, text in {"lib/__init__.py": "", "lib/rechnen.py": "def plus(a, b):\n    return a - b\n", "web/api.php": "<?php\n"}.items():
        schreiben(repo, rel, text)
    g(os.path.dirname(repo), "init", "-q", "-b", "main", repo)
    g(repo, "add", "-A")
    g(repo, "commit", "-q", "-m", "basis")
    kern.projekt_ordner_setzen(con, pid, repo)


def bereit(con, pid, repo, titel, dateien, nr=1):
    """Ein p-Paket auf Platz nr bis „bereit zum Merge“ – wie Disponent + Prüfung C + E7 es hinterlassen."""
    aid = kern.aufgabe_neu(con, pid, "TL", titel, "CC1")
    arbeitspaket.setzen(con, pid, "TL", aid, art="p")
    p = platz.plaetze(con, pid)[nr - 1]
    basis = platz.vorbereiten(p, repo, mergeliste.zweig(aid), aufgabe=aid)["basis"]
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=disponent.VERMERK,
                     aufgabe_id=aid, text=json.dumps({"platz": nr, "basis": basis, "zweig": mergeliste.zweig(aid)}))
    for rel, text in dateien.items():
        schreiben(p["klon"], rel, text)
    pruefung_c.basis_holen(p, repo, basis)
    kopf = pruefung_c.einsammeln(p, basis, aid, f"A{aid}: {titel}")
    for z in ("startklar", "laeuft", "abgegeben", "abnahme", "merge_reihe"):
        arbeitspaket.zustand_setzen(con, pid, "AMW", aid, z)
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art="paket_entscheidung",
                     aufgabe_id=aid, text=json.dumps({"zeile": "E7", "code": None, "kopf": kopf}))
    return aid, kopf, p


@unittest.skipUnless(shutil.which("git") and os.name == "nt", "git/Windows fehlt")
class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        o = self.ordner.name
        self.pfad = os.path.join(o, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad, "LOCALAPPDATA": os.path.join(o, "lad")})
        u.start()
        self.addCleanup(u.stop)
        for k in ("AMW_AGENT", "AMW_PROJEKT"):
            os.environ.pop(k, None)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid, "PR1")
        self.repo = os.path.join(o, "projekt")
        projekt_repo(self.con, self.pid, self.repo)

    def plaetze(self, n):
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, platz_wurzel=os.path.join(self.ordner.name, "plaetze"), plaetze=n)

    def bereit(self, titel, dateien, nr=1):
        return bereit(self.con, self.pid, self.repo, titel, dateien, nr)


class Liste(Grund):
    def test_ohne_plaetze_leer(self):
        self.assertEqual(mergeliste.liste(self.con, self.pid)["pakete"], [])

    def test_stat_diff_und_blick(self):
        self.plaetze(2)
        a, kopf, _ = self.bereit("plus reparieren", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"})
        b, _, _ = self.bereit("API ändern", {"web/api.php": "<?php\necho 'x';\n", "lib/neu.py": "URL = 'https://fremd.example.net/x'\n"
                                                                                                "import os; os.system('dir')\n"}, nr=2)
        d = mergeliste.liste(self.con, self.pid)
        e = {x["aufgabe"]: x for x in d["pakete"]}
        self.assertEqual(sorted(e), [a, b])
        self.assertEqual((e[a]["kopf"], e[a]["zweig"], e[a]["geaendert"]), (kopf, f"paket-A{a}", ["lib/rechnen.py"]))
        self.assertIn("lib/rechnen.py", e[a]["stat"])
        self.assertIn("+    return a + b", e[a]["diff"])
        self.assertEqual((e[a]["server"], e[a]["blick"], e[a]["freigegeben"]), ([], False, False))
        self.assertEqual((e[b]["server"], e[b]["blick"]), (["web/api.php"], True))            # Vorgabe server: Blick bei web/*.php
        self.assertEqual(e[b]["aussen"], ["lib/neu.py: Adresse fremd.example.net", "lib/neu.py: Shell/Prozess"])
        self.assertEqual((d["merge_blick"], d["merge_aussen_pruefung"]), ("server", "an"))
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, merge_blick="alle")
        self.assertTrue(all(x["blick"] for x in mergeliste.liste(self.con, self.pid, diff=False)["pakete"]))
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, merge_blick="aus")
        self.assertFalse(any(x["blick"] for x in mergeliste.liste(self.con, self.pid, diff=False)["pakete"]))

    def test_diff_gekuerzt(self):
        self.plaetze(1)
        a, _, _ = self.bereit("viel", {"lib/viel.py": "".join(f"x{i} = {i}\n" for i in range(400))})
        e = mergeliste.liste(self.con, self.pid)["pakete"][0]
        self.assertTrue(e["gekuerzt"])
        self.assertEqual(len(e["diff"].splitlines()), mergeliste.DIFF_ZEILEN)


class Freigabe(Grund):
    def test_eine_freigabe_ueber_alle(self):
        self.plaetze(2)
        a, ka, _ = self.bereit("plus reparieren", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"})
        b, kb, _ = self.bereit("minus dazu", {"lib/minus.py": "def minus(a, b):\n    return a - b\n"}, nr=2)
        r = mergeliste.freigeben(self.con, self.pid, "TL")
        self.assertEqual([(x["aufgabe"], x["ok"]) for x in r], [(a, True), (b, True)], r)
        for aid, kopf in ((a, ka), (b, kb)):
            self.assertEqual(g(self.repo, "rev-parse", f"refs/heads/paket-A{aid}"), kopf)    # genau der eine Ref im Projekt
            p = self.con.execute("SELECT * FROM pruefung WHERE aufgabe_id = ?", (aid,)).fetchone()
            self.assertEqual((p["ergebnis"], p["sha"], p["zweig"], p["bauer"], p["pruefer"]), ("gruen", kopf, f"paket-A{aid}", "AMW", "TL"))
            self.assertEqual(p["bemerkung"], "Prüfung C (AMW) + Freigabe TL")
            self.assertTrue(betrieb.merge_ok(self.con, self.pid, aid, f"paket-A{aid}"))
        self.assertEqual(g(self.repo, "rev-parse", "--abbrev-ref", "HEAD"), "main")             # Projekt: nichts ausgecheckt
        self.assertEqual([x["text"] for x in mergeliste.freigeben(self.con, self.pid, "TL", [a])], ["ist schon freigegeben"])

    def test_blick_noetig_nur_einzeln_mit_blick(self):
        self.plaetze(1)
        a, _, _ = self.bereit("API", {"web/api.php": "<?php\necho 1;\n"})
        r = mergeliste.freigeben(self.con, self.pid, "TL")
        self.assertFalse(r[0]["ok"])
        self.assertIn("Blick", r[0]["text"])
        self.assertNotIn(f"paket-A{a}", g(self.repo, "branch", "--list"))
        r = mergeliste.freigeben(self.con, self.pid, "TL", [a], blick=[a])
        self.assertTrue(r[0]["ok"], r)
        self.assertIn("mit Blick", self.con.execute("SELECT bemerkung FROM pruefung WHERE aufgabe_id = ?", (a,)).fetchone()[0])

    def test_wer_darf(self):
        self.plaetze(1)
        self.bereit("plus", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"})
        with self.assertRaisesRegex(kern.AmwFehler, "Freigeben dürfen"):
            mergeliste.freigeben(self.con, self.pid, "CC1")
        kern.projekt_einstellen(self.con, self.pid, "TL", paket_pruefer="PR1")
        self.assertTrue(mergeliste.freigeben(self.con, self.pid, "PR1")[0]["ok"])                # der Prüfer der Pakete

    def test_vorhandener_zweig_wird_nicht_ueberschrieben(self):
        self.plaetze(1)
        a, _, _ = self.bereit("plus", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"})
        g(self.repo, "branch", f"paket-A{a}", "main")
        r = mergeliste.freigeben(self.con, self.pid, "TL")
        self.assertFalse(r[0]["ok"])
        self.assertIn("schon mit anderem Stand", r[0]["text"])
        self.assertEqual(g(self.repo, "rev-parse", f"paket-A{a}"), g(self.repo, "rev-parse", "main"))
        self.assertIsNone(self.con.execute("SELECT 1 FROM pruefung WHERE aufgabe_id = ?", (a,)).fetchone())

    def test_seite_nur_am_pc(self):
        """Workbench: „Alle freigeben“ am PC (als Mensch); online/Handy nie."""
        from amw import aktionen
        self.plaetze(1)
        a, kopf, _ = self.bereit("plus", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"})
        with self.assertRaisesRegex(aktionen.Ungueltig, "nur am PC"):
            aktionen.ausfuehren(self.con, self.pid, "/api/paket/freigeben", {}, kanal="netz")
        self.assertIsNone(self.con.execute("SELECT 1 FROM pruefung WHERE aufgabe_id = ?", (a,)).fetchone())
        r = aktionen.ausfuehren(self.con, self.pid, "/api/paket/freigeben", {}, kanal="seite")
        self.assertEqual(r["text"], "1 von 1 freigegeben")
        self.assertEqual(self.con.execute("SELECT pruefer FROM pruefung WHERE aufgabe_id = ?", (a,)).fetchone()[0], kern.ENTWICKLER)

    def test_einstellungen_nur_der_mensch(self):
        for k, v in (("merge_blick", "alle"), ("merge_aussen_pruefung", "aus")):
            with self.assertRaisesRegex(kern.AmwFehler, "nur der Mensch"):
                kern.projekt_einstellen(self.con, self.pid, "TL", **{k: v})
            kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, **{k: v})
            self.assertEqual(kern.projekt_wahl(self.con, self.pid, k), v)
        kern.projekt_einstellen(self.con, self.pid, "TL", merge_blick="alle")                    # unverändert mitgeschickt: erlaubt


class Ausgeliefert(Grund):
    def test_gemergt_fertig_platz_frei(self):
        self.plaetze(1)
        a, kopf, p = self.bereit("plus", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"})
        mergeliste.freigeben(self.con, self.pid, "TL")
        g(self.repo, "merge", "-q", "--ff-only", f"paket-A{a}")
        self.assertEqual(disponent.belegte_plaetze(self.con, self.pid), {1: a})
        aus = planautomatik.ausgeliefert(self.con, self.pid, "1.0.1", kopf, lambda s: True)
        self.assertEqual([x["aufgabe"] for x in aus], [a])
        self.assertIn("gemergt, fertig, Platz 1 frei", aus[0]["paket"])
        self.assertEqual((arbeitspaket.lesen(self.con, a)["zustand"],
                          self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (a,)).fetchone()[0]), ("fertig", "fertig"))
        self.assertIn("gemergt", [neu for _, _, neu, _ in arbeitspaket.verlauf(self.con, a)])
        self.assertEqual(disponent.belegte_plaetze(self.con, self.pid), {})
        self.assertEqual(g(p["klon"], "status", "--porcelain"), "")

    def test_art_agent_wie_heute(self):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "normal", "CC1")
        self.assertIsNone(mergeliste.ausgeliefert(self.con, self.pid, aid, "abc1234"))


class ServerCode(unittest.TestCase):
    def test_versionshinweis_zeile(self):
        """B2900: ändert der Stand web/*.php, nennt die Kette es im Versionshinweis als „Server-Code geändert“."""
        from amw import auslieferung
        aufrufe = []
        k = auslieferung.Kette.__new__(auslieferung.Kette)
        k.repo, k.extern = "X", lambda befehl, ordner: (aufrufe.append(befehl), (0, "lib/a.py\nweb/api.php\nweb/inc/x.php\n"))[1]
        self.assertEqual(k.server_code("abc"), ["web/api.php", "web/inc/x.php"])
        self.assertIn("main...abc", aufrufe[0])
        k.extern = lambda befehl, ordner: (0, "lib/a.py\n")
        self.assertEqual(k.server_code("abc"), [])


@unittest.skipUnless(shutil.which("git") and os.name == "nt", "git/Windows fehlt")
class AussenPruefung(Grund):
    def test_aus_nur_hinweis(self):
        self.plaetze(1)
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "fremd", "CC1")
        p = platz.plaetze(self.con, self.pid)[0]
        basis = platz.vorbereiten(p, self.repo, mergeliste.zweig(aid), aufgabe=aid)["basis"]
        schreiben(p["klon"], "lib/neu.py", "URL = 'https://fremd.example.net/x'\n")
        befehl = f"{sys.executable.replace(chr(92), '/')} -c pass"
        an = pruefung_c.pruefen(p, self.repo, basis, aid, befehl, ["lib/"], regression=None)
        self.assertEqual(an["code"], "C/aussen")
        aus = pruefung_c.pruefen(p, self.repo, basis, aid, befehl, ["lib/"], regression=None, aussen=False)
        self.assertIsNone(aus["code"], aus)
        self.assertIn("nur als Hinweis", aus["grund"])


if __name__ == "__main__":
    unittest.main()
