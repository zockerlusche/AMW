# 03 · Ist-Stand (Projekt LayerIT, 01.11.2026)

Nur Bestand. Bewertung → 04, Anforderungen → 05. Zahlen geprüft von CCamw am 01.11. ~08:30 per Abfrage auf `bus.db` (nur lesend) und Datei-Zählung; Fundstellen als `Datei:Zeile` relativ zu `F:\agent-bus\projekt-netly\`. Grundlage: CC3-Inventur `cc3\a1207\inventur_*.txt` (nachgeprüft).

## 1 Beteiligte
| Wer | Wo läuft er | Rolle heute |
|---|---|---|
| Marcel | Windows-PC, Claude-App | Entwickler, Entscheidungen, Tests am Schirm |
| TL | Claude-Sitzung in der Cloud, Zugriff auf den PC über die Desktop-App (Ordner, SQLite-MCP, Shell-VM) | Führung, Kontrolle, Doku |
| CC1 | Claude Code (Windows Terminal, F:\layerit) | Bauer Code |
| CC2 | dto. | Prüfer (Abläufe, Abnahme am Schirm, Testbuilds) |
| CC3 | dto. | Merge-Dienst, Bus-Werkzeuge, Wache |
| CC4 | dto. | Werte, Daten, Pläne |
| CC5 | dto. | Web (Homepage, Wiki, Objekt-Seite), Grafik |
| CC6 | aus (letzter Puls 28.10.) | früher Bauer/Doku-Umbau |
| CC7 | dto. wie CC1 | nur 3D (ruht, letzter Puls 30.10.) |
| CC8 | geschlossen (nie gepulst) | Prüfer 2 |
| CCamw | Claude Code in F:\amw | nur AMW (B2364); nicht in `meta.agenten`, bekommt nur direkt adressierte Nachrichten |

- Start der Agenten: `layerit-agenten.ps1:26` – je Agent ein Tab mit `claude --remote-control '<Name>' --effort … --dangerously-skip-permissions` (alle Sitzungen laufen also im Bypass-Modus; wichtig für Sitzungs-Nachrichten → 06 §4).
- Einstellungen der Agenten-Sitzungen (Auskunft CC1–CC5, #16170–#16174): `crossSessionInbound` ist **nirgends** gesetzt; Hooks nur in der Projekt-Einstellung `F:\layerit\.claude\settings.local.json` (bei CC5 noch `F:\netly\.claude\settings.local.json`): PreCompact + SessionStart(compact) → `hooks/compact_schutz.py` (§3). Benutzer-Einstellung `~/.claude/settings.json` ohne Hooks und ohne env.
- Empfänger von Rundschreiben: `meta.agenten` = `TL,CC1,CC2,CC3,CC4,CC5`.
- Status je Agent: `agent_status` (10 Zeilen: TL, CC1–CC8, CCamw; Spalten soll, zustand, letzter_puls_utc, aufgabe_id, taetigkeit, puls_grenze_s). Der TL pulst dort nicht (letzter Puls 18.10.).

## 2 Bus-Datenbank
`bus.db` – SQLite im WAL-Modus, 25,7 MB, Schema-Version 7 (`meta.schema_version`). 32 Tabellen, 17 Sichten, 7 Trigger, 8 Indizes.

| Bereich | Tabellen (Zeilen 01.11.) |
|---|---|
| Kommunikation | nachricht (16 167), empfang (55 793), agent_status (10), pause (0) |
| Arbeit | aufgabe (1 207), frage_tl (129), auftrag_entwurf (13) |
| Entwickler | marcel_wort (1 156), frage_marcel (348), frage_verlauf (111), beschluss (1 422) |
| Regeln | kernregel (18: Nr. 9, 10, 12, 15–27, 29, 30 – Arbeitsregeln), baugesetz (31 – Spielregeln) |
| Stand/Gedächtnis TL | tl_stand (74) |
| Release | release (145), devlog_post (16) |
| Projekt-Daten LayerIT | asset_herkunft (653), rezept_audit (221), rolle_uebersicht (175), bewertung (145), geraet_inventur (92), aera_durchgang (83), objekt_entwurf (74), objekt_vorgang (21) |
| Technik | meta (8), schema_log (33), nutzung_log (13), sqlite_sequence |
| Alt, zum Entfernen vorgesehen (A1206, noch vorhanden) | marcel_wahl (15), marcel_notiz (5), marcel_aufgabe_meldung (6), marcel_reihenfolge (0), wunsch (2) |

**Letzte Nutzung der Alt-Tabellen:** marcel_aufgabe_meldung 11.10., marcel_wahl/marcel_notiz 15.10. (letzte Antwort über die Fragen-Seite), bewertung 18.10., nutzung_log 19.10., wunsch 19.10., frage_verlauf 06.10. (seither nicht mehr geschrieben), pause und marcel_reihenfolge nie.

**Stand der Inhalte:**
- aufgabe: wartet 244 · läuft 1 · blockiert 12 · fertig 892 · verworfen 58.
- frage_marcel: offen 12 · beantwortet 300 · verworfen 36.
- beschluss: gilt 1 288 · ueberholt 44 · unklar 90; **142 ohne zeit_utc** (nur angelegt_utc).
- marcel_wort: 1 155 aus dem TL-Chat, 1 aus dem CC5-Chat; keine aus der Seite.
- devlog_post: alle 16 im Status „entwurf“, keiner veröffentlicht.
- empfang: **15 048 Zeilen nie erledigt** (TL 6 537, CC4 2 095, CC5 2 014, CC1 1 879, CC2 1 625, CC3 761, CC6 110, Marcel 18, sonstige 9).
- nachricht seit 25.10.: 3 281, davon 1 576 (48 %) Job-Zeilen (RECHEN-JOB, LEICHT-JOB, MESSFENSTER und deren ENDE).

**Nachrichten-Arten:** `bus.py:65` kennt 8 Arten (auftrag, meldung, frage, push_ok, push_bitte, abnahme, marcel, info) und speichert andere nur mit Hinweis (`bus.py:236`). Seit 20.10. tatsächlich benutzt: 22 Arten (meldung 4 509, auftrag 377, info 149, takt 110, frage 58, antwort 34, entscheid 33, freigabe 31, entscheidung 30, korrektur 26, regel 12, bug 9, ergaenzung 8, hinweis 7, stopp 4, storno 3, pruefung 3, lob 3, prio 2, eilig 2, befund 2, rueckmeldung 1). Die Wache weckt nach einer **dritten**, eigenen Liste (→ §5).

Sichten (17): v_agenten, v_ampel, v_bewertung, v_frage_verlauf, v_marcel_dran, v_marcel_historie, v_marcel_historie_verlauf, v_marcel_in_klaerung, v_marcel_luecken, v_marcel_offen, v_offen, v_pflege, v_punkte_offen, v_tl, v_tl_eingang, v_toepfe_offen, v_warteschlange. v_offen, v_tl und v_tl_eingang zählen die nie erledigten Empfänge mit.

Trigger (7, alle auf aufgabe): aufgabe_status_ins/_upd (nur wartet|laeuft|blockiert|fertig|verworfen), aufgabe_einstufung_ins/_upd/_neu (nur aktiv|keine_prio|geparkt|pool_ausloeser), aufgabe_geparkt_zeit (stempelt geparkt_utc), aufgabe_zu_fragen (markiert hängende Fragen beim Schließen).

Schreibwege: Agenten über `bus.py` (posten, erledigt, aufgabe, puls …); der TL per SQL (SQLite-MCP); der Server über POST-Wege (§4); die Wache schreibt nur den Puls in agent_status (`werkzeug/wache.py:118`). Eine Besitz-Prüfung (darf dieser Agent diese Aufgabe schließen?) gibt es in `bus.py` nicht.

## 3 Programme
| Datei | Zeilen | Aufgabe | Lebt? |
|---|---|---|---|
| bus.py | 2 717 | Kommandozeile für Agenten (posten, lesen, Status, Aufgaben …), HTML-Erzeugung, Schema und Web-Server `serve` in einer Datei | ja |
| bus_ablauf.py | 506 | Live-Seite `/` aus bus_ansicht.html + `/api/ablauf` (`bus_ablauf.py:441`) | ja |
| bus_objekte.py | 1 382 | Objekt-Editor `/objekte` | ja |
| bus_bau.py | 1 155 | Bau-Editor `/bau` (Parallelwelt) | ja |
| bus_netz.py | 814 | Netz-Karte `/netz` | ja |
| bus_wissen.py | 549 | `/wissen` (Beschlüsse, Wortlaut, Suche) | ja |
| bus_rollen.py | 182 | `/rollen` | ja |
| bus_aera.py | 109 | `/aera` | ja |
| bus_wunsch.py | 176 | `/api/wunsch` (Wünsche aus der Netz-Karte); noch eingebunden in `bus.py:2548` und `bus_netz.py:240` | alt, zum Entfernen (A1206) |
| zeitstrahl.py | 684 | Timeline (git + DB) | ja |
| werkzeug/wache.py | 269 | Wache je Agent (→ §5) | ja |
| hooks/compact_schutz.py | 150 | Komprimierungs-Schutz (A388, 10.10.): `vorher` (PreCompact) sichert den Verlauf gepackt nach `F:\netly-repo\_verlauf\<Agent>\` (letzte 10); `nachher` (SessionStart compact) spielt bis ~2 000 Zeichen Kontext aus bus.db ein: Agent-Name, Kurzregeln (fester Text vom 10.10., verweist auf `tl_stand 04_regeln` und Pfade `F:\netly`), eigene agent_status-Zeile, offene Aufgaben, ungelesene Nachrichten. Agent-Name aus `NETLY_AGENT` oder „Du bist CCn.“ im Verlauf (`compact_schutz.py:31`, nur `CC\d+`). Vorlage: `hooks/settings.local.json.vorlage` | ja, Inhalt veraltet |
| werkzeug/zwilling.py, aera_passung.py, ram_auffuellen.py | 144/95/154 | Hilfswerkzeuge | – |
| wach_alarm.py + wach-alarm.cmd | 203 | älterer Wecker, nur noch von `cc4/test_wach_alarm.py` benutzt | tot |
| bus_backup_vor_klartext.py | 2 124 | Sicherungskopie von bus.py | tot |
| referenz_fifo_hj13.py | 40 | Referenz-Rechnung | – |

Daneben eigene Werkzeug-Kopien je Agent in `ccN\` (post.py, job_anmelden.py, warte_*.py, Schirm-Skripte).

## 4 Oberflächen
**Server:** `bus.py serve` (`bus.py:1346`, nur 127.0.0.1, Standardbibliothek `http.server`).
- **8765** – geplante Aufgabe „Netly Bus-Ansicht“ (läuft), pythonw, Prozess seit **20.10. 10:56** (12 Tage) → zeigt den Code-Stand von damals, obwohl `bus.py` seither oft geändert wurde. Startdatei auch `bus-serve.cmd:4`. Neustart nur durch Marcel.
- **8766** – zweite Instanz von CC5 seit 01.11. 05:34 (Objekt-Editor mit neuem Code).
- Kein Log (`bus.py:2469` `log_message` schreibt nichts, weil pythonw keine Konsole hat), keine PID-Datei, keine Gesundheits-Route.

**Lese-Wege** (`bus.py:2484–2527`): `/` (Live-Seite aus bus_ansicht.html, A644) · `/v1` (alte Ansicht) · `/api/ablauf` · `/api/daten` · `/api/nachricht/<n>` · `/aera` · `/netz` · `/bau` · `/rollen` · `/objekte` · `/wissen` · `/alt` (= export_html) · `/api/zeitstrahl` · `/zeitstrahl-alt` · `/content/CHANGELOG*.md` (`bus.py:2465`).

**Schreib-Wege** (`bus.py:2539–2556`, Prüfung Herkunft 127.0.0.1/localhost in `bus.py:1599`): `/api/wahl`, `/api/notiz`, `/api/aufgabe` (Fragen-Seite „An Marcel“, heute defekt → A1206), `/api/reihenfolge`, `/api/wunsch` + `/api/wunsch_zurueck` (alt), `/bau/api/*` (Parallelwelt), `/api/objekt_entwurf`, `/api/objekt_vorgang`.

**HTML-Dateien im Bus-Ordner:**
| Datei | Stand | Lebt? |
|---|---|---|
| bus_ansicht.html (57 KB) | 31.10. | ja – Vorlage der Live-Seite `/`, wird bei jedem Abruf frisch gelesen (`bus_ablauf.py:443`) |
| bus-ansicht.html (737 KB) | 09.10. | tot – alter Export von `export_html`; `/alt` erzeugt die Seite live neu |
| bus-zeitstrahl.html (255 KB) | 09.10. | tot – alter Export; `/zeitstrahl-alt` erzeugt live |

## 5 Kommunikationsfluss
1. Marcel → TL: Chat. TL schreibt jeden Satz wörtlich nach marcel_wort, Festlegungen nach beschluss.
2. TL → Agent: Zeile in nachricht + je Empfänger eine Zeile in empfang (Status offen → erledigt per `bus.py erledigt`).
3. Agent ↔ Agent: dasselbe über `bus.py posten`.
4. **Wecken** (`werkzeug/wache.py`): jeder Agent startet seine Wache selbst als Hintergrund-Prozess seiner Claude-Code-Sitzung. Sie prüft alle 2 s `PRAGMA data_version`, pulst alle 30 s in agent_status und **beendet sich** bei einer handlungspflichtigen Zeile für genau diesen Agenten – das Prozess-Ende weckt den Agenten, der sie danach neu starten muss. Handlungspflichtig: Arten in `WECK_ARTEN` (`wache.py:33`: auftrag, stopp, entscheidung, entscheid, frage, antwort, freigabe, eilig, storno, korrektur, regel); meldung/befund nur, wenn der Agent einziger Empfänger ist; neue oder freigegebene Aufgabe. Ausgenommen: Job-/Messfenster-Zeilen. Rückfall: nach 2 h (`--max`) endet sie still. Je Agent höchstens eine Wache (PID-Datei `werkzeug/wache_<Agent>.pid`). Stand 01.11. 08:30: Wachen für CC1–CC5 und CCamw laufen.
   - Die Arten push_bitte, abnahme, push_ok und marcel aus `bus.py:65` stehen **nicht** in `WECK_ARTEN`; info, takt, hinweis, bug, ergaenzung, pruefung, prio, rueckmeldung wecken ebenfalls nicht.
   - Zweiter Weg (Notlösung): CC3 oder TL weckt per Claude-Code-Sitzungsnachricht (SendMessage), der Agent startet seine Wache neu (Marcel #14979).
5. Prüf-Kette: Bauer → Prüfbitte direkt an CC2 → grün → Merge-Bitte an CC3 → Meldung an TL. Prüfbitte und „grün“ sind Freitext in nachricht.
6. Rechen-Jobs und Schirm: Anmeldung per Nachricht (RECHEN-JOB, LEICHT-JOB, MESSFENSTER + ENDE …), ein Lauf zur Zeit; Speichergrenze (≥ 8 GB frei) nur als Text.
7. Fragen an Marcel: frage_marcel; Antworten seit 15.10. nur noch im Chat.
8. TL-Takt: Erinnerung alle 2 h (Kette einmaliger Erinnerungen in der TL-Sitzung).
9. Release Notes: release (145 Zeilen, je Push eine Version) → `content/CHANGELOG.md`; zwischen zwei Pushes keine Zeile je Merge; devlog_post nur Entwürfe.

## 6 Dateiablagen neben der DB
Zählung 01.11. im Bus-Ordner (mit Unterordnern):
- 656 Markdown-Dateien, davon 87 seit 17.10. (Beschluss „Bus = einzige Quelle“), 47 davon in `tl\`; 2 485 Text-Dateien (überwiegend Ergebnisse/Pläne als Anhang).
- Große Ordner: `ui-audit-2026-09-26` 1,5 GB, `laptop-paket` 1,2 GB, `cc3` 519 MB, `cc5` 445 MB, `cc4` 290 MB, `archiv` 102 MB, `tl` 25 MB.
- 41 lose Dateien direkt im Bus-Ordner, u. a. `channel.md` (06.10., wird im CC5-Startsatz noch genannt), `brainstorm-2026-09-26-business-auftraege.md`, `netly-agenten.ps1` (alt, ersetzt durch `layerit-agenten.ps1`), 9 × `nutzung.json.*.tmp`, `bus.db.vor-a644-einstufung`, `bus.dbclear`, `bus.py.alt-2026-10-17-vor-v7`.
- Ordnerrollen: `tl\` (Neuansatz-Papiere, Befunde, Bögen), `ccN\` (Pläne, Berichte, Prüfungen als TXT/MD, eigene Werkzeug-Kopien), `content\` (CHANGELOG), `archiv\` (Sicherungen).
- Regel heute: Wissen in die DB, Dateien nur als Anhang mit Verweis (KR17/KR30) – wird nicht durchgehend eingehalten (→ 04 §7).

## 7 Rechner
Windows 11, 31,9 GB RAM; frei am 01.11.: 4,7 GB um 03:40 (CC3-Messung, Verbraucher → `tl_stand.betrieb_0111`), 8,4 GB um 08:30.
