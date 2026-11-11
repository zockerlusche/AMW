# Betrieb: Arbeiten mit AMW

## 1 Die Workbench
http://127.0.0.1:8780 (am Handy dieselbe Seite über die Online-Adresse). Oben in ganzen Wörtern: „Wächter läuft“,
„x von y Agenten laufen“, „Arbeitsspeicher: n GB frei“ und die Suche (Aufgaben, Beschlüsse, Fragen, Wortlaut,
Nachrichten). Die erste Zeile zeigt nur Zustände; weicht etwas vom Normalfall ab („Angehalten“, „Bildschirm: frei für
Agenten“, „n werden beendet“), steht es dort als Hinweis, ein Klick führt zum Leitstand.

**Leitstand** (Start, direkt unter den Agenten) – alles Steuerbare an einer Stelle:

| Feld | Zustand | Knöpfe |
|---|---|---|
| Arbeit der Agenten | läuft / angehalten | Alle anhalten · Weiterarbeiten |
| Bildschirm | belegt / frei für Agenten (bis …) | Für Agenten freigeben … (nur am PC) · Wieder belegen |
| Sitzungen | n laufen · n abgemeldet · n fehlen | Alle sichern & beenden · Fehlende starten (beides nur am PC) |
| Wächter | läuft · Version | Neu starten (nur am PC) |

**Team** (Start): als **Baum** – du oben, darunter der Lead (was er plant, Takt, letzte Meldung), darunter die Agenten
mit Fachgebiet, Zustand, Aufgabe, „wartet auf“ und Verbrauch; gestrichelte Bögen verbinden, wer gerade zusammenarbeitet
(offene Prüfbitte). Oben rechts umschaltbar auf die **Liste** (eine Zeile je Agent, Vorgabe am Handy); die Wahl bleibt
je Gerät. Ein Klick auf einen Agenten öffnet seine Übersicht.

**Aktionsmenü „⋯“** an jedem Agenten: Nachricht schreiben, Gespräch mitlesen, Übersicht und Aufgabenliste ·
Anhalten (nur diesen) bzw. Weiterarbeiten lassen, Sichern & beenden lassen, Sofort beenden, Starten/fortsetzen, Neue
Sitzung beginnen (Sitzungen nur am PC) · Profil und Zuständigkeit.

| Ansicht | Wofür |
|---|---|
| **Start** | „Seit du weg warst“, Warnungen, **Wartet auf dich** (Freigaben, eigene Schritte, Fragen), das Team als Baum oder Liste (Zustand, was er gerade tut, Kontext/5-Stunden-Grenze; Klick = Übersicht mit Starten/Beenden), Nachrichten an dich |
| **Fragen** | Reiter *Offen* und *Geparkt*: Fragen an dich mit Optionen und Empfehlung; Antwort per Klick, eigener Text oder Rückfrage; Verlauf wie im Chat; parken und wieder aufnehmen |
| **Planung** | Zeitleiste der Bögen mit Ampel und Prognose, Spezifikation freigeben, Leitbild, Risiken, Plan-Check, Protokoll |
| **Aufgaben** | Board (läuft · wartet · blockiert), geparkt, Pool, abgeschlossen; Filter nach Agent und Text |
| **Verlauf** | alles, was passiert ist, je Tag, filterbar |
| **Release Notes** | je Zusammenführung eine Zeile, Versionen |
| **Wissen** | Beschlüsse, Regeln, Wortlaut, Notizen; Suche |
| **Betrieb** | Projekt-Server, Verbrauch je Agent und Tag, Sperren, Sitzungen, Rechen-Läufe, Protokoll des Wächters |
| **Einstellungen** | Projekt, Agenten (mit Profil), Online-Seite, dieser PC, Online-Speicher, Benachrichtigungen |

Hell/Dunkel und Deutsch/Englisch unten links; die Seite aktualisiert Start und Betrieb von selbst (nicht während du tippst).
Die Untermenüs einer Seite (Reiter, Filter, Sprungmarken) bleiben beim Scrollen oben stehen – am Handy je Untermenü eine
Zeile, die sich waagrecht wischen lässt.

## 2 Mit den Agenten arbeiten
- **Auftrag geben:** am Agenten ⋯ › „Nachricht schreiben“ (Art Auftrag weckt) – oder an den Lead, der verteilt.
- **Fragen beantworten:** Start oder Fragen; eine Rückfrage geht zurück an den Fragesteller, dessen Antwort erscheint im Verlauf der Frage.
- **Fragen parken:** Eine Frage, die du gerade nicht verfolgen willst, parkst du über *Parken* auf der Karte. Steht Text im
  Feld, ist das der Grund. Die Frage bleibt offen, steht aber in keiner offenen Liste, in keinem Zähler und in keiner
  Push-Erinnerung mehr. Unter *Geparkt* siehst du sie vollständig mit Zeit und Person und nimmst sie mit *Wieder aufnehmen*
  zurück. Antworten geht auch geparkt. Der TL und die Agenten parken mit `amw frage parken <nr> --grund "…"` (der Lead und
  der Fragesteller; auch über die TL-Brücke), `amw frage aufnehmen <nr>` holt sie zurück, `amw frage liste --geparkt`
  zeigt sie. Parken und Aufnehmen stehen im Verlauf der Frage, der Fragesteller bekommt eine Info.
- **Anhalten:** im Leitstand „Alle anhalten“ (alle oder einen Agenten) oder im Aktionsmenü ⋯ des Agenten „Anhalten (nur
  diesen)“; „Weiterarbeiten“ hebt auf. Agenten beginnen nichts Neues, Läufe starten nicht.
- **Starten, fortsetzen, beenden:** Aktionsmenü ⋯ des Agenten (oder Klick › Übersicht). „Fortsetzen“ setzt die letzte
  Sitzung fort (Gesprächsverlauf bleibt), „Neue Sitzung beginnen“ startet frisch mit dem Startsatz. „Fehlende starten“
  im Leitstand startet alle, die laufen sollen und nicht laufen, nacheinander. Ordner, Modell, Rechte und Startsatz: Zahnrad › Agenten › Block „Sitzung“.
- **Agenten einstellen (Zahnrad › Agenten):** links die Agenten, rechts der gewählte in vier Blöcken. *Wer:* Lead (ein
  Schalter – führt das Projekt), Fachgebiet (frei, mit Vorschlägen), Arbeitsweise. *Auftrag:* „Zuständig für“ und „Fasst
  nicht an“ – beides steht im Pflicht-Kontext jeder Sitzung des Agenten. *Sitzung:* Ordner, Modell, Rechte, Startsatz (nur
  am PC). *Überwachung:* soll laufen, Lebenszeichen. Die Arbeitsweise bestimmt, was die AMW tut: „Claude Code im Terminal“
  startet, weckt und überwacht sie; „Claude Code in der Desktop-App“ startet der Mensch selbst – die AMW startet sie nie;
  ein „Chat“ (schreibt über die Brücke) wird weder gestartet noch überwacht und zählt nicht zu den Agenten, die laufen
  sollen. „Vorschlag aus der Datenbank“ leitet Fachgebiet und Zuständigkeit aus den fertigen Aufgaben des Agenten ab –
  er füllt nur leere Felder, gespeichert wird erst mit „Speichern“. Per Befehl: `amw agent profil <kennung> --rolle lead|""
  --fachgebiet … --arbeitsweise terminal|desktop|chat --zustaendig … --nicht …`.
- **Sichern & beenden (z. B. vor einem Update):** im Leitstand für alle, im Aktionsmenü für einen. Der Agent bekommt
  die Bitte, seinen Stand festzuhalten und sich abzumelden (`amw abmelden`); sobald er abgemeldet ist, beendet die AMW
  seine Sitzung – nach 5 Minuten auch ohne Abmeldung. Das Fenster bleibt offen; „Starten / fortsetzen“ holt ihn zurück.
  Nur am PC.
- **Mitlesen:** am Agenten ⋯ › „Gespräch mitlesen“ (oder in der Übersicht der Reiter *Gespräch*) zeigt, was der Agent mit Claude Code
  bespricht – live, ohne sein Fenster zu suchen. Deine Eingaben stehen rechts, Claudes Antworten links. Weckrufe der AMW,
  Aufgabenmeldungen und Zusammenfassungen sind klein dazwischen. Die Arbeitsschritte (Werkzeuge) sind je Strecke
  eingeklappt, „7 Arbeitsschritte · Bash, Read, Edit“. Aufgeklappt zeigt jeder Schritt Eingabe und Ergebnis, Fehler sind rot.
  Der Schalter *Arbeitsschritte* blendet sie ganz aus. *Ältere laden* blättert zurück, eine frühere Sitzung wählst du oben.
  Gelesen wird nur das Protokoll von Claude Code (`~/.claude/projects/…`), nichts wird dort geändert. Geheimnis-Muster
  (Schlüssel, `password=…`) sind immer verdeckt.
- **In Claude öffnen:** Läuft der Agent mit Fernsteuerung (Profil › Fernsteuerung, ab dem nächsten Start), öffnet der Knopf
  seine Sitzung auf claude.ai bzw. in der Claude-App am Handy. Dort schreibst du direkt mit ihm, das Terminal am PC bleibt
  gleichzeitig offen. Ohne Fernsteuerung oder bei beendeter Sitzung steht dort, was fehlt.
- **Zustand verstehen:** *arbeitet* · *frei* (wartet auf Nachrichten) · *wartet auf Freigabe* (im Fenster des Agenten
  fragt Claude Code um Erlaubnis – dorthin schauen) · *wartet auf Eingabe* · *Fehler* (z. B. Nutzungsgrenze erreicht).

## 3 Was Agenten mit `amw` tun
```
amw lesen --von CC1                       # offene Nachrichten (amw lesen 123: ganze Nachricht, gilt als gelesen)
amw erledigt 123 124 --von CC1
amw posten --an CC2 --art pruefbitte --kurz "…" --von CC1
amw schritt naechster --nehmen --von CC1  # nächster bereiter Schritt (aktiver Bogen zuerst)
amw aufgabe kriterium 1201 1 --von CC1    # Abnahmekriterium erfüllt
amw aufgabe fertig 1201 --beleg <commit> --zusammenfassung "…" --von CC1
amw lauf start --beschreibung "Build" --dauer 10 --warten --von CC1   # dann: amw lauf ende <nr> --rc 0
amw pruefung bitte --pruefer CC2 --zweig cc1-x --sha <commit> --von CC1
amw frage neu --an entwickler --kurz "…" --option "A=…" --option "B=…" --empfehlung A --grund "…" --von TL
amw taetigkeit "A1201 Login-Formular" --von CC1   # steht beim Agenten unter „Arbeitet an“
amw kontext --von CC1                     # Pflicht-Kontext
```
**Anmelden von selbst.** Ein Hook, den `amw einrichten agenten-ordner` in jeden Agenten-Ordner einträgt, sieht jeden
Shell-Befehl vor dem Start. Ist er schwer – ganze Test-Suite, Browser-Tests, Build, Abzug des Web-Zweigs oder ein Muster
des Projekts (Zahnrad › Projekt › „Weitere schwere Befehle“) – und läuft nicht schon über die Warteschlange, wird er
abgewiesen, und der Agent bekommt den fertigen Ersatz: `amw lauf ausfuehren --beschreibung "…" -- <befehl>`. Einzelne
Test-Module bleiben frei. Abschalten je Rechner: Zahnrad › Dieser PC. Der Hook sperrt nie durch einen Fehler: Fehlt seine
Datei oder scheitert er, läuft der Befehl normal; der Fehler steht in `%LOCALAPPDATA%\amw\hook-fehler.log`. Bestehende Ordner bekommen ihn mit einem erneuten
`amw einrichten agenten-ordner <ordner>`; laufende Sitzungen übernehmen ihn nach wenigen Sekunden.

**Schwere Läufe und der Rechner.** Mehrere Projekte teilen sich einen PC. Schwere Läufe (Test-Suiten, Builds, alles mit
Grafikkarte oder Fenster) gehören deshalb in die Warteschlange – sie gilt für den **ganzen Rechner, über alle Projekte**:
wer zuerst kommt, ist zuerst dran, egal aus welchem Projekt. Am einfachsten mit
`amw lauf ausfuehren --beschreibung "Tests" --dauer 6 -- <befehl>`: meldet an, wartet, bis der Rechner frei ist, startet
den Befehl, reicht den Rückgabewert durch und meldet das Ende. Eingelassen wird, wenn ein Platz frei ist (Grafikkarte und
Bildschirm: ein Lauf zur Zeit; schwere Läufe ohne beides: so viele wie unter „Dieser PC“ eingestellt) und genug
Arbeitsspeicher: frei − Reserve − Bedarf gerade gestarteter Läufe ≥ Bedarf des Laufs. Die Reserve (Vorgabe 3 GB,
Zahnrad › Dieser PC) bleibt für den Menschen am Rechner. Den Bedarf nennt der Lauf selbst:
`--braucht-gb` (Arbeitsspeicher; ohne Angabe gilt das Rezept, sonst die Grenze des Projekts), dazu wahlweise
`--braucht-vram-gb` (Grafikspeicher) und `--braucht-platte-gb` (freier Platz auf dem Laufwerk des Projekts) – diese beiden
werden nur geprüft, wenn sie angegeben sind und sich der freie Wert messen lässt. Jeder Lauf trägt den Namen des Rechners,
auf dem er angemeldet wurde; die Warteschlange zählt nur Läufe ihres eigenen Rechners. Ein Lead zieht nur Läufe seines eigenen Projekts vor (sie tauschen untereinander die Plätze); über
Projekte hinweg zieht nur der Mensch vor. Über Läufe eines anderen Projekts erfährt man nur die Belegung – „L12 (anderes
Projekt, läuft seit 16:05, voraussichtlich bis 16:20)“ –, nie Agent, Beschreibung oder Projekt. Der Leitstand zeigt unter
„Rechner“, wie viele Läufe laufen und warten und wann er voraussichtlich frei ist. Eine Datenbank steht für einen Rechner;
Agenten auf einem anderen Rechner haben ihre eigene Warteschlange.

Alle Befehle: [befehle.md](befehle.md). `--von` kann entfallen, wenn `AMW_AGENT` gesetzt ist (Startskript, Hook).
Du selbst nimmst `--von Entwickler`. Den genauen Befehl (`python <AMW-Ordner>/amw-cli.py`) bekommen die Agenten im
Pflicht-Kontext; mit `<AMW-Ordner>\bin` im Pfad geht überall kurz `amw`.

## 4 Überwachung und Warnungen
- **Projekt-Server** (Testseiten, Editoren …): `amw server anmelden editor --port 8766 --start "pythonw C:/pfad/server.py"
  --ordner C:/pfad --neustart --zustaendig CC2` – Ausfall wird gemeldet, mit `--neustart` nach zwei Runden „aus“ neu
  gestartet (höchstens 3 je Stunde).
- **Stillstand:** Weckruf seit 30 min ohne Reaktion; Lauf länger als doppelt erwartet (ohne Angabe 90 min);
  Freigabe-Abfrage seit 2 min; Abbruch mit Fehler; Kontext ≥ 90 %; 5-Stunden-Grenze ≥ 90 %. Schwellen im Zahnrad › Projekt.
- Warnungen stehen oben auf der Startseite, gehen einmal als Nachricht an den Lead und als Push an dich.

## 5 Sichern und wiederherstellen
- `amw sichern` → `sicherung-<Datum>-<Uhrzeit>.db` neben der Datenbank (vollständige Kopie, auch im laufenden Betrieb);
  `amw sichern --ziel D:\Sicherung` legt sie in diesen Ordner (wird angelegt), `--ziel D:\x.db` als genau diese Datei.
- Wiederherstellen: Wächter anhalten (`amw dienst entfernen --ja` oder die Aufgabe in der Aufgabenplanung beenden),
  `daten\amw.db` durch die Sicherung ersetzen (die Dateien `amw.db-wal` und `amw.db-shm` daneben löschen), Wächter wieder
  einrichten bzw. starten.
- Die Dokumenten-Ablage (`dokumente/` neben der Datenbank) kopiert `amw sichern` nach `…-dokumente/` neben die
  Sicherung – nur, was dort noch fehlt ([anleitung-dokumente.md](anleitung-dokumente.md)).
- Vor jedem Update sichern (neue Versionen stellen die Datenbank beim ersten Schreibzugriff um).

### Wochenlimit und Token-Pause
Das Wochenlimit des Kontos gilt für alle Projekte dieses PCs zusammen. Die AMW schreibt den Wochenverbrauch mit (was
die Statusline der Sitzungen meldet) und rechnet daraus (`amw/tokenprognose.py`, nichts wird gespeichert):
- **Konto-Verlauf:** je Viertelstunde ein Wert aus allen Sitzungen. Melden sie sehr Verschiedenes, gilt der niedrige –
  dann gab es einen Reset und einige Sitzungen zeigen noch den alten Stand.
- **Reset:** ein Abfall um mehr als 30 Punkte, auch außer der Reihe. Er zählt als Ereignis, nicht als Verbrauch.
- **Tempo:** Anstieg je Tag an den Arbeitstagen der letzten 14 Tage – wahrscheinlich (Mittel) und vorsichtig (oberes
  Viertel); angebrochene Tage zählen mit ihrem Anteil.
- **Diese Woche:** Rest ÷ Tempo = „leer am“; liegt das vor dem Reset, ist bis dahin Pause. **Folgewochen:** 100 ÷ Tempo
  Tage Arbeit (höchstens 7), der Rest ist Pause.

Angezeigt wird das als **Wochenlimit** im Leitstand der Startseite und über der Übersicht der Planung, und als eigenes
Stück ⧗ hinter jedem Prognose-Datum: `Prognose 27.11. – 01.12. ⧗ +12 T → ≈ 09.12.`. In der Übersicht hängt es als
schraffiertes Stück in eigener Farbe hinten am Balken. Das Prognose-Datum selbst bleibt, wie es ohne Grenze wäre – so ist
sichtbar, was Arbeit ist und was Warten. Der Rechenweg steht im Hinweistext. Grenzen der Aussage: Die 5-Stunden-Grenze
kommt in den Messwerten nicht an. Tage, an denen das Kontingent mindestens einen halben Tag lang aufgebraucht war, zählen
nicht in den Durchsatz der Prognose – so wird die Pause nicht doppelt gerechnet. Die Ampel eines Meilensteins rechnet die
Pause ein: Sie steht nur grün, wenn der Termin auch mit Pause hält; „(mit Pause)“ am Datum zeigt, dass er ohne sie zu
halten wäre. Steht „unsicher“ dabei, gibt es zu wenige Messtage.

## 6 Einstellungen dieses PCs
Zahnrad › Dieser PC, oder von Hand in `%LOCALAPPDATA%\amw\einstellungen.json` (JSON, nur Schlüssel, die von der
Vorgabe abweichen, z. B. `{"port": 8790}`). Was der Wächter nur beim Start liest, trägt im Zahnrad das Zeichen ↻ und
wirkt nach `amw dienst neustart` (oder Start › Leitstand › Neu starten); alles andere gilt sofort.

**Betriebsart** (`amw/betriebsart.py`): „Nur dieser PC“ · „Eigener Server im Firmennetz“ · „Cloud“. Sie legt fest, wohin
diese Installation Verbindungen aufbauen darf, und wird an jeder Stelle geprüft, an der die AMW nach außen geht (Abgleich
mit dem Online-Speicher, Benachrichtigungen, Prüfung der Online-Seite, Link „In Claude öffnen“) – entschieden nach der
Adresse des Ziels: dieser PC, Firmennetz (private Adressbereiche, Namen ohne Punkt oder mit `.lan`, `.local`, `.intern` …)
oder Internet. In „Nur dieser PC“ wird nicht einmal ein Name aufgelöst. Wer nichts gewählt hat, behält, was bisher lief
(mit eingeschaltetem Abgleich oder Benachrichtigungen „Cloud“, sonst „Nur dieser PC“). Zeigen und setzen:
`amw einrichten betriebsart [pc|server|cloud]`. Die Liste aller Verbindungen dieser Installation steht im Zahnrad unter
der Betriebsart und kommt mit `amw einrichten verbindungen [--pruefen]`; der Befehl endet mit Fehler, wenn etwas
eingeschaltet, aber gesperrt ist. Nicht erfasst ist, was außerhalb der AMW läuft: Claude Code spricht mit seinem
Anbieter, Git mit seinem Server.

Das Zahnrad ist in dieser Reihenfolge gegliedert: **Betriebsart** · **Speicher und Abgleich** (Art, Adresse und Schlüssel des
Online-Speichers, Abgleich an/aus und seine Takte) · **Online-Seite** (ihre Adresse, Grenzen der Anmeldung) ·
**Benachrichtigungen** · **Dieser PC** · **Projekt** · **Agenten**. Jeder Abschnitt nennt, wofür er gilt (dieser PC, die
Online-Seite, dieses Projekt). Weicht ein Wert vom Standard ab, steht der Standard darunter. Zwei Knöpfe testen die
gespeicherten Werte: „Verbindung testen“ (Anmeldung am Online-Speicher, Datenbank eingerichtet?) und „Online-Seite
testen“ (erreichbar über https, läuft dort eine AMW-Seite?). Schlüssel bleiben in lokalen Dateien und zeigen nur „gespeichert“.

| Schlüssel | Vorgabe | Bedeutung |
|---|---|---|
| `db_pfad` | `<AMW-Ordner>\daten\amw.db` | Datenbank (vollständiger Pfad, Ordner muss es geben) |
| `port` | 8780 | Port der Workbench auf 127.0.0.1 |
| `aufsicht_s` | 30 | Takt der Aufsicht in Sekunden (5–600) |
| `abgleich_hoch_s` | 30 | Online: frühestens so oft hochladen |
| `abgleich_puls_s` | 300 | Online: Lebenszeichen, auch ohne Änderung |
| `abgleich_eingang_s` | 15 | Online: so oft den Briefkasten abholen |
| `bruecke_an` | aus | Datei-Brücke für einen Agenten ohne direkten Datenbankzugriff (→ [architektur.md](architektur.md) §3) |
| `bruecke_absender` | TL | Kennung, als die Befehle der Brücke ausgeführt werden |
| `bruecke_kopie_s` | 60 | Lesekopie der Brücke höchstens so oft erneuern |
| `statusline_weiter` | leer | bisherige Statusline, die die Statusline-Brücke weiterreicht (setzt `amw einrichten`) |
| `claude_befehl` | `claude` | wie Claude Code gestartet wird (falls nötig mit vollem Pfad) |
| `speicher_reserve_gb` | 3 | so viel Arbeitsspeicher bleibt frei, bevor ein schwerer Lauf startet (0–64) |
| `lauf_hook` | an | schwere Befehle abweisen und über die Warteschlange schicken (Hook in den Agenten-Ordnern) |
| `sprache` | auto | Sprache der Oberfläche, solange im Browser nichts gewählt ist: `auto` (wie der Browser), `de`, `en` |
| `claude_link` | an | Knopf „In Claude öffnen“ auf der Agenten-Seite zeigen |
| `betriebsart` | leer | `pc`, `server` oder `cloud`; leer = nicht gewählt, es gilt, was bisher lief |
