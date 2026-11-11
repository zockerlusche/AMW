# Zweiter Faktor: neues oder verlorenes Handy

Die Online-Seite verlangt beim Anmelden neben dem Passwort eine sechsstellige Zahl aus deiner Authenticator-App. Ist das Handy neu oder weg, richtest du den zweiten Faktor vom PC aus neu ein.

## Du brauchst
- Zugriff auf den PC, auf dem die AMW läuft – nur von dort lässt sich der zweite Faktor zurücksetzen.
- Benutzer und Passwort der Online-Seite.
- Eine Authenticator-App auf dem neuen Handy.

## Schritte
1. **Am PC zurücksetzen** Den Befehl `amw web zweitfaktor-neu` ausführen. Er löscht das bisherige Geheimnis im Online-Speicher; die alte App zeigt danach keine gültigen Zahlen mehr.
2. **Online anmelden** Die Online-Seite öffnen, Benutzer und Passwort eingeben und das Feld für die Zahl leer lassen.
3. **Neu scannen** Die Seite zeigt einen neuen QR-Code. Mit der Authenticator-App scannen und die erste Zahl bestätigen.
4. **Alten Eintrag löschen** Im alten Handy bzw. in der alten App den Eintrag der AMW entfernen.

## Typische Fehler
- **„Verbindung zum Online-Speicher … ist blockiert“** – Die Betriebsart lässt den Online-Speicher nicht zu; unter Einstellungen › Betriebsart „Cloud“ wählen.
- **Die Zahl wird nicht angenommen** – Die Uhr des Handys geht falsch (die Zahl gilt nur etwa 30 Sekunden) oder die Zahl wurde schon einmal benutzt; die nächste abwarten.
- **Gesperrt nach Fehlversuchen** – Nach 5 Fehlversuchen von einer Adresse ist die Anmeldung für bis zu 15 Minuten gesperrt. Abwarten; die Grenzen stehen unter Einstellungen › Online-Seite.

## Danach
- Das Zurücksetzen geht nur am PC. Wer nur das Passwort kennt, kann den zweiten Faktor nicht umgehen.
- Das Passwort bleibt, wie es war.

## Häufige Fragen
### Ich habe das Handy verloren – muss ich sofort etwas tun?
Ja: zurücksetzen (Schritt 1), damit die App auf dem verlorenen Handy keine gültigen Zahlen mehr liefert, und neu einrichten.

### Kann ich zwei Handys benutzen?
Ja, wenn beide denselben QR-Code beim Einrichten scannen. Später lässt sich ein zweites Gerät nur durch Zurücksetzen und erneutes Scannen mit beiden hinzufügen.
