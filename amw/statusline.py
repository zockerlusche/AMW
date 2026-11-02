"""Statusline-Brücke (Stufe C): merkt sich je Sitzung Kontext-Füllstand, Nutzungsgrenzen, Kosten und Modell und gibt
die bisherige Statusline unverändert weiter.

Claude Code ruft den statusLine-Befehl sehr oft auf (bei jeder Änderung im Gespräch) und reicht dabei JSON auf stdin
(→ code.claude.com/docs/en/statusline). Darum hier KEIN Datenbankzugriff: nur eine kleine Datei je Sitzung unter
%LOCALAPPDATA%\\amw\\zustand\\<session_id>.json; der Wächter übernimmt sie in die Datenbank.

Einbau (je Agent bzw. Projektordner, `amw einrichten` macht das):
  "statusLine": {"type": "command", "command": "python -X utf8 C:/amw/amw-statusline.py"}
Eine schon vorhandene Statusline bleibt erhalten: steht in den Einstellungen dieses PCs „statusline_weiter“, wird sie
mit denselben Daten aufgerufen und ihre Ausgabe gezeigt; sonst druckt die Brücke selbst eine kurze Zeile.
Nie abstürzen, nie hängen: jeder Fehler endet mit einer schlichten Zeile.
"""
import json
import os
import subprocess
import sys
import time


def ordner():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "amw", "zustand")


def _zahl(x):
    try:
        return None if x is None else round(float(x), 2)
    except (TypeError, ValueError):
        return None


def auszug(d):
    """Nur, was die AMW braucht – keine Pfade zu Inhalten, keine Gesprächsdaten."""
    cw, rl, cost = d.get("context_window") or {}, d.get("rate_limits") or {}, d.get("cost") or {}
    fuenf, sieben = rl.get("five_hour") or {}, rl.get("seven_day") or {}
    return {"sitzung": d.get("session_id"), "zeit": int(time.time()),
            "kontext": _zahl(cw.get("used_percentage")), "kontext_groesse": cw.get("context_window_size"),
            "limit_5h": _zahl(fuenf.get("used_percentage")), "limit_5h_reset": fuenf.get("resets_at"),
            "limit_7t": _zahl(sieben.get("used_percentage")), "limit_7t_reset": sieben.get("resets_at"),
            "kosten": _zahl(cost.get("total_cost_usd")),
            "modell": (d.get("model") or {}).get("display_name") or (d.get("model") or {}).get("id"),
            "denkstufe": (d.get("effort") or {}).get("level"), "version": d.get("version")}


def merken(a):
    if not a.get("sitzung") or not all(c.isalnum() or c == "-" for c in a["sitzung"]):
        return
    os.makedirs(ordner(), exist_ok=True)
    ziel = os.path.join(ordner(), a["sitzung"] + ".json")
    neu = f"{ziel}.{os.getpid()}.neu"
    with open(neu, "w", encoding="utf-8") as f:
        json.dump(a, f)
    os.replace(neu, ziel)


def zeile(a):
    teile = [a["modell"] or "?"]
    if a["kontext"] is not None:
        teile.append(f"Kontext {a['kontext']:.0f} %")
    if a["limit_5h"] is not None:
        teile.append(f"5h {a['limit_5h']:.0f} %")
    if a["limit_7t"] is not None:
        teile.append(f"Woche {a['limit_7t']:.0f} %")
    if a["kosten"] is not None:
        teile.append(f"{a['kosten']:.2f} $")
    return " · ".join(teile)


def weiter_befehl():
    try:
        from . import einstellungen
        return einstellungen.wert("statusline_weiter") or ""
    except Exception:
        return ""


MESSPUNKT_S = 300
AUFHEBEN_S = 7 * 86400


def _utc(sek):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(sek)) if sek else None


def uebernehmen(con):
    """Wächter: Zustandsdateien → sitzung (laufende Sitzungen), alle MESSPUNKT_S ein Messpunkt in verbrauch.
    Alte Dateien (> 7 Tage) werden gelöscht. Rückgabe: Zahl übernommener Sitzungen."""
    from . import db
    try:
        namen = [n for n in os.listdir(ordner()) if n.endswith(".json")]
    except OSError:
        return 0
    n = 0
    for name in namen:
        datei = os.path.join(ordner(), name)
        try:
            if time.time() - os.path.getmtime(datei) > AUFHEBEN_S:
                os.remove(datei)
                continue
            with open(datei, encoding="utf-8") as f:
                a = json.load(f)
        except (OSError, ValueError):
            continue
        s = con.execute("SELECT s.id, s.status_utc, g.kennung FROM sitzung s JOIN agent g ON g.id = s.agent_id"
                        " WHERE s.claude_sitzung = ? AND s.zustand = 'aktiv'", (a.get("sitzung"),)).fetchone()
        stand = _utc(a.get("zeit"))
        if not s or (s["status_utc"] and stand <= s["status_utc"]):
            continue
        with db.schreiben(con):
            con.execute("UPDATE sitzung SET kontext_prozent = ?, limit_5h = ?, limit_5h_reset_utc = ?, limit_7t = ?,"
                        " limit_7t_reset_utc = ?, kosten_usd = ?, modell = ?, denkstufe = ?, status_utc = ? WHERE id = ?",
                        (a.get("kontext"), a.get("limit_5h"), _utc(a.get("limit_5h_reset")), a.get("limit_7t"),
                         _utc(a.get("limit_7t_reset")), a.get("kosten"), a.get("modell"), a.get("denkstufe"), stand, s["id"]))
            letzt = con.execute("SELECT max(zeit_utc) FROM verbrauch WHERE sitzung_id = ?", (s["id"],)).fetchone()[0]
            if not letzt or a["zeit"] - _sek(letzt) >= MESSPUNKT_S:
                db.einfuegen(con, "verbrauch", sitzung_id=s["id"], agent=s["kennung"], zeit_utc=stand, kosten_usd=a.get("kosten"),
                             kontext_prozent=a.get("kontext"), limit_5h=a.get("limit_5h"), limit_7t=a.get("limit_7t"))
        n += 1
    return n


def _sek(utc):
    import calendar
    return calendar.timegm(time.strptime(utc, "%Y-%m-%dT%H:%M:%SZ"))


def verbrauch_tage(con, pid, tage=7):
    """Kosten je Agent und lokalem Tag aus den Messpunkten: Summe der Zuwächse je Sitzung (sinkt der Zähler, hat die
    Sitzung neu gezählt – dann zählt der neue Wert ganz). Rückgabe: {"tage": [...], "agenten": {kennung: {tag: usd}}}."""
    import datetime
    ab = _utc(time.time() - (tage + 1) * 86400)
    zeilen = con.execute("SELECT v.sitzung_id, v.agent, v.zeit_utc, v.kosten_usd FROM verbrauch v JOIN agent g"
                         " ON g.kennung = v.agent AND g.projekt_id = ? WHERE v.zeit_utc >= ? AND v.kosten_usd IS NOT NULL"
                         " ORDER BY v.sitzung_id, v.zeit_utc", (pid, ab)).fetchall()
    heute = datetime.date.today()
    liste = [(heute - datetime.timedelta(days=i)).isoformat() for i in range(tage - 1, -1, -1)]
    aus, vorher = {}, {}
    for z in zeilen:
        tag = datetime.datetime.fromtimestamp(_sek(z["zeit_utc"])).date().isoformat()
        alt = vorher.get(z["sitzung_id"])
        zuwachs = z["kosten_usd"] if alt is None or z["kosten_usd"] < alt else z["kosten_usd"] - alt
        if alt is None:
            zuwachs = 0.0                     # erster Messpunkt: Stand unbekannt, ab hier wird gezählt
        vorher[z["sitzung_id"]] = z["kosten_usd"]
        if tag in liste:
            t = aus.setdefault(z["agent"], {})
            t[tag] = round(t.get(tag, 0.0) + zuwachs, 2)
    return {"tage": liste, "agenten": aus}


def main():
    roh = sys.stdin.buffer.read()
    try:
        d = json.loads(roh.decode("utf-8") or "{}")
    except ValueError:
        d = {}
    a = auszug(d)
    try:
        merken(a)
    except OSError:
        pass
    befehl = weiter_befehl()
    if befehl:
        try:
            r = subprocess.run(befehl, input=roh, capture_output=True, timeout=5, shell=True)
            sys.stdout.buffer.write(r.stdout)
            return 0
        except (OSError, subprocess.SubprocessError):
            pass
    sys.stdout.write(zeile(a) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
