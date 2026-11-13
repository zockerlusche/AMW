# Den Dienst im Blick behalten

Der Dienst der AMW arbeitet in mehreren Teilen nebeneinander: die Hauptschleife (Benachrichtigen, Aufsicht, Warteschlange), der Dateiaustausch, die Synchronisierung mit dem Online-Speicher und der KI-Arbeiter. Jeder Teil meldet sich nach jeder Runde. Ein Aufpasser sieht nach, ob alle sich melden.

## Schritte
1. **Ansehen** Unter Betrieb › Dienst steht je Teil, ob er läuft, wann seine letzte Runde war, wie lange sie gedauert hat, wie oft er neu gestartet wurde und sein letzter Fehler.
2. **Auf die Farbe achten** Grün: alles in Ordnung. Gelb: die letzte Runde hatte einen Fehler, der Teil ist länger still als erlaubt oder wurde in der letzten Stunde neu gestartet. Rot: der Teil steht – dann zeigt auch die Startseite ein Band.
3. **Nichts tun müssen** Steht ein Teil länger still als erlaubt, startet die AMW ihn selbst neu und schickt dir einmal eine Nachricht. Die anderen Teile laufen dabei weiter.
4. **Nur bei der Hauptschleife eingreifen** Die Hauptschleife kann sich nicht selbst ersetzen. Steht sie, kommt eine Nachricht; dann den Dienst neu starten: `amw dienst neustart`.

## Diese Werte trägst du ein
| Teil | Erlaubte Stille |
|---|---|
| Hauptschleife | 3 Minuten |
| Dateiaustausch | 5 Minuten |
| Synchronisierung | 15 Minuten |
| KI-Arbeiter | 30 Minuten (er rechnet Aufträge in seiner Runde) |

## Typische Fehler
- **Alles rot, „Der Dienst meldet sich nicht mehr“** – Der Dienst läuft nicht oder hängt ganz. `amw dienst status` zeigt, ob er läuft; `amw dienst neustart` startet ihn neu.
- **Ein Teil bleibt gelb** – Seine letzte Runde hatte einen Fehler, etwa kein Netz für die Synchronisierung. Der Fehler steht in der Tabelle; oft löst er sich mit der nächsten Runde.
- **„aus“** – Der Teil ist in diesem Dienst nicht eingeschaltet, zum Beispiel die Synchronisierung ohne Online-Speicher.
