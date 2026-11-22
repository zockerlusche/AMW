"""Abnahme durch die AMW für kopflose Arbeiter (M50 S3 / A1846) – Konzept D1258 v4 §5 (Liste gesperrter Pfade) und §6 Schritt 4;
Einwände D1259 Nr. 1, 28 und D1270 Nr. 14, 22, 25.

Ohne Lead prüft nur die Abnahme – darum führt die AMW sie selbst aus (nie die Meldung des Arbeiters glauben), im Platz, mit
seinen Daten und Ports, im Windows-Job-Objekt mit Zeitlimit (ein hängender Test wird samt Kindprozessen beendet). Vor dem Bau
muss sie rot sein (sonst prüft sie nichts), außer bei den Pakettypen „test-schreiben“ und „test-ergaenzen“. Nach dem Bau gleicht das Diff-Tor ab: nur
Dateien in den geplanten Bereichen geändert, keine gesperrten Pfade.

Die Liste gesperrter Pfade gibt es genau einmal (dieses Modul ist ihr Besitzer) – für die Startregel 5 und für das Diff-Tor.
Testskripte und Testkonfiguration sind immer gesperrt; Testdateien sind gesperrt außer bei „test-schreiben“ und „test-ergaenzen“ (dieser darf NUR Testdateien ändern).
Nichts hier wird ohne eingerichtete Plätze aufgerufen (plaetze = 0: die AMW arbeitet wie bisher).
"""
import fnmatch
import os
import subprocess
import time

# (Muster, Art, Grund) – Muster relativ zum Repository, mit / getrennt; Art „fest“ = immer gesperrt, „test“ = außer test-schreiben/test-ergaenzen
GESPERRT = (
    (".git/*", "fest", "Git-Verwaltung"),
    ("*/.git/*", "fest", "Git-Verwaltung"),
    (".claude/*", "fest", "Einstellungen und Hooks von Claude Code"),
    ("*/.claude/*", "fest", "Einstellungen und Hooks von Claude Code"),
    (".githooks/*", "fest", "Git-Hooks"),
    ("*/.githooks/*", "fest", "Git-Hooks"),
    (".gitignore", "fest", "Git-Einstellung (Ausnahmen aufheben)"),
    ("*/.gitignore", "fest", "Git-Einstellung (Ausnahmen aufheben)"),
    (".gitattributes", "fest", "Git-Einstellung"),
    ("*/.gitattributes", "fest", "Git-Einstellung"),
    ("amw-*.py", "fest", "Einstiege (Befehlszeile, Hook, Statusline, Connector)"),
    ("*.pyw", "fest", "Einstiege (Dienst, Infobereich)"),
    ("CLAUDE.md", "fest", "Anweisungen an Agenten"),
    ("*/CLAUDE.md", "fest", "Anweisungen an Agenten"),
    ("amw/abnahme.py", "fest", "Abnahme und gesperrte Pfade"),
    ("amw/platz.py", "fest", "Arbeitsplätze"),
    ("amw/disponent*.py", "fest", "Disponent"),
    ("amw/dienst.py", "fest", "Disponent (Dienst)"),
    ("amw/arbeitspaket*.py", "fest", "Pakete und Zustände"),
    ("amw/auslieferung.py", "fest", "Auslieferung und Merge-Reihe"),
    ("amw/releasetakt.py", "fest", "Auslieferung"),
    ("amw/benutzer.py", "fest", "Rechte"),
    ("amw/bruecke.py", "fest", "Rechte (Dateiaustausch)"),
    ("amw/mcp_server.py", "fest", "Rechte (Connector)"),
    ("amw/mcp_schluessel.py", "fest", "Rechte (Connector)"),
    ("amw/rueckmeldung.py", "fest", "Rückmelde-Connector der Arbeiter (A1857)"),
    ("amw/vorlagen/*", "fest", "Auftragsvorlage der Arbeiter (A1857)"),
    # A1872 (S3b, Befund D1289): alles, was einen Arbeiter abschottet, prüft, startet oder Rechte vergibt
    ("amw/arbeiter.py", "fest", "Abschottung der Arbeiter"),
    ("amw/versionsprobe.py", "fest", "Negativprobe neuer Claude-Code-Versionen (A1906)"),
    ("amw/anbieter.py", "fest", "Anbieter je Projekt (A1931)"),
    ("amw/schalter.py", "fest", "Projekt-Schalter mit Probe (A1926)"),
    ("amw/anbieter_schluessel.py", "fest", "apiKeyHelper – gibt nur freigegebene Schlüsseldateien aus (A1931)"),
    ("amw-anbieter-schluessel.py", "fest", "apiKeyHelper (A1931)"),
    ("amw/gegenlesen.py", "fest", "Gegenleser der Themen – startet claude -p (A1914)"),
    ("amw/verteilen.py", "fest", "Verteilen an Agenten und Ausfall (A1927)"),
    ("amw/veroeffentlichung.py", "fest", "Veröffentlichung nach außen – Push, GitHub-Release (A1928)"),
    ("amw/waechter.py", "fest", "Startregeln (Wächter)"),
    ("amw/entscheidung.py", "fest", "Entscheidungstabelle nach dem Lauf"),
    ("amw/pruefung_c.py", "fest", "eigene Prüfung der AMW (Prüfung C)"),
    ("amw/tokenprognose.py", "fest", "Wochenlimit (Startregel 8)"),
    ("amw/db.py", "fest", "Datenbank und Live-Schutz"),
    ("amw/einstellungen.py", "fest", "Einstellungen dieses PCs (Datenbank-Pfad)"),
    ("amw/betrieb.py", "fest", "Läufe, Prüfungen, Merge-OK"),
    ("amw/laufdienst.py", "fest", "Lauf-Schlange"),
    ("amw/belegung.py", "fest", "Lauf-Schlange"),
    ("amw/kern.py", "fest", "Rechte und Projekt-Einstellungen"),
    ("amw/steuerung.py", "fest", "Agenten starten und beenden"),
    ("amw/paketliste.py", "fest", "Eingriffe des Menschen in p-Pakete (Pause, Notbremse)"),
    ("amw/mergeliste.py", "fest", "Merge-Freigabe der p-Pakete"),
    ("amw/limithalt.py", "fest", "Halt beim Wochenlimit"),
    ("amw/buendel.py", "fest", "Bündeln der p-Pakete zum Release-Stand (A1876)"),
    ("amw/cli.py", "fest", "Befehle mit ihren Sperren"),
    ("amw/aktionen.py", "fest", "Aktionen der Oberfläche mit ihren Sperren"),
    ("amw/schluessel.py", "fest", "Rechte (Schlüssel)"),
    ("amw/versionsnummer.py", "fest", "Auslieferung (Versionsnummer)"),
    ("amw/versionshinweise.py", "fest", "Auslieferung (Versionshinweise)"),
    ("amw/__main__.py", "fest", "Einstieg (python -m amw)"),
    # P274 (CCamwTL, Abgleich aller Dateien): Schema, Kanal und Netz, Einrichtung, Prüfkette, Bildschirm, KI-Rechte, Skripte, Server
    ("amw/schema.sql", "fest", "Schema (ändert nur der Mensch)"),
    ("amw/migration_*.sql", "fest", "Schema (ändert nur der Mensch)"),
    ("amw/workbench.py", "fest", "Oberfläche: Kanal, Token, Zugriff"),
    ("amw/abgleich.py", "fest", "Online-Abgleich, TLS"),
    ("amw/einrichtung.py", "fest", "Einrichtung der Agenten-Ordner (Hooks, Startskripte)"),
    ("amw/assistent.py", "fest", "Einrichtung (Startskripte, Leads)"),
    ("amw/pruefstufe.py", "fest", "Prüfkette (wer prüft)"),
    ("amw/schirm.py", "fest", "Bildschirm-Freigabe des Menschen"),
    ("amw/ki.py", "fest", "Rechte der lokalen KIs"),
    ("amw/pipe.py", "fest", "Nachrichten an Sitzungen (Zugangsschlüssel)"),
    ("amw/tray.py", "fest", "Einstieg (Infobereich, Bildschirm-Freigabe)"),
    ("amw/paket.py", "fest", "Server-Paket mit Zugang"),
    ("amw/push.py", "fest", "Benachrichtigungen nach außen"),
    ("amw/wissen.py", "fest", "Beschlüsse, Regeln, Wortlaut des Menschen"),
    ("amw/regelwerk.py", "fest", "Regeln"),
    ("amw/server/*", "fest", "Server-Konfiguration der Online-Seite"),
    ("bin/*", "fest", "Skripte"),
    ("*.sh", "fest", "Skripte"),
    ("web/.htaccess", "fest", "Zugriffsregeln der Online-Seite"),
    ("web/inc/.htaccess", "fest", "Zugriffsregeln der Online-Seite"),
    ("*/.htaccess", "fest", "Zugriffsregeln der Online-Seite"),
    ("web/sso.php", "fest", "Anmeldung der Online-Seite"),
    ("web/inc/sso.php", "fest", "Anmeldung der Online-Seite"),
    ("web/inc/lib.php", "fest", "Anmeldung und Zugriff der Online-Seite"),
    # Dateien, die Python und Werkzeuge beim Start von selbst laden (D1258 §6a.3) – überall im Baum
    ("sitecustomize.py", "fest", "automatisch geladen (Python-Start)"),
    ("*/sitecustomize.py", "fest", "automatisch geladen (Python-Start)"),
    ("usercustomize.py", "fest", "automatisch geladen (Python-Start)"),
    ("*/usercustomize.py", "fest", "automatisch geladen (Python-Start)"),
    ("*.pth", "fest", "automatisch geladen (Python-Pfade)"),
    ("conftest.py", "fest", "automatisch geladen (Test-Werkzeug)"),
    ("*/conftest.py", "fest", "automatisch geladen (Test-Werkzeug)"),
    ("pyproject.toml", "fest", "automatisch geladen (Werkzeug-Einstellungen)"),
    ("*/pyproject.toml", "fest", "automatisch geladen (Werkzeug-Einstellungen)"),
    ("setup.cfg", "fest", "automatisch geladen (Werkzeug-Einstellungen)"),
    ("*/setup.cfg", "fest", "automatisch geladen (Werkzeug-Einstellungen)"),
    ("tox.ini", "fest", "automatisch geladen (Werkzeug-Einstellungen)"),
    ("*/tox.ini", "fest", "automatisch geladen (Werkzeug-Einstellungen)"),
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
TEST_SCHREIBEN = "test-schreiben"          # Test + Änderung: der neue Test ist rot gegen den alten Code
TEST_ERGAENZEN = "test-ergaenzen"          # A1895: nur Tests für bestehenden, unveränderten Code – grün, nur Testdateien
TESTTYPEN = (TEST_SCHREIBEN, TEST_ERGAENZEN)   # Testdateien nicht gesperrt, Regel 6 entfällt, immer E4 (Lead liest)
FRIST_S = 1800


def _norm(pfad):
    n = str(pfad).replace("\\", "/")
    while n.startswith("./"):
        n = n[2:]
    return n


def _klein(pfad):
    """Für Vergleiche: Windows unterscheidet nicht nach Groß/Klein (Claude.md, .Claude/ wirken wie CLAUDE.md, .claude/)."""
    return _norm(pfad).lower()


def projekt_muster(con, pid):
    """A1919 (TH160 F2): Sperrmuster des Projekts (Projekt-Einstellung sperrmuster) – zusätzlich zur festen Liste GESPERRT."""
    import json
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    try:
        m = json.loads((r[0] if r else None) or "{}").get("sperrmuster") or []
    except ValueError:
        return []
    return [str(x) for x in m if str(x).strip()]


def muster_pruefen(v):
    """Projekt-Einstellung sperrmuster: Liste (JSON oder durch Komma getrennt), je Muster bis 200 Zeichen, höchstens 50."""
    import json
    if isinstance(v, str):
        s = v.strip()
        v = json.loads(s) if s.startswith(("[", "{")) else s.split(",")
    if not isinstance(v, list):
        raise ValueError("eine Liste von Mustern, z. B. [\"src/sicherheit/*\", \"*.key\"]")
    aus = []
    for x in v:
        x = str(x).strip().replace("\\", "/")
        if not x:
            continue
        if len(x) > 200 or x.startswith("/") or ".." in x.split("/"):
            raise ValueError(f"Muster „{x[:60]}“: relativ zum Projektordner, ohne .., bis 200 Zeichen")
        aus.append(x)
    if len(aus) > 50:
        raise ValueError("höchstens 50 Muster")
    return list(dict.fromkeys(aus))


def gesperrt(pfade, typ=None, projekt=None):
    """[(pfad, grund)] der gesperrten unter `pfade` – Testdateien nicht bei den Pakettypen test-schreiben und test-ergaenzen.
    projekt (A1919): die Sperrmuster des Projekts (projekt_muster) – gelten zusätzlich und für jeden Pakettyp; die feste Liste
    GESPERRT gilt immer."""
    aus = []
    for p in pfade:
        n, k = _norm(p), _klein(p)
        for muster, art, grund in GESPERRT:
            if fnmatch.fnmatchcase(k, muster.lower()) and not (art == "test" and typ in TESTTYPEN):
                aus.append((n, grund))
                break
        else:
            for muster in projekt or []:
                if fnmatch.fnmatchcase(k, muster.lower()):
                    aus.append((n, f"gesperrt im Projekt ({muster})"))
                    break
    return aus


def ist_testdatei(pfad):
    """A1895: eine Testdatei im Sinn der Sperrliste (Art „test“, z. B. tests/*) – und keine der fest gesperrten (Testskripte,
    Testkonfiguration, tests/abschotten.py …)."""
    k = _klein(pfad)
    for muster, art, _ in GESPERRT:
        if fnmatch.fnmatchcase(k, muster.lower()):
            return art == "test"
    return False


def nicht_nur_tests(pfade):
    """A1895 (Pakettyp test-ergaenzen): geänderte Dateien, die keine Testdateien sind – das Paket darf nur Tests anlegen/ändern."""
    return [_norm(p) for p in pfade if not ist_testdatei(p)]


def im_bereich(pfad, bereiche):
    """Liegt `pfad` in einem der Bereiche (Ordner „amw/“, Datei „amw/x.py“ oder Muster „web/hilfe/*.json“)?"""
    n = _klein(pfad)
    for b in bereiche or []:
        b = _klein(b)
        if b.endswith("/") and n.startswith(b) or n == b or fnmatch.fnmatchcase(n, b):
            return True
    return False


def startregel(bereiche, typ=None, projekt=None):
    """Regel 5 vor dem Start: Bereiche, die gesperrte Pfade enthalten oder sind → [(bereich, grund)]. projekt: A1919."""
    aus = []
    for b in bereiche or []:
        n = _klein(b)
        probe = n + "x" if n.endswith("/") else n                  # Ordner: gesperrt, wenn darin Gesperrtes liegen könnte
        treffer = gesperrt([probe], typ, projekt) or [(n, g) for m, art, g in GESPERRT
                                                      if (n.endswith("/") and m.lower().startswith(n)) and not (art == "test" and typ in TESTTYPEN)] \
            or [(n, f"gesperrt im Projekt ({m})") for m in (projekt or []) if n.endswith("/") and m.lower().startswith(n)]
        if treffer:
            aus.append((n, treffer[0][1]))
    return aus


def _git(klon, *args):
    r = subprocess.run(["git", "-c", "core.quotepath=off", "-C", klon, *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", stdin=subprocess.DEVNULL, timeout=300, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {(r.stdout + r.stderr).strip()[-300:]}")
    return r.stdout


def geaendert(klon, basis):
    """Alle Pfade, die der Arbeiter seit `basis` angefasst hat – Commits, Änderungen im Arbeitsbaum, neue Dateien."""
    pfade = set(_git(klon, "diff", "--no-renames", "--name-only", f"{basis}..HEAD").splitlines())   # P242: Umbenennen zeigt sonst
    pfade |= set(_git(klon, "diff", "--no-renames", "--name-only", "HEAD").splitlines())             # nur den neuen Namen
    pfade |= set(_git(klon, "ls-files", "--others", "--exclude-standard").splitlines())
    zwischen = lambda n: "/__pycache__/" in "/" + n or n.endswith((".pyc", ".pyo"))   # erzeugt die Abnahme selbst
    return sorted(n for n in (_norm(p) for p in pfade if p) if not zwischen(n))


def diff_tor(klon, basis, bereiche, typ=None, projekt=None):
    """{"ok", "ausserhalb": [pfad], "gesperrt": [(pfad, grund)], "geaendert": [pfad]} – nur geplante Bereiche, nichts Gesperrtes."""
    g = geaendert(klon, basis)
    ausserhalb = [p for p in g if not im_bereich(p, bereiche)]
    gesp = gesperrt(g, typ, projekt)
    return {"ok": bool(g) and not ausserhalb and not gesp, "leer": not g, "ausserhalb": ausserhalb, "gesperrt": gesp, "geaendert": g}


# --- Ausführen im Job-Objekt (Windows): ein Zeitlimit beendet den ganzen Prozessbaum ---------------------------------------

def _job_neu(name=None):
    """Ein Job-Objekt, das beim Schließen alle Prozesse beendet – oder None (kein Windows). name: benannt (Notbremse, A1848)."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.restype = wintypes.HANDLE
    k.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    job = k.CreateJobObjectW(None, name)
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


def _in_job(job, handle):
    """Prozess ins Job-Objekt; True bei Erfolg (eigene Funktion – im Test ersetzbar)."""
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.AssignProcessToJobObject.restype = wintypes.BOOL
    return bool(k.AssignProcessToJobObject(wintypes.HANDLE(job), wintypes.HANDLE(handle)))


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
        if not _in_job(job, int(p._handle)):                   # P242: ohne Job kein Zeitlimit für den ganzen Baum – nicht starten
            p.kill()                                           # er ist noch angehalten, hat also nichts gestartet
            p.communicate()
            ctypes.WinDLL("kernel32").CloseHandle(wintypes.HANDLE(job))
            return {"rc": None, "ausgabe": "", "zeitlimit": False, "dauer_s": round(time.monotonic() - t0, 1),
                    "fehler": "Prozess ließ sich nicht ins Job-Objekt nehmen – nicht ausgeführt"}
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
    r["gruen"] = r["rc"] == 0 and not r["zeitlimit"] and not r.get("fehler")
    return r


def rot_vor_bau(p, befehl, typ=None, frist=FRIST_S):
    """Regel 6: vor dem Bau muss die Abnahme rot sein – sonst prüft sie nichts. Beim Pakettyp test-schreiben entfällt das
    (dort wird geprüft, dass der neue Test gegen den alten Stand rot ist: test_gegen_basis). Rückgabe {"ok", "grund", …}."""
    if typ in TESTTYPEN:
        return {"ok": True, "grund": f"{typ}: Prüfung nach dem Bau"}
    r = abnahme(p, befehl, frist)
    if r.get("fehler"):
        return {**r, "ok": False, "grund": r["fehler"]}
    if r["zeitlimit"]:
        return {**r, "ok": False, "grund": "Abnahme hängt schon vor dem Bau (Zeitlimit)"}
    return {**r, "ok": not r["gruen"], "grund": None if not r["gruen"] else "Abnahme ist schon vor dem Bau grün – sie prüft nichts"}


def test_gegen_basis(p, befehl, basis, testdateien, frist=FRIST_S, umgebung=None):
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
        r = ausfuehren(befehl, p["klon"], umgebung or platz.umgebung(p), frist)   # A1849: Prüfung C gibt die minimale Umgebung mit
    finally:
        _git(p["klon"], "checkout", kopf, "--", ".")          # alles war committet: der Stand des Arbeiters ist unverändert
    if r.get("fehler"):
        return {**r, "ok": False, "grund": r["fehler"]}
    gruen = r["rc"] == 0 and not r["zeitlimit"]
    return {**r, "ok": not gruen, "grund": None if not gruen else "der neue Test ist schon gegen den alten Stand grün – er prüft nichts"}
