"""Herzschlag je Strang des Dienstes, Aufpasser und Gesundheit (A1655, B47).

Stränge: die Hauptschleife (Zustellen, Aufsicht mit Warteschlange und Laufdienst) und die Fäden Dateiaustausch,
Synchronisierung und KI-Arbeiter. Jeder meldet je Runde einen Herzschlag: Zeit, Dauer der Runde, letzter Fehler, Zahl der
Runden. Die Herzschläge liegen im Speicher des Dienstes; der Aufpasser schreibt sie alle AUFPASSER_S Sekunden nach
daten/dienst-herzschlag.json (so sieht sie auch ein anderer Prozess) – je Runde in die Datenbank zu schreiben wäre selbst
eine Last.

Aufpasser: Ist ein Faden länger als seine Grenze still, startet er eine neue Instanz (der alte Faden bekommt sein
Stop-Zeichen und beendet sich, falls er je aufwacht – einen Python-Faden kann man nicht töten) und meldet es dem Menschen
einmal je Vorfall. Die Hauptschleife kann er nicht ersetzen, den KI-Arbeiter ersetzt er nicht (ein zweiter nähme den
laufenden Auftrag noch einmal) – dann nur Meldung und rot. Lange Runden melden zwischendurch ein Lebenszeichen (lebt).

Gesundheit je Teil: grün (Herzschlag jünger als die Grenze, letzte Runde ohne Fehler), gelb (älter als die Grenze, letzte
Runde mit Fehler, oder in der letzten Stunde neu gestartet), rot (älter als 3× die Grenze) – „aus“, wenn der Teil in
diesem Dienst nicht läuft (z. B. Synchronisierung ohne Online-Speicher).
"""
import json
import logging
import os
import threading
import time

from . import db

log = logging.getLogger("amw.herzschlag")

# Teil → (Name für Menschen, Grenze in Sekunden). Der KI-Arbeiter rechnet Aufträge in seiner Runde – darum großzügig.
TEILE = {"hauptschleife": ("Hauptschleife (Benachrichtigen, Aufsicht, Warteschlange)", 180),
         "dateiaustausch": ("Dateiaustausch", 300),
         "synchronisierung": ("Synchronisierung mit dem Online-Speicher", 900),
         "ki": ("KI-Arbeiter", 1800)}
AUFPASSER_S = 10
NEU_GELB_S = 3600

_sperre = threading.Lock()
_stand = {}
_straenge = {}
_gemeldet = set()


def pfad():
    return os.path.join(os.path.dirname(db.db_pfad()), "dienst-herzschlag.json")


def schlag(teil, dauer_s=None, fehler=None):
    """Ein Herzschlag am Ende einer Runde. fehler: die Runde ging schief (wird angezeigt, der Strang lebt trotzdem)."""
    with _sperre:
        e = _stand.setdefault(teil, {"runden": 0, "neustarts": 0})
        e["zeit"] = time.time()
        e["runden"] += 1
        e["dauer_s"] = round(dauer_s, 3) if dauer_s is not None else e.get("dauer_s")
        e["fehler"] = f"{type(fehler).__name__}: {fehler}"[:300] if fehler else None
        if fehler:
            e["fehler_zeit"] = time.time()


def lebt(teil):
    """Lebenszeichen mitten in einer langen Runde (je Befehlsdatei, während ein KI-Auftrag rechnet): setzt nur die Zeit."""
    with _sperre:
        _stand.setdefault(teil, {"runden": 0, "neustarts": 0})["zeit"] = time.time()


class Runde:
    """with herzschlag.Runde("dateiaustausch"): … – misst die Runde und schlägt am Ende (auch bei Fehler, der weiterfliegt)."""

    def __init__(self, teil):
        self.teil = teil

    def __enter__(self):
        self.t0 = time.time()
        return self

    def __exit__(self, art, fehler, _):
        schlag(self.teil, time.time() - self.t0, fehler)
        return False


class Strang:
    """Ein Faden, den der Aufpasser bei Stillstand ersetzen kann. ziel(stop=Event) ist die Schleife des Fadens."""

    def __init__(self, teil, ziel, ersetzbar=True):
        self.teil, self.ziel, self.stop, self.faden, self.ersetzbar = teil, ziel, None, None, ersetzbar

    def starten(self):
        self.stop = threading.Event()
        stop = self.stop
        self.faden = threading.Thread(target=lambda: self.ziel(stop=stop), name=self.teil, daemon=True)
        self.faden.start()
        with _sperre:
            _stand.setdefault(self.teil, {"runden": 0, "neustarts": 0})["gestartet"] = time.time()
        return self

    def ersetzen(self):
        if self.stop:
            self.stop.set()
        with _sperre:
            e = _stand.setdefault(self.teil, {"runden": 0, "neustarts": 0})
            e["neustarts"] += 1
            e["neu_zeit"] = time.time()
        return self.starten()


def strang(teil, ziel, ersetzbar=True):
    """Faden anmelden und starten (statt threading.Thread im Dienst). ersetzbar=False: der Aufpasser meldet nur – für den
    KI-Arbeiter, denn ein zweiter nähme den laufenden Auftrag noch einmal (er endet spätestens mit seiner Frist)."""
    s = Strang(teil, ziel, ersetzbar).starten()
    _straenge[teil] = s
    return s


def _alter(e, jetzt):
    seit = e.get("zeit") or e.get("gestartet")
    return None if seit is None else jetzt - seit


def zustand(teil, e, jetzt):
    """grün | gelb | rot | aus"""
    if not e:
        return "aus"
    grenze = TEILE.get(teil, ("", 300))[1]
    alter = _alter(e, jetzt)
    if alter is None or alter > 3 * grenze:
        return "rot"
    if alter > grenze or e.get("fehler") or (e.get("neu_zeit") and jetzt - e["neu_zeit"] < NEU_GELB_S):
        return "gelb"
    return "gruen"


def aufpassen(melden=None, jetzt=None):
    """Eine Runde des Aufpassers: Datei schreiben, stille Fäden ersetzen, einmal je Vorfall melden. Rückgabe: Ereignisse."""
    jetzt = time.time() if jetzt is None else jetzt
    aus = []
    for teil, (name, grenze) in TEILE.items():
        with _sperre:
            e = dict(_stand.get(teil) or {})
        alter = _alter(e, jetzt) if e else None
        if alter is None or alter <= grenze:
            _gemeldet.discard(teil)                     # wieder gesund: ein neuer Vorfall wird wieder gemeldet
            continue
        if teil in _straenge and _straenge[teil].ersetzbar:
            _straenge[teil].ersetzen()
            text = f"{name} war {int(alter)} s still (Grenze {grenze} s) – neu gestartet"
        else:
            text = f"{name} ist {int(alter)} s still (Grenze {grenze} s) – kann nur ein Neustart des Dienstes beheben"
        log.warning("Aufpasser: %s", text)
        aus.append(text)
        if teil not in _gemeldet and melden:
            _gemeldet.add(teil)
            try:
                melden(text)
            except Exception as x:                       # Melden darf den Aufpasser nie anhalten
                log.warning("Aufpasser: Meldung fehlgeschlagen: %s", x)
    _schreiben(jetzt)
    return aus


def _schreiben(jetzt):
    with _sperre:
        inhalt = {"pid": os.getpid(), "geschrieben": jetzt, "teile": {k: dict(v) for k, v in _stand.items()}}
    neu = pfad() + ".neu"
    try:
        with open(neu, "w", encoding="utf-8") as f:
            json.dump(inhalt, f)
        os.replace(neu, pfad())
    except OSError as x:
        log.warning("Herzschlag-Datei: %s", x)


def aufpasser_starten(melden=None):
    def lauf():
        while True:
            try:
                aufpassen(melden)
            except Exception as x:                       # noqa: BLE001 – nie sterben
                log.warning("Aufpasser: %s: %s", type(x).__name__, x)
            time.sleep(AUFPASSER_S)
    f = threading.Thread(target=lauf, name="aufpasser", daemon=True)
    f.start()
    return f


def gesundheit(jetzt=None):
    """Für Betrieb und Startseite: je Teil Zustand, Alter des letzten Herzschlags, Dauer, Fehler, Neustarts. Aus diesem
    Prozess (läuft der Dienst hier), sonst aus der Datei; ist auch die alt, steht der ganze Dienst."""
    jetzt = time.time() if jetzt is None else jetzt
    with _sperre:
        teile = {k: dict(v) for k, v in _stand.items()}
    quelle = "dienst"
    if not teile:
        try:
            with open(pfad(), encoding="utf-8") as f:
                d = json.load(f)
            teile, quelle = d.get("teile") or {}, "datei"
            if jetzt - d.get("geschrieben", 0) > 3 * AUFPASSER_S + 60:
                quelle = "alt"                           # der Aufpasser schreibt nicht mehr: Dienst steht oder ist aus
        except (OSError, ValueError):
            teile, quelle = {}, "keine"
    aus = []
    for teil, (name, grenze) in TEILE.items():
        e = teile.get(teil)
        z = "rot" if quelle == "alt" and e else zustand(teil, e, jetzt)
        alter = _alter(e, jetzt) if e else None
        aus.append({"teil": teil, "name": name, "zustand": z, "grenze_s": grenze, "alter_s": None if alter is None else int(alter),
                    "dauer_s": (e or {}).get("dauer_s"), "fehler": (e or {}).get("fehler"), "neustarts": (e or {}).get("neustarts", 0),
                    "runden": (e or {}).get("runden", 0)})
    return {"quelle": quelle, "teile": aus}


def _zuruecksetzen():
    """Nur für Tests."""
    with _sperre:
        _stand.clear()
    _straenge.clear()
    _gemeldet.clear()
