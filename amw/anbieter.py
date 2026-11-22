"""Weitere Anbieter und lokale Modelle je Projekt (A1931, TH159, Entscheidungen CCamwTL #29930).

Jeder Anbieter ist extern, auch Anthropic. Der Mensch gibt Anbieter je Projekt frei (`amw anbieter freigeben`, nur im eigenen
Terminal, auch nicht der Lead). In der Datenbank steht je Anbieter: Basis-URL einer Anthropic-kompatiblen Schnittstelle, der
PFAD zu einer lokalen Schlüsseldatei (nie der Schlüssel selbst – nicht in Datenbank, Repo, Nachricht, Bericht oder Ereignis),
lokal ja/nein und die Modelle (das erste prüft die Negativprobe).

Ein Paket nennt seinen Anbieter im Modell: `anbieter@modell` (z. B. minimax@MiniMax-M2; `amw aufgabe aendern N --anbieter`).
Ohne Präfix gilt anthropic – ohne Eintrag freigegeben wie bisher. Der Arbeiter startet mit eigener --settings-Datei:
env ANTHROPIC_BASE_URL und apiKeyHelper = amw-anbieter-schluessel.py mit dem Pfad; das Skript gibt die Datei nur aus, wenn ihr Pfad in
der Freigabe-Liste steht (FREIGABE, von der AMW geschrieben). So steht der Schlüssel in keiner Umgebung und keiner Datei des
Platzes. Lokale Anbieter belegen die Grafikkarte (Regel 3: bis zur Lauf-Schlange für gpu gesperrt). Vor dem ersten Paket prüft
die AMW den Anbieter mit der Negativprobe (versionsprobe, A1906-Weg) – auch, dass der Schlüssel unsichtbar bleibt.
"""
import json
import os
import re
import sys

from . import db, kern

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from .anbieter_schluessel import FREIGABE  # noqa: E402 – nur Pfade freigegebener Schlüsseldateien (daten/ ist nicht versioniert)
EINSTIEG = os.path.join(WURZEL, "amw-anbieter-schluessel.py")
STANDARD = "anthropic"
NAME = re.compile(r"[a-z][a-z0-9_-]{1,29}")
TRENNER = "@"


def zerlegen(modell):
    """„anbieter@modell“ → (anbieter, modell); ohne Präfix (anthropic, modell)."""
    m = (modell or "").strip()
    if TRENNER in m:
        a, rest = m.split(TRENNER, 1)
        return a.strip().lower(), rest.strip() or None
    return STANDARD, m or None


def liste(con, pid):
    """Freigegebene Anbieter des Projekts: {name: {basis_url, schluessel_datei, lokal, modelle}} (ohne den Standard)."""
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    try:
        a = json.loads((r[0] if r else None) or "{}").get("anbieter") or {}
    except ValueError:
        return {}
    return a if isinstance(a, dict) else {}


def eintrag(con, pid, name):
    """Der freigegebene Anbieter oder None. anthropic ohne Eintrag: {"name": "anthropic", "standard": True} (wie bisher)."""
    name = (name or STANDARD).lower()
    e = liste(con, pid).get(name)
    if e:
        return dict(e, name=name)
    return {"name": STANDARD, "standard": True} if name == STANDARD else None


def _innen(pfad, ordner):
    if not ordner:
        return False
    a, o = os.path.normcase(os.path.abspath(pfad)), os.path.normcase(os.path.abspath(ordner))
    return a == o or a.startswith(o.rstrip("\\/") + os.sep)


def pruefen(con, pid, name, basis_url, schluessel_datei, lokal=False, modelle=None):
    """Eintrag prüfen und vereinheitlichen; AmwFehler mit Grund. Die Schlüsseldatei wird nur auf Dasein geprüft, nie gelesen."""
    from . import platz
    name = (name or "").strip().lower()
    if not NAME.fullmatch(name) or name == STANDARD:
        raise kern.AmwFehler(f"Anbieter „{name}“: klein, Buchstabe zuerst, dann Buchstaben/Ziffern/-/_ (2–30); anthropic ist der Standard")
    url = (basis_url or "").strip().rstrip("/")
    if not re.fullmatch(r"https://[^\s]+", url) and not (lokal and re.fullmatch(r"http://(localhost|127\.0\.0\.1)(:\d+)?(/[^\s]*)?", url)):
        raise kern.AmwFehler("Basis-URL: https://… (lokal auch http://localhost:…)")
    s = (schluessel_datei or "").strip()
    if not s or not os.path.isabs(s):
        raise kern.AmwFehler("Schlüsseldatei: absoluter Pfad zu einer Datei auf diesem PC")
    s = os.path.abspath(s)
    if not os.path.isfile(s):
        raise kern.AmwFehler(f"Schlüsseldatei {s} gibt es nicht")
    wurzel, _ = platz.einstellung(con, pid)
    for ordner, was in ((WURZEL, "im Ordner der AMW"), (kern.projekt_ordner(con, pid), "im Projektordner"), (wurzel, "in den Arbeitsplätzen")):
        if _innen(s, ordner):
            raise kern.AmwFehler(f"Schlüsseldatei liegt {was} – sie gehört außerhalb jedes Repos und Arbeitsplatzes")
    ms = [m.strip() for m in (modelle or []) if m and m.strip()]
    if not ms or any(TRENNER in m or len(m) > 100 for m in ms):
        raise kern.AmwFehler("Modelle: mindestens eins (das erste prüft die Negativprobe), ohne @")
    return name, {"basis_url": url, "schluessel_datei": s, "lokal": bool(lokal), "modelle": list(dict.fromkeys(ms))}


def _speichern(con, pid, von, art, text, aendern):
    with db.schreiben(con):
        e = json.loads(con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()[0] or "{}")
        a = e.get("anbieter") if isinstance(e.get("anbieter"), dict) else {}
        aendern(a)
        if a:
            e["anbieter"] = a
        else:
            e.pop("anbieter", None)
        con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?", (json.dumps(e, ensure_ascii=False), pid))
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=art, text=json.dumps(text, ensure_ascii=False))
    freigabe_schreiben(con)


def freigeben(con, pid, von, name, basis_url, schluessel_datei, lokal=False, modelle=None):
    """Nur der Mensch (die Befehlszeile prüft zusätzlich: nicht aus einer Agenten-Sitzung). Ereignis ohne Schlüssel."""
    if von != kern.ENTWICKLER:
        raise kern.AmwFehler("Anbieter gibt nur der Mensch frei (--von Entwickler im eigenen Terminal) – auch nicht der Lead")
    name, e = pruefen(con, pid, name, basis_url, schluessel_datei, lokal, modelle)
    _speichern(con, pid, von, "anbieter_freigegeben", dict(e, name=name), lambda a: a.__setitem__(name, e))
    return name, e


def entfernen(con, pid, von, name):
    if von != kern.ENTWICKLER:
        raise kern.AmwFehler("Anbieter entfernt nur der Mensch")
    name = (name or "").strip().lower()
    if name not in liste(con, pid):
        raise kern.AmwFehler(f"Anbieter {name} ist in diesem Projekt nicht freigegeben")
    _speichern(con, pid, von, "anbieter_entfernt", {"name": name}, lambda a: a.pop(name, None))
    return name


def freigabe_schreiben(con, ziel=None):
    """Die Liste der freigegebenen Schlüsseldateien aller Projekte (nur Pfade) für amw-anbieter-schluessel.py."""
    pfade = []
    for (pid,) in con.execute("SELECT id FROM projekt").fetchall():
        pfade += [os.path.normcase(os.path.abspath(e["schluessel_datei"])) for e in liste(con, pid).values() if e.get("schluessel_datei")]
    ziel = ziel or FREIGABE
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    tmp = f"{ziel}.{os.getpid()}.neu"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"pfade": sorted(set(pfade))}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ziel)
    return ziel


def settings_teil(e, einstieg=None, python=None):
    """Was die --settings-Datei des Arbeiters für Anbieter e zusätzlich braucht – None für den Standard (anthropic)."""
    if not e or e.get("standard"):
        return None
    helfer = f'"{python or sys.executable}" -I -X utf8 "{einstieg or EINSTIEG}" "{e["schluessel_datei"]}"'
    return {"env": {"ANTHROPIC_BASE_URL": e["basis_url"]}, "apiKeyHelper": helfer}
