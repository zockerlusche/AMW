"""Symbol im Infobereich (A1746, Marcel 15.11. 07:51, Aussehen F5338 A / D1141): Bildschirm-Freigabe ohne Browser.

Ein kleiner Punkt im Infobereich der Taskleiste zeigt den Zustand ohne Klick – bernstein = frei für Agenten, blau = frei,
aber „kurz da“, grau = belegt; der Zustand steht auch als Text beim Drüberfahren. Rechtsklick öffnet das Menü (frei bis …,
„Ich bin kurz da“ 15/30/60 min, Freigabe beenden, Workbench öffnen), Linksklick die Workbench.

Nur Windows, nur Python-Standardbibliothek (ctypes, Shell_NotifyIcon) – keine neue Abhängigkeit (pystray wäre LGPL). Läuft im
Benutzer-Kontext (pythonw, ohne Konsole), eine Instanz je Benutzer. Schaltet über dieselben Funktionen wie Workbench und
Befehlszeile (schirm.setzen als Entwickler, schirm.kurz_da) – gleiche Regeln: neue Läufe mit Fenster starten erst, wenn der
PC ruht; laufende laufen weiter.

Start: pythonw F:/amw/amw-tray.pyw  ·  Autostart richtet der Mensch ein (Hilfe „Bildschirm“).
"""
import ctypes
import datetime
import os
import struct
import sys
import time

from . import db, einstellungen, kern, schirm

FARBEN = {"frei": (240, 169, 58), "kurz": (106, 166, 224), "zu": (140, 134, 122)}   # bernstein, blau, grau
BIS_STUNDEN = (1, 2)
BIS_UHR = "22:00"
TAKT_MS = 5000


# --- Zustand und Menü als Daten (testbar ohne Fenster) -------------------------------------------------------------------
def lage(con, jetzt=None):
    """{"art": frei|kurz|zu, "titel", "unter"} – was das Symbol zeigt."""
    jetzt = jetzt or time.time()
    z = schirm.zustand(con)
    if not z["frei"]:
        return {"art": "zu", "titel": "Belegt – keine Läufe mit Fenster",
                "unter": f"seit {schirm.lokal(z['seit_utc'])} · {z['grund']}" if z.get("seit_utc") else z["grund"]}
    kurz = schirm.kurz_da_bis(jetzt)
    bis = f" bis {schirm.lokal(z['bis_utc'])}" if z.get("bis_utc") else ""
    if kurz:
        return {"art": "kurz", "titel": f"Frei – du bist kurz da bis {datetime.datetime.fromtimestamp(kurz).strftime('%H:%M')}",
                "unter": f"Eingaben schließen nicht · neue Fenster-Läufe warten, bis der PC {schirm.RUHE_S // 60} min ruht"}
    return {"art": "frei", "titel": f"Frei für Agenten{bis}", "unter": f"seit {schirm.lokal(z['seit_utc'])} · {z['grund']}"}


def menue(art):
    """Einträge: (Kennung, Text) · (None, None) = Trennlinie · (Text, [Einträge]) = Untermenü. Kennungen siehe ausfuehren()."""
    bis = [(f"bis:{h}h", f"{h} Stunde" + ("n" if h > 1 else "")) for h in BIS_STUNDEN] + [(f"bis:{BIS_UHR}", f"bis {BIS_UHR}"),
                                                                                         ("bis:ohne", "ohne Ende")]
    kurz = [(f"kurz:{m}", f"{m} Minuten") for m in schirm.KURZ_DA_MINUTEN]
    if art == "zu":
        return [("Für Agenten freigeben", bis), (None, None), ("oeffnen", "Workbench öffnen"), ("ende", "Symbol ausblenden")]
    eintraege = [("Länger da" if art == "kurz" else "Ich bin kurz da", kurz)]
    if art == "kurz":
        eintraege.append(("weg", "Bin wieder weg"))
    return eintraege + [("Frei bis …", bis), ("zu", "Freigabe beenden"), (None, None), ("oeffnen", "Workbench öffnen"),
                        ("ende", "Symbol ausblenden")]


def ausfuehren(con, kennung, jetzt=None):
    """Einen Menüeintrag ausführen – mit denselben Funktionen wie Workbench und Befehlszeile. Rückgabe: kurzer Text."""
    jetzt = jetzt or time.time()
    pid = (con.execute("SELECT id FROM projekt ORDER BY id LIMIT 1").fetchone() or [None])[0]
    was, _, wert = kennung.partition(":")
    if was == "bis":
        if wert == "ohne":
            bis = None
        elif wert.endswith("h"):
            bis = datetime.datetime.fromtimestamp(jetzt + int(wert[:-1]) * 3600).strftime("%H:%M")
        else:
            bis = wert
        schirm.setzen(con, pid, kern.ENTWICKLER, True, "Freigabe über das Symbol in der Taskleiste", bis=bis, quelle="workbench")
        return "frei" + (f" bis {bis}" if bis else "")
    if was == "zu":
        schirm.setzen(con, pid, kern.ENTWICKLER, False, "Freigabe über das Symbol beendet", quelle="workbench")
        return "zu"
    if was == "kurz":
        schirm.kurz_da(con, int(wert), jetzt)
        return f"kurz da {wert} min"
    if was == "weg":
        schirm.kurz_da(con, 0, jetzt)
        return "wieder weg"
    raise kern.AmwFehler(f"unbekannter Eintrag {kennung}")


def ico_bytes(farbe, groesse=32):
    """Ein Punkt in `farbe` als .ico (32 Bit, mit weichem Rand) – ohne Bildbibliothek."""
    r, g, b = farbe
    zeilen = []
    mitte, radius = (groesse - 1) / 2, groesse * 0.36
    for y in range(groesse - 1, -1, -1):                 # BMP: von unten nach oben
        z = bytearray()
        for x in range(groesse):
            d = ((x - mitte) ** 2 + (y - mitte) ** 2) ** 0.5
            a = max(0.0, min(1.0, radius + 0.5 - d))
            ring = max(0.0, min(1.0, radius + 2.0 - d)) - a   # dunkler Rand: auf heller Taskleiste sichtbar
            al = int(255 * min(1.0, a + ring * 0.55))
            f = (0.25 if ring > a else 1.0)
            z += bytes((int(b * f), int(g * f), int(r * f), al))
        zeilen.append(bytes(z))
    pixel = b"".join(zeilen)
    maske = b"\x00" * (((groesse + 31) // 32) * 4 * groesse)
    kopf = struct.pack("<IiiHHIIiiII", 40, groesse, groesse * 2, 1, 32, 0, len(pixel) + len(maske), 0, 0, 0, 0)
    bild = kopf + pixel + maske
    return struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", groesse, groesse, 0, 0, 1, 32, len(bild), 22) + bild


# --- Windows: Symbol, Menü, Nachrichtenschleife ---------------------------------------------------------------------------
def _win():
    from ctypes import wintypes as w
    u, k, s = ctypes.windll.user32, ctypes.windll.kernel32, ctypes.windll.shell32
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", w.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", w.HINSTANCE), ("hIcon", w.HICON), ("hCursor", w.HANDLE), ("hbrBackground", w.HBRUSH),
                    ("lpszMenuName", w.LPCWSTR), ("lpszClassName", w.LPCWSTR)]

    class GUID(ctypes.Structure):
        _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [("cbSize", w.DWORD), ("hWnd", w.HWND), ("uID", w.UINT), ("uFlags", w.UINT), ("uCallbackMessage", w.UINT),
                    ("hIcon", w.HICON), ("szTip", ctypes.c_wchar * 128), ("dwState", w.DWORD), ("dwStateMask", w.DWORD),
                    ("szInfo", ctypes.c_wchar * 256), ("uVersion", w.UINT), ("szInfoTitle", ctypes.c_wchar * 64),
                    ("dwInfoFlags", w.DWORD), ("guidItem", GUID), ("hBalloonIcon", w.HICON)]

    u.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    u.DefWindowProcW.restype = LRESULT
    u.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID]
    u.CreateWindowExW.restype = w.HWND
    u.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    u.LoadImageW.argtypes = [w.HINSTANCE, w.LPCWSTR, w.UINT, ctypes.c_int, ctypes.c_int, w.UINT]
    u.LoadImageW.restype = w.HANDLE
    u.CreatePopupMenu.restype = w.HMENU
    u.AppendMenuW.argtypes = [w.HMENU, w.UINT, ctypes.c_size_t, w.LPCWSTR]
    u.TrackPopupMenu.argtypes = [w.HMENU, w.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.HWND, w.LPVOID]
    u.DestroyMenu.argtypes = [w.HMENU]
    u.SetTimer.argtypes = [w.HWND, ctypes.c_size_t, w.UINT, w.LPVOID]
    u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    u.GetMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
    s.Shell_NotifyIconW.argtypes = [w.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    k.GetModuleHandleW.restype = w.HMODULE
    k.CreateMutexW.restype = w.HANDLE
    return u, k, s, w, WNDPROC, WNDCLASSW, NOTIFYICONDATAW


class Tray:
    WM_SYMBOL = 0x8000 + 1                               # WM_APP + 1
    NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
    NIF_MESSAGE, NIF_ICON, NIF_TIP = 1, 2, 4

    def __init__(self):
        self.u, self.k, self.s, self.w, WNDPROC, WNDCLASSW, self.NID = _win()
        self.con = db.verbinde()
        self.ordner = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "amw", "tray")
        os.makedirs(self.ordner, exist_ok=True)
        self.icons = {}
        for art, farbe in FARBEN.items():
            pfad = os.path.join(self.ordner, f"{art}.ico")
            with open(pfad, "wb") as f:
                f.write(ico_bytes(farbe))
            self.icons[art] = self.u.LoadImageW(None, pfad, 1, 0, 0, 0x10 | 0x40)   # IMAGE_ICON, LR_LOADFROMFILE|LR_DEFAULTSIZE
        self._proc = WNDPROC(self._wndproc)              # Referenz halten (sonst räumt Python sie weg)
        inst = self.k.GetModuleHandleW(None)
        wc = WNDCLASSW(lpfnWndProc=self._proc, hInstance=inst, lpszClassName="AMWTray")
        self.u.RegisterClassW(ctypes.byref(wc))
        self.hwnd = self.u.CreateWindowExW(0, "AMWTray", "AMW", 0, 0, 0, 0, 0, None, None, inst, None)
        self.neu_gestartet = self.u.RegisterWindowMessageW("TaskbarCreated")
        self.kennungen, self.art = {}, None
        self._symbol(self.NIM_ADD)
        self.u.SetTimer(self.hwnd, 1, TAKT_MS, None)

    def _daten(self):
        nid = self.NID()
        nid.cbSize = ctypes.sizeof(self.NID)
        nid.hWnd, nid.uID = self.hwnd, 1
        nid.uFlags = self.NIF_MESSAGE | self.NIF_ICON | self.NIF_TIP
        nid.uCallbackMessage = self.WM_SYMBOL
        l = lage(self.con)
        self.art = l["art"]
        nid.hIcon = self.icons[l["art"]]
        nid.szTip = ("AMW · " + l["titel"])[:127]
        return nid

    def _symbol(self, was):
        nid = self._daten()
        self.s.Shell_NotifyIconW(was, ctypes.byref(nid))

    def _menue_bauen(self, eintraege):
        m = self.u.CreatePopupMenu()
        for a, b in eintraege:
            if a is None:
                self.u.AppendMenuW(m, 0x800, 0, None)                         # MF_SEPARATOR
            elif isinstance(b, list):
                self.u.AppendMenuW(m, 0x10, self._menue_bauen(b), a)          # MF_POPUP
            else:
                nr = len(self.kennungen) + 100
                self.kennungen[nr] = a
                self.u.AppendMenuW(m, 0, nr, b)
        return m

    def _menue(self):
        self.kennungen = {}
        l = lage(self.con)
        m = self.u.CreatePopupMenu()
        self.u.AppendMenuW(m, 0x1 | 0x2, 0, l["titel"])                      # Kopfzeile (grau, nicht wählbar)
        self.u.AppendMenuW(m, 0x1 | 0x2, 0, l["unter"][:90])
        self.u.AppendMenuW(m, 0x800, 0, None)
        for a, b in menue(l["art"]):
            if a is None:
                self.u.AppendMenuW(m, 0x800, 0, None)
            elif isinstance(b, list):
                self.u.AppendMenuW(m, 0x10, self._menue_bauen(b), a)
            else:
                nr = len(self.kennungen) + 100
                self.kennungen[nr] = a
                self.u.AppendMenuW(m, 0, nr, b)
        punkt = self.w.POINT()
        self.u.GetCursorPos(ctypes.byref(punkt))
        self.u.SetForegroundWindow(self.hwnd)
        nr = self.u.TrackPopupMenu(m, 0x0100 | 0x0020, punkt.x, punkt.y, 0, self.hwnd, None)   # TPM_RETURNCMD | TPM_RIGHTBUTTON
        self.u.PostMessageW(self.hwnd, 0, 0, 0)
        self.u.DestroyMenu(m)
        return self.kennungen.get(nr)

    def _wahl(self, kennung):
        if kennung == "oeffnen":
            os.startfile(f"http://127.0.0.1:{einstellungen.wert('port')}/")
        elif kennung == "ende":
            self.u.DestroyWindow(self.hwnd)
        elif kennung:
            try:
                ausfuehren(self.con, kennung)
            except kern.AmwFehler as e:
                self.u.MessageBoxW(None, str(e), "AMW", 0x30)
            self._symbol(self.NIM_MODIFY)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == self.WM_SYMBOL:
            if lparam in (0x0205, 0x007B):                                      # WM_RBUTTONUP, WM_CONTEXTMENU
                self._wahl(self._menue())
            elif lparam == 0x0202:                                              # WM_LBUTTONUP
                self._wahl("oeffnen")
            return 0
        if msg == 0x0113:                                                       # WM_TIMER: Zustand nachziehen
            try:
                self._symbol(self.NIM_MODIFY)
            except Exception:                                                   # Datenbank kurz belegt: nächste Runde
                pass
            return 0
        if msg == self.neu_gestartet:                                           # Explorer neu gestartet: Symbol neu anlegen
            self._symbol(self.NIM_ADD)
            return 0
        if msg == 0x0002:                                                       # WM_DESTROY
            nid = self._daten()
            self.s.Shell_NotifyIconW(self.NIM_DELETE, ctypes.byref(nid))
            self.u.PostQuitMessage(0)
            return 0
        return self.u.DefWindowProcW(hwnd, msg, wparam, lparam)

    def laufen(self):
        nachricht = self.w.MSG()
        while self.u.GetMessageW(ctypes.byref(nachricht), None, 0, 0) > 0:
            self.u.TranslateMessage(ctypes.byref(nachricht))
            self.u.DispatchMessageW(ctypes.byref(nachricht))


def main():
    if os.name != "nt":
        print("Das Symbol im Infobereich gibt es nur unter Windows.")
        return 1
    k = ctypes.windll.kernel32
    k.CreateMutexW.restype = ctypes.c_void_p
    sperre = k.CreateMutexW(None, False, "Local\\AMW-Tray")             # eine Instanz je Benutzer
    if k.GetLastError() == 183:                                           # ERROR_ALREADY_EXISTS
        return 0
    try:
        Tray().laufen()
    finally:
        k.CloseHandle(ctypes.c_void_p(sperre))
    return 0


if __name__ == "__main__":
    sys.exit(main())
