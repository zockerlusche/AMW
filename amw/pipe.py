"""Zustellen einer Nachricht in die Pipe einer Claude-Code-Sitzung (→ doc/06 §8 P2, Probe 01.11.2026).

Protokoll (Claude Code 2.1.309, nicht dokumentiert, aus dem Programm gelesen):
  Zeile 1: {"type":"auth","token":"<CLAUDE_CODE_MESSAGING_TOKEN>"}   – unter Windows Pflicht
  Zeile 2: {"type":"user","message":{"role":"user","content":"<Text>"}}
Die Pipe antwortet nicht. Verbindung erst öffnen, wenn alles fertig ist (Claude Code schließt nach 30 s ohne Zeile).
Hier wird nur geschrieben, nie gelesen: unter Windows blockiert ein hängendes Lesen das Schließen des Handles.
"""
import json
import os


class ZustellFehler(Exception):
    pass


def senden(pipe, schluessel, text):
    daten = (json.dumps({"type": "auth", "token": schluessel}) + "\n"
             + json.dumps({"type": "user", "message": {"role": "user", "content": text}}, ensure_ascii=False) + "\n")
    try:
        with open(pipe, "wb", buffering=0) as f:
            f.write(daten.encode("utf-8"))
    except OSError as e:          # Sitzung beendet → Pipe fehlt; ausgelastet → ERROR_PIPE_BUSY
        raise ZustellFehler(f"{type(e).__name__}: {e.strerror or e}") from None


def lebt(pipe):
    """Gibt es die Pipe noch? Öffnet KEINE Verbindung (sonst protokolliert die Sitzung eine stumme Verbindung)."""
    try:
        name = pipe.split("\\pipe\\", 1)[1]
    except IndexError:
        return False
    try:
        return name in os.listdir("\\\\.\\pipe\\")   # Einträge heißen z. B. LOCAL\cc-msg-<32 hex>
    except OSError:
        return False
