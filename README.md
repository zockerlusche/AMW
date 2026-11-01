# AMW – Agentenmanagement Workbench

Ein Werkzeug, mit dem ein Entwickler ein Team aus Claude-Code-Agenten über Tage führt. Konzept und Entscheidungen: [doc/README.md](doc/README.md) (Architektur: [doc/10-architektur.md](doc/10-architektur.md)).

Stand: Stufe 1 im Bau (lokal, nur Python-Standardbibliothek, SQLite).

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
- Dienst: `python -X utf8 -m amw.dienst` (mit `PYTHONPATH=F:\amw`). Läuft genau einmal (Sperre `daten/dienst.lock`), Protokoll `daten/dienst.log`. Einrichtung als geplante Aufgabe: erst nach Rückfrage beim Entwickler (doc/07 E7).
- Hook je Agent (Projekt-Einstellung, SessionStart, Matcher `startup|resume|compact`): `python -X utf8 -m amw.hook` mit `AMW_AGENT` und `PYTHONPATH`. Pipe-Pfad und Schlüssel landen in `%LOCALAPPDATA%\amw\sitzungen\<Agent>.json`, nie in der Datenbank.
