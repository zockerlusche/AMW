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
# für den Agenten kein Arbeitsordner eingetragen ist – zu Recht, der Dienst rechnet nur in eingetragenen Ordnern).
# Seit 1.118.1: kein Subtree-Split mehr (läuft die ganze Geschichte ab – 15.11. zweimal über 10 bzw. 30 Minuten), sondern ein
# Commit mit dem Baum <Stand>:web und origin/web als Eltern – Sekunden, immer Fast-Forward, der Inhalt ist derselbe.
WEB_AUTOR = ["-c", "user.name=AMW", "-c", "user.email=amw@invalid"]
DIENST_WARTEN_S = 90
WEB_FRIST_S = 600


def web_commit(lauf, version, sha, kurz):
    """Den web-Zweig auf den Stand bringen: Baum <sha>:web als neuer Commit über origin/web (Fast-Forward), Push.
    lauf(befehl) → (rc, Ausgabe). Rückgabe (rc, Ausgabe). Unverändert: nichts zu tun."""
    rc, aus = lauf(["git", "fetch", "origin", "web"])
    eltern = []
    if rc == 0:
        rc, alt = lauf(["git", "rev-parse", "origin/web"])
        if rc == 0 and alt.strip():
            eltern = ["-p", alt.strip()]
    rc, baum = lauf(["git", "rev-parse", f"{sha}:web"])
    if rc != 0:
        return rc, baum
    baum = baum.strip()
    if eltern:
        rc, alter_baum = lauf(["git", "rev-parse", "origin/web^{tree}"])
        if rc == 0 and alter_baum.strip() == baum:
            return 0, "web unverändert"
    rc, neu = lauf(["git", *WEB_AUTOR, "commit-tree", baum, *eltern, "-m", f"web {version} ({sha[:8]})"])
    if rc != 0:
        return rc, neu
    neu = neu.strip()
    lauf(["git", "branch", "-f", f"web-{kurz}", neu])
    return lauf(["git", "push", "origin", f"{neu}:refs/heads/web"])


def patch_ids(repo, basis, sha):
    """{Commit: patch-id} der Commits basis..sha – gleicher Inhalt ergibt dieselbe ID, auch nach dem Neu-Aufsetzen (A1814).
    Leeres Ergebnis, wenn git nicht antwortet."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        log = subprocess.run(["git", "log", "-p", "--no-color", "--no-ext-diff", "--format=commit %H", f"{basis}..{sha}"], cwd=repo,
                             capture_output=True, timeout=120, stdin=subprocess.DEVNULL, creationflags=flags)
        if log.returncode != 0:
            return {}
        ids = subprocess.run(["git", "patch-id", "--stable"], cwd=repo, input=log.stdout, capture_output=True, timeout=120,
                             creationflags=flags)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    aus = {}
    for z in ids.stdout.decode("utf-8", "replace").splitlines():
        teile = z.split()
        if len(teile) == 2:
            aus[teile[1]] = teile[0]
    return aus


class Stopp(kern.AmwFehler):
    """Die Kette hält an – mit Schritt und Grund."""


def _laufen(befehl, ordner, frist=600):
    """(rc, Ausgabe) eines externen Befehls; nie interaktiv."""
    try:
        r = subprocess.run(befehl, cwd=ordner, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           stdin=subprocess.DEVNULL, timeout=frist, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
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
        wartung = (" – der Wartungsmodus bleibt an (keine neuen p-Starts); aufheben: amw waechter weiter"
                   if getattr(self, "wartung_an", False) else "")
        raise Stopp(f"Stopp bei „{schritt}“: {grund} – erledigt: {fertig}{wartung}")

    def schritt(self, name):
        self.erledigt.append(name)
        self.ausgabe(f"✓ {name}")

    def uebertragen(self, sha, zweig):
        """A1814 (Nacht 15./16.11.: nach dem Neu-Aufsetzen brauchte jeder neue Stand wieder Grün und Merge-OK – 8 h Stillstand):
        Für jeden Commit main..sha ohne grüne Prüfung sucht die AMW eine grüne Prüfung mit demselben Inhalt (git patch-id) –
        nur wenn auch alle Commits darunter im neuen Stand stecken. Dann gelten Grün (neue Zeile, Quelle vermerkt) und – falls
        es für den alten Zweig galt – das Merge-OK auch für den neuen Stand bzw. Zweig. Geänderte Patches: nichts. Rückgabe: Texte."""
        neu = patch_ids(self.repo, "main", sha)
        if not neu:
            return []
        neu_ids = set(neu.values())
        commit_zu = {pid: c for c, pid in neu.items()}
        reihe = self.reihe(sha)
        aus = []
        while True:                                      # A1834: wiederholen – eine Übernahme weiter unten kann die nächste decken
            n = len(aus)
            aus += self._uebertragen_runde(zweig, neu, neu_ids, commit_zu, reihe)
            if len(aus) == n:
                return aus

    def baum(self, sha):
        """A1932: Baum eines Stands (git rev-parse <sha>^{tree}) oder None."""
        rc, aus = self.extern(["git", "rev-parse", f"{sha}^{{tree}}"], self.repo)
        return aus.strip() if rc == 0 and aus.strip() else None

    def reihe(self, sha):
        """Commits main..sha, älteste zuerst."""
        rc, aus = self.extern(["git", "rev-list", "--reverse", f"main..{sha}"], self.repo)
        return [z.strip() for z in aus.splitlines() if z.strip()] if rc == 0 else []

    def ungeprueft(self, reihe, bis=None):
        """A1834: Commits der Reihe (bis einschließlich `bis`), die kein grüner Stand deckt – ein Grün auf einem Commit deckt
        ihn und alle darunter."""
        reihe = reihe[:reihe.index(bis) + 1] if bis in reihe else list(reihe)
        letzte = max((i for i, c in enumerate(reihe) if betrieb.ist_gruen(self.con, self.pid, c)), default=-1)
        return reihe[letzte + 1:]

    def _uebertragen_runde(self, zweig, neu, neu_ids, commit_zu, reihe):
        aus = []
        for p in self.con.execute("SELECT * FROM pruefung WHERE projekt_id = ? AND ergebnis = 'gruen' AND aufgabe_id IS NOT NULL"
                                  " ORDER BY id DESC LIMIT 60", (self.pid,)).fetchall():
            if p["sha"] in neu or len(p["sha"]) < 40:
                continue                                 # schon auf diesem Stand (oder alter kurzer SHA: nicht sicher)
            a = self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (p["aufgabe_id"],)).fetchone()
            if not a or a["status"] in ("fertig", "verworfen"):
                continue
            if self.extern(["git", "merge-base", "--is-ancestor", p["sha"], "main"], self.repo)[0] == 0:
                continue                                 # schon draußen
            rc, basis = self.extern(["git", "merge-base", p["sha"], "main"], self.repo)
            if rc != 0:
                continue
            alt = patch_ids(self.repo, basis.strip().splitlines()[-1], p["sha"])
            eigene = alt.get(p["sha"])
            if not eigene or eigene not in commit_zu or not set(alt.values()) <= neu_ids:
                continue                                 # Inhalt geändert oder nicht vollständig im neuen Stand
            ziel = commit_zu[eigene]
            # A1912 (21.11., S8: nach einem abgebrochenen Bündel und neuer Freigabe ging nur das Grün ins neue Bündel, das
            # Merge-OK nicht – die jüngste grüne Prüfung kam aus dem alten Bündel, dessen OK nicht mehr galt, und die Prüfung
            # mit gültigem OK wurde übersprungen, weil das Ziel schon grün war): ist das Ziel eines Bündels schon grün, geht
            # noch das OK mit. Nur für buendel-*: sonst bleibt es dabei, dass ein schon grüner Stand sein eigenes OK braucht.
            ok_mit = bool(betrieb.merge_ok(self.con, self.pid, p["aufgabe_id"], p["zweig"])) and \
                not betrieb.merge_ok(self.con, self.pid, p["aufgabe_id"], zweig)
            # A1932 (22.11., stapel2): „schon grün“ je Aufgabe – teilen mehrere Aufgaben einen Stapel-SHA, bekommt jede ihre Zeile
            schon_gruen = bool(self.con.execute("SELECT 1 FROM pruefung WHERE projekt_id = ? AND aufgabe_id = ? AND sha = ?"
                                                " AND ergebnis = 'gruen'", (self.pid, p["aufgabe_id"], ziel)).fetchone())
            if schon_gruen and not (ok_mit and str(zweig).startswith("buendel-")):
                continue
            alt_ids = set(alt.values())                  # A1834 (16.11.: 99df76e ging ungeprüft mit): jeder Commit bis zum Ziel muss
            if any(neu.get(c) not in alt_ids for c in self.ungeprueft(reihe, ziel)[:-1]):   # im geprüften alten Stand stecken
                continue                                 # oder unter einem grünen Stand liegen – sonst keine Übernahme
            jetzt = db.jetzt()
            with db.schreiben(self.con):
                if schon_gruen:
                    text = f"P{p['id']}: {p['sha'][:8]} → {ziel[:8]} schon grün"
                else:
                    prid = db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=p["aufgabe_id"], zweig=zweig, sha=ziel,
                                        bauer=p["bauer"], pruefer=p["pruefer"], ergebnis="gruen", angefragt_utc=jetzt, ergebnis_utc=jetzt,
                                        punkte=f"Übernommen aus P{p['id']} ({p['zweig']}@{p['sha'][:8]}) – gleicher Inhalt (git patch-id),"
                                               " nur neu aufgesetzt", bemerkung=f"automatisch von der AMW (A1814), Quelle P{p['id']}")
                    text = f"P{prid} ← P{p['id']}: {p['sha'][:8]} → {ziel[:8]} gleicher Inhalt"
                if ok_mit:
                    db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=jetzt, von="AMW", art="merge_ok",
                                 aufgabe_id=p["aufgabe_id"], text=zweig)
                    text += f", Merge-OK für {zweig} übernommen"
                db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=jetzt, von="AMW", art="freigabe_uebernommen",
                             aufgabe_id=p["aufgabe_id"], text=text[:300])
            aus.append(f"A{p['aufgabe_id']}: {text}")
        return aus

    def web_abzug(self, version, sha, kurz):
        lauf = (lambda b: _laufen(b, self.repo, WEB_FRIST_S)) if self.extern is _laufen else (lambda b: self.extern(b, self.repo))
        return web_commit(lauf, version, sha, kurz)

    @staticmethod
    def _start_version():
        try:
            with urllib.request.urlopen("http://127.0.0.1:8780/api/start", timeout=5) as r:
                return json.load(r).get("version")
        except (OSError, ValueError):
            return None

    def stand(self, zweig):
        """Commit eines Zweigs. Erst refs/heads/<zweig> (ein Name wie „a1848“ ist sonst auch ein abgekürzter Hash, git warnt
        „refname is ambiguous“), sonst der Name wie gegeben; aus der Ausgabe zählt nur die 40-stellige Hex-Zeile (17.11.)."""
        for ref in (f"refs/heads/{zweig}", zweig):
            rc, aus = self.extern(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], self.repo)
            treffer = re.findall(r"^[0-9a-f]{40}$", aus or "", re.M)
            if rc == 0 and treffer:
                return treffer[-1]
        self.stopp("Stand bestimmen", f"Zweig {zweig} nicht gefunden")

    def datei(self, sha, pfad):
        return self.git("show", f"{sha}:{pfad}", schritt="Stand lesen")

    def release_art(self):
        """A1923: woher die Version kommt – {"modus": datei | tag, "version_datei", "changelog"} aus den Projekt-Einstellungen
        (release_modus, version_datei, changelog_datei); ohne Einstellung wie die AMW (amw/__init__.py, CHANGELOG.md)."""
        r = self.con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (self.pid,)).fetchone()
        e = json.loads((r[0] if r else None) or "{}")
        return {"modus": kern.projekt_wahl(self.con, self.pid, "release_modus"),
                "version_datei": e.get("version_datei") or "amw/__init__.py", "changelog": e.get("changelog_datei") or "CHANGELOG.md"}

    def nur_amw(self):
        """A1923: Die Kette liefert bisher nur die AMW selbst aus (Dienst, Versionszeile, Web) – Projekte mit eigener Versionsquelle
        stoppen vor dem ersten Schritt nach außen (Mehrprojekt 9, A1933)."""
        a = self.release_art()
        return a["modus"] == "datei" and a["version_datei"] == "amw/__init__.py"

    def notizen(self, sha, version):
        """Abschnitt der Version aus dem CHANGELOG des Stands: (Titel, Text). A1923: auch Keep a Changelog („## [X.Y.Z] - Datum“)."""
        text = self.datei(sha, self.release_art()["changelog"])
        m = re.search(rf"^## \[?{re.escape(version)}\]?(?![\d.])[^\n]*?(?:·\s*(?P<titel>[^\n]+))?\n(?P<text>.*?)(?=^## |\Z)",
                      text, re.M | re.S)
        if not m:
            self.stopp("Versionshinweise", f"im CHANGELOG fehlt „## {version}“")
        return (m.group("titel") or version).strip(), m.group("text").strip()

    def server_code(self, sha):
        """Online-Server-Code (web/*.php), den der Stand gegenüber main ändert (A1858, B2900)."""
        from . import mergeliste
        rc, aus = self.extern(["git", "-c", "core.quotepath=off", "diff", "--no-renames", "--name-only", f"main...{sha}"], self.repo)
        return mergeliste.server_code([z.strip() for z in aus.splitlines() if z.strip()]) if rc == 0 else []

    def version_an(self, sha):
        """Version an einem Stand, None wenn nicht lesbar: __version__ aus amw/__init__.py (die AMW). A1923: aus der
        version_datei des Projekts (erste Nummer X.Y.Z) bzw. bei release_modus = tag aus dem obersten Abschnitt des CHANGELOG
        unter [Unreleased] – dort schreibt das Bündel die Nummer hin."""
        a = self.release_art()
        pfad = a["changelog"] if a["modus"] == "tag" else a["version_datei"]
        rc, text = self.extern(["git", "show", f"{sha}:{pfad}"], self.repo)
        if rc != 0:
            return None
        if a["modus"] == "tag":
            m = re.search(r"^## \[?v?(\d+\.\d+\.\d+)\b", text, re.M)
        elif pfad == "amw/__init__.py":
            m = re.search(r'__version__ = "([^"]+)"', text)
        else:
            m = re.search(r"\b(\d+\.\d+\.\d+)\b", text)
        return m.group(1) if m else None

    def zwischenversionen(self, sha, version):
        """Versionen zwischen main und dem Release-Stand (TL #24530): [(version, [Commits mit dieser Nummer, alt → neu])]
        aufsteigend – die Kette taggt und trägt sie mit ein, damit keine Versionszeile fehlt. Welcher Commit getaggt wird,
        entscheidet vorbereiten() (A1878: der neueste mit grüner Prüfung – nicht einfach der letzte mit der Nummer, denn die
        nächste Aufgabe committet oft erst Arbeit und hebt die Nummer später)."""
        rc, aus = self.extern(["git", "rev-list", "--reverse", f"main..{sha}"], self.repo)
        if rc != 0:
            self.stopp("Zwischenversionen", aus[-200:])
        jetzt = kern.version_teile(self.version_an("main"))
        je = {}
        for c in aus.split():
            v = self.version_an(c)
            if v and v != version and kern.version_teile(v) and (not jetzt or kern.version_teile(v) > jetzt):
                je.setdefault(v, []).append(c)
        return sorted(je.items(), key=lambda x: kern.version_teile(x[0]))

    def staende(self, sha, ausnahme_aufgabe=None):
        """A1875 (P275/#29058): jeder Stand unter der Spitze ist geprüft. Für jeden Commit in main..sha: die Aufgaben aus seiner
        Betreffzeile („1.141.0: A1872 – …“) müssen als NEUESTE Prüfung GRÜN haben, auf einem Stand, der diesen Commit enthält –
        sonst ginge ein roter Stand mit einer grünen Spitze live. Ausnahme: die Aufgabe einer Auslieferung ohne Prüfbitte
        (Prüfstufe niedrig, --aufgabe). Rückgabe: Liste der Mängel (Aufgabe, Commit, Prüfung)."""
        rc, aus = self.extern(["git", "log", "--format=%H%x09%s", f"main..{sha}"], self.repo)
        if rc != 0:
            return [f"Stände: git log main..{sha[:8]} ging nicht"]
        mangel, gesehen = [], {}
        for zeile in aus.splitlines():
            if "\t" not in zeile:
                continue
            c, betreff = zeile.split("\t", 1)
            if not re.fullmatch(r"[0-9a-f]{40}", c):
                continue
            for nr in dict.fromkeys(int(x) for x in re.findall(r"\bA(\d{1,6})\b", betreff)):
                if nr == ausnahme_aufgabe:
                    continue
                if not self.con.execute("SELECT 1 FROM aufgabe WHERE id = ? AND projekt_id = ?", (nr, self.pid)).fetchone():
                    continue                                    # keine Aufgabe dieses Projekts (z. B. Zitat)
                if nr not in gesehen:
                    gesehen[nr] = self.con.execute("SELECT id, sha, ergebnis FROM pruefung WHERE projekt_id = ? AND aufgabe_id = ?"
                                                   " ORDER BY id DESC LIMIT 1", (self.pid, nr)).fetchone()
                p = gesehen[nr]
                if not p:
                    mangel.append(f"Stände: A{nr} hat einen Commit {c[:8]} im Bereich, aber keine Prüfung")
                elif p["ergebnis"] != "gruen":
                    mangel.append(f"Stände: A{nr} – neueste Prüfung P{p['id']} ist {p['ergebnis']} (Commit {c[:8]})")
                elif self.extern(["git", "merge-base", "--is-ancestor", c, p["sha"]], self.repo)[0] != 0:
                    mangel.append(f"Stände: A{nr} – Commit {c[:8]} steckt nicht im grün geprüften Stand P{p['id']} ({p['sha'][:8]})")
        return list(dict.fromkeys(mangel))

    def reihenfolge(self, sha, version):
        """Liegt eine kleinere Version grün und mit Merge-OK bereit, die dieser Stand NICHT enthält? Dann zuerst sie (TL #24530)."""
        ziel = kern.version_teile(version)
        live = kern.version_teile(self.version_an("main"))
        gesehen, aufgaben, fehlt = set(), set(), []
        for p in self.con.execute("SELECT * FROM pruefung WHERE projekt_id = ? AND ergebnis = 'gruen' AND aufgabe_id IS NOT NULL"
                                  " ORDER BY id DESC LIMIT 60", (self.pid,)).fetchall():
            if p["aufgabe_id"] in aufgaben:
                continue                                 # je Aufgabe zählt nur die neueste grüne Prüfung (17.11.: P246 vor P249)
            aufgaben.add(p["aufgabe_id"])
            if p["sha"] in gesehen or not betrieb.merge_ok(self.con, self.pid, p["aufgabe_id"], p["zweig"]):
                continue
            gesehen.add(p["sha"])
            a = self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (p["aufgabe_id"],)).fetchone()
            if a and a["status"] in ("fertig", "verworfen"):
                continue                                 # Aufgabe abgeschlossen: ihre Prüfung ist überholt (Befund CCamw2 14.11.)
            if self.extern(["git", "merge-base", "--is-ancestor", p["sha"], "main"], self.repo)[0] == 0:
                continue                                 # schon draußen
            if self.extern(["git", "merge-base", "--is-ancestor", p["sha"], sha], self.repo)[0] == 0:
                continue                                 # kommt mit diesem Stand mit
            v = self.version_an(p["sha"])
            if not v or not kern.version_teile(v) or (live and kern.version_teile(v) <= live):
                continue                                 # Nummer schon live (z. B. neu aufgesetzt und unter anderem Stand ausgeliefert)
            if self.extern(["git", "rev-parse", "-q", "--verify", f"refs/tags/v{v}"], self.repo)[0] == 0:
                continue                                 # Tag gibt es: ausgeliefert
            if kern.version_teile(v) < ziel:
                fehlt.append(f"Reihenfolge: {v} (A{p['aufgabe_id']}, {p['zweig']}@{p['sha'][:8]}) ist grün mit Merge-OK, aber nicht"
                             f" ausgeliefert und nicht in {sha[:8]} enthalten – erst {v} ausliefern oder neu aufsetzen")
        return fehlt

    # --- Vorbedingungen -------------------------------------------------------------------------------------------------
    def pruefen(self, zweig, gesamtlauf=None, aufgabe=None):
        sha = self.stand(zweig)
        a = self.release_art()                           # A1923: Versionsquelle des Projekts
        quelle = f"{a['changelog']} (release_modus tag)" if a["modus"] == "tag" else a["version_datei"]
        if a["modus"] != "tag":
            self.datei(sha, a["version_datei"])          # fehlt die Datei: Stopp „Stand lesen“ wie bisher
        version = self.version_an(sha)
        if not version:
            self.stopp("Version", f"{quelle} nennt keine Version")
        for z in self.uebertragen(sha, zweig):           # A1814: gleicher Inhalt nach dem Neu-Aufsetzen – Grün/Merge-OK gehen mit
            self.ausgabe(f"Freigabe übernommen – {z}")
        fehlt = []                                       # A1814: alle fehlenden Freigaben auf einmal nennen
        g = betrieb.ist_gruen(self.con, self.pid, sha)
        niedrig = False                                 # A1656: Prüfstufe niedrig (nur Doku/Tests) geht ohne Prüfbitte
        if g:
            p = self.con.execute("SELECT * FROM pruefung WHERE id = ?", (g["id"],)).fetchone()
        else:
            from . import kern, pruefstufe
            an = kern.projekt_wahl(self.con, self.pid, "pruefstufen") == "an"
            stufe, _ = pruefstufe.einstufen(pruefstufe.dateien(self.repo, sha), pruefstufe.muster(self.con, self.pid)) if an else (None, None)
            if stufe != "niedrig":
                offen = self.ungeprueft(self.reihe(sha))  # A1834: welche Commits keine Prüfung deckt
                fehlt.append(f"Prüfung: keine grüne Prüfung auf genau {sha[:8]} – erst Prüfbitte, dann GRÜN"
                             + (f" (Prüfstufe {stufe})" if an else "")
                             + (f"; ungeprüft: {', '.join(c[:8] for c in offen[:6])}" if len(offen) > 1 else ""))
                p = {"id": None, "aufgabe_id": int(aufgabe) if aufgabe else None, "zweig": zweig}
            elif not aufgabe:
                self.stopp("Prüfung", f"Prüfstufe niedrig: ohne Prüfbitte mit --aufgabe <nr> (für das Merge-OK des Leads)")
            else:
                p, niedrig = {"id": None, "aufgabe_id": int(aufgabe), "zweig": zweig}, True
        ok = None
        if not p["aufgabe_id"]:
            if p["id"]:
                fehlt.append(f"Merge-OK: P{p['id']} hängt an keiner Aufgabe – das Merge-OK gilt je Aufgabe")
        else:
            ok = betrieb.merge_ok(self.con, self.pid, p["aufgabe_id"], p["zweig"])
            if ok and str(p["zweig"] or "").startswith("buendel-") and ok["von"] == "AMW":
                ok = None                                # A1876 (F3b): ein Bündel gibt der Lead selbst frei – kein übernommenes OK
            if not ok:
                fehlt.append(f"Merge-OK: keins für A{p['aufgabe_id']} ({p['zweig']}) – der Lead gibt es mit amw freigabe merge"
                             f" {p['aufgabe_id']} --zweig {p['zweig']}")
        ausnahme = betrieb.gesamtlauf_ausnahme(self.con, self.pid, p["aufgabe_id"], baum_gleich=lambda s: self.baum(s) == self.baum(sha)) \
            if p["aufgabe_id"] else None                 # A1932: ein übertragenes OK hebt sie bei gleichem Baum nicht auf
        ausnahme = f"{ausnahme['von']}: {ausnahme['text']}" if ausnahme and not niedrig else None   # ohne Prüfbitte: nur echter Lauf
        # Gesamtlauf: zählt nur, wenn der beim tatsächlichen Start gemerkte Stand genau dieser ist und sauber war (TL #24259) –
        # die Beschreibung kann veralten (Arbeitsbaum zwischen Einreihen und Start gewechselt)
        stand = f"%{betrieb.stand_text(('', sha, True))}%"
        lauf = None
        if gesamtlauf:
            lauf = self.con.execute("SELECT * FROM lauf WHERE id = ? AND projekt_id = ?", (int(str(gesamtlauf).lstrip("Ll")), self.pid)).fetchone()
            if not lauf or lauf["status"] != "fertig" or lauf["rc"] != 0:
                fehlt.append(f"Gesamtlauf: L{gesamtlauf} ist nicht grün fertig")
                lauf = None
            elif betrieb.stand_text(("", sha, True)) not in (lauf["ergebnis"] or ""):
                fehlt.append(f"Gesamtlauf: L{gesamtlauf} hat nicht genau {sha[:8]} sauber geprüft (Ergebnis: {(lauf['ergebnis'] or '')[:80]})")
                lauf = None
        else:                                           # ein grüner Lauf geht vor; ohne ihn nur die Ausnahme des Leads
            lauf = self.con.execute("SELECT * FROM lauf WHERE projekt_id = ? AND status = 'fertig' AND rc = 0 AND ergebnis LIKE ?"
                                    " ORDER BY id DESC LIMIT 1", (self.pid, stand)).fetchone()
            if not lauf and not ausnahme:
                fehlt.append(f"Gesamtlauf: kein grüner Lauf, der genau {sha[:8]} sauber geprüft hat – --gesamtlauf L<nr>, oder der Lead"
                             f" vermerkt eine Ausnahme: amw freigabe merge {p['aufgabe_id']} --ausnahme \"Grund\"")
        # nur Änderungen an versionierten Dateien halten an (A1663) – unversionierte stören den Fast-Forward nicht; würde eine
        # überschrieben, verweigert git den Merge selbst (dann Stopp bei „Fast-Forward“)
        geaendert = self.git("status", "--porcelain", "--untracked-files=no", schritt="Arbeitsbaum").strip()
        if geaendert:
            self.stopp("Arbeitsbaum", f"{self.repo} hat ungesicherte Änderungen: {' '.join(z[3:] for z in geaendert.splitlines()[:5])}")
        fremd = [z[3:] for z in self.git("status", "--porcelain", schritt="Arbeitsbaum").splitlines() if z.startswith("??")]
        if fremd:
            self.ausgabe(f"Hinweis: unversioniert im Arbeitsbaum (stört nicht): {', '.join(fremd[:5])}")
        rc, _ = self.extern(["git", "merge-base", "--is-ancestor", "main", sha], self.repo)
        if rc != 0:
            self.stopp("Fast-Forward", f"main ist kein Vorfahre von {sha[:8]} – erst neu aufsetzen")
        rc, _ = self.extern(["git", "rev-parse", "-q", "--verify", f"refs/tags/v{version}"], self.repo)
        if rc == 0:
            self.stopp("Tag", f"v{version} gibt es schon")
        titel, text = self.notizen(sha, version)
        server = self.server_code(sha)                  # A1858 (B2900): Online-Server-Code im Stand → eigene Zeile im Versionshinweis
        if server and "Server-Code geändert" not in text:
            text += f"\n- **Server-Code geändert:** {', '.join(server[:6])}" + (" …" if len(server) > 6 else "")
        fehlt += self.reihenfolge(sha, version)
        fehlt += self.staende(sha, ausnahme_aufgabe=aufgabe if niedrig else None)
        if fehlt:                                        # A1814: alles auf einmal – nicht eine Freigabe nach der anderen
            self.stopp("Freigaben", f"{len(fehlt)} fehlt: " + " · ".join(fehlt))
        zwischen, aufgegangen = [], []
        gruen = [r[0] for r in self.con.execute("SELECT sha FROM pruefung WHERE projekt_id = ? AND ergebnis = 'gruen'", (self.pid,))]
        for v, commits in self.zwischenversionen(sha, version):
            if self.extern(["git", "rev-parse", "-q", "--verify", f"refs/tags/v{v}"], self.repo)[0] == 0:
                continue                                 # schon getaggt (z. B. von Hand)
            # A1878 (#29128: 1.142.0 grün auf b5359ce, danach A1867-Arbeit noch unter 1.142.0): der neueste geprüfte Commit
            c = next((x for x in reversed(commits)
                      if any(g and len(g) >= 7 and (x.startswith(g) or g.startswith(x)) for g in gruen)), None)   # P265 (a): wie ist_gruen
            if not c:
                aufgegangen.append(v)                    # A1866 (17.11.: 1.132.0/1.133.0 nach Umnummerieren): kein eigenes Release
                continue
            zwischen.append({"version": v, "sha": c, "notizen": self.notizen(c, v)})   # CHANGELOG an ihrem eigenen Stand
        if aufgegangen:
            self.ausgabe(f"Ohne eigene grüne Prüfung auf ihrem Stand, kein eigenes Release: {', '.join(aufgegangen)} – geht in {version} auf")
        return {"sha": sha, "version": version, "lauf": lauf["id"] if lauf else None, "ausnahme": None if lauf else ausnahme,
                "titel": titel, "text": text, "niedrig": niedrig, "zwischen": zwischen,
                "merge_ok": ok["von"] if ok else None}

    # --- die Kette ------------------------------------------------------------------------------------------------------
    def ausliefern(self, zweig, gesamtlauf=None, aufgabe=None):
        """Die ganze Kette. A1866 (P257): bricht sie mit einem unerwarteten Fehler ab (keine Stopp-Meldung), wird daraus ein Stopp
        mit dem Hinweis auf den Wartungsmodus – sonst bliebe er ohne Hinweis an."""
        try:
            return self._ausliefern(zweig, gesamtlauf, aufgabe)
        except Stopp:
            raise
        except Exception as e:                                   # noqa: BLE001 – jeder andere Fehler wird zum Stopp mit Hinweis
            if not getattr(self, "wartung_an", False):
                raise
            import traceback                                     # P265 (c): der Traceback geht nicht verloren
            try:                                                 # P266: ist die Datenbank selbst der Fehler, bleibt es beim Stopp
                with db.schreiben(self.con):
                    db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von=self.von, art="auslieferung_fehler",
                                 text=traceback.format_exc()[-1500:])
            except Exception:                                    # noqa: BLE001
                pass
            self.stopp("Unerwarteter Fehler", f"{type(e).__name__}: {str(e)[:300]} (Traceback im Protokoll: plan_ereignis auslieferung_fehler)")

    def _ausliefern(self, zweig, gesamtlauf=None, aufgabe=None):
        v = self.pruefen(zweig, gesamtlauf, aufgabe)
        sha, version, ausnahme = v["sha"], v["version"], v["ausnahme"]
        self.ausgabe(f"Version {version} = {sha[:8]} · {'Prüfstufe niedrig (ohne Prüfbitte)' if v['niedrig'] else 'Prüfung grün'} · Merge-OK {v['merge_ok']} · "
                     + (f"Gesamtlauf L{v['lauf']}" if v["lauf"] else f"Ausnahme ({ausnahme})"))
        if not self.nur_amw():                          # A1923 (#29877): klarer Stopp vor dem ersten Schritt nach außen
            self.stopp("Projekt", f"Version {version} ist geprüft und freigegeben – ausliefern kann die Kette bisher nur die AMW selbst"
                       " (Dienst, Web). Für Projekte mit eigener Versionsquelle kommt das mit Mehrprojekt 9 (A1933); nichts geändert,"
                       " kein Tag gesetzt")
        from . import waechter                         # A1847/P253: während jeder Auslieferung keine neuen p-Starts
        wartung = not waechter.zustand()["wartung"]     # schon an (von Hand): bleibt, wie es war
        if wartung:
            waechter.wartung_an("Auslieferung der AMW")
        self.wartung_an = True                           # bricht die Kette ab, bleibt er an – stopp() sagt es
        if waechter.p_laufend(self.con):
            fertig, rest = waechter.vor_auslieferung(self.con)
            if not fertig:
                self.stopp("Wartungsmodus", "p-Pakete laufen noch: " + ", ".join(f"A{x}" for x in rest)
                           + " – später erneut ausliefern")
            self.schritt("Wartungsmodus – keine p-Pakete mehr laufend")
        from . import dokumente
        ziel = db.sichern(None)
        dokumente.sichern(os.path.splitext(ziel)[0] + "-dokumente")
        self.schritt(f"Sicherung {os.path.basename(ziel)}")
        self.git("merge", "--ff-only", "-q", sha, schritt="Fast-Forward")
        self.schritt(f"main → {sha[:8]}")
        for z in v["zwischen"]:                         # Zwischenversionen im selben Stand: eigene Tags (TL #24530)
            self.git("tag", f"v{z['version']}", z["sha"], schritt="Tag")
        self.git("tag", f"v{version}", sha, schritt="Tag")
        self.schritt(f"Tag v{version}" + "".join(f" + v{z['version']}" for z in v["zwischen"]))
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
        from . import veroeffentlichung                 # A1928 (TH158): Push und GitHub-Release erst bei der Abnahme des Meilensteins
        sofort = veroeffentlichung.modus(self.con, self.pid) == "sofort"
        if not sofort:
            self.schritt("Lokal live – Push und GitHub-Release bei der Abnahme des Meilensteins (veroeffentlichen = meilenstein)")
        else:
            self._veroeffentlichen(version, v)
        self.lokal_live = not sofort
        # A1756: erst Versionszeilen und fertige Aufgaben, dann der Web-Abzug – scheitert er (14.11.: Zeitlimit unter Last),
        # ist alles andere schon eingetragen, und die Meldung nennt, wie er nachgeholt wird.
        return self._nach_dienst(sha, version, v, ausnahme, wartung)

    def _veroeffentlichen(self, version, v):
        """Wie bis 1.15x bei jeder Auslieferung (veroeffentlichen = sofort): Push main + Tags, GitHub-Release je Version."""
        self.git("push", "-q", "origin", "main", *[f"v{z['version']}" for z in v["zwischen"]], f"v{version}", schritt="Push")
        self.schritt("Push main + Tag")
        for nummer, notiztext, neueste in [(z["version"], z["notizen"][1], False) for z in v["zwischen"]] + [(version, v["text"], True)]:
            notiz = os.path.join(os.path.dirname(db.db_pfad()), f"notizen-{nummer}.md")
            with open(notiz, "w", encoding="utf-8", newline="") as f:
                f.write(notiztext + "\n")
            try:
                rc, aus = self.extern(["gh", "release", "create", f"v{nummer}", "--title", nummer, "--notes-file", notiz,
                                       "--latest" if neueste else "--latest=false"], self.repo)
            finally:
                os.remove(notiz)
            if rc != 0:
                self.stopp("GitHub-Release", f"v{nummer}: {aus[-300:]}")
        self.schritt("GitHub-Release" + (f" (+ {', '.join(z['version'] for z in v['zwischen'])})" if v["zwischen"] else ""))

    def _nach_dienst(self, sha, version, v, ausnahme, wartung):
        from . import waechter, wissen
        for z in v["zwischen"]:                         # aufsteigend vor der obersten – „größer als die letzte“ bleibt wahr
            if not self.con.execute("SELECT 1 FROM release WHERE projekt_id = ? AND art = 'version' AND version = ?",
                                    (self.pid, z["version"])).fetchone():
                wissen.release_version(self.con, self.pid, self.von, z["version"], z["notizen"][0], z["sha"][:7],
                                       oeffentlich=z["notizen"][1], kette=True)
        rid, _ = wissen.release_version(self.con, self.pid, self.von, version, v["titel"], sha[:7], kette=True)
        if self.lokal_live:                             # A1928: was noch nicht veröffentlicht ist (Für dich → Abnehmen)
            from . import veroeffentlichung
            with db.schreiben(self.con):
                db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von=self.von, art=veroeffentlichung.LOKAL,
                             text=json.dumps({"version": version, "sha": sha}))
        self.schritt(f"Versionszeile R{rid}" + (f" (+ {', '.join(z['version'] for z in v['zwischen'])})" if v["zwischen"] else ""))
        from . import planautomatik                     # A1738: was dieser Stand enthält, ist fertig (Beleg = geprüfter Stand)
        try:
            fertig = planautomatik.ausgeliefert(self.con, self.pid, version, sha,
                                                lambda s: self.extern(["git", "merge-base", "--is-ancestor", s, sha], self.repo)[0] == 0)
        except Exception as e:                           # ausgeliefert ist ausgeliefert – nur melden
            fertig = [{"aufgabe": 0, "titel": "", "fehler": f"{type(e).__name__}: {e}"}]
        ok = [x for x in fertig if not x.get("fehler")]
        if fertig:
            self.schritt("Aufgaben fertig: " + (", ".join(f"A{x['aufgabe']}" for x in ok) or "keine")
                         + "".join(f" · A{x['aufgabe']} nicht: {x['fehler'][:120]}" for x in fertig if x.get("fehler"))
                         + "".join(f" · A{x['aufgabe']} Paket {x['paket'][:120]}" for x in ok if x.get("paket")))
        fertig_liste = ", ".join(f"A{x['aufgabe']}" for x in ok)
        kriterien = "".join(f" A{x['aufgabe']} hat offene Kriterien: {' | '.join(x['kriterien_offen'][:3])}." for x in ok if x["kriterien_offen"])
        kurz = version.replace(".", "")
        lid = betrieb.lauf_start(self.con, self.pid, self.von, f"Web-Abzug {version} (leicht)", schwer=False, ordner=self.repo)
        rc, aus = self.web_abzug(version, sha, kurz)
        betrieb.lauf_ende(self.con, self.pid, self.von, lid, rc, (f"rc {rc} · " + (aus[-300:] if rc else "web-Zweig aktualisiert"))[:500])
        if rc != 0:
            self.stopp("Web-Abzug", f"L{lid}: {aus[-300:]} – Versionszeilen und Aufgaben sind schon eingetragen; nachholen: ein"
                                    f" Commit mit dem Baum {sha[:8]}:web und origin/web als Eltern (git commit-tree), dann"
                                    " Fast-Forward-Push nach web")
        self.schritt(f"Web-Abzug L{lid}")
        an = kern.lead(self.con, self.pid)
        if an and an != self.von:
            with db.schreiben(self.con):
                kern._posten(self.con, self.pid, "AMW", an, "info", f"Version {version} {'lokal ' if self.lokal_live else ''}live – {v['titel']}",
                             f"main {sha[:8]}, Tag v{version}, " + ("lokal (veröffentlicht wird bei der Abnahme des Meilensteins)"
                                                                    if self.lokal_live else "GitHub-Release")
                             + f", Web-Abzug L{lid}, Versionszeile R{rid}."
                             + (f" Gesamtlauf L{v['lauf']}." if v["lauf"] else f" Ohne Gesamtlauf: {ausnahme}.")
                             + (f" Fertig gesetzt: {fertig_liste}." if ok else "") + kriterien)
        if wartung:
            waechter.wartung_aus()
            self.ausgabe("Wartungsmodus aufgehoben")
        self.ausgabe(f"Version {version} {'lokal ' if self.lokal_live else ''}live.")
        return {"version": version, "sha": sha, "web_lauf": lid, "release": rid}
