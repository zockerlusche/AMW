# Plan: Dokumente – Ausarbeitungen, Bilder und Mockups an einem Ort

Stand 02.11.2026 · **freigegeben** · Umsetzung in drei Stufen (je eine Version), danach Gesprächsansicht je Agent

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

## 4b Einsammeln vorhandener Ergebnisse
Nichts wird automatisch übernommen. `amw dokument einsammeln <ordner> --nur-liste` erstellt je Ablage eine Liste: Ordner,
Anzahl, Größe, Zeitraum, Vorschlag behalten/weg und Grund, z. B. „Prüflauf-Einzelbilder“ oder „Arbeitskopie“. Sie geht an
Lead und Mensch. Übernommen wird erst nach Freigabe, und nur Ergebnisse; Arbeitskopien und Code bleiben in ihren Ordnern.

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
| D1 · am PC | Schema 9, Ablage, `amw dokument …`, Standard im Pflicht-Kontext, Workbench-Bereich mit Vorschau, Bezüge an Bogen/Schritt/Frage, Suche, Kommentar → Nachricht, Tests, UI-Prüfung | ~1 Tag |
| D2 · online | Metadaten/Text über Turso, Upload-Endpunkt und Dateiausgabe beim Hoster, Online-Ansicht, Aktionen über den Briefkasten | ~1 Tag |
| D3 · Komfort | Berichtigen im Browser mit Versionsvergleich, Upload vom Handy (Foto → Dokument), vorhandene Dateien einsammeln (`amw dokument einsammeln <ordner>` mit Vorschlag zur Zuordnung), Mockup-Varianten in Fragen | ~1 Tag |

## 7 Entscheidungen (02.11.2026)
1. Plan und Schema 9 freigegeben, vorher Sicherung, Stufen D1–D3.
2. Dateien auf dem Webspace des Hosters, online nur bei Bedarf; Turso für Liste, Metadaten und Text (§4a).
3. Markdown als Standard; vor dem Einsammeln je Ablage eine Liste zur Freigabe (§4b), nichts automatisch.
4. Gesprächsansicht je Agent und „In Claude öffnen“ einplanen (nach D1/D2).
