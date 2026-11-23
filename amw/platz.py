"""Arbeitsplätze für kopflose Arbeiter (`claude -p`), M50 S1b / A1855 – Konzept D1258 v4 §6 Schritt 1, Einwände D1270 Nr. 2, 3, 24.

Ein Platz ist ein **eigener Klon** des Projekt-Repositorys (eigenes .git, ohne Hardlinks – nichts wird mit dem Haupt-Checkout
geteilt), dazu ein **eigener Datenordner** daneben: Datenbank (AMW_DB), LOCALAPPDATA (Zugänge, Einstellungen, Port), TEMP,
Claude-Ablagen. Was im Platz läuft, sieht nur diese Umgebung (`umgebung`) – nie die Live-Datenbank und nie den Port des
Dienstes. Wo die Plätze liegen, steht nur in den Einstellungen des Projekts (platz_wurzel, plaetze); beides setzt nur der
Mensch (das ist seine einmalige Freigabe). plaetze = 0 (Vorgabe): es gibt keine Plätze, die AMW verhält sich wie bisher.

`vorbereiten` legt den Klon an oder holt ihn auf den Stand von main (Zweig ab origin/main, sauber); `zuruecksetzen` macht
ihn wieder sauber – auch nach einem Abbruch (liegengebliebene index.lock, halbe Änderungen, fremde Dateien).

Gelöscht wird nichts (Marcel B2894, A1861): Reste wandern erst ins Archiv (<wurzel>/_archiv/platzN-<Zeit>[-A<nr>]: Patch
der ungesicherten Änderungen, Bundle der Commits, fremde und ignorierte Dateien, der Datenordner – verschoben, nicht kopiert),
ist das Paket fertig, schiebt `aufraeumen` das Archiv nach <wurzel>/_loeschen. Endgültig löscht nur der Mensch.
"""
import json
import os
import shutil
import subprocess

from . import kern

MARKER = ".amw-platz"                # Markerdatei: nur wo sie liegt, löscht die AMW (TL P239)
PORT_BASIS = 8800                    # Platz n bekommt PORT_BASIS + n (der Dienst bleibt auf seinem Port)
MAX_PLAETZE = 8


class PlatzFehler(kern.AmwFehler):
    pass


def einstellung(con, pid):
    """(wurzel, anzahl) aus den Projekt-Einstellungen; ohne Wurzel oder mit 0 Plätzen: (None, 0)."""
    e = json.loads(con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()[0] or "{}")
    wurzel, n = (e.get("platz_wurzel") or "").strip(), int(e.get("plaetze") or 0)
    return (wurzel, n) if wurzel and n > 0 else (None, 0)


def pfade(wurzel, nr):
    """Ordner und Werte von Platz `nr` (1 …)."""
    if not 1 <= nr <= MAX_PLAETZE:
        raise PlatzFehler(f"Platz {nr}: 1 bis {MAX_PLAETZE}")
    klon = os.path.join(wurzel, f"platz{nr}")
    daten = os.path.join(wurzel, f"platz{nr}-daten")
    return {"nr": nr, "klon": klon, "daten": daten, "db": os.path.join(daten, "amw.db"), "lad": os.path.join(daten, "lad"),
            "tmp": os.path.join(daten, "tmp"), "claude": os.path.join(daten, "claude"), "port": PORT_BASIS + nr}


def plaetze(con, pid):
    wurzel, n = einstellung(con, pid)
    lfs = lfs_modus(con, pid)
    return [dict(pfade(wurzel, i), lfs=lfs) for i in range(1, n + 1)] if wurzel else []


def lfs_modus(con, pid):
    """A1921: Projekt-Einstellung platz_lfs – „aus“ (Vorgabe: klonen wie bisher) oder „teilen“: LFS-Dateien kommen beim Klonen
    und bei jedem Auschecken nur als kleine Verweise in den Platz (GIT_LFS_SKIP_SMUDGE, git lfs install --local --skip-smudge);
    braucht ein Arbeiter eine, holt `git lfs pull --include <pfad>` sie aus dem Projekt-Repo (origin) – dort wird nur gelesen."""
    e = json.loads(con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()[0] or "{}")
    return "teilen" if (e.get("platz_lfs") or "").strip().lower() == "teilen" else "aus"


def _lfs_da():
    return bool(shutil.which("git-lfs"))


def _lfs_einstellen(p):
    """Im Klon: bei „teilen“ das Auschecken von LFS-Dateien abschalten, bei „aus“ wieder einschalten (nur wenn es abgeschaltet
    war). Ohne git-lfs gibt es nichts einzustellen – LFS-Dateien sind dann ohnehin nur Verweise."""
    if not _lfs_da():
        return
    r = subprocess.run(["git", "-C", p["klon"], "config", "--local", "--get", "filter.lfs.smudge"], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    uebersprungen = "--skip" in (r.stdout or "")
    if p.get("lfs") == "teilen" and not uebersprungen:
        _git(p["klon"], "lfs", "install", "--local", "--skip-smudge")
    elif p.get("lfs") != "teilen" and uebersprungen:
        _git(p["klon"], "lfs", "install", "--local", "--force")


def umgebung(p, basis=None):
    """Umgebung für alles, was im Platz läuft (Arbeiter, Abnahme-Befehl): eigene Daten, eigener Port, keine Kennung."""
    u = dict(os.environ if basis is None else basis)
    for k in ("AMW_AGENT", "AMW_PROJEKT", "AMW_TEST_LOKAL", "CLAUDE_CODE_MESSAGING_SOCKET"):
        u.pop(k, None)
    u.update(AMW_DB=p["db"], LOCALAPPDATA=p["lad"], TEMP=p["tmp"], TMP=p["tmp"], AMW_CLAUDE_BASIS=p["claude"], AMW_PLATZ=str(p["nr"]))
    return u


def _git(ordner, *args, frist=600):
    r = subprocess.run(["git", "-C", ordner, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       stdin=subprocess.DEVNULL, timeout=frist, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        raise PlatzFehler(f"git {' '.join(args)} im Platz: {(r.stdout + r.stderr).strip()[-300:]}")
    return r.stdout.strip()


def _marker(ordner):
    return os.path.join(ordner, MARKER)


def _daten_anlegen(p):
    os.makedirs(p["daten"], exist_ok=True)
    open(_marker(p["daten"]), "w").close()
    for k in ("lad", "tmp", "claude"):
        os.makedirs(p[k], exist_ok=True)
    os.makedirs(os.path.join(p["lad"], "amw"), exist_ok=True)
    with open(os.path.join(p["lad"], "amw", "einstellungen.json"), "w", encoding="utf-8") as f:   # eigener Port, nichts sonst
        json.dump({"port": p["port"]}, f)


def vorbereiten(p, quelle, zweig, aufgabe=None):
    """Platz auf den Stand von main der Quelle bringen: Klon anlegen (falls nötig), holen, Zweig `zweig` ab origin/main,
    sauber; Datenordner frisch. Rückgabe: {"klon", "zweig", "basis"} (basis = SHA von origin/main)."""
    quelle = os.path.abspath(quelle)
    if os.path.normcase(os.path.abspath(p["klon"])).startswith(os.path.normcase(quelle) + os.sep):
        raise PlatzFehler("Der Platz darf nicht im Projektordner liegen")
    from . import arbeiter
    arbeiter.stempel(p, "vorbereitet")                   # A1987: neues Paket – eine frühere Notbremse gilt nicht mehr
    if not os.path.isdir(os.path.join(p["klon"], ".git")):
        if os.path.exists(p["klon"]) and os.listdir(p["klon"]):
            raise PlatzFehler(f"{p['klon']} ist kein Klon und nicht leer – die AMW legt dort nichts an")
        os.makedirs(os.path.dirname(p["klon"]) or ".", exist_ok=True)
        from . import pruefung_c                                         # A1911: Zeilenenden wie im Projekt, nicht wie das System
        u = dict(os.environ, GIT_LFS_SKIP_SMUDGE="1") if p.get("lfs") == "teilen" else None   # A1921: LFS nur als Verweise
        r = subprocess.run(["git", "clone", "-q", "--no-hardlinks", "-c", f"core.autocrlf={pruefung_c.autocrlf_projekt(quelle)}",
                            quelle, p["klon"]], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=1800, env=u,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0:
            raise PlatzFehler(f"git clone: {(r.stdout + r.stderr).strip()[-300:]}")
        open(_marker(os.path.join(p["klon"], ".git")), "w").close()   # in .git: nicht im Arbeitsbaum, nie committet
        if os.path.exists(p["daten"]) and os.listdir(p["daten"]) and not os.path.exists(_marker(p["daten"])):
            raise PlatzFehler(f"{p['daten']} ist nicht leer und kein Datenordner eines Platzes – die AMW fasst ihn nicht an")
        _daten_anlegen(p)
    _lfs_einstellen(p)                                                   # A1921: vor dem Auschecken
    _git(p["klon"], "remote", "set-url", "origin", quelle)
    zuruecksetzen(p, holen=True, projektordner=quelle, aufgabe=aufgabe)
    _git(p["klon"], "checkout", "-q", "-B", zweig, "origin/main")
    basis = _git(p["klon"], "rev-parse", "origin/main")
    if not sauber(p):
        raise PlatzFehler("Platz nach dem Vorbereiten nicht sauber")
    return {"klon": p["klon"], "zweig": zweig, "basis": basis}


def _wurzel(p):
    return os.path.dirname(os.path.abspath(p["klon"]))


class _Archiv:
    """Archiv-Ordner eines Zurücksetzens – erst angelegt, wenn wirklich etwas zu sichern ist (kein leerer Ordner je Lauf)."""

    def __init__(self, p, aufgabe):
        import datetime
        name = f"platz{p['nr']}-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}" + (f"-A{aufgabe}" if aufgabe else "")
        self.pfad, self.inhalt = os.path.join(_wurzel(p), "_archiv", name), []

    def ordner(self):
        os.makedirs(self.pfad, exist_ok=True)
        return self.pfad

    def schreiben(self, name, daten):
        with open(os.path.join(self.ordner(), name), "wb") as f:
            f.write(daten)
        self.inhalt.append(name)

    def verschieben(self, quelle, ziel_rel):
        ziel = os.path.join(self.ordner(), ziel_rel)
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        shutil.move(quelle, ziel)
        self.inhalt.append(ziel_rel.replace(os.sep, "/"))


def _daten_frisch(p):
    """Nur die Grundeinrichtung (Marker, Port-Einstellung, leere Ordner)? Dann gibt es nichts zu sichern."""
    grund = {os.path.normcase(_marker(p["daten"])), os.path.normcase(os.path.join(p["lad"], "amw", "einstellungen.json"))}
    return all(os.path.normcase(os.path.join(w, f)) in grund for w, _, fs in os.walk(p["daten"]) for f in fs)


def _roh(ordner, *args):
    r = subprocess.run(["git", "-C", ordner, *args], capture_output=True, stdin=subprocess.DEVNULL, timeout=600,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode, r.stdout


def zuruecksetzen(p, holen=False, projektordner=None, aufgabe=None):
    """Platz sauber machen – auch nach einem Abbruch – OHNE zu löschen (B2894): Reste kommen ins Archiv (Sperrdatei,
    Patch der ungesicherten Änderungen, Bundle der Commits seit origin/main, fremde und ignorierte Dateien, Datenordner –
    verschoben), erst danach geht der Klon auf origin/main (losgelöst) und der Datenordner wird neu angelegt (Port bleibt).
    Nur mit Markerdatei und nie im Projektordner. Rückgabe {"sauber", "archiv" (Pfad oder None), "inhalt"}."""
    if not os.path.isdir(os.path.join(p["klon"], ".git")):
        raise PlatzFehler(f"Platz {p['nr']} ist noch nicht angelegt (amw platz vorbereiten)")
    if not os.path.exists(_marker(os.path.join(p["klon"], ".git"))):
        raise PlatzFehler(f"{p['klon']} trägt keine Markierung als Platz – die AMW setzt ihn nicht zurück")
    if projektordner and os.path.normcase(os.path.abspath(p["klon"])).startswith(os.path.normcase(os.path.abspath(projektordner)) + os.sep):
        raise PlatzFehler("Der Platz liegt im Projektordner – die AMW setzt ihn nicht zurück")
    if os.path.isdir(p["daten"]) and not os.path.exists(_marker(p["daten"])):
        raise PlatzFehler(f"{p['daten']} trägt keine Markierung als Datenordner eines Platzes – nichts angefasst")
    a = _Archiv(p, aufgabe)
    sperre = os.path.join(p["klon"], ".git", "index.lock")
    if os.path.exists(sperre):
        a.verschieben(sperre, "index.lock")
    # P244 (Pflicht): schlägt das Sichern fehl, bricht das Zurücksetzen ab – kein checkout -f, sonst gingen Änderungen verloren
    rc, patch = _roh(p["klon"], "diff", "HEAD", "--binary")              # 1. ungesicherte Änderungen (auch vorgemerkte)
    if rc != 0:
        raise PlatzFehler(f"Platz {p['nr']}: ungesicherte Änderungen ließen sich nicht sichern (git diff) – nichts zurückgesetzt")
    if patch.strip():
        a.schreiben("ungesichert.patch", patch)
    rc, zahl = _roh(p["klon"], "rev-list", "--count", "origin/main..HEAD")   # 2. Commits seit main als Bundle
    if rc != 0:
        raise PlatzFehler(f"Platz {p['nr']}: Commits ließen sich nicht zählen – nichts zurückgesetzt")
    if int(zahl.strip() or 0):
        try:
            _git(p["klon"], "bundle", "create", os.path.join(a.ordner(), "commits.bundle"), "origin/main..HEAD")
        except PlatzFehler as e:
            raise PlatzFehler(f"Platz {p['nr']}: Commits ließen sich nicht sichern ({e}) – nichts zurückgesetzt") from None
        a.inhalt.append("commits.bundle")
    rc, fremd = _roh(p["klon"], "ls-files", "--others", "-z")              # 3. fremde und ignorierte Dateien: verschieben
    if rc != 0:
        raise PlatzFehler(f"Platz {p['nr']}: fremde Dateien ließen sich nicht auflisten – nichts zurückgesetzt")
    for rel in [x.decode("utf-8", "replace") for x in fremd.split(b"\0") if x]:
        quelle = os.path.join(p["klon"], rel)
        if os.path.isfile(quelle):
            a.verschieben(quelle, os.path.join("dateien", rel))
    for x in (("rebase", "--abort"), ("merge", "--abort"), ("cherry-pick", "--abort")):
        try:
            _git(p["klon"], *x)
        except PlatzFehler:
            pass
    if holen:
        _git(p["klon"], "fetch", "-q", "origin", "--prune")
    _git(p["klon"], "checkout", "-q", "-f", "--detach", "origin/main")   # alles Geänderte liegt jetzt im Archiv
    _git(p["klon"], "reset", "-q", "--hard", "origin/main")
    if projektordner:
        zeilenenden_angleichen(p["klon"], projektordner)
    if os.path.isdir(p["daten"]) and not _daten_frisch(p):             # 4. Datenordner: verschieben, neu anlegen
        a.verschieben(p["daten"], "daten")
    _daten_anlegen(p)
    if a.inhalt:
        import json as _j
        a.schreiben("platz.json", _j.dumps({"platz": p["nr"], "aufgabe": aufgabe, "inhalt": list(a.inhalt)}, ensure_ascii=False).encode())
    return {"sauber": sauber(p), "archiv": a.pfad if a.inhalt else None, "inhalt": a.inhalt}


def zeilenenden_angleichen(klon, projektordner):
    """A1911: Der Klon checkt mit dem core.autocrlf des Projekts aus (Wert in seiner eigenen Konfiguration, damit auch der
    Arbeiter ihn sieht – dessen git läuft ohne System-Konfiguration). Vor A1911 angelegte Klone hatten den Systemwert (true →
    CRLF, das Projekt LF): Weicht der Wert ab, wird er gesetzt und jede versionierte Datei neu geschrieben (checkout-index;
    `checkout -f` ließe sie liegen, weil ihr Index-Eintrag passt), danach ist der Index frisch. Nur nach dem Zurücksetzen –
    dann liegt nichts Ungesichertes mehr im Klon. Rückgabe: True, wenn neu geschrieben wurde."""
    from . import pruefung_c
    wert = pruefung_c.autocrlf_projekt(projektordner)
    rc, jetzt = _roh(klon, "config", "--local", "--get", "core.autocrlf")
    if rc == 0 and jetzt.decode("utf-8", "replace").strip().lower() == wert:
        return False
    _git(klon, "config", "--local", "core.autocrlf", wert)
    _git(klon, "read-tree", "--empty")                                # Index leer → reset schreibt jede versionierte Datei
    _git(klon, "reset", "-q", "--hard", "HEAD")                       # neu (checkout-index -f übersprang Dateien mit passendem Stat)
    return True


def aufraeumen(con, pid, wurzel):
    """Archive fertiger Pakete (Aufgabe fertig oder verworfen) von _archiv nach _loeschen verschieben – nie löschen;
    _loeschen leert der Mensch. Rückgabe: Liste der verschobenen Ordnernamen."""
    import re
    quelle, ziel = os.path.join(wurzel, "_archiv"), os.path.join(wurzel, "_loeschen")
    aus = []
    for name in sorted(os.listdir(quelle)) if os.path.isdir(quelle) else []:
        m = re.search(r"-A(\d+)$", name)
        if not m:
            continue
        r = con.execute("SELECT status FROM aufgabe WHERE id = ? AND projekt_id = ?", (int(m.group(1)), pid)).fetchone()
        if r and r["status"] in ("fertig", "verworfen"):
            os.makedirs(ziel, exist_ok=True)
            shutil.move(os.path.join(quelle, name), os.path.join(ziel, name))
            aus.append(name)
    return aus


def groesse(ordner):
    """Bytes in einem Ordner (0, wenn es ihn nicht gibt)."""
    s = 0
    for w, _, fs in os.walk(ordner):
        for f in fs:
            try:
                s += os.path.getsize(os.path.join(w, f))
            except OSError:
                pass
    return s


def sauber(p):
    """Keine Änderungen, keine fremden Dateien, kein Rebase/Merge offen."""
    if _git(p["klon"], "status", "--porcelain", "--ignored"):
        return False
    g = os.path.join(p["klon"], ".git")
    return not any(os.path.exists(os.path.join(g, x)) for x in ("rebase-merge", "rebase-apply", "MERGE_HEAD", "index.lock"))
