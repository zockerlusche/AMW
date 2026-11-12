"""Versionshinweise ohne KI: aus den fertigen Aufgaben seit der letzten Version ein Entwurf „Neu / Verbessert / Behoben“.

Quelle ist zuerst der Satz für Nutzer, den der Agent beim Abschließen angibt (`amw aufgabe fertig … --hinweis …
--gruppe neu|verbessert|behoben`). Fehlt er, macht eine Regel einen Vorschlag aus der Zusammenfassung (erster Satz,
interne Verweise entfernt, Gruppe nach Stichworten) – erkennbar als Vorschlag. Der Lead gibt den Text mit
`amw release version … ` frei; erst dann steht er für alle da.
"""
import re

GRUPPEN = ("neu", "verbessert", "behoben")
NAMEN = {"neu": "Neu", "verbessert": "Verbessert", "behoben": "Behoben"}
BEHOBEN = re.compile(r"\b(fix|behoben|behebt|fehler|kaputt|abgefangen|repariert|wieder)\b", re.I)
NEU = re.compile(r"\b(neu|neue[rsn]?|erstmals|hinzu|eingeführt)\b", re.I)
NICHT = re.compile(r"^(nicht umgesetzt|auf anweisung .* geschlossen|verworfen|kein[e]? änderung)", re.I)
INTERN = re.compile(r"\s*\((?:[^()]*\b(?:[WBDF]\d{3,}|#\d{3,}|[0-9a-f]{7,40})\b[^()]*)\)|\b(?:[WB]\d{3,}|#\d{3,})\b"
                    r"|\bRelease \d+\.\d+\.\d+\b|\bFix [0-9a-f]{7}\b|,?\s*live geprüft")


def gruppe_pruefen(g):
    g = (g or "").strip().lower()
    if g and g not in GRUPPEN:
        raise ValueError(f"Gruppe „{g}“ gibt es nicht – neu, verbessert oder behoben")
    return g or None


def satz(text):
    """Erster Satz, ohne interne Verweise, mit Großbuchstaben am Anfang (für den Vorschlag ohne Satz des Agenten)."""
    t = " ".join((text or "").split())
    t = re.split(r"(?<=[.!?])\s", t)[0]
    t = INTERN.sub("", t)
    t = re.sub(r"\s{2,}", " ", t).replace(" ,", ",").strip(" ,;:–-")
    t = re.sub(r"^[A-ZÄÖÜ ]{4,}:\s*", lambda m: m.group(0).capitalize(), t)
    return (t[:1].upper() + t[1:]) if t else ""


def regel(titel, zusammenfassung):
    """Vorschlag der Gruppe aus Stichworten (Rückfall, wenn der Agent keine angegeben hat); None = nichts ausgeliefert."""
    if NICHT.search(zusammenfassung or ""):
        return None
    text = f"{titel} {zusammenfassung or ''}"
    return "behoben" if BEHOBEN.search(text) else "neu" if NEU.search(text) else "verbessert"


def seit(con, pid):
    """Zeitpunkt der letzten eingetragenen Version dieses Projekts (oder None)."""
    r = con.execute("SELECT max(zeit_utc) FROM release WHERE projekt_id = ? AND art = 'version'", (pid,)).fetchone()
    return r[0] if r else None


def entwurf(con, pid, ab=None):
    """{gruppe: [{"id", "text", "vorschlag": bool}]} aus den fertigen Aufgaben seit `ab` (Vorgabe: letzte Version)."""
    ab = ab if ab is not None else seit(con, pid)
    aus = {g: [] for g in GRUPPEN}
    for a in con.execute("SELECT id, titel, zusammenfassung, hinweis, hinweis_gruppe FROM aufgabe WHERE projekt_id = ? AND status = 'fertig'"
                         " AND (? IS NULL OR fertig_utc > ?) ORDER BY fertig_utc, id", (pid, ab, ab)):
        if a["hinweis"]:
            g = a["hinweis_gruppe"] or regel(a["titel"], a["zusammenfassung"]) or "verbessert"
            aus[g].append({"id": a["id"], "text": a["hinweis"].strip(), "vorschlag": False})
            continue
        g = a["hinweis_gruppe"] or regel(a["titel"], a["zusammenfassung"])
        if g is None:
            continue
        text = satz(a["zusammenfassung"] or a["titel"])
        if text:
            aus[g].append({"id": a["id"], "text": text, "vorschlag": True})
    return aus


def als_text(e, mit_aufgaben=False):
    """Der Entwurf als Markdown („### Neu“ …) – so wird er als öffentlicher Text gespeichert."""
    teile = []
    for g in GRUPPEN:
        if e.get(g):
            teile.append(f"### {NAMEN[g]}\n" + "\n".join(f"- {x['text']}" + (f" (A{x['id']})" if mit_aufgaben else "") for x in e[g]))
    return "\n\n".join(teile)


def aufgaben(e):
    return ", ".join(f"A{x['id']}" for g in GRUPPEN for x in e.get(g) or [])
