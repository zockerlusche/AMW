"""Schlüssel je Projekt für den MCP-Server (A1826, Marcel 16.11. 17:01).

Vorfall 16.11.: Der GlassWorld-Lead konnte über den Connector „amw“ (gestartet für AMW/TL) das AMW-Postfach lesen – in der
Claude-App ist jeder eingetragene Connector in jedem Chat wählbar. Ein Projektname als Pflichtfeld wäre fälschbar. Darum:
Jedes Projekt hat einen geheimen Schlüssel. Gespeichert wird nur sein Hash (mit Salz) – in einer Datei dieses PCs außerhalb
von Repository und Datenbank (%LOCALAPPDATA%\\amw\\mcp\\<projekt>.schluessel). Den Klartext sieht nur der Mensch, genau
einmal beim Erzeugen; er trägt ihn in die Projekt-Anweisungen des Lead-Chats ein. Jedes Werkzeug verlangt ihn.
"""
import datetime
import hashlib
import hmac
import json
import os
import re
import secrets


def ordner():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "amw", "mcp")


def pfad(projekt):
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", str(projekt or "").strip())[:60] or "_"
    return os.path.join(ordner(), f"{name}.schluessel")


def _hash(salz, schluessel):
    return hashlib.sha256((salz + ":" + schluessel).encode("utf-8")).hexdigest()


def erzeugen(projekt):
    """Neuer Schlüssel für das Projekt (ersetzt einen alten). Rückgabe: der Klartext – einmal, nirgends gespeichert."""
    schluessel = "amw-" + secrets.token_urlsafe(18)
    salz = secrets.token_hex(16)
    os.makedirs(ordner(), exist_ok=True)
    tmp = pfad(projekt) + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"projekt": projekt, "salz": salz, "hash": _hash(salz, schluessel),
                   "erzeugt_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}, f)
    os.replace(tmp, pfad(projekt))
    return schluessel


def stand(projekt):
    """{"da": bool, "erzeugt_utc": …} – ohne Hash und Salz."""
    try:
        with open(pfad(projekt), encoding="utf-8") as f:
            d = json.load(f)
        return {"da": bool(d.get("hash")), "erzeugt_utc": d.get("erzeugt_utc")}
    except (OSError, ValueError):
        return {"da": False, "erzeugt_utc": None}


def pruefen(projekt, schluessel):
    """Stimmt der Schlüssel? (Vergleich in konstanter Zeit; ohne gespeicherten Schlüssel nie.)"""
    if not isinstance(schluessel, str) or not schluessel:
        return False
    try:
        with open(pfad(projekt), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return False
    if not d.get("hash") or not d.get("salz"):
        return False
    return hmac.compare_digest(d["hash"], _hash(d["salz"], schluessel))


def eintrag(projekt, lead, wurzel=None):
    """Die fertige Zeile für claude_desktop_config.json (unter mcpServers) – ohne Schlüssel."""
    wurzel = (wurzel or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).replace("\\", "/")
    name = "amw-" + re.sub(r"[^a-z0-9]+", "-", str(projekt).lower()).strip("-")
    return (f'"{name}": {{"command": "python", "args": ["{wurzel}/amw-mcp.py", "--projekt", {json.dumps(projekt, ensure_ascii=False)},'
            f' "--von", {json.dumps(lead, ensure_ascii=False)}]}}')
