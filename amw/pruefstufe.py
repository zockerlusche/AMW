"""Prüfstufe einer Prüfbitte aus den geänderten Dateien (A1656).

Die AMW sieht nach, welche Dateien ein Stand gegenüber der Basis (main) ändert, und ordnet ihn einer Stufe zu: hoch
(Datenbank, Anmeldung, Rechte, Dateiaustausch, Warteschlange, Auslieferung …), sobald eine Datei ein Hoch-Muster trifft;
niedrig nur, wenn ALLE Dateien Niedrig-Mustern folgen (Doku, Tests, Versionsnummer); sonst mittel (TL 14.11.: niedrig =
nur Doku/Tests). Die Muster stehen je Projekt in den Projekt-Einstellungen („pruef_muster“: {"hoch": [...], "mittel": [...],
"niedrig": [...]}); ohne Eintrag gilt die Vorgabe unten. Muster wie bei fnmatch – „*“ passt auch über „/“ hinweg.

Wort: „Prüfstufe“ – „Risiko“ heißt in der AMW schon etwas anderes (Planung › Risiken). Nur lesen, ändert nichts.
"""
import fnmatch
import json
import subprocess

# hoch: alles mit Rechte- oder Sicherheitsprüfungen (TL 14.11., P157) – Befehlszeile (Kanal, Läufe), Online-Aktionen, Workbench
# (Host/Heimnetz, Schlüssel), Dienst (Weckruf, Aufpasser), KI (beendet Prozesse), PC-Einstellungen (Netzbereiche), Lead-Runde, PHP
VORGABE = {"hoch": ["amw/migration_*.sql", "amw/schema.sql", "amw/db.py", "amw/benutzer.py", "amw/anmeldung*", "amw/kern.py",
                    "amw/hook.py", "amw/bruecke.py", "amw/laufdienst.py", "amw/auslieferung.py", "amw/betrieb.py", "amw/cli.py",
                    "amw/aktionen.py", "amw/workbench.py", "amw/dienst.py", "amw/ki.py", "amw/einstellungen.py", "amw/runde.py",
                    "web/*.php"],
           "mittel": ["amw/workbench.html", "web/*", "doc/hilfe/*"],
           "niedrig": ["doc/*", "tests/*", "*.md", "amw/__init__.py", "web/inc/VERSION"]}
STUFEN = ("niedrig", "mittel", "hoch")
UNBEKANNT = "unbekannt"


def muster(con, pid):
    """Muster des Projekts, sonst die Vorgabe."""
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    m = json.loads(r[0] or "{}").get("pruef_muster") if r else None
    if isinstance(m, dict) and any(m.get(k) for k in ("hoch", "mittel", "niedrig")):
        return {k: list(m.get(k) or []) for k in ("hoch", "mittel", "niedrig")}
    return VORGABE


def dateien(ordner, sha, basis="main"):
    """Geänderte Dateien von basis bis sha (ab dem gemeinsamen Vorfahren), None wenn Git sie nicht liefert."""
    if not ordner or not sha:
        return None
    try:
        r = subprocess.run(["git", "-C", ordner, "diff", "--name-only", f"{basis}...{sha}"], capture_output=True, text=True,
                           timeout=60, stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return [z.strip() for z in r.stdout.splitlines() if z.strip()]


def einstufen(liste, m):
    """(stufe, [Dateien, die die Stufe bestimmen]) – None als Liste ergibt „unbekannt“."""
    if liste is None:
        return UNBEKANNT, []
    passt = lambda d, stufe: any(fnmatch.fnmatch(d, x) for x in m.get(stufe) or [])
    for stufe in ("hoch", "mittel"):
        treffer = [d for d in liste if passt(d, stufe)]
        if treffer:
            return stufe, treffer
    rest = [d for d in liste if not passt(d, "niedrig")]
    return ("mittel", rest) if rest else ("niedrig", [])   # niedrig nur, wenn alles Doku/Tests ist


def stufe(con, pid, sha, basis="main"):
    """Für eine Prüfbitte: {"stufe", "treffer", "dateien"} aus dem Projektordner."""
    from . import kern
    liste = dateien(kern.projekt_ordner(con, pid), sha, basis)
    s, treffer = einstufen(liste, muster(con, pid))
    return {"stufe": s, "treffer": treffer, "dateien": liste}


def hoeher(a, b):
    """Die höhere von zwei Stufen (unbekannt zählt wie hoch)."""
    rang = {"niedrig": 0, "mittel": 1, "hoch": 2, UNBEKANNT: 2}
    return a if rang[a] >= rang[b] else b


def regel(con, pid, info, bauer, pruefer, angegeben=None):
    """Nur mit Projekt-Wahl „pruefstufen = an“: hoch → der Lead prüft, mittel → nicht der Bauer selbst. angegeben: der
    Bauer stuft höher ein (nie niedriger). Rückgabe: die geltende Stufe; Verstoß → AmwFehler."""
    from . import kern
    s = info["stufe"]
    if angegeben:
        if angegeben not in STUFEN:
            raise kern.AmwFehler(f"--stufe: {' | '.join(STUFEN)}")
        if hoeher(angegeben, s) != angegeben:
            raise kern.AmwFehler(f"Prüfstufe {s} aus den geänderten Dateien – niedriger einstufen geht nicht")
        s = angegeben
    if kern.projekt_wahl(con, pid, "pruefstufen") != "an":
        return s
    if s in ("hoch", UNBEKANNT) and not kern.ist_lead(con, pid, pruefer):
        lead = kern.lead(con, pid) or "der Lead"
        raise kern.AmwFehler(f"Prüfstufe {s} ({', '.join(info['treffer'][:3]) or 'geänderte Dateien unbekannt'}) – prüfen muss {lead}:"
                             f" --pruefer {lead}")
    if s == "mittel" and pruefer == bauer:
        raise kern.AmwFehler("Prüfstufe mittel – ein anderer Agent prüft, nicht der Bauer selbst")
    return s


def zeile(info, hoechstens=4):
    """„Prüfstufe hoch – amw/bruecke.py, amw/db.py (+2)“ für die Prüfbitte-Nachricht."""
    s, treffer = info["stufe"], info["treffer"]
    if s == UNBEKANNT:
        return "Prüfstufe unbekannt – geänderte Dateien nicht lesbar (Projektordner oder Stand fehlt)"
    if not treffer:
        return f"Prüfstufe {s} – {len(info['dateien'] or [])} Datei(en), nur Doku und Tests"
    mehr = f" (+{len(treffer) - hoechstens})" if len(treffer) > hoechstens else ""
    return f"Prüfstufe {s} – {', '.join(treffer[:hoechstens])}{mehr}"
