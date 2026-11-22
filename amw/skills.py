"""Kleiner Startkontext, Anleitungen als Skills (A1956, TH168 Hebel 7, Marcel W2461).

Der Pflichtkontext beim Start bleibt kurz (Rolle, Konzept, Kurzregeln, Arbeitsweise); die ausführlichen Anleitungen stehen als
Claude-Code-Skills im Repo (.claude/skills/amw-<thema>/SKILL.md) – Claude Code lädt einen Skill erst, wenn seine Beschreibung zur
Aufgabe passt. Quelle bleiben doc/befehle.md, doc/automatismen.md, doc/fehlerbehebung.md, doc/anleitung-*.md und doc/hilfe/*.md (eine Stelle, nichts geht verloren) – ein Skill ist nur Beschreibung + Verweis; `amw skills bauen` erzeugt sie,
ein Test prüft, dass sie zu den Quellen passen (wie doc/befehle.md).

Messung vorher/nachher (TH168 „Messen“): kontext_masse() je Agent (Zeilen/Zeichen von Pflichtkontext und Regeln) und die Kosten
je abgenommenem Paket (Median der letzten 10 je Agent) – `amw messung --hebel7 [--basis]` schreibt mit --basis das Ereignis
basis_hebel7.
"""
import json
import os
import re

from . import db, kern

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(WURZEL, ".claude", "skills")
BASIS = "basis_hebel7"


SKILLS = (   # wenige Skills mit kurzer Beschreibung: Name und Beschreibung jedes Skills stehen in JEDER Sitzung im Kontext
    ("amw-befehle", "AMW-Befehlsreferenz (amw …) mit allen Optionen – wenn du einen Befehl oder seine genaue Schreibweise brauchst.",
     ["doc/befehle.md"]),
    ("amw-automatismen", "Was die AMW selbst tut (Weckrufe, Läufe, Prüfungen, Releases, Planer) – ob etwas automatisch geregelt ist.",
     ["doc/automatismen.md"]),
    ("amw-fehlerbehebung", "Bekannte Fehler und Abhilfen – wenn ein amw-Befehl, Dienst, Hook, Lauf (hängt, rot) oder Test nicht wie"
                           " erwartet arbeitet.",
     ["doc/fehlerbehebung.md"]),
    ("amw-anleitungen", "Anleitungen: Ergebnisse/Bilder/Mockups ablegen, ein Projekt planen, mehrere Projekte, Push aufs Handy.",
     "doc/anleitung-*.md"),
    ("amw-hilfe", "Hilfe je Funktion: Agenten, Themen, Planung, p-Pakete, Versionen, Release-Takt, schwere Läufe, Bildschirm,"
                  " Reihenfolge, Lead-Runde, Dienst, Termine.",
     "doc/hilfe/*.md"),
)


def _titel(rel):
    with open(os.path.join(WURZEL, rel), encoding="utf-8") as f:
        return next((z[2:].strip() for z in f.read().splitlines() if z.startswith("# ")), os.path.basename(rel))


def quellen():
    """[(Skill-Name, Pfad relativ zum Repo)] – jede Quelle unter doc/, die ein Skill nennt."""
    aus = []
    for name, _, q in SKILLS:
        if isinstance(q, str):
            ordner, muster = os.path.split(q)
            vorn = muster.split("*")[0]
            q = [f"{ordner}/{d}" for d in sorted(os.listdir(os.path.join(WURZEL, ordner)))
                 if d.startswith(vorn) and d.endswith(".md") and d.lower() != "readme.md"]
        aus += [(name, r) for r in q]
    return aus


def skills(absolut=False):
    """{relativer Pfad: Inhalt} – je Skill name/description für Claude Code und die Verweise auf seine Quellen (der Inhalt steht nur
    einmal im Repo). absolut: Pfade zum AMW-Ordner (für Agenten-Ordner anderer Projekte)."""
    q = quellen()
    aus = {}
    for name, beschreibung, _ in SKILLS:
        if not re.fullmatch(r"[a-z0-9-]{1,64}", name):
            raise kern.AmwFehler(f"Skill-Name „{name}“: nur Kleinbuchstaben, Ziffern und Bindestriche")
        dateien = [r for n, r in q if n == name]
        zeilen = [f"- {_titel(r)}: steht in `{os.path.join(WURZEL, r).replace(os.sep, '/') if absolut else r}`" for r in dateien]
        wo = "" if absolut else " (Pfade vom Repo-Wurzelordner aus)"
        aus[name + "/SKILL.md"] = (
            f"---\nname: {name}\ndescription: {json.dumps(beschreibung, ensure_ascii=False)}\n---\n\n"
            f"<!-- erzeugt von amw skills bauen – nicht von Hand ändern -->\n\n"
            f"Lies die passende Seite mit dem Read-Werkzeug, bevor du handelst{wo}. Sie ist die einzige Quelle, dieser Skill nur ein"
            f" Verzeichnis.\n\n" + "\n".join(zeilen) + "\n")
    return aus


def bauen(ziel=ZIEL):
    """Skills schreiben (LF); verwaiste amw-* Skills bleiben liegen und werden genannt (nichts löschen, B2894)."""
    s = skills(absolut=os.path.abspath(ziel) != os.path.abspath(ZIEL))
    for rel, inhalt in s.items():
        pfad = os.path.join(ziel, rel)
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad, "w", encoding="utf-8", newline="\n") as f:
            f.write(inhalt)
    da = {d for d in os.listdir(ziel) if d.startswith("amw-")} if os.path.isdir(ziel) else set()
    verwaist = sorted(da - {r.split("/")[0] for r in s})
    return sorted(s), verwaist


def kurzregeln(con, pid):
    """„KR1 Versionen (G1) · KR2 Fertig heißt belegt (G2) · …“ – je Regel nur der Titel (erster Satz, gekürzt, im Wortlaut der Regel)
    und die Kennung aus dem Grund-Regelwerk, auf die sich Nachrichten und Doku beziehen."""
    aus = []
    for r in con.execute("SELECT ebene, nr, text, vorlage FROM regel WHERE projekt_id = ? ORDER BY ebene, nr", (pid,)).fetchall():
        t = (r["text"] or "").strip()
        titel = re.split(r"(?<=[.!?])\s", t)[0].rstrip(".")
        if len(titel) > 48:
            titel = titel[:46].rsplit(" ", 1)[0] + " …"
        g = f" ({r['vorlage'].split('/')[0]})" if r["vorlage"] else ""
        aus.append(f"{'KR' if r['ebene'] == 'arbeit' else 'PR'}{r['nr']} {titel}{g}")
    return aus


def kontext_masse(con, pid):
    """[{agent, kontext_zeilen, kontext_zeichen, regeln_zeilen, regeln_zeichen, usd_median, n}] je (nicht entferntem) Agenten."""
    from . import aufwand
    regeln = "\n\n".join(r["text"] for r in con.execute("SELECT text FROM regel WHERE projekt_id = ? ORDER BY ebene, nr", (pid,)))
    aus = []
    for (k,) in con.execute("SELECT kennung FROM agent WHERE projekt_id = ? AND entfernt_utc IS NULL ORDER BY kennung", (pid,)).fetchall():
        t = kern.kontext(con, pid, k)
        t = "\n".join(t) if isinstance(t, list) else str(t)
        try:
            ja = aufwand.je_agent(con, pid, k, letzte=10)
        except Exception:                                # noqa: BLE001 – ohne Messwerte gibt es keinen Median
            ja = None
        aus.append({"agent": k, "kontext_zeilen": len(t.splitlines()), "kontext_zeichen": len(t),
                    "regeln_zeilen": len(regeln.splitlines()), "regeln_zeichen": len(regeln),
                    "usd_median": ja["median"] if ja else None, "n": ja["n"] if ja else 0})
    return aus


def basis_merken(con, pid, von):
    m = kontext_masse(con, pid)
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=BASIS,
                     text=json.dumps({"agenten": m}, ensure_ascii=False))
    return m
