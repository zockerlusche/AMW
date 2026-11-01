# 13 · Ausbau zum vollständigen Lead-Werkzeug

**Status: in Arbeit.** Stand 01.11.2026. Auftrag: AMW soll aus Sicht des Anwenders alles abdecken, was ein Lead braucht,
der Projekte mit einem KI-Assistenten (Team-Lead-Agent) und mehreren Coding-Agenten baut – lieber etwas mehr als zu wenig.
Grundlage: Durchsicht der Oberfläche (Desktop und Handy, Bildschirmfotos aller Ansichten) und zwei Recherchen zu
Agenten-Workbenches und Projektplanung (Quellen §9).

Arbeitsweise: entwickelt wird in einer eigenen Arbeitskopie (Git-Worktree) mit einer Kopie der Datenbank und einer
Workbench auf eigenem Port – laufende Agenten benutzen den Code im Hauptordner live. Jede Stufe endet mit Tests,
Bildschirmfotos (Desktop 1440 px, Handy 390 px mit echter Geräte-Emulation), Release und Changelog.

## 1 Was dem Anwender heute fehlt (Befund)
| Bereich | Befund |
|---|---|
| Startseite | Nachrichten mit vollem Text verdrängen Fragen und Agenten nach unten; Nachträge zu Fragen erscheinen doppelt. |
| Kopfzeile | „9/7 Agenten“: Agenten, die nicht laufen sollen, zählen mit. |
| Handy | Agenten-Übersicht zweispaltig gequetscht (CSS-Reihenfolge), Menüpunkt „Einstellungen“ abgeschnitten. |
| Navigation | Zurück-Knopf und Links mit `#ansicht` wechseln die Ansicht nicht. |
| Aufgaben | Spalte „Läuft“ immer leer (Agenten setzen den Status selten); Karten ohne Alter. |
| Wissen | Notizen nirgends sichtbar. |
| Betrieb | Projekt-Server (z. B. eine Editor-Seite) fallen unbemerkt aus; hängende Agenten und Läufe fallen niemandem auf. |
| Unterwegs | Keine Benachrichtigung aufs Handy. |
| Kosten/Grenzen | Kein Überblick über Kontext-Füllstand, Nutzungsgrenzen und Kosten je Agent. |
| Agenten | Starten/Neustarten nur von Hand im Terminal; abgestürzte Agenten bleiben liegen. |
| Planung | Keine Ziele, Meilensteine, Spezifikationen, Abnahmekriterien, Abhängigkeiten, Prognose. |
| Lernen | Kein Rückblick je Meilenstein, kein Verlauf „was ist passiert, während ich weg war“. |
| Fremde Anwender | Doku ist projektbezogen gewachsen; eine Schritt-für-Schritt-Installation fehlt. |

## 2 Stufe A – Grundlage und Bedienbarkeit (0.10.0) ✔ 01.11.2026
- [x] Startseite neu geordnet: Warnungen → wartet auf dich (Fragen, mit „neuer Nachtrag“) → Agenten → Nachrichten (gekürzt, aufklappbar); Nachträge nur in der Frage, beim Beantworten erledigt.
- [x] Kopfzeile zählt laufende von den Agenten, die laufen sollen; außerplanmäßige getrennt.
- [x] Handy: Agenten-Übersicht einspaltig, Menü-Kurzname „Setup“, Nummern brechen nicht um.
- [x] Zurück-Knopf und `#ansicht`-Links funktionieren.
- [x] Aufgaben: „Läuft“ zeigt, woran Agenten gerade arbeiten; Alter/letzte Änderung je Karte.
- [x] Wissen: Reiter „Notizen“.
- [x] Überwachung Projekt-Server: `amw server anmelden|abmelden|liste|pruefen`, Wächter prüft je Runde, meldet Ausfall und Wiederkehr, Neustart nach zwei Runden „aus“, höchstens 3 je Stunde; Betrieb zeigt die Server.
- [x] Stillstand: Weckruf unbeantwortet (Vorgabe 30 min), Lauf über erwarteter Dauer (`lauf start --dauer`); Warnband auf der Startseite, Meldung an den Lead; Schwellen im Zahnrad.

## 3 Stufe B – Benachrichtigen (0.11.0)
- [ ] Push über **ntfy**, **Pushover** oder **Telegram** (wählbar, mehrere gleichzeitig möglich); Zugangsdaten nur in den PC-Einstellungen, nie in DB/Repo.
- [ ] Ereignisse wählbar: neue Frage an dich, Warnung (Server/Stillstand/Lauf), Agent wartet auf Eingabe, Halt, Rückblick.
- [ ] Nur Hinweise im Text („Neue Frage F123 von TL“), keine Inhalte; Link öffnet die Workbench bzw. Online-Seite.
- [ ] Ruhezeiten (z. B. 23–7 Uhr nur dringende), Probe-Knopf im Zahnrad.

## 4 Stufe C – Zustand, Kontext und Verbrauch je Agent (0.12.0)
- [ ] Claude-Code-Hooks `Notification` (wartet auf Eingabe/Freigabe), `Stop`, `StopFailure` (API-Fehler) → `amw hook ereignis`; die Kachel zeigt „wartet auf Eingabe seit …“, „Fehler“, „fertig“.
- [ ] Statusline-Brücke `amw statusline`: Kontext-Füllstand, 5-Stunden-Grenze, Kosten der Sitzung je Agent; Kachel und Übersicht zeigen Balken; Warnung bei hoher Füllung.
- [ ] Verbrauch je Agent und Tag (Kosten-Schätzung zum Listenpreis, Tokens) in Betrieb; Summe je Projekt.

## 5 Stufe D – Agenten steuern (0.13.0)
- [ ] Agenten-Profil: Ordner, Zusatzordner, Denkstufe, Modell, Startsatz, Rechte-Modus (im Zahnrad).
- [ ] „Starten“/„Beenden“ per Klick in der Workbench am PC (nie über die Online-Seite): neuer Terminal-Tab mit Claude, Kennung, Hook; Beenden der Sitzung des Agenten.
- [ ] Automatischer Neustart (Resume derselben Sitzung) eines abgestürzten Agenten mit Soll „an“, höchstens 3 je Stunde, mit Meldung.
- [ ] `amw agenten-start` erzeugt das Startskript aus den Profilen (ersetzt handgeschriebene Skripte).

## 6 Stufe E – Projektplanung (0.14.0)
Nach Kiro, GitHub Spec Kit, Taskmaster, Backlog.md, Claude Code Agent Teams, Linear (Agenten) – §9.
- [ ] **Leitbild** je Projekt: Ziel, Nicht-Ziele, Prinzipien mit Prüffrage; Teil des Pflicht-Kontexts der Agenten.
- [ ] **Bögen** (Meilensteine): Ziel, Reihenfolge, Status, Fortschritt (erledigt/gesamt, blockiert), Zieldatum.
- [ ] **Spezifikation** je Bogen in drei Teilen – Anforderungen, Entwurf, Schritte – mit Freigabe je Teil durch den Menschen; offene Punkte `[KLÄREN: …]` werden automatisch Fragen und blockieren die Freigabe.
- [ ] **Aufgaben erweitert**: Bogen, Abnahmekriterien (abhakbar), Abhängigkeiten (blockiert wird berechnet, Zyklusprüfung), Schätzung, Komplexität 1–10, Plan des Bearbeiters, Abschluss-Zusammenfassung, verantwortlich (Mensch/Agent).
- [ ] **Plan-Freigabe**: großer Schritt → Agent legt Plan vor, Lead/Mensch gibt frei, erst dann Umsetzung.
- [ ] **Nächster Schritt**: `amw schritt naechster` – der Agent nimmt sich atomar den nächsten freien Schritt seines Bogens/seiner Rolle.
- [ ] **Abnahme-Regel (DoD)**: projektweite Liste; „fertig“ nur mit allen Abnahmekriterien und, wo verlangt, grüner Prüfung.
- [ ] **Ansicht „Planung“**: Leitbild, Bögen mit Fortschrittsbalken, Bogen-Detail mit Spezifikation und Schritten in Wellen (was parallel geht), Bahnen je Agent.
- [ ] **Prognose-Zeitleiste (senkrecht)**: voraussichtliches Ende je Schritt und Bogen aus dem Durchsatz der letzten Tage (P50/P85), eigene Schritte des Menschen mit eigener Taktung.

## 7 Stufe F – Rückblick und Verlauf (0.15.0)
- [ ] **Rückblick je Bogen**: gut / schlecht / Maßnahme; eine Maßnahme kann als Beschluss oder Regel übernommen werden.
- [ ] **Verlauf (senkrecht)**: was wann passiert ist – Nachrichten, erledigte Schritte, Läufe, Prüfungen, Freigaben – je Tag und Agent filterbar.
- [ ] **„Seit du weg warst“**: Zusammenfassung seit dem letzten Besuch auf der Startseite (und als Push).

## 8 Stufe G – Für jeden Anwender (1.0.0)
- [ ] Repo neutral: keine Bezüge auf ein bestimmtes Projekt in Code, Doku, Changelog; projektbezogene Doku lokal in `intern/` (nicht veröffentlicht).
- [ ] Doku neu: Was AMW ist, Bausteine und Datenfluss (Agenten-Sitzungen, Hook, Kommandozeile, SQLite, Wächter, Workbench, Online-Speicher, Online-Seite), Reihenfolge der Einrichtung, Betrieb, Sicherheit, Fehlerbehebung.
- [ ] `amw einrichten`: geführte Einrichtung (Projekt, Agenten, Hook-Eintrag, Startskript, Wächter-Aufgabe, optional Online).
- [ ] Online-Teil Schritt für Schritt: Online-Speicher anlegen, Hoster per Git, Einrichtungs-Assistent, zweiter Faktor.
- [ ] Probe: ein frischer Agent installiert nach der Anleitung in einen leeren Ordner; jede Stolperstelle wird behoben.
- [ ] Online-Seite: alle neuen Ansichten im Spiegel, neue Schreibwege über den Briefkasten.

## 9 Quellen der Recherche (Auswahl)
Claude Code: agent-view, hooks, statusline, monitoring-usage, agent-teams, cross-session-messaging (code.claude.com/docs) ·
ntfy (docs.ntfy.sh), Pushover, Telegram Bot API · Kiro specs/steering (kiro.dev/docs) · GitHub Spec Kit
(github.com/github/spec-kit) · Taskmaster (docs.task-master.dev) · Backlog.md · BMAD-METHOD · Roo Code Boomerang ·
Cline Plan/Act · Linear Agents (linear.app/developers/agents) · Devin · GitHub Copilot cloud agent · Linear project graph
(Prognose) · Monte-Carlo-Prognose (prokanban.org).
