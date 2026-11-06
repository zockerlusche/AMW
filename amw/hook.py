"""SessionStart-Hook: Sitzung anmelden und Pflicht-Kontext einspielen (→ doc/architektur.md).

Eintrag in der Projekt-Einstellung des Agenten (.claude/settings.local.json), Matcher startup|resume|compact:
  python -X utf8 -m amw.hook        (mit PYTHONPATH=<AMW-Ordner>, AMW_AGENT=<Kennung>, ggf. AMW_PROJEKT)

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


def claude_prozesse():
    """Claude Code führt je laufendem Prozess ~/.claude/sessions/<pid>.json (pid, kind interactive|bg, name, Ordner,
    Postfach). Nur lesen – die Schlüssel daneben fasst die AMW nie an."""
    ordner = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude"), "sessions")
    try:
        namen = [n for n in os.listdir(ordner) if n.endswith(".json")]
    except OSError:
        return []
    erg = []
    for n in namen:
        try:
            with open(os.path.join(ordner, n), encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        erg.append({"pid": d.get("pid"), "art": d.get("kind"), "name": d.get("name"), "sitzung": d.get("sessionId") or "",
                    "ordner": d.get("cwd"), "pipe": d.get("messagingSocketPath")})
    return erg


def claude_prozess(pipe):
    """Eintrag zu diesem Postfach, sonst None (Prozess beendet oder Datei unbekannt)."""
    return next((p for p in claude_prozesse() if pipe and p["pipe"] == pipe), None)


def bekannte_kennung(con, pid, sitzung):
    """Kennung, unter der diese Claude-Sitzung schon angemeldet war – ein Resume behält die Sitzungs-ID (nach einem
    Resume von Hand ohne Startskript fehlt AMW_AGENT – trotzdem soll die Sitzung angemeldet werden)."""
    if not sitzung:
        return None
    r = con.execute("SELECT a.kennung FROM sitzung s JOIN agent a ON a.id = s.agent_id WHERE a.projekt_id = ?"
                    " AND s.claude_sitzung = ? ORDER BY s.id DESC LIMIT 1", (pid, sitzung)).fetchone()
    return r["kennung"] if r else None


def angemeldete_postfaecher():
    ordner = schluessel_ordner()
    try:
        namen = [n for n in os.listdir(ordner) if n.endswith(".json")]
    except OSError:
        return {}
    erg = {}
    for n in namen:
        try:
            with open(os.path.join(ordner, n), encoding="utf-8") as f:
                erg[json.load(f).get("pipe")] = n[:-5]
        except (OSError, ValueError):
            continue
    return erg


def unangemeldet(con, pid):
    """Laufende Sitzungen mit Fenster, die nicht angemeldet sind, aber zu einem Agenten gehören: Sitzungs-ID war schon
    angemeldet (Resume) oder sie läuft im selben Ordner wie ein angemeldeter Agent. Für Workbench und dienst status."""
    postfach = angemeldete_postfaecher()
    alle = claude_prozesse()
    live_ordner = {p["ordner"] for p in alle if p["pipe"] in postfach}
    erg = []
    for p in alle:
        if p["pipe"] in postfach or p["art"] == "bg":
            continue
        k = bekannte_kennung(con, pid, p["sitzung"])
        if k or p["ordner"] in live_ordner or agenten_ordner(con, p["ordner"]):
            erg.append({"kennung": k, "pid": p["pid"], "sitzung": p["sitzung"][:8], "ordner": p["ordner"], "name": p["name"]})
    return erg


def beschreibung(p):
    return f"Sitzung {p['sitzung'][:8]}, PID {p['pid']}, " + ("Hintergrund ohne Fenster" if p["art"] == "bg" else "mit Fenster")


def anmelden(con, pid, kennung, eingabe, ersetzen=False, streng=False):
    """Trägt die Sitzung ein. Hintergrund-Sitzungen (kind=bg, kein Fenster) nie – sonst gingen Weckrufe in
    eine Sitzung ohne Fenster. streng (amw anmelden): eine noch lebende andere Sitzung derselben Kennung wird
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
    claude_pid = ich["pid"] if ich else None
    try:                                            # Fenster = Elternprozess von Claude (Absturz-Erkennung, Stufe D)
        from . import steuerung
        fenster_pid = steuerung.eltern(claude_pid) if claude_pid else None
    except (OSError, AttributeError, ValueError):
        fenster_pid = None
    with db.schreiben(con):
        con.execute("UPDATE sitzung SET zustand = 'beendet', beendet_utc = ? WHERE agent_id = ? AND zustand IN"
                    " ('aktiv', 'ruht')", (t, a["id"]))
        db.einfuegen(con, "sitzung", agent_id=a["id"], claude_sitzung=eingabe.get("session_id"),
                     arbeitsordner=eingabe.get("cwd"), schluessel_datei=datei, gestartet_utc=t, letzter_puls_utc=t,
                     claude_pid=claude_pid, fenster_pid=fenster_pid)
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
    if eingabe.get("hook_event_name", "SessionStart") != "SessionStart":
        try:                                        # Zustands-Hooks: still, schnell, nie störend
            ereignis(eingabe)
        except Exception:
            pass
        return 0
    kennung = os.environ.get("AMW_AGENT")           # Startskript; fehlt sie (Resume von Hand), zählt die Sitzungs-ID
    quelle = eingabe.get("source", "startup")
    teile, meldung = [], None                       # meldung: sichtbar im Fenster (systemMessage)
    try:
        con = db.verbinde()
        try:
            try:
                pid = db.projekt_fuer(con, os.environ.get("AMW_PROJEKT"), kennung)
            except LookupError:                     # falsches AMW_PROJEKT: das Projekt der Kennung;
                try:                                # mehrdeutig ohne Kennung: wie bisher das erste Projekt
                    pid = db.projekt_fuer(con, None, kennung)
                except LookupError:
                    pid = con.execute("SELECT min(id) FROM projekt").fetchone()[0]
            erkannt = not kennung
            kennung = kern.kennung_heute(con, kennung, pid) or bekannte_kennung(con, pid, eingabe.get("session_id"))
            if not kennung:
                if quelle in ("startup", "resume") and agenten_ordner(con, eingabe.get("cwd")):
                    meldung = ("AMW: diese Sitzung ist NICHT angemeldet und wird nicht geweckt. Als Agent: "
                               f"{kern.BEFEHL} anmelden --von <Kennung>")
                    teile.append(meldung)
                else:
                    return 0                        # Sitzung gehört zu keinem AMW-Agenten
            else:
                if quelle in ("startup", "resume"):
                    hinweis = anmelden(con, pid, kennung, eingabe)
                    meldung = f"AMW: {hinweis}" if hinweis else \
                        f"AMW: als {kennung} angemeldet" + (" (erkannt an der früheren Anmeldung dieser Sitzung)" if erkannt else "")
                    if hinweis:
                        teile.append(hinweis)
                teile.insert(0, kern.kontext(con, pid, kennung))
        finally:
            con.close()
    except Exception as e:                          # Hook darf die Sitzung nie aufhalten
        teile.append(f"AMW-Hook-Fehler ({type(e).__name__}: {e}) – Kontext per `amw kontext` holen.")
        meldung = teile[-1]
    aus = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n".join(teile)}}
    if meldung:
        aus["systemMessage"] = meldung
    print(json.dumps(aus, ensure_ascii=False))
    return 0


# Zustand aus den Hook-Ereignissen (→ code.claude.com/docs/en/hooks): was der Agent gerade tut bzw. worauf er wartet.
NOTIFICATION = {"permission_prompt": "wartet_freigabe", "elicitation_dialog": "wartet_eingabe",
                "elicitation_url_dialog": "wartet_eingabe", "agent_needs_input": "wartet_eingabe", "idle_prompt": "frei"}


def zustand_aus(eingabe):
    """Hook-Eingabe → (ereignis, text) oder None (nichts ändern)."""
    art = eingabe.get("hook_event_name")
    if art == "UserPromptSubmit":
        return "arbeitet", None
    if art == "Stop":
        return "frei", None
    if art == "StopFailure":
        fehler = eingabe.get("error_type") or eingabe.get("error") or eingabe.get("reason") or "unbekannt"
        return "fehler", str(fehler)[:200]
    if art == "Notification":
        z = NOTIFICATION.get(eingabe.get("notification_type"))
        return (z, (eingabe.get("message") or "")[:200] or None) if z else None
    if art == "SessionEnd":
        return "beendet", (eingabe.get("reason") or None)
    return None


def ereignis(eingabe):
    z = zustand_aus(eingabe)
    if not z or not eingabe.get("session_id"):
        return
    con = db.verbinde()
    try:
        with db.schreiben(con):
            con.execute("UPDATE sitzung SET ereignis = ?, ereignis_text = ?, ereignis_utc = ? WHERE claude_sitzung = ?"
                        " AND zustand = 'aktiv'", (z[0], z[1], db.jetzt(), eingabe["session_id"]))
    finally:
        con.close()


def agenten_ordner(con, ordner):
    """Läuft hier schon einmal ein angemeldeter Agent? (Ordner aus der Sitzungstabelle, ohne Groß/klein.)"""
    return bool(ordner) and con.execute("SELECT 1 FROM sitzung WHERE lower(arbeitsordner) = lower(?) LIMIT 1",
                                        (ordner,)).fetchone() is not None


if __name__ == "__main__":
    sys.exit(main())
