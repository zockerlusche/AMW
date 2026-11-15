# Release-Takt und Prüfstufen

Die AMW kann zwei Dinge für dich regeln: wie streng eine Änderung geprüft wird (Prüfstufe) und wann sie meldet, dass etwas ausgeliefert werden kann (Release-Takt). Beides ist aus, bis der Lead es einschaltet.

## Schritte
1. **Prüfstufen einschalten** Einstellungen › Projekt › Prüfstufen auf „an“. Ab dann steht oben in jeder Prüfbitte die Stufe und welche Dateien sie bestimmen.
2. **Wer prüft** Hoch – alles mit Rechte- oder Sicherheitsprüfungen: Datenbank, Anmeldung, Befehlszeile, Online-Aktionen, Dienst, Dateiaustausch, Warteschlange, Auslieferung, PHP der Online-Seite – prüft der Lead. Mittel – Oberfläche, Hilfe und anderer Code – prüft ein anderer Agent als der, der gebaut hat. Niedrig – nur Doku und Tests – braucht keine Prüfbitte.
3. **Niedrig ausliefern** Mit Merge-OK des Leads und einem grünen Gesamtlauf auf genau diesem Stand: `amw release ausliefern --zweig <zweig> --aufgabe <nr>`.
4. **Höher einstufen** Wer baut, kann eine Prüfbitte höher einstufen: `amw pruefung bitte … --stufe hoch`. Niedriger geht nicht.
5. **Release-Takt wählen** Einstellungen › Projekt › Release-Takt: sofort, täglich um eine Uhrzeit oder je Meilenstein. Ist etwas bereit – grüne Prüfung, Merge-OK, Gesamtlauf auf genau dem Stand –, bekommt der Zuständige für Merges (sonst der Lead) einmal eine Nachricht. Ausliefern tut die AMW nie selbst.
6. **Aufgaben schließt die Auslieferung** Nach `amw release ausliefern` gilt jede Aufgabe als fertig, deren grüner Stand mit Merge-OK darin steckt – Beleg ist der geprüfte Stand. Den Satz für die Versionshinweise gibst du gleich in der Prüfbitte mit: `amw pruefung bitte … --aufgabe <nr> --gruppe neu --hinweis "…"`. Offene Kriterien halten das nicht auf; der Lead erfährt sie. Wartet eine Aufgabe auf den Entwickler (etwa eine Bestätigung am Gerät), bleibt sie offen. Projekte, die über GitHub-Pull-Requests mergen: Beginnt der Titel eines gemergten PRs mit der Aufgabe („A1234: …“, „[A1234] …“) oder steht im Text „fertig: A1234“ bzw. „closes A1234“, und sind seine Prüfungen grün, steht die Aufgabe ebenfalls auf fertig (Beleg = Merge-Commit). Bloßes Erwähnen („Vorarbeit für A1235“) zählt nicht. Die AMW fragt dafür höchstens alle 5 Minuten mit `gh` im Projektordner nach – nur, wenn die Betriebsart die Verbindung erlaubt (github.com nur in „Cloud“); die Anmeldung hält `gh` selbst. Abschalten: Einstellungen › Projekt › Planung automatisch.

## Diese Werte trägst du ein
| Feld in der AMW | Bedeutung |
|---|---|
| Prüfstufen | an oder aus (Vorgabe aus) |
| Release-Takt | aus, sofort, täglich um HH:MM, je Meilenstein |
| Eigene Muster | Befehlszeile: `amw projekt einstellen 'pruef_muster={"hoch": ["src/db/*"], "mittel": ["ui/*"], "niedrig": ["docs/*", "tests/*"]}'` |

## Typische Fehler
- **„Der Stand ändert Sichtbares … – Prüfbitte nur mit Bild“** – Der Stand ändert die Seite oder die Hilfe, an der Aufgabe hängt aber kein Bild. Bild vom PC und vom Handy (390 px) ablegen: `amw dokument ablegen bild.png --art bild --aufgabe <nr> --titel …`; die Prüfbitte nennt es dann von selbst. Ausnahme nur mit `--ohne-bild <Grund>`.
- **„Version 1.2.0 ist schon vergeben“ bei der Prüfbitte** – Eine andere Aufgabe trägt diese Nummer schon (offene oder grüne, noch nicht ausgelieferte Prüfung), sie liegt nicht über main oder es gibt den Tag schon. Die Meldung nennt die nächste freie Nummer; die im Stand ändern und neu einreichen.
- **„Prüfstufe hoch – prüfen muss …“** – Die Prüfbitte ging an einen Agenten, die Stufe verlangt den Lead. Prüfbitte an den Lead stellen.
- **„Prüfstufe unbekannt“** – Die AMW konnte die geänderten Dateien nicht lesen: Projektordner fehlt oder der Stand ist dort unbekannt. Sie zählt dann wie hoch.
- **Keine Nachricht im Takt „je Meilenstein“** – Es meldet sich erst, wenn jede offene Aufgabe des Meilensteins bereit ist.
