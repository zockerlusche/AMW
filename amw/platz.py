"""Arbeitsplätze für kopflose Arbeiter (`claude -p`), M50 S1b / A1855 – Konzept D1258 v4 §6 Schritt 1, Einwände D1270 Nr. 2, 3, 24.

Ein Platz ist ein **eigener Klon** des Projekt-Repositorys (eigenes .git, ohne Hardlinks – nichts wird mit dem Haupt-Checkout
geteilt), dazu ein **eigener Datenordner** daneben: Datenbank (AMW_DB), LOCALAPPDATA (Zugänge, Einstellungen, Port), TEMP,
Claude-Ablagen. Was im Platz läuft, sieht nur diese Umgebung (`umgebung`) – nie die Live-Datenbank und nie den Port des
Dienstes. Wo die Plätze liegen, steht nur in den Einstellungen des Projekts (platz_wurzel, plaetze); beides setzt nur der
Mensch (das ist seine einmalige Freigabe). plaetze = 0 (Vorgabe): es gibt keine Plätze, die AMW verhält sich wie bisher.

`vorbereiten` legt den Klon an oder holt ihn auf den Stand von main (Zweig ab origin/main, sauber); `zuruecksetzen` macht
ihn wieder sauber – auch nach einem Abbruch (liegengebliebene index.lock, halbe Änderungen, fremde Dateien). Gelöscht wird
dabei nur innerhalb des Platzes (Klon und Datenordner), den der Mensch dafür freigegeben hat.
"""
import json
import os
import shutil
import subprocess

from . import kern

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
    return [pfade(wurzel, i) for i in range(1, n + 1)] if wurzel else []


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


def _daten_anlegen(p):
    for k in ("lad", "tmp", "claude"):
        os.makedirs(p[k], exist_ok=True)
    os.makedirs(os.path.join(p["lad"], "amw"), exist_ok=True)
    with open(os.path.join(p["lad"], "amw", "einstellungen.json"), "w", encoding="utf-8") as f:   # eigener Port, nichts sonst
        json.dump({"port": p["port"]}, f)


def vorbereiten(p, quelle, zweig):
    """Platz auf den Stand von main der Quelle bringen: Klon anlegen (falls nötig), holen, Zweig `zweig` ab origin/main,
    sauber; Datenordner frisch. Rückgabe: {"klon", "zweig", "basis"} (basis = SHA von origin/main)."""
    quelle = os.path.abspath(quelle)
    if os.path.normcase(os.path.abspath(p["klon"])).startswith(os.path.normcase(quelle) + os.sep):
        raise PlatzFehler("Der Platz darf nicht im Projektordner liegen")
    if not os.path.isdir(os.path.join(p["klon"], ".git")):
        if os.path.exists(p["klon"]) and os.listdir(p["klon"]):
            raise PlatzFehler(f"{p['klon']} ist kein Klon und nicht leer – die AMW legt dort nichts an")
        os.makedirs(os.path.dirname(p["klon"]) or ".", exist_ok=True)
        r = subprocess.run(["git", "clone", "-q", "--no-hardlinks", quelle, p["klon"]], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=1800,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0:
            raise PlatzFehler(f"git clone: {(r.stdout + r.stderr).strip()[-300:]}")
    _git(p["klon"], "remote", "set-url", "origin", quelle)
    zuruecksetzen(p, holen=True)
    _git(p["klon"], "checkout", "-q", "-B", zweig, "origin/main")
    basis = _git(p["klon"], "rev-parse", "origin/main")
    if not sauber(p):
        raise PlatzFehler("Platz nach dem Vorbereiten nicht sauber")
    return {"klon": p["klon"], "zweig": zweig, "basis": basis}


def zuruecksetzen(p, holen=False):
    """Platz sauber machen – auch nach einem Abbruch: Sperrdatei weg, laufende Rebase/Merge abbrechen, Änderungen und
    fremde Dateien verwerfen, auf origin/main (losgelöst); Datenordner leeren und neu anlegen (Port bleibt)."""
    if not os.path.isdir(os.path.join(p["klon"], ".git")):
        raise PlatzFehler(f"Platz {p['nr']} ist noch nicht angelegt (amw platz vorbereiten)")
    sperre = os.path.join(p["klon"], ".git", "index.lock")
    if os.path.exists(sperre):
        os.remove(sperre)
    for x in (("rebase", "--abort"), ("merge", "--abort"), ("cherry-pick", "--abort")):
        try:
            _git(p["klon"], *x)
        except PlatzFehler:
            pass
    if holen:
        _git(p["klon"], "fetch", "-q", "origin", "--prune")
    _git(p["klon"], "reset", "-q", "--hard")
    _git(p["klon"], "clean", "-q", "-ffdx")
    _git(p["klon"], "checkout", "-q", "--detach", "origin/main")
    _git(p["klon"], "reset", "-q", "--hard", "origin/main")
    if os.path.isdir(p["daten"]):
        shutil.rmtree(p["daten"])
    _daten_anlegen(p)
    return sauber(p)


def sauber(p):
    """Keine Änderungen, keine fremden Dateien, kein Rebase/Merge offen."""
    if _git(p["klon"], "status", "--porcelain", "--ignored"):
        return False
    g = os.path.join(p["klon"], ".git")
    return not any(os.path.exists(os.path.join(g, x)) for x in ("rebase-merge", "rebase-apply", "MERGE_HEAD", "index.lock"))
