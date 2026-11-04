# Automatismen statt Gebote

Was ein Agent vergessen kann, regelt die AMW technisch, statt es in Regeln zu schreiben. Diese Seite beschreibt die vier
Automatismen: Schirm-Schalter, Wartegründe, Leerlauf-Prüfung und Frage-Prüfung. Befehle im Einzelnen:
[befehle.md](befehle.md).

## Schirm-Schalter (seit 1.7.0)

**Wozu:** Läufe mit Fenster (Spiel, Editor, Bildschirmfotos) stören, wenn der Entwickler am PC sitzt. Sie dürfen nur
laufen, solange er den Bildschirm ausdrücklich freigegeben hat.

- **Zustand:** frei oder zu, PC-weit. Jeder Wechsel ist eine Zeile in der Tabelle `schirm` (wird nie gelöscht).
  **Vorgabe: zu**, auch nach jedem Neustart.
- **Frei** gibt nur der Entwickler, in der Workbench am PC, oder der Lead auf sein Wort (`amw schirm frei --grund …
  [--bis 07:00]`, auch über die Brücke). Pflicht ist ein Grund, eine Uhrzeit für das Ende ist möglich.
- **Zu** darf jeder machen, der Entwickler auch online vom Handy aus.
- **Geht von selbst zu**, sobald der Entwickler wieder am PC ist. Das erkennt die AMW nur an Signalen am PC selbst:
  - eine Eingabe an diesem PC, frühestens 2 Minuten nach dem Freigeben (sonst schlösse der Klick auf „frei“ ihn
    gleich wieder), auch über eine Fernsitzung,
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
