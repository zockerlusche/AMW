# 06 · Varianten

**Status: ausgearbeitet (CCamw, A1207 Phase 1, 01.11.2026). Entscheidung: Marcel** (→ 07 „Offene Entscheidungen“).
Grundlage: CC3-Entwurf `F:\agent-bus\projekt-netly\cc3\a1207\konzept.txt` + `markt.txt` (22 Quellen), Befragung CC1–CC5 (Bus #16147–#16156, Nachfrage #16168 → #16170–#16174), eigene Prüfung der Claude-Code-Doku und der Anbieter-Seiten am 01.11., TL-Vorschlag (§7). Probleme → 04; Anforderungen → 05; Produktbild → 01.

## 1 Kriterien für die Bewertung
Zuverlässigkeit · Ordnung (eine Quelle) · Bedienbarkeit für den Entwickler · Aufwand · Speicherbedarf · Token-Kosten · Erweiterbarkeit (weitere Projekte) · Produktfähigkeit.

## 2 Marktvergleich
Prüffragen je Werkzeug: Dauerbetrieb über Tage? Wecken? Gedächtnis über Komprimierung? Oberfläche für den Entwickler? Lokal unter Windows? Aufwand?
„geprüft“ = von CCamw in der Original-Quelle nachgelesen; „CC3“ = aus `markt.txt`, nicht einzeln nachgeprüft.

### 2.1 Bordmittel von Claude Code (heute Version 2.1.309)
| Mittel | Was es kann | Für uns | Grenzen | Quelle |
|---|---|---|---|---|
| **Sitzungs-Nachrichten** (SendMessage/ListAgents) | Nachricht an eine andere Sitzung auf demselben Rechner; eine ruhende Sitzung **startet damit eine neue Runde**. Unter Windows über eine Named Pipe je Sitzung (ab 2.1.234). | Einziger eingebauter Weg, einen schlafenden Agenten zu wecken; am 01.11. 4 von 4 Weckrufen angekommen. | Max. 50 Nachrichten in der Schlange, gleiche Wiederholungen werden kurz verworfen, Bursts abgelehnt. Eine Sitzung im Bypass-Modus **hält** fremde Nachrichten zurück, außer der Sender ist auch im Bypass – bei uns laufen alle im Bypass (→ 03 §1), deshalb kam alles an. Festschreiben mit `crossSessionInbound: accept` – heute bei keinem Agenten gesetzt (→ 03 §1). | geprüft: [cross-session-messaging](https://code.claude.com/docs/en/cross-session-messaging) |
| **Wecken von außen über Pipe + Schlüssel** | Jede Sitzung gibt ihren Pipe-Pfad (`CLAUDE_CODE_MESSAGING_SOCKET`) und einen Schlüssel (`CLAUDE_CODE_MESSAGING_TOKEN`) an Hooks und Shell-Befehle weiter. Wer die erste Zeile `{"type":"auth","token":"…"}` schickt, gilt als eigener Kindprozess; die Nachricht wird zugestellt. | Ein **Dienst außerhalb von Claude Code** kann jeden Agenten direkt wecken – ohne Umweg über TL/CC3 und ohne raten, welche Sitzung zu welchem Agenten gehört. Ein SessionStart-Hook schreibt Pfad + Schlüssel beim Start in eine nur für den Windows-Benutzer lesbare Datei (nicht in die DB, → 05 §6 Geheimnisse). | Unter Windows ist die Schlüssel-Zeile Pflicht. Verbindung erst öffnen, wenn die Zeile fertig ist (Frist 30 s). Neuer Schlüssel bei jedem Sitzungs-Neustart → Hook muss bei startup **und** resume schreiben. **Erprobt am 01.11.: weckt eine ruhende Sitzung** (§8 P2). Nur auf demselben Rechner. | geprüft: dto., Abschnitt „The session's inbox socket“ |
| **Hooks** | `SessionStart` mit Matcher `compact`/`resume`/`startup` spielt Text (bis 10 000 Zeichen) als Kontext ein; `asyncRewake`: Hintergrund-Hook, der Claude bei Exit-Code 2 weckt; `Stop`-Hook mit Exit 2 verhindert das Anhalten. Unter Windows auch als PowerShell. | **Gedächtnis:** nach jeder Komprimierung automatisch Pflicht-Kontext → 05 §4. **Bei uns schon vorhanden** (→ 03 §3 `hooks/compact_schutz.py`), aber mit veraltetem Inhalt – den Agenten fehlte trotzdem Wesentliches (→ 04 #20). **Wecken:** Wache als asyncRewake-Hook statt als Hintergrund-Shell. | Ob ein asyncRewake-Hook den gleichen Abbrüchen unterliegt wie die heutige Wache: unbekannt. Einstellung je Projekt/Sitzung nötig. | geprüft: [hooks](https://code.claude.com/docs/en/hooks) |
| **Hintergrund-Sitzungen** (`claude --bg`, `claude agents`) | Ein Supervisor-Dienst hält Sitzungen ohne Terminal am Leben und **startet unerwartet beendete neu**. Eine Liste aller Sitzungen. | Würde Abstürze ganzer Agenten abfangen. | Research Preview. Eine ruhende, nicht verbundene Sitzung wird nach ~1 h angehalten, außer sie ist angeheftet (Ctrl+T). Ob eine Sitzungs-Nachricht eine angehaltene Sitzung weckt, sagt die Doku nicht. Anderer Start als heute (Windows-Terminal-Tabs). | geprüft: [agent-view](https://code.claude.com/docs/en/agent-view) |
| **Agent Teams** | Ein Lead + Teammates in **einer** Sitzung, gemeinsame Aufgabenliste, Postfach. | Für kurze Recherche-/Review-Runden. | Experimentell, standardmäßig aus; ein Team je Sitzung; `/resume` holt Teammates nicht zurück; geteilte Fenster nicht im Windows Terminal; deutlich mehr Tokens. **Für Tage-Betrieb ungeeignet.** | geprüft: [agent-teams](https://code.claude.com/docs/en/agent-teams) |
| **Claude Agent SDK** | Claude Code als Bibliothek (Python/TypeScript) mit Werkzeugen, Hooks, Sitzungen. | Grundlage, falls die AMW Agenten **selbst** starten soll. | Ein Produkt für andere darf **keine claude.ai-Anmeldung** (Abo) anbieten, nur API-Schlüssel → für Nutzer teurer als das Abo. Für das Produktbild (→ 01, „für andere Nutzer“) heißt das: Die AMW koordiniert Claude-Code-Sitzungen, die jeder Nutzer selbst mit seinem Konto startet, statt sie selbst zu betreiben. | geprüft: [agent-sdk/overview](https://code.claude.com/docs/en/agent-sdk/overview) |
| Variable `CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP` (Frage 334) | Schaltet das Beenden von Hintergrund-Shells bei Speicherdruck ab. | Würde genau unsere Abbrüche verhindern – wenn sie unter Windows wirkt. | **Widerspruch:** Doku wörtlich „Windows has no memory-pressure signal, so this variable has no effect there.“ Die Meldung von Claude Code bei uns unter Windows (CC3: 31.10. ~13:20/~21:10, 01.11. ~01:06, je 5,1–5,2 GB frei; CC4 gleicher Wortlaut) lautet dagegen „…was stopped because the system is running low on memory … The user can turn this behavior off by starting Claude Code with CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP=1“. Die Doku ist hier vermutlich älter als 2.1.309. Kostet nichts, ein Versuch lohnt; echter Speichermangel trifft dann aber andere Prozesse (§8 P1). | geprüft: [env-vars](https://code.claude.com/docs/en/env-vars); Wortlaut: Bus #16172, #16173 |

### 2.2 Fremde Werkzeuge
| Werkzeug | Was es ist | Löst es unser Problem? | Quelle |
|---|---|---|---|
| CrewAI, LangGraph, AutoGen/AG2, MetaGPT, OpenHands | Eigene Agenten-Laufzeiten (Frameworks) | **Nein.** Sie zielen auf automatisierte Abläufe und ersetzen Claude Code, statt ein Team aus bestehenden Claude-Code-Sitzungen mit menschlichem Entwickler zu führen; Umzug aller Regeln und Abläufe, Abrechnung über API. | CC3; bestätigt die TL-Erwartung (§7) |
| Ruflo / claude-flow | Großer Schwarm-Orchestrator für Claude Code mit Vektor-Gedächtnis | Nein – kein Wecken, keine Freigabe-Oberfläche, viel Neues. | CC3 |
| Claude Squad | Mehrere Sitzungen in tmux | Nein – unter nativem Windows kaputt, AGPL. | CC3 |
| Vibe Kanban | Kanban-Oberfläche für Agenten | Nein – Hersteller hat Schließung angekündigt. | CC3 |
| **MCP Agent Mail** (Rust) | Postfach je Agent mit Threads, Quittungen, Datei-Reservierungen; Git-Archiv + SQLite; Web-Oberfläche mit „Overseer“; Windows-Build; MIT mit Zusatzklausel | **Teilweise** – kommt dem heutigen Bus am nächsten, aber Zustellung nur per Abholen, **weckt nicht**. Ideen übernehmen (Quittungen, Datei-Reservierungen), nicht das Werkzeug. | geprüft: [GitHub](https://github.com/Dicklesworthstone/mcp_agent_mail_rust) |
| Dashboards (claude-agents-dashboard, claude-view, claude-dash, ccboard, Marc Nuris Herzschlag-Dashboard) | Übersicht/Kanban über laufende Sitzungen, teils über das Agent SDK | Nein – Überwachung ohne Wecken, ohne Fragen-/Beschluss-Führung. Der Herzschlag-Ansatz entspricht unserem Puls. | Web-Suche 01.11., nicht einzeln geprüft |

### 2.3 Fazit Marktvergleich
- Kein fertiges Werkzeug löst „5–8 lokale Claude-Code-Sitzungen über Tage, zuverlässig wecken, Gedächtnis über Komprimierung, Entscheidungs-Oberfläche für den Entwickler“ – und erst recht nicht das Produktbild aus 01 (installierbar, allgemein, lokal + zentral, Veröffentlichen).
- Das Kernproblem ist das **Wecken**, nicht die Datenbank. Dafür gibt es seit Claude Code 2.1.234 ein Bordmittel (Pipe + Schlüssel), das ein eigener Dienst nutzen kann.
- Für das **Gedächtnis** gibt es ebenfalls ein Bordmittel (SessionStart-Hook bei `compact`), das wir schon einsetzen – es fehlt der richtige Inhalt.
- Selbst bauen muss man den Kleber: Datenmodell, Dienst, Abgleich, Oberfläche. Das deckt sich mit dem TL-Vorschlag (§7).

## 3 Lösungswege
| | Idee | Für | Wider | Aufwand (Schätzung CC3) |
|---|---|---|---|---|
| **A** | Heutiges System aufräumen und härten: feste Tabellen-Struktur, Alt-Teile raus, Dienst + Weckruf, eine Workbench-Seite in `bus.py` | wenig Umbau, alles Wissen bleibt, schrittweise und jederzeit abbrechbar; alle vier befragten Agenten empfehlen A (#16153–#16156) | `bus.py` bleibt groß (2 717 Zeilen, CLI + Server + HTML in einer Datei); LayerIT-Daten und Agenten-Bus bleiben vermischt; erfüllt das Produktbild (→ 01: allgemein, installierbar, Abgleich, Sicherheit) nicht | ≈ 6–8 Agenten-Tage |
| **B** | Auf ein fertiges Werkzeug/Framework umsteigen | fremde Pflege | Laut §2 löst keines das Wecken und die Entwickler-Oberfläche; Frameworks ersetzen Claude Code; Umzug von 1 207 Aufgaben, 16 167 Nachrichten und allen Regeln; Lernkurve aller Agenten | hoch, nicht seriös schätzbar |
| **C** | AMW als eigenes Produkt in `F:\amw` (eigenes git, später privates Repo), sauber getrennt von LayerIT | klare Grenzen, testbar, für weitere Projekte und Nutzer, eigene Release Notes; **einziger Weg, der das Produktbild (→ 01) trägt** | Doppelarbeit, wenn zu früh vom Betrieb gelöst; Umzug der Daten nötig; Sicherheit, Installation, Abgleich (→ 05 §6–§8) kommen als Aufwand dazu | ≈ A + 3–4 Tage für Trennung, Paket, Doku; Anteile aus 05 §6–§8 noch nicht geschätzt |

Mischformen sind erlaubt.

**Empfehlung CCamw: C, gebaut in Schritten wie A.** Neuer Code entsteht von Anfang an in `F:\amw` (B2363). Die heutige `bus.db` bleibt in Betrieb, bis die AMW sie Teil für Teil übernimmt. Aus B werden nur die Bordmittel aus §2.1 übernommen (Sitzungs-Nachrichten, Hooks), kein Framework.
Begründung: Die Probleme aus 04 liegen in den Mechanismen (Wecken, Rauschen, Oberfläche, Pflicht-Kontext), nicht in den Daten. A löst sie am schnellsten, aber nur der Zuschnitt C erfüllt Grundsatz 6 und das Produktbild (→ 01).

## 4 Wecken-Optionen
| | Weg | Für | Wider | Bewertung |
|---|---|---|---|---|
| W1 | Wache je Agent, endet beim Wecken (heute) | erprobt, klein, nur Standardbibliothek | Neustart hängt am Agenten (→ 04 #14); stirbt bei Abbrüchen durch Claude Code (→ 04 #1); weckt nicht bei allen Arten (→ 04 #15) | bleibt, bis W4 läuft |
| W2 | Dauer-Wache: Prozess meldet jede neue Zeile und läuft weiter (Monitor-Werkzeug) | kein Neustart je Wecken | Monitor hat laut CC3 eine Frist (Standard 5 min, max. 30 min) und braucht unter Windows Git Bash; Abbrüche treffen ihn evtl. auch | Versuch in einer Sitzung |
| W3 | Wache als `asyncRewake`-Hook | eingebautes Mittel | Verhalten bei Abbrüchen unbekannt; Einstellung je Projekt | Versuch neben W2 |
| **W4** | **Ein Dienst außerhalb von Claude Code** (Windows-Dienst/geplante Aufgabe bzw. Container, → §7 TL-Vorschlag): beobachtet die Datenbank, weckt bei handlungspflichtigen Zeilen die Sitzung **direkt über Pipe + Schlüssel** (§2.1), prüft den Puls und meldet Ausfälle | übersteht Abbrüche und Vergessen, ein Prozess für alle, braucht keine wache Claude-Sitzung; ersetzt die Wachen je Agent ganz | Systemeingriff (richtet Marcel ein); Schlüssel-Datei je Sitzung über SessionStart-Hook | **Kern der Lösung** – Zustellweg erprobt (§8 P2) |
| W5 | TL/CC3 weckt per Sitzungs-Nachricht (heute Notlösung) | bewährt 01.11. | braucht eine wache Sitzung, die es merkt; Zuordnung Sitzung ↔ Agent geraten | Rückfall, bis W4 läuft |
| W6 | Hintergrund-Sitzungen mit Supervisor (`claude --bg`) | startet abgestürzte Sitzungen neu | Research Preview; Halt nach ~1 h ohne Anheften; anderer Start der Agenten | später prüfen |
| W7 | Variable aus Frage 334 | kostet nichts, Claude Code empfiehlt sie selbst in seiner Abbruch-Meldung | Doku sagt „unter Windows ohne Wirkung“ (Widerspruch, §2.1); bei echtem Speichermangel trifft es andere Prozesse | **Versuch ja, nicht als alleinige Lösung** – W4 bleibt nötig, weil auch Vergessen (→ 04 #14) und Abstürze abgedeckt werden müssen |

Ergänzend für alle Wege: `crossSessionInbound: accept` in den Einstellungen der Agenten (§2.1); eine feste Liste von Nachrichten-Arten mit festgelegter Weck-Wirkung (→ 04 #15). Wecken bleibt immer **lokal** auf dem Rechner der Agenten (→ 05 §7), auch wenn zentral abgeglichen wird.

## 5 Datenbank-Optionen
Grundsatz: Die Anwendung spricht über eine Datenzugriffs-Schicht, damit die Datenbank wechselbar bleibt (→ 01 Produktbild „Skalierbar“). Lokal führt immer SQLite (→ 05 §7); die Frage ist nur, **wohin zentral abgeglichen wird**.

| Option | Art | Kosten (Anbieter-Seiten, geprüft 01.11.2026) | Für | Wider | Bewertung |
|---|---|---|---|---|---|
| **SQLite lokal** | Datei | 0 | ein Rechner, wenige Schreiber; WAL passt; Änderungen billig erkennbar (`PRAGMA data_version`); keine Abhängigkeit | kann nicht benachrichtigen, nur abfragen | **lokal immer** (heute) |
| Postgres selbst betrieben | eigener Server/Webspace | Server-Kosten | volle Kontrolle, Daten im Haus | Betrieb, Sicherung, Sicherheit selbst | wenn die AMW ohnehin auf einem eigenen Webserver läuft |
| **Neon** (Postgres) | Cloud, Abrechnung nach wacher Zeit | Free: 100 CU-h je Projekt/Monat, 1 GB je Projekt, 5 GB Datenverkehr, schläft nach 5 min (nicht abschaltbar). Launch: 0,106 $/CU-h, 0,35 $/GB-Monat, kein Mindestbetrag. 1 CU ≈ 4 GB RAM. [neon.com/pricing](https://neon.com/pricing) | echtes Postgres, nach §6 im Free-Rahmen | Kosten hängen an der wachen Zeit, nicht an der Menge; Abgleich-Dienst SQLite ↔ Postgres selbst bauen | **zentral geeignet** |
| Supabase (Postgres) | Cloud mit Zusatzdiensten | Pro ca. 25 $/Monat | viele Zusatzdienste | zu teuer für den Bedarf (Marcel 08:42); lokal als Docker-Stack zu schwer | nein |
| **Turso** (libSQL) | Cloud-SQLite mit lokalen Kopien („Embedded Replicas“) | Free: 0 $, 5 GB, 500 Mio. gelesene / 10 Mio. geschriebene Zeilen je Monat, 3 GB Abgleich. Developer 4,99 $ (25 Mio. Schreib-Zeilen, 10 GB Abgleich). Abrechnung nach Zeilen, **nicht nach wacher Zeit**; ruhende Datenbanken kosten nur Speicher. [turso.tech/pricing](https://turso.tech/pricing) | gleiche SQL-Sprache wie lokal (SQLite); unser Schreibvolumen (§6) liegt bei ~1 % des Free-Rahmens; Abgleich als Bordmittel | Bindung an libSQL; wie die lokalen Kopien unter Windows/Python abgleichen (Konflikte, Offline-Schreiben) ist ungeprüft (§8 P6) | **zentral geeignet, fachlich am nächsten** |
| Mischform (lokal führend, online Abgleich) | – | – | entspricht dem Produktbild (→ 01, 05 §7) | zwei Stände, Abgleich-Konflikte (nur Status-Felder, → 05 §7) | gewählte Bauform, nicht Alternative |
| Postgres lokal / Redis Streams | – | 0 | LISTEN/NOTIFY bzw. Strom mit Quittung | wecken Claude ebenfalls nicht; Redis unter Windows nur Memurai/WSL | nein |

## 6 Kostenrechnung zentraler Speicher (CCamw, mit echten Schreibzahlen)
**Grundlage:** alle Schreibvorgänge der Bus-DB vom 18.10. bis 31.10.2026 (14 Tage, UTC, nur lesend gezählt; Skript: `F:\amw\werkzeug\neon_rechnung.py`, neu ausführbar).

| Was | 14 Tage | je Tag |
|---|---|---|
| nachricht | 6 462 | 462 |
| empfang neu / erledigt | 18 965 / 11 632 | 1 355 / 831 |
| marcel_wort · beschluss · frage_marcel | 1 069 · 329 · 147 | 76 · 24 · 11 |
| aufgabe neu / begonnen / fertig | 515 / 364 / 384 | 37 / 26 / 27 |
| **Summe** | **39 867** | **≈ 2 850** |
| Puls (6 Wachen × alle 30 s) | – | ≈ 17 300 – **bleibt lokal**, wird nicht abgeglichen |

Datenmenge: `bus.db` 25,7 MB nach ~6 Wochen → ~0,2 GB im Jahr, weit unter 1 GB.

**Neon** (wach bis 5 min nach dem letzten Abgleich, 0,25 CU angenommen – die Anbieter-Seite nennt die Mindestgröße nur in Beispielen, §8 P7). Abgleich nur, wenn seit dem letzten etwas geschrieben wurde:

| Abgleich-Takt | Abgleiche je Tag | wach je Tag | CU-h je Monat | Free (100 CU-h)? | Launch (alle CU-h bezahlt) |
|---|---|---|---|---|---|
| 1 min | 379 | 12,1 h | 91 | ja, knapp | ≈ 9,60 $ |
| 5 min | 144 | 12,1 h | 91 | ja, knapp | ≈ 9,60 $ |
| 15 min | 64 | 5,5 h | 41 | ja | ≈ 4,40 $ |
| 30 min | 36 | 3,1 h | 23 | ja | ≈ 2,40 $ |
| 60 min | 19 | 1,7 h | 13 | ja | ≈ 1,30 $ |

Speicher kostet bei Launch ≈ 0,01–0,07 $/Monat (25–200 MB).

**Ergebnis:**
- Die grobe TL-Schätzung „Abgleich alle paar Sekunden → nie schlafend → ~180 CU-h“ trifft nicht zu: Die Agenten schreiben nur ~12 h am Tag, nachts schläft die Datenbank auch bei sehr kurzem Takt. Jeder Takt bis 5 min ergibt dieselben ~91 CU-h (die Datenbank schläft ohnehin erst nach 5 min).
- **Empfehlung Neon: Takt 15 min** → ~41 CU-h, deutlich im Free-Rahmen mit Luft für Lesezugriffe von unterwegs. Jeder Lese-Zugriff von außen (Marcel unterwegs), der die Datenbank weckt, kostet ≈ 0,02 CU-h (5 min × 0,25 CU); die restlichen ~59 CU-h reichen für weit über tausend solcher Zugriffe im Monat.
- Ein zweiter Rechner mit Agenten zählt im selben Projekt mit; zwei Rechner mit versetzten Arbeitszeiten verdoppeln die wache Zeit im schlechtesten Fall → bei 15 min immer noch < 100 CU-h.
- **Turso** hat dieses Problem nicht (Abrechnung nach Zeilen): ~85 000 Schreib-Zeilen im Monat sind < 1 % des Free-Rahmens (10 Mio.), auch mit Puls wären es ~0,6 Mio. → Takt frei wählbar, auch fast live.
- Die Homepage liest nur den veröffentlichten Auszug und weckt die Datenbank nicht (→ 02 §9).

## 7 TL-Vorschlag (01.11., noch nicht entschieden)
- **Ein Dienst statt einer Wache je Agent:** läuft außerhalb von Claude Code (Windows-Dienst bzw. Container), wird bei Speicherknappheit nicht beendet, weckt die Agenten.
- **Lokal zuerst:** SQLite je Rechner mit neuer fester Struktur, jede Tabelle mit Projekt-Spalte; zentral abgeglichen (→ 05 §7).
- **Zentraler Speicher:** Postgres mit Abrechnung nach Nutzung (z. B. Neon) oder Turso; Wahl nach CCamws Rechnung.
- **Server:** Python als Dienst mit Selbst-Neustart; Oberfläche als eine Web-App.
- **Datenzugriffs-Schicht:** Datenbank wechselbar ohne Umbau der Anwendung.
- **Projekt-Spezifisches als Erweiterung** (→ 02 §11).
- Erwartung: Fertige Frameworks (CrewAI, LangGraph …) zielen auf automatisierte Abläufe, nicht auf ein Team aus Claude-Code-Sitzungen mit menschlichem Entwickler → vermutlich schlanker Eigenbau, der Claude-Code-Bordmittel zum Wecken nutzt.

**Abgleich CCamw mit dem TL-Vorschlag:** in allen Punkten einverstanden; die Erwartung zu den Frameworks ist durch §2 bestätigt. Konkretisierungen:
- Der Dienst weckt über Pipe + Schlüssel (§2.1, W4) – das ist der „Claude-Code-Bordmittel“-Weg.
- Zentraler Speicher: beide passen preislich (§6). **Turso**, wenn sich die lokalen Kopien unter Windows/Python bewähren (§8 P6) – gleiche SQL-Sprache lokal und zentral, Kosten unabhängig vom Takt. Sonst **Neon** mit Abgleich-Takt 15 min.
- Der Pflicht-Kontext nach Komprimierung (→ 05 §4) gehört in den Dienst-Umfang: Der vorhandene Hook bleibt, sein Inhalt wird aus den Daten erzeugt (→ 04 #20).

## 8 Offene Prüfpunkte (vor Phase 3)
| | Frage | Stand |
|---|---|---|
| P1 | Woran sterben die Wachen unter Windows, und wirkt die Variable aus Frage 334 dort? | teilweise geklärt: Claude Code meldet unter Windows selbst „running low on memory“ (3 Abbrüche, je 5,1–5,2 GB frei, #16172/#16173) und nennt die Variable – entgegen der Doku. CC5 sah außerdem „[process exited while detached; exit code unknown]“ (#16170). Probe: Variable bei einer Sitzung setzen und beobachten. |
| P2 | Darf ein fremder Prozess in die Pipe einer Sitzung zustellen? | **geklärt, Probe grün (01.11.):** (a) 09:08 Zustellung in eine laufende Runde; (b) 09:10 ein losgelöster Prozess (eigener Start, Schlüssel aus einer nur für den Benutzer lesbaren Datei) hat die **ruhende** Sitzung von CCamw geweckt – neue Runde mit der Nachricht. Format nach der Auth-Zeile (nicht dokumentiert, aus claude.exe 2.1.309): `{"type":"user","message":{"role":"user","content":"…"}}`; andere Formen werden still verworfen, die Pipe antwortet nie. Die Sitzung kennzeichnet die Nachricht als „von einer anderen Claude-Sitzung“. Skript: `F:\amw\proben\p2_weckruf.py`. |
| P3 | Weckt eine Nachricht eine angehaltene Hintergrund-Sitzung? | offen (nur für W6) |
| P4 | Warum kamen die Weckrufe trotz Bypass an? | geklärt: Sender auch im Bypass; `accept` festschreiben |
| P5 | Unterliegen Monitor (W2) und asyncRewake-Hook (W3) denselben Abbrüchen? | offen – Versuch |
| P6 | Turso: Abgleich lokaler Kopien unter Windows/Python, Schreiben ohne Netz, Konflikte | offen – Anbieter-Seite beschreibt es nicht; Doku/Probe nötig |
| P7 | Neon: kleinste Rechengröße (0,25 CU angenommen) und ob der Free-Rahmen je Projekt für mehrere Rechner gilt | offen – Anbieter-Doku lesen |

## 9 Bewertung
| Kriterium | A | B | C (in Schritten) |
|---|---|---|---|
| Zuverlässigkeit | + (mit W4) | o (Wecken bleibt ungelöst) | + (mit W4) |
| Ordnung (eine Quelle) | o (Vermischung LayerIT/Bus bleibt) | − (Umzug, zwei Welten) | + |
| Bedienbarkeit | + | o | + |
| Aufwand | + (klein) | − (groß) | o (A + Trennung + Sicherheit/Abgleich/Installation) |
| Speicherbedarf | + (Standardbibliothek) | − (eigene Laufzeit) | + |
| Token-Kosten | + (Pflicht-Kontext gezielt) | − (Teams/Frameworks teurer) | + |
| Erweiterbarkeit | − | o | + |
| Produktfähigkeit | − | − (fremdes Produkt) | + |
