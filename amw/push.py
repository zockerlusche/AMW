"""Push-Benachrichtigungen aufs Handy (Stufe B, → doc/13 §3, doc/recherche/push.md).

Drei Anbieter, einzeln an/aus: ntfy (ntfy.sh oder eigener Server), Pushover, Telegram-Bot. Zugangsdaten und Vorlieben
liegen in %LOCALAPPDATA%\\amw\\push.json – nie im Repo, nie in der Datenbank, nie im Online-Speicher.
Der Wächter sammelt je Runde Ereignisse aus der Datenbank (ereignisse) und verschickt sie (runde): ohne Doppelte
(eindeutiger Schlüssel in push_versand), gebündelt je Art, höchstens max_je_stunde, Ruhezeiten (nur Priorität 5 kommt
durch, der Rest danach gesammelt), Wiederholung nur bei vorübergehenden Fehlern. Texte nur Metadaten + Link.
"""
import datetime
import html
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from . import db, kern

EREIGNISSE = {                       # Art → (Vorgabe an, Priorität 1–5, Überschrift im Bündel)
    "frage": (True, 4, "neue Fragen an dich"),
    "nachricht": (True, 3, "neue Nachrichten an dich"),
    "warnung": (True, 4, "Warnungen"),
    "eingabe": (True, 4, "Agenten warten auf Eingabe"),
    "halt": (True, 5, "Halt"),
    "rueckblick": (True, 2, "Rückblicke"),
}
ANBIETER = ("ntfy", "pushover", "telegram")
WIEDERHOLEN_NACH_S = (0, 30, 120)   # 1., 2., 3. Versuch
ERINNERN_NACH_MIN = 60
EINGABE_NACH_MIN = 5
ZEITGRENZE_S = 10

VORGABE = {
    "an": False, "seit_utc": None, "link": "",
    "ntfy": {"an": False, "server": "https://ntfy.sh", "topic": "", "token": ""},
    "pushover": {"an": False, "app_token": "", "user_key": ""},
    "telegram": {"an": False, "bot_token": "", "chat_id": ""},
    "ereignisse": {k: v[0] for k, v in EREIGNISSE.items()},
    "ruhe": {"an": False, "von": "22:00", "bis": "07:00"},
    "max_je_stunde": 10,
}
GEHEIM = {"ntfy": ("token",), "pushover": ("app_token", "user_key"), "telegram": ("bot_token",)}


class Fehler(kern.AmwFehler):
    """Versand gescheitert; vorlaeufig=True → später erneut versuchen (Netz, 5xx, 429)."""

    def __init__(self, text, vorlaeufig):
        super().__init__(text)
        self.vorlaeufig = vorlaeufig


# --- Einstellungen -------------------------------------------------------------------------------

def pfad():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "amw", "push.json")


def laden():
    try:
        with open(pfad(), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    aus = json.loads(json.dumps(VORGABE))
    for k, v in (d if isinstance(d, dict) else {}).items():
        if isinstance(aus.get(k), dict) and isinstance(v, dict):
            aus[k].update(v)
        elif k in aus:
            aus[k] = v
    return aus


def _schreiben(cfg):
    os.makedirs(os.path.dirname(pfad()), exist_ok=True)
    with open(pfad() + ".neu", "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    os.replace(pfad() + ".neu", pfad())


def _uhrzeit(v):
    try:
        h, m = str(v).split(":")
        h, m = int(h), int(m)
    except ValueError:
        raise ValueError("Uhrzeit hh:mm") from None
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError("Uhrzeit hh:mm")
    return f"{h:02d}:{m:02d}"


def speichern(werte):
    """Teilweise ändern. Leere Geheimnisse lassen den gespeicherten Wert stehen (die Oberfläche zeigt sie nie)."""
    cfg = laden()
    for k, v in werte.items():
        if k in ANBIETER:
            if not isinstance(v, dict):
                raise ValueError(f"{k}: Objekt erwartet")
            for f, w in v.items():
                if f not in cfg[k]:
                    raise ValueError(f"unbekannt: {k}.{f}")
                if f in GEHEIM[k] and (w is None or str(w).strip() == ""):
                    continue
                cfg[k][f] = bool(w) if f == "an" else str(w).strip()
            if k == "ntfy":
                t = cfg["ntfy"]["topic"]
                if t and not (len(t) <= 64 and all(c.isalnum() or c in "-_" for c in t)):
                    raise ValueError("ntfy-Kanal: bis 64 Zeichen, Buchstaben/Ziffern/-/_")
                if not cfg["ntfy"]["server"].startswith("https://"):
                    raise ValueError("ntfy-Server: https://…")
        elif k == "ereignisse":
            for e, w in v.items():
                if e not in EREIGNISSE:
                    raise ValueError(f"unbekanntes Ereignis {e}")
                cfg["ereignisse"][e] = bool(w)
        elif k == "ruhe":
            cfg["ruhe"]["an"] = bool(v.get("an", cfg["ruhe"]["an"]))
            for f in ("von", "bis"):
                if f in v:
                    cfg["ruhe"][f] = _uhrzeit(v[f])
        elif k == "max_je_stunde":
            n = int(v)
            if not 1 <= n <= 60:
                raise ValueError("höchstens je Stunde: 1–60")
            cfg[k] = n
        elif k == "link":
            v = str(v).strip()
            if v and not v.startswith(("https://", "http://127.0.0.1", "http://localhost")):
                raise ValueError("Link: https://… (oder die lokale Workbench)")
            cfg[k] = v
        elif k == "an":
            neu = bool(v)
            if neu and not cfg["an"]:
                cfg["seit_utc"] = db.jetzt()          # nichts Altes nachholen
            cfg["an"] = neu
        else:
            raise ValueError(f"unbekannte Einstellung: {k}")
    _schreiben(cfg)
    return oeffentlich(cfg)


def oeffentlich(cfg=None):
    """Für Anzeige und Online-Spiegel: Geheimnisse nur als „gespeichert“. Der ntfy-Kanal ist auch ein Geheimnis."""
    cfg = cfg or laden()
    aus = json.loads(json.dumps(cfg))
    for a, felder in GEHEIM.items():
        for f in felder:
            aus[a][f + "_gespeichert"] = bool(cfg[a][f])
            aus[a].pop(f, None)
    aus["ntfy"]["topic_gespeichert"] = bool(cfg["ntfy"]["topic"])
    aus["ntfy"].pop("topic", None)
    aus["datei"] = pfad()
    return aus


def neuer_ntfy_kanal():
    return "amw-" + secrets.token_urlsafe(24).replace("_", "-")


# --- Anbieter ------------------------------------------------------------------------------------

def _anfrage(url, daten=None, kopf=None, form=False):
    if form:
        body, typ = urllib.parse.urlencode(daten).encode(), "application/x-www-form-urlencoded"
    else:
        body, typ = json.dumps(daten).encode("utf-8"), "application/json"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": typ, "User-Agent": "AMW", **(kopf or {})})
    try:
        with urllib.request.urlopen(req, timeout=ZEITGRENZE_S) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")[:300]
        raise Fehler(f"HTTP {e.code}: {text}", e.code >= 500 or e.code == 429) from None
    except (urllib.error.URLError, OSError) as e:
        raise Fehler(f"nicht erreichbar: {getattr(e, 'reason', e)}", True) from None


def ntfy(c, titel, text, prio, link):
    if not c["topic"]:
        raise Fehler("kein Kanal eingerichtet", False)
    d = {"topic": c["topic"], "title": titel, "message": text, "priority": prio,
         "tags": ["rotating_light"] if prio >= 5 else ["bell"] if prio >= 4 else []}
    if link:
        d["click"] = link
        d["actions"] = [{"action": "view", "label": "Öffnen", "url": link, "clear": True}]
    kopf = {"Authorization": f"Bearer {c['token']}"} if c.get("token") else {}
    _anfrage(c["server"].rstrip("/") + "/", d, kopf)


def pushover(c, titel, text, prio, link):
    if not (c["app_token"] and c["user_key"]):
        raise Fehler("App-Token und Benutzerschlüssel fehlen", False)
    d = {"token": c["app_token"], "user": c["user_key"], "title": titel[:250], "message": text[:1024],
         "priority": {5: 1, 4: 0, 3: 0, 2: -1, 1: -2}[prio]}
    if link:
        d.update(url=link[:512], url_title="Öffnen")
    _, antwort = _anfrage("https://api.pushover.net/1/messages.json", d, form=True)
    if json.loads(antwort or "{}").get("status") != 1:
        raise Fehler(f"abgelehnt: {antwort[:200]}", False)


def telegram(c, titel, text, prio, link):
    if not (c["bot_token"] and c["chat_id"]):
        raise Fehler("Bot-Token und Chat-ID fehlen", False)
    d = {"chat_id": c["chat_id"], "parse_mode": "HTML", "disable_notification": prio <= 2,
         "text": f"<b>{html.escape(titel, quote=False)}</b>\n{html.escape(text, quote=False)}"[:4096],
         "link_preview_options": {"is_disabled": True}}
    if link.startswith("https://"):
        d["reply_markup"] = {"inline_keyboard": [[{"text": "Öffnen", "url": link}]]}
    try:
        _anfrage(f"https://api.telegram.org/bot{c['bot_token']}/sendMessage", d)
    except Fehler as e:                            # das Token steht in der URL – nie in Fehlertexte
        raise Fehler(str(e).replace(c["bot_token"], "…"), e.vorlaeufig) from None


SENDER = {"ntfy": ntfy, "pushover": pushover, "telegram": telegram}


def telegram_chats(bot_token):
    """Chat-IDs aus den letzten Nachrichten an den Bot (getUpdates) – für die Einrichtung."""
    try:
        _, a = _anfrage(f"https://api.telegram.org/bot{bot_token}/getUpdates", {})
    except Fehler as e:
        raise Fehler(str(e).replace(bot_token, "…"), e.vorlaeufig) from None
    chats = {}
    for u in json.loads(a).get("result", []):
        ch = (u.get("message") or u.get("channel_post") or {}).get("chat") or {}
        if ch.get("id"):
            chats[ch["id"]] = ch.get("username") or ch.get("title") or ch.get("first_name") or ""
    return chats


def senden(cfg, titel, text, prio, link, nur=None):
    """An alle eingeschalteten Anbieter (oder nur einen). Rückgabe {anbieter: None | Fehler}."""
    erg = {}
    for a in ANBIETER:
        if (nur and a != nur) or (not nur and not cfg[a]["an"]):
            continue
        try:
            SENDER[a](cfg[a], titel, text, prio, link)
            erg[a] = None
        except Fehler as e:
            erg[a] = e
    return erg


def probe(anbieter=None):
    cfg = laden()
    erg = senden(cfg, "AMW: Probe", "Wenn du das liest, kommen Benachrichtigungen an.", 3, _link(cfg, "start"), anbieter)
    if not erg:
        raise kern.AmwFehler("kein Anbieter eingeschaltet" if not anbieter else f"{anbieter} unbekannt")
    return {a: ("ok" if e is None else str(e)) for a, e in erg.items()}


# --- Ereignisse und Versand ----------------------------------------------------------------------

def _link(cfg, sicht):
    basis = cfg.get("link") or ""
    if not basis:
        from . import einstellungen
        basis = f"http://127.0.0.1:{einstellungen.wert('port')}/"
    return basis.rstrip("/") + "/#" + sicht


def _minuten_alt(utc):
    return (time.time() - db_sek(utc)) / 60


def db_sek(utc):
    return datetime.datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp()


def ereignisse(con, pid, cfg):
    """Alles, was gemeldet werden soll, mit eindeutigem Schlüssel (nur Neues seit dem Einschalten)."""
    seit = cfg.get("seit_utc") or db.jetzt()
    aus = []
    for f in con.execute("SELECT id, von, zeit_utc FROM frage WHERE projekt_id = ? AND an = 'entwickler' AND status = 'offen'"
                         " AND kurz NOT LIKE 'GEPARKT%' AND zeit_utc >= ?", (pid, seit)):
        aus.append(("frage", f"frage:{f['id']}", f"Neue Frage F{f['id']}", f"von {f['von']}", "fragen"))
        if _minuten_alt(f["zeit_utc"]) >= ERINNERN_NACH_MIN:
            aus.append(("frage", f"frage:{f['id']}:erinnerung", f"Frage F{f['id']} wartet seit {ERINNERN_NACH_MIN} min",
                        f"von {f['von']}", "fragen"))
    for n in con.execute("SELECT n.id, n.von, n.art FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id"
                         " WHERE n.projekt_id = ? AND e.agent = ? AND e.status = 'offen' AND n.zeit_utc >= ?",
                         (pid, kern.ENTWICKLER, seit)):
        aus.append(("nachricht", f"nachricht:{n['id']}", f"Nachricht #{n['id']} von {n['von']}", n["art"], "start"))
    from . import ueberwachung
    for w in ueberwachung.warnungen(con, pid):
        aus.append(("warnung", f"warnung:{w['schluessel']}", "Achtung", w["text"], "start"))
    for s in con.execute("SELECT s.id, a.kennung, s.ereignis, s.ereignis_utc FROM sitzung s JOIN agent a ON a.id = s.agent_id"
                         " WHERE a.projekt_id = ? AND s.zustand = 'aktiv' AND s.ereignis IN ('wartet_freigabe', 'wartet_eingabe')"
                         " AND s.ereignis_utc >= ?", (pid, seit)):
        if _minuten_alt(s["ereignis_utc"]) >= EINGABE_NACH_MIN:
            was = "eine Freigabe" if s["ereignis"] == "wartet_freigabe" else "Eingabe"
            aus.append(("eingabe", f"eingabe:{s['id']}:{s['ereignis_utc']}", f"{s['kennung']} wartet auf {was}",
                        f"seit {int(_minuten_alt(s['ereignis_utc']))} min – im Fenster des Agenten", "start"))
    for h in con.execute("SELECT id, gilt_fuer, von, seit_utc, aufgehoben_utc FROM sperre WHERE projekt_id = ? AND art = 'halt'"
                         " AND (seit_utc >= ? OR aufgehoben_utc >= ?)", (pid, seit, seit)):
        if h["seit_utc"] >= seit:
            aus.append(("halt", f"halt:{h['id']}", f"HALT für {h['gilt_fuer']}", f"gesetzt von {h['von']}", "start"))
        if h["aufgehoben_utc"] and h["aufgehoben_utc"] >= seit:
            aus.append(("halt", f"weiter:{h['id']}", f"Halt aufgehoben ({h['gilt_fuer']})", "", "start"))
    return [{"ereignis": e, "schluessel": k, "titel": t, "text": x, "sicht": s} for e, k, t, x, s in aus
            if cfg["ereignisse"].get(e, True)]


def _in_ruhe(cfg, jetzt=None):
    r = cfg["ruhe"]
    if not r.get("an"):
        return False
    t = (jetzt or datetime.datetime.now()).strftime("%H:%M")
    return (r["von"] <= t < r["bis"]) if r["von"] < r["bis"] else (t >= r["von"] or t < r["bis"])


def runde(con, pid, cfg=None, jetzt=None):
    """Eine Wächter-Runde: neue Ereignisse eintragen, fällige verschicken. Rückgabe: Liste kurzer Texte fürs Protokoll."""
    cfg = cfg or laden()
    if not cfg["an"] or not any(cfg[a]["an"] for a in ANBIETER):
        return []
    with db.schreiben(con):
        for e in ereignisse(con, pid, cfg):
            con.execute("INSERT OR IGNORE INTO push_versand (zeit_utc, ereignis, schluessel, titel, text, prioritaet, sicht)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?)", (db.jetzt(), e["ereignis"], e["schluessel"], e["titel"], e["text"],
                                                          EREIGNISSE[e["ereignis"]][1], e["sicht"]))
    jetzt_s = time.time()
    faellig = []
    for p in con.execute("SELECT * FROM push_versand WHERE ergebnis IN ('offen', 'fehler') AND versuche < ?"
                         " ORDER BY id", (len(WIEDERHOLEN_NACH_S),)).fetchall():
        if p["versuche"] and jetzt_s - db_sek(p["geaendert_utc"]) < WIEDERHOLEN_NACH_S[p["versuche"]]:
            continue
        if _in_ruhe(cfg, jetzt) and p["prioritaet"] < 5:
            continue                                   # nach der Ruhezeit gesammelt
        faellig.append(p)
    if not faellig:
        return []
    stunde = con.execute("SELECT count(DISTINCT buendel) FROM push_versand WHERE ergebnis IN ('gesendet', 'teilweise')"
                         " AND geaendert_utc >= ?", (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(jetzt_s - 3600)),)).fetchone()[0]
    frei = max(0, int(cfg["max_je_stunde"]) - stunde)
    gruppen = {}
    for p in faellig:
        gruppen.setdefault(p["ereignis"], []).append(p)
    protokoll = []
    reihenfolge = sorted(gruppen, key=lambda e: -EREIGNISSE[e][1])
    if frei < len(reihenfolge) and frei > 0:          # Grenze: alles Übrige in eine Sammelmeldung
        rest = [p for e in reihenfolge[frei - 1:] for p in gruppen.pop(e)]
        gruppen["sammel"] = rest
        reihenfolge = reihenfolge[:frei - 1] + ["sammel"]
    elif frei == 0:
        return []
    for art in reihenfolge:
        teile = gruppen[art]
        prio = max(p["prioritaet"] for p in teile)
        if len(teile) == 1:
            titel, text, sicht = teile[0]["titel"], teile[0]["text"] or "", teile[0]["sicht"]
        else:
            name = EREIGNISSE[art][2] if art in EREIGNISSE else "Meldungen"
            titel = f"{len(teile)} {name}"
            text = " · ".join(p["titel"] for p in teile)[:900]
            sicht = teile[0]["sicht"] if art in EREIGNISSE else "start"
        erg = senden(cfg, "AMW: " + titel, text, prio, _link(cfg, sicht))
        ok = [a for a, e in erg.items() if e is None]
        fehl = {a: e for a, e in erg.items() if e is not None}
        if not fehl:
            ergebnis = "gesendet"
        elif ok:
            ergebnis = "teilweise"                     # nicht wiederholen – sonst doppelt bei den anderen
        else:
            ergebnis = "fehler" if any(e.vorlaeufig for e in fehl.values()) else "unterdrueckt"
        fehltext = "; ".join(f"{a}: {e}" for a, e in fehl.items())[:500] or None
        with db.schreiben(con):
            for p in teile:
                con.execute("UPDATE push_versand SET ergebnis = ?, fehler = ?, versuche = versuche + 1, kanaele = ?, buendel = ?,"
                            " geaendert_utc = ? WHERE id = ?", (ergebnis, fehltext, ",".join(erg), teile[0]["id"], db.jetzt(), p["id"]))
        protokoll.append(f"{titel} → {ergebnis}" + (f" ({fehltext})" if fehltext else ""))
    return protokoll


def protokoll(con, n=30):
    return [dict(r) for r in con.execute("SELECT zeit_utc, geaendert_utc, ereignis, titel, prioritaet, kanaele, ergebnis,"
                                         " fehler, versuche FROM push_versand ORDER BY id DESC LIMIT ?", (n,))]
