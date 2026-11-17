"""Rückmeldevertrag (A1857, M50 S5b; D1258 v14 §6a.1, §6a.2, §6a.6, §6.3).

Ein `-p`-Arbeiter meldet sein Ergebnis über einen eigenen kleinen Connector (stdio-MCP-Server mit genau einem Werkzeug
`ergebnis_melden`), den die AMW nur diesem Lauf per `--mcp-config` mitgibt. Kein Schlüssel, keine Datei, keine Ersatzzeile:
Der Connector prüft die Eingabe gegen das Schema und antwortet „angenommen“ oder mit dem Fehler samt Schema. Die AMW liest Aufruf
und Antwort aus dem stream-json des Laufs (das nur der Starter liest) und nimmt die letzte gültige Meldung – und prüft sie dabei
selbst noch einmal (sie glaubt auch dem Connector nicht). Interaktive Agenten melden dasselbe mit `amw paket ergebnis`.

Die Meldung steuert nur, wohin das Paket geht; ob die Arbeit gut ist, entscheidet die eigene Prüfung der AMW (§6a.3, S6a).
Freitext des Agenten ist nicht vertrauenswürdig und wird so gespeichert; `hinweis` geht nur an den Lead, nie in einen Auftrag.
"""
import io
import json
import os
import sys

NAME = "amw-rueckmeldung"
WERKZEUG = "ergebnis_melden"
VOLL = f"mcp__{NAME}__{WERKZEUG}"                      # so heißt das Werkzeug im Lauf (Freigabeliste, stream-json)
STATUS = ("erledigt", "blockiert", "aufgegeben")
FRAGE_AN = ("lead", "mensch")
MAX_BYTES = 20_000
MAX_SATZ = 400                                         # „ein Satz“ – großzügig, aber kein Bericht
VERSIONEN = ["2025-06-18", "2025-03-26", "2024-11-05"]

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "zusammenfassung"],
    "properties": {
        "status": {"type": "string", "enum": list(STATUS), "description": "erledigt | blockiert | aufgegeben"},
        "zusammenfassung": {"type": "string", "maxLength": MAX_SATZ, "description": "ein Satz, was gemacht wurde"},
        "frage": {"type": "string", "maxLength": 2000, "description": "Pflicht bei blockiert: die eine Frage, die dich stoppt"},
        "frage_an": {"type": "string", "enum": list(FRAGE_AN), "description": "lead (Vorgabe) oder mensch"},
        "grund": {"type": "string", "maxLength": 2000, "description": "Pflicht bei aufgegeben: warum es nicht geht"},
        "hinweis": {"type": "string", "maxLength": 2000, "description": "optional: was der Lead wissen muss"},
    },
}
BEISPIEL = '{"status": "erledigt", "zusammenfassung": "Hilfetext für den Export ergänzt und Test dazu geschrieben."}'


def pruefen(m):
    """Fehler der Meldung gegen das Schema (§6a.2) – leere Liste = gültig. Prüft selbst, ohne Bibliothek."""
    if not isinstance(m, dict):
        return ["Die Meldung muss ein JSON-Objekt sein"]
    f = []
    if len(json.dumps(m, ensure_ascii=False).encode("utf-8")) > MAX_BYTES:
        f.append(f"Die Meldung ist größer als {MAX_BYTES} Bytes")
    fremd = sorted(set(m) - set(SCHEMA["properties"]))
    if fremd:
        f.append(f"Unbekannte Felder: {', '.join(fremd)} (erlaubt: {', '.join(SCHEMA['properties'])})")
    for k, d in SCHEMA["properties"].items():
        if k in m and not isinstance(m[k], str):
            f.append(f"{k} muss Text sein")
        elif k in m and "enum" in d and m[k] not in d["enum"]:
            f.append(f"{k}: „{m[k]}“ – erlaubt: {', '.join(d['enum'])}")
        elif k in m and len(m[k]) > d.get("maxLength", 10 ** 9):
            f.append(f"{k} ist länger als {d['maxLength']} Zeichen")
    for k in SCHEMA["required"]:
        if not str(m.get(k) or "").strip():
            f.append(f"{k} fehlt")
    if m.get("status") == "blockiert" and not str(m.get("frage") or "").strip():
        f.append("Bei blockiert ist frage Pflicht")
    if m.get("status") == "aufgegeben" and not str(m.get("grund") or "").strip():
        f.append("Bei aufgegeben ist grund Pflicht")
    if m.get("frage_an") and m.get("status") != "blockiert":
        f.append("frage_an gehört zu blockiert")
    return f


# --- Connector (stdio, JSON-RPC 2.0, eine Nachricht je Zeile) -----------------------------------------------------------

def _werkzeug():
    return {"name": WERKZEUG, "title": "Ergebnis melden",
            "description": ("Meldet das Ergebnis deines Pakets an die AMW. Genau ein Status. Im Zweifel blockiert mit einer Frage. "
                            "Nie erledigt ohne Änderungen. Commits, Dateien und Tests meldest du nicht – die AMW liest und prüft "
                            "sie selbst. Du kannst mehrmals melden; es gilt die letzte gültige Meldung. Beispiel: " + BEISPIEL),
            "inputSchema": SCHEMA}


def bearbeiten(n):
    """Eine JSON-RPC-Nachricht → Antwort oder None. Kann nur annehmen oder ablehnen – nichts lesen, nichts sonst."""
    if not isinstance(n, dict) or n.get("jsonrpc") != "2.0" or not isinstance(n.get("method"), str):
        if isinstance(n, dict) and "id" in n and "method" not in n:
            return None
        return {"jsonrpc": "2.0", "id": n.get("id") if isinstance(n, dict) else None,
                "error": {"code": -32600, "message": "ungültige Anfrage"}}
    if "id" not in n:
        return None
    mid, methode, p = n["id"], n["method"], n.get("params") or {}
    if methode == "initialize":
        v = p.get("protocolVersion")
        erg = {"protocolVersion": v if v in VERSIONEN else VERSIONEN[0], "capabilities": {"tools": {"listChanged": False}},
               "serverInfo": {"name": NAME, "title": "AMW Rückmeldung", "version": "1"},
               "instructions": "Ein Werkzeug: ergebnis_melden – das Ergebnis dieses Pakets an die AMW. Sonst nichts."}
    elif methode == "ping":
        erg = {}
    elif methode == "tools/list":
        erg = {"tools": [_werkzeug()]}
    elif methode == "tools/call":
        if p.get("name") != WERKZEUG:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unbekanntes Werkzeug: {p.get('name')}"}}
        fehler = pruefen(p.get("arguments"))
        if fehler:
            text = "Nicht angenommen: " + "; ".join(fehler) + ". Schema: " + json.dumps(SCHEMA, ensure_ascii=False) + " Beispiel: " + BEISPIEL
            erg = {"content": [{"type": "text", "text": text}], "isError": True}
        else:
            erg = {"content": [{"type": "text", "text": "angenommen – es gilt die letzte gültige Meldung"}], "isError": False}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unbekannte Methode: {methode}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": erg}


def laufen(ein=None, aus=None):
    ein = ein or io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")
    aus = aus or io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")
    for zeile in ein:
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            n = json.loads(zeile)
        except ValueError:
            antwort = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "kein gültiges JSON"}}
        else:
            antwort = [a for a in (bearbeiten(x) for x in n) if a] if isinstance(n, list) else bearbeiten(n)
        if antwort:
            aus.write(json.dumps(antwort, ensure_ascii=False) + "\n")
            aus.flush()


def mcp_config(skript, python=None):
    """--mcp-config für einen Lauf. `python -I` + absoluter Pfad des Einstiegs im Ordner der AMW: der Connector lädt nie Code
    aus dem Klon des Platzes (dort ist der Arbeitsordner)."""
    return {"mcpServers": {NAME: {"type": "stdio", "command": python or sys.executable, "args": ["-I", "-X", "utf8", skript], "env": {}}}}


def einstieg():
    """Pfad des Connector-Einstiegs (amw-rueckmeldung.py) im Ordner dieses Codes."""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "amw-rueckmeldung.py")


# --- Auswertung des Laufs ----------------------------------------------------------------------------------------------

def auswerten(ereignisse):
    """Letzte gültige Meldung aus den stream-json-Ereignissen: Aufruf von ergebnis_melden, Antwort des Connectors ohne Fehler,
    und die AMW prüft die Eingabe selbst noch einmal. Rückgabe (meldung | None, versuche)."""
    aufrufe, antworten = {}, {}
    for e in ereignisse:
        if not isinstance(e, dict):
            continue
        nachricht = e.get("message")
        inhalt = nachricht.get("content") if isinstance(nachricht, dict) else None   # echter Strom: message/content auch als Text
        if not isinstance(inhalt, list):                       # echter Strom: content kann auch ein einfacher Text sein
            continue
        if e.get("type") == "assistant":
            for c in inhalt:
                if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") == VOLL and c.get("id"):
                    aufrufe[c["id"]] = c.get("input")                    # P267: ohne id keine Zuordnung zur Antwort – verworfen
        elif e.get("type") == "user":
            for c in inhalt:
                if isinstance(c, dict) and c.get("type") == "tool_result" and c.get("tool_use_id") in aufrufe:
                    antworten[c["tool_use_id"]] = not c.get("is_error")
    gueltig = [m for i, m in aufrufe.items() if antworten.get(i) and not pruefen(m)]
    return (gueltig[-1] if gueltig else None), len(aufrufe)


def ereignisse_lesen(protokoll):
    aus = []
    try:
        with open(protokoll, encoding="utf-8") as f:
            for z in f:
                try:
                    aus.append(json.loads(z))
                except ValueError:
                    pass
    except OSError:
        pass
    return aus


# --- Speichern (nicht vertrauenswürdig) und interaktive Meldung ---------------------------------------------------------

def speichern(con, pid, von, aid, meldung, quelle):
    """Meldung als plan_ereignis „paket_ergebnis“ – ausdrücklich als ungeprüfte Angabe des Agenten. quelle: p | agent."""
    from . import db
    text = json.dumps({"quelle": quelle, "vertrauen": "ungeprüft – Angabe des Agenten", "meldung": meldung}, ensure_ascii=False)
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art="paket_ergebnis", aufgabe_id=aid, text=text)


def letzte(con, pid, aid):
    r = con.execute("SELECT text, von, zeit_utc FROM plan_ereignis WHERE projekt_id = ? AND aufgabe_id = ? AND art = 'paket_ergebnis'"
                    " ORDER BY id DESC LIMIT 1", (pid, aid)).fetchone()
    return dict(json.loads(r["text"]), von=r["von"], zeit=r["zeit_utc"]) if r else None


def melden_interaktiv(con, pid, von, aid, meldung, umgebung=None, zweig=None):
    """`amw paket ergebnis` (§6a.6): nur der zugeteilte Agent (AMW_AGENT = --von = Besitzer der Aufgabe), nur Art agent/sitzung,
    nur solange das Paket läuft. Gleiches Schema wie der Connector."""
    from . import arbeitspaket, kern
    u = os.environ if umgebung is None else umgebung
    a = con.execute("SELECT agent, status FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    if not a:
        raise kern.AmwFehler(f"A{aid} gibt es nicht")
    if not a["agent"] or von != a["agent"] or u.get("AMW_AGENT") != a["agent"]:
        raise kern.AmwFehler(f"A{aid} ist {a['agent'] or 'niemandem'} zugeteilt – melden kann nur dieser Agent aus seiner Sitzung")
    art = arbeitspaket.lesen(con, aid)["art"]
    if art not in ("agent", "sitzung"):
        raise kern.AmwFehler(f"A{aid} ist ein Paket der Art {art} – es meldet über seinen Rückmelde-Zugang, nicht über diesen Befehl")
    if a["status"] != "laeuft":
        raise kern.AmwFehler(f"A{aid} läuft nicht (Status {a['status']}) – ein Ergebnis gibt es nur für ein laufendes Paket")
    fehler = pruefen(meldung)
    if fehler:
        raise kern.AmwFehler("Nicht angenommen: " + "; ".join(fehler) + f". Beispiel: {BEISPIEL}")
    zeile = con.execute("SELECT titel, pruefbefehl, dateibereich FROM aufgabe WHERE id = ?", (aid,)).fetchone()
    mit_abnahme = meldung["status"] == "erledigt" and (zeile["pruefbefehl"] or "").strip()
    if mit_abnahme and not (zweig or "").strip():                # §6a.6: für eine Meldung mit Abnahme ist ein Zweig je Paket Pflicht
        raise kern.AmwFehler(f"A{aid} hat einen Abnahme-Befehl – erledigt nur mit --zweig <dein Zweig für dieses Paket>")
    speichern(con, pid, von, aid, meldung, "agent")
    if mit_abnahme:                                              # Stufe 1 kein Autopfad: Prüfbitte mit dem Befund der AMW
        return {"meldung": meldung, "pruefbitte": _pruefbitte_aus_ergebnis(con, pid, von, aid, zeile, meldung, zweig.strip())}
    return {"meldung": meldung, "pruefbitte": None}


def _pruefbitte_aus_ergebnis(con, pid, von, aid, zeile, meldung, zweig):
    from . import abnahme, arbeitspaket, betrieb, entscheidung, kern, pruefung_c
    quelle = kern.projekt_ordner(con, pid)
    if not quelle:
        raise kern.AmwFehler("Das Projekt hat keinen Ordner (amw projekt ordner …) – die AMW kann den Zweig nicht prüfen")
    bereiche = abnahme_bereiche(zeile["dateibereich"])
    b = pruefung_c.zweig_befund(quelle, zweig, bereiche, arbeitspaket.lesen(con, aid).get("pakettyp"))
    if b["code"] == "C/technik":
        raise kern.AmwFehler(b["grund"])
    pruefer = entscheidung.empfaenger(con, pid, "pruefer")
    punkte = (f"Aus dem Ergebnis erzeugt (§6a.6, Stufe 1 ohne Autopfad). Meldung des Agenten (ungeprüft): {meldung['status']} – "
              f"{meldung['zusammenfassung']}" + (f" · hinweis: {meldung['hinweis']}" if meldung.get("hinweis") else "")
              + f"\nBefund der AMW ({b['code'] or 'ohne Befund'}): {b['grund']}. Geändert: {', '.join(b['geaendert'][:12])}"
              + f"\nAbnahme-Befehl: {zeile['pruefbefehl']} – die Abnahme im frischen Checkout läuft über die Lauf-Schlange (Disponent).")
    prid = betrieb.pruefbitte(con, pid, von, pruefer, zweig, b["kopf"], punkte, aid)
    return {"id": prid, "an": pruefer, "befund": b["code"]}


def abnahme_bereiche(text):
    from . import waechter
    return waechter.bereiche(text)


# --- Auftragsvorlage (§6.3) --------------------------------------------------------------------------------------------

VORLAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vorlagen", "auftrag_p.md")


def auftrag(con, pid, aid):
    """Auftrag für einen -p-Lauf aus der versionierten Vorlage: Ziel, Bereiche, Abnahme-Befehl, Regeln, gültiges Beispiel.
    Der Auftragstext der Aufgabe stammt vom Lead (vertrauenswürdig); ein früherer `hinweis` eines Agenten kommt nie hinein."""
    a = con.execute("SELECT id, titel, auftrag, pruefbefehl, dateibereich FROM aufgabe WHERE id = ? AND projekt_id = ?",
                    (aid, pid)).fetchone()
    if not a:
        from . import kern
        raise kern.AmwFehler(f"A{aid} gibt es nicht")
    with open(VORLAGE, encoding="utf-8") as f:
        v = f.read()
    return (v.replace("{{NUMMER}}", f"A{a['id']}").replace("{{TITEL}}", a["titel"] or "").replace("{{AUFTRAG}}", (a["auftrag"] or "").strip())
             .replace("{{BEREICHE}}", (a["dateibereich"] or "").strip()).replace("{{ABNAHME}}", (a["pruefbefehl"] or "").strip())
             .replace("{{BEISPIEL}}", BEISPIEL))
