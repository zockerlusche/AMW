# 06 · Varianten

**Status: offen.** Ausarbeitung, Marktvergleich und Bewertung: CCamw (A1207, Phase 1). Entscheidung: Marcel.

## Lösungswege
| | Idee | Für | Wider |
|---|---|---|---|
| A | Heutiges System aufräumen (eine DB-Struktur, robuste Wache, neue Oberfläche) | wenig Umbau, alles Wissen bleibt | Altlasten-Gefahr, eigene Wartung |
| B | Auf ein fertiges Werkzeug umsteigen | fremde Pflege, erprobt | passt evtl. nicht zu Dauerbetrieb, Entwickler-Oberfläche, Gedächtnis |
| C | AMW als eigenes Produkt (eigenes Repo, sauber getrennt) | maßgeschneidert, später teilbar | größter Aufwand |
Mischformen sind erlaubt (z. B. C mit Bausteinen aus B).

## Datenbank-Optionen
| Option | Art | Kosten (Stand 01.11.2026, prüfen) | Passt zu |
|---|---|---|---|
| SQLite lokal | Datei | 0 | Einzelplatz, lokaler Bus (heute) |
| Postgres selbst betrieben | eigener Server/Webspace | Server-Kosten | volle Kontrolle |
| Neon (Postgres) | Cloud, Abrechnung nach Nutzung, schläft nach 5 min | Free: 100 CU-h, 1 GB je Projekt; Launch: 0,106 $/CU-h, 0,35 $/GB-Monat, kein Mindestbetrag | zentraler Speicher bei gebündeltem Abgleich |
| Supabase (Postgres) | Cloud mit Zusatzdiensten | Pro ca. 25 $/Monat | zu teuer für den Bedarf (Marcel 08:42) |
| Turso (libSQL) | Cloud-SQLite mit lokalen Kopien | prüfen | passt fachlich genau zu „lokal SQLite, zentral abgeglichen“ |
Grundsatz: Die Anwendung spricht über eine Datenzugriffs-Schicht, damit die Datenbank wechselbar bleibt (→ 01 Produktbild „Skalierbar“).

## Kostenschätzung zentraler Speicher (TL, grob)
- Datenmenge: Bus heute ca. 24 MB nach rund 6 Wochen → unter 1 GB für lange Zeit.
- Rechenzeit entscheidet: Neon rechnet die Zeit ab, in der die Datenbank wach ist (mind. 0,25 CU).
  - Abgleich alle paar Sekunden → nie schlafend → ca. 180 CU-h/Monat → über Free, ca. 19 $/Monat.
  - Abgleich gebündelt alle 15 min → ca. 8 h wach am Tag → ca. 60 CU-h/Monat → im Free-Rahmen.
  - Homepage liest nur den veröffentlichten Auszug → weckt die Datenbank nicht.
- Folge: Abgleich bündeln (→ 05 §7). Genaue Rechnung mit echten Schreibzahlen: CCamw.

## Wecken-Optionen
- Wache je Agent (heute) · Nachrichten zwischen Claude-Code-Sitzungen · Dienst, der alle Agenten überwacht · Kombination mit Rückfall.

## TL-Vorschlag (01.11., noch nicht entschieden)
- **Ein Dienst statt einer Wache je Agent:** läuft außerhalb von Claude Code (Windows-Dienst bzw. Container), wird bei Speicherknappheit nicht beendet, weckt die Agenten.
- **Lokal zuerst:** SQLite je Rechner mit neuer fester Struktur, jede Tabelle mit Projekt-Spalte; zentral abgeglichen (→ 05 §7).
- **Zentraler Speicher:** Postgres mit Abrechnung nach Nutzung (z. B. Neon) oder Turso; Wahl nach CCamws Rechnung.
- **Server:** Python als Dienst mit Selbst-Neustart; Oberfläche als eine Web-App.
- **Datenzugriffs-Schicht:** Datenbank wechselbar ohne Umbau der Anwendung.
- **Projekt-Spezifisches als Erweiterung** (→ 02 §11).
- Erwartung: Fertige Frameworks (CrewAI, LangGraph …) zielen auf automatisierte Abläufe, nicht auf ein Team aus Claude-Code-Sitzungen mit menschlichem Entwickler → vermutlich schlanker Eigenbau, der Claude-Code-Bordmittel zum Wecken nutzt. Prüfung: CCamw.

## Marktvergleich (zu prüfen)
Claude Code Agent-Teams und Sitzungs-Nachrichten · Claude Agent SDK · CrewAI · LangGraph · AutoGen · MetaGPT · OpenHands · Projekt-/Kanban-Werkzeuge.
Prüffragen: Dauerbetrieb über Tage? Wecken? Gedächtnis über Komprimierung? Oberfläche für den Entwickler? Lokal betreibbar? Aufwand?

## Kriterien für die Bewertung
Zuverlässigkeit · Ordnung (eine Quelle) · Bedienbarkeit für den Entwickler · Aufwand · Speicherbedarf · Token-Kosten · Erweiterbarkeit (weitere Projekte) · Produktfähigkeit.
