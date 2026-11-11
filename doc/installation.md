# Installation

Dauer: etwa 15 Minuten. Alles läuft unter deinem Windows-Benutzer, ohne Administratorrechte.

## 1 Voraussetzungen
| | prüfen mit | woher |
|---|---|---|
| Windows 10 oder 11 | | |
| Python ≥ 3.11 im Pfad | `python --version` | python.org (beim Installieren „Add python.exe to PATH“ anhaken) |
| Claude Code ≥ 2.1 im Pfad, angemeldet | `claude --version` | code.claude.com |
| Git | `git --version` | git-scm.com |
| empfohlen: Windows Terminal | `where wt` | Microsoft Store (sonst startet AMW Agenten in Konsolenfenstern) |

## 2 Herunterladen
```
git clone https://github.com/zockerlusche/AMW.git C:\amw
```
Jeder Ordner geht; im Folgenden `C:\amw`. Damit `amw` überall funktioniert – in PowerShell, cmd **und Git Bash**
(die Shell, in der Claude Code unter Windows Befehle ausführt) –, den Unterordner `bin` in den Pfad nehmen
(Einstellungen › System › Info › Erweiterte Systemeinstellungen › Umgebungsvariablen › Benutzervariable `Path` › Neu:
`C:\amw\bin`), neues Terminal öffnen, prüfen: `amw --version`. Ohne Pfad geht immer `python C:\amw\amw-cli.py …` –
so steht der Befehl auch im Pflicht-Kontext der Agenten, damit er bei ihnen ohne Pfad-Einstellung funktioniert.

**Wer bin ich?** Jeder `amw`-Befehl, der etwas tut, fragt, wer handelt: `--von CC1`. Agenten bekommen ihre Kennung
automatisch (Umgebungsvariable `AMW_AGENT` aus dem Startskript). **Du als Mensch** schreibst `--von Entwickler` – oder
arbeitest in der Workbench, die das für dich erledigt.

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
7. **Remote Control?** (Vorgabe nein) – die Sitzungen sind dann zusätzlich über claude.ai bzw. die Claude-App
   steuerbar (Claude Codes `--remote-control`). Später je Agent: Zahnrad › Agenten › Block „Sitzung“.
8. **Hooks eintragen?** – schreibt in `<Projektordner>\.claude\settings.local.json` (vorhandene Einträge bleiben, Sicherung
   `*.vor-amw-<Datum>`):
   - `SessionStart`: meldet die Sitzung beim Wächter an und gibt den Pflicht-Kontext;
   - `Notification`, `Stop`, `StopFailure`, `UserPromptSubmit`, `SessionEnd` (im Hintergrund): Zustand des Agenten;
   - `statusLine`: Brücke für Kontext, Grenzen, Kosten – eine vorhandene Statusline wird weitergereicht;
   - Sperr-Regeln: Agenten dürfen den Wächter nicht entfernen oder neu einrichten;
   - ist der Projektordner ein Git-Repository, wird `settings.local.json` dort lokal ausgenommen (`.git/info/exclude`) –
     die Datei enthält Pfade dieses PCs und gehört nicht ins Repo.
9. **Wächter einrichten?** – geplante Aufgabe „AMW Dienst“: startet bei der Anmeldung ohne Fenster, wird alle 5 min
   angestoßen (läuft er, passiert nichts), liefert die Workbench auf http://127.0.0.1:8780. Nur ausprobieren? Dann „n“
   und später in einem eigenen Fenster `amw dienst vordergrund` (Strg+C beendet ihn); dauerhaft:
   `amw dienst einrichten --ja` (ohne `--ja` zeigt er nur, was er täte).

Ohne Fragen (z. B. für Skripte): `amw einrichten schnell --projekt-name "Mein Projekt" --lead TL --agenten CC1,CC2
--ordner C:\projekt --rechte vorgabe --mit-dienst`. Der Assistent ist wiederholbar – was es schon gibt, bleibt
(auch Profile, die du inzwischen geändert hast; neue Agenten kommen dazu).

Wo was liegt:
| | |
|---|---|
| Datenbank | `C:\amw\daten\amw.db` (anderer Ort: Zahnrad › Dieser PC; die Umgebungsvariable `AMW_DB` sieht der Wächter nur, wenn sie dauerhaft gesetzt ist) |
| Protokoll des Wächters | `C:\amw\daten\dienst.log` |
| Einstellungen dieses PCs | `%LOCALAPPDATA%\amw\einstellungen.json` |
| Anmeldungen der Sitzungen (Pipe + Schlüssel) | `%LOCALAPPDATA%\amw\sitzungen\` – nie in der Datenbank |
| Push-Zugänge, Online-Zugang | `%LOCALAPPDATA%\amw\push.json`, `turso.json` – nie im Repo |
| Startskript | `C:\amw\agenten-start.bat` (aus den Profilen erzeugt, lesbar; ältere `.ps1` bleiben liegen) |

## 4 Erster Start
1. **Workbench öffnen:** http://127.0.0.1:8780 – „Dienst“ oben grün? Sonst `amw dienst status`.
2. **Agenten starten:** Kachel eines Agenten anklicken › „Starten“ (neuer Tab im Windows Terminal) – oder
   `C:\amw\agenten-start.bat` (Doppelklick) für alle mit Profil auf einmal. Das Skript ist im Klartext lesbar: je Agent ein
   Tab, zuerst die letzte Sitzung fortsetzen, gibt es keine, neu mit derselben ID und dem Startsatz. Ein Lead ohne
   Ordner im Profil (er arbeitet als Chat in der Claude-App bzw. Cowork, über die Datei-Brücke) startet hier nie.
   Im Tab erscheint „AMW: als CC1 angemeldet“. Ein Agent liest seine Nachrichten mit `amw lesen --von CC1`.
3. **Probe:** In der Workbench über „Nachricht“ einem Agenten einen Auftrag schicken – der Wächter weckt ihn, und der
   Agent liest und antwortet.
4. **Planung beginnen:** Planung › Leitbild ausfüllen, „Neuer Bogen“ – siehe [anleitung-planung.md](anleitung-planung.md).
5. Optional: [Push aufs Handy](anleitung-push.md), [Online-Seite](online.md).

Bereits laufende Claude-Code-Sitzung nachträglich anmelden: im Tab `amw anmelden --von CC1`.
Einen bestehenden weiteren Projektordner einrichten: `amw einrichten agenten-ordner C:\anderes-projekt` (mit mehreren
Projekten dazu `--projekt <name>`: ein Ordner gehört zu genau einem Projekt).

## 5 Wie lernen die Agenten AMW?
- **Startsatz** (Zahnrad › Agenten › Block „Sitzung“): die erste Anweisung einer neuen Sitzung. Der Assistent setzt einen, der
  sagt, wer der Agent ist, wie er `amw` aufruft und womit er anfängt (Regeln, Nachrichten, nächster Schritt).
- **Pflicht-Kontext**: bei jedem Start und nach jeder Komprimierung bekommt der Agent den genauen Befehl und eine
  Kurzanleitung (lesen → erledigt, posten, nächster Schritt, fertig melden, Frage an dich), dazu seine Aufgaben,
  Nachrichten, das Leitbild und die Regeln.
- **Regeln für dein Team**: erst ein Beschluss, dann die Regel dazu – sie erscheinen in `amw regeln` und im Pflicht-Kontext:
  ```
  amw beschluss --stichwort "Prüfen" --quelle "Absprache 02.11." --text "Jede Änderung prüft ein zweiter Agent" --von Entwickler
  amw regel --ebene arbeit --nr 1 --beschluss 1 --text "Vor fertig: amw pruefung bitte an einen anderen Agenten" --von Entwickler
  ```
  (`--ebene arbeit` = wie das Team arbeitet, `projekt` = Fachregeln deines Projekts; `--beschluss` = Nummer aus der
  ersten Zeile.)

## 5a Weiterer Rechner (eigenes Projekt)
Ein Projekt kann auf einem anderen Rechner laufen, mit eigenen Agenten und eigener Datenbank. Die Workbench zeigt dann
alle Projekte in der Auswahl oben in der Navigation; Umschalten ändert nur die Ansicht.
1. AMW auf dem zweiten Rechner installieren wie oben, dort das Projekt anlegen (`amw projekt neu <name>`) und die
   Agenten einrichten.
2. Zahnrad › Dieser PC › **Name dieses Rechners** vergeben (z. B. „Laptop“). So erscheint er in der Projekt-Auswahl.
3. Zahnrad › Speicher und Abgleich: **denselben** Online-Speicher eintragen wie auf dem ersten Rechner und den Abgleich
   einschalten.
4. Fertig. Jeder Rechner lädt nur seine eigenen Projekte hoch und führt nur deren Befehle vom Handy aus. Am ersten
   Rechner steht das neue Projekt mit „↗“ in der Auswahl und öffnet die Online-Seite. Dafür muss unter Zahnrad › Online-Seite
   die Adresse der Online-Seite eingetragen sein.

**Weiteres Projekt auf diesem Rechner:** Workbench › Projekt-Auswahl › **+ Neues Projekt** – Schritt für Schritt in
[anleitung-projekte.md](anleitung-projekte.md).

Mehrere Projekte auf **demselben** Rechner liegen in derselben Datenbank, völlig getrennt nach Projekt: eigene
Agenten, Regeln, Aufgaben, Dokumente und KI-Vorlagen; kein Agent kommt in ein anderes Projekt. Gemeinsam sind nur
Grafikkarte und Schirm über eine gemeinsame Lauf-Schlange. Anlegen mit `amw projekt neu <name>`; mit
`--regeln-von <Projekt>` startet es mit einer Kopie der Arbeitsregeln eines anderen (danach getrennt). Dann
`amw einrichten` mit diesem Namen und einem **eigenen Projektordner**: Der Ordner bekommt das Projekt in seine Umgebung
(`AMW_PROJEKT`), das Startskript heißt `agenten-start-<projekt>.bat` – das des ersten Projekts bleibt unverändert.

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
amw sichern --ziel C:\Sicherung                       # falls du die Daten behalten willst
amw einrichten agenten-ordner C:\projekt --entfernen  # je Projektordner: Hooks, Statusline-Brücke, Sperr-Regeln heraus
amw dienst entfernen --ja
```
Dann den Ordner `C:\amw` und `%LOCALAPPDATA%\amw` löschen und `C:\amw\bin` aus dem Pfad nehmen. Eigene Einträge in
`settings.local.json` bleiben beim Entfernen erhalten; vor jeder Änderung liegt eine Sicherung `*.vor-amw-<Datum>` daneben.
