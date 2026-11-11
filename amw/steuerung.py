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
    """PowerShell-Befehlszeile für den Tab: Umgebung setzen, Claude mit Profil starten."""
    teile = ["--resume", fortsetzen_id] if fortsetzen_id else ["--session-id", neue_id] if neue_id else []
    teile += _optionen(p)
    if not fortsetzen_id and p["startsatz"]:
        teile.append(p["startsatz"])
    aufruf = _aufruf(teile)
    projekt = f"$env:AMW_PROJEKT = {_ps(p['projekt'])}; " if p.get("projekt") else ""
    return f"Set-Location {_ps(p['ordner'])}; $env:AMW_AGENT = {_ps(p['kennung'])}; {projekt}{aufruf}; {MAUS_AUS}"


def _shell():
    return shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"


def letzte_sitzung(con, pid, kennung):
    r = con.execute("SELECT s.claude_sitzung FROM sitzung s JOIN agent a ON a.id = s.agent_id WHERE a.projekt_id = ?"
                    " AND a.kennung = ? AND s.claude_sitzung IS NOT NULL ORDER BY s.id DESC LIMIT 1", (pid, kennung)).fetchone()
    return r["claude_sitzung"] if r else None


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
    return f"{kennung} " + (f"setzt Sitzung {fort[:8]} fort" if fort else f"startet neu (Sitzung {neue[:8]})") \
        + (" im Windows Terminal" if wt_exe else " in einem Konsolenfenster")


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
    (beenden_mit or (lambda p: subprocess.run(["taskkill", "/PID", str(p), "/T", "/F"], capture_output=True)))(cpid)
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


def ende_anfordern(con, pid, kennungen=None, frist_min=ENDE_FRIST_MIN, jetzt=None):
    """Bittet laufende Agenten, zu sichern und sich abzumelden; nach `frist_min` beendet der Wächter die Sitzung.
    kennungen=None: alle, die gerade mit eigenem Prozess laufen. Rückgabe: {"agenten": [...], "bis_utc": …}."""
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
    for a in con.execute("SELECT kennung, ordner FROM agent WHERE projekt_id = ? AND soll = 'an' ORDER BY id", (pid,)):
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
                         + ("" if kennungen or alle else " AND soll = 'an'") + " ORDER BY id", (pid,)).fetchall():
        if kennungen and a["kennung"] not in kennungen:
            continue
        p = profil(con, pid, a["kennung"])
        sid = letzte_sitzung(con, pid, a["kennung"]) or str(uuid.uuid5(uuid.NAMESPACE_URL, f"amw:{uid}:{a['kennung']}"))
        weiter = _aufruf(["--resume", sid] + _optionen(p) + [NEUSTART_SATZ], lesbar=True)
        neu = _aufruf(["--session-id", sid] + _optionen(p) + ([p["startsatz"]] if p["startsatz"] else []), lesbar=True)
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
