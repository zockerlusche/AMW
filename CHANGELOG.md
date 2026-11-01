# Änderungen · Changelog

Versionen nach dem Schema MAJOR.MINOR.PATCH: MINOR für neue Fähigkeiten, PATCH für Korrekturen; 1.0.0, wenn die AMW
für andere Teams ohne Begleitung einsetzbar ist (Stufe 3, → doc/10 §4). Die Nummer steht in `amw/__init__.py`,
`amw --version` zeigt sie, die Workbench in der Kopfzeile. Zu jeder Version gibt es den Git-Tag `vX.Y.Z`.

## 0.9.1 – 01.11.2026 · Keine falschen Anmeldungen mehr
- Eine Hintergrund-Sitzung ohne Fenster hatte sich beim Umzug als CC5 angemeldet; Weckrufe für CC5 gingen dorthin statt
  ins Fenster (TL #16500). Jetzt: Hintergrund-Sitzungen (Claude Code `kind=bg`) werden nie angemeldet, und
  `amw anmelden` löst eine noch lebende andere Sitzung derselben Kennung nur mit `--ersetzen` ab. Erkannt über
  `~/.claude/sessions/<pid>.json` (Postfach → Prozess).
- `amw dienst status` zeigt je Agent: Sitzung, Prozess, mit Fenster oder Hintergrund („← PRÜFEN“).

## 0.9.0 – 01.11.2026 · Warteschlange für Rechen-Läufe
- `amw lauf start … --warten`: Ist der Platz belegt (ein schwerer Lauf, ein Schirm-Lauf zur Zeit) oder der Speicher
  knapp, wird der Lauf eingereiht statt abgelehnt. Sobald er dran ist, startet der Wächter ihn und weckt den Agenten mit
  einer Freigabe „Lx ist dran“. Niemand überholt: Wer ohne `--warten` startet, während jemand für denselben Platz
  wartet, wird abgelehnt (TL #16445: CC5 kam vorher 4× nicht dran).
- `amw lauf vorziehen <nr>` (Lead/Entwickler, auch über die Brücke), `amw lauf liste` zeigt die Schlange,
  `amw lauf ende <nr> --abgebrochen` nimmt einen Lauf aus der Schlange oder gibt einen reservierten Platz frei.
  Agenten ohne laufende Sitzung werden übersprungen, bis sie wieder da sind.
- Agenten-Kachel: „offen“ zählt nur, was eine Handlung braucht (weckende Arten); reine Info zählt nicht mehr
  (Wunsch Marcel). Die Übersicht zeigt weiter alles.
- Korrektur: offene Prüfbitten erschienen in der Agenten-Übersicht nie.
- Datenbank-Schema 3 (`lauf.rang`, `amw/migration_3.sql`).

## 0.8.0 – 01.11.2026 · Gesprächsverlauf je Frage
- Jede Frage hat einen Verlauf wie im Chat (Fragesteller links, du rechts): Rückfragen, Antworten des Fragestellers,
  deine Antwort – nichts wird mehr überschrieben (Wunsch Marcel). Online erscheint eine Rückfrage sofort als „unterwegs“.
- `amw frage nachtrag <nr> --text …` (Fragesteller oder Lead) und `amw frage verlauf <nr>`; eine Nachricht mit
  `--antwort-auf <Rückfrage-Nachricht>` wird automatisch als Nachtrag erkannt. Nachträge erscheinen auch unter
  „Nachrichten an dich“.
- Karte zeigt „wartet auf TL“, solange eine Rückfrage offen ist.
- Datenbank-Schema 2 (Tabelle `frage_verlauf`, gegen Löschen geschützt); ältere Datenbanken werden beim ersten
  Schreibzugriff umgestellt (`amw/migration_2.sql`), bisherige Rückfragen werden übernommen.

## 0.7.1 – 01.11.2026 · Übersicht lesbarer
- Agenten-Übersicht etwa zwei Drittel breit (vorher überschrieb die allgemeine Dialog-Breite von 520 px), zwei Spalten:
  links „Kommt noch“, Läufe, Prüfbitten – rechts neue Nachrichten, letzte Meldungen; auf dem Handy eine Spalte.
- Jeder Eintrag als eigener Block mit Kopfzeile (Nummer, Kennzeichen, Zeit) und farbigem Rand nach Status/Art;
  Anzahl je Abschnitt; Esc schließt (Wunsch Marcel).

## 0.7.0 – 01.11.2026 · Agenten auf einen Blick
- Agenten-Kachel: „Gerade“ (eigene Angabe › laufende Aufgabe › Aufgabe aus der letzten Meldung), „Zuletzt“ (letzte
  Meldung), offen zählt nur Neues seit dem Umzug, Altbestand aus dem alten Bus getrennt (Wunsch Marcel/TL #16353).
- Klick auf die Kachel: Übersicht – macht gerade, kommt noch (Aufgaben nach Rang), Rechen-Läufe, Prüfbitten,
  neue Nachrichten an ihn, seine letzten Meldungen; auch online.
- `amw taetigkeit "…" [--aufgabe N]`: Agenten sagen selbst, woran sie sind (auch über die Brücke).
- Start der Agenten: Startskript setzt `AMW_AGENT`, der SessionStart-Hook (`amw-hook.py`) meldet neue Sitzungen an.

## 0.6.0 – 01.11.2026 · Suche online
- Suche auf der Online-Seite: der PC lädt einen gepackten Suchindex hoch (Aufgaben, Beschlüsse, Fragen, Wortlaut
  vollständig, die letzten 2000 Nachrichten mit Kurztext; höchstens alle 15 min, nur bei Änderung).
- Doku: Fahrplan und Stufen auf den Stand gebracht (Stufe 1 und 2 in Betrieb).

## 0.5.0 – 01.11.2026 · Einstellungen
- Zahnrad „Einstellungen“ (lokal und online): Projekt (Takt, Speicher-Grenze), Agenten (anlegen, Rolle, Soll, Grenzen,
  Rundschreiben, Puls-Grenze), Online-Seite (Abmelden nach Leerlauf, längste Sitzung, Sperre nach Fehlversuchen).
- „Dieser PC“ (Datenbank-Pfad, Port, Takte von Wächter, Abgleich und Brücke) und „Online-Speicher“ (Adresse,
  Schlüssel, Abgleich) nur am PC änderbar, online nur sichtbar; der Schlüssel wird nie angezeigt.
  Gespeichert in `%LOCALAPPDATA%\amw\einstellungen.json`; `amw dienst neustart` übernimmt sie.
- Version unten links in der Workbench.
- `amw notiz entfernen <schlüssel …>` – nur Lead/Entwickler oder mit `--beschluss` auf einen geltenden Beschluss.
- Korrektur: Briefkasten-Einträge werden an Nummer, Zeit und Inhalt erkannt (eine neue Online-Datenbank zählt wieder ab 1);
  Einstellungen aus dem Briefkasten gehen in denselben Online-Speicher.

## 0.4.0 – 01.11.2026 · Online (Stufe 2)
- Workbench im Netz: PHP-Seite (Zweig `web`) über Turso – Schaufenster (Ansichten vom PC) + Briefkasten (Antworten,
  Nachrichten, Gelesen, Halt, Weiter); der PC bleibt aus dem Netz unerreichbar.
- Anmeldung mit Passwort + Einmalcode (TOTP, RFC 6238), QR-Code ohne fremde Bibliothek, Sperre nach Fehlversuchen.
- Einrichtungs-Assistent im Browser für jeden Anwender; `amw web einrichten` am PC. Die Seite speichert ihre
  Konfiguration selbst außerhalb des Deploy-Ordners.
- Nachrichten an den Entwickler (Empfänger `Entwickler`), in der Workbench „Nachrichten an dich“ mit Antworten/Gelesen.
- Datei-Brücke für Sitzungen ohne direkten Datenbankzugriff (TL in einer VM): Lesekopie ohne WAL, Befehlsdateien, Puls.
- Workbench aktualisiert still: keine Einblend-Animation und kein Sprung nach oben beim Selbst-Aktualisieren.
- Versionierung: `amw --version`, Anzeige in der Workbench, CHANGELOG, Git-Tags.

## 0.3.0 – 01.11.2026 · Umzug des LayerIT-Teams
- LayerIT-Bus übernommen (alle Zählungen gleich), Wächter als geplante Aufgabe „AMW Dienst“.
- `amw anmelden` für laufende Sitzungen ohne Neustart, `amw-cli.py` ohne PYTHONPATH, `--von` auch hinter dem Befehl.
- Umzugs-Sperre im alten Bus (Rückweg: Schalter-Datei), Compact-Hook liefert den Kontext aus der AMW.
- Zeiten in Ortszeit.

## 0.2.0 – 01.11.2026 · Stufe 1 vollständig
- Kommandozeile für TL und Agenten vollständig (Läufe, Prüfungen, Anweisungen, Rezepte, Wortlaut, Beschlüsse, Regeln,
  Notizen, Release Notes).
- Workbench zweisprachig (DE/EN) und fürs Handy; Nachricht an Agenten; Takt für den Lead.
- Einrichtung des Wächters vorbereitet (`amw dienst`), Hook-Einstellungen (`amw hook zeige`).

## 0.1.0 – 01.11.2026 · Stufe 1 Kern
- Datenmodell (18 Tabellen), Datenzugriff, Fachlogik, CLI `amw`.
- Wächter: weckt Agenten über die Pipe ihrer Claude-Code-Sitzung; SessionStart-Hook mit Pflicht-Kontext.
- Übernahme aus dem LayerIT-Bus (nur lesend); Workbench-Oberfläche (Leitstand).
