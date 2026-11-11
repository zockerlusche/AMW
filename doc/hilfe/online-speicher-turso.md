# Online-Speicher bei Turso anlegen

Der Online-Speicher ist die Ablage, über die dein PC und die Online-Seite Daten austauschen. Du legst ihn einmal an und trägst Adresse und Schlüssel in der AMW ein.

## Du brauchst
- Die AMW läuft auf diesem PC (der Wächter ist eingerichtet).
- Ein kostenloses Konto bei turso.tech.
- Etwa 10 Minuten.

## Schritte
0. **Betriebsart** Der Online-Speicher liegt im Internet: unter Einstellungen › Betriebsart muss „Cloud“ gewählt sein (`amw einrichten betriebsart cloud`). In „Nur dieser PC“ ist die Verbindung blockiert.
1. **Konto und Datenbank** Melde dich auf turso.tech an und lege eine Datenbank an („Create Database“). Der Name ist frei, wähle einen Standort in deiner Nähe.
2. **Adresse kopieren** Auf der Seite der Datenbank steht die Adresse („Database URL“). Sie beginnt mit `libsql://` und endet auf `.turso.io`.
3. **Schlüssel erzeugen** Auf derselben Seite „Create Token“ wählen: Lesen und Schreiben, ohne Ablauf. Den Schlüssel kopieren – er wird nur einmal gezeigt.
4. **Am PC eintragen** In der AMW: Einstellungen › Speicher und Abgleich. Adresse und Schlüssel einfügen und speichern. Die AMW prüft die Verbindung, legt die Tabellen an und schaltet den Abgleich ein. Als Befehl geht dasselbe mit `amw web einrichten`.
5. **Wächter neu starten** Die AMW sagt es dazu: Der Abgleich beginnt mit dem nächsten Start des Wächters (Leitstand › Wächter › Neu starten).
6. **Prüfen** Unter Einstellungen › Speicher und Abgleich steht „Schlüssel gespeichert“ und der Abgleich ist an; „Verbindung testen“ meldet „Anmeldung erfolgreich“ und „Die Datenbank ist eingerichtet“. `amw web status` zeigt, wann zuletzt hochgeladen wurde.

## Diese Werte trägst du ein
| Feld in der AMW | Woher |
|---|---|
| Adresse | Turso, Seite der Datenbank: „Database URL“ (`libsql://name-konto.turso.io`) |
| Schlüssel | Turso, „Create Token“ (Lesen und Schreiben) |

## Typische Fehler
- **„Adresse libsql://….turso.io und Schlüssel nötig“** – Es wurde die Adresse der Webseite kopiert statt der „Database URL“, oder ein Feld ist leer.
- **„nicht erreichbar oder Schlüssel abgelehnt – nichts gespeichert“** – Entweder gehört der Schlüssel zu einer anderen Datenbank, darf nur lesen oder ist abgelaufen (dann einen neuen mit Lesen und Schreiben erzeugen), oder es gibt gerade keine Verbindung ins Internet.
- **Nichts kommt online an** – Der Wächter läuft nicht oder wurde nach dem Eintragen nicht neu gestartet.

## Danach
- Die Online-Seite einrichten: Sie fragt beim ersten Öffnen nach derselben Adresse und demselben Schlüssel.
- Den Schlüssel nirgends ablegen oder weitergeben. Die AMW speichert ihn nur auf diesem PC und zeigt ihn nie an.

## Häufige Fragen
### Kostet das etwas?
Für ein oder zwei Projekte reicht der kostenlose Tarif von Turso.

### Was liegt im Online-Speicher?
Eine Kopie dessen, was die Online-Seite zeigt, und der Briefkasten mit dem, was du von unterwegs tust. Die vollständigen Daten bleiben auf deinem PC.

### Wie schalte ich es wieder ab?
Einstellungen › Speicher und Abgleich › Abgleich aus. Die Online-Seite zeigt dann den letzten Stand und nimmt nichts mehr an.
