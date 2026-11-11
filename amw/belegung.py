"""Dauer-Belegung: Programme, die außerhalb der Warteschlange lange viel Arbeitsspeicher halten – ein lokaler KI-Server,
eine virtuelle Maschine, ein großes Programm. Sie stehen in keiner Warteschlange, nehmen den schweren Läufen aber den
Platz. Die AMW erkennt und zeigt sie; sie beendet nie etwas.

Erkannt wird ein Prozess, der mindestens so viel Arbeitsspeicher hält wie eingestellt (dauer_ab_gb) und seit mindestens
MIN_ALTER_S läuft; mehrere solche Prozesse desselben Programms stehen zusammen. Viele kleine Prozesse (Browser) zählen
nicht. Prozesse eines Laufs aus der Warteschlange zählen nicht – sie sind dort schon angemeldet. Gelesen wird nur die Prozessliste des Systems (Name, Speicher, Startzeit), keine Befehlszeile.
"""
import ctypes
import datetime
import os
import time

MIN_ALTER_S = 600             # jünger: noch kein Dauer-Verbraucher (Tests, Builds, kurze Werkzeuge)
MERKEN_S = 15                 # so lange gilt eine Messung (die Startseite fragt alle paar Sekunden)
# Programme des Systems, die keinem Nutzer-Programm gehören
SYSTEM = {"", "system", "registry", "memory compression", "memcompression", "secure system", "idle", "system idle process"}
# Bekannte Arten – nur für die Bezeichnung; erkannt wird alles über der Grenze
ARTEN = (("ki", ("llama-server", "llama-cli", "llama", "ollama", "koboldcpp", "lm studio", "lmstudio", "text-generation", "comfyui",
                 "localai", "vllm", "tabby")),
         ("vm", ("vmmem", "vmwp", "vboxheadless", "virtualboxvm", "vmware-vmx", "qemu-system", "docker", "wslhost")))


def art(name):
    """„ki“ (lokale KI), „vm“ (virtuelle Maschine) oder „programm“."""
    n = name.lower()
    return next((a for a, muster in ARTEN if any(n.startswith(m) for m in muster)), "programm")


class _Text(ctypes.Structure):
    _fields_ = [("Length", ctypes.c_ushort), ("MaximumLength", ctypes.c_ushort), ("Buffer", ctypes.c_void_p)]


class _Prozess(ctypes.Structure):                 # SYSTEM_PROCESS_INFORMATION (Anfang), natürliche Ausrichtung
    _fields_ = [("NextEntryOffset", ctypes.c_ulong), ("NumberOfThreads", ctypes.c_ulong), ("WorkingSetPrivateSize", ctypes.c_longlong),
                ("HardFaultCount", ctypes.c_ulong), ("NumberOfThreadsHighWatermark", ctypes.c_ulong), ("CycleTime", ctypes.c_ulonglong),
                ("CreateTime", ctypes.c_longlong), ("UserTime", ctypes.c_longlong), ("KernelTime", ctypes.c_longlong),
                ("ImageName", _Text), ("BasePriority", ctypes.c_long), ("UniqueProcessId", ctypes.c_void_p),
                ("InheritedFromUniqueProcessId", ctypes.c_void_p), ("HandleCount", ctypes.c_ulong), ("SessionId", ctypes.c_ulong),
                ("UniqueProcessKey", ctypes.c_void_p), ("PeakVirtualSize", ctypes.c_size_t), ("VirtualSize", ctypes.c_size_t),
                ("PageFaultCount", ctypes.c_ulong), ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t)]


EPOCHE = datetime.datetime(1601, 1, 1, tzinfo=datetime.timezone.utc)


def prozesse():
    """Alle Prozesse des Rechners: [{"pid", "eltern", "name", "gb", "seit"}] – Name ohne „.exe“, gb = Arbeitsspeicher,
    seit = Startzeit (UTC). Leere Liste, wenn sich die Liste nicht lesen lässt (anderes System, Fehler)."""
    if os.name != "nt":
        return []
    try:
        abfrage = ctypes.WinDLL("ntdll").NtQuerySystemInformation
        abfrage.restype = ctypes.c_long
        abfrage.argtypes = [ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)]
        groesse = ctypes.c_ulong(1 << 20)
        for _ in range(8):
            puffer = ctypes.create_string_buffer(groesse.value)
            status = abfrage(5, puffer, groesse.value, ctypes.byref(groesse))        # 5 = Prozessliste
            if status == 0:
                break
            if status & 0xFFFFFFFF != 0xC0000004:                                    # etwas anderes als „Puffer zu klein“
                return []
            groesse = ctypes.c_ulong(groesse.value + (1 << 17))
        else:
            return []
        aus, stelle, ende = [], 0, len(puffer) - ctypes.sizeof(_Prozess)
        while 0 <= stelle <= ende:
            p = _Prozess.from_buffer(puffer, stelle)
            name = ctypes.wstring_at(p.ImageName.Buffer, p.ImageName.Length // 2) if p.ImageName.Buffer and p.ImageName.Length else ""
            if name.lower().endswith(".exe"):
                name = name[:-4]
            aus.append({"pid": p.UniqueProcessId or 0, "eltern": p.InheritedFromUniqueProcessId or 0, "name": name,
                        "gb": p.WorkingSetSize / 1024 ** 3,
                        "seit": EPOCHE + datetime.timedelta(microseconds=p.CreateTime // 10) if p.CreateTime > 0 else None})
            if not p.NextEntryOffset:
                break
            stelle += p.NextEntryOffset
        return aus
    except (OSError, ValueError, AttributeError):
        return []


# --- Prozesse der Läufe aus der Warteschlange (zählen nicht als Dauer-Belegung) ---------------------------------------

def _ordner():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "amw", "laeufe")


def lauf_merken(lid, prozess_id):
    """„amw lauf ausfuehren“ hat für Lauf lid diesen Prozess gestartet. Fehler hier dürfen den Lauf nie stören."""
    try:
        os.makedirs(_ordner(), exist_ok=True)
        with open(os.path.join(_ordner(), f"{int(lid)}.pid"), "w", encoding="ascii") as f:
            f.write(str(int(prozess_id)))
    except (OSError, ValueError):
        pass


def lauf_vergessen(lid):
    try:
        os.remove(os.path.join(_ordner(), f"{int(lid)}.pid"))
    except (OSError, ValueError):
        pass


def lauf_pid(lid):
    """Der Prozess, den „amw lauf ausfuehren“ für Lauf lid gestartet hat – oder None (anders gestartet, schon vorbei)."""
    try:
        with open(os.path.join(_ordner(), f"{int(lid)}.pid"), encoding="ascii") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def baum_gb(liste, prozess_id):
    """Arbeitsspeicher eines Prozesses samt Kindern und Kindeskindern (GB) – None, wenn der Prozess nicht (mehr) da ist."""
    if not any(p["pid"] == prozess_id for p in liste):
        return None
    baum = _nachkommen(liste, [prozess_id])
    return sum(p["gb"] for p in liste if p["pid"] in baum)


def lauf_prozesse(laufende=None):
    """Prozess-Nummern der gemerkten Läufe. laufende: Nummern der Läufe, die noch laufen (andere Einträge sind
    Überbleibsel und zählen nicht); None = alle gemerkten."""
    aus = set()
    try:
        namen = os.listdir(_ordner())
    except OSError:
        return aus
    for n in namen:
        try:
            lid = int(n.rsplit(".", 1)[0])
            if laufende is None or lid in laufende:
                with open(os.path.join(_ordner(), n), encoding="ascii") as f:
                    aus.add(int(f.read().strip()))
        except (OSError, ValueError):
            pass
    return aus


def _nachkommen(liste, wurzeln):
    """Die Wurzel-Prozesse samt allen Kindern und Kindeskindern (Nummern)."""
    kinder = {}
    for p in liste:
        kinder.setdefault(p["eltern"], []).append(p["pid"])
    aus, offen = set(), [w for w in wurzeln if w]
    while offen:
        x = offen.pop()
        if x not in aus:
            aus.add(x)
            offen.extend(kinder.get(x, ()))
    return aus


def dauer(liste, ab_gb, jetzt=None, ohne=(), min_alter_s=MIN_ALTER_S):
    """Dauer-Verbraucher aus einer Prozessliste: je Programm {"name", "art", "gb", "seit_utc", "prozesse"}, größter zuerst.
    ohne: Prozess-Nummern der Läufe aus der Warteschlange (samt Kindern ausgenommen)."""
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    weg = _nachkommen(liste, ohne)
    gruppen = {}
    for p in liste:
        if p["pid"] in weg or p["name"].lower() in SYSTEM or not p["pid"] or p["gb"] < ab_gb:
            continue
        if not p["seit"] or (jetzt - p["seit"]).total_seconds() < min_alter_s:
            continue
        g = gruppen.setdefault(p["name"].lower(), {"name": p["name"], "gb": 0.0, "seit": None, "prozesse": 0})
        g["gb"] += p["gb"]
        g["prozesse"] += 1
        if p["seit"] and (g["seit"] is None or p["seit"] < g["seit"]):
            g["seit"] = p["seit"]
    aus = []
    for g in gruppen.values():
        if g["seit"]:
            aus.append({"name": g["name"], "art": art(g["name"]), "gb": round(g["gb"], 1),
                        "seit_utc": g["seit"].strftime("%Y-%m-%dT%H:%M:%SZ"), "prozesse": g["prozesse"]})
    return sorted(aus, key=lambda x: -x["gb"])


_gemerkt = [0.0, None, []]                         # (Zeitpunkt, Grenze, Ergebnis)


def aktuell(con=None, ab_gb=None):
    """Die Dauer-Verbraucher dieses Rechners jetzt (kurz gemerkt). Grenze 0 = ausgeschaltet."""
    from . import einstellungen
    ab = float(einstellungen.wert("dauer_ab_gb")) if ab_gb is None else ab_gb
    if ab <= 0:
        return []
    if _gemerkt[1] == ab and time.time() - _gemerkt[0] < MERKEN_S:
        return _gemerkt[2]
    laufende = None
    if con is not None:
        try:
            laufende = {r[0] for r in con.execute("SELECT id FROM lauf WHERE status = 'laeuft'")}
        except Exception:
            laufende = None
    _gemerkt[:] = [time.time(), ab, dauer(prozesse(), ab, ohne=lauf_prozesse(laufende))]
    return _gemerkt[2]


def nennen(liste, hoechstens=2):
    """Kurztext für Meldungen: „llama-server (16,4 GB, seit 14:02)“ – Zeiten in Ortszeit."""
    teile = []
    for x in liste[:hoechstens]:
        try:
            seit = datetime.datetime.strptime(x["seit_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).astimezone()
            wann = seit.strftime("%H:%M") if seit.date() == datetime.datetime.now().astimezone().date() else seit.strftime("%d.%m. %H:%M")
        except ValueError:
            wann = "?"
        teile.append(f"{x['name']} ({str(x['gb']).replace('.', ',')} GB, seit {wann})")
    return ", ".join(teile) + (f" und {len(liste) - hoechstens} weitere" if len(liste) > hoechstens else "")
