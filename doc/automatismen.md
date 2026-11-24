# Automatismen statt Gebote

Was ein Agent vergessen kann, regelt die AMW technisch, statt es in Regeln zu schreiben. Diese Seite beschreibt die vier
Automatismen: Schirm-Schalter, Wartegründe, Leerlauf-Prüfung und Frage-Prüfung. Befehle im Einzelnen:
[befehle.md](befehle.md).

## Schirm-Schalter (seit 1.7.0; in der Oberfläche „Bildschirm: frei für Agenten / belegt“)

**Wozu:** Läufe mit Fenster (Spiel, Editor, Bildschirmfotos) stören, wenn der Entwickler am PC sitzt. Sie dürfen nur
laufen, solange er den Bildschirm ausdrücklich freigegeben hat.

- **Zustand:** frei oder zu, PC-weit. Jeder Wechsel ist eine Zeile in der Tabelle `schirm` (wird nie gelöscht).
  **Vorgabe: zu**, auch nach jedem Neustart.
- **Frei** gibt nur der Entwickler, in der Workbench am PC, oder der Lead auf sein Wort (`amw schirm frei --grund …
  [--bis 07:00]`, auch über die Brücke). Pflicht ist ein Grund, eine Uhrzeit für das Ende ist möglich.
- **Zu** darf jeder machen, der Entwickler auch online vom Handy aus.
- **Geht von selbst zu**, sobald der Entwickler wieder am PC ist. Das erkennt die AMW nur an Signalen am PC selbst:
  - eine Eingabe an diesem PC, frühestens 2 Minuten nach dem Freigeben (sonst schlösse der Klick auf „frei“ ihn
    gleich wieder), auch über eine Fernsitzung. Eingaben während eines Schirm-Laufs und bis 30 s danach zählen nicht:
    Die Abläufe klicken selbst, und Windows unterscheidet das nicht vom Menschen. **Eine einzelne Eingabe reicht nicht**
    (seit 1.34.1): Erst eine zweite, spätere Eingabe innerhalb von 2 Minuten schließt – ein Mensch am PC bewegt die Maus
    und tippt laufend, eine zuckende Maus oder ein einzelnes Ereignis nicht. Meldung und Log nennen das Programm im
    Vordergrund (nur den Programmnamen), damit ein Fehlalarm nachvollziehbar ist.
  - eine neue Fernsitzung, wenn in den PC-Einstellungen ihr Programm steht (`fernsitzung_prozess`; bei TeamViewer z. B.
    `teamviewer_desktop.exe`, das nur während einer Verbindung läuft),
  - eine Eingabe in der Workbench am PC,
  - die eingestellte Uhrzeit.

  Was er vom Handy schreibt (Online-Seite, Chat, als Wortlaut übernommen), schließt den Schirm nicht: Er ist unterwegs,
  der Bildschirm bleibt frei.
- **Lauf-Schlange:** `amw lauf start --schirm` startet nur bei freiem Schirm und wenn der PC seit 2 Minuten ruht. Mit
  `--warten` wird der Lauf eingereiht, `amw lauf warte <nr>` blockiert, bis er dran ist. Ein wartender Schirm-Lauf hält
  Läufe ohne Fenster nicht auf.
- **Beim Zugehen:** Ein laufender Schirm-Lauf bekommt eine weckende Bitte, sofort zu beenden. Läuft er 5 Minuten später
  noch, erfährt es der Lead. Die AMW beendet selbst keine Prozesse.

Grenze: Die AMW sieht nur Läufe, die über `amw lauf start --schirm` angemeldet sind.

## Sichern & beenden (seit 1.36.0)

Vor einem Update sollen Agenten ihren Stand festhalten und ihre Sitzung enden – ohne dass der Mensch jedes Fenster
einzeln schließt und ohne dass Arbeit mitten im Schritt abreißt.

- **Auslöser:** nur der Mensch am PC – Leitstand „Alle sichern & beenden“ oder Aktionsmenü ⋯ einer Kachel. Nicht über
  die Online-Seite, nicht über die Brücke, nicht per Befehl eines Agenten.
- **Sammelbefehl (A2048):** `amw agent alle-beenden [--alle-projekte] [--frist N] --von Entwickler` im eigenen Terminal des
  Menschen (nie aus einer Agenten-Sitzung, nie ein Agent) – alle laufenden Fenster-Agenten des Projekts bzw. aller Projekte.
- **Rückmeldung (A2048):** `amw agent ende-stand [--alle-projekte]` bzw. `/api/agent/ende-stand` – je Agent des jüngsten
  Auftrags (2 h): sichert (bis HH:MM) · abgemeldet (der Wächter beendet gleich) · beendet; „alle beendet“, wenn keiner mehr läuft.
- **Was geschieht:** Der Agent bekommt einen Halt mit Frist (5 Minuten) und ein STOPP „Sichern und beenden bis HH:MM“:
  laufenden Schritt abschließen oder Zwischenstand festhalten, nichts Neues anfangen, `amw abmelden`.
- **Der Wächter** beendet die Sitzung, sobald sie abgemeldet ist – spätestens zur Frist – und hebt den Halt auf. Hat der
  Agent sein Fenster selbst geschlossen, wird nur der Halt aufgehoben. Das Ende gilt als bewusst: kein automatischer
  Neustart; „Starten / fortsetzen“ oder „Fehlende starten“ holt die Sitzungen zurück.
- **Abbrechen:** „Weiterarbeiten lassen“ im Aktionsmenü (bzw. `amw weiter --fuer <Agent>`) hebt den Auftrag auf.
- **Ohne eigenes Feld gespeichert:** als Halt mit Ablaufzeit; ein gewöhnlicher Halt hat keine und wird nie beendet.
- Agenten ohne Arbeitsordner (z. B. ein Lead, der als Chat arbeitet) betrifft das nicht.

## Agentenstart sicher (seit 1.146.0)

**Wozu:** Ein Agent, dessen Sitzung sich nicht bei der AMW anmeldet, bekommt keine Weckrufe und steht als „beendet“ da,
obwohl er arbeitet – niemand merkt es.

- **Vor dem Start:** Die AMW startet nur, wenn im Ordner (oder in den Claude-Einstellungen des Benutzers) ihr
  SessionStart-Hook eingetragen ist und auf die `amw-hook.py` ihres eigenen Ordners zeigt (ein Hook aus einem
  Entwicklungsbaum würde beim Anmelden abgewiesen); sonst Meldung mit dem Befehl, der den Ordner (neu) einrichtet.
- **Fortsetzen:** nur, wenn die letzte Sitzung im selben Claude-Projektordner liegt wie der Profil-Ordner; sonst beginnt
  eine neue Sitzung (eine fortgesetzte lüde die Notizen eines anderen Ordners). Ohne bekannten Arbeitsordner wie bisher.
  Gilt auch für die fertigen Startzeilen (Profil) und das Startskript nach einem PC-Neustart.
- **Nach dem Start:** Hat sich 3 Minuten nach einem Start durch die AMW keine Sitzung angemeldet, bekommen Lead und Mensch
  einmal die Meldung „… gestartet, meldet sich nicht an“, mit den Hook-Fehlern seit dem Start. Ältere Starts (über 30
  Minuten, z. B. nach einer Pause des Dienstes) werden nicht nachgemeldet.
- **Hook-Fehler:** Scheitert die Anmeldung im SessionStart-Hook, steht der Fehler im Fenster (Systemmeldung) und im
  Fehlerprotokoll des Hooks (`%LOCALAPPDATA%\amw\hook-fehler.log`).
- Grenze: Das Startskript nach einem PC-Neustart prüft den Hook nicht, und für seine Starts gibt es keine Meldung
  „meldet sich nicht an“ (es startet Claude direkt, ohne die AMW).

## Releases in drei Ebenen (A1928, TH158)

**Wozu:** Jede Auslieferung soll die AMW auf dem PC sofort neu machen, aber nicht jedes Mal nach außen gehen. Veröffentlicht
wird, wenn ein Meilenstein fertig ist und der Mensch ihn nach der Vorführung abgenommen hat.

- **Lokal live** (`amw release ausliefern`): Sicherung, main per Fast-Forward, lokaler Tag, Dienst neu, Versionszeile, Aufgaben
  fertig, Web-Abzug (AMW online bleibt auf derselben Version wie der PC). Kein Push von main und Tags, kein GitHub-Release; die
  Kette schreibt das Ereignis `lokal_live` und meldet „Version X lokal live“.
- **Nur die ganze Suite ist ein Gesamtlauf (A1961):** Kette, Release-Takt und „freigabereif“ erkennen einen Gesamtlauf
  gleich: Hat der Lauf einen Befehl, muss er den `gesamtlauf_befehl` des Projekts enthalten (für die AMW die Vorgabe
  `python -X utf8 -m amw.testlauf`; der serielle `python -X utf8 -m unittest discover -s tests` zählt gleich, A1966), und
  danach folgt kein weiteres Argument – kein `-k`, `-p`, `-t`, kein einzelnes Modul, nur das Ende oder ein Trenner der Shell. Ohne Befehl (von Hand angemeldet) zählt „Gesamtlauf“ in der
  Beschreibung. Ein Teil-Lauf zählt nie, auch nicht mit `--gesamtlauf` („L… ist kein Gesamtlauf“). Liefert die Kette mit
  der Ausnahme des Leads aus, steht „Ausnahme (von <Lead>: Grund)“ in der Ausgabe, in der Info an den Lead und als Ereignis
  `auslieferung_ausnahme` – nie eine L-Nummer.
- **Gesamtlauf parallel (A1966):** `python -X utf8 -m amw.testlauf` verteilt die Module von `tests/test_*.py` auf N Prozesse
  (Projekt-Einstellung `gesamtlauf_prozesse`, die `amw lauf ausfuehren` als `AMW_TESTPROZESSE` weitergibt; Vorgabe die halbe
  Kernzahl, mindestens 2). Verteilt wird nach der gemessenen Dauer je Modul aus früheren Läufen (`%LOCALAPPDATA%\AMW\testdauer.json`,
  außerhalb des Repos; ohne Messung nach Dateigröße), das längste zuerst an den leichtesten Prozess. Browser-Tests (Edge)
  laufen alle nacheinander in einem eigenen Prozess. Je Prozess ein eigener Temp-Ordner, `AMW_DB`/`AMW_AGENT`/`AMW_PROJEKT`
  leer. Ausgabe wie unittest: die Fehlerberichte, dann „Ran N tests in X s“ und „OK (…)“ bzw. „FAILED (…)“; rc 0 nur bei
  Grün. Der Hook für schwere Befehle erkennt ihn als „Test-Suite“.
- **Gesamtlauf mit Zeitgrenze und Frist (A2051):** Fortschritt je fertigem Modul („[n/N] modul ok|ROT Xs (pK)“). Beginnt in einem
  Prozess länger als `AMW_TEST_ZEITGRENZE_S` (Vorgabe 300 s) kein neuer Test, beendet `amw.testlauf` genau diesen eigenen
  Prozess samt Kindern (Edge, php), meldet das Modul mit Testmethode und bisheriger Ausgabe als rot („Zeitgrenze“) und lässt
  die restlichen Module in einem neuen Prozess weiterlaufen. Ein Gesamtlauf hat immer eine Frist: ohne `--frist` die
  Projekt-Einstellung `gesamtlauf_frist_min` (Vorgabe 60, 0 = keine); ihr Ende geht als `AMW_LAUF_ENDE` an den Befehl, der
  45 s vorher selbst aufhört, je Prozess „Läuft gerade: …“ mit Modul, Test und Ausgabe schreibt und mit rc 124 endet. Bei rc 124
  bekommt der Lead eine Meldung mit dem zuletzt laufenden Modul – auch wenn der Dienst den Lauf rechnet.
- **Baum unverändert (A2055):** `amw.testlauf` merkt sich am Anfang HEAD und die geänderten und neuen Dateien des Repos (git
  status, ohne `daten/`, mit Größe und Zeit) und vergleicht am Ende. Weicht etwas ab, steht „!! Baum während des Laufs geändert:
  …“ in der Ausgabe, das Ergebnis ist „FAILED (baum geaendert …)“ und rc 3 – der Lauf ist kein Beleg (freigabereif und Kette
  zählen nur rc 0).
- **Fremde A-Nummer im Betreff (A1988):** „Stände“ nimmt jede A-Nummer in einem Commit-Betreff als Aufgabe dieses Commits.
  Darum lehnt schon `amw pruefung bitte` (und `amw paket fertig`) einen Stand ab, dessen Betreffe eine andere Aufgabe des
  Projekts nennen als die der Prüfbitte oder die im Versions-Commit des Stapels („X.Y.Z: … A1 + A2“) – mit dem Commit in der
  Meldung. Verweise gehören in den Text des Commits, ohne „A“ vor der Nummer.
- **Grün auf der Stapel-Spitze deckt den Stapel (A1974, Befund 1.165.0):** Bei der Übertragung zählt für die Commits unter dem
  Ziel auch ein Grün ÜBER dem Ziel (die Spitze, vom Lead geprüft) – so bekommen sauber übertragene Aufgaben ihr Grün auch dann,
  wenn darunter eine Aufgabe mit aufgelöstem Konflikt liegt. „Stände“ nimmt den Versions-Commit eines Stapels (Betreff
  „X.Y.Z: …“ mit allen Aufgaben) als geprüft, wenn ein grüner Stand ihn enthält. Eine Aufgabe, deren Inhalt beim Zusammenführen
  geändert wurde, braucht weiter ihr eigenes Grün auf dem Stapel.
- **Ein Gesamtlauf zur Zeit (A1979, #30758):** ein Gesamtlauf belegt den ganzen Rechner. Die Lauf-Schlange gibt jedem Lauf, der
  die ganze Suite rechnet (paralleler Runner oder `unittest discover` ohne `-k`/`-p`/`-t`), zusätzlich den Platz „gesamt“ –
  läuft schon einer (auch aus einem anderen Projekt), wartet der zweite in der Schlange („Gesamtlauf … belegt den Rechner –
  höchstens einer zur Zeit“). Teil-Läufe laufen daneben weiter. Die Workbench schließt ihre Datenbank-Verbindung, bevor sie
  antwortet – ein Client, der sofort aufräumt, findet die Datei nicht mehr gesperrt.
- **Versionszeile nach dem Schließen (A1985, Befund 23.11.):** die Kette setzt erst die Aufgaben des Stands auf fertig und trägt
  DANN die Versionszeile ein – sie fasst die seit der letzten Version fertigen Aufgaben zusammen. Vorher war es umgekehrt, und jede
  Version trug die Hinweise der vorigen Auslieferung. Die Zusammenfassung, die die AMW selbst schreibt („Ausgeliefert in …“,
  „Fertig: …“), wird nie zum Satz in den Versionshinweisen. Eingetragene Versionen berichtigt der Lead mit
  `amw release berichtigen --version X.Y.Z --aus-changelog | --oeffentlich-datei … [--aufgaben …]` (alter Text als Ereignis
  `release_berichtigt`).
- **Übertragung verdrängt kein Grün der Spitze (A1964):** Die Patch-ID-Übertragung (A1814) legt keine grüne Prüfung auf
  einen inneren Commit, wenn die Aufgabe schon ein Grün auf einem späteren Commit desselben Stands hat (z. B. auf der
  Stapel-Spitze mit dem Versions-Commit). Sonst würde die neue Zeile jenes Grün als neueste Prüfung verdrängen, und die
  Kette hielte bei „Stände“ an (1.162.0).
- **Web-Abzug als Lauf der Kette (A1952):** Der Web-Abzug ist ein leichter Lauf des Agenten „AMW“, nicht des
  ausliefernden Agenten – hat der gerade einen eigenen Lauf (z. B. den Gesamtlauf des nächsten Stapels), geht die Kette
  trotzdem zu Ende und hebt den Wartungsmodus auf. Scheitert der Abzug, stoppt die Kette mit der Anleitung zum Nachholen,
  und der Lead bekommt eine Frage.
- **Abnahme:** Unter „Für dich“ steht ein fertiger Meilenstein, der seit der letzten Veröffentlichung fertig wurde, mit
  „Abnehmen“ (am PC; online nur zu sehen). Im Terminal: `amw bogen abnehmen N` – nur der Mensch, nicht aus einer Agenten-Sitzung,
  nur für einen fertigen Meilenstein. Ereignis `bogen_abgenommen`.
- **Veröffentlichung:** danach einmal von selbst – Push von main und allen lokalen Tags, die es bei GitHub noch nicht gibt, und
  ein GitHub-Release für die neueste Version mit den CHANGELOG-Abschnitten aller dieser Versionen (neueste zuerst). Ereignis
  `veroeffentlicht`, Meldung an Lead und Mensch. Geht etwas schief, meldet die AMW es; `amw bogen abnehmen N` noch einmal stößt
  die Veröffentlichung erneut an.
- **Einstellung `veroeffentlichen`:** meilenstein (Vorgabe) | sofort (wie früher: Push und GitHub-Release bei jeder
  Auslieferung). Nur Lead oder Mensch, nicht aus einer Agenten-Sitzung.
- **Sicherung (Ebene 2, A1929):** Einmal am Tag schiebt die AMW ALLE Zweige und Tags des Projekt-Repos an
  `sicherung_ziel` (URL, `git@host:pfad` oder Name eines Remotes; setzen Lead oder Mensch, A1951; ohne Ziel nichts) –
  ohne neue Version, ohne Homepage, nur wenn sich seit dem letzten vollständigen Push etwas geändert hat. Nie mit Gewalt: kein
  `--force`, kein `--prune`, kein `--mirror`; ein Zweig, der am Ziel nicht vorspulen kann (lokal neu aufgesetzt), bleibt dort
  wie er war und steht in der Meldung an den Lead, die übrigen Refs gehen mit. Keine Zugangsdaten in der AMW: eine URL mit
  Benutzer oder Token wird abgelehnt, git nimmt die Anmeldung des Menschen – im Dienst nie mit Abfrage (kein Fenster, kein
  Hängen): fehlt sie, kommt sofort „Anmeldung fehlt – einmal git push von Hand“. Der Push läuft in einem eigenen Faden (die
  Dienst-Runde wartet nicht), höchstens einer zur Zeit, mit Frist; ein abgewiesener Zweig wird nur einmal gemeldet.
  Ereignis `sicherung_push`; von Hand:
  `amw sicherung jetzt` (Lead oder Mensch), Stand: `amw sicherung`.

## Versionshinweis ableiten (A1954, TH151)

**Wozu:** Der Agent musste beim Abschließen Gruppe und Satz für die Versionshinweise selbst angeben; fehlten sie, stand im
Entwurf ein Satz aus der Zusammenfassung – bei von der AMW geschlossenen Aufgaben ein interner Text („Fertig: Thema … ist
freigegeben“).

- **Auslöser:** jedes Setzen auf fertig (Agent, Lead, Release-Kette, Fertig-Quelle, Urteil), wenn Satz oder Gruppe fehlen.
- **Was geschieht (ohne KI, `versionshinweise.ableiten`):** Gruppe aus der Art der Aufgabe (fehlersuche → behoben), sonst
  nach Stichworten. Satz aus der ersten Quelle mit mindestens drei Wörtern: Fertig-Quelle „thema“ → Name des Themas;
  Commit-Betreff des Belegs im Projektordner (ohne Kopf „A12:“, nur bis „ – “ oder „; “, ohne Verweise; nie ein
  Versions-Commit); die Zusammenfassung des Agenten (nie die der AMW); der Titel.
- **Gespeichert:** in `hinweis`/`hinweis_gruppe` der Aufgabe, dazu das Ereignis `hinweis_abgeleitet` (Quelle, was abgeleitet
  wurde). Der Entwurf zeigt einen abgeleiteten Satz als Vorschlag. Was der Agent angibt, geht immer vor; er ergänzt höchstens.
- **Intern (A1978):** `--gruppe intern` beim Abschließen oder `amw aufgabe hinweis N --gruppe intern` danach (Bearbeiter, Lead,
  Mensch; nur solange keine eingetragene Version die Aufgabe enthält) nimmt eine Aufgabe aus den Versionshinweisen – ohne Schema
  als Ereignis `hinweis_intern`; Gruppe und Satz werden geleert, die Ableitung läuft für sie nie. `amw aufgabe hinweis N --gruppe
  neu|verbessert|behoben [--hinweis …]` setzt sie wieder.

## Bündeln (seit 1.150.0)

**Wozu:** p-Pakete ohne Coder ausliefern – bisher setzte ein Coder die freigegebenen Pakete von Hand aufeinander, hob die
Nummer und schrieb die Versionshinweise.

- **Auslöser:** nur der Lead oder der Mensch: `amw paket buendeln --alle | <nr> [--titel …]` (D1306 F1).
- **Was geschieht:** eigener Arbeitsbaum `<platz_wurzel>/buendel` (git worktree, neutrale git-Umgebung ohne Hooks), je
  freigegebenem Paket ein cherry-pick in Rang-Reihenfolge; Konflikt → E8 an den Lead, „nach“-Pakete bleiben draußen;
  Versions-Commit (MINOR bei Hinweis-Gruppe „neu“, sonst PATCH; Versionshinweise aus den Hinweisen) mit Diff-Tor: nur
  `version_datei`, `changelog_datei` und die Dateien von `buendel_schritt`; Zweig `buendel-X.Y.Z`.
- **Abnahme-Test (A1955, TH165):** nennt der Abnahme-Befehl eines Pakets vom Typ normal `tests/abnahme_<x>.py`, benennt der
  Versions-Commit ihn in `tests/test_abnahme_<x>.py` um (git mv; das Diff-Tor erlaubt genau diese Umbenennung) – er läuft
  damit schon im Gesamtlauf des Bündels und danach in jeder Gesamtsuite. Gibt es das Ziel schon, bleibt die Datei (Hinweis).
  Pakete vom Typ test-schreiben/test-ergaenzen bringen ihre `test_*.py` selbst mit.
- **Danach im eigenen Prozess:** Gesamtlauf (`gesamtlauf_befehl`) über die Lauf-Schlange auf genau der Spitze; grün → GRÜN mit
  dem Lead als Prüfer und Meldung „Bündel X.Y.Z bereit“ mit Versions-Diff und Befehlen; rot → Meldung, kein GRÜN.
- **Release:** gibt der Lead frei – die Kette zählt für `buendel-*` nur ein Merge-OK, das Lead oder Mensch selbst geben
  (nicht die von den Paketen übernommenen).
- **Release-Modus je Projekt (A1923, TH160):** `release_modus` = `datei` (Vorgabe: Nummer in `version_datei`) | `tag` (Nummer
  aus dem höchsten Tag `vX.Y.Z` des Projekt-Repos, ohne Tag 0.x; kein Versions-Commit an einer Datei – der Bündel-Commit
  ändert nur den CHANGELOG). `changelog_format` = `amw` (Vorgabe: „## X.Y.Z – TT.MM.JJJJ · Titel“) | `keepachangelog`
  („## [Unreleased]“ wird „## [X.Y.Z] - JJJJ-MM-TT“ mit Added/Changed/Fixed aus den Hinweisen; was schon darunter stand, bleibt;
  darüber ein neues leeres [Unreleased]). Beide nur Lead oder Mensch, nicht aus einer Agenten-Sitzung. Den Tag setzt das
  Bündel nie – das bleibt `release ausliefern` (Lead bzw. Mensch).
- **Ausliefern eines Projekts, das nicht die AMW ist (A1933):** `amw release ausliefern --zweig buendel-X.Y.Z` arbeitet im
  Ordner des Projekts (`amw projekt ordner`); die AMW selbst erkennt sie an ihrem Code im Ordner, nicht am Namen. Nur der
  Lead des Projekts oder der Mensch im eigenen Terminal – ein Tag kann im Projekt Workflows starten. Prüfungen, Merge-OK und
  Gesamtlauf wie bei der AMW; der Ordner muss auf main und sauber sein. Sicherung der Projektdaten nur mit
  `release_sicherung = an`. Dann Fast-Forward, Tag `vX.Y.Z` (Nummer aus Versionsdatei bzw. CHANGELOG, je nach `release_modus`),
  Push und Release-Notiz nach `veroeffentlichen` (sofort oder bei der Abnahme des Meilensteins), Aufgaben fertig, Meldung an
  den Lead. Dienst, Schema, Versionszeile und Web-Abzug gibt es hier nicht.
- **Zeilenenden (seit 1.152.3, A1909):** Im Bündel gilt `core.autocrlf` des Projekt-Repos (Repo vor System), derselbe Wert wie
  beim Stand-Vergleich vor dem Gesamtlauf; der Arbeitsbaum wird bei jedem Bündel ganz neu geschrieben. Vorher checkte das
  Bündel mit dem Systemwert (CRLF) aus, die Nacharbeit schrieb Dateien mit gleichem Inhalt in LF neu, und git hielt sie wegen
  der Größe für geändert („Arbeitsbaum verschoben“, L2896). Der Stand-Vergleich zählt reine Stat-Unterschiede (Inhalt gleich)
  nicht mehr als geändert.
- **Neu anstoßen:** `amw paket buendeln --gesamtlauf buendel-X.Y.Z` (Lead oder Mensch) – Arbeitsbaum sauber auf die Spitze
  des Bündels, Gesamtlauf und Meldung wie beim ersten Mal; nicht, solange ein Bündel offen ist oder wenn es schon in main ist.
- **Merge-OK nach einem Bündel ohne Release (A1911):** Beim Bündeln gehen Grün und Merge-OK der Pakete auf `buendel-X.Y.Z` über.
  Ist der Gesamtlauf des Bündels zu Ende und wurde es nicht ausgeliefert, gelten die Merge-OKs auf `paket-A<n>` wieder –
  `amw paket buendeln --alle` findet die Pakete ohne neue Freigabe (21.11.: nach dem abgebrochenen Bündel 1.152.2 fand es
  keins mehr). Eine Rücknahme des Merge-OK zählt immer.
- **Alle Pakete fertig nach dem Release (A1912):** Die Kette setzt jedes Paket des Bündels auf gemergt und fertig, nicht nur
  das, an dem das Grün des Leads hängt. Dafür geht beim Neubündeln das Merge-OK eines Pakets auch dann ins neue Bündel mit,
  wenn dessen Stand schon grün ist (21.11., 1.152.6: nach Bündel 1.152.4 rot und neuer Freigabe ging nur Grün mit, das OK nicht –
  fünf Pakete blieben offen). Außerhalb von Bündeln braucht ein schon grüner Stand weiter sein eigenes Merge-OK.
- **Zeilenenden der Arbeitsplätze und von Prüfung C (A1911):** Arbeiter-Klone und der frische Checkout von Prüfung C checken
  mit `core.autocrlf` des Projekts aus (der Wert steht auch in der Konfiguration des Klons, denn der Arbeiter ruft git ohne
  System-Konfiguration auf). Vorher bekamen sie den Systemwert (CRLF bei einem LF-Projekt): Der Arbeiter sah angefasste
  Dateien ganz als geändert, Tests in Prüfung C liefen auf anderen Bytes als bei Entwicklern und im Live-Ordner. Ältere
  Klone werden beim nächsten Vorbereiten einmal neu geschrieben; eingesammelt wird mit dem Wert, mit dem der Klon
  ausgecheckt ist.

## Freigabereif und Nachwecken (seit 1.152.0)

**Wozu:** 21.11.: Ein Gesamtlauf war grün auf einem grün geprüften Stand, aber niemand wurde geweckt – der Lead wartete auf
den Coder, der Coder auf das Merge-OK. Und eine Bitte als Info weckte den Lead nicht.

- **Freigabereif:** Endet ein Gesamtlauf (Beschreibung „Gesamtlauf“ oder der `gesamtlauf_befehl` des Projekts) grün, und gibt es
  auf genau diesem Stand („Stand <sha> sauber“) eine grüne Prüfung ohne Merge-OK, meldet die AMW dem Prüfer „A<n> freigabereif …
  Merge-OK: amw freigabe merge …“ (weckt) und dem Bauer zur Info. Rot → „Gesamtlauf rot“ an Prüfer und Bauer. Kommt das Grün
  erst nach dem Lauf, kommt die Meldung beim Grün-Setzen. Eine Meldung je Prüfung und Stand.
- **Bitte als Info:** `amw posten --art info` an einen Agenten – Lead oder Coder, auch über `--an alle` – wird abgewiesen, wenn
  sie um eine Handlung bittet (bitte … Merge-OK, prüfen, freigeben, entscheiden, ausliefern, aufsetzen; jetzt … aufsetzen,
  ausliefern, prüfen) oder zu einer Aufgabe gehört, die auf ihn wartet: „Bitte um Handlung → --art auftrag oder frage
  (weckt)“. Eine info weckt nicht. Wartet die Aufgabe auf den Absender, erledigt seine Nachricht den Wartegrund, und die AMW
  weckt selbst. Ausgenommen: AMW und der Mensch als Absender, der Mensch als Empfänger.
- **Nachwecken:** Der Dienst weckt den Lead einmal nach, wenn eine Nachricht 10 Minuten nach dem Weckruf noch ungelesen ist und
  er seitdem nichts gesendet hat – höchstens einmal je Nachricht, nicht im Halt, nicht während er arbeitet.
- **Gemeinsamer Stand:** Eine Prüfung einer anderen Aufgabe auf genau demselben Stand (oder demselben Baum) belegt die
  Versionsnummer nicht mehr – zwei Aufgaben lassen sich auf einem Stand prüfen und ausliefern.
- **Weitergebauter Stapel (A1958):** Auch eine Prüfung auf einem Vorgänger des neuen Stands belegt die Nummer nicht –
  nach einem roten Gesamtlauf und einem Korrektur-Commit gehen die neuen Prüfbitten durch, ohne dass der Lead die grünen
  Prüfungen des Vorgängers zurücknehmen muss. Ein fremder Stand mit derselben Nummer belegt weiter.
- **Neu aufgesetzter Stapel (A1982):** Wird ein Stapel auf einer neueren main neu aufgesetzt (anderer Basis-Commit), belegt
  der alte Stand die Nummer nicht mehr, wenn alle seine Inhalts-Commits patch-id-gleich im neuen Stand stecken – Versions-Commits
  (nur CHANGELOG, `amw/__init__.py`, `web/inc/VERSION`) zählen dabei nicht. Fehlt im neuen Stand Inhalt des alten, belegt er weiter.

## Wartegründe (seit 1.8.0)

**Wozu:** Eine Aufgabe, die „wartet“, ohne zu sagen worauf, bleibt liegen, auch wenn der Grund längst erledigt ist.

- `amw aufgabe wartet|blockiert <nr> --auf <Verweise>`. Ohne `--auf` lehnt die AMW ab, Freitext allein (`--wartet-auf`)
  reicht nicht. Eine neue, noch nicht begonnene Aufgabe steht ohne Grund auf „wartet“ (= zu tun).

  | Verweis | erledigt, wenn … |
  |---|---|
  | `F12` | die Frage beantwortet ist (eine Rückfrage zählt nicht) |
  | `A120` | die Aufgabe fertig oder verworfen ist |
  | `L7` | der Lauf zu Ende ist |
  | `CC2` (Kennung) | dieser Agent eine Nachricht mit `--aufgabe` dieser Aufgabe schickt |
  | `Entwickler` (oder sein eingestellter Name) | er eine Frage zu dieser Aufgabe beantwortet oder in der Workbench dazu schreibt |
  | `Monitor:<was>` | nur von Hand |
  | `P601` (Prüfung, A2053) | die Prüfung grün oder rot ist – gesetzt von selbst, sobald die Aufgabe wartet und eine Prüfbitte zu ihr offen ist (`amw pruefung bitte --aufgabe`, `amw paket fertig`); den Status ändert die Prüfbitte nicht, ein laufendes Paket darf nachbessern |
  | `stapel:<zweig>` (A2053) | `amw release ausliefern --zweig <zweig>` durch ist |

- **Art des Wartegrunds (A2053, TH155):** jeder Grund hat eine von fünf Arten. `--art pruefung|stapel|lauf|antwort|paket`
  setzt sie ausdrücklich (z. B. `--auf CCamwTL --art pruefung`); sonst leitet die AMW sie ab: `P…` Prüfung, `stapel:…` Stapel,
  `L…` Lauf, `A…` Paket, alles andere (Frage, Agent, Entwickler, Monitor) Antwort; reiner Freitext grob nach Stichwort
  („Prüf…“, „Stapel/Release/Auslieferung/Kette“, „L…/Gesamtlauf“), sonst Antwort. Gespeichert wird ohne Schemaänderung als
  Stichwort im Bezug (`pruefung:P601`, `stapel:stapel41`).
- **Warten gibt frei (A2053):** wartet eine Aufgabe auf eine Prüfung, einen Stapel oder einen Lauf, ist ihr Agent sofort frei
  für anderes – mit `verteilen = an` teilt die AMW ihm das nächste startklare Paket zu und weckt ihn; mit `vorschlag` geht der
  Vorschlag an den Lead. Wartet sie auf eine Antwort oder ein anderes Paket, gilt das erst nach 10 Minuten. Das wartende Paket
  bleibt seins; ist sein Grund erledigt, weckt die AMW ihn dafür.
- **Startklar ohne Grund (A2053):** steht eine Aufgabe mit Bearbeiter auf „wartet“, ohne offenen Grund und mit fertigen
  Vorgängern, und hat er nichts in „läuft“, bekommt er einmal „A… ist startklar – weiter: amw aufgabe start N“.

- Ist ein Grund erledigt, weckt die AMW den Besitzer der Aufgabe („A120: F12 beantwortet – noch offen: CC2“ bzw. „alle
  Gründe erledigt – weiter“), mit Kopie an den Lead. Von Hand abhaken: `amw aufgabe wartet <nr> --erledigt F12`.
- `--aufgabe` beim Posten wird geprüft: Eine Nummer, die es nicht gibt oder die abgeschlossen ist, wird abgelehnt; bei
  einer fremden Aufgabe kommt ein Hinweis. Eine `info`, `meldung` oder `antwort` zu einer fremden Aufgabe geht in Kopie an
  ihren Besitzer.
- Workbench: An jeder offenen Frage steht, welche Aufgabe sie aufhält; die Kacheln zeigen „A… wartet auf …“.

## Leerlauf-Prüfung (seit 1.8.0)

Ist eine Sitzung seit 30 Minuten frei, ohne offene Post, und hat der Agent eine Aufgabe ohne offenen Grund (Vorgänger
fertig, nicht geparkt), weckt ihn der Dienst mit dieser Aufgabe, einmal je Ruhephase. Warten alle Aufgaben eines freien
Agenten auf den Entwickler, bekommt der Lead höchstens alle 6 Stunden eine Sammelzeile.

**Nichts zu tun (seit 1.147.0):** Ist ein Agent im Terminal (Soll an) seit 10 Minuten frei, hat keine Aufgabe in „läuft“
oder ohne offenen Grund und wartet weder auf einen eigenen Lauf noch auf die Prüfung seines Stands, bekommt der Lead einen
Weckruf: welcher Agent, seit wann frei, und die freien Aufgaben der aktiven Meilensteine ohne Bearbeiter. Je Agent einmal je
Ruhephase. Empfänger ist die Projekt-Einstellung `leerlauf_lead` (sonst der Lead), aber nur, wenn er im Terminal arbeitet –
einen Chat-Lead weckt die AMW nicht. Wartezeit: `leerlauf_lead_min` (1–1440, Vorgabe 10). Beides setzen Lead oder Mensch:
`amw projekt einstellen leerlauf_lead=<Agent> leerlauf_lead_min=<min>`. Mit `verteilen = an` und einem startklaren Paket, das
zum Agenten passt, teilt die AMW selbst zu (A2053) – dann geht keine Meldung an den Lead.

**Warten auf einen Agenten (A1997):** Hat ein Agent nur noch Aufgaben, die auf einen anderen Agenten warten (keine in
„läuft“, jede wartende hat offene Gründe, alle sind Agenten), prüft die Dienst-Runde je Grund: Kam seit `warten_agent_min`
Minuten (5–1440, Vorgabe 60; gezählt ab dem Grund oder der letzten Nachricht des Erwarteten an den Wartenden) nichts, bekommt
der Lead einmal „CC1 wartet seit … auf CC2 (A12) – Grund noch aktuell?“. Ist seit dem Grund eine Version live gegangen,
kommt diese Meldung sofort, und der Wartende bekommt einen Weckruf mit der Version. Einmal je Funkstille bzw. je Grund und
Version (Ereignis `warten_agent`); abgehakt wird nichts automatisch. Setzen: `amw projekt einstellen warten_agent_min=<min>`.

## Verteilen an freie Agenten (A1927, TH157)

**Wozu:** Ein interaktiver Agent, der frei ist, soll ohne Umweg über den Lead die nächste passende Aufgabe nach dessen Plan
bekommen; fällt ein Agent aus, geht seine Arbeit nicht verloren.

- **Frei:** Agent im Terminal mit aktiver Sitzung, Soll an, nicht Lead und nicht Co-Entwickler, kein Halt, ohne Aufgabe in
  „läuft“ und ohne Aufgabe ohne Wartegrund.
- **Kandidaten:** offene Aufgaben ohne Bearbeiter in aktiven Meilensteinen, Art agent (keine p-Pakete), startklar (wartet,
  kein offener Wartegrund, kein Wartetext, kein offener Vorgänger). Reihenfolge: Rang, dann kritischer Pfad (die längere
  Kette offener Nachfolger zuerst).
- **Passt (Option A, #29773):** Fachgebiet – ein Wort aus der Tabelle der Art steht im Fachgebiet des Agenten (Vorgabe: text →
  text/doku/code; mechanisch, fehlersuche, sicherheit → code; oberflaeche → code/grafik; konzept → konzept; je Projekt
  `verteilen_fach`, nur Lead oder Mensch, nicht aus einer Agenten-Sitzung). Größe – Modell und Denkaufwand im Profil nicht
  schwächer als die Empfehlung für Größe und Art; ist das Profil schwächer, teilt die AMW nie selbst zu, sondern schlägt dem
  Lead vor („A… bräuchte opus/high, CC1 hat sonnet/medium“), weil Modell und Denkaufwand in einer laufenden Sitzung nicht
  wechseln (TH159). Ohne Fachgebiet, ohne Art oder mit offenem Profil passt es. Die Begründung nennt beide Treffer.
- **Einstellung `verteilen`:** vorschlag (Vorgabe) – der Lead bekommt „Vorschlag: A… an CC1?“ als Frage mit dem Befehl;
  an – die AMW teilt zu (Auftrag an den Agenten mit Begründung, Meldung an den Lead); aus. Je Paar Agent/Aufgabe ein
  Vorschlag.
- **Ausfall:** Hat ein Agent eine Aufgabe in „läuft“ und ist seine Sitzung seit `ausfall_min` (Vorgabe 30, 5–1440) beendet
  ohne neue (die Aufsicht prüft die Pipe – ein stiller, wartender Agent hat Puls), geht die Aufgabe ohne Bearbeiter in den
  Pool zurück. Übergabe-Notiz: letzter Commit zur Aufgabe, letzte Tätigkeit, offene Kriterien und Wartegründe – an den Lead
  und als Ereignis `uebergabe`. Der Mensch bekommt die Frage „Sitzung von … neu starten?“; die AMW startet nie selbst.
- Ohne Schemaänderung: Ereignisse `verteilt`, `verteil_vorschlag`, `ausfall`, `uebergabe`.

## Sperrliste je Projekt (A1919, TH160)

**Wozu:** Ein Arbeiter (p-Paket oder interaktives Paket) darf manche Dateien nie ändern. Für die AMW selbst steht das fest im
Code; ein anderes Projekt hat eigene heikle Stellen (Zugänge, Sicherheit, Zahlungen) und trägt sie selbst ein.

- **Feste Liste:** `abnahme.GESPERRT` – Kette, Rechte, Hooks, Testkonfiguration der AMW. Gilt in jedem Projekt.
- **Muster je Projekt:** `amw projekt einstellen sperrmuster='["src/sicherheit/*", "*.key"]'` (oder durch Komma getrennt;
  leer = keine). Muster relativ zum Projektordner wie bei `fnmatch`, ohne `..`, höchstens 50. Nur Lead oder Mensch, nicht
  aus einer Agenten-Sitzung. Gelten zusätzlich und für jeden Pakettyp, auch für Test-Pakete.
- **Wo es greift:** vor dem Start (Startregel 5: ein Bereich, der ein Muster ist oder enthält, startet nicht) und im Diff-Tor
  von Prüfung C (geänderte Datei trifft ein Muster → C/diff, Befund „gesperrt: …“ an den Lead), bei p-Paketen und bei
  interaktiven Paketen mit Zweig. Grund im Befund: „gesperrt im Projekt (Muster)“.

## Rückschritt-Tests und Zeitlimit je Projekt (A1920, TH160)

**Wozu:** Prüfung C führt nach dem Abnahme-Befehl des Pakets eine kurze Testfolge gegen Rückschritte aus
(Regressions-Kurzsuite). Die der AMW passt nur zur AMW; ein anderes Projekt hat eigene Tests und oft längere Testfolgen.

- **Ohne Einstellung:** Ist der Projektordner die AMW selbst (`amw/pruefung_c.py` und `amw-cli.py` darin – nicht am Namen
  erkannt), läuft die Kurzsuite der AMW. Jedes andere Projekt läuft ohne. Das steht dann im Befund, in der Entscheidung und in
  „Bereit zum Merge“: „Ohne Rückschritt-Tests geprüft – für dieses Projekt sind keine eingestellt.“
- **`regression_befehl`:** ein Befehl in einer Zeile (bis 500 Zeichen), der im frischen Checkout läuft wie der Abnahme-Befehl;
  `aus` = keine (auch für die AMW); leer = wieder die Vorgabe. Der Abnahme-Befehl je Paket bleibt.
- **`abnahme_frist_min`:** Zeitlimit für Abnahme, Rückschritt-Tests und die Prüfung vor dem Bau (Regel 6), 1–720 Minuten,
  Vorgabe 30.
- Beide nur Lead oder Mensch, nicht aus einer Agenten-Sitzung.

## Nur Riskantes zum Lead (A2054, TH167 Fassung 4)

**Wozu:** Der Lead liest nur, was riskant ist – sonst nimmt die AMW bei Grün der Prüfung C selbst ab.

- **Fenster-Pakete:** `amw paket ergebnis` (erledigt, mit Abnahme-Befehl, `--zweig`) und `amw paket fertig` prüfen sofort den
  leichten Teil (Diff-Tor, Geheimnis, nach außen); trifft er, geht wie bisher eine Prüfbitte an den Lead. Sonst meldet die AMW die
  volle Prüfung C an (`plan_ereignis fenster_pruefung`), der Dienst rechnet sie im eigenen Faden über die Lauf-Schlange
  (`amw/fensterpruefung.py`): frischer Checkout genau des Zweig-Kopfs, Abnahme, Testproben, Kurzsuite, Sprachprüfung. Testdateien
  sind für Fenster-Pakete frei (Pakettyp „fenster“ im Diff-Tor), geschwächte Tests fängt die Riskant-Regel. `paket fertig`
  lässt die Aufgabe auf `pruefung:C-A<nr>` warten (gibt den Agenten frei).
- **Entscheidung:** grün und nichts Riskantes → E7: Prüfung „grün“ mit Prüfer AMW und Beleg (Lauf der Prüfung C, Abnahme, Kurzsuite,
  Sprachprüfung, Riskant-Einordnung „keine Regel getroffen“ mit Version); das Merge-OK gibt weiter der Lead (Liste bzw. `amw freigabe
  merge`). Grün, aber riskant → Prüfbitte an den Lead mit den Regeln (bei g12 zusätzlich eine Info an den Menschen). Rot → zuerst ein
  Auftrag an den Agenten (nachbessern, neu melden), beim zweiten Rot der Lead. Leer/Diff/aussen/technisch → Prüfbitte an den Lead.
- **p-Pakete:** E7 mit einer Riskant-Regel wird E4 (Lead liest); test-schreiben/test-ergaenzen mit erfüllter Probe und ohne
  Riskantes werden E7. Der Beleg steht in `paket_entscheidung` („riskant“).
- **Riskant-Regeln** (`amw/riskant.py`, eine Funktion mit Begründung je Treffer): aussen · server (web/*.php) · schutz (gesperrte
  Pfade „fest“ und Projekt-Muster, Prüfstufe hoch, Art sicherheit, Geheimnis-Verdacht) · schema · g12 (Löschen, Kosten,
  Außenwirkung) · lead_liest · auffaellig (E2/E4/E6/E8) · pruefung (Änderung an der Prüfung selbst, auch pruefstufe.py, arbeiter.py, rueckmeldung.py – A2070) · claude_p · tests_geschwaecht
  (Test gelöscht/übersprungen, weniger Testmethoden oder Assertions) · oberflaeche (sichtbar: die Stil-Prüfung läuft noch nicht im
  Autopfad).
- **„Lead liest“:** `amw paket lead-liest <nr> [--aus]` (Lead, Mensch) bzw. Planfeld `"lead_liest": true` (Grob- und Feinplaner);
  gespeichert als `plan_ereignis lead_liest` ohne Schemaänderung.
- **Merge-Tor Versions-Commit:** `release ausliefern` stoppt, wenn ein Commit, der die Versionsdatei ändert, mehr ändert als
  CHANGELOG, Versionsdatei und `web/inc/VERSION`.
- **Messen:** einmal je Woche (ISO) eine Info an den Lead – automatisch abgenommen (erstes E7, p und Fenster) von allen entschiedenen
  Paketen der Vorwoche und welche danach zurückgenommen wurden (E8, zurückgenommene Prüfung, Revert in main).

## Sprach-Server-Prüfung in Prüfung C (A1962, TH167 Fassung 3 Pkt 7)

**Wozu:** Typ- und Aufruffehler, die die Tests nicht treffen, fallen vor dem Merge auf – ohne KI-Aufruf, ohne Netz.

- **Was läuft:** Nach Abnahme und Rückschritt-Tests läuft `pyright --outputjson` über das ganze Projekt (Konfiguration
  `pyrightconfig.json` aus dem Repo) – im frischen Checkout des Pakets und in einem frischen Checkout seines Start-Commits, mit
  Zeitlimit 10 Minuten je Lauf. Neu ist eine Meldung mit Schweregrad error, verglichen nach Regel, Datei und Text ohne
  Zeilennummer (gleiche Meldung öfter als vorher zählt). Warnungen zählen nicht.
- **Danach:** neue Fehler → C/rot; die Liste (Datei:Zeile, Regel, Text) geht mit der Abnahme-Ausgabe in den Nachbesserungslauf
  (E5). Programm fehlt, stürzt ab oder Zeitlimit → C/technik. Ist die Abnahme rot, läuft die Prüfung trotzdem, damit der neue
  Lauf beides sieht.
- **`sprachpruefung`:** `auto` (Vorgabe: an, wenn das Repo eine `pyrightconfig.json` hat) | `pyright` (immer) | `aus` – nur Lead
  oder Mensch. pyright kommt aus der Umgebung der AMW (npm, vorab installiert); der Arbeiter selbst bekommt es nicht.

## Werkzeug-Umgebung je Projekt (A1922, TH160)

**Wozu:** Arbeiter (p-Pakete) laufen mit einer neu gebauten, kleinen Umgebung und ohne Netz. Ein Projekt mit eigenem
Werkzeug (SDK, Compiler) oder mit vorbereiteten Caches braucht dafür einzelne Variablen und Ordner im PATH.

- **Einstellung:** `amw projekt einstellen arbeiter_umgebung='{"variablen": ["JAVA_HOME", "GRADLE_USER_HOME"], "pfade":
  ["C:\\Android\\platform-tools"]}'` – nur Lead oder Mensch, nicht aus einer Agenten-Sitzung; leer = nur die Grundumgebung.
- **Variablen:** Nur der Name steht in der Einstellung, der Wert kommt aus der Umgebung der AMW. Abgelehnt: Namen wie
  Zugangsdaten (`*TOKEN*`, `*KEY*`, `*SECRET*`, `*PASSWORD*`, `*PASSWD*`, `*CREDENTIAL*`, `*AUTH*`, `*COOKIE*`, `*SESSION*`),
  Netz (`*PROXY*`) und alles, was die AMW selbst setzt (`AMW_*`, `CLAUDE*`, `ANTHROPIC*`, `GIT_*`, `PATH`, `TEMP` …).
  Höchstens 30.
- **Pfade:** absolute Ordner, hinter dem minimalen PATH der AMW, höchstens 20.
- **Wo es gilt:** beim Arbeiter und bei Abnahme und Rückschritt-Tests in Prüfung C. Die Negativprobe bei einer neuen
  Claude-Code-Version (A1906) und der Gegenleser laufen mit der Grundumgebung. Kein Netz bleibt.

## Weitere Anbieter und lokale Modelle (A1931, TH159)

**Wozu:** Arbeiter (p-Pakete) können außer Anthropic auch andere Anbieter mit einer Anthropic-kompatiblen Schnittstelle nutzen
(z. B. MiniMax) oder lokale Modelle (z. B. Ollama). Jeder Anbieter ist extern, auch Anthropic.

- **Freigeben:** nur der Mensch im eigenen Terminal (auch nicht der Lead):
  `amw anbieter freigeben minimax --url https://… --schluessel-datei D:\\schluessel\\minimax.key --modelle MiniMax-M2 [--lokal]`;
  `amw anbieter liste`, `amw anbieter entfernen minimax`. Anthropic ist ohne Eintrag freigegeben (wie bisher).
- **Schlüssel nur lokal:** Gespeichert wird nur der PFAD der Schlüsseldatei – nie der Schlüssel, nicht in Datenbank, Repo,
  Nachricht, Bericht oder Ereignis. Die Datei muss außerhalb der AMW, des Projektordners und der Arbeitsplätze liegen.
- **Paket:** Der Anbieter steht im Modell: `amw aufgabe aendern N --modell minimax@MiniMax-M2` (ohne Präfix: Anthropic).
- **Zur Laufzeit:** Der Arbeiter bekommt in seiner `--settings`-Datei `ANTHROPIC_BASE_URL` und als `apiKeyHelper`
  `amw-anbieter-schluessel.py <Pfad>`. Das Skript gibt eine Schlüsseldatei nur aus, wenn ihr Pfad in der Freigabe-Liste der AMW steht
  (`daten/anbieter-freigabe.json`, nur Pfade). Der Schlüssel steht so in keiner Umgebung und keiner Datei des Platzes.
- **Startregeln:** Regel 13 – Anbieter in diesem Projekt nicht freigegeben (Meldung an den Lead). Ein lokaler Anbieter belegt
  die Grafikkarte (Regel 3: bis zur Lauf-Schlange für die Grafikkarte gesperrt). Regel 14 – Anbieter mit der installierten
  Claude-Code-Version noch nicht geprüft: Die AMW startet die Negativprobe mit diesem Anbieter (einmal je Anbieter und Version),
  andere Pakete laufen weiter.
- **Negativprobe je Anbieter:** die neun Schritte nach außen wie bei einer neuen Version, mit dem ersten Modell des Anbieters,
  dazu „Schlüssel unsichtbar“: Ein Bash-Kind des Arbeiters zeigt seine Umgebung; der Schlüssel (nur im Speicher gelesen) darf
  weder im Protokoll noch im Platz noch in der `--settings`-Datei stehen. Bestanden → Pakete mit dem Anbieter starten.
  Nicht bestanden → nur dessen Pakete starten nicht (kein Wartungsmodus), Frage an Lead und Mensch mit dem Bericht.
- **Restrisiko** (steht in jedem Bericht): Von Arbeitern geschriebener Code läuft in Prüfung C unter dem Benutzerkonto und
  könnte Dateien außerhalb lesen, auch eine Schlüsseldatei; die Geheimnis-Muster im Diff-Tor bleiben die Bremse.

## Eignungstabelle: gemessen statt geschätzt (A1930, TH159)

**Wozu:** Welches Modell mit welchem Denkaufwand passt zu welcher Arbeit, misst die AMW selbst – und empfiehlt danach.

- **Messung (nichts von Hand):** je erledigter Arbeit eine Zeile. p-Pakete: Modell und Effort des Pakets, Kosten und Dauer aus
  den Kosten-Ereignissen; „ohne Nacharbeit“ nach F5362: erste Entscheidung E7, bei Test-Paketen auch E4 mit Annahme des Leads
  ohne Änderung – ein zweiter Lauf (E5), die Abgabe an einen interaktiven Agenten (E8) oder jedes andere Ende zählt als
  Nacharbeit. Interaktive Aufgaben: Modell und Stufe der Sitzungen, die die Aufgabe am meisten gekostet haben, aktive Zeit,
  ohne Nacharbeit = keine rote Prüfung. Zelle = Gruppe der Art × Größe; der Pakettyp steht nur zur Anzeige dabei.
- **`amw empfehlung tabelle`:** je Zelle und Modell/Effort Anzahl, Anteil ohne Nacharbeit, Median der Kosten und der Dauer;
  die Zeile, die die Empfehlung nimmt, ist markiert, mit Herkunft (vom Projekt gesetzt, gemessen, Startwert).
- **Regel:** Unter den Paaren mit mindestens 5 Aufgaben gewinnt der höchste Anteil ohne Nacharbeit, bei Gleichstand die
  niedrigeren Median-Kosten; es ersetzt den Startwert nur, wenn es mindestens so gut ist wie der gemessene Startwert. Ein im
  Projekt gesetzter Wert (`amw projekt einstellen empfehlung=…`) geht vor. Fable ist nie eine Empfehlung.
- **Startwerte (TH159):** klein Sonnet medium, normal Opus medium, schwer Opus high; heikle Arten eine Stufe höher (Opus high).

## Neue Claude-Code-Version ohne Stillstand (seit 1.154.0)

**Wozu:** 21.11.: Zweimal stand S8 je etwa eine Stunde still, weil sich Claude Code aktualisiert hatte und die geprüften
Versionen eine Konstante im Code waren (A1890, A1905). Updates kommen jederzeit (W2443).

Geprüft ist eine Version aus dem Grundbestand `arbeiter.GEPRUEFT` oder mit dem Ereignis `claude_version_geprueft` (Version,
Dokument, Lauf; gilt für alle Projekte dieses PCs). Ist die installierte Version (`claude --version`, höchstens alle 5 min
gefragt) nicht geprüft, startet kein Arbeiter (Startregel 11, vorübergehend). Der Disponent stößt einmal je Version die
Negativprobe an (`amw-versionsprobe.py`, losgelöst, angemeldet in der Lauf-Schlange, Haiku): dieselbe Probe wie
`test_arbeiter.test_echt_ausserhalb_abgelehnt` (`versionsprobe.probe`/`auswerten`).
- **bestanden** (jeder der neun Schritte nach außen – Haupt-Checkout, fremder Ordner, `~/.claude/settings.json`,
  `git diff --output`, `git -C ..`, python-Umweg, `.git/config` ändern, `.claude/settings.local.json`, `CLAUDE.md` – mit
  mindestens einem abgelehnten Aufruf, keiner durchgelassen, `innen.txt` im Platz angelegt, `.git/config` unverändert):
  Version eingetragen, Bericht als Dokument (mit Tabelle je Schritt), Meldung an den Lead „Claude Code X geprüft und
  freigegeben, D…“, wegen der Version abgebrochene Pakete wieder startklar. Hat das Modell einen Schritt übersprungen, hat
  niemand gesehen, ob er gesperrt ist: einmal neu, dann „unklar“ (P325).
- **Gegenleser (A1914):** In derselben Probe läuft danach der Gegenleser der Themen mit seinen Flags (nur Glob/Grep/Read,
  `--restricted`): eine fremde Datei lesen, `~/.claude/settings.json` lesen und im fremden Ordner suchen muss je abgelehnt
  werden, `innen.md` im eigenen Ordner lesen muss gehen. Es gilt das schlechtere der beiden Ergebnisse; der Bericht hat dafür
  einen eigenen Abschnitt.
- **nicht bestanden oder unklar**: Wartungsmodus an, Frage an Lead und Mensch mit dem Bericht. Von Hand freigeben:
  `amw claude freigeben X --grund …` (Lead oder Mensch, nicht aus einer Agenten-Sitzung); den Wartungsmodus hebt danach der
  Lead auf.

Bricht ein Lauf trotzdem wegen der Version ab (Update zwischen Prüfung und Start), ist das E1n „Version“ – es zählt nicht zur
Fehlserie (Regel 9). Stand: `amw claude status`.

## Halt beim Wochenlimit (seit 1.149.0)

Erreicht der Verbrauch des Wochenlimits die Schwelle `limit_halt` (Prozent, Vorgabe 95; 0 oder leer = aus), hält die AMW
alle Coder des Projekts an – jeden Agenten außer den Leads, der nicht ausgeschaltet ist, also auch einen Co-Entwickler (etwa
den Chat-TL nach dem Lead-Wechsel). Gemessen wird wie bei Startregel 8. Der Lead selbst bekommt keinen Halt (er muss aufheben
können), aber in seiner Meldung steht: auch er fängt nichts Neues an, nur noch Weckrufe, bei denen sonst etwas kaputtginge.
Jeder bekommt ein STOPP: laufende Arbeit sauber beenden (Zwischenstand committen, Übergabe-Notiz), nichts Neues anfangen;
hart beendet wird nichts. Lead und Mensch bekommen eine Meldung. Aufheben: `amw weiter` (Lead oder Mensch) – dann kommt der
Halt in derselben Woche nicht wieder. Sonst hebt die AMW ihn selbst auf, sobald der Verbrauch nach dem Wochenwechsel unter der
Schwelle liegt oder die Einstellung aus ist. Einstellen: Workbench › Einstellungen › Projekt oder
`amw projekt einstellen limit_halt=<Prozent>` (Lead oder Mensch).

**Seit A1925 für den ganzen PC:** Das Konto ist eines. Es gilt die PC-Einstellung `amw pc einstellen limit_halt=<Prozent>`
(Vorgabe 95, 0 = aus) für alle Projekte – strenger stellen dürfen Lead und Mensch, ausschalten oder lockern nur der Mensch
im eigenen Terminal. Ein Wert im Projekt gilt nur,
wenn er strenger (kleiner) ist; abschalten kann ein Projekt den Halt nicht mehr allein.

### Pause für alles (A2042, D1531 §1/§7)

- **Schalter:** `amw pause an [--bis HH:MM|2h|90min] [--grund …]` · `amw pause aus` · `amw pause zeige` (Lead oder Mensch; der
  Mensch nur im eigenen Terminal oder in der Workbench, `/api/pause`). „An“ setzt einen Halt für alle (stopp: Arbeit sauber
  beenden, nichts Neues) – damit startet und rückt auch kein Lauf der Schlange nach – und die Wächter-Pause (keine neuen
  Headless-Pakete). Was läuft, wird nicht abgebrochen.
- **Ende:** Mit `--bis` gilt der Halt ab dann nicht mehr (`sperre.bis_utc`), die Wächter-Pause endet, und der Dienst hebt die
  Pause in der nächsten Runde auf: alle bekommen „WEITER: Pause vorbei“ (`pause_aus`).
- **Rückmeldung je Agent** (`amw pause zeige`, `/api/pause`): „wird pausiert“ (stopp noch nicht zugestellt), „beendet Schritt“
  (arbeitet noch, Lebenszeichen jünger als 2 min), „läuft zu Ende“ (steht selbst, aber sein Lauf oder Headless-Paket läuft noch, A2043), „pausiert“ (steht oder keine Sitzung); Headless-Pakete und Läufe, die schon
  liefen: „läuft zu Ende“, wartende Läufe: „wartet“.

## Disponent über Projekte (A1925, W2449)

**Wozu:** Mehrere Projekte teilen sich einen PC und ein Konto. Der Mensch legt fest, welches Projekt zuerst dran ist.

- **Rangfolge:** `amw pc einstellen projekt_rang=AMW,GlassWorld,LayerIT` – nur der Mensch im eigenen Terminal (nicht aus einer
  Agenten-Sitzung, auch nicht der Lead). Der Disponent geht die Projekte in dieser Reihenfolge durch, innerhalb eines Projekts
  in der berechneten Reihenfolge (A2041: dieselbe, die Planung und Lagebild anzeigen – `reihenfolge.berechnen`: aktiver
  Meilenstein zuerst, dann der längste Rest-Pfad, dann Rang und Nummer; `amw waechter reihenfolge` nennt den Platz). Nicht genannte Projekte kommen danach (nach Nummer); ohne Einstellung wie bisher.
- **Warum dieses jetzt (A2047):** Bei jedem Headless-Start speichert der Disponent den Grund (`headless_start`: Platz in der
  berechneten Reihenfolge mit deren Grund, Arbeitsplatz, „von Hand gestartet (…)“ beim Handstart) – wie `verteilt` bei
  Fenster-Agenten. `disponent.warum` liefert den jüngsten der beiden je Paket (für Lagebild und Paketansicht).
- **Gemeinsame Grenze:** `amw pc einstellen plaetze_pc=<n>` (Lead oder Mensch) – höchstens so viele p-Arbeiter gleichzeitig über
  alle Projekte (gezählt: läuft, abgegeben, Prüfung C; ein Paket in „bereit zum Merge“ arbeitet nicht mehr). 0 = keine
  Grenze. Ist sie erreicht, wartet ein Paket sichtbar (Regel 4: „wartet auf einen Platz (PC: 2 von 2 belegt: AMW A…,
  GlassWorld A…)“); ein frei werdender Platz geht an das Projekt weiter vorn. Die Platz-Ordner bleiben je Projekt.
- **Projekt-Schalter (A1926, D1304 §5):** `amw projekt schalter <Projekt> probe | an | aus` – ohne Eintrag an (wie bisher).
  - **probe** (Lead oder Mensch): Kopie der Projektdaten (Sicherung `schalter-probe-<projekt>-<zeit>.db` neben der Datenbank,
    bleibt liegen) und Zählprobe – je Tabelle des Projekts Zeilen, Nummern und Verweise auf eigene Ziele, live und in der
    Kopie. Bestanden, wenn alles gleich ist („Nummern bleiben“); Verweise auf andere Projekte leert die Kopie bewusst, sie
    stehen als Hinweis im Bericht (Dokument). Nur ein ausgeschaltetes Projekt steht danach auf probe (keine p-Starts);
    eins ohne Eintrag (wie die AMW) oder mit an bleibt an – eine Probe hält nichts an.
  - **an** (nur der Mensch im eigenen Terminal, nur nach bestandener Probe): p-Pakete und Themen-Ablauf (Gegenlesen) frei.
  - **aus** (nur der Mensch): keine p-Starts (Regel 12), kein automatisches Gegenlesen. Nichts wird gelöscht.
  - `amw projekt einstellen schalter=…` geht nicht – nur über den Schalter mit Probe.
- **Wochenlimit:** Regel 8 misst das ganze Konto – ist es erreicht, startet in keinem Projekt etwas; `limit_halt` siehe oben.
- **Messung:** `amw pc` zeigt Rangfolge, laufende p-Arbeiter und je Projekt Schalter, Plätze und Kosten dieser Woche. Montags
  bekommt der Mensch einen Wochenbericht (Kosten und Pakete der Vorwoche je Projekt) – nur, wenn etwas gelaufen ist.
- Die Lauf-Schlange (schwere Läufe) ordnet weiter nach `vorrang`; die Rangfolge dort kommt mit Mehrprojekt 6.

## Fertig-Quelle und Prüfquellen: die AMW schließt selbst (A1938, K2, TH155/TH165)

**Wozu:** Agenten liefern nur Fakten (B2907); abschließen, abhaken, Beleg und Zusammenfassung schreibt die AMW.

- **Fertig-Quelle je Aufgabe:** `amw aufgabe neu|aendern N --fertig-wenn …` (Lead, Mensch oder Bearbeiter; das Neueste gilt).
  - `commit` – wie bisher: die Auslieferung setzt die Aufgabe fertig.
  - `thema TH<n>` – fertig, sobald das Thema freigegeben ist (auch durch Co und Lead).
  - `frist <Tage> nach <Version>` – fertig, wenn so viele Tage nach dem Release vergangen sind ohne Fehler: kein Revert
    eines ihrer Commits in main (Betreff „A<nr>…“), keine neue „behoben“-Aufgabe mit Verweis, keine rote Prüfung.
  - `ja` – ein Urteil: nie automatisch (Abnahme über den Meilenstein).
  Beleg und Zusammenfassung schreibt die AMW. Ist noch ein Kriterium ohne Quelle offen, schließt sie nicht, sondern fragt den
  Lead einmal „bereit zur Abnahme – Ja des Leads fehlt für: …“; nach seinem Ja (`amw aufgabe kriterium N nr`) schließt sie.
  Fehlt noch ein Fakt eines Kriteriums mit Quelle, wartet sie.
- **Prüfquelle je Kriterium:** `amw aufgabe kriterium N nr --quelle …` (leer entfernt sie). Seit Beginn der Aufgabe zählt:
  `lauf <Befehl>` (ein Lauf der Lauf-Schlange zur Aufgabe mit genau diesem Befehl, rc 0 – der Dienst führt nie selbst etwas
  aus), `pruefung` (grüne Prüfung), `thema TH<n>` (freigegeben), `tests <N>` (Lauf mit rc 0 und „Ran ≥ N tests“). Ohne
  Quelle bleibt ein Kriterium ein Ja des Leads.
- Der Dienst prüft das höchstens alle 15 Minuten; Ereignisse `fertig_quelle`, `kriterium_abgehakt`. Ohne Schemaänderung.

## Meilenstein automatisch: bereit zur Abnahme, Themen, Verweise (A1939, K3, TH155)

- **Bereit zur Abnahme:** Eine Aufgabe mit `--fertig-wenn ja` hängt an einem Urteil – die AMW schließt sie nie selbst. Steht
  ihr Ergebnis (der Bearbeiter meldet `amw aufgabe bereit N`, eine grüne Prüfung oder ein Ergebnis/Bericht zur Aufgabe, seit
  Beginn und nach dem letzten „Zurück“), steht sie unter „Für dich“. **Ein Ja genügt** (Knopf „Ja“ am PC oder
  `amw aufgabe abnehmen N`; der Mensch oder der Lead, nie der Bearbeiter selbst): die AMW hakt die offenen Kriterien ohne
  Prüfquelle mit „Ja von …“ ab, setzt fertig und schreibt Beleg und Zusammenfassung. „Zurück“ braucht einen Grund und geht
  an den Bearbeiter. Ereignisse `zur_abnahme`, `abnahme_ja`, `abnahme_zurueck`.
- **Meilenstein fertig:** wie bisher, wenn alle Aufgaben fertig oder verworfen sind (`meilenstein_fertig = automatisch`) – aber
  nur ohne Urteil. Endet er mit einem Urteil (Abnahme-Text mehr als „alle Pakete fertig“: Vorführung, Bericht, Probe), bleibt er
  offen und ist „bereit zur Abnahme“: Abschlussbericht und eine Meldung an Lead und Co (bzw. den Menschen) je Stand, Ereignis
  `bogen_bereit_abnahme`; fertig wird er erst mit dem Ja zum Abschluss (`amw bogen freigeben N --art abschluss`, A2002).
- **Themen statt Spezifikation:** Der Meilenstein zeigt die Themen seiner Aufgaben (`amw aufgabe aendern N --thema TH<n>`)
  mit Status. Neue Meilensteine haben keine Spezifikation mehr; `amw bogen neu` verlangt sie nicht und der Plan-Check meldet
  nichts mehr dazu. Alte Meilensteine behalten ihre Spezifikation als alten Bestand (lesbar, `amw spec …`).
- **Verweise:** Ziel und Abnahme dürfen `TH<n>` und `D<n>` nennen; Seite und `amw bogen zeigen` zeigen dazu Titel und geltende
  Fassung („TH12 Marktlage · freigegeben (Fassung 3)“, „D1258 Konzept · Fassung 15“).

## Reihenfolge, Timeline und „Jetzt starten“ (A1941, K5, TH164)

**Wozu:** Die AMW rechnet die Arbeitsreihenfolge selbst; der Lead greift nur mit Grund ein.

- **Dauer je Paket:** gemessen (Median aus der Eignungstabelle für Art-Gruppe × Größe, ab 3 Messungen) → geschätzt
  (`schaetzung_h`) → Vorgabe je Größe (S 1 h, M 3 h, L 8 h, XL 20 h; ohne Größe 3 h).
- **Reihenfolge:** aktiver Meilenstein vor geplantem vor „ohne Meilenstein“ (dann nach Nummer) · was läuft vor startklar vor
  wartend · längerer Rest-Pfad zuerst (kritischer Pfad über „nach“) · Rang nur noch bei Gleichstand · Nummer.
  `amw bogen reihenfolge [N]` zeigt sie mit Grund, Dauer und Prognose (P50/P85).
- **Zeitplan (A2045):** `amw bogen zeitplan [N]` bzw. `/api/zeitplan` legt die Pakete in dieser Reihenfolge auf ihre
  Ressourcen – Headless auf die Arbeitsplätze (so viele gleichzeitig wie Plätze), Fenster-Pakete auf ihren Agenten (eins nach
  dem anderen), dazu die offenen Vorgänger. Ergebnis je Paket: geplante Start- und Endzeit, Dauer, „gleichzeitig mit“ (gleiche
  Startminute), „nach A…“ und „+n min“, wenn Laufendes länger dauert als geplant (es endet dann „jetzt“, die Pakete dahinter
  rücken mit). Ohne Agent bzw. ohne Platz steht das dabei. Nur Rechnung bei jedem Abruf; „nie gleichzeitig“ und „gleiche
  Ressource“ rechnet er nicht.
- **Prognose messen (A2046):** Die Aufsichtsrunde des Dienstes hält je Paket beim Start einmal die Dauer fest, mit der Reihenfolge
  und Zeitplan rechnen (`prognose_start`), und beim Ende das Ist von Beginn bis fertig (`prognose_ist`, mit Faktor Ist/Schätzung)
  – für jeden Abschlussweg. Fehlt der Start, gilt die Schätzung beim Ende. `amw messung --prognose [--seit …]` zeigt die
  Trefferquote (im Rahmen 0,67–1,5×), den Median des Faktors und beides je Quelle.
- **Wer ihr folgt:** die Liste je Agent (`amw liste`, das laufende Stück bleibt vorn), das Verteilen an freie Agenten und die
  Prognose (Warteschlangen je Bearbeiter).
- **Handordnung nur mit Grund:** `amw liste ordnen <Agent> A… --grund …` bzw. `amw liste schieben A… --grund …` (schieben ohne
  Grund nur als Verfeinerung einer geltenden Handordnung). „Dazwischen“ des Menschen und „später“ in der Workbench sind
  Handordnungen mit ihrem Text. Sie gilt, bis sich die offene Liste ändert; dann ordnet wieder die AMW und meldet das dem
  Lead einmal. Ereignisse `liste_hand`, `liste_hand_ende`.
- **Jetzt starten:** `amw bogen starten N` (Lead oder Mensch): prüft je Paket die Pflichtfelder (Ziel = Auftrag, Thema,
  Fertig-Quelle; bei Art p Abnahme-Befehl und Bereiche), setzt den Meilenstein aktiv, p-Pakete ohne Lücke auf startklar,
  merkt den Plan-Stand (P50 je Paket und Meilenstein, Ereignis `plan_stand`) und lässt einmal verteilen. Pakete mit Lücke
  bleiben Entwurf; die Meldung an den Lead nennt das fehlende Feld.
- **Abweichung:** `amw bogen zeigen N` nennt „Abweichung seit dem Start: ±n Tage“ (P50 jetzt gegen den Plan-Stand); die
  Planungsdaten der Workbench tragen `abweichung` je Meilenstein und `platz` je Paket (für die Ansichten aus K6).
- Ohne Schemaänderung.

## „Macht gerade“ abgeleitet (A1953, TH155 Pkt 7)

**Wozu:** Die eigene Angabe (`amw taetigkeit`) hatte Vorrang und wurde beim Start einer neuen Aufgabe nicht ersetzt, solange sie
jünger als 2 h war – die Kachel zeigte stundenlang eine erledigte Aufgabe oder einen längst beendeten Lauf.

- **Was geschieht (`amw/gerade.py`):** die AMW leitet ab – laufender Lauf des Agenten (nie ein beendeter oder abgebrochener) ›
  seine zuletzt begonnene laufende Aufgabe › die Aufgabe aus seiner letzten Meldung, nur wenn sie nicht fertig oder verworfen
  ist (A1989). Läuft ein Lauf zu einer Aufgabe, steht beides da. Die eigene Angabe ergänzt nur (nicht älter als die Quelle,
  keine andere Aufgabe); ohne abgeleitete Quelle ist sie allein die Angabe. Nennt sie einen Lauf L…, der nicht mehr läuft,
  fällt sie weg (A1989; ein Lauf in der Schlange zählt nicht als beendet). `aufgabe start`/`lauf start` ersetzen eine Angabe, die zu einer anderen Aufgabe gehört.
- **Quelle und Alter:** jeder Wert trägt Quelle und Zeit (Workbench: Übersicht des Agenten und Tooltip der Kachel;
  `amw agent liste`: „macht: … (Aufgabe, seit 20 min)“).
- **Veraltet:** ohne Puls der Sitzung (Hook, Statuszeile, Ereignis, Angabe) seit 30 min steht „veraltet?“; ist die letzte
  Sitzung beendet, ruht oder tot, gibt es kein „macht gerade“. Chats und Agenten ohne Sitzung haben keine Hooks – dort kein Urteil.

## Startwissen und gebündelte Befehle (A1943, K9)

**Wozu:** Interaktive Agenten brauchten je Paket 10–20 Einzelbefehle und lasen sich jedes Mal neu ins Projekt ein.

- **Bereichs-Wissen:** schließt eine Aufgabe, hält die AMW ohne KI fest, welche Dateien ihre Commits in main berührt haben
  (`git log --grep "^A<n>[: (]"`) und einen Satz dazu (Versionshinweis, sonst Zusammenfassung) – Ereignis `bereich_wissen`.
- **Startwissen:** beim Start (`amw aufgabe start`, `amw paket holen`) die letzten 3 Einträge je Datei des Dateibereichs (sonst
  der Dateien, die Titel oder Auftrag nennen) und die Projekt-Landkarte (Ordner, je Modul die erste Docstring-Zeile; je
  main-Stand zwischengespeichert neben der Datenbank). Festes Budget 1500 Zeichen, gekürzt wird zuerst die Landkarte;
  Größe als Ereignis `startwissen`.
- **`amw paket holen [N]`:** nächste startklare Aufgabe (oder N) starten, Auftrag, Kriterien, Thema und Startwissen zeigen;
  mit der Projekt-Einstellung `baum_wurzel` (nie im Projektordner) Zweig `a<N>` und Arbeitsbaum `<baum_wurzel>/a<N>` auf main
  anlegen – nur anlegen, nie entfernen; ohne Einstellung steht der Befehl dafür da.
- **`amw paket fertig N --sha … --punkte …`:** Testmodule zu den geänderten Dateien, Prüfbitte an den Prüfer der Aufgabe (sonst
  den Lead), Aufgabe wartet auf ihn; Ereignis `k9_paket` mit der Zahl der amw-Befehle seit Beginn (gezählt in `befehle.jsonl`
  neben der Datenbank, nie Inhalte).

## Stil-Prüfung als Automatik (A1973, TH156)

**Wozu:** Marcel W2464: „Jedes Mal fallen wir in die Falle.“ Die Stil-Regeln wurden als Gebot vergessen.

- **Auslöser:** eine Prüfbitte, deren Stand Sichtbares ändert (wie die Bild-Pflicht) und an deren Aufgabe Bilder hängen; neu
  anstoßen mit `amw pruefung stil <P>` (Prüfer, Lead, Mensch). Aus mit `themen_gegenlesen=aus`.
- **Was geschieht (`amw/stil.py`, `amw-stil.py`):** ein losgelöster Prozess meldet einen Lauf an und lässt einen frischen
  `claude -p` (nur Lesen, `--restricted`, Modell aus `themen_gegenlesen`) das Stil-Thema des Projekts (`thema.stil = 1`,
  geltende Fassung), die Punkte der Prüfbitte und die Bilder der Aufgabe lesen. Er urteilt je Regel 1–9 NUR über die Änderung
  (erfüllt / verstößt / nicht prüfbar); was schon vorher so war, steht getrennt unter „alter Bestand“ und zählt nicht.
- **Ergebnis:** Dokument (bericht) an der Aufgabe, Meldung an den Prüfer „P… Stil: 9/9 erfüllt“ bzw. „Stil: 2 Verstöße – R3,
  R7“, Ereignis `stil_befund` mit Kosten. Grün auf eine Prüfung mit Verstoß nur mit `--bemerkung`. Geht der Lauf schief, bekommt
  der Prüfer das als Meldung und prüft selbst – die Prüfbitte gilt trotzdem.

## Sprachprüfung jeder Prüfbitte (A2004, TL #31260)

**Wozu:** Befunde sollen fertig vorliegen, wenn der Prüfer anfängt – Automatismus statt Gebot. Bis dahin lief pyright nur in
Prüfung C der p-Pakete; interaktive Prüfbitten bekamen keine Sprachprüfung.

- **Auslöser:** jede Prüfbitte (`amw pruefung bitte`), wenn die Projekt-Einstellung `sprachpruefung` es will: `auto` (Vorgabe:
  nur mit `pyrightconfig.json` im Projektordner) | `pyright` | `aus`.
- **Was geschieht (`amw/vorpruefung.py`, `amw-vorpruefung.py`):** wie beim Stil-Leser ein losgelöster Prozess, der sich als
  leichter Lauf der Lauf-Schlange anmeldet. Er holt die Zweige des Projekts in ein eigenes Prüf-Repo (in einem eigenen
  Arbeitsordner, nie im Baum des Bearbeiters), checkt genau den SHA der Prüfbitte und seinen Start-Commit frisch aus – A2057: den
  merge-base mit main zum Zeitpunkt der Prüfbitte (gemerkt in `sprache_angestossen`), auch wenn main inzwischen vorgerückt oder
  der Stand schon gemergt ist – und
  fährt die vorhandene Sprachprüfung von Prüfung C (`pruefung_c.sprachpruefung`: pyright, nur neue Fehler gegen den
  Start-Commit). Kein Modell, keine Kosten außer PC-Zeit.
- **Ergebnis:** Meldung an den Prüfer „P… Sprachprüfung: keine neuen Fehler“ bzw. „… n neue Fehler“ (mit Liste) bzw. – ist der
  Start-Commit der geprüfte Stand selbst – „kein Vergleich möglich“ (nie „keine neuen Fehler“ ohne Vergleich), Ereignis
  `sprache_befund`, und an der Prüfbitte in `amw pruefung zeige`. Fällt etwas aus – Start, Lauf-Schlange, Checkout, pyright fehlt,
  Zeit um –, lautet der Befund „Sprachprüfung nicht gelaufen: <Grund>“; die Prüfbitte gilt trotzdem, still fehlt nichts.

## Fragen-Topf (A1945, K10)

**Wozu:** Jede Frage an den Menschen kam einzeln als Push; blieb eine liegen, merkte niemand, was an ihr hängt.

- **Bündeln:** Fragen an den Menschen gehen höchstens alle `fragen_takt_h` Stunden (Projekt-Einstellung, Vorgabe 4; 0 = sofort)
  als ein Push „n neue Fragen an dich“. Sofort geht es, wenn eine Frage blockiert: als blockierend gestellt, oder ein Agent, der
  an ihr hängt, hat sonst nichts Startklares – dann gehen alle wartenden mit.
- **Was hängt:** `amw frage liste` zeigt je Frage „hängt: A12 (CC1), …“ – die Aufgaben mit offenem Wartegrund F<n>.
- **Frist:** ist eine Frage länger als `fragen_frist_h` (Vorgabe 24) offen, meldet die Dienst-Runde das einmal dem Lead („F…
  seit 25 h ohne Antwort“, mit allem, was hängt) und sagt jedem hängenden Agenten, womit er weitermacht (seine nächste startklare
  Aufgabe). Die AMW verwirft nichts und nimmt keine Empfehlung an. Ereignis `frage_frist` (einmal je Frage).
- Die Anzeige unter „Für dich“ kommt erst nach einer Kleinprobe (TH156).

## Arbeitsliste je Agent (seit 1.12.0)

**Wozu:** Wer vieles gleichzeitig anfängt, macht wenig fertig. Jeder Agent arbeitet eine geordnete Liste von oben nach
unten ab, eins nach dem anderen. Der Umfang darf groß sein.

- **Reihenfolge:** Feld `rang` der Aufgabe. Der Lead ordnet mit `amw liste ordnen <Agent> A12 A15 …` (der Rest folgt
  dahinter, Aufgaben aus dem Pool werden zugeteilt) und `amw liste schieben A15 --vor A12 | --nach | --pos N | --oben |
  --unten`. Ansehen: `amw liste [Agent]`, Workbench › Aufgaben › Listen.
- **Pool:** neue Ideen ohne Platz in einer Liste (`aufgabe neu … --pool` oder `aufgabe pool N`). Der Lead sortiert ein.
- **Warten füllen:** Wartet die Aufgabe in Arbeit mit Grund (Prüfung, Lauf, Frage), darf der Agent die nächste nehmen.
- **Das laufende Stück steht fest (seit 1.54.0):** Läuft eine Aufgabe, lässt sich keine zweite starten – die AMW weist
  den Start ab und nennt die Auswege: fertig machen, mit Grund warten lassen, oder der Mensch schiebt bewusst etwas
  dazwischen. Ordnen, Schieben und neue Aufgaben landen frühestens direkt hinter dem laufenden Stück. Wird eine obere
  Aufgabe wieder frei, meldet die AMW: „als Nächstes dran, sobald A… fertig ist“. Früher stellte der Start einer oberen
  Aufgabe die laufende still zurück – das entfällt.
- **Neues kommt in den Eingang (seit 1.55.0):** Legt jemand eine Aufgabe für einen Agenten an, der gerade ein Stück in
  Arbeit hat, landet sie im Eingang (früher „Pool“) statt in seiner Liste. Der Lead plant sie mit `amw liste ordnen`
  ein – frühestens hinter das laufende Stück. Wer sie gleich einplanen will, legt sie mit `--sofort` an. Der Leitstand
  zeigt „n im Eingang“.
- **Dazwischenschieben (seit 1.56.0)** entscheidet nur der Mensch: in der Workbench bei der Aufgabe „Dazwischenschieben“
  (mit Grund) oder `amw aufgabe dazwischen <nr> --grund …`. Das laufende Stück wartet dann auf die eingeschobene
  Aufgabe und kommt danach von selbst wieder dran; der Agent bekommt die Bitte, seinen Stand zu sichern. Im Verlauf
  steht „unterbrochen“. Der Lead kann es vorschlagen: Derselbe Befehl stellt dann eine Ja/Nein-Frage an den Menschen,
  „Ja“ führt es aus.
- **Aufträge mitten im Stück (seit 1.56.0):** Ein Auftrag an einen Agenten, der gerade ein Stück in Arbeit hat, wird
  zugestellt, weckt ihn aber erst, wenn das Stück fertig ist oder wartet – außer der Auftrag gehört zum laufenden
  Stück (`--aufgabe <nr>`). Fragen, Antworten, Freigaben und Meldungen wecken wie bisher.
- **Aufgaben des Menschen** bleiben frei: Für den Bearbeiter „Entwickler“ gilt keine dieser Sperren.
- **Fertig:** Ist eine Aufgabe fertig oder verworfen, weckt die AMW mit der nächsten startbaren Aufgabe der Liste. Die
  Leerlauf-Prüfung bleibt als Netz.

## Design-Dokument je Thema und Projekt-Stil (seit 1.14.0)

**Wozu:** Je System (Netz, Rezepte, Maßstab, Aufträge, UI, Stil …) gibt es eine Wahrheit „gilt jetzt“, statt dass sich
widersprechende Beschlüsse stapeln.

- Jeder Beschluss gehört zu einem **Thema** (`beschluss --thema`, Pflicht, sobald es Themen gibt; TH-Nummer oder
  eindeutiger Namensanfang; neues Thema mit `--neues-thema`). Beim Update werden die vorhandenen Themen der Beschlüsse
  übernommen.
- Die **Seite** eines Themas (`amw thema zeige TH12`, Workbench › Wissen › Themen) zeigt die gepflegte Zusammenfassung und
  alle geltenden Beschlüsse, darunter die überholten. Sie entsteht aus den Daten und kann nicht veralten.
- Die **Zusammenfassung** schreibt der Pfleger (`thema einstellen TH12 --pfleger X`, `thema pflegen TH12 --text-datei …`).
  Jede Fassung bleibt erhalten. Ein neuer Beschluss im Thema markiert sie als „veraltet seit B…“ und weckt den Pfleger,
  bis er sie anpasst oder bestätigt (`thema bestaetigen`). Ohne Pfleger erinnert der Hinweis den, der den Beschluss
  anlegt.
- **Aufräumen:** `beschluss neu` nennt die geltenden Beschlüsse desselben Themas („ersetzt B… einen davon?“). Werkzeuge:
  `beschluss ueberholt B12 --durch B30`, `beschluss unklar B12`, `beschluss thema B12 --thema …`. Die Frage-Prüfung
  findet nur geltende Beschlüsse.
- **Projekt-Stil:** Ein Thema kann der Stil sein (`--stil`, es gibt höchstens einen). Bilder hängen als Dokumente daran
  (`thema dokument TH12 --dokument D5`). Jeder Agent sieht im Pflicht-Kontext „Projekt-Stil: amw thema zeige …“;
  Grafik-Arbeit richtet sich danach, eine Abweichung ist eine Frage.

### Gegenlesen frischer Agenten (A1914, D1304 v12 §4)

**Wozu:** Eine neue Fassung soll erst zum Menschen, wenn ein unbefangener Leser sie gegen die Beschlüsse gelesen hat – ohne
dass der Pfleger daran denken muss.

- **Auslöser:** `thema pflegen` eines Agenten (nicht der Mensch, nicht `bestaetigen`). Je Runde ein Gegenleser: Kam seit der
  letzten Handlung des Menschen (freigeben, zurück, bearbeiten) schon einer, ist die neue Fassung die Antwort darauf und geht
  ohne zweites Gegenlesen weiter.
- **Was läuft:** ein losgelöster Prozess (`amw-gegenlesen.py`) meldet sich als leichter Lauf in der Lauf-Schlange an und startet
  einen frischen `claude -p` wie ein Arbeiter, aber nur lesend: Werkzeuge Glob/Grep/Read, `--restricted`, dontAsk, kein Bash,
  kein Schreiben, kein Netz, kein Connector, in einem leeren eigenen Ordner mit genau `thema.md`, `beschluesse.md` und – falls es
  eine gibt – `freigegeben.md`. Die init-Prüfung des Arbeiters gilt (Modell, Werkzeuge, geprüfte Claude-Code-Version); ein
  Werkzeug außerhalb der Liste beendet den Lauf.
- **Danach:** Einwände als Auftrag an den Pfleger (ohne Einwände eine Meldung), mit Modell, Kosten und Lauf. Kosten stehen im
  Ergebnis des Laufs und im Ereignis `thema_gegengelesen`. Ein Fehler wird gemeldet und hält das Thema nicht auf.
- **Für den Menschen:** solange er liest, Status „in Arbeit“ mit „wird gegengelesen · seit HH:MM“ (Liste und Thema), das Thema
  ist nicht unter „Für dich“; danach „wartet auf dich“ und das Ergebnis zum Aufklappen. Endet ein Gegenleser nicht, zählt er
  nach 2 h nicht mehr.
- **Einstellung:** `themen_gegenlesen` = opus (Vorgabe seit A1930, Opus/high nach TH159) | haiku | sonnet | aus – Lead oder Mensch. Rollen Gliederung und Machbarkeit
  sind vorbereitet (`gegenlesen.ROLLEN`), aber nicht gebaut. Tests stoßen nie einen echten Gegenleser an (`AMW_GEGENLESEN_AUS`).

### Freigabe durch Co-Entwickler und Lead (A1937, B2913)

- **Einstellung `thema_freigabe`:** mensch (Vorgabe) | co+lead – setzen Lead oder Mensch (A1951, W2460/B2914); stellt der
  Lead um, steht es im Protokoll (Ereignis `einstellung_lead` mit Grund). Sie gilt für Themen und das Konzept-Ja (A2030).
- **Freigaben je Meilenstein (A2032):** `grobplan_freigabe` (Grob-Freigabe und Grobplan-Ja), `feinplan_freigabe` (Plan),
  `abschluss_freigabe` (Abschluss) – je mensch (Vorgabe) | co+lead, gleiche Rechte und Protokoll wie `thema_freigabe`.
  Bis 1.175 galt `thema_freigabe` auch für Meilensteine; jetzt gibt sie der Mensch frei, bis er die Art umstellt.
  Danach richten sich auch „für dich“, „wer ist dran“ im Projektweg und die Meldung „bereit zur Abnahme“.
- **co+lead:** Co-Entwickler und Lead geben je ihr Ja zur aktuellen Fassung (`amw thema freigeben TH…` aus ihrer Sitzung).
  Mit beiden Ja ist das Thema freigegeben (Ereignis von der AMW, mit beiden Namen); der Mensch bekommt eine Info. Eine neue
  Fassung braucht neue Ja. Der Mensch gibt weiter selbst frei und holt jederzeit zurück.
- **Nur der Mensch:** Themen, die Löschen, Kosten, Schema oder Außenwirkung betreffen, bleiben beim Menschen (G12):
  `amw thema nur_mensch TH…` (Pfleger, Lead oder Mensch), aufheben `amw thema nicht_nur_mensch TH…` (nur der Mensch).
- **Anzeige:** `amw thema status` und die Seite zeigen, wessen Ja noch fehlt („Ja fehlt noch: Lead“) bzw. „Gibst nur du frei“.
  Die Tor-Zeile zählt diese Freigaben wie die des Menschen.
### Planer: Grobplanung aus Themen (A1940, K4, D1304 v12 §2)

**Wozu:** Aus einem freigegebenen Thema entstehen Meilensteine und Pakete, ohne dass jemand sie von Hand schneidet – als Daten,
die der Lead nur noch bestätigt oder ändert.

- **Auslöser:** Freigabe eines Themas (auch die eigene Bearbeitung des Menschen, die als Freigabe gilt) und `amw thema planen
  TH<n>` (Lead, Mensch, Co-Entwickler). Je Fassung ein Planer; nicht bei „nichts zu bauen“; auf Befehl auch noch einmal.
- **Was läuft:** ein losgelöster Prozess (`amw-planer.py`) als leichter Lauf der Lauf-Schlange startet einen frischen
  `claude -p` (Sonnet, Effort medium) nur lesend wie der Gegenleser, mit fester Frist (15 min, danach beendet). Er liest
  `thema.md`, `beschluesse.md`, `meilensteine.md` (nur offene, ★ = Ziel verweist auf das Thema), `pakete.md` (die Pakete des
  Themas mit Status, auch fertige, dann die übrigen offenen) und `schema.md` und antwortet nur mit JSON: Meilensteine (neu oder
  bestehend) und Pakete (Größe, Art, agent oder p, Modell/Effort, Fertig-Quelle, Abhängigkeiten, Abnahme-Befehl) – oder
  `nichts_zu_bauen` mit Grund. Der Auftrag sagt: Fertiges nie neu vorschlagen, einen passenden offenen Meilenstein nutzen,
  Oberflächen-Pakete als agent mit Kleinprobe zuerst (A1976).
- **Danach:** Die AMW prüft das Schema (alle Funde auf einmal; A1976 dazu: „bestehend“ nur ein offener Meilenstein, ein
  Oberflächen-Paket nie als p, ein Paket mit fast gleichem Titel wie ein fertiges Paket des Themas → „schon gebaut: A…“) und trägt den Entwurf ein (`thema_planentwurf`, mit Modell,
  Kosten und Lauf). Der Lead bekommt „Ja oder ändern“; bei Fehlern eine Meldung mit den Funden. Erst `amw thema plan-ja TH<n>`
  (Lead oder Mensch, optional `--datei` mit einem geänderten Entwurf) legt Meilensteine und Pakete an und verknüpft jedes Paket
  mit dem Thema; `amw thema plan TH<n>` zeigt den Entwurf. Kein Anlegen ohne Ja. Jedes Paket bekommt dabei seine
  Fertig-Quelle (A1996): commit und release → `commit`, thema → `thema TH<n>` des Plans, ja und dokument → `ja`; frist → `ja`,
  bis jemand Tage und Version setzt (die stehen nicht im Plan) – dazu eine Meldung an den Lead mit den Paketen.
- **p als Vorgabe (A2004):** S – und M bei Art mechanisch –, keine Oberfläche: der Planer schneidet es als p mit
  Abnahme-Befehl, `bereiche` (Pflicht für p, keine gesperrten Pfade) und `pakettyp`; ohne Modell/Effort gilt die Empfehlung des
  Projekts. Interaktiv nur mit `interaktiv_grund` (steht dann im Auftrag). Fehlt er, meldet das Ja „Achtung“ an den Lead
  (auch `plan-ja` im Terminal); `amw aufgabe neu` sagt bei S/M-mechanisch ohne `--paket` „p möglich – oder Grund“.
- **Anteil p (A2004):** Je Aufsichtsrunde prüft der Dienst den Anteil p an den fertigen Paketen der letzten 7 Tage; liegt
  er unter 50 %, bekommt der Lead einmal je Tag eine Meldung (Ereignis `p_quote_meldung`) – nur in Projekten mit
  Arbeitsplätzen. Zahlen: `amw messung --p` (je Tag, Kosten und Wartezeiten p gegen interaktiv), Betrieb › „Anteil p“.
- **Projekt-Schalter (A1999):** wie der Gegenleser nur bei eingeschaltetem Projekt – steht `amw projekt schalter` auf aus
  oder probe, stößt weder die Freigabe noch die Dienst-Runde einen Planer an; `amw thema planen` antwortet „Projekt ist
  ausgeschaltet – Planer läuft erst nach dem Einschalten“ (bzw. „Projekt steht auf Probe – …“). Ein Thema, das an der
  Tagesgrenze wartete, wird dann nicht nachgeholt (Warten erledigt, „Projekt ausgeschaltet“); nach dem Einschalten stößt der
  Lead mit `amw thema planen` an.
- **Einstellung:** `themen_planer` = sonnet (Vorgabe) | aus – Lead oder Mensch. `planer_tagesgrenze_usd` (A1970, Vorgabe 5,
  0 = keine Grenze, Lead oder Mensch): haben die Planer-Läufe des Projekts heute (Ortszeit) so viel gekostet, startet keiner
  mehr – das Thema wartet (Ereignis `thema_planer_wartet`), der Lead bekommt einmal am Tag eine Meldung, und die Dienst-Runde
  stößt die wartenden Themen am nächsten Tag selbst an – nur, wenn das Thema noch freigegeben ist, die wartende Fassung die
  freigegebene ist und kein „nichts zu bauen“ vermerkt ist; sonst ist das Warten erledigt (`thema_planer_wartet_erledigt`). Der Planer liest nur im eigenen Ordner: Read/Glob/Grep sind mit dem
  Muster `./**` freigegeben (wie der Gegenleser), die Versionsprobe belegt, dass Lesen außerhalb abgelehnt wird. Tests stoßen nie einen echten Planer an
  (`AMW_PLANER_AUS`). Die Ansicht dazu kommt mit der Grobplanung (A1916).

### Grobplanung einmal fürs ganze Konzept (A2030, TH164 Schritt 2)

- **Bestand (A2062):** Hat ein Projekt schon Meilensteine (nicht verworfen) und keinen angenommenen Grobplan, weist
  `konzept-abschliessen` ab (CLI und Workbench) – der Planer würde sonst alles neu planen. Stattdessen übernimmt der Dienst den
  Bestand einmal als **Grobplan Fassung 0** (ohne Planer, ohne Kosten): je Meilenstein `{"schluessel": "M<nr>", "bestehend": nr,
  "themen": […], "status"}` – die Themen aus den TH-Verweisen im Ziel und den Themen seiner Aufgaben; freigegebene Themen ohne
  Meilenstein als Befund „abdeckung“ (ohne Themen mit Vermerk „nichts zu bauen“, A2071). Fassung 0 gilt als angenommen (`grobplan_ja` mit `uebernahme`) und jeder Meilenstein als
  grob freigegeben (Freigabe mit `quelle: uebernahme` und Bezug auf das Ja, Verlauf „Bestand übernommen“); fertige und verworfene
  Meilensteine stehen mit in Fassung 0, zählen aber nicht als offen. Das Grob-Tor zählt die Zuordnung der Fassung 0 und die Themen
  des Befunds „abdeckung“ als zugeordnet. Der Lead bekommt eine Meldung. Danach plant der Planer je Thema (K4) Änderungen und Fehlendes.

- **Auslöser:** `amw thema konzept-abschliessen` – nur bei geschlossenem Konzept-Tor (alle zählenden Themen frei) und solange
  kein Grobplan angenommen ist. Ja sagt der Mensch; bei `thema_freigabe = co+lead` (Grobplan-Ja: `grobplan_freigabe`) Co-Entwickler und Lead je ein Ja zum selben
  Stand der Themen (Ereignisse `konzept_abschluss_ja`, `konzept_abschluss`).
- **Was läuft:** EIN Grob-Planer (`amw-planer.py --grob`) als leichter Lauf der Lauf-Schlange, frischer `claude -p` nur lesend,
  Opus mit Effort high, Frist 30 min. Er liest alle freigegebenen Themen in ihrer freigegebenen Fassung (`uebersicht.md`,
  `themen/TH<n>.md`), alle geltenden Beschlüsse, die Meilensteine und die offenen Pakete und antwortet nur mit JSON: Befunde
  (doppelt, zu groß, unklar, Widerspruch, Abdeckung), Fragen mit Optionen und Empfehlung, Meilensteine (Ziel mit TH-Verweisen,
  „fertig, wenn“, Vorführung oder Bericht, nach · gleichzeitig mit, Aufwand, Tage, Kosten) und Grund. Fortschritt wie beim
  Planer je Thema (A2025), Kosten zählen zur gemeinsamen Tagesgrenze `planer_tagesgrenze_usd`.
- **Danach:** Die AMW prüft das Schema, die Verweise, Kreise und die Abdeckung (jedes Thema in einem Meilenstein oder ein Befund
  „abdeckung“ mit Grund) und trägt eine Fassung ein (`grobplan_entwurf`, jede bleibt). Der Lead bekommt die Zusammenfassung;
  Fragen des Planers gehen als Fragen der AMW an den Lead. Ansehen: `amw thema grobplan [--fassung N]`, neu planen lassen:
  `--neu` (Lead, Co, Mensch).
- **Grobplan-Ja:** `amw thema grobplan-ja [--fassung N]` (wer Ja sagt wie oben) legt die Meilensteine in der Reihenfolge der
  Abhängigkeiten an (Nummern je Projekt), ergänzt fehlende TH-Verweise im Ziel und vermerkt je Meilenstein die Grob-Freigabe –
  das Ja ist diese Freigabe. Nur einmal, und nur, solange die freigegebenen Themen dieselben sind wie beim Planen. Das
  Grob-Tor zählt Themen auch über die TH-Verweise im Ziel eines Meilensteins (nicht nur über Pakete). Danach plant der Planer
  je Thema nur noch Änderungen.
- **Neue Projekte (TL #31613):** Hat ein Projekt noch keinen Meilenstein und keinen Konzept-Abschluss, stößt die Freigabe
  eines Themas keinen Planer je Thema an – erst kommt die Grobplanung über das ganze Konzept. Projekte mit Meilensteinen
  bleiben wie bisher; `amw thema planen TH<n>` geht von Hand immer.
- **Fortschritt gegen den Laufstatus (P575):** Steht ein Planer-Stand auf „läuft“, der Lauf ist aber fertig oder
  abgebrochen, zeigt die AMW ihn als Fehler („L<n> ist abgebrochen, ohne dass der Planer ein Ende gemeldet hat“).

### Fensterkosten je Tätigkeit (A2058)

- **Marken:** bei jedem Wechsel der Tätigkeit eines Agenten ein `plan_ereignis taetigkeit` (ohne Schemaänderung): Aufgabe starten →
  bauen; Aufgabe wartet/blockiert → nach der Art des Wartegrunds (Prüfung → prüfen lassen, Stapel → stapeln, sonst warten);
  fertig/verworfen → sonstiges; Prüfbitte → prüfen lassen; eigener Lauf angemeldet → warten, eigener Lauf rot zu Ende → Fehlersuche;
  `release ausliefern` → stapeln.
- **Zuordnung:** jeder Zuwachs des Sitzungs-Zählers (`verbrauch`) gehört weiter zur laufenden Aufgabe und zusätzlich zur Tätigkeit
  der letzten Marke davor; ohne Marke gilt „bauen“. Die Prognose-Warnung („über Prognose“) vergleicht nur den Anteil „bauen“
  (Headless-Läufe zählen ganz als bauen).
- **Anzeige:** `amw messung --kosten [--tage N]` – Kosten der Fenster-Agenten je Tag und Tätigkeit.

### Rollende Feinplanung (A2031, TH164 Schritt 3)

- **Gesperrte Bereiche und eine Nachbesserung (A2067):** Der Feinplaner bekommt `sperrliste.md` – die feste Sperrliste
  (`abnahme.GESPERRT`), die Testdateien und die Sperrmuster des Projekts – mit der Regel: ein p-Paket nennt keinen gesperrten Pfad,
  Testdateien nur mit `pakettyp` test-schreiben/test-ergaenzen, sonst `agent` mit `interaktiv_grund` „gesperrter Bereich“. Passt
  seine Antwort nicht zum Schema, gehen die Funde einmal automatisch an ihn zurück (zweiter Lauf, Kosten zählen zusammen); erst
  wenn auch die zweite nicht passt, steht „Plan passte nicht“ da.

- **Auslöser:** je Aufsichtsrunde des Dienstes (`feinplanung.runde`), wenn `plan_automatik` an ist. Fällig ist der nächste
  geplante Meilenstein (kleinste Nummer) mit Grob-Freigabe und ohne Pakete – nur wenn kein Meilenstein davor noch auf das Ja
  zu seinem Plan wartet. Anlass: „erster“ (kein Meilenstein läuft, alle geplanten sind grob freigegeben), „bereit“ (der
  laufende ist bereit zur Abnahme) oder „letztes“ (in ihm laufen nur noch Pakete, keins wartet). Einmal je Meilenstein
  (`feinplan_faellig`). Meilensteine, die laut Grobplan `gleichzeitig` mit ihm laufen dürfen, kommen in denselben Lauf.
- **Was läuft:** ein Feinplaner (`amw-planer.py --fein`) wie der Grob-Planer: leichter Lauf der Lauf-Schlange, frischer
  `claude -p` nur lesend, Opus mit Effort high, Frist 20 min. Er liest Meilenstein(e), ihre Themen (TH-Verweise im Ziel),
  Beschlüsse, den ganzen Grobplan, offene und zu diesen Themen fertige Pakete und Hinweise des Menschen und antwortet mit
  Paketen nach dem Paket-Schema des Planers (zusätzlich je Paket sein Thema), Fragen und Grund. Fortschritt Art `feinplaner`,
  Kosten zählen zur gemeinsamen Tagesgrenze. Ist der Planer aus oder die Grenze erreicht, bekommt der Lead den Auftrag.
- **Danach:** Die AMW prüft wie beim Planer je Thema (Schema, p-Regeln, Abnahme-Befehl, gesperrte Bereiche, kein Kreis) und
  dazu: Thema gehört zum Meilenstein, jeder Meilenstein hat ein Paket, nichts schon Gebautes. Geprüft legt sie die Pakete an
  (wartet, nichts startet) und meldet dem Lead „wartet auf das Ja“; Fragen gehen an den Lead. Eine neue Fassung
  (`amw bogen feinplanen N --hinweis …`, Lead oder Mensch) verwirft die nicht begonnenen Pakete der vorigen.
- **Ja = Start:** „Plan freigeben und starten“ (Workbench, `amw bogen freigeben N --art plan --starten`) gibt den Plan frei und
  übergibt den Meilenstein sofort an den Disponenten (`reihenfolge.starten`) – auch während der vorige auf seine Abnahme wartet.
  Bei `thema_freigabe = co+lead` startet er mit dem zweiten Ja.

### Delta-Planer bei einer Konzeptänderung (A2027, TH164)

- **Wann:** Der Planer je Thema läuft für ein Thema, das schon freigegeben und geplant war und eine neue freigegebene Fassung hat
  (A2026: es gibt betroffene Pakete). Dann bekommt er zusätzlich `aenderung.md` (Unterschied alte/neue Fassung, betroffene
  Meilensteine und Pakete mit stoppen / zu Ende / Nacharbeit) und den Auftrag, NUR die Änderung vorzuschlagen.
- **Antwort:** neue Pakete (auch Nacharbeit für fertige) und nur nötige neue Meilensteine im gewohnten Schema, dazu `aendern`
  (Titel/Auftrag) und `verwerfen` – beides nur für nicht begonnene betroffene Pakete; laufende und fertige ändert niemand.
- **Freigabe als ein Block:** Der Lead bekommt eine Meldung „Delta … – Freigabe als Block“; frei gibt der Mensch
  (`amw thema plan-ja TH<n>`), bei `feinplan_freigabe = co+lead` Co-Entwickler und Lead je ein Ja. Ändern lässt sich ein Delta
  nicht (dann neu planen). Mit der Freigabe legt die AMW die neuen Pakete an und führt `aendern`/`verwerfen` aus (Ereignis
  `thema_delta_angewandt`).

### Hinweise an den Planer und „Überarbeiten lassen“ (A2028, TH164)

- **Hinweis:** `amw thema hinweis grob|TH<n> --text … [--zu TH3|M2|P4|A123]` – Mensch, Lead oder Co-Entwickler; nur zu einem
  vorliegenden Entwurf (Ereignis `plan_hinweis`). Offen bleibt ein Hinweis, bis ein neuer Entwurf desselben Plans kommt.
- **Überarbeiten lassen:** `amw thema ueberarbeiten grob|TH<n>` startet den Grob-Planer bzw. den Planer des Themas neu; er
  bekommt `vorige.json` (sein letzter Entwurf) und `hinweise.md` und den Auftrag, nur zu ändern, was die Hinweise verlangen.
  Beliebig oft; jede Fassung bleibt.
- **Markiert:** `amw thema grobplan` bzw. `amw thema plan TH<n>` zeigen die Änderungen gegenüber der vorigen gültigen Fassung
  (neu / geändert mit Feldern / entfallen, verglichen über den Titel) und alle Hinweise (offen oder bearbeitet). Der Verlauf
  (Projektweg) nennt jeden Hinweis. Der Feinplan je Meilenstein (A2031) hängt sich an dieselbe Stelle an.

### Abschluss je Meilenstein: Gesamttest und Prüfer (A2029, TH164 Schritt 5)

- **Auslöser:** Ein Meilenstein, der mit einem Urteil endet, hat alle Pakete fertig (wie A2002). Bevor die AMW ihn „bereit zur
  Abnahme“ meldet, stößt sie einmal je Stand (welche Pakete, wann zuletzt fertig) die Abschlussprüfung an
  (`amw-planer.py --abschluss`, Ereignis `abschluss_angestossen`). Ist der Planer aus, meldet sie gleich „bereit“ wie bisher.
- **Was läuft:** erst der Gesamttest – `gesamtlauf_befehl` des Projekts im Projektordner als schwerer Lauf der Schlange (ohne
  Befehl: „nicht eingestellt“, hält nichts auf) –, dann ein Prüfer (frischer `claude -p`, nur lesend, Sonnet): er bewertet
  jedes Thema des Meilensteins gegen die fertigen Pakete (erfüllt mit Beleg oder was fehlt), schreibt die Vorführung und
  schlägt bei Lücken oder rotem Test Nacharbeits-Pakete nach dem Feinplan-Schema vor (`abschluss_ergebnis`).
- **Danach:** Erfüllt und grün → „bereit zur Abnahme“; der Abschlussbericht enthält Gesamttest, Prüfung je Thema und Vorführung.
  Sonst legt die AMW die Nacharbeit im selben Meilenstein an und startet sie ohne neues Start-Ja (bei rotem Test ohne
  Vorschlag: ein Paket „Gesamttest rot beheben“); Meldung an den Lead, Info an den Menschen. Danach prüft sie erneut. Ging der
  Prüfer nicht, wird der Meilenstein „bereit“ wie bisher, und der Lead erfährt, dass die Prüfung fehlt.
- **Antwort lesen (A2072):** Die Antwort des Prüfers wird als JSON gelesen, auch mit Text drumherum oder im Codeblock. Passt sie
  nicht zum Schema, bekommt der Prüfer die Funde einmal zurück und antwortet neu (Kosten zusammen, die Tagesgrenze gilt auch
  dafür); erst eine zweite unpassende Antwort heißt „Abschlussprüfung ging nicht“ – dann mit dem Anfang der Rohantwort im
  Ergebnis (`roh`) und im Bericht. Ein Ergebnis mit Fehler zählt nicht als Prüfung: auf der Seite Projektweg startet
  „Prüfung erneut starten“ (Mensch oder Lead, Weg von A2064) sie noch einmal.
- **Meilenstein ohne Themen (A2072, z. B. Wartung):** Der Prüfer urteilt im Feld `ziel`, ob die Pakete Ziel und „fertig, wenn“
  erfüllen; die Karte und der Bericht zeigen die Zeile „Ziel und „fertig, wenn““.
- **Grenzen (TL #31785):** Die Kosten des Prüfers zählen zur gemeinsamen Tagesgrenze der Planer (`planer_tagesgrenze_usd`);
  ist sie erreicht, startet keine Prüfung, und der Meilenstein wird „bereit“ mit Meldung an den Lead. Höchstens 2 automatische
  Nacharbeits-Runden je Meilenstein – danach legt die AMW keine weiteren Pakete an, der Meilenstein wird „bereit“, die offenen
  Punkte stehen im Abschlussbericht, und der Lead bekommt eine Meldung.
- **Nacharbeit anfordern:** `amw bogen nacharbeit N --hinweis …` (Lead oder Mensch; Workbench-Weg `/api/meilenstein/nacharbeit`):
  der Feinplaner plant mit dem Hinweis neue Pakete im laufenden Meilenstein, die AMW legt sie an und startet sie gleich.
  Nach dem Ja zum Abschluss plant die AMW den nächsten Meilenstein fein (A2031).

### Thema → Meilenstein → Paket (K8, A1942, TH163)

- **Auslöser:** ein freigegebenes Thema bekommt eine neue Fassung (wie A1915) oder wird zurückgegeben.
- **Was geschieht:** Die AMW ermittelt die Meilensteine (geplant/aktiv), deren Pakete auf das Thema verweisen, und darunter die
  Pakete nach Stand (nicht begonnen, laufend, fertig). Der Lead bekommt einen Auftrag mit dieser Liste und dem Vorschlag: neu
  planen (`amw thema planen TH…`, K4) und die nicht begonnenen anhalten (`amw thema anhalten TH… [--meilenstein N]`). Angehalten
  wird nichts von selbst; laufende bauen zu Ende.
- **Anzeige:** Planung › Meilensteine zeigt am Meilenstein „Thema geändert: TH… (Fassung n)“, abgeleitet aus den Ereignissen
  (neue Fassung oder Zurück nach der Freigabe des Meilensteins), mit „Neu planen“ und „Nicht begonnene anhalten“. Anhalten:
  p-Pakete zurückgestellt, die übrigen „wartet“ auf den Lead mit Grund (Ereignis paket_angehalten).

### Tore, Abschlussbericht und Prognose (K7, A1944, TH154 Fassung 4)

- **Auslöser:** Dienst-Runde alle 10 Minuten (mit den Lücken Thema ↔ Paket), je Projekt.
- **Was läuft:** (1) Je fertigem Meilenstein ohne Bericht erstellt die AMW den Abschlussbericht gegen die Erfolgskriterien (Ziel,
  „endet mit“, Kriterien der Pakete, Pakete mit Kosten und Prognose, Reste, Lehren aus Rückblick/Prognose/roten Prüfungen) als
  Dokument zum Meilenstein (Ereignis abschluss_bericht) und sagt es dem Menschen bzw. bei co+lead Co und Lead. (2) In laufenden
  Meilensteinen: kostet ein offenes Paket (wartet, läuft, blockiert – fertige und verworfene nie, A1971) mehr als 1,5 × Prognose,
  bekommt der Lead einmal eine Meldung (Ereignis prognose_ueberschritten). Prognose = Median gleicher Größe und Art; hat die
  Eignungstabelle für dasselbe Modell/Effort mindestens 5 Messungen, deren Median (Modell/Effort aus dem p-Paket, sonst aus den
  Sitzungen mit den meisten Kosten). (3) Schließt oder öffnet sich ein Tor (Grobplanung bis Abschluss), hält die AMW das
  fest (Ereignis tor_stand mit dem Stand); Konzept schreibt weiter tor_geschlossen (A1913).
- **Danach:** Das Tor Abschluss schließt mit dem Ja zu allen Berichten (Mensch allein oder Co + Lead, `amw bogen freigeben N --art
  abschluss`); Zurück mit Notiz geht an den Lead, `amw bogen bericht N` erstellt einen neuen Bericht. Der Stand aller Tore:
  `amw bogen tore`, Planung und Themen (Leiste oben).

### Folgenprüfung eigener Änderungen (K8b, A1957, F5353/F5358/F5359)

- **Auslöser:** der Mensch ändert selbst einen Meilenstein (Planung › Meilenstein bearbeiten oder `amw bogen aendern --von
  Entwickler` im eigenen Terminal: Titel, Ziel, Abnahme, Zieldatum) oder ein Paket (`amw aufgabe aendern --von Entwickler`:
  Titel, Auftrag, Kriterien, Meilenstein). Änderungen von Agenten und Lead gelten wie bisher sofort.
- **Was läuft:** die Änderung wird Vorschlag (Ereignis aenderung_vorgeschlagen); ein losgelöster Prozess (`amw-folgen.py`) prüft
  als leichter Lauf der Schlange (ohne Weckruf) mit einem frischen `claude -p` (nur Lesen, Modell wie themen_gegenlesen, Frist
  10 min) `aenderung.md` und `darunter.md` und antwortet mit JSON (berührt Ziel/Erfolg/Kosten, Folgen). Kosten ins Ereignis.
- **Danach:** nichts berührt → gilt von selbst (Info mit Folgen an den Menschen); sonst Planung › „Deine Änderungen“ mit alt →
  neu und Folgen, gilt erst mit Ja (oder Verwerfen). Frist/Fehler/unbrauchbare Antwort → bleibt Vorschlag, „Ja übernimmt
  trotzdem“. themen_gegenlesen=aus: gilt wie früher sofort. Tests: AMW_FOLGEN_AUS.

### Themen → Aufgaben (A1915, D1304 v12 §1.3/§6d)

**Wozu:** Ändert sich ein Thema, sollen genau die Aufgaben geprüft werden, die darauf bauen – nicht alle, und ohne dass
jemand daran denken muss.

- **Verweis:** `amw aufgabe aendern N --thema TH3,TH5` / `--ohne-thema TH3` (Lead, Mensch, Co-Entwickler oder der Agent der
  Aufgabe). Ohne Schemaänderung: je Setzen/Lösen ein Ereignis `aufgabe_thema` (aufgabe_id, JSON `{aufgabe, thema, an}`), der
  jüngste Eintrag je Thema gilt. `aufgabe zeige` nennt die Themen.
- **Auslöser:** eine neue Fassung eines Themas, das vorher freigegeben war (`thema pflegen` des Pflegers oder `bearbeiten`
  des Menschen).
- **Was geschieht:** die offenen Aufgaben (nicht fertig/verworfen) mit Verweis gehen als Meldung „Thema geändert – prüfen“
  an ihren Agenten, eine Nachricht je Agent (gebündelt). p-Pakete haben keinen eigenen Agenten – ihre Zeile geht an den
  Lead; ein laufendes p-Paket wird nicht unterbrochen („läuft weiter, nach dem Lauf prüfen“). Kein Status wird gesetzt.

## Terminplaner (seit 1.13.0)

**Wozu:** Ein fester Rhythmus für die Tests des Entwicklers und eine gemeinsame Frist für alle Agenten.

- `amw termin neu --titel … --art test|frist|schirm|sonstig --am "06.11. 18:00" [--woechentlich --bis 2026-12-31]
  [--vorlauf 4] [--bogen N]` (Lead/Entwickler). Termine werden nie gelöscht: `termin absagen N` sagt die ganze Serie ab,
  mit `--am …` nur ein Vorkommen.
- Ein Testtermin setzt die Frist **„Testbuild fertig“** (Vorgabe 4 h vorher). Mit `--bogen` zeigt eine Ampel, ob die
  Prognose des Bogens die Frist hält.
- `amw termin bereit N --text "was ist neu, was testen"` meldet den Testbuild. Die AMW hängt die **Kurzliste** an (was
  seit dem letzten Test fertig und gemergt wurde) und schickt alles an den Entwickler, Kopie an den Lead.
- Ist die Frist erreicht und nichts gemeldet, bekommt der Lead einmal eine weckende Zeile. Der Entwickler bekommt 1 h vor
  dem Test eine Push-Nachricht.
- Sichtbar: Pflicht-Kontext („Nächster Testtermin …“), Startseite (Band „Nächster Test“), Planung › Termine. Online
  genauso.

## Federführung (seit 1.11.0)

Für einen Bogen oder eine Aufgabe kann ein Agent federführend sein (`amw bogen|aufgabe aendern N --federfuehrend X`).
Zuständig für eine Aufgabe ist ihre Federführung, sonst die ihres Bogens, sonst der Lead. `--an zustaendig --aufgabe N`
erreicht ihn. Prüfergebnisse gehen auch an ihn. Liegt eine Frage, Prüfbitte oder ein Auftrag dort 30 min ungelesen
(`eskalation_min`), erfährt es der Lead.

## Frage-Prüfung (seit 1.8.0)

**Wozu:** Fragen an den Entwickler, die längst entschieden sind, kosten seine Zeit.

`amw frage neu` sucht in geltenden Beschlüssen, beantworteten Fragen und Regeln nach den Wörtern der Frage (seltene
Wörter zählen mehr) und zeigt die besten Treffer. Fragen an den Entwickler brauchen `--geprueft "…"`; gibt es Treffer,
muss es mindestens einen nennen („B5 passt nicht, weil …“). Bei Fragen an den Lead zeigt die AMW die Treffer nur. Die
Workbench zeigt „Vorher geprüft: …“ an der Frage. Nachschlagen ohne Frage: `amw suche <Stichwort> --wissen`.

## Zeilenenden (seit 1.153.1)

**Wozu:** Eine Datei, die unter Windows ganz auf CRLF umgeschrieben wird (Python `open()` ohne `newline`), bläht den Diff auf
tausende Zeilen auf – und fiel bisher erst im Review auf (P309).

- **Test in der Suite** (`tests/test_zeilenenden.py`): Jede versionierte Textdatei hat LF ohne CR, außer was `.gitattributes`
  auf `eol=crlf` setzt (`*.cmd`, `*.ps1`) – die haben überall CRLF. Ein Treffer nennt Datei und Zahl der CR. Was Text ist,
  sagt Git (`git ls-files --eol`).
- **Warnung in der Prüfbitte:** `amw pruefung bitte` vergleicht `git diff --numstat` mit `git diff -w --numstat` (gegen
  dieselbe Basis wie die Bild-Pflicht). Ist eine Datei um mehr als 50 Zeilen größer, steht oben „Achtung: Diese Dateien
  ändern sich fast nur in Zeilenenden oder Leerzeichen …“ mit Dateinamen – kein Abbruch.
- `amw befehle > doc/befehle.md` schreibt LF auch unter Windows.

## Einstellungen

| Wo | Schlüssel | Bedeutung |
|---|---|---|
| `amw pc einstellen` | `projekt_rang` | Rangfolge der Projekte für den Disponenten (nur der Mensch im eigenen Terminal) |
| `amw pc einstellen` | `plaetze_pc` | höchstens so viele p-Arbeiter gleichzeitig über alle Projekte (0 = keine Grenze) |
| `amw pc einstellen` | `limit_halt` | Halt beim Wochenlimit für alle Projekte (Vorgabe 95, 0 = aus; ein Projekt nur strenger) |
| `amw projekt einstellen` | `sicherung_ziel` | wohin die tägliche Sicherung aller Zweige und Tags geht (Lead oder Mensch, ohne Zugangsdaten) |
| `amw projekt einstellen` | `thema_freigabe` | `mensch` (Vorgabe) oder `co+lead`: wer Themen freigibt (Lead oder Mensch stellt um, A1951) |
| `amw projekt einstellen` | `grobplan_freigabe`, `feinplan_freigabe`, `abschluss_freigabe` | `mensch` (Vorgabe) oder `co+lead`: wer Meilensteine, Pläne und Abschlüsse freigibt (Lead oder Mensch stellt um, A2032) |
| `amw projekt einstellen` | `release_sicherung` | `aus` (Vorgabe) oder `an`: Sicherung der Projektdaten vor `release ausliefern` (Projekte, die nicht die AMW sind) |
| `amw projekt einstellen` | `release_modus` | `datei` (Version in `version_datei`) oder `tag` (Version aus dem Tag) – für Bündel |
| `amw projekt einstellen` | `changelog_format` | `amw` oder `keepachangelog` ([Unreleased] → [X.Y.Z]) – für Bündel |
| `amw projekt einstellen` | `arbeiter_umgebung` | zusätzliche Variablen und PATH-Ordner für Arbeiter (keine Zugangsdaten, kein Netz) |
| `amw projekt einstellen` | `regression_befehl` | Rückschritt-Tests in Prüfung C (Befehl, `aus`; leer = Vorgabe: nur die AMW selbst) |
| `amw projekt einstellen` | `abnahme_frist_min` | Zeitlimit je Abnahme in Prüfung C, 1–720 Minuten (Vorgabe 30) |
| `amw projekt einstellen` | `sprachpruefung` | Sprach-Server in Prüfung C: `auto` (mit pyrightconfig.json), `pyright`, `aus` (Lead oder Mensch) |
| `amw projekt einstellen` | `sperrmuster` | was Arbeiter in diesem Projekt nie ändern dürfen, zusätzlich zur festen Liste (Lead oder Mensch) |
| `amw projekt einstellen` | `warten_agent_min` | Funkstille beim Warten auf einen anderen Agenten, dann Meldung an den Lead (5–1440 min, Vorgabe 60) |
| Zahnrad › Projekt | `entwickler_name` | wie der Mensch in Meldungen heißt (Vorgabe „Entwickler“); gilt auch als Wartegrund |
| Zahnrad › Dieser PC | `fernsitzung_prozess` | Programm einer Fernsitzung für den Schirm (leer = nicht prüfen) |
