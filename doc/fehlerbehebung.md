# Fehlerbehebung

Erste Schritte bei jedem Problem: `amw dienst status` (läuft der Wächter, antwortet die Workbench, welche Sitzungen
sind angemeldet) und das Protokoll `daten\dienst.log` (in der Workbench: Betrieb › Protokoll).

| Zeichen | Ursache | Abhilfe |
|---|---|---|
| Workbench nicht erreichbar | Wächter läuft nicht, oder der Port ist belegt | `amw dienst status`; `amw dienst neustart`; im Protokoll „Workbench nicht gestartet (Port …)“ → anderen Port im Zahnrad › Dieser PC oder in `einstellungen.json`, dann `amw dienst neustart` |
| Agent wird nicht geweckt | Sitzung nicht angemeldet (Kachel rot „nicht angemeldet“ oder Band „NICHT ANGEMELDET“) | im Tab des Agenten `amw anmelden --von CC1`; dauerhaft: Hooks im Projektordner (`amw einrichten agenten-ordner <ordner>`) |
| „… ist schon angemeldet und diese Sitzung lebt noch“ | zwei Sitzungen wollen dieselbe Kennung | im richtigen Fenster `amw anmelden --von CC1 --ersetzen` |
| Kachel „wartet auf Freigabe“ | Claude Code fragt im Fenster des Agenten um Erlaubnis | ins Fenster schauen und bestätigen – oder Profil-Rechte „auto“ |
| Kachel „Fehler (rate_limit)“ | Nutzungsgrenze erreicht | warten bis zur Rücksetzzeit (Übersicht des Agenten) – dann eine Nachricht schicken |
| Keine Kontext-/Kostenbalken | Statusline-Brücke nicht eingetragen | `amw einrichten agenten-ordner <ordner>`; die bisherige Statusline wird weitergereicht |
| Umlaute kaputt / Abbruch mit `UnicodeEncodeError` | Konsole nicht in UTF-8 | `amw.cmd` bzw. `python -X utf8 …` benutzen |
| `database is locked` | sehr lange Schreibvorgänge parallel | kommt praktisch nicht vor (30 s Wartezeit); sonst Agenten kurz anhalten, `amw dienst neustart` |
| Lauf startet nicht | Halt, Speicher unter der Grenze, schwerer Lauf/Schirm belegt oder Warteschlange | Meldung lesen; `--warten` reiht ein; `amw lauf liste` |
| „Bogen-Schritte brauchen … --zusammenfassung“ | Regel für geplante Schritte | Kriterien abhaken, `--zusammenfassung` angeben |
| „wartet auf A… (Abhängigkeit)“ | Vorgänger nicht fertig | Vorgänger abschließen oder Abhängigkeit ändern (`amw aufgabe aendern <nr> --nach …`) |
| Push kommt nicht | Hauptschalter aus, Anbieter aus, Ruhezeit, falscher Schlüssel | `amw push status` (Protokoll mit Fehlern), `amw push probe <anbieter>` |
| Online: „PC-Stand vor x min“ veraltet | Wächter aus oder Abgleich aus | `amw web status`; Zahnrad › Online-Speicher › Abgleich an |
| Online: „Konfiguration fehlt“ nach Bereitstellung | Konfiguration lag im Bereitstellungs-Ordner | Seite öffnen → Einrichtungs-Assistent erneut (Zweiter Faktor bleibt, Zahl aus der App) |
| Online: Anmeldung „Herkunft“ abgewiesen | Seite über andere Adresse/Proxy aufgerufen | direkt über die eingerichtete https-Adresse öffnen |
| Datenbank auf neuer Version, alte AMW startet nicht mehr | Rückkehr zu einer älteren Version | Sicherung vor dem Update zurückspielen ([betrieb.md](betrieb.md) §5) |

Weitere Hilfe: `amw <befehl> --help`, [architektur.md](architektur.md), Issues im Repository.
