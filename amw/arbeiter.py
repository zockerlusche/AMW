"""`claude -p`-Arbeiter am Arbeitsplatz starten, abschotten und notfalls beenden (A1848, M50 S5a; D1258 §6 Schritt 2, D1270 Nr. 1,
5, 17, 19, 24).

Abschottung (gemessen mit Claude Code 2.1.326, Probe in der Prüfbitte):
- `--restricted`: Datei-Werkzeuge (auch Lesen) nur im Arbeitsordner des Platzes; Benutzer-, Projekt- und lokale Einstellungen
  (Hooks, Rechte, MCP) werden nicht geladen, auch keine CLAUDE.md; Schreiben in Einstellungen, .git und Werkzeug-Dateien braucht
  einen Menschen → im Modus dontAsk abgelehnt.
- `--strict-mcp-config`: keine MCP-Server außer denen, die die AMW mitgibt (S5a: keine; S5b: der Rückmelde-Zugang).
- `--settings` (Datei außerhalb des Klons) mit `defaultMode: dontAsk` und der Freigabeliste: Bash nur git status/diff/log/add/commit
  und genau der Abnahme-Befehl – alles andere lehnt Claude Code ohne Rückfrage ab (steht in `permission_denials`).
- Umgebung des Platzes (eigene DB, LOCALAPPDATA, TEMP, Port; keine Kennung, kein Nachrichten-Zugang), Auto-Update aus, UTF-8.
- Das init-Ereignis aus stream-json wird gegen die Sollliste geprüft (Werkzeuge, MCP, Modell, Rechte-Modus, Ordner, keine Skills,
  nur eingebaute Plugins). Abweichung → Lauf sofort beendet. Lücke: das Effort steht nicht im init-Ereignis (nur
  `per_turn_effort_active`) – es ist nur über den eigenen Startbefehl belegt.

Prozess: Der Arbeiter startet angehalten, kommt in ein benanntes Job-Objekt (beim Schließen alles beenden) und läuft erst dann.
Das Job-Objekt gehört dem Starter (dem Prozess, der `laufen` ausführt), nicht dem Dienst – ein Neustart des Dienstes beendet
keinen Arbeiter. Die Notbremse öffnet das Job-Objekt über seinen Namen und beendet den ganzen Baum (keine Waisen).

Restrisiko (Stufe 1, D1258 §12: kein eigener Windows-Benutzer): Code, den der Arbeiter schreibt, läuft über den Abnahme-Befehl mit
Marcels Rechten. Begrenzt durch: nur genau dieser Befehl, Job-Objekt mit Zeitlimit (Abnahme), Daten und Ports des Platzes,
Diff-Tor danach (abnahme.diff_tor), Live-DB-Schutz (A1862).
"""
import hashlib
import json
import os
import shutil
import subprocess
import time

from . import abnahme, db, platz

WERKZEUGE = ("Bash", "Edit", "Glob", "Grep", "Read", "Write")
# git nur in festen Formen: ein Platzhalter hinter diff/log erlaubte --output=<Datei irgendwo> (Schreiben außerhalb) und
# --no-index (Lesen beliebiger Dateien). Nur add und commit -m haben einen Platzhalter (Pfade bzw. Nachricht).
GIT_FEST = ("git status", "git status --short", "git diff", "git diff --stat", "git diff --cached", "git diff --cached --stat",
            "git diff HEAD", "git diff HEAD --stat", "git log --oneline -5", "git log --oneline -20", "git log -1", "git log -1 --stat")
GIT_FREI = ("git add *", "git commit -m *")
# … und keine Option, mit der git eine Datei (auch außerhalb des Platzes) einliest (Gegenlesen Nr. 3/4)
GIT_VERBOTEN = ("--output", "--no-index", "--exec", "-C ", "--git-dir", "--work-tree", "-c ", " -F", "--file", "--template", " -t ",
                "--pathspec-from-file", "--reuse-message", "--reedit-message", "--trailer")
STEUERDATEIEN = ("./.git/**", "./.claude/**", "./CLAUDE.md", "./.mcp.json", "**/.claude/**", "**/CLAUDE.md", "**/.mcp.json")
# Claude-Code-Versionen, für die die Negativprobe (test_arbeiter.test_echt_ausserhalb_abgelehnt) bestanden ist – eine andere
# Version gilt als Abweichung, bis die Probe wiederholt und die Version hier eingetragen ist (Gegenlesen Nr. 21/22).
GEPRUEFT = ("2.1.326",)
# Umgebung als Freigabeliste (Gegenlesen Nr. 7): nur diese Variablen des Menschen werden übernommen – keine Token, keine
# Umleitungen, keine Python-/Git-Steuerung. Das Login liegt im Benutzerordner (USERPROFILE), deshalb bleibt er gesetzt.
UMGEBUNG_ERLAUBT = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "OS", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
                    "PROCESSOR_IDENTIFIER", "PROCESSOR_LEVEL", "PROCESSOR_REVISION", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "HOME",
                    "USERNAME", "USERDOMAIN", "COMPUTERNAME", "APPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)",
                    "PROGRAMW6432", "COMMONPROGRAMFILES", "COMMONPROGRAMFILES(X86)", "COMMONPROGRAMW6432", "ALLUSERSPROFILE", "PUBLIC")
MODELL = "claude-opus-5-5"
EFFORT = "high"
EFFORTS = ("low", "medium", "high", "xhigh", "max")
# Probe 17.11.: im frischen Klon fehlt eine git-Identität („Author identity unknown“). Neutral, ohne Personennamen (KR22) –
# welche Identität öffentlich erscheinen soll, entscheidet der Mensch (Prüfbitte); AMW_ARBEITER_GIT_NAME/-_EMAIL gehen vor.
GIT_NAME = "AMW-Arbeiter"
GIT_EMAIL = "arbeiter@amw.invalid"


class ArbeiterFehler(ValueError):
    pass


# --- Startbefehl, Freigabeliste, Umgebung ----------------------------------------------------------------------------------

def ordner(p):
    """Eigener Ordner des Starters neben dem Klon (nie im Klon – sonst sähe ihn das Diff-Tor bzw. der Arbeiter)."""
    return os.path.join(p["daten"], "arbeiter")


def freigabe(pruefbefehl):
    """Die Freigabeliste (permissions) für `--settings`. Ohne Eintrag lehnt dontAsk ab."""
    befehl = (pruefbefehl or "").strip()
    if not befehl:
        raise ArbeiterFehler("ohne Abnahme-Befehl startet kein Arbeiter (Regel 1)")
    if any(z in befehl for z in ("&&", "||", ";", "|", ">", "<", "`", "$(", "\n")):
        raise ArbeiterFehler(f"Abnahme-Befehl „{befehl}“: nur ein einzelner Befehl ohne Verkettung oder Umleitung")
    allow = ["Read", "Glob", "Grep", "Edit", "Write"] + [f"Bash({g})" for g in GIT_FEST + GIT_FREI] + [f"Bash({befehl})"]
    steuer = [f"{w}({m})" for w in ("Edit", "Write") for m in STEUERDATEIEN]     # Gegenlesen D Nr. 1/2: zusätzlich zu --restricted
    # „-c “/„-C “ mit Leerzeichen – ohne träfe die Sperre auch das erlaubte „git diff --cached“
    deny = [f"Bash(*{v}*)" for v in GIT_VERBOTEN] + ["Bash(git push*)", "Bash(git remote*)", "Bash(git config*)",
            "Bash(git reset*)", "Bash(git checkout*)", "Bash(git switch*)", "Bash(git rebase*)", "Bash(git clean*)", "WebFetch", "WebSearch"] + steuer
    import fnmatch                                             # P259 (1): deny geht vor allow – trifft der Abnahme-Befehl eine
    trifft = [d for d in deny if d.startswith("Bash(") and fnmatch.fnmatchcase(befehl, d[5:-1])]   # Sperre, könnte ihn der
    if trifft:                                                 # Arbeiter nie ausführen (unklar → Regel 9): gleich ablehnen
        raise ArbeiterFehler(f"Abnahme-Befehl „{befehl}“ trifft die Sperre {trifft[0]} – bitte ohne diese Option formulieren")
    return {"permissions": {"defaultMode": "dontAsk", "allow": allow, "deny": deny}, "env": {"DISABLE_AUTOUPDATER": "1"}}


def programm():
    """claude.exe – nicht der npm-Starter claude.cmd (dort ginge die Befehlszeile durch cmd.exe). AMW_CLAUDE_EXE geht vor."""
    if os.environ.get("AMW_CLAUDE_EXE"):
        return os.environ["AMW_CLAUDE_EXE"]
    w = shutil.which("claude")
    if not w:
        raise ArbeiterFehler("claude nicht gefunden")
    if w.lower().endswith((".cmd", ".bat")) or not os.path.splitext(w)[1]:
        exe = os.path.join(os.path.dirname(w), "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe")
        if os.path.exists(exe):
            return exe
    return w


def befehl(p, einstellungen, modell=None, effort=None, mcp=None, sitzung=None, prog=None):
    """Argumente für den Arbeiter. Der Auftrag kommt über stdin (keine Längengrenze, keine Anführungszeichen-Fallen)."""
    effort = effort or EFFORT
    if effort not in EFFORTS:
        raise ArbeiterFehler(f"Effort „{effort}“: {', '.join(EFFORTS)}")
    prog = prog or programm()
    a = [*(prog if isinstance(prog, (list, tuple)) else [prog]), "-p", "--model", modell or MODELL, "--effort", effort, "--restricted",
         "--tools", ",".join(WERKZEUGE), "--strict-mcp-config", "--settings", einstellungen, "--permission-mode", "dontAsk",
         "--output-format", "stream-json", "--verbose", "--disable-slash-commands"]
    if mcp:
        a += ["--mcp-config", mcp]
    if sitzung:
        a += ["--session-id", sitzung]
    return a


def _pfad():
    """Minimaler PATH: Windows, Python, git (samt Git-Bash für das Bash-Werkzeug) – nicht der PATH des Menschen (Nr. 6)."""
    import sys
    sr = os.environ.get("SYSTEMROOT", r"C:\Windows")
    teile = [os.path.join(sr, "System32"), sr, os.path.join(sr, "System32", "Wbem"), os.path.dirname(sys.executable)]
    g = shutil.which("git")
    if g:
        wurzel = os.path.dirname(os.path.dirname(g))
        if os.path.basename(wurzel).lower() in ("mingw64", "mingw32"):
            wurzel = os.path.dirname(wurzel)
        teile += [os.path.dirname(g), os.path.join(wurzel, "cmd"), os.path.join(wurzel, "usr", "bin")]
    return os.pathsep.join(dict.fromkeys(t for t in teile if os.path.isdir(t)))


def umgebung(p, basis=None, zusatz=None):
    """Umgebung neu gebaut (Freigabeliste UMGEBUNG_ERLAUBT) + Werte des Platzes (platz.umgebung: DB, LOCALAPPDATA, TEMP, Port)
    + minimaler PATH, Auto-Update aus, UTF-8, git ohne globale/System-Konfiguration, ohne Hooks und fsmonitor (Nr. 1, 6–8)."""
    quelle = dict(os.environ if basis is None else basis)
    gross = {k.upper(): v for k, v in quelle.items()}
    u = {k: gross[k] for k in UMGEBUNG_ERLAUBT if k in gross}
    platz_werte = platz.umgebung(p, {})
    u.update(platz_werte)
    leer = os.path.join(ordner(p), "git-leer")
    os.makedirs(os.path.join(leer, "hooks"), exist_ok=True)
    open(os.path.join(leer, "gitconfig"), "a").close()
    u.update(PATH=_pfad(), DISABLE_AUTOUPDATER="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1",
             GIT_CONFIG_GLOBAL=os.path.join(leer, "gitconfig"), GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0",
             GIT_CONFIG_COUNT="3", GIT_CONFIG_KEY_0="core.hooksPath", GIT_CONFIG_VALUE_0=os.path.join(leer, "hooks"),
             GIT_CONFIG_KEY_1="core.fsmonitor", GIT_CONFIG_VALUE_1="false", GIT_CONFIG_KEY_2="core.pager", GIT_CONFIG_VALUE_2="cat")
    u.update(zusatz or {})                                    # nur Tests (Attrappe); der Disponent gibt nichts mit
    name = os.environ.get("AMW_ARBEITER_GIT_NAME") or GIT_NAME
    mail = os.environ.get("AMW_ARBEITER_GIT_EMAIL") or GIT_EMAIL
    u.update(GIT_AUTHOR_NAME=name, GIT_COMMITTER_NAME=name, GIT_AUTHOR_EMAIL=mail, GIT_COMMITTER_EMAIL=mail)
    return u


# --- Sollliste für das init-Ereignis ---------------------------------------------------------------------------------------

def soll(p, modell=None, mcp_namen=()):
    return {"cwd": p["klon"], "modell": modell or MODELL, "werkzeuge": sorted(WERKZEUGE), "mcp": sorted(mcp_namen),
            "versionen": GEPRUEFT}


def _modell_passt(ist, gewollt):
    ist, gewollt = (ist or "").lower(), (gewollt or "").lower()
    if gewollt in ("opus", "sonnet", "haiku", "fable"):              # Kurzname: Familie muss passen
        return f"-{gewollt}-" in f"-{ist}-" or ist.startswith(f"claude-{gewollt}")
    return ist == gewollt or ist.startswith(gewollt + "[") or ist.startswith(gewollt + "-2")


def init_pruefen(ereignis, s):
    """Abweichungen des init-Ereignisses von der Sollliste – leere Liste = in Ordnung."""
    if not isinstance(ereignis, dict) or ereignis.get("type") != "system" or ereignis.get("subtype") != "init":
        return ["erstes Ereignis ist kein init"]
    ab = []
    norm = lambda x: os.path.normcase(os.path.abspath(x or ""))
    if norm(ereignis.get("cwd")) != norm(s["cwd"]):
        ab.append(f"Ordner {ereignis.get('cwd')} statt {s['cwd']}")
    if ereignis.get("additional_directories"):
        ab.append(f"weitere Ordner: {ereignis['additional_directories']}")
    if not _modell_passt(ereignis.get("model"), s["modell"]):
        ab.append(f"Modell {ereignis.get('model')} statt {s['modell']}")
    if ereignis.get("permissionMode") != "dontAsk":
        ab.append(f"Rechte-Modus {ereignis.get('permissionMode')} statt dontAsk")
    if sorted(ereignis.get("tools") or []) != s["werkzeuge"]:
        ab.append(f"Werkzeuge {sorted(ereignis.get('tools') or [])} statt {s['werkzeuge']}")
    mcp = sorted((m.get("name") if isinstance(m, dict) else str(m)) for m in (ereignis.get("mcp_servers") or []))
    if mcp != s["mcp"]:
        ab.append(f"MCP-Server {mcp} statt {s['mcp']}")
    for feld in ("skills", "slash_commands"):
        if ereignis.get(feld):
            ab.append(f"{feld}: {ereignis[feld]}")
    if s.get("versionen") and ereignis.get("claude_code_version") not in s["versionen"]:
        ab.append(f"Claude Code {ereignis.get('claude_code_version')} ist nicht geprüft (geprüft: {', '.join(s['versionen'])}) – "
                  "Negativprobe wiederholen, dann in arbeiter.GEPRUEFT eintragen")
    fremd = [x.get("name") for x in (ereignis.get("plugins") or []) if not isinstance(x, dict) or x.get("path") != "builtin"]
    if fremd:
        ab.append(f"Plugins außer den eingebauten: {fremd}")
    return ab


# --- Job-Objekt und Notbremse ----------------------------------------------------------------------------------------------

def job_name(p):
    """Name des Job-Objekts eines Platzes – eindeutig je Klon-Ordner auf diesem PC."""
    return "Local\\amw-arbeiter-" + hashlib.sha256(os.path.normcase(os.path.abspath(p["klon"])).encode("utf-8")).hexdigest()[:16]


def _kernel():
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenJobObjectW.restype = wintypes.HANDLE
    k.OpenJobObjectW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    k.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    return k


UI_GRENZEN = 0x1 | 0x2 | 0x4 | 0x8 | 0x10 | 0x20 | 0x40 | 0x80   # HANDLES, Zwischenablage lesen/schreiben, Systemparameter,
#                                                                 Anzeige, globale Atome, Desktop, Abmelden (Gegenlesen Nr. 18)


def _grenzen(job):
    """UI-Grenzen setzen; Rückgabe: aktive Prozesse im Job (0 = frisch angelegt, sonst gab es den Namen schon – Nr. 16)."""
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    ui = wintypes.DWORD(UI_GRENZEN)
    k.SetInformationJobObject(wintypes.HANDLE(job), 4, ctypes.byref(ui), ctypes.sizeof(ui))       # BasicUIRestrictions
    return aktive(job)


def aktive(job):
    """Anzahl der Prozesse im Job-Objekt (JobObjectBasicAccountingInformation)."""
    import ctypes
    from ctypes import wintypes

    class Buchung(ctypes.Structure):
        _fields_ = [("a", ctypes.c_int64), ("b", ctypes.c_int64), ("c", ctypes.c_int64), ("d", ctypes.c_int64),
                    ("TotalPageFaultCount", wintypes.DWORD), ("TotalProcesses", wintypes.DWORD),
                    ("ActiveProcesses", wintypes.DWORD), ("TotalTerminatedProcesses", wintypes.DWORD)]
    b = Buchung()
    ok = ctypes.WinDLL("kernel32").QueryInformationJobObject(wintypes.HANDLE(job), 1, ctypes.byref(b), ctypes.sizeof(b), None)
    return b.ActiveProcesses if ok else -1


def notbremse(p):
    """Beendet den Arbeiter des Platzes samt aller Kindprozesse (TerminateJobObject über den Namen). True = es lief einer."""
    if os.name != "nt":
        raise ArbeiterFehler("Notbremse gibt es nur unter Windows (Job-Objekt)")
    k = _kernel()
    job = k.OpenJobObjectW(0x0008 | 0x0004, False, job_name(p))          # JOB_OBJECT_TERMINATE | QUERY
    if not job:
        return False
    try:
        ok = bool(k.TerminateJobObject(job, 1))
        for _ in range(50):                                    # Rückmeldung: ist wirklich nichts mehr übrig? (Nr. 20)
            if aktive(job) == 0:
                break
            time.sleep(0.1)
        if aktive(job) > 0:
            raise ArbeiterFehler(f"Notbremse Platz {p['nr']}: {aktive(job)} Prozess(e) laufen noch – bitte ansehen")
        return ok
    finally:
        k.CloseHandle(job)


def notbremse_ziehen(con, pid, p, von, aufgabe=None):
    """Notbremse des Menschen (D1258 §2): Arbeiter + Kinder beenden, Übergabe-Notiz und Protokoll in der AMW (keine Datei),
    Meldung an den Lead. Rückgabe: Text für die Ausgabe."""
    from . import kern
    if (von != kern.ENTWICKLER or os.environ.get("AMW_AGENT") or os.environ.get("CLAUDE_CODE_MESSAGING_SOCKET")
            or os.environ.get("CLAUDECODE")):                  # P259 (3): dieselbe Sperre wie der Agentenstart (A1865)
        raise kern.AmwFehler("Die Notbremse zieht nur der Mensch (--von Entwickler, nicht aus einer Agenten-Sitzung)")
    lief = notbremse(p)
    notiz = uebergabe(p) if os.path.isdir(os.path.join(p["klon"], ".git")) else "kein Klon"
    text = (f"Platz {p['nr']}: " + ("Arbeiter samt Kindprozessen beendet" if lief else "kein laufender Arbeiter") + f" – {notiz}")[:1500]
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art="notbremse", aufgabe_id=aufgabe, text=text)
        if lief:
            kern._posten(con, pid, "AMW", kern.lead(con, pid) or kern.ENTWICKLER, "info",
                         f"Notbremse: Platz {p['nr']}" + (f" (A{aufgabe})" if aufgabe else "") + " beendet", text)
    return text


def uebergabe(p, basis=None):
    """Maschinelle Übergabe-Notiz (kein Dateischreiben): Stand im Klon für den, der übernimmt."""
    teile = []
    for args, titel in ((["log", "-1", "--format=%h %s"], "letzter Commit"), (["status", "--short"], "offen"),
                        (["diff", "--stat", basis or "HEAD"], "Änderungen")):
        r = subprocess.run(["git", "-c", "core.quotepath=off", "-C", p["klon"], *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        teile.append(f"{titel}: {(r.stdout or r.stderr).strip()[-600:] or '–'}")
    return " · ".join(teile)


# --- Lauf ------------------------------------------------------------------------------------------------------------------

def laufen(p, auftrag, pruefbefehl, modell=None, effort=None, mcp=None, mcp_namen=(), sitzung=None, prog=None, basis_umgebung=None,
           zusatz=None):
    """Einen Arbeiter im Platz `p` laufen lassen, bis er endet. Rückgabe {"rc", "abweichungen", "init", "ergebnis",
    "sitzung", "protokoll", "dauer_s", "fehler"}. Abweichung im init-Ereignis → sofort beendet (rc None, abweichungen gesetzt)."""
    if os.name != "nt":
        raise ArbeiterFehler("Arbeiter nur unter Windows (Job-Objekt)")
    if not os.path.isdir(os.path.join(p["klon"], ".git")):
        raise ArbeiterFehler(f"Platz {p['nr']} ist nicht vorbereitet (kein Klon)")
    o = ordner(p)
    os.makedirs(o, exist_ok=True)
    for d in (p["lad"], p["tmp"]):
        os.makedirs(d, exist_ok=True)
    if os.name == "nt":                                                         # läuft hier schon einer? (gleiches Job-Objekt)
        k0 = _kernel()
        alt = k0.OpenJobObjectW(0x0004, False, job_name(p))
        if alt:
            k0.CloseHandle(alt)
            raise ArbeiterFehler(f"Platz {p['nr']}: dort läuft schon ein Arbeiter")
    datei = os.path.join(o, "einstellungen.json")
    with open(datei, "w", encoding="utf-8") as f:
        json.dump(freigabe(pruefbefehl), f, ensure_ascii=False, indent=1)
    argv = befehl(p, datei, modell, effort, mcp, sitzung, prog)
    s = soll(p, modell, mcp_namen)
    protokoll = os.path.join(o, "lauf.jsonl")
    t0 = time.monotonic()
    job = abnahme._job_neu(job_name(p))
    if not job:
        raise ArbeiterFehler("Job-Objekt ließ sich nicht anlegen – ohne Notbremse kein Start")
    if _grenzen(job) != 0:                                     # den Namen gab es schon (fremdes oder altes Objekt): nicht hinein
        _kernel().CloseHandle(job)
        raise ArbeiterFehler(f"Platz {p['nr']}: Job-Objekt {job_name(p)} besteht schon mit laufenden Prozessen – kein Start")
    import ctypes
    from ctypes import wintypes
    k = _kernel()
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | 0x4                     # CREATE_SUSPENDED
    try:
        proc = subprocess.Popen(argv, cwd=p["klon"], env=umgebung(p, basis_umgebung, zusatz), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, creationflags=flags)
        if not abnahme._in_job(job, int(proc._handle)):
            proc.kill()
            proc.communicate()
            return {"rc": None, "abweichungen": [], "init": None, "ergebnis": None, "sitzung": None, "protokoll": protokoll,
                    "dauer_s": round(time.monotonic() - t0, 1), "fehler": "Prozess ließ sich nicht ins Job-Objekt nehmen – nicht gestartet"}
        ctypes.WinDLL("ntdll").NtResumeProcess(wintypes.HANDLE(int(proc._handle)))
        try:
            proc.stdin.write(auftrag.encode("utf-8"))
            proc.stdin.close()
        except OSError:
            pass
        init, ergebnis, abweichungen = None, None, []
        with open(protokoll, "w", encoding="utf-8") as aus:
            for zeile in proc.stdout:
                text = zeile.decode("utf-8", "replace")
                aus.write(text)
                aus.flush()
                try:
                    e = json.loads(text)
                except ValueError:
                    continue
                if init is None and isinstance(e, dict) and e.get("type") == "system":
                    init = e
                    abweichungen = init_pruefen(e, s)
                    if abweichungen:
                        k.TerminateJobObject(wintypes.HANDLE(job), 1)
                        break
                elif isinstance(e, dict) and e.get("type") == "assistant":   # jeder Werkzeugaufruf gegen die Liste (Nr. 21)
                    fremd = [c.get("name") for c in (e.get("message") or {}).get("content") or []
                             if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") not in WERKZEUGE
                             and not str(c.get("name", "")).startswith(tuple(f"mcp__{m}__" for m in mcp_namen))]
                    if fremd:
                        abweichungen = [f"Werkzeug außerhalb der Liste aufgerufen: {fremd}"]
                        k.TerminateJobObject(wintypes.HANDLE(job), 1)
                        break
                elif isinstance(e, dict) and e.get("type") == "result":
                    ergebnis = e
        proc.wait()
        k.TerminateJobObject(wintypes.HANDLE(job), 0)          # D1258 v9 §6a 3.1: Lauf zu Ende → Job hart beenden, keine Reste
        rest = 0
        for _ in range(50):
            rest = aktive(job)
            if rest <= 0:
                break
            time.sleep(0.1)
        if rest > 0:
            abweichungen = abweichungen + [f"{rest} Prozess(e) im Job nach dem Laufende nicht beendet"]
        if init is None and not abweichungen:
            abweichungen = ["kein init-Ereignis"]
        return {"rc": None if abweichungen else proc.returncode, "abweichungen": abweichungen, "init": init, "ergebnis": ergebnis,
                "sitzung": (init or {}).get("session_id"), "protokoll": protokoll, "dauer_s": round(time.monotonic() - t0, 1),
                "fehler": None}
    finally:
        k.CloseHandle(wintypes.HANDLE(job))                                    # KILL_ON_JOB_CLOSE: nichts bleibt zurück
