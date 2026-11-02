# Plan: Dokumente – Ausarbeitungen, Bilder und Mockups an einem Ort

Stand 02.11.2026 · **freigegeben** · umgesetzt in drei Stufen (1.2.0, 1.3.0, 1.4.0), danach Gesprächsansicht je Agent

## 1 Problem
Agenten legen Ergebnisse irgendwo als Datei ab (txt, md, html, docx, png …). Der Mensch findet sie nicht, sieht nicht,
wozu sie gehören, kann nicht darauf reagieren, und unterwegs sieht er gar nichts. Bilder und Mockups landen im
Projektordner oder im Chat und sind danach verloren.

## 2 Ziel
Jedes Ergebnis eines Agenten liegt **in der AMW**: einem Bogen, Schritt, einer Frage oder einem Beschluss zugeordnet,
durchsuchbar, mit Vorschau am PC und am Handy, mit Versionen und einem Gesprächsfaden. Der Mensch kann kommentieren,
eine Überarbeitung anfordern, selbst berichtigen, neu zuordnen und archivieren.

Nicht-Ziele: kein allgemeiner Dateiserver, keine gemeinsame Bearbeitung in Echtzeit, keine Office-Vorschau im Browser.

## 3 Standard für Agenten (wird Pflicht-Kontext)
| Inhalt | Format | Vorschau |
|---|---|---|
| Text: Ausarbeitung, Bericht, Konzept, Entwurf | **Markdown (.md)** – das eine Textformat | gerendert, durchsuchbar, Versionsvergleich |
| Bild, Screenshot, Grafik | PNG, JPG, WebP, SVG | Bildansicht |
| Klick-Mockup | **eine** HTML-Datei ohne externe Abhängigkeiten | im abgeschotteten Rahmen (sandbox) |
| Fremde Unterlagen | PDF | Browser-Vorschau |
| Office | DOCX, XLSX | nur Download; Text von DOCX für die Suche |

Regel: **keine losen Ergebnisdateien** – `amw dokument ablegen <datei> --titel … --art ergebnis|bericht|entwurf|mockup|bild|quelle
--zu B3|A1234|F12|B2362`. Eine Überarbeitung ist eine neue Version: `amw dokument version <nr> <datei> --notiz …`.
Die AMW kopiert die Datei in ihre Ablage. Wo der Agent sie danach hat, ist egal.

## 4 Technik
- **PC ist die Quelle.** Dateien unter `daten/dokumente/<sha256>.<endung>` (gleicher Inhalt = eine Datei); `amw sichern`
  nimmt den Ordner mit.
- **Schema 9** (Migration, vorher Sicherung): `dokument` (Titel, Art, Bezug, Status aktuell|archiviert|geloescht, von,
  Zeiten), `dokument_version` (Nr, Datei-Hash, Format, Größe, Notiz, von, Zeit, Suchtext), Kommentare als Nachrichten
  mit Dokument-Bezug (wecken den Verfasser). Die bisher ungenutzte Tabelle `anhang` geht darin auf.
- **Schutz:** Formate nur aus der Liste, Größe bis 25 MB, Prüfung auf Geheimnisse (Schlüssel-Muster) vor dem Ablegen,
  HTML nur im abgeschotteten Rahmen (`sandbox="allow-scripts"`, ohne Zugriff auf die Seite), Dateien mit `nosniff`
  und ohne öffentliche Adresse.
- **Online – Preis/Leistung:**

| Weg | Kosten | Platz | Aufwand | Bewertung |
|---|---|---|---|---|
| Alles in Turso (Dateien als BLOB) | Free 0 $ mit 5 GB gesamt; Developer 4,99 $/Monat mit 9 GB | knapp, zählt zur Datenbank | klein | gut für Text, schlecht für Bilder: jede Datei läuft base64 über SQL-über-HTTP |
| **Turso für Liste und Text + Hostinger-Webspace für Dateien** | **0 € zusätzlich** (im Paket) | je nach Paket 50–200 GB | mittel | **Empfehlung** – Login und PHP gibt es schon |
| Cloudflare R2 | 10 GB frei, danach 0,015 $/GB-Monat, kein Traffic-Preis | beliebig | mittel–groß | gut, aber neues Konto und S3-Signaturen |
| GitHub | – | – | – | nein: Repo ist öffentlich |

  Empfohlen: Liste, Metadaten und Markdown-Text gehen wie heute über den Abgleich nach Turso (online durchsuchbar).
  Dateien schiebt der Wächter per HTTPS an einen Upload-Endpunkt beim Hoster (geheimer Schlüssel nur in
  `%LOCALAPPDATA%\amw`). Sie liegen dort **außerhalb** des Ordners, den das Git-Deploy überschreibt, und kommen nur nach
  dem Login über PHP heraus.

## 4a Bedarf und Speicherort
Grundlage: eine Messung der vorhandenen Ablagen im eigenen Projekt (nur gelesen). **Roh** liegt dort sehr viel, aber das
meiste ist Arbeitsmaterial und wird nicht übernommen: Arbeitskopien, Prüfläufe mit Tausenden Einzelbildern, entpackte
Daten. Echte Ergebnisse sind je Aufgabe typisch 1–20 MB, große Standbild-Läufe 70–150 MB.

| Szenario | je Tag | je Jahr |
|---|---|---|
| sparsam: nur ausgewählte Ergebnisse | ~10 MB | ~3,6 GB |
| mittel: alles aus den Ergebnis-Ablagen | ~50 MB | ~18 GB |
| hoch: viele große Standbild-Läufe | ~100 MB | ~36 GB |

**Online nur bei Bedarf** (Texte immer, Dateien nur ausgewählt, ≈ 10–20 %) senkt das auf wenige GB im Jahr.

**Turso:**
- Der Free-Tarif (5 GB, mit der Datenbank zusammen) wäre bei „alles online“ nach wenigen Monaten voll, bei Bedarf nach 1–2
  Jahren.
- Technisch läuft jede Datei als base64 (+33 %) durch SQL-über-HTTP und bei jedem Ansehen durch PHP, ohne Browser-Caching.

**Webspace beim Hoster:**
- Typisch 50–200 GB im Paket, ohne Zusatzkosten.
- PHP liefert direkt mit Caching aus, die Sicherungen des Pakets nehmen die Dateien mit.

**Entscheidung:** Turso für Liste, Metadaten und Text; Dateien auf dem Webspace, online nur bei Bedarf.

**Online bei Bedarf:**
- Texte (Markdown) sind immer online.
- Dateien sind online, wenn der Agent sie zur Ansicht ablegt (`--online`, z. B. Mockups für eine Frage) oder der Mensch sie
  am PC mit „online stellen“ freigibt.
- Unterwegs heißt es „anfordern“: Der Wächter lädt die Datei dann beim nächsten Abgleich hoch.
- „Offline nehmen“ löscht nur die Kopie beim Hoster.

**Umsetzung D2 (Abweichung vom Upload-Endpunkt):** Der PC schiebt eine Datei nicht direkt zum Hoster, sondern legt sie
in Teilen in Turso ab (`datei_teil`, je 256 KB). Die Seite holt sie beim nächsten Aufruf **einmal** ab, prüft Größe und
Prüfsumme, legt sie neben ihre Konfiguration und löscht die Teile; danach liefert PHP direkt vom Webspace mit
Browser-Cache. Gründe: Der PC braucht weder die Adresse der Seite noch einen zweiten Schlüssel, beim Hoster muss niemand
etwas von Hand ablegen, und es gibt keinen weiteren Endpunkt, der von außen Dateien annimmt. Turso trägt eine Datei nur
kurz (Base64 einmal, nicht bei jedem Ansehen); das Gegenargument aus der Tabelle oben gilt damit nicht.

## 4b Einsammeln vorhandener Ergebnisse
Nichts wird automatisch übernommen. `amw dokument einsammeln <ordner> --nur-liste` erstellt je Ablage eine Liste: Ordner,
Anzahl, Größe, Zeitraum, Vorschlag behalten/weg und Grund, z. B. „Prüflauf-Einzelbilder“ oder „Arbeitskopie“. Sie geht an
Lead und Mensch. Übernommen wird erst nach Freigabe, und nur Ergebnisse; Arbeitskopien und Code bleiben in ihren Ordnern.

## 4c Entwurf D3 (Komfort)
Vorbild und Recherche: Web-Editoren von GitHub/GitLab (Bearbeiten mit Vorschau-Reiter, Commit-Notiz, Konflikt bei
zwischenzeitlicher Änderung), Versionsvergleich als Zeilen-Diff mit hervorgehobenen Wörtern; Datei-Uploads am Handy wie
Nextcloud/Google Drive (Kamera direkt, Bild vor dem Senden verkleinert, Upload in Teilen, damit ein Funkloch nicht alles
verwirft); Abstimmungen mit Bildern (Figma/Miro „Variante A/B“).

**Selbst berichtigen** (Markdown/Text, am PC und online):
- *Bearbeiten* im Dokument öffnet den Text der gezeigten Version mit Vorschau-Umschalter und Feld „Was hast du geändert?“.
- Speichern ergibt eine neue Version von „Entwickler“; der Verfasser bekommt eine Nachricht (abschaltbar).
- **Konflikt:** Gespeichert wird nur, wenn die bearbeitete Version noch die neueste ist (`basis`). Sonst bleibt der Text im
  Editor, die Meldung nennt die neue Version, und der Vergleich zeigt, was sich inzwischen geändert hat.
- Prüfungen wie beim Ablegen (Geheimnis-Muster, Größe); bis 400 000 Zeichen.

**Versionen vergleichen:** Bei zwei und mehr Versionen *Vergleichen* (vX ↔ vY). Texte: Zeilen-Diff (gelöscht/neu),
geänderte Zeilen mit hervorgehobenen Wörtern, unveränderte Abschnitte eingeklappt. Bilder, Mockups, PDF: beide Fassungen
nebeneinander (am Handy untereinander).

**Hochladen** (am PC und vom Handy):
- *Hochladen* im Bereich Dokumente und an Bogen/Aufgabe/Frage: Datei wählen, am Handy *Foto aufnehmen*, am PC auch
  hineinziehen oder ein Bildschirmfoto mit Strg+V einfügen.
- Fotos werden im Browser neu gerechnet: höchstens 2560 px (abschaltbar), JPEG – dabei fallen Standort und Kameradaten
  (EXIF) weg. GIF und SVG bleiben unverändert.
- Titel, Art und Bezug vorgeschlagen; vom Handy steht die Datei gleich auf „auch online“.
- **Weg:** in Teilen zu 192 KB (`/api/hochladen` start → teil … → `/api/dokument/neu`), Prüfsumme aus dem Browser.
  Am PC landen die Teile im Datenordner (`hoch/`). Online legt die Seite die Teile in den Speicher (`hoch`, `hoch_teil`)
  und zugleich in ihre Ablage; der PC holt sie über den Briefkasten, prüft Größe und Prüfsumme, legt das Dokument an und
  löscht die Teile. Die Kopie auf dem Webspace gilt gleich als abgelegt – nichts läuft doppelt.
- Grenzen: 25 MB je Datei, online höchstens 100 MB unterwegs; Liegengebliebenes räumt der PC nach einem Tag weg.

**Einsammeln** (§4b): `amw dokument einsammeln <ordner>` liest nur und gibt je Ablage (Ordner mit Dateien) aus: Anzahl,
Größe, Zeitraum, Vorschlag *behalten/weg* mit Grund (Prüflauf-Einzelbilder, Arbeitskopie, schon in der AMW, Format nicht
erlaubt) und je Datei einen Vorschlag für Art und Bezug (A…/B…/F… im Pfad). `--melden` legt die Liste als Dokument (Bericht)
ab und fragt den Menschen (Frage mit A = Vorschlag übernehmen, B = nichts); der Lead bekommt eine Info.
`--uebernehmen --frage F<nr>` übernimmt erst, wenn diese Frage mit A oder einem Text beantwortet ist, und nur die Dateien
der Liste, deren Inhalt sich nicht geändert hat (`--nur <unterordner>` grenzt ein). Keine Datei wird verschoben.

**Varianten in Fragen:** `amw frage neu … --option A=… --option B=… --anhang A=<datei|D-nr>` hängt je Option ein Bild oder
Mockup an (abgelegt als Dokument zur Frage, auch online). In der Frage stehen die Varianten als Karten mit Vorschau
nebeneinander; Vollbild blättert durch die Varianten, gewählt wird wie bisher per Klick. Gespeichert im Options-JSON
(`"dokument": <id>`), kein neues Feld.

**Lücken geprüft:** Konflikt beim Bearbeiten (basis), Datenschutz bei Fotos (EXIF), abgebrochene Uploads (Teile,
Aufräumen), Missbrauch online (Größen, Anmeldung, CSRF, Formatliste, Geheimnis-Prüfung am PC), Einsammeln ohne Freigabe
(Frage nötig), geänderte Dateien zwischen Liste und Übernahme (Prüfsumme), Bilder an Optionen online (immer „auch online“).

## 5 Bedienung
- **Neuer Bereich „Dokumente“** (unter Wissen):
  - Raster mit Vorschaubildern oder Liste.
  - Filter nach Art, Bogen, Agent, Zeitraum und Format; Suche im Text.
  - Markierung „neu seit deinem Besuch“.
- **Detailansicht:**
  - Vorschau groß; Markdown gerendert, Bild zoombar, Mockup klickbar.
  - Daneben: wozu es gehört, von wem, Versionen mit Vergleich, Gesprächsfaden.
  - Knöpfe: *Kommentieren* · *Überarbeiten lassen* (Auftrag an den Verfasser) · *Selbst berichtigen* (Markdown im
    Browser, ergibt eine neue Version) · *Zuordnen* · *Archivieren*. *Endgültig löschen* geht nur am PC.
- **Wo es auftaucht:**
  - an der Bogen-Karte („Dokumente 3“) und an Schritten (📎);
  - in Fragen als Anhang, auch Mockup-Varianten zur Auswahl („A oder B?“ mit Bild);
  - im Verlauf, in „Seit du weg warst“ und in der globalen Suche.
- **Handy:** gleiche Ansicht, Vorschau in voller Breite, Aktionen unten. Aktionen laufen wie heute über den Briefkasten.

## 6 Stufen und Aufwand (Arbeitszeit CCamw, grob)
| Stufe | Inhalt | Aufwand |
|---|---|---|
| D1 · am PC ✅ 1.2.0 | Schema 9, Ablage, `amw dokument …`, Standard im Pflicht-Kontext, Workbench-Bereich mit Vorschau, Bezüge an Bogen/Schritt/Frage, Suche, Kommentar → Nachricht, Tests, UI-Prüfung | ~1 Tag |
| D2 · online ✅ 1.3.0 | Metadaten/Text über Turso, Dateien zum Hoster (Durchreiche über Turso statt Upload-Endpunkt, siehe 4a), Dateiausgabe beim Hoster, Online-Ansicht, Aktionen über den Briefkasten | ~1 Tag |
| D3 · Komfort ✅ 1.4.0 | Berichtigen im Browser mit Versionsvergleich, Upload vom Handy (Foto → Dokument), vorhandene Dateien einsammeln (`amw dokument einsammeln <ordner>` mit Vorschlag zur Zuordnung), Mockup-Varianten in Fragen | ~1 Tag |

## 7 Entscheidungen (02.11.2026)
1. Plan und Schema 9 freigegeben, vorher Sicherung, Stufen D1–D3.
2. Dateien auf dem Webspace des Hosters, online nur bei Bedarf; Turso für Liste, Metadaten und Text (§4a).
3. Markdown als Standard; vor dem Einsammeln je Ablage eine Liste zur Freigabe (§4b), nichts automatisch.
4. Gesprächsansicht je Agent und „In Claude öffnen“ einplanen (nach D1/D2). ✅ 1.5.0 (siehe betrieb.md › Mitlesen).
