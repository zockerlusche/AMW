# Architektur

## 1 Leitlinien
- **Eine führende Datenbank je PC** (SQLite im WAL-Modus). Alles, was Agenten tun, geht über die Kommandozeile `amw`
  in diese Datenbank – sie ist die einzige Wahrheit; Dateien und Chats sind es nicht.
- **Nur Python-Standardbibliothek** (Windows-API über `ctypes`, HTTP über `urllib`); die Oberfläche ist eine einzige
  HTML-Seite ohne Build-Schritt. Kein Paketmanager, nichts zu installieren außer Python.
- **Die Agenten bleiben Claude-Code-Sitzungen** des Anwenders (sein Konto, seine Fenster). AMW startet sie auf Wunsch,
  koordiniert und weckt sie – es ist keine eigene Agenten-Laufzeit.
- **Der PC ist aus dem Netz nicht erreichbar.** Online gibt es nur fertige Ansichten und einen Briefkasten; der PC holt
  ab und führt aus.
- **Verlauf wird nie gelöscht** (Nachrichten, Wortlaut, Beschlüsse, Aufgaben, Fragen, Läufe, Prüfungen) – nur Status.
- **Jede Zeile ist abgleich-fähig:** eindeutige `uid`, `herkunft` (Rechner), `geaendert_utc`.

## 2 Bausteine
| Datei | Aufgabe |
|---|---|
| `amw/db.py` | einziger Datenbankzugang: Verbindung (WAL, Wartezeit), Anlegen, Umstellen auf neue Schema-Versionen (`migration_<n>.sql` beim ersten Schreibzugriff), Sicherung |
| `amw/schema.sql` | Datenmodell (§4) |
| `amw/kern.py` | Nachrichten, Empfänger, Aufgaben, Fragen mit Verlauf, Halt/Hinweise, Pflicht-Kontext |
| `amw/wissen.py` | Beschlüsse, Regeln (nur mit Beschluss), Wortlaut, Notizen, Release Notes, Einstufung (geparkt/Pool) – Fragen parken: `kern.frage_parken` |
| `amw/betrieb.py` | Rechen-Läufe mit Regeln und Warteschlange (zwei Spuren: Grafikkarte/Schirm exklusiv, CPU parallel; je Agent ein schwerer Lauf), Prüfungen, Rezepte |
| `amw/ki.py` | Lokale KIs: eintragen, Modelle freigeben, Rechte, Aufträge als Lauf, Ausführung im Dienst über HTTP, Herkunft, Nachweis ([plan-lokale-ki.md](plan-lokale-ki.md)) |
| `amw/planung.py` | Leitbild, Bögen, Spezifikation, Schritte, Abhängigkeiten, nächster Schritt, Risiken, Prognose, Plan-Check |
| `amw/verlauf.py` | Rückblick je Bogen, Verlauf aller Ereignisse, Zusammenfassungen |
| `amw/dokumente.py` | Dokumente: Ablage (Hash im Datenordner), Versionen, Formate und Schutz, Bezüge, Kommentar an den Verfasser |
| `amw/cli.py` | Kommandozeile `amw` (`amw.cmd`, `amw-cli.py` starten sie ohne PYTHONPATH) |
| `amw/hook.py` | Claude-Code-Hooks: Anmeldung beim Start, Pflicht-Kontext, Zustand (arbeitet/frei/wartet/Fehler) |
| `amw/statusline.py` | Statusline-Brücke: Kontext, Nutzungsgrenzen, Kosten je Sitzung; reicht die bisherige Statusline weiter |
| `amw/dienst.py` | der Wächter: Wecken, Aufsicht der Sitzungen, Takt, Warteschlange, Überwachung, Neustart, Push, Workbench, Abgleich, Brücke, KI-Arbeiter |
| `amw/pipe.py` | Zustellung in die Nachrichten-Pipe einer Claude-Code-Sitzung |
| `amw/ueberwachung.py` | Projekt-Server (Port prüfen, Neustart), Warnungen (Stillstand, Lauf, Freigabe, Fehler, Kontext, Grenze) |
| `amw/steuerung.py` | Agenten-Profil, Starten/Fortsetzen/Beenden, Neustart nach Absturz, Startskript |
| `amw/push.py` | Benachrichtigungen über ntfy, Pushover, Telegram |
| `amw/workbench.py`, `amw/workbench.html` | Workbench: HTTP-Server nur auf 127.0.0.1, Daten-Schnittstellen, eine Seite für lokal und online |
| `amw/aktionen.py` | alles, was die Seite schreiben darf – derselbe Weg für lokal und den Online-Briefkasten |
| `amw/abgleich.py` | Online-Speicher (Turso über HTTP): Ansichten hochladen, Briefkasten abholen |
| `amw/bruecke.py` | Datei-Brücke für Sitzungen ohne direkten Datenbankzugriff |
| `amw/einrichtung.py`, `amw/assistent.py` | Wächter als geplante Aufgabe, Hooks im Projektordner, geführte Einrichtung |
| `amw/einstellungen.py` | Einstellungen dieses PCs |
| `web/` | Online-Seite (PHP): Anmeldung mit Passwort + TOTP, Ansichten, Briefkasten, Einrichtungs-Assistent |

## 3 Abläufe
**Anmelden.** Claude Code ruft beim Start (und beim Fortsetzen) den `SessionStart`-Hook. Er ermittelt die Kennung
(Umgebungsvariable `AMW_AGENT` aus dem Startbefehl, sonst die frühere Anmeldung derselben Sitzungs-ID), schreibt
Pipe-Pfad und Schlüssel der Sitzung in `%LOCALAPPDATA%\amw\sitzungen\<Kennung>.json` und trägt die Sitzung mit
Claude-PID und Fenster-PID ein. Hintergrund-Sitzungen ohne Fenster werden nie angemeldet. Ausgabe: Pflicht-Kontext.

**Wecken.** Eine neue Nachricht einer weckenden Art erzeugt Empfänge. Der Wächter bemerkt die Änderung (SQLite
`data_version`), schreibt der Sitzung jedes Empfängers über ihre Pipe (erste Zeile Anmeldung mit Schlüssel, dann der
Text „Neue Nachrichten: #… – lies mit amw lesen“) und vermerkt `geweckt_utc`. Schläft ein Agent nicht, landet der Text
in seiner Eingabe und wird nach dem aktuellen Schritt gelesen. Während eines Halts weckt er nur für Stopp/Freigabe.

**Aufsicht (jede Runde, Vorgabe 30 s).** Lebt die Pipe jeder Sitzung? (sonst „beendet“) · Brücken-Sitzungen: Puls ·
Warteschlange der Läufe · Statusline-Dateien übernehmen, Messpunkte · Projekt-Server prüfen, ggf. neu starten ·
Warnungen an den Lead · abgestürzte Agenten fortsetzen (nur mit Profil-Einstellung, nur bei offenem Fenster) ·
Takt an den Lead · Push.

**Zustand der Agenten.** Die Hooks `UserPromptSubmit` (arbeitet), `Stop` (frei), `Notification` (wartet auf Freigabe
bzw. Eingabe), `StopFailure` (Fehler mit Art), `SessionEnd` laufen im Hintergrund und schreiben nur den Zustand der
Sitzung. Die Statusline-Brücke schreibt bei jeder Aktualisierung eine kleine Datei je Sitzung; der Wächter übernimmt sie.

**Starten.** Aus dem Profil entsteht eine PowerShell-Zeile (`Set-Location`, `$env:AMW_AGENT`, `claude --resume <id>`
bzw. `--session-id <neu>`, Denkstufe, Modell, Zusatzordner, Rechte, Remote Control, Startsatz); sie läuft in einem neuen
Windows-Terminal-Tab. Beenden trifft nur den Claude-Prozess. Ein automatischer Neustart setzt voraus: Claude-Prozess
weg, Fenster noch offen, kein bewusstes Ende, Soll „an“, im Profil erlaubt, höchstens 3 je Stunde.

**Online.** Der Wächter berechnet dieselben Ansichten wie die Workbench und lädt sie bei Änderung in den
Online-Speicher; die PHP-Seite zeigt sie nach der Anmeldung. Schreiben online = eine Zeile in den Briefkasten; der PC
holt sie (Vorgabe alle 15 s), prüft sie mit demselben Code wie lokal und führt sie höchstens einmal aus. Mehr: [online.md](online.md).

**Datei-Brücke** (aus, bis `bruecke_an` gesetzt ist). Für einen Agenten, der die Datenbank nicht direkt öffnen kann (z. B. in einer VM über eine
Freigabe, wo SQLite-WAL scheitert): Lesekopie `daten/tl_lesen.db` ohne WAL (höchstens jede Minute, nur nach Änderungen);
Schreiben über JSON-Befehlsdateien in `eingang-tl/befehle/`, die der Wächter als dieser Agent ausführt – auch die Planung
(`leitbild`, `bogen`, `spec`, `aufgabe … --bogen`, `risiko`, `rueckblick`); `--datei` nur aus `eingang-tl/`, z. B.
`{"befehl": "spec", "aktion": "schreiben", "bogen": 3, "teil": "anforderungen", "datei": "plan/anf-3.md"}`.
Mit mehreren Projekten hat jedes seine Brücke (`eingang-<projekt>/`, `daten/lesen-<projekt>.db`, ausgeführt als sein Lead –
gedacht für einen Lead, der als Chat arbeitet: ein eigener Agent mit Rolle `lead` ohne Arbeitsordner, er wird nie gestartet.
Kommt ein Chat-Lead zu einem Projekt dazu, das bisher ein Agent mit eigener Sitzung führt: Chat-Lead anlegen
(`amw agent neu <kennung> --rolle lead`, dann `amw agent profil <kennung> --ordner ""`) und dem bisherigen Lead eine andere
Rolle geben (`amw agent profil <kennung> --rolle …`) – sonst liefen die Befehle der Brücke unter dessen Namen);
die Lese-Kopie enthält dann nur dieses Projekt ([anleitung-projekte.md](anleitung-projekte.md)).

## 4 Datenmodell (Schema 9)
| Bereich | Tabellen |
|---|---|
| Projekt und Agenten | `projekt` (Einstellungen, Leitbild, DoD), `agent` (Rolle, Soll, Profil), `sitzung` (Claude-Sitzung, PIDs, Puls, Zustand, Kontext, Grenzen, Kosten) |
| Kommunikation | `nachricht_art` (weckt ja/nein), `nachricht`, `empfang` (je Empfänger: offen/gelesen/erledigt, geweckt) |
| Arbeit | `aufgabe` (Status, Einstufung, Rang, Bogen, Kriterien, Plan, Zusammenfassung …), `abhaengigkeit` |
| Planung | `bogen`, `spezifikation`, `risiko`, `plan_ereignis`, `rueckblick` |
| Dokumente | `dokument` (Titel, Art, Bezug, Status, online), `dokument_version` (Hash, Endung, Größe, Notiz, Suchtext); Kommentare: `nachricht.dokument_id`; Dateien unter `<Datenordner>/dokumente/` |
| Fragen | `frage` (Optionen, Empfehlung, Antwort), `frage_verlauf` |
| Wissen | `wortlaut`, `beschluss`, `regel`, `notiz`, `release` |
| Betrieb | `lauf`, `rezept`, `pruefung`, `sperre` (Hinweis/Halt), `server`, `verbrauch`, `push_versand` (je Projekt seit Schema 18) |
| Lokale KI (Schema 17) | PC-weit `ki`, `ki_modell` (Freigabe), `ki_vorlage`; je Projekt `ki_recht`; `ki_auftrag` (je Lauf), `ki_herkunft` (je Dokument-Version, unveränderlich) |
| Abgleich | `netz_eingang` (Briefkasten-Zeilen, die schon ausgeführt sind) |
Schutz in der Datenbank: Trigger verhindern das Löschen von Verlauf, Änderungen am Wortlaut und „fertig/verworfen“
ohne Beleg. Neue Versionen kommen als `amw/migration_<n>.sql`; ein Test prüft, dass eine umgestellte alte Datenbank
Spalte für Spalte einer neu angelegten gleicht.

## 5 Grenzen und Zahlen
- Mehrere Agenten schreiben gleichzeitig: SQLite-WAL, Schreib-Transaktionen sperren sofort (`BEGIN IMMEDIATE`), Wartezeit 30 s.
- Ein PC mit den Agenten; der Online-Teil ist ein Spiegel mit Briefkasten, kein Zwei-Wege-Abgleich zwischen mehreren PCs.
- Die Prognose rechnet in Stückzahlen (Durchsatz je Bearbeiter); sie wird besser, je ähnlicher die Schritte groß sind.
