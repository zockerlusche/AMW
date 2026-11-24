"""A2035: langsame Anfragen der Workbench belegen – je Anfrage die Dauer; ab GRENZE_S eine Zeile in dienst.log mit Weg, Dauer
und den längsten Teilschritten.

Teilschritte (nur gezählt, solange in diesem Faden eine Anfrage gemessen wird – sonst kostet es nichts außer einer Abfrage):
- „DB öffnen“ und „DB-Sperre“: Warten in db.verbinde und db.schreiben (db._warten),
- „Aufruf <Programm>“: externe Programme über subprocess.run/check_output (git, tasklist, powershell, claude …),
- „Abgleich“: Abfragen beim Online-Speicher (workbench, Einstellungen).
Zeile (Logger amw.workbench, Stufe WARNING): „Langsame Anfrage GET /api/einstellungen: 17.3 s (200) – längste Teilschritte:
Aufruf git 15.9 s (3×), DB-Sperre 0.4 s“.
"""
import logging
import os
import subprocess
import threading
import time
from contextlib import contextmanager

GRENZE_S = 1.0
ZEIGEN = 3                                                # so viele Teilschritte stehen in der Zeile
log = logging.getLogger("amw.workbench")
_lokal = threading.local()
_eingehaengt = False


def start(weg):
    _lokal.m = {"weg": weg, "t0": time.monotonic(), "teile": {}}


def teil(name, dauer):
    m = getattr(_lokal, "m", None)
    if m is not None:
        d, n = m["teile"].get(name, (0.0, 0))
        m["teile"][name] = (d + dauer, n + 1)


@contextmanager
def messen(name):
    if getattr(_lokal, "m", None) is None:
        yield
        return
    t0 = time.monotonic()
    try:
        yield
    finally:
        teil(name, time.monotonic() - t0)


def ende(code=None, grenze=None):
    """Messung beenden; ab der Grenze die Zeile ins Log (und zurück), sonst None."""
    m = getattr(_lokal, "m", None)
    _lokal.m = None
    if m is None:
        return None
    dauer = time.monotonic() - m["t0"]
    if dauer < (GRENZE_S if grenze is None else grenze):
        return None
    teile = sorted(m["teile"].items(), key=lambda x: -x[1][0])[:ZEIGEN]
    zeile = (f"Langsame Anfrage {m['weg']}: {dauer:.1f} s" + (f" ({code})" if code is not None else "")
             + (" – längste Teilschritte: " + ", ".join(f"{name} {d:.1f} s" + (f" ({n}×)" if n > 1 else "") for name, (d, n) in teile)
                if teile else " – keine gemessenen Teilschritte (Rechnen in Python)"))
    log.warning(zeile)
    return zeile


def _programm(args, kw):
    a = args[0] if args else kw.get("args")
    erstes = a if isinstance(a, str) else (a[0] if a else "")
    erstes = str(erstes).strip().strip('"').split()[0] if str(erstes).strip() else "?"
    return os.path.splitext(os.path.basename(erstes))[0] or "?"


def einhaengen():
    """subprocess.run und check_output zählen „Aufruf <Programm>“ mit – einmal je Prozess, verhält sich sonst unverändert."""
    global _eingehaengt
    if _eingehaengt:
        return
    _eingehaengt = True
    for name in ("run", "check_output"):
        echt = getattr(subprocess, name)

        def huelle(*args, _echt=echt, **kw):
            if getattr(_lokal, "m", None) is None or getattr(_lokal, "drin", False):   # check_output ruft run: einmal zählen
                return _echt(*args, **kw)
            _lokal.drin = True
            try:
                with messen(f"Aufruf {_programm(args, kw)}"):
                    return _echt(*args, **kw)
            finally:
                _lokal.drin = False
        huelle.__wrapped__ = echt
        setattr(subprocess, name, huelle)
