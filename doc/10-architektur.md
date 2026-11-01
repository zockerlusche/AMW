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
| **0 Proben** | P1: Variable aus Frage 334 an einer Sitzung · P2: Weckruf über Pipe + Schlüssel aus einem fremden Prozess an die Sitzung von CCamw – **grün 01.11. 09:10** (→ 06 §8) · P6/P7: Turso-Abgleich unter Windows, Neon-Mindestgröße | klärt die zwei tragenden Annahmen, bevor gebaut wird | nur CCamws eigene Sitzung und F:\amw – kein Eingriff in LayerIT |
| **1 Lokal** | amw.db + CLI, amw-dienst (Wecker, Aufsicht, Server), Hook (Anmelden + Pflicht-Kontext), Workbench-Seite (Fragen, Wer macht was, Aufgaben, Regeln, Beschlüsse, Release Notes), Übernahme der LayerIT-Daten aus bus.db | die Probleme aus 04 #1, #8, #14–#18, #20 sind gelöst | Marcels Wort zu Variante und Stufen; Windows-Aufgabe richtet Marcel ein |
| **2 Unterwegs** | Spiegel nach zentral (Turso, sonst Neon, → 06 §6), Antworten von unterwegs als angehängte Zeilen zurück; Anmeldung mit zweitem Faktor, HTTPS, Rollen; Veröffentlichen von Release Notes/Blog auf die Homepage | Marcel sieht und beantwortet alles von überall | Stufe 1 trägt im Betrieb |
| **3 Produkt** | Installer + Einrichtungs-Assistent, mehrere Benutzer und Projekte, Container für den Webserver, Zwei-Wege-Abgleich für mehrere Agenten-Rechner, eigenes Repo (privat) | andere Nutzer können die AMW einsetzen | Stufe 2 trägt; Marcels Wort zum Repo |

## 5 Ablauf Wecken, Halt und Neustart
**Wecken:** Die Windows-Aufgabenplanung startet `amw-dienst` bei der Anmeldung und startet ihn nach einem Absturz neu; sie schaut selbst nicht in die Datenbank. Der Dienst erkennt Änderungen wie die heutige Wache über `PRAGMA data_version` (alle 1–2 s). Bei einer neuen Nachricht, deren Art laut `nachricht_art.weckt` weckt, liest er Pipe-Adresse und Schlüssel des Empfängers aus dessen Schlüssel-Datei und legt eine kurze Zeile in die Pipe: Eine ruhende Sitzung beginnt eine neue Runde, eine arbeitende bekommt die Zeile zwischen zwei Schritten. `empfang.geweckt_utc` wird gesetzt. Kein Neustart nach dem Wecken; Claude Code kann den Dienst nicht beenden, weil er nicht sein Kind ist.

**Anmelden:** Ein SessionStart-Hook (startup, resume) schreibt bei jedem Sitzungsstart Pipe-Adresse und Schlüssel in eine nur für den Benutzer lesbare Datei und trägt die Sitzung in `sitzung` ein (ohne Schlüssel). Nur angemeldete, lebende Sitzungen werden geweckt.

**Halt** (Marcel 01.11. 09:25): Entwickler (Workbench) oder TL (`amw halt`) setzt eine `sperre` mit art `halt` für alle oder einzelne Agenten.
- Der Dienst stellt sofort jedem betroffenen laufenden Agenten ein STOPP zu („aktuelle Arbeit sauber beenden, nichts Neues anfangen“).
- Solange der Halt gilt, weckt er nur noch für `stopp` und `freigabe`; `amw` verweigert neue Läufe und Aufgaben-Starts; der Pflicht-Kontext zeigt den Halt zuerst.
- „Weiter“ hebt den Halt auf; liegengebliebene Nachrichten werden danach der Reihe nach zugestellt.
- Der Dienst beendet **keine** Claude-Code-Sitzungen (Abbruch mitten in Commit oder Schreibvorgang wäre gefährlicher als der Nutzen; → 05 §2 „Nichts Fremdes beenden“). Hartes Beenden bleibt Hand des Entwicklers.
- Der Halt steht in der Datenbank und gilt deshalb über Neustarts hinweg.

**Windows-Neustart:** Nach dem Hochfahren läuft nur der Dienst (wenige MB, liefert die Workbench); Agenten startet er **nie von selbst** (Tokens, Kontrolle). Alte Sitzungen werden als `beendet` geführt, ihre Schlüssel sind ungültig; niemand wird ins Leere geweckt. Nachrichten bleiben offen, bis der Agent gestartet ist und sein Hook ihn anmeldet – dann stellt der Dienst das Offene zu. Die Workbench zeigt je Agent `soll` gegen Ist („CC2: soll laufen, läuft nicht, 3 offen“); ein Startknopf startet später nur auf Klick des Entwicklers.

**Kontrolle über den Dienst** (Marcel 01.11. 09:27):
- **Hart, nur lokal:** Geplante Aufgabe und Dienst-Prozess gehören dem Windows-Benutzer des Entwicklers. Ein-/Ausschalten, Löschen, Beenden nur am PC selbst (Aufgabenplanung, Task-Manager).
- **Weich, auch aus dem Netz:** Die Weboberfläche – lokal oder später auf einem Webserver – hat **keinen Befehlsweg** zum PC, nur Daten in der Datenbank. Sie steuert das Verhalten des Dienstes (Halt/Weiter), nicht den Dienst selbst. Ein Angriff auf die Webseite kann so höchstens Daten ändern, nichts auf dem PC ausführen.
- **Stufe 2:** Ein Halt aus dem Netz erreicht den PC über den Abgleich. Der Dienst fragt den zentralen Speicher dafür häufiger ab, aber nur nach Halt und Freigabe (→ 06 §6: bei Turso ohne nennenswerte Kosten, bei Neon hielte es die Datenbank wach – Kriterium für E4).
- **Agenten:** Sie laufen unter dem Benutzer des Entwicklers im Bypass-Modus und hätten die Rechte, Aufgabe oder Prozess anzufassen. Regel: kein Agent tut das ohne Wort des Entwicklers. Beim Umschalten (07 E6) zusätzlich Sperr-Regeln in den Agenten-Einstellungen gegen `schtasks`, `Disable-ScheduledTask`, `Unregister-ScheduledTask` und das Beenden des Dienst-Prozesses.

## 6 Übergang vom heutigen Bus
1. bus.db läuft während Stufe 1 unverändert weiter; nichts wird dort umgebaut.
2. Ein Übernahme-Skript liest bus.db **nur lesend** und schreibt amw.db nach der Zuordnung in §3; wiederholbar, mit Zählvergleich je Tabelle.
3. Umschalten in einem Schritt (Marcels Wort): Agenten benutzen ab dann `amw` statt `bus.py`; bus.db bleibt als Archiv lesbar.
4. Tote Teile (→ 03: Alt-Tabellen, alte HTML-Dateien, wach_alarm, bus_backup_vor_klartext) werden nicht übernommen.
