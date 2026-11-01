# 01 · Zielbild

## Was die AMW ist
Ein Werkzeug, mit dem **ein Entwickler ein Team aus KI-Agenten** über Tage und Wochen führt – **Agentenmanagement und Projektführung in einem**. Es verbindet:
- die **Koordination der Agenten** (wer arbeitet woran, wer wird wann geweckt, wer prüft wen),
- die **Projektführung** (Aufgaben, Themen, Meilensteine, Timeline, Release Notes),
- den **Dialog mit dem Entwickler** (Fragen mit Empfehlung, Antworten, Rückfragen, Beschlüsse).

Name: **Agentenmanagement Workbench (AMW)**. Erstes Projekt darin: **LayerIT** (Godot-Spiel).

## Produktbild (Marcel 01.11. 08:42)
- **Allgemein:** für beliebige Projekte und andere Nutzer einsetzbar (z. B. Familie), nicht nur LayerIT.
- **Installierbar:** eine Installation mit Einrichtungs-Assistent, ohne Handarbeit in Dateien.
- **Lokal oder im Netz:** dieselbe Anwendung läuft auf dem eigenen PC oder auf einem Webserver.
- **Lokal zuerst, zentral abgeglichen:** jeder Rechner mit Agenten hat seinen lokalen Bus; ein zentraler Speicher gleicht ab, damit man von überall auf den Stand zugreift.
- **Skalierbar:** von einer lokalen Datei-Datenbank bis zu einer Datenbank im Netz, ohne die Anwendung zu wechseln.
- **Veröffentlichen:** Release Notes und Entwickler-Blog fließen aus der AMW auf die Projekt-Homepage.
- **Sicher:** Web-Sicherheit von Anfang an (→ 05 §6).
- **Übersichtlich:** der Inhalt ist für den Menschen strukturiert, nicht für die Agenten.

## Rollen
| Rolle | Wer | Aufgabe | Spricht mit |
|---|---|---|---|
| Entwickler | Marcel | entscheidet, gibt Richtung und Werte vor, prüft am Ende | nur mit dem TL (Chat) und über die Workbench-Oberfläche |
| Tech-Lead (TL) | ein Claude-Agent | übersetzt Marcels Wort in Aufgaben, verteilt, kontrolliert jedes Ergebnis gegen Marcels Modell, hält die Ordnung | mit Marcel (Chat) und den Agenten (Bus) |
| Agenten | CC1 … CCn | bauen, prüfen, mergen, rechnen – je nach Rolle | mit TL und untereinander (Bus) |

Beispiel-Rollen aus LayerIT: Bauer (Code), Prüfer (Tests, Abnahme am Schirm), Merge-Dienst, Werte/Balancing, Web/Grafik, Spezialist (nur 3D).

## Grundsätze
1. **Eine Quelle der Wahrheit.** Jede Information steht genau einmal; Verlauf ist Verlauf, gültiger Stand ist gültiger Stand.
2. **Nichts dazu erfinden.** Feste Struktur; neue Tabellen, Felder oder Ablagen nur mit Wort des Entwicklers.
3. **Der Entwickler sieht alles, ohne zu fragen.** Offene Fragen mit Vorgeschichte, wer macht was, was ist offen/geparkt/erledigt.
4. **Gedächtnis gehört ins System, nicht in den Agenten.** Agenten verlieren Wissen beim Komprimieren; das System hält es und bietet es gezielt an.
5. **Kontrolle vor Übernahme.** Ergebnisse von Agenten werden gegen das festgehaltene Modell geprüft, bevor der Entwickler sie sieht.
6. **Wie ein Produkt bauen.** Projekt-Spezifisches (z. B. LayerIT-Objekt-Editor) ist austauschbar; die AMW selbst kennt kein Spiel.

## Nicht-Ziele (vorerst)
- Kein offener Dienst für fremde Nutzer, solange es im eigenen Betrieb nicht trägt (installierbar für Bekannte ja, öffentliche Anmeldung nein).
- Kein Ersatz für die Werkzeuge der Agenten (Claude Code, git, Godot) – die AMW koordiniert sie.
