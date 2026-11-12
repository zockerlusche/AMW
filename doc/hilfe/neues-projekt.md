# Neues Projekt – Schritt für Schritt

Ein Projekt ist für sich: eigene Agenten, Regeln, Aufgaben und Dokumente. Von Hand legst du nur den Projektordner an – alles andere macht die AMW.

## Du brauchst
- Anlegen geht nur am PC (Workbench auf dem Rechner, auf dem die AMW läuft). Hier kannst du die Schritte lesen.

## Schritte
1. **Projektordner anlegen** Im Explorer, z. B. F:\webshop. Darin arbeiten die Agenten (meist das Repository). Ein Ordner gehört zu genau einem Projekt.
2. **„+ Neues Projekt“ öffnen** Workbench am PC › oben in der Navigation die Projekt-Auswahl › „+ Neues Projekt“ (auch unter Einstellungen › Projekt). ![„+ Neues Projekt“ öffnen](np-auswahl)
3. **Ausfüllen und anlegen** Name, Projektordner, Lead (leer, wenn du selbst leitest), Agenten, Rechte, Regelwerk (das mitgelieferte Grund-Regelwerk – Regeln einzeln abhaken und anpassen –, die Kopie eines anderen Projekts oder ohne) und Farbe. „Anlegen“ richtet den Ordner ein (Hooks, Projekt-Name, amw-Befehl ohne Rückfrage), legt Lead und Agenten mit Profil und Startanweisung an und schreibt ein eigenes Startskript. ![Ausfüllen und anlegen](np-dialog) ![Ausfüllen und anlegen](np-fertig)
4. **Vor dem ersten Start: Leitbild und erste Aufgabe** „Zum Projekt“ › Planung › Leitbild: Ziel, Nicht-Ziele, Prinzipien. Dann eine erste Aufgabe (Arbeit) oder einen Meilenstein (Planung) – sonst findet der Agent nichts zu tun. Projektwissen (Technik, Build, Stil) schreibst du in eine CLAUDE.md im Projektordner; die legt die AMW nicht an. ![Vor dem ersten Start: Leitbild und erste Aufgabe](np-leitbild)
5. **Agent starten** Start › Kachel des Agenten › „Starten“. Es öffnet sich ein Tab „CC1 · Projektname“. Beim allerersten Start in einem neuen Ordner fragt Claude Code einmal, ob du dem Ordner vertraust – im Tab mit „Yes, proceed“ bestätigen; vorher läuft nichts an. Danach steht im Fenster „AMW: als CC1 angemeldet“. ![Agent starten](np-start)
6. **Erste Nachricht** Der Agent liest Regeln und Nachrichten, holt seine Arbeit und meldet sich. Seine Nachrichten siehst du unter Start, im Verlauf und in der Kachel (Gespräch). ![Erste Nachricht](np-nachricht)

## Häufige Fragen
### Woher weiß der erste Agent alles?
Startanweisung – der erste Satz jeder neuen Sitzung, im Profil des Agenten (Kachel › Profil, dort änderbar): wer er ist, wie er die AMW aufruft und womit er anfängt (Lead: planen und verteilen, Agent: Arbeit holen). Startinformationen – bei jedem Start, Fortsetzen und Verdichten gibt der Start-Hook ihm: Befehl und Kurzanleitung, Ziel, Nicht-Ziele und Prinzipien aus dem Leitbild, aktive Meilensteine, seine Aufgabenliste, offene Nachrichten und Regeln. Projektwissen – deine CLAUDE.md im Projektordner liest Claude Code selbst.

### Braucht ein neues Projekt MCP?
Nein. Agenten arbeiten über die Hooks und den amw-Befehl; beides richtet „Anlegen“ im Projektordner ein. Nur ein Lead ohne direkten Zugriff (z. B. in Cowork oder einer VM) nutzt den Dateiaustausch: Einstellungen › Dieser PC › Dateiaustausch an; Befehle in eingang-<projekt>\befehle im AMW-Ordner, Lese-Kopie daten\lesen-<projekt>.db – dafür muss der AMW-Ordner in der Desktop-App verbunden sein.

### Muss ich den Dienst kopieren?
Nein. Ein Dienst je PC benachrichtigt die Agenten jedes Projekts für sich. Keine zweite AMW-Installation anlegen.

### Was lege ich von Hand an?
Nur den Projektordner (und, wenn du willst, eine CLAUDE.md darin). Projekt, Agenten, Profile, Hooks und Startskript legt die AMW an.

### Brauche ich ein Git-Repository?
Für die AMW nicht. Für Code empfohlen: Aufgaben schließt ein Agent mit einem Beleg ab – Commit, Datei:Zeile oder Folgeaufgabe.

### Wo liegen die Claude-Code-Sitzungen?
Die Agenten arbeiten im Projektordner. Claude Code legt den Verlauf in deinem Benutzerordner unter .claude\projects ab, je Ordner. In der Workbench: Kachel › Gespräch.

### Dürfen die Agenten wie im anderen Projekt heißen?
Ja, CC1 darf es in jedem Projekt geben. Der Tab heißt dann „CC1 · Projektname“; jede Sitzung meldet sich nur in ihrem Projekt an.

### Projekt auf einen anderen Rechner?
amw sichern --projekt <name> schreibt das Projekt als eigene Datenbank samt Dokumenten (Anleitung „Mehrere Projekte“ in der Doku).
