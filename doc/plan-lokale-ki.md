# Lokale KIs in der AMW (universal)

Stand 05.11.2026. Anlass: Wunsch des Entwicklers, die lokal installierten KIs so überschaubar zu führen wie die Agenten.
Status: **Stufe 1 umgesetzt (AMW 1.16.0, Schema 17)**, freigegeben vom Entwickler. Stufe 2 und 3 siehe unten.

## Bedienung (Stufe 1)

```
# einmal am PC eintragen (nicht über Brücke/Online-Seite – Endpunkt und Startbefehl)
amw ki neu ollama  --art sprache --schnittstelle ollama  --lizenz MIT
amw ki neu comfyui --art bild    --schnittstelle comfyui --lizenz GPL-3.0 \
    --start "<python> main.py --listen 127.0.0.1 --port 8188 …" --ordner <ComfyUI-Ordner>
amw ki modell comfyui sdxl-base --datei sd_xl_base_1.0.safetensors --lizenz "CreativeML Open RAIL++-M" \
    --kommerziell ja --nutzungsregeln --quelle <URL> --sha256 <…>
amw ki freigeben comfyui sdxl-base          # Lead; bei Nutzungsregeln/Registrierung nur der Entwickler
amw ki sperren comfyui flux-dev --grund "nicht kommerziell"
amw ki vorlage comfyui sprite-sdxl --datei workflow_api.json   # ComfyUI: Workflow → Export (API)
amw ki recht comfyui --wer Grafik           # oder alle | rolle:<rolle>; Lead und Entwickler dürfen immer

# beauftragen – der Agent muss danach nicht warten, er wird geweckt
amw ki auftrag comfyui --vorlage sprite-sdxl --prompt "…" --anzahl 4 --seed 4711 --aufgabe 1234 [--bild D96]
amw ki auftrag ollama --modell qwen3.5:9b --prompt-datei texte.md [--parameter '{"temperature":0.2}']
amw ki zeige L812        # Stand, Ergebnisse, Herkunft je Dokument
amw ki                   # KIs, Modelle mit Freigabe, Vorlagen, Aufträge
amw ki nachweis [--aufgabe N | --bogen N]   # Liste aller KI-Dokumente mit Modell und Lizenz
amw lauf start|ausfuehren --gpu …           # eigene Läufe, die die Grafikkarte brauchen
```

- **Vorlagen-Platzhalter:** `{prompt}` `{negativ}` `{seed}` `{breite}` `{hoehe}` `{bild}` `{modell}`. Steht ein Platzhalter
  allein, behält der Wert seinen Typ (Seed als Zahl). Bild n bekommt Seed + n − 1.
- **Freigaben:** Jede Modell-Datei, die eine Vorlage nennt (auch VAE, Text-Encoder), muss eingetragen und frei sein.
  Ändern sich Lizenz, Datei oder Prüfsumme, ist die Freigabe wieder offen. Frei geht nur bei kommerziell nutzbarer Lizenz.
- **Schlange:** Ein KI-Auftrag ist ein schwerer Lauf mit Platz `gpu`. Er wartet auf schwere Läufe des Projekts und PC-weit
  auf GPU- und Schirm-Läufe; umgekehrt warten diese auf ihn. Vorziehen und Abbrechen wie bei jedem Lauf
  (`amw lauf vorziehen|ende <nr> --abgebrochen`).
- **Ausführung:** Der Dienst holt den Lauf ab, sobald er dran ist (auch ohne Sitzung des Auftraggebers), startet ComfyUI bei
  Bedarf mit dem Startbefehl, schickt die Prompts, legt jedes Ergebnis als Dokument zur Aufgabe ab, schreibt die Herkunft
  (`ki_herkunft`, unveränderlich), entlädt die Modelle (`/free`, Ollama `keep_alive: 0`), beendet den Lauf und weckt den
  Auftraggeber mit einer Meldung. Abbruch über `/interrupt` bzw. Schließen der Anfrage; die AMW beendet keine Prozesse.
  Ein Neustart des Dienstes holt laufende ComfyUI-Aufträge weiter ab und fragt Ollama neu.
- **Gegenprobe:** Bei PNG aus ComfyUI vergleicht die AMW den Seed im Bild mit dem Auftrag („bestätigt“ oder „ABWEICHUNG“).
- **Sichtbar:** Workbench und online unter Betrieb → „Lokale KI“, die Herkunft im Dokument-Fenster.

### Entschieden (zu den offenen Fragen unten)

1. Variante C und Ausführung durch die AMW (2b) – so gebaut.
2. Frei gibt der Lead; bei Nutzungsregeln oder Registrierung nur der Entwickler.
3. KI-Fenster `--nachts`: kommt mit Stufe 2.
4. Anfangs dürfen nur Lead und Entwickler beauftragen; weitere Rechte setzt der Lead (`amw ki recht`).

## Kurzfassung

Eine lokale KI ist in der AMW ein **Werkzeug**, kein Agent. Sie hat Modelle mit Lizenz und Version. Die Rechte
(wer darf beauftragen) gelten je Projekt.

1. **Auftrag:** Agenten beauftragen sie nur **über die AMW**, und zwar als **KI-Lauf** in der bestehenden
   Lauf-Schlange.
2. **Grafikkarte:** Sie ist ein neuer PC-weiter Platz „gpu“. Läufe des Projekts (z. B. Spiel-Engine) und KI-Läufe stehen in derselben
   Reihe, und niemand überholt.
3. **Ausführung:** Den KI-Lauf führt die **AMW selbst** über die lokale HTTP-Schnittstelle aus (Ollama,
   ComfyUI). Der Agent muss dafür nicht wach sein, auch nachts nicht.
4. **Ergebnis:** Jedes Ergebnis wird ein **Dokument mit Herkunft** (KI, Modell, Version, Lizenz, Prompt,
   Seed, Parameter, Dauer). Die AMW schreibt die Herkunft selbst, sie beruht nicht auf Angaben des Agenten.
   Auswahl und Nachbearbeitung durch Agent oder Entwickler werden am Dokument vermerkt.
5. **Nachweis:** Aus diesen Angaben erzeugt `amw ki nachweis` die Liste für Steam und das Urheberrecht.

## 1. Setup – was ist eine lokale KI in der AMW?

### Varianten

| | A: als Agent anlegen | B: als `server` + Rezepte | **C: eigene Art „KI“ (Empfehlung)** |
|---|---|---|---|
| Pro | sofort sichtbar in Kacheln, nichts Neues | kein neues Schema; Port-Prüfung und Neustart gibt es schon | passt genau: Modelle, Lizenzen, Grafikkarte, Rechte, Herkunft |
| Contra | Ein Agent liest Nachrichten, hat Sitzung, Puls und Arbeitsliste – eine KI hat nichts davon. Weckrufe, „alle“ und das Startskript würden falsch greifen. | `server` gilt je Projekt, die KI gilt für den ganzen PC. Kein Platz für Modelle, Lizenz und Herkunft. Die Herkunft bliebe Handarbeit des Agenten. | neue Tabellen (Schema 17) |

### Felder (Variante C)

- **`ki`** gilt PC-weit wie `schirm`, weil installierte Programme und die Grafikkarte dem PC gehören und nicht
  einem Projekt. Felder:
  - Name (z. B. `ollama`, `comfyui`);
  - Art: sprache | bild | ton | 3d | video | sonstig;
  - Schnittstelle: ollama | comfyui | befehl;
  - Endpunkt: nur `127.0.0.1`/`localhost`, alles andere lehnt die AMW ab;
  - Programm-Version und Lizenz des Programms;
  - Ablage (Ordner);
  - optional Start- und Prüfbefehl;
  - Zustand an | aus | belegt | gestört (prüft der Dienst wie bei `server`);
  - VRAM-Bedarf als Richtwert.
- **`ki_modell`** je KI. Felder:
  - Name, Datei bzw. Variante, Version oder sha256, Quelle (URL), Lizenz;
  - **Freigabe**: offen | frei | gesperrt (mit Grund);
  - kommerziell: ja | nein | registrierung;
  - VRAM-Probe (GB, Sekunden je Auftrag).
  - Ein Modell, das nicht **frei** ist, kann nicht beauftragt werden.
  - Wer freigibt: Lead. Bei „registrierung“ oder einer Lizenz mit Nutzungsregeln (z. B. Open RAIL++-M) gibt
    **der Entwickler** frei.
- **`ki_vorlage`** (für ComfyUI und Blender): ein benannter Workflow (API-JSON als Dokument, sha256) mit
  Platzhaltern `{prompt}`, `{negativ}`, `{seed}`, `{bild}`, `{breite}`, `{hoehe}`. Das entspricht den
  Rezepten für Läufe. Ohne Vorlage gibt es keinen Bild-Auftrag, denn freie Workflows wären nicht überschaubar.
- **`ki_recht`** je Projekt bestimmt, wer beauftragen darf. Möglich sind „alle“, eine Rolle oder einzelne
  Agenten, je KI.
  - Vorgabe beim Anlegen: niemand außer Lead und Entwickler.

Eintragen: `amw ki neu …`, `amw ki modell …`, `amw ki vorlage …`, `amw ki recht …`. Eine vorhandene
Installationsliste lässt sich fast 1:1 übernehmen; ein Agent trägt sie einmal ein.

## 2. Wer beauftragt – und wie?

### Direkt oder über die AMW?

| | Direkt (MCP/HTTP vom Agenten) | **Über die AMW (Empfehlung)** |
|---|---|---|
| Pro | flexibel; der Agent kann Workflows frei bauen und iterieren; nichts zu bauen | Die Grafikkarte ist ein Platz und wird gerecht verteilt. Jeder sieht, was erzeugt wird. Die Herkunft ist automatisch und vollständig. Es geht nachts ohne wachen Agenten. Rechte und Lizenzsperren greifen. |
| Contra | Grafikkarte doppelt belegt (ein Test des Projekts bricht ab oder lagert aus); keiner sieht es; Herkunft hängt an der Disziplin; Agent wartet und verbraucht Token | etwas weniger frei: neue Workflows erst als Vorlage eintragen |

### Wer führt den Auftrag aus?

| | (a) Der Agent nach Freigabe (heutiger Lauf) | **(b) Die AMW selbst (Empfehlung)** |
|---|---|---|
| Pro | nichts Neues; der Agent kann zwischendurch eingreifen | Der Agent kann schlafen. Die Herkunft kommt von dem, der den Prompt wirklich abschickt. Die nächtliche Reihe läuft durch. |
| Contra | Der Agent muss wach sein und warten (Token, Nacht); die Herkunft ist nur Selbstauskunft | Der Dienst bekommt einen Arbeiter. Abbruch über die API (`/interrupt`, Abbruch der Anfrage), nicht durch Beenden von Prozessen. |

**Regel „Die AMW beendet keine Prozesse“:** Sie bleibt in Phase 1 unberührt.
- Phase 1 umfasst nur die Schnittstellen ollama und comfyui, also HTTP.
- Platz schaffen: Die AMW entlädt Modelle über die API: Ollama mit `keep_alive: 0`, ComfyUI mit `/free`.
- Abbrechen: über `/interrupt`, bzw. die AMW schließt die Anfrage.
- **Starten:** Läuft ComfyUI nicht, startet die AMW es über den bestehenden Weg für Server
  (`ueberwachung.py`, Startbefehl ohne Fenster). Den gibt es schon, Neues kommt nicht hinzu. Danach bleibt
  ComfyUI an und wird nur über `/free` entladen. Beendet wird es nicht.
- Blender und ffmpeg (Schnittstelle „befehl“) kommen erst in Phase 3 und laufen dort wie heute über den
  Agenten mit `amw lauf ausfuehren`, der nur seinen eigenen Kindbaum beendet.

### Wer darf beauftragen?

- Agenten mit Recht laut `ki_recht`, außerdem Lead und Entwickler (über Workbench oder Handy).
- Der Entwickler bekommt online **keinen** Startknopf für die KI, wie bei den Agenten. Er darf aber vorziehen,
  zurückstellen und die Ergebnisse auswählen.

### Befehl (Entwurf)

```
amw ki auftrag comfyui --vorlage sprite-sdxl --modell sdxl-base --prompt "…" --seed 4711 --anzahl 4 \
    --aufgabe 1234 [--bild D96] [--nachts] [--von Grafik]
amw ki auftrag ollama --modell qwen3.5:9b --prompt-datei texte.md [--aufgabe …]
```

Das legt einen Lauf an (Art „ki“, Platz „gpu“). Die AMW führt ihn aus und legt die Bilder bzw. Texte als
Dokumente zur Aufgabe ab. Danach weckt sie den Auftraggeber: „L812 fertig: D140–D143 (4 Bilder)“.

## 3. Reihenfolge

| | Unteraufgabe in der Arbeitsliste | Eigene Liste je KI | **Lauf in der gemeinsamen Schlange, Platz „gpu“ (Empfehlung)** |
|---|---|---|---|
| Pro | sichtbar beim Agenten | übersichtlich je KI | Eine Reihe für die eine Grafikkarte, also kein Streit zwischen Projekt-Läufen und KI. Vorziehen, Wartegründe und Freigaben gibt es schon. |
| Contra | Ein KI-Auftrag ist keine Arbeit des Agenten. Er würde gegen „genau eine in Arbeit“ zählen und das Zurückstellen auslösen. | Zwei Schlangen für dieselbe Karte müssten sich trotzdem absprechen | – |

Dazu im Einzelnen:

- **Platz „gpu“ PC-weit:** Heute gelten „schwer“ und „schirm“ je Projekt. Die Grafikkarte gehört dem PC.
  Läufe und Rezepte des Projekts, die die Grafikkarte brauchen, bekommen ein Merkmal „gpu“, KI-Läufe haben es immer.
- **Beim Agenten:** Der KI-Lauf hängt an seiner Aufgabe und erscheint auf deren Karte. Die Aufgabe kann so
  lange auf „wartet auf L812“ stehen, und die Arbeitsliste lässt ihn die nächste nehmen.
- **Workbench:** Betrieb → „KI“ zeigt eine Kachel je KI (Zustand, Modell im Speicher, Reihe davor) und
  darunter die KI-Läufe gefiltert aus der gemeinsamen Schlange. Es ist eine Ansicht, keine zweite Schlange.
- **Nachts oder wenn der Entwickler weg ist:** `--nachts` heißt „nicht vor dem KI-Fenster“. Das Fenster ist eine
  PC-weite Einstellung, z. B. 22–06 Uhr, oder „wenn Schirm frei/Entwickler abwesend“. Der Terminplaner zeigt das
  Fenster als Band und daneben die Menge der wartenden Aufträge (Schätzung aus der VRAM-Probe in Sekunden).
- **Testtermine haben Vorrang:** In der Vorlaufzeit vor einem Testtermin (termin.vorlauf_h) startet die
  AMW keine neuen `--nachts`-Aufträge.

## 4. Kontrolle

- **Herkunft je Dokumentversion** (Tabelle `ki_herkunft`):
  - Lauf, KI, Programm-Version, Modell, Datei bzw. sha256, Lizenz, Vorlage und deren sha256;
  - Prompt, Negativ-Prompt, Seed und weitere Parameter (JSON), Eingabebilder als D-Nummern;
  - Dauer und VRAM-Spitze.
  - Zur Gegenprobe: ComfyUI schreibt Workflow und Seed in die PNG. Die AMW vergleicht das beim Ablegen.
- **Vermerke am Dokument**, je mit wer, wann und Text:
  - ausgewählt / verworfen (Agent oder Entwickler, auch per Handy);
  - **nachbearbeitet**: was von Hand geändert wurde. Für das Urheberrecht ist das der entscheidende Teil
    (in Deutschland: AG München, 13.02.2026, 142 C 9786/25); in der AMW heißt das „menschliche Gestaltungsentscheidung“.
- **Nachweis:** `amw ki nachweis [--aufgabe/--bogen/--alle]` erzeugt eine Liste aller KI-Dokumente:
  - Modell und Lizenz;
  - ausgewählt / nachbearbeitet;
  - ob sie in einem Commit stecken (Beleg).
  - Daraus entsteht die Angabe für Steam (pre-generated) und eine `ASSET_SOURCES.md`.
- **Zeit und Kosten je Auftrag:** Dauer und Grafikkarten-Minuten stehen in der Ansicht „Verbrauch“, getrennt
  von den Claude-Token.

## 5. Sicherheit

- Endpunkte sind nur lokal (`127.0.0.1`, `localhost`, `::1`). Jeder andere Host wird beim Eintragen
  abgelehnt.
- Keine Konten, Token oder Logins in der AMW. Die Freischaltung auf Hugging Face macht der Entwickler selbst, die AMW
  merkt sich nur „Freigabe frei, kommerziell: registrierung (Entwickler, Datum)“.
- Ein Modell ohne Freigabe „frei“ kann nicht beauftragt werden. Gesperrte Modelle (z. B. Hunyuan wegen EU,
  FLUX-dev wegen non-commercial) stehen mit Grund sichtbar in der Liste, damit keiner sie erneut lädt.
- Online gelten die Regeln wie bei anderen Dokumenten (Einstellung `dateien_online`). Prompts sind Text und
  online lesbar; wer das nicht will, setzt das Dokument offline.
- **Umgehung sichtbar machen (Phase 3):**
  - Der Dienst schaut per `nvidia-smi` nach, wer die Grafikkarte belegt. Steckt dahinter kein laufender Lauf,
    meldet er „fremde GPU-Last“. Er meldet nur und beendet nichts.
  - comfyui-mcp kommt in keine Agenten-Konfiguration. Höchstens Werkzeuge, die nur lesen, wären denkbar; das
    entscheidet der Lead.

## 6. Stufen

| Stufe | Inhalt |
|---|---|
| 1 | `ki`, `ki_modell` (Freigabe), `ki_vorlage`, `ki_recht`; Platz „gpu“ PC-weit; `amw ki auftrag` für ollama und comfyui, ausgeführt vom Dienst; Ergebnis als Dokument mit `ki_herkunft`; Weckruf an den Auftraggeber; Workbench: Betrieb → KI |
| 2 | KI-Fenster `--nachts` mit Band im Terminplaner; Vermerke ausgewählt, verworfen und nachbearbeitet (Workbench und Handy); `amw ki nachweis` |
| 3 | Schnittstelle „befehl“ (Blender, ffmpeg) über `lauf ausfuehren`; Meldung „fremde GPU-Last“ |

## Offene Fragen an den Entwickler

1. Variante C (eigene Art „KI“) und Ausführung durch die AMW (2b)? Mit Schema 17.
2. Wer gibt Modelle frei: der Lead allgemein, der Entwickler nur bei „registrierung“ oder Nutzungsregeln. Oder bei
   allen Modellen der Entwickler?
3. Wie ist das KI-Fenster für `--nachts` festgelegt: feste Uhrzeit, oder „wenn Schirm frei/Entwickler weg“?
4. Wer darf anfangs beauftragen: alle Agenten, oder nur Rollen mit Grafik oder Text (z. B. für Grafik oder Übersetzung)?
