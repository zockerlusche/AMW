# Anleitung: Projekte planen mit AMW

Die Planung folgt einer bewährten Kette – angepasst an einen Menschen, einen Team-Lead-Agenten und mehrere Agenten
(Methode und Quellen: `doc/recherche/planung.md`):

**Leitbild → Bögen → Spezifikation (mit deiner Freigabe) → Schritte → Ausführung → Abnahme → Prognose und Status.**

Befehle in dieser Anleitung führt meist der Lead-Agent aus (`--von TL`); du selbst arbeitest in der Workbench oder an der
Kommandozeile mit `--von Entwickler`. Beispiele ohne `--von` setzen voraus, dass `AMW_AGENT` gesetzt ist.

Der Mensch ist der Engpass: alles, was auf dich wartet (Freigaben, Klärungsfragen, eigene Schritte), steht in der
Workbench unter „Wartet auf dich“, in der Ansicht **Planung** oben und kommt als Push aufs Handy.

## 1 Leitbild – woran sich alles misst
Projektziel (ein Satz, messbar), Kennzahlen, **Nicht-Ziele** (was ausdrücklich nicht gebaut wird – das bremst Agenten,
die mehr bauen als verlangt), Prinzipien mit Prüffrage und die **Definition of Done** für jeden Schritt.
Die Agenten bekommen das automatisch in ihren Pflicht-Kontext.
- Workbench: Planung › Leitbild
- `amw leitbild setzen --ziel "…" --nicht-ziel "…" --prinzip "Einfach|Versteht es ein Neuling?" --dod "Tests grün"`

## 2 Bögen – Meilensteine mit prüfbarem Abnahmekriterium
Ein Bogen hat ein Ziel, ein **prüfbares Abnahmekriterium** („Login-Test grün“, nicht „Login fertig“) und ein Zieldatum.
Beim Aktivieren wird das Zieldatum als **Baseline** eingefroren; eine spätere Verschiebung geht nur mit Grund und steht im
Protokoll (Änderungssteuerung).
- Workbench: Planung › „Neuer Bogen“, auf der Karte „Aktivieren“ / „Abschließen“ / „Bearbeiten“
- `amw bogen neu --titel … --ziel … --abnahme … --zieldatum 2026-12-01` · `amw bogen status <n> aktiv` · `amw bogen liste`

## 3 Spezifikation – erst klären, dann bauen
Jeder Bogen hat drei Teile, die nacheinander zur Freigabe kommen (wie GitHub Spec Kit / Kiro):
1. **Anforderungen** – je Zeile eine mit ID (`R1 …`); unklare Stellen als `[KLÄREN: Frage?]` – daraus wird automatisch
   eine Frage an dich, und die Freigabe wartet, bis sie beantwortet ist (nicht raten!).
2. **Entwurf** – wie es gebaut wird (vorlegen erst nach freigegebenen Anforderungen).
3. **Schritte** – die Zerlegung als Text (vorlegen erst nach freigegebenem Entwurf).

Die Reihenfolge gilt für das **Vorlegen** der Teile. Schritte als Aufgaben (`amw aufgabe neu --bogen …`) kann der Lead
jederzeit anlegen – der Plan-Check (§6) meldet aktive Bögen, deren Anforderungen noch nicht freigegeben sind. In `amw bogen zeigen`
steht je Teil der Stand: *in Arbeit* (noch nicht vorgelegt), *vorgelegt*, *frei*, *zurück*.

Der TL schreibt und legt vor (`amw spec schreiben <n> anforderungen --datei a.md`, `amw spec vorlegen <n> anforderungen`),
**du gibst frei oder gibst mit Kommentar zurück** (Workbench: Chip „zur Freigabe“ anklicken – auch online vom Handy).
Wird ein freigegebener Teil geändert, entsteht eine neue Version, die wieder vorgelegt werden muss.

## 4 Schritte – klein, prüfbar, mit Abnahmekriterien
Schritte sind Aufgaben mit Bogen. Ein guter Schritt („bereit“) hat: Abnahmekriterien, Bearbeiter, erledigte Vorgänger;
dazu nach Bedarf Schätzung (Stunden), Komplexität 1–10, Prüfbefehl (wie der Agent selbst prüft), Dateibereich (was er
anfassen darf) und die abgedeckten Anforderungen (`R1,R3`).
```
amw aufgabe neu --titel "Login-Formular" --bogen 1 --agent CC1 --kriterium "Formular sendet" --kriterium "Fehler sichtbar" \
    --anforderungen R1 --schaetzung 3 --komplexitaet 4 --pruefbefehl "pytest tests/login" --nach 1201,1203
```
(`--nach`: Nummern der Vorgänger-Schritte – die gibt es in deinem Projekt natürlich unter anderen Nummern.)
Schritte für **dich** bekommen `--agent Entwickler` – sie erscheinen unter „Wartet auf dich“ und zählen mit deinem
eigenen Tempo in die Prognose.

## 5 Ausführung – Regeln, die Agenten helfen
- `amw schritt naechster --nehmen` gibt dem Agenten den nächsten bereiten Schritt (aktiver Bogen zuerst, dann Rang) und
  übernimmt ihn in einem Zug – zwei Agenten bekommen nie denselben.
- Ein Bogen-Schritt startet erst, wenn seine Vorgänger fertig sind (Abhängigkeit „Ende → Anfang“; Kreise werden abgewiesen).
- Ab **Komplexität 7** legt der Agent zuerst einen Plan vor (`amw aufgabe plan <a> --text …`); der Lead – oder du, wenn
  du verantwortlich bist – gibt ihn frei (`amw aufgabe planfrei <a>`), erst dann wird umgesetzt.
- „Fertig“ nur mit erfüllten Kriterien (`amw aufgabe kriterium <a> <nr>`) und einer **Zusammenfassung**
  (`amw aufgabe fertig <a> --beleg <commit> --zusammenfassung "…"`).
- Aufgaben ohne Bogen funktionieren wie bisher – die Regeln gelten nur für geplante Schritte.

## 6 Prognose, Ampel, Plan-Check
- **Prognose**: aus dem tatsächlichen Tempo der letzten 14 Tage je Bearbeiter (Monte Carlo, 1 000 Durchläufe) – für
  jeden Schritt und Bogen ein Datum, das mit 50 % (P50) bzw. 85 % (P85) erreicht wird. Ein Schritt endet nie vor
  seinen Vorgängern.
- **Ampel je Bogen**: grün, wenn P85 vor dem Zieldatum liegt; gelb zwischen P50 und P85; rot, wenn schon P50 danach liegt.
- **Status je Dimension** (oben in der Planung): Termin, Risiko, Qualität – nach Regeln berechnet, mit Begründung.
- **Übersicht** (oben in der Zeitleiste): ein Balken je Bogen vom Start bis zur Prognose – fest bis P50, schraffiert
  bis P85 –, dazu Zieldatum (◆), deine eigenen Schritte (●) und die Heute-Linie. Oben steht, wann alles startet und
  wann voraussichtlich alles fertig ist. Ein Klick auf eine Zeile springt zum Bogen. Der Start eines Bogens ist der
  früheste tatsächliche Beginn seiner Schritte, sonst der Tag, an dem nach der Prognose der erste Schritt beginnt.
- **Plan-Check** sucht Lücken, die später Zeit oder Nacharbeit kosten – je Befund mit **Bedeutung** (was passiert,
  wenn man es lässt), **Abhilfe** (was zu tun ist, mit Befehl) und **wer** handelt (du oder der Lead), gruppiert nach
  Projekt, Bogen und Risiken. Stufen: *Fehler* – so ist der Plan nicht belastbar, zuerst beheben; *Warnung* – schwächt
  Termin, Prognose oder Abnahme; *Hinweis* – Ordnung. Geprüft wird: kein Ziel/Nicht-Ziel/DoD, Bogen ohne Abnahme oder
  Zieldatum, aktiver Bogen mit nicht freigegebenen Anforderungen, Termin rot/gelb, Anforderungen ohne Schritt, Schritt
  ohne Kriterien/Bearbeiter, Komplexität ohne Plan oder zu groß, fertige Schritte ohne Zusammenfassung, Risiko ohne
  Maßnahme oder eingetreten, Abhängigkeit auf verworfene Aufgabe.
- **Einlenken**: In der Workbench je Befund *öffnen* (Bogen, Anforderungen, Leitbild, Risiko, Schritt in der
  Zeitleiste), *An TL geben* (Auftrag mit Bedeutung und Abhilfe an den Lead) oder – bei Warnungen und Hinweisen –
  *Akzeptieren* mit Grund: der Befund zählt dann nicht mehr, steht unter „Bewusst akzeptiert“ und im Protokoll und
  lässt sich mit *Wieder prüfen* zurückholen. Fehler lassen sich nicht akzeptieren.
- Kommandozeile: `amw plan pruefen [--kurz]` (mit Schlüssel je Befund), `amw plan akzeptieren <schlüssel> --grund …`,
  `amw plan wieder <schlüssel>`, `amw plan status`, `amw plan prognose`. Abhängigkeit lösen:
  `amw aufgabe aendern <nr> --ohne-vorgaenger <nr>`; Zusammenfassung nachtragen: `amw aufgabe aendern <nr> --zusammenfassung …`.

## 7 Risiken
Ursache, Wirkung, Wahrscheinlichkeit × Auswirkung (je 1–5; ab 15 rot, ab 8 gelb), Strategie (vermeiden, mindern,
übertragen, akzeptieren), Maßnahme, Verantwortlicher, Auslöser. Matrix und Liste unter Planung › Risiken;
`amw risiko neu --titel … --w 4 --a 3 --strategie mindern --massnahme … --verantwortlich TL`.

## 8 Ein guter Tagesablauf mit Agenten
1. Morgens Planung öffnen: Ampel, Freigaben, „Wartet auf dich“ abarbeiten.
2. Der TL hält Bögen und Schritte aktuell (Plan-Check sauber), legt Spezifikationen vor, gibt Pläne frei.
3. Agenten holen sich mit `amw schritt naechster --nehmen` Arbeit und schließen mit Kriterien + Zusammenfassung ab.
4. Wird ein Bogen gelb/rot: Umfang kürzen (Nicht-Ziele!), Schritte umverteilen oder Zieldatum mit Grund verschieben.
5. Bogen fertig → Abnahmekriterium prüfen → „Abschließen“ → Rückblick.

## 9 Rückblick und Verlauf
- **Rückblick** am Bogen: was lief gut, was nicht, was ändern wir, was haben wir gelernt. Maßnahmen werden zur Aufgabe
  oder – als Lessons Learned – zum Beschluss, damit sie beim nächsten Bogen gelten. Agenten tragen bei mit
  `amw rueckblick <bogen> --schlecht "…"`.
- **Verlauf** zeigt, was wann passiert ist; die Startseite fasst zusammen, was seit deinem letzten Besuch geschah, und
  morgens kommt der Rückblick der letzten 24 Stunden aufs Handy.
