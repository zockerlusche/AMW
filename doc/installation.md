# Installation

Dauer: etwa 15 Minuten. Alles läuft unter deinem Windows-Benutzer, ohne Administratorrechte.

## 1 Voraussetzungen
| | prüfen mit | woher |
|---|---|---|
| Windows 10 oder 11 | | |
| Python ≥ 3.11 im Pfad | `python --version` | python.org (beim Installieren „Add python.exe to PATH“ anhaken) |
| Claude Code ≥ 2.1 im Pfad, angemeldet | `claude --version` | code.claude.com |
| Git | `git --version` | git-scm.com |
| empfohlen: Windows Terminal | `wt -v` | Microsoft Store (sonst startet AMW Agenten in Konsolenfenstern) |

## 2 Herunterladen
```
git clone https://github.com/zockerlusche/AMW.git C:\amw
```
Jeder Ordner geht; im Folgenden `C:\amw`. Damit `amw` überall funktioniert, den Ordner in den Pfad nehmen
(Einstellungen › System › Info › Erweiterte Systemeinstellungen › Umgebungsvariablen › Benutzervariable `Path` › Neu:
`C:\amw`), neues Terminal öffnen, prüfen: `amw --version`. Ohne Pfad: `C:\amw\amw.cmd …` oder
`python C:\amw\amw-cli.py …`.

## 3 Einrichten (Assistent)
```
amw einrichten
```
Der Assistent fragt:
1. **Name des Projekts**
2. **Kennung des Lead-Agenten** (Vorgabe `TL`; leer, wenn du selbst leitest)
3. **Kennungen der Agenten** (z. B. `CC1,CC2,CC3`)
4. **Projektordner**, in dem die Agenten arbeiten (das Repository deines Projekts)
5. **Rechte** der Agenten: `vorgabe` (Claude Code fragt bei heiklen Aktionen), `auto` oder `umgehen` (alles
   erlauben – nur, wenn du den Agenten vertraust; die Sperr-Regeln für den Wächter gelten trotzdem)
6. **Denkstufe** (leer = Vorgabe von Claude Code)
7. **Hooks eintragen?** – schreibt in `<Projektordner>\.claude\settings.local.json` (vorhandene Einträge bleiben, Sicherung
   `*.vor-amw-<Datum>`):
   - `SessionStart`: meldet die Sitzung beim Wächter an und gibt den Pflicht-Kontext;
   - `Notification`, `Stop`, `StopFailure`, `UserPromptSubmit`, `SessionEnd` (im Hintergrund): Zustand des Agenten;
   - `statusLine`: Brücke für Kontext, Grenzen, Kosten – eine vorhandene Statusline wird weitergereicht;
   - Sperr-Regeln: Agenten dürfen den Wächter nicht entfernen oder neu einrichten.
8. **Wächter einrichten?** – geplante Aufgabe „AMW Dienst“: startet bei der Anmeldung ohne Fenster, wird alle 5 min
   angestoßen (läuft er, passiert nichts), liefert die Workbench auf http://127.0.0.1:8780.

Ohne Fragen (z. B. für Skripte): `amw einrichten schnell --projekt-name "Mein Projekt" --lead TL --agenten CC1,CC2
--ordner C:\projekt --rechte vorgabe --mit-dienst`. Der Assistent ist wiederholbar – was es schon gibt, bleibt.

Wo was liegt:
| | |
|---|---|
| Datenbank | `C:\amw\daten\amw.db` (anderer Ort: Zahnrad › Dieser PC, oder Umgebungsvariable `AMW_DB`) |
| Protokoll des Wächters | `C:\amw\daten\dienst.log` |
| Einstellungen dieses PCs | `%LOCALAPPDATA%\amw\einstellungen.json` |
| Anmeldungen der Sitzungen (Pipe + Schlüssel) | `%LOCALAPPDATA%\amw\sitzungen\` – nie in der Datenbank |
| Push-Zugänge, Online-Zugang | `%LOCALAPPDATA%\amw\push.json`, `turso.json` – nie im Repo |
| Startskript | `C:\amw\agenten-start.ps1` (aus den Profilen erzeugt) |

## 4 Erster Start
1. **Workbench öffnen:** http://127.0.0.1:8780 – „Dienst“ oben grün? Sonst `amw dienst status`.
2. **Agenten starten:** Kachel eines Agenten anklicken › „Starten“ (neuer Tab im Windows Terminal) – oder
   `C:\amw\agenten-start.ps1` (Rechtsklick › Mit PowerShell ausführen) für alle auf einmal.
   Im Tab erscheint „AMW: als CC1 angemeldet“. Ein Agent liest seine Nachrichten mit `amw lesen --von CC1`.
3. **Probe:** In der Workbench über „Nachricht“ einem Agenten einen Auftrag schicken – der Wächter weckt ihn, und der
   Agent liest und antwortet.
4. **Planung beginnen:** Planung › Leitbild ausfüllen, „Neuer Bogen“ – siehe [anleitung-planung.md](anleitung-planung.md).
5. Optional: [Push aufs Handy](anleitung-push.md), [Online-Seite](online.md).

Bereits laufende Claude-Code-Sitzung nachträglich anmelden: im Tab `amw anmelden --von CC1`.
Einen bestehenden weiteren Projektordner einrichten: `amw einrichten agenten-ordner C:\anderes-projekt`.

## 5 Was den Agenten sagen?
Der Startsatz im Profil (Zahnrad › Agenten › Profil) ist die erste Anweisung einer neuen Sitzung. Bewährt:
> Du bist CC1. Wir arbeiten in C:\projekt. Bus = AMW: Lies zuerst `amw regeln` und `amw lesen --von CC1`.
> Nimm Arbeit mit `amw schritt naechster --nehmen --von CC1`, melde mit `amw posten`, schließe mit
> `amw aufgabe fertig <nr> --beleg <commit> --zusammenfassung "…"`.

Regeln für dein Team legst du als Beschluss und Regel an (`amw beschluss …`, `amw regel …`) – sie erscheinen in
`amw regeln` und im Pflicht-Kontext.

## 6 Aktualisieren
```
cd C:\amw
amw sichern
git pull
amw dienst neustart
```
Neue Datenbank-Versionen stellt AMW beim ersten Schreibzugriff selbst um (vorher sichern – siehe oben). Hat sich die
Online-Seite geändert, liefert dein Hoster den Zweig `web` neu aus (bei Git-Bereitstellung automatisch).

## 7 Entfernen
```
amw dienst entfernen --ja
```
Dann den Ordner `C:\amw` und `%LOCALAPPDATA%\amw` löschen und in den Projektordnern die AMW-Einträge aus
`.claude\settings.local.json` nehmen (oder die Sicherung `*.vor-amw-*` zurückkopieren).
