# Projekt-Auswahl: mehrere Projekte, auch auf mehreren Rechnern (universal)

Stand 06.11.2026. Anlass: Der Entwickler will weitere, unabhängige Projekte genauso über die AMW führen, auch wenn ihre
Agenten auf einem anderen Rechner arbeiten. Die Workbench ist **Übersicht und Dirigent**. Sie fasst alle Projekte
zusammen und lässt eines auswählen.
- **Umschalten ändert nur die Ansicht.** Kein Projekt wird angehalten.
- Jedes Projekt hat seine Agenten, seine Datenbank und sein Wecksystem und läuft unabhängig weiter.
- Alles, was online beim Hoster liegt, ist einem Projekt zugeordnet.

Status: **freigegeben (Variante A, Schema-Änderung erlaubt), Ausbau auf mehrere Rechner ergänzt.** Release 1 (Agenten,
Brücke, Push je Projekt, Schema 18) umgesetzt in AMW 1.17.0, Release 2 (Auswahl in der Workbench am PC) in 1.18.0, Release 3 (online je Projekt,
mehrere Rechner) in 1.19.0.
Mockup: [plan-projektwahl-mockup.html](plan-projektwahl-mockup.html).

## Ziel und Abnahme

1. Die Auswahl sitzt oben in der Navigation, am Handy als Chip im Kopf. Sie listet **alle** Projekte: die dieses
   Rechners und die anderer Rechner (über den Online-Speicher), jeweils mit Rechner, Zustand und offenen Fragen an den
   Entwickler. Ein Wechsel lädt die Seite neu.
2. Danach zeigt jede Ansicht nur das gewählte Projekt: Start, Fragen, Planung, Aufgaben, Verlauf, Releases, Wissen,
   Dokumente, Betrieb, Einstellungen, Suche, Zähler und „Seit du weg warst“. Das gilt am PC und online gleich.
3. Jeder Knopf und jede Aktion wirkt nur im gewählten Projekt, auch Befehle vom Handy. Ein Befehl für ein Projekt auf
   einem anderen Rechner wird nur von **diesem** Rechner ausgeführt.
4. Teile, die zu einem Rechner gehören (lokale KIs, Schirm, GPU-/Schirm-Platz, Dienst, Speicher, Push-Kanäle), tragen
   die Marke „dieser PC“ bzw. den Namen des Rechners.
5. Jedes Projekt weckt und überwacht nur seine eigenen Agenten. Ein Halt gilt nur für das Projekt, in dem man ihn
   drückt.
6. Online trägt jeder Eintrag die Projekt-Kennung (`projekt.uid`): Ansichten, Befehle vom Handy, Uploads, Dateien,
   Gespräche, Suchindex und Zustand. Ein Rechner überschreibt oder löscht nie Daten eines Projekts, das ihm nicht
   gehört.
7. Mit nur einem Projekt ändert sich für Agenten und Befehle nichts.
8. Keine projektbezogenen Begriffe in der Oberfläche. Die Tests laufen mit zwei Projekten in einer Datenbank und mit zwei
   Datenbanken als zwei Rechnern an einem gemeinsamen Online-Speicher.

## Aufbau

```
 Rechner 1 (AMW + amw.db)            Rechner 2 (AMW + amw.db)
   Projekt A  ─ Agenten, Wächter       Projekt C ─ Agenten, Wächter
   Projekt B  ─ Agenten                    │
        │  Abgleich (nur eigene Projekte)  │  Abgleich (nur eigene Projekte)
        └──────────────► Online-Speicher ◄─┘
                    Verzeichnis aller Projekte, Ansichten je Projekt,
                    Befehle je Projekt → nur der Rechner des Projekts führt sie aus
        Workbench am PC: eigene Projekte direkt, fremde über die Online-Seite
        Online-Seite / Handy: alle Projekte
```

- **Eine AMW-Installation je Rechner** mit ihrer lokalen SQLite-Datenbank, ihrem Wächter und ihren Agenten. Ein Projekt
  lebt auf genau einem Rechner.
- **Mehrere Projekte auf demselben Rechner** liegen getrennt nach Projekt in dessen Datenbank. Jede Tabelle trägt das
  Projekt, und der Wächter weckt je Projekt. Warum keine eigene Datenbank je Projekt auf demselben Rechner?
  - Grafikkarte, Schirm und lokale KIs gibt es nur einmal. Die Lauf-Schlange muss sie über alle Projekte des Rechners
    verteilen, sonst rechnen zwei Projekte gleichzeitig auf derselben Karte.
  - Wer es trotzdem strikt getrennt will, legt eine zweite Installation an (eigener Ordner, eigener Port). Das geht
    schon heute, dann aber ohne gemeinsame GPU-Schlange.
- **Die Projekt-Kennung** online ist `projekt.uid` (zufällig, weltweit eindeutig). Die laufende Nummer `projekt.id` ist
  je Datenbank und kann sich auf zwei Rechnern überschneiden.
- **Rechner-Name:** Einstellung dieses PCs (Standard: Name des Computers). Er erscheint in der Projektliste.

## Bestandsaufnahme (was heute nur ein Projekt kennt)

Der Wächter arbeitet schon je Projekt: Takt, Warteschlange, Termine, Eskalation, Überwachung und Neustarter laufen über
alle Projekte. Nur ein Projekt kennen dagegen:

| Teil | heute | Folge mit einem zweiten Projekt |
|---|---|---|
| Workbench-Server | `?projekt=` geht, Standard ist das erste Projekt | die Oberfläche schickt nie `projekt=` → immer Projekt 1 |
| Oberfläche | keine Auswahl; `localStorage` (Sicht, letzter Besuch) nicht je Projekt | – |
| Online-Abgleich | eine Instanz für das erste Projekt; Ansichten unter `/api/start` ohne Projekt; `eingang` ohne Projekt; löscht online alle Dateien, die es nicht kennt | Projekt 2 nicht online; Handy-Befehle landen in Projekt 1; ein zweiter Rechner würde die Daten des ersten überschreiben und dessen Dateien löschen |
| Push | Warteschlange `push_versand` ohne Projekt; eine Runde je Projekt hält die Einträge des anderen für „erledigt“ | **Push von Projekt 2 geht verloren**; gleiche Schlüssel (`rueckblick:<Datum>`) schlucken sich |
| CLI der Agenten | Projekt aus `--projekt`/`AMW_PROJEKT`, sonst „genau eins“ | **jeder Agenten-Befehl scheitert**, sobald ein zweites Projekt angelegt ist |
| Brücke | ohne `--projekt` | jeder Befehl scheitert („mehrere Projekte“) |
| Hook/Einrichtung | Standard erstes Projekt | Sitzungen landen ohne Angabe in Projekt 1 |
| Verbrauch | Zuordnung über die Kennung | gleiche Kennung in zwei Projekten zählt doppelt |

## Entwurf

### A. Projekt der Agenten (Grundlage, zuerst)
- **CLI:** Fehlt `--projekt`/`AMW_PROJEKT`, nimmt die AMW das Projekt aus der Kennung (`--von`), wenn es sie in genau
  einem Projekt gibt. Ist die Kennung mehrdeutig, schlägt der Befehl fehl und nennt die Projekte. Mit einem Projekt
  ändert sich nichts.
- **Einrichtung:** `amw einrichten agenten-ordner` schreibt `AMW_PROJEKT` in die Umgebung des Agenten-Ordners (wie heute
  `AMW_AGENT`). Der Hook meldet die Sitzung im richtigen Projekt an.
- **Brücke:** Befehlsdateien dürfen `"projekt": "<name>"` tragen; ohne Angabe gilt das Projekt, in dem die Kennung des
  Leads liegt (bei mehreren: Fehler mit Hinweis).
- **Verbrauch:** über `sitzung → agent` zuordnen statt über die Kennung.

### B. Push je Projekt
- Jede Meldung gehört zu einem Projekt; eine Runde sieht nur die eigenen. Schlüssel sind je Projekt eindeutig.
- Bei mehr als einem Projekt steht der Projektname im Titel („Webshop · Frage F48 …“). Der Link öffnet
  `?projekt=<uid>#fragen`.
- Ruhezeit, Höchstzahl je Stunde und Kanäle bleiben Einstellungen des Rechners. Jeder Rechner verschickt die Meldungen
  seiner Projekte selbst.

### C. Workbench am PC
- **Auswahl:** oben in der Navigation unter der Marke (Variante A). Sie zeigt Name, Farbe, Rechner und offene Fragen je
  Projekt. Am Handy steht sie als Chip im Kopf und öffnet ein Blatt von unten. Bei zugeklappter Navigation wandert sie in
  den Kopf.
- **Projekte dieses Rechners** öffnet die Workbench direkt aus der Datenbank. **Projekte anderer Rechner** stehen in
  derselben Liste mit dem Rechnernamen und öffnen die Online-Seite dieses Projekts. Darüber lassen sie sich auch
  dirigieren: Befehle gehen an den Rechner des Projekts.
- **Merken:** im Browser (`localStorage`) und in der Adresse (`?projekt=<uid>`), damit ein Link oder Push genau dieses
  Projekt öffnet. Sicht und letzter Besuch werden je Projekt gemerkt.
- **Jede Anfrage** trägt das Projekt. Das geschieht an einer Stelle (`ziel()`), nicht in jeder Ansicht.
- **Farbe** je Projekt, als Einstellung im Projekt (`projekt.einstellungen`). Sie erscheint als dünner Streifen über
  dem Kopf.
- **„dieser PC“:** Diese Marke tragen Lokale KI, Schirm, Dieser PC, Online-Speicher und Push-Kanäle. Die Signale im
  Kopf (Dienst, Speicher, Schirm) bekommen ein kleines „PC“. Läufe anderer Projekte desselben Rechners, die die
  Grafikkarte oder den Schirm belegen, stehen grau mit dem Projektnamen in der Lauf-Liste, ohne Titel.
- **HALT** bleibt, wie er ist. Er gilt für das Projekt, in dem man ihn drückt.
- **Einstellungen:** „Aktives Projekt“ wird zur echten Auswahl, dazu kommen Farbe und Rechner-Name. Die Speichergrenze
  bleibt je Projekt, denn sie gilt für die Läufe des Projekts.
- **Arbeitsregeln (KR)** gelten wie bisher für alle Projekte einer AMW, Projektregeln (PR) je Projekt. Ob ein zweites
  Projekt auf demselben Rechner eigene Arbeitsregeln braucht, entscheidet der Entwickler.

### D. Online-Speicher und Online-Seite
- **Verzeichnis** `projekt` (online): Kennung, Name, Farbe, Rechner, zuletzt gesehen, offene Fragen, Halt. Jeder
  Rechner trägt nur seine eigenen Projekte ein. Ein Projekt, das ein Rechner länger als 7 Tage nicht meldet, steht als
  „nicht erreichbar“ in der Liste und wird nicht gelöscht.
- **Ansichten** liegen unter `<uid>:/api/start` usw. Gespräche, Suchindex und Zustand (`pc_gesehen_utc` …) sind je
  Projekt bzw. je Rechner getrennt.
- **Befehle vom Handy** (`eingang`) und **Uploads** (`hoch`) tragen die Projekt-Kennung. Ein Rechner holt nur Befehle
  seiner Projekte ab. Ein Befehl für ein unbekanntes Projekt bleibt liegen und wird nicht falsch ausgeführt.
- **Dateien** gehen nach Inhalt (sha) und können in mehreren Projekten vorkommen. Ein Rechner löscht eine Datei nur,
  wenn kein Projekt sie mehr nennt (Zuordnung `datei_projekt`).
- `api.php` nimmt `projekt` mit, liefert das Verzeichnis und prüft jede Anfrage gegen das Verzeichnis. Anmeldung und
  Sitzung gelten für alle Projekte.
- **Übergang:** Alte Schlüssel ohne Projekt gelten für das bisherige Projekt, bis der erste Abgleich mit Kennung durch
  ist. So gibt es keine leere Seite beim Umstieg.

### E. Zweiter Rechner
- Anleitung in `doc/installation.md`: AMW installieren, Projekt anlegen, denselben Online-Speicher eintragen und
  einen eigenen Rechner-Namen vergeben.
- Kein Rechner braucht Zugriff auf die Datenbank eines anderen. Sie begegnen sich nur im Online-Speicher.

## Datenbank

- **amw.db (Schema 18):** `push_versand.projekt_id`. Vorhandene Einträge gehören zum bisherigen Projekt.
- **Online-Speicher:** neue Tabelle `projekt` (Verzeichnis) und `datei_projekt`. Spalte `projekt` an `eingang` und
  `hoch`. Ansichten bekommen die Kennung im Schlüssel. Der Abgleich legt das selbst an, wie bisher bei neuen Spalten.
- Alles andere in amw.db trägt das Projekt schon (oder erbt es) oder gehört bewusst zum Rechner (`schirm`, `ki`,
  `ki_modell`, `ki_vorlage`).

## Ablauf und Aufwand

| Schritt | Inhalt | Zeit | live |
|---|---|---|---|
| 1 | A: CLI, Einrichtung, Hook, Brücke, Verbrauch | 1,5 h | Release 1 |
| 2 | B: Push je Projekt (Schema 18, Sicherung vorher) | 1 h | Release 1 |
| 3 | C: Auswahl in der Workbench, Anfragen, Merken, Marken, Einstellungen, Handy | 2,5 h | Release 2 |
| 4 | D: Online-Verzeichnis, Kennung an allen Online-Daten, Befehle/Uploads je Projekt, Dateien je Projekt, Übergang | 3,5 h | Release 3 |
| 5 | C+E: fremde Projekte in der Auswahl, Rechner-Name, Anleitung zweiter Rechner | 1,5 h | Release 3 |
| 6 | Durchgang (zwei Projekte; zwei Datenbanken an einem Online-Speicher), Fotos PC/Handy, Doku | 2 h | je Release |

Zusammen etwa 12 h. Die Releases gehen einzeln live: 1 am Vormittag, 2 am frühen Nachmittag, 3 am Abend oder spätestens
Samstagvormittag. Laufende Arbeit im bestehenden Projekt bleibt unberührt.

## Geklärt (Entwickler, 06.11.)

- Variante A, Schema-Änderung freigegeben.
- Umschalten ändert nur die Ansicht. Nichts wird angehalten, Agenten und Datenbank arbeiten weiter.
- Projekte können auf anderen Rechnern laufen, mit eigenen Agenten und eigener lokaler Datenbank. Die Workbench fasst sie
  zusammen. Online ist alles einem Projekt zugeordnet. Das Wecksystem ist je Projekt getrennt.
