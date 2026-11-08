# Fehlerbehebung

Erste Schritte bei jedem Problem: `amw dienst status` (läuft der Wächter, antwortet die Workbench, welche Sitzungen
sind angemeldet) und das Protokoll `daten\dienst.log` (in der Workbench: Betrieb › Protokoll).

| Zeichen | Ursache | Abhilfe |
|---|---|---|
| `amw: command not found` (Git Bash) oder „Die Benennung amw wurde nicht … erkannt“ | `<AMW-Ordner>\bin` nicht im Pfad | Pfad ergänzen ([installation.md](installation.md) §2), neues Fenster – oder `python <AMW-Ordner>/amw-cli.py …` |
| „wer bist du? --von oder AMW_AGENT setzen“ | Befehl ohne Absender | `--von Entwickler` (du) bzw. `--von CC1` (Agent) |
| „Die Aufgabe „AMW Dienst“ gehört zu einer anderen AMW-Installation“ | zwei AMW-Ordner auf einem PC | dort entfernen (`amw dienst entfernen --ja` im anderen Ordner) oder dieses AMW mit `amw dienst vordergrund` betreiben |
| Workbench nicht erreichbar | Wächter läuft nicht, oder der Port ist belegt | `amw dienst status`; `amw dienst neustart`; im Protokoll „Workbench nicht gestartet (Port …)“ → anderen Port im Zahnrad › Dieser PC oder in `einstellungen.json`, dann `amw dienst neustart` |
| Agent wird nicht geweckt | Sitzung nicht angemeldet (Kachel rot „nicht angemeldet“ oder Band „NICHT ANGEMELDET“) | im Tab des Agenten `amw anmelden --von CC1`; dauerhaft: Hooks im Projektordner (`amw einrichten agenten-ordner <ordner>`) |
| „… ist schon angemeldet und diese Sitzung lebt noch“ | zwei Sitzungen wollen dieselbe Kennung | im richtigen Fenster `amw anmelden --von CC1 --ersetzen` |
| Kachel „wartet auf Freigabe“ | Claude Code fragt im Fenster des Agenten um Erlaubnis | ins Fenster schauen und bestätigen – oder Profil-Rechte „auto“ |
| Kachel „Fehler (rate_limit)“ | Nutzungsgrenze erreicht | warten bis zur Rücksetzzeit (Übersicht des Agenten) – dann eine Nachricht schicken |
| Keine Kontext-/Kostenbalken | Statusline-Brücke nicht eingetragen | `amw einrichten agenten-ordner <ordner>`; die bisherige Statusline wird weitergereicht |
| Umlaute kaputt / Abbruch mit `UnicodeEncodeError` | Konsole nicht in UTF-8 | `amw.cmd` bzw. `python -X utf8 …` benutzen |
| `database is locked` | sehr lange Schreibvorgänge parallel | kommt praktisch nicht vor (30 s Wartezeit); sonst Agenten kurz anhalten, `amw dienst neustart` |
| Lauf startet nicht | Halt, Schirm zu (bei `--schirm`), Speicher unter der Grenze (gerade gestartete Läufe zählen 3 Minuten mit), Grafikkarte/Schirm belegt, CPU-Spur voll, eigener schwerer Lauf läuft noch oder Warteschlange | Meldung lesen; `--warten` reiht nur ein, dann `amw lauf warte <nr>`; Grund: `amw lauf zeige <nr>`, `amw schirm` |
| Schirm geht gleich wieder zu | zwei Eingaben am PC (innerhalb von 2 min) später als 2 min nach dem Freigeben – der Grund nennt das Programm im Vordergrund, neue Fernsitzung, Eingabe in der Workbench am PC | so gewollt ([automatismen.md](automatismen.md)); Grund steht in `amw schirm --verlauf` |
| Agent unter alter Kennung angesprochen (`--von CC3`) nach dem Umbenennen | so gewollt: die alte Kennung gilt als Alias | nichts; `amw agent liste` zeigt „(früher …)“ |
| „wartet nur mit --auf“ | Wartegrund fehlt | `amw aufgabe wartet <nr> --auf F…/A…/L…/Agent/Entwickler/Monitor:…`; Erklärung zusätzlich mit `--wartet-auf` |
| „Ist das schon entschieden? Die AMW findet dazu: …“ bei `frage neu` | Frage an den Entwickler ohne Prüfung | Treffer lesen; passt keiner: `--geprueft "B… passt nicht, weil …"` (ohne Treffer: `--geprueft "keine Treffer"`) |
| „A… ist fertig – für Neues eine neue Aufgabe“ | `--aufgabe` mit abgeschlossener Aufgabe | neue Aufgabe anlegen oder ohne `--aufgabe` posten |
| Meldung „Leerlauf: seit … min frei, Arbeit liegt vor“ | Sitzung frei, aber eine eigene Aufgabe wartet auf nichts | weitermachen oder den Grund setzen (`aufgabe wartet … --auf …`) |
| „Bogen-Schritte brauchen … --zusammenfassung“ | Regel für geplante Schritte | Kriterien abhaken, `--zusammenfassung` angeben |
| „wartet auf A… (Abhängigkeit)“ | Vorgänger nicht fertig | Vorgänger abschließen oder Abhängigkeit ändern (`amw aufgabe aendern <nr> --nach …`) |
| Push kommt nicht | Hauptschalter aus, Anbieter aus, Ruhezeit, falscher Schlüssel | `amw push status` (Protokoll mit Fehlern), `amw push probe <anbieter>` |
| Online: „PC-Stand vor x min“ veraltet | Wächter aus oder Abgleich aus | `amw web status`; Zahnrad › Online-Speicher › Abgleich an |
| Online: „Konfiguration fehlt“ nach Bereitstellung | Konfiguration lag im Bereitstellungs-Ordner | Seite öffnen → Einrichtungs-Assistent erneut (Zweiter Faktor bleibt, Zahl aus der App) |
| Online: Anmeldung „Herkunft“ abgewiesen | Seite über andere Adresse/Proxy aufgerufen | direkt über die eingerichtete https-Adresse öffnen |
| Datenbank auf neuer Version, alte AMW startet nicht mehr | Rückkehr zu einer älteren Version | Sicherung vor dem Update zurückspielen ([betrieb.md](betrieb.md) §5) |

Weitere Hilfe: `amw <befehl> --help`, [architektur.md](architektur.md), Issues im Repository.
