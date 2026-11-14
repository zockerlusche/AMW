# Release-Takt und Prüfstufen

Die AMW kann zwei Dinge für dich regeln: wie streng eine Änderung geprüft wird (Prüfstufe) und wann sie meldet, dass etwas ausgeliefert werden kann (Release-Takt). Beides ist aus, bis der Lead es einschaltet.

## Schritte
1. **Prüfstufen einschalten** Einstellungen › Projekt › Prüfstufen auf „an“. Ab dann steht oben in jeder Prüfbitte die Stufe und welche Dateien sie bestimmen.
2. **Wer prüft** Hoch – Datenbank, Anmeldung, Rechte, Dateiaustausch, Warteschlange, Auslieferung – prüft der Lead. Mittel – Oberfläche, Hilfe und anderer Code – prüft ein anderer Agent als der, der gebaut hat. Niedrig – nur Doku und Tests – braucht keine Prüfbitte.
3. **Niedrig ausliefern** Mit Merge-OK des Leads und einem grünen Gesamtlauf auf genau diesem Stand: `amw release ausliefern --zweig <zweig> --aufgabe <nr>`.
4. **Höher einstufen** Wer baut, kann eine Prüfbitte höher einstufen: `amw pruefung bitte … --stufe hoch`. Niedriger geht nicht.
5. **Release-Takt wählen** Einstellungen › Projekt › Release-Takt: sofort, täglich um eine Uhrzeit oder je Meilenstein. Ist etwas bereit – grüne Prüfung, Merge-OK, Gesamtlauf auf genau dem Stand –, bekommt der Zuständige für Merges (sonst der Lead) einmal eine Nachricht. Ausliefern tut die AMW nie selbst.

## Diese Werte trägst du ein
| Feld in der AMW | Bedeutung |
|---|---|
| Prüfstufen | an oder aus (Vorgabe aus) |
| Release-Takt | aus, sofort, täglich um HH:MM, je Meilenstein |
| Eigene Muster | Befehlszeile: `amw projekt einstellen 'pruef_muster={"hoch": ["src/db/*"], "mittel": ["ui/*"], "niedrig": ["docs/*", "tests/*"]}'` |

## Typische Fehler
- **„Prüfstufe hoch – prüfen muss …“** – Die Prüfbitte ging an einen Agenten, die Stufe verlangt den Lead. Prüfbitte an den Lead stellen.
- **„Prüfstufe unbekannt“** – Die AMW konnte die geänderten Dateien nicht lesen: Projektordner fehlt oder der Stand ist dort unbekannt. Sie zählt dann wie hoch.
- **Keine Nachricht im Takt „je Meilenstein“** – Es meldet sich erst, wenn jede offene Aufgabe des Meilensteins bereit ist.
