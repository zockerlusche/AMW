# Befehle

Erzeugt aus der Kommandozeile (`amw befehle > doc/befehle.md`). Jeder Befehl zeigt mit `--help` dasselbe.
Gemeinsam für alle: `--von <Kennung>` (wer handelt; sonst `AMW_AGENT`), `--projekt <Name>` (sonst das erste Projekt).

| Befehl | Zweck |
|---|---|
| [`init`](#init) | neue Datenbank anlegen |
| [`projekt`](#projekt) | Projekte: neu <name> ¦ liste |
| [`agent`](#agent) | neu ¦ liste ¦ profil ¦ starten ¦ beenden ¦ startskript ¦ umbenennen ALT NEU |
| [`posten`](#posten) | Nachricht schicken: --an CC2 (oder alle, Entwickler) --art auftrag¦frage¦info¦… --kurz … |
| [`lesen`](#lesen) | ohne Nummer: offene Liste; mit Nummer: ganze Nachricht |
| [`erledigt`](#erledigt) | Nachrichten als erledigt markieren: amw erledigt 12 13 |
| [`aufgabe`](#aufgabe) | neu ¦ aendern N ¦ liste ¦ zeige N ¦ start ¦ fertig ¦ … ¦ kriterium N nr ¦ plan N --text ¦ planfrei N [--zurueck --kommentar] |
| [`frage`](#frage) | Fragen an den Entwickler oder Lead: neu ¦ liste [--geparkt] ¦ antworten ¦ nachtrag ¦ verlauf ¦ parken N [--grund] ¦ aufnehmen N |
| [`halt`](#halt) | alle oder einen Agenten anhalten |
| [`weiter`](#weiter) | Halt aufheben |
| [`taetigkeit`](#taetigkeit) | was ich gerade tue (zeigt die Workbench), z. B. taetigkeit "A12 Login-Formular" |
| [`kontext`](#kontext) | Pflicht-Kontext für einen Agenten |
| [`regeln`](#regeln) | alle geltenden Regeln (Arbeits- und Projektregeln) |
| [`suche`](#suche) | Volltext über Aufgaben, Beschlüsse, Fragen, Wortlaut, Nachrichten, Dokumente: amw suche Modem |
| [`zeige`](#zeige) | Einträge ganz lesen: amw zeige B2420 F5148 A1238 W12 #16000 D5 KR3 PR42 |
| [`leitbild`](#leitbild) | Projektziel, Kennzahlen, Nicht-Ziele, Prinzipien, Definition of Done: zeigen ¦ setzen |
| [`bogen`](#bogen) | Meilensteine: liste ¦ neu ¦ zeigen N ¦ aendern N ¦ status N aktiv¦fertig¦geplant¦verworfen |
| [`spec`](#spec) | Spezifikation je Bogen: zeigen N [teil] ¦ schreiben N teil --text/--datei ¦ vorlegen N teil ¦ frei N teil ¦ zurueck N teil --kommentar  (teil: anforderungen ¦ entwurf ¦ schritte) |
| [`schritt`](#schritt) | naechster [--nehmen]: nächster bereiter Schritt (aktiver Bogen, ohne offene Vorgänger) |
| [`risiko`](#risiko) | liste ¦ neu --titel … ¦ setzen N --status … |
| [`rueckblick`](#rueckblick) | Rückblick je Bogen: amw rueckblick <bogen> [--gut … --schlecht … --massnahme … --gelernt …] ¦ --uebernehmen <nr> --als aufgabe¦beschluss |
| [`verlauf`](#verlauf) | was passiert ist: amw verlauf [--stunden 24] [--agent CC1] [--art erledigt --art pruefung] [--zusammenfassung] |
| [`plan`](#plan) | pruefen (Lücken mit Bedeutung und Abhilfe) ¦ akzeptieren <schlüssel> --grund … ¦ wieder <schlüssel> ¦ prognose (P50/P85 je Schritt und Bogen) ¦ status (Ampel je Dimension) |
| [`lauf`](#lauf) | Rechen-Läufe: start [--warten] prüft Halt, Schirm, Speicher, einen schweren/Schirm-Lauf zur Zeit, Warteschlange · warte <nr> blockiert, bis er dran ist · zeige <nr> mit Wartegrund |
| [`schirm`](#schirm) | Schirm-Schalter: zeige ¦ frei --grund … [--bis HH:MM] (Entwickler/Lead) ¦ zu [--grund …] (alle) |
| [`server`](#server) | Projekt-Server überwachen: anmelden ¦ abmelden ¦ liste ¦ pruefen |
| [`pruefung`](#pruefung) | Prüfbitte je Stand (SHA), Ergebnis grün/rot |
| [`hinweis`](#hinweis) | Anweisung an einen Agenten oder alle (z. B. „keine Rechen-Jobs“) |
| [`rezept`](#rezept) | Lauf-Rezepte als Daten |
| [`wortlaut`](#wortlaut) | Aussage des Entwicklers wörtlich erfassen |
| [`beschluss`](#beschluss) | Beschluss anlegen (optional einen alten ersetzen) |
| [`regel`](#regel) | Regel anlegen/ändern – nur mit Beschluss |
| [`dokument`](#dokument) | Ergebnisse ablegen und finden: ablegen <datei> ¦ version <nr> <datei> ¦ liste ¦ zeigen <nr> ¦ kommentar¦ueberarbeiten <nr> --text … ¦ zuordnen <nr> ¦ archivieren¦wiederherstellen <nr> ¦ online¦offline <nr> ¦ loeschen <nr> --ja ¦ einsammeln <ordner> [--melden] ¦ einsammeln --uebernehmen --frage <nr> |
| [`notiz`](#notiz) | gepflegte Notizen (Schlüssel/Wert) |
| [`dienst`](#dienst) | Wächter als geplante Windows-Aufgabe: einrichten ¦ entfernen ¦ status ¦ neustart ¦ vordergrund (ohne Aufgabe in diesem Fenster, zum Ausprobieren) |
| [`web`](#web) | Online-Teil: einrichten (Turso-Zugang, einmal) ¦ status ¦ einmal (Abgleich) ¦ zweitfaktor-neu ¦ bauen ¦ schema |
| [`anmelden`](#anmelden) | laufende Sitzung beim Wächter anmelden (ohne Neustart) |
| [`einrichten`](#einrichten) | ohne Angabe: geführte Einrichtung (fragt nach) ¦ schnell --projekt-name … (ohne Fragen) ¦ agenten-ordner <pfad> (Hooks, Statusline-Brücke, Sperren) |
| [`befehle`](#befehle) | Befehlsreferenz als Markdown (für doc/befehle.md) |
| [`sichern`](#sichern) | Sicherung der Datenbank (vollständige Kopie, auch während des Betriebs) |
| [`push`](#push) | Benachrichtigungen aufs Handy: status ¦ probe ¦ an ¦ aus ¦ ntfy ¦ pushover ¦ telegram ¦ ruhe 22:00-07:00¦aus ¦ link URL ¦ ereignis art=an¦aus |
| [`hook`](#hook) | zeigt die Einstellungen für einen Agenten-Projektordner (schreibt nichts) |
| [`release`](#release) | Release Notes: je Merge eine Zeile, Version fasst zusammen |

## init
```
usage: amw init [-h] [--projekt PROJEKT_INIT] [--von VON]

options:
  -h, --help            show this help message and exit
  --projekt PROJEKT_INIT
                        gleich ein erstes Projekt anlegen
  --von VON
```

## projekt
```
usage: amw projekt [-h] [--beschreibung BESCHREIBUNG] [--von VON]
                   [--projekt PROJEKT]
                   {neu,liste} [name]

positional arguments:
  {neu,liste}
  name

options:
  -h, --help            show this help message and exit
  --beschreibung BESCHREIBUNG
  --von VON
  --projekt PROJEKT
```

## agent
```
usage: amw agent [-h] [--ordner ORDNER] [--zusatz ZUSATZ]
                 [--denkstufe DENKSTUFE] [--modell MODELL]
                 [--startsatz STARTSATZ] [--rechte RECHTE] [--fernsteuerung]
                 [--keine-fernsteuerung] [--neustart] [--kein-neustart]
                 [--neu] [--datei DATEI] [--rolle ROLLE] [--grenzen GRENZEN]
                 [--startbefehl STARTBEFEHL] [--ohne-rund] [--von VON]
                 [--projekt PROJEKT]
                 {neu,liste,profil,starten,beenden,startskript,umbenennen}
                 [kennung] [neu]

positional arguments:
  {neu,liste,profil,starten,beenden,startskript,umbenennen}
  kennung
  neu                   umbenennen: die neue Kennung (die alte bleibt als
                        Alias gültig)

options:
  -h, --help            show this help message and exit
  --ordner ORDNER       profil: Arbeitsordner
  --zusatz ZUSATZ       profil: weitere Ordner, mit ; getrennt
  --denkstufe DENKSTUFE
                        profil: low | medium | high | xhigh | max
  --modell MODELL       profil: z. B. opus, sonnet (leer = Vorgabe)
  --startsatz STARTSATZ
                        profil: erste Anweisung einer neuen Sitzung
  --rechte RECHTE       profil: vorgabe | auto | umgehen
  --fernsteuerung       profil: Remote Control an
  --keine-fernsteuerung
  --neustart            profil: nach Absturz automatisch fortsetzen
  --kein-neustart
  --neu                 starten: frische Sitzung statt Fortsetzen
  --datei DATEI         startskript: in diese Datei schreiben
  --rolle ROLLE
  --grenzen GRENZEN
  --startbefehl STARTBEFEHL
  --ohne-rund           bekommt keine Rundschreiben
  --von VON
  --projekt PROJEKT
```

## posten
```
usage: amw posten [-h] --an AN --art ART --kurz KURZ [--text TEXT]
                  [--text-datei TEXT_DATEI] [--antwort-auf ANTWORT_AUF]
                  [--aufgabe AUFGABE] [--von VON] [--projekt PROJEKT]

options:
  -h, --help            show this help message and exit
  --an AN
  --art ART
  --kurz KURZ
  --text TEXT
  --text-datei TEXT_DATEI
  --antwort-auf ANTWORT_AUF
  --aufgabe AUFGABE
  --von VON
  --projekt PROJEKT
```

## lesen
```
usage: amw lesen [-h] [--grenze GRENZE] [--von VON] [--projekt PROJEKT] [id]

positional arguments:
  id

options:
  -h, --help         show this help message and exit
  --grenze GRENZE
  --von VON
  --projekt PROJEKT
```

## erledigt
```
usage: amw erledigt [-h] [--bemerkung BEMERKUNG] [--von VON]
                    [--projekt PROJEKT]
                    ids [ids ...]

positional arguments:
  ids

options:
  -h, --help            show this help message and exit
  --bemerkung BEMERKUNG
  --von VON
  --projekt PROJEKT
```

## aufgabe
```
usage: amw aufgabe [-h] [--titel TITEL] [--agent AGENT] [--auftrag AUFTRAG]
                   [--rang RANG] [--pruefer PRUEFER] [--beleg BELEG]
                   [--wartet-auf WARTET_AUF] [--auf AUF] [--erledigt ERLEDIGT]
                   [--bemerkung BEMERKUNG] [--alle] [--bogen BOGEN]
                   [--kriterium KRITERIUM] [--schaetzung SCHAETZUNG]
                   [--komplexitaet KOMPLEXITAET] [--nach NACH]
                   [--verantwortlich VERANTWORTLICH]
                   [--pruefbefehl PRUEFBEFEHL] [--dateien DATEIEN]
                   [--anforderungen ANFORDERUNGEN]
                   [--zusammenfassung ZUSAMMENFASSUNG]
                   [--ohne-vorgaenger OHNE_VORGAENGER] [--text TEXT] [--nein]
                   [--zurueck] [--kommentar KOMMENTAR] [--von VON]
                   [--projekt PROJEKT]
                   {neu,aendern,liste,zeige,start,blockiert,wartet,fertig,verwerfen,parken,aktiv,keine_prio,pool,kriterium,plan,planfrei}
                   [id] [nr]

positional arguments:
  {neu,aendern,liste,zeige,start,blockiert,wartet,fertig,verwerfen,parken,aktiv,keine_prio,pool,kriterium,plan,planfrei}
  id
  nr                    kriterium: Nummer des Kriteriums

options:
  -h, --help            show this help message and exit
  --titel TITEL
  --agent AGENT         Bearbeiter (auch „Entwickler“ für Schritte des
                        Menschen)
  --auftrag AUFTRAG
  --rang RANG
  --pruefer PRUEFER
  --beleg BELEG
  --wartet-auf WARTET_AUF
                        wartet/blockiert: Erklärung als Text (zusätzlich zu
                        --auf)
  --auf AUF             wartet/blockiert: worauf, als Verweise –
                        F5148,A1240,L141,CC2,Marcel,Monitor:<was> (Pflicht;
                        erledigt sich von selbst und weckt dich)
  --erledigt ERLEDIGT   wartet/blockiert: diese Gründe von Hand abhaken, z. B.
                        F5148 (allein: Status bleibt)
  --bemerkung BEMERKUNG
  --alle
  --bogen BOGEN         Planung: gehört zu Bogen N
  --kriterium KRITERIUM
                        Planung: Abnahmekriterium, mehrfach (ersetzt die
                        Liste)
  --schaetzung SCHAETZUNG
                        Planung: Stunden
  --komplexitaet KOMPLEXITAET
                        Planung: 1–10; ab 7 braucht der Schritt einen
                        freigegebenen Plan
  --nach NACH, --abhaengig-von NACH
                        Vorgänger, z. B. 1201,1203 (startbar erst, wenn sie
                        fertig sind)
  --verantwortlich VERANTWORTLICH
                        Planung: wer abnimmt bzw. Pläne freigibt
  --pruefbefehl PRUEFBEFEHL
                        Planung: wie der Bearbeiter selbst prüft
  --dateien DATEIEN     Planung: Dateibereich, den er anfassen darf
  --anforderungen ANFORDERUNGEN
                        Planung: abgedeckte Anforderungen, z. B. R1,R3
  --zusammenfassung ZUSAMMENFASSUNG
                        fertig: Pflicht für Schritte in einem Bogen; aendern:
                        nachtragen
  --ohne-vorgaenger OHNE_VORGAENGER
                        aendern: diese Vorgänger lösen, z. B. 115
  --text TEXT           plan: der Plan
  --nein                kriterium: wieder als offen markieren
  --zurueck             planfrei: zurückweisen (mit --kommentar)
  --kommentar KOMMENTAR
  --von VON
  --projekt PROJEKT
```

## frage
```
usage: amw frage [-h] [--an {entwickler,tl}] [--kurz KURZ] [--worum WORUM]
                 [--option OPTION] [--empfehlung EMPFEHLUNG]
                 [--fundstellen FUNDSTELLEN] [--geprueft GEPRUEFT]
                 [--aufgabe AUFGABE] [--blockiert] [--text TEXT]
                 [--rueckfrage RUECKFRAGE] [--grund GRUND] [--geparkt]
                 [--anhang ANHANG] [--von VON] [--projekt PROJEKT]
                 {neu,liste,antworten,nachtrag,verlauf,parken,aufnehmen} [id]

positional arguments:
  {neu,liste,antworten,nachtrag,verlauf,parken,aufnehmen}
  id

options:
  -h, --help            show this help message and exit
  --an {entwickler,tl}
  --kurz KURZ
  --worum WORUM
  --option OPTION       neu: 'A=Text' (mehrfach); antworten: Kennung
  --empfehlung EMPFEHLUNG
  --fundstellen FUNDSTELLEN
  --geprueft GEPRUEFT   neu: was du vorher in der AMW geprüft hast
                        (Beschlüsse, Fragen, Regeln) – Pflicht bei Fragen an
                        den Entwickler; findet die AMW Treffer, nenne
                        mindestens einen
  --aufgabe AUFGABE
  --blockiert
  --text TEXT
  --rueckfrage RUECKFRAGE
  --grund GRUND         neu: warum du das empfiehlst; parken/aufnehmen: warum
                        (steht im Verlauf)
  --geparkt             liste: nur die geparkten
  --anhang ANHANG       neu: Bild/Mockup zu einer Option, 'A=datei.png' oder
                        'A=D12' (mehrfach) – erscheint als Variante zum
                        Anklicken, auch online
  --von VON
  --projekt PROJEKT
```

## halt
```
usage: amw halt [-h] [--fuer FUER] --text TEXT [--von VON] [--projekt PROJEKT]

options:
  -h, --help         show this help message and exit
  --fuer FUER
  --text TEXT
  --von VON
  --projekt PROJEKT
```

## weiter
```
usage: amw weiter [-h] [--fuer FUER] [--von VON] [--projekt PROJEKT]

options:
  -h, --help         show this help message and exit
  --fuer FUER
  --von VON
  --projekt PROJEKT
```

## taetigkeit
```
usage: amw taetigkeit [-h] [--aufgabe AUFGABE] [--von VON] [--projekt PROJEKT]
                      [text ...]

positional arguments:
  text

options:
  -h, --help         show this help message and exit
  --aufgabe AUFGABE
  --von VON
  --projekt PROJEKT
```

## kontext
```
usage: amw kontext [-h] [--von VON] [--projekt PROJEKT] [agent]

positional arguments:
  agent

options:
  -h, --help         show this help message and exit
  --von VON
  --projekt PROJEKT
```

## regeln
```
usage: amw regeln [-h] [--von VON] [--projekt PROJEKT]

options:
  -h, --help         show this help message and exit
  --von VON
  --projekt PROJEKT
```

## suche
```
usage: amw suche [-h]
                 [--art {aufgabe,beschluss,frage,wortlaut,nachricht,dokument}]
                 [--grenze GRENZE] [--wissen] [--von VON] [--projekt PROJEKT]
                 text [text ...]

positional arguments:
  text

options:
  -h, --help            show this help message and exit
  --art {aufgabe,beschluss,frage,wortlaut,nachricht,dokument}
                        nur diese Art (mehrfach)
  --grenze GRENZE
  --wissen              dazu: passende Beschlüsse/Fragen/Regeln wie bei frage
                        neu
  --von VON
  --projekt PROJEKT
```

## zeige
```
usage: amw zeige [-h] [--von VON] [--projekt PROJEKT] refs [refs ...]

positional arguments:
  refs

options:
  -h, --help         show this help message and exit
  --von VON
  --projekt PROJEKT
```

## leitbild
```
usage: amw leitbild [-h] [--ziel ZIEL] [--kennzahl KENNZAHL]
                    [--nicht-ziel NICHT_ZIEL] [--prinzip PRINZIP] [--dod DOD]
                    [--von VON] [--projekt PROJEKT]
                    [{zeigen,setzen}]

positional arguments:
  {zeigen,setzen}

options:
  -h, --help            show this help message and exit
  --ziel ZIEL
  --kennzahl KENNZAHL   mehrfach; ersetzt die Liste
  --nicht-ziel NICHT_ZIEL
                        mehrfach; ersetzt die Liste
  --prinzip PRINZIP     "Text|Prüffrage", mehrfach; ersetzt die Liste
  --dod DOD             Definition of Done, mehrfach; ersetzt die Liste
  --von VON
  --projekt PROJEKT
```

## bogen
```
usage: amw bogen [-h] [--titel TITEL] [--ziel ZIEL] [--abnahme ABNAHME]
                 [--zieldatum ZIELDATUM] [--nr NR] [--grund GRUND]
                 [--erzwingen] [--von VON] [--projekt PROJEKT]
                 {liste,neu,zeigen,aendern,status} [id] [wert]

positional arguments:
  {liste,neu,zeigen,aendern,status}
  id
  wert                  status: aktiv | fertig | geplant | verworfen

options:
  -h, --help            show this help message and exit
  --titel TITEL
  --ziel ZIEL
  --abnahme ABNAHME     prüfbares Abnahmekriterium
  --zieldatum ZIELDATUM
                        JJJJ-MM-TT
  --nr NR               Reihenfolge
  --grund GRUND         nötig, wenn das Zieldatum nach der Baseline geändert
                        wird
  --erzwingen
  --von VON
  --projekt PROJEKT
```

## spec
```
usage: amw spec [-h] [--text TEXT] [--datei DATEI] [--kommentar KOMMENTAR]
                [--von VON] [--projekt PROJEKT]
                {zeigen,schreiben,vorlegen,frei,zurueck} bogen
                [{anforderungen,entwurf,schritte}]

positional arguments:
  {zeigen,schreiben,vorlegen,frei,zurueck}
  bogen
  {anforderungen,entwurf,schritte}

options:
  -h, --help            show this help message and exit
  --text TEXT
  --datei DATEI
  --kommentar KOMMENTAR
  --von VON
  --projekt PROJEKT
```

## schritt
```
usage: amw schritt [-h] [--nehmen] [--von VON] [--projekt PROJEKT] {naechster}

positional arguments:
  {naechster}

options:
  -h, --help         show this help message and exit
  --nehmen           gleich übernehmen (Bearbeiter = du, Status läuft)
  --von VON
  --projekt PROJEKT
```

## risiko
```
usage: amw risiko [-h] [--titel TITEL] [--ursache URSACHE] [--wirkung WIRKUNG]
                  [--w W] [--a A]
                  [--strategie {vermeiden,mindern,uebertragen,akzeptieren}]
                  [--massnahme MASSNAHME] [--verantwortlich VERANTWORTLICH]
                  [--ausloeser AUSLOESER]
                  [--status {offen,eingetreten,erledigt}] [--bogen BOGEN]
                  [--von VON] [--projekt PROJEKT]
                  {liste,neu,setzen} [id]

positional arguments:
  {liste,neu,setzen}
  id

options:
  -h, --help            show this help message and exit
  --titel TITEL
  --ursache URSACHE
  --wirkung WIRKUNG
  --w W                 Wahrscheinlichkeit 1–5
  --a A                 Auswirkung 1–5
  --strategie {vermeiden,mindern,uebertragen,akzeptieren}
  --massnahme MASSNAHME
  --verantwortlich VERANTWORTLICH
  --ausloeser AUSLOESER
  --status {offen,eingetreten,erledigt}
  --bogen BOGEN
  --von VON
  --projekt PROJEKT
```

## rueckblick
```
usage: amw rueckblick [-h] [--gut GUT] [--schlecht SCHLECHT]
                      [--massnahme MASSNAHME] [--gelernt GELERNT]
                      [--uebernehmen UEBERNEHMEN] [--als {aufgabe,beschluss}]
                      [--agent AGENT] [--von VON] [--projekt PROJEKT]
                      [bogen]

positional arguments:
  bogen

options:
  -h, --help            show this help message and exit
  --gut GUT
  --schlecht SCHLECHT
  --massnahme MASSNAHME
  --gelernt GELERNT
  --uebernehmen UEBERNEHMEN
                        Nummer eines Maßnahmen-Eintrags
  --als {aufgabe,beschluss}
  --agent AGENT         Bearbeiter, wenn eine Maßnahme zur Aufgabe wird
  --von VON
  --projekt PROJEKT
```

## verlauf
```
usage: amw verlauf [-h] [--stunden STUNDEN] [--agent AGENT]
                   [--art {nachricht,erledigt,lauf,pruefung,frage,beschluss,plan,sitzung,dokument}]
                   [--grenze GRENZE] [--zusammenfassung] [--von VON]
                   [--projekt PROJEKT]

options:
  -h, --help            show this help message and exit
  --stunden STUNDEN
  --agent AGENT
  --art {nachricht,erledigt,lauf,pruefung,frage,beschluss,plan,sitzung,dokument}
  --grenze GRENZE
  --zusammenfassung     nur Zahlen
  --von VON
  --projekt PROJEKT
```

## plan
```
usage: amw plan [-h] [--grund GRUND] [--kurz] [--von VON] [--projekt PROJEKT]
                {pruefen,prognose,status,akzeptieren,wieder} [schluessel]

positional arguments:
  {pruefen,prognose,status,akzeptieren,wieder}
  schluessel            akzeptieren/wieder: Schlüssel des Befunds, z. B.
                        bogen_ohne_zieldatum:B3

options:
  -h, --help            show this help message and exit
  --grund GRUND         akzeptieren: warum es so in Ordnung ist
  --kurz                pruefen: nur eine Zeile je Befund
  --von VON
  --projekt PROJEKT
```

## lauf
```
usage: amw lauf [-h] [--warten] [--hoechstens HOECHSTENS] [--dauer DAUER]
                [--beschreibung BESCHREIBUNG] [--rezept REZEPT] [--leicht]
                [--schirm] [--aufgabe AUFGABE] [--rc RC] [--ergebnis ERGEBNIS]
                [--abgebrochen] [--grenze GRENZE] [--von VON]
                [--projekt PROJEKT]
                {start,ende,liste,vorziehen,zeige,warte} [id]

positional arguments:
  {start,ende,liste,vorziehen,zeige,warte}
  id

options:
  -h, --help            show this help message and exit
  --warten              ist der Platz belegt: NUR einreihen (noch nicht
                        rechnen!) statt ablehnen; Freigabe weckt dich – oder
                        danach: amw lauf warte <nr>
  --hoechstens HOECHSTENS
                        warte: nach so vielen Minuten aufgeben (rc 3), Lauf
                        bleibt eingereiht
  --dauer DAUER         erwartete Dauer in Minuten; doppelt so lang → Warnung
                        an den Lead
  --beschreibung BESCHREIBUNG
  --rezept REZEPT
  --leicht              kein schwerer Lauf (keine Speicher-Grenze)
  --schirm
  --aufgabe AUFGABE
  --rc RC
  --ergebnis ERGEBNIS
  --abgebrochen
  --grenze GRENZE
  --von VON
  --projekt PROJEKT
```

## schirm
```
usage: amw schirm [-h] [--grund GRUND] [--bis BIS] [--verlauf]
                  [--grenze GRENZE] [--von VON] [--projekt PROJEKT]
                  [{zeige,frei,zu}]

positional arguments:
  {zeige,frei,zu}

options:
  -h, --help         show this help message and exit
  --grund GRUND
  --bis BIS          frei: geht zu dieser Ortszeit von selbst zu, z. B. 07:00
                     oder "2026-11-05 07:00"
  --verlauf          zeige: die letzten Wechsel
  --grenze GRENZE
  --von VON
  --projekt PROJEKT
```

## server
```
usage: amw server [-h] [--port PORT] [--start START] [--ordner ORDNER]
                  [--neustart] [--zustaendig ZUSTAENDIG] [--von VON]
                  [--projekt PROJEKT]
                  {anmelden,abmelden,liste,pruefen} [name]

positional arguments:
  {anmelden,abmelden,liste,pruefen}
  name

options:
  -h, --help            show this help message and exit
  --port PORT
  --start START         Startbefehl, z. B. "pythonw C:/pfad/server.py --port
                        8766"
  --ordner ORDNER       Arbeitsordner für den Startbefehl
  --neustart            bei Ausfall automatisch neu starten
  --zustaendig ZUSTAENDIG
                        wer bei Ausfall benachrichtigt wird (Vorgabe: du)
  --von VON
  --projekt PROJEKT
```

## pruefung
```
usage: amw pruefung [-h] [--pruefer PRUEFER] [--zweig ZWEIG] [--sha SHA]
                    [--punkte PUNKTE] [--aufgabe AUFGABE]
                    [--bemerkung BEMERKUNG] [--alle] [--von VON]
                    [--projekt PROJEKT]
                    {bitte,gruen,rot,ist-gruen,liste} [id]

positional arguments:
  {bitte,gruen,rot,ist-gruen,liste}
  id

options:
  -h, --help            show this help message and exit
  --pruefer PRUEFER
  --zweig ZWEIG
  --sha SHA
  --punkte PUNKTE
  --aufgabe AUFGABE
  --bemerkung BEMERKUNG
  --alle
  --von VON
  --projekt PROJEKT
```

## hinweis
```
usage: amw hinweis [-h] [--fuer FUER] [--text TEXT] [--bis BIS] [--von VON]
                   [--projekt PROJEKT]
                   {setzen,aufheben} [id]

positional arguments:
  {setzen,aufheben}
  id

options:
  -h, --help         show this help message and exit
  --fuer FUER
  --text TEXT
  --bis BIS          UTC, z. B. 2026-11-02T06:00:00Z
  --von VON
  --projekt PROJEKT
```

## rezept
```
usage: amw rezept [-h] [--befehl BEFEHL] [--beschreibung BESCHREIBUNG]
                  [--schirm] [--speicher SPEICHER] [--leicht] [--von VON]
                  [--projekt PROJEKT]
                  {setzen,zeige,liste} [name]

positional arguments:
  {setzen,zeige,liste}
  name

options:
  -h, --help            show this help message and exit
  --befehl BEFEHL
  --beschreibung BESCHREIBUNG
  --schirm
  --speicher SPEICHER
  --leicht
  --von VON
  --projekt PROJEKT
```

## wortlaut
```
usage: amw wortlaut [-h] [--text TEXT] [--text-datei TEXT_DATEI]
                    [--kanal KANAL] [--zeit ZEIT] [--bemerkung BEMERKUNG]
                    [--von VON] [--projekt PROJEKT]

options:
  -h, --help            show this help message and exit
  --text TEXT
  --text-datei TEXT_DATEI
  --kanal KANAL
  --zeit ZEIT           UTC der Aussage
  --bemerkung BEMERKUNG
  --von VON
  --projekt PROJEKT
```

## beschluss
```
usage: amw beschluss [-h] [--text TEXT] [--text-datei TEXT_DATEI] --stichwort
                     STICHWORT --quelle QUELLE [--thema THEMA] [--zeit ZEIT]
                     [--wortlaut WORTLAUT] [--aufgaben AUFGABEN]
                     [--ersetzt ERSETZT] [--von VON] [--projekt PROJEKT]

options:
  -h, --help            show this help message and exit
  --text TEXT
  --text-datei TEXT_DATEI
  --stichwort STICHWORT
  --quelle QUELLE
  --thema THEMA
  --zeit ZEIT
  --wortlaut WORTLAUT
  --aufgaben AUFGABEN
  --ersetzt ERSETZT
  --von VON
  --projekt PROJEKT
```

## regel
```
usage: amw regel [-h] [--text TEXT] [--text-datei TEXT_DATEI] --ebene
                 {arbeit,projekt} --nr NR --beschluss BESCHLUSS [--teil TEIL]
                 [--von VON] [--projekt PROJEKT]

options:
  -h, --help            show this help message and exit
  --text TEXT
  --text-datei TEXT_DATEI
  --ebene {arbeit,projekt}
  --nr NR
  --beschluss BESCHLUSS
  --teil TEIL
  --von VON
  --projekt PROJEKT
```

## dokument
```
usage: amw dokument [-h] [--datei DATEI] [--titel TITEL]
                    [--art {ergebnis,bericht,entwurf,mockup,bild,quelle}]
                    [--notiz NOTIZ] [--bogen BOGEN] [--aufgabe AUFGABE]
                    [--frage FRAGE] [--beschluss BESCHLUSS] [--loesen]
                    [--online] [--agent AGENT] [--suche SUCHE] [--alle]
                    [--text TEXT] [--ja] [--melden] [--uebernehmen]
                    [--nur NUR] [--von VON] [--projekt PROJEKT]
                    {ablegen,version,liste,zeigen,kommentar,ueberarbeiten,zuordnen,archivieren,wiederherstellen,online,offline,loeschen,einsammeln}
                    [nr] [pfad]

positional arguments:
  {ablegen,version,liste,zeigen,kommentar,ueberarbeiten,zuordnen,archivieren,wiederherstellen,online,offline,loeschen,einsammeln}
  nr                    ablegen: die Datei; einsammeln: der Ordner; sonst
                        Nummer des Dokuments (D12 oder 12)
  pfad                  version: die neue Datei

options:
  -h, --help            show this help message and exit
  --datei DATEI         statt der Positionsangabe (Brücke: nur aus eingang-
                        tl/)
  --titel TITEL
  --art {ergebnis,bericht,entwurf,mockup,bild,quelle}
  --notiz NOTIZ         was diese Version ist bzw. was sich geändert hat
  --bogen BOGEN         Bezug: bogen (Nummer)
  --aufgabe AUFGABE     Bezug: aufgabe (Nummer)
  --frage FRAGE         Bezug: frage (Nummer)
  --beschluss BESCHLUSS
                        Bezug: beschluss (Nummer)
  --loesen              zuordnen: Bezug entfernen
  --online              ablegen: Datei auch online zeigen (Texte sind es
                        immer)
  --agent AGENT         liste: nur von diesem Agenten
  --suche SUCHE         liste: in Titel und Text suchen
  --alle                liste: auch archivierte und gelöschte
  --text TEXT           kommentar/ueberarbeiten: was zu sagen ist
  --ja                  loeschen: bestätigen
  --melden              einsammeln: Liste als Dokument ablegen und den
                        Entwickler fragen
  --uebernehmen         einsammeln: nach der Antwort auf --frage übernehmen
  --nur NUR             einsammeln --uebernehmen: nur diese Ablage
                        (Unterordner), mehrfach
  --von VON
  --projekt PROJEKT
```

## notiz
```
usage: amw notiz [-h] [--beschluss BESCHLUSS] [--text TEXT]
                 [--text-datei TEXT_DATEI] [--von VON] [--projekt PROJEKT]
                 {setzen,zeige,entfernen} [schluessel ...]

positional arguments:
  {setzen,zeige,entfernen}
  schluessel            entfernen: mehrere möglich

options:
  -h, --help            show this help message and exit
  --beschluss BESCHLUSS
                        entfernen ohne Lead-Rolle: Nummer eines geltenden
                        Beschlusses (z. B. B2376)
  --text TEXT
  --text-datei TEXT_DATEI
  --von VON
  --projekt PROJEKT
```

## dienst
```
usage: amw dienst [-h] [--port PORT] [--ja] [--von VON] [--projekt PROJEKT]
                  {einrichten,entfernen,status,neustart,vordergrund}

positional arguments:
  {einrichten,entfernen,status,neustart,vordergrund}

options:
  -h, --help            show this help message and exit
  --port PORT           Vorgabe: Zahnrad › Dieser PC (8780)
  --ja                  wirklich ausführen (sonst nur anzeigen)
  --von VON
  --projekt PROJEKT
```

## web
```
usage: amw web [-h] [--von VON] [--projekt PROJEKT]
               {einrichten,bauen,schema,einmal,status,zweitfaktor-neu}

positional arguments:
  {einrichten,bauen,schema,einmal,status,zweitfaktor-neu}

options:
  -h, --help            show this help message and exit
  --von VON
  --projekt PROJEKT
```

## anmelden
```
usage: amw anmelden [-h] [--ersetzen] [--von VON] [--projekt PROJEKT]

options:
  -h, --help         show this help message and exit
  --ersetzen         eine noch lebende andere Sitzung derselben Kennung
                     ablösen
  --von VON
  --projekt PROJEKT
```

## einrichten
```
usage: amw einrichten [-h] [--nur-zeigen] [--ohne-sperren]
                      [--projekt-name PROJEKT_NAME] [--lead LEAD]
                      [--agenten AGENTEN] [--ordner ORDNER]
                      [--rechte {vorgabe,auto,umgehen}]
                      [--denkstufe {low,medium,high,xhigh,max}] [--mit-dienst]
                      [--ohne-hooks] [--fernsteuerung] [--entfernen]
                      [--von VON] [--projekt PROJEKT]
                      [{assistent,schnell,agenten-ordner}] [pfad]

positional arguments:
  {assistent,schnell,agenten-ordner}
  pfad

options:
  -h, --help            show this help message and exit
  --nur-zeigen
  --ohne-sperren        keine Sperr-Regeln (Ordner dessen, der den Wächter
                        betreut)
  --projekt-name PROJEKT_NAME
                        schnell: Name des Projekts
  --lead LEAD           schnell: Kennung des Lead-Agenten (leer = keiner)
  --agenten AGENTEN     schnell: Kennungen, mit Komma
  --ordner ORDNER       schnell: Projektordner der Agenten
  --rechte {vorgabe,auto,umgehen}
  --denkstufe {low,medium,high,xhigh,max}
  --mit-dienst          schnell: Wächter als geplante Aufgabe einrichten
  --ohne-hooks          schnell: Projektordner nicht anfassen
  --fernsteuerung       schnell: Remote Control für die Agenten an (Vorgabe
                        aus)
  --entfernen           agenten-ordner: AMW-Einträge wieder herausnehmen
  --von VON
  --projekt PROJEKT
```

## befehle
```
usage: amw befehle [-h] [--von VON] [--projekt PROJEKT]

options:
  -h, --help         show this help message and exit
  --von VON
  --projekt PROJEKT
```

## sichern
```
usage: amw sichern [-h] [--ziel ZIEL] [--von VON] [--projekt PROJEKT]

options:
  -h, --help         show this help message and exit
  --ziel ZIEL        Datei (*.db) oder Ordner (Vorgabe: sicherung-<Datum-
                     Zeit>.db neben der Datenbank)
  --von VON
  --projekt PROJEKT
```

## push
```
usage: amw push [-h] [--kanal KANAL] [--server SERVER] [--token TOKEN]
                [--chat CHAT] [--app-token APP_TOKEN] [--user-key USER_KEY]
                [--von VON] [--projekt PROJEKT]
                {status,probe,an,aus,ntfy,pushover,telegram,ruhe,link,ereignis}
                [wert]

positional arguments:
  {status,probe,an,aus,ntfy,pushover,telegram,ruhe,link,ereignis}
  wert                  ruhe: 22:00-07:00 oder aus · link: URL · ereignis:
                        frage=aus · probe: Anbieter

options:
  -h, --help            show this help message and exit
  --kanal KANAL         ntfy: eigener Kanalname (sonst zufällig)
  --server SERVER       ntfy: eigener Server (https://…)
  --token TOKEN         ntfy-Zugangstoken bzw. Telegram-Bot-Token
  --chat CHAT           Telegram: Chat-ID
  --app-token APP_TOKEN
                        Pushover: App-Token
  --user-key USER_KEY   Pushover: Benutzerschlüssel
  --von VON
  --projekt PROJEKT
```

## hook
```
usage: amw hook [-h] [--agent AGENT] [--von VON] [--projekt PROJEKT] {zeige}

positional arguments:
  {zeige}

options:
  -h, --help         show this help message and exit
  --agent AGENT      nur für die Beispielzeile des Startbefehls
  --von VON
  --projekt PROJEKT
```

## release
```
usage: amw release [-h] [--titel TITEL] [--commit COMMIT] [--version VERSION]
                   [--aufgaben AUFGABEN] [--text TEXT]
                   [--text-datei TEXT_DATEI] [--von VON] [--projekt PROJEKT]
                   {merge,version,liste}

positional arguments:
  {merge,version,liste}

options:
  -h, --help            show this help message and exit
  --titel TITEL
  --commit COMMIT
  --version VERSION
  --aufgaben AUFGABEN
  --text TEXT
  --text-datei TEXT_DATEI
  --von VON
  --projekt PROJEKT
```
