# 07 · Fahrplan

| Phase | Inhalt | Wer | Stand |
|---|---|---|---|
| 0 | Verzeichnis F:\amw, Doku-Gerüst, lokales git | Marcel, TL, CCamw | erledigt 01.11. |
| 1 | Inventur (03), Erfahrungen (04), Befragung aller Agenten, Marktvergleich + Varianten + Kosten (06), Architektur + Stufen (10) | CCamw (seit 01.11. 08:47 allein verantwortlich) | erledigt 01.11. |
| 2 | Entscheidungen des Entwicklers (unten) | Marcel | E1–E3 entschieden 01.11. 08:58 |
| 3 | Stufe 0 Proben (→ 10 §4) | CCamw | P2 grün 01.11. 09:10; P1 zurückgestellt (Dienst macht sie hinfällig); P6/P7 vor Stufe 2 |
| 4 | Stufe 1 Lokal: amw.db, CLI, amw-dienst, Hook, Workbench-Seite, Übernahme aus bus.db (→ 10 §4–§6) | CCamw; Auskünfte von CC3 (Bus/Wache) und CC5 (Oberfläche) | läuft – fertig 01.11.: Datenmodell, CLI, Hook, Wächter (Ende-zu-Ende an CCamw erprobt), Übernahme aus bus.db (Probe: alle Zählungen gleich), Workbench-Seite (Start, Fragen mit Antwort per Klick, Aufgaben, Wissen, Betrieb, Release Notes, Halt), 24 Tests; offen: Einrichtung als geplante Aufgabe (E7), Probebetrieb mit echten Daten |
| 5 | Umschalten LayerIT auf die AMW (ohne Datenverlust) | Marcel gibt frei | nach Stufe 1 |
| 6 | Stufe 2 Unterwegs (Spiegel, Anmeldung, Veröffentlichen) | CCamw | wenn Stufe 1 trägt |
| 7 | Stufe 3 Produkt (Installer, mehrere Nutzer/Rechner, eigenes Repo privat; öffentlich erst, wenn es im Betrieb trägt) | CCamw, Marcel | später |

## Brücke bis dahin
- A1206 (CC3): Fragen-Seite der heutigen Bus-Ansicht reparieren – Antworten direkt in die Fragen, Vorgeschichte sichtbar. Hilft sofort; die Workbench-Seite der Stufe 1 löst sie später ab.

## Entscheidungen (Marcel)
| Nr | Entscheidung | Stand |
|---|---|---|
| E1 | Ablage der AMW-Entscheidungen: in F:\amw\doc (07 + 09, git), nicht im LayerIT-Bus; später in der AMW-Datenbank | **entschieden** 01.11. 08:58 |
| E2 | Grundrichtung: Variante C (eigenes Produkt) in Stufen – erst lokal, dann unterwegs, dann Produkt für andere (→ 06 §3, 10 §1/§4) | **entschieden** 01.11. 08:58 |
| E3 | Freigabe Stufe 0 (Proben nur an CCamws eigener Sitzung) und Bau von Stufe 1 in F:\amw, ohne Eingriff in LayerIT und den heutigen Bus; Umschalten der LayerIT-Agenten nur mit Marcels Wort | **entschieden** 01.11. 08:58 |
| E4 | Zentrale Datenbank für Stufe 2: CCamw wählt die Plattform mit Begründung, Marcel legt das Konto an (Marcel 01.11. 09:19) | **Wahl CCamw 01.11.: Turso** (Begründung → 06 §7); Konto legt Marcel erst zu Beginn von Stufe 2 an |
| E5 | Zeitpunkt eigenes Repo (Stufe 3) | offen |
| E7 | amw-dienst als geplante Aufgabe unter Marcels Benutzer anlegen (ersetzt die Wachen je Agent) | grundsätzlich klar (Marcel 01.11. 09:19); Anlegen erst nach Rückfrage, Ende Stufe 1 |
| E6 | Umschalten LayerIT auf die AMW (Phase 5): entscheiden Marcel und CCamw gemeinsam; CCamw meldet, wenn der Punkt erreicht ist. Dabei mit zu klären: Altbestand offener Empfänge (Probe-Übernahme 01.11.: TL 2 767, CC4 461, CC2 322 …, → 04 #16) – übernehmen wie er ist oder vor einem Stichtag als „gelesen“ führen | offen, nach Stufe 1 |

## Regeln für diese Doku
→ README „Leseregel“.
