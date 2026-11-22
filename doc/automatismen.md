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
- **Abnahme:** Unter „Für dich“ steht ein fertiger Meilenstein, der seit der letzten Veröffentlichung fertig wurde, mit
  „Abnehmen“ (am PC; online nur zu sehen). Im Terminal: `amw bogen abnehmen N` – nur der Mensch, nicht aus einer Agenten-Sitzung,
  nur für einen fertigen Meilenstein. Ereignis `bogen_abgenommen`.
- **Veröffentlichung:** danach einmal von selbst – Push von main und allen lokalen Tags, die es bei GitHub noch nicht gibt, und
  ein GitHub-Release für die neueste Version mit den CHANGELOG-Abschnitten aller dieser Versionen (neueste zuerst). Ereignis
  `veroeffentlicht`, Meldung an Lead und Mensch. Geht etwas schief, meldet die AMW es; `amw bogen abnehmen N` noch einmal stößt
  die Veröffentlichung erneut an.
- **Einstellung `veroeffentlichen`:** meilenstein (Vorgabe) | sofort (wie früher: Push und GitHub-Release bei jeder
  Auslieferung). Nur Lead oder Mensch, nicht aus einer Agenten-Sitzung.

## Bündeln (seit 1.150.0)

**Wozu:** p-Pakete ohne Coder ausliefern – bisher setzte ein Coder die freigegebenen Pakete von Hand aufeinander, hob die
Nummer und schrieb die Versionshinweise.

- **Auslöser:** nur der Lead oder der Mensch: `amw paket buendeln --alle | <nr> [--titel …]` (D1306 F1).
- **Was geschieht:** eigener Arbeitsbaum `<platz_wurzel>/buendel` (git worktree, neutrale git-Umgebung ohne Hooks), je
  freigegebenem Paket ein cherry-pick in Rang-Reihenfolge; Konflikt → E8 an den Lead, „nach“-Pakete bleiben draußen;
  Versions-Commit (MINOR bei Hinweis-Gruppe „neu“, sonst PATCH; Versionshinweise aus den Hinweisen) mit Diff-Tor: nur
  `version_datei`, `changelog_datei` und die Dateien von `buendel_schritt`; Zweig `buendel-X.Y.Z`.
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
- **Bitte als Info:** `amw posten --art info` an den Lead wird abgewiesen, wenn sie um eine Handlung bittet (bitte … Merge-OK,
  prüfen, freigeben, entscheiden, ausliefern) oder zu einer Aufgabe gehört, die auf den Lead wartet: „Bitte um Handlung →
  --art frage (weckt)“.
- **Nachwecken:** Der Dienst weckt den Lead einmal nach, wenn eine Nachricht 10 Minuten nach dem Weckruf noch ungelesen ist und
  er seitdem nichts gesendet hat – höchstens einmal je Nachricht, nicht im Halt, nicht während er arbeitet.
- **Gemeinsamer Stand:** Eine Prüfung einer anderen Aufgabe auf genau demselben Stand (oder demselben Baum) belegt die
  Versionsnummer nicht mehr – zwei Aufgaben lassen sich auf einem Stand prüfen und ausliefern.

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
`amw projekt einstellen leerlauf_lead=<Agent> leerlauf_lead_min=<min>`.

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
- **Einstellung:** `themen_gegenlesen` = haiku (Vorgabe) | sonnet | aus – Lead oder Mensch. Rollen Gliederung und Machbarkeit
  sind vorbereitet (`gegenlesen.ROLLEN`), aber nicht gebaut. Tests stoßen nie einen echten Gegenleser an (`AMW_GEGENLESEN_AUS`).

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
| `amw projekt einstellen` | `release_sicherung` | `aus` (Vorgabe) oder `an`: Sicherung der Projektdaten vor `release ausliefern` (Projekte, die nicht die AMW sind) |
| `amw projekt einstellen` | `release_modus` | `datei` (Version in `version_datei`) oder `tag` (Version aus dem Tag) – für Bündel |
| `amw projekt einstellen` | `changelog_format` | `amw` oder `keepachangelog` ([Unreleased] → [X.Y.Z]) – für Bündel |
| `amw projekt einstellen` | `arbeiter_umgebung` | zusätzliche Variablen und PATH-Ordner für Arbeiter (keine Zugangsdaten, kein Netz) |
| `amw projekt einstellen` | `regression_befehl` | Rückschritt-Tests in Prüfung C (Befehl, `aus`; leer = Vorgabe: nur die AMW selbst) |
| `amw projekt einstellen` | `abnahme_frist_min` | Zeitlimit je Abnahme in Prüfung C, 1–720 Minuten (Vorgabe 30) |
| `amw projekt einstellen` | `sperrmuster` | was Arbeiter in diesem Projekt nie ändern dürfen, zusätzlich zur festen Liste (Lead oder Mensch) |
| Zahnrad › Projekt | `entwickler_name` | wie der Mensch in Meldungen heißt (Vorgabe „Entwickler“); gilt auch als Wartegrund |
| Zahnrad › Dieser PC | `fernsitzung_prozess` | Programm einer Fernsitzung für den Schirm (leer = nicht prüfen) |
