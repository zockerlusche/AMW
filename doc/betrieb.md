# Betrieb: Arbeiten mit AMW

## 1 Die Workbench
http://127.0.0.1:8780 (am Handy dieselbe Seite über die Online-Adresse). Oben in ganzen Wörtern: „Wächter läuft“,
„x von y Agenten laufen“, „Arbeitsspeicher: n GB frei“ und die Suche (Aufgaben, Beschlüsse, Fragen, Wortlaut,
Nachrichten). Die erste Zeile zeigt nur Zustände; weicht etwas vom Normalfall ab („Angehalten“, „Bildschirm: frei für
Agenten“, „n werden beendet“), steht es dort als Hinweis, ein Klick führt zum Leitstand.

**Leitstand** (Start, direkt unter den Agenten) – alles Steuerbare an einer Stelle:

| Feld | Zustand | Knöpfe |
|---|---|---|
| Arbeit der Agenten | läuft / angehalten | Alle anhalten · Weiterarbeiten |
| Bildschirm | belegt / frei für Agenten (bis …) | Für Agenten freigeben … (nur am PC) · Wieder belegen |
| Sitzungen | n laufen · n abgemeldet · n fehlen | Alle sichern & beenden · Fehlende starten (beides nur am PC) |
| Wächter | läuft · Version | Neu starten (nur am PC) |

**Aktionsmenü „⋯“** an jeder Agenten-Kachel: Nachricht schreiben, Gespräch mitlesen, Übersicht und Aufgabenliste ·
Anhalten (nur diesen) bzw. Weiterarbeiten lassen, Sichern & beenden lassen, Sofort beenden, Starten/fortsetzen, Neue
Sitzung beginnen (Sitzungen nur am PC) · Profil und Zuständigkeit.

| Ansicht | Wofür |
|---|---|
| **Start** | „Seit du weg warst“, Warnungen, **Wartet auf dich** (Freigaben, eigene Schritte, Fragen), Agenten-Kacheln (Zustand, was er gerade tut, Kontext/5-Stunden-Grenze; Klick = Übersicht mit Starten/Beenden), Nachrichten an dich |
| **Fragen** | Reiter *Offen* und *Geparkt*: Fragen an dich mit Optionen und Empfehlung; Antwort per Klick, eigener Text oder Rückfrage; Verlauf wie im Chat; parken und wieder aufnehmen |
| **Planung** | Zeitleiste der Bögen mit Ampel und Prognose, Spezifikation freigeben, Leitbild, Risiken, Plan-Check, Protokoll |
| **Aufgaben** | Board (läuft · wartet · blockiert), geparkt, Pool, abgeschlossen; Filter nach Agent und Text |
| **Verlauf** | alles, was passiert ist, je Tag, filterbar |
| **Release Notes** | je Zusammenführung eine Zeile, Versionen |
| **Wissen** | Beschlüsse, Regeln, Wortlaut, Notizen; Suche |
| **Betrieb** | Projekt-Server, Verbrauch je Agent und Tag, Sperren, Sitzungen, Rechen-Läufe, Protokoll des Wächters |
| **Einstellungen** | Projekt, Agenten (mit Profil), Online-Seite, dieser PC, Online-Speicher, Benachrichtigungen |

Hell/Dunkel und Deutsch/Englisch unten links; die Seite aktualisiert Start und Betrieb von selbst (nicht während du tippst).
Die Untermenüs einer Seite (Reiter, Filter, Sprungmarken) bleiben beim Scrollen oben stehen – am Handy je Untermenü eine
Zeile, die sich waagrecht wischen lässt.

## 2 Mit den Agenten arbeiten
- **Auftrag geben:** Kachel › „Nachricht“ (Art Auftrag weckt) – oder an den Lead, der verteilt.
- **Fragen beantworten:** Start oder Fragen; eine Rückfrage geht zurück an den Fragesteller, dessen Antwort erscheint im Verlauf der Frage.
- **Fragen parken:** Eine Frage, die du gerade nicht verfolgen willst, parkst du über *Parken* auf der Karte. Steht Text im
  Feld, ist das der Grund. Die Frage bleibt offen, steht aber in keiner offenen Liste, in keinem Zähler und in keiner
  Push-Erinnerung mehr. Unter *Geparkt* siehst du sie vollständig mit Zeit und Person und nimmst sie mit *Wieder aufnehmen*
  zurück. Antworten geht auch geparkt. Der TL und die Agenten parken mit `amw frage parken <nr> --grund "…"` (der Lead und
  der Fragesteller; auch über die TL-Brücke), `amw frage aufnehmen <nr>` holt sie zurück, `amw frage liste --geparkt`
  zeigt sie. Parken und Aufnehmen stehen im Verlauf der Frage, der Fragesteller bekommt eine Info.
- **Anhalten:** im Leitstand „Alle anhalten“ (alle oder einen Agenten) oder im Aktionsmenü ⋯ der Kachel „Anhalten (nur
  diesen)“; „Weiterarbeiten“ hebt auf. Agenten beginnen nichts Neues, Läufe starten nicht.
- **Starten, fortsetzen, beenden:** Aktionsmenü ⋯ der Kachel (oder Kachel › Übersicht). „Fortsetzen“ setzt die letzte
  Sitzung fort (Gesprächsverlauf bleibt), „Neue Sitzung beginnen“ startet frisch mit dem Startsatz. „Fehlende starten“
  im Leitstand startet alle, die laufen sollen und nicht laufen, nacheinander. Profil im Zahnrad › Agenten › Profil.
- **Sichern & beenden (z. B. vor einem Update):** im Leitstand für alle, im Aktionsmenü für einen. Der Agent bekommt
  die Bitte, seinen Stand festzuhalten und sich abzumelden (`amw abmelden`); sobald er abgemeldet ist, beendet die AMW
  seine Sitzung – nach 5 Minuten auch ohne Abmeldung. Das Fenster bleibt offen; „Starten / fortsetzen“ holt ihn zurück.
  Nur am PC.
- **Mitlesen:** Kachel › „Gespräch“ (oder in der Übersicht der Reiter *Gespräch*) zeigt, was der Agent mit Claude Code
  bespricht – live, ohne sein Fenster zu suchen. Deine Eingaben stehen rechts, Claudes Antworten links. Weckrufe der AMW,
  Aufgabenmeldungen und Zusammenfassungen sind klein dazwischen. Die Arbeitsschritte (Werkzeuge) sind je Strecke
  eingeklappt, „7 Arbeitsschritte · Bash, Read, Edit“. Aufgeklappt zeigt jeder Schritt Eingabe und Ergebnis, Fehler sind rot.
  Der Schalter *Arbeitsschritte* blendet sie ganz aus. *Ältere laden* blättert zurück, eine frühere Sitzung wählst du oben.
  Gelesen wird nur das Protokoll von Claude Code (`~/.claude/projects/…`), nichts wird dort geändert. Geheimnis-Muster
  (Schlüssel, `password=…`) sind immer verdeckt.
- **In Claude öffnen:** Läuft der Agent mit Fernsteuerung (Profil › Fernsteuerung, ab dem nächsten Start), öffnet der Knopf
  seine Sitzung auf claude.ai bzw. in der Claude-App am Handy. Dort schreibst du direkt mit ihm, das Terminal am PC bleibt
  gleichzeitig offen. Ohne Fernsteuerung oder bei beendeter Sitzung steht dort, was fehlt.
- **Zustand verstehen:** *arbeitet* · *frei* (wartet auf Nachrichten) · *wartet auf Freigabe* (im Fenster des Agenten
  fragt Claude Code um Erlaubnis – dorthin schauen) · *wartet auf Eingabe* · *Fehler* (z. B. Nutzungsgrenze erreicht).

## 3 Was Agenten mit `amw` tun
```
amw lesen --von CC1                       # offene Nachrichten (amw lesen 123: ganze Nachricht, gilt als gelesen)
amw erledigt 123 124 --von CC1
amw posten --an CC2 --art pruefbitte --kurz "…" --von CC1
amw schritt naechster --nehmen --von CC1  # nächster bereiter Schritt (aktiver Bogen zuerst)
amw aufgabe kriterium 1201 1 --von CC1    # Abnahmekriterium erfüllt
amw aufgabe fertig 1201 --beleg <commit> --zusammenfassung "…" --von CC1
amw lauf start --beschreibung "Build" --dauer 10 --warten --von CC1   # dann: amw lauf ende <nr> --rc 0
amw pruefung bitte --pruefer CC2 --zweig cc1-x --sha <commit> --von CC1
amw frage neu --an entwickler --kurz "…" --option "A=…" --option "B=…" --empfehlung A --grund "…" --von TL
amw taetigkeit "A1201 Login-Formular" --von CC1   # zeigt die Kachel „Gerade“
amw kontext --von CC1                     # Pflicht-Kontext
```
Alle Befehle: [befehle.md](befehle.md). `--von` kann entfallen, wenn `AMW_AGENT` gesetzt ist (Startskript, Hook).
Du selbst nimmst `--von Entwickler`. Den genauen Befehl (`python <AMW-Ordner>/amw-cli.py`) bekommen die Agenten im
Pflicht-Kontext; mit `<AMW-Ordner>\bin` im Pfad geht überall kurz `amw`.

## 4 Überwachung und Warnungen
- **Projekt-Server** (Testseiten, Editoren …): `amw server anmelden editor --port 8766 --start "pythonw C:/pfad/server.py"
  --ordner C:/pfad --neustart --zustaendig CC2` – Ausfall wird gemeldet, mit `--neustart` nach zwei Runden „aus“ neu
  gestartet (höchstens 3 je Stunde).
- **Stillstand:** Weckruf seit 30 min ohne Reaktion; Lauf länger als doppelt erwartet (ohne Angabe 90 min);
  Freigabe-Abfrage seit 2 min; Abbruch mit Fehler; Kontext ≥ 90 %; 5-Stunden-Grenze ≥ 90 %. Schwellen im Zahnrad › Projekt.
- Warnungen stehen oben auf der Startseite, gehen einmal als Nachricht an den Lead und als Push an dich.

## 5 Sichern und wiederherstellen
- `amw sichern` → `sicherung-<Datum>-<Uhrzeit>.db` neben der Datenbank (vollständige Kopie, auch im laufenden Betrieb);
  `amw sichern --ziel D:\Sicherung` legt sie in diesen Ordner (wird angelegt), `--ziel D:\x.db` als genau diese Datei.
- Wiederherstellen: Wächter anhalten (`amw dienst entfernen --ja` oder die Aufgabe in der Aufgabenplanung beenden),
  `daten\amw.db` durch die Sicherung ersetzen (die Dateien `amw.db-wal` und `amw.db-shm` daneben löschen), Wächter wieder
  einrichten bzw. starten.
- Die Dokumenten-Ablage (`dokumente/` neben der Datenbank) kopiert `amw sichern` nach `…-dokumente/` neben die
  Sicherung – nur, was dort noch fehlt ([anleitung-dokumente.md](anleitung-dokumente.md)).
- Vor jedem Update sichern (neue Versionen stellen die Datenbank beim ersten Schreibzugriff um).

## 6 Einstellungen dieses PCs
Zahnrad › Dieser PC, oder von Hand in `%LOCALAPPDATA%\amw\einstellungen.json` (JSON, nur Schlüssel, die von der
Vorgabe abweichen, z. B. `{"port": 8790}`). Wirkt nach `amw dienst neustart`.

| Schlüssel | Vorgabe | Bedeutung |
|---|---|---|
| `db_pfad` | `<AMW-Ordner>\daten\amw.db` | Datenbank (vollständiger Pfad, Ordner muss es geben) |
| `port` | 8780 | Port der Workbench auf 127.0.0.1 |
| `aufsicht_s` | 30 | Takt der Aufsicht in Sekunden (5–600) |
| `abgleich_hoch_s` | 30 | Online: frühestens so oft hochladen |
| `abgleich_puls_s` | 300 | Online: Lebenszeichen, auch ohne Änderung |
| `abgleich_eingang_s` | 15 | Online: so oft den Briefkasten abholen |
| `bruecke_an` | aus | Datei-Brücke für einen Agenten ohne direkten Datenbankzugriff (→ [architektur.md](architektur.md) §3) |
| `bruecke_absender` | TL | Kennung, als die Befehle der Brücke ausgeführt werden |
| `bruecke_kopie_s` | 60 | Lesekopie der Brücke höchstens so oft erneuern |
| `statusline_weiter` | leer | bisherige Statusline, die die Statusline-Brücke weiterreicht (setzt `amw einrichten`) |
| `claude_befehl` | `claude` | wie Claude Code gestartet wird (falls nötig mit vollem Pfad) |
