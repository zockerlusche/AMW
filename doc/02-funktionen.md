# 02 · Funktionen

Sicht des Entwicklers. Jede Funktion steht einmal; Betriebsanforderungen → 05.

## 0 Oberfläche (was der Mensch sieht)
- **Startseite:** oben die Leiste „wartet auf dich“ (offene Fragen, Freigaben, Abnahmen) – in 10 Sekunden klar, was der Entwickler tun muss. Darunter je Agent eine Kachel: Zustand, aktuelle Aufgabe, letzter Puls.
- **Navigation:** Fragen · Arbeit (Board) · Zeitleiste · Regeln · Agenten · Release Notes · Projekt-Werkzeuge · Einstellungen; Projekt-Wahl oben.
- **Grundsatz:** Inhalte für den Menschen strukturiert – kurze Karten, Details aufklappbar, keine Roh-Tabellen.
- **Sprachen:** Oberfläche auf Deutsch und Englisch, umschaltbar (Marcel 01.11.). Inhalte aus der Datenbank (Fragen, Beschlüsse, Wortlaut) bleiben in ihrer Originalsprache.
- **Handy:** Die Oberfläche ist für Handy-Bildschirme optimiert – vor allem Fragen beantworten, Start, Halt (Marcel 01.11.). Erreichbar von unterwegs erst mit Stufe 2 (→ 10 §4); in Stufe 1 nur am PC selbst (Server nur auf 127.0.0.1).

## 1 Einstellungen
- **Einrichtungs-Assistent** beim ersten Start: Betriebsart (nur lokal / lokal + zentral / zentral), Datenbank, Administrator-Konto.
- **Projekte** anlegen/wählen, Pfade (Repo, Arbeitsordner, Archiv), Sprache, Zeitzone.
- **Datenbank und Abgleich:** lokale Datenbank, zentrale Datenbank (Adresse, Verbindung testen), Abgleich-Takt, Stand des letzten Abgleichs, Konflikte.
- **Benutzer und Rechte:** Konten, Rollen (Administrator, Entwickler, Leser), Anmeldung mit zweitem Faktor, aktive Sitzungen.
- **Zugangsschlüssel:** je Agent und je Rechner ein eigener Schlüssel mit begrenzten Rechten, widerrufbar; Schlüssel werden nie angezeigt oder gespeichert, nur ihr Fingerabdruck.
- **Veröffentlichung:** Ziel-Homepage, was öffentlich wird (Release Notes, Blog), Freigabe vor Veröffentlichung.
- **Sicherung:** Zeitplan, Ziel, Wiederherstellung testen.
- Regeln je Ebene: **Arbeitsregeln** (gelten für alle Projekte) und **Projektregeln** (z. B. LayerIT-Baugesetz) – je Regel genau eine gültige Fassung.
- Ressourcen-Grenzen: z. B. „nur ein Rechen-Lauf zur Zeit“, „≥ 8 GB frei“, „Schirm nur ohne Fernwartung“.

## 2 Agenten
- Agenten **definieren**: Kennung, Rolle, Fähigkeiten, Grenzen (z. B. „CC7 nur 3D“), Werkzeug-Version, Startbefehl.
- **Status je Agent**: arbeitet / wartet / schläft / tot, letzter Puls, aktuelle Aufgabe, Wache läuft ja/nein.
- Aktionen: wecken, Auftrag geben, pausieren; Hinweis, wenn eine Meldung ungelesen liegt.

## 3 Projekte und Übersicht
- Je Projekt: Ziel, Meilensteine, Themen, Zweige/Stände, aktueller Testbuild.
- **Wer macht was** auf einen Blick: Agent → Aufgabe → Status → wartet auf wen.

## 4 Aufgaben
- Status: wartet / läuft / blockiert / fertig / verworfen. Einstufung: aktiv / keine Priorität / geparkt / Brainstorming.
- Felder: Auftraggeber, Agent, Beschreibung, Belege (Commit, Datei:Zeile), Abhängigkeiten, Prüfer.
- Ansichten: offen, geparkt, Brainstorming, erledigt; Filter je Agent/Thema.

## 5 Timeline
- Zeitstrahl je Projekt: Beschlüsse, Merges, Testbuilds, Releases, Abnahmen; Prognose offener Meilensteine.

## 6 Fragen und Antworten
- Jede Frage an den Entwickler hat ein **festes Format**: Kurzfrage, worum es geht, Optionen, Empfehlung + Grund, Fundstellen.
- **Vorgeschichte aufklappbar**: verknüpfte Aufgaben, Beschlüsse, Wortlaut, Nachrichten, Vorgänger-Fragen.
- Antworten per Klick (Empfehlung / andere Option / eigener Text) oder **Rückfrage** – direkt gespeichert, der TL wird benachrichtigt.
- Der TL arbeitet beantwortete Fragen bei jedem Sync ab und erzeugt daraus Arbeit.

## 7 Beschlüsse, Regeln, Wortlaut
- **Wortlaut** des Entwicklers vollständig und unverändert.
- **Beschlüsse**: was gilt, Quelle, ersetzt durch.
- **Regeln**: gültiger Stand, keine Altlasten (Verlauf im System, nicht im Text).

## 8 Kommunikation
- Nachrichten TL ↔ Agenten und Agent ↔ Agent, direkt adressiert; Rundschreiben nur für Infos.
- Lesebestätigung; Wecken nur bei handlungspflichtigen Nachrichten (→ 05).

## 9 Release Notes und Devlog
- **Lückenlos**: jeder Merge/Release mit Version, Inhalt, Belegen; daraus intern (Changelog) und öffentlich (Devlog/Patchnotes).
- **Veröffentlichen auf die Homepage** nur nach Freigabe des Entwicklers; die Homepage liest einen veröffentlichten Auszug, nie die Arbeits-Datenbank.

## 10 Suche
- Eine Suche über Aufgaben, Beschlüsse, Fragen, Wortlaut, Nachrichten, Regeln.

## 11 Projekt-Werkzeuge (Erweiterungen)
- Projekte können eigene Seiten einhängen. LayerIT heute: Objekt-Editor (Entwürfe, Klonen, Löschen vormerken), geplant: Werkbank (Objekte per Drag & Drop verbinden), Labor-Anbindung.
