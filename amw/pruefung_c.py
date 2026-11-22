"""Prüfung C: die eigene Prüfung der AMW nach einem -p-Lauf, nie im Arbeitsbereich des Arbeiters (A1849, M50 S6a;
D1258 v14 §6a.3). Die Meldung des Arbeiters steuert nur, wohin das Paket geht – ob die Arbeit gut ist, entscheidet allein C.

1. (arbeiter.laufen) Job-Objekt hart beendet, keine Restprozesse.
2. Die AMW liest die Änderungen mit eigenem git: eigenes Prüf-Repo (--git-dir) im Datenordner des Platzes, Klon nur als
   --work-tree, eigener Index. Konfiguration neutral (keine globale/System-Konfiguration, Hooks-Pfad leer, fsmonitor aus) –
   aus .git/config des Platzes wird nichts gelesen oder ausgeführt. Die Basis kommt aus dem Projektordner, nicht aus dem Platz.
   Diff-Tor (Bereiche, gesperrte Pfade, automatisch geladene Dateien), Geheimnis-Muster, Adressen/Aufrufe nach außen;
   dann committet die AMW selbst als AMW-Arbeiter.
3. Netto-Diff leer → C/leer. Diff-Tor/Geheimnis → C/diff. Adressen/gefährliche Aufrufe → C/aussen.
4. Abnahme in einem frischen, sauberen Checkout genau dieses Commits mit frischem Datenordner, mit Zeitlimit und der minimalen
   Umgebung des Arbeiters (keine Zugänge des Menschen): Paket-Abnahme-Befehl plus feste Regressions-Kurzsuite.
   Nicht ausführbar / Zeitlimit → C/technik; Exit ≠ 0 eines vollständig gelaufenen Befehls → C/rot.
5. Pakettyp test-schreiben: maschinell rot gegen alten, grün gegen neuen Code, mindestens ein ausgeführter Test.
7. (A1962) Sprach-Server-Prüfung: pyright über das ganze Projekt im Paket-Stand und im Start-Commit, nur neue Fehler → C/rot.
   Pakettyp test-ergaenzen (A1895): nur Testdateien geändert, grün, mindestens ein wirklich ausgeführter (nicht übersprungener) Test.
"""
import datetime
import fnmatch
import os
import re
import subprocess

from . import abnahme

# nicht je Paket wählbar (§6a.3.4): kurz, ohne Fenster, ohne Netz. A1919/A1920 (TH160 F2): je Projekt (regression_befehl);
# ohne Einstellung gilt diese Kurzsuite nur für das Projekt, das die AMW selbst ist (ist_amw), andere Projekte ohne
REGRESSION = "python -X utf8 -m unittest tests.test_abschotten tests.test_live_schutz tests.test_abnahme tests.test_hilfen"
OHNE_REGRESSION = "ohne Rückschritt-Tests geprüft (für dieses Projekt keine eingestellt: amw projekt einstellen regression_befehl=…)"
AUS_REGRESSION = "ohne Rückschritt-Tests geprüft (für dieses Projekt ausgeschaltet: regression_befehl=aus)"


def ist_amw(ordner):
    """A1920: Ist der Projektordner die AMW selbst? (eigener Code und Befehl darin – nicht am Namen des Projekts erkannt)"""
    return bool(ordner) and os.path.isfile(os.path.join(ordner, "amw", "pruefung_c.py")) and os.path.isfile(os.path.join(ordner, "amw-cli.py"))


def projekt_abnahme(con, pid):
    """A1920: {"regression": Befehl oder None, "hinweis": Text oder None, "frist_s"} für Pakete des Projekts – aus den
    Projekt-Einstellungen regression_befehl (Befehl | aus) und abnahme_frist_min; ohne Einstellung wie oben."""
    import json
    from . import kern
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    try:
        e = json.loads((r[0] if r else None) or "{}")
    except ValueError:
        e = {}
    frist = int(e.get("abnahme_frist_min") or 0) * 60 or abnahme.FRIST_S
    sprache = kern.projekt_wahl(con, pid, "sprachpruefung")          # A1962: auto | pyright | aus
    befehl = str(e.get("regression_befehl") or "").strip()
    if befehl.lower() == "aus":
        return {"regression": None, "hinweis": AUS_REGRESSION, "frist_s": frist, "sprache": sprache}
    if befehl:
        return {"regression": befehl, "hinweis": None, "frist_s": frist, "sprache": sprache}
    if ist_amw(kern.projekt_ordner(con, pid)):
        return {"regression": REGRESSION, "hinweis": None, "frist_s": frist, "sprache": sprache}
    return {"regression": None, "hinweis": OHNE_REGRESSION, "frist_s": frist, "sprache": sprache}
# Dateien, die Python/Werkzeuge beim Start von selbst laden (§6a.3.3): die Liste gibt es genau einmal – in abnahme.GESPERRT
# (Besitzer Abnahme-Modul, D1258 §5); hier nur die Auswahl für den eigenen Befund „automatisch geladen“
AUTOGELADEN = tuple(m for m, _, grund in abnahme.GESPERRT if grund.startswith("automatisch geladen")) + ("pytest.ini", "*/pytest.ini")
GIT_NAME, GIT_EMAIL = "AMW-Arbeiter", "arbeiter@amw.invalid"
# Geheimnis-Muster: nur der Name des Treffers wird gemeldet, nie der Wert
GEHEIM = (("privater Schlüssel", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
          ("Anthropic-Schlüssel", r"sk-ant-[A-Za-z0-9_-]{16,}"),
          ("GitHub-Token", r"\b(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})"),
          ("AWS-Schlüssel", r"\bAKIA[0-9A-Z]{16}\b"),
          ("Slack-Token", r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
          ("Google-Schlüssel", r"\bAIza[0-9A-Za-z_-]{35}\b"),
          ("JWT", r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
          ("Zuweisung eines Geheimnisses", r"(?i)\b(password|passwort|secret|token|api[_-]?key|auth)\w*\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"))
# nach außen (§6a.5, automatisch für alle Pakete): Adressen fremder Hosts und gefährliche Aufrufe
EIGENE_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "::1", "example.com", "example.org", "example.net")
AUFRUFE = (("Shell/Prozess", r"\b(os\.system|os\.popen|subprocess\.|shell_exec|proc_open|popen\(|passthru\()"),
           ("eval/exec", r"(?<![\w.])(eval|exec)\s*\("),
           ("Netz", r"\b(requests\.|urllib\.request|http\.client|socket\.|curl_init|file_get_contents\(\s*['\"]https?:|fetch\(\s*['\"]https?:)"),
           ("Datei außerhalb des Projekts", r"(['\"][A-Za-z]:[\\/]|expanduser\(|%USERPROFILE%|%APPDATA%|os\.environ\[['\"](USERPROFILE|APPDATA|HOME)['\"]\])"))


class PruefFehler(RuntimeError):
    pass


def _leer(p):
    o = os.path.join(p["daten"], "pruefung")
    os.makedirs(os.path.join(o, "hooks-leer"), exist_ok=True)
    cfg = os.path.join(o, "gitconfig-leer")
    open(cfg, "a").close()
    return o, cfg


_AUTOCRLF = {}


def autocrlf():
    """core.autocrlf, mit dem git die Klone auf diesem PC auschecken (Konfiguration der AMW selbst, nicht die des Platzes).
    Ohne denselben Wert hielte das Prüf-Repo jede ausgecheckte Datei für geändert (CRLF gegen LF)."""
    if "wert" not in _AUTOCRLF:
        r = subprocess.run(["git", "config", "--get", "core.autocrlf"], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                           cwd=os.path.expanduser("~"), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        v = r.stdout.strip().lower()
        _AUTOCRLF["wert"] = v if v in ("true", "input", "false") else "false"
    return _AUTOCRLF["wert"]


_AUTOCRLF_PROJEKT = {}


def autocrlf_projekt(ordner):
    """A1909/A1911: core.autocrlf, wie git im Repo von `ordner` (dem Projektordner) selbst ihn sieht – Repo-Einstellung vor
    System und Benutzer. Mit diesem Wert checken Bündel, Arbeiter-Klone und der frische Checkout von Prüfung C aus, damit sie
    dieselben Zeilenenden haben wie das Projekt (F:\\amw: false → LF; der Systemwert true gäbe CRLF). Nicht ermittelbar → false."""
    schluessel = os.path.normcase(os.path.abspath(ordner))
    if schluessel not in _AUTOCRLF_PROJEKT:
        try:
            r = subprocess.run(["git", "-C", ordner, "config", "--get", "core.autocrlf"], capture_output=True, text=True, timeout=30,
                               stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            v = r.stdout.strip().lower()
        except (OSError, subprocess.SubprocessError):
            v = ""
        _AUTOCRLF_PROJEKT[schluessel] = v if v in ("true", "input", "false") else "false"
    return _AUTOCRLF_PROJEKT[schluessel]


def autocrlf_klon(klon):
    """A1911: core.autocrlf, mit dem der Arbeiter-Klon ausgecheckt ist – seine eigene Einstellung (seit A1911 die des Projekts,
    platz.zeilenenden_angleichen), sonst der Systemwert (Klone von vorher). Beim Einsammeln zählt dieser Wert: Mit einem
    anderen sähe git jede Datei mit anderen Zeilenenden als geändert."""
    try:
        r = subprocess.run(["git", "config", "--file", os.path.join(klon, ".git", "config"), "--get", "core.autocrlf"],   # nur lesen,
                           capture_output=True, text=True, timeout=30,                                            # nur diese Datei
                           stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        v = r.stdout.strip().lower()
    except (OSError, subprocess.SubprocessError):
        v = ""
    return v if v in ("true", "input", "false") else autocrlf()


def _umgebung(p, extra=None):
    """Neutrale Umgebung für git: keine Konfiguration des Menschen, keine Hooks, kein fsmonitor, keine Rückfragen.
    core.autocrlf: der Wert des Projekts, wenn `p` ihn trägt (A1911, pruefen setzt ihn), sonst der Systemwert."""
    o, cfg = _leer(p)
    u = {k: v for k, v in os.environ.items() if k.upper() in ("SYSTEMROOT", "PATH", "PATHEXT", "COMSPEC", "TEMP", "TMP", "USERPROFILE",
                                                              "HOMEDRIVE", "HOMEPATH", "WINDIR")}
    u.update(GIT_CONFIG_GLOBAL=cfg, GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0", GIT_CONFIG_COUNT="4",
             GIT_CONFIG_KEY_3="core.autocrlf", GIT_CONFIG_VALUE_3=p.get("autocrlf") or autocrlf(),
             GIT_CONFIG_KEY_0="core.hooksPath", GIT_CONFIG_VALUE_0=os.path.join(o, "hooks-leer"),
             GIT_CONFIG_KEY_1="core.fsmonitor", GIT_CONFIG_VALUE_1="false", GIT_CONFIG_KEY_2="core.quotepath", GIT_CONFIG_VALUE_2="off",
             GIT_AUTHOR_NAME=GIT_NAME, GIT_AUTHOR_EMAIL=GIT_EMAIL, GIT_COMMITTER_NAME=GIT_NAME, GIT_COMMITTER_EMAIL=GIT_EMAIL)
    u.update(extra or {})
    return u


def _git(p, *args, arbeitsbaum=None, extra=None, ok=(0,)):
    befehl = ["git", f"--git-dir={repo(p)}"] + ([f"--work-tree={arbeitsbaum}"] if arbeitsbaum else []) + list(args)
    r = subprocess.run(befehl, capture_output=True, text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=600,
                       env=_umgebung(p, extra), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode not in ok:
        raise PruefFehler(f"git {' '.join(args[:3])}: {(r.stdout + r.stderr).strip()[-300:]}")
    return r.stdout


def repo(p):
    return os.path.join(p["daten"], "pruefung", "repo.git")


def repo_anlegen(p):
    """Eigenes Prüf-Repo (bare) im Datenordner des Platzes – nie das .git des Klons."""
    r = repo(p)
    if not os.path.isdir(r):
        os.makedirs(os.path.dirname(r), exist_ok=True)
        subprocess.run(["git", "init", "-q", "--bare", r], check=True, capture_output=True, env=_umgebung(p),
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r


def basis_holen(p, quelle, basis):
    """Die Basis aus dem Projektordner holen (nicht aus dem Platz) – danach ist sie im Prüf-Repo."""
    repo_anlegen(p)
    _git(p, "fetch", "-q", "--no-tags", quelle, "+refs/heads/*:refs/quelle/*")
    _git(p, "cat-file", "-e", f"{basis}^{{commit}}")


REPARSE = 0x400                                                # FILE_ATTRIBUTE_REPARSE_POINT (Symlink, Junction …)


def verweise(wurzel):
    """P268: Verweise im Arbeitsbaum (ohne .git) – Symlinks, Junctions und andere Reparse-Points sowie Hardlinks auf Dateien
    mit weiteren Namen. git add folgt Junctions und nähme so Dateien von außen (Benutzerordner, Live-Daten) ins Repo; ein
    Hardlink (gleiches Laufwerk) zeigt denselben Inhalt wie eine Datei außerhalb. Rückgabe [(pfad, art)] relativ zu wurzel."""
    aus = []
    for ordner, unter, dateien in os.walk(wurzel, topdown=True, followlinks=False):
        rel_ordner = os.path.relpath(ordner, wurzel)
        if rel_ordner == ".":
            unter[:] = [u for u in unter if u.lower() != ".git"]
        behalten = []
        for u in unter:
            pfad = os.path.join(ordner, u)
            st = os.lstat(pfad)
            if os.path.islink(pfad) or getattr(st, "st_file_attributes", 0) & REPARSE or getattr(os.path, "isjunction", lambda x: False)(pfad):
                aus.append((os.path.relpath(pfad, wurzel).replace(os.sep, "/"), "Verweis (Symlink/Junction)"))
            else:
                behalten.append(u)
        unter[:] = behalten                                       # nie in einen Verweis hineingehen
        for d in dateien:
            pfad = os.path.join(ordner, d)
            st = os.lstat(pfad)
            rel = os.path.relpath(pfad, wurzel).replace(os.sep, "/")
            if os.path.islink(pfad) or getattr(st, "st_file_attributes", 0) & REPARSE:
                aus.append((rel, "Verweis (Symlink)"))
            elif st.st_nlink > 1:
                aus.append((rel, "Hardlink (weiterer Name derselben Datei)"))
    return sorted(aus)


def einsammeln(p, basis, aid, nachricht):
    """Den Arbeitsbaum des Klons (nur als Daten) gegen `basis` einsammeln und als AMW-Arbeiter committen. None = nichts geändert."""
    index = os.path.join(os.path.dirname(repo(p)), "index")
    if os.path.exists(index):
        os.replace(index, index + ".alt")                                   # nicht löschen: der nächste read-tree überschreibt ohnehin
    extra = {"GIT_INDEX_FILE": index}
    _git(p, "read-tree", basis, extra=extra)
    _git(p, "add", "-A", arbeitsbaum=p["klon"], extra=extra)          # ohne Pfadangabe: der ganze Arbeitsbaum (.git bleibt draußen)
    baum = _git(p, "write-tree", extra=extra).strip()
    if baum == _git(p, "rev-parse", f"{basis}^{{tree}}").strip():
        return None
    kopf = _git(p, "commit-tree", baum, "-p", basis, "-m", nachricht).strip()
    _git(p, "update-ref", f"refs/heads/paket-A{aid}", kopf)
    return kopf


def geaendert(p, basis, kopf):
    zwischen = lambda n: "/__pycache__/" in "/" + n or n.endswith((".pyc", ".pyo"))
    return sorted(n for n in _git(p, "diff", "--no-renames", "--name-only", basis, kopf).splitlines() if n and not zwischen(n))


def zusaetze(p, basis, kopf):
    """Hinzugefügte Zeilen des Netto-Diffs: [(pfad, zeile)]."""
    aus, pfad = [], None
    for z in _git(p, "diff", "--no-renames", "-U0", basis, kopf).splitlines():
        if z.startswith("+++ "):
            pfad = z[6:] if z.startswith("+++ b/") else None
        elif z.startswith("+") and pfad:
            aus.append((pfad, z[1:]))
    return aus


def autogeladen(pfade):
    return [p for p in pfade if any(fnmatch.fnmatchcase(p.lower(), m.lower()) for m in AUTOGELADEN)]


def geheimnisse(zeilen):
    """[(pfad, art)] – nie der Wert selbst."""
    return sorted({(p, art) for p, z in zeilen for art, m in GEHEIM if re.search(m, z)})


def nach_aussen(zeilen):
    """[(pfad, was)] für neue Adressen fremder Hosts und gefährliche Aufrufe."""
    aus = set()
    for p, z in zeilen:
        for host in re.findall(r"https?://([A-Za-z0-9.-]+)", z):
            h = host.lower().rstrip(".")
            if not (h in EIGENE_HOSTS or h.endswith((".invalid", ".example", ".localhost", ".test"))):
                aus.add((p, f"Adresse {h}"))
        for was, m in AUFRUFE:
            if re.search(m, z):
                aus.add((p, was))
    return sorted(aus)


def _frisch(p, kopf):
    """Frischer, sauberer Checkout genau dieses Commits mit frischem Datenordner (eigener Port wie der Platz)."""
    stempel = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    wurzel = os.path.join(p["daten"], "pruefung", "abnahme", f"{kopf[:10]}-{stempel}")
    klon = os.path.join(wurzel, "stand")
    # A1911: der Wert steht auch in der Konfiguration des Klons – git in den Tests (Umgebung des Arbeiters, ohne System-
    # Konfiguration) sieht dann dieselben Zeilenenden wie der Checkout
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", "--no-checkout", "-c", f"core.autocrlf={p.get('autocrlf') or autocrlf()}",
                    repo(p), klon], check=True, capture_output=True, env=_umgebung(p),
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    r = subprocess.run(["git", "-C", klon, "checkout", "-q", "--detach", kopf], capture_output=True, text=True, env=_umgebung(p),
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode:
        raise PruefFehler(f"Checkout {kopf[:8]}: {(r.stdout + r.stderr).strip()[-300:]}")
    daten = os.path.join(wurzel, "daten")
    q = {"nr": p["nr"], "klon": klon, "daten": daten, "db": os.path.join(daten, "amw.db"), "lad": os.path.join(daten, "lad"),
         "tmp": os.path.join(daten, "tmp"), "claude": os.path.join(daten, "claude"), "port": p["port"]}
    for d in (q["lad"], q["tmp"]):
        os.makedirs(d, exist_ok=True)
    return q


TECHNIK_RC = (9009, 127)                                       # cmd: „Befehl nicht gefunden“ / sh: dasselbe
# cmd meldet einen unbekannten Befehl je nach Sprache mit rc 1 und diesem Text – das ist „nicht ausführbar“, nicht „rot“
# (nur der Befehl selbst fehlt – ein kaputter Import im Code des Arbeiters ist rot, nicht technisch: er soll nachbessern, E5)
NICHT_GEFUNDEN = re.compile(r"(konnte nicht gefunden werden|ist entweder falsch geschrieben|is not recognized as an internal or external"
                            r"|command not found)", re.I)


def _laufen(q, befehl, frist, werkzeuge=None):
    from . import arbeiter
    r = abnahme.ausfuehren(befehl, q["klon"], arbeiter.umgebung(q, werkzeuge=werkzeuge), frist)   # dieselbe Umgebung wie der Arbeiter
    nicht_da = r["rc"] not in (0, None) and NICHT_GEFUNDEN.search((r.get("ausgabe") or "")[:600])
    if r.get("fehler") or r["zeitlimit"] or r["rc"] in TECHNIK_RC or r["rc"] is None or nicht_da:
        r["befund"] = "C/technik"
    elif r["rc"] != 0:
        r["befund"] = "C/rot"
    else:
        r["befund"] = None
    return r


def _tests_gelaufen(ausgabe):
    m = re.findall(r"^Ran (\d+) tests?", ausgabe or "", re.M)
    return int(m[-1]) if m else 0


def _tests_uebersprungen(ausgabe):
    """A1895: „OK (skipped=3)“ bzw. „FAILED (…, skipped=3)“ von unittest – übersprungene Tests beweisen nichts."""
    m = re.findall(r"skipped=(\d+)", ausgabe or "")
    return int(m[-1]) if m else 0


def zweig_befund(quelle, zweig, bereiche, typ=None, haupt="main", aussen=True, sperrmuster=None):
    """Interaktive Pakete (§6a.6): der leichte Teil von C sofort und ohne schweren Lauf – Netto-Diff des Zweigs gegen main,
    Diff-Tor, automatisch geladene Dateien, Geheimnis-Muster, nach außen. Die Abnahme im frischen Checkout läuft über die
    Lauf-Schlange (Disponent, S6c). Rückgabe wie pruefen() ohne abnahme/regression."""
    def git(*args):
        r = subprocess.run(["git", "-c", "core.quotepath=off", "-C", quelle, *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", stdin=subprocess.DEVNULL, timeout=300, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode:
            raise PruefFehler(f"git {' '.join(args[:3])}: {(r.stdout + r.stderr).strip()[-300:]}")
        return r.stdout
    b = {"code": None, "kopf": None, "geaendert": [], "ausserhalb": [], "gesperrt": [], "autogeladen": [], "geheim": [], "aussen": [],
         "abnahme": None, "regression": None, "test_schreiben": None, "grund": None}
    try:
        kopf = git("rev-parse", "--verify", f"refs/heads/{zweig}^{{commit}}").strip()
        basis = git("merge-base", haupt, kopf).strip()
        g = sorted(n for n in git("diff", "--no-renames", "--name-only", basis, kopf).splitlines() if n)
        links = [z.split("\t", 1)[1] for z in git("diff", "--no-renames", "--raw", basis, kopf).splitlines()
                 if z.startswith(":") and "\t" in z and z.split()[1] == "120000"]
        zeilen, pfad = [], None
        for z in git("diff", "--no-renames", "-U0", basis, kopf).splitlines():
            if z.startswith("+++ "):
                pfad = z[6:] if z.startswith("+++ b/") else None
            elif z.startswith("+") and pfad:
                zeilen.append((pfad, z[1:]))
    except (PruefFehler, subprocess.SubprocessError, OSError) as e:
        return dict(b, code="C/technik", grund=f"Zweig {zweig} ließ sich nicht lesen: {e}")
    b.update(kopf=kopf, geaendert=g, ausserhalb=[x for x in g if not abnahme.im_bereich(x, bereiche)] if bereiche else [],
             gesperrt=abnahme.gesperrt(g, typ, sperrmuster), autogeladen=autogeladen(g), geheim=geheimnisse(zeilen),
             aussen=nach_aussen(zeilen))
    if not g:
        return dict(b, code="C/leer", grund="keine Änderungen gegen main")
    if links:
        return dict(b, code="C/diff", grund="Symlinks im Zweig: " + ", ".join(links[:8]))
    if b["ausserhalb"] or b["gesperrt"] or b["autogeladen"] or b["geheim"]:
        return dict(b, code="C/diff", grund="Diff-Tor: " + "; ".join(
            x for x in (b["ausserhalb"] and f"außerhalb der Bereiche: {', '.join(b['ausserhalb'][:5])}",
                        b["gesperrt"] and f"gesperrt: {', '.join(x for x, _ in b['gesperrt'][:5])}",
                        b["autogeladen"] and f"automatisch geladen: {', '.join(b['autogeladen'][:5])}",
                        b["geheim"] and f"Geheimnis-Muster: {', '.join(f'{x} ({a})' for x, a in b['geheim'][:5])}") if x))
    if b["aussen"] and aussen:
        return dict(b, code="C/aussen", grund="nach außen: " + "; ".join(f"{x}: {w}" for x, w in b["aussen"][:8]))
    if b["aussen"]:                                   # A1858: merge_aussen_pruefung = aus – nur Hinweis, kein Befund
        return dict(b, grund="Diff-Tor ohne Befund; nach außen nur als Hinweis (Außen-Prüfung aus): "
                    + "; ".join(f"{x}: {w}" for x, w in b["aussen"][:8]))
    return dict(b, grund="Diff-Tor ohne Befund; Geheimnis- und Außen-Muster: keine Treffer (Muster-Prüfung, kein Beweis – §6a.5)")


def pruefen(p, quelle, basis, aid, pruefbefehl, bereiche, typ=None, frist=abnahme.FRIST_S, nachricht=None, regression=REGRESSION,
           aussen=True, sperrmuster=None, ohne_regression=None, werkzeuge=None, sprache="aus"):
    """Prüfung C für Paket `aid` im Platz `p`. Rückgabe: Befund mit "code" (None = alles grün) und allen Einzelheiten.
    sprache (A1962): auto | pyright | aus – Schritt 7 nach Abnahme und Kurzsuite (auch wenn die Abnahme rot ist)."""
    b = {"code": None, "kopf": None, "geaendert": [], "ausserhalb": [], "gesperrt": [], "autogeladen": [], "geheim": [], "aussen": [],
         "abnahme": None, "regression": None, "test_schreiben": None, "sprache": None, "grund": None}
    p = dict(p, autocrlf=autocrlf_klon(p["klon"]))               # A1911: einsammeln, wie der Klon ausgecheckt ist
    try:
        v = verweise(p["klon"])                                   # P268: vor jedem git add – nichts von außen einsammeln
    except OSError as e:
        return dict(b, code="C/technik", grund=f"Arbeitsbaum ließ sich nicht durchsehen: {e}")
    if v:
        return dict(b, code="C/diff", verweise=v, grund="Verweise im Arbeitsbaum (nicht eingesammelt): "
                    + "; ".join(f"{x} – {a}" for x, a in v[:8]))
    try:
        basis_holen(p, quelle, basis)
        kopf = einsammeln(p, basis, aid, nachricht or f"A{aid}: Stand des Arbeiters (Prüfung C)")
    except (PruefFehler, subprocess.SubprocessError, OSError) as e:
        return dict(b, code="C/technik", grund=f"Änderungen ließen sich nicht einsammeln: {e}")
    if not kopf:
        return dict(b, code="C/leer", grund="keine Änderungen")
    b["kopf"] = kopf
    g = geaendert(p, basis, kopf)
    zeilen = zusaetze(p, basis, kopf)
    b.update(geaendert=g, ausserhalb=[x for x in g if not abnahme.im_bereich(x, bereiche)], gesperrt=abnahme.gesperrt(g, typ, sperrmuster),
             autogeladen=autogeladen(g), geheim=geheimnisse(zeilen), aussen=nach_aussen(zeilen),
             keine_tests=abnahme.nicht_nur_tests(g) if typ == abnahme.TEST_ERGAENZEN else [])   # A1895: nur Testdateien
    if b["ausserhalb"] or b["gesperrt"] or b["autogeladen"] or b["geheim"] or b["keine_tests"]:
        return dict(b, code="C/diff", grund="Diff-Tor: " + "; ".join(
            x for x in (b["ausserhalb"] and f"außerhalb der Bereiche: {', '.join(b['ausserhalb'][:5])}",
                        b["keine_tests"] and f"test-ergaenzen ändert nur Tests – nicht: {', '.join(b['keine_tests'][:5])}",
                        b["gesperrt"] and f"gesperrt: {', '.join(x for x, _ in b['gesperrt'][:5])}",
                        b["autogeladen"] and f"automatisch geladen: {', '.join(b['autogeladen'][:5])}",
                        b["geheim"] and f"Geheimnis-Muster: {', '.join(f'{x} ({a})' for x, a in b['geheim'][:5])}") if x))
    if b["aussen"] and aussen:
        return dict(b, code="C/aussen", grund="nach außen: " + "; ".join(f"{x}: {w}" for x, w in b["aussen"][:8]))
    if b["aussen"]:                                   # A1858: merge_aussen_pruefung = aus – grün geht weiter, mit Hinweis
        b["grund"] = "nach außen nur als Hinweis (Außen-Prüfung aus): " + "; ".join(f"{x}: {w}" for x, w in b["aussen"][:8])
    try:
        q = _frisch(dict(p, autocrlf=autocrlf_projekt(quelle)), kopf)   # A1911: frischer Checkout mit den Zeilenenden des Projekts
    except (PruefFehler, subprocess.SubprocessError, OSError) as e:
        return dict(b, code="C/technik", grund=f"frischer Checkout: {e}")
    b["abnahme"] = _laufen(q, pruefbefehl, frist, werkzeuge)
    sprache_an_ = sprache_an(sprache, q["klon"])

    def mit_sprache(code, grund):                     # A1962: Schritt 7 läuft auch, wenn die Abnahme rot ist
        if code == "C/rot" and sprache_an_ and b["sprache"] is None:
            b["sprache"] = sprachpruefung(p, q, basis, werkzeuge=werkzeuge)
            if b["sprache"]["befund"] == "C/rot":
                grund += f"; Sprachprüfung: {b['sprache']['grund']}"
        return dict(b, code=code, grund=grund)
    if b["abnahme"]["befund"]:
        return mit_sprache(b["abnahme"]["befund"], f"Abnahme {'technisch nicht ausführbar' if b['abnahme']['befund'] == 'C/technik' else 'rot'}")
    if typ == abnahme.TEST_SCHREIBEN:
        testdateien = [x for x in g if x.lower().startswith("tests/")]
        from . import arbeiter
        t = (abnahme.test_gegen_basis(q, pruefbefehl, basis, testdateien, frist, umgebung=arbeiter.umgebung(q, werkzeuge=werkzeuge))
             if testdateien
             else {"ok": False, "grund": "keine Testdatei"})
        b["test_schreiben"] = dict(t, tests=_tests_gelaufen(b["abnahme"].get("ausgabe")))
        if not t.get("ok") or b["test_schreiben"]["tests"] < 1:
            return mit_sprache("C/rot", "test-schreiben: " + (t.get("grund") or "kein Test ausgeführt"))
    if typ == abnahme.TEST_ERGAENZEN:                 # A1895: grün reicht, aber nur mit wirklich ausgeführten Tests
        n, weg = _tests_gelaufen(b["abnahme"].get("ausgabe")), _tests_uebersprungen(b["abnahme"].get("ausgabe"))
        b["test_ergaenzen"] = {"tests": n, "uebersprungen": weg}
        if n - weg < 1:
            return mit_sprache("C/rot", "test-ergaenzen: kein Test ausgeführt" + (f" ({weg} übersprungen)" if weg else ""))
    if regression:
        b["regression"] = _laufen(q, regression, frist, werkzeuge)
        if b["regression"]["befund"]:
            return mit_sprache(b["regression"]["befund"], "Regressions-Kurzsuite " + ("rot" if b["regression"]["befund"] == "C/rot" else "nicht ausführbar"))
    elif ohne_regression:                             # A1920: klar gemeldet – im Befund, in der Entscheidung und in der Merge-Liste
        b["ohne_regression"] = ohne_regression
        b["grund"] = "; ".join(x for x in (b["grund"], ohne_regression) if x)
    if sprache_an_:                                   # A1962: Schritt 7 – neue Fehler des Sprach-Servers
        b["sprache"] = sprachpruefung(p, q, basis, werkzeuge=werkzeuge)
        if b["sprache"]["befund"]:
            return dict(b, code=b["sprache"]["befund"], grund="Sprachprüfung: " + (b["sprache"]["grund"] or ""))
    return b

# --- 7. Sprach-Server-Prüfung (A1962, TH167 Fassung 3 Pkt 7, Marcel W2463) – ohne KI-Aufruf ---------------------------------
# Im frischen Checkout des Pakets und in einem frischen Checkout des Start-Commits (gleiche Version, Konfiguration aus dem Repo)
# läuft derselbe Sprach-Server über das ganze Projekt. „Neu“ = Meldung mit Schweregrad error, verglichen nach Regel, Datei und
# Text, ohne Zeilennummer (mehrfach gleiche zählen einzeln). Neue Fehler → C/rot; Programm fehlt, stürzt ab, Zeitlimit → C/technik.
# Läuft auch, wenn die Abnahme rot ist (dann gehen beide Ausgaben in den neuen Lauf, E5). Projekt-Einstellung sprachpruefung:
# auto (Vorgabe: an, wenn das Repo eine pyrightconfig.json hat) | pyright | aus.
SPRACHE_FRIST_S = 10 * 60
SPRACHE_KONFIG = "pyrightconfig.json"


def sprache_an(modus, klon):
    """Soll für diesen Checkout geprüft werden? auto: nur mit pyrightconfig.json im Repo."""
    if modus == "pyright":
        return True
    return modus == "auto" and os.path.isfile(os.path.join(klon, SPRACHE_KONFIG))


def _pyright(q, frist, werkzeuge=None):
    """pyright --outputjson im Checkout q. Rückgabe {"fehler": [(regel, datei, text, zeile)], "version", "technik": Grund | None,
    "dauer_s"}. Die JSON-Ausgabe geht in eine Datei (die Befehlsausgabe ist gekürzt)."""
    import json
    import shutil
    from . import arbeiter
    u = arbeiter.umgebung(q, werkzeuge=werkzeuge)
    extra = [os.path.dirname(x) for x in (shutil.which("pyright"), shutil.which("node")) if x]   # Werkzeug der AMW, ohne Netz
    u["PATH"] = os.pathsep.join([u["PATH"], *extra])
    datei = os.path.join(q["tmp"], "pyright.json")
    os.makedirs(q["tmp"], exist_ok=True)
    r = abnahme.ausfuehren(f'pyright --outputjson > "{datei}"', q["klon"], u, frist)
    aus = {"fehler": [], "version": None, "technik": None, "dauer_s": r.get("dauer_s"), "rc": r.get("rc")}
    if r.get("fehler") or r["zeitlimit"] or r["rc"] not in (0, 1):
        aus["technik"] = (r.get("fehler") or (f"Zeitlimit {frist // 60} min" if r["zeitlimit"] else
                          f"pyright endete mit {r['rc']}" + (f": {r['ausgabe'].strip()[-300:]}" if (r.get("ausgabe") or "").strip() else "")))
        if NICHT_GEFUNDEN.search((r.get("ausgabe") or "")[:600]):
            aus["technik"] = "pyright fehlt auf diesem PC (npm install -g pyright, ohne Netz beim Prüfen)"
        return aus
    try:
        with open(datei, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError) as e:
        aus["technik"] = f"Ausgabe von pyright unlesbar: {e}"
        return aus
    aus["version"] = d.get("version")
    for m in d.get("generalDiagnostics") or []:
        if m.get("severity") != "error":
            continue
        try:
            rel = os.path.relpath(m.get("file") or "", q["klon"]).replace("\\", "/")
        except ValueError:
            rel = (m.get("file") or "").replace("\\", "/")
        zeile = ((m.get("range") or {}).get("start") or {}).get("line")
        aus["fehler"].append((m.get("rule") or "", rel, " ".join((m.get("message") or "").split()), (zeile + 1) if zeile is not None else None))
    return aus


def sprach_vergleich(kopf, basis):
    """Neue Fehler (Liste mit Zeile aus dem Paket-Stand): was im Paket öfter vorkommt als im Start-Commit, ohne Zeilennummer."""
    import collections
    rest = collections.Counter((r, d, t) for r, d, t, _ in basis)
    neu = []
    for r, d, t, z in kopf:
        if rest[(r, d, t)] > 0:
            rest[(r, d, t)] -= 1
        else:
            neu.append((r, d, t, z))
    return neu


def sprachpruefung(p, kopf_q, basis, frist=SPRACHE_FRIST_S, werkzeuge=None):
    """Schritt 7: {"befund": None | "C/rot" | "C/technik", "neu": [...], "version", "ausgabe" (für den neuen Lauf), "dauer_s"}."""
    k = _pyright(kopf_q, frist, werkzeuge)
    if k["technik"]:
        return {"befund": "C/technik", "neu": [], "version": k["version"], "ausgabe": f"Sprachprüfung (pyright): {k['technik']}",
                "grund": k["technik"], "dauer_s": k["dauer_s"]}
    try:
        bq = _frisch(p, basis)
    except (PruefFehler, subprocess.SubprocessError, OSError) as e:
        return {"befund": "C/technik", "neu": [], "version": k["version"], "ausgabe": f"Sprachprüfung: Start-Commit nicht auscheckbar: {e}",
                "grund": f"Start-Commit nicht auscheckbar: {e}", "dauer_s": k["dauer_s"]}
    b = _pyright(bq, frist, werkzeuge)
    if b["technik"]:
        return {"befund": "C/technik", "neu": [], "version": k["version"], "ausgabe": f"Sprachprüfung (pyright, Start-Commit): {b['technik']}",
                "grund": f"auf dem Start-Commit: {b['technik']}", "dauer_s": (k["dauer_s"] or 0) + (b["dauer_s"] or 0)}
    neu = sprach_vergleich(k["fehler"], b["fehler"])
    zeilen = [f"- {d}{':' + str(z) if z else ''} [{r or 'ohne Regel'}] {t}" for r, d, t, z in neu[:60]]
    ausgabe = (f"Sprachprüfung (pyright {k['version'] or '?'}): {len(neu)} neue Fehler gegenüber dem Start-Commit"
               + (" – beheben:\n" + "\n".join(zeilen) + ("\n…" if len(neu) > 60 else "") if neu else ""))
    return {"befund": "C/rot" if neu else None, "neu": [list(x) for x in neu], "version": k["version"], "ausgabe": ausgabe,
            "fehler_paket": len(k["fehler"]), "fehler_start": len(b["fehler"]),
            "grund": f"{len(neu)} neue Fehler (pyright)" if neu else None, "dauer_s": (k["dauer_s"] or 0) + (b["dauer_s"] or 0)}
