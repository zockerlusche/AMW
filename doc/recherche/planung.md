# Recherche: Projektplanung (Methodik und Werkzeuge) – Grundlage für Stufe E

Stand 01.11.2026. Zusammenfassung zweier Recherchen; Quellen am Ende. „(u)“ = nur Sekundärquelle.

## 1 Ablauf guter Planung (hybrid aus PMBOK/PRINCE2, Scrum, Kanban)
1. **Leitbild/Charter:** Problem, Nutzen, 2–5 SMART-Ziele mit Kennzahl, Annahmen, Zeitrahmen.
2. **Umfang und Nicht-Ziele** (bremsen Agenten, die mehr bauen als verlangt).
3. **Beteiligte / RACI:** genau ein Verantwortlicher (Accountable) je Aufgabe.
4. **Anforderungen:** Story oder „WHEN … THE SYSTEM SHALL …“ (EARS); ID, Priorität, Abnahmekriterien (Given/When/Then).
5. **Strukturplan (WBS):** nach Liefergegenständen; 100 %-Regel (Kinder = ganze Arbeit des Elternteils); unterste Ebene Arbeitspakete.
6. **Meilensteine/Bögen** mit prüfbarem Abnahmekriterium (Gate), nicht nur Datum.
7. **Abhängigkeiten:** FS (Normalfall), SS, FF, SF; Wartezeit (Lag); externe Abhängigkeiten.
8. **Schätzung:** Drei-Punkt/PERT E = (O + 4M + P) / 6, σ = (P − O) / 6 (Pfad: Varianzen addieren); Größen (S/M/L) oder Punkte; Referenzklasse aus eigener Historie.
9. **Kritischer Pfad:** Vorwärts-/Rückwärtsrechnung, Puffer; kritisch = Puffer 0.
10. **Kapazität und Ausgleich:** Ressourcen (Mensch, Agenten, knappe Maschinenplätze wie „ein schwerer Lauf zur Zeit“).
11. **Risikoregister:** Ursache/Ereignis/Wirkung, Wahrscheinlichkeit × Auswirkung (1–5), Strategie (vermeiden, übertragen, mindern, akzeptieren), Verantwortlicher, Auslöser, Maßnahme.
12. **Status:** RAG (rot/gelb/grün) je Termin, Umfang, Qualität, Risiko – nach Regeln berechnet; feste Taktung.
13. **Änderungssteuerung:** Änderungsantrag mit Wirkung → Entscheidung → bewusst neue Baseline.
14. **Baseline vs. Ist:** Plan einfrieren, Abweichung messen.
15. **Definition of Ready / Done:** Ready = Spec, Abnahmekriterien, Abhängigkeiten, Dateibereich; Done = gilt für das Ergebnis.
16. **Abschluss:** Abnahme, Übergabe offener Punkte, Rückblick (gut / schlecht / ändern), Lessons Learned → Schätzhistorie.

Agil dazu: Roadmap Jetzt/Als Nächstes/Später; Epic → Feature → Story → Aufgabe (INVEST); Priorisierung MoSCoW, WSJF
((Wert + Zeitkritik + Risikominderung) ÷ Größe), RICE; Kanban: WIP-Grenzen, Durchsatz, Alter, Durchlaufzeit,
Zielwert „85 % in ≤ N Tagen“; Burn-up (zeigt Umfangswachstum); Monte-Carlo-Prognose aus Tagesdurchsatz → P50/P85.

## 2 Besonderheiten mit KI-Agenten + einem Menschen
- **Der Mensch ist der Engpass:** Freigaben, Fragen, Prüfungen als eigene, blockierende Punkte; Kapazität (Std/Woche) und WIP des Menschen.
- **Aufgaben-Spec vor „bereit“:** Ziel, Nicht-Ziele, Dateibereich, Abnahmekriterien, **Prüfbefehl**, Abbruchbedingung, erwarteter Beleg (Anthropic Best Practices: Befehl + Ausgabe als Beleg verlangen).
- Fünf Fragen vor unbeaufsichtigter Arbeit: Weiß der Agent, wann er fertig ist? Kann er selbst prüfen? Was darf er anfassen? Was stoppt ihn? Wer zeichnet ab?
- **Agent Teams (Anthropic):** gemeinsame Aufgabenliste, pending/in progress/completed, blockiert = offene Abhängigkeit; 5–6 Aufgaben je Agent; jeder Agent eigene Dateien; Quality-Gates per Hook; Status kann nachhinken.
- **Lange Läufe (Anthropic):** Feature-Liste mit „passes“-Flag (nur das Flag ändern), Fortschrittsdatei, ein Feature je Sitzung, Ende sauber und zusammenführbar, Start mit Orientierung.
- **Spec Kit / Kiro:** Phasen Spezifizieren → Planen → Aufgaben → Umsetzen, jede mit Freigabe; stabile IDs; Wellen aus dem Abhängigkeitsgraphen (Welle nacheinander, innen parallel); `[NEEDS CLARIFICATION]`-Marker → Fragen, nicht raten.
- **Taskmaster:** PRD → Aufgaben, Komplexität 1–10 mit empfohlener Teilung, `next` wählt nach Abhängigkeiten, Kurskorrektur schreibt Folgeaufgaben um.
- **Backlog.md:** DoD-Vorlage je Aufgabe, Plan steht in der Aufgabe vor dem Code, Abnahmekriterien abhakbar.
- **Linear (Agenten):** Mensch verantwortlich, Agent bearbeitet; typisierte Aktivitäten; Plan-Schritte pending/inProgress/completed/canceled; Zustand awaitingInput/stale.
- **Roo Boomerang:** Teilaufgabe läuft isoliert, nur die Zusammenfassung kommt zurück (Pflicht-Zusammenfassung).
- Schätzung: Agenten-Laufzeit und Prüfzeit des Menschen getrennt; Durchlaufzeit wird oft vom Warten auf den Menschen bestimmt.

## 3 Prüfliste (das Werkzeug muss beantworten können)
1 SMART-Ziele und Nicht-Ziele vorhanden? · 2 Jede Anforderung von ≥ 1 Aufgabe abgedeckt? · 3 Jede Aufgabe auf Anforderung/Ziel rückführbar? ·
4 100 %-Regel je Strukturelement? · 5 Zu große Aufgaben? · 6 Aufgaben ohne DoR (Kriterien, Prüfbefehl, Dateibereich)? ·
7 Kritischer Pfad und Puffer? · 8 Zyklen/verwaiste Abhängigkeiten? · 9 Blockiert wodurch? · 10 Was wartet auf den Menschen, seit wann, was hängt dahinter? ·
11 Stunden Menschen-Arbeit diese Woche vs. Kapazität? · 12 Agenten frei/belegt/hängend? · 13 Knappe Plätze überbucht? · 14 Überlappende Dateien? ·
15 Wann ist Meilenstein X fertig (P50/P85)? · 16 Wie viel bis Datum Y (P85)? · 17 Ist vs. Baseline je Meilenstein? · 18 Aufgaben über dem Alterszielwert? ·
19 WIP-Grenze überschritten (Spalte, Agent, Mensch)? · 20 Durchsatz/Durchlaufzeit-Trend? · 21 Top-Risiken mit Verantwortlichem und Maßnahme? · 22 Risiko-Auslöser eingetreten? ·
23 Offene/dokumentierte Entscheidungen? · 24 Offene Änderungsanträge und ihre Wirkung? · 25 Verantwortlicher je Aufgabe? · 26 Erledigt ohne Abnahme-Beleg? ·
27 Zurückgewiesene Aufgaben, Nacharbeit-Quote? · 28 RAG je Dimension mit Begründung? · 29 Was hat sich seit dem letzten Bericht geändert? ·
30 Lessons Learned in Schätzungen? · 31 Umfangswachstum im Burn-up? · 32 Meilensteine ohne prüfbares Kriterium?

## 4 Datenmodell-Vorschlag (Recherche) und Ansichten
Projekt (Leitbild, Ziele, Nicht-Ziele, RAG, Baseline, DoD) · Anforderung (ID, Text, Priorität, Kriterien, Status) ·
Arbeitselement (Eltern, Ebene, Spec, Kriterien, Prüfbefehl, Dateibereich, DoR, Schätzung O/M/P, Ressourcenklasse,
wartet auf Mensch, Status, Zeitstempel bereit/start/fertig) · Anforderung↔Element · Abhängigkeit (Typ, Lag, extern) ·
Ressource (Mensch/Agent/Maschine, Kapazität, WIP) · Zuweisung (RACI) · Meilenstein (Termin, Gate, P50/P85, Baseline) ·
Risiko · Entscheidung/Frage · Änderungsantrag · Baseline · Ereignis-Log (alt→neu, Beleg) · Abnahme (Prüfer, Ergebnis, Beleg) · Rückblick.

Ansichten: „Mein Eingang“ (wartet auf den Menschen, nach Folgewirkung sortiert) · senkrechte Zeitleiste mit Heute-Linie,
Baseline- und Prognosebalken, P50/P85 · Board mit WIP und Alter · Kapazität · Roadmap Jetzt/Nächstes/Später ·
Abhängigkeiten/kritischer Pfad · Risiko-Heatmap 5×5 · Rückverfolgbarkeit Anforderung↔Aufgabe↔Beleg · Statusbericht (RAG, Burn-up, Änderungen).

## Quellen
code.claude.com/docs/en/best-practices · code.claude.com/docs/en/agent-teams ·
anthropic.com/engineering/effective-harnesses-for-long-running-agents · github.com/github/spec-kit (+ spec-driven.md, GitHub-Blog) ·
kiro.dev/docs/specs, kiro.dev/docs/steering · docs.task-master.dev · github.com/MrLesk/Backlog.md · github.com/bmad-code-org/BMAD-METHOD (u) ·
linear.app/developers/agents, linear.app/docs/project-graph · roocodeinc.github.io/Roo-Code/features/boomerang-tasks ·
docs.cline.bot/features/plan-and-act · kanbanguides.org (2020.12) · prokanban.org (SLE, Forecasting) · scrumguides.org ·
atlassian.com (RACI) · Wikipedia WBS/INVEST · martinfowler.com/bliki/GivenWhenThen · WSJF/RICE-Übersichten (rework.com).
