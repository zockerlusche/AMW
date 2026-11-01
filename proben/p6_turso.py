"""Probe P6 (AMW, vor Stufe 2): Turso über die HTTP-Schnittstelle /v2/pipeline, nur Standardbibliothek.

Liest Adresse und Schlüssel aus %LOCALAPPDATA%\\amw\\turso.json (nie aus dem Repo, nie ausgeben).
Legt eine Probetabelle an, schreibt mit Parametern, liest, misst die Zeit und löscht die Tabelle wieder.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request


def lade():
    with open(os.path.join(os.environ["LOCALAPPDATA"], "amw", "turso.json"), encoding="utf-8") as f:
        d = json.load(f)
    url = d["url"].strip()
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    return url.rstrip("/"), d["token"].strip()


def pipeline(url, token, anweisungen):
    body = {"requests": [{"type": "execute", "stmt": s} for s in anweisungen] + [{"type": "close"}]}
    req = urllib.request.Request(url + "/v2/pipeline", data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=20) as r:
        antwort = json.load(r)
    return antwort, (time.perf_counter() - t0) * 1000


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    url, token = lade()
    print("Ziel:", url)
    probe = [
        {"sql": "CREATE TABLE IF NOT EXISTS amw_probe (id INTEGER PRIMARY KEY, text TEXT, zeit TEXT)"},
        {"sql": "INSERT INTO amw_probe (text, zeit) VALUES (?, ?)",
         "args": [{"type": "text", "value": "Grüße aus der AMW – Umlaute äöü ß"}, {"type": "text", "value": time.strftime("%Y-%m-%dT%H:%M:%S")}]},
        {"sql": "SELECT id, text, zeit FROM amw_probe"},
        {"sql": "SELECT sqlite_version()"},
        {"sql": "DROP TABLE amw_probe"},
    ]
    try:
        antwort, ms = pipeline(url, token, probe)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300].replace(token, '<schluessel>')}")
        return 1
    except urllib.error.URLError as e:
        print("Verbindung fehlgeschlagen:", e.reason)
        return 1
    for i, r in enumerate(antwort["results"][:len(probe)]):
        if r["type"] != "ok":
            print(f"Schritt {i + 1}: FEHLER {r.get('error')}")
            continue
        res = r["response"].get("result", {})
        zeilen = [[c.get("value") for c in z] for z in res.get("rows", [])]
        print(f"Schritt {i + 1}: ok" + (f" · Zeilen {zeilen}" if zeilen else "") +
              (f" · geändert {res.get('affected_row_count')}" if res.get("affected_row_count") else ""))
    print(f"Ein Durchgang (5 Anweisungen): {ms:.0f} ms")
    zeiten = []
    for _ in range(3):
        zeiten.append(pipeline(url, token, [{"sql": "SELECT 1"}])[1])
    print("Einzelabfrage (wie die Halt-Prüfung):", " / ".join(f"{z:.0f} ms" for z in zeiten))
    return 0


if __name__ == "__main__":
    sys.exit(main())
