# AMW – Agentenmanagement Workbench

Ein Werkzeug, mit dem ein Entwickler ein Team aus Claude-Code-Agenten über Tage führt. Konzept und Entscheidungen: [doc/README.md](doc/README.md) (Architektur: [doc/10-architektur.md](doc/10-architektur.md)).

Stand 01.11.2026: Stufe 1 in Betrieb (lokal, nur Python-Standardbibliothek, SQLite; das LayerIT-Team läuft darüber, → [doc/11](doc/11-umzug.md)). Stufe 2 vorbereitet: Workbench im Netz über PHP-Hosting + Turso, Login mit Passwort und Einmalcode (→ [doc/12](doc/12-online.md)).

Lizenz: [MIT](LICENSE) – frei zu benutzen, zu ändern und weiterzugeben. Zweig `web` enthält nur den Online-Teil (für das Hosting).

## Aufbau
| Pfad | Inhalt |
|---|---|
| `amw/schema.sql` | Datenmodell (18 Tabellen) |
| `amw/db.py` | Datenzugriffs-Schicht – einziger Ort, der die Datenbank anfasst |
| `amw/kern.py` | Fachlogik: Nachrichten, Aufgaben, Fragen, Halt, Pflicht-Kontext |
| `amw/cli.py`, `amw.cmd` | Kommandozeile `amw` |
| `amw/hook.py` | SessionStart-Hook: Sitzung anmelden, Pflicht-Kontext einspielen |
| `amw/dienst.py`, `amw/pipe.py` | Wächter: weckt Agenten über die Pipe ihrer Sitzung, startet die Workbench |
| `amw/workbench.py`, `amw/workbench.html` | Workbench-Oberfläche auf http://127.0.0.1:8780 (Start, Fragen, Aufgaben, Wissen, Betrieb, Release Notes, Halt) |
| `amw/uebernahme.py` | Übernahme des LayerIT-Busses (bus.db nur lesend) in eine neue amw.db |
| `amw/aktionen.py`, `amw/abgleich.py` | Stufe 2: erlaubte Aktionen der Seite; Abgleich mit Turso (Schaufenster + Briefkasten) |
| `web/` | Online-Teil (PHP): Login mit Passwort + TOTP, Ansichten, Briefkasten |
| `amw-cli.py` | Start ohne PYTHONPATH: `python amw-cli.py lesen --von CC1` |
| `tests/` | `python -m unittest discover -s tests` |
| `daten/` | Datenbank `amw.db`, `dienst.log` (nicht im git) |

## Bedienung (Kurz)
```
amw init --projekt LayerIT            # Datenbank anlegen
amw agent neu TL --rolle lead         # Agenten definieren
set AMW_AGENT=CC1                     # wer bin ich (je Agenten-Sitzung)
amw lesen | amw lesen 12 | amw erledigt 12 13
amw posten --an CC2 --art pruefbitte --kurz "…"
amw aufgabe liste | start 5 | fertig 5 --beleg <commit>
amw halt --text "Pause" | amw weiter   # nur Lead/Entwickler
amw kontext                           # Pflicht-Kontext
```
Andere Datenbank: Umgebungsvariable `AMW_DB`.

## Wächter und Hook
- Dienst: `python -X utf8 -m amw.dienst` (mit `PYTHONPATH=F:\amw`). Läuft genau einmal (Sperre `daten/dienst.lock`), Protokoll `daten/dienst.log`. Einrichtung als geplante Aufgabe „AMW Dienst“: `amw dienst einrichten` zeigt nur an, `--ja` richtet ein (erst nach Rückfrage beim Entwickler, doc/07 E7); `amw dienst status`, `amw dienst entfernen --ja`. Starter ohne Fenster: `start_dienst.pyw`.
- Hook je Agent (Projekt-Einstellung, SessionStart, Matcher `startup|resume|compact`): `python -X utf8 -m amw.hook` mit `AMW_AGENT` und `PYTHONPATH`. Pipe-Pfad und Schlüssel landen in `%LOCALAPPDATA%\amw\sitzungen\<Agent>.json`, nie in der Datenbank.

## Online in 4 Schritten (Workbench im Netz)
Voraussetzung: die AMW läuft am PC (Wächter eingerichtet), ein Webhoster mit PHP ≥ 8.1 (curl, mbstring) und eine kostenlose Datenbank bei [turso.tech](https://turso.tech).

1. **Turso:** Datenbank anlegen, dann bei der Datenbank „Create Token“ (Lesen + Schreiben). Adresse (`libsql://….turso.io`) und Schlüssel bereithalten – den Schlüssel nirgends speichern oder weitergeben.
2. **PC:** `amw web einrichten` – fragt Adresse und Schlüssel (verdeckt), prüft die Verbindung, schaltet den Abgleich ein und startet den Wächter neu.
3. **Hoster:** Git-Bereitstellung aus diesem Repo, **Zweig `web`** (enthält nur die Web-Dateien), in den Ordner der (Sub-)Domain; SSL einschalten.
4. **Browser:** Seite öffnen – der Einrichtungs-Assistent fragt Turso-Adresse + Schlüssel (nur wer den Schlüssel hat, kann einrichten), legt Benutzer + Passwort fest und zeigt einen QR-Code für die Authenticator-App. Danach bist du angemeldet; ein späteres erneutes Bereitstellen ändert daran nichts.

Neues Handy: `amw web zweitfaktor-neu` am PC, dann beim nächsten Einrichten/Anmelden neu scannen. Abschalten: `"abgleich": false` in `%LOCALAPPDATA%\amw\turso.json`. Details und Sicherheit: [doc/12-online.md](doc/12-online.md).

### Online in 4 steps (English)
Requires: AMW running on your PC (service installed), a web host with PHP ≥ 8.1 (curl, mbstring), a free [turso.tech](https://turso.tech) database.

1. **Turso:** create a database, then "Create Token" (read + write). Keep the URL (`libsql://….turso.io`) and the token at hand – never store or share the token.
2. **PC:** `amw web einrichten` – asks for URL and token (hidden), checks the connection, enables sync and restarts the service.
3. **Host:** Git deployment from this repo, **branch `web`** (web files only), into the (sub)domain folder; enable SSL.
4. **Browser:** open the site – the setup wizard asks for the Turso URL + token (only the token holder can set up), sets user + password and shows a QR code for your authenticator app. You are signed in; redeploying later keeps the setup.
