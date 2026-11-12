# Betriebsart wählen

Die Betriebsart legt fest, wohin diese Installation Verbindungen aufbauen darf. Sie wird an jeder Stelle geprüft, an der die AMW nach außen geht – nicht nur in der Oberfläche.

## Du brauchst
- Die AMW läuft auf diesem PC.
- Eine Antwort auf die Frage: Dürfen Daten dieses Projekts den Rechner bzw. das Firmennetz verlassen?

## Schritte
1. **Stand ansehen** Einstellungen › Betriebsart. Darunter steht die Liste „Verbindungen der AMW“: jede Adresse, zu der die AMW eine Verbindung aufbaut, und in welches Netz sie führt (dieser PC, Firmennetz, Internet). Als Befehl: `amw einrichten verbindungen`.
2. **Betriebsart wählen** Eine der drei Karten anklicken und speichern. Als Befehl: `amw einrichten betriebsart pc` (oder `server`, `cloud`).
3. **Testen** „Verbindungen testen“ drücken. Jede erlaubte Adresse wird auf Erreichbarkeit getestet (nur der Verbindungsaufbau, keine Daten). Rot ist, was eingeschaltet, aber in dieser Betriebsart blockiert ist.
4. **Aufräumen** Rote Zeilen beheben: den Dienst ausschalten (z. B. Synchronisierung aus, Benachrichtigungen aus) oder eine andere Betriebsart wählen.

## Diese Werte trägst du ein
| Feld in der AMW | Woher |
|---|---|
| Nur dieser PC | Nichts verlässt den Rechner: keine Synchronisierung, keine Online-Seite, keine Benachrichtigungen |
| Eigener Server im Firmennetz | Verbindungen nur zu Adressen im eigenen Netz (z. B. `192.168.…`, `10.…`, Namen wie `ntfy.firma.lan`) |
| Cloud | Online-Speicher, Online-Seite und Benachrichtigungs-Dienste im Internet sind erlaubt |

## Typische Fehler
- **„Betriebsart …: Verbindung zum Online-Speicher zu … ist blockiert“** – Die gewählte Betriebsart lässt diese Adresse nicht zu. Betriebsart ändern oder die Synchronisierung ausschalten.
- **Benachrichtigungen kommen nicht mehr an** – In „Nur dieser PC“ und bei Diensten im Internet auch in „Eigener Server“ werden sie nicht verschickt; im Versandprotokoll steht der Grund.
- **Ein Name im Firmennetz gilt als Internet** – Ein Name mit Punkt zählt nur dann zum Firmennetz, wenn er ausschließlich auf Adressen im eigenen Netz zeigt. Sonst die Adresse als Zahl eintragen.

## Danach
- Noch nichts gewählt? Dann gilt, was bisher lief: mit eingeschalteter Synchronisierung oder Benachrichtigungen „Cloud“, sonst „Nur dieser PC“.
- Die Betriebsart gilt für diesen PC und alle Projekte darauf.

## Häufige Fragen
### Verlässt in „Nur dieser PC“ wirklich nichts den Rechner?
Die AMW selbst baut dann keine Verbindung nach außen auf. Was außerhalb der AMW läuft, ist davon nicht erfasst: Claude Code spricht mit seinem Anbieter, Git mit seinem Server.

### Kann ich in „Eigener Server“ ntfy benutzen?
Ja, mit einem eigenen ntfy-Server im Firmennetz – dort auch über `http://`. Der öffentliche Dienst `ntfy.sh` liegt im Internet und ist dann blockiert.

### Online-Speicher und Online-Seite im eigenen Netz?
Ja: ein eigener libSQL-Server als Speicher und die Online-Seite auf einem Webserver der Firma. `amw web paket --seite https://amw.firma.lan --speicher https://amw-db.firma.lan` baut am PC eine ZIP mit allem, was der Webserver braucht, samt Anleitung, und trägt den Zugang an diesem PC ein. Im Firmennetz geht auch `http://` – Anmeldeseite und Einstellungen warnen dann, weil Passwörter unverschlüsselt durchs Netz gehen.

### Was passiert mit dem „In Claude öffnen“-Knopf?
Er führt ins Internet und wird nur in der Betriebsart „Cloud“ gezeigt.
