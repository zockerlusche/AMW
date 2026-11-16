"""Läufe ohne Bildschirm, die doch ein Fenster öffnen (A1747, Marcel 14.11.: Godot-Fenster, während er spielte und der
Bildschirm zu war – angemeldet waren die Läufe ohne --schirm).

Der Dienst sieht je Aufsichtsrunde nach: Hat ein Prozess aus einem laufenden Lauf ohne --schirm (Prozessbaum, wie ihn
„amw lauf ausfuehren“ merkt) ein sichtbares Fenster? Dann gilt der Lauf ab jetzt als Lauf mit Fenster (schirm = 1, die
Schlange behandelt ihn so), Agent und Lead erfahren es – und ist der Bildschirm zu, wird der Agent gebeten, den Lauf zu
beenden. Die AMW beendet nichts selbst. Gelesen wird nur, welcher Prozess ein Fenster hat, nie der Fenstertitel.

Danach nimmt die Schlange denselben Lauf (gleiche Art: Befehl ohne Ziffern/Hashes, wie beim Lernen des Bedarfs) 7 Tage lang
nur mit --schirm an. Dasselbe gilt, wenn ein Lauf ohne --schirm bei belegtem Bildschirm von außen geschlossen wurde
(Rückgabe 0xC000013A – so endet ein Programm, dessen Fenster jemand schließt).
"""
import ctypes
import datetime
import json
import os

from . import belegung, betrieb, db, kern

MERKER = "fenster_ohne_schirm"     # plan_ereignis.art – Text: „L<nr> · <Lauf-Art>“
SPERRE_TAGE = 7
GESCHLOSSEN = {0xC000013A, 0xC000013A - (1 << 32)}   # STATUS_CONTROL_C_EXIT: Fenster/Konsole von außen geschlossen


def sichtbare_fenster():
    """Prozess-Nummern mit mindestens einem sichtbaren Hauptfenster (nicht versteckt, kein Werkzeugfenster, nicht
    „cloaked“). Nur die Nummern – keine Titel. Leere Menge außerhalb von Windows oder bei Fehlern."""
    if os.name != "nt":
        return set()
    try:
        from ctypes import wintypes
        u = ctypes.windll.user32
        try:
            dwm = ctypes.windll.dwmapi
        except OSError:
            dwm = None
        aus = set()

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def je(h, _):
            if not u.IsWindowVisible(h) or u.GetWindow(h, 4):              # 4 = GW_OWNER: nur Hauptfenster
                return True
            if u.GetWindowLongW(h, -20) & 0x80:                           # GWL_EXSTYLE · WS_EX_TOOLWINDOW
                return True
            if dwm is not None:
                versteckt = wintypes.DWORD()
                if dwm.DwmGetWindowAttribute(h, 14, ctypes.byref(versteckt), ctypes.sizeof(versteckt)) == 0 and versteckt.value:
                    return True                                          # 14 = DWMWA_CLOAKED (z. B. andere Arbeitsfläche)
            r = wintypes.RECT()
            if u.GetWindowRect(h, ctypes.byref(r)) and (r.right - r.left < 50 or r.bottom - r.top < 50):
                return True
            p = wintypes.DWORD()
            u.GetWindowThreadProcessId(h, ctypes.byref(p))
            if p.value:
                aus.add(p.value)
            return True

        u.EnumWindows(je, 0)
        return aus
    except (AttributeError, OSError):
        return set()


def pruefen(con, fenster=None, liste=None, schirm_frei=None, konsole=None):
    """Eine Runde im Dienst. Rückgabe: Liste (Lauf-Nr, Programmname) der neu erkannten Läufe. Fenster eines Prozesses aus dem
    Baum des Laufs – oder (A1763) ein sichtbares Konsolenfenster eines dieser Prozesse. konsole: Ersatz für den Konsolen-Helfer
    (Tests), False = Konsolen nicht prüfen."""
    from . import schirm
    laufende = con.execute("SELECT * FROM lauf l WHERE l.status = 'laeuft' AND l.schirm = 0 AND " + betrieb.HIER,
                           (betrieb.rechner(),)).fetchall()
    kandidaten = [(l, belegung.lauf_pid(l["id"])) for l in laufende]
    kandidaten = [(l, p) for l, p in kandidaten if p]
    if not kandidaten:
        return []
    fenster = sichtbare_fenster() if fenster is None else fenster
    liste = belegung.prozesse() if liste is None else liste
    namen = {p["pid"]: p["name"] for p in liste}
    if schirm_frei is None:
        schirm_frei = bool(schirm.zustand(con)["frei"])
    neu = []
    for l, wurzel in kandidaten:
        baum = belegung._nachkommen(liste, [wurzel])
        mit = sorted(baum & fenster) or sorted(konsolen_fenster(baum, konsole) if konsole is not False else ())   # A1763
        if not mit:
            continue
        programm = namen.get(mit[0]) or "ein Programm"
        art = betrieb.lauf_art(json.loads(l["befehl"]) if l["befehl"] else None, l["beschreibung"])
        with db.schreiben(con):
            con.execute("UPDATE lauf SET schirm = 1 WHERE id = ?", (l["id"],))
            db.einfuegen(con, "plan_ereignis", projekt_id=l["projekt_id"], zeit_utc=db.jetzt(), von="AMW", art=MERKER,
                         aufgabe_id=l["aufgabe_id"], text=f"L{l['id']} · {art}"[:500])
            bitte = ("" if schirm_frei else " Der Bildschirm ist gerade ZU (jemand arbeitet am PC): bitte den Lauf sofort beenden und"
                     f" melden (amw lauf ende {l['id']} --rc <Code> oder --abgebrochen) – die AMW beendet nichts selbst.")
            kern._posten(con, l["projekt_id"], "AMW", l["agent"], "korrektur" if not schirm_frei else "info",
                         f"L{l['id']} öffnet ein Fenster ({programm}) – angemeldet ohne --schirm"[:300],
                         f"Der Lauf „{l['beschreibung'] or ''}“ ist ohne --schirm angemeldet, {programm} zeigt aber ein Fenster. Er gilt ab"
                         f" jetzt als Lauf mit Fenster. Denselben Lauf nimmt die Schlange {SPERRE_TAGE} Tage lang nur noch mit --schirm an"
                         " (amw lauf ausfuehren --schwer --schirm …) – oder ohne Fenster starten (z. B. --headless)." + bitte,
                         aufgabe_id=l["aufgabe_id"])
            lead = kern.lead(con, l["projekt_id"])
            if lead and lead != l["agent"]:
                kern._posten(con, l["projekt_id"], "AMW", lead, "info",
                             f"L{l['id']} ({l['agent']}) öffnet ein Fenster ohne --schirm"[:300],
                             f"{programm} aus L{l['id']} zeigt ein Fenster, angemeldet war der Lauf ohne Bildschirm."
                             + ("" if schirm_frei else f" Der Bildschirm ist zu – {l['agent']} ist gebeten, ihn zu beenden."),
                             aufgabe_id=l["aufgabe_id"])
        neu.append((l["id"], programm))
    return neu


def geschlossen(con, l, rc, schirm_frei):
    """Beim Ende eines Laufs (betrieb.lauf_ende): ein Lauf ohne --schirm, der bei belegtem Bildschirm mit 0xC000013A endete,
    wurde von außen geschlossen – vermutlich sein Fenster. Gleiche Sperre wie bei einem erkannten Fenster. In der
    Transaktion des Aufrufers."""
    if l["schirm"] or schirm_frei or rc is None or int(rc) not in GESCHLOSSEN:
        return False
    art = betrieb.lauf_art(json.loads(l["befehl"]) if l["befehl"] else None, l["beschreibung"])
    db.einfuegen(con, "plan_ereignis", projekt_id=l["projekt_id"], zeit_utc=db.jetzt(), von="AMW", art=MERKER,
                 aufgabe_id=l["aufgabe_id"], text=f"L{l['id']} · {art}"[:500])
    return True


FEHLALARM = "fenster_fehlalarm"


def fehlalarm(con, pid, von, lid):
    """Lead/Mensch: die Fenster-Meldung zu L<lid> war falsch (z. B. eine neu vergebene Prozess-Nummer) – die Sperre „nur noch
    mit --schirm“ entfällt. Rückgabe: Anzahl aufgehobener Vermerke."""
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Fehlalarm bestätigen dürfen nur Lead und Entwickler")
    with db.schreiben(con):
        n = con.execute("UPDATE plan_ereignis SET art = ? WHERE projekt_id = ? AND art = ? AND text LIKE ?",
                        (FEHLALARM, pid, MERKER, f"L{int(lid)} · %")).rowcount
    if not n:
        raise kern.AmwFehler(f"Zu L{lid} gibt es keine Fenster-Meldung")
    return n


def sperrgrund(con, pid, befehl, beschreibung, schirm):
    """Für lauf_start: None, oder warum dieser Lauf --schirm braucht (derselbe Lauf öffnete in den letzten Tagen ein Fenster
    bzw. wurde bei belegtem Bildschirm von außen geschlossen)."""
    if schirm:
        return None
    art = betrieb.lauf_art(befehl, beschreibung)
    seit = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=SPERRE_TAGE)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for (text,) in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND zeit_utc >= ? ORDER BY id DESC",
                               (pid, MERKER, seit)).fetchall():
        nr, _, a = (text or "").partition(" · ")
        if a == art:
            return (f"Dieser Lauf öffnete zuletzt ein Fenster ({nr}) – anmelden mit --schirm (er wartet dann auf einen freien"
                    " Bildschirm) oder ohne Fenster starten, z. B. --headless")
    return None


# --- A1763: Konsolenfenster (LayerIT R19: Godot_*_console.exe öffnet je Aufruf ein eigenes Konsolenfenster) ----------------
# Das Fenster einer Konsole gehört nicht dem Programm selbst, sondern conhost/OpenConsole bzw. dem Windows Terminal – darum
# fragt ein kleiner Hilfsprozess OHNE eigene Konsole je Prozess des Laufs: AttachConsole(pid) → GetConsoleWindow(); sichtbar
# ist es, wenn das Fenster selbst oder sein oberster Besitzer (Windows Terminal) sichtbar ist. Im Dienst selbst nie
# AttachConsole – das würde seine Ein-/Ausgabe umhängen.
_KONSOLE = r"""
import ctypes, sys
k, u = ctypes.windll.kernel32, ctypes.windll.user32
k.GetConsoleWindow.restype = ctypes.c_void_p
u.GetAncestor.restype = ctypes.c_void_p
u.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
u.IsWindowVisible.argtypes = [ctypes.c_void_p]
aus = []
for p in sys.argv[1:]:
    k.FreeConsole()
    if not k.AttachConsole(int(p)):
        continue
    h = k.GetConsoleWindow()
    if h and (u.IsWindowVisible(h) or u.IsWindowVisible(u.GetAncestor(h, 3))):   # 3 = GA_ROOTOWNER (Windows Terminal)
        aus.append(p)
    k.FreeConsole()
print(" ".join(aus))
"""


def konsolen_fenster(pids, laufen=None):
    """Prozess-Nummern (aus pids), deren Konsole ein sichtbares Fenster hat. Leere Menge außerhalb von Windows/bei Fehlern."""
    import subprocess
    import sys
    pids = sorted({int(p) for p in pids if p})
    if os.name != "nt" or not pids:
        return set()
    if laufen is None:
        exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        exe = exe if os.path.exists(exe) else sys.executable
        def laufen(befehl):
            r = subprocess.run(befehl, capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL,
                               creationflags=0x00000008)          # DETACHED_PROCESS: der Helfer hat keine eigene Konsole
            return r.stdout
        befehl = [exe, "-c", _KONSOLE, *map(str, pids[:60])]
    else:
        befehl = ["helfer", *map(str, pids[:60])]
    try:
        return {int(x) for x in (laufen(befehl) or "").split() if x.isdigit()}
    except (OSError, ValueError, Exception):              # noqa: BLE001 – nie den Dienst stören
        return set()
