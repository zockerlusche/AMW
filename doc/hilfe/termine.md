# Testtermine und Fristen

Ein Testtermin legt fest, wann du testest. Die AMW leitet daraus für alle die Frist „Testbuild fertig“ ab und zeigt mit einer Ampel, ob der verknüpfte Meilenstein bis dahin fertig wird.

## Du brauchst
- Den Zeitpunkt des Tests, bei wiederkehrenden Tests auch den Wochentag.

## Schritte
1. **Termin anlegen** `amw termin neu --titel "Wochentest" --art test --am "13.11. 18:00"` – wöchentlich mit `--woechentlich`, bis zu einem Tag mit `--bis JJJJ-MM-TT`.
2. **Mit einem Meilenstein verknüpfen (optional)** `--bogen <nummer>` anhängen. Die Ampel vergleicht dann seine Prognose mit der Frist.
3. **Vorlauf anpassen (optional)** Standard: Der Testbuild ist 4 Stunden vor dem Termin fällig. Anders mit `--vorlauf <stunden>`.

## Diese Werte trägst du ein
| Feld in der AMW | Woher |
|---|---|
| Titel | kurz, z. B. „Wochentest“ |
| Zeitpunkt | Ortszeit, z. B. „13.11. 18:00“ |
| Meilenstein | Nummer aus der Planung |

## Typische Fehler
- **„Testbuild noch nicht gemeldet“** – Der Agent meldet den fertigen Testbuild mit `amw termin bereit <termin> --text "was neu ist"`.
- **Ein einzelner Termin fällt aus** – `amw termin absagen <termin> --am "20.11. 18:00"` sagt nur dieses Vorkommen ab.

## Danach
- Termine siehst du unter Planung › Termine, den nächsten Test auch auf der Startseite.
