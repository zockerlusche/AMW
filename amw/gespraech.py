"""Gesprächsansicht je Agent: liest das Gesprächsprotokoll von Claude Code (JSONL unter ~/.claude/projects/…) nur von
hinten und nur so weit wie nötig, und macht daraus eine ruhige Folge von Einträgen (Mensch, Claude, Werkzeug, Hinweis).

Das Protokoll ist ein internes Format von Claude Code und ändert sich – alles hier ist tolerant: Unbekanntes wird
übersprungen, nie ein Fehler. Die AMW liest es nur, sie schreibt nie hinein. Geheimnis-Muster werden immer verdeckt.

„In Claude öffnen“: Läuft die Sitzung mit Fernsteuerung (--remote-control), führt Claude Code in
~/.claude/sessions/<pid>.json die Kennung `bridgeSessionId` – daraus wird https://claude.ai/code/<kennung>.
"""
import json
import os
import re

from . import kern

FENSTER = 4 * 1024 * 1024           # so viel wird je Schritt von hinten gelesen
FENSTER_MAX = 48 * 1024 * 1024      # eine einzelne Zeile kann sehr lang sein (Bilder, große Ergebnisse)
EINTRAEGE = 160                     # je Abruf höchstens so viele Einträge
TEXT_MAX = 12_000                   # Zeichen je Text am PC
ERGEBNIS_MAX = 2_000                # Zeichen je Werkzeug-Ergebnis am PC
ONLINE_EINTRAEGE = 120
ONLINE_TEXT_MAX = 3_000

SITZUNG = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
BRUECKE = re.compile(r"^session_[A-Za-z0-9]{10,64}$")
# Zeilen, die nie etwas zeigen – am Anfang erkennbar, damit lange Zeilen gar nicht erst gelesen werden
UNSICHTBAR = ('"type":"api-request', '"type":"file-history', '"type":"queue-operation"', '"type":"mode"',
              '"type":"permission-mode"', '"type":"atis-latch"', '"type":"last-prompt"', '"type":"bridge-session"',
              '"type":"cost-state"', '"type":"attachment"', '"type":"ai-title"')
VERDECKT = "•••"
_GEHEIM_WERT = re.compile(r"(?i)\b(passw(?:or)?t|password|passwd|secret|token|api[_-]?key)(\s*[:=]\s*)(\"[^\"]{4,}\"|'[^']{4,}'|\S{4,})")


def claude_ordner():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def verdecken(text):
    from .dokumente import GEHEIM
    text = GEHEIM.sub(VERDECKT, text)
    return _GEHEIM_WERT.sub(lambda m: m.group(1) + m.group(2) + VERDECKT, text)


def protokoll(sitzung, ordner=None):
    """Pfad des Protokolls zur Sitzung oder None. Erst der Ordner, den Claude Code aus dem Arbeitsordner bildet
    (jedes Zeichen außer Buchstaben/Ziffern wird „-“), sonst die Sitzung in allen Projektordnern suchen."""
    if not sitzung or not SITZUNG.match(sitzung):
        return None
    basis = os.path.join(claude_ordner(), "projects")
    if ordner:
        p = os.path.join(basis, re.sub(r"[^A-Za-z0-9]", "-", ordner), sitzung + ".jsonl")
        if os.path.isfile(p):
            return p
    try:
        for name in os.listdir(basis):
            p = os.path.join(basis, name, sitzung + ".jsonl")
            if os.path.isfile(p):
                return p
    except OSError:
        pass
    return None


def laufende():
    """sessionId → {link, status} der laufenden Claude-Prozesse (nur gelesen; die Schlüssel daneben nie)."""
    from . import hook, steuerung
    erg = {}
    zeigen = link_zeigen()
    ordner = os.path.join(claude_ordner(), "sessions")
    for p in hook.claude_prozesse():
        try:
            if not steuerung.lebt(int(p["pid"])):          # Datei eines abgestürzten Prozesses: keine Sitzung, kein Link
                continue
            with open(os.path.join(ordner, f"{p['pid']}.json"), encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError, TypeError, AttributeError):
            continue
        b = d.get("bridgeSessionId") or ""
        erg[d.get("sessionId") or ""] = {"link": f"https://claude.ai/code/{b}" if zeigen and BRUECKE.match(b) else None,
                                         "status": d.get("status") if d.get("status") in ("busy", "idle") else None}
    return erg


def sitzungen(con, pid, kennung):
    """Die letzten Claude-Sitzungen des Agenten (neueste zuerst), je Sitzung einmal."""
    a = con.execute("SELECT id FROM agent WHERE projekt_id = ? AND kennung = ?", (pid, kennung)).fetchone()
    if not a:
        raise LookupError(kennung)
    gesehen, erg = set(), []
    for r in con.execute("SELECT claude_sitzung, arbeitsordner, gestartet_utc, beendet_utc, zustand FROM sitzung"
                         " WHERE agent_id = ? AND claude_sitzung IS NOT NULL ORDER BY id DESC LIMIT 40", (a["id"],)):
        if r["claude_sitzung"] in gesehen:
            continue
        gesehen.add(r["claude_sitzung"])
        erg.append(dict(r))
        if len(erg) >= 10:
            break
    return erg


# --- Protokoll lesen -----------------------------------------------------------------------------

def _zeilen_rueckwaerts(f, ende):
    """(start, zeile) vollständiger Zeilen vor `ende` (Zeilengrenze), von hinten nach vorn."""
    pos, rest, fenster = ende, b"", FENSTER
    while pos > 0:
        start = max(0, pos - fenster)
        f.seek(start)
        block = f.read(pos - start) + rest
        if start > 0 and b"\n" not in block:
            if fenster < FENSTER_MAX:                  # eine sehr lange Zeile (Bild, großes Ergebnis): weiter ausholen
                fenster *= 2
                continue
            pos, rest, fenster = start, b"", FENSTER    # länger als FENSTER_MAX: diese Zeile auslassen
            continue
        teile = block.split(b"\n")
        if start > 0:
            rest = teile.pop(0)
            off = start + len(rest) + 1
        else:
            rest, off = b"", 0
        liste = []
        for z in teile:
            liste.append((off, z))
            off += len(z) + 1
        yield from reversed(liste)
        pos, fenster = start, FENSTER


def _kurz(name, eingabe):
    """Eine Zeile, was das Werkzeug tut."""
    if not isinstance(eingabe, dict):
        return ""
    for k in ("description", "file_path", "path", "pattern", "query", "url", "skill", "command", "prompt", "subject"):
        v = eingabe.get(k)
        if isinstance(v, str) and v.strip():
            v = v.strip().splitlines()[0]
            if k == "file_path" and name in ("Read", "Edit", "Write", "NotebookEdit"):
                v = v.replace("\\", "/")
            return v[:160]
    for v in eingabe.values():
        if isinstance(v, str) and v.strip():
            return v.strip().splitlines()[0][:160]
    return ""


def _text_aus(inhalt):
    if isinstance(inhalt, str):
        return inhalt
    if isinstance(inhalt, list):
        return "\n".join(b.get("text", "") for b in inhalt if isinstance(b, dict) and b.get("type") == "text")
    return ""


_TAG = re.compile(r"<(command-name|command-message|command-args|local-command-stdout|local-command-stderr|"
                  r"local-command-caveat|system-reminder|task-notification)>(.*?)</\1>", re.S)


def _mensch(text):
    """Text einer Nutzer-Zeile → (art, text) oder None. Befehle, Aufgabenmeldungen, Erinnerungen getrennt."""
    tags = {m.group(1): m.group(2).strip() for m in _TAG.finditer(text)}
    rein = _TAG.sub("", text).strip()
    if "command-name" in tags:
        return "befehl", (tags["command-name"] + " " + tags.get("command-args", "")).strip()
    if "task-notification" in tags:
        s = re.search(r"<summary>(.*?)</summary>", tags["task-notification"], re.S)
        return "hinweis", (s.group(1).strip() if s else "Hintergrundaufgabe gemeldet")
    if not rein:
        return None
    if rein.startswith("This session is being continued from a previous conversation"):
        return "hinweis", "Fortsetzung nach Zusammenfassung"
    if rein.startswith("Another Claude session sent a message:"):
        return "weckruf", rein.split("\n", 1)[-1].strip()
    return "mensch", rein


def eintraege(d, online=False):
    """Eine Protokollzeile → Liste von Einträgen {art, zeit, …}."""
    if not isinstance(d, dict) or d.get("isSidechain"):
        return []
    typ, zeit = d.get("type"), d.get("timestamp")
    tmax = ONLINE_TEXT_MAX if online else TEXT_MAX
    zu = lambda s: verdecken(s if len(s) <= tmax else s[:tmax] + " …")
    erg = []
    if typ == "user":
        m = d.get("message") or {}
        inhalt = m.get("content")
        if isinstance(inhalt, list):
            for b in inhalt:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_result" and not online:
                    t = _text_aus(b.get("content")).strip()
                    erg.append({"art": "ergebnis", "zeit": zeit, "id": b.get("tool_use_id"), "fehler": bool(b.get("is_error")),
                                "text": verdecken(t if len(t) <= ERGEBNIS_MAX else t[:ERGEBNIS_MAX] + " …")})
                elif b.get("type") == "image":
                    erg.append({"art": "mensch", "zeit": zeit, "text": "[Bild]"})
            t = _text_aus([b for b in inhalt if isinstance(b, dict) and b.get("type") == "text"])
        else:
            t = inhalt if isinstance(inhalt, str) else ""
        x = _mensch(t) if t else None
        if x and d.get("isMeta"):                  # automatisch eingespielt: nur Weckrufe und geplante Aufträge zeigen
            herkunft = d.get("origin") if isinstance(d.get("origin"), dict) else {}
            x = ("weckruf", x[1]) if herkunft.get("kind") == "peer" or d.get("promptSource") == "system" else None
        if x:
            erg.append({"art": x[0], "zeit": zeit, "text": zu(x[1])})
    elif typ == "assistant":
        for b in (d.get("message") or {}).get("content") or []:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text" and (b.get("text") or "").strip():
                erg.append({"art": "claude", "zeit": zeit, "text": zu(b["text"].strip())})
            elif b.get("type") == "tool_use":
                e = {"art": "werkzeug", "zeit": zeit, "name": str(b.get("name") or "?")[:60],
                     "kurz": verdecken(_kurz(b.get("name"), b.get("input")))}
                if not online:
                    e["id"] = b.get("id")
                    roh = json.dumps(b.get("input"), ensure_ascii=False, indent=1)
                    e["eingabe"] = verdecken(roh if len(roh) <= ERGEBNIS_MAX else roh[:ERGEBNIS_MAX] + " …")
                erg.append(e)
    elif typ == "system":
        sub = d.get("subtype")
        if sub == "compact_boundary":
            erg.append({"art": "hinweis", "zeit": zeit, "text": "Gespräch zusammengefasst (Kontext voll)"})
        elif sub in ("api_error", "error") or d.get("level") == "error":
            erg.append({"art": "fehler", "zeit": zeit, "text": zu(str(d.get("content") or "Fehler"))})
        elif sub == "away_summary" and d.get("content"):
            erg.append({"art": "hinweis", "zeit": zeit, "text": zu("Zusammenfassung: " + str(d["content"]))})
    return erg


def _parse(roh):
    kopf = roh[:120].decode("utf-8", "replace").replace(" ", "")
    if any(u in kopf for u in UNSICHTBAR):
        return None
    try:
        return json.loads(roh)
    except ValueError:
        return None


def lesen(pfad, vor=None, ab=None, anzahl=EINTRAEGE, online=False):
    """Einträge aus dem Protokoll.
    ab=<Byte>: alles Neue ab dieser Stelle (für „live“); vor=<Byte>: die `anzahl` Einträge davor (Ältere laden);
    sonst die letzten `anzahl`. Rückgabe: {eintraege, vor, ab, anfang, titel}."""
    with open(pfad, "rb") as f:
        f.seek(0, os.SEEK_END)
        groesse = f.tell()
        if ab is not None:
            ab = max(0, min(int(ab), groesse))
            f.seek(ab)
            neu = f.read(min(groesse - ab, FENSTER_MAX))
            ende = neu.rfind(b"\n") + 1
            erg, off = [], ab
            for z in neu[:ende].split(b"\n")[:-1] if ende else []:
                d = _parse(z)
                if d:
                    erg += eintraege(d, online)
                off += len(z) + 1
            return {"eintraege": erg, "ab": ab + ende, "vor": None, "anfang": False, "titel": None}
        bis = groesse if vor is None else max(0, min(int(vor), groesse))
        if bis == groesse and groesse:                     # letzte Zeile wird vielleicht gerade geschrieben
            f.seek(groesse - 1)
            if f.read(1) != b"\n":
                f.seek(max(0, groesse - FENSTER_MAX))
                block = f.read()
                bis = groesse - len(block) + block.rfind(b"\n") + 1 if b"\n" in block else 0
        stuecke, erste, titel = [], bis, None
        for start, z in _zeilen_rueckwaerts(f, bis):
            if titel is None and vor is None and b'"ai-title"' in z[:60]:
                try:
                    titel = json.loads(z).get("aiTitle")
                except ValueError:
                    pass
            d = _parse(z)
            if not d:
                continue
            e = eintraege(d, online)
            if e:
                stuecke.append(e)
                erste = start
                if sum(1 for s in stuecke for x in s if x["art"] != "ergebnis") >= anzahl:   # Ergebnisse hängen am Werkzeug
                    break
        else:
            erste = 0
        erg = [x for s in reversed(stuecke) for x in s]
        return {"eintraege": erg, "vor": erste, "ab": bis if vor is None else None, "anfang": erste == 0, "titel": titel}


# --- für Workbench und Online ---------------------------------------------------------------------

def daten(con, pid, kennung, sitzung=None, vor=None, ab=None, online=False):
    liste = sitzungen(con, pid, kennung)
    if sitzung and sitzung not in [s["claude_sitzung"] for s in liste]:
        raise kern.AmwFehler("Diese Sitzung gehört nicht zu diesem Agenten")
    lauf = laufende()
    kopf = {"kennung": kennung, "sitzungen": [{"sitzung": s["claude_sitzung"], "gestartet_utc": s["gestartet_utc"],
                                               "beendet_utc": s["beendet_utc"], "zustand": s["zustand"],
                                               "laeuft": s["claude_sitzung"] in lauf} for s in liste]}
    wahl = None
    for s in liste:
        if (sitzung and s["claude_sitzung"] == sitzung) or (not sitzung and protokoll(s["claude_sitzung"], s["arbeitsordner"])):
            wahl = s
            break
    if not wahl:
        return {**kopf, "sitzung": None, "eintraege": [], "link": None, "status": None}
    p = protokoll(wahl["claude_sitzung"], wahl["arbeitsordner"])
    l = lauf.get(wahl["claude_sitzung"]) or {}
    kopf.update(sitzung=wahl["claude_sitzung"], link=l.get("link"), status=l.get("status"), laeuft=bool(l))
    if not p:
        return {**kopf, "eintraege": [], "fehlt": True}
    return {**kopf, **lesen(p, vor=vor, ab=ab, anzahl=ONLINE_EINTRAEGE if online else EINTRAEGE, online=online)}


def link_zeigen():
    """Der Link führt ins Internet: nur, wenn er eingeschaltet ist (Zahnrad › Dieser PC) und die Betriebsart das zulässt."""
    from . import betriebsart, einstellungen
    return bool(einstellungen.wert("claude_link")) and betriebsart.erlaubt("https://claude.ai")


def link(sitzung):
    """Link „In Claude öffnen“ für eine laufende Sitzung mit Fernsteuerung, sonst None."""
    return (laufende().get(sitzung) or {}).get("link") if sitzung else None
