# Plan 1.11.0 – Federführung, Abnahme-Kette, Läufe aus einer Hand

Herkunft: Gespräch Lead ↔ AMW-Agent am 04.11. Der Entwickler hatte darum gebeten, die Frage „Leads, denen Agenten
zugeordnet sind“ mit Argumenten durchzusprechen. Dazu kam ein Wunsch des Prüf-Agenten aus dem Betrieb.

## Ausgangslage

- **Lead als Flaschenhals:** An einem Abend warteten Abnahmen und Merge-OKs je 20–60 min auf den Lead. Nachts läuft der
  Lead nur im Stundentakt.
- **Feste Leiter (Gruppenleiter über Agenten) verworfen:** eine Stufe mehr, und jeder Leiter braucht dauerhaft eigenen
  Kontext. „Lead ad hoc“ hatte der Entwickler verwirrend gefunden, die Struktur soll man an den Namen erkennen.
- **Gewählt: Federführung je Bogen bzw. Aufgabe.** Sie wechselt mit der Arbeit und ist an jeder Stelle sichtbar.

## A. Federführung (Schema 14)

- Neue Spalte `federfuehrend` an `bogen` und an `aufgabe`. Setzen dürfen nur Lead und Entwickler:
  `amw bogen aendern N --federfuehrend CCengine`, `amw aufgabe aendern N --federfuehrend …`. Leer nimmt sie weg.
- **Zuständig für eine Aufgabe:** ihre Federführung, sonst die ihres Bogens, sonst der Lead.
- **Empfänger `zustaendig`:** `amw posten --an zustaendig --aufgabe N …` und `amw frage neu --an zustaendig --aufgabe N`
  gehen an den Zuständigen. So schreiben Agenten Prüfergebnisse, Merge-Bitten und Fragen zum Bogen, ohne zu wissen, wer
  gerade führt.
- **Ergebnis einer Prüfung** (`pruefung gruen|rot`) geht an den Bauer und in Kopie an den Zuständigen. Ist das nicht der
  Lead, bekommt der Lead nichts. Abschluss und Abweichungen meldet der Federführende.
- **Eskalation:** Bleibt eine Frage, Prüfbitte oder ein Auftrag an einen Federführenden 30 min ungelesen
  (Projekt-Einstellung `eskalation_min`, 0 = aus), bekommt der Lead einmal eine weckende Zeile.
- **Sichtbar:**
  - Pflicht-Kontext: „Du führst: Bogen 3 (…), A1250“.
  - Workbench: am Bogen und an der Aufgabe „federführend: X“; auf der Kachel des Agenten „führt B3“.
  - Online genauso.
- **Bleibt beim Lead:** Zuschnitt der Bögen, alles, was der Entwickler entscheidet (Fragen an ihn, Werte, Freigaben),
  Querschnitt zwischen Bögen, main und Push.

## B. Abnahme-Kette (Projekt-Einstellung, Vorgabe aus)

- Einstellungen `merge_dienst` (Kennung, z. B. der Engine-Agent) und `abnahme_kette` (aus | an).
- Bei „an“: Eine grüne Prüfung mit Aufgabe schickt von selbst eine Merge-Bitte (auftrag) an den Merge-Dienst, mit Zweig,
  Stand, Prüfung und Bauer. Der Zuständige bekommt eine Kopie. Fehlt die Federführung, gibt wie bisher der Lead das OK.
- Der Merge-Dienst meldet sein Ergebnis mit `--aufgabe`. Über die Kopie an den Besitzer erfahren es alle Beteiligten.
- **Zu entscheiden (Lead bzw. Entwickler):** Ob das OK des Federführenden das OK des Leads vor dem Merge ersetzen darf, ist
  eine Regel des Projekts, keine Technik. Deshalb steht die Kette auf „aus“, bis der Lead sie einschaltet.

## C. `amw lauf ausfuehren` (Wunsch des Prüf-Agenten)

```
amw lauf ausfuehren --beschreibung "…" [--schirm] [--schwer] [--aufgabe N] [--dauer MIN] [--ergebnis DATEI] -- <befehl …>
```

Der Befehl macht in einem Schritt:
1. Lauf einreihen und warten, bis er dran ist, mit einer Zeile je Minute.
2. Den Befehl starten. Seine Ausgabe geht in die Ergebnis-Datei und auf den Bildschirm.
3. Den Rückgabewert durchreichen und `lauf ende` mit rc und Ergebnis melden.
4. Beim Schirm-Lauf alle 5 s nachsehen: Geht der Schirm zu oder kommt „L… jetzt beenden“, beendet er den Prozessbaum des
   eigenen Befehls und meldet „abgebrochen“. Das tut der Prozess des Agenten selbst, nicht der Dienst. Der Grundsatz „die
   AMW beendet keine Prozesse“ bleibt damit gewahrt.
5. Strg+C beendet den Befehl ebenso und meldet „abgebrochen“.

Das ersetzt die eigenen Hüllen-Skripte der Agenten (einreihen → Nummer heraussuchen → warten → starten → Ende melden),
spart je Prüfung etwa 10 min und verhindert „Ende ohne Anmeldung“.

## Stand

A und C erscheinen mit 1.11.0. B (Abnahme-Kette) folgt, sobald der Lead die Regel „OK des Federführenden ersetzt das OK des
Leads vor dem Merge“ entschieden hat.

## Reihenfolge

Zuerst C (ohne Schema, sofort nützlich), dann A, dann B. Alle drei erscheinen als 1.11.0. Für Schema 14 wird vorher
`amw sichern` ausgeführt.
