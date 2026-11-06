# Projekt-Auswahl: mehrere Projekte in einer AMW (universal)

Stand 06.11.2026. Anlass: Der Entwickler will ein zweites, unabhängiges Projekt genauso über die AMW führen. Dafür braucht
es eine zentrale Projekt-Auswahl. Nach dem Wechsel zeigt die ganze Oberfläche nur noch das gewählte Projekt. Was für den
ganzen PC gilt, ist als „alle Projekte“ gekennzeichnet.
Status: **Entwurf, wartet auf Freigabe.** Mockup: [plan-projektwahl-mockup.html](plan-projektwahl-mockup.html).

## Ziel und Abnahme

1. Die Auswahl sitzt oben in der Navigation, am Handy als Chip im Kopf. Ein Wechsel lädt die Seite neu, danach zeigt
   jede Ansicht nur das gewählte Projekt: Start, Fragen, Planung, Aufgaben, Verlauf, Releases, Wissen, Dokumente,
   Betrieb, Einstellungen, Suche, Zähler, „Seit du weg warst“. Am PC und online gleich.
2. Jeder Knopf und jede Aktion wirkt nur im gewählten Projekt, auch Befehle vom Handy.
3. PC-weite Teile tragen die Marke „alle Projekte“. Das sind lokale KIs, Schirm, GPU-/Schirm-Platz der Lauf-Schlange,
   Dienst, Speicher, „Dieser PC“, Online-Speicher, Push-Kanäle und die Online-Anmeldung. Belegt ein Lauf des anderen
   Projekts die Grafikkarte, sieht man das mit Projektnamen, aber ohne dessen Inhalte.
4. Die Liste der Projekte zeigt je Projekt die offenen Fragen an den Entwickler, damit man nicht wechseln muss, um zu
   sehen, ob drüben etwas wartet. Push-Meldungen nennen das Projekt, sobald es mehr als eins gibt, und ihr Link öffnet
   das richtige Projekt.
5. Mit nur einem Projekt ändert sich nichts außer der Anzeige des Namens. Kein Agent und kein Befehl muss angepasst
   werden.
6. Keine projektbezogenen Begriffe in der Oberfläche; die Tests laufen mit zwei Demo-Projekten.

## Bestandsaufnahme (was heute nur ein Projekt kennt)

Der Wächter arbeitet schon je Projekt: Takt, Warteschlange, Termine, Eskalation, Überwachung und Neustarter laufen über
alle Projekte. Nur ein Projekt kennen dagegen:

| Teil | heute | Folge mit zwei Projekten |
|---|---|---|
| Workbench-Server | `?projekt=` geht, Standard ist das erste Projekt | die Oberfläche schickt nie `projekt=` → immer Projekt 1 |
| Oberfläche | keine Auswahl; `localStorage` (Sicht, letzter Besuch) nicht je Projekt | – |
| Online-Abgleich | eine Instanz für das erste Projekt; Ansichten unter `/api/start` ohne Projekt; `eingang` ohne Projekt; Dateien des anderen Projekts würden gelöscht | Projekt 2 nicht online; Handy-Befehle landen in Projekt 1 |
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

### B. Workbench am PC
- **Auswahl:** oben in der Navigation unter der Marke (Mockup Variante A, Begründung dort), mit Name, Farbe und
  offenen Fragen je Projekt. Am Handy als Chip im Kopf mit einem Blatt von unten. Bei zugeklappter Navigation
  (schmale Fenster) wandert die Auswahl in den Kopf.
- **Merken:** im Browser (`localStorage`) und in der Adresse (`?projekt=<name>`), damit ein Link oder Push genau dieses
  Projekt öffnet. Beim Wechsel wird neu geladen. Sicht und letzter Besuch werden je Projekt gemerkt.
- **Jede Anfrage** trägt das Projekt: eine Stelle in `holen`/`schicken` (`ziel()`), keine Änderung je Ansicht.
- **Farbe** je Projekt: Einstellung im Projekt (`projekt.einstellungen`, wie `entwickler_name`), wählbar unter
  Einstellungen → Projekt. Als dünner Streifen über dem Kopf.
- **„alle Projekte“:** Marke an Lokale KI, Schirm, Dieser PC, Online-Speicher, Push-Kanälen. Die Signale im Kopf
  (Dienst, Speicher, Schirm) bekommen ein kleines „PC“. In der Lauf-Liste stehen fremde GPU-/Schirm-Läufe grau mit dem
  Projektnamen, ohne Titel.
- **HALT** gilt wie heute für das gewählte Projekt. Neu im Halt-Fenster: „alle Projekte anhalten“ (siehe Frage).
- **Einstellungen:** „Aktives Projekt“ wird zur echten Auswahl. Speichergrenze, Dienst und Push sind als PC-Einstellung
  gekennzeichnet; die Speichergrenze zieht von „Projekt“ zu „Dieser PC“ um.

### C. Online-Seite
- Der Abgleich läuft für jedes Projekt: Ansichten unter `p<id>:/api/start`, Dateien, Gespräche und Suchindex je
  Projekt. Gelöscht wird nur, was zu keinem Projekt mehr gehört.
- `api.php` nimmt `projekt` mit und gibt es an `eingang` weiter. Der PC führt jeden Handy-Befehl im genannten Projekt
  aus, und zwar nur, wenn das Projekt existiert.
- Die Online-Seite bekommt dieselbe Auswahl; Anmeldung und Sitzung bleiben für alle Projekte gleich.
- Übergang: Die alten Schlüssel ohne Projekt gelten für das erste Projekt, bis der erste Abgleich mit Projekten
  durch ist. So gibt es keine leere Seite beim Umstieg.

### D. Push
- Jede Meldung gehört zu einem Projekt; eine Runde sieht nur die eigenen. Schlüssel sind je Projekt eindeutig.
- Bei mehr als einem Projekt steht der Projektname im Titel („Webshop · Frage F48 …“), und der Link öffnet
  `?projekt=…#fragen`.
- Ruhezeit, Höchstzahl je Stunde und Kanäle bleiben PC-weit.

## Datenbank

- **amw.db:** `push_versand` bekommt `projekt_id`. Das wäre Schema 18; vorhandene Einträge gehören zum ersten
  Projekt. Ohne Schema-Änderung ginge es auch mit einem Präfix im Schlüssel. Das ist unsauberer und braucht eine
  Sonderregel für Altbestände.
- Alles andere trägt das Projekt schon (oder erbt es) oder gilt bewusst für den PC (`schirm`, `ki`, `ki_modell`,
  `ki_vorlage`).
- **Online-Speicher:** `eingang` bekommt die Spalte `projekt`, die Ansichten bekommen das Projekt im Schlüssel. Das
  legt der Abgleich selbst an, wie bisher bei neuen Spalten.

## Ablauf und Aufwand

| Schritt | Inhalt | Zeit |
|---|---|---|
| 1 | A: CLI, Einrichtung, Hook, Brücke, Verbrauch + Tests mit zwei Projekten | 1,5 h |
| 2 | D: Push je Projekt (Schema 18, Sicherung vorher) | 1 h |
| 3 | B: Auswahl, Anfragen, Merken, Marken, Einstellungen, Handy | 2,5 h |
| 4 | C: Abgleich und api.php je Projekt, Übergang | 2,5 h |
| 5 | Durchgang mit Demo-DB (zwei Projekte), Fotos PC/Handy, Doku, Release | 1,5 h |

Zusammen etwa 9 h. Zwischenstände gehen einzeln live (erst A+D, dann B, dann C). Laufende Arbeit im bestehenden Projekt
bleibt unberührt, weil es bis zum zweiten Projekt nur eines gibt.

## Offene Fragen an den Entwickler

1. **Was heißt „immer nur ein Projekt aktiv“?** Empfehlung: Es geht um die Anzeige. Die Agenten beider Projekte
   arbeiten weiter und teilen sich Grafikkarte und Schirm über die Schlange. Die Alternative wäre: Der Wechsel hält
   das andere Projekt an.
2. **HALT:** Empfehlung: wie heute nur das gewählte Projekt, dazu im Halt-Fenster die Wahl „alle Projekte“.
3. **Schema 18** (`push_versand.projekt_id`) – ja? Empfehlung: ja.
4. **Auswahl oben in der Navigation** (Variante A) oder im Kopf (B)? Empfehlung: A.
