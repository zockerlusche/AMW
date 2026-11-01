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


def anmelden(con, pid, kennung, eingabe):
    pipe = os.environ.get("CLAUDE_CODE_MESSAGING_SOCKET")
    schluessel = os.environ.get("CLAUDE_CODE_MESSAGING_TOKEN")
    if not (pipe and schluessel):
        return "Hinweis: Sitzung ohne Postfach (CLAUDE_CODE_MESSAGING_*) – der Dienst kann sie nicht wecken."
    ordner = schluessel_ordner()
    os.makedirs(ordner, exist_ok=True)
    datei = os.path.join(ordner, f"{kennung}.json")
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
