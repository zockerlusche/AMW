# Ausbau zum vollständigen Lead-Werkzeug

**Status: abgeschlossen mit 1.0.0** (02.11.2026). Auftrag: AMW soll aus Sicht des Anwenders alles abdecken, was ein Lead braucht,
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

## 5 Stufe D – Agenten steuern (0.12.0) ✔ 02.11.2026
**Grundlage.** Bewährtes Startskript (Windows-Terminal-Tab je Agent: `wt new-tab --title X -d Ordner pwsh -NoExit
-EncodedCommand …`, darin `$env:AMW_AGENT='X'; claude --remote-control X --effort … --add-dir … '<Startsatz>'`) und die
Optionen von Claude Code 2.1.309 (`--resume <id>`, `--session-id <uuid>`, `--model`, `--effort`, `--permission-mode`,
`--dangerously-skip-permissions`, `--add-dir`, `--remote-control`, `-n`).
**Konzept.** Profil je Agent in der Tabelle `agent`: Ordner, Zusatzordner, Denkstufe, Modell, Startsatz, Rechte
(Vorgabe/auto/umgehen), Fernsteuerung (Remote Control), Auto-Neustart. Der Befehl „claude“ ist eine PC-Einstellung
(`claude_befehl`, falls anders installiert). **Starten** (Workbench am PC, CLI): setzt die letzte Sitzung des Agenten
fort (`--resume`), sonst neue Sitzung mit eigener `--session-id` – so ist die Zuordnung Sitzung ↔ Agent sofort eindeutig.
Ohne Windows Terminal: eigenes Konsolenfenster. Startet nicht, wenn der Agent schon läuft. **Beenden**: beendet den
Claude-Prozess dieser Sitzung (nicht das Fenster) und vermerkt „durch AMW beendet“. **Auto-Neustart** nur, wenn
eindeutig ein Absturz vorliegt: Claude-Prozess weg, sein Fenster (die Shell) lebt noch, kein bewusstes Ende
(SessionEnd „prompt_input_exit/logout/clear“, AMW-Beenden), Soll „an“, Auto-Neustart im Profil an; höchstens 3 je Stunde,
mit Meldung an den Lead. Wer ein Fenster schließt, beendet bewusst – das wird nie neu geöffnet. Dafür merkt sich die
Anmeldung Prozess- und Fenster-PID. **Startskript**: `amw agent startskript` schreibt ein PowerShell-Skript für alle
Agenten mit Soll „an“ (zum Doppelklicken), erzeugt aus den Profilen. Nie über die Online-Seite.
Lücken: Profile aus dem bisherigen Skript übernehmen (einmalig per CLI); fehlt Windows Terminal → Konsole; der erste
Start ohne Sitzungs-ID → neue ID.
- [x] Profil (Schema 6), CLI `amw agent profil|starten|beenden|startskript`, PC-Einstellung `claude_befehl`
- [x] Prozess-/Fenster-PID bei der Anmeldung, Auto-Neustart im Wächter mit Absturz-Erkennung und Grenze
- [x] Workbench: Starten/Fortsetzen/Neu/Beenden in Kachel und Übersicht (nur am PC, mit Rückfrage), Profil im Zahnrad
- [x] Tests, Bildschirmfotos, Profile der vorhandenen Agenten übernehmen

## 6 Stufe E – Projektplanung (0.13.0; Recherche: recherche/planung.md) ✔ 02.11.2026 – Anleitung: anleitung-planung.md
**Methode** (hybrid, für einen Menschen + KI-Agenten): Leitbild (Ziel mit Kennzahl, Nicht-Ziele, Prinzipien mit
Prüffrage, Definition of Done) → Bögen = Meilensteine mit prüfbarem Abnahmekriterium und Zieldatum → je Bogen eine
Spezifikation in drei Teilen (Anforderungen mit IDs `R1 …`, Entwurf, Schritte) mit Freigabe je Teil durch den Menschen
(„spezifizieren → planen → zerlegen“ nach Spec Kit/Kiro; unklare Stellen `[KLÄREN: …]` werden Fragen und blockieren die
Freigabe) → Schritte (vorhandene Aufgaben, erweitert) → Ausführung mit „nächster Schritt“, Plan-Freigabe bei großen
Schritten, Abnahme gegen Kriterien und DoD → Prognose und Status → Rückblick (Stufe F). Der Mensch ist der Engpass:
alles, was auf ihn wartet (Freigaben, Fragen, eigene Schritte), steht gesammelt in „Wartet auf dich“ und kommt als Push.

**Datenmodell (Schema 7).** `projekt.leitbild` (JSON: ziel, kennzahlen[], nicht_ziele[], prinzipien[{text, pruefung}]),
`projekt.dod` (JSON-Liste). `bogen` (nr, titel, ziel, abnahme, status geplant|aktiv|fertig|verworfen, zieldatum,
baseline_datum, baseline_grund). `spezifikation` (bogen, teil anforderungen|entwurf|schritte, text, status
entwurf|vorgelegt|frei|zurueck, version, kommentar, freigabe_utc). `aufgabe` + bogen_id, kriterien (JSON
[{text, erfuellt}]), schaetzung_h, komplexitaet 1–10, verantwortlich, pruefbefehl, dateibereich, plan, plan_status
keiner|vorgelegt|frei|zurueck, zusammenfassung, anforderungen (IDs). `abhaengigkeit` (vor, nach, art FS|SS|FF, extern) –
das alte Textfeld wird übernommen. `risiko` (titel, ursache, wirkung, wahrscheinlichkeit 1–5, auswirkung 1–5, strategie
vermeiden|mindern|uebertragen|akzeptieren, massnahme, verantwortlich, ausloeser, status offen|eingetreten|erledigt,
bogen). `plan_ereignis` (Protokoll aller Planänderungen und Freigaben – Grundlage für Verlauf und Statusbericht).

**Regeln** (nur für Schritte in einem Bogen – bestehende Aufgaben bleiben frei). Blockiert wird berechnet (offene Vorgänger), Zyklen werden beim Anlegen abgewiesen. Ein Schritt ist
„bereit“ (Definition of Ready), wenn Kriterien, Bearbeiter und erledigte Vorgänger da sind. Komplexität ≥ 7 verlangt
einen freigegebenen Plan, bevor er „läuft“. „Fertig“ nur, wenn alle Kriterien erfüllt sind und eine Zusammenfassung
vorliegt (Beleg-Pflicht wie bisher). `amw schritt naechster` nimmt in einer Transaktion den nächsten bereiten Schritt
(aktiver Bogen zuerst, dann Rang). Baseline: beim Aktivieren eines Bogens wird das Zieldatum eingefroren; spätere
Änderung nur mit Grund (Änderungssteuerung).

**Prognose.** Monte Carlo aus dem Tagesdurchsatz je Bearbeiter (letzte 14 Tage, mindestens 1 Erledigung angenommen,
2 000 Läufe): für jeden offenen Schritt das Datum, an dem er mit 50 % bzw. 85 % fertig ist, in der Reihenfolge der
Warteschlange des Bearbeiters und nie vor seinen Vorgängern; Bogen-Ende = spätester Schritt. Ampel je Bogen: grün, wenn
P85 ≤ Zieldatum; gelb, wenn P50 ≤ Zieldatum < P85; rot, wenn P50 > Zieldatum. Der Mensch hat seinen eigenen Durchsatz.

**Plan-Check** (Lückenprüfung, aus der Prüfliste der Recherche): fehlende Ziele/Nicht-Ziele/DoD; Bogen ohne
Abnahmekriterium oder Zieldatum; Anforderung ohne Schritt; Schritt im aktiven Bogen ohne Kriterien/Bearbeiter;
Komplexität ≥ 7 ohne Plan; Zyklen/verwaiste Vorgänger; erledigt ohne Zusammenfassung; Risiko ohne Maßnahme/Verantwortlichen;
Bogen rot laut Prognose; Mensch überlastet (Schritte des Menschen > Durchsatz bis zum Zieldatum).

**Ansicht „Planung“.** Senkrechte Zeitleiste der Bögen (Heute-Linie, Zieldatum, Baseline, P50/P85, Ampel,
Fortschritt), darunter je Bogen Schritte in Wellen (was parallel geht) mit Bearbeiter und Prognose; Bogen-Detail mit
Spezifikation (drei Teile, Freigabe/Zurück mit Kommentar), Risiken (Matrix 5 × 5 und Liste), Leitbild, Plan-Check.
„Wartet auf dich“ zeigt Freigaben (Spezifikation, Pläne) und eigene Schritte. Online lesbar; Freigaben auch von unterwegs.
Agenten-Befehle: `amw leitbild`, `amw bogen`, `amw spec`, `amw aufgabe … --bogen --kriterium --nach --schaetzung
--komplexitaet`, `amw aufgabe kriterium|plan|planfrei|fertig`, `amw schritt naechster`, `amw risiko`, `amw plan pruefen|prognose`.
- [x] Schema 7, Modul `planung.py` (Leitbild, Bögen, Spezifikation mit KLÄREN-Fragen, Abhängigkeiten, Kriterien, Plan-Gate, nächster Schritt, Risiken, Ereignisse)
- [x] Prognose (Monte Carlo) und Plan-Check
- [x] CLI für TL/Agenten; Pflicht-Kontext enthält Leitbild und aktiven Bogen
- [x] Ansicht „Planung“ (Zeitleiste, Bogen-Detail, Freigaben, Risiken, Leitbild, Plan-Check), „Wartet auf dich“, Push für Freigaben
- [x] Online-Spiegel und Freigaben über den Briefkasten; Tests; Bildschirmfotos Desktop/Handy

## 7 Stufe F – Rückblick und Verlauf (0.14.0) ✔ 02.11.2026
**Konzept.** (1) **Rückblick je Bogen** nach dem bewährten Muster „Was lief gut / was nicht / was ändern wir“
(Start-Stop-Continue, 4L – recherche/planung.md §1.16): Einträge mit Art gut | schlecht | massnahme | gelernt, Verfasser,
Zeit. Eine Maßnahme wird mit einem Klick zur Aufgabe (mit Bezug) oder zum Beschluss (Lessons Learned fließen ins Wissen);
der Bezug bleibt sichtbar. Agenten können beitragen (`amw rueckblick <bogen> --gut …`); nach dem Abschluss eines Bogens
erinnert die Karte daran. (2) **Verlauf**: eine senkrechte Zeitleiste aller Ereignisse aus vorhandenen Daten (keine neue
Erfassung): Nachrichten, erledigte Aufgaben/Schritte, Läufe (Start/Ende), Prüfungen (grün/rot), Fragen (gestellt/
beantwortet), Beschlüsse, Planungs-Ereignisse (Freigaben, Bögen, Baseline), Sitzungen (Start/Ende) – je Tag gruppiert,
filterbar nach Agent und Art, Zeitraum wählbar. (3) **„Seit du weg warst“**: die Startseite merkt sich (je Gerät) den
letzten Besuch und zeigt eine Zusammenfassung seither in Zahlen mit Link in den Verlauf; täglich zur gewählten Uhrzeit
als Push (Ereignis „rueckblick“, Vorgabe 08:00, nur Zahlen).
Lücken: Verlauf liest viele Tabellen → Grenze je Abfrage (300) und Zeitraum; Rückblick-Maßnahmen als Beschluss nur durch
Lead/Entwickler (Beschlüsse sind verbindlich).
- [x] Schema 8 (`rueckblick`), Modul `verlauf.py` (Rückblick, Verlauf, Zusammenfassung seit), CLI `amw rueckblick`, `amw verlauf`
- [x] Ansicht „Verlauf“ (Tag-Gruppen, Filter), Rückblick-Dialog am Bogen, Banner „Seit du weg warst“, Push-Rückblick
- [x] Tests, Bildschirmfotos Desktop/Handy

## 8 Stufe G – Für jeden Anwender (1.0.0)
- [x] Beenden nur durch den Menschen (Workbench); Kommandozeile nur die eigene Sitzung, Brücke gar nicht.
- [x] Repo neutral: keine Bezüge auf ein bestimmtes Projekt in Code, Doku, Changelog; projektbezogene Doku lokal in `intern/` (nicht veröffentlicht).
- [x] Doku neu (`doc/README.md`, Befehlsreferenz aus dem Parser): Was AMW ist, Bausteine und Datenfluss (Agenten-Sitzungen, Hook, Kommandozeile, SQLite, Wächter, Workbench, Online-Speicher, Online-Seite), Reihenfolge der Einrichtung, Betrieb, Sicherheit, Fehlerbehebung.
- [x] `amw einrichten`: geführte Einrichtung (Projekt, Agenten, Hook-Eintrag, Startskript, Wächter-Aufgabe; Online verweist auf `amw web einrichten`), `amw einrichten schnell`, `amw sichern`.
- [x] Online-Teil Schritt für Schritt (`doc/online.md`): Online-Speicher anlegen, Hoster per Git, Einrichtungs-Assistent, zweiter Faktor.
- [x] Probe: ein frischer Agent installiert nach der Anleitung in einen leeren Ordner; jede Stolperstelle wird behoben (18 Befunde, alle bearbeitet; Nachprüfung der geänderten Wege selbst, isoliert).
- [x] Online-Seite: alle neuen Ansichten im Spiegel (auch „Seit du weg warst“ – online je Gerät aus Zeitpunkten gezählt, Test vergleicht mit dem PC), neue Schreibwege über den Briefkasten.

## 9 Quellen der Recherche (Auswahl)
Claude Code: agent-view, hooks, statusline, monitoring-usage, agent-teams, cross-session-messaging (code.claude.com/docs) ·
ntfy (docs.ntfy.sh), Pushover, Telegram Bot API · Kiro specs/steering (kiro.dev/docs) · GitHub Spec Kit
(github.com/github/spec-kit) · Taskmaster (docs.task-master.dev) · Backlog.md · BMAD-METHOD · Roo Code Boomerang ·
Cline Plan/Act · Linear Agents (linear.app/developers/agents) · Devin · GitHub Copilot cloud agent · Linear project graph
(Prognose) · Monte-Carlo-Prognose (prokanban.org).
