"""Agenten steuern (Stufe D, → doc/ausbau.md §5): Profil, Starten, Beenden, Auto-Neustart nach Absturz, Startskript.

Ein Agent startet in einem eigenen Windows-Terminal-Tab (sonst Konsolenfenster): PowerShell setzt AMW_AGENT und ruft
Claude Code mit dem Profil auf. Gibt es eine frühere Sitzung des Agenten, wird sie fortgesetzt (--resume), sonst
beginnt eine neue mit vorgegebener --session-id – so ist die Zuordnung Sitzung ↔ Agent sofort eindeutig.
Beenden trifft nur den Claude-Prozess dieser Sitzung (das Fenster bleibt) und wird vermerkt. Neu gestartet wird
automatisch nur nach einem echten Absturz: Claude weg, Fenster noch da, kein bewusstes Ende – wer ein Fenster schließt,
beendet bewusst. Nur am PC; nie über die Online-Seite.
"""
import base64
import ctypes
import ctypes.wintypes as wt
import datetime
import json
import os
import re
import shutil
import subprocess
import time
import uuid

from . import db, kern

DENKSTUFEN = ("low", "medium", "high", "xhigh", "max")
RECHTE = {"vorgabe": [], "auto": ["--permission-mode", "auto"], "umgehen": ["--dangerously-skip-permissions"]}
BEWUSST = ("prompt_input_exit", "logout", "clear", "amw")     # SessionEnd-Gründe bzw. AMW-Beenden: kein Absturz
NEUSTARTS_JE_STUNDE = 3
NEUSTART_FENSTER_S = 900       # nur Abstürze der letzten 15 min


# --- Prozesse (Windows-API über ctypes, nur Standardbibliothek) ----------------------------------

class _PE(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


def prozesse():
    """{pid: (eltern_pid, exe)} aller laufenden Prozesse."""
    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    erg = {}
    try:
        e = _PE()
        e.dwSize = ctypes.sizeof(_PE)
        ok = k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            erg[e.th32ProcessID] = (e.th32ParentProcessID, e.szExeFile)
            ok = k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    return erg


def lebt(pid):
    if not pid:
        return False
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = wt.HANDLE
    h = k32.OpenProcess(0x1000, False, int(pid))         # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = wt.DWORD()
        return bool(k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259   # STILL_ACTIVE
    finally:
        k32.CloseHandle(h)


def eltern(pid, alle=None):
    alle = alle if alle is not None else prozesse()
    return alle.get(int(pid), (None, None))[0] if pid else None


# --- Profil --------------------------------------------------------------------------------------

def profil(con, pid, kennung):
    a = kern.agent_zeile(con, pid, kennung)
    try:
        zusatz = json.loads(a["zusatzordner"] or "[]")
    except ValueError:
        zusatz = []
    projekt = con.execute("SELECT name FROM projekt WHERE id = ?", (pid,)).fetchone()["name"]
    return {"kennung": a["kennung"], "projekt": projekt, "ordner": a["ordner"], "zusatzordner": zusatz, "denkstufe": a["denkstufe"],
            "modell": a["modell"], "startsatz": a["startsatz"], "rechte": a["rechte"] or "vorgabe",
            "fernsteuerung": bool(a["fernsteuerung"]), "neustart_auto": bool(a["neustart_auto"])}


WORT_GUELTIG_H = 24
WORT_NIE_FUER_SICH = ("rechte", "fernsteuerung", "neustart_auto")   # der Lead erhöht sich selbst nie über ein Wort


def wort_pruefen(con, pid, wort):
    """W<nr> muss ein Wortlaut des Entwicklers aus diesem Projekt und den letzten WORT_GUELTIG_H Stunden sein (A1662)."""
    import datetime
    nr = str(wort or "").strip().upper().lstrip("W")
    if not nr.isdigit():
        raise kern.AmwFehler("--wort W<nr> – die Nummer eines Wortlauts des Entwicklers")
    w = con.execute("SELECT id, zeit_utc, text FROM wortlaut WHERE id = ? AND projekt_id = ?", (int(nr), pid)).fetchone()
    if not w:
        raise kern.AmwFehler(f"W{nr} gibt es in diesem Projekt nicht")
    grenze = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=WORT_GUELTIG_H)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if w["zeit_utc"] < grenze:
        raise kern.AmwFehler(f"W{nr} ist älter als {WORT_GUELTIG_H} Stunden – für eine Profiländerung braucht es ein frisches Wort")
    return w


def profil_setzen(con, pid, von, kennung, wort=None, **werte):
    """Nur Lead und Entwickler. Prüft Ordner, Denkstufe, Rechte; Zusatzordner als Liste. wort (A1662): Änderung auf ein frisches
    Wort des Entwicklers – auch über den Dateiaustausch; dann nie die eigenen Rechte/Fernsteuerung des Leads, jede Änderung
    mit alt → neu im Verlauf und eine Info an den Menschen."""
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Profile ändern nur Lead und Entwickler")
    kern.agent_zeile(con, pid, kennung)
    w = wort_pruefen(con, pid, wort) if wort else None
    if w and kennung.casefold() == str(von).casefold():
        selbst = [k for k in WORT_NIE_FUER_SICH if werte.get(k) is not None]
        if selbst:
            raise kern.AmwFehler(f"{', '.join(selbst)} am eigenen Profil ändert ein Lead nie über ein Wort – das macht der Entwickler am PC")
    vorher = profil(con, pid, kennung)
    setzen = {}
    for k, v in werte.items():
        if v is None:
            continue
        if k == "ordner":
            v = str(v).strip()
            if v and not os.path.isdir(v):
                raise kern.AmwFehler(f"Ordner {v} gibt es nicht")
        elif k == "zusatzordner":
            liste = [x.strip() for x in (v if isinstance(v, list) else str(v).split(";")) if x.strip()]
            fehlt = [x for x in liste if not os.path.isdir(x)]
            if fehlt:
                raise kern.AmwFehler(f"Ordner gibt es nicht: {', '.join(fehlt)}")
            v = json.dumps(liste, ensure_ascii=False)
        elif k == "denkstufe":
            if v and v not in DENKSTUFEN:
                raise kern.AmwFehler(f"Denkaufwand: {', '.join(DENKSTUFEN)}")
        elif k == "rechte":
            if v not in RECHTE:
                raise kern.AmwFehler(f"Rechte: {', '.join(RECHTE)}")
        elif k in ("fernsteuerung", "neustart_auto"):
            v = int(bool(v))
        elif k in ("modell", "startsatz"):
            v = str(v).strip()[:4000]
        else:
            raise kern.AmwFehler(f"unbekanntes Profilfeld {k}")
        setzen[k] = v
    if setzen:
        with db.schreiben(con):
            con.execute(f"UPDATE agent SET {', '.join(k + ' = ?' for k in setzen)} WHERE projekt_id = ? AND kennung = ?",
                        (*setzen.values(), pid, kennung))         # Spaltennamen nur aus der Prüfung oben
    nachher = profil(con, pid, kennung)
    if w:                                            # A1662: Verlauf je Feld + eine Info an den Menschen
        geaendert = [f"{k}: {vorher.get(k)!s} → {nachher.get(k)!s}" for k in setzen if vorher.get(k) != nachher.get(k)]
        if geaendert:
            with db.schreiben(con):
                for z in geaendert:
                    db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art="profil_auf_wort",
                                 text=f"{kennung} · {z} · W{w['id']}")
                kern._posten(con, pid, "AMW", kern.ENTWICKLER, "info", f"{von} hat das Profil von {kennung} geändert (auf dein Wort W{w['id']})",
                             "\n".join(geaendert) + f"\n\nDein Wort: „{(w['text'] or '')[:300]}“")
    return nachher


# --- Befehl --------------------------------------------------------------------------------------

def _ps(s):
    return "'" + str(s).replace("'", "''") + "'"


def claude_befehl():
    from . import einstellungen
    return einstellungen.wert("claude_befehl") or "claude"


def _optionen(p):
    """Was aus dem Profil an Claude geht (ohne Sitzung und ersten Satz)."""
    teile = []
    if p["fernsteuerung"]:
        teile += ["--remote-control", p["kennung"]]
    if p["denkstufe"]:
        teile += ["--effort", p["denkstufe"]]
    if p["modell"]:
        teile += ["--model", p["modell"]]
    for z in p["zusatzordner"]:
        teile += ["--add-dir", z]
    return teile + RECHTE.get(p["rechte"], [])


def _wort(x):
    """Für PowerShell: einfache Wörter (Schalter, IDs, Pfade ohne Leerzeichen) lesbar ohne Anführungszeichen, alles andere in '…'."""
    return x if re.fullmatch(r"-{0,2}[A-Za-z0-9_][A-Za-z0-9_.:/\-]*", x) else _ps(x)


def _aufruf(teile, lesbar=False):
    erstes = claude_befehl()
    return ((f"& {_ps(erstes)} " if " " in erstes or "\\" in erstes else f"{erstes} ")
            + " ".join((_wort if lesbar else _ps)(x) for x in teile))


# Nach dem Ende von Claude (auch nach hartem Beenden: die PowerShell im Tab lebt mit -NoExit weiter) das Terminal aus dem
# Mausmodus holen – sonst schreibt jeder Klick Steuerzeichen in den Tab (Probe 07.11.). Nur einfache Anführungszeichen:
# die .bat ersetzt doppelte (_bat).
MAUS_AUS = "[Console]::Write(" + "+".join(f"[char]27+'[?{n}l'" for n in (1000, 1002, 1003, 1006, 1015, 2004)) + ")"


def befehl(p, fortsetzen_id=None, neue_id=None):
    """PowerShell-Befehlszeile für den Tab: Umgebung setzen, Claude mit Profil starten. Mit beiden IDs (A1865, wie das
    Startskript): erst die letzte Sitzung fortsetzen; scheitert das (Sitzung gibt es nicht mehr), neu mit der festen ID und
    dem Startsatz."""
    neu = (["--session-id", neue_id] if neue_id else []) + _optionen(p) + ([p["startsatz"]] if p["startsatz"] else [])
    if fortsetzen_id:
        aufruf = _aufruf(["--resume", fortsetzen_id] + _optionen(p))
        if neue_id:
            aufruf += f"; if ($LASTEXITCODE -ne 0) {{ {_aufruf(neu)} }}"
    else:
        aufruf = _aufruf(neu)
    projekt = f"$env:AMW_PROJEKT = {_ps(p['projekt'])}; " if p.get("projekt") else ""
    return f"Set-Location {_ps(p['ordner'])}; $env:AMW_AGENT = {_ps(p['kennung'])}; {projekt}{aufruf}; {MAUS_AUS}"


def _cmd(x):
    """Für cmd: einfache Wörter so, alles andere in "…" (innere " als \\"); Zeilenumbrüche werden Leerzeichen."""
    x = " ".join(str(x).splitlines())
    return x if re.fullmatch(r"[A-Za-z0-9_.:/\\=\-]+", x) else '"' + x.replace('"', '\\"') + '"'


def startbefehle(con, pid, kennung):
    """Was man braucht, um einen Agenten von Hand zu starten: Angaben aus dem Profil, letzte Sitzung und fertige Zeilen für
    PowerShell und cmd – „fortsetzen“ (letzte Sitzung) und „neu“ (feste neue Sitzungs-ID, bis sie benutzt wurde).
    Ohne Zeilen, wenn der Agent nicht im Terminal arbeitet oder kein Ordner eingetragen ist (grund)."""
    a = kern.agent_zeile(con, pid, kennung)
    p = profil(con, pid, kennung)
    r = con.execute("SELECT s.claude_sitzung, s.gestartet_utc, coalesce(s.letzter_puls_utc, s.beendet_utc, s.gestartet_utc) AS zuletzt,"
                    " s.zustand, (SELECT count(*) FROM sitzung x WHERE x.agent_id = a.id) AS anzahl FROM sitzung s JOIN agent a"
                    " ON a.id = s.agent_id WHERE a.projekt_id = ? AND a.kennung = ? AND s.claude_sitzung IS NOT NULL ORDER BY s.id DESC LIMIT 1",
                    (pid, kennung)).fetchone()
    weise = a["arbeitsweise"] or "terminal"
    aus = {"arbeitsweise": weise, "ordner": p["ordner"], "zusatzordner": p["zusatzordner"], "modell": p["modell"],
           "denkstufe": p["denkstufe"], "rechte": p["rechte"], "startsatz": p["startsatz"], "fernsteuerung": p["fernsteuerung"],
           "letzte": {"sitzung": r["claude_sitzung"], "gestartet_utc": r["gestartet_utc"], "zuletzt_utc": r["zuletzt"],
                      "zustand": r["zustand"]} if r else None, "befehle": None, "grund": None}
    if weise != "terminal":
        aus["grund"] = weise
        return aus
    if not p["ordner"]:
        aus["grund"] = "kein_ordner"
        return aus
    fort = fortsetzbar(con, pid, kennung, p["ordner"])[0]     # A1881: nur im selben Claude-Projektordner
    neue = str(uuid.uuid5(uuid.NAMESPACE_URL, f"amw:{a['uid']}:{r['claude_sitzung'] if r else ''}:{r['anzahl'] if r else 0}"))

    def teile(fortsetzen):
        x = ["--resume", fort] if fortsetzen else ["--session-id", neue]
        x += _optionen(p)
        if not fortsetzen and p["startsatz"]:
            x.append(p["startsatz"])
        return x

    def ps(fortsetzen):
        return (f"Set-Location {_ps(p['ordner'])}; $env:AMW_AGENT = {_ps(p['kennung'])}; $env:AMW_PROJEKT = {_ps(p['projekt'])}; "
                + _aufruf(teile(fortsetzen), lesbar=True))

    def cmd(fortsetzen):
        return (f"cd /d {_cmd(p['ordner'])} && set \"AMW_AGENT={p['kennung']}\" && set \"AMW_PROJEKT={p['projekt']}\" && "
                + " ".join(_cmd(x) for x in [claude_befehl(), *teile(fortsetzen)]))

    aus["neue_sitzung"] = neue
    aus["befehle"] = {"powershell": {"fortsetzen": ps(True) if fort else None, "neu": ps(False)},
                      "cmd": {"fortsetzen": cmd(True) if fort else None, "neu": cmd(False)}}
    return aus


def _shell():
    return shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"


def letzte_sitzung(con, pid, kennung):
    r = con.execute("SELECT s.claude_sitzung FROM sitzung s JOIN agent a ON a.id = s.agent_id WHERE a.projekt_id = ?"
                    " AND a.kennung = ? AND s.claude_sitzung IS NOT NULL ORDER BY s.id DESC LIMIT 1", (pid, kennung)).fetchone()
    return r["claude_sitzung"] if r else None


def claude_projektordner(pfad):
    """Name des Ordners, unter dem Claude Code Sitzungen und Notizen eines Arbeitsordners ablegt (~/.claude/projects/<name>):
    jedes Zeichen außer Buchstaben und Ziffern wird „-“ (F:\\amw → F--amw)."""
    return re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(pfad)).casefold()


def fortsetzbar(con, pid, kennung, ordner):
    """A1881/D1301: (Sitzungs-ID zum Fortsetzen oder None, Grund oder None). Fortgesetzt wird nur eine Sitzung, die im selben
    Claude-Projektordner liegt wie der Profil-Ordner – sonst lüde sie die Notizen eines anderen Ordners (F:\\amw ↔ amw-dev2).
    Ohne bekannten Arbeitsordner (alte Zeilen) wie bisher."""
    r = con.execute("SELECT s.claude_sitzung, s.arbeitsordner FROM sitzung s JOIN agent a ON a.id = s.agent_id WHERE a.projekt_id = ?"
                    " AND a.kennung = ? AND s.claude_sitzung IS NOT NULL ORDER BY s.id DESC LIMIT 1", (pid, kennung)).fetchone()
    if not r:
        return None, None
    if r["arbeitsordner"] and claude_projektordner(r["arbeitsordner"]) != claude_projektordner(ordner):
        return None, f"die letzte Sitzung lief in {r['arbeitsordner']}, nicht in {ordner}"
    return r["claude_sitzung"], None


def _claude_einstellungen():
    return os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude"), "settings.json")


def amw_hooks(ordner):
    """Befehle der SessionStart-Hooks mit amw-hook in <ordner>/.claude/settings(.local).json und in den Claude-Einstellungen
    des Benutzers."""
    aus = []
    for datei in (os.path.join(ordner, ".claude", "settings.local.json"), os.path.join(ordner, ".claude", "settings.json"),
                  _claude_einstellungen()):
        try:
            with open(datei, encoding="utf-8") as f:
                eintraege = (json.load(f).get("hooks") or {}).get("SessionStart") or []
        except (OSError, ValueError, AttributeError):
            continue
        aus += [str(h.get("command")) for e in eintraege if isinstance(e, dict) for h in e.get("hooks") or []
                if isinstance(h, dict) and "amw-hook" in str(h.get("command") or "")]
    return aus


def _live_hook():
    from . import einrichtung                         # der AMW-Ordner des laufenden Codes (wie amw einrichten ihn einträgt)
    return os.path.join(einrichtung.WURZEL, "amw-hook.py").replace("\\", "/").casefold()


def amw_hook_da(ordner):
    """Meldet sich eine Sitzung in diesem Ordner bei der AMW an? Ja, wenn ein SessionStart-Hook auf die amw-hook.py des
    AMW-Ordners zeigt (P289 a: ein Hook aus einem Entwicklungsbaum wiese der Live-Schutz beim Anmelden ab)."""
    return any(_live_hook() in b.replace("\\", "/").casefold() for b in amw_hooks(ordner))


def laeuft(con, pid, kennung):
    """Hat der Agent eine lebende Claude-Sitzung (Prozess der angemeldeten Sitzung)?"""
    from . import hook
    r = con.execute("SELECT s.claude_pid, s.claude_sitzung, s.schluessel_datei FROM sitzung s JOIN agent a ON a.id = s.agent_id"
                    " WHERE a.projekt_id = ? AND a.kennung = ? AND s.zustand = 'aktiv' ORDER BY s.id DESC LIMIT 1",
                    (pid, kennung)).fetchone()
    if not r:
        return False
    if r["claude_pid"]:
        return lebt(r["claude_pid"])
    if r["schluessel_datei"]:
        return hook.prozess_der_sitzung(r["claude_sitzung"], r["schluessel_datei"]) is not None
    return True                                       # Brücken-Sitzung: gilt als laufend


def zwilling(con, pid, p):
    """A1865 (B2897): würde ein Start hier einen Zwilling erzeugen? Grund in Worten oder None.
    - Der Ordner trägt in seinen Claude-Einstellungen (.claude/settings*.json, env) einen anderen Agenten oder ein anderes
      Projekt fest ein – dann meldete sich die neue Sitzung als dieser an.
    - Im Ordner läuft gerade ein Agent eines anderen Projekts (ein gemeinsamer Ordner im selben Projekt, z. B. zwei Agenten in
      einem Spielordner, bleibt erlaubt – sie unterscheidet AMW_AGENT)."""
    for name in ("settings.json", "settings.local.json"):
        try:
            with open(os.path.join(p["ordner"], ".claude", name), encoding="utf-8") as f:
                env = json.load(f).get("env") or {}
        except (OSError, ValueError, AttributeError):
            continue
        ag, pr = str(env.get("AMW_AGENT") or ""), str(env.get("AMW_PROJEKT") or "")
        if ag and ag.casefold() != p["kennung"].casefold():
            return f"der Ordner {p['ordner']} meldet jede Sitzung als {ag} an (.claude/{name}, env AMW_AGENT) – das wäre ein Zwilling"
        if pr and pr.casefold() != (p["projekt"] or "").casefold():
            return f"der Ordner {p['ordner']} gehört zu Projekt {pr} (.claude/{name}, env AMW_PROJEKT) – die Sitzung landete dort"
    ordner = os.path.normcase(os.path.abspath(p["ordner"]))
    for r in con.execute("SELECT a.kennung, s.arbeitsordner, s.claude_pid, pr.name FROM sitzung s JOIN agent a ON a.id = s.agent_id"
                         " JOIN projekt pr ON pr.id = a.projekt_id WHERE s.zustand = 'aktiv' AND a.projekt_id != ?"
                         " AND s.arbeitsordner IS NOT NULL", (pid,)).fetchall():
        if os.path.normcase(os.path.abspath(r["arbeitsordner"])) == ordner and (not r["claude_pid"] or lebt(r["claude_pid"])):
            return f"im Ordner {p['ordner']} arbeitet gerade {r['kennung']} aus Projekt {r['name']} – fremder Live-Ordner"
    return None


def starten(con, pid, kennung, neu=False, ausfuehren=None):
    """Startet den Agenten im neuen Terminal-Tab. neu=True: frische Sitzung statt Fortsetzen. Rückgabe: Beschreibung.
    Wer startet, prüft der Aufrufer: nur der Mensch am PC (Workbench mit Rückfrage, Befehlszeile --von Entwickler) und die
    Absturz-Überwachung bei eingeschaltetem Auto-Neustart – nie online, nie ein Agent (A1865, B2897)."""
    p = profil(con, pid, kennung)
    weise = kern.agent_zeile(con, pid, kennung)["arbeitsweise"] or "terminal"
    if weise != "terminal":                        # Chat und Desktop-App startet der Mensch selbst
        raise kern.AmwFehler(f"{kennung} arbeitet {'als Chat' if weise == 'chat' else 'in der Desktop-App'} – die AMW startet nur "
                             f"Agenten im Terminal (amw agent profil {kennung} --arbeitsweise terminal)")
    if not p["ordner"]:
        raise kern.AmwFehler(f"{kennung}: kein Ordner im Profil – amw agent profil {kennung} --ordner <Pfad>")
    if not os.path.isdir(p["ordner"]):
        raise kern.AmwFehler(f"{kennung}: Ordner {p['ordner']} gibt es nicht – amw agent profil {kennung} --ordner <Pfad>")
    if laeuft(con, pid, kennung):
        raise kern.AmwFehler(f"{kennung} läuft schon")
    grund = zwilling(con, pid, p)
    if grund:
        raise kern.AmwFehler(f"{kennung} nicht gestartet: {grund}")
    if not amw_hook_da(p["ordner"]):                  # A1881 (D1301): sonst meldet sich die Sitzung nie an
        from . import einrichtung
        einrichten = f"{kern.BEFEHL} einrichten agenten-ordner {p['ordner']} --projekt {p['projekt']}"
        if amw_hooks(p["ordner"]):                    # vorhandene AMW-Einträge ergänzt einrichten nicht – erst heraus
            was = f"der AMW-Hook im Ordner {p['ordner']} zeigt nicht auf den AMW-Ordner {einrichtung.WURZEL}"
            wie = f"Neu einrichten: {kern.BEFEHL} einrichten agenten-ordner {p['ordner']} --entfernen, danach {einrichten}"
        else:
            was, wie = f"im Ordner {p['ordner']} fehlt der AMW-Hook", f"Einrichten: {einrichten}"
        raise kern.AmwFehler(f"{kennung} nicht gestartet: {was} – die Sitzung meldete sich nie an (keine Weckrufe, Anzeige"
                             f" „beendet“). {wie}")
    fort, anders = (None, None) if neu else fortsetzbar(con, pid, kennung, p["ordner"])
    neue = str(uuid.uuid4())                          # neu – oder Rückfall, wenn das Fortsetzen scheitert
    zeile = befehl(p, fort, neue)
    b64 = base64.b64encode(zeile.encode("utf-16-le")).decode()
    shell = _shell()
    wt_exe = shutil.which("wt")
    titel = kennung                                   # mehrere Projekte: CC1 gibt es vielleicht in jedem – Tab mit Projekt
    if con.execute("SELECT count(*) FROM projekt").fetchone()[0] > 1:
        titel = f"{kennung} · {p['projekt']}"
    if wt_exe:
        args = [wt_exe, "-w", "amw", "new-tab", "--title", titel, "--suppressApplicationTitle", "-d", p["ordner"], shell, "-NoExit", "-EncodedCommand", b64]
        flags = 0
    else:
        args = [shell, "-NoExit", "-EncodedCommand", b64]
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    (ausfuehren or (lambda a, f, o: subprocess.Popen(a, cwd=o, creationflags=f, close_fds=True)))(args, flags, p["ordner"])
    with db.schreiben(con):                           # A1881: meldet sie sich nicht binnen ANMELDE_FRIST_S → anmeldung_pruefen
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=START_EREIGNIS,
                     text=f"{kennung}|{p['ordner']}")
    return f"{kennung} " + (f"setzt Sitzung {fort[:8]} fort" if fort else f"startet neu (Sitzung {neue[:8]})") \
        + (" im Windows Terminal" if wt_exe else " in einem Konsolenfenster") \
        + (f" – nicht fortgesetzt: {anders} (sonst lüde sie fremde Notizen)" if anders else "")


# --- Anmeldung nach dem Start (A1881, D1301) ------------------------------------------------------
START_EREIGNIS = "agent_start"
ANMELDE_FRIST_S = 180          # so lange darf ein gestarteter Agent brauchen, bis sich seine Sitzung anmeldet
ANMELDE_FENSTER_S = 1800       # ältere Starts werden nicht mehr nachgemeldet (z. B. nach einer Pause des Dienstes)


def anmeldung_pruefen(con, jetzt=None):
    """Runde des Dienstes: hat die AMW einen Agenten gestartet und hat sich nach ANMELDE_FRIST_S keine Sitzung angemeldet,
    einmal eine Meldung an Lead und Mensch – statt still „beendet“. Hook-Fehler beim Anmelden seit dem Start stehen dabei.
    Rückgabe: Ereignisse fürs Log."""
    from . import hook
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    bis = (jetzt - datetime.timedelta(seconds=ANMELDE_FRIST_S)).strftime(fmt)
    ab = (jetzt - datetime.timedelta(seconds=ANMELDE_FENSTER_S)).strftime(fmt)
    aus = []
    for e in con.execute("SELECT id, projekt_id, zeit_utc, text FROM plan_ereignis WHERE art = ? AND zeit_utc <= ? AND zeit_utc >= ?"
                         " AND NOT EXISTS (SELECT 1 FROM plan_ereignis x WHERE x.art = 'agent_stumm' AND x.text = CAST(plan_ereignis.id AS TEXT))"
                         " ORDER BY id", (START_EREIGNIS, bis, ab)).fetchall():
        kennung, _, ordner = (e["text"] or "").partition("|")
        a = con.execute("SELECT id FROM agent WHERE projekt_id = ? AND kennung = ?", (e["projekt_id"], kennung)).fetchone()
        if not a or con.execute("SELECT 1 FROM sitzung WHERE agent_id = ? AND gestartet_utc >= ?", (a["id"], e["zeit_utc"])).fetchone():
            continue
        fehler = hook.hook_fehler_seit(e["zeit_utc"], "SessionStart")
        ortszeit = datetime.datetime.strptime(e["zeit_utc"], fmt).replace(tzinfo=datetime.timezone.utc).astimezone().strftime("%H:%M")
        kurz = f"{kennung} gestartet, meldet sich nicht an"
        text = (f"Die AMW hat {kennung} um {ortszeit} gestartet (Ordner {ordner}). Nach {ANMELDE_FRIST_S // 60} Minuten hat sich keine"
                " Sitzung angemeldet – ohne Anmeldung bekommt der Agent keine Weckrufe und erscheint als beendet. Bitte das Fenster"
                f" ansehen. Häufige Gründe: der Start ist gescheitert, oder der Hook im Ordner fehlt bzw. scheitert"
                f" ({kern.BEFEHL} einrichten agenten-ordner {ordner} --projekt <Name>).")
        if fehler:
            text += " Hook-Fehler seit dem Start: " + " · ".join(fehler[-3:])
        lead = kern.lead(con, e["projekt_id"])
        with db.schreiben(con):
            db.einfuegen(con, "plan_ereignis", projekt_id=e["projekt_id"], zeit_utc=db.jetzt(), von="AMW", art="agent_stumm",
                         text=str(e["id"]))
            kern._posten(con, e["projekt_id"], "AMW", ",".join(dict.fromkeys(x for x in (lead, kern.ENTWICKLER) if x and x != kennung)),
                         "meldung", kurz, text)
        aus.append(kurz)
    return aus


def _sitzung_mit_prozess(con, pid, kennung, auch_ruhend=False):
    """(Sitzungs-Zeile, PID des lebenden Claude-Prozesses) der jüngsten Sitzung mit eigenem Prozess – oder (Zeile, None).
    auch_ruhend: auch eine abgemeldete Sitzung (ihr Fenster ist noch offen)."""
    r = con.execute("SELECT s.id, s.zustand, s.claude_pid, s.claude_sitzung, s.schluessel_datei FROM sitzung s JOIN agent a ON a.id = s.agent_id"
                    " WHERE a.projekt_id = ? AND a.kennung = ? AND s.zustand IN ('aktiv'" + (", 'ruht'" if auch_ruhend else "") + ")"
                    " AND s.schluessel_datei IS NOT NULL ORDER BY s.id DESC LIMIT 1", (pid, kennung)).fetchone()
    cpid = r["claude_pid"] if r else None
    if not cpid and r:
        from . import hook                            # nur der Prozess genau dieser Sitzung – nie der einer anderen
        ich = hook.prozess_der_sitzung(r["claude_sitzung"], r["schluessel_datei"])
        cpid = ich and ich["pid"]
    return r, (cpid if cpid and lebt(cpid) else None)


def beenden(con, pid, kennung, beenden_mit=None, auch_ruhend=False):
    """Beendet den Claude-Prozess der laufenden Sitzung (das Fenster bleibt offen) und vermerkt es als bewusst."""
    r, cpid = _sitzung_mit_prozess(con, pid, kennung, auch_ruhend)
    if not r or not cpid:
        raise kern.AmwFehler(f"{kennung} läuft nicht")
    with db.schreiben(con):
        con.execute("UPDATE sitzung SET ereignis = 'beendet', ereignis_text = 'amw', ereignis_utc = ? WHERE id = ?",
                    (db.jetzt(), r["id"]))
    (beenden_mit or (lambda p: subprocess.run(["taskkill", "/PID", str(p), "/T", "/F"], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))))(cpid)
    if not lebt(cpid):                                # A1965: die Sitzung ist zu Ende – Kachel, Menü und agent liste sagen es sofort
        with db.schreiben(con):
            con.execute("UPDATE sitzung SET zustand = 'beendet', beendet_utc = ? WHERE id = ? AND zustand IN ('aktiv', 'ruht')",
                        (db.jetzt(), r["id"]))
    return f"{kennung}: Claude-Prozess {cpid} beendet (Fenster bleibt offen)"


# --- Geordnetes Ende („Sichern & beenden“, z. B. vor einem Update) ----------------------------------
# Ohne eigenes Feld: ein Halt für genau diesen Agenten mit Frist (sperre.bis_utc) und festem Textanfang. Der Agent bekommt
# ein STOPP mit der Bitte, zu sichern und sich abzumelden; der Wächter beendet die Sitzung, sobald sie abgemeldet ist –
# spätestens zur Frist – und hebt den Halt auf. Nur der Mensch am PC stößt das an (aktionen: /api/agent/ende).

ENDE_TEXT = "Sichern und beenden"
ENDE_FRIST_MIN = 5


def ende_offen(con, pid=None):
    """Offene Aufträge „Sichern & beenden“: [{id, projekt_id, kennung, bis_utc}]."""
    sql = ("SELECT id, projekt_id, gilt_fuer AS kennung, bis_utc FROM sperre WHERE art = 'halt' AND bis_utc IS NOT NULL"
           " AND aufgehoben_utc IS NULL AND text LIKE ?")
    par = [ENDE_TEXT + "%"]
    if pid is not None:
        sql += " AND projekt_id = ?"
        par.append(pid)
    return [dict(r) for r in con.execute(sql + " ORDER BY id", par)]


def ende_frist(con, pid):
    """Frist für „Sichern & beenden“ in Minuten: Projekt-Einstellung ende_frist_min, sonst ENDE_FRIST_MIN."""
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    try:
        return int(json.loads(r[0] or "{}").get("ende_frist_min", ENDE_FRIST_MIN)) if r else ENDE_FRIST_MIN
    except (TypeError, ValueError):
        return ENDE_FRIST_MIN


def ende_anfordern(con, pid, kennungen=None, frist_min=None, jetzt=None):
    """Bittet laufende Agenten, zu sichern und sich abzumelden; nach `frist_min` (ohne Angabe: Einstellung des Projekts,
    Vorgabe 5) beendet der Wächter die Sitzung. kennungen=None: alle, die gerade mit eigenem Prozess laufen.
    Rückgabe: {"agenten": [...], "bis_utc": …}."""
    frist_min = ende_frist(con, pid) if frist_min is None else frist_min
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    bis = (jetzt + datetime.timedelta(minutes=max(1, min(60, int(frist_min))))).strftime("%Y-%m-%dT%H:%M:%SZ")
    schon = {e["kennung"] for e in ende_offen(con, pid)}
    alle = [r["kennung"] for r in con.execute("SELECT kennung FROM agent WHERE projekt_id = ? ORDER BY id", (pid,))]
    for k in kennungen or []:
        if k not in alle:
            raise kern.AmwFehler(f"Agent {k} gibt es nicht")
    laufend = [k for k in (kennungen or alle) if k not in schon and _sitzung_mit_prozess(con, pid, k, auch_ruhend=True)[1]]
    if kennungen and not laufend:
        raise kern.AmwFehler(f"{', '.join(kennungen)} läuft nicht" if not set(kennungen) & schon
                             else f"{', '.join(kennungen)}: Sichern & beenden läuft schon")
    ortszeit = datetime.datetime.strptime(bis, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).astimezone().strftime("%H:%M")
    with db.schreiben(con):
        for k in laufend:
            sid = db.einfuegen(con, "sperre", projekt_id=pid, art="halt", gilt_fuer=k, von=kern.ENTWICKLER,
                               text=f"{ENDE_TEXT} bis {ortszeit}", seit_utc=db.jetzt(), bis_utc=bis)
            kern._posten(con, pid, kern.ENTWICKLER, k, "stopp", f"SICHERN UND BEENDEN bis {ortszeit}",
                         f"Auftrag #{sid} vom Entwickler (z. B. für ein Update): 1. Laufenden Schritt sauber abschließen oder den "
                         f"Zwischenstand festhalten (Tätigkeit, Notiz; nichts Halbfertiges veröffentlichen). 2. Nichts Neues "
                         f"anfangen. 3. `amw abmelden` – dann beendet die AMW deine Sitzung sofort, sonst um {ortszeit}. "
                         f"Nach dem Neustart setzt du mit `amw lesen` fort.")
    return {"agenten": laufend, "bis_utc": bis if laufend else None}


def ende_pruefen(con, jetzt=None, beenden_mit=None):
    """Runde des Wächters: abgemeldete oder überfällige Sitzungen mit offenem Auftrag beenden, Halt aufheben.
    Rückgabe: Ereignisse fürs Log."""
    stempel = (jetzt or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    aus = []
    for e in ende_offen(con):
        r, cpid = _sitzung_mit_prozess(con, e["projekt_id"], e["kennung"], auch_ruhend=True)
        if cpid and r["zustand"] != "ruht" and stempel < e["bis_utc"]:
            continue                                   # arbeitet noch und hat noch Zeit
        if cpid:
            try:
                beenden(con, e["projekt_id"], e["kennung"], beenden_mit=beenden_mit, auch_ruhend=True)
                aus.append(f"{e['kennung']} beendet ({'abgemeldet' if r['zustand'] == 'ruht' else 'Frist abgelaufen'})")
            except (kern.AmwFehler, OSError) as x:
                aus.append(f"{e['kennung']}: Beenden fehlgeschlagen ({x})")
                continue
        else:
            aus.append(f"{e['kennung']} läuft nicht mehr – Auftrag erledigt")
        with db.schreiben(con):
            con.execute("UPDATE sperre SET aufgehoben_utc = ? WHERE id = ?", (db.jetzt(), e["id"]))
    return aus


def fehlende(con, pid):
    """Agenten, die laufen sollen, einen Arbeitsordner haben (kein Chat) und weder laufen noch abgemeldet warten."""
    aus = []
    for a in con.execute("SELECT kennung, ordner FROM agent WHERE projekt_id = ? AND soll = 'an'"
                         " AND coalesce(arbeitsweise, 'terminal') = 'terminal' ORDER BY id", (pid,)):
        if a["ordner"] and not _sitzung_mit_prozess(con, pid, a["kennung"], auch_ruhend=True)[1] and not laeuft(con, pid, a["kennung"]):
            aus.append(a["kennung"])
    return aus


def fehlende_starten(con_fabrik, pid, kennungen, abstand_s=None, starte=None, warte=time.sleep):
    """Startet die Agenten nacheinander mit Abstand (wie das Startskript). con_fabrik: öffnet eine eigene Verbindung
    (läuft in einem eigenen Thread). Rückgabe: Texte je Agent."""
    abstand_s = STARTSKRIPT_ABSTAND_S if abstand_s is None else abstand_s
    con, aus = con_fabrik(), []
    try:
        for i, k in enumerate(kennungen):
            if i:
                warte(abstand_s)
            try:
                aus.append((starte or starten)(con, pid, k))
            except (kern.AmwFehler, OSError) as e:
                aus.append(f"{k}: {e}")
    finally:
        con.close()
    return aus


# --- Auto-Neustart -------------------------------------------------------------------------------

class Neustarter:
    """Im Wächter: abgestürzte Agenten (Soll an, Auto-Neustart an) fortsetzen – höchstens NEUSTARTS_JE_STUNDE je Agent."""

    def __init__(self, con, starter=None):
        self.con, self.versuche, self.starter = con, {}, starter or starten

    def kandidaten(self, pid, jetzt=None):
        jetzt = jetzt or time.time()
        aus = []
        for a in self.con.execute("SELECT id, kennung FROM agent WHERE projekt_id = ? AND soll = 'an' AND neustart_auto = 1"
                                  " AND coalesce(arbeitsweise, 'terminal') = 'terminal'",
                                  (pid,)).fetchall():
            if self.con.execute("SELECT 1 FROM sitzung WHERE agent_id = ? AND zustand = 'aktiv'", (a["id"],)).fetchone():
                continue
            s = self.con.execute("SELECT * FROM sitzung WHERE agent_id = ? ORDER BY id DESC LIMIT 1", (a["id"],)).fetchone()
            if not s or not s["beendet_utc"] or not s["fenster_pid"]:
                continue                                  # ohne bekanntes Fenster kein Urteil → nie automatisch
            if jetzt - db_sek(s["beendet_utc"]) > NEUSTART_FENSTER_S:
                continue
            if s["ereignis"] == "beendet" and (s["ereignis_text"] or "") in BEWUSST:
                continue
            if not lebt(s["fenster_pid"]) or lebt(s["claude_pid"]):
                continue                                  # Fenster zu = bewusst; Claude lebt = kein Absturz
            aus.append((a["kennung"], s))
        return aus

    def runde(self):
        ereignisse = []
        for p in self.con.execute("SELECT id FROM projekt").fetchall():
            for kennung, s in self.kandidaten(p["id"]):
                jetzt = time.time()
                liste = [x for x in self.versuche.get(kennung, []) if jetzt - x < 3600]
                if len(liste) >= NEUSTARTS_JE_STUNDE:
                    continue
                self.versuche[kennung] = liste + [jetzt]
                try:
                    text = self.starter(self.con, p["id"], kennung)
                    ergebnis = f"{kennung} war abgestürzt – automatisch fortgesetzt ({len(liste) + 1}. in dieser Stunde)"
                except (kern.AmwFehler, OSError) as e:
                    text, ergebnis = str(e), f"{kennung} abgestürzt – Neustart fehlgeschlagen: {e}"
                leads = ",".join(r["kennung"] for r in self.con.execute(
                    "SELECT kennung FROM agent WHERE projekt_id = ? AND rolle = 'lead'", (p["id"],)))
                if leads:
                    kern.posten(self.con, p["id"], "AMW", leads, "meldung", ergebnis, text)
                ereignisse.append(ergebnis)
        return ereignisse


def db_sek(utc):
    import calendar
    return calendar.timegm(time.strptime(utc, "%Y-%m-%dT%H:%M:%SZ"))


# --- Startskript ---------------------------------------------------------------------------------

STARTSKRIPT_ABSTAND_S = 20       # alle auf einmal legten den PC lahm (Neustart 03.11.: 8 Sitzungen, > 120 s je Befehl)


NEUSTART_SATZ = "Neustart des PCs. Lies deinen Stand in der AMW (Nachrichten, Notizen) und mach mit deiner Aufgabe weiter."


def _bat(text):
    """Text in einer Zeile der .bat: für cmd (% verdoppeln, keine doppelten Anführungszeichen im -Command) und für wt
    (; trennt dort Befehle, deshalb \\;)."""
    return str(text).replace("%", "%%").replace('"', "'").replace(";", "\\;")


def startskript(con, pid, kennungen=None, alle=False, abstand_s=STARTSKRIPT_ABSTAND_S):
    """Lesbare .bat (Doppelklick), die die Agenten mit Soll „an“ (alle=True: jeder mit Profil-Ordner; oder die genannten)
    in Tabs eines Fensters je Projekt startet – alles im Klartext, aus den Profilen. Je Agent zuerst die letzte Sitzung
    fortsetzen (--resume); gibt es sie nicht (mehr), beginnt eine neue mit derselben ID und dem Startsatz. Ein Agent ohne
    Profil-Ordner (z. B. ein Lead, der als Chat arbeitet) startet hier nie."""
    projekt, uid = con.execute("SELECT name, uid FROM projekt WHERE id = ?", (pid,)).fetchone()   # uid: feste ID ohne frühere Sitzung
    fenster = db.kurzname(projekt, pid) or "amw"
    shell = os.path.splitext(os.path.basename(_shell()))[0].lower()
    zeilen = ["@echo off", "chcp 65001 >nul",
              f"rem {projekt}: Agenten starten – erzeugt von der AMW (amw agent startskript). Ändern im Profil der Agenten",
              "rem (Workbench › Kachel › Profil), nicht hier. Je Agent: letzte Sitzung fortsetzen, gibt es keine: neu mit",
              f"rem derselben ID und dem Startsatz. Ein Fenster „{fenster}“, ein Tab je Agent, {abstand_s} s Pause dazwischen.",
              "where wt >nul 2>nul || (echo Windows Terminal (wt) fehlt – Agenten in der Workbench einzeln starten. & pause & exit /b 1)", ""]
    n = 0
    for a in con.execute("SELECT kennung FROM agent WHERE projekt_id = ? AND ordner IS NOT NULL AND ordner != ''"
                         " AND coalesce(arbeitsweise, 'terminal') = 'terminal'"
                         + ("" if kennungen or alle else " AND soll = 'an'") + " ORDER BY id", (pid,)).fetchall():
        if kennungen and a["kennung"] not in kennungen:
            continue
        p = profil(con, pid, a["kennung"])
        fort, anders = fortsetzbar(con, pid, a["kennung"], p["ordner"])   # A1881: nur im selben Claude-Projektordner
        # P289 (b): darf nicht fortgesetzt werden, eine frische ID nur mit --session-id – --resume fände Sitzungen auch in
        # anderen Claude-Projektordnern, also vielleicht eine frühere mit der festen ID
        sid = fort or (str(uuid.uuid4()) if anders else str(uuid.uuid5(uuid.NAMESPACE_URL, f"amw:{uid}:{a['kennung']}")))
        neu = _aufruf(["--session-id", sid] + _optionen(p) + ([p["startsatz"]] if p["startsatz"] else []), lesbar=True)
        if anders:
            ps = f"$env:AMW_AGENT={_ps(p['kennung'])}; $env:AMW_PROJEKT={_ps(projekt)}; {neu}; {MAUS_AUS}"
        else:
            weiter = _aufruf(["--resume", sid] + _optionen(p) + [NEUSTART_SATZ], lesbar=True)
            ps = (f"$env:AMW_AGENT={_ps(p['kennung'])}; $env:AMW_PROJEKT={_ps(projekt)}; {weiter}; "
                  f"if ($LASTEXITCODE -ne 0) {{ {neu} }}; {MAUS_AUS}")
        ordner = p["ordner"].rstrip("\\") or p["ordner"]
        if ordner.endswith(":"):
            ordner += "\\."                                   # "F:\" würde das Anführungszeichen schützen
        if n and abstand_s:
            zeilen.append(f"timeout /t {int(abstand_s)} /nobreak >nul")
        zeilen += [f"rem --- {a['kennung']} ---  Sitzung {sid}",
                   f'wt -w {fenster} new-tab --title {a["kennung"]} --suppressApplicationTitle -d "{_bat(ordner)}" {shell} -NoExit'
                   f' -Command "{_bat(ps)}"', ""]
        n += 1
    if not n:
        raise kern.AmwFehler("kein Agent mit Profil-Ordner – amw agent profil <kennung> --ordner <Pfad>")
    zeilen.append(f"echo {n} Agent(en) gestartet.")
    return "\r\n".join(zeilen) + "\r\n"


# --- Startvorschläge (A1867, D1258 §6b) --------------------------------------------------------------------------------------
# Die AMW schlägt einen Start vor; der Mensch bestätigt am PC (W2337 Pkt 7) – sie startet nie von selbst und nie online.
VORSCHLAG_RUHE_H = 12          # „Nicht jetzt“: so lange kein neuer Vorschlag für diesen Agenten


def startvorschlaege(con, pid):
    """[{"kennung", "grund", "text", "aufgabe"}] – Agenten im Terminal mit Startprofil, die nicht laufen, aber dran wären:
    Paket der Art sitzung ist dran (grund „sitzung“), letzte Sitzung endete ohne bewusstes Ende und es gibt Arbeit
    („absturz“), oder es gibt Arbeit in der Liste („arbeit“). Dran = in der Liste ohne offenen Wartegrund; ein p-Paket nur,
    wenn es auf interaktiv wartet (nie im Entwurf). Ohne „Nicht jetzt“ der letzten VORSCHLAG_RUHE_H Stunden."""
    from . import arbeitsliste
    grenze = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=VORSCHLAG_RUHE_H)).strftime("%Y-%m-%dT%H:%M:%SZ")
    abgelehnt = {r[0] for r in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = 'startvorschlag_nein'"
                                           " AND zeit_utc >= ?", (pid, grenze))}
    aus = []
    for a in con.execute("SELECT kennung, ordner FROM agent WHERE projekt_id = ? AND soll != 'aus' AND entfernt_utc IS NULL"
                         " AND coalesce(arbeitsweise, 'terminal') = 'terminal' AND coalesce(ordner, '') != '' ORDER BY id", (pid,)).fetchall():
        k = a["kennung"]
        if k in abgelehnt or laeuft(con, pid, k) or _sitzung_mit_prozess(con, pid, k, auch_ruhend=True)[1]:
            continue
        bereit = [x for x in arbeitsliste.liste(con, pid, k) if x["status"] == "laeuft" or not x["gruende"]]
        art = _paket_arten(con, [x["id"] for x in bereit])
        # A1878: ein p-Paket ist nur dann Arbeit für den interaktiven Agenten, wenn es auf ihn wartet – im Entwurf ist es
        # noch nicht freigegeben, sonst führt es der Arbeiter der AMW aus. Art sitzung hat keinen Zustand: „dran“ heißt wie
        # bei jeder Aufgabe in der Liste (nicht geparkt, kein offener Wartegrund).
        bereit = [x for x in bereit if art.get(x["id"], ("agent", None))[0] != "p" or art[x["id"]][1] == "wartet_interaktiv"]
        if not bereit:
            continue
        paket = next((x for x in bereit if art.get(x["id"], ("agent", None))[0] == "sitzung"), None)
        if paket:
            aus.append({"kennung": k, "grund": "sitzung", "aufgabe": paket["id"], "text": paket["titel"]})
            continue
        s = con.execute("SELECT s.zustand, s.ereignis, s.ereignis_text FROM sitzung s JOIN agent g ON g.id = s.agent_id"
                        " WHERE g.projekt_id = ? AND g.kennung = ? ORDER BY s.id DESC LIMIT 1", (pid, k)).fetchone()
        absturz = bool(s and s["zustand"] in ("beendet", "tot")                  # wie Ueberwachung.kandidaten: bewusst =
                       and not (s["ereignis"] == "beendet" and (s["ereignis_text"] or "") in BEWUSST))   # „beendet“ + BEWUSST
        aus.append({"kennung": k, "grund": "absturz" if absturz else "arbeit", "aufgabe": bereit[0]["id"], "text": bereit[0]["titel"]})
    return aus


def _paket_arten(con, ids):
    """{aufgabe_id: (art, zustand)} – nur Aufgaben mit Paket-Zeile (keine Zeile = Art agent)."""
    if not ids:
        return {}
    try:
        return {r[0]: (r[1], r[2]) for r in con.execute(
            f"SELECT aufgabe_id, art, zustand FROM paket WHERE aufgabe_id IN ({','.join('?' * len(ids))})", ids)}
    except Exception:                                      # ältere Datenbank ohne Tabelle paket
        return {}


def startvorschlag_ablehnen(con, pid, kennung):
    """„Nicht jetzt“ des Menschen – steht im Planungs-Protokoll; für VORSCHLAG_RUHE_H Stunden kein neuer Vorschlag."""
    kern.agent_zeile(con, pid, kennung)
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=kern.ENTWICKLER, art="startvorschlag_nein", text=kennung)
    return {"kennung": kennung}
