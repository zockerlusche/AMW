# Agenten: Ordner einrichten, umbenennen, starten

Ein Agent arbeitet in einem Ordner auf diesem PC. Damit die AMW ihn benachrichtigen, überwachen und seinen Verbrauch anzeigen kann, richtet sie diesen Ordner einmal ein.

## Du brauchst
- Den Ordner, in dem der Agent arbeitet (meist der Projektordner).
- Die Befehlszeile am PC (`amw …`).

## Schritte
1. **Ordner einrichten** `amw einrichten agenten-ordner <ordner> --projekt <projekt>` ausführen. Die AMW trägt ihre Einträge in die Einstellungen von Claude Code in diesem Ordner ein und sichert die Datei vorher. Danach erscheinen „Zustand und Verbrauch“ des Agenten.
2. **Profil prüfen** Unter Einstellungen › Agenten stehen Ordner, Modell, Denkaufwand, Rechte und Startanweisung. Ändern geht dort oder mit `amw agent profil <name> --ordner … --modell …`.
3. **Starten** Auf der Startseite den Agenten anklicken › „Starten / fortsetzen“. Die AMW öffnet ihn in einem neuen Terminal-Tab.

## Diese Werte trägst du ein
| Feld in der AMW | Woher |
|---|---|
| Arbeitsordner | der Ordner des Projekts, in dem der Agent arbeitet |
| Startanweisung | erster Satz einer neuen Sitzung, z. B. „Lies deine Nachrichten und arbeite sie ab.“ |

## Typische Fehler
- **„Noch keine Daten“ bei Zustand und Verbrauch** – Der Ordner ist noch nicht eingerichtet (Schritt 1), oder die Sitzung wurde vor dem Einrichten gestartet. Einmal neu starten.
- **„Nicht verbunden“** – Die Sitzung läuft, kennt aber ihren Namen nicht. Im Fenster des Agenten `amw anmelden --von <name>` ausführen.
- **Der Ordner gehört schon zu einem anderen Projekt** – Ein Ordner gehört zu genau einem Projekt. Für ein zweites Projekt einen eigenen Ordner nehmen.

## Danach
- Umbenennen: `amw agent umbenennen <alt> <neu>`. Der alte Name bleibt als zweiter Name gültig, damit ältere Nachrichten und Befehle weiter funktionieren.
- Was die AMW in den Ordner einträgt, nimmt `amw einrichten agenten-ordner <ordner> --entfernen` wieder heraus.

## Häufige Fragen
### Warum geht das Umbenennen nicht in der Workbench?
Der Name steckt in Startskripten und laufenden Sitzungen auf diesem PC. Die Befehlszeile ändert alles an einer Stelle, ohne dass eine laufende Sitzung ihren Namen verliert.

### Wie starte ich einen Agenten von Hand – etwa nach einem Neustart des PCs?
⋯ am Agenten › „Startbefehl …“ (oder Einstellungen › Agenten › „Startbefehl zum Kopieren“). Dort stehen Ordner, Zusatzordner, Modell, Denkaufwand, Rechte und die letzte Sitzung, darunter zwei fertige Zeilen: „Fortsetzen“ (letzte Sitzung) und „Neu starten“ – für PowerShell oder die Eingabeaufforderung. „Kopieren“, ins Terminal einfügen, Enter. Genau so startet die AMW den Agenten auch selbst.

### Wie viel verbraucht ein Agent je Aufgabe?
Klick auf den Agenten › Übersicht › „Verbrauch je Aufgabe“: das Mittel (Median) der letzten zehn fertigen Aufgaben, das eingestellte Modell mit Denkaufwand, die Aufgabe in Arbeit bisher und je Aufgabe der Betrag. Im Fenster einer Aufgabe steht ihr Wert unter „Verbrauch“, in der Befehlszeile bei `amw aufgabe zeige <nr>` und `amw agent profil <name>`. Gezählt wird der Gegenwert in Dollar, den Claude Code je Sitzung meldet – auch im Abo, wo nichts extra bezahlt wird. Je Aufgabe ist er genähert: Was zwischen Beginn und Abschluss anfiel, zählt zu der Aufgabe, die der Agent zuletzt begonnen hat. Die Zahlen helfen beim Einstellen von Modell und Denkaufwand im Profil; sie gelten ab dem nächsten Start.
