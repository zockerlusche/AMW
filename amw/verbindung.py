"""Prüf-Knöpfe der Einstellungen: Ist der Online-Speicher erreichbar und eingerichtet? Antwortet die Online-Seite?

Nur lesend und nur vom PC aus angestoßen. Die Antwort nennt Schritte mit einem festen Namen (die Oberfläche übersetzt
sie) – nie Schlüssel und nie Antworttexte des Speichers. Geprüft wird das Gespeicherte, nicht das gerade Eingetippte.
"""
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from . import abgleich, push

TABELLEN = ("zustand", "eingang", "projekt")       # ohne sie kann weder der Abgleich noch die Online-Seite arbeiten
HILFE_PROBE = "/hilfe/neues-projekt.de.json"       # öffentlich ausgeliefert, seit es die Hilfen in der Workbench gibt


def _schritt(name, ok, wert=None):
    return {"name": name, "ok": bool(ok), "wert": wert}


def _ergebnis(schritte):
    return {"ok": all(s["ok"] for s in schritte), "schritte": schritte}


def speicher(sp=None):
    """Anmelden und nachsehen, ob die Tabellen da sind."""
    sp = sp or abgleich.speicher_aus_zugang(nur_wenn_an=False)
    if sp is None:
        return _ergebnis([_schritt("zugang", False)])
    beginn = time.time()
    try:
        namen = {z[0] for z in sp.ausfuehren([("SELECT name FROM sqlite_master WHERE type = 'table'", [])])[0]}
    except (OSError, ValueError, KeyError, TypeError) as e:
        return _ergebnis([_schritt("anmelden", False, str(e)[:160])])
    fehlen = sorted(set(TABELLEN) - namen)
    return _ergebnis([_schritt("anmelden", True, int((time.time() - beginn) * 1000)),
                      _schritt("tabellen", not fehlen, ", ".join(fehlen) if fehlen else len(namen))])


def _holen(adresse):
    """(Status, Text) einer Adresse; wirft OSError, wenn keine Verbindung zustande kommt."""
    from . import betriebsart
    betriebsart.pruefe(adresse, "Prüfung der Online-Seite")
    anfrage = urllib.request.Request(adresse, headers={"User-Agent": "amw-pruefung"})
    try:
        with urllib.request.urlopen(anfrage, timeout=15) as r:
            return r.status, r.read(200_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


def seiten_version(sp=None):
    """Die Version, die die Online-Seite bei der letzten Anmeldung im Online-Speicher hinterlegt hat – oder None (kein
    Speicher, nicht erreichbar, blockiert oder seit der Bereitstellung noch niemand angemeldet)."""
    try:
        sp = sp or abgleich.speicher_aus_zugang(nur_wenn_an=False)
        if sp is None:
            return None
        z = sp.ausfuehren([("SELECT wert FROM zustand WHERE schluessel = 'web_version'", [])])[0]
        return str(z[0][0]) if z and z[0][0] else None
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return None


def seite(adresse=None, holen=_holen, version=seiten_version):
    """Antwortet die eingetragene Adresse über https, liegt dort eine AMW-Seite, und hat sie die Version dieses PCs?"""
    adresse = (push.laden().get("link") or "" if adresse is None else adresse).strip().rstrip("/")
    if not adresse:
        return _ergebnis([_schritt("adresse", False)])
    if not adresse.startswith("https://"):
        return _ergebnis([_schritt("https", False, adresse)])
    beginn = time.time()
    try:
        status, _ = holen(adresse + "/")
    except (OSError, ValueError) as e:
        return _ergebnis([_schritt("https", True), _schritt("verbindung", False, str(getattr(e, "reason", e))[:160])])
    schritte = [_schritt("https", True), _schritt("antwort", status == 200, f"HTTP {status}, {int((time.time() - beginn) * 1000)} ms")]
    if status == 200:
        try:
            status, text = holen(adresse + HILFE_PROBE)
            hilfe = status == 200 and isinstance(json.loads(text), dict)
        except (OSError, ValueError):
            hilfe = False
        schritte.append(_schritt("amw", hilfe))
        online = version() if hilfe else None
        if online:                                   # nur wenn die Seite ihre Version schon hinterlegt hat
            from . import __version__
            schritte.append(_schritt("version", online == __version__, online if online == __version__ else f"{online}, dieser PC: {__version__}"))
    return _ergebnis(schritte)


def _ziel(adresse):
    """(Rechnername, Port) einer Adresse – ohne Pfad, Benutzer oder Schlüssel."""
    a = str(adresse or "").strip()
    try:
        u = urllib.parse.urlsplit(a if "://" in a else "//" + a)
        port = u.port
    except ValueError:
        return "", None
    return (u.hostname or "").lower(), port or (80 if u.scheme in ("http", "ws") else 443)


def liste(con=None):
    """Jede Adresse, zu der diese Installation eine Verbindung aufbaut – aus der Konfiguration gelesen, ohne etwas zu
    verbinden. Je Zeile: wer, Ziel (Rechner:Port), wohin es führt (pc | firma | internet), ob es gerade benutzt wird und ob
    die Betriebsart es zulässt. „fehler“ zählt, was eingeschaltet, aber gesperrt ist."""
    from . import betriebsart, einstellungen
    art = betriebsart.aktuell()
    aufloesen = None if art == "pc" else betriebsart._aufloesen
    zeilen = []

    def dazu(wer, adresse, aktiv, zusatz=None, nur_pruefung=False):
        rechner, port = _ziel(adresse)
        if not rechner:
            return
        stufe = betriebsart.netz(adresse, aufloesen)
        zeilen.append({"wer": wer, "zusatz": zusatz, "rechner": rechner, "port": port, "stufe": stufe, "aktiv": bool(aktiv),
                       "nur_pruefung": nur_pruefung, "erlaubt": stufe in betriebsart.ERLAUBT[art]})

    dazu("workbench", f"http://127.0.0.1:{einstellungen.wert('port')}", True)
    try:
        with open(abgleich.zugang_pfad(), encoding="utf-8") as f:
            z = json.load(f)
    except (OSError, ValueError):
        z = {}
    if z.get("url") and not z.get("sqlite"):
        dazu("speicher", z["url"], z.get("abgleich"))
    try:
        cfg = push.laden()
    except Exception:
        cfg = {}
    if cfg.get("link"):
        dazu("seite", cfg["link"], False, nur_pruefung=True)   # dorthin verbindet sich die AMW nur für „Seite erreichbar?“
    fest = {"ntfy": (cfg.get("ntfy") or {}).get("server"), "pushover": "https://api.pushover.net", "telegram": "https://api.telegram.org"}
    for anbieter, adresse in fest.items():
        if (cfg.get(anbieter) or {}).get("an") and adresse:
            dazu("push", adresse, cfg.get("an"), anbieter)
    if con is not None:
        try:
            for r in con.execute("SELECT name, endpunkt FROM ki ORDER BY id"):
                dazu("ki", r["endpunkt"], True, r["name"])
        except Exception:
            pass
    return {"betriebsart": art, "gewaehlt": betriebsart.gewaehlt(), "zeilen": zeilen,
            "fehler": sum(1 for x in zeilen if x["aktiv"] and not x["erlaubt"])}


def erreichbar(con=None, verbinde=None):
    """Wie liste(), dazu je erlaubter Zeile: kommt eine Verbindung zustande? Nur der Verbindungsaufbau, keine Daten.
    Gesperrte Ziele werden nicht angefasst."""
    def offen(rechner, port):
        try:
            with socket.create_connection((rechner, port), timeout=4):
                return True
        except OSError:
            return False

    d = liste(con)
    for x in d["zeilen"]:
        x["erreichbar"] = (verbinde or offen)(x["rechner"], x["port"]) if x["erlaubt"] else None
    return d


def pruefen(was, con=None):
    if was == "speicher":
        return speicher()
    if was == "seite":
        return seite()
    if was == "verbindungen":
        return liste(con)
    if was == "erreichbar":
        return erreichbar(con)
    raise LookupError(f"unbekannte Prüfung: {was}")
