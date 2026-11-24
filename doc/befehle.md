# Befehle

Erzeugt aus der Kommandozeile (`amw befehle > doc/befehle.md`). Jeder Befehl zeigt mit `--help` dasselbe.
Gemeinsam für alle: `--von <Name>` (wer handelt; sonst `AMW_AGENT`), `--projekt <Name>` (sonst das erste Projekt).

| Befehl | Zweck |
|---|---|
| [`init`](#init) | neue Datenbank anlegen |
| [`projekt`](#projekt) | Projekte: neu <name> ¦ liste ¦ ordner [<name>] – jedes Projekt ist für sich (eigene Agenten, Regeln, Daten); bequemer: Workbench › Projekt-Auswahl › Neues Projekt |
| [`agent`](#agent) | neu ¦ liste ¦ profil ¦ starten ¦ beenden ¦ startskript ¦ umbenennen ALT NEU ¦ lead NEU --co ALT --grund … ¦ entfernen ¦ wiederaufnehmen AGENT (der Mensch; wiederaufnehmen auch der Lead mit --wort W<nr>) |
| [`posten`](#posten) | Nachricht schicken: --an CC2 (oder alle, Entwickler) --art auftrag¦frage¦info¦… --kurz … |
| [`lesen`](#lesen) | ohne Nummer: offene Liste; mit Nummern: ganze Nachrichten (lesen 16707 16589) |
| [`erledigt`](#erledigt) | Nachrichten als erledigt markieren: amw erledigt 12 13 ¦ --info [--vor 04.11.] |
| [`aufgabe`](#aufgabe) | neu ¦ aendern N ¦ liste ¦ zeige N [--kurz] ¦ start ¦ fertig ¦ … ¦ kriterium N nr ¦ bereit N (Ergebnis steht, bei --fertig-wenn ja) ¦ abnehmen N [--zurueck --kommentar] ¦ plan N --text ¦ planfrei N [--zurueck --kommentar] ¦ nachtrag N --titel … (Folgearbeit zu einer fertigen Aufgabe) |
| [`paket`](#paket) | Arbeitspakete (Mischbetrieb): zeigen N ¦ zustand N <zustand> [--grund … --beleg …] ¦ liste [--zustand …] ¦ ergebnis N (--json - über stdin oder --status/--zusammenfassung/--frage/--frage-an/--grund/--hinweis; nur der zugeteilte Agent, Art agent/sitzung, Paket läuft) ¦ starten N (Lead/Mensch: ein startklares p-Paket jetzt starten – der Wächter entscheidet) ¦ mergeliste [--diff] (bereit zum Merge: diff --stat, Server-Code, Blick nötig) ¦ freigeben --alle ¦ freigeben N [--blick] (Prüfer der Pakete, Lead, Mensch) ¦ buendeln --alle ¦ buendeln N [--titel …] (freigegebene Pakete zu einem Release-Stand; Lead, Mensch) ¦ annehmen N --grund … (E4-Paket nach dem Lesen in die Merge-Liste; Lead, Mensch) ¦ holen [N] (interaktiv: nächste Aufgabe nehmen, Auftrag + Startwissen, Zweig/Arbeitsbaum) ¦ fertig N --sha … --punkte … (interaktiv: Tests-Hinweis, Prüfbitte, wartet auf den Prüfer) – Felder setzen: amw aufgabe neu¦aendern … --paket p … |
| [`thema`](#thema) | Design-Dokument je Thema: liste [--suche] ¦ zeige TH12 ¦ neu "Name" [--pfleger X] [--stil] ¦ einstellen TH12 --pfleger X ¦ --stil ¦ pflegen TH12 --text-datei … ¦ bestaetigen TH12 ¦ dokument TH12 --dokument D5 [--loesen] ¦ status (ein Status je Thema) ¦ freigeben TH12 ¦ zurueck TH12 --notiz … ¦ markieren¦entmarkieren TH12 (nur der Mensch; bei thema_freigabe=co+lead gibt freigeben von Co und Lead je ein Ja, B2913) ¦ nur_mensch TH12 (Pfleger, Lead, Mensch) ¦ nicht_nur_mensch TH12 (nur der Mensch) ¦ vermerk TH12 --nichts-zu-bauen --grund … [--aufheben] ¦ luecken (Thema ohne Paket, Paket ohne Thema) ¦ planen TH12 (Planer anstoßen, Lead/Co) ¦ plan TH12 (Entwurf zeigen) ¦ plan-ja TH12 [--datei geändert.json] (Lead) ¦ anhalten TH12 [--meilenstein N] (nicht begonnene Pakete eines geänderten Themas, Lead/Co) ¦ uebernehmen --datei konzept.md [--ebene 2] [--anlegen] (Konzept-Markdown aus dem Projektordner in Themen-Entwürfe, mit Zählprobe; ohne --anlegen nur Vorschau – Lead/Co) ¦ konzept-abschliessen (alle Themen frei: Konzept-Ja, startet die Grobplanung über alle Themen) ¦ grobplan [--fassung N] [--neu] (Fassungen und Entwurf zeigen, neu planen lassen) ¦ grobplan-ja [--fassung N] (legt die Meilensteine an – wer Ja sagt wie bei den Themen) – A2030 ¦ hinweis grob¦TH12 --text … [--zu TH3¦M2¦P4¦A123] (Ergänzung an den Planer) ¦ ueberarbeiten grob¦TH12 (Planer legt mit den offenen Hinweisen eine neue Fassung vor; Mensch, Lead, Co) – A2028 |
| [`termin`](#termin) | Terminplaner: neu --titel … --art test¦frist¦schirm¦sonstig --am "2026-11-06 18:00" [--woechentlich --bis 2026-12-31] [--vorlauf 4] [--bogen N] ¦ liste [--tage 21] ¦ aendern N ¦ absagen N [--am …] ¦ bereit N --text "was testen" ¦ kurzliste N (Planen: Lead/Entwickler) |
| [`liste`](#liste) | Arbeitsliste je Agent: liste [Agent¦pool] ¦ ordnen <Agent> A12 A15 … --grund … ¦ schieben A15 --vor A12 ¦ --nach ¦ --pos N ¦ --oben ¦ --unten [--grund …] (ordnen/schieben: Lead; die Reihenfolge rechnet sonst die AMW) |
| [`frage`](#frage) | Fragen an den Entwickler oder Lead: neu ¦ liste [--geparkt] ¦ antworten ¦ nachtrag ¦ verlauf ¦ parken N [--grund] ¦ aufnehmen N ¦ weiterleiten N [--text] (Lead → Entwickler) |
| [`pause`](#pause) | Pause für alles (A2042): an [--bis HH:MM¦2h¦90min] [--grund …] ¦ aus ¦ zeige (Rückmeldung je Agent) |
| [`halt`](#halt) | alle oder einen Agenten anhalten |
| [`weiter`](#weiter) | Halt aufheben |
| [`taetigkeit`](#taetigkeit) | was ich gerade tue (zeigt die Workbench), z. B. taetigkeit "A12 Login-Formular" |
| [`waechter`](#waechter) | Wächter für p-Pakete: pruefen A ¦ protokoll [A] ¦ reihenfolge ¦ zustand ¦ wartung an¦aus ¦ weiter |
| [`claude`](#claude) | Claude-Code-Versionen der Arbeiter: status (installiert, geprüft, Proben) ¦ freigeben X.Y.Z --grund (Lead oder Mensch, nicht aus einer Agenten-Sitzung) – eine neue Version prüft die AMW selbst (A1906) |
| [`platz`](#platz) | Arbeitsplätze für kopflose Arbeiter (claude -p): liste ¦ vorbereiten N ¦ zuruecksetzen N ¦ aufraeumen ¦ notbremse N (nur der Mensch: Arbeiter samt Kindern beenden) – nichts wird gelöscht: Reste ins Archiv, fertige Pakete nach _loeschen |
| [`sicherung`](#sicherung) | Tägliche Sicherung aller Zweige und Tags an sicherung_ziel (A1929): zeigen ¦ jetzt (Lead oder Mensch) – ohne --force, nie löschen, keine Zugangsdaten |
| [`empfehlung`](#empfehlung) | Eignungstabelle (A1930, TH159): tabelle – je Zelle und Modell/Effort Anzahl, Anteil ohne Nacharbeit, Median Kosten und Dauer; was die Empfehlung nimmt (nur lesen) |
| [`anbieter`](#anbieter) | Anbieter je Projekt (A1931, TH159): liste ¦ freigeben NAME --url https://… --schluessel-datei <Pfad> --modelle a,b [--lokal] ¦ entfernen NAME – freigeben/entfernen nur der Mensch im eigenen Terminal; nur der Pfad der Schlüsseldatei wird gespeichert, nie der Schlüssel |
| [`pc`](#pc) | Disponent über Projekte (A1925): zeigen (Rangfolge, p-Arbeiter, Kosten je Projekt diese Woche) ¦ einstellen projekt_rang=A,B,C (nur der Mensch) ¦ plaetze_pc=N ¦ limit_halt=P (Lead oder Mensch) |
| [`messung`](#messung) | Wartezeit und Kosten je Aufgabe (Liegezeit, aktiv, wartet nach Grund, $, Lücken) – nur lesen |
| [`skills`](#skills) | Anleitungen als Claude-Code-Skills: bauen (aus doc nach .claude/skills, A1956) |
| [`kosten`](#kosten) | Kosten eines Laufs außerhalb der Sitzungs-Zähler einer Aufgabe zuordnen (z. B. claude -p) |
| [`mcp`](#mcp) | Connector für Chat-Leads: schluessel (neu erzeugen – nur der Mensch, einmal sichtbar) ¦ eintrag (Zeile für claude_desktop_config.json) |
| [`takt`](#takt) | ein Durchgang für Leads: Postfach mit Text, Prüfbitten, Fragen, Antworten des Menschen, Läufe, Lead-Runde, Auslieferungen – knapp, je Punkt eine Zeile |
| [`kontext`](#kontext) | Startinformationen für einen Agenten |
| [`runde`](#runde) | Lead-Runde: Kanal nur zwischen den Leads aller Projekte – nur Information, nie Befehle (runde schreiben --kurz … [--an Projekt] · runde lesen [--neu]) |
| [`regeln`](#regeln) | alle geltenden Regeln (Arbeits- und Projektregeln) – oder eine ganz: amw regeln KR3 |
| [`verbrauch`](#verbrauch) | Verbrauch nach Anlass (Pareto): wofür die Agenten des Projekts ihr Geld ausgeben |
| [`suche`](#suche) | Volltext über Aufgaben, Beschlüsse, Fragen, Deine Worte, Nachrichten, Dokumente: amw suche Modem |
| [`zeige`](#zeige) | Einträge ganz lesen: amw zeige B5 F12 A120 W3 16000 D5 KR3 PR4 (Nachricht ohne #: in der Shell beginnt mit # ein Kommentar) |
| [`leitbild`](#leitbild) | Projektziel, Kennzahlen, Nicht-Ziele, Prinzipien, Definition of Done: zeigen ¦ setzen |
| [`bogen`](#bogen) | Meilensteine: liste ¦ neu ¦ zeigen N ¦ aendern N ¦ status N aktiv¦fertig¦geplant¦verworfen ¦ starten N (Jetzt starten: an den Disponenten) ¦ reihenfolge [N] (berechnet, kritischer Pfad) ¦ abnehmen N (nur der Mensch: fertigen Meilenstein abnehmen, danach veröffentlicht die AMW) |
| [`spec`](#spec) | Spezifikation je Meilenstein: zeigen N [teil] ¦ schreiben N teil --text/--datei ¦ vorlegen N teil ¦ frei N teil ¦ zurueck N teil --kommentar  (teil: anforderungen ¦ entwurf ¦ schritte) |
| [`schritt`](#schritt) | naechster [--nehmen]: nächster bereiter Schritt (aktiver Meilenstein, ohne offene Vorgänger) |
| [`risiko`](#risiko) | liste ¦ neu --titel … ¦ setzen N --status … |
| [`rueckblick`](#rueckblick) | Rückblick je Meilenstein: amw rueckblick <bogen> [--gut … --schlecht … --massnahme … --gelernt …] ¦ --uebernehmen <nr> --als aufgabe¦beschluss |
| [`verlauf`](#verlauf) | was passiert ist: amw verlauf [--stunden 24] [--agent CC1] [--art erledigt --art pruefung] [--zusammenfassung] |
| [`plan`](#plan) | pruefen (Lücken mit Bedeutung und Abhilfe) ¦ akzeptieren <schlüssel> --grund … ¦ wieder <schlüssel> ¦ prognose (P50/P85 je Schritt und Meilenstein) ¦ status (Ampel je Dimension) |
| [`lauf`](#lauf) | Rechen-Läufe: start [--warten] prüft Halt, Bildschirm, Speicher je Lauf, zwei Spuren (Grafikkarte/Bildschirm: einer zur Zeit; schwere ohne Fenster: parallel bis cpu_laeufe, je Agent einer), Warteschlange · warte <nr> blockiert, bis er dran ist · zeige <nr> mit Wartegrund · ausfuehren --beschreibung … [--schirm] [--ergebnis datei] -- <befehl …> (einreihen, warten, starten, rc durchreichen, Ende melden; bei Bildschirm zu den eigenen Befehl beenden) |
| [`benutzer`](#benutzer) | Benutzer der Online-Seite (nur der Mensch): neu NAME --rolle … [--projekte A,B] ¦ liste ¦ aendern NAME ¦ sperren NAME ¦ entsperren NAME |
| [`rechner`](#rechner) | Der Rechner auf einen Blick: Arbeitsspeicher, was außerhalb der Warteschlange Speicher belegt, freier Platz je Laufwerk, Aufräumvorschläge für alte Sicherungen (nur Anzeige) |
| [`schirm`](#schirm) | Bildschirm-Schalter: zeige ¦ frei --grund … [--bis HH:MM] (Entwickler/Lead; schon frei: ändert nur --bis, ohne --bis = ohne Ende) ¦ zu [--grund …] (alle) |
| [`server`](#server) | Projekt-Server überwachen: anmelden ¦ abmelden ¦ liste ¦ pruefen |
| [`pruefung`](#pruefung) | Prüfbitte je Stand (SHA), Ergebnis grün/rot; zuruecknehmen N --grund … (ein GRÜN widerrufen: Prüfer, Lead, Mensch); stil N (Stil-Prüfung der Bilder nach dem Stil-Thema neu anstoßen: Prüfer, Lead, Mensch) |
| [`freigabe`](#freigabe) | Merge-OK (Lead/Entwickler oder der Prüfer der jüngsten grünen Prüfung): freigabe merge A<nr> [--zweig z] [--zurueck] – Abnahme-Kette: nach grüner Prüfung geht die Merge-Bitte von selbst an den Merge-Dienst |
| [`hinweis`](#hinweis) | Anweisung an einen Agenten oder alle (z. B. „keine Rechen-Jobs“) |
| [`rezept`](#rezept) | Lauf-Rezepte als Daten |
| [`ki`](#ki) | Lokale KIs (PC-weit): liste ¦ neu¦aendern <ki> (nur am PC) ¦ modell <ki> <name> ¦ freigeben¦sperren <ki> <modell> ¦ vorlage <ki> <name> --datei ¦ recht <ki> --wer ¦ auftrag <ki> --prompt … ¦ zeige L<nr> ¦ pruefen ¦ nachweis ¦ vermerk D<nr> --art … ¦ fenster |
| [`wortlaut`](#wortlaut) | Aussage des Entwicklers wörtlich erfassen |
| [`beschluss`](#beschluss) | Beschluss anlegen (optional einen alten ersetzen) |
| [`regel`](#regel) | Regel anlegen/ändern – nur mit Beschluss |
| [`dokument`](#dokument) | Ergebnisse ablegen und finden: ablegen <datei> ¦ version <nr> <datei> ¦ liste ¦ zeigen <nr> ¦ kommentar¦ueberarbeiten <nr> --text … ¦ zuordnen <nr> ¦ archivieren¦wiederherstellen <nr> ¦ online¦offline <nr> ¦ loeschen <nr> --ja ¦ einsammeln <ordner> [--melden] ¦ einsammeln --uebernehmen --frage <nr> |
| [`notiz`](#notiz) | gepflegte Notizen (Schlüssel/Wert) |
| [`dienst`](#dienst) | Dienst als geplante Windows-Aufgabe: einrichten ¦ entfernen ¦ status ¦ neustart ¦ vordergrund (ohne Aufgabe in diesem Fenster, zum Ausprobieren) |
| [`web`](#web) | Online-Teil: einrichten (Turso-Zugang, einmal) ¦ status ¦ einmal (Synchronisierung) ¦ zweitfaktor-neu ¦ bauen ¦ schema ¦ sso [--aussteller URL --client-id ID --an¦--aus] (Firmen-Anmeldung; Geheimnis nur auf der Online-Seite) ¦ paket --seite https://… --speicher https://… [--admin NAME] [--ca firma.pem] [--ziel datei.zip] (eigener Server im Firmennetz: ZIP für den Webserver) |
| [`speicher`](#speicher) | Eigener Online-Speicher (libSQL-Server im Firmennetz): schluessel --url https://… [--ca firma.pem] [--ordner …] [--ersetzen] – Schlüsselpaar und Token erzeugen, Zugang am PC eintragen |
| [`anmelden`](#anmelden) | laufende Sitzung beim Dienst anmelden (ohne Neustart) |
| [`abmelden`](#abmelden) | Sitzung ruht: nicht mehr benachrichtigen, nicht automatisch neu starten (bis anmelden) |
| [`einrichten`](#einrichten) | ohne Angabe: geführte Einrichtung (fragt nach) ¦ schnell --projekt-name … (ohne Fragen) ¦ agenten-ordner <pfad> (Hooks, Statusline-Anbindung, Sperren) ¦ betriebsart [pc¦server¦cloud] ¦ verbindungen [--pruefen] (jede Adresse, zu der die AMW eine Verbindung aufbaut) |
| [`regelwerk`](#regelwerk) | Grund-Regelwerk im bestehenden Projekt: abgleich [--ablegen] ¦ uebernehmen G7 [--text …] |
| [`befehle`](#befehle) | Befehlsreferenz als Markdown (für doc/befehle.md) |
| [`sichern`](#sichern) | Sicherung der Datenbank (vollständige Kopie, auch während des Betriebs); mit --projekt <name> nur dieses Projekt als eigene Datenbank (z. B. zum Umziehen auf einen anderen Rechner) |
| [`push`](#push) | Benachrichtigungen aufs Handy: status ¦ probe ¦ an ¦ aus ¦ ntfy ¦ pushover ¦ telegram ¦ ruhe 22:00-07:00¦aus ¦ link URL ¦ ereignis art=an¦aus |
| [`hook`](#hook) | zeigt die Einstellungen für einen Agenten-Projektordner (schreibt nichts) |
| [`release`](#release) | Versionshinweise: je Merge eine Zeile, Version fasst zusammen |

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
                   {neu,liste,ordner,einstellen,schalter} [name] [wert]

positional arguments:
  {neu,liste,ordner,einstellen,schalter}
  name                  einstellen: schluessel=wert · schalter: Projektname
  wert                  schalter: probe (Lead oder Mensch) | an | aus (nur der
                        Mensch im eigenen Terminal)

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
usage: amw agent [-h] [--co CO] [--grund GRUND] [--ordner ORDNER]
                 [--zusatz ZUSATZ] [--denkstufe DENKSTUFE] [--modell MODELL]
                 [--startsatz STARTSATZ] [--rechte RECHTE] [--wort WORT]
                 [--fernsteuerung] [--keine-fernsteuerung] [--neustart]
                 [--kein-neustart] [--neu] [--datei DATEI] [--alle]
                 [--abstand ABSTAND] [--rolle ROLLE] [--fachgebiet FACHGEBIET]
                 [--arbeitsweise {terminal,desktop,chat}]
                 [--zustaendig ZUSTAENDIG] [--nicht NICHT]
                 [--startbefehl STARTBEFEHL] [--ohne-rund] [--von VON]
                 [--projekt PROJEKT]
                 {neu,liste,profil,starten,beenden,startskript,umbenennen,lead,entfernen,wiederaufnehmen}
                 [kennung] [neu]

positional arguments:
  {neu,liste,profil,starten,beenden,startskript,umbenennen,lead,entfernen,wiederaufnehmen}
  kennung
  neu                   umbenennen: der neue Name (der alte bleibt als Alias
                        gültig)

options:
  -h, --help            show this help message and exit
  --co CO               lead: der bisherige Lead wird Co-Entwickler (Wortlaut,
                        Beschlüsse, Fragen an den Menschen, Dokumente; behält
                        den Dateiaustausch); ist NEU schon Lead, setzt --co
                        nur den Co-Entwickler
  --grund GRUND         lead: warum (z. B. der Beschluss)
  --ordner ORDNER       profil: Arbeitsordner
  --zusatz ZUSATZ       profil: weitere Ordner, mit ; getrennt
  --denkstufe DENKSTUFE
                        profil: low | medium | high | xhigh | max
  --modell MODELL       profil: z. B. opus, sonnet (leer = Vorgabe)
  --startsatz STARTSATZ
                        profil: erste Anweisung einer neuen Sitzung
  --rechte RECHTE       profil: vorgabe | auto | umgehen
  --wort WORT           profil, wiederaufnehmen, lead: auf ein Wort des
                        Entwicklers (W<nr>, höchstens 24 h alt) – darf der
                        Lead, auch über den Dateiaustausch
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
  --rolle ROLLE         neu/profil: lead = führt das Projekt, leer = führt
                        nicht (ein anderes Wort gilt als Fachgebiet)
  --fachgebiet FACHGEBIET
                        neu/profil: z. B. Code, Grafik, Prüfen (bis 40
                        Zeichen; leer = keines)
  --arbeitsweise {terminal,desktop,chat}
                        neu/profil: Claude Code im Terminal (startet die AMW)
                        | Claude Code in der Desktop-App | Chat über den
                        Dateiaustausch
  --zustaendig ZUSTAENDIG
                        neu/profil: wofür der Agent zuständig ist
  --nicht NICHT         neu/profil: was der Agent nicht anfasst
  --startbefehl STARTBEFEHL
  --ohne-rund           bekommt keine Rundschreiben
  --von VON
  --projekt PROJEKT
```

## posten
```
usage: amw posten [-h] --an AN --art ART --kurz KURZ [--text TEXT]
                  [--text-datei TEXT_DATEI] [--antwort-auf ANTWORT_AUF]
                  [--aufgabe AUFGABE] [--bis BIS] [--bezug BEZUG]
                  [--neuer-faden] [--von VON] [--projekt PROJEKT]

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
  --bezug BEZUG         worum es geht: A<nr> Aufgabe, F<nr> Frage, D<nr>
                        Dokument, M<nr> Meilenstein, P<nr> Prüfung, L<nr>
                        Lauf, T<nr> Thema, B<nr> Beschluss, @Kennung Agent;
                        ohne: aus --aufgabe oder geerbt von der Nachricht in
                        --antwort-auf
  --neuer-faden         an den Menschen: nicht von selbst an seine letzte
                        Nachricht an dich hängen (sonst tut die AMW das, wenn
                        sie höchstens 2 Tage alt ist)
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
                   [--ohne-bogen] [--kriterium KRITERIUM]
                   [--fertig-wenn FERTIG_WENN] [--quelle QUELLE]
                   [--schaetzung SCHAETZUNG] [--komplexitaet KOMPLEXITAET]
                   [--groesse {S,M,L,XL}]
                   [--art {text,mechanisch,fehlersuche,oberflaeche,sicherheit,konzept}]
                   [--nach NACH] [--verantwortlich VERANTWORTLICH]
                   [--pruefbefehl PRUEFBEFEHL] [--dateien DATEIEN]
                   [--anforderungen ANFORDERUNGEN]
                   [--zusammenfassung ZUSAMMENFASSUNG]
                   [--ohne-vorgaenger OHNE_VORGAENGER] [--thema THEMA]
                   [--ohne-thema OHNE_THEMA]
                   [--ohne-thema-grund OHNE_THEMA_GRUND] [--text TEXT]
                   [--nein] [--zurueck] [--kommentar KOMMENTAR] [--kurz]
                   [--federfuehrend FEDERFUEHREND] [--pool] [--grund GRUND]
                   [--hinweis HINWEIS]
                   [--gruppe {neu,verbessert,behoben,intern}] [--sofort]
                   [--paket {agent,sitzung,p}] [--gewicht {leicht,schwer}]
                   [--ressourcen RESSOURCEN] [--modell MODELL]
                   [--effort {low,medium,high}]
                   [--pakettyp {normal,test-schreiben,test-ergaenzen}]
                   [--nie-gleichzeitig NIE_GLEICHZEITIG]
                   [--gleiche-ressource GLEICHE_RESSOURCE] [--von VON]
                   [--projekt PROJEKT]
                   {neu,aendern,liste,zeige,start,blockiert,wartet,fertig,verwerfen,parken,aktiv,keine_prio,pool,kriterium,plan,planfrei,nachtrag,dazwischen,bereit,abnehmen,hinweis}
                   [id] [nr]

positional arguments:
  {neu,aendern,liste,zeige,start,blockiert,wartet,fertig,verwerfen,parken,aktiv,keine_prio,pool,kriterium,plan,planfrei,nachtrag,dazwischen,bereit,abnehmen,hinweis}
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
                        erledigt sich von selbst und benachrichtigt dich).
                        Fügt Gründe HINZU – alte bleiben offen, bis sie sich
                        erledigen oder du sie mit --erledigt abhakst
  --erledigt ERLEDIGT   wartet/blockiert: diese Gründe von Hand abhaken, z. B.
                        F12 oder CCamw (allein: Status bleibt; mit --auf:
                        alten Grund abhaken und neuen setzen in einem Schritt)
  --bemerkung BEMERKUNG
  --alle
  --bogen BOGEN         Planung: gehört zu Meilenstein N (neu: Pflicht,
                        solange es einen aktiven oder geplanten gibt)
  --ohne-bogen          neu: Lead – bewusst ohne Meilenstein; steht dann in
                        der Planung unter „Ohne Meilenstein“
  --kriterium KRITERIUM
                        Planung: Abnahmekriterium, mehrfach (ersetzt die
                        Liste)
  --fertig-wenn FERTIG_WENN
                        neu/aendern (A1938): Fertig-Quelle – commit | thema
                        TH<n> | frist <Tage> nach <Version> | ja; die AMW
                        schließt die Aufgabe selbst
  --quelle QUELLE       kriterium N nr (A1938): Prüfquelle – lauf <Befehl> |
                        pruefung | thema TH<n> | tests <N>; leer entfernt sie;
                        die AMW hakt selbst ab
  --schaetzung SCHAETZUNG
                        Planung: Stunden
  --komplexitaet KOMPLEXITAET
                        Planung: 1–10; ab 7 braucht der Schritt einen
                        freigegebenen Plan
  --groesse {S,M,L,XL}  Größe (für die Empfehlung Modell/Denkaufwand): S klein
                        … XL sehr groß
  --art {text,mechanisch,fehlersuche,oberflaeche,sicherheit,konzept}
                        Art (für die Empfehlung): text = Text/Doku, mechanisch
                        = mechanische Änderung, fehlersuche, oberflaeche,
                        sicherheit, konzept = Architektur/Konzept
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
                        fertig: Pflicht für Schritte in einem Meilenstein;
                        aendern: nachtragen
  --ohne-vorgaenger OHNE_VORGAENGER
                        aendern: diese Vorgänger lösen, z. B. 115
  --thema THEMA         neu/aendern: verweist auf diese Themen, z. B. TH3,TH5
                        – ändert sich ein freigegebenes Thema, meldet die AMW
                        die Aufgabe zum Prüfen (A1915)
  --ohne-thema OHNE_THEMA
                        aendern: diese Themen-Verweise lösen, z. B. TH3
  --ohne-thema-grund OHNE_THEMA_GRUND
                        neu: bewusst ohne Thema (interne Pflege, z. B.
                        Aufräumen, Fehlerbehebung) – mit Grund (A1947)
  --text TEXT           plan: der Plan
  --nein                kriterium: wieder als offen markieren
  --zurueck             planfrei, abnehmen: zurückweisen (mit --kommentar)
  --kommentar KOMMENTAR
  --kurz                zeige: nur Status, Agent, Titel und Wartegründe
  --federfuehrend FEDERFUEHREND
                        aendern: wer diese Aufgabe führt (Lead/Entwickler;
                        leer = weg)
  --pool                neu: in den Eingang (noch in keiner Arbeitsliste)
  --grund GRUND         dazwischen: warum diese Aufgabe vor das laufende Stück
                        muss (Pflicht)
  --hinweis HINWEIS     fertig|hinweis: ein Satz für die Versionshinweise, in
                        der Sprache der Nutzer (ohne: die AMW leitet ihn ab –
                        aus Commit-Betreff, Thema oder Titel)
  --gruppe {neu,verbessert,behoben,intern}
                        fertig|hinweis: Gruppe in den Versionshinweisen (ohne:
                        die AMW leitet sie ab – Art fehlersuche = behoben,
                        sonst nach Stichworten; intern = nie in den
                        Versionshinweisen)
  --sofort              neu: direkt hinter das laufende Stück des Agenten
                        einplanen statt in den Eingang (ohne laufendes Stück:
                        wie bisher in die Liste)
  --paket {agent,sitzung,p}
                        Paket: wer ausführt – agent (interaktiver Agent,
                        Vorgabe), sitzung (neue Sitzung), p (frischer claude
                        -p-Arbeiter)
  --gewicht {leicht,schwer}
                        Paket: leicht (Vorgabe) oder schwer
  --ressourcen RESSOURCEN
                        Paket: gpu,bildschirm (Vorgabe: keine)
  --modell MODELL       Paket: wie claude --model (Vorgabe claude-opus-5-5);
                        bei einem freigegebenen Anbieter anbieter@modell, z.
                        B. minimax@MiniMax-M2 (A1931)
  --effort {low,medium,high}
                        Paket: wie claude --effort (Vorgabe high)
  --pakettyp {normal,test-schreiben,test-ergaenzen}
                        Paket: normal (Vorgabe), test-schreiben (Test +
                        Änderung, rot gegen alt) oder test-ergaenzen (nur
                        Tests für bestehenden Code, grün; Lead liest)
  --nie-gleichzeitig NIE_GLEICHZEITIG
                        Paket: nie gleichzeitig mit diesen Aufgaben, z. B.
                        A12,A13
  --gleiche-ressource GLEICHE_RESSOURCE
                        Paket: Name einer gemeinsamen Ressource – Pakete mit
                        demselben Namen laufen nacheinander
  --von VON
  --projekt PROJEKT
```

## paket
```
usage: amw paket [-h] [--grund GRUND] [--beleg BELEG] [--nur NUR] [--diff]
                 [--alle] [--blick] [--titel TITEL] [--gesamtlauf ZWEIG]
                 [--json JSON] [--status {erledigt,blockiert,aufgegeben}]
                 [--zusammenfassung ZUSAMMENFASSUNG] [--frage FRAGE]
                 [--frage-an {lead,mensch}] [--hinweis HINWEIS]
                 [--zweig ZWEIG] [--sha SHA] [--punkte PUNKTE]
                 [--pruefer PRUEFER] [--gruppe {neu,verbessert,behoben}]
                 [--ohne-bild OHNE_BILD] [--von VON] [--projekt PROJEKT]
                 {zeigen,zustand,liste,ergebnis,starten,mergeliste,freigeben,buendeln,annehmen,holen,fertig}
                 [id] [zustand]

positional arguments:
  {zeigen,zustand,liste,ergebnis,starten,mergeliste,freigeben,buendeln,annehmen,holen,fertig}
  id
  zustand               zustand: entwurf, startklar, laeuft, abgegeben,
                        abnahme, merge_reihe, gemergt, fertig, blockiert,
                        unklar, wartet_interaktiv, abgebrochen,
                        zurueckgestellt

options:
  -h, --help            show this help message and exit
  --grund GRUND         zustand: warum (steht im Planungs-Protokoll) ·
                        ergebnis aufgegeben: warum es nicht geht · annehmen:
                        was du gelesen hast und warum es passt
  --beleg BELEG         zustand fertig: Commit
  --nur NUR             liste: nur diese Zustände, z. B. startklar,laeuft
  --diff                mergeliste: auch den gekürzten Diff zeigen
  --alle                freigeben: alle Pakete, die bereit zum Merge sind
                        (außer denen, die einen Blick brauchen)
  --blick               freigeben N: du hast in den Diff gesehen (nötig laut
                        merge_blick)
  --titel TITEL         buendeln: Titel des Abschnitts in den
                        Versionshinweisen (sonst aus dem Hinweis bzw.
                        „Gebündelte Pakete“)
  --gesamtlauf ZWEIG    buendeln: den Gesamtlauf eines vorhandenen Bündels
                        (buendel-X.Y.Z) neu anstoßen
  --json JSON           ergebnis: „-“ = die Meldung als JSON von stdin
  --status {erledigt,blockiert,aufgegeben}
                        ergebnis: genau ein Status
  --zusammenfassung ZUSAMMENFASSUNG
                        ergebnis: ein Satz, was gemacht wurde
  --frage FRAGE         ergebnis blockiert: die eine Frage, die dich stoppt
  --frage-an {lead,mensch}
                        ergebnis blockiert: wer antworten soll (Vorgabe lead)
  --hinweis HINWEIS     ergebnis: optional, geht nur an den Lead
  --zweig ZWEIG         ergebnis erledigt bei einem Paket mit Abnahme-Befehl:
                        dein Zweig (Pflicht) – die AMW prüft ihn und stellt
                        die Prüfbitte mit ihrem Befund · fertig: dein Zweig
                        (Vorgabe a<N>)
  --sha SHA             fertig: der genaue Stand (Commit) für die Prüfbitte
  --punkte PUNKTE       fertig: was du geprüft hast (Proben, Läufe) – steht in
                        der Prüfbitte
  --pruefer PRUEFER     fertig: wer prüft (Vorgabe: Prüfer der Aufgabe, sonst
                        der Lead)
  --gruppe {neu,verbessert,behoben}
                        fertig: Gruppe für die Versionshinweise
  --ohne-bild OHNE_BILD
                        fertig: sichtbare Änderung ausnahmsweise ohne Bild –
                        mit Grund
  --von VON
  --projekt PROJEKT
```

## thema
```
usage: amw thema [-h] [--zu ZU] [--fassung FASSUNG] [--neu] [--ebene 1-6]
                 [--anlegen] [--meilenstein MEILENSTEIN] [--nichts-zu-bauen]
                 [--aufheben] [--bestaetigen] [--grund GRUND] [--datei DATEI]
                 [--notiz NOTIZ] [--pfleger PFLEGER] [--stil] [--kein-stil]
                 [--text TEXT] [--text-datei TEXT_DATEI] [--dokument DOKUMENT]
                 [--loesen] [--suche SUCHE] [--grenze GRENZE] [--von VON]
                 [--projekt PROJEKT]
                 [{liste,zeige,neu,einstellen,pflegen,bestaetigen,dokument,status,freigeben,zurueck,markieren,entmarkieren,nur_mensch,nicht_nur_mensch,vermerk,luecken,planen,plan,plan-ja,anhalten,uebernehmen,konzept-abschliessen,grobplan,grobplan-ja,hinweis,ueberarbeiten}]
                 [name]

positional arguments:
  {liste,zeige,neu,einstellen,pflegen,bestaetigen,dokument,status,freigeben,zurueck,markieren,entmarkieren,nur_mensch,nicht_nur_mensch,vermerk,luecken,planen,plan,plan-ja,anhalten,uebernehmen,konzept-abschliessen,grobplan,grobplan-ja,hinweis,ueberarbeiten}
  name                  TH-Nummer oder Name (eindeutiger Anfang reicht)

options:
  -h, --help            show this help message and exit
  --zu ZU               hinweis: die Karte – TH3, M2, P4 oder A123 (ohne: der
                        ganze Plan) – A2028
  --fassung FASSUNG     grobplan, grobplan-ja: diese Fassung des Grobplans
                        statt der neuesten – A2030
  --neu                 grobplan: den Grob-Planer neu planen lassen (neue
                        Fassung) – A2030
  --ebene 1-6           uebernehmen: welche Überschriften-Ebene zu Themen wird
                        (Vorgabe: die Gliederung unter dem Titel)
  --anlegen             uebernehmen: wirklich anlegen (ohne: nur Vorschau,
                        nichts geschrieben)
  --meilenstein MEILENSTEIN
                        anhalten: nur in diesem Meilenstein (Nummer) – K8
  --nichts-zu-bauen     vermerk: das Thema braucht kein Paket (mit --grund) –
                        A1947
  --aufheben            vermerk: den Vermerk „nichts zu bauen“ wieder aufheben
  --bestaetigen         vermerk: „nichts zu bauen“ bestätigen (Co-Entwickler
                        oder Mensch) – K7
  --grund GRUND
  --datei DATEI         plan-ja: geänderter Entwurf als JSON-Datei (gleiches
                        Schema, wird neu geprüft) – A1940; uebernehmen: die
                        Konzept-Datei (.md) im Projektordner – A1994
  --notiz NOTIZ         zurueck: was soll anders werden (Pflicht)
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
  --bogen BOGEN         Ampel: Prognose dieses Meilensteins gegen die Frist
  --notiz NOTIZ
  --text TEXT           bereit: was ist neu, was soll getestet werden
  --tage TAGE
  --von VON
  --projekt PROJEKT
```

## liste
```
usage: amw liste [-h] [--vor VOR] [--nach NACH] [--pos POS] [--oben] [--unten]
                 [--grund GRUND] [--von VON] [--projekt PROJEKT]
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
  --grund GRUND      ordnen/schieben (A1941): warum von Hand – sonst rechnet
                     die AMW die Reihenfolge
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
                 [--buendeln BUENDELN] [--anhang ANHANG] [--von VON]
                 [--projekt PROJEKT]
                 {neu,liste,zeige,antworten,nachtrag,verlauf,parken,aufnehmen,weiterleiten}
                 [id]

positional arguments:
  {neu,liste,zeige,antworten,nachtrag,verlauf,parken,aufnehmen,weiterleiten}
  id

options:
  -h, --help            show this help message and exit
  --an {entwickler,tl,zustaendig}
                        zustaendig: an die Federführung der --aufgabe (sonst
                        Meilenstein, sonst Lead)
  --kurz KURZ
  --worum WORUM
  --option OPTION       neu: 'A=Text' (mehrfach); antworten: Kürzel der Option
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
  --buendeln BUENDELN   neu (Lead): diese offenen Fragen der Agenten in eine
                        neue Frage an den Entwickler bündeln, z. B. F12,F13 –
                        die Antwort gilt auch für sie (A2021)
  --anhang ANHANG       neu: Bild/Mockup zu einer Option, 'A=datei.png' oder
                        'A=D12' (mehrfach) – erscheint als Variante zum
                        Anklicken, auch online
  --von VON
  --projekt PROJEKT
```

## pause
```
usage: amw pause [-h] [--bis BIS] [--grund GRUND] [--von VON]
                 [--projekt PROJEKT]
                 {an,aus,zeige}

positional arguments:
  {an,aus,zeige}

options:
  -h, --help         show this help message and exit
  --bis BIS          an: Ende – HH:MM (heute, sonst morgen), 2h oder 90min;
                     ohne: bis „amw pause aus“
  --grund GRUND
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

## waechter
```
usage: amw waechter [-h] [--grund GRUND] [--von VON] [--projekt PROJEKT]
                    {pruefen,protokoll,reihenfolge,zustand,wartung,weiter}
                    [nr]

positional arguments:
  {pruefen,protokoll,reihenfolge,zustand,wartung,weiter}
  nr                    Aufgabe (pruefen, protokoll) bzw. an|aus (wartung)

options:
  -h, --help            show this help message and exit
  --grund GRUND
  --von VON
  --projekt PROJEKT
```

## claude
```
usage: amw claude [-h] [--grund GRUND] [--von VON] [--projekt PROJEKT]
                  {status,freigeben} [version]

positional arguments:
  {status,freigeben}
  version             freigeben: die Version, z. B. 2.1.331

options:
  -h, --help          show this help message and exit
  --grund GRUND       freigeben: warum die Version trotz Probe in Ordnung ist
  --von VON
  --projekt PROJEKT
```

## platz
```
usage: amw platz [-h] [--aufgabe AUFGABE] [--zweig ZWEIG] [--von VON]
                 [--projekt PROJEKT]
                 {liste,vorbereiten,zuruecksetzen,aufraeumen,notbremse} [nr]

positional arguments:
  {liste,vorbereiten,zuruecksetzen,aufraeumen,notbremse}
  nr

options:
  -h, --help            show this help message and exit
  --aufgabe AUFGABE     Aufgabe des Pakets (Name des Archivs, damit aufraeumen
                        es nach Paketende verschiebt)
  --zweig ZWEIG         vorbereiten: Name des Zweigs ab main (Vorgabe platzN)
  --von VON
  --projekt PROJEKT
```

## sicherung
```
usage: amw sicherung [-h] [--von VON] [--projekt PROJEKT] [{zeigen,jetzt}]

positional arguments:
  {zeigen,jetzt}

options:
  -h, --help         show this help message and exit
  --von VON
  --projekt PROJEKT
```

## empfehlung
```
usage: amw empfehlung [-h] [--von VON] [--projekt PROJEKT] [{tabelle}]

positional arguments:
  {tabelle}

options:
  -h, --help         show this help message and exit
  --von VON
  --projekt PROJEKT
```

## anbieter
```
usage: amw anbieter [-h] [--url URL] [--schluessel-datei SCHLUESSEL_DATEI]
                    [--modelle MODELLE] [--lokal] [--von VON]
                    [--projekt PROJEKT]
                    [{liste,freigeben,entfernen}] [name]

positional arguments:
  {liste,freigeben,entfernen}
  name

options:
  -h, --help            show this help message and exit
  --url URL             Basis-URL der Anthropic-kompatiblen Schnittstelle
                        (https://…; lokal auch http://localhost:…)
  --schluessel-datei SCHLUESSEL_DATEI
                        absoluter Pfad zur Datei mit dem Schlüssel (außerhalb
                        jedes Repos)
  --modelle MODELLE     Modelle des Anbieters, mit Komma (das erste prüft die
                        Negativprobe)
  --lokal               lokales Modell (belegt die Grafikkarte)
  --von VON
  --projekt PROJEKT
```

## pc
```
usage: amw pc [-h] [--von VON] [--projekt PROJEKT]
              [{zeigen,einstellen}] [wert]

positional arguments:
  {zeigen,einstellen}
  wert                 schluessel=wert

options:
  -h, --help           show this help message and exit
  --von VON
  --projekt PROJEKT
```

## messung
```
usage: amw messung [-h] [--seit SEIT] [--agent AGENT] [--vergleich] [--hebel7]
                   [--basis] [--p] [--tage TAGE] [--gesamt] [--von VON]
                   [--projekt PROJEKT]
                   [nr]

positional arguments:
  nr                 eine Aufgabe (A12 oder 12); ohne: alle begonnenen

options:
  -h, --help         show this help message and exit
  --seit SEIT        nur Aufgaben, die ab dann noch liefen (17.11. oder ISO-
                     Zeit)
  --agent AGENT
  --vergleich        letzte 7 Tage gegen die 7 Tage davor (Mediane, D1258 v2
                     §8)
  --hebel7           Startkontext je Agent (Zeilen/Zeichen) und Kosten je
                     Paket (Median der letzten 10) – A1956, TH168 Hebel 7
  --basis            mit --hebel7: als Basis festhalten (Ereignis
                     basis_hebel7; Lead oder Mensch)
  --p                Anteil p an fertigen Paketen je Tag (Ziel ≥ 50 %) und
                     Kosten p gegen interaktiv (Median, Summe) – A2004
  --tage TAGE        mit --p: so viele Tage zurück (Vorgabe 7)
  --gesamt           Kosten des Projekts: bisher (gemessen, Fenster-Agenten
                     und Headless), noch (Schätzung offener Pakete) und gesamt
  --von VON
  --projekt PROJEKT
```

## skills
```
usage: amw skills [-h] [--ziel ZIEL] [--von VON] [--projekt PROJEKT] {bauen}

positional arguments:
  {bauen}

options:
  -h, --help         show this help message and exit
  --ziel ZIEL        anderer Ordner für .claude/skills (z. B. der Agenten-
                     Ordner eines anderen Projekts)
  --von VON
  --projekt PROJEKT
```

## kosten
```
usage: amw kosten [-h] --aufgabe AUFGABE
                  (--json JSON | --usd USD | --unbekannt) [--notiz NOTIZ]
                  [--von VON] [--projekt PROJEKT]
                  {erfassen}

positional arguments:
  {erfassen}

options:
  -h, --help         show this help message and exit
  --aufgabe AUFGABE
  --json JSON        Datei mit der Ausgabe von claude -p --output-format json
  --usd USD
  --unbekannt        Lauf ohne Ergebnis (abgebrochen) – als Lücke vermerken
  --notiz NOTIZ
  --von VON
  --projekt PROJEKT
```

## mcp
```
usage: amw mcp [-h] [--von VON] [--projekt PROJEKT] {schluessel,eintrag}

positional arguments:
  {schluessel,eintrag}

options:
  -h, --help            show this help message and exit
  --von VON
  --projekt PROJEKT
```

## takt
```
usage: amw takt [-h] [--seit SEIT] [--abhaken] [--grenze GRENZE] [--von VON]
                [--projekt PROJEKT]

options:
  -h, --help         show this help message and exit
  --seit SEIT        Antworten/Läufe/Auslieferungen seit (HH:MM oder Datum);
                     sonst seit dem letzten Takt
  --abhaken          gezeigte Infos und Meldungen gleich erledigen
  --grenze GRENZE    höchstens so viele Nachrichten (Vorgabe 30)
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

## runde
```
usage: amw runde [-h] [--kurz KURZ] [--text TEXT] [--text-datei TEXT_DATEI]
                 [--art {info,frage}] [--an AN] [--antwort-auf ANTWORT_AUF]
                 [--neu] [--von VON] [--projekt PROJEKT]
                 [{lesen,schreiben}]

positional arguments:
  {lesen,schreiben}

options:
  -h, --help            show this help message and exit
  --kurz KURZ
  --text TEXT
  --text-datei TEXT_DATEI
                        Text aus einer Datei (UTF-8)
  --art {info,frage}    nur info oder frage – keine Aufträge an andere
                        Projekte
  --an AN               direkte Anrede: Projekt, dessen Lead zusätzlich eine
                        Info ins Postfach bekommt (weckt nicht)
  --antwort-auf ANTWORT_AUF
                        Antwort auf Eintrag R<nr>
  --neu                 lesen: nur Ungelesenes
  --von VON
  --projekt PROJEKT
```

## regeln
```
usage: amw regeln [-h] [--von VON] [--projekt PROJEKT] [nr]

positional arguments:
  nr                 eine Regel: KR3, PR2 oder 3 (= KR3)

options:
  -h, --help         show this help message and exit
  --von VON
  --projekt PROJEKT
```

## verbrauch
```
usage: amw verbrauch [-h] [--tage TAGE] [--von VON] [--projekt PROJEKT]
                     {pareto}

positional arguments:
  {pareto}

options:
  -h, --help         show this help message and exit
  --tage TAGE        Zeitraum ab lokaler Mitternacht (Vorgabe 7)
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
                 [--nr NR] [--grund GRUND] [--erzwingen]
                 [--art {grob,plan,abschluss}] [--notiz NOTIZ]
                 [--hinweis HINWEIS] [--starten] [--von VON]
                 [--projekt PROJEKT]
                 {liste,neu,zeigen,aendern,status,abnehmen,freigeben,zurueck,bericht,tore,starten,reihenfolge,feinplanen,nacharbeit}
                 [id] [wert]

positional arguments:
  {liste,neu,zeigen,aendern,status,abnehmen,freigeben,zurueck,bericht,tore,starten,reihenfolge,feinplanen,nacharbeit}
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
                        aendern: wer den Meilenstein führt (Lead/Entwickler;
                        leer = weg)
  --nr NR               Reihenfolge
  --grund GRUND         nötig, wenn das Zieldatum nach der Baseline geändert
                        wird
  --erzwingen
  --art {grob,plan,abschluss}
                        freigeben/zurueck: Meilenstein (grob), sein Plan oder
                        sein Abschlussbericht – K6/K7
  --notiz NOTIZ         zurueck: was soll anders werden (Pflicht)
  --hinweis HINWEIS     feinplanen: Hinweis an den Feinplaner (was er anders
                        machen soll); nacharbeit: was fehlt (Pflicht)
  --starten             freigeben --art plan: Plan freigeben und den
                        Meilenstein gleich starten (ein Klick wie in der
                        Workbench)
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
                [--dauer DAUER] [--braucht-gb GB] [--braucht-vram-gb GB]
                [--braucht-platte-gb GB] [--beschreibung BESCHREIBUNG]
                [--rezept REZEPT] [--leicht] [--schwer] [--dauerlauf]
                [--schirm] [--gpu] [--aufgabe AUFGABE] [--rc RC]
                [--ergebnis ERGEBNIS] [--abgebrochen] [--grenze GRENZE]
                [--von VON] [--projekt PROJEKT]
                {start,ende,liste,vorziehen,zeige,warte,ausfuehren,fehlalarm}
                [id]

positional arguments:
  {start,ende,liste,vorziehen,zeige,warte,ausfuehren,fehlalarm}
  id

options:
  -h, --help            show this help message and exit
  --warten              ist der Platz belegt: NUR einreihen (noch nicht
                        rechnen!) statt ablehnen; Freigabe benachrichtigt dich
                        – oder danach: amw lauf warte <nr>
  --hoechstens HOECHSTENS
                        warte: nach so vielen Minuten aufgeben (rc 3), Lauf
                        bleibt eingereiht · ausfuehren: dann aus der Schlange
                        nehmen (rc 200)
  --frist FRIST         ausfuehren: der Befehl darf so viele Minuten laufen,
                        dann Ende (rc 124)
  --dauer DAUER         erwartete Dauer in Minuten; doppelt so lang → Warnung
                        an den Lead
  --braucht-gb GB       start/ausfuehren: geschätzter Arbeitsspeicher dieses
                        Laufs (sonst Rezept, sonst die Grenze des Projekts)
  --braucht-vram-gb GB  start/ausfuehren: benötigter Grafikspeicher
  --braucht-platte-gb GB
                        start/ausfuehren: benötigter freier Platz auf dem
                        Laufwerk des Projekts
  --beschreibung BESCHREIBUNG
  --rezept REZEPT
  --leicht              Pflicht (oder --schwer): normales Bauen/Testen – läuft
                        parallel, wartet nie auf schwere
  --schwer              Pflicht (oder --leicht): KI, Grafikkarte, Fenster oder
                        viel Speicher – läuft einzeln
  --dauerlauf           start/ausfuehren: kopflos, ohne KI/GPU/Fenster, mit
                        --braucht-gb als fester Grenze – läuft neben dem
                        schweren Lauf, die Grenze wird vorgemerkt, der Dienst
                        passt auf, dass er sie hält
  --schirm
  --gpu                 belegt die Grafikkarte: PC-weit nur ein GPU-Lauf zur
                        Zeit (auch KI-Aufträge; ein Lauf mit Fenster wartet
                        ebenfalls)
  --aufgabe AUFGABE
  --rc RC
  --ergebnis ERGEBNIS   ende: Ergebnis-Text · ausfuehren: Datei für die
                        Ausgabe des Befehls (ohne: laeufe/L<nr>.txt neben der
                        Datenbank)
  --abgebrochen
  --grenze GRENZE
  --von VON
  --projekt PROJEKT
```

## benutzer
```
usage: amw benutzer [-h] [--stunden STUNDEN]
                    [--rolle {leser,bearbeiter,projekt_admin,system_admin}]
                    [--projekte PROJEKTE] [--anzeige ANZEIGE] [--email EMAIL]
                    [--von VON] [--projekt PROJEKT]
                    [{neu,liste,aendern,sperren,entsperren,freischalten}]
                    [name]

positional arguments:
  {neu,liste,aendern,sperren,entsperren,freischalten}
  name

options:
  -h, --help            show this help message and exit
  --stunden STUNDEN     freischalten: so lange gilt der Code (1–168)
  --rolle {leser,bearbeiter,projekt_admin,system_admin}
  --projekte PROJEKTE   Namen der Projekte, mit Komma getrennt
  --anzeige ANZEIGE
  --email EMAIL
  --von VON
  --projekt PROJEKT
```

## rechner
```
usage: amw rechner [-h] [--von VON] [--projekt PROJEKT]

options:
  -h, --help         show this help message and exit
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
                    [--bemerkung BEMERKUNG] [--grund GRUND] [--alle]
                    [--stufe {niedrig,mittel,hoch}]
                    [--gruppe {neu,verbessert,behoben}] [--hinweis HINWEIS]
                    [--ohne-bild GRUND] [--von VON] [--projekt PROJEKT]
                    {bitte,gruen,rot,zuruecknehmen,ist-gruen,liste,zeige,stil}
                    [id]

positional arguments:
  {bitte,gruen,rot,zuruecknehmen,ist-gruen,liste,zeige,stil}
  id

options:
  -h, --help            show this help message and exit
  --pruefer PRUEFER
  --zweig ZWEIG
  --sha SHA
  --punkte PUNKTE
  --aufgabe AUFGABE
  --bemerkung BEMERKUNG
                        gruen/rot: Befund (bei rot Pflicht)
  --grund GRUND         zuruecknehmen: was nicht stimmt (Pflicht) · gruen/rot:
                        wie --bemerkung
  --alle
  --stufe {niedrig,mittel,hoch}
                        Prüfstufe höher einstufen als die geänderten Dateien
                        ergeben (nie niedriger)
  --gruppe {neu,verbessert,behoben}
                        bitte: Versionshinweis der Aufgabe (setzt sie die
                        Release-Kette fertig, gilt er)
  --hinweis HINWEIS     bitte: ein Satz für Nutzer zu den Versionshinweisen
  --ohne-bild GRUND     bitte: sichtbare Änderung ausnahmsweise ohne Bild-
                        Dokument an der Aufgabe – mit Grund
  --von VON
  --projekt PROJEKT
```

## freigabe
```
usage: amw freigabe [-h] [--zweig ZWEIG] [--zurueck] [--ausnahme AUSNAHME]
                    [--von VON] [--projekt PROJEKT]
                    {merge} aufgabe

positional arguments:
  {merge}
  aufgabe

options:
  -h, --help           show this help message and exit
  --zweig ZWEIG        nur für diesen Zweig – muss zu einer grünen oder
                       offenen Prüfung der Aufgabe passen; ohne: der Zweig der
                       jüngsten grünen Prüfung (vor der ersten Prüfung: jeder
                       Zweig)
  --zurueck            OK zurücknehmen
  --ausnahme AUSNAHME  ohne eigenen Gesamtlauf ausliefern dürfen – mit Grund
                       (liest amw release ausliefern)
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
                  [--schirm] [--speicher SPEICHER] [--leicht] [--schwer]
                  [--gpu] [--von VON] [--projekt PROJEKT]
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
  --leicht              Pflicht (oder --schwer): Läufe mit diesem Rezept sind
                        leicht
  --schwer              Pflicht (oder --leicht): Läufe mit diesem Rezept sind
                        schwer
  --gpu                 Läufe mit diesem Rezept belegen die Grafikkarte
  --von VON
  --projekt PROJEKT
```

## ki
```
usage: amw ki [-h] [--art ART] [--schnittstelle SCHNITTSTELLE]
              [--endpunkt ENDPUNKT] [--version VERSION] [--lizenz LIZENZ]
              [--ablage ABLAGE] [--start START] [--ordner ORDNER]
              [--vram VRAM] [--abschalten] [--einschalten] [--immer-an]
              [--bei-bedarf] [--datei DATEI] [--sha256 SHA256]
              [--quelle QUELLE] [--kommerziell {ja,nein,registrierung,unklar}]
              [--nutzungsregeln] [--ohne-nutzungsregeln] [--sekunden SEKUNDEN]
              [--notiz NOTIZ] [--grund GRUND] [--beschreibung BESCHREIBUNG]
              [--wer WER] [--entziehen] [--modell MODELL] [--vorlage VORLAGE]
              [--prompt PROMPT] [--prompt-datei PROMPT_DATEI]
              [--negativ NEGATIV] [--seed SEED] [--anzahl ANZAHL]
              [--breite BREITE] [--hoehe HOEHE] [--bild BILD]
              [--parameter PARAMETER] [--titel TITEL] [--aufgabe AUFGABE]
              [--bogen BOGEN] [--frist FRIST] [--nachts] [--text TEXT]
              [--alle] [--von VON] [--projekt PROJEKT]
              [{liste,neu,aendern,modell,freigeben,sperren,vorlage,recht,auftrag,zeige,pruefen,nachweis,vermerk,fenster}]
              [name] [teil]

positional arguments:
  {liste,neu,aendern,modell,freigeben,sperren,vorlage,recht,auftrag,zeige,pruefen,nachweis,vermerk,fenster}
  name                  die KI (z. B. ollama, comfyui) · zeige: Lauf-Nummer
                        L812
  teil                  modell/freigeben/sperren: das Modell · vorlage: Name
                        der Vorlage

options:
  -h, --help            show this help message and exit
  --art ART             neu: sprache | bild | ton | 3d | video | sonstig ·
                        vermerk: ausgewaehlt | verworfen | nachbearbeitet
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
                        startet die KI, wenn ein Auftrag für sie dran ist und
                        sie nicht antwortet)
  --ordner ORDNER       neu/aendern: Arbeitsordner für den Startbefehl
  --vram VRAM           GB Grafikspeicher (Richtwert/Probe)
  --abschalten          aendern: KI nicht mehr beauftragen
  --einschalten
  --immer-an            neu/aendern: die AMW hält die KI am Laufen (startet
                        sie von selbst, beendet sie nie) – Einstellung dieses
                        PCs
  --bei-bedarf          neu/aendern: Vorgabe – startet erst mit einem Auftrag;
                        hat die AMW sie gestartet, beendet sie sie nach
                        ki_leerlauf_min (30) min ohne Auftrag
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
  --wer WER             recht: alle | rolle:<rolle> | <Name>
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
  --nachts              auftrag: erst im KI-Fenster starten (Vorgabe 22–06
                        Uhr), nie vor einem Testtermin – eilt nicht, belegt
                        die Grafikkarte nicht, während du am PC bist
  --text TEXT           vermerk: was von Hand nachbearbeitet wurde bzw. warum
                        ausgewählt/verworfen
  --alle                nachweis: auch archivierte und gelöschte Dokumente
  --von VON
  --projekt PROJEKT
```

## wortlaut
```
usage: amw wortlaut [-h] [--text TEXT] [--text-datei TEXT_DATEI] [--liste]
                    [--seit SEIT] [--grenze GRENZE] [--kanal KANAL]
                    [--zeit ZEIT] [--bemerkung BEMERKUNG] [--von VON]
                    [--projekt PROJEKT]

options:
  -h, --help            show this help message and exit
  --text TEXT
  --text-datei TEXT_DATEI
  --liste               erfasste Aussagen zeigen (neueste zuerst) statt eine
                        zu erfassen
  --seit SEIT           mit --liste: nur ab diesem Zeitpunkt (Datum, z. B.
                        15.11. oder 2026-11-15T18:00:00Z)
  --grenze GRENZE       mit --liste: höchstens so viele
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
                        Aussage des Entwicklers wörtlich: wird im selben Zug
                        als W… erfasst und verknüpft (keine vorhergesagte
                        W-Nummer)
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
                    [--text TEXT] [--ja] [--melden] [--inhalt]
                    [--fassung FASSUNG] [--uebernehmen] [--nur NUR]
                    [--von VON] [--projekt PROJEKT]
                    {ablegen,version,liste,zeigen,kommentar,ueberarbeiten,zuordnen,archivieren,wiederherstellen,online,offline,loeschen,einsammeln}
                    [nr] [pfad]

positional arguments:
  {ablegen,version,liste,zeigen,kommentar,ueberarbeiten,zuordnen,archivieren,wiederherstellen,online,offline,loeschen,einsammeln}
  nr                    ablegen: die Datei; einsammeln: der Ordner; sonst
                        Nummer des Dokuments (D12 oder 12)
  pfad                  version: die neue Datei

options:
  -h, --help            show this help message and exit
  --datei DATEI         statt der Positionsangabe (Dateiaustausch: nur aus
                        eingang-tl/)
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
  --inhalt              zeigen: auch den Inhalt der neuesten (oder --fassung)
                        Fassung – Text bis 20 000 Zeichen, sonst Hinweis +
                        Pfad
  --fassung FASSUNG     zeigen --inhalt: diese Fassung (Nummer) statt der
                        neuesten
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
usage: amw web [-h] [--seite SEITE] [--speicher SPEICHER] [--admin ADMIN]
               [--ca CA] [--ziel ZIEL] [--passwort-abfragen] [--ersetzen]
               [--aussteller AUSSTELLER] [--client-id CLIENT_ID] [--an]
               [--aus] [--von VON] [--projekt PROJEKT]
               {einrichten,bauen,schema,einmal,status,zweitfaktor-neu,sso,paket}

positional arguments:
  {einrichten,bauen,schema,einmal,status,zweitfaktor-neu,sso,paket}

options:
  -h, --help            show this help message and exit
  --seite SEITE         paket: Adresse der Online-Seite, z. B.
                        https://amw.firma.lan (http:// nur im Firmennetz)
  --speicher SPEICHER   paket: Adresse des libSQL-Servers, z. B. https://amw-
                        db.firma.lan (http:// nur im Firmennetz)
  --admin ADMIN         paket: Name des ersten Admins der Online-Seite
                        (Vorgabe: admin)
  --ca CA               paket: Zertifikat der Firmen-CA (PEM) für PC und
                        Seite, wenn die Zertifikate der Server von der Firma
                        sind
  --ziel ZIEL           paket: wohin die ZIP kommt (Vorgabe: amw-
                        paket-<Name>-<Datum>.zip im aktuellen Ordner)
  --passwort-abfragen   paket: Passwort des Admins eintippen statt erzeugen
                        lassen
  --ersetzen            paket: einen schon eingetragenen Online-Speicher
                        ersetzen (neue Schlüssel)
  --aussteller AUSSTELLER
                        sso: Aussteller (Issuer), z. B.
                        https://login.microsoftonline.com/<Mandanten-ID>/v2.0
  --client-id CLIENT_ID
                        sso: Anwendungs-ID (Client-ID) aus der App-
                        Registrierung
  --an                  sso: Knopf „Mit Firmenkonto anmelden“ zeigen
  --aus                 sso: Firmen-Anmeldung ausschalten
  --von VON
  --projekt PROJEKT
```

## speicher
```
usage: amw speicher [-h] [--url URL] [--ca CA] [--ordner ORDNER] [--ersetzen]
                    [--von VON] [--projekt PROJEKT]
                    {schluessel}

positional arguments:
  {schluessel}

options:
  -h, --help         show this help message and exit
  --url URL          Adresse des libSQL-Servers, z. B. https://amw-
                     db.firma.lan (http:// nur im Firmennetz)
  --ca CA            Zertifikat der Firmen-CA (PEM), wenn Windows das
                     Zertifikat des Servers nicht kennt
  --ordner ORDNER    wohin der öffentliche Schlüssel kommt (Vorgabe: neben dem
                     Zugang dieses PCs)
  --ersetzen         einen schon eingetragenen Online-Speicher ersetzen
  --von VON
  --projekt PROJEKT
```

## anmelden
```
usage: amw anmelden [-h] [--ersetzen] [--von VON] [--projekt PROJEKT]

options:
  -h, --help         show this help message and exit
  --ersetzen         eine noch lebende andere Sitzung mit demselben Namen
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
usage: amw einrichten [-h] [--pruefen] [--nur-zeigen] [--ohne-sperren]
                      [--projekt-name PROJEKT_NAME] [--lead LEAD]
                      [--agenten AGENTEN] [--ordner ORDNER]
                      [--rechte {vorgabe,auto,umgehen}]
                      [--denkstufe {low,medium,high,xhigh,max}] [--mit-dienst]
                      [--ohne-hooks] [--fernsteuerung] [--grund-regelwerk]
                      [--entfernen] [--von VON] [--projekt PROJEKT]
                      [{assistent,schnell,agenten-ordner,betriebsart,verbindungen}]
                      [pfad]

positional arguments:
  {assistent,schnell,agenten-ordner,betriebsart,verbindungen}
  pfad                  agenten-ordner: der Ordner | betriebsart: pc, server
                        oder cloud (ohne Angabe: zeigen)

options:
  -h, --help            show this help message and exit
  --pruefen             verbindungen: je erlaubter Adresse den
                        Verbindungsaufbau testen
  --nur-zeigen
  --ohne-sperren        keine Sperr-Regeln (Ordner dessen, der den Dienst
                        betreut)
  --projekt-name PROJEKT_NAME
                        schnell: Name des Projekts
  --lead LEAD           schnell: Name des Lead-Agenten (leer = keiner)
  --agenten AGENTEN     schnell: Namen der Agenten, mit Komma
  --ordner ORDNER       schnell: Projektordner der Agenten
  --rechte {vorgabe,auto,umgehen}
  --denkstufe {low,medium,high,xhigh,max}
  --mit-dienst          schnell: Dienst als geplante Aufgabe einrichten
  --ohne-hooks          schnell: Projektordner nicht anfassen
  --fernsteuerung       schnell: Remote Control für die Agenten an (Vorgabe
                        aus)
  --grund-regelwerk     schnell: das mitgelieferte Grund-Regelwerk übernehmen
                        (Regeln, Definition of Done, Version 0.1.0)
  --entfernen           agenten-ordner: AMW-Einträge wieder herausnehmen
  --von VON
  --projekt PROJEKT
```

## regelwerk
```
usage: amw regelwerk [-h] [--text TEXT] [--ablegen] [--von VON]
                     [--projekt PROJEKT]
                     {abgleich,uebernehmen} [nr]

positional arguments:
  {abgleich,uebernehmen}
  nr                    uebernehmen: Nummer der Grundregel (G1 … G19, W1 … W4)

options:
  -h, --help            show this help message and exit
  --text TEXT           uebernehmen: eigener Wortlaut statt dem der Vorlage
  --ablegen             abgleich: als Dokument ablegen und dem Lead schicken
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
usage: amw release [-h] [--aus-changelog] [--zweig ZWEIG]
                   [--gesamtlauf GESAMTLAUF] [--aufgabe AUFGABE]
                   [--oeffentlich-datei OEFFENTLICH_DATEI] [--titel TITEL]
                   [--commit COMMIT] [--nachtrag] [--version VERSION]
                   [--aufgaben AUFGABEN] [--text TEXT]
                   [--text-datei TEXT_DATEI] [--von VON] [--projekt PROJEKT]
                   {merge,version,liste,entwurf,ausliefern,berichtigen}

positional arguments:
  {merge,version,liste,entwurf,ausliefern,berichtigen}
                        ausliefern --zweig X: die ganze Release-Kette in einem
                        Schritt (Prüfung GRÜN, Merge-OK und Gesamtlauf nötig)
                        · berichtigen --version X --aus-changelog |
                        --oeffentlich-datei … [--aufgaben …] (Lead/Mensch:
                        Text einer eingetragenen Version)

options:
  -h, --help            show this help message and exit
  --aus-changelog       berichtigen: Text aus dem Abschnitt der Version im
                        CHANGELOG auf main
  --zweig ZWEIG         ausliefern: Zweig oder Stand, der live gehen soll
  --gesamtlauf GESAMTLAUF
                        ausliefern: grüner Gesamtlauf L<nr> (sonst sucht die
                        AMW den Lauf, der genau diesen Stand sauber geprüft
                        hat)
  --aufgabe AUFGABE     ausliefern ohne Prüfbitte (Prüfstufe niedrig, nur
                        Doku/Tests): die Aufgabe mit dem Merge-OK
  --oeffentlich-datei OEFFENTLICH_DATEI
                        version: eigener Text für alle statt des Entwurfs
                        (Markdown)
  --titel TITEL
  --commit COMMIT
  --nachtrag            version: eine fehlende kleinere Version nachtragen,
                        die es als Git-Tag gibt (nur Lead)
  --version VERSION
  --aufgaben AUFGABEN
  --text TEXT
  --text-datei TEXT_DATEI
  --von VON
  --projekt PROJEKT
```
