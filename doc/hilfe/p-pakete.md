# p-Pakete schreiben (für den Lead)

Ein p-Paket ist eine kleine, klar prüfbare Aufgabe, die ein frischer `claude -p`-Arbeiter neben den interaktiven Agenten erledigt. Der Lead plant es so, dass die AMW es ohne Rückfrage starten, prüfen und zur Freigabe vorlegen kann: mit einem Abnahme-Befehl, eng gefassten Bereichen und den Angaben, womit gearbeitet wird.

## Du brauchst
- Eine Aufgabe, die für sich allein fertig werden kann – klein, ohne Optik und ohne Entscheidungen, die ein Mensch sehen muss.
- Einen Befehl, der heute rot ist und grün wird, sobald die Aufgabe erledigt ist.
- Die Rolle Lead (oder den Menschen): Paket-Angaben setzt nur, wer plant.

## Schritte
1. **Kandidaten wählen** Gut geeignet: ein Fehler mit klarem Test, eine kleine Erweiterung in wenigen Dateien, Texte oder Doku mit prüfbarem Ergebnis. Nicht geeignet: alles mit Bildschirm, GPU, viel Speicher, Oberflächen-Optik oder offenen Fragen – das bleibt bei einem interaktiven Agenten.
2. **Abnahme-Befehl schreiben** Ein Befehl, den die AMW selbst ausführt, z. B. `python -m unittest tests.test_rechner`. Er muss **vor** dem Bau rot sein – sonst prüft er nichts, und die AMW startet das Paket nicht. Ein eigener neuer Test ist meist der beste Abnahme-Befehl.
3. **Bereiche eng halten** Nur die Dateien oder Muster, die das Paket wirklich ändern darf, z. B. `amw/rechner.py,tests/test_rechner.py`. Was außerhalb liegt, gilt nach dem Lauf als Abweichung. Zwei Pakete mit überlappenden Bereichen laufen nicht gleichzeitig.
4. **Paket anlegen oder umstellen** `amw aufgabe neu --titel … --paket p --pruefbefehl "python -m unittest tests.test_rechner" --dateien amw/rechner.py,tests/test_rechner.py --bogen <nr>` – oder eine vorhandene Aufgabe mit `amw aufgabe aendern <nr> --paket p …`. Fehlt etwas, sagt die AMW es gleich als „Achtung“.
5. **Prüfen und freigeben** `amw paket zeigen <nr>` zeigt alle Angaben, auch die Vorgaben. Steht alles, gibt `amw paket zustand <nr> startklar` das Paket zum Start frei.

## Diese Werte trägst du ein
| Feld in der AMW | Woher |
|---|---|
| `--paket` | `p` für einen `claude -p`-Arbeiter; `agent` (Vorgabe) für einen vorhandenen interaktiven Agenten; `sitzung` für eine neue Sitzung |
| `--pruefbefehl` | der Abnahme-Befehl – Pflicht bei `p`, vor dem Bau rot |
| `--dateien` | die Bereiche – Pflicht bei `p`, so eng wie möglich |
| `--modell`, `--effort` | wie `claude --model` / `--effort`; Vorgabe claude-opus-5-5 und high, für einfache Pakete reicht oft medium |
| `--gewicht`, `--ressourcen` | leicht (Vorgabe) / schwer; gpu, bildschirm – mit schwer oder Ressourcen startet die AMW ein p-Paket nicht |
| `--nach` | erst nach diesen Aufgaben (wie bisher) |
| `--nie-gleichzeitig` | nie gleichzeitig mit diesen Aufgaben, z. B. `A12,A13` |
| `--gleiche-ressource` | ein Name; Pakete mit demselben Namen laufen nacheinander |
| `--pakettyp` | `normal` (Vorgabe) oder `test-schreiben`, wenn das Paket nur einen neuen Test schreibt |
| `--rang` | kleiner = früher (wie bisher) |

## Typische Fehler
- **„Achtung: Art p ohne Abnahme-Befehl“ / „ohne Bereiche“** – Die AMW startet das Paket so nicht. `--pruefbefehl` bzw. `--dateien` nachtragen.
- **„Achtung: Art p mit Gewicht schwer oder Ressourcen“** – Ein p-Paket läuft nur leicht und ohne GPU oder Bildschirm. Entweder kleiner schneiden oder als `--paket agent` einem interaktiven Agenten geben.
- **„… → … geht nicht“ bei `amw paket zustand`** – Der Wechsel ist nicht erlaubt; die Meldung nennt, welche Zustände von hier aus möglich sind.
- **„Paketfelder setzt der Lead“** – Ein anderer Agent hat versucht, Paket-Angaben zu setzen. Das plant der Lead.

## Danach
- **In der Workbench verfolgen:** Arbeit › Pakete zeigt jedes Paket mit Art, Zustand, Kosten und – wenn es nicht startet – dem Grund in Worten (etwa „Startet nicht: alle Arbeitsplätze belegt“). Bei „wartet auf Lead/dich“ steht, wer dran ist. Am PC kannst du dort ein Paket vorziehen oder zurückstellen, alle neuen Starts pausieren, einem laufenden Arbeiter mit „Mitlesen“ zusehen und ihn mit „Notbremse“ samt Unterprozessen beenden – jeder Eingriff steht im Planungs-Protokoll. Online und am Handy siehst du die Liste nur; gesteuert wird am PC. „Was bedeuten die Zustände?“ unter der Liste zeigt, welcher Zustand als fertig, läuft, wartet oder blockiert zählt.
- Die AMW führt jedes p-Paket durch seine Zustände: Entwurf → startklar → läuft → abgegeben → in der Abnahme → bereit zum Merge → gemergt → fertig. Daneben: blockiert (Frage offen), unklar (keine Schlusszeile), wartet auf interaktiv, abgebrochen, zurückgestellt. In Planung und Übersicht steht ein p-Paket wie jede Aufgabe als läuft, wartet, blockiert oder fertig.
- Aufgaben mit `--paket agent` (die Vorgabe) haben keine dieser Zustände – für sie gilt der Status der Aufgabe wie bisher.

## Häufige Fragen
### Was ist ein guter Abnahme-Befehl?
Einer, der genau das prüft, was das Paket liefern soll, schnell läuft und heute rot ist. Ein ganzer Testlauf ist zu breit; ein einzelner neuer Test oder eine kleine Testklasse ist ideal.

### Wann `--nach`, wann `--nie-gleichzeitig`, wann `--gleiche-ressource`?
`--nach`: das Paket braucht das Ergebnis der anderen Aufgabe. `--nie-gleichzeitig`: die beiden stören sich, egal in welcher Reihenfolge. `--gleiche-ressource`: viele Pakete teilen sich etwas (z. B. dieselbe Testdatenbank) – sie bekommen denselben Namen und laufen nacheinander.

### Ein p-Paket hängt fest – wie gebe ich es einem interaktiven Agenten?
Steht es auf „wartet auf interaktiv“, „blockiert“, „unklar“ oder „abgebrochen“: `amw aufgabe aendern <nr> --paket agent --agent <Kennung>`. Ab dann gilt wieder der normale Status der Aufgabe; die Zustände bis dahin bleiben im Planungs-Protokoll.

### Was macht der Pakettyp „test-schreiben“?
Für Pakete, die nur einen neuen Test schreiben. Bei ihnen ist der Abnahme-Befehl vor dem Bau naturgemäß nicht rot; dafür muss der neue Test gegen den alten Stand rot und gegen den neuen grün sein, und der Lead liest ihn.
