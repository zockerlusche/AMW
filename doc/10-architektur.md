# 10 · Architektur und Stufen (Vorschlag CCamw)

**Status: Grundrichtung und Stufen entschieden** (Marcel 01.11. 08:58, → 07 E2/E3); Einzelheiten bleiben Vorschlag und werden beim Bau verfeinert. Stand 01.11.2026.
Grundlage: Anforderungen 02/05, Probleme 04, Optionen und Kosten 06. Die Vorgaben aus 01 „Produktbild“ und der TL-Vorschlag (06 §7) sind laut Übergabe (Marcel 01.11. 08:47) **Vorschläge**. Dieses Dokument sagt, wie CCamw es bauen würde, und wo und warum es abweicht.

## 1 Leitentscheidungen
| # | Entscheidung | Begründung | Verhältnis zum Vorschlag |
|---|---|---|---|
| L1 | **Erst das lösen, was heute weh tut** – Wecken, Pflicht-Kontext, Fragen, Übersicht (→ 04 #1, #8, #14, #20). | Diese vier kosten heute täglich Zeit und Fehler; alles andere ist Ausbau. | gleiche Ziele, andere Reihenfolge |
| L2 | **In Stufen bauen** (§4): Stufe 1 nur lokal, Stufe 2 von unterwegs, Stufe 3 Produkt für andere. Jede Stufe ist für sich nutzbar. | Das Produktbild (installierbar, mehrere Nutzer, lokal + zentral, Web-Sicherheit) auf einmal heißt Monate ohne Nutzen und viele Teile, die sich erst im Betrieb als richtig oder falsch zeigen. | **Abweichung:** nicht alles gleichzeitig |
| L3 | **Eine führende Datenbank je Agenten-Rechner** (SQLite). Zentral zuerst nur **Spiegel zum Lesen** plus **angehängte Antworten** von unterwegs; echter Zwei-Wege-Abgleich erst, wenn ein zweiter Rechner mit Agenten wirklich kommt. | Zwei-Wege-Abgleich ist der fehleranfälligste Teil (Konflikte, doppelte Zeilen). Heute laufen alle Agenten auf einem PC; „von überall auf den Stand zugreifen“ braucht nur Lesen + Antworten. Antworten sind neue Zeilen, also konfliktfrei. | **Abweichung** von „lokal + zentral abgeglichen“ (01, 05 §7) in Stufe 1–2; Zielbild bleibt |
| L4 | **Das Datenmodell ist von Anfang an abgleich-fähig:** jede Zeile mit Projekt, Herkunft (Rechner), global eindeutiger Kennung und Änderungszeit; Verlauf nur anhängen. | Kostet beim Bau wenig, erspart später den Umbau (L3, Stufe 3). | wie 05 §7 |
| L5 | **Ein Dienst `amw-dienst` außerhalb von Claude Code** übernimmt Wecken, Puls-Aufsicht und Web-Server. Er weckt Sitzungen über deren Pipe + Schlüssel (06 W4). Die Wachen je Agent entfallen. | Übersteht Abbrüche durch Claude Code und vergessene Neustarts (→ 04 #1, #14); ein Prozess statt sechs. | wie TL-Vorschlag, konkretisiert |
| L6 | **Pflicht-Kontext wird aus den Daten erzeugt**, nicht als fester Text: der vorhandene SessionStart-Hook ruft `amw kontext <Agent>` auf. | → 04 #20; der Hook-Mechanismus ist da und bewährt, nur der Inhalt veraltet. | neu |
| L7 | **Python mit Standardbibliothek** für Kern, CLI und Dienst; die Oberfläche als **eine Web-Seite ohne Build-Schritt**. Fremd-Bibliotheken nur, wo die Standardbibliothek nicht reicht (z. B. Passwort-Hash Argon2, Turso-Anbindung) – erst ab Stufe 2. | Läuft heute schon so (bus.py), keine Installation nötig, wenig Speicher (→ 04 #3); Agenten kennen es. | wie TL-Vorschlag |
| L8 | **Sicherheit nach Stufe:** Stufe 1 bindet nur an 127.0.0.1 (heute schon so) und hält die Grundregeln (keine Geheimnisse in DB/Repo, parametrisierte Abfragen, Ausgaben maskieren, CSRF-Schutz). Anmeldung, zweiter Faktor, Rollen, HTTPS kommen mit Stufe 2, sobald etwas aus dem Netz erreichbar ist. | Anmeldung für einen Dienst, den nur der eigene PC erreicht, schützt nichts, kostet aber Bau und Bedienung. Die Grundregeln sorgen dafür, dass Stufe 2 nichts umbauen muss. | **Abweichung** von „von Anfang an“ (01) nur in der Reihenfolge; 05 §6 gilt vollständig ab Stufe 2 |
| L9 | **Kein Framework, keine Agenten-Laufzeit:** die AMW startet keine Agenten selbst, sie koordiniert Claude-Code-Sitzungen, die der Nutzer mit seinem eigenen Konto startet. | → 06 §2: Frameworks lösen das Problem nicht; ein Produkt mit Agent SDK dürfte kein Abo-Login anbieten. | wie TL-Erwartung |
| L10 | **LayerIT ist ein Projekt in der AMW**, keine Sonderform: Projektregeln (baugesetz), Fach-Tabellen und Fach-Seiten (/objekte, /netz, /bau …) werden Erweiterungen (→ 02 §11). | Grundsatz 6 (→ 01). | wie Vorschlag |

## 2 Bausteine
```
            Claude-Code-Sitzungen (TL, CC1 … CCn)
              │ amw-CLI (posten, lesen, aufgabe …)      ▲ Weckruf über Pipe + Schlüssel
              ▼                                         │
   ┌──────────────────────── amw.db (SQLite, WAL) ─────────────────────┐
   │  Kern-Tabellen (§3) · Projekt-Erweiterungen (z. B. LayerIT)       │
   └───────────────────────────────────────────────────────────────────┘
              ▲ liest/schreibt                          │
   amw-dienst (Windows: geplante Aufgabe, Selbst-Neustart)
     · Wecker: neue handlungspflichtige Zeile → Weckruf an die Sitzung
     · Aufsicht: Puls der Sitzungen, Speicher, laufende Läufe → Meldung
     · Web-Server 127.0.0.1: Workbench-Oberfläche + Projekt-Seiten
     · (Stufe 2) Spiegel: gebündelt nach zentral, Antworten zurück
   Hook je Sitzung: SessionStart(startup|resume) → Pipe-Pfad + Schlüssel in geschützte Datei
                    SessionStart(compact)        → `amw kontext <Agent>` (Pflicht-Kontext)
```
| Baustein | Aufgabe | Ersetzt heute |
|---|---|---|
| `amw` (CLI) | einziger Schreibweg der Agenten; feste Arten-Liste, Besitz-Prüfung, „mehrere erledigt“, `kontext`, `takt` | bus.py (CLI-Teil), Werkzeug-Kopien in ccN\ |
| `amw-dienst` | Wecker, Aufsicht, Web-Server, später Spiegel | werkzeug/wache.py (6×), bus.py serve (8765/8766), wach_alarm.py |
| Workbench-Seite | Oberfläche nach 02 §0; Mockup von CC3 als Ausgangspunkt (→ 07) | bus_ansicht.html, /alt, /v1, /wissen, Fragen-Seite |
| Hook-Skript | Sitzung anmelden (Pipe + Schlüssel), Pflicht-Kontext | hooks/compact_schutz.py (bleibt für die Verlauf-Sicherung) |
| Projekt-Erweiterung LayerIT | baugesetz, Fach-Tabellen, Fach-Seiten | bus_objekte/bus_netz/bus_bau/bus_aera/bus_rollen |

## 3 Datenmodell (Entwurf Stufe 1)
Jede Tabelle hat zusätzlich: `projekt`, `herkunft` (Rechner), `uid` (global eindeutig), `geaendert_utc`. Verlaufs-Tabellen nur anhängen bzw. Status ändern.

| Tabelle | Inhalt | Kommt aus (heute) |
|---|---|---|
| projekt | Name, Pfade, Einstellungen | – (heute fest LayerIT) |
| agent | Kennung, Rolle, Grenzen, Startbefehl, soll/zustand, letzter Puls | agent_status, meta.agenten |
| sitzung | Agent ↔ Claude-Code-Sitzung, Start, letzter Puls, Verweis auf die Schlüssel-Datei (nie der Schlüssel selbst) | – (heute geraten, → 06 W5) |
| nachricht | von, art (feste Liste mit Weck-Wirkung), kurz, text, antwort_auf, aufgabe, Anhang | nachricht |
| empfang | je Empfänger: offen/gelesen/erledigt – Rauschen erzeugt keine Empfänge | empfang |
| aufgabe | wie heute (Status/Einstufung mit Prüfung), dazu Besitzer-Prüfung, Prüfer | aufgabe |
| frage | festes Format: kurz, worum, optionen (Liste), empfehlung, grund, fundstellen, folge_von; Antwort-Art (Option/Text/Rückfrage), Antwort, Zeit, Kanal | frage_marcel, frage_tl (Art „an TL“ / „an Entwickler“), frage_verlauf |
| wortlaut | Aussagen des Entwicklers, unverändert, Kanal | marcel_wort |
| beschluss | Festlegung, Quelle, Zeit (Pflicht), ersetzt_durch | beschluss |
| regel | Ebene (Arbeit/Projekt), Nr., gültiger Text, Stand-Zeit | kernregel, baugesetz |
| lauf | Rechen-Job: Agent, Rezept, Start/Ende, Ergebnis, freier Speicher, Schirm ja/nein | RECHEN-JOB-/MESSFENSTER-Nachrichten (48 % Rauschen, → 04 #17) |
| rezept | Lauf-Rezepte als Daten | Scratchpads der Agenten (→ 04 #20) |
| pruefung | Prüfbitte: Aufgabe, Zweig, Stand-SHA, Prüfpunkte, grün/rot | Freitext-Nachrichten |
| sperre | Anweisung je Agent oder alle (z. B. „keine Rechen-Jobs“), von, bis | Freitext in TL-Nachrichten |
| release | Version, Merges, Text intern/öffentlich, Freigabe, veröffentlicht | release, devlog_post |
| notiz | gepflegte Notizen des TL (Schlüssel/Wert) | tl_stand |
| anhang | Datei-Verweis mit Hash | datei_pfad-Spalten, ccN\-Dateien |

17 Tabellen statt heute 32. Neue Tabellen gegenüber heute: projekt, sitzung, lauf, rezept, pruefung, sperre, anhang.

## 4 Stufen
| Stufe | Inhalt | Nutzen | Voraussetzung |
|---|---|---|---|
| **0 Proben** | P1: Variable aus Frage 334 an einer Sitzung · P2: Weckruf über Pipe + Schlüssel aus einem fremden Prozess an die Sitzung von CCamw · P6/P7: Turso-Abgleich unter Windows, Neon-Mindestgröße | klärt die zwei tragenden Annahmen, bevor gebaut wird | nur CCamws eigene Sitzung und F:\amw – kein Eingriff in LayerIT |
| **1 Lokal** | amw.db + CLI, amw-dienst (Wecker, Aufsicht, Server), Hook (Anmelden + Pflicht-Kontext), Workbench-Seite (Fragen, Wer macht was, Aufgaben, Regeln, Beschlüsse, Release Notes), Übernahme der LayerIT-Daten aus bus.db | die Probleme aus 04 #1, #8, #14–#18, #20 sind gelöst | Marcels Wort zu Variante und Stufen; Windows-Aufgabe richtet Marcel ein |
| **2 Unterwegs** | Spiegel nach zentral (Turso, sonst Neon, → 06 §6), Antworten von unterwegs als angehängte Zeilen zurück; Anmeldung mit zweitem Faktor, HTTPS, Rollen; Veröffentlichen von Release Notes/Blog auf die Homepage | Marcel sieht und beantwortet alles von überall | Stufe 1 trägt im Betrieb |
| **3 Produkt** | Installer + Einrichtungs-Assistent, mehrere Benutzer und Projekte, Container für den Webserver, Zwei-Wege-Abgleich für mehrere Agenten-Rechner, eigenes Repo (privat) | andere Nutzer können die AMW einsetzen | Stufe 2 trägt; Marcels Wort zum Repo |

## 5 Übergang vom heutigen Bus
1. bus.db läuft während Stufe 1 unverändert weiter; nichts wird dort umgebaut.
2. Ein Übernahme-Skript liest bus.db **nur lesend** und schreibt amw.db nach der Zuordnung in §3; wiederholbar, mit Zählvergleich je Tabelle.
3. Umschalten in einem Schritt (Marcels Wort): Agenten benutzen ab dann `amw` statt `bus.py`; bus.db bleibt als Archiv lesbar.
4. Tote Teile (→ 03: Alt-Tabellen, alte HTML-Dateien, wach_alarm, bus_backup_vor_klartext) werden nicht übernommen.
