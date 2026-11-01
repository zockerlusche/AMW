# Betrieb: Arbeiten mit AMW

## 1 Die Workbench
http://127.0.0.1:8780 (am Handy dieselbe Seite über die Online-Adresse). Oben: Dienst, laufende Agenten,
freier Arbeitsspeicher, Suche (Aufgaben, Beschlüsse, Fragen, Wortlaut, Nachrichten), **HALT**.

| Ansicht | Wofür |
|---|---|
| **Start** | „Seit du weg warst“, Warnungen, **Wartet auf dich** (Freigaben, eigene Schritte, Fragen), Agenten-Kacheln (Zustand, was er gerade tut, Kontext/5-Stunden-Grenze; Klick = Übersicht mit Starten/Beenden), Nachrichten an dich |
| **Fragen** | Fragen an dich mit Optionen und Empfehlung; Antwort per Klick, eigener Text oder Rückfrage; Verlauf wie im Chat |
| **Planung** | Zeitleiste der Bögen mit Ampel und Prognose, Spezifikation freigeben, Leitbild, Risiken, Plan-Check, Protokoll |
| **Aufgaben** | Board (läuft · wartet · blockiert), geparkt, Pool, abgeschlossen; Filter nach Agent und Text |
| **Verlauf** | alles, was passiert ist, je Tag, filterbar |
| **Release Notes** | je Zusammenführung eine Zeile, Versionen |
| **Wissen** | Beschlüsse, Regeln, Wortlaut, Notizen; Suche |
| **Betrieb** | Projekt-Server, Verbrauch je Agent und Tag, Sperren, Sitzungen, Rechen-Läufe, Protokoll des Wächters |
| **Einstellungen** | Projekt, Agenten (mit Profil), Online-Seite, dieser PC, Online-Speicher, Benachrichtigungen |

Hell/Dunkel und Deutsch/Englisch unten links; die Seite aktualisiert Start und Betrieb von selbst (nicht während du tippst).

## 2 Mit den Agenten arbeiten
- **Auftrag geben:** Kachel › „Nachricht“ (Art Auftrag weckt) – oder an den Lead, der verteilt.
- **Fragen beantworten:** Start oder Fragen; eine Rückfrage geht zurück an den Fragesteller, dessen Antwort erscheint im Verlauf der Frage.
- **Anhalten:** HALT oben rechts (alle oder einen Agenten); „Weiter“ hebt auf. Agenten beginnen nichts Neues, Läufe starten nicht.
- **Starten, fortsetzen, beenden:** Kachel › Übersicht. „Fortsetzen“ setzt die letzte Sitzung fort (Gesprächsverlauf
  bleibt), „Neu beginnen“ startet frisch mit dem Startsatz. Profil im Zahnrad › Agenten › Profil.
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

## 4 Überwachung und Warnungen
- **Projekt-Server** (Testseiten, Editoren …): `amw server anmelden editor --port 8766 --start "pythonw C:/pfad/server.py"
  --ordner C:/pfad --neustart --zustaendig CC2` – Ausfall wird gemeldet, mit `--neustart` nach zwei Runden „aus“ neu
  gestartet (höchstens 3 je Stunde).
- **Stillstand:** Weckruf seit 30 min ohne Reaktion; Lauf länger als doppelt erwartet (ohne Angabe 90 min);
  Freigabe-Abfrage seit 2 min; Abbruch mit Fehler; Kontext ≥ 90 %; 5-Stunden-Grenze ≥ 90 %. Schwellen im Zahnrad › Projekt.
- Warnungen stehen oben auf der Startseite, gehen einmal als Nachricht an den Lead und als Push an dich.

## 5 Sichern und wiederherstellen
- `amw sichern` → `daten/sicherung-<Datum>.db` (vollständige Kopie, auch im laufenden Betrieb); `amw sichern --ziel D:\Sicherung`.
- Wiederherstellen: Wächter anhalten (`amw dienst entfernen --ja` oder die Aufgabe in der Aufgabenplanung beenden),
  `daten\amw.db` durch die Sicherung ersetzen (die Dateien `amw.db-wal` und `amw.db-shm` daneben löschen), Wächter wieder
  einrichten bzw. starten.
- Vor jedem Update sichern (neue Versionen stellen die Datenbank beim ersten Schreibzugriff um).

## 6 Einstellungen dieses PCs
Zahnrad › Dieser PC (oder `%LOCALAPPDATA%\amw\einstellungen.json`): Datenbank-Pfad, Port der Workbench, Takt der
Aufsicht, Abgleich, Datei-Brücke, weitergereichte Statusline, Befehl für Claude Code. Wirkt nach `amw dienst neustart`.
