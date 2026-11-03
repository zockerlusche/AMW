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
import json
import os
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
    return {"kennung": a["kennung"], "ordner": a["ordner"], "zusatzordner": zusatz, "denkstufe": a["denkstufe"],
            "modell": a["modell"], "startsatz": a["startsatz"], "rechte": a["rechte"] or "vorgabe",
            "fernsteuerung": bool(a["fernsteuerung"]), "neustart_auto": bool(a["neustart_auto"])}


def profil_setzen(con, pid, von, kennung, **werte):
    """Nur Lead und Entwickler. Prüft Ordner, Denkstufe, Rechte; Zusatzordner als Liste."""
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Profile ändern nur Lead und Entwickler")
    kern.agent_zeile(con, pid, kennung)
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
                raise kern.AmwFehler(f"Denkstufe: {', '.join(DENKSTUFEN)}")
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
    return profil(con, pid, kennung)


# --- Befehl --------------------------------------------------------------------------------------

def _ps(s):
    return "'" + str(s).replace("'", "''") + "'"


def claude_befehl():
    from . import einstellungen
    return einstellungen.wert("claude_befehl") or "claude"


def befehl(p, fortsetzen_id=None, neue_id=None):
    """PowerShell-Befehlszeile für den Tab: Umgebung setzen, Claude mit Profil starten."""
    teile = [claude_befehl()]
    if fortsetzen_id:
        teile += ["--resume", fortsetzen_id]
    elif neue_id:
        teile += ["--session-id", neue_id]
    if p["fernsteuerung"]:
        teile += ["--remote-control", p["kennung"]]
    if p["denkstufe"]:
        teile += ["--effort", p["denkstufe"]]
    if p["modell"]:
        teile += ["--model", p["modell"]]
    for z in p["zusatzordner"]:
        teile += ["--add-dir", z]
    teile += RECHTE.get(p["rechte"], [])
    if not fortsetzen_id and p["startsatz"]:
        teile.append(p["startsatz"])
    erstes, rest = teile[0], teile[1:]
    aufruf = (f"& {_ps(erstes)} " if " " in erstes or "\\" in erstes else f"{erstes} ") + " ".join(_ps(x) for x in rest)
    return f"Set-Location {_ps(p['ordner'])}; $env:AMW_AGENT = {_ps(p['kennung'])}; {aufruf}"


def _shell():
    return shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"


def letzte_sitzung(con, pid, kennung):
    r = con.execute("SELECT s.claude_sitzung FROM sitzung s JOIN agent a ON a.id = s.agent_id WHERE a.projekt_id = ?"
                    " AND a.kennung = ? AND s.claude_sitzung IS NOT NULL ORDER BY s.id DESC LIMIT 1", (pid, kennung)).fetchone()
    return r["claude_sitzung"] if r else None


def laeuft(con, pid, kennung):
    """Hat der Agent eine lebende Claude-Sitzung (Prozess der angemeldeten Sitzung)?"""
    from . import hook
    r = con.execute("SELECT s.claude_pid, s.schluessel_datei FROM sitzung s JOIN agent a ON a.id = s.agent_id"
                    " WHERE a.projekt_id = ? AND a.kennung = ? AND s.zustand = 'aktiv' ORDER BY s.id DESC LIMIT 1",
                    (pid, kennung)).fetchone()
    if not r:
        return False
    if r["claude_pid"]:
        return lebt(r["claude_pid"])
    if r["schluessel_datei"]:
        try:
            with open(r["schluessel_datei"], encoding="utf-8") as f:
                return hook.claude_prozess(json.load(f).get("pipe")) is not None
        except (OSError, ValueError):
            return False
    return True                                       # Brücken-Sitzung: gilt als laufend


def starten(con, pid, kennung, neu=False, ausfuehren=None):
    """Startet den Agenten im neuen Terminal-Tab. neu=True: frische Sitzung statt Fortsetzen. Rückgabe: Beschreibung."""
    p = profil(con, pid, kennung)
    if not p["ordner"]:
        raise kern.AmwFehler(f"{kennung}: kein Ordner im Profil – amw agent profil {kennung} --ordner <Pfad>")
    if laeuft(con, pid, kennung):
        raise kern.AmwFehler(f"{kennung} läuft schon")
    fort = None if neu else letzte_sitzung(con, pid, kennung)
    neue = None if fort else str(uuid.uuid4())
    zeile = befehl(p, fort, neue)
    b64 = base64.b64encode(zeile.encode("utf-16-le")).decode()
    shell = _shell()
    wt_exe = shutil.which("wt")
    if wt_exe:
        args = [wt_exe, "-w", "amw", "new-tab", "--title", kennung, "--suppressApplicationTitle", "-d", p["ordner"], shell, "-NoExit", "-EncodedCommand", b64]
        flags = 0
    else:
        args = [shell, "-NoExit", "-EncodedCommand", b64]
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    (ausfuehren or (lambda a, f, o: subprocess.Popen(a, cwd=o, creationflags=f, close_fds=True)))(args, flags, p["ordner"])
    return f"{kennung} " + (f"setzt Sitzung {fort[:8]} fort" if fort else f"startet neu (Sitzung {neue[:8]})") \
        + (" im Windows Terminal" if wt_exe else " in einem Konsolenfenster")


def beenden(con, pid, kennung, beenden_mit=None):
    """Beendet den Claude-Prozess der laufenden Sitzung (das Fenster bleibt offen) und vermerkt es als bewusst."""
    r = con.execute("SELECT s.id, s.claude_pid FROM sitzung s JOIN agent a ON a.id = s.agent_id WHERE a.projekt_id = ?"
                    " AND a.kennung = ? AND s.zustand = 'aktiv' AND s.schluessel_datei IS NOT NULL ORDER BY s.id DESC LIMIT 1",
                    (pid, kennung)).fetchone()
    cpid = r["claude_pid"] if r else None
    if not cpid and r:
        from . import hook
        try:
            with open(con.execute("SELECT schluessel_datei FROM sitzung WHERE id = ?", (r["id"],)).fetchone()[0], encoding="utf-8") as f:
                ich = hook.claude_prozess(json.load(f).get("pipe"))
            cpid = ich and ich["pid"]
        except (OSError, ValueError, TypeError):
            cpid = None
    if not r or not cpid or not lebt(cpid):
        raise kern.AmwFehler(f"{kennung} läuft nicht")
    with db.schreiben(con):
        con.execute("UPDATE sitzung SET ereignis = 'beendet', ereignis_text = 'amw', ereignis_utc = ? WHERE id = ?",
                    (db.jetzt(), r["id"]))
    (beenden_mit or (lambda p: subprocess.run(["taskkill", "/PID", str(p), "/T", "/F"], capture_output=True)))(cpid)
    return f"{kennung}: Claude-Prozess {cpid} beendet (Fenster bleibt offen)"


# --- Auto-Neustart -------------------------------------------------------------------------------

class Neustarter:
    """Im Wächter: abgestürzte Agenten (Soll an, Auto-Neustart an) fortsetzen – höchstens NEUSTARTS_JE_STUNDE je Agent."""

    def __init__(self, con, starter=None):
        self.con, self.versuche, self.starter = con, {}, starter or starten

    def kandidaten(self, pid, jetzt=None):
        jetzt = jetzt or time.time()
        aus = []
        for a in self.con.execute("SELECT id, kennung FROM agent WHERE projekt_id = ? AND soll = 'an' AND neustart_auto = 1",
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

def startskript(con, pid, kennungen=None):
    """PowerShell-Skript, das alle Agenten mit Soll „an“ (oder die genannten) in Tabs startet – aus den Profilen."""
    zeilen = ["# Erzeugt von AMW (amw agent startskript) – Änderungen im Profil der Agenten, nicht hier.",
              "# Setzt jeweils die letzte Sitzung des Agenten fort; ohne frühere Sitzung beginnt eine neue.", ""]
    tabs = []
    for a in con.execute("SELECT kennung FROM agent WHERE projekt_id = ? AND ordner IS NOT NULL AND ordner != ''"
                         + ("" if kennungen else " AND soll = 'an'") + " ORDER BY id", (pid,)).fetchall():
        if kennungen and a["kennung"] not in kennungen:
            continue
        p = profil(con, pid, a["kennung"])
        fort = letzte_sitzung(con, pid, a["kennung"])
        b64 = base64.b64encode(befehl(p, fort, None if fort else str(uuid.uuid4())).encode("utf-16-le")).decode()
        ordner = p["ordner"].replace("'", "''")             # steht in der einfach gequoteten -ArgumentList
        tabs.append(f'new-tab --title {a["kennung"]} --suppressApplicationTitle -d "{ordner}" {os.path.basename(_shell())} -NoExit -EncodedCommand {b64}')
    if not tabs:
        raise kern.AmwFehler("kein Agent mit Profil-Ordner – amw agent profil <kennung> --ordner <Pfad>")
    zeilen.append("Start-Process wt.exe -ArgumentList '-w amw " + " ; ".join(tabs) + "'")
    return "\n".join(zeilen) + "\n"
