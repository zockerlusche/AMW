"""Einstellungen dieses PCs (→ doc/installation.md): Datenbank-Pfad, Port, Takte des Wächters, Brücke.

Datei: %LOCALAPPDATA%\\amw\\einstellungen.json (je Windows-Benutzer, nie im Repo; der Turso-Zugang liegt getrennt in
turso.json). Fehlt ein Wert, gilt die Vorgabe unten. Die Umgebungsvariable AMW_DB geht dem Datenbank-Pfad vor (Tests).
Projekt- und Agenten-Einstellungen liegen in der Datenbank (projekt.einstellungen, Tabelle agent), die der Online-Seite
im Online-Speicher (zustand „web_einstellungen“). Änderungen hier wirken beim nächsten Start des Wächters.
Kein Import von db – db fragt hier nach dem Pfad.
"""
import json
import os
import re
import socket

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Schlüssel → (Vorgabe, Prüfung). Die Prüfung gibt den bereinigten Wert zurück oder wirft ValueError.
def _ganz(lo, hi):
    def pruefe(v):
        v = int(v)
        if not lo <= v <= hi:
            raise ValueError(f"muss zwischen {lo} und {hi} liegen")
        return v
    return pruefe


def _pfad(v):
    v = str(v).strip()
    if not v.lower().endswith(".db") or not os.path.isabs(v):
        raise ValueError("vollständiger Pfad zu einer .db-Datei")
    if not os.path.isdir(os.path.dirname(v)):
        raise ValueError(f"Ordner gibt es nicht: {os.path.dirname(v)}")
    return v


def _wahr(v):
    if isinstance(v, bool):
        return v
    if str(v).lower() in ("1", "true", "ja", "an", "on"):
        return True
    if str(v).lower() in ("0", "false", "nein", "aus", "off", ""):
        return False
    raise ValueError("an oder aus")


def _befehl(v):
    v = str(v).strip()
    if len(v) > 500 or "\n" in v:
        raise ValueError("ein Befehl in einer Zeile (bis 500 Zeichen)")
    return v


def _prozess(v):
    v = str(v or "").strip().lower()
    if v and not re.fullmatch(r"[a-z0-9_.\- ]{1,60}\.exe", v):
        raise ValueError("Programmname wie fernwartung.exe (leer = aus)")
    return v


def _name(v):
    v = " ".join(str(v or "").split())
    if not 1 <= len(v) <= 40:
        raise ValueError("1 bis 40 Zeichen")
    return v


def _kennung(v):
    v = str(v).strip()
    if not v or len(v) > 20 or not all(c.isalnum() or c in "-_" for c in v):
        raise ValueError("Kennung eines Agenten (Buchstaben, Ziffern, - _)")
    return v


FELDER = {
    "db_pfad": (os.path.join(WURZEL, "daten", "amw.db"), _pfad),
    "port": (8780, _ganz(1024, 65535)),
    "aufsicht_s": (30, _ganz(5, 600)),
    "abgleich_hoch_s": (30, _ganz(10, 3600)),
    "abgleich_puls_s": (300, _ganz(60, 3600)),
    "abgleich_eingang_s": (15, _ganz(5, 600)),
    "bruecke_an": (False, _wahr),           # Datei-Brücke für einen Agenten ohne direkten DB-Zugriff
    "bruecke_absender": ("TL", _kennung),
    "bruecke_kopie_s": (60, _ganz(15, 3600)),
    "statusline_weiter": ("", _befehl),            # bisherige Statusline, die amw-statusline.py weiterreicht
    "claude_befehl": ("claude", _befehl),          # Claude Code starten (falls anders installiert: voller Pfad)
    # Schirm: dieses Programm läuft nur während einer Fernsitzung (Fernwartungs-Werkzeug) – leer = nicht prüfen
    "fernsitzung_prozess": ("", _prozess),
    # Name dieses Rechners in der Projekt-Auswahl (mehrere Rechner an einem Online-Speicher, doc/plan-projektwahl.md)
    "rechner": ((socket.gethostname() or "PC")[:40], _name),
}


def pfad():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "amw", "einstellungen.json")


def _datei():
    try:
        with open(pfad(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def laden():
    """Alle Werte: aus der Datei, sonst Vorgabe (ungültige Werte in der Datei fallen auf die Vorgabe zurück)."""
    d = _datei()
    aus = {}
    for k, (vorgabe, pruefe) in FELDER.items():
        try:
            aus[k] = pruefe(d[k]) if k in d else vorgabe
        except (ValueError, TypeError):
            aus[k] = vorgabe
    return aus


def wert(schluessel):
    return laden()[schluessel]


def speichern(neu):
    """Prüft und speichert nur bekannte Schlüssel; gibt die gespeicherten Werte zurück. Wirft ValueError mit Feldnamen."""
    d = _datei()
    for k, v in neu.items():
        if k not in FELDER:
            raise ValueError(f"unbekannte Einstellung: {k}")
        try:
            d[k] = FELDER[k][1](v)
        except (ValueError, TypeError) as e:
            raise ValueError(f"{k}: {e}") from None
    os.makedirs(os.path.dirname(pfad()), exist_ok=True)
    tmp = pfad() + ".neu"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, pfad())
    return {k: d[k] for k in neu}
