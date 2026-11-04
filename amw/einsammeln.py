"""Vorhandene Ergebnisse einsammeln (Stufe D3, → doc/plan-dokumente.md §4b): erst eine Liste je Ablage zur Freigabe,
nichts automatisch.

`liste(ordner)` liest nur: je Ordner mit Dateien Anzahl, Größe, Zeitraum und ein Vorschlag behalten/weg mit Grund, je
Datei Art, Bezug und Titel. `melden()` legt die Liste als Bericht ab und fragt den Menschen (A = übernehmen, B = nichts),
der Lead bekommt eine Info. `uebernehmen()` legt erst nach dieser Antwort an – nur Dateien der Liste, deren Inhalt sich
seitdem nicht geändert hat. Verschoben oder gelöscht wird nichts.
"""
import datetime
import hashlib
import json
import os
import re
import tempfile

from . import db, dokumente, kern

UEBERSPRINGEN = {".git", ".godot", ".import", ".svn", ".hg", ".idea", ".vs", ".vscode", ".venv", "venv", "node_modules",
                 "__pycache__", "bin", "obj"}
ARBEIT = re.compile(r"(^|[-_ .])(tmp|temp|cache|kopie|copy|backup|bak|alt|old|arbeit|work|scratch|trash|papierkorb)([-_ .]|\d|$)", re.I)
NUMMERIERT = re.compile(r"\d{3,}")
BEZUG = re.compile(r"(?<![A-Za-z0-9])([ABF])(\d{2,5})(?!\d)")
BILDER_LAUF = 40                         # so viele nummerierte Bilder in einem Ordner = Prüflauf-Einzelbilder
KENNUNG = "amw-einsammeln"               # Markierung des maschinenlesbaren Teils im Bericht


def _art(name, vorschau):
    if vorschau == "bild":
        return "bild"
    if vorschau == "mockup":
        return "mockup"
    if vorschau in ("pdf", "download"):
        return "quelle"
    n = name.lower()
    if re.search(r"bericht|report|pruef|prüf|test|messung|analyse", n):
        return "bericht"
    if re.search(r"entwurf|draft|konzept|idee|skizze", n):
        return "entwurf"
    return "ergebnis"


def _bezug(con, pid, rel):
    """Vorschlag aus dem Pfad: A1234 → Aufgabe, B12 → Beschluss, F7 → Frage – nur, was es in der AMW gibt. Der
    Dateiname zählt vor dem Ordner (das letzte passende Kürzel gewinnt)."""
    tabelle = {"A": "aufgabe", "B": "beschluss", "F": "frage"}
    for k, nr in reversed(BEZUG.findall(rel.replace("\\", "/"))):
        if con.execute(f"SELECT 1 FROM {tabelle[k]} WHERE id = ? AND projekt_id = ?", (int(nr), pid)).fetchone():
            return tabelle[k], int(nr)
    return None, None


def _zeit(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%d.%m.%Y")


def liste(con, pid, ordner):
    """Liest den Ordner (nur lesen). Rückgabe: {"ordner", "ablagen": [...], "zeit_utc"}."""
    wurzel = os.path.abspath(ordner)
    if not os.path.isdir(wurzel):
        raise kern.AmwFehler(f"Ordner {ordner} gibt es nicht")
    vorhanden = {r[0]: r[1] for r in con.execute(
        "SELECT v.sha256, min(v.dokument_id) FROM dokument_version v JOIN dokument d ON d.id = v.dokument_id"
        " WHERE d.projekt_id = ? AND d.status != 'geloescht' GROUP BY v.sha256", (pid,))}
    ablagen = []
    for pfad, unter, dateien in os.walk(wurzel):
        unter[:] = sorted(u for u in unter if u not in UEBERSPRINGEN and not u.startswith("."))
        if not dateien:
            continue
        rel_ordner = os.path.relpath(pfad, wurzel).replace("\\", "/")
        passend, andere = [], 0
        for name in sorted(dateien):
            endung = os.path.splitext(name)[1].lower()
            if endung not in dokumente.FORMATE:
                andere += 1
                continue
            p = os.path.join(pfad, name)
            try:
                st = os.stat(p)
            except OSError:
                continue
            passend.append({"name": name, "rel": (name if rel_ordner == "." else f"{rel_ordner}/{name}"), "groesse": st.st_size,
                            "zeit": st.st_mtime, "vorschau": dokumente.FORMATE[endung][2]})
        if not passend:
            if andere:
                ablagen.append({"ordner": rel_ordner, "dateien": [], "andere": andere, "groesse": 0, "von": None, "bis": None,
                                "vorschlag": "weg", "grund": f"nur Code/Daten ({andere} Dateien) – bleiben, wo sie sind"})
            continue
        bilder = [d for d in passend if d["vorschau"] == "bild"]
        nummeriert = [d for d in bilder if NUMMERIERT.search(d["name"])]
        if ARBEIT.search(rel_ordner if rel_ordner != "." else ""):
            vorschlag, grund = "weg", "Arbeitskopie/Zwischenstand (Ordnername)"
        elif len(nummeriert) >= BILDER_LAUF and len(nummeriert) >= 0.8 * len(passend):
            vorschlag, grund = "weg", f"Prüflauf-Einzelbilder ({len(nummeriert)} nummerierte Bilder) – bei Bedarf einzelne von Hand"
        else:
            vorschlag, grund = "behalten", "Ergebnisse"
        for d in passend:
            d["vorschlag"], d["grund"] = vorschlag, None
            if d["groesse"] > dokumente.GROESSE_MAX:
                d["vorschlag"], d["grund"] = "weg", f"größer als {dokumente.GROESSE_MAX // 1024 // 1024} MB"
                continue
            if vorschlag == "weg":
                continue
            try:
                with open(os.path.join(wurzel, d["rel"]), "rb") as f:
                    d["sha"] = hashlib.sha256(f.read()).hexdigest()
            except OSError:
                d["vorschlag"], d["grund"] = "weg", "nicht lesbar"
                continue
            if d["sha"] in vorhanden:
                d["vorschlag"], d["grund"] = "weg", f"schon in der AMW (D{vorhanden[d['sha']]})"
                continue
            d["art"] = _art(d["name"], d["vorschau"])
            d["bezug_art"], d["bezug_id"] = _bezug(con, pid, d["rel"])
            d["titel"] = os.path.splitext(d["name"])[0].replace("_", " ").strip()[:200]
        zeiten = [d["zeit"] for d in passend]
        ablagen.append({"ordner": rel_ordner, "dateien": passend, "andere": andere, "groesse": sum(d["groesse"] for d in passend),
                        "von": min(zeiten), "bis": max(zeiten), "vorschlag": vorschlag, "grund": grund})
    return {"ordner": wurzel, "ablagen": ablagen, "zeit_utc": db.jetzt()}


def summe(l):
    behalten = [d for a in l["ablagen"] for d in a["dateien"] if d["vorschlag"] == "behalten"]
    return len(behalten), sum(d["groesse"] for d in behalten)


def _mb(n):
    return f"{n / 1024 / 1024:.1f} MB" if n >= 100 * 1024 else f"{max(1, n // 1024)} KB"


def bericht(l):
    """Die Liste als Markdown: lesbar oben, der maschinenlesbare Teil (nur Dateien mit Vorschlag „behalten“) unten."""
    n, groesse = summe(l)
    alle = sum(len(a["dateien"]) for a in l["ablagen"])
    z = [f"# Einsammeln: {l['ordner']}", "",
         f"Stand {l['zeit_utc']} · {len(l['ablagen'])} Ablagen · {alle} passende Dateien · **Vorschlag: {n} übernehmen ({_mb(groesse)})**",
         "", "Nichts wird verschoben oder gelöscht. Übernommen wird erst nach der Antwort auf die Frage, und nur Dateien,",
         "deren Inhalt sich bis dahin nicht geändert hat.", "",
         "| Ablage | Dateien | Größe | Zeitraum | Vorschlag | Grund |", "|---|---|---|---|---|---|"]
    for a in l["ablagen"]:
        zeitraum = "–" if a["von"] is None else _zeit(a["von"]) if _zeit(a["von"]) == _zeit(a["bis"]) else f"{_zeit(a['von'])}–{_zeit(a['bis'])}"
        anzahl = f"{len(a['dateien'])}" + (f" (+{a['andere']} andere)" if a["andere"] else "")
        z.append(f"| `{a['ordner']}` | {anzahl} | {_mb(a['groesse']) if a['groesse'] else '–'} | {zeitraum} | {a['vorschlag']} | {a['grund']} |")
    z += ["", "## Dateien mit Vorschlag „behalten“", ""]
    for a in l["ablagen"]:
        for d in a["dateien"]:
            if d["vorschlag"] == "behalten":
                b = f" · zu {({'aufgabe': 'A', 'beschluss': 'B', 'frage': 'F'})[d['bezug_art']]}{d['bezug_id']}" if d.get("bezug_art") else ""
                z.append(f"- `{d['rel']}` → {d['art']}{b} · {_mb(d['groesse'])}")
    ausnahmen = [(d["rel"], d["grund"]) for a in l["ablagen"] for d in a["dateien"] if d["vorschlag"] == "weg" and d["grund"]]
    if ausnahmen:
        z += ["", "## Einzelne Dateien nicht übernehmen", ""] + [f"- `{r}` – {g}" for r, g in ausnahmen[:200]]
    maschine = {"ordner": l["ordner"], "zeit_utc": l["zeit_utc"],
                "dateien": [{k: d.get(k) for k in ("rel", "sha", "groesse", "art", "bezug_art", "bezug_id", "titel")}
                            for a in l["ablagen"] for d in a["dateien"] if d["vorschlag"] == "behalten"]}
    z += ["", "<details><summary>Auswahl für die Übernahme (maschinenlesbar)</summary>", "", f"```json {KENNUNG}",
          json.dumps(maschine, ensure_ascii=False, indent=1), "```", "", "</details>", ""]
    return "\n".join(z)


def melden(con, pid, von, l):
    """Liste als Bericht ablegen, Frage an den Menschen, Info an den Lead. Rückgabe: (Dokument, Frage)."""
    n, groesse = summe(l)
    if not n:
        raise kern.AmwFehler("Nichts zu übernehmen – keine Frage nötig (Liste ohne --melden ansehen)")
    name = os.path.basename(l["ordner"].rstrip("\\/")) or l["ordner"]
    with tempfile.TemporaryDirectory() as t:
        p = os.path.join(t, "einsammeln.md")
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(bericht(l))
        did = dokumente.ablegen(con, pid, von, p, f"Einsammeln: {name}", "bericht", f"Liste aus {l['ordner']}")
    fid = kern.frage_neu(con, pid, von, "entwickler", f"Ergebnisse aus „{name}“ in die AMW übernehmen?"[:300],
                         [("A", f"Vorschlag übernehmen ({n} Dateien, {_mb(groesse)})"), ("B", "Nichts übernehmen")], "A",
                         "Nur Ergebnisse laut Liste (D%d); Arbeitskopien, Prüflauf-Einzelbilder und Code bleiben, wo sie sind. "
                         "Nichts wird verschoben oder gelöscht. Für eine Auswahl: als Text antworten, welche Ablagen." % did,
                         f"{len(l['ablagen'])} Ablagen in {l['ordner']} geprüft – die Liste hängt als D{did} an.",
                         f"D{did}", geprueft="von der AMW gestellt (Einsammeln)", pruefen=False)
    dokumente.setzen(con, pid, von, did, frage=fid)
    lead = kern.lead(con, pid)
    if lead and lead != von:
        kern.posten(con, pid, von, lead, "info", f"Einsammel-Liste {name}: {n} Dateien vorgeschlagen (D{did}, F{fid})"[:300],
                    f"Ordner {l['ordner']}. Übernommen wird erst nach der Antwort des Entwicklers auf F{fid}.")
    return did, fid


def _auswahl(con, pid, fid):
    f = con.execute("SELECT status, antwort_art, antwort FROM frage WHERE id = ? AND projekt_id = ?", (fid, pid)).fetchone()
    if not f:
        raise kern.AmwFehler(f"F{fid} gibt es nicht")
    if f["status"] != "beantwortet":
        raise kern.AmwFehler(f"F{fid} ist noch nicht beantwortet – übernommen wird erst nach der Freigabe")
    if f["antwort_art"] == "option" and f["antwort"] != "A":
        raise kern.AmwFehler(f"F{fid} wurde mit {f['antwort']} beantwortet – nichts übernehmen")
    d = con.execute("SELECT id FROM dokument WHERE projekt_id = ? AND bezug_art = 'frage' AND bezug_id = ? AND art = 'bericht'"
                    " AND titel LIKE 'Einsammeln:%' AND status != 'geloescht' ORDER BY id DESC LIMIT 1", (pid, fid)).fetchone()
    if not d:
        raise kern.AmwFehler(f"Zu F{fid} gibt es keine Einsammel-Liste")
    text = dokumente.inhalt(con, pid, d["id"], 1)[0].decode("utf-8")   # v1: die Liste, die gefragt wurde
    m = re.search(r"```json " + KENNUNG + r"\r?\n(.*?)\r?\n```", text, re.S)
    if not m:
        raise kern.AmwFehler(f"D{d['id']}: Auswahl nicht lesbar")
    return json.loads(m.group(1)), f, d["id"]


def uebernehmen(con, pid, von, fid, nur=None):
    """Nach der Freigabe: Dateien der Liste anlegen. nur: Liste von Unterordnern (Pflicht bei Text-Antworten).
    Rückgabe: (angelegt [(rel, D-nr)], übersprungen [(rel, Grund)])."""
    auswahl, f, did = _auswahl(con, pid, fid)
    if f["antwort_art"] == "text" and not nur:
        raise kern.AmwFehler(f"F{fid} wurde mit Text beantwortet („{f['antwort'][:200]}“) – Auswahl mit --nur <unterordner> angeben")
    nur = [n.strip("/\\").replace("\\", "/") for n in (nur or [])]
    wurzel = auswahl["ordner"]
    vorhanden = {r[0] for r in con.execute(
        "SELECT v.sha256 FROM dokument_version v JOIN dokument d ON d.id = v.dokument_id WHERE d.projekt_id = ?"
        " AND d.status != 'geloescht'", (pid,))}
    angelegt, weg = [], []
    for x in auswahl["dateien"]:
        if nur and not any(x["rel"] == n or x["rel"].startswith(n + "/") for n in nur):
            continue
        p = os.path.join(wurzel, x["rel"])
        try:
            with open(p, "rb") as fh:
                roh = fh.read()
        except OSError:
            weg.append((x["rel"], "nicht mehr da"))
            continue
        sha = hashlib.sha256(roh).hexdigest()
        if sha != x["sha"]:
            weg.append((x["rel"], "inzwischen geändert – neu auflisten"))
            continue
        if sha in vorhanden:
            weg.append((x["rel"], "schon in der AMW"))
            continue
        bezug = {x["bezug_art"]: x["bezug_id"]} if x.get("bezug_art") else {}
        try:
            neu = dokumente.ablegen_inhalt(con, pid, von, roh, x["rel"], x["titel"], x["art"],
                                           f"eingesammelt aus {x['rel']} (F{fid}, D{did})", **bezug)
        except kern.AmwFehler as e:
            weg.append((x["rel"], str(e)))
            continue
        vorhanden.add(sha)
        angelegt.append((x["rel"], neu))
    return angelegt, weg
