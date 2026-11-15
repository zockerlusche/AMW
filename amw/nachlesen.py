"""Messen: Lesen Agenten nach einem Weckruf mit Inhalt trotzdem nach? (A1757, Lückenliste TL, Marcel W2168 – liefert die Zahl
für das Token-Ziel.) Seit 1.98.0 steht im Weckruf alles Nötige; Nachlesen (amw lesen/kontext) sollte die Ausnahme sein.

Die Befehlszeile hält jeden Aufruf von „amw lesen“ und „amw kontext“ eines Agenten fest – Zeit, Projekt, Agent, Befehl, nie
Inhalte – in einer kleinen Zeilen-Datei neben der Datenbank (kein Schema). Betrieb › „Wofür das Geld geht“ zählt daraus, nach
wie vielen Weckrufen der Agent innerhalb von FENSTER_S nachgelesen hat, und stellt die Kosten je Weckruf vor und nach der
Version gegenüber, ab der Weckrufe den Inhalt mitbringen (1.98.0).
"""
import json
import os

from . import db

FENSTER_S = 120
MAX_BYTES = 2_000_000          # dann wird die ältere Hälfte verworfen
VERSION_INHALT = "1.98.0"      # ab dieser Version bringen Weckrufe den Inhalt mit (A1645)


def pfad():
    return os.path.join(os.path.dirname(os.path.abspath(db.db_pfad())), "nachlesen.jsonl")


def merken(projekt, agent, befehl):
    """Eine Zeile anhängen – still, nie störend (die Befehlszeile soll deshalb nie scheitern)."""
    try:
        p = pfad()
        if os.path.exists(p) and os.path.getsize(p) > MAX_BYTES:
            with open(p, encoding="utf-8") as f:
                zeilen = f.readlines()
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.writelines(zeilen[len(zeilen) // 2:])
        with open(p, "a", encoding="utf-8", newline="") as f:
            f.write(json.dumps({"t": db.jetzt(), "p": projekt, "a": agent, "b": befehl}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def lesen():
    try:
        with open(pfad(), encoding="utf-8") as f:
            return [json.loads(z) for z in f if z.strip()]
    except (OSError, ValueError):
        return []


def _sek(utc):
    import calendar
    import time
    return calendar.timegm(time.strptime(utc[:19], "%Y-%m-%dT%H:%M:%S"))


def auswertung(con, pid, ab, bis=None):
    """{"weckrufe", "nachgelesen", "anteil", "seit"} – nur Weckrufe ab dem ersten Eintrag des Protokolls (vorher wurde nicht
    gemessen); dazu {"vorher", "nachher"}: Kosten je Weckruf (USD) in gleich langen Zeiträumen vor und nach VERSION_INHALT."""
    from . import anlass
    name = con.execute("SELECT name FROM projekt WHERE id = ?", (pid,)).fetchone()[0]
    eintraege = [e for e in lesen() if e.get("p") == name]
    aus = {"weckrufe": 0, "nachgelesen": 0, "anteil": None, "seit": eintraege[0]["t"] if eintraege else None}
    if eintraege:
        start = max(ab, eintraege[0]["t"])
        je_agent = {}
        for e in eintraege:
            je_agent.setdefault(e["a"], []).append(_sek(e["t"]))
        for (kennung,) in con.execute("SELECT kennung FROM agent WHERE projekt_id = ?", (pid,)).fetchall():
            zeiten = je_agent.get(kennung, [])
            for w in anlass._weckrufe(con, pid, kennung, start):
                if bis and w["t"] >= bis:
                    continue
                aus["weckrufe"] += 1
                t = _sek(w["t"])
                if any(t <= z <= t + FENSTER_S for z in zeiten):
                    aus["nachgelesen"] += 1
        if aus["weckrufe"]:
            aus["anteil"] = round(100 * aus["nachgelesen"] / aus["weckrufe"], 1)
    r = con.execute("SELECT min(zeit_utc) FROM release WHERE art = 'version' AND version = ?", (VERSION_INHALT,)).fetchone()
    aus["version"] = VERSION_INHALT
    aus["vorher"] = aus["nachher"] = None
    if r and r[0]:
        import datetime
        grenze = datetime.datetime.strptime(r[0][:19], "%Y-%m-%dT%H:%M:%S")
        jetzt = datetime.datetime.utcnow()
        tage = max(1, min(7, (jetzt - grenze).days or 1))
        iso = lambda x: x.strftime("%Y-%m-%dT%H:%M:%SZ")

        def je(von, bis_):
            a = anlass.anlaesse(con, pid, iso(von), iso(bis_))
            fremd = sum(z["usd"] for z in a["zeilen"] if z["anlass"] != anlass.EIGENE)
            return round(fremd / a["weckrufe"], 2) if a["weckrufe"] else None
        aus["vorher"] = je(grenze - datetime.timedelta(days=tage), grenze)
        aus["nachher"] = je(grenze, grenze + datetime.timedelta(days=tage))
        aus["tage"] = tage
    return aus
