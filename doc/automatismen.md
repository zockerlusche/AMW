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

## Arbeitsliste je Agent (seit 1.12.0)

**Wozu:** Wer vieles gleichzeitig anfängt, macht wenig fertig. Jeder Agent arbeitet eine geordnete Liste von oben nach
unten ab, genau eine Aufgabe ist in Arbeit. Der Umfang darf groß sein.

- **Reihenfolge:** Feld `rang` der Aufgabe. Der Lead ordnet mit `amw liste ordnen <Agent> A12 A15 …` (der Rest folgt
  dahinter, Aufgaben aus dem Pool werden zugeteilt) und `amw liste schieben A15 --vor A12 | --nach | --pos N | --oben |
  --unten`. Ansehen: `amw liste [Agent]`, Workbench › Aufgaben › Listen.
- **Pool:** neue Ideen ohne Platz in einer Liste (`aufgabe neu … --pool` oder `aufgabe pool N`). Der Lead sortiert ein.
- **Warten füllen:** Wartet die Aufgabe in Arbeit mit Grund (Prüfung, Lauf, Frage), darf der Agent die nächste nehmen.
  Wird die obere wieder frei, weckt ihn die AMW („Pos 1 deiner Liste – zuerst abschließen“).
- **Zurückstellen:** Startet er eine weiter oben stehende, wartet die laufende untere von selbst auf sie (Wartegrund
  `A…`). Ist die obere fertig, kommt die untere mit einem Weckruf zurück.
- **Zwei in Arbeit:** Startet er eine weiter unten, während eine obere läuft, bekommt er einen Hinweis, und der Lead
  erfährt es.
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

## Einstellungen

| Wo | Schlüssel | Bedeutung |
|---|---|---|
| Zahnrad › Projekt | `entwickler_name` | wie der Mensch in Meldungen heißt (Vorgabe „Entwickler“); gilt auch als Wartegrund |
| Zahnrad › Dieser PC | `fernsitzung_prozess` | Programm einer Fernsitzung für den Schirm (leer = nicht prüfen) |
