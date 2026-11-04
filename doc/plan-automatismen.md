# Plan: Automatismen statt Gebote (A1246, Beschluss B2419)

Stand 04.11.2026 · CCamw · Anlass: Nachtfreigabe B2414 endete nicht von selbst (Fenster-Läufe, obwohl Marcel per
TeamViewer am PC war); A1238 lag über Nacht liegen, obwohl die Gründe für das Warten erledigt waren.

Leitsatz aus B2419: **Was vergessen werden kann, regelt die AMW technisch statt per Gebot.**

## Versionen

| Version | Inhalt | Schema |
|---|---|---|
| **1.7.0** | Teil 1 Schirm-Schalter + `lauf warte`/`lauf zeige` (gehört dazu: wer auf den Schirm wartet, muss richtig warten können) | 11 |
| **1.8.0** | Teil 2 Wartegründe und Wecken L1–L6, Frage-Prüfung (B2422) | 12 |
| **1.9.0** | Agenten nach Rolle umbenennen (Alias), CLAUDE.md ohne bus.py | (12) |
| **1.9.x** | Rest aus der Wochen-Umfrage #16787 (s. u.) | – |

## Teil 1: Schirm-Schalter (1.7.0)

### Zustand
Neue Tabelle `schirm` (PC-weit, nicht je Projekt – es gibt nur einen Bildschirm). Jede Änderung ist eine Zeile;
die jüngste gilt. Felder: `frei` (0/1), `seit_utc`, `bis_utc` (optional), `grund`, `von`, `quelle`
(`workbench`, `cli`, `bruecke`, `automatik`).

- **Vorgabe: zu.** Leere Tabelle, Neustart des Rechners oder des Dienstes → zu. Frei wird der Schirm nur durch ein
  ausdrückliches „frei“.
- **Frei setzen** dürfen nur Marcel (Workbench am PC, `--von Entwickler`) und der Lead auf Marcels Wort (Brücke).
  Pflicht: Grund. Optional: `--bis 07:00`.
- **Zu setzen** darf jeder Agent und Marcel auch online vom Handy aus. Das ist die sichere Richtung.

### Automatisch zu (Prüfung im Takt des Dienstes, alle 15–30 s)
1. **Eingabe am PC:** `GetLastInputInfo` (der Dienst läuft in Marcels Sitzung, geprüft). Gilt nur Eingabe, die
   **später als 2 min nach dem Freigeben** kommt. Sonst würde der Klick auf „frei“ den Schirm sofort wieder schließen.
2. **TeamViewer:** Eine Fernsitzung beginnt **nach** dem Freigeben (`TeamViewer_Desktop.exe` erscheint).
   Gemessen am 04.11.: `TeamViewer.exe` und `TeamViewer_Service.exe` laufen seit dem Windows-Start ständig
   (Infobereich) und sagen nichts. `TeamViewer_Desktop.exe` startete um 06:36 mit Marcels Verbindung. Seine
   Startzeit gibt Windows ohne Adminrechte nicht heraus, deshalb zählt, wann der Dienst die Sitzung zuerst sah.
   Nach einem Neustart des Dienstes gilt eine laufende Sitzung als neu, und der Schirm geht zu (sichere Richtung).
   Eingaben über TeamViewer zählen außerdem als Eingabe am PC (Punkt 1).
   *Abweichung vom Wortlaut von B2419* („TeamViewer-Prozess läuft“): Sonst ginge der Schirm nie auf.
3. **Marcel schreibt:** neuer Eintrag von Marcel in der Workbench (PC oder online) oder ein Wortlaut mit Marcels
   Zeit nach dem Freigeben.
4. **Uhrzeit:** `bis_utc` erreicht.

Der Grund steht in der neuen Zeile, z. B. „zu: TeamViewer läuft (06:50)“ oder „zu: Eingabe am PC (06:02)“.

### Lauf-Schlange
- `lauf start --schirm` bei zu: ohne `--warten` Fehler mit Grund („Schirm zu seit 06:02: Eingabe am PC“), mit
  `--warten` eingereiht mit diesem Grund. Die Schlange startet Schirm-Läufe nur bei frei **und** wenn der PC seit
  2 min ruht.
- **Beim Zugehen:** Wer einen Schirm-Lauf am Laufen hat, bekommt eine weckende Meldung: „Schirm zu (Grund) – L123
  sofort beenden: amw lauf ende 123 …“. Die AMW beendet keine Prozesse selbst (nur Marcel beendet Prozesse,
  #16557). Wer Schirm-Läufe in der Schlange hat, bekommt einen Hinweis, dass sie bis zur nächsten Freigabe warten.
- **Beim Aufgehen:** Die Schlange startet den nächsten Schirm-Lauf wie heute, mit einer weckenden Freigabe.
- **Neu: `amw lauf warte <nr>`** blockiert, bis der Lauf läuft (rc 0) oder abgebrochen ist (rc ≠ 0). Unterwegs
  kommt jede Minute eine Zeile mit dem Wartegrund. **`amw lauf zeige <nr>`** zeigt Status, Platz in der Schlange,
  den Lauf davor und den Grund.
- `--warten` bleibt, heißt in der Hilfe aber klar „nur einreihen“.

### Befehle und Oberfläche
- `amw schirm` zeigt den Zustand, die Dauer seit dem letzten Wechsel, den Grund und die letzten Wechsel.
- `amw schirm frei --grund … [--bis HH:MM]` (Entwickler/Lead), `amw schirm zu [--grund …]` (alle).
- Brücke: dieselben Befehle für den TL.
- Workbench: eine Kachel auf der Startseite „Schirm frei/zu · seit · Grund“ mit Knopf (frei nur am PC). Unter
  „Betrieb“ der Verlauf der Wechsel. Den Pflichtkontext beim Sitzungsstart bekommt eine Zeile „Schirm: zu seit …“.
- Push an Marcel: optional, nur Metadaten („Schirm zu: TeamViewer“). Standard aus.

### Grenzen (ehrlich)
- Die AMW sperrt nur Läufe, die über `lauf start --schirm` angemeldet sind. Startet ein Agent ein Fenster an der
  Schlange vorbei, sieht die AMW das nicht. Mögliche Ergänzung, falls der TL das will: Der Dienst meldet dem TL ein
  sichtbares Godot-Fenster, während der Schirm zu ist.
- Erzeugt ein Schirm-Lauf selbst Windows-Eingaben (Maus/Tastatur per Programm), hält die AMW das für Marcel und
  schließt den Schirm. Das ist der sichere Fehler. Falls das vorkommt, folgt ein Filter für künstliche Eingaben.

### Tests
- Zustand und Vorgabe zu, Rechte (frei nur Entwickler/Lead, zu alle).
- Jeder Auto-Grund einzeln (Eingabe, TeamViewer, Workbench, Wortlaut, Uhrzeit) mit vorgetäuschten Messwerten, auch
  die 2-min-Gnadenfrist.
- Schlange: Schirm-Lauf hält bei zu, startet bei frei + Ruhe; Meldung beim Zugehen an den laufenden Lauf.
- `lauf warte`/`lauf zeige` mit rc.
- Workbench-Kachel: Fotos Desktop/Handy.

## Teil 2: Wartegründe, Wecken, Frage-Prüfung (1.8.0, Schema 12)
Dazu B2422 (Marcel 04.11. 18:02): Fragen, die in der Datenbank schon beantwortet sind, soll die AMW abfangen.

### L1 Wartegrund als Verweis
Neue Tabelle `wartegrund` (Aufgabe, Art, Bezug, Text, angelegt von/um, erledigt um/durch). Arten und Bezug:

| Angabe | Art | erledigt, wenn … |
|---|---|---|
| `F5148` | frage | die Frage beantwortet oder verworfen ist (Rückfrage zählt nicht) |
| `A1240` | aufgabe | die Aufgabe fertig oder verworfen ist |
| `L141` | lauf | der Lauf zu Ende ist (fertig oder abgebrochen) |
| `CC2` (Kennung) | agent | dieser Agent eine Nachricht mit `--aufgabe` dieser Aufgabe schickt |
| `Marcel` / `Entwickler` | entwickler | Marcel eine Frage zu dieser Aufgabe beantwortet oder in der Workbench zu ihr schreibt |
| `Monitor:<was>` | monitor | nur von Hand (der eigene Monitor in der Sitzung) |

- `amw aufgabe wartet <nr> --auf F5148,A1240,CC2 [--wartet-auf "Erklärung"]`, ebenso `blockiert`. **Ohne `--auf`
  lehnt die AMW „wartet“/„blockiert“ ab.** Eine neue, noch nicht begonnene Aufgabe steht wie bisher auf „wartet“ –
  das ist „zu tun“ und braucht keinen Grund.
- `amw aufgabe wartet <nr> --erledigt F5148` hakt einen Grund von Hand ab (z. B. der TL nach Marcels Wort im Chat).
- Startet, endet oder wird eine Aufgabe verworfen, sind ihre offenen Gründe mit erledigt.
- Alte Aufgaben mit Freitext in `wartet_auf` bleiben, wie sie sind (zählen als wartend).

### L2 Erledigter Grund weckt
Wird ein Grund erledigt, bekommt der Besitzer eine weckende Meldung, Kopie an den Lead:
„A1238: F5148 beantwortet (B) – noch offen: A1240“ bzw. „… – alle Gründe erledigt, weiter: amw aufgabe start 1238“.

### L3 Leerlauf-Prüfung
Der Dienst prüft je angemeldeter Sitzung (Pipe, nicht die Brücke): Ist sie seit 30 min frei (Hook-Ereignis „frei“),
ohne offene Nachrichten, und hat der Agent eine Aufgabe, an der er arbeiten kann (läuft, oder wartet ohne offenen Grund
und ohne Freitext, Vorgänger fertig, nicht geparkt), weckt eine Meldung mit dieser Aufgabe – einmal je Ruhephase.
Wartet alles des Agenten auf Marcel, höchstens alle 6 h eine Sammelzeile an den Lead („CC1, CC5 frei – warten auf
Marcel: F5148, F5151“).

### L4 Aufgaben-Bezug prüfen
`posten --aufgabe` (und `frage neu --aufgabe`): Gibt es die Aufgabe nicht oder ist sie fertig/verworfen → Ablehnung.
Gehört sie einem anderen Agenten → Hinweis in der Ausgabe (keine Ablehnung, Merge-Bitten tragen fremde Nummern).

### L5 Kopie an den Besitzer
Eine `info`/`meldung`/`antwort` mit `--aufgabe` einer fremden Aufgabe, deren Besitzer nicht unter den Empfängern
ist, geht in Kopie an ihn – weckend, wenn seine Aufgabe wartet oder blockiert ist. Nicht bei `auftrag` und
`pruefbitte` (Merge- und Prüfbitten).

### L6 Was eine Frage aufhält
Workbench und Online-Seite zeigen bei offenen Fragen „hält A1238 (CC1) seit 06:12“ (aus `wartegrund`, sonst aus
`frage.aufgabe_id` bei blockierenden Fragen).

### Frage-Prüfung gegen die Datenbank (B2422)
`amw frage neu` sucht vor dem Anlegen in geltenden Beschlüssen, beantworteten Fragen und Regeln nach den Wörtern
aus `--kurz`/`--worum` (Wortanfänge, seltene Wörter zählen mehr) und zeigt die besten Treffer mit Antwort.
- Neues Feld `--geprueft "B2419 passt nicht, weil …"` (Spalte `frage.geprueft`). Ohne `--geprueft` legt die AMW die
  Frage nicht an, sondern zeigt die Treffer. Gibt es Treffer, muss `--geprueft` mindestens einen davon nennen
  (B…/F…/PR…/KR…); ohne Treffer reicht ein Satz („keine Treffer“).
- Gilt für Fragen an Marcel; bei Fragen an den Lead zeigt die AMW die Treffer nur an.
- Die Workbench zeigt „geprüft: …“ unter der Frage, damit Marcel sieht, was der Agent schon gelesen hat.

## Umbenennen nach Rolle (1.9.0, Marcel 04.11. 18:04)
CC1 → CCdesign, CC2 → CCqa, CC3 → CCengine, CC4 → CCcontent, CC5 → CCui, CC6 → CCsim, CC7 → CC3d, TL → CClead.
- `agent.alias` (Schema 12 gleich mit): alte Kennung bleibt gültig. `--von CC3`, `AMW_AGENT=CC3`, `--an CC3`,
  `--agent CC3`, Halt für CC3 landen bei CCengine. Laufende Sitzungen müssen also nicht neu starten.
- `amw agent umbenennen CC3 CCengine` (nur Entwickler/Lead): in **einem** Schreibvorgang alle Spalten, die eine
  Kennung enthalten (Nachrichten von/an, Aufgaben, Fragen, Läufe, Prüfungen, Sperren, Sitzungen, Profile …), neue
  Kennung; Freitexte („CC3 bitte …“) bleiben. Vorher `amw sichern`. Der Online-Abgleich schickt die geänderten Zeilen
  einmal nach.
- Sitzungen (`--resume <id>`) hängen an der Sitzungs-ID, nicht am Namen; Gesprächsansicht und „In Claude öffnen“
  bleiben. Tab-Titel und `--remote-control`-Name kommen aus dem Profil (neue Kennung) – Wirkung beim nächsten Start.
- Danach: Startdatei des TL, Startskript, CLAUDE.md (gemeinsam mit dem Teil „ohne bus.py“).
- Marcels eigene Startdatei (Nachtrag #16902): vorher Kopie `….vor-umbenennung` daneben, dann je Tab Titel,
  `AMW_AGENT` und `--remote-control` auf die neue Kennung; Sitzungs-IDs (`--resume`) bleiben. Abstand wie die
  Startdatei des TL (B2410: 20 s statt heute 3 s). Sie startet heute CC1–CC7 und CCamw, nicht den TL.
- Zeitpunkt: ruhig (kein Lauf aktiv), vorher Ansage an alle; Ablauf je Agent in einem Rutsch, danach `amw agent liste`.

## Rest aus der Umfrage #16787 (1.8.x)
`beschluss zeige/suche`, amw-cli meldet Wartezeit auf die Datenbank und bricht mit Fehlercode ab, Ausgabe immer
UTF-8, Startskript zeitversetzt + `--alle`, „an alle“ = alle laufenden Sitzungen (oder Warnung, wer fehlt),
`lesen --neu` und mehrere Nummern, Aufgaben-Nr. auch als „A1162“, `abmelden`, Notizen nach Agent filtern, Alter
der Tätigkeit in der Workbench, Leitfaden/CLAUDE.md der Agenten ohne die alten `bus.py`-Befehle.
