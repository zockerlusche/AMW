# Befehle

Erzeugt aus der Kommandozeile (`amw befehle > doc/befehle.md`). Jeder Befehl zeigt mit `--help` dasselbe.
Gemeinsam für alle: `--von <Kennung>` (wer handelt; sonst `AMW_AGENT`), `--projekt <Name>` (sonst das erste Projekt).

| Befehl | Zweck |
|---|---|
| [`init`](#init) | neue Datenbank anlegen |
| [`projekt`](#projekt) | Projekte: neu <name> ¦ liste ¦ ordner [<name>] – jedes Projekt ist für sich (eigene Agenten, Regeln, Daten); bequemer: Workbench › Projekt-Auswahl › Neues Projekt |
| [`agent`](#agent) | neu ¦ liste ¦ profil ¦ starten ¦ beenden ¦ startskript ¦ umbenennen ALT NEU |
| [`posten`](#posten) | Nachricht schicken: --an CC2 (oder alle, Entwickler) --art auftrag¦frage¦info¦… --kurz … |
| [`lesen`](#lesen) | ohne Nummer: offene Liste; mit Nummern: ganze Nachrichten (lesen 16707 16589) |
| [`erledigt`](#erledigt) | Nachrichten als erledigt markieren: amw erledigt 12 13 ¦ --info [--vor 04.11.] |
| [`aufgabe`](#aufgabe) | neu ¦ aendern N ¦ liste ¦ zeige N [--kurz] ¦ start ¦ fertig ¦ … ¦ kriterium N nr ¦ plan N --text ¦ planfrei N [--zurueck --kommentar] ¦ nachtrag N --titel … (Folgearbeit zu einer fertigen Aufgabe) |
| [`thema`](#thema) | Design-Dokument je Thema: liste [--suche] ¦ zeige TH12 ¦ neu "Name" [--pfleger X] [--stil] ¦ einstellen TH12 --pfleger X ¦ --stil ¦ pflegen TH12 --text-datei … ¦ bestaetigen TH12 ¦ dokument TH12 --dokument D5 [--loesen] |
| [`termin`](#termin) | Terminplaner: neu --titel … --art test¦frist¦schirm¦sonstig --am "2026-11-06 18:00" [--woechentlich --bis 2026-12-31] [--vorlauf 4] [--bogen N] ¦ liste [--tage 21] ¦ aendern N ¦ absagen N [--am …] ¦ bereit N --text "was testen" ¦ kurzliste N (Planen: Lead/Entwickler) |
| [`liste`](#liste) | Arbeitsliste je Agent: liste [Agent¦pool] ¦ ordnen <Agent> A12 A15 … ¦ schieben A15 --vor A12 ¦ --nach ¦ --pos N ¦ --oben ¦ --unten (ordnen/schieben: Lead) |
| [`frage`](#frage) | Fragen an den Entwickler oder Lead: neu ¦ liste [--geparkt] ¦ antworten ¦ nachtrag ¦ verlauf ¦ parken N [--grund] ¦ aufnehmen N ¦ weiterleiten N [--text] (Lead → Entwickler) |
| [`halt`](#halt) | alle oder einen Agenten anhalten |
| [`weiter`](#weiter) | Halt aufheben |
| [`taetigkeit`](#taetigkeit) | was ich gerade tue (zeigt die Workbench), z. B. taetigkeit "A12 Login-Formular" |
| [`kontext`](#kontext) | Pflicht-Kontext für einen Agenten |
| [`regeln`](#regeln) | alle geltenden Regeln (Arbeits- und Projektregeln) |
| [`suche`](#suche) | Volltext über Aufgaben, Beschlüsse, Fragen, Wortlaut, Nachrichten, Dokumente: amw suche Modem |
| [`zeige`](#zeige) | Einträge ganz lesen: amw zeige B5 F12 A120 W3 16000 D5 KR3 PR4 (Nachricht ohne #: in der Shell beginnt mit # ein Kommentar) |
| [`leitbild`](#leitbild) | Projektziel, Kennzahlen, Nicht-Ziele, Prinzipien, Definition of Done: zeigen ¦ setzen |
| [`bogen`](#bogen) | Meilensteine: liste ¦ neu ¦ zeigen N ¦ aendern N ¦ status N aktiv¦fertig¦geplant¦verworfen |
| [`spec`](#spec) | Spezifikation je Bogen: zeigen N [teil] ¦ schreiben N teil --text/--datei ¦ vorlegen N teil ¦ frei N teil ¦ zurueck N teil --kommentar  (teil: anforderungen ¦ entwurf ¦ schritte) |
| [`schritt`](#schritt) | naechster [--nehmen]: nächster bereiter Schritt (aktiver Bogen, ohne offene Vorgänger) |
| [`risiko`](#risiko) | liste ¦ neu --titel … ¦ setzen N --status … |
| [`rueckblick`](#rueckblick) | Rückblick je Bogen: amw rueckblick <bogen> [--gut … --schlecht … --massnahme … --gelernt …] ¦ --uebernehmen <nr> --als aufgabe¦beschluss |
| [`verlauf`](#verlauf) | was passiert ist: amw verlauf [--stunden 24] [--agent CC1] [--art erledigt --art pruefung] [--zusammenfassung] |
| [`plan`](#plan) | pruefen (Lücken mit Bedeutung und Abhilfe) ¦ akzeptieren <schlüssel> --grund … ¦ wieder <schlüssel> ¦ prognose (P50/P85 je Schritt und Bogen) ¦ status (Ampel je Dimension) |
| [`lauf`](#lauf) | Rechen-Läufe: start [--warten] prüft Halt, Schirm, Speicher je Lauf, zwei Spuren (Grafikkarte/Schirm: einer zur Zeit; schwere ohne Fenster: parallel bis cpu_laeufe, je Agent einer), Warteschlange · warte <nr> blockiert, bis er dran ist · zeige <nr> mit Wartegrund · ausfuehren --beschreibung … [--schirm] [--ergebnis datei] -- <befehl …> (einreihen, warten, starten, rc durchreichen, Ende melden; bei Schirm zu den eigenen Befehl beenden) |
| [`schirm`](#schirm) | Schirm-Schalter: zeige ¦ frei --grund … [--bis HH:MM] (Entwickler/Lead) ¦ zu [--grund …] (alle) |
| [`server`](#server) | Projekt-Server überwachen: anmelden ¦ abmelden ¦ liste ¦ pruefen |
| [`pruefung`](#pruefung) | Prüfbitte je Stand (SHA), Ergebnis grün/rot |
| [`hinweis`](#hinweis) | Anweisung an einen Agenten oder alle (z. B. „keine Rechen-Jobs“) |
| [`rezept`](#rezept) | Lauf-Rezepte als Daten |
| [`ki`](#ki) | Lokale KIs (PC-weit): liste ¦ neu¦aendern <ki> (nur am PC) ¦ modell <ki> <name> ¦ freigeben¦sperren <ki> <modell> ¦ vorlage <ki> <name> --datei ¦ recht <ki> --wer ¦ auftrag <ki> --prompt … ¦ zeige L<nr> ¦ pruefen ¦ nachweis |
| [`wortlaut`](#wortlaut) | Aussage des Entwicklers wörtlich erfassen |
| [`beschluss`](#beschluss) | Beschluss anlegen (optional einen alten ersetzen) |
| [`regel`](#regel) | Regel anlegen/ändern – nur mit Beschluss |
| [`dokument`](#dokument) | Ergebnisse ablegen und finden: ablegen <datei> ¦ version <nr> <datei> ¦ liste ¦ zeigen <nr> ¦ kommentar¦ueberarbeiten <nr> --text … ¦ zuordnen <nr> ¦ archivieren¦wiederherstellen <nr> ¦ online¦offline <nr> ¦ loeschen <nr> --ja ¦ einsammeln <ordner> [--melden] ¦ einsammeln --uebernehmen --frage <nr> |
| [`notiz`](#notiz) | gepflegte Notizen (Schlüssel/Wert) |
| [`dienst`](#dienst) | Wächter als geplante Windows-Aufgabe: einrichten ¦ entfernen ¦ status ¦ neustart ¦ vordergrund (ohne Aufgabe in diesem Fenster, zum Ausprobieren) |
| [`web`](#web) | Online-Teil: einrichten (Turso-Zugang, einmal) ¦ status ¦ einmal (Abgleich) ¦ zweitfaktor-neu ¦ bauen ¦ schema |
| [`anmelden`](#anmelden) | laufende Sitzung beim Wächter anmelden (ohne Neustart) |
| [`abmelden`](#abmelden) | Sitzung ruht: nicht mehr wecken, nicht automatisch neu starten (bis anmelden) |
| [`einrichten`](#einrichten) | ohne Angabe: geführte Einrichtung (fragt nach) ¦ schnell --projekt-name … (ohne Fragen) ¦ agenten-ordner <pfad> (Hooks, Statusline-Brücke, Sperren) |
| [`befehle`](#befehle) | Befehlsreferenz als Markdown (für doc/befehle.md) |
| [`sichern`](#sichern) | Sicherung der Datenbank (vollständige Kopie, auch während des Betriebs); mit --projekt <name> nur dieses Projekt als eigene Datenbank (z. B. zum Umziehen auf einen anderen Rechner) |
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
usage: amw projekt [-h] [--beschreibung BESCHREIBUNG] [--regeln-von PROJEKT]
                   [--ordner ORDNER] [--von VON] [--projekt PROJEKT]
                   {neu,liste,ordner,einstellen} [name]

positional arguments:
  {neu,liste,ordner,einstellen}
  name                  einstellen: schluessel=wert

options:
  -h, --help            show this help message and exit
  --beschreibung BESCHREIBUNG
  --regeln-von PROJEKT  neu: die Arbeitsregeln (KR) eines Projekts einmal
                        kopieren – danach getrennt änderbar
  --ordner ORDNER       Projektordner (das Repository, in dem die Agenten
                        arbeiten; vorher selbst anlegen)
  --von VON
  --projekt PROJEKT
```

## agent
```
usage: amw agent [-h] [--ordner ORDNER] [--zusatz ZUSATZ]
                 [--denkstufe DENKSTUFE] [--modell MODELL]
                 [--startsatz STARTSATZ] [--rechte RECHTE] [--fernsteuerung]
                 [--keine-fernsteuerung] [--neustart] [--kein-neustart]
                 [--neu] [--datei DATEI] [--alle] [--abstand ABSTAND]
                 [--rolle ROLLE] [--grenzen GRENZEN]
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
  --alle                startskript: auch Agenten mit Soll aus/ruht (jeder mit
                        Profil-Ordner)
  --abstand ABSTAND     startskript: Sekunden zwischen zwei Starts (Vorgabe
                        20)
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
                  [--aufgabe AUFGABE] [--bis BIS] [--von VON]
                  [--projekt PROJEKT]

options:
  -h, --help            show this help message and exit
  --an AN
  --art ART
  --kurz KURZ
  --text TEXT
  --text-datei TEXT_DATEI
  --antwort-auf ANTWORT_AUF
  --aufgabe AUFGABE
  --bis BIS             die Meldung erledigt sich von selbst, sobald das
                        erfüllt ist: leitbild | aufgabe (du hast eine) | A<nr>
                        (fertig) | F<nr> (beantwortet)
  --von VON
  --projekt PROJEKT
```

## lesen
```
usage: amw lesen [-h] [--grenze GRENZE] [--neu] [--verlauf] [--von VON]
                 [--projekt PROJEKT]
                 [id ...]

positional arguments:
  id

options:
  -h, --help         show this help message and exit
  --grenze GRENZE
  --neu              nur Ungelesenes, neueste zuerst
  --verlauf          die letzten Nachrichten an mich, auch gelesene und
                     erledigte
  --von VON
  --projekt PROJEKT
```

## erledigt
```
usage: amw erledigt [-h] [--bemerkung BEMERKUNG] [--info] [--vor VOR]
                    [--fuer FUER] [--von VON] [--projekt PROJEKT]
                    [ids ...]

positional arguments:
  ids

options:
  -h, --help            show this help message and exit
  --bemerkung BEMERKUNG
  --info                alle offenen info-Nachrichten an mich erledigen
  --vor VOR             mit --info: nur ältere als dieses Datum (04.11. oder
                        2026-11-04)
  --fuer FUER           Lead: veraltete info/meldung an den Entwickler
                        schließen (--fuer Entwickler --bemerkung "warum")
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
                   [--zurueck] [--kommentar KOMMENTAR] [--kurz]
                   [--federfuehrend FEDERFUEHREND] [--pool] [--von VON]
                   [--projekt PROJEKT]
                   {neu,aendern,liste,zeige,start,blockiert,wartet,fertig,verwerfen,parken,aktiv,keine_prio,pool,kriterium,plan,planfrei,nachtrag}
                   [id] [nr]

positional arguments:
  {neu,aendern,liste,zeige,start,blockiert,wartet,fertig,verwerfen,parken,aktiv,keine_prio,pool,kriterium,plan,planfrei,nachtrag}
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
                        F12,A120,L7,CC2,Entwickler,Monitor:<was> (Pflicht;
                        erledigt sich von selbst und weckt dich)
  --erledigt ERLEDIGT   wartet/blockiert: diese Gründe von Hand abhaken, z. B.
                        F12 (allein: Status bleibt)
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
  --kurz                zeige: nur Status, Agent, Titel und Wartegründe
  --federfuehrend FEDERFUEHREND
                        aendern: wer diese Aufgabe führt (Lead/Entwickler;
                        leer = weg)
  --pool                neu: in den Pool (noch in keiner Arbeitsliste)
  --von VON
  --projekt PROJEKT
```

## thema
```
usage: amw thema [-h] [--pfleger PFLEGER] [--stil] [--kein-stil] [--text TEXT]
                 [--text-datei TEXT_DATEI] [--dokument DOKUMENT] [--loesen]
                 [--suche SUCHE] [--grenze GRENZE] [--von VON]
                 [--projekt PROJEKT]
                 [{liste,zeige,neu,einstellen,pflegen,bestaetigen,dokument}]
                 [name]

positional arguments:
  {liste,zeige,neu,einstellen,pflegen,bestaetigen,dokument}
  name                  TH-Nummer oder Name (eindeutiger Anfang reicht)

options:
  -h, --help            show this help message and exit
  --pfleger PFLEGER
  --stil                dieses Thema ist der Projekt-Stil (es gibt höchstens
                        einen)
  --kein-stil
  --text TEXT
  --text-datei TEXT_DATEI
  --dokument DOKUMENT
  --loesen
  --suche SUCHE
  --grenze GRENZE
  --von VON
  --projekt PROJEKT
```

## termin
```
usage: amw termin [-h] [--titel TITEL] [--art {test,frist,schirm,sonstig}]
                  [--am AM] [--dauer DAUER] [--woechentlich] [--bis BIS]
                  [--vorlauf VORLAUF] [--bogen BOGEN] [--notiz NOTIZ]
                  [--text TEXT] [--tage TAGE] [--von VON] [--projekt PROJEKT]
                  [{neu,liste,aendern,absagen,bereit,kurzliste}] [id]

positional arguments:
  {neu,liste,aendern,absagen,bereit,kurzliste}
  id

options:
  -h, --help            show this help message and exit
  --titel TITEL
  --art {test,frist,schirm,sonstig}
  --am AM               Ortszeit: JJJJ-MM-TT HH:MM oder TT.MM. HH:MM
                        (absagen/bereit: dieses Vorkommen)
  --dauer DAUER         Minuten
  --woechentlich
  --bis BIS             wöchentlich bis zu diesem Tag (JJJJ-MM-TT)
  --vorlauf VORLAUF     test: Testbuild fertig so viele Stunden vorher
                        (Vorgabe 4)
  --bogen BOGEN         Ampel: Prognose dieses Bogens gegen die Frist
  --notiz NOTIZ
  --text TEXT           bereit: was ist neu, was soll getestet werden
  --tage TAGE
  --von VON
  --projekt PROJEKT
```

## liste
```
usage: amw liste [-h] [--vor VOR] [--nach NACH] [--pos POS] [--oben] [--unten]
                 [--von VON] [--projekt PROJEKT]
                 [wer] [rest ...]

positional arguments:
  wer                Agent, pool, ordnen oder schieben
  rest               ordnen: Agent und Aufgaben-Nummern · schieben: die
                     Aufgabe

options:
  -h, --help         show this help message and exit
  --vor VOR
  --nach NACH
  --pos POS
  --oben
  --unten
  --von VON
  --projekt PROJEKT
```

## frage
```
usage: amw frage [-h] [--an {entwickler,tl,zustaendig}] [--kurz KURZ]
                 [--worum WORUM] [--option OPTION] [--empfehlung EMPFEHLUNG]
                 [--fundstellen FUNDSTELLEN] [--geprueft GEPRUEFT]
                 [--aufgabe AUFGABE] [--blockiert] [--text TEXT]
                 [--rueckfrage RUECKFRAGE] [--grund GRUND] [--geparkt]
                 [--anhang ANHANG] [--von VON] [--projekt PROJEKT]
                 {neu,liste,antworten,nachtrag,verlauf,parken,aufnehmen,weiterleiten}
                 [id]

positional arguments:
  {neu,liste,antworten,nachtrag,verlauf,parken,aufnehmen,weiterleiten}
  id

options:
  -h, --help            show this help message and exit
  --an {entwickler,tl,zustaendig}
                        zustaendig: an die Federführung der --aufgabe (sonst
                        Bogen, sonst Lead)
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
                 [--zieldatum ZIELDATUM] [--federfuehrend FEDERFUEHREND]
                 [--nr NR] [--grund GRUND] [--erzwingen] [--von VON]
                 [--projekt PROJEKT]
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
  --federfuehrend FEDERFUEHREND
                        aendern: wer den Bogen führt (Lead/Entwickler; leer =
                        weg)
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
usage: amw lauf [-h] [--warten] [--hoechstens HOECHSTENS] [--frist FRIST]
                [--dauer DAUER] [--beschreibung BESCHREIBUNG]
                [--rezept REZEPT] [--leicht] [--schirm] [--gpu]
                [--aufgabe AUFGABE] [--rc RC] [--ergebnis ERGEBNIS]
                [--abgebrochen] [--grenze GRENZE] [--von VON]
                [--projekt PROJEKT]
                {start,ende,liste,vorziehen,zeige,warte,ausfuehren} [id]

positional arguments:
  {start,ende,liste,vorziehen,zeige,warte,ausfuehren}
  id

options:
  -h, --help            show this help message and exit
  --warten              ist der Platz belegt: NUR einreihen (noch nicht
                        rechnen!) statt ablehnen; Freigabe weckt dich – oder
                        danach: amw lauf warte <nr>
  --hoechstens HOECHSTENS
                        warte: nach so vielen Minuten aufgeben (rc 3), Lauf
                        bleibt eingereiht · ausfuehren: dann aus der Schlange
                        nehmen (rc 200)
  --frist FRIST         ausfuehren: der Befehl darf so viele Minuten laufen,
                        dann Ende (rc 124)
  --dauer DAUER         erwartete Dauer in Minuten; doppelt so lang → Warnung
                        an den Lead
  --beschreibung BESCHREIBUNG
  --rezept REZEPT
  --leicht              kein schwerer Lauf (keine Speicher-Grenze)
  --schirm
  --gpu                 belegt die Grafikkarte: PC-weit nur ein GPU-Lauf zur
                        Zeit (auch KI-Aufträge; ein Lauf mit Fenster wartet
                        ebenfalls)
  --aufgabe AUFGABE
  --rc RC
  --ergebnis ERGEBNIS   ende: Ergebnis-Text · ausfuehren: Datei für die
                        Ausgabe des Befehls
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
                  [--schirm] [--speicher SPEICHER] [--leicht] [--gpu]
                  [--von VON] [--projekt PROJEKT]
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
  --gpu                 Läufe mit diesem Rezept belegen die Grafikkarte
  --von VON
  --projekt PROJEKT
```

## ki
```
usage: amw ki [-h] [--art ART] [--schnittstelle SCHNITTSTELLE]
              [--endpunkt ENDPUNKT] [--version VERSION] [--lizenz LIZENZ]
              [--ablage ABLAGE] [--start START] [--ordner ORDNER]
              [--vram VRAM] [--abschalten] [--einschalten] [--datei DATEI]
              [--sha256 SHA256] [--quelle QUELLE]
              [--kommerziell {ja,nein,registrierung,unklar}]
              [--nutzungsregeln] [--ohne-nutzungsregeln] [--sekunden SEKUNDEN]
              [--notiz NOTIZ] [--grund GRUND] [--beschreibung BESCHREIBUNG]
              [--wer WER] [--entziehen] [--modell MODELL] [--vorlage VORLAGE]
              [--prompt PROMPT] [--prompt-datei PROMPT_DATEI]
              [--negativ NEGATIV] [--seed SEED] [--anzahl ANZAHL]
              [--breite BREITE] [--hoehe HOEHE] [--bild BILD]
              [--parameter PARAMETER] [--titel TITEL] [--aufgabe AUFGABE]
              [--bogen BOGEN] [--frist FRIST] [--alle] [--von VON]
              [--projekt PROJEKT]
              [{liste,neu,aendern,modell,freigeben,sperren,vorlage,recht,auftrag,zeige,pruefen,nachweis}]
              [name] [teil]

positional arguments:
  {liste,neu,aendern,modell,freigeben,sperren,vorlage,recht,auftrag,zeige,pruefen,nachweis}
  name                  die KI (z. B. ollama, comfyui) · zeige: Lauf-Nummer
                        L812
  teil                  modell/freigeben/sperren: das Modell · vorlage: Name
                        der Vorlage

options:
  -h, --help            show this help message and exit
  --art ART             neu: sprache | bild | ton | 3d | video | sonstig
  --schnittstelle SCHNITTSTELLE
                        neu: ollama | comfyui | befehl (eigenes Programm ohne
                        Dienst-Schnittstelle, z. B. eine Ton-KI in Python:
                        eintragen, Recht und Modell-Freigabe wie sonst;
                        rechnen über amw lauf ausfuehren --gpu)
  --endpunkt ENDPUNKT   neu: nur lokal, z. B. http://127.0.0.1:8188 (Vorgabe
                        je Schnittstelle)
  --version VERSION
  --lizenz LIZENZ
  --ablage ABLAGE       neu: Ordner der Installation/Modelle
  --start START         neu/aendern: Startbefehl ohne Fenster (der Dienst
                        startet die KI, wenn sie nicht antwortet)
  --ordner ORDNER       neu/aendern: Arbeitsordner für den Startbefehl
  --vram VRAM           GB Grafikspeicher (Richtwert/Probe)
  --abschalten          aendern: KI nicht mehr beauftragen
  --einschalten
  --datei DATEI         modell: Dateiname wie in der Vorlage · vorlage: API-
                        JSON (ComfyUI: Export (API))
  --sha256 SHA256
  --quelle QUELLE       modell: URL
  --kommerziell {ja,nein,registrierung,unklar}
  --nutzungsregeln      modell: Lizenz mit Nutzungsregeln (z. B. Open
                        RAIL++-M) – frei gibt dann nur der Entwickler
  --ohne-nutzungsregeln
  --sekunden SEKUNDEN   modell: Probe, Sekunden je Auftrag
  --notiz NOTIZ
  --grund GRUND         freigeben/sperren: Begründung (sperren: Pflicht)
  --beschreibung BESCHREIBUNG
  --wer WER             recht: alle | rolle:<rolle> | <Kennung>
  --entziehen
  --modell MODELL
  --vorlage VORLAGE
  --prompt PROMPT
  --prompt-datei PROMPT_DATEI
  --negativ NEGATIV
  --seed SEED
  --anzahl ANZAHL
  --breite BREITE
  --hoehe HOEHE
  --bild BILD           auftrag: Eingabebild als Dokument, z. B. D96
  --parameter PARAMETER
                        auftrag: JSON, z. B. {"temperature": 0.2, "system":
                        "…"}
  --titel TITEL
  --aufgabe AUFGABE
  --bogen BOGEN
  --frist FRIST         auftrag: höchstens so viele Minuten rechnen (Vorgabe
                        60)
  --alle                nachweis: auch archivierte und gelöschte Dokumente
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
usage: amw beschluss [-h] [--text TEXT] [--text-datei TEXT_DATEI]
                     [--durch DURCH] [--stichwort STICHWORT] [--quelle QUELLE]
                     [--thema THEMA] [--neues-thema] [--zeit ZEIT]
                     [--wortlaut WORTLAUT] [--wortlaut-text WORTLAUT_TEXT]
                     [--wortlaut-kanal WORTLAUT_KANAL]
                     [--wortlaut-zeit WORTLAUT_ZEIT] [--aufgaben AUFGABEN]
                     [--ersetzt ERSETZT] [--von VON] [--projekt PROJEKT]
                     [{neu,ueberholt,unklar,gilt,thema}] [nr]

positional arguments:
  {neu,ueberholt,unklar,gilt,thema}
                        neu (Vorgabe) | ueberholt B12 [--durch B30] | unklar
                        B12 | gilt B12 | thema B12 --thema …
  nr

options:
  -h, --help            show this help message and exit
  --text TEXT
  --text-datei TEXT_DATEI
  --durch DURCH         ueberholt: ersetzt durch diesen Beschluss
  --stichwort STICHWORT
  --quelle QUELLE
  --thema THEMA         Pflicht, sobald es Themen gibt: TH-Nr. oder Name
                        (eindeutiger Anfang reicht)
  --neues-thema         --thema gibt es noch nicht: neu anlegen
  --zeit ZEIT
  --wortlaut WORTLAUT
  --wortlaut-text WORTLAUT_TEXT
                        Marcels Aussage wörtlich: wird im selben Zug als W…
                        erfasst und verknüpft (keine vorhergesagte W-Nummer)
  --wortlaut-kanal WORTLAUT_KANAL
  --wortlaut-zeit WORTLAUT_ZEIT
                        UTC der Aussage
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
                 [--text-datei TEXT_DATEI] [--suche SUCHE] [--von VON]
                 [--projekt PROJEKT]
                 {setzen,zeige,entfernen} [schluessel ...]

positional arguments:
  {setzen,zeige,entfernen}
  schluessel            entfernen: mehrere möglich

options:
  -h, --help            show this help message and exit
  --beschluss BESCHLUSS
                        entfernen ohne Lead-Rolle: Nummer eines geltenden
                        Beschlusses (z. B. B5)
  --text TEXT
  --text-datei TEXT_DATEI
  --suche SUCHE         zeige: nur Notizen, deren Schlüssel oder Text alle
                        Wörter enthält (z. B. CC5, A1162)
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

## abmelden
```
usage: amw abmelden [-h] [--von VON] [--projekt PROJEKT]

options:
  -h, --help         show this help message and exit
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
