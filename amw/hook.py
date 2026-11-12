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


def schluessel_datei(con, pid, kennung):
    """Je Projekt und Kennung eine Datei: CC1 darf es in mehreren Projekten geben, und jede Anmeldung schreibt ihre Datei neu.
    Mit nur der Kennung im Namen überschrieb der zweite CC1 die Weck-Adresse des ersten."""
    uid = con.execute("SELECT uid FROM projekt WHERE id = ?", (pid,)).fetchone()[0]
    return os.path.join(schluessel_ordner(), f"{kennung}@{uid[:8]}.json")


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


def prozess_der_sitzung(claude_sitzung, datei):
    """Der Claude-Prozess genau dieser Sitzung, sonst None – zuerst über die Sitzungs-ID, dann über das Postfach der Datei.
    Gehört die Datei zu einer anderen Sitzung, zählt sie nicht: wer danach einen Prozess beendet, träfe sonst einen fremden."""
    if claude_sitzung:
        p = next((x for x in claude_prozesse() if x["sitzung"] == claude_sitzung), None)
        if p:
            return p
    try:
        with open(datei, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError, TypeError):
        return None
    if claude_sitzung and d.get("sitzung") and d["sitzung"] != claude_sitzung:
        return None
    return claude_prozess(d.get("pipe"))


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
                erg[json.load(f).get("pipe")] = n[:-5].split("@")[0]
        except (OSError, ValueError):
            continue
    return erg


def unangemeldet(con, pid):
    """Laufende Sitzungen mit Fenster, die nicht angemeldet sind, aber zu einem Agenten DIESES Projekts gehören: Sitzungs-ID
    war schon angemeldet (Resume) oder sie läuft in einem Ordner, in dem hier schon ein Agent angemeldet war. Für Workbench
    und dienst status; Sitzungen anderer Projekte erscheinen dort nicht."""
    postfach = angemeldete_postfaecher()
    erg = []
    for p in claude_prozesse():
        if p["pipe"] in postfach or p["art"] == "bg":
            continue
        k = bekannte_kennung(con, pid, p["sitzung"])
        if k or agenten_ordner(con, p["ordner"], pid):
            erg.append({"kennung": k, "pid": p["pid"], "sitzung": p["sitzung"][:8], "ordner": p["ordner"], "name": p["name"]})
    return erg


def beschreibung(p):
    return f"Sitzung {p['sitzung'][:8]}, PID {p['pid']}, " + ("Hintergrund ohne Fenster" if p["art"] == "bg" else "mit Fenster")


def anmelden(con, pid, kennung, eingabe, ersetzen=False, streng=False):
    """Trägt die Sitzung ein. Hintergrund-Sitzungen (kind=bg, kein Fenster) nie – sonst gingen Weckrufe in
    eine Sitzung ohne Fenster. streng (amw anmelden): eine noch lebende andere Sitzung derselben Kennung wird
    nur mit ersetzen übernommen. Rückgabe: None oder Grund, warum nicht angemeldet wurde."""
    weg = con.execute("SELECT entfernt_utc FROM agent WHERE projekt_id = ? AND kennung = ?", (pid, kennung)).fetchone()
    if weg and weg[0]:
        return f"Nicht als {kennung} angemeldet: der Agent ist entfernt – wieder aufnehmen geht in Einstellungen › Agenten."
    pipe = os.environ.get("CLAUDE_CODE_MESSAGING_SOCKET")
    schluessel = os.environ.get("CLAUDE_CODE_MESSAGING_TOKEN")
    if not (pipe and schluessel):
        return "Hinweis: Sitzung ohne Postfach (CLAUDE_CODE_MESSAGING_*) – der Dienst kann sie nicht benachrichtigen."
    ich = claude_prozess(pipe)
    if ich and ich["art"] == "bg" and not ersetzen:
        return (f"Nicht als {kennung} angemeldet: diese Sitzung ist eine Hintergrund-Sitzung ohne Fenster ({beschreibung(ich)})."
                f" Agenten laufen im Fenster des Startskripts.")
    ordner = schluessel_ordner()
    os.makedirs(ordner, exist_ok=True)
    datei = schluessel_datei(con, pid, kennung)
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
    alt = os.path.join(ordner, f"{kennung}.json")     # Name vor 1.27.1: weg, wenn sie zu dieser Sitzung gehört
    try:
        with open(alt, encoding="utf-8") as f:
            meine = json.load(f).get("sitzung") == eingabe.get("session_id")
        if meine:
            os.remove(alt)
    except (OSError, ValueError):
        pass
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


def hook_fehler_pfad():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "amw", "hook-fehler.log")


def hook_fehler(fehler):
    """Ein Fehler im Hook für schwere Befehle sperrt nichts – er steht nur hier (höchstens ~200 Zeilen, die ältesten fallen weg)."""
    try:
        pfad = hook_fehler_pfad()
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        try:
            with open(pfad, encoding="utf-8") as f:
                alt = f.readlines()[-199:]
        except OSError:
            alt = []
        with open(pfad, "w", encoding="utf-8") as f:
            f.writelines(alt + [f"{db.jetzt()} {type(fehler).__name__}: {str(fehler)[:300]}\n"])
    except Exception:
        pass


def schwere_befehle(eingabe):
    """Antwort für den PreToolUse-Hook: None (Befehl läuft) oder die Abweisung mit dem fertigen Ersatz-Befehl. Abgewiesen
    wird nur, wenn der Schalter „lauf_hook“ dieses PCs an ist; die Muster des Projekts (Einstellung schwere_befehle) gelten
    zusätzlich zu den mitgelieferten. Lässt sich das Projekt nicht bestimmen, gelten nur die mitgelieferten."""
    from . import einstellungen, schwer
    if not einstellungen.wert("lauf_hook") or not schwer.erkennbar(eingabe):
        return None
    eigene = []
    try:
        con = db.verbinde()
        try:
            pid = projekt_der_sitzung(con, os.environ.get("AMW_AGENT"), eingabe)
            if pid is not None:
                r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
                eigene = json.loads(r["einstellungen"] or "{}").get("schwere_befehle") or []
        finally:
            con.close()
    except Exception:
        eigene = []
    return schwer.entscheide(eingabe, eigene, amw=kern.BEFEHL)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    try:
        eingabe = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        eingabe = {}
    if eingabe.get("hook_event_name") == "PreToolUse":   # vor einem Shell-Befehl: schwere Läufe über die Warteschlange
        try:
            antwort = schwere_befehle(eingabe)
            if antwort:
                sys.stdout.write(json.dumps(antwort, ensure_ascii=False))
        except Exception as e:                      # nie stören: im Zweifel läuft der Befehl – aber der Fehler wird notiert
            hook_fehler(e)
        return 0
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
            pid = projekt_der_sitzung(con, kennung, eingabe)
            erkannt = not kennung
            if pid is not None:
                kennung = kern.kennung_heute(con, kennung, pid) or bekannte_kennung(con, pid, eingabe.get("session_id"))
            if pid is None and kennung:             # lieber nicht anmelden als im falschen Projekt (fremdes Wecken)
                meldung = (f"AMW: diese Sitzung ist NICHT angemeldet und wird nicht benachrichtigt – den Namen {kennung} gibt es "
                           "in mehreren Projekten. Starte über die Workbench (Kachel › Starten) oder richte den Ordner "
                           f"einem Projekt zu: {kern.BEFEHL} einrichten agenten-ordner <ordner> --projekt <name>")
                teile.append(meldung)
            elif not kennung:
                if quelle in ("startup", "resume") and agenten_ordner(con, eingabe.get("cwd")):
                    meldung = ("AMW: diese Sitzung ist NICHT angemeldet und wird nicht benachrichtigt. Als Agent: "
                               f"{kern.BEFEHL} anmelden --von <Name>")
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


def projekt_der_sitzung(con, kennung, eingabe):
    """Projekt dieser Sitzung: AMW_PROJEKT (Startbefehl oder Projektordner, → einrichtung.agenten_ordner_einrichten),
    sonst das der Kennung. Gibt es die Kennung in mehreren Projekten: über den Arbeitsordner (Profil-Ordner der Agenten),
    dann über eine frühere Anmeldung dieser Sitzung. Bleibt es offen: None – in einem falschen Projekt würden Nachrichten
    eines anderen Projekts diese Sitzung wecken."""
    for name in (os.environ.get("AMW_PROJEKT"), None):    # falsches AMW_PROJEKT: das Projekt der Kennung
        try:
            return db.projekt_fuer(con, name, kennung)
        except LookupError:
            pass
    alle = {r[0] for r in con.execute("SELECT id FROM projekt")}
    kandidaten = (db._projekte_der_kennung(con, kennung) if kennung else set()) or alle
    ordner = eingabe.get("cwd")
    if ordner:
        ordner = os.path.normcase(os.path.abspath(ordner))
        treffer = {r[0] for r in con.execute("SELECT projekt_id, ordner FROM agent WHERE ordner IS NOT NULL")
                   if r[0] in kandidaten and os.path.normcase(os.path.abspath(r[1])) == ordner}
        if len(treffer) == 1:
            return treffer.pop()
    if eingabe.get("session_id"):
        treffer = {r[0] for r in con.execute("SELECT a.projekt_id FROM sitzung s JOIN agent a ON a.id = s.agent_id"
                                             " WHERE s.claude_sitzung = ?", (eingabe["session_id"],))} & kandidaten
        if len(treffer) == 1:
            return treffer.pop()
    return None


def agenten_ordner(con, ordner, pid=None):
    """Lief hier schon einmal ein angemeldeter Agent? (Ordner aus der Sitzungstabelle, ohne Groß/klein; pid: nur dieses Projekt.)"""
    if not ordner:
        return False
    return con.execute("SELECT 1 FROM sitzung s JOIN agent a ON a.id = s.agent_id WHERE lower(s.arbeitsordner) = lower(?)"
                       " AND (? IS NULL OR a.projekt_id = ?) LIMIT 1", (ordner, pid, pid)).fetchone() is not None


if __name__ == "__main__":
    sys.exit(main())
