"""Versionshinweise ohne KI: aus den fertigen Aufgaben seit der letzten Version ein Entwurf „Neu / Verbessert / Behoben“.

Quelle ist zuerst der Satz für Nutzer, den der Agent beim Abschließen angibt (`amw aufgabe fertig … --hinweis …
--gruppe neu|verbessert|behoben`). Fehlt er, macht eine Regel einen Vorschlag aus der Zusammenfassung (erster Satz,
interne Verweise entfernt, Gruppe nach Stichworten) – erkennbar als Vorschlag. Der Lead gibt den Text mit
`amw release version … ` frei; erst dann steht er für alle da.
"""
import json
import re

GRUPPEN = ("neu", "verbessert", "behoben")
NAMEN = {"neu": "Neu", "verbessert": "Verbessert", "behoben": "Behoben"}
BEHOBEN = re.compile(r"\b(fix|behoben|behebt|fehler|kaputt|abgefangen|repariert|wieder)\b", re.I)
NEU = re.compile(r"\b(neu|neue[rsn]?|erstmals|hinzu|eingeführt)\b", re.I)
NICHT = re.compile(r"^(nicht umgesetzt|auf anweisung .* geschlossen|verworfen|kein[e]? änderung)", re.I)
INTERN = re.compile(r"\s*\((?:[^()]*\b(?:[WBDF]\d{3,}|#\d{3,}|[0-9a-f]{7,40})\b[^()]*)\)|\b(?:[WB]\d{3,}|#\d{3,})\b"
                    r"|\bRelease \d+\.\d+\.\d+\b|\bFix [0-9a-f]{7}\b|,?\s*live geprüft")


GRUPPE_INTERN = "intern"                   # A1978: nie in den Versionshinweisen – als Ereignis (die Spalte kennt nur GRUPPEN)
INTERN_ART = "hinweis_intern"


def gruppe_pruefen(g, intern_erlaubt=False):
    g = (g or "").strip().lower()
    if g == GRUPPE_INTERN and intern_erlaubt:
        return g
    if g and g not in GRUPPEN:
        raise ValueError(f"Gruppe „{g}“ gibt es nicht – neu, verbessert, behoben" + (" oder intern" if intern_erlaubt else ""))
    return g or None


def ist_intern(con, aid):
    """Das neueste Ereignis hinweis_intern der Aufgabe zählt ({"intern": true|false})."""
    r = con.execute("SELECT text FROM plan_ereignis WHERE aufgabe_id = ? AND art = ? ORDER BY id DESC LIMIT 1", (aid, INTERN_ART)).fetchone()
    try:
        return bool(r and json.loads(r[0] or "{}").get("intern"))
    except ValueError:
        return False


def intern_setzen(con, pid, von, aid, intern):
    """In der Transaktion des Aufrufers: intern → Gruppe und Satz leer, Ereignis; zurück (intern=False) nur das Ereignis."""
    from . import db
    if intern:
        con.execute("UPDATE aufgabe SET hinweis = NULL, hinweis_gruppe = NULL WHERE id = ?", (aid,))
    db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=INTERN_ART, aufgabe_id=aid,
                 text=json.dumps({"intern": bool(intern)}))


def nachtragen(con, pid, von, aid, gruppe=None, hinweis=None):
    """A1978: Gruppe/Satz einer Aufgabe ändern – auch nach dem Abschließen, solange keine Version sie schon enthält.
    Bearbeiter oder Lead. gruppe intern nimmt sie aus den Versionshinweisen."""
    from . import db, kern
    a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    if not a:
        raise kern.AmwFehler(f"A{aid} gibt es nicht")
    if von not in (a["agent"], kern.ENTWICKLER) and not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Den Versionshinweis ändern der Bearbeiter, der Lead oder der Mensch")
    s = seit(con, pid)
    if a["status"] == "fertig" and s and a["fertig_utc"] and a["fertig_utc"] <= s:
        raise kern.AmwFehler(f"A{aid} steht schon in einer eingetragenen Version – dort ändert ihn nur der Lead (amw release version)")
    try:
        g = gruppe_pruefen(gruppe, intern_erlaubt=True)
    except ValueError as e:
        raise kern.AmwFehler(str(e)) from None
    if not g and not (hinweis or "").strip():
        raise kern.AmwFehler("--gruppe neu|verbessert|behoben|intern und/oder --hinweis „Satz“")
    with db.schreiben(con):
        if g == GRUPPE_INTERN:
            intern_setzen(con, pid, von, aid, True)
            return "intern"
        felder = {k: v for k, v in (("hinweis_gruppe", g), ("hinweis", " ".join((hinweis or "").split())[:300] or None)) if v}
        con.execute(f"UPDATE aufgabe SET {', '.join(k + ' = ?' for k in felder)} WHERE id = ?", (*felder.values(), aid))
        if ist_intern(con, aid):
            intern_setzen(con, pid, von, aid, False)
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=ABGELEITET, aufgabe_id=aid,
                     text=json.dumps({"quelle": f"von {von}", "gruppe": False, "text": False}))   # ab jetzt kein Vorschlag mehr
    return g or "Satz"


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


SHA = re.compile(r"^[0-9a-f]{7,40}$")
KOPF = re.compile(r"^(?:(?:A\d+|K\d+[a-z]?|TH\d+|P\d+)(?:\s*\+\s*(?:A\d+|K\d+[a-z]?|TH\d+))*\s*[:,]?\s+)+")
ABGELEITET = "hinweis_abgeleitet"          # plan_ereignis: der Hinweis stammt von der AMW, nicht vom Agenten (A1954)
MIN_WOERTER = 3                            # kürzer („Versionsnummer“) sagt einem Nutzer nichts – dann die nächste Quelle


def kurz(text):
    """Ein Betreff oder Titel als Satz für Nutzer: Aufgaben-/Themen-Kopf weg, nur der erste Teil vor „ – “ oder „; “,
    interne Verweise weg (satz)."""
    t = " ".join((text or "").split())
    t = KOPF.sub("", t)
    t = re.split(r"\s[–—]\s|;\s", t)[0]
    t = re.sub(r"\s*\([^()]*#\d+[^()]*\)", "", t)              # (… #30434): Verweis auf eine Nachricht
    if t.count("(") > t.count(")"):                           # beim Abschneiden offen gebliebene Klammer
        t = t[:t.rfind("(")]
    return satz(t)


def _genug(text):
    return len(text.split()) >= MIN_WOERTER


def betreff(ordner, sha):
    """Commit-Betreff zu einem Beleg im Repo des Projekts (None, wenn kein Commit oder kein Repo)."""
    sha = (sha or "").strip()
    if not ordner or not SHA.match(sha):
        return None
    import subprocess
    try:
        r = subprocess.run(["git", "-C", ordner, "log", "-1", "--format=%s", sha], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=20, stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return None
    s = r.stdout.strip() if r.returncode == 0 else ""
    if not s or re.match(r"^\d+\.\d+\.\d+\b", s):            # Versions-Commit eines Stapels: sagt nichts über die eine Aufgabe
        return None
    return s


def ableiten(con, pid, a, beleg=None, zusammenfassung=None, automatik=False):
    """A1954 (TH151): Gruppe und Satz für die Versionshinweise ohne KI – {"gruppe", "text", "quelle"} oder None.
    Gruppe: Art der Aufgabe (fehlersuche → behoben), sonst Stichworte (regel). Satz: geschlossen über die Fertig-Quelle
    „thema“ → der Name des Themas; sonst der Commit-Betreff des Belegs; sonst die Zusammenfassung des Agenten; sonst der
    Titel – die erste Quelle mit mindestens MIN_WOERTER Wörtern. Die Zusammenfassung einer von der AMW geschlossenen
    Aufgabe (automatik) ist kein Satz für Nutzer und zählt nie."""
    from . import fertigquelle, kern
    if NICHT.search(zusammenfassung or a["zusammenfassung"] or ""):     # nichts ausgeliefert
        return None
    q = fertigquelle.lesen(con, a["id"])
    kandidaten = []
    if q and q.get("art") == "thema":
        t = con.execute("SELECT name FROM thema WHERE projekt_id = ? AND id = ?", (pid, q.get("thema"))).fetchone()
        if t:
            kandidaten.append((t["name"], f"Thema TH{q['thema']}"))
    s = betreff(kern.projekt_ordner(con, pid), beleg or a["beleg"])
    if s:
        kandidaten.append((s, f"Commit {str(beleg or a['beleg'])[:8]}"))
    if not automatik and (zusammenfassung or "").strip():    # vom Agenten selbst geschrieben
        kandidaten.append((zusammenfassung, "Zusammenfassung"))
    kandidaten.append((a["titel"], "Titel"))
    roh = text = quelle = None
    for r, qu in kandidaten:                                  # die erste Quelle mit einem Satz, der etwas sagt
        k = kurz(r)
        if text is None or (_genug(k) and not _genug(text)):
            roh, text, quelle = r, k, qu
        if _genug(text):
            break
    if not text:
        return None
    gruppe = "behoben" if a["art"] == "fehlersuche" else regel(a["titel"], roh)
    if gruppe is None:
        return None
    return {"gruppe": gruppe, "text": text[:300], "quelle": quelle}


def seit(con, pid):
    """Zeitpunkt der letzten eingetragenen Version dieses Projekts (oder None)."""
    r = con.execute("SELECT max(zeit_utc) FROM release WHERE projekt_id = ? AND art = 'version'", (pid,)).fetchone()
    return r[0] if r else None


def _abgeleitet(con, pid):
    """Aufgaben, deren gespeicherter Hinweistext von der AMW abgeleitet ist (das neueste Ereignis je Aufgabe zählt)."""
    import json
    aus = {}
    for r in con.execute("SELECT aufgabe_id, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id", (pid, ABGELEITET)):
        try:
            aus[r[0]] = bool(json.loads(r[1] or "{}").get("text"))
        except ValueError:
            continue
    return {k for k, v in aus.items() if v}


def entwurf(con, pid, ab=None):
    """{gruppe: [{"id", "text", "vorschlag": bool}]} aus den fertigen Aufgaben seit `ab` (Vorgabe: letzte Version)."""
    ab = ab if ab is not None else seit(con, pid)
    aus = {g: [] for g in GRUPPEN}
    abgeleitet = _abgeleitet(con, pid)
    for a in con.execute("SELECT id, titel, zusammenfassung, hinweis, hinweis_gruppe FROM aufgabe WHERE projekt_id = ? AND status = 'fertig'"
                         " AND (? IS NULL OR fertig_utc > ?) ORDER BY fertig_utc, id", (pid, ab, ab)):
        if ist_intern(con, a["id"]):                 # A1978: intern – nie in den Versionshinweisen
            continue
        if a["hinweis"]:
            g = a["hinweis_gruppe"] or regel(a["titel"], a["zusammenfassung"]) or "verbessert"
            aus[g].append({"id": a["id"], "text": a["hinweis"].strip(), "vorschlag": a["id"] in abgeleitet})
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
