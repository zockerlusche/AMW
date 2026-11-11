# Schwere Läufe: Tests und Builds über die Warteschlange

Mehrere Projekte teilen sich einen PC. Starten Test-Suiten, Builds oder Bild-Läufe gleichzeitig, reicht der Arbeitsspeicher nicht und alle scheitern. Die AMW reiht solche Läufe deshalb in eine Warteschlange für den ganzen Rechner ein – von selbst, ohne dass ein Agent daran denken muss.

## Du brauchst
- Agenten-Ordner, die die AMW eingerichtet hat (`amw einrichten agenten-ordner <ordner>`).
- Den Schalter „Schwere Befehle über die Warteschlange“ unter Einstellungen › Dieser PC (ist ab Werk an).

## Schritte
1. **Ordner auf den neuen Stand bringen** Für jeden Agenten-Ordner einmal `amw einrichten agenten-ordner <ordner>` ausführen. Das ergänzt den Hook; laufende Sitzungen übernehmen ihn nach wenigen Sekunden.
2. **So läuft es dann** Startet ein Agent einen schweren Befehl direkt (zum Beispiel die ganze Test-Suite), wird der Befehl nicht ausgeführt. Der Agent bekommt stattdessen den fertigen Ersatz: `amw lauf ausfuehren --beschreibung "Test-Suite" -- <sein Befehl>`. Der wartet, bis der Rechner frei ist, läuft dann und gibt das Ergebnis zurück.
3. **Eigene Befehle ergänzen** Unter Einstellungen › Projekt › „Weitere schwere Befehle“ je Zeile einen Eintrag `Name = Muster` eintragen, zum Beispiel `Karten rechnen = karten\.py`.
4. **Bedarf nennen** Wer weiß, was ein Lauf braucht, gibt es an: `--braucht-gb 4` (Arbeitsspeicher), wahlweise `--braucht-vram-gb` (Grafikspeicher) und `--braucht-platte-gb` (freier Platz). Ohne Angabe rechnet die AMW mit der Speicher-Grenze des Projekts.
5. **Nachsehen** Start › Leitstand › „Rechner“ zeigt, wie viele Läufe laufen und warten und wann der Rechner voraussichtlich frei ist.

## Diese Werte trägst du ein
| Feld in der AMW | Woher |
|---|---|
| Schwere Befehle über die Warteschlange (Dieser PC) | an lassen; aus heißt: Agenten starten alles direkt |
| Arbeitsspeicher-Reserve (Dieser PC) | so viel bleibt für dich frei, Vorgabe 3 GB |
| Weitere schwere Befehle (Projekt) | Name = Muster, ein Eintrag je Zeile; das Muster ist ein regulärer Ausdruck |

## Typische Fehler
- **Ein Agent startet Tests weiter direkt** – Sein Ordner hat den Hook noch nicht: `amw einrichten agenten-ordner <ordner>` ausführen.
- **Ein Lauf wartet lange** – Im Leitstand steht, warum: der Rechner ist belegt oder es ist zu wenig Arbeitsspeicher frei. Der Mensch kann einen Lauf vorziehen (`amw lauf vorziehen <nr>`).
- **Ein einzelner kurzer Test wird abgewiesen** – Das Muster ist zu weit gefasst. Einzelne Test-Module bleiben frei; eigene Muster enger fassen.
- **„Muster ungültig“** – Das Muster ist kein gültiger regulärer Ausdruck, zum Beispiel fehlt eine Klammer.

## Danach
- Als schwer gelten ab Werk: ganze Test-Suiten, Browser-Tests, Builds und der Abzug des Web-Zweigs.
- Über Läufe eines anderen Projekts sieht man nur, dass der Rechner belegt ist und bis wann – nie, was dort läuft.
- Jeder Rechner hat seine eigene Warteschlange.

## Häufige Fragen
### Was passiert, wenn der Hook einmal nicht funktioniert?
Dann läuft der Befehl ganz normal – gesperrt wird bei einem Fehler nie. Der Fehler steht im Protokoll `%LOCALAPPDATA%\amw\hook-fehler.log` auf diesem PC; steht dort etwas, lohnt ein Blick, weil schwere Befehle dann wieder direkt starten.

### Kann ich das für einen Rechner abschalten?
Ja: Einstellungen › Dieser PC › „Schwere Befehle über die Warteschlange“ ausschalten. Die Warteschlange selbst bleibt, nur das Abweisen entfällt.
