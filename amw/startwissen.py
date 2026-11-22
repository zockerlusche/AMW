"""Token-Sparer für interaktive Agenten (A1943, K9, D1258 §12 Pkt 3, Entwurf #30726, Ja #30728).

- Bereichs-Wissen: schließt eine Aufgabe, hält die AMW ohne KI fest, welche Dateien ihre Commits berührt haben (git log
  --grep "^A<n>[: (]" im Projektordner) und einen Satz dazu (Versionshinweis, sonst Zusammenfassung) – Ereignis bereich_wissen.
- Projekt-Landkarte: aus dem Repo erzeugt (Ordner der obersten Ebene, je Python-Modul die erste Zeile seines Docstrings),
  je main-Stand zwischengespeichert neben der Datenbank.
- Startwissen: beim Start einer Aufgabe die letzten Einträge zu ihren Dateien plus die Landkarte – mit festem Budget
  (BUDGET Zeichen; gekürzt wird zuerst die Landkarte). Größe als Ereignis startwissen.
- Befehle zählen: jeder amw-Aufruf eines Agenten als Zeile in befehle.jsonl neben der Datenbank (kein Schema, nie Inhalte);
  „paket fertig“ legt je Aufgabe ein Ereignis k9_paket mit der Zahl der Befehle seit Beginn ab (Messung vorher/nachher).
"""
import json
import os
import re
import subprocess

from . import db, kern

BUDGET = 1500                   # Zeichen für das ganze Startwissen (#30728)
WISSEN_JE_DATEI = 3
ART = "bereich_wissen"
MESSUNG = "k9_paket"
MAX_BYTES = 2_000_000


# --- git ------------------------------------------------------------------------------------------------------------------------

def _git(ordner, *args):
    try:
        r = subprocess.run(["git", "-C", ordner, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=30, stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def dateien_der_aufgabe(ordner, aid):
    """Dateien, die die Commits der Aufgabe (Betreff „A<n>: …“) in main berührt haben – höchstens 30."""
    aus = _git(ordner, "log", "main", "-E", f"--grep=^A{int(aid)}[: (]", "--name-only", "--format=") or ""
    return list(dict.fromkeys(z.strip() for z in aus.splitlines() if z.strip()))[:30]


# --- Bereichs-Wissen ------------------------------------------------------------------------------------------------------------

def bereich_merken(con, pid, aid):
    """Beim Schließen: Dateien + ein Satz als Ereignis (still – Wissen ist Zusatz). Läuft in der Transaktion des Aufrufers."""
    ordner = kern.projekt_ordner(con, pid)
    a = con.execute("SELECT id, titel, hinweis, zusammenfassung FROM aufgabe WHERE id = ?", (aid,)).fetchone()
    if not ordner or not a:
        return None
    dateien = dateien_der_aufgabe(ordner, aid)
    if not dateien:
        return None
    satz = " ".join((a["hinweis"] or a["zusammenfassung"] or a["titel"] or "").split())[:200]
    db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=ART, aufgabe_id=aid,
                 text=json.dumps({"dateien": dateien, "satz": satz}, ensure_ascii=False))
    return dateien


def wissen_zu(con, pid, dateien, ohne=None, je_datei=WISSEN_JE_DATEI):
    """Die letzten Einträge je Datei: [(datei, aufgabe, satz)] – neueste zuerst."""
    aus, gesehen = [], set()
    rows = con.execute("SELECT aufgabe_id, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id DESC LIMIT 500",
                       (pid, ART)).fetchall()
    for d in dateien:
        n = 0
        for r in rows:
            try:
                w = json.loads(r["text"] or "{}")
            except ValueError:
                continue
            if r["aufgabe_id"] == ohne or d not in (w.get("dateien") or []) or (d, r["aufgabe_id"]) in gesehen:
                continue
            gesehen.add((d, r["aufgabe_id"]))
            aus.append((d, r["aufgabe_id"], w.get("satz") or ""))
            n += 1
            if n >= je_datei:
                break
    return aus


# --- Landkarte -------------------------------------------------------------------------------------------------------------------

DOC = re.compile(r'^\s*(?:"""|\'\'\')\s*(.+?)\s*(?:"""|\'\'\'|$)', re.S)


def landkarte(ordner):
    """Zeilen „pfad – erste Zeile“; je main-Stand zwischengespeichert (neben der Datenbank)."""
    sha = (_git(ordner, "rev-parse", "main") or "").strip()[:12]
    cache = os.path.join(os.path.dirname(os.path.abspath(db.db_pfad())), f"landkarte-{sha or 'x'}.txt")
    if sha and os.path.isfile(cache):
        try:
            with open(cache, encoding="utf-8") as f:
                return f.read().splitlines()
        except OSError:
            pass
    zeilen = []
    dateien = (_git(ordner, "ls-tree", "-r", "--name-only", "main") or "").splitlines()
    ordnernamen = sorted({d.split("/")[0] + "/" for d in dateien if "/" in d})
    if ordnernamen:
        zeilen.append("Ordner: " + " ".join(ordnernamen))
    for d in dateien:
        if not d.endswith(".py") or d.startswith("tests/") or d.count("/") > 1:
            continue
        kopf = ""
        try:
            with open(os.path.join(ordner, *d.split("/")), encoding="utf-8", errors="replace") as f:
                m = DOC.match(f.read(2000))
            kopf = " ".join(m.group(1).split("\n")[0].split())[:90] if m else ""
        except OSError:
            pass
        zeilen.append(f"{d} – {kopf}" if kopf else d)
    if sha:
        try:
            with open(cache, "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(zeilen))
        except OSError:
            pass
    return zeilen


# --- Startwissen ---------------------------------------------------------------------------------------------------------------

def _dateien_fuer(con, pid, a, ordner):
    """Dateibereich der Aufgabe (Muster), sonst Dateien, deren Name im Titel oder Auftrag vorkommt."""
    bereich = [x.strip() for x in re.split(r"[,;\s]+", a["dateibereich"] or "") if x.strip()]
    if bereich:
        return [b for b in bereich if "*" not in b][:10]
    text = f"{a['titel']} {a['auftrag'] or ''}".lower()
    dateien = (_git(ordner, "ls-tree", "-r", "--name-only", "main") or "").splitlines() if ordner else []
    treffer = [d for d in dateien if d.endswith(".py") and re.search(r"\b" + re.escape(os.path.splitext(os.path.basename(d))[0].lower())
                                                                    + r"(\.py)?\b", text)]
    return treffer[:10]


def startwissen(con, pid, aid, budget=BUDGET):
    """Text für den Start einer Aufgabe – höchstens budget Zeichen; erst Bereichs-Wissen, dann so viel Landkarte wie passt."""
    a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    ordner = kern.projekt_ordner(con, pid)
    if not a or not ordner:
        return ""
    teile = []
    w = wissen_zu(con, pid, _dateien_fuer(con, pid, a, ordner), ohne=aid)
    if w:
        teile.append("Wissen zu deinen Dateien:")
        teile += [f"- {d} (A{x}): {s}" for d, x, s in w]
    wissen = "\n".join(teile)[:budget * 2 // 3]
    rest = budget - len(wissen) - 20
    karte = []
    for z in landkarte(ordner):
        if rest - len(z) - 1 < 0:
            karte.append("… (Landkarte gekürzt)")
            break
        karte.append(z)
        rest -= len(z) + 1
    text = "\n".join(x for x in ([wissen] if wissen else []) + (["Projekt-Landkarte:"] + karte if karte else []))[:budget]
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art="startwissen", aufgabe_id=aid,
                     text=json.dumps({"zeichen": len(text), "wissen": len(w)}, ensure_ascii=False))
    return text


# --- Befehle zählen -------------------------------------------------------------------------------------------------------------

def _befehle_pfad():
    return os.path.join(os.path.dirname(os.path.abspath(db.db_pfad())), "befehle.jsonl")


def befehl_merken(projekt, agent, befehl):
    """Eine Zeile je amw-Aufruf eines Agenten – still, nie störend, nie Inhalte."""
    try:
        p = _befehle_pfad()
        if os.path.exists(p) and os.path.getsize(p) > MAX_BYTES:
            with open(p, encoding="utf-8") as f:
                zeilen = f.readlines()
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.writelines(zeilen[len(zeilen) // 2:])
        with open(p, "a", encoding="utf-8", newline="") as f:
            f.write(json.dumps({"t": db.jetzt(), "p": projekt, "a": agent, "b": befehl}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def befehle_seit(projekt, agent, seit):
    try:
        with open(_befehle_pfad(), encoding="utf-8") as f:
            return sum(1 for z in f if z.strip() and (lambda e: e.get("p") == projekt and e.get("a") == agent
                                                      and (e.get("t") or "") >= (seit or ""))(json.loads(z)))
    except (OSError, ValueError):
        return None


def messung(con, pid):
    """{"mit": [befehle…], "ohne": [befehle…]} je Aufgabe – mit = über paket holen begonnen."""
    aus = {"mit": [], "ohne": []}
    for (t,) in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id", (pid, MESSUNG)):
        try:
            e = json.loads(t or "{}")
        except ValueError:
            continue
        if e.get("befehle") is not None:
            aus["mit" if e.get("holen") else "ohne"].append(e["befehle"])
    return aus


# --- Tests-Hinweis ---------------------------------------------------------------------------------------------------------------

def tests_zu(ordner, dateien):
    """Testmodule, die eines der geänderten amw-Module importieren (from amw import x / amw.x), dazu geänderte Tests selbst."""
    module = {os.path.splitext(os.path.basename(d))[0] for d in dateien if d.startswith("amw/") and d.endswith(".py")}
    aus = [os.path.splitext(os.path.basename(d))[0] for d in dateien if d.startswith("tests/test_") and d.endswith(".py")]
    if not module:
        return sorted(set(aus))
    muster = re.compile(r"from amw import ([^\n]+)|amw\.(\w+)")
    tests = os.path.join(ordner, "tests")
    try:
        namen = sorted(n for n in os.listdir(tests) if n.startswith("test_") and n.endswith(".py"))
    except OSError:
        return sorted(set(aus))
    for n in namen:
        try:
            with open(os.path.join(tests, n), encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        genutzt = set()
        for m in muster.finditer(text):
            if m.group(1):
                genutzt |= {x.strip().split(" as ")[0] for x in re.split(r"[,()]", m.group(1)) if x.strip()}
            else:
                genutzt.add(m.group(2))
        if genutzt & module:
            aus.append(n[:-3])
    return sorted(set(aus))
