"""Prüf-Knöpfe der Einstellungen: Ist der Online-Speicher erreichbar und eingerichtet? Antwortet die Online-Seite?

Nur lesend und nur vom PC aus angestoßen. Die Antwort nennt Schritte mit einem festen Namen (die Oberfläche übersetzt
sie) – nie Schlüssel und nie Antworttexte des Speichers. Geprüft wird das Gespeicherte, nicht das gerade Eingetippte.
"""
import json
import time
import urllib.error
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
    anfrage = urllib.request.Request(adresse, headers={"User-Agent": "amw-pruefung"})
    try:
        with urllib.request.urlopen(anfrage, timeout=15) as r:
            return r.status, r.read(200_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


def seite(adresse=None, holen=_holen):
    """Antwortet die eingetragene Adresse über https, und liegt dort eine AMW-Seite?"""
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
    return _ergebnis(schritte)


def pruefen(was):
    if was == "speicher":
        return speicher()
    if was == "seite":
        return seite()
    raise LookupError(f"unbekannte Prüfung: {was}")
