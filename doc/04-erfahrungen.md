# 04 · Erfahrungen

Was im Betrieb schiefging (Beleg) und was die AMW deshalb können muss (→ Verweis auf 02/05).

| # | Erfahrung | Beleg | Folgerung für die AMW |
|---|---|---|---|
| 1 | **Wachen sterben bei Speicherknappheit.** Claude Code beendet Hintergrund-Prozesse; der Agent schläft, bis jemand ihn weckt. | 31.10. mittags (CC1/CC4/CC7), 01.11. 01:06 (CC1/CC2/CC4/CC5 bei 5,1 von 31,9 GB frei, ohne laufende Jobs) | Wecken darf nicht an einem sterblichen Prozess hängen; Rückfall-Wecker (→ 05 §1) |
| 2 | **Rundschreiben wecken nicht.** | CC2 verschlief Meldung #15944 rund 55 min | Wecken nach Empfänger, nicht nach Art; Lesebestätigung sichtbar (→ 02 §8) |
| 3 | **Speicher wird knapp.** 9 Claude-Sitzungen + Desktop-App ≈ 5 GB, je Sitzung ein eigener Datei-MCP-Server (12× node ≈ 1,8 GB), dazu Fremdprogramme. | CC3-Messung 01.11. 03:40 | Ressourcen-Anzeige und Grenzen (→ 02 §1, 05 §2) |
| 4 | **Gedächtnisverlust beim Komprimieren** (TL und Agenten). Folge: Fragen, deren Antwort schon in der DB stand; Regeln nicht gelesen. | Fragen 341, 346; KR9/KR22 mehrfach verschärft | Pflicht-Kontext beim Start/Wiederaufnehmen automatisch anbieten (→ 05 §4) |
| 5 | **Abrutschen in Realwelt-Denken** beim Spielmodell (Push-Prinzip vergessen). | 31.10./01.11.: „Kreis“, „DNS meldet sich an“ | Projektregeln sichtbar am Arbeitsplatz; Kontrolle vor Übernahme (→ 01 Grundsatz 5) |
| 6 | **Doppelte Regeln und Tabellen;** Beschlüsse ändern Regeln, ohne dass die Regel angepasst wird. | Aufräumen 01.11. (12 Kernregeln, 10 Baugesetze entfernt) | Eine Struktur, Regel-Änderung nur an der Regel (→ 02 §7) |
| 7 | **Wissen in Dateien neben der DB** (TXT/MD-Pläne, Berichte). | tl\, ccN\ | Klare Grenze DB ↔ Anhang (→ 05 §5) |
| 8 | **Fragen-Seite still kaputt;** Entwickler muss jede Frage im Chat nachfragen. | A1206 | Festes Frage-Format, Antwort direkt gespeichert (→ 02 §6) |
| 9 | **Agent versteht Auftrag anders** als der Entwickler. | Namen B2319, Klon-Felder A1200, Bauplan H2 | TL-Kontrolle gegen festgehaltenes Modell (→ 01 Grundsatz 5) |
| 10 | **Parallele Läufe** stören sich (Schirm, Speicher). | Messfenster-Regeln, 01.11. Speicher | Lauf-Sperre und Warteschlange (→ 05 §2) |
| 11 | **Server-Änderungen wirken erst nach Hand-Neustart.** | 8765 vs. 8766 (A1197/A1200); 8765 läuft seit 20.10. 10:56 mit altem Code, ohne Log (→ 03 §4) | Server als Dienst mit Neustart (→ 05 §3) |
| 12 | **Zuständigkeit/Erreichbarkeit unklar** (wer läuft gerade?). | A1195 kurz falsch umgehängt | Agenten-Status mit Puls und Wache sichtbar (→ 02 §2) |
| 13 | **TL-Takt händisch** (Erinnerungsketten, Aufräumen). | KR21/KR29 | Takt und Erinnerungen als Funktion (→ 02 §5, 05 §1) |
| 14 | **Wache muss nach jedem Wecken von Hand neu gestartet werden;** wer es vergisst, verschläft. | CC2 sah Storno #16078 zu spät, Wache lief nach Weckung nicht mehr (#16093) | Wecker, der nach dem Wecken weiterläuft (→ 05 §1) |
| 15 | **Drei verschiedene Listen von Nachrichten-Arten.** bus.py kennt 8, die Wache weckt bei 11, benutzt werden 22; push_bitte und abnahme wecken nicht. | `bus.py:65`, `werkzeug/wache.py:33`, Zählung seit 20.10. (→ 03 §2) | Eine feste Arten-Liste mit festgelegter Weck-Wirkung (→ 02 §8) |
| 16 | **Lesebestätigung ohne Aussage.** 15 048 Empfänge nie erledigt; Sichten zeigen deshalb Tausende offene Zeilen. | empfang 01.11. (→ 03 §2) | Lesebestätigung muss stimmen, Rauschen erzeugt keine Empfänge (→ 02 §8) |
| 17 | **Rauschen im Nachrichtenstrom:** fast die Hälfte sind Job-Anmeldungen. | seit 25.10. 1 576 von 3 281 Nachrichten (→ 03 §2) | Läufe als eigene Daten, nicht als Nachricht (→ 05 §2) |
| 18 | **Keine Besitz-Prüfung:** ein Agent kann die Aufgabe eines anderen schließen. | CC2 setzte A1203 (CC1) auf fertig (#16093) | Aufgaben nur vom Zuständigen schließbar (→ 02 §4) |
| 19 | **Zeitstempel fehlen:** Beschlüsse ohne Beschluss-Zeit, Sortierung nach Zeit bricht. | 142 Beschlüsse ohne zeit_utc (→ 03 §2) | Pflichtfelder vom System gesetzt (→ 05 §5) |
| 20 | **Pflicht-Kontext nach Komprimierung gibt es schon, er reicht aber nicht.** Der Hook spielt Aufgaben und ungelesene Nachrichten ein, aber Kurzregeln vom 10.10. mit alten Pfaden. Es fehlten den Agenten: gültiger Regelstand mit Stand-Zeit/Änderungen seit dem letzten Lesen (CC3, CC5) · wer auf mich wartet und auf wen ich warte – offene Prüf- und Merge-Bitten mit SHA, die nur als Nachricht existieren (CC2, CC3, CC4) · geltende Sonderregeln/Sperren von Marcel (Nacht-Freigabe, ≥ 8 GB, „keine Rechen-Jobs“) (CC2, CC5) · Lauf-Rezepte, die im Sitzungs-Scratchpad liegen (CC1, CC3) · eigene offene Arbeitskopien/Zweige, Testserver, Jobs (CC1, CC2) · ob die eigene Wache läuft (CC4) · der heutige Bus-Weg statt channel.md (CC5). Das eigene Gedächtnis (MEMORY.md) war veraltet und wurde nicht korrigiert (CC4). | Nachfrage #16168, Antworten #16170–#16174; `hooks/compact_schutz.py` (→ 03 §3) | Pflicht-Kontext aus den Daten erzeugen statt fester Text; was er braucht, muss als Daten existieren (Prüfbitten, Sperren, Lauf-Rezepte, Arbeitskopien) (→ 05 §4) |
