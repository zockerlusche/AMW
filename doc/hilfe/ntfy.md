# Benachrichtigungen aufs Handy mit ntfy

Die AMW schickt dir eine kurze Nachricht aufs Handy, wenn etwas auf dich wartet – eine Frage, eine Freigabe, ein Halt. ntfy ist dafür der einfachste Weg: eine kostenlose App und ein geheimer Kanalname.

## Du brauchst
- Die AMW läuft auf diesem PC (der Wächter ist eingerichtet).
- Die App **ntfy** auf dem Handy (Google Play, F-Droid oder App Store).

## Schritte
1. **Kanal erzeugen** Am PC den Befehl `amw push ntfy` ausführen. Die AMW erzeugt einen zufälligen, geheimen Kanalnamen, zeigt ihn an und trägt ihn ein – er steht danach unter Einstellungen › Benachrichtigungen aufs Handy bei „Kanal (Topic)“.
2. **Kanal im Handy abonnieren** In der App auf „+“ tippen, den Kanalnamen genau so eintragen und abonnieren. Der Server bleibt `ntfy.sh`, außer du betreibst einen eigenen.
3. **Link setzen** Damit ein Tipp auf die Nachricht die richtige Seite öffnet: unter Einstellungen › Online-Seite die „Adresse der Online-Seite“ eintragen (`https://…`). Als Befehl: `amw push link https://deine-seite.example/`.
4. **Einschalten und testen** Den Hauptschalter „Benachrichtigen“ und ntfy einschalten, speichern und „Probe ntfy“ drücken. Als Befehl: `amw push an`, dann `amw push probe ntfy`. Die Probe kommt nach wenigen Sekunden an.

## Diese Werte trägst du ein
| Feld in der AMW | Woher |
|---|---|
| Kanal (Topic) | erzeugt die AMW – im Handy genau so abonnieren |
| Server | `https://ntfy.sh` oder die Adresse deines eigenen ntfy-Servers |
| Adresse der Online-Seite (Abschnitt Online-Seite) | Adresse deiner Online-Seite |

## Typische Fehler
- **Die Probe kommt nicht an** – Der Kanalname im Handy weicht ab (Groß- und Kleinschreibung zählt) oder die App darf keine Mitteilungen zeigen.
- **Nachrichten kommen verspätet (Android ohne Google-Dienste)** – In der App „Sofortige Zustellung“ einschalten.
- **Es kommt gar nichts mehr** – Der Wächter läuft nicht (`amw dienst status`); er verschickt die Nachrichten.
- **„ntfy-Server: https://…“** – Die Adresse des Servers muss mit `https://` beginnen.

## Danach
- Der Kanalname ist wie ein Passwort: Wer ihn kennt, kann mitlesen. Die Nachrichten nennen deshalb nur, dass etwas wartet – keine Inhalte.
- Ruhezeit und „Was gemeldet wird“ stellst du an derselben Stelle ein.

## Häufige Fragen
### Kann ich einen eigenen ntfy-Server benutzen?
Ja. Trage seine Adresse bei „Server“ ein und abonniere den Kanal in der App auf diesem Server.

### Geht es auch ohne ntfy?
Ja, über Pushover oder Telegram – beide stehen daneben in den Einstellungen.
