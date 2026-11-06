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
3. **Anlegen.** Die AMW legt Projekt, Lead und Agenten mit Profil an, richtet den Projektordner ein (Hooks, Statusline,
   Sperr-Regeln und die Projekt-Kennung `AMW_PROJEKT` in `.claude\settings.local.json`) und schreibt ein eigenes
   Startskript `agenten-start-<projekt>.ps1`. Das Startskript des ersten Projekts bleibt unverändert.
4. **Zum Projekt** wechseln › Start › Kachel eines Agenten › **Starten**. Im Tab steht „AMW: als CC1 angemeldet“.
5. Planung › Leitbild ausfüllen, Bögen anlegen ([Planung](anleitung-planung.md)); Regeln erst als Beschluss, dann als
   Regel ([Installation](installation.md), Abschnitt 5).

Ohne Workbench geht dasselbe mit `amw einrichten` (fragt bei einem weiteren Projekt auch nach der Regel-Kopie) oder
einzeln: `amw projekt neu <name> --ordner <pfad> [--regeln-von <Projekt>]`, dann `amw agent neu <kennung> --projekt
<name> --von Entwickler` (bekommt den Projektordner als Profil) und `amw einrichten agenten-ordner <pfad> --projekt <name>`.

## Woher ein Agent weiß, wohin er gehört

- **Startbefehl** (Kachel „Starten“ oder Startskript) setzt `AMW_AGENT` (Kennung) und `AMW_PROJEKT` (Projekt).
- **Projektordner**: `AMW_PROJEKT` steht auch in `.claude\settings.local.json` – Claude Code setzt es jeder Sitzung dort,
  auch wenn du sie von Hand startest.
- **Beim Start** meldet der Hook die Sitzung im Projekt an und gibt den Pflicht-Kontext dieses Projekts: Befehl und
  Kurzanleitung, Aufgaben, Nachrichten, Leitbild, Regeln. Ist das Projekt nicht erkennbar und gibt es die Kennung in
  mehreren Projekten, meldet er die Sitzung **nicht** an und sagt im Fenster, was zu tun ist – nie im falschen Projekt.
- `amw` findet die Datenbank selbst; ein Agent nennt nie ein fremdes Projekt (`--projekt` mit einem Projekt, in dem es
  seine Kennung nicht gibt, lehnt die AMW ab).

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
