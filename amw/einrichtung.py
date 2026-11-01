"""Einrichtung des Wächters als geplante Windows-Aufgabe (→ doc/10 §5 „Start und Steuerung“, doc/07 E7).

Stufe 1: Aufgabe „AMW Dienst“ unter dem angemeldeten Benutzer – Start bei Anmeldung, ohne Fenster (pythonw),
danach alle 5 min erneut angestoßen (nur eine Instanz: läuft er, passiert nichts; ist er weg, startet er neu),
zusätzlich Neustart bei Startfehler, keine Laufzeitgrenze. Keine Administratorrechte.
Ohne `--ja` wird nur angezeigt, was passieren würde. Angelegt wird erst nach Zustimmung des Entwicklers.
"""
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
        f" -Description {q('AMW-Wächter: weckt Agenten, liefert die Workbench (127.0.0.1). Doku: F:\\amw\\doc\\10-architektur.md §5')}"
        " | Out-Null",
        f"Start-ScheduledTask -TaskName {q(AUFGABE)}",
        f"'eingerichtet und gestartet: ' + {q(AUFGABE)}",
    ])


def skript_entfernen():
    return (f"Stop-ScheduledTask -TaskName '{AUFGABE}' -ErrorAction SilentlyContinue; "
            f"Unregister-ScheduledTask -TaskName '{AUFGABE}' -Confirm:$false; 'entfernt: {AUFGABE}'")


def powershell(skript):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", skript],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout + r.stderr).strip()


def status(port):
    rc, aus = powershell(f"$x = Get-ScheduledTask -TaskName '{AUFGABE}' -ErrorAction SilentlyContinue; "
                         "if ($x) { $i = $x | Get-ScheduledTaskInfo; "
                         "'Aufgabe: ' + $x.State + ' · zuletzt ' + $i.LastRunTime + ' · Ergebnis ' + $i.LastTaskResult } "
                         "else { 'Aufgabe: nicht eingerichtet' }")
    zeilen = [aus]
    sperre = os.path.join(os.path.dirname(db.db_pfad()), "dienst.lock")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/projekte", timeout=3) as r:
            zeilen.append(f"Workbench: http://127.0.0.1:{port}/ antwortet ({r.status})")
    except OSError:
        zeilen.append(f"Workbench: auf Port {port} keine Antwort")
    zeilen.append(f"Datenbank: {db.db_pfad()}" + ("" if os.path.exists(db.db_pfad()) else " (gibt es noch nicht)"))
    zeilen.append(f"Sperrdatei: {sperre}" + (" vorhanden" if os.path.exists(sperre) else " fehlt"))
    return "\n".join(zeilen)
