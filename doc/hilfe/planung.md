# Planung: Wo stehen wir?

Die Planung zeigt auf einen Blick, welcher Meilenstein gerade aktiv ist, wie weit er ist, wer an was arbeitet und was noch keinem Meilenstein zugeordnet ist.

## Schritte
1. **„Wo stehen wir gerade?“ lesen** Ganz oben unter Planung › Zeitleiste steht der aktive Meilenstein mit seinem Fortschritt („Endversion 2.0: 3 von 8 Aufgaben erledigt · Ziel 20.11.“), das nächste Ziel und unter „Gerade in Arbeit“, welcher Agent an welcher Aufgabe arbeitet. Ein Klick auf eine Aufgabe öffnet sie.
2. **Übersicht lesen** Jeder Meilenstein ist ein Balken von seinem Start bis zur Prognose. Die senkrechte Linie mit „Jetzt“ ist jetzt; fährst du darüber, siehst du Datum, Uhrzeit und was gerade läuft. Fährst du über einen Balken oder eine Raute, siehst du Titel, Status, Fortschritt, Prognose und Zieldatum.
3. **Erledigtes einblenden (optional)** Erledigte Meilensteine sind ausgeblendet, damit das Aktive vorne steht. „Erledigte einblenden“ in der Übersicht zeigt sie, blass und mit ✓. In der Zeitleiste darunter stehen sie eingeklappt unter „Erledigte Meilensteine“.
4. **Aufgaben ohne Meilenstein zuordnen** Ganz unten in der Zeitleiste steht „Ohne Meilenstein (n)“ mit allen offenen Aufgaben, die zu keinem Meilenstein gehören. Zuordnen: `amw aufgabe aendern <nr> --bogen <nr>`.

## Diese Werte trägst du ein
| Feld in der AMW | Woher |
|---|---|
| `--bogen` beim Anlegen einer Aufgabe | Nummer des Meilensteins aus der Planung, z. B. 45 für B45 |

## Typische Fehler
- **„Zu welchem Meilenstein gehört die Aufgabe?“** – Der Lead legt eine Aufgabe an, und es gibt einen aktiven oder geplanten Meilenstein. Die Meldung listet sie auf und macht einen Vorschlag. Mit `--bogen <nr>` zuordnen oder bewusst mit `--ohne-bogen` darauf verzichten.
- **„Kein Meilenstein ist aktiv“** – Alle Meilensteine sind geplant oder fertig. Den nächsten unter Planung mit „Aktivieren“ starten.

## Danach
- „Was der Rechner heute gemacht hat“ unter der Übersicht ist eingeklappt. Ein Klick öffnet es; dort steht, welche Läufe heute auf diesem PC liefen und welche warten.

## Häufige Fragen
### Warum muss ich beim Anlegen einen Meilenstein angeben?
Damit nichts verschwindet: Eine Aufgabe ohne Meilenstein taucht in der Übersicht nicht auf. Andere Agenten als der Lead dürfen keinen Meilenstein setzen. Ihre Aufgaben stehen unter „Ohne Meilenstein“, bis der Lead sie zuordnet.
