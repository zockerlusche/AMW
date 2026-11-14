"""Release-Kette als ein Befehl (A1644): `amw release ausliefern --zweig X` – erst alle Vorbedingungen prüfen, dann ohne
weiteres Nachdenken: Sicherung, Fast-Forward, Tag, Dienst neu (Version und Schema prüfen), Push, GitHub-Release,
Web-Abzug (rechnet die Kette selbst als leichten Lauf), Versionszeile aus dem CHANGELOG und EINE
Meldung „Version x live“ (Info, weckt nicht).

Vorbedingungen (alle vor dem ersten verändernden Schritt): Prüfung GRÜN auf genau diesem Stand; Merge-OK des Leads für
die Aufgabe der Prüfung; Gesamtlauf mit rc 0 auf diesem Stand (oder ausdrücklich angegebener Lauf; ohne Lauf nur mit einer
Ausnahme, die der Lead in der AMW vermerkt hat: freigabe merge … --ausnahme „Grund“); main lässt sich per
Fast-Forward nachziehen; Arbeitsbaum sauber; Tag gibt es noch nicht.
Fehler: Stopp mit einer klaren Zeile – was schon erledigt ist und was fehlt. Nichts wird zurückgedreht (ein gepushter Tag
bleibt), es geht auch nichts halb weiter.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

from . import betrieb, db, kern

# Web-Abzug: die Kette rechnet ihn selbst als leichten Lauf (Befund 14.11.: als Dienst-Lauf lehnte der Dienst ihn ab, wenn
# für den Agenten kein Arbeitsordner eingetragen ist – zu Recht, der Dienst rechnet nur in eingetragenen Ordnern)
WEB_SCHRITTE = (["git", "subtree", "split", "--prefix", "web", "-b", "web-{kurz}"], ["git", "fetch", "origin", "web"],
                ["git", "merge-base", "--is-ancestor", "origin/web", "web-{kurz}"], ["git", "push", "origin", "web-{kurz}:web"])
DIENST_WARTEN_S = 90


class Stopp(kern.AmwFehler):
    """Die Kette hält an – mit Schritt und Grund."""


def _laufen(befehl, ordner, frist=600):
    """(rc, Ausgabe) eines externen Befehls; nie interaktiv."""
    try:
        r = subprocess.run(befehl, cwd=ordner, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           stdin=subprocess.DEVNULL, timeout=frist)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, f"{type(e).__name__}: {e}"


class Kette:
    """extern(befehl, ordner) → (rc, Ausgabe) für git/gh/Dienst; start_version() → Version, die der Dienst meldet (Tests)."""

    def __init__(self, con, pid, von, repo, extern=None, start_version=None, ausgabe=print):
        self.con, self.pid, self.von, self.repo = con, pid, von, os.path.abspath(repo)
        self.extern = extern or _laufen
        self.start_version = start_version or self._start_version
        self.ausgabe = ausgabe
        self.erledigt = []

    # --- Hilfen --------------------------------------------------------------------------------------------------------
    def git(self, *args, schritt):
        rc, aus = self.extern(["git", *args], self.repo)
        if rc != 0:
            self.stopp(schritt, f"git {' '.join(args)}: {aus[-300:]}")
        return aus

    def stopp(self, schritt, grund):
        fertig = ", ".join(self.erledigt) or "noch nichts"
        raise Stopp(f"Stopp bei „{schritt}“: {grund} – erledigt: {fertig}")

    def schritt(self, name):
        self.erledigt.append(name)
        self.ausgabe(f"✓ {name}")

    @staticmethod
    def _start_version():
        try:
            with urllib.request.urlopen("http://127.0.0.1:8780/api/start", timeout=5) as r:
                return json.load(r).get("version")
        except (OSError, ValueError):
            return None

    def datei(self, sha, pfad):
        return self.git("show", f"{sha}:{pfad}", schritt="Stand lesen")

    def notizen(self, sha, version):
        """Abschnitt der Version aus dem CHANGELOG des Stands: (Titel, Text)."""
        text = self.datei(sha, "CHANGELOG.md")
        m = re.search(rf"^## {re.escape(version)}\b[^\n]*?(?:·\s*(?P<titel>[^\n]+))?\n(?P<text>.*?)(?=^## |\Z)", text, re.M | re.S)
        if not m:
            self.stopp("Versionshinweise", f"im CHANGELOG fehlt „## {version}“")
        return (m.group("titel") or version).strip(), m.group("text").strip()

    # --- Vorbedingungen -------------------------------------------------------------------------------------------------
    def pruefen(self, zweig, gesamtlauf=None, aufgabe=None):
        sha = self.git("rev-parse", "--verify", f"{zweig}^{{commit}}", schritt="Stand bestimmen").splitlines()[-1].strip()
        m = re.search(r'__version__ = "([^"]+)"', self.datei(sha, "amw/__init__.py"))
        if not m:
            self.stopp("Version", "amw/__init__.py nennt keine Version")
        version = m.group(1)
        g = betrieb.ist_gruen(self.con, self.pid, sha)
        niedrig = False                                 # A1656: Prüfstufe niedrig (nur Doku/Tests) geht ohne Prüfbitte
        if g:
            p = self.con.execute("SELECT * FROM pruefung WHERE id = ?", (g["id"],)).fetchone()
        else:
            from . import kern, pruefstufe
            an = kern.projekt_wahl(self.con, self.pid, "pruefstufen") == "an"
            stufe, _ = pruefstufe.einstufen(pruefstufe.dateien(self.repo, sha), pruefstufe.muster(self.con, self.pid)) if an else (None, None)
            if stufe != "niedrig":
                self.stopp("Prüfung", f"keine grüne Prüfung auf genau {sha[:8]} – erst Prüfbitte, dann GRÜN"
                                      + (f" (Prüfstufe {stufe})" if an else ""))
            if not aufgabe:
                self.stopp("Prüfung", f"Prüfstufe niedrig: ohne Prüfbitte mit --aufgabe <nr> (für das Merge-OK des Leads)")
            p, niedrig = {"id": None, "aufgabe_id": int(aufgabe), "zweig": zweig}, True
        if not p["aufgabe_id"]:
            self.stopp("Merge-OK", f"P{p['id']} hängt an keiner Aufgabe – das Merge-OK gilt je Aufgabe")
        ok = betrieb.merge_ok(self.con, self.pid, p["aufgabe_id"], p["zweig"])
        if not ok:
            self.stopp("Merge-OK", f"kein Merge-OK für A{p['aufgabe_id']} ({p['zweig']}) – der Lead gibt es mit"
                                    f" amw freigabe merge {p['aufgabe_id']}")
        ausnahme = betrieb.gesamtlauf_ausnahme(self.con, self.pid, p["aufgabe_id"])
        ausnahme = f"{ausnahme['von']}: {ausnahme['text']}" if ausnahme and not niedrig else None   # ohne Prüfbitte: nur echter Lauf
        # Gesamtlauf: zählt nur, wenn der beim tatsächlichen Start gemerkte Stand genau dieser ist und sauber war (TL #24259) –
        # die Beschreibung kann veralten (Arbeitsbaum zwischen Einreihen und Start gewechselt)
        stand = f"%{betrieb.stand_text(('', sha, True))}%"
        lauf = None
        if gesamtlauf:
            lauf = self.con.execute("SELECT * FROM lauf WHERE id = ? AND projekt_id = ?", (int(str(gesamtlauf).lstrip("Ll")), self.pid)).fetchone()
            if not lauf or lauf["status"] != "fertig" or lauf["rc"] != 0:
                self.stopp("Gesamtlauf", f"L{gesamtlauf} ist nicht grün fertig")
            if betrieb.stand_text(("", sha, True)) not in (lauf["ergebnis"] or ""):
                self.stopp("Gesamtlauf", f"L{gesamtlauf} hat nicht genau {sha[:8]} sauber geprüft (Ergebnis: {(lauf['ergebnis'] or '')[:80]})")
        else:                                           # ein grüner Lauf geht vor; ohne ihn nur die Ausnahme des Leads
            lauf = self.con.execute("SELECT * FROM lauf WHERE projekt_id = ? AND status = 'fertig' AND rc = 0 AND ergebnis LIKE ?"
                                    " ORDER BY id DESC LIMIT 1", (self.pid, stand)).fetchone()
            if not lauf and not ausnahme:
                self.stopp("Gesamtlauf", f"kein grüner Lauf, der genau {sha[:8]} sauber geprüft hat – --gesamtlauf L<nr>, oder der Lead"
                                         f" vermerkt eine Ausnahme: amw freigabe merge {p['aufgabe_id']} --ausnahme \"Grund\"")
        if self.git("status", "--porcelain", schritt="Arbeitsbaum").strip():
            self.stopp("Arbeitsbaum", f"{self.repo} hat ungesicherte Änderungen")
        rc, _ = self.extern(["git", "merge-base", "--is-ancestor", "main", sha], self.repo)
        if rc != 0:
            self.stopp("Fast-Forward", f"main ist kein Vorfahre von {sha[:8]} – erst neu aufsetzen")
        rc, _ = self.extern(["git", "rev-parse", "-q", "--verify", f"refs/tags/v{version}"], self.repo)
        if rc == 0:
            self.stopp("Tag", f"v{version} gibt es schon")
        titel, text = self.notizen(sha, version)
        return {"sha": sha, "version": version, "lauf": lauf["id"] if lauf else None, "ausnahme": None if lauf else ausnahme,
                "titel": titel, "text": text, "niedrig": niedrig,
                "merge_ok": ok["von"]}

    # --- die Kette ------------------------------------------------------------------------------------------------------
    def ausliefern(self, zweig, gesamtlauf=None, aufgabe=None):
        v = self.pruefen(zweig, gesamtlauf, aufgabe)
        sha, version, ausnahme = v["sha"], v["version"], v["ausnahme"]
        self.ausgabe(f"Version {version} = {sha[:8]} · {'Prüfstufe niedrig (ohne Prüfbitte)' if v['niedrig'] else 'Prüfung grün'} · Merge-OK {v['merge_ok']} · "
                     + (f"Gesamtlauf L{v['lauf']}" if v["lauf"] else f"Ausnahme ({ausnahme})"))
        from . import dokumente
        ziel = db.sichern(None)
        dokumente.sichern(os.path.splitext(ziel)[0] + "-dokumente")
        self.schritt(f"Sicherung {os.path.basename(ziel)}")
        self.git("merge", "--ff-only", "-q", sha, schritt="Fast-Forward")
        self.schritt(f"main → {sha[:8]}")
        self.git("tag", f"v{version}", sha, schritt="Tag")
        self.schritt(f"Tag v{version}")
        rc, aus = self.extern([sys.executable, "-X", "utf8", os.path.join(self.repo, "amw-cli.py"), "dienst", "neustart"], self.repo)
        if rc != 0:
            self.stopp("Dienst neu", aus[-300:])
        ende = time.time() + DIENST_WARTEN_S
        while self.start_version() != version:
            if time.time() > ende:
                self.stopp("Dienst neu", f"meldet nach {DIENST_WARTEN_S} s nicht {version}")
            time.sleep(3)
        schema = int(re.search(r"SCHEMA_VERSION = (\d+)", self.datei(sha, "amw/db.py")).group(1))
        con = db.verbinde(nur_lesen=True)
        try:
            uv, qc = con.execute("PRAGMA user_version").fetchone()[0], con.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            con.close()
        if uv != schema or qc != "ok":
            self.stopp("Datenbank prüfen", f"Schema {uv} (erwartet {schema}), quick_check {qc}")
        self.schritt(f"Dienst {version}, Schema {schema}, quick_check ok")
        self.git("push", "-q", "origin", "main", f"v{version}", schritt="Push")
        self.schritt("Push main + Tag")
        notiz = os.path.join(os.path.dirname(db.db_pfad()), f"notizen-{version}.md")
        with open(notiz, "w", encoding="utf-8", newline="") as f:
            f.write(v["text"] + "\n")
        try:
            rc, aus = self.extern(["gh", "release", "create", f"v{version}", "--title", version, "--notes-file", notiz, "--latest"], self.repo)
        finally:
            os.remove(notiz)
        if rc != 0:
            self.stopp("GitHub-Release", aus[-300:])
        self.schritt("GitHub-Release")
        kurz = version.replace(".", "")
        lid = betrieb.lauf_start(self.con, self.pid, self.von, f"Web-Abzug {version} (leicht)", schwer=False, ordner=self.repo)
        rc, aus = 0, ""
        for teil in WEB_SCHRITTE:
            rc, aus = self.extern([x.format(kurz=kurz) for x in teil], self.repo)
            if rc != 0:
                break
        betrieb.lauf_ende(self.con, self.pid, self.von, lid, rc, (f"rc {rc} · " + (aus[-300:] if rc else "web-Zweig aktualisiert"))[:500])
        if rc != 0:
            self.stopp("Web-Abzug", f"L{lid}: {aus[-300:]}")
        self.schritt(f"Web-Abzug L{lid}")
        from . import wissen
        rid, _ = wissen.release_version(self.con, self.pid, self.von, version, v["titel"], sha[:7], kette=True)
        self.schritt(f"Versionszeile R{rid}")
        an = kern.lead(self.con, self.pid)
        if an and an != self.von:
            with db.schreiben(self.con):
                kern._posten(self.con, self.pid, "AMW", an, "info", f"Version {version} live – {v['titel']}",
                             f"main {sha[:8]}, Tag v{version}, GitHub-Release, Web-Abzug L{lid}, Versionszeile R{rid}."
                             + (f" Gesamtlauf L{v['lauf']}." if v["lauf"] else f" Ohne Gesamtlauf: {ausnahme}."))
        self.ausgabe(f"Version {version} live.")
        return {"version": version, "sha": sha, "web_lauf": lid, "release": rid}
