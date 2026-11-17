"""Oberfläche Stufe 1 (A1850, M50 S7; D1258 v15 §10, §4, §6a.4): die Liste der Arbeitspakete mit Art, Zustand, Kosten und dem Grund,
warum eines nicht startet – dazu die Eingriffe des Menschen (vorziehen, zurückstellen, Pause, Notbremse) mit Protokoll und das
Mitlesen eines laufenden `claude -p`-Arbeiters.

Grundsätze:
- Eine Ansicht ändert nichts von selbst: der Grund einer Startsperre kommt aus dem Protokoll (plan_ereignis „waechter“), nicht aus
  einer neuen Prüfung (die könnte die Pause setzen).
- Steuern nur am PC und nur der Mensch (aktionen: kanal „seite“); die Online-Seite und das Handy sehen die Liste ohne Knöpfe und
  ohne Mitlesen (D1258 §10: keine Steuerung von -p über Web/Handy in Stufe 1).
- Begriffe in Alltagssprache (B2639): „startet nicht, weil …“, nie „Wächter“ oder „Regel N“ als Hauptsatz.
- Plätze = 0: Mischbetrieb aus – die Liste sagt das, sonst ändert sich nichts (D1258 §5 Regel 10).
"""
import json
import os
import re

from . import arbeitspaket, db, kern

# Zustand eines p-Pakets → Gruppe der Oberfläche (D1258 §4: fertig / läuft / wartet / blockiert). Eine Stelle, als Tabelle in der
# Hilfe und unter der Liste gezeigt.
GRUPPE = {"entwurf": "wartet", "startklar": "wartet", "laeuft": "laeuft", "abgegeben": "laeuft", "abnahme": "laeuft",
          "merge_reihe": "wartet", "gemergt": "fertig", "fertig": "fertig", "blockiert": "blockiert", "unklar": "blockiert",
          "wartet_interaktiv": "blockiert", "abgebrochen": "blockiert", "zurueckgestellt": "wartet"}
MITLESEN_ZEILEN = 400
_REGEL = re.compile(r"^A\d+ nicht gestartet, Regel (\d+): (.*)$", re.S)


def _wer_dran(grund):
    """wartet_interaktiv: steht im Protokoll, wer dran ist (D1258 §4) – Marcel/Mensch oder der Lead."""
    g = (grund or "").casefold()
    return "mensch" if any(w in g for w in ("marcel", "mensch", "entwickler", kern.ENTWICKLER.casefold())) else "lead"


def _startgrund(con, pid, aid):
    """Letzter Eintrag „A12 nicht gestartet, Regel N: …“ → {"regel", "text", "zeit"} oder None (ohne neue Prüfung)."""
    r = con.execute("SELECT zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND art = 'waechter' AND aufgabe_id = ?"
                    " ORDER BY id DESC LIMIT 1", (pid, aid)).fetchone()
    m = _REGEL.match(r["text"]) if r else None
    return {"regel": int(m.group(1)), "text": m.group(2), "zeit": r["zeit_utc"]} if m else None


def _platz_laeuft(p):
    """Läuft auf dem Platz gerade ein Arbeiter (Job-Objekt mit aktiven Prozessen)? None = nicht feststellbar (kein Windows)."""
    if os.name != "nt":
        return None
    try:
        from . import arbeiter
        k = arbeiter._kernel()
        job = k.OpenJobObjectW(0x0004, False, arbeiter.job_name(p))       # JOB_OBJECT_QUERY
        if not job:
            return False
        try:
            return arbeiter.aktive(job) > 0
        finally:
            k.CloseHandle(job)
    except (OSError, AttributeError):
        return None


def daten(con, pid, am_pc=True):
    """{"plaetze", "aus", "pause", "wartung", "pakete": [...], "gruppen"} für die Ansicht Arbeit › Pakete."""
    from . import messung, platz, waechter
    plaetze = platz.plaetze(con, pid)
    z = waechter.zustand()
    pakete = []
    for r in con.execute("SELECT a.id, a.titel, a.agent, a.status, a.rang, a.bogen_id, k.art, k.zustand, k.zustand_utc"
                         " FROM paket k JOIN aufgabe a ON a.id = k.aufgabe_id WHERE a.projekt_id = ? AND k.art IN ('p', 'sitzung')"
                         " AND NOT (coalesce(k.zustand, '') = 'fertig' AND a.fertig_utc < strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-7 days'))"
                         " ORDER BY coalesce(a.rang, 999999), a.id", (pid,)).fetchall():
        zust = r["zustand"] if r["art"] == "p" else None
        letzter = arbeitspaket.verlauf(con, r["id"])[-1:] if zust else []
        x = {"id": r["id"], "titel": r["titel"], "art": r["art"], "zustand": zust, "seit": r["zustand_utc"], "rang": r["rang"],
             "gruppe": GRUPPE.get(zust, {"laeuft": "laeuft", "fertig": "fertig", "blockiert": "blockiert"}.get(r["status"], "wartet")),
             "usd": None, "grund": None, "dran": None, "letzter_grund": letzter[0][3] if letzter else None}
        try:
            m = messung.je_aufgabe(con, pid, r["id"])
            x["usd"] = m["usd"] if m else None
        except Exception:                                   # Messung ist Zusatz – die Liste darf daran nie scheitern
            x["usd"] = None
        if zust == "startklar":
            x["grund"] = _startgrund(con, pid, r["id"])
        if zust == "wartet_interaktiv":
            x["dran"] = _wer_dran(x["letzter_grund"])
        pakete.append(x)
    aus = {"aus": not plaetze, "pause": z["pause"], "wartung": z["wartung"], "pakete": pakete, "gruppen": GRUPPE,
           "plaetze": [{"nr": p["nr"], "laeuft": _platz_laeuft(p) if am_pc else None} for p in plaetze]}
    return aus


# --- Mitlesen ------------------------------------------------------------------------------------------------------------

def _kurz(x, n=240):
    x = " ".join(str(x).split())
    return x if len(x) <= n else x[:n - 1] + "…"


def mitlesen(con, pid, nr):
    """Die letzten Ereignisse des Arbeiters auf Platz `nr` aus dessen stream-json-Protokoll, als einfache Zeilen
    [{"art": "text"|"werkzeug"|"ergebnis"|"ende"|"start", "text"}]. Nur am PC (die Datei liegt im Platz)."""
    from . import arbeiter, platz
    p = next((x for x in platz.plaetze(con, pid) if x["nr"] == nr), None)
    if not p:
        raise kern.AmwFehler(f"Platz {nr} gibt es nicht")
    datei = os.path.join(arbeiter.ordner(p), "lauf.jsonl")
    try:
        with open(datei, encoding="utf-8", errors="replace") as f:
            zeilen = f.readlines()[-MITLESEN_ZEILEN:]
    except OSError:
        return {"platz": nr, "zeilen": [], "datei": None}
    aus = []
    for z in zeilen:
        try:
            e = json.loads(z)
        except ValueError:
            continue
        typ = e.get("type")
        if typ == "system" and e.get("subtype") == "init":
            aus.append({"art": "start", "text": f"{e.get('model') or ''} · {e.get('permissionMode') or ''}".strip(" ·")})
        elif typ == "result":
            aus.append({"art": "ende", "text": _kurz(f"{e.get('subtype') or ''} · {e.get('num_turns') or 0} Runden · "
                                                     f"{e.get('total_cost_usd') or 0} $ – {e.get('result') or ''}", 400)})
        elif typ in ("assistant", "user"):
            for c in (e.get("message") or {}).get("content") or []:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "text" and typ == "assistant":
                    aus.append({"art": "text", "text": _kurz(c.get("text"), 600)})
                elif c.get("type") == "tool_use":
                    eingabe = c.get("input") or {}
                    ziel = eingabe.get("file_path") or eingabe.get("command") or eingabe.get("pattern") or ""
                    aus.append({"art": "werkzeug", "text": _kurz(f"{c.get('name')} {ziel}")})
                elif c.get("type") == "tool_result":
                    inhalt = c.get("content")
                    if isinstance(inhalt, list):
                        inhalt = " ".join(x.get("text", "") for x in inhalt if isinstance(x, dict))
                    aus.append({"art": "ergebnis", "text": _kurz(inhalt, 200)})
    return {"platz": nr, "zeilen": aus[-200:], "datei": datei}


# --- Eingriffe des Menschen (nur am PC; aktionen prüft den Kanal) ----------------------------------------------------------

def _log(con, pid, art, text, aid=None):
    db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=kern.ENTWICKLER, art=art, aufgabe_id=aid, text=text[:500])


def _p_paket(con, pid, aid):
    f = arbeitspaket.lesen(con, aid)
    if not con.execute("SELECT 1 FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone():
        raise kern.AmwFehler(f"A{aid} gibt es nicht")
    if f["art"] != "p":
        raise kern.AmwFehler(f"A{aid} ist kein p-Paket")
    return f


def vorziehen(con, pid, aid):
    """An die Spitze der startklaren p-Pakete (Rang kleiner als alle anderen)."""
    f = _p_paket(con, pid, aid)
    if f["zustand"] not in ("entwurf", "startklar", "zurueckgestellt"):
        raise kern.AmwFehler(f"A{aid} ist „{arbeitspaket.TEXT[f['zustand']]}“ – vorziehen geht nur vor dem Start")
    kleinster = con.execute("SELECT min(coalesce(a.rang, 50)) FROM paket k JOIN aufgabe a ON a.id = k.aufgabe_id WHERE a.projekt_id = ?"
                            " AND k.art = 'p' AND k.zustand IN ('entwurf', 'startklar', 'zurueckgestellt') AND a.id != ?", (pid, aid)).fetchone()[0]
    neu = min(50, kleinster if kleinster is not None else 50) - 1
    with db.schreiben(con):
        alt = con.execute("SELECT rang FROM aufgabe WHERE id = ?", (aid,)).fetchone()[0]
        con.execute("UPDATE aufgabe SET rang = ?, geaendert_utc = ? WHERE id = ?", (neu, db.jetzt(), aid))
        _log(con, pid, "paket_vorziehen", f"A{aid} vorgezogen (Rang {alt} → {neu})", aid)
    return {"aufgabe": aid, "rang": neu}


def zurueckstellen(con, pid, aid):
    _p_paket(con, pid, aid)
    alt, neu, status = arbeitspaket.zustand_setzen(con, pid, kern.ENTWICKLER, aid, "zurueckgestellt", "vom Menschen in der Workbench")
    return {"aufgabe": aid, "zustand": neu}


def pause(con, pid, an, grund=None):
    """Pause = keine neuen Starts (Laufendes läuft zu Ende); aus = Pause und Wartung aufheben."""
    from . import waechter
    if an:
        waechter.pause_an(grund or "vom Menschen in der Workbench")
    else:                                             # P271: mit Projekt – sonst fehlt das Ereignis waechter_weiter und
        waechter.weiter(con, pid, kern.ENTWICKLER)  # Regel 9 zählte die alten Enden weiter (Pause sofort wieder da)
    with db.schreiben(con):
        _log(con, pid, "paket_pause", "Pause an – keine neuen Starts" + (f": {grund}" if grund else "") if an else "Pause aufgehoben")
    return waechter.zustand()


def notbremse(con, pid, nr, aid=None):
    from . import arbeiter, platz
    p = next((x for x in platz.plaetze(con, pid) if x["nr"] == nr), None)
    if not p:
        raise kern.AmwFehler(f"Platz {nr} gibt es nicht")
    return {"text": arbeiter.notbremse_ziehen(con, pid, p, kern.ENTWICKLER, aid)}
