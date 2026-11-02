# Anleitung: Dokumente – Ergebnisse, Bilder und Mockups

Agenten legen jedes Ergebnis **in der AMW** ab statt irgendwo als Datei: einer Ausarbeitung, einem Bericht, einem
Standbild oder einem Klick-Mockup. Du findest es in der Workbench unter **Dokumente** mit Vorschau, wozu es gehört, allen
Versionen und dem Gespräch dazu. Plan und Hintergrund: [plan-dokumente.md](plan-dokumente.md).

## 1 Standard für Agenten
| Inhalt | Format |
|---|---|
| Text: Ausarbeitung, Bericht, Konzept, Entwurf | **Markdown (.md)** |
| Bild, Screenshot, Grafik | PNG, JPG, WebP, GIF, SVG |
| Klick-Mockup | **eine** HTML-Datei ohne externe Abhängigkeiten (Bilder als data:-URL) |
| Unterlagen von außen | PDF, DOCX, XLSX |

Agenten legen keine losen Ergebnisdateien mehr an. Wie man ablegt, steht in ihrem Pflicht-Kontext:

```
amw dokument ablegen bericht.md --titel "Prüfbericht Lauf 29" --art bericht --aufgabe 1230
amw dokument ablegen variante-b.html --art mockup --frage 5138     # z. B. als Anhang zu einer Frage an dich
amw dokument version 12 bericht-v2.md --notiz "Speicherwarnung erklärt"
amw frage neu --an entwickler --kurz "Welche Kopfleiste?" --option A=oben --option B=unten --empfehlung A --grund "…" \
  --anhang A=oben.png --anhang B=D12        # Varianten: je Option ein Bild oder Mockup (Datei oder vorhandenes Dokument)
```

- **Arten:** `ergebnis`, `bericht`, `entwurf`, `mockup`, `bild`, `quelle`.
- **Bezug** (höchstens einer): `--bogen`, `--aufgabe`, `--frage` oder `--beschluss` mit Nummer.
- **Die AMW kopiert die Datei** in ihre Ablage. Was der Agent danach mit seiner Datei macht, ist egal. Arbeitskopien und
  Code bleiben in ihren Ordnern.
- **Abgewiesen wird:** ein Format, das nicht in der Liste steht, eine Datei über 25 MB und eine Datei, die wie ein Schlüssel
  oder Zugangsdaten aussieht.

## 2 In der Workbench
- **Dokumente:**
  - Raster mit Vorschaubildern oder Liste.
  - Suche in Titel und Text, auch in älteren Versionen und in DOCX.
  - Filter nach Art, Agent, Bogen, und ob ein Dokument aktuell oder archiviert ist.
- **Detail:**
  - Links die Vorschau: Markdown gerendert, Bild, Mockup klickbar, PDF. Office-Dateien nur zum Herunterladen.
  - **Vollbild:** Ein Klick aufs Bild oder auf *Vollbild* öffnet es bildschirmfüllend. Mausrad oder zwei Finger zoomen
    an der Stelle, Ziehen verschiebt, Doppelklick oder Doppeltippen wechselt zwischen 1:1 und eingepasst. Mit
    ←/→ blätterst du durch die Bilder derselben Aufgabe oder desselben Bogens, Esc schließt. Tasten: `+` `−` `0`
    (einpassen) `1` (1:1). Mockups und PDF gehen ebenfalls ins Vollbild.
  - Rechts: wozu es gehört, alle Versionen (anklicken zeigt die alte Fassung) und das Gespräch.
- **Reagieren:**
  - *Kommentieren* oder *Überarbeiten lassen*: geht als Nachricht an den Verfasser und weckt ihn. Er legt eine neue Version
    ab.
  - *Zuordnen* ändert Titel, Art und Bezug. *Archivieren* blendet ein Dokument aus, *Wiederherstellen* holt es zurück.
  - *Endgültig löschen* geht nur am PC. Es entfernt die Dateien, der Eintrag bleibt als „gelöscht“ im Verlauf.
  - **Bearbeiten** (Markdown und Text, am PC und online): öffnet den Text im Editor mit *Schreiben*/*Vorschau* und dem
    Feld „Was hast du geändert?“. *Speichern* legt eine neue Version von dir an, der Verfasser bekommt eine Nachricht
    (abschaltbar). Strg+S speichert, Esc schließt (fragt bei Änderungen nach). Bei einer älteren Fassung heißt der Knopf
    *Diese Fassung bearbeiten …* – so holst du einen alten Stand als neue Version zurück.
  - **Konflikt:** Hat ein Agent inzwischen eine neuere Version abgelegt, wird nichts überschrieben. Dein Text bleibt im
    Editor, *Unterschiede zur neuesten Fassung* zeigt, was sich geändert hat, danach kannst du bewusst speichern.
  - **Vergleichen** (ab zwei Versionen, neben „Versionen“): Texte Zeile für Zeile, geänderte Wörter hervorgehoben,
    unveränderte Strecken eingeklappt. Bilder, Mockups und PDF nebeneinander (am Handy untereinander).
- **Hochladen** (Knopf im Bereich Dokumente, an jeder Frage *Datei/Foto anhängen*):
  - am PC: Datei wählen, hineinziehen oder ein Bildschirmfoto mit **Strg+V** einfügen (im Bereich Dokumente geht Strg+V
    auch ohne Dialog);
  - am Handy: *Foto aufnehmen* oder *Datei wählen*;
  - Fotos rechnet der Browser neu: höchstens 2560 px (abschaltbar), **Standort und Kameradaten fallen immer weg**;
  - Titel, Art und *Gehört zu* (z. B. `A1234`, `F12`, `B5` oder `Bogen 3`) sind vorbelegt; vom Handy steht die Datei
    gleich auf „auch online“.
- **Varianten in Fragen:** Hat der Agent je Option ein Bild oder Mockup angehängt, stehen die Varianten als Karten über den
  Optionen. Ein Klick zeigt sie groß (←/→ blättert zwischen den Varianten), gewählt wird wie immer mit der Option darunter.
- **Wo Dokumente außerdem auftauchen:**
  - an der Bogen-Karte („Dokumente (n)“) und am Schritt (📎);
  - in der Frage als Anhang mit Vorschaubild, z. B. Mockup-Varianten zur Wahl;
  - im Verlauf (Art „Dokumente“) und in der Suche oben.

## 3 Kommandozeile
`amw dokument liste [--art …] [--bogen N|--aufgabe N|--frage N] [--agent …] [--suche …] [--alle]` ·
`amw dokument zeigen <nr>` (Versionen mit Dateipfad, Gespräch) · `kommentar|ueberarbeiten <nr> --text …` ·
`zuordnen <nr> [--titel …] [--art …] [--aufgabe N | --loesen]` · `archivieren|wiederherstellen <nr>` ·
`online|offline <nr>` · `loeschen <nr> --ja` (nur Entwickler). Über die Datei-Brücke: `"datei"` (und Dateien bei
`--anhang`) relativ zu `eingang-tl/`.

**Vorhandene Ergebnisse einsammeln** – nichts geschieht automatisch:

```
amw dokument einsammeln F:/projekt/ergebnisse                 # nur lesen: Liste je Ablage mit Vorschlag
amw dokument einsammeln F:/projekt/ergebnisse --melden        # Liste als Dokument + Frage an dich, Info an den Lead
amw dokument einsammeln --uebernehmen --frage 5150            # erst nach deiner Antwort
amw dokument einsammeln --uebernehmen --frage 5150 --nur berichte --nur mockups   # nur diese Ablagen
```

- Die Liste nennt je Ordner Anzahl, Größe, Zeitraum und einen Vorschlag *behalten* oder *weg* mit Grund: Arbeitskopie
  (Ordner wie `tmp`, `alt`, `backup`), Prüflauf-Einzelbilder (viele nummerierte Bilder), schon in der AMW, zu groß, nur
  Code/Daten. Je Datei schlägt sie Art und Bezug vor (`A1234`, `B12`, `F7` im Pfad, wenn es die Nummer gibt).
- Antwortest du mit **A**, übernimmt der Agent alle vorgeschlagenen Dateien; mit **B** nichts. Antwortest du mit Text
  („nur die Berichte“), muss er die Auswahl mit `--nur` angeben.
- Übernommen werden nur Dateien, deren Inhalt seit der Liste gleich geblieben ist; nichts wird verschoben oder gelöscht.
  `.git`, `node_modules`, `.godot` und ähnliche Ordner werden gar nicht erst gelesen.

## 4 Ablage und Sicherung
- **Ablage:** Die Dateien liegen neben der Datenbank in `dokumente/<aa>/<sha256>.<endung>`. Gleicher Inhalt liegt nur
  einmal dort, auch wenn er in mehreren Dokumenten vorkommt.
- **Sicherung:** `amw sichern` kopiert die Ablage neben die Datenbank-Sicherung nach `…-dokumente/`, jeweils nur, was dort
  noch fehlt.
- **Online** (wenn die Online-Seite eingerichtet ist, [online.md](online.md)):
  - Liste, Details, Gespräch und **alle Texte** sind immer online, auch zum Durchsuchen.
  - **Dateien** (Bilder, Mockups, PDF, Office) nur bei Bedarf: wenn das Dokument auf *Auch online zeigen* steht. Das
    setzt du am PC, der Agent beim Ablegen mit `--online` (z. B. Mockups für eine Frage), oder du forderst sie unterwegs
    an: *Online anfordern* im Dokument, *Alle Dateien von A… anfordern* für alle Dateien derselben Aufgabe. Der PC lädt sie
    beim nächsten Abgleich hoch (meist unter 1 Minute).
  - *Nur am PC* nimmt die Datei wieder vom Webspace. In der Liste steht bei solchen Dokumenten „Datei nur am PC“.
  - Online kannst du kommentieren, überarbeiten lassen, bearbeiten, hochladen, zuordnen und archivieren; endgültig
    löschen geht nur am PC.
  - Hochladen vom Handy: Die Seite nimmt die Datei in Teilen an, legt sie gleich auf den Webspace und reicht sie über den
    Briefkasten an den PC; der PC prüft Größe und Prüfsumme und legt das Dokument an (meist unter 1 Minute).
