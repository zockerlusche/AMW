"""Schirm-Schalter (Schema 11, → doc/automatismen.md).

Darf gerade ein Lauf am Bildschirm laufen? Vorgabe: nein. Frei gibt nur der Entwickler (Workbench am PC) oder der
Lead auf sein Wort (Brücke); zu darf jeder. Der Dienst schließt den Schirm von selbst, sobald der Entwickler wieder da
ist – nur Signale am PC selbst: Eingabe am PC (später als RUHE_S nach dem Freigeben, auch über eine Fernsitzung), eine
Fernsitzung beginnt (wenn ihr Programm in den PC-Einstellungen steht), eine Eingabe in der Workbench am PC, oder die
bis-Uhrzeit ist erreicht. Schreibt er vom Handy (Online-Seite, Chat, Wortlaut), bleibt der Schirm frei. Die Lauf-Schlange startet Schirm-Läufe nur bei frei und wenn der PC seit RUHE_S ruht
(betrieb.py). Die AMW beendet selbst keine Prozesse – sie meldet.
"""
import calendar
import ctypes
import time
from ctypes import wintypes
from datetime import datetime, timedelta

from . import db, einstellungen, kern

RUHE_S = 120                 # so lange ohne Eingabe gilt der PC als verlassen
NACHFRIST_S = 300            # läuft ein Schirm-Lauf so lange nach dem Zugehen weiter, erfährt es der Lead
QUELLEN = ("workbench", "netz", "cli", "bruecke", "automatik")


def _sek(utc):
    return calendar.timegm(time.strptime(utc, "%Y-%m-%dT%H:%M:%SZ"))


def _utc(sek):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(sek))


def lokal(utc):
    """„06:02“ bzw. „03.11. 21:51“ (nicht heute) in Ortszeit."""
    d = datetime.fromtimestamp(_sek(utc))
    return d.strftime("%H:%M") if d.date() == datetime.now().date() else d.strftime("%d.%m. %H:%M")


def bis_utc(text):
    """„07:00“ → nächstes 07:00 Ortszeit; „2026-11-05 07:00“ genau dann. Rückgabe UTC-Zeitstempel."""
    text = (text or "").strip()
    try:
        if len(text) <= 5:
            h, m = (int(x) for x in text.split(":"))
            jetzt = datetime.now()
            d = jetzt.replace(hour=h, minute=m, second=0, microsecond=0)
            if d <= jetzt:
                d += timedelta(days=1)
        else:
            d = datetime.strptime(text, "%Y-%m-%d %H:%M")
    except ValueError:
        raise kern.AmwFehler(f"--bis „{text}“: HH:MM oder JJJJ-MM-TT HH:MM") from None
    return _utc(time.mktime(d.timetuple()))


# --- Messen --------------------------------------------------------------------------------------

def leerlauf_s():
    """Sekunden seit der letzten Eingabe an diesem PC (Windows GetLastInputInfo); None, wenn nicht messbar.
    Gilt für die Sitzung, in der der Dienst läuft – die geplante Aufgabe läuft in der Sitzung des Entwicklers."""
    class LII(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    try:
        li = LII()
        li.cbSize = ctypes.sizeof(LII)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li)):
            return None
        jetzt = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
        return ((jetzt - li.dwTime) & 0xFFFFFFFF) / 1000
    except (AttributeError, OSError):
        return None


def programme():
    """Laufende Programme {name klein: [PID, …]} über die Toolhelp-Schnittstelle – ohne Hilfsprozess."""
    class PE(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]
    try:
        k = ctypes.windll.kernel32
    except AttributeError:
        return {}
    k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    h = k.CreateToolhelp32Snapshot(2, 0)                   # TH32CS_SNAPPROCESS
    if not h or h == wintypes.HANDLE(-1).value:
        return {}
    laufend = {}
    try:
        pe = PE()
        pe.dwSize = ctypes.sizeof(PE)
        ok = k.Process32FirstW(h, ctypes.byref(pe))
        while ok:
            laufend.setdefault(pe.szExeFile.lower(), []).append(pe.th32ProcessID)
            ok = k.Process32NextW(h, ctypes.byref(pe))
    finally:
        k.CloseHandle(h)
    return laufend


def startzeit(pid):
    """Startzeit eines Prozesses (Unix-Sekunden) oder None."""
    try:
        k = ctypes.windll.kernel32
    except AttributeError:
        return None
    k.OpenProcess.restype = wintypes.HANDLE
    h = k.OpenProcess(0x1000, False, pid)                   # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        t = [wintypes.FILETIME() for _ in range(4)]
        if not k.GetProcessTimes(h, *(ctypes.byref(x) for x in t)):
            return None
        ft = (t[0].dwHighDateTime << 32) | t[0].dwLowDateTime
        return ft / 1e7 - 11644473600                       # 100-ns-Schritte seit 1601 → Unix-Sekunden
    finally:
        k.CloseHandle(h)


_gesehen = {}                # PID des Fernsitzungs-Programms → Beginn (oder: wann dieser Prozess es zuerst sah)


def fernsitzung():
    """Beginn der jüngsten Fernsitzung (Unix-Sekunden) oder None. Erkannt am Programm aus der PC-Einstellung
    fernsitzung_prozess – eins, das nur während einer Verbindung läuft (bei TeamViewer z. B. TeamViewer_Desktop.exe;
    das Hauptprogramm läuft oft ständig im Infobereich und sagt nichts). Läuft es als SYSTEM, verweigert Windows ohne
    Adminrechte die Startzeit – dann zählt, wann wir es zuerst sahen. Nach einem Neustart des Dienstes gilt eine
    laufende Sitzung deshalb als neu: lieber zu als zu Unrecht frei."""
    name = einstellungen.wert("fernsitzung_prozess")
    pids = programme().get(name, []) if name else []
    for p in pids:
        _gesehen.setdefault(p, startzeit(p) or time.time())
    for p in [p for p in _gesehen if p not in pids]:
        del _gesehen[p]
    return max((_gesehen[p] for p in pids), default=None)


# --- Zustand -------------------------------------------------------------------------------------

def zustand(con):
    r = con.execute("SELECT * FROM schirm ORDER BY id DESC LIMIT 1").fetchone()
    if r:
        return dict(r)
    return {"frei": 0, "seit_utc": None, "bis_utc": None, "grund": "noch nie freigegeben", "von": "AMW", "quelle": "automatik"}


def verlauf(con, grenze=20):
    return [dict(r) for r in con.execute("SELECT * FROM schirm ORDER BY id DESC LIMIT ?", (grenze,))]


def text(z):
    """Eine Zeile für Menschen und Agenten."""
    if z["frei"]:
        return (f"Schirm FREI seit {lokal(z['seit_utc'])}" + (f" bis {lokal(z['bis_utc'])}" if z["bis_utc"] else "")
                + f" ({z['von']}): {z['grund']}")
    if not z["seit_utc"]:
        return "Schirm ZU (noch nie freigegeben)"
    return f"Schirm ZU seit {lokal(z['seit_utc'])} ({z['von']}): {z['grund']}"


def sperrgrund(con, leerlauf=None):
    """None, wenn ein Schirm-Lauf jetzt starten darf; sonst der Grund (für Meldungen und die Schlange)."""
    z = zustand(con)
    if not z["frei"]:
        return text(z)
    if leerlauf is None:
        leerlauf = leerlauf_s()
    if leerlauf is not None and leerlauf < RUHE_S:
        return (f"Schirm frei, aber am PC wurde vor {int(leerlauf)} s etwas eingegeben – Schirm-Läufe starten erst nach"
                f" {RUHE_S // 60} min Ruhe")
    return None


def setzen(con, pid, von, frei, grund=None, bis=None, quelle="cli"):
    """Schirm frei (nur Entwickler/Lead, mit Grund) oder zu (jeder). Zu, wenn schon zu: keine neue Zeile.
    Beim Zugehen erfahren Agenten mit laufenden oder eingereihten Schirm-Läufen davon (weckend)."""
    if quelle not in QUELLEN:
        raise kern.AmwFehler(f"Quelle {quelle}?")
    grund = (grund or "").strip()[:500]
    bis_zeit = None
    if frei:
        if pid is None or not kern.ist_lead(con, pid, von):
            raise kern.AmwFehler("Schirm frei geben nur der Entwickler und der Lead auf sein Wort")
        if not grund:
            raise kern.AmwFehler("Grund angeben, z. B. „Entwickler 21:51: weg bis morgen, Monitor an“")
        if bis:
            bis_zeit = bis_utc(bis)
    with db.schreiben(con):
        vorher = zustand(con)
        if not frei and not vorher["frei"]:
            return vorher
        db.einfuegen(con, "schirm", frei=int(bool(frei)), seit_utc=db.jetzt(), bis_utc=bis_zeit,
                     grund=grund or f"zu von {von}", von=von, quelle=quelle)
        if not frei:
            _zu_melden(con, grund or f"zu von {von}")
    return zustand(con)


def _zu_melden(con, grund):
    for l in con.execute("SELECT * FROM lauf WHERE schirm = 1 AND status = 'laeuft'").fetchall():
        kern._posten(con, l["projekt_id"], "AMW", l["agent"], "korrektur",
                     f"Schirm zu – L{l['id']} jetzt beenden: {grund}"[:300],
                     f"Der Schirm ist zu ({grund}). Bitte den Schirm-Lauf L{l['id']} ({l['beschreibung']}) sofort beenden"
                     f" und melden: amw lauf ende {l['id']} --rc <Code> (oder --abgebrochen). Die AMW beendet keine"
                     f" Prozesse selbst. Läuft er in {NACHFRIST_S // 60} min noch, erfährt es der Lead.",
                     aufgabe_id=l["aufgabe_id"])
    wartend = {}
    for l in con.execute("SELECT * FROM lauf WHERE schirm = 1 AND status = 'angemeldet' ORDER BY id").fetchall():
        wartend.setdefault((l["projekt_id"], l["agent"]), []).append(f"L{l['id']}")
    for (pid, agent), nummern in wartend.items():
        kern._posten(con, pid, "AMW", agent, "meldung", f"Schirm zu – {', '.join(nummern)} warten bis zur nächsten Freigabe",
                     f"Grund: {grund}. Die Schlange startet sie von selbst, sobald der Schirm wieder frei ist, und weckt"
                     " dich dann. Bis dahin nichts am Bildschirm starten.")


def entwickler_da(con, wo):
    """Der Entwickler hat etwas getan (Workbench, Handy) – ein freier Schirm geht zu."""
    if zustand(con)["frei"]:
        setzen(con, None, "AMW", False, f"{kern.entwickler_name(con)} ist da ({wo}, {datetime.now().strftime('%H:%M')})",
               quelle="automatik")
        return True
    return False


def pruefen(con, leerlauf=None, tv=None, jetzt=None):
    """Eine Runde im Dienst: schließt einen freien Schirm, sobald der Entwickler wieder da ist, und meldet dem Lead
    Schirm-Läufe, die nach dem Zugehen weiterlaufen. leerlauf/tv/jetzt nur für Tests. Rückgabe: Ereignisse fürs Log."""
    jetzt = jetzt or time.time()
    tv = fernsitzung() if tv is None else tv       # jede Runde, auch bei zu: sonst sähen wir eine ältere Sitzung erst
    z = zustand(con)                               # nach dem Freigeben „zum ersten Mal“ und hielten sie für neu
    aus = []
    if z["frei"]:
        seit = _sek(z["seit_utc"])
        grund = None
        if z["bis_utc"] and jetzt >= _sek(z["bis_utc"]):
            grund = f"Freigabe bis {lokal(z['bis_utc'])} ist abgelaufen"
        if not grund and tv and tv > seit:          # nur eine Sitzung, die nach dem Freigeben beginnt; tippt er in
            grund = f"Fernsitzung seit {lokal(_utc(tv))}"          # einer älteren, zählt das als Eingabe am PC
        if not grund:
            leerlauf = leerlauf_s() if leerlauf is None else leerlauf
            if leerlauf is not None and jetzt - leerlauf > seit + RUHE_S:
                grund = f"Eingabe am PC ({lokal(_utc(jetzt - leerlauf))})"
        if grund:
            setzen(con, None, "AMW", False, grund, quelle="automatik")
            aus.append(f"Schirm zu: {grund}")
        return aus
    if not z["seit_utc"] or jetzt - _sek(z["seit_utc"]) < NACHFRIST_S:
        return aus
    for l in con.execute("SELECT * FROM lauf WHERE schirm = 1 AND status = 'laeuft'").fetchall():
        kurz = f"L{l['id']} läuft trotz Schirm zu"
        if con.execute("SELECT 1 FROM nachricht WHERE von = 'AMW' AND kurz LIKE ? AND zeit_utc >= ?",
                       (kurz + "%", z["seit_utc"])).fetchone():
            continue
        leads = [r["kennung"] for r in con.execute("SELECT kennung FROM agent WHERE projekt_id = ? AND rolle = 'lead'",
                                                    (l["projekt_id"],))]
        if leads:
            kern.posten(con, l["projekt_id"], "AMW", ",".join(leads), "meldung",
                        f"{kurz} ({l['agent']}, seit {lokal(z['seit_utc'])} zu)",
                        f"{text(z)}. {l['agent']} wurde beim Zugehen gebeten, L{l['id']} ({l['beschreibung']}) zu beenden."
                        " Die AMW beendet keine Prozesse – bitte nachfassen.", aufgabe_id=l["aufgabe_id"])
            aus.append(f"{kurz}: Lead gemeldet")
    return aus
