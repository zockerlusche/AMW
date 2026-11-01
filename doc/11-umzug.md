# 11 · Umzug LayerIT-Bus → AMW (01.11.2026)

Freigabe: Marcel 01.11. 11:44 „CCAMW kann loslegen, umziehen.“ (marcel_wort #1172, TL #16280). Ablauf nach 10 §6, mit den Bedingungen des TL (Sicherung, bus.db als Rückweg, Jobs abwarten, Halt, TL-Übergabe vor dem Weiter).

## 1 Was sich ändert – in einem Satz
Nachrichten, Aufgaben, Fragen, Beschlüsse, Wortlaut und Regeln laufen ab dem Umzug über **`F:\amw\daten\amw.db`** und die Kommandozeile **`amw`**; geweckt wird vom **AMW-Wächter** (geplante Aufgabe „AMW Dienst“) über das Postfach der Sitzung – die Bus-Wache entfällt.

## 2 Für jeden Agenten (CC1–CC5, CC7)
1. Laufenden Schritt sauber abschließen. **Keine Bus-Wache mehr starten** (`wache.py`, `db_wache.py`).
2. Anmelden – einmal, aus der eigenen Claude-Code-Shell (sie kennt dein Postfach):
   `python F:/amw/amw-cli.py anmelden --von CC1`
3. Lesen: `python F:/amw/amw-cli.py lesen --von CC1` (neueste zuerst), eine ganze Nachricht: `… lesen 16290 --von CC1`.
4. Bestätigen: `python F:/amw/amw-cli.py posten --an CCamw --art meldung --kurz "CC1 umgezogen" --von CC1`
5. Ab jetzt nur noch `amw`. Du wirst geweckt, wenn eine weckende Nachricht für dich kommt (auftrag, frage, antwort, korrektur, stopp, freigabe, pruefbitte, meldung, takt; `info` weckt nicht).

`bus.py posten/lesen/erledigt/status/aufgabe/…` antworten nach dem Umzug mit „UMGEZOGEN“ und dem passenden `amw`-Befehl. Nach einem Compact liefert der bisherige Hook (`hooks/compact_schutz.py nachher`) den Kontext aus der AMW.

| bisher (bus.py) | jetzt (`python F:/amw/amw-cli.py … --von <Name>`) |
|---|---|
| `posten --von X --an Y --art A --kurz K --text T` | `posten --an Y --art A --kurz K --text T` (`--an alle` = Rundschreiben) |
| `lesen --agent X --neu` | `lesen` · ganze Nachricht `lesen <nr>` (setzt gelesen) |
| `erledigt <nr> --agent X` | `erledigt <nr> [<nr> …] [--bemerkung …]` |
| `aufgabe …` | `aufgabe liste` · `zeige <A>` · `start <A>` · `wartet <A> --wartet-auf …` · `blockiert <A>` · `fertig <A> --beleg <SHA/Nachricht>` |
| RECHEN-JOB / ENDE-Zeilen, `job_anmelden.py` | `lauf start --beschreibung … [--schirm|--leicht] [--aufgabe A]` → `lauf ende <nr> --rc 0` (prüft Halt, Speicher, einen schweren/Schirm-Lauf zur Zeit) |
| Prüfbitte als Nachricht | `pruefung bitte --pruefer CC2 --zweig … --sha … --punkte …` · Ergebnis `pruefung gruen|rot <nr>` |
| Frage an TL / an Marcel | `frage neu --an tl|entwickler --kurz … --option "A=…" --option "B=…" --empfehlung A --grund …` |
| `wache.py`, `puls` | entfällt |
| eigener Pflicht-Kontext | `kontext` |

Arten (9 + info): auftrag, frage, antwort, korrektur, stopp, freigabe, pruefbitte, meldung, takt, info. Alte Arten sind beim Übernehmen zugeordnet (eilig/vorgabe/push_bitte → auftrag, befund/fertig/abnahme → meldung, entscheidung/push_ok → freigabe …).

## 3 Für den TL (Cloud-Sitzung, nicht per Postfach weckbar)
**Nachtrag 01.11. 14:26 – Datei-Brücke:** Die Shell des TL ist eine Linux-VM, F:\amw dort per FUSE eingehängt; SQLite mit WAL scheitert darüber (`disk I/O error`, TL-Übergabe 12:35). Darum liest der TL `daten/tl_lesen.db` (Kopie ohne WAL, höchstens minütlich, `?immutable=1`) und schreibt über Befehlsdateien `eingang-tl/befehle/*.json`, die der Wächter als `--von TL` ausführt (`amw/bruecke.py`, Anleitung im Briefkasten `eingang-tl/`, der nicht ins Repo gehört). Später zusätzlich möglich: ein SQLite-MCP auf amw.db zum Lesen (Variante B, Marcel).

- **Datenbank:** `F:\amw\daten\amw.db` (SQLite, WAL). **Schreiben nur über `amw`** (Trigger prüfen Belege, Wächter weckt die Empfänger). **Lesen** über `amw` oder direkt per SQLite **nur lesend** (`file:F:/amw/daten/amw.db?mode=ro`), gezielte SELECTs wie bisher (KR26/KR30).
- **Wecken:** Dein Stunden-Takt (send_later) bleibt; je Takt `amw kontext --von TL` und `amw lesen --von TL`. Der Takt des Wächters geht nur an Leads mit Postfach – an dich also nicht, es gibt keinen doppelten Takt.
- **Halt/Weiter:** `amw halt --fuer alle --text …` / `amw weiter --fuer alle` (TL ist Lead) oder in der Workbench.

| bus.db | amw.db | Hinweis |
|---|---|---|
| marcel_wort | wortlaut | gleiche Nummern; neu: `amw wortlaut --text … --kanal chat-tl --zeit …` |
| beschluss | beschluss | gleiche Nummern; neu: `amw beschluss --stichwort … --quelle … --text …` (ersetzt: `--ersetzt B…`) |
| frage_marcel | frage (an = entwickler) | gleiche Nummern; Marcel antwortet in der Workbench |
| frage_tl | frage (an = tl) | Nummer + 5000 (T5 → 5005) |
| aufgabe | aufgabe | gleiche Nummern; Einstufung pool_ausloeser → pool, HOCH → aktiv mit Rang 10 |
| nachricht / empfang | nachricht / empfang | gleiche Nummern; Empfangsstand bleibt (offen bleibt offen) |
| kernregel | regel (ebene = arbeit) | ändern nur mit Beschluss: `amw regel --ebene arbeit --nr 26 --beschluss B… --text …` |
| baugesetz | regel (ebene = projekt) | dto. mit `--ebene projekt` |
| tl_stand | notiz | `amw notiz zeige [schlüssel]` · `amw notiz setzen <schlüssel> --text …` |
| agent_status | agent + sitzung | Zustand zeigt die Workbench (Soll/Ist, Puls des Postfachs) |
| release | release | `amw release merge|version` |

**Bitte nach dem Umzug (TL):** kernregel 26 („Umgang mit der Bus-DB“) und Startsätze, die `bus.py`/Wache nennen, per Beschluss auf `amw` umstellen.

## 4 Was bleibt, wie es ist
- **Objekt-Editor (Port 8766)** und die LayerIT-Fachtabellen bleiben in bus.db: objekt_entwurf, objekt_vorgang, wunsch, aera_durchgang, devlog_post, asset_herkunft, geraet_inventur, bewertung, auftrag_entwurf, nutzung_log, marcel_* (Seitenzustand). Das sind Projektdaten, keine Agenten-Kommunikation; `bus.py objekte` und `serve` sind nicht gesperrt. Umzug dieser Daten wäre LayerIT-Arbeit (später als Projekt-Erweiterung, 10 L10).
- **Marcel antwortet ab jetzt in der Workbench** http://127.0.0.1:8780 (auch auf dem Handy am PC). Die alte Seite 8765 läuft noch mit altem Stand; Antworten dort landen nur im Archiv.
- **Offene Empfänge** aus dem alten Bus bleiben offen (nichts wird stillschweigend erledigt); `amw lesen` zeigt die neuesten zuerst. Altbestand wurde nicht neu geweckt.

## 5 Rückweg
Wenn etwas hakt: Schalter `F:\agent-bus\projekt-netly\umgezogen.txt` umbenennen → bus.py schreibt wieder, der Compact-Hook liest wieder bus.db; Agenten starten ihre Wache wieder; Meldung an TL. bus.db ist seit dem Halt unverändert in den Kommunikations-Tabellen; Sicherungen: `archiv\bus-vor-amw-umzug-2026-11-01.db` (11:47) und `…-halt.db` (beim Halt). Originale von bus.py und compact_schutz.py: `archiv\vor-amw-umzug\`. amw.db bleibt als Stand erhalten. Wächter abschalten: `amw dienst entfernen --ja`.

## 6 Ablauf (CCamw)
| # | Schritt | Stand |
|---|---|---|
| 1 | Sicherung bus.db (VACUUM INTO, integrity ok) | ✓ 11:47 |
| 2 | Rechen-Jobs: CC1, CC5 – keiner läuft | ✓ 11:49 |
| 3 | Halt im alten Bus an alle (#16287), Quittungen sammeln | ✓ 11:57 CC1–CC5; CC7 ohne Wache (seit 30.10.) |
| 4 | zweite Sicherung, Übernahme nach daten/amw.db, Zählvergleich | ✓ 11:58 alle Zählungen gleich (bis #16293) |
| 5 | Wächter einrichten (E7), eigene Anmeldung, Weckprobe an CCamw | ✓ 11:58 eingerichtet, Workbench 200; CCamw durch die erste Bestätigung geweckt |
| 6 | Anleitung (diese Seite) als letzte Nachricht im alten Bus, dann Schalter `umgezogen.txt` | ✓ 11:59 (#16294 alt und neu) |
| 7 | Agenten melden sich an und bestätigen in der AMW; Weckprobe je Agent | CC1, CC2, CC4, CC5 umgezogen + geweckt (12:00–12:01); CC3 offen (Wache nach Halt nicht neu gestartet, braucht einen Anstoß); TL im Stundentakt |
| 8 | TL-Übergabe bestätigt → Weiter | |
