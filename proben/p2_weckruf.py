"""Probe P2 (AMW Stufe 0): Nachricht über die Named Pipe einer Claude-Code-Sitzung zustellen.

Liest Pipe-Pfad und Schlüssel aus CLAUDE_CODE_MESSAGING_SOCKET / _TOKEN (oder --pipe / --schluessel-datei),
schickt die Auth-Zeile und danach eine Nachrichten-Zeile, protokolliert jede Antwort der Pipe.
Der Schlüssel wird nie ausgegeben. Nur Standardbibliothek, nur Windows.

Aufruf:  python p2_weckruf.py --text "…" [--form N] [--warte 3]
"""
import argparse
import json
import os
import sys
import threading
import time

FORMEN = [  # Form 0 = Rezept aus claude.exe 2.1.309 („[uds-messaging] Inject messages …“); 1–4 = frühere Versuche ohne Wirkung
    lambda t: {"type": "user", "message": {"role": "user", "content": t}},
    lambda t: {"type": "message", "text": t},
    lambda t: {"type": "message", "from": "amw-probe", "text": t},
    lambda t: {"type": "message", "content": t},
    lambda t: {"type": "peer_message", "text": t},
]


def lies(f, ausgabe, halt):
    while not halt.is_set():
        try:
            z = f.readline()
        except OSError as e:
            ausgabe.append(f"<lesefehler {e}>")
            return
        if not z:
            ausgabe.append("<pipe geschlossen>")
            return
        ausgabe.append(z.decode("utf-8", "replace").rstrip())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--text", required=True)
    p.add_argument("--form", type=int, default=0)
    p.add_argument("--warte", type=float, default=3.0)
    p.add_argument("--pipe")
    p.add_argument("--schluessel-datei")
    a = p.parse_args()
    pipe = a.pipe or os.environ.get("CLAUDE_CODE_MESSAGING_SOCKET")
    if a.schluessel_datei:
        with open(a.schluessel_datei, encoding="utf-8") as f:
            schluessel = f.read().strip()
    else:
        schluessel = os.environ.get("CLAUDE_CODE_MESSAGING_TOKEN")
    if not pipe or not schluessel:
        sys.exit("FEHLER: Pipe oder Schlüssel fehlt")
    zeilen = [json.dumps({"type": "auth", "token": schluessel}), json.dumps(FORMEN[a.form](a.text), ensure_ascii=False)]
    # Windows: synchrones Pipe-Handle – gleichzeitiges Lesen (Thread) und Schreiben blockiert sich gegenseitig.
    # Darum erst alles schreiben, dann (mit Frist) lesen.
    ausgabe, halt = [], threading.Event()
    print("öffne Pipe …", flush=True)
    f = open(pipe, "r+b", buffering=0)
    print("offen, schreibe …", flush=True)
    f.write(("\n".join(zeilen) + "\n").encode("utf-8"))
    print(f"gesendet: <auth> + {zeilen[1]}", flush=True)
    t = threading.Thread(target=lies, args=(f, ausgabe, halt), daemon=True)
    t.start()
    t.join(a.warte)
    halt.set()
    if t.is_alive():
        ausgabe.append(f"<nach {a.warte} s keine weitere Zeile>")
    print("Antworten der Pipe:" if ausgabe else "keine Antwort der Pipe", flush=True)
    for z in ausgabe:
        print("  " + z.replace(schluessel, "<schluessel>"), flush=True)
    os._exit(0)  # Schließen eines Handles mit hängendem ReadFile blockiert unter Windows – darum hart beenden


if __name__ == "__main__":
    main()
