# Mehrere Projekte

Eine AMW kann mehrere Projekte führen, auf einem Rechner und über mehrere Rechner verteilt. Jedes Projekt ist für sich: eigene
Agenten, Regeln, Aufgaben, Fragen, Dokumente und KI-Vorlagen. Kein Agent kommt in ein anderes Projekt. In der Workbench
wählst du das Projekt oben in der Navigation (am Handy: Chip im Kopf); Umschalten ändert nur die Ansicht, alle Projekte
arbeiten weiter.

## Was getrennt ist und was gemeinsam

| getrennt je Projekt | gemeinsam auf einem Rechner (Marke „dieser PC“) |
|---|---|
| Agenten, Sitzungen, Wecken, HALT | der Wächter (`AMW Dienst`) – er weckt je Projekt nur dessen Agenten |
| Arbeits- und Projektregeln, Beschlüsse, Wortlaut | die Datenbank `amw.db` – jede Zeile trägt ihr Projekt |
| Aufgaben, Planung, Fragen, Dokumente, Releases | Grafikkarte und Schirm über **eine** Lauf-Schlange (fremde Läufe nur mit Projektname und Platz) |
| KI-Vorlagen | eingetragene KIs und Modelle samt Lizenz-Freigabe |
| Push-Meldungen (mit Projektname im Titel) | Einstellungen dieses PCs: Port, Online-Speicher, Push-Kanäle |
| Projektordner, Startskript, Datei-Brücke | |

Eine zweite AMW-Installation auf demselben Rechner ist nicht vorgesehen: sie würde sich mit der ersten die geplante
Aufgabe, den Port und die Einstellungen teilen.

## Neues Projekt auf diesem Rechner

Dieselbe Anleitung mit Bildern steht in der Workbench: Projekt-Auswahl › **? Anleitung** (auch im Dialog „Neues
Projekt“ und unter Einstellungen › Projekt; online nur zum Lesen – angelegt wird am PC).

1. **Projektordner anlegen** – selbst, z. B. im Explorer: `F:\webshop`. Darin arbeiten die Agenten des Projekts (meist
   das Repository). Ein Ordner gehört zu genau einem Projekt.
2. **Workbench am PC öffnen** (http://127.0.0.1:8780) › oben auf die Projekt-Auswahl › **+ Neues Projekt** (auch unter
   Einstellungen › Projekt). Ausfüllen:
   - **Name**
   - **Projektordner** – der Pfad aus Schritt 1
   - **Lead** (Vorgabe `TL`; leer, wenn du selbst leitest) und **Agenten** (`CC1,CC2`) – Kennungen dürfen wie in anderen
     Projekten heißen
   - **Rechte** der Agenten
   - **Arbeitsregeln**: ohne oder eine einmalige Kopie der Arbeitsregeln eines anderen Projekts (danach getrennt)
   - **Farbe** für Streifen und Projekt-Auswahl
3. **Anlegen.** Die AMW legt Projekt, Lead und Agenten mit Profil und Startsatz an, richtet den Projektordner ein (Hooks,
   Statusline, Sperr-Regeln, der amw-Befehl ohne Rückfrage und die Projekt-Kennung `AMW_PROJEKT` in
   `.claude\settings.local.json`) und schreibt ein eigenes Startskript `agenten-start-<projekt>.ps1`. Das Startskript
   des ersten Projekts bleibt unverändert.
4. **Vor dem ersten Start:** **Zum Projekt** wechseln › Planung › **Leitbild** ausfüllen (Ziel, Nicht-Ziele, Prinzipien)
   und eine **erste Aufgabe** oder einen Bogen anlegen ([Planung](anleitung-planung.md)). Projektwissen (Technik, Build,
   Stil) gehört in eine `CLAUDE.md` im Projektordner – die legt die AMW nicht an. Regeln erst als Beschluss, dann als
   Regel ([Installation](installation.md), Abschnitt 5).
5. Start › Kachel eines Agenten › **Starten**. Es öffnet sich ein Tab „CC1 · <Projekt>“. **Beim allerersten Start in
   einem neuen Ordner** fragt Claude Code einmal, ob du dem Ordner vertraust – im Tab mit „Yes, proceed“ bestätigen;
   vorher laufen weder Hook noch Startsatz. Danach steht im Fenster „AMW: als CC1 angemeldet“. Der Agent liest Regeln und Nachrichten, holt seine Arbeit und meldet sich.

Ohne Workbench geht dasselbe mit `amw einrichten` (fragt bei einem weiteren Projekt auch nach der Regel-Kopie) oder
einzeln: `amw projekt neu <name> --ordner <pfad> [--regeln-von <Projekt>]`, dann `amw agent neu <kennung> --projekt
<name> --von Entwickler` (bekommt den Projektordner als Profil) und `amw einrichten agenten-ordner <pfad> --projekt <name>`.

## Woher der erste Agent alles weiß

- **Startsatz** – der erste Satz jeder neuen Sitzung, im Profil des Agenten (Kachel › Profil, dort änderbar): wer er
  ist, wie er die AMW aufruft, womit er anfängt. Agent: „Du bist CC1. Wir koordinieren uns über AMW … Lies zuerst
  `amw regeln` und `amw lesen`, dann hole Arbeit mit `amw schritt naechster --nehmen`.“ Lead: „… plane mit
  `amw leitbild`, `amw bogen`, `amw spec` und verteile die Schritte.“
- **Pflicht-Kontext** – bei jedem Start, Fortsetzen und Verdichten gibt der Start-Hook: Befehl und Kurzanleitung,
  Projektziel, Nicht-Ziele, Prinzipien und Definition of Done aus dem Leitbild, aktive Bögen, seine Aufgabenliste, offene
  Nachrichten, Regeln. **Fehlt das Leitbild**, steht dort „Projekt NEU“: der Lead fragt den Entwickler nach Ziel und
  Nicht-Zielen und trägt sie ein; ein Agent meldet sich und wartet auf seine erste Aufgabe, statt zu raten.
- **Projektwissen** – eine `CLAUDE.md` im Projektordner liest Claude Code selbst.

## Woher ein Agent weiß, wohin er gehört

- **Startbefehl** (Kachel „Starten“ oder Startskript) setzt `AMW_AGENT` (Kennung) und `AMW_PROJEKT` (Projekt).
- **Projektordner**: `AMW_PROJEKT` steht auch in `.claude\settings.local.json` – Claude Code setzt es jeder Sitzung dort,
  auch wenn du sie von Hand startest.
- **Beim Start** meldet der Hook die Sitzung im Projekt an und gibt den Pflicht-Kontext dieses Projekts: Befehl und
  Kurzanleitung, Aufgaben, Nachrichten, Leitbild, Regeln. Ist das Projekt nicht erkennbar und gibt es die Kennung in
  mehreren Projekten, meldet er die Sitzung **nicht** an und sagt im Fenster, was zu tun ist – nie im falschen Projekt.
- `amw` findet die Datenbank selbst; ein Agent nennt nie ein fremdes Projekt (`--projekt` mit einem Projekt, in dem es
  seine Kennung nicht gibt, lehnt die AMW ab).

## Häufige Fragen

| Frage | Antwort |
|---|---|
| Braucht ein neues Projekt MCP? | Nein. Agenten arbeiten über die Hooks und den amw-Befehl; beides richtet „Anlegen“ im Projektordner ein. Nur ein Lead ohne direkten Zugriff (Cowork, VM) nutzt die [Datei-Brücke](#datei-brücke-je-projekt) – dafür muss der AMW-Ordner in der Desktop-App verbunden sein. |
| Muss ich den Wächter kopieren? | Nein. Ein Wächter je PC weckt die Agenten jedes Projekts für sich (Nachrichten, Takt, HALT, Neustart je Projekt). Keine zweite AMW-Installation. |
| Was lege ich von Hand an? | Nur den Projektordner – und, wenn du willst, eine `CLAUDE.md` darin. |
| Brauche ich ein Git-Repository? | Für die AMW nicht. Für Code empfohlen: Aufgaben schließt ein Agent mit einem Beleg ab (Commit, Datei:Zeile oder Folgeaufgabe). |
| Wo liegen die Claude-Code-Sitzungen? | Die Agenten arbeiten im Projektordner; Claude Code legt den Verlauf im Benutzerordner unter `.claude\projects\` ab (je Ordner). In der Workbench: Kachel › Gespräch. |
| Dürfen Agenten wie im anderen Projekt heißen? | Ja. Der Tab heißt dann „CC1 · <Projekt>“; jede Sitzung meldet sich nur in ihrem Projekt an. |
| Fragt Claude Code bei jedem amw-Befehl nach? | Nein: der amw-Befehl ist im Projektordner erlaubt (auch mit Rechten „vorgabe“); was ein Agent darf, prüft die AMW selbst. Andere heikle Aktionen fragt Claude Code wie gewohnt nach. |
| Teilen sich Projekte etwas? | Grafikkarte und Schirm (ein Lauf zur Zeit), die CPU-Spur der Lauf-Schlange (Vorgabe 2 schwere Läufe zugleich) und den Arbeitsspeicher – Rechen-Läufe können also aufeinander warten, Wecken und Nachrichten nie. |

## Ein Projekt sichern oder umziehen

`amw sichern --projekt <name>` schreibt eine eigene, vollständige AMW-Datenbank nur mit diesem Projekt (dazu, was zum
Rechner gehört: KIs, Modelle, Schirm) und daneben seine Dokument-Dateien – geht auch, während die Agenten arbeiten.
Umziehen auf einen neuen Rechner: dort AMW installieren, die Sicherung als `daten\amw.db` und den Ordner
`…-dokumente` als `daten\dokumente` hineinlegen, dann `amw einrichten` (Projektordner und Wächter). Danach das Projekt
auf dem alten Rechner nicht mehr betreiben – ein Projekt lebt auf genau einem Rechner.

## Datei-Brücke je Projekt

Für einen Lead, der die Datenbank nicht direkt öffnen kann (z. B. in einer VM; Einstellung `bruecke_an`), hat jedes
Projekt seine eigene Brücke:

| | erstes Projekt | jedes weitere |
|---|---|---|
| Befehle | `eingang-tl\befehle\*.json` | `eingang-<projekt>\befehle\*.json` |
| Lese-Kopie | `daten\tl_lesen.db` | `daten\lesen-<projekt>.db` |
| ausgeführt als | Einstellung `bruecke_absender` (Vorgabe TL) | der Lead des Projekts |

Mit mehreren Projekten enthält jede Lese-Kopie nur ihr Projekt (dazu, was zum PC gehört: KIs, Modelle, Schirm). Ein
Befehl wirkt nur im Projekt seiner Brücke; `"projekt"` in der Befehlsdatei darf nur dieses nennen.

## Projekt auf einem anderen Rechner

1. Dort AMW installieren und `amw einrichten` laufen lassen ([Installation](installation.md)).
2. Zahnrad › Dieser PC › **Name dieses Rechners** vergeben.
3. Zahnrad › Online-Speicher: **denselben** Online-Speicher wie auf dem ersten Rechner eintragen, Abgleich an.

Jeder Rechner lädt nur seine eigenen Projekte hoch und führt nur deren Befehle vom Handy aus; online trägt jeder Eintrag
die Projekt-Kennung. Am ersten Rechner steht das Projekt mit „↗“ in der Auswahl und öffnet die Online-Seite (dafür unter
Zahnrad › Push den Link der Online-Seite eintragen). Kein Rechner liest die Datenbank eines anderen.
