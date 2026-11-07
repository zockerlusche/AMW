"""Einrichtung des Wächters als geplante Windows-Aufgabe (→ doc/installation.md).

Stufe 1: Aufgabe „AMW Dienst“ unter dem angemeldeten Benutzer – Start bei Anmeldung, ohne Fenster (pythonw),
danach alle 5 min erneut angestoßen (nur eine Instanz: läuft er, passiert nichts; ist er weg, startet er neu),
zusätzlich Neustart bei Startfehler, keine Laufzeitgrenze. Keine Administratorrechte.
Ohne `--ja` wird nur angezeigt, was passieren würde. Angelegt wird erst nach Zustimmung des Entwicklers.
"""
import json
import os
import subprocess
import sys
import urllib.request

from . import db

AUFGABE = "AMW Dienst"
WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pythonw():
    kandidat = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return kandidat if os.path.exists(kandidat) else sys.executable


def skript_einrichten(port):
    starter = os.path.join(WURZEL, "start_dienst.pyw")
    # Werte stehen in einfachen Anführungszeichen; Pfade mit ' werden verdoppelt (PowerShell-Regel).
    q = lambda s: "'" + str(s).replace("'", "''") + "'"
    argumente = f'"{starter}" --port {port}'
    return "\n".join([
        f"$a = New-ScheduledTaskAction -Execute {q(pythonw())} -Argument {q(argumente)}"
        f" -WorkingDirectory {q(WURZEL)}",
        # Bei Anmeldung, dann alle 5 min wiederholt: läuft der Dienst, verwirft Windows den Start (IgnoreNew);
        # ist er weg (Absturz, beendet), startet er neu. Das „bei Fehler neu starten“ allein greift nicht bei jedem Ende.
        "$t = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME",
        "$t.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)).Repetition",
        "$s = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)"
        " -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable"
        " -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries",
        "$p = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited",
        f"Register-ScheduledTask -TaskName {q(AUFGABE)} -Action $a -Trigger $t -Settings $s -Principal $p"
        f" -Description {q('AMW-Wächter: weckt Agenten, liefert die Workbench (127.0.0.1). Doku: ' + os.path.join(WURZEL, 'doc', 'betrieb.md'))}"
        " | Out-Null",
        f"Start-ScheduledTask -TaskName {q(AUFGABE)}",
        f"'eingerichtet und gestartet: ' + {q(AUFGABE)}",
    ])


def skript_entfernen():
    return (f"Stop-ScheduledTask -TaskName '{AUFGABE}' -ErrorAction SilentlyContinue; "
            f"Unregister-ScheduledTask -TaskName '{AUFGABE}' -Confirm:$false; 'entfernt: {AUFGABE}'")


def befehl_cli():
    """So wird AMW aus jeder Shell aufgerufen (für Hinweise an den Benutzer)."""
    return f"python {WURZEL.replace(os.sep, '/')}/amw-cli.py"


def powershell(skript):
    # Ausgabe als UTF-8 (sonst kommen Umlaute und · aus Windows PowerShell 5 verstümmelt an)
    skript = "[Console]::OutputEncoding = [Text.Encoding]::UTF8; " + skript
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", skript],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout + r.stderr).strip()


def aufgabe_ordner():
    """Arbeitsordner der eingerichteten Wächter-Aufgabe (None = keine Aufgabe) – gehört sie zu dieser AMW?"""
    rc, aus = powershell(f"$x = Get-ScheduledTask -TaskName '{AUFGABE}' -ErrorAction SilentlyContinue; "
                         "if ($x) { $x.Actions[0].WorkingDirectory }")
    return aus.strip() or None if rc == 0 else None


def fremde_aufgabe():
    """Text, wenn die Aufgabe „AMW Dienst“ zu einer anderen AMW-Installation gehört, sonst None."""
    ordner = aufgabe_ordner()
    if ordner and os.path.normcase(os.path.normpath(ordner)) != os.path.normcase(os.path.normpath(WURZEL)):
        return (f"Die Aufgabe „{AUFGABE}“ gehört zu einer anderen AMW-Installation ({ordner}), nicht zu dieser ({WURZEL})."
                " Dort ausführen oder sie dort erst entfernen.")
    return None


def status(port):
    rc, aus = powershell(f"$x = Get-ScheduledTask -TaskName '{AUFGABE}' -ErrorAction SilentlyContinue; "
                         "if ($x) { $i = $x | Get-ScheduledTaskInfo; "
                         "'Aufgabe: ' + $x.State + ' · zuletzt ' + $i.LastRunTime + ' · Ergebnis ' + $i.LastTaskResult } "
                         "else { 'Aufgabe: nicht eingerichtet' }")
    zeilen = [aus]
    fremd = fremde_aufgabe()
    if fremd:
        zeilen.append("ACHTUNG: " + fremd)
    if os.environ.get("AMW_DB"):
        zeilen.append("Hinweis: AMW_DB ist in diesem Fenster gesetzt – der Wächter sieht sie nur, wenn sie dauerhaft als"
                      " Benutzervariable gesetzt ist; besser: Zahnrad › Dieser PC › Datenbank")
    sperre = os.path.join(os.path.dirname(db.db_pfad()), "dienst.lock")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/projekte", timeout=3) as r:
            zeilen.append(f"Workbench: http://127.0.0.1:{port}/ antwortet ({r.status})")
    except OSError:
        zeilen.append(f"Workbench: auf Port {port} keine Antwort")
    zeilen.append(f"Datenbank: {db.db_pfad()}" + ("" if os.path.exists(db.db_pfad()) else " (gibt es noch nicht)"))
    zeilen.append(f"Sperrdatei: {sperre}" + (" vorhanden" if os.path.exists(sperre) else " fehlt"))
    zeilen.append("Angemeldete Sitzungen (Postfach → Claude-Prozess):")     # doppelte/Hintergrund-Anmeldung erkennen
    from . import hook
    try:
        namen = sorted(n for n in os.listdir(hook.schluessel_ordner()) if n.endswith(".json"))
    except OSError:
        namen = []
    for n in namen:
        try:
            with open(os.path.join(hook.schluessel_ordner(), n), encoding="utf-8") as f:
                p = hook.claude_prozess(json.load(f).get("pipe"))
        except (OSError, ValueError):
            p = None
        zeilen.append(f"  {n[:-5]:<8} " + (hook.beschreibung(p) + ("  ← PRÜFEN" if p["art"] == "bg" else "") if p else "Prozess beendet"))
    try:
        con = db.verbinde(nur_lesen=True)
        fehlt = [u for (p,) in con.execute("SELECT id FROM projekt").fetchall() for u in hook.unangemeldet(con, p)]
        con.close()
    except Exception:
        fehlt = []
    for u in fehlt:
        zeilen.append(f"  NICHT ANGEMELDET: {u['kennung'] or '?'} · Sitzung {u['sitzung']}, PID {u['pid']}, {u['ordner']}"
                      f" – im Fenster: {befehl_cli()} anmelden --von {u['kennung'] or '<Kennung>'}")
    return "\n".join(zeilen)


def befehl(starter):
    """Aufruf eines Starters aus dem AMW-Ordner (amw-hook.py, amw-statusline.py) mit dem Python dieses PCs."""
    py = pythonw().replace("pythonw.exe", "python.exe")
    return f'"{py}" -X utf8 "{os.path.join(WURZEL, starter).replace(os.sep, "/")}"'


ZUSTANDS_HOOKS = ("Notification", "Stop", "StopFailure", "UserPromptSubmit", "SessionEnd")
SPERREN = [f"Bash(*schtasks*{AUFGABE}*)", f"PowerShell(*schtasks*{AUFGABE}*)", f"PowerShell(*ScheduledTask*{AUFGABE}*)",
           f"Bash(*ScheduledTask*{AUFGABE}*)", "Bash(*amw*dienst entfernen*)", "PowerShell(*amw*dienst entfernen*)",
           "Bash(*amw*dienst einrichten*)", "PowerShell(*amw*dienst einrichten*)"]
# Der amw-Befehl braucht keine Rückfrage: ein Agent ruft ihn ständig auf (lesen, posten, schritt …), auch mit Rechten
# „vorgabe“. Was er darf, prüft die AMW selbst (Rolle, Lead, Entwickler) – die Erlaubnis gilt nur für diesen einen Befehl.
AMW_BEFEHL = f"python {WURZEL.replace(os.sep, '/')}/amw-cli.py"
ERLAUBT = [f"Bash({AMW_BEFEHL}:*)", f"PowerShell({AMW_BEFEHL}:*)"]


def hook_einstellungen():
    """Was ein Agenten-Projektordner in .claude/settings.local.json braucht (→ doc/ausbau.md §4):
    SessionStart meldet an und gibt den Pflicht-Kontext; die Zustands-Hooks laufen im Hintergrund (async) und setzen
    „arbeitet / frei / wartet auf Freigabe / Fehler“; die Statusline-Brücke merkt sich Kontext, Grenzen, Kosten und reicht
    die bisherige Statusline weiter; die Sperren schützen den Wächter vor Versehen."""
    hook = {"type": "command", "command": befehl("amw-hook.py"), "timeout": 30}
    still = {**hook, "async": True}
    return {
        "hooks": {"SessionStart": [{"matcher": "startup|resume|compact", "hooks": [hook]}],
                  **{e: [{"hooks": [still]}] for e in ZUSTANDS_HOOKS}},
        "statusLine": {"type": "command", "command": befehl("amw-statusline.py"), "padding": 0},
        "permissions": {"deny": SPERREN, "allow": ERLAUBT},
    }


def _hat_amw(eintraege, starter):
    return any(starter in (h.get("command") or "") for e in eintraege or [] for h in e.get("hooks", []))


def _sichern_und_schreiben(datei, d):
    os.makedirs(os.path.dirname(datei), exist_ok=True)
    if os.path.exists(datei):
        import shutil
        shutil.copy2(datei, datei + f".vor-amw-{db.jetzt()[:10]}")
    with open(datei + ".neu", "w", encoding="utf-8", newline="\n") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(datei + ".neu", datei)


def _git_ausnehmen(ordner):
    """settings.local.json enthält Pfade dieses PCs – im Git des Projekts lokal ausnehmen (.git/info/exclude, wird
    nicht eingecheckt). Rückgabe: Text der Änderung oder None."""
    info = os.path.join(ordner, ".git", "info")
    if not os.path.isdir(os.path.join(ordner, ".git")):
        return None
    zeilen = [".claude/settings.local.json", ".claude/settings.local.json.vor-amw-*"]   # samt Sicherungen
    datei = os.path.join(info, "exclude")
    try:
        with open(datei, encoding="utf-8") as f:
            da = f.read().split("\n")
    except FileNotFoundError:
        da = []
    fehlt = [z for z in zeilen if z not in da]
    if not fehlt:
        return None
    os.makedirs(info, exist_ok=True)
    with open(datei, "a", encoding="utf-8") as f:
        f.write("\n" + "\n".join(fehlt) + "\n")
    return "im Git des Projekts lokal ausgenommen (.git/info/exclude)"


def agenten_ordner_entfernen(ordner, schreiben=True):
    """Nimmt alle AMW-Einträge (Hooks, Statusline-Brücke, Sperr-Regeln) wieder aus settings.local.json."""
    datei = os.path.join(ordner, ".claude", "settings.local.json")
    try:
        with open(datei, encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        return []
    aenderungen = []
    for ereignis, eintraege in list((d.get("hooks") or {}).items()):
        rest = [e for e in eintraege if not any("amw-hook.py" in (h.get("command") or "") for h in e.get("hooks", []))]
        if len(rest) != len(eintraege):
            aenderungen.append(f"Hook {ereignis}")
            if rest:
                d["hooks"][ereignis] = rest
            else:
                del d["hooks"][ereignis]
    if d.get("hooks") == {}:
        del d["hooks"]
    if "AMW_PROJEKT" in (d.get("env") or {}):
        aenderungen.append(f"Projekt {d['env'].pop('AMW_PROJEKT')} (AMW_PROJEKT)")
        if not d["env"]:
            del d["env"]
    if "amw-statusline.py" in ((d.get("statusLine") or {}).get("command") or ""):
        del d["statusLine"]
        aenderungen.append("Statusline-Brücke (es gilt wieder deine eigene Statusline)")
    liste = (d.get("permissions") or {}).get("deny")
    if liste:
        rest = [s for s in liste if s not in SPERREN]
        if len(rest) != len(liste):
            aenderungen.append(f"{len(liste) - len(rest)} Sperr-Regel(n)")
            d["permissions"]["deny"] = rest
    liste = (d.get("permissions") or {}).get("allow")
    if liste:
        rest = [s for s in liste if s not in ERLAUBT]
        if len(rest) != len(liste):
            aenderungen.append("amw-Befehl ohne Rückfrage")
            d["permissions"]["allow"] = rest
    if aenderungen and schreiben:
        _sichern_und_schreiben(datei, d)
    return aenderungen


def ordner_projekt(ordner):
    """Projekt, dem der Ordner schon gehört (AMW_PROJEKT in .claude/settings.local.json), sonst None."""
    try:
        with open(os.path.join(ordner, ".claude", "settings.local.json"), encoding="utf-8") as f:
            return (json.load(f).get("env") or {}).get("AMW_PROJEKT")
    except (OSError, ValueError, AttributeError):
        return None


def agenten_ordner_einrichten(ordner, schreiben=True, sperren=True, projekt=None):
    """Führt hook_einstellungen() in <ordner>/.claude/settings.local.json zusammen – vorhandene Einträge bleiben,
    AMW-Einträge werden nur ergänzt, nie doppelt. Eine fremde Statusline wird nicht ersetzt, sondern als
    „statusline_weiter“ hinter die Brücke gehängt. Vorher eine Sicherung der Datei. Rückgabe: Liste der Änderungen.
    projekt: Name des Projekts, zu dem der Ordner gehört – steht als AMW_PROJEKT in „env“, das Claude Code jeder Sitzung
    dort setzt (auch von Hand gestartet). Ein Ordner gehört zu genau einem Projekt."""
    from . import einstellungen
    if not os.path.isdir(ordner):
        raise FileNotFoundError(f"Ordner {ordner} gibt es nicht")
    datei = os.path.join(ordner, ".claude", "settings.local.json")
    try:
        with open(datei, encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        d = {}
    soll, aenderungen = hook_einstellungen(), []
    if projekt:
        umgebung = d.setdefault("env", {})
        alt = umgebung.get("AMW_PROJEKT")
        if alt and alt != projekt:
            raise ValueError(f"Ordner {ordner} gehört schon zum Projekt {alt} – ein Ordner gehört zu genau einem Projekt "
                             "(anderes Projekt: eigener Ordner)")
        if not alt:
            umgebung["AMW_PROJEKT"] = projekt
            aenderungen.append(f"Projekt {projekt} (AMW_PROJEKT)")
    hooks = d.setdefault("hooks", {})
    for ereignis, eintraege in soll["hooks"].items():
        if not _hat_amw(hooks.get(ereignis), "amw-hook.py"):
            hooks.setdefault(ereignis, []).extend(eintraege)
            aenderungen.append(f"Hook {ereignis}")
    alt = (d.get("statusLine") or {}).get("command", "")
    if "amw-statusline.py" not in alt:
        if not alt:                                       # sonst gälte die des Benutzers – auch die weiterreichen
            try:
                with open(os.path.join(os.path.expanduser("~"), ".claude", "settings.json"), encoding="utf-8") as f:
                    alt = (json.load(f).get("statusLine") or {}).get("command", "")
            except (OSError, ValueError):
                alt = ""
        if alt and "amw-statusline.py" not in alt and not einstellungen.wert("statusline_weiter"):
            if schreiben:
                einstellungen.speichern({"statusline_weiter": alt})
            aenderungen.append(f"bisherige Statusline wird weitergereicht: {alt}")
        d["statusLine"] = soll["statusLine"]
        aenderungen.append("Statusline-Brücke")
    if sperren:                                           # nicht im Ordner dessen, der den Wächter betreut
        liste = d.setdefault("permissions", {}).setdefault("deny", [])
        neu = [s for s in soll["permissions"]["deny"] if s not in liste]
        if neu:
            liste.extend(neu)
            aenderungen.append(f"{len(neu)} Sperr-Regel(n)")
        liste = d["permissions"].setdefault("allow", [])
        neu = [s for s in soll["permissions"]["allow"] if s not in liste]
        if neu:
            liste.extend(neu)
            aenderungen.append("amw-Befehl ohne Rückfrage")
    if aenderungen and schreiben:
        _sichern_und_schreiben(datei, d)
    if schreiben and os.path.exists(datei):               # auch bei bestehender Einrichtung nachziehen
        git = _git_ausnehmen(ordner)
        if git:
            aenderungen.append(git)
    return aenderungen
