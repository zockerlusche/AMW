"""SessionStart-Hook: Sitzung anmelden und Pflicht-Kontext einspielen (→ doc/10-architektur.md §5, L6).

Eintrag in der Projekt-Einstellung des Agenten (.claude/settings.local.json), Matcher startup|resume|compact:
  python -X utf8 -m amw.hook        (mit PYTHONPATH=F:\\amw, AMW_AGENT=<Kennung>, ggf. AMW_PROJEKT)

- startup/resume: schreibt Pipe-Pfad + Schlüssel der Sitzung in eine Datei unter %LOCALAPPDATA%\\amw\\sitzungen
  (nur der Windows-Benutzer liest dort; der Schlüssel kommt nie in die Datenbank) und trägt die Sitzung ein;
  ältere aktive Sitzungen desselben Agenten werden beendet.
- immer: gibt den Pflicht-Kontext als additionalContext aus.
Blockiert NIE: jeder Fehler endet mit Exit 0 und einem Hinweis im Kontext.
"""
import json
import os
import sys

from . import db, kern


def schluessel_ordner():
    basis = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(basis, "amw", "sitzungen")


def claude_prozess(pipe):
    """Claude Code führt je laufendem Prozess ~/.claude/sessions/<pid>.json (pid, kind interactive|bg, name, Postfach).
    Gibt den Eintrag zu diesem Postfach zurück, sonst None (Prozess beendet oder Datei unbekannt)."""
    ordner = os.path.join(os.path.expanduser("~"), ".claude", "sessions")
    try:
        namen = [n for n in os.listdir(ordner) if n.endswith(".json")]
    except OSError:
        return None
    for n in namen:
        try:
            with open(os.path.join(ordner, n), encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        if pipe and d.get("messagingSocketPath") == pipe:
            return {"pid": d.get("pid"), "art": d.get("kind"), "name": d.get("name"), "sitzung": d.get("sessionId") or ""}
    return None


def beschreibung(p):
    return f"Sitzung {p['sitzung'][:8]}, PID {p['pid']}, " + ("Hintergrund ohne Fenster" if p["art"] == "bg" else "mit Fenster")


def anmelden(con, pid, kennung, eingabe, ersetzen=False, streng=False):
    """Trägt die Sitzung ein. Hintergrund-Sitzungen (kind=bg, kein Fenster) nie – eine solche hatte sich am 01.11.
    als CC5 angemeldet (TL #16500). streng (amw anmelden): eine noch lebende andere Sitzung derselben Kennung wird
    nur mit ersetzen übernommen. Rückgabe: None oder Grund, warum nicht angemeldet wurde."""
    pipe = os.environ.get("CLAUDE_CODE_MESSAGING_SOCKET")
    schluessel = os.environ.get("CLAUDE_CODE_MESSAGING_TOKEN")
    if not (pipe and schluessel):
        return "Hinweis: Sitzung ohne Postfach (CLAUDE_CODE_MESSAGING_*) – der Dienst kann sie nicht wecken."
    ich = claude_prozess(pipe)
    if ich and ich["art"] == "bg" and not ersetzen:
        return (f"Nicht als {kennung} angemeldet: diese Sitzung ist eine Hintergrund-Sitzung ohne Fenster ({beschreibung(ich)})."
                f" Agenten laufen im Fenster des Startskripts.")
    ordner = schluessel_ordner()
    os.makedirs(ordner, exist_ok=True)
    datei = os.path.join(ordner, f"{kennung}.json")
    if streng and not ersetzen and os.path.exists(datei):
        try:
            with open(datei, encoding="utf-8") as f:
                alt_pipe = json.load(f).get("pipe")
        except (OSError, ValueError):
            alt_pipe = None
        alt = claude_prozess(alt_pipe) if alt_pipe and alt_pipe != pipe else None
        if alt:
            return (f"{kennung} ist schon angemeldet und diese Sitzung lebt noch ({beschreibung(alt)}). Bist du der richtige"
                    f" {kennung}: amw anmelden --von {kennung} --ersetzen")
    neu = datei + ".neu"
    with open(neu, "w", encoding="utf-8") as f:
        json.dump({"pipe": pipe, "schluessel": schluessel, "sitzung": eingabe.get("session_id")}, f)
    os.replace(neu, datei)
    a = kern.agent_zeile(con, pid, kennung)
    t = db.jetzt()
    with db.schreiben(con):
        con.execute("UPDATE sitzung SET zustand = 'beendet', beendet_utc = ? WHERE agent_id = ? AND zustand IN"
                    " ('aktiv', 'ruht')", (t, a["id"]))
        db.einfuegen(con, "sitzung", agent_id=a["id"], claude_sitzung=eingabe.get("session_id"),
                     arbeitsordner=eingabe.get("cwd"), schluessel_datei=datei, gestartet_utc=t, letzter_puls_utc=t)
    return None


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    try:
        eingabe = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        eingabe = {}
    kennung = os.environ.get("AMW_AGENT")
    if not kennung:
        return 0                                   # Sitzung gehört zu keinem AMW-Agenten
    teile = []
    try:
        con = db.verbinde()
        try:
            name = os.environ.get("AMW_PROJEKT")
            pid = db.projekt_id(con, name) if name else con.execute("SELECT min(id) FROM projekt").fetchone()[0]
            if eingabe.get("source", "startup") in ("startup", "resume"):
                hinweis = anmelden(con, pid, kennung, eingabe)
                if hinweis:
                    teile.append(hinweis)
            teile.insert(0, kern.kontext(con, pid, kennung))
        finally:
            con.close()
    except Exception as e:                          # Hook darf die Sitzung nie aufhalten
        teile.append(f"AMW-Hook-Fehler ({type(e).__name__}: {e}) – Kontext per `amw kontext` holen.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": "\n".join(teile)}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
