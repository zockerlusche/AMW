# Anleitung: Benachrichtigungen aufs Handy

AMW meldet sich auf dem Handy, wenn etwas auf dich wartet: eine neue Frage (Erinnerung nach 60 min), eine Nachricht an
dich, eine Warnung (Projekt-Server aus, Agent hängt, Lauf überfällig, Fehler, Kontext oder 5-Stunden-Grenze fast voll),
ein Agent wartet auf deine Freigabe/Eingabe, ein Halt. Die Meldung enthält **nur einen Hinweis** („Neue Frage F123 von
TL“) und einen Link – den Inhalt siehst du erst nach der Anmeldung auf deiner Seite.

Zugangsdaten liegen nur auf dem PC in `%LOCALAPPDATA%\amw\push.json` – nie im Repo, in der Datenbank oder online.
Einrichten geht am PC im Zahnrad („Benachrichtigungen aufs Handy“) oder mit der Kommandozeile.

## 1 Anbieter wählen (einer reicht, mehrere gehen)
| | ntfy | Pushover | Telegram |
|---|---|---|---|
| Kosten | kostenlos | einmalig ca. 5 $ je Plattform | kostenlos |
| Konto | keins nötig | ja | Telegram-Konto |
| Datenschutz | Kanalname = Passwort | Schlüssel | Bot-Chat (nicht Ende-zu-Ende) |

### ntfy (empfohlen)
1. Am PC: `python F:/amw/amw-cli.py push ntfy` – erzeugt einen zufälligen, geheimen Kanal und zeigt ihn an.
2. Handy: App **ntfy** installieren (Google Play, F-Droid oder App Store) → „+“ → Kanal (Topic) eintragen, Server `ntfy.sh`.
3. Link auf deine Online-Seite setzen: `python F:/amw/amw-cli.py push link https://deine-seite.example/`
4. Einschalten und testen: `python F:/amw/amw-cli.py push an` und `python F:/amw/amw-cli.py push probe ntfy`.

### Pushover
1. Konto auf pushover.net, App installieren. Benutzerschlüssel steht im Dashboard.
2. Unter pushover.net/apps/build eine App „AMW“ anlegen → App-Token.
3. `python F:/amw/amw-cli.py push pushover --app-token <Token> --user-key <Schlüssel>` → `push probe pushover`.

### Telegram
1. In Telegram @BotFather → `/newbot` → Bot-Token kopieren.
2. Deinem neuen Bot eine beliebige Nachricht schreiben.
3. `python F:/amw/amw-cli.py push telegram --token <Bot-Token>` zeigt deine Chat-ID;
   dann `push telegram --token <Bot-Token> --chat <ID>` → `push probe telegram`.

## 2 Feineinstellung
- Ereignisse an/aus: `push ereignis frage=aus` (Arten: frage, nachricht, warnung, eingabe, halt, rueckblick).
- Ruhezeit: `push ruhe 22:00-07:00` – nachts kommen nur Halt und Server-Ausfall, alles andere morgens gesammelt; `push ruhe aus`.
- Höchstens 10 Meldungen je Stunde (Zahnrad); gleiche Meldungen werden gebündelt („3 neue Fragen“).
- Stand und Versandprotokoll: `push status` oder Zahnrad.

## 3 Wenn nichts ankommt
- `push probe <anbieter>` zeigt die Antwort des Anbieters.
- `push status` → steht „AN“, ist der Anbieter „an“? Das Protokoll zeigt Fehler (z. B. falscher Schlüssel).
- Der Wächter muss laufen (`amw dienst status`); er verschickt je Aufsichtsrunde (Vorgabe 30 s).
- ntfy auf Android ohne Google-Dienste: in der App „Sofortige Zustellung“ einschalten.
