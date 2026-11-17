"""Versionsnummer schon bei der Prüfbitte prüfen (A1753, Lückenliste TL, Beschluss parameter-statt-regeln, Marcel W2168).

Zweimal vergaben zwei Coder dieselbe Nummer (1.96.0, 1.98.0) – gemerkt erst beim Ausliefern. Jetzt liest `amw pruefung bitte`
die Version aus dem Stand und lehnt ab, wenn sie
  - nicht über der Version auf main liegt,
  - als Tag v<Nummer> schon existiert,
  - oder eine andere Aufgabe sie in einer offenen oder grünen, noch nicht ausgelieferten Prüfung trägt.
Dieselbe Aufgabe darf ihre Nummer behalten (neuer Stand nach ROT, neu aufgesetzt). Die Meldung nennt die nächste freie Nummer.
Ohne Projektordner oder ohne erkennbare Versionsdatei prüft die AMW nichts (andere Projekte haben andere Schemata).
"""
import json
import re
import subprocess

from . import kern

VERSION_PY = re.compile(r"""__version__\s*=\s*["']([^"']+)["']""")


def _git(ordner, *args):
    try:
        r = subprocess.run(["git", "-C", ordner, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=30, stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def version_im_stand(ordner, sha):
    """Versionsnummer im Stand: VERSION, amw/__init__.py (__version__) oder package.json („version“) – sonst None."""
    roh = _git(ordner, "show", f"{sha}:VERSION")
    if roh and kern.version_teile(roh.strip()):
        return roh.strip()
    roh = _git(ordner, "show", f"{sha}:amw/__init__.py")
    m = VERSION_PY.search(roh or "")
    if m and kern.version_teile(m.group(1)):
        return m.group(1)
    roh = _git(ordner, "show", f"{sha}:package.json")
    try:
        v = json.loads(roh)["version"] if roh else None
    except (ValueError, KeyError, TypeError):
        v = None
    return v if v and kern.version_teile(v) else None


def pruefen(con, pid, sha, aufgabe_id):
    """Wirft AmwFehler, wenn die Nummer im Stand schon vergeben ist; gibt sie sonst zurück (oder None: nichts zu prüfen)."""
    ordner = kern.projekt_ordner(con, pid)
    if not ordner:
        return None
    v = version_im_stand(ordner, sha)
    if not v:
        return None
    t = kern.version_teile(v)
    belegt = {}                                          # Nummer → wer sie trägt (für die Meldung und die nächste freie)
    live = version_im_stand(ordner, "main")
    if live:
        belegt[live] = "main"
    for tag in (_git(ordner, "tag", "--list", "v*") or "").split():
        if kern.version_teile(tag[1:]):
            belegt.setdefault(tag[1:], f"Tag {tag}")
    gesehen = set()
    for p in con.execute("SELECT * FROM pruefung WHERE projekt_id = ? AND ergebnis IN ('offen', 'gruen') AND aufgabe_id IS NOT NULL"
                         " AND aufgabe_id != ? ORDER BY id DESC LIMIT 60", (pid, aufgabe_id or 0)).fetchall():
        if p["aufgabe_id"] in gesehen:                   # A1873 (F1): je Aufgabe belegt nur ihre neueste offene oder grüne Prüfung –
            continue                                     # eine neu aufgesetzte Aufgabe gibt die alte Nummer frei (17.11.: P248)
        gesehen.add(p["aufgabe_id"])                     # (rote zählen nicht: nach einer roten bleibt die ältere grüne belegend)
        a = con.execute("SELECT status FROM aufgabe WHERE id = ?", (p["aufgabe_id"],)).fetchone()
        if a and a["status"] in ("fertig", "verworfen"):
            continue
        if p["ergebnis"] == "gruen" and _git(ordner, "merge-base", "--is-ancestor", p["sha"], "main") is not None:
            continue                                     # schon draußen
        pv = version_im_stand(ordner, p["sha"])
        if pv:
            belegt.setdefault(pv, f"A{p['aufgabe_id']} (P{p['id']}, {p['zweig']})")
    hoechste = max((kern.version_teile(x) for x in belegt), default=(0, 0, 0))
    vorschlag = f"{hoechste[0]}.{hoechste[1]}.{hoechste[2] + 1} oder {hoechste[0]}.{hoechste[1] + 1}.0"
    if live and t <= kern.version_teile(live):
        raise kern.AmwFehler(f"Version {v} im Stand liegt nicht über main ({live}) – nächste freie Nummer: {vorschlag}")
    if v in belegt:
        raise kern.AmwFehler(f"Version {v} ist schon vergeben ({belegt[v]}) – nächste freie Nummer: {vorschlag}")
    return v
