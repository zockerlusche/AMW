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


def _dezimal(lo, hi):
    def pruefe(v):
        v = round(float(v), 1)
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


def _kennung_leer(v):
    """Kennung oder leer (= aus)."""
    v = str(v or "").strip()
    return _kennung(v) if v else ""


def _kennung(v):
    v = str(v).strip()
    if not v or len(v) > 20 or not all(c.isalnum() or c in "-_" for c in v):
        raise ValueError("Kennung eines Agenten (Buchstaben, Ziffern, - _)")
    return v


def _fenster(v):
    """Uhrzeit-Fenster „22-06“ oder „21:30-05:45“ (Ortszeit, darf über Mitternacht gehen); leer = kein Fenster."""
    v = str(v or "").strip().replace("–", "-").replace(" ", "")
    if not v:
        return ""
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?-(\d{1,2})(?::(\d{2}))?", v)
    if not m:
        raise ValueError("Fenster wie 22-06 oder 21:30-05:45 (leer = keins)")
    a, b = (int(m[1]), int(m[2] or 0)), (int(m[3]), int(m[4] or 0))
    if any(h > 24 or mi > 59 or (h == 24 and mi) for h, mi in (a, b)) or a == b:
        raise ValueError("Uhrzeiten 0–24, Anfang ≠ Ende")
    return f"{a[0]:02d}:{a[1]:02d}-{b[0]:02d}:{b[1]:02d}"


def _sprache(v):
    v = str(v).strip().lower()
    if v not in ("auto", "de", "en"):
        raise ValueError("auto, de oder en")
    return v


def _betriebsart(v):
    v = str(v or "").strip().lower()
    if v not in ("", "pc", "server", "cloud"):
        raise ValueError("pc, server oder cloud (leer = nicht gewählt)")
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
    "cpu_laeufe": (2, _ganz(1, 8)),
    # so viel Arbeitsspeicher bleibt frei, bevor die Warteschlange einen schweren Lauf einlässt (für den Menschen am Rechner)
    "speicher_reserve_gb": (3.0, _dezimal(0, 64)),
    "platte_gelb_prozent": (15.0, _dezimal(0, 100)),   # Laufwerk: darunter Warnung …
    "platte_rot_prozent": (5.0, _dezimal(0, 100)),     # … und darunter dringend
    "sicherungen_behalten": (10, _ganz(1, 1000)),      # so viele neueste Sicherungen bleiben; ältere sind Aufräumvorschläge
    "dauer_ab_gb": (4.0, _dezimal(0, 256)),   # Programme außerhalb der Warteschlange ab so viel Arbeitsspeicher zeigen (0 = aus)
    # schwere Befehle (Test-Suite, Build …) abweisen und über die Warteschlange schicken (Hook in den Agenten-Ordnern)
    "lauf_hook": (True, _wahr),               # schwere Läufe ohne Fenster/Grafikkarte zugleich (Lauf-Schlange, Spur CPU)
    "statusline_weiter": ("", _befehl),            # bisherige Statusline, die amw-statusline.py weiterreicht
    "claude_befehl": ("claude", _befehl),          # Claude Code starten (falls anders installiert: voller Pfad)
    # Schirm: dieses Programm läuft nur während einer Fernsitzung (Fernwartungs-Werkzeug) – leer = nicht prüfen
    "fernsitzung_prozess": ("", _prozess),
    # Name dieses Rechners in der Projekt-Auswahl (mehrere Rechner an einem Online-Speicher, doc/plan-projektwahl.md)
    "rechner": ((socket.gethostname() or "PC")[:40], _name),
    # Entwickler-Kanal: dieser Agent entwickelt die AMW selbst und spricht mit den Leads aller Projekte – er darf in
    # jedem Projekt schreiben und angeschrieben werden, `amw lesen` zeigt ihm alle Projekte (leer = aus)
    "produkt_entwickler": ("", _kennung_leer),
    # KI-Fenster (Ortszeit): KI-Aufträge mit --nachts starten nur darin, nie in der Vorlaufzeit eines Testtermins
    "ki_fenster": ("22:00-06:00", _fenster),
    # Sprache der Oberfläche, solange im Browser nichts gewählt ist (auto = wie der Browser)
    "sprache": ("auto", _sprache),
    # Knopf „In Claude öffnen“ auf der Agenten-Seite (Link zu claude.ai für eine laufende Sitzung mit Fernsteuerung)
    "claude_link": (True, _wahr),
    # Betriebsart (amw/betriebsart.py): pc | server | cloud; leer = nicht gewählt, dann gilt, was bisher lief
    "betriebsart": ("", _betriebsart),
}
# Diese Werte liest der Wächter nur beim Start – eine Änderung wirkt nach `amw dienst neustart`
NEUSTART = ("db_pfad", "port", "aufsicht_s", "abgleich_hoch_s", "abgleich_puls_s", "abgleich_eingang_s",
            "bruecke_an", "bruecke_absender", "bruecke_kopie_s")


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
