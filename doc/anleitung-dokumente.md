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
  - Links die Vorschau: Markdown gerendert, Bild (Klick zoomt), Mockup klickbar, PDF. Office-Dateien nur zum
    Herunterladen.
  - Rechts: wozu es gehört, alle Versionen (anklicken zeigt die alte Fassung) und das Gespräch.
- **Reagieren:**
  - *Kommentieren* oder *Überarbeiten lassen*: geht als Nachricht an den Verfasser und weckt ihn. Er legt eine neue Version
    ab.
  - *Zuordnen* ändert Titel, Art und Bezug. *Archivieren* blendet ein Dokument aus, *Wiederherstellen* holt es zurück.
  - *Endgültig löschen* geht nur am PC. Es entfernt die Dateien, der Eintrag bleibt als „gelöscht“ im Verlauf.
- **Wo Dokumente außerdem auftauchen:**
  - an der Bogen-Karte („Dokumente (n)“) und am Schritt (📎);
  - in der Frage als Anhang mit Vorschaubild, z. B. Mockup-Varianten zur Wahl;
  - im Verlauf (Art „Dokumente“) und in der Suche oben.

## 3 Kommandozeile
`amw dokument liste [--art …] [--bogen N|--aufgabe N|--frage N] [--agent …] [--suche …] [--alle]` ·
`amw dokument zeigen <nr>` (Versionen mit Dateipfad, Gespräch) · `kommentar|ueberarbeiten <nr> --text …` ·
`zuordnen <nr> [--titel …] [--art …] [--aufgabe N | --loesen]` · `archivieren|wiederherstellen <nr>` ·
`online|offline <nr>` · `loeschen <nr> --ja` (nur Entwickler). Über die Datei-Brücke: `"datei"` relativ zu `eingang-tl/`.

## 4 Ablage und Sicherung
- **Ablage:** Die Dateien liegen neben der Datenbank in `dokumente/<aa>/<sha256>.<endung>`. Gleicher Inhalt liegt nur
  einmal dort, auch wenn er in mehreren Dokumenten vorkommt.
- **Sicherung:** `amw sichern` kopiert die Ablage neben die Datenbank-Sicherung nach `…-dokumente/`, jeweils nur, was dort
  noch fehlt.
- **Online:** Texte werden online sichtbar, Dateien nur bei Bedarf („Auch online zeigen“). Das kommt mit Stufe D2 des
  Plans, bis dahin sind Dokumente nur am PC zu sehen.
