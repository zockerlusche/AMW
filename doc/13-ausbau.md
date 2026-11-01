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

## 3 Stufe B – Benachrichtigen (0.11.0, zusammen mit C; Recherche: recherche/push.md) ✔ 02.11.2026
**Konzept.** Modul `amw/push.py`. Zugangsdaten und Vorlieben in `%LOCALAPPDATA%\amw\push.json` (nur dieser Benutzer;
nie Repo, nie Datenbank, nie Online-Speicher; im Zahnrad nur „gespeichert“). Anbieter ntfy (JSON an die Wurzel-URL,
Token optional), Pushover (Formular), Telegram (JSON, HTML-Maskierung) – jeder einzeln an/aus. Der Wächter sammelt je
Runde **Ereignisse** aus der Datenbank (neue Frage an den Menschen, neue Nachricht an ihn, Warnungen, Agent wartet auf
Freigabe/Eingabe seit ≥ 5 min, Halt gesetzt/aufgehoben) und schreibt sie mit eindeutigem Schlüssel in `push_versand`
(keine Doppelten). Erst ab dem Einschalten (kein Nachholen alter Dinge). Versand je Runde: Bündeln gleicher Art
(„3 neue Fragen“), Obergrenze 10 je Stunde (Rest als Sammelmeldung), gleiche Warnung frühestens nach 30 min erneut,
Ruhezeiten in lokaler Zeit (Vorgabe aus; während der Ruhe nur Priorität 5, Rest wird danach gesammelt zugestellt),
Erinnerung an eine unbeantwortete Frage einmal nach 60 min. Wiederholung nur bei Netzfehler/5xx/429 (≤ 3, Abstand
wachsend); Pushover-4xx nie. Text nur Metadaten + Link (Online-Seite, sonst Workbench). Versandprotokoll in Betrieb.
Bedienung: Zahnrad „Benachrichtigungen“ (nur am PC), Probe-Knopf je Anbieter mit Antwort der API;
`amw push status|probe|einrichten`. Gefundene Lücken: Telegram-Chat-ID ermitteln → `amw push telegram-chat` liest
getUpdates; ntfy-Topic erzeugen → zufällig beim Einrichten; Tagesrückblick → Stufe F.
- [x] push.json, Anbieter, Versand mit Wiederholung, Protokoll, Bündeln, Grenze, Ruhezeiten, Erinnerung
- [x] Ereignisquellen im Wächter; Zahnrad-Abschnitt mit Probe; CLI; Tests; Doku für das Handy (App, Abo)

## 4 Stufe C – Zustand, Kontext und Verbrauch je Agent (0.11.0; Recherche: recherche/workbenches.md) ✔ 02.11.2026
**Konzept.** (1) `amw-statusline.py` wird vor die vorhandene Statusline gehängt: merkt sich je Sitzung Kontext %,
5-h-/7-Tage-Grenze, Kosten, Modell, Denkstufe in `%LOCALAPPDATA%\amw\zustand\<sitzung>.json` (kein DB-Zugriff, weil
sehr häufig aufgerufen) und gibt die bisherige Statusline (Einstellung `statusline_weiter`) unverändert aus. (2) Der
Wächter übernimmt die Dateien je Runde in `sitzung` und schreibt höchstens alle 5 min einen Messpunkt in `verbrauch`.
(3) Hooks `Notification`, `Stop`, `StopFailure`, `UserPromptSubmit`, `SessionEnd` (async) → `amw-hook.py` setzt
`sitzung.ereignis`: arbeitet | frei | wartet_freigabe | wartet_eingabe | fehler (mit Text, z. B. „rate_limit“).
Warnungen: wartet auf Freigabe ≥ 2 min, Fehler, Kontext ≥ 90 %, 5-h-Grenze ≥ 90 %. (4) Anzeige: Kachel mit Zustand
und Balken (Kontext, 5 h), Übersicht mit allen Werten, Betrieb „Verbrauch“ je Agent und Tag (Kosten-Schätzung, letzte
7 Tage). (5) Einbau der Hooks/Statusline: `amw einrichten agenten-ordner <pfad>` führt die Einträge zusammen.
Lücken: Kosten sind Schätzungen (Listenpreis) – so beschriftet; Sitzungs-Neustart setzt Kosten zurück → Tageswerte
aus Differenzen der Messpunkte, Rücksprung = neue Zählung.
- [x] Statusline-Brücke, Wächter-Übernahme, Messpunkte, Hook-Ereignisse, Warnungen
- [x] Kachel/Übersicht/Betrieb; Einbau in die Agenten-Ordner; Tests; Bildschirmfotos

## 5 Stufe D – Agenten steuern (0.12.0)
- [ ] Agenten-Profil: Ordner, Zusatzordner, Denkstufe, Modell, Startsatz, Rechte-Modus (im Zahnrad).
- [ ] „Starten“/„Beenden“ per Klick in der Workbench am PC (nie über die Online-Seite): neuer Terminal-Tab mit Claude, Kennung, Hook; Beenden der Sitzung des Agenten.
- [ ] Automatischer Neustart (Resume derselben Sitzung) eines abgestürzten Agenten mit Soll „an“, höchstens 3 je Stunde, mit Meldung.
- [ ] `amw agenten-start` erzeugt das Startskript aus den Profilen (ersetzt handgeschriebene Skripte).

## 6 Stufe E – Projektplanung (0.13.0)
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

## 7 Stufe F – Rückblick und Verlauf (0.14.0)
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
