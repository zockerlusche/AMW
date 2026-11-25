"""A2035: langsame Anfragen der Workbench belegen – je Anfrage die Dauer; ab GRENZE_S eine Zeile in dienst.log mit Weg, Dauer
und den längsten Teilschritten.

Teilschritte (nur gezählt, solange in diesem Faden eine Anfrage gemessen wird – sonst kostet es nichts außer einer Abfrage):
- „DB öffnen“ und „DB-Sperre“: Warten in db.verbinde und db.schreiben (db._warten),
- „Aufruf <Programm>“: externe Programme über subprocess.run/check_output (git, tasklist, powershell, claude …),
- „Abgleich“: Abfragen beim Online-Speicher (workbench, Einstellungen).
Zeile (Logger amw.workbench, Stufe WARNING): „Langsame Anfrage GET /api/einstellungen: 17.3 s (200) – längste Teilschritte:
Aufruf git 15.9 s (3×), DB-Sperre 0.4 s“.

A2144, mit der Einstellung anfrage_zaehlen (am Anfang jeder Anfrage gelesen): dazu Projektnummer, Zahl und Zeit der Datenbank-Abfragen,
Schreibsperre, Rest (Rechnen) und die drei teuersten Abfragen. Gemessen wird das Ausführen und das Holen der Zeilen – SQLite rechnet
erst dabei. Was in „DB öffnen“ und „DB-Sperre“ läuft, zählt dort und nicht noch einmal als Datenbank. Eine Abfrage heißt nach ihren
Tabellen und der Funktion, die sie stellt; Werte und Texte kommen nie in die Zeile.
"""
import glob
import logging
import os
import re
import sqlite3
import statistics
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from typing import Any

GRENZE_S = 1.0
ZEIGEN = 3                                                # so viele Teilschritte (und Abfragen) stehen in der Zeile
TEIL_AB_S = 0.05                                          # gezählte Anfrage: kürzere Teilschritte stehen nicht in der Zeile
log = logging.getLogger("amw.workbench")
_lokal = threading.local()
_eingehaengt = False
_gelesen: Any = (None, False)                             # (Merkmal der Einstellungsdatei, Schalter): nur lesen, wenn sie sich ändert


def _schalter():
    global _gelesen
    from . import einstellungen
    pfad = einstellungen.pfad()
    try:
        st = os.stat(pfad)
        merkmal = (pfad, st.st_mtime_ns, st.st_size)
    except OSError:
        merkmal = (pfad, 0, 0)
    if _gelesen[0] != merkmal:
        _gelesen = (merkmal, einstellungen.wert("anfrage_zaehlen"))
    return _gelesen[1]


def start(weg):
    """sql: None = nicht zählen, sonst je SQL-Text [Zahl, Sekunden, Aufrufer]; tief, aussen: laufende Teilschritte, ihre Zeit zusammen."""
    _lokal.m = {"weg": weg, "t0": time.monotonic(), "teile": {}, "pid": None, "tief": 0, "aussen": 0.0, "n": 0, "bank": 0.0,
                "sql": {} if _schalter() else None}


def projekt(pid):
    m = getattr(_lokal, "m", None)
    if m is not None:
        m["pid"] = pid


def zaehlt():
    m = getattr(_lokal, "m", None)
    return m is not None and m["sql"] is not None


def teil(name, dauer):
    m = getattr(_lokal, "m", None)
    if m is not None:
        d, n = m["teile"].get(name, (0.0, 0))
        m["teile"][name] = (d + dauer, n + 1)


@contextmanager
def messen(name):
    m = getattr(_lokal, "m", None)
    if m is None:
        yield
        return
    t0 = time.monotonic()
    m["tief"] += 1
    try:
        yield
    finally:
        m["tief"] -= 1
        dauer = time.monotonic() - t0
        if not m["tief"]:
            m["aussen"] += dauer
        teil(name, dauer)


def ende(code=None, grenze=None):
    """Messung beenden; ab der Grenze die Zeile ins Log (und zurück), sonst None."""
    m = getattr(_lokal, "m", None)
    _lokal.m = None
    if m is None:
        return None
    dauer = time.monotonic() - m["t0"]
    if dauer < (GRENZE_S if grenze is None else grenze):
        return None
    gezaehlt = m["sql"] is not None
    teile = sorted((x for x in m["teile"].items() if not gezaehlt or x[1][0] >= TEIL_AB_S), key=lambda x: -x[1][0])[:ZEIGEN]
    zeile = (f"Langsame Anfrage {m['weg']}: {dauer:.1f} s" + (f" ({code})" if code is not None else "")
             + (" – " + _abfragen(m, dauer) if gezaehlt else "")
             + (" – längste Teilschritte: " + ", ".join(f"{name} {d:.1f} s" + (f" ({n}×)" if n > 1 else "") for name, (d, n) in teile)
                if teile else "" if gezaehlt else " – keine gemessenen Teilschritte (Rechnen in Python)"))
    log.warning(zeile)
    return zeile


# --- A2144: Abfragen zählen --------------------------------------------------------------------------------------------------

_HIER = os.path.dirname(os.path.abspath(__file__))
_EIGEN = {os.path.normcase(os.path.join(_HIER, n)) for n in ("db.py", "einmal.py", "anfragezeit.py")}
_uhr = time.perf_counter
_naechste = sqlite3.Cursor.__next__


def _aufrufer():
    """Code der Funktion, die die Abfrage stellt (Stapel nur einmal je SQL-Text und Anfrage)."""
    f = sys._getframe(2)
    while f is not None and (f.f_code.co_name.startswith("<") or os.path.normcase(f.f_code.co_filename) in _EIGEN):
        f = f.f_back
    return f.f_code if f is not None else None


class Zaehler(sqlite3.Cursor):
    """Cursor, der Zahl und Zeit je SQL-Text an die laufende Anfrage schreibt; verhält sich sonst wie der gewöhnliche."""
    _m: Any = None
    _e: Any = None

    def _neu(self, sql):
        m = getattr(_lokal, "m", None)
        if m is None or m["sql"] is None:                 # die Anfrage ist vorbei, der Cursor lebt noch
            self._m = self._e = None
            return
        m["n"] += 1
        e = m["sql"].get(sql)
        if e is None:
            e = m["sql"][sql] = [0, 0.0, _aufrufer()]
        e[0] += 1
        self._m, self._e = m, e

    def _dazu(self, t):
        m = self._m
        if m is not None and not m["tief"]:               # im Teilschritt (Öffnen, Sperre) zählt die Zeit dort
            d = _uhr() - t
            m["bank"] += d
            self._e[1] += d

    def execute(self, sql, *a):
        self._neu(sql)
        t = _uhr()
        try:
            return super().execute(sql, *a)
        finally:
            self._dazu(t)

    def executemany(self, sql, *a):
        self._neu(sql)
        t = _uhr()
        try:
            return super().executemany(sql, *a)
        finally:
            self._dazu(t)

    def fetchone(self):
        t = _uhr()
        try:
            return super().fetchone()
        finally:
            self._dazu(t)

    def fetchmany(self, *a, **kw):
        t = _uhr()
        try:
            return super().fetchmany(*a, **kw)
        finally:
            self._dazu(t)

    def fetchall(self):
        t = _uhr()
        try:
            return super().fetchall()
        finally:
            self._dazu(t)

    def __next__(self):
        t = _uhr()
        try:
            return _naechste(self)
        finally:
            self._dazu(t)


_LITERAL = re.compile(r"'(?:[^']|'')*'")
_TABELLE = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
_WORT = re.compile(r"[A-Za-z]+")


def _name(sql):
    """Tabellen einer Abfrage (höchstens drei), ohne Werte und Texte; ohne Tabelle das erste Wort (PRAGMA, BEGIN, COMMIT)."""
    tabellen = list(dict.fromkeys(_TABELLE.findall(_LITERAL.sub("", sql))))
    if tabellen:
        return ", ".join(tabellen[:3]) + (" …" if len(tabellen) > 3 else "")
    m = _WORT.search(sql)
    return m.group(0).upper() if m else "?"


def _wer(code):
    return f"{os.path.splitext(os.path.basename(code.co_filename))[0]}.{code.co_name}" if code is not None else "?"


def _abfragen(m, dauer):
    je = {}
    for sql, (n, s, code) in m["sql"].items():
        e = je.setdefault((_name(sql), _wer(code)), [0, 0.0])
        e[0] += n
        e[1] += s
    teuer = sorted(je.items(), key=lambda x: -x[1][1])[:ZEIGEN]
    rest = max(0.0, dauer - m["bank"] - m["aussen"])
    return ((f"Projekt {m['pid']}, " if m["pid"] else "") + f"{m['n']} Abfragen, Datenbank {m['bank']:.2f} s,"
            f" Schreibsperre {m['teile'].get('DB-Sperre', (0.0, 0))[0]:.2f} s, Rest (Rechnen) {rest:.2f} s"
            + (" – teuerste Abfragen: " + ", ".join(f"{t} {s:.2f} s ({n}×, {w})" for (t, w), (n, s) in teuer) if teuer else ""))


_ZEILE = re.compile(r"Langsame Anfrage (\S+ \S+): (\d+\.\d) s(?: \(\d+\))? – (?:(?:Projekt (\d+), )?(\d+) Abfragen, Datenbank (\S+) s,"
                    r" Schreibsperre (\S+) s, Rest \(Rechnen\) (\S+) s)?")


def zusammenfassen(ordner, zeilen=50):
    """Aus dienst.log (samt älteren): je Weg und Projekt Mediane der neuesten `zeilen` langsamen Anfragen, die langsamste Ansicht zuerst.
    Zeilen ohne Zahlen (älter oder Zählen aus): projekt und abfragen None, nur die Dauer."""
    je = {}
    namen = [p for p in glob.glob(os.path.join(glob.escape(ordner), "dienst.log*")) if re.fullmatch(r"dienst\.log(\.\d+)?", os.path.basename(p))]
    for p in sorted(namen, key=lambda p: -int((p.rsplit("log", 1)[1] or ".0")[1:])):    # .3 ist die älteste
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                for m in filter(None, map(_ZEILE.search, f)):
                    weg, dauer, pid, n, bank, sperre, rest = m.groups()
                    zahlen = None if n is None else (int(n), float(bank), float(sperre), float(rest))
                    je.setdefault((weg, int(pid) if pid else None, zahlen is not None), []).append((float(dauer), zahlen))
        except OSError:
            continue
    aus = []
    for (weg, pid, mit), werte in je.items():
        werte = werte[-zeilen:]
        med = [statistics.median(w[1][i] for w in werte) for i in range(4)] if mit else [None] * 4
        aus.append({"weg": weg, "projekt": pid, "n": len(werte), "dauer": statistics.median(w[0] for w in werte),
                    "abfragen": med[0], "bank": med[1], "sperre": med[2], "rest": med[3]})
    return sorted(aus, key=lambda x: -x["dauer"])


# --- Externe Programme -------------------------------------------------------------------------------------------------------

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
