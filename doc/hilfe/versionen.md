# Versionen eintragen

Jede Auslieferung bekommt eine Nummer der Form MAJOR.MINOR.PATCH, zum Beispiel 1.4.0. So sieht jeder, was ausgeliefert ist, und die Versionshinweise ordnen sich danach. Die AMW erinnert daran und prüft die Nummer; eintragen muss, wer ausliefert.

## Du brauchst
- Lead oder du selbst – Agenten tragen keine Versionen ein.
- Einstellungen › Projekt › „Versionen“: Pflicht, empfohlen oder aus. Neue Projekte mit Grund-Regelwerk stehen auf Pflicht.

## Schritte
1. **Ausliefern** Wie im Projekt üblich (Merge, Tag, Paket).
2. **Eintragen** `amw release version --version 1.4.0 --titel "Kurzer Name"` – die Versionshinweise kommen aus den fertigen Aufgaben seit der letzten Version.
3. **Nummer wählen** Neues oder Verbessertes: MINOR erhöhen (1.4.0 → 1.5.0). Nur Korrekturen: PATCH (1.4.0 → 1.4.1). Bricht etwas Bestehendes: MAJOR.

## Typische Fehler
- **„hat nicht die Form MAJOR.MINOR.PATCH“** – Ohne „v“ davor und mit drei Zahlen: 1.4.0, nicht v1.4 oder 1.4.
- **„ist nicht größer als die letzte“** – Die Meldung nennt die passenden nächsten Nummern.
- **Meilenstein lässt sich nicht abschließen** – Bei Pflicht muss nach seiner letzten fertigen Aufgabe eine Version eingetragen sein. Nur du kannst trotzdem abschließen (`amw bogen status <nr> fertig --erzwingen`).

## Danach
- Der Plan-Check meldet bei Pflicht einen Fehler, solange keine Version eingetragen ist, bei „empfohlen“ einen Hinweis.
- Liegt Fertiges länger als die eingestellte Frist (Vorgabe 14 Tage) ohne Version, warnt der Plan-Check. Wartet ihr bewusst, akzeptiere die Warnung dort mit Grund.
