"""Abnahme durch die AMW für kopflose Arbeiter (M50 S3 / A1846) – Konzept D1258 v4 §5 (Liste gesperrter Pfade) und §6 Schritt 4;
Einwände D1259 Nr. 1, 28 und D1270 Nr. 14, 22, 25.

Ohne Lead prüft nur die Abnahme – darum führt die AMW sie selbst aus (nie die Meldung des Arbeiters glauben), im Platz, mit
seinen Daten und Ports, im Windows-Job-Objekt mit Zeitlimit (ein hängender Test wird samt Kindprozessen beendet). Vor dem Bau
muss sie rot sein (sonst prüft sie nichts), außer beim Pakettyp „test-schreiben“. Nach dem Bau gleicht das Diff-Tor ab: nur
Dateien in den geplanten Bereichen geändert, keine gesperrten Pfade.

Die Liste gesperrter Pfade gibt es genau einmal (dieses Modul ist ihr Besitzer) – für die Startregel 5 und für das Diff-Tor.
Testskripte und Testkonfiguration sind immer gesperrt; Testdateien sind gesperrt außer beim Pakettyp „test-schreiben“.
Nichts hier wird ohne eingerichtete Plätze aufgerufen (plaetze = 0: die AMW arbeitet wie bisher).
"""
import fnmatch
import os
import subprocess
import time

# (Muster, Art, Grund) – Muster relativ zum Repository, mit / getrennt; Art „fest“ = immer gesperrt, „test“ = außer test-schreiben
GESPERRT = (
    (".git/*", "fest", "Git-Verwaltung"),
    (".claude/*", "fest", "Einstellungen und Hooks von Claude Code"),
    (".githooks/*", "fest", "Git-Hooks"),
    ("CLAUDE.md", "fest", "Anweisungen an Agenten"),
    ("*/CLAUDE.md", "fest", "Anweisungen an Agenten"),
    ("amw/abnahme.py", "fest", "Abnahme und gesperrte Pfade"),
    ("amw/platz.py", "fest", "Arbeitsplätze"),
    ("amw/disponent*.py", "fest", "Disponent"),
    ("amw/arbeitspaket*.py", "fest", "Pakete und Zustände"),
    ("amw/auslieferung.py", "fest", "Auslieferung und Merge-Reihe"),
    ("amw/releasetakt.py", "fest", "Auslieferung"),
    ("amw/benutzer.py", "fest", "Rechte"),
    ("amw/bruecke.py", "fest", "Rechte (Dateiaustausch)"),
    ("amw/mcp_server.py", "fest", "Rechte (Connector)"),
    ("amw/mcp_schluessel.py", "fest", "Rechte (Connector)"),
    ("amw/hook.py", "fest", "Hooks"),
    ("amw/schwer.py", "fest", "Hooks (schwere Befehle)"),
    ("*.ps1", "fest", "Skripte"),
    ("*.bat", "fest", "Skripte"),
    ("*.cmd", "fest", "Skripte"),
    ("tests/abschotten.py", "fest", "Testkonfiguration"),
    ("tests/rundgang.py", "fest", "Testskript"),
    ("tests/oidc_attrappe.py", "fest", "Testskript"),
    ("tests/__init__.py", "fest", "Testkonfiguration"),
    ("tests/conftest.py", "fest", "Testkonfiguration"),
    ("setup.cfg", "fest", "Testkonfiguration"),
    ("pyproject.toml", "fest", "Testkonfiguration"),
    ("pytest.ini", "fest", "Testkonfiguration"),
    ("tox.ini", "fest", "Testkonfiguration"),
    ("tests/*", "test", "Testdatei"),
)
TEST_SCHREIBEN = "test-schreiben"
FRIST_S = 1800


def _norm(pfad):
    n = str(pfad).replace("\\", "/")
    while n.startswith("./"):
        n = n[2:]
    return n


def gesperrt(pfade, typ=None):
    """[(pfad, grund)] der gesperrten unter `pfade` – Testdateien nicht beim Pakettyp test-schreiben."""
    aus = []
    for p in pfade:
        n = _norm(p)
        for muster, art, grund in GESPERRT:
            if fnmatch.fnmatchcase(n, muster) and not (art == "test" and typ == TEST_SCHREIBEN):
                aus.append((n, grund))
                break
    return aus


def im_bereich(pfad, bereiche):
    """Liegt `pfad` in einem der Bereiche (Ordner „amw/“, Datei „amw/x.py“ oder Muster „web/hilfe/*.json“)?"""
    n = _norm(pfad)
    for b in bereiche or []:
        b = _norm(b)
        if b.endswith("/") and n.startswith(b) or n == b or fnmatch.fnmatchcase(n, b):
            return True
    return False


def startregel(bereiche, typ=None):
    """Regel 5 vor dem Start: Bereiche, die gesperrte Pfade enthalten oder sind → [(bereich, grund)]."""
    aus = []
    for b in bereiche or []:
        n = _norm(b)
        probe = n + "x" if n.endswith("/") else n                  # Ordner: gesperrt, wenn darin Gesperrtes liegen könnte
        treffer = gesperrt([probe], typ) or [(n, g) for m, art, g in GESPERRT
                                              if (n.endswith("/") and m.startswith(n)) and not (art == "test" and typ == TEST_SCHREIBEN)]
        if treffer:
            aus.append((n, treffer[0][1]))
    return aus


def _git(klon, *args):
    r = subprocess.run(["git", "-C", klon, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       stdin=subprocess.DEVNULL, timeout=300, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {(r.stdout + r.stderr).strip()[-300:]}")
    return r.stdout


def geaendert(klon, basis):
    """Alle Pfade, die der Arbeiter seit `basis` angefasst hat – Commits, Änderungen im Arbeitsbaum, neue Dateien."""
    pfade = set(_git(klon, "diff", "--name-only", f"{basis}..HEAD").split())
    pfade |= set(_git(klon, "diff", "--name-only", "HEAD").split())
    pfade |= set(_git(klon, "ls-files", "--others", "--exclude-standard").split())
    zwischen = lambda n: "/__pycache__/" in "/" + n or n.endswith((".pyc", ".pyo"))   # erzeugt die Abnahme selbst
    return sorted(n for n in (_norm(p) for p in pfade if p) if not zwischen(n))


def diff_tor(klon, basis, bereiche, typ=None):
    """{"ok", "ausserhalb": [pfad], "gesperrt": [(pfad, grund)], "geaendert": [pfad]} – nur geplante Bereiche, nichts Gesperrtes."""
    g = geaendert(klon, basis)
    ausserhalb = [p for p in g if not im_bereich(p, bereiche)]
    gesp = gesperrt(g, typ)
    return {"ok": bool(g) and not ausserhalb and not gesp, "leer": not g, "ausserhalb": ausserhalb, "gesperrt": gesp, "geaendert": g}


# --- Ausführen im Job-Objekt (Windows): ein Zeitlimit beendet den ganzen Prozessbaum ---------------------------------------

def _job_neu():
    """Ein Job-Objekt, das beim Schließen alle Prozesse beendet – oder None (kein Windows)."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.restype = wintypes.HANDLE
    job = k.CreateJobObjectW(None, None)
    if not job:
        return None

    class Grenzen(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class IoZaehler(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("a", "b", "c", "d", "e", "f")]

    class Erweitert(ctypes.Structure):
        _fields_ = [("Basic", Grenzen), ("Io", IoZaehler), ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    info = Erweitert()
    info.Basic.LimitFlags = 0x2000                              # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    k.SetInformationJobObject(wintypes.HANDLE(job), 9, ctypes.byref(info), ctypes.sizeof(info))   # ExtendedLimitInformation
    return job


def ausfuehren(befehl, ordner, umgebung, frist=FRIST_S):
    """Befehl (Shell-Zeile) im Ordner mit Umgebung ausführen; nach `frist` Sekunden wird der ganze Prozessbaum beendet.
    Rückgabe {"rc", "ausgabe", "zeitlimit": bool, "dauer_s"}. Der Prozess startet angehalten und kommt erst ins Job-Objekt,
    dann läuft er – so entkommt kein Kindprozess."""
    t0 = time.monotonic()
    job = _job_neu()
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | (0x4 if job else 0)       # CREATE_SUSPENDED
    p = subprocess.Popen(befehl, cwd=ordner, env=umgebung, shell=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, creationflags=flags)
    if job:
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.AssignProcessToJobObject(wintypes.HANDLE(job), wintypes.HANDLE(int(p._handle)))
        ctypes.WinDLL("ntdll").NtResumeProcess(wintypes.HANDLE(int(p._handle)))
    zeitlimit = False
    try:
        aus, _ = p.communicate(timeout=frist)
    except subprocess.TimeoutExpired:
        zeitlimit = True
        if job:
            import ctypes
            from ctypes import wintypes
            ctypes.WinDLL("kernel32").TerminateJobObject(wintypes.HANDLE(job), 1)
        else:
            p.kill()
        aus, _ = p.communicate()
    finally:
        if job:
            import ctypes
            from ctypes import wintypes
            ctypes.WinDLL("kernel32").CloseHandle(wintypes.HANDLE(job))
    return {"rc": p.returncode, "ausgabe": (aus or b"").decode("utf-8", "replace")[-4000:], "zeitlimit": zeitlimit,
            "dauer_s": round(time.monotonic() - t0, 1)}


def abnahme(p, befehl, frist=FRIST_S):
    """Den Abnahme-Befehl im Platz `p` (amw.platz.pfade) mit seinen Daten und Ports ausführen. grün = rc 0 ohne Zeitlimit."""
    from . import platz
    r = ausfuehren(befehl, p["klon"], platz.umgebung(p), frist)
    r["gruen"] = r["rc"] == 0 and not r["zeitlimit"]
    return r


def rot_vor_bau(p, befehl, typ=None, frist=FRIST_S):
    """Regel 6: vor dem Bau muss die Abnahme rot sein – sonst prüft sie nichts. Beim Pakettyp test-schreiben entfällt das
    (dort wird geprüft, dass der neue Test gegen den alten Stand rot ist: test_gegen_basis). Rückgabe {"ok", "grund", …}."""
    if typ == TEST_SCHREIBEN:
        return {"ok": True, "grund": "test-schreiben: Prüfung nach dem Bau"}
    r = abnahme(p, befehl, frist)
    if r["zeitlimit"]:
        return {**r, "ok": False, "grund": "Abnahme hängt schon vor dem Bau (Zeitlimit)"}
    return {**r, "ok": not r["gruen"], "grund": None if not r["gruen"] else "Abnahme ist schon vor dem Bau grün – sie prüft nichts"}


def test_gegen_basis(p, befehl, basis, testdateien, frist=FRIST_S):
    """Pakettyp test-schreiben: die neuen Tests müssen gegen den alten Stand (Code von `basis`) rot sein. Dazu kommt der Code
    von `basis` vorübergehend zurück, die Testdateien bleiben; danach wird der Arbeitsbaum wiederhergestellt."""
    from . import platz
    if _git(p["klon"], "status", "--porcelain", "--untracked-files=no"):   # unverfolgte (z. B. __pycache__) bleiben ohnehin unberührt
        return {"ok": False, "grund": "nicht alles committet – der alte Stand lässt sich so nicht sauber herstellen", "rc": None}
    kopf = _git(p["klon"], "rev-parse", "HEAD").strip()
    in_basis = set(_git(p["klon"], "ls-tree", "-r", "--name-only", basis).split())
    andere = [x for x in geaendert(p["klon"], basis) if x not in set(_norm(t) for t in testdateien) and x in in_basis]
    try:
        if andere:
            _git(p["klon"], "checkout", basis, "--", *andere)
        r = ausfuehren(befehl, p["klon"], platz.umgebung(p), frist)
    finally:
        _git(p["klon"], "checkout", kopf, "--", ".")          # alles war committet: der Stand des Arbeiters ist unverändert
    gruen = r["rc"] == 0 and not r["zeitlimit"]
    return {**r, "ok": not gruen, "grund": None if not gruen else "der neue Test ist schon gegen den alten Stand grün – er prüft nichts"}
