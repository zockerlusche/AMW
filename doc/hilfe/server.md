# Projekt-Server überwachen

Läuft für ein Projekt ein eigener Server auf diesem PC – etwa ein Testserver oder eine lokale Schnittstelle –, prüft die AMW regelmäßig, ob er antwortet, und startet ihn auf Wunsch neu.

## Du brauchst
- Den Port, auf dem der Server antwortet.
- Optional den Befehl, mit dem er startet, und seinen Arbeitsordner.

## Schritte
1. **Server anmelden** `amw server anmelden <name> --port <port>` ausführen.
2. **Neustart einrichten (optional)** Mit Startbefehl: `amw server anmelden <name> --port <port> --start "pythonw C:/pfad/server.py --port 8766" --ordner C:/pfad --neustart`. Fällt der Server aus, startet der Dienst ihn neu.
3. **Prüfen** Unter Betrieb › Projekt-Server stehen Zustand, Ausfälle und wer bei einem Ausfall benachrichtigt wird. Sofort prüfen: `amw server pruefen <name>`.

## Diese Werte trägst du ein
| Feld in der AMW | Woher |
|---|---|
| Name | frei wählbar, kurz, z. B. „spielserver“ |
| Port | Port, auf dem der Server lokal antwortet |
| Startbefehl | Befehl ohne Fenster, z. B. mit `pythonw` |
| Zuständig | wer bei einem Ausfall eine Nachricht bekommt (Standard: du) |

## Typische Fehler
- **„noch nicht geprüft“** – Der Dienst prüft in seinem nächsten Durchgang; nach einer Minute steht der Zustand da.
- **Der Server startet nicht neu** – Ohne `--neustart` und Startbefehl meldet die AMW den Ausfall nur.

## Danach
- Abmelden: `amw server abmelden <name>`. Der Server selbst läuft weiter; die AMW beendet nichts.
