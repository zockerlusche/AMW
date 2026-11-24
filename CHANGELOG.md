# Änderungen · Changelog

Versionen nach dem Schema MAJOR.MINOR.PATCH: MINOR für neue Fähigkeiten, PATCH für Korrekturen; 1.0.0, wenn die AMW
für andere Teams ohne Begleitung einsetzbar ist. Die Nummer steht in `amw/__init__.py`,
`amw --version` zeigt sie, die Workbench in der Kopfzeile. Zu jeder Version gibt es den Git-Tag `vX.Y.Z`.

## 1.186.0 – 24.11.2026 · Bestand als Grobplan, nur Riskantes zum Lead
- **Neu:** Hat ein Projekt schon Meilensteine, übernimmt die AMW sie als Grobplan (Fassung 0); er gilt als angenommen, der Projektweg steht beim richtigen Schritt, und die Grobplanung zeigt die Meilensteine mit ihren Themen. „Konzept abschließen“ plant einen Bestand nicht mehr neu.
- **Neu:** Pakete aus dem Fenster eines Agenten laufen durch dieselbe Prüfung wie Headless-Pakete; ist sie grün und nichts riskant, nimmt die AMW sie selbst ab. Der Lead liest nur noch Riskantes – mit Begründung je Regel – und bekommt jede Woche, wie viele Pakete die AMW selbst abgenommen hat und wie viele zurückgenommen wurden.
- **Neu:** „Lead liest“ markiert ein Paket, das die AMW nie selbst abnimmt (`amw paket lead-liest <nr>`).
- **Neu:** `amw messung --kosten` zeigt die Kosten der Agenten im Fenster je Tag und Tätigkeit (bauen, stapeln, prüfen lassen, warten, Fehlersuche); die Warnung „über Prognose“ zählt nur noch das Bauen.
- **Verbessert:** Der Feinplaner kennt die gesperrten Bereiche; passt sein Plan nicht, bessert er einmal selbst nach, bevor du davon hörst.
- **Behoben:** Die Sprachprüfung vergleicht mit dem Start-Commit des Pakets, nicht mit dem aktuellen Stand von main; ohne Vergleich sagt sie das.
- **Behoben:** Ein Versions-Commit mit Code hält die Auslieferung an.

## 1.185.0 – 24.11.2026 · Projektweg ruhig und passend für laufende Projekte
- **Behoben:** Die Seite Projektweg baut sich nicht mehr alle paar Sekunden neu auf; sie zeichnet nur, wenn sich wirklich etwas geändert hat. Scroll-Stand und offenes Seitenfenster bleiben.
- **Verbessert:** Bei Projekten mit Bestand zeigt die Grobplanung die vorhandenen Meilensteine, die Umsetzung die laufenden – der jüngste oben, fertige Pakete eingeklappt. „Konzept abschließen“ steht dort nicht mehr, bis die Übernahme kommt.
- **Verbessert:** Im Abschluss stehen alle Meilensteine, die auf deine Abnahme warten; abnehmen geht erst mit vollständiger Prüfliste. Meilensteine, die vor der Prüfung gegen das Konzept bereit wurden, bekommen „Prüfung starten“.
- **Verbessert:** Feinplan und Änderungen erscheinen als Karten in Stufen; der Knopf nennt genau, was du freigibst.
- **Verbessert:** Der Verlauf zeigt, was zum gewählten Schritt gehört – eine Zeile je Eintrag, Langes auf Klick, umschaltbar auf alle Schritte. Meilensteine tragen überall ihre Projektnummer.

## 1.184.0 – 24.11.2026 · Abnehmen und Feinplan-Funde auf der Seite Projektweg
- **Behoben:** „Abnehmen“ im Schritt Abschluss der Seite Projektweg nimmt einen Meilenstein, der bereit zur Abnahme ist, jetzt wirklich ab; vorher kam eine Fehlermeldung. Der Knopf erscheint, sobald der Abschlussbericht da ist.
- **Behoben:** Passt ein Feinplan nicht (zum Beispiel, weil ein Paket gesperrte Dateien ändern würde), zeigt die Seite Projektweg den Grund und „Überarbeiten lassen“ – vorher stand dort nur „Noch kein Feinplan“.

## 1.183.0 – 24.11.2026 · Warten gibt frei: die AMW verteilt selbst weiter
- **Neu:** Jeder Wartegrund hat eine Art – Prüfung, Stapel, Lauf, Antwort oder Paket. Wartet eine Aufgabe, zählt eine offene Prüfbitte zu ihr von selbst als Grund, das Ergebnis hebt ihn auf; nach einer Auslieferung ist „wartet auf Stapel“ erledigt.
- **Neu:** Wartet ein Agent auf eine Prüfung, einen Stapel oder einen Lauf, ist er sofort frei für das nächste startklare Paket (mit „Verteilen an“ teilt die AMW selbst zu); bei einer Antwort oder einem anderen Paket nach 10 Minuten. Eine Aufgabe, die auf nichts mehr wartet, weckt ihren Agenten.
- **Neu:** Die Pause zeigt einen Agenten, dessen Lauf oder Headless-Paket noch läuft, als „läuft zu Ende“.
- **Verbessert:** Langsame Anfragen der Workbench (ab 1 Sekunde) stehen mit ihren längsten Teilschritten im Protokoll.
- **Behoben:** Ändert sich der geprüfte Ordner während eines Gesamtlaufs, zählt der Lauf nicht mehr als Beleg.

## 1.182.0 – 24.11.2026 · Der Projektweg als eigene Seite
- **Neu:** Seite „Projektweg“: der ganze Weg in fünf Schritten – Konzept, Grobplanung, Feinplanung, Umsetzung, Abschluss – als Leiste; „wartet auf dich“ nur, wenn dein Ja fehlt, und die Handlung dazu steht gleich oben neben dem Schritt.
- **Neu:** Im Grobplan siehst du jede Fassung des Planers mit den Änderungen gegenüber der vorigen, im Feinplan die Pakete in Stufen mit „wer“ (Headless oder Fenster-Agent), in der Umsetzung die Fragen des Leads, im Abschluss Gesamttest, Prüfung und Vorführung.
- **Neu:** Ein Klick auf Thema, Meilenstein oder Paket zeigt die Einzelheiten rechts; von dort geht ein Hinweis an den Planer. Läuft ein Planer, zeigt ein Fenster seinen Fortschritt und schließt sich, sobald das Ergebnis da ist. Rechts steht, wer wann was getan hat.

## 1.181.0 – 24.11.2026 · Laufausgabe live, Zeitplan je Paket, Prognose messen, alle beenden
- **Neu:** Bei einem eigenen Lauf im Zeitstrahl „Was der Rechner heute gemacht hat“ öffnest du die Ausgabe; sie lädt alle 3 s nach, bis der Lauf endet. Das Mitlesen bei Headless-Paketen lädt ebenso selbst nach.
- **Neu:** Zeitplan je Paket (`amw bogen zeitplan [N]`): geplante Start- und Endzeit, was gleichzeitig läuft und um wie viele Minuten sich etwas verschiebt.
- **Neu:** Die AMW misst, wie gut ihre Dauer-Schätzungen treffen – `amw messung --prognose` zeigt die Trefferquote, auch je Quelle.
- **Neu:** Beim Start eines Headless-Pakets hält die AMW fest, warum gerade dieses dran war: Platz in der Reihenfolge, Arbeitsplatz und wer gestartet hat.
- **Neu:** `amw agent alle-beenden` bittet alle Fenster-Agenten (mit `--alle-projekte` über alle Projekte) zu sichern und sich zu beenden; `amw agent ende-stand` zeigt je Agent: sichert, abgemeldet oder beendet.

## 1.180.0 – 24.11.2026 · Abschluss je Meilenstein mit Prüfer, Pause für alles, Gesamtlauf ohne Hänger
- **Neu:** Bevor ein Meilenstein „bereit zur Abnahme“ steht, laufen der Gesamttest und ein Prüfer: Er gleicht jedes Thema gegen das Gebaute ab und bereitet die Vorführung vor – beides steht im Abschlussbericht. Fehlt etwas oder ist der Test rot, legt die AMW Nacharbeit im selben Meilenstein an und startet sie gleich.
- **Neu:** „Nacharbeit anfordern“ (`amw bogen nacharbeit N --hinweis …`): der Planer plant neue Pakete im selben Meilenstein, sie starten ohne weiteres Ja.
- **Neu:** Höchstens zwei automatische Nacharbeits-Runden je Meilenstein; die Kosten des Prüfers zählen zur Tagesgrenze der Planer.
- **Neu:** Pause für alles (`amw pause an --bis 2h`): alle Agenten halten an, keine neuen Headless-Pakete und Läufe; zum Ende geht es von selbst weiter. `amw pause zeige` zeigt je Agent, wo er steht.
- **Behoben:** Ein hängender Test hält den Gesamtlauf nicht mehr auf: nach 5 Minuten Stillstand wird nur dieser Testprozess beendet und als rot mit Modul und Test gezeigt, der Rest läuft weiter. Ein Gesamtlauf hat immer eine Frist (Vorgabe 60 Minuten); vorher hält er fest, was gerade lief, und der Lead bekommt eine Meldung.

## 1.179.0 – 24.11.2026 · Änderungen am Konzept als ein Block, Hinweise an den Planer
- **Neu:** Änderst du ein schon geplantes Thema, schlägt der Planer nur die Änderung vor – neue Pakete, geänderte oder nicht mehr nötige, die noch nicht begonnen sind. Du gibst sie als einen Block frei.
- **Neu:** Passt an einem Entwurf etwas nicht, gib dem Planer einen Hinweis zu einer Karte und lass ihn überarbeiten; jede Fassung bleibt sichtbar, Neues, Geändertes und Entfallenes ist markiert.

## 1.178.0 – 24.11.2026 · Rollende Feinplanung: der nächste Meilenstein ist geplant, bevor der laufende fertig ist
- **Neu:** Die AMW plant den nächsten Meilenstein selbst fein, sobald der laufende bereit zur Abnahme ist oder sein letztes Paket läuft: ein Planer zerlegt ihn in Pakete mit Ziel, Thema, Dateien, Abnahme, Abhängigkeiten und wer sie ausführt.
- **Neu:** „Plan freigeben und starten“ – dein Ja zum Feinplan ist zugleich der Start, auch während der vorige Meilenstein noch auf deine Abnahme wartet.
- **Verbessert:** Headless-Pakete starten in derselben Reihenfolge, die die Planung anzeigt (aktiver Meilenstein zuerst, dann der längste Weg bis zum Ende).
- **Behoben:** Kosten in der Planung, im Abschlussbericht und die Meldung „über Prognose“ zählen jetzt auch die Läufe der Headless-Pakete; neu: Kosten des Projekts bisher, noch und gesamt (`amw messung --gesamt`).
- **Behoben:** Anhalten und Weiter als Entwickler gehen nur noch im eigenen Terminal oder in der Workbench, nicht aus einer Agenten-Sitzung; der Lead hält weiter mit eigenem Namen an.
- **Behoben:** Neue Agenten legen nur noch der Lead oder der Mensch an; den Dienst starten der Mensch, der Lead oder die Auslieferung neu.

## 1.177.1 – 24.11.2026 · Seite bleibt unter Last nicht hängen
- **Behoben:** Scheitert unter Last ein Abruf der Seite an der Verbindung, versucht sie ihn einmal neu – statt bis zum Neuladen „Failed to fetch“ zu zeigen.

## 1.177.0 – 24.11.2026 · Wer Meilensteine freigibt, stellst du ein
- **Neu:** Je Projekt stellst du ein, wer Meilensteine, Pläne und Abschlüsse freigibt: du allein (Vorgabe) oder Co-Entwickler und Lead gemeinsam. Die Einstellung für Themen gilt nur noch für Themen.

## 1.176.0 – 24.11.2026 · Konzept abschließen und einmal grob planen
- **Neu:** Sind alle Themen freigegeben, schließt du das Konzept ab; ein Planer plant dann einmal das ganze Konzept: Meilensteine mit Themen, Reihenfolge, Aufwand und Kosten, dazu Doppeltes, Unklares und Lücken. Mit deinem Ja legt die AMW die Meilensteine an.
- **Verbessert:** In einem neuen Projekt ohne Meilensteine startet die Freigabe eines Themas keinen eigenen Planer mehr – erst kommt die Grobplanung über alle Themen.

## 1.175.2 – 24.11.2026 · Workbench antwortet auch unter Last sauber
- **Behoben:** Eine abgelehnte Eingabe (z. B. von einer Seite vor dem Neustart) bekommt auch unter Last die Antwort „neu laden“ statt eines Verbindungsfehlers.

## 1.175.1 – 24.11.2026 · Prüfung C erkennt Tests für neue Module
- **Behoben:** Prüfung C erkennt jetzt Tests für neue Module richtig; solche p-Pakete fallen nicht mehr fälschlich als „prüft nichts“ durch.

## 1.175.0 – 23.11.2026 · Nur der Lead fragt dich
- **Verbessert:** Dich fragt nur noch der Lead: Fragen der Agenten gehen an ihn, er stellt sie dir – auch gebündelt.

## 1.174.1 – 23.11.2026 · Team zeigt den Co-Entwickler richtig
- **Behoben:** Der Co-Entwickler heißt in der Workbench „Co-Entwickler“, und das Team zeigt bei ihm keine fremde Aufgabe mehr.

## 1.174.0 – 23.11.2026 · Zeitfenster für schwere Läufe je Projekt
- **Neu:** Je Projekt lässt sich ein Zeitfenster für schwere Läufe setzen (z. B. 18:00–07:00); außerhalb warten sie sichtbar und halten niemanden auf. Ohne Fenster bleibt alles wie bisher.

## 1.173.0 – 23.11.2026 · p als Vorgabe, Anteil p und Sprachprüfung
- **Verbessert:** Kleine Pakete plant die AMW als p; Betrieb zeigt den Anteil p, und jede Prüfbitte bekommt eine Sprachprüfung.

## 1.172.1 – 23.11.2026 · Online wieder aktuell
- **Behoben:** Die Online-Seite wird wieder aktuell gehalten, und das Zahnrad öffnet sich schnell.

## 1.172.0 – 23.11.2026 · Meilensteine mit Abnahme schließen erst nach dem Ja
- **Verbessert:** Ein Meilenstein, der mit Vorführung, Bericht oder Probe endet, schließt erst mit dem Ja zum Abschluss – vorher steht er auf „bereit zur Abnahme“.
- **Behoben:** Wer einen entfernten Agenten wieder aufnimmt, macht ihn nie nebenbei zum zweiten Lead.

## 1.171.0 – 23.11.2026 · Agenten per Befehl entfernen und zurückholen
- **Verbessert:** Agenten lassen sich auch per Befehl entfernen und wieder aufnehmen; ein entfernter Agent führt nie das Projekt.

## 1.170.3 – 23.11.2026 · Planer nur bei eingeschaltetem Projekt
- **Behoben:** Bei ausgeschaltetem Projekt oder im Probebetrieb startet kein Planer mehr.

## 1.170.2 – 23.11.2026 · Projekte online sauber getrennt
- **Behoben:** Online zeigt ein Projekt vor seinem ersten Abgleich „Noch kein Abgleich von diesem Rechner.“ statt Daten eines anderen Projekts.

## 1.170.1 – 23.11.2026 · Nachfragen bei langem Warten
- **Verbessert:** Wartet ein Agent lange auf einen anderen, ohne dass etwas kommt, oder ist inzwischen eine Version live, fragt die AMW beim Lead nach, ob der Grund noch gilt.

## 1.170.0 – 23.11.2026 · Konzepte übernehmen, Pläne startklar
- **Neu:** Ein Konzept als Markdown wird auf Wunsch zu Themen-Entwürfen – mit Vorschau und Zählprobe, freigegeben wird nichts (`amw thema uebernehmen`).
- **Behoben:** Pakete aus einem angenommenen Plan haben ihre Fertig-Quelle gleich mit und sind ohne Nacharbeit startklar.

## 1.169.1 – 23.11.2026 · Fragen richtig gezählt
- **Behoben:** Unter „Für dich“ zählt „Fragen n“ alle offenen Fragen, auch wenn mehr als 20 offen sind.

## 1.169.0 – 23.11.2026 · Planer mit Kostengrenze, genauere Anzeigen
- **Verbessert:** Die Planer eines Projekts kosten höchstens 5 $ am Tag (einstellbar); danach plant die AMW am nächsten Tag weiter.
- **Verbessert:** Eine Prüfung lässt sich nur mit Begründung auf Rot setzen; `--grund` zählt dabei wie `--bemerkung`.
- **Behoben:** „Macht gerade“ zeigt keine erledigte Aufgabe und keinen beendeten Lauf mehr.
- **Behoben:** Nach einem Neustart zählen die Kosten einer Aufgabe nicht mehr den ganzen Zählerstand als neuen Zuwachs.

## 1.168.0 – 23.11.2026 · Fragen unter „Für dich“
- **Verbessert:** Unter „Für dich“ stehen offene Fragen als eine Gruppe; blockierende zuerst, je Frage eine Zeile.

## 1.167.4 – 23.11.2026 · Prüfbitte prüft Betreffe
- **Verbessert:** Eine Prüfbitte meldet gleich, wenn ein Commit-Betreff eine fremde Aufgabe nennt, statt dass die Auslieferung
  später anhält.

## 1.167.3 – 23.11.2026 · Notbremse sofort
- **Verbessert:** Die Notbremse wirkt sofort, auch auf einen Arbeiter, der gerade erst startet.

## 1.167.2 – 23.11.2026 · Neu aufgesetzte Stapel
- **Behoben:** Ein neu aufgesetzter Stapel gibt die Versionsnummer seines alten Stands frei; alte Prüfungen müssen nicht mehr
  von Hand zurückgenommen werden.

## 1.167.1 – 23.11.2026 · Notbremse auch beim Start
- **Behoben:** Die Notbremse hält einen Arbeiter auch dann an, wenn er gerade erst startet.
- **Verbessert:** Der Schutz vor versehentlichen schweren Läufen erkennt mehr Arten, einen Befehl zu starten.

## 1.167.0 – 23.11.2026 · Fragen gebündelt
- **Neu:** Fragen an dich kommen gebündelt höchstens alle vier Stunden; bleibt eine einen Tag liegen, plant die AMW um, damit der
  Rest weiterläuft.
- **Behoben:** Die Versionshinweise einer Version zeigen wieder genau, was sie gebracht hat; der Lead kann eingetragene Versionen
  aus dem CHANGELOG berichtigen (`amw release berichtigen`).

## 1.166.0 – 23.11.2026 · Startwissen für Agenten, Stil-Prüfung als Automatik, ein Gesamtlauf zur Zeit
- **Neu:** Agenten bekommen beim Start das Wissen zu ihren Dateien und eine Projekt-Landkarte; Anfangen und Abgeben geht mit
  je einem Befehl (`amw paket holen`, `amw paket fertig`).
- **Neu:** Prüfbitten mit sichtbarer Änderung bekommen automatisch einen Stil-Befund je Regel; Grün trotz Verstoß nur mit
  Begründung.
- **Verbessert:** Es läuft höchstens ein ganzer Testlauf zur Zeit auf dem Rechner; ein zweiter wartet von selbst in der Schlange.
- **Verbessert:** Aufgaben, die nicht in die Versionshinweise gehören, lassen sich als intern markieren – auch nach dem Abschließen.
- **Behoben:** Ein vom Lead geprüfter Stapel geht ohne zusätzliche Prüfbitte je Aufgabe live, auch wenn darunter ein Konflikt
  aufgelöst wurde.
- **Behoben:** Der Hook für schwere Befehle hält einen Befehl nicht mehr an, nur weil sein Text in einer Nachricht oder
  Commit-Beschreibung steht.

## 1.165.2 – 22.11.2026 · „Über Prognose“ nur für offene Pakete, Planer kennt den Bestand
- **Behoben:** Die Meldung „über Prognose“ an den Lead kommt nur noch für offene Pakete, nie für fertige; die Prognose nimmt,
  wenn genug Messungen da sind, Pakete mit gleichem Modell und Denkaufwand.
- **Verbessert:** Der Planer sieht, was zu einem Thema schon gebaut ist und welche offenen Meilensteine dazu passen; die AMW
  weist Vorschläge zurück, die ein fertiges Paket wiederholen, und plant Oberflächen nie ohne Kleinprobe.

## 1.165.1 – 22.11.2026 · Themen-Seite zeigt nur, was auf dich wartet; pyright nur an festen Orten
- **Verbessert:** Die Themen-Seite zeigt oben nur noch die fünf Tore; die Werte eines Tors erscheinen auf Klick, und nur wenn
  du etwas tun musst, steht darunter eine Zeile („Wartet auf dich: 1 Thema · 1 Meilenstein“) mit Sprung dorthin.
- **Behoben:** Die Sprachprüfung sucht pyright und node nur in den festen Ordnern aus PATH, nie im aktuellen Ordner – ein
  dort liegendes Programm kann die Prüfung nicht ersetzen. Ein Test hängt nicht mehr von der Dauer des Gesamtlaufs ab.

## 1.165.0 – 22.11.2026 · Reihenfolge rechnet die AMW, schnellerer Gesamtlauf, „macht gerade“ abgeleitet
- **Neu:** Die AMW rechnet die Reihenfolge der Arbeit selbst (kritischer Pfad und gemessene Dauer); Listen, Verteilen und
  Prognose folgen ihr, von Hand ordnen geht nur mit Grund. `amw bogen starten` gibt einen Meilenstein an den Disponenten,
  `amw bogen reihenfolge` zeigt die berechnete Reihenfolge.
- **Neu:** Der Gesamtlauf der Tests verteilt sich auf mehrere Prozesse und ist damit deutlich schneller
  (`python -X utf8 -m amw.testlauf`; Anzahl über die Projekt-Einstellung `gesamtlauf_prozesse`).
- **Verbessert:** Was ein Agent gerade macht, leitet die AMW selbst ab (laufender Lauf, laufende Aufgabe, letzte Meldung) und
  zeigt Quelle und Alter; ohne Lebenszeichen seit 30 Minuten steht „veraltet?“ dabei.
- **Verbessert:** Fehlt beim Abschließen der Satz für die Versionshinweise, schlägt die AMW ihn selbst vor – aus Commit, Thema
  oder Titel.
- **Verbessert:** Ein Abnahme-Test läuft nach dem Bündeln in jedem Gesamtlauf mit; Pakete zeigen die erwarteten Kosten als
  Spanne aus gemessenen Paketen.
- **Behoben:** Meilensteine ohne Spezifikation zeigen keine leeren Spezifikationsteile mehr.

## 1.164.0 – 22.11.2026 · Grob- und Feinplanung, Planer aus Themen, alle fünf Tore
- **Neu:** Planung › Meilensteine und Pakete: jeder Meilenstein mit seinen Themen und womit er endet, je Meilenstein die Pakete
  mit Agent, Reihenfolge, Prüfung und Kosten (Summe oben). Freigeben je Meilenstein und je Plan – wer freigegeben hat, steht
  dabei; ändert sich danach etwas, muss neu freigegeben werden. „Jetzt starten“ erscheint, sobald alles freigegeben ist.
- **Neu:** Wird ein Thema freigegeben, entwirft ein Planer (ein eigener, nur lesender Agent mit fester Frist) Meilensteine und
  Pakete dafür – mit Auftrag und Abnahme-Befehl je Paket zum Ansehen; angelegt wird erst mit „Ja – anlegen“.
- **Neu:** Oben in Planung und Themen steht eine Leiste mit allen fünf Toren (Konzept, Grobplanung, Feinplanung, Umsetzung,
  Abschluss). Ist ein Meilenstein fertig, schreibt die AMW einen Abschlussbericht gegen die Erfolgskriterien – mit Resten und
  Lehren – und das Tor schließt mit dem Ja dazu. Kostet ein Paket deutlich mehr als geschätzt, bekommt der Lead eine Meldung.
- **Neu:** Ändert sich ein freigegebenes Thema, zeigt der Meilenstein das mit „Neu planen“ und „Nicht begonnene anhalten“.
  Änderst du selbst einen Meilenstein oder ein Paket, prüft ein Agent erst die Folgen: Berührt die Änderung weder Ziel noch
  Erfolgskriterien noch Kosten, gilt sie von selbst, sonst siehst du alt → neu mit den Folgen und entscheidest.
- **Verbessert:** Agenten starten mit einem kürzeren Einstieg – Regeln nur als Titel (ganz mit `amw regeln KR3`), ausführliche
  Anleitungen als Skills, die nur bei Bedarf geladen werden (`amw messung --hebel7` zeigt die Größe).
- **Verbessert:** Bevor ein Arbeiter-Paket zusammengeführt wird, prüft die AMW mit pyright, ob es neue Typfehler bringt
  (`amw projekt einstellen sprachpruefung=auto|pyright|aus`).
- **Behoben:** Nach „Speichern & beenden“ zeigt die Kachel des Agenten nicht mehr „läuft“, und „Starten / fortsetzen“ ist
  wieder wählbar.

## 1.163.0 – 22.11.2026 · Lücken Thema ↔ Paket, ruhigere Läufe, kürzerer Einstieg
- **Neu:** Die Planung zeigt selbst, welches freigegebene Thema noch kein Paket hat und welches Paket kein Thema – der Lead
  bekommt jede neue Lücke einmal gemeldet. Neue Aufgaben nennen ihr Thema (`--thema TH3`) oder bewusst keins mit Grund
  (`--ohne-thema-grund …`); ein Thema, das nichts braucht, bekommt den Vermerk „nichts zu bauen“ (`amw thema vermerk`).
- **Verbessert:** Läufe, die die AMW selbst ausführt und beendet (Gegenlesen, Negativprobe, Arbeiter, Bündel), wecken beim Start
  niemanden mehr mit „jetzt starten“.
- **Verbessert:** Nach dem Start liest ein Agent nur noch das Einstiegs-Thema des Konzepts und das Thema seines laufenden Pakets
  (`amw projekt einstellen konzept_einstieg=TH…`) – keine Konzept-Dokumente mehr.

## 1.162.1 – 22.11.2026 · Auslieferung hält nicht mehr bei „Stände“
- **Behoben:** Ist ein Stapel an der Spitze grün geprüft, bleibt dieses Grün erhalten; die Auslieferung hält nicht mehr bei
  „Stände“, weil ein übertragenes Grün auf einem inneren Commit es verdrängt hatte.

## 1.162.0 – 22.11.2026 · Sprach-Server für die Agenten, sicherere Auslieferung
- **Neu:** Die Agenten sehen Fehler in Python und PHP gleich beim Schreiben (Sprach-Server), statt sie erst beim Testen zu
  finden. Gilt für die Sitzungen der Agenten, nicht für die Arbeiter im Hintergrund.
- **Verbessert:** Nach einem roten Gesamtlauf und einer Korrektur gehen neue Prüfbitten durch, ohne dass ältere Prüfungen
  desselben Stapels von Hand zurückgenommen werden müssen.
- **Behoben:** Als Beleg für eine Auslieferung zählt nur noch ein Lauf aller Tests; ein Teil-Lauf wird nie mehr als Gesamtlauf
  gewertet.

## 1.161.0 – 22.11.2026 · Aufgaben schließen sich selbst, Abnehmen mit einem Ja
- **Neu:** Eine Aufgabe kann sagen, wann sie fertig ist (`--fertig-wenn`: Thema freigegeben, oder einige Tage nach einer
  Version ohne Fehler); die AMW schließt sie dann selbst und schreibt Beleg und Zusammenfassung. Kriterien mit einer
  Prüfquelle (Lauf, Prüfung, Thema, Testzahl) hakt die AMW selbst ab; ist nur noch ein Urteil offen, fragt sie den Lead.
- **Neu:** Hängt eine Aufgabe an deinem Urteil und ihr Ergebnis steht, siehst du sie unter „Für dich“; ein Ja genügt, den
  Status setzt die AMW. Ein Meilenstein zeigt seine Themen, und Ziel und Abnahme dürfen auf Themen und Dokumente verweisen
  (mit geltender Fassung). Neue Meilensteine brauchen keine Spezifikation mehr.
- **Verbessert:** Ob Themen von Co-Entwickler und Lead freigegeben werden und wohin die tägliche Sicherung geht, kann jetzt auch
  der Lead einstellen; jede Änderung durch ihn steht im Protokoll.
- **Behoben:** Eine Auslieferung geht jetzt auch dann bis zum Ende, wenn der ausliefernde Agent gerade einen eigenen Lauf hat;
  scheitert die Aktualisierung der Online-Seite, erfährt es der Lead.

## 1.159.0 – 22.11.2026 · Themen freigeben durch Co-Entwickler und Lead, Prüfbitte ohne eigene Version
- **Neu:** Auf Wunsch geben Co-Entwickler und Lead Themen gemeinsam frei (`amw projekt einstellen thema_freigabe=co+lead`, nur
  du stellst um); du kannst jederzeit selbst freigeben oder zurückholen. Themen zu Löschen, Kosten, Schema oder Außenwirkung
  bleiben bei dir. Am Thema steht, wessen Ja noch fehlt.
- **Verbessert:** Eine Prüfbitte auf einem Zweig ohne eigene Versionsnummer geht jetzt durch; die Nummer bekommt erst der
  Stapel, der mehrere Aufgaben gemeinsam ausliefert.
- **Intern:** Das alte Feld „Grenzen“ eines Agenten heißt im Code nur noch „Zuständig für“; die bisherigen Befehle gehen weiter.

## 1.158.0 – 22.11.2026 · Anbieter, Projekt-Schalter, Eignung, Sicherung
- **Neu:** Arbeiter können außer Anthropic auch andere Anbieter mit Anthropic-kompatibler Schnittstelle nutzen (z. B. MiniMax).
  Freigeben kannst nur du (`amw anbieter freigeben …`); gespeichert wird nur der Pfad zur Schlüsseldatei, nie der Schlüssel.
  Vor dem ersten Paket prüft die AMW den Anbieter selbst – auch, dass der Schlüssel für den Arbeiter unsichtbar bleibt.
- **Neu:** Ein Projekt wird mit `amw projekt schalter <Projekt> probe` an einer Kopie geprüft (Einträge, Nummern und Verweise
  bleiben gleich, Bericht als Dokument) und erst danach von dir eingeschaltet (`… an`); `… aus` hält Arbeitsplätze und
  Themen-Ablauf an. Gelöscht wird nichts.
- **Neu:** Die AMW misst, welches Modell mit welchem Denkaufwand welche Arbeit ohne Nacharbeit schafft und was es kostet
  (`amw empfehlung tabelle`). Ab fünf Aufgaben je Paar ersetzt das Gemessene die Startwerte der Empfehlung.
- **Neu:** Die AMW sichert einmal am Tag alle Zweige und Tags an ein Ziel, das du einstellst
  (`amw projekt einstellen sicherung_ziel=…`) – ohne am Ziel etwas zu überschreiben oder zu löschen, ohne Zugangsdaten zu
  speichern und ohne je nach einer Anmeldung zu fragen. Von Hand: `amw sicherung jetzt`.
- **Verbessert:** Die Startwerte der Empfehlung folgen TH159 (klein Sonnet, normal Opus medium, schwer Opus high); das
  Gegenlesen von Themen läuft jetzt mit Opus high (umstellbar auf haiku, sonnet oder aus).

## 1.157.0 – 22.11.2026 · Wo das Konzept steht, große Repos
- **Neu:** Oben auf der Themen-Seite steht, wo das Projekt steht: „Konzept · 2 von 7 Themen freigegeben“ (zum Löschen markierte
  zählen nicht). Gibst du das letzte offene Thema frei, fragt die Seite vorher „Damit schließt das Tor Konzept“ – einen eigenen
  Knopf dafür gibt es nicht. Danach steht dort „Grobplanung · Konzept fertig“. Gibst du später ein Thema zurück oder kommt eines
  dazu, ist das Konzept wieder offen.
- **Neu:** Arbeitsplätze für große Repos: Mit `amw projekt einstellen platz_lfs=teilen` kommen Git-LFS-Dateien nur als kleine
  Verweise in die Plätze; ein Arbeiter holt eine bei Bedarf aus deinem Projekt. Die Plätze liegen nie auf dem Systemlaufwerk,
  und jedes Projekt hat seinen eigenen Ordner dafür.
- **Behoben:** Bittet ein Agent einen anderen Agenten per Info um etwas (etwa „jetzt aufsetzen“), weist die AMW das ab – eine
  Info weckt nicht. Bisher galt das nur für Nachrichten an den Lead; jetzt für jeden Agenten.

## 1.156.0 – 22.11.2026 · Mehrere Projekte auf einem PC
- **Neu:** Jedes Projekt kann eigene Muster für Dateien eintragen, die Arbeiter nie ändern dürfen – zusätzlich zur festen
  Liste der AMW (`amw projekt einstellen sperrmuster='["src/sicherheit/*", "*.key"]'`, nur Lead oder du).
- **Neu:** Jedes Projekt stellt selbst ein, welche Rückschritt-Tests nach einem Paket laufen und wie lange eine Abnahme dauern
  darf (`regression_befehl`, `abnahme_frist_min`). Ohne Einstellung laufen die Tests der AMW nur in der AMW selbst; in anderen
  Projekten steht bei „Bereit zum Merge“, dass ohne geprüft wurde.
- **Neu:** Arbeiter eines Projekts können eigene Werkzeuge nutzen – einzelne Variablen und Ordner im PATH, etwa für ein SDK
  (`arbeiter_umgebung`). Namen wie Zugangsdaten lehnt die AMW ab; Arbeiter bleiben ohne Netz.
- **Neu:** Ein Projekt kann seine Versionsnummer aus dem Git-Tag nehmen und seinen CHANGELOG im Format „Keep a Changelog“
  führen (`release_modus=tag`, `changelog_format=keepachangelog`).
- **Neu:** `amw release ausliefern` liefert auch Projekte aus, die nicht die AMW sind: Fast-Forward, Tag, Push und
  Release-Notiz im Ordner des Projekts. Auslösen darf nur der Lead des Projekts oder du.
- **Neu:** Du legst fest, welches Projekt bei den Arbeitsplätzen zuerst dran ist (`amw pc einstellen
  projekt_rang=AMW,GlassWorld,LayerIT`) und wie viele Arbeiter über alle Projekte gleichzeitig laufen (`plaetze_pc`). Ein
  Paket, das wartet, sagt, worauf. `amw pc` zeigt die Kosten je Projekt; montags kommt ein Wochenbericht.
- **Verbessert:** Der Halt beim Wochenlimit gilt für den ganzen PC (`amw pc einstellen limit_halt=…`) – ein Projekt kann ihn nur
  strenger stellen, nicht abschalten.

## 1.155.1 – 22.11.2026 · Seiten laden zuverlässig
- **Behoben:** Beim Öffnen blieb eine Seite manchmal leer mit „Failed to fetch“, wenn sie viel auf einmal lud. Der Server nimmt
  jetzt viele Verbindungen gleichzeitig an.

## 1.155.0 – 22.11.2026 · Themen gegenlesen, Arbeit verteilen, lokal live
- **Neu:** Liefert der Betreuer eine neue Fassung eines Themas, liest ein frischer Agent sie zuerst gegen – er liest nur und
  kostet wenige Cent. Seine Einwände gehen an den Betreuer; erst danach wartet das Thema auf dich. Solange steht dort
  „wird gegengelesen · seit …“, danach klappst du das Ergebnis auf. Abschalten: `amw projekt einstellen themen_gegenlesen=aus`.
- **Neu:** Aufgaben können auf Themen verweisen (`amw aufgabe aendern <nr> --thema TH3`). Bekommt ein freigegebenes Thema eine
  neue Fassung, meldet die AMW die offenen Aufgaben mit Verweis ihrem Agenten zum Prüfen – eine Nachricht je Agent.
- **Neu:** Ist ein Agent frei, schlägt die AMW dem Lead die nächste passende Aufgabe nach dem Plan vor – nach Rang, bei gleichem
  Rang die mit mehr wartenden Nachfolgern zuerst, passend nach Fachgebiet und Größe. Mit `amw projekt einstellen verteilen=an`
  teilt sie selbst zu und nennt den Grund.
- **Neu:** Fällt ein Agent aus, geht seine laufende Aufgabe mit einer Übergabe-Notiz zurück, und du bekommst die Frage, ob seine
  Sitzung neu starten soll – starten tut nur du.
- **Neu:** `amw release ausliefern` kann lokal live machen, ohne zu veröffentlichen: Ist ein Meilenstein fertig, steht er unter
  „Für dich“ mit „Abnehmen“; danach veröffentlicht die AMW alle Versionen seit der letzten Veröffentlichung mit einem
  GitHub-Release (`amw projekt einstellen veroeffentlichen=meilenstein`; Vorgabe für neue Projekte).
- **Behoben:** Wird ein Stapel mehrerer Aufgaben nur neu aufgesetzt, übernimmt die Auslieferung Grün und Merge-OK für jede Aufgabe,
  und eine Ausnahme vom Gesamtlauf bleibt bei gleichem Inhalt gültig.

## 1.154.0 – 22.11.2026 · Updates ohne Stillstand, Prüfung zurücknehmen
- **Neu:** Aktualisiert sich Claude Code, prüft die AMW die neue Version selbst: Ein Arbeiter versucht mit dem kleinsten
  Modell Zugriffe außerhalb seines Platzes, jeder muss abgelehnt werden (wenige Cent, etwa eine Minute). Besteht die Version,
  starten die Arbeiter wie gewohnt weiter; der Bericht liegt als Dokument vor. Sonst schaltet die AMW den Wartungsmodus an und
  fragt Lead und dich. `amw claude status` zeigt den Stand, `amw claude freigeben` gibt von Hand frei.
- **Neu:** Ein schon gegebenes GRÜN lässt sich mit Grund zurücknehmen (`amw pruefung zuruecknehmen P… --grund …`, Prüfer, Lead
  oder du). Der Stand gilt danach nicht mehr als geprüft, ein Merge-OK darauf fällt weg; im Verlauf bleibt sichtbar, dass er
  grün war.
- **Verbessert:** Ein Versionswechsel von Claude Code zählt nie als Fehlschlag eines Pakets.
- **Verbessert:** Der Co-Entwickler eines Projekts darf Themen anlegen – im Terminal und über den Connector. Betreuer und
  Projekt-Stil setzen weiter du oder der Lead; freigeben, zurückgeben und markieren bleibt bei dir.
- **Behoben:** Ein Auftrag zu einer anderen Aufgabe weckt den Agenten jetzt, sobald er eine Pause macht oder sein laufendes Stück
  wartet – nicht erst, wenn das Stück fertig ist. Steht die Aufgabe des Auftrags in der Liste vor dem laufenden Stück, wartet er
  nicht auf dieses Stück.
- **Behoben:** Nach der Auslieferung eines Bündels stehen alle seine Pakete auf fertig, auch wenn das Bündel vorher einmal
  neu gebaut wurde. Bisher blieben dann alle bis auf eines offen.

## 1.153.0 – 21.11.2026 · Posteingang über alle Projekte
- **Neu:** Nachrichten zeigen alles an dich aus allen Projekten auf diesem PC in einer Liste. Jede Zeile trägt ihr Projekt mit
  Farbmarke, oben wählst du „Alle Projekte“ oder eines. Die Reiter heißen jetzt „An dich“, „Mitlesen“ (bisher Team-Chat) und
  „Gesendet“.
- **Neu:** „An dich“ zeigt zuerst nur Offenes, darüber „n offen für dich“. Was du liest, bleibt stehen, bis du die Seite verlässt.
- **Verbessert:** Der Knopf heißt jetzt „Erledigt“ (auch „Alle erledigt“) – er hakt die Nachricht ab, am PC, online und am Handy.
- **Neu:** Rechts steht der ganze Verlauf wie im Mail-Programm – alles zum selben Bezug, auch was Agenten untereinander dazu
  schrieben. In der Liste siehst du „· n im Verlauf“. Am Handy zeigt das Gespräch nur noch den Verlauf und „‹ zurück“.
- **Verbessert:** „Mitlesen“ zeigt ebenfalls alle Projekte mit Projekt-Filter. Fragen bleiben ihr eigener Menüpunkt.
- **Verbessert:** Ein Test prüft, dass jede versionierte Textdatei LF hat (außer *.cmd/*.ps1 laut .gitattributes). Ändert eine
  Prüfbitte eine Datei fast nur in Zeilenenden oder Leerzeichen, warnt sie mit dem Dateinamen.
- **Verbessert:** `amw lauf ausfuehren` legt die ganze Ausgabe immer auch als Datei ab, ohne `--ergebnis` unter
  `laeufe/L<nr>.txt` neben der Datenbank; `amw lauf zeige` nennt den Pfad.
- **Behoben:** Wechselst du die Seite oder einen Reiter, während die vorige noch lädt, zeichnet die vorige nicht mehr
  darüber – auch nicht beim ersten Laden der Startseite. Dialoge öffnen trotzdem.
- **Behoben:** Am Handy stand oben kurz ein leerer Projekt-Knopf, solange die Projektliste noch lud.
- **Behoben:** Fünf Dateien mit CRLF auf LF gebracht; `amw befehle` schreibt LF auch unter Windows.

## 1.152.6 – 21.11.2026 · Probebetrieb S8: Tests für bestehenden Code
- **Intern:** 6 Paket(e) ohne sichtbare Änderung (Tests und Pflege).

## 1.152.5 – 21.11.2026 · Pakete bleiben freigegeben, Arbeitsplätze wie das Projekt
- **Behoben:** Wird ein Bündel nicht ausgeliefert, bleiben seine Pakete freigegeben – das nächste `amw paket buendeln --alle`
  nimmt sie ohne neue Freigabe wieder mit.
- **Behoben:** Arbeitsplätze und die Prüfung der Pakete haben dieselben Zeilenenden wie das Projekt. Vorher sah ein Arbeiter
  jede Datei, die er anfasste, ganz als geändert, und die Tests der Prüfung liefen auf anderen Dateien als im Projekt.

## 1.152.3 – 21.11.2026 · Bündel-Gesamtlauf läuft wieder
- **Behoben:** Der Gesamtlauf eines Bündels bricht nicht mehr mit „Arbeitsbaum verschoben“ ab, wenn die Nacharbeit (etwa die
  Webseite bauen) Dateien mit gleichem Inhalt neu schreibt. Das Bündel nimmt jetzt dieselben Zeilenenden wie das Projekt.
- **Neu:** `amw paket buendeln --gesamtlauf buendel-X.Y.Z` stößt den Gesamtlauf eines vorhandenen Bündels neu an.

## 1.152.1 – 21.11.2026 · Neue Claude-Code-Version für Arbeiter
- **Behoben:** Arbeiter auf den Arbeitsplätzen laufen wieder mit der aktuellen Claude-Code-Version 2.1.330. Die AMW hatte sie
  abgebrochen, weil diese Version noch nicht geprüft war. Die Probe, dass ein Arbeiter nichts außerhalb seines Platzes ändern
  kann, ist mit 2.1.330 bestanden.

## 1.152.0 – 21.11.2026 · Niemand wartet still
- **Neu:** Endet ein Gesamtlauf grün auf genau dem Stand, den der Prüfer grün gegeben hat, meldet die AMW dem Prüfer von selbst
  „freigabereif“ mit dem fertigen Befehl für das Merge-OK; ist er rot, erfahren es Prüfer und Bauer.
- **Neu:** Bleibt eine Nachricht an den Lead nach dem Weckruf 10 Minuten ungelesen und hat er nichts geschrieben, weckt die
  AMW ihn einmal nach.
- **Verbessert:** Eine Bitte an den Lead (Merge-OK, prüfen, freigeben, entscheiden) geht nur noch als Frage – als Info, die
  nicht weckt, lehnt die AMW sie ab.
- **Behoben:** Zwei Aufgaben auf demselben Stand lassen sich wieder beide prüfen und gemeinsam ausliefern.
- **Behoben:** Ein vom Lead angenommenes Paket hält Auslieferungen nicht mehr im Wartungsmodus an; nach kurzem
  Herausnehmen lässt es sich wieder annehmen.
- **Behoben:** Der Pakettyp „test-ergaenzen“ lässt sich jetzt speichern (Datenbank-Schema 34; die AMW stellt beim ersten Start
  von selbst um).

## 1.151.1 – 21.11.2026 · Themen ruhiger
- **Verbessert:** „neu prüfen“ ist jetzt grau wie „in Arbeit“ – das erledigt die KI, nicht du.
- **Verbessert:** Der Grund für „neu prüfen“ („wegen: B… · Datum“) steht auch in der Themen-Liste, klein unter dem Namen.

## 1.151.0 – 21.11.2026 · Themen auf einen Blick
- **Neu:** Menüpunkt „Themen“: jedes Thema mit genau einem Status – wartet auf dich, neu prüfen (mit Grund), in Arbeit oder
  freigegeben. Ein Thema öffnet sich als ein lesbarer Text. Am PC gibt es nur, was gerade geht: Freigeben, Zurück mit Notiz,
  Bearbeiten (dein Text gilt als von dir freigegeben) und Löschen markieren; die Notiz geht als Auftrag an den Betreuer des
  Themas. Mit „+ Thema“ legst du selbst eins an. Am Handy liest du mit und siehst zuerst die Liste. Wartende Themen stehen
  unter „Für dich“ und führen direkt hin; „neu prüfen“ prüft zuerst die KI.
- **Neu:** Den Status setzt niemand von Hand – die AMW leitet ihn aus Fassungen, Beschlüssen und deinen Handlungen ab. Agenten
  sehen ihn mit `amw thema status` und liefern neue Fassungen wie bisher.

## 1.150.2 – 21.11.2026 · Geprüfte Pakete annehmen, Tests für bestehenden Code
- **Behoben:** Ein Paket, das nach der Prüfung an den Lead geht (z. B. „test-schreiben“), kam bisher nie in die Merge-Liste,
  und sein geprüfter Stand lag nur noch im Archiv. Die AMW hebt den Stand jetzt im Projekt auf, und `amw paket annehmen <nr>
  --grund …` (Lead oder du) bringt das Paket nach dem Lesen unter „Bereit zum Merge“.
- **Neu:** Pakettyp `test-ergaenzen` für Pakete, die nur Tests für bestehenden Code schreiben: Sie dürfen ausschließlich
  Testdateien ändern, ihre Tests müssen grün laufen (mindestens einer wirklich ausgeführt), und der Lead liest sie. Der Typ
  `test-schreiben` bleibt für einen Test zu einer Änderung (rot gegen den alten Stand).

## 1.150.1 – 21.11.2026 · Nacharbeit Rechte, Leerlauf, Wochenlimit
- **Behoben:** Einstellungen, die Rechte vergeben (Prüfer der Pakete, Empfänger des Leerlauf-Weckrufs, Halt beim Wochenlimit,
  Blick und Außen-Prüfung vor der Merge-Freigabe), setzt „Entwickler“ nur noch aus dem eigenen Terminal oder der Workbench –
  nicht aus einer Agenten-Sitzung. Der Lead darf weiter.
- **Behoben:** Der Leerlauf-Weckruf nennt keine Pakete für kopflose Arbeiter mehr als freie Aufgaben – die übernimmt nie ein
  interaktiver Agent.
- **Verbessert:** Beim Halt am Wochenlimit steht in der Meldung an den Lead, dass auch er nichts Neues anfängt; die Hilfe
  nennt, dass auch ein Co-Entwickler angehalten wird.

## 1.150.0 – 21.11.2026 · Pakete bündeln ohne Coder
- **Neu:** `amw paket buendeln --alle` setzt die freigegebenen p-Pakete zu einem Release-Stand zusammen: in einem eigenen
  Arbeitsordner, mit neuer Versionsnummer, Versionshinweisen aus den Hinweisen der Pakete und einem Gesamtlauf. Ist er grün,
  bekommt der Lead „Bündel X.Y.Z bereit“ mit den Befehlen zum Freigeben und Ausliefern.
- **Neu:** Passt ein Paket nicht auf die anderen, bleibt es draußen und wartet auf den Lead; der Rest wird gebündelt.
- **Neu:** Projekt-Einstellungen `version_datei`, `changelog_datei`, `gesamtlauf_befehl` und `buendel_schritt` sagen, was ein
  Projekt zum Bündeln braucht.

## 1.149.1 – 21.11.2026 · Neue Claude-Code-Version für Arbeiter
- **Behoben:** Arbeiter auf den Arbeitsplätzen laufen wieder mit der aktuellen Claude-Code-Version 2.1.329. Die AMW hatte sie
  abgebrochen, weil diese Version noch nicht geprüft war. Die Probe, dass ein Arbeiter nichts außerhalb seines Platzes ändern
  kann, ist mit 2.1.329 bestanden.

## 1.149.0 – 21.11.2026 · Halt beim Wochenlimit
- **Neu:** Erreicht der Verbrauch des Wochenlimits eine einstellbare Schwelle (Vorgabe 95 %), hält die AMW alle Coder an: Sie
  beenden ihre Arbeit sauber mit Zwischenstand, nichts wird hart beendet. Du und der Lead bekommen eine Meldung. Mit
  „weiter“ hebst du den Halt auf, sonst geht es nach dem Wochenwechsel von selbst weiter. Die Schwelle stellst du unter
  Einstellungen › Projekt ein (leer = aus).

## 1.148.0 – 20.11.2026 · Führung übergeben
- **Neu:** `amw agent lead <neuer Lead> --co <bisheriger Lead> --grund …` übergibt die Führung in einem Schritt – nie zwei
  Leads, nie keiner. Weckrufe, Fragen an den Lead, Prüfbitten, Planungs- und Leerlauf-Weckrufe gehen danach an den neuen Lead.
- **Neu:** Der bisherige Lead kann Co-Entwickler werden: Er hält Worte und Beschlüsse fest, legt Dokumente ab und fragt dich
  direkt, plant aber nicht, prüft nicht und gibt kein Merge-OK. Sein Dateiaustausch läuft weiter unter seinem Namen.
- **Behoben:** Kein Agent kann sich mehr selbst zum Lead machen: die Rolle vergeben, den Lead wechseln oder einen Lead anlegen
  geht nur durch den Lead oder durch dich – mit `--von Entwickler` nur in deinem eigenen Terminal, nicht aus einer Agenten-Sitzung.

## 1.147.0 – 19.11.2026 · Der Lead merkt, wenn ein Agent nichts zu tun hat
- **Neu:** Hat ein Agent im Terminal seit 10 Minuten nichts zu tun – keine laufende Aufgabe, keine ohne offenen Grund, und er
  wartet weder auf einen eigenen Lauf noch auf eine Prüfung –, bekommt der Lead einen Weckruf: welcher Agent, seit wann, und
  welche Aufgaben der aktiven Meilensteine noch niemand bearbeitet. Einmal je Ruhephase. Wer ihn bekommt und nach wie vielen
  Minuten, stellen Lead oder Mensch ein (`leerlauf_lead`, `leerlauf_lead_min`); einen Lead, der als Chat arbeitet, weckt die
  AMW nicht.

## 1.146.0 – 19.11.2026 · Agentenstart sicher
- **Neu:** Hat die AMW einen Agenten gestartet und meldet sich seine Sitzung nach 3 Minuten nicht an, bekommen du und der Lead
  eine Meldung „… gestartet, meldet sich nicht an“ – mit den Fehlern des Hooks, falls es welche gab.
- **Behoben:** Die AMW startet einen Agenten nur noch in einem eingerichteten Ordner. Ohne AMW-Hook meldete sich die Sitzung
  nie an (keine Benachrichtigungen, Anzeige „beendet“); jetzt sagt der Start, welcher Befehl den Ordner einrichtet.
- **Behoben:** Lief die letzte Sitzung eines Agenten in einem anderen Ordner, setzt die AMW sie nicht mehr fort, sondern
  beginnt eine neue – sonst lud der Agent die Notizen jenes Ordners. Das gilt auch für die Startzeilen und das Startskript.
- **Verbessert:** Scheitert die Anmeldung beim Start einer Sitzung, sagt der Hinweis im Fenster, dass die Sitzung vermutlich
  nicht angemeldet ist, und der Fehler steht im Protokoll des Hooks.

## 1.145.3 – 19.11.2026 · Tests ohne Spuren im Arbeitsordner
- **Behoben:** Die Tests legten bei jedem Lauf ein Startskript `agenten-start.bat` im Arbeitsordner bzw. im Prüfklon ab. Es
  landet jetzt im Temp-Ordner des Testlaufs. Mit `AMW_STARTSKRIPT` lässt sich der Ort des Startskripts auch sonst ändern.

## 1.145.2 – 19.11.2026 · Alte Wartegründe sichtbar
- **Verbessert:** Bekommt eine wartende Aufgabe mit `--auf` einen neuen Grund, bleiben die alten offen. Der Befehl sagt das
  jetzt gleich dazu und nennt den Weg zum Abhaken (`--erledigt <Grund>`, auch zusammen mit `--auf` in einem Schritt). Hilfe
  „Reihenfolge“ und die Befehlshilfe erklären es.

## 1.145.1 – 19.11.2026 · Kleine Korrekturen vor dem Probebetrieb
- **Behoben:** Die Meldung „Platz frei, kein startklares Paket“ nennt den Meilenstein mit der Nummer, die überall sonst steht.
- **Behoben:** Für ein Paket, das noch im Entwurf ist, schlägt die AMW keinen Agentenstart mehr vor. Ein Paket für eine neue
  Sitzung schlägt sie nur vor, wenn es dran ist (nicht geparkt, wartet auf nichts).
- **Behoben:** Liefert die Release-Kette mehrere Versionen auf einmal aus, bekommt eine geprüfte Version darunter ihr eigenes
  Release, auch wenn danach schon Arbeit für die nächste Version unter ihrer Nummer liegt.

## 1.145.0 – 17.11.2026 · Bereit zum Merge, eine Freigabe für alle
- **Neu:** Unter Planung › Aufgaben › Pakete steht „Bereit zum Merge“: jedes Paket, das die AMW fertig geprüft hat, mit den
  geänderten Dateien und den Änderungen zum Aufklappen. „Alle freigeben“ gibt sie am PC auf einmal frei (im Terminal
  `amw paket freigeben --alle`); die AMW holt je Paket genau seinen Stand als eigenen Zweig ins Projekt und vermerkt Prüfung
  und Merge-OK – ausgeliefert wird wie immer über die Kette. Danach steht das Paket auf fertig, und sein Arbeitsplatz ist frei.
- **Neu:** Ändert ein Paket Code auf dem Online-Server, siehst du es dir vor der Freigabe an („erst ansehen“, mit kurzer
  Prüfliste). Unter Einstellungen › Projekt stellst nur du ein, wann dieser Blick nötig ist und ob Aufrufe nach außen ein Paket
  anhalten oder nur als Hinweis erscheinen. Ändert eine Auslieferung Server-Code, steht das im Versionshinweis.

## 1.144.0 – 17.11.2026 · Dienst-Ausfall robust
- **Verbessert:** War der Dienst lange weg (Absturz, PC aus), meldet er das beim nächsten Start mit Push.
- **Verbessert:** Steht der Dienst länger als 10 Minuten still, bekommen die Agenten bei jeder Eingabe einen Hinweis und melden es.
- **Behoben:** Ein Arbeiter, der fertig war, als sein Starter wegfiel, wird nicht mehr als Abbruch gewertet: die AMW holt die
  Prüfung nach und entscheidet wie sonst. Ein gerade gestartetes Paket gilt in der ersten Minute nicht als verwaist.

## 1.143.0 – 17.11.2026 · Die AMW schlägt Starts vor
- **Neu:** Läuft ein Agent nicht, obwohl er dran wäre, steht unter „Für dich“ „<Agent> starten?“ mit dem Grund: ein Paket
  „neue Sitzung“ ist für ihn fällig, er ist abgestürzt und hat noch Arbeit, oder er hat Arbeit und keine Sitzung. „Starten“
  startet ihn nach deiner Bestätigung aus dem Startprofil (mit allen Prüfungen), „Nicht jetzt“ lässt ihn 12 Stunden in Ruhe.
  Ohne deine Bestätigung startet nichts; am Handy siehst du den Vorschlag nur.
- **Behoben:** Der Versionshinweis zu 1.135.0 hieß „Agenten startet nur der Mensch“ – gemeint ist: die AMW startet Agenten nur
  nach deiner Bestätigung.

## 1.142.0 – 17.11.2026 · Arbeitspakete im Blick
- **Neu:** Planung › Aufgaben › Pakete zeigt alle Pakete für kopflose Arbeiter mit Art, Zustand, Kosten und – wenn eines nicht
  startet – dem Grund in Worten („Startet nicht: alle Arbeitsplätze belegt“). Wartet ein Paket auf den Lead oder auf dich, steht
  dort, wer dran ist. „Was bedeuten die Zustände?“ zeigt, welcher Zustand als fertig, läuft, wartet oder blockiert zählt.
- **Neu:** Am PC kannst du ein Paket vorziehen oder zurückstellen, alle neuen Starts pausieren, einem laufenden Arbeiter beim
  Arbeiten zusehen („Mitlesen“) und ihn mit der Notbremse samt Unterprozessen beenden – jeder Eingriff steht im
  Planungs-Protokoll. Online und am Handy ist die Liste nur zum Lesen.

## 1.141.2 – 17.11.2026 · Jeder Stand geprüft
- **Behoben:** Die Auslieferung geht nur noch, wenn jede Aufgabe mit einem Commit im ausgelieferten Bereich als neueste
  Prüfung „grün“ hat – auf einem Stand, der diesen Commit enthält. Ein roter Stand unter einer grünen Spitze hält sie an.

## 1.141.1 – 17.11.2026 · Versionsnummer wird frei
- **Behoben:** Wird eine Aufgabe neu aufgesetzt, gibt ihre alte Prüfung die Versionsnummer frei – es belegt nur noch die neueste
  offene oder grüne Prüfung einer Aufgabe eine Nummer.

## 1.141.0 – 17.11.2026 · Sperrliste für Arbeiter vollständig
- **Behoben (für Arbeitsplätze):** Ein Arbeiter darf keine Datei mehr ändern, die ihn abschottet, prüft, startet oder Rechte
  vergibt (u. a. Wächter, Prüfung, Entscheidung, Datenbank, Rechte, Befehle), und keine Datei, die Python oder Werkzeuge
  beim Start von selbst laden. Die Liste gibt es genau einmal.

## 1.140.0 – 17.11.2026 · Die AMW startet Pakete am Arbeitsplatz selbst
- **Neu (für Arbeitsplätze):** Der Dienst startet startklare p-Pakete selbst – Wächter, Platz vorbereiten, Abnahme vor dem Bau
  rot, Arbeiter in einem eigenen Prozess (übersteht einen Neustart des Dienstes), danach eigene Prüfung und Entscheidung. Ist
  ein Platz frei und nichts startklar, bekommt der Lead einmal einen Hinweis. Von Hand: `amw paket starten N` (Lead/Mensch).

## 1.139.0 – 17.11.2026 · Eigene Prüfung nach einem Arbeiter-Lauf
- **Neu (für Arbeitsplätze):** Nach einem Lauf prüft die AMW selbst – außerhalb des Arbeitsplatzes, mit eigenem Prüf-Repo:
  nur geplante Bereiche, keine gesperrten oder automatisch geladenen Dateien, keine Zugangsdaten, keine neuen Adressen nach
  außen, keine Verweise nach außen; dann committet sie den Stand selbst und führt Abnahme und eine feste Kurzsuite in einem frischen Checkout aus.
  Eine feste Tabelle entscheidet danach, wohin das Paket geht (bereit zum Merge, einmal nachbessern oder an den Prüfer);
  hängt ein Lauf, meldet die AMW es. Agenten im Terminal melden mit `--zweig` und bekommen die Prüfbitte mit dem Befund.

## 1.137.0 – 17.11.2026 · Ergebnis eines Pakets melden
- **Neu (für Arbeitsplätze):** Ein Arbeiter meldet sein Ergebnis über ein eigenes Werkzeug, das nur für seinen Lauf da ist –
  ohne Schlüssel und ohne Datei; es gilt die letzte gültige Meldung, die AMW prüft sie selbst nach. Kosten jedes Laufs werden
  automatisch erfasst. Agenten im Terminal melden dasselbe mit `amw paket ergebnis N` (JSON über stdin oder einzelne Schalter).

## 1.136.1 – 17.11.2026 · Auslieferung genauer
- **Behoben:** Die Auslieferung veröffentlicht eine Zwischenversion nur noch, wenn sie eine eigene grüne Prüfung auf genau
  ihrem Stand hat – sonst geht sie in der obersten Version auf.
- **Behoben:** Ein Zweigname, der zugleich wie ein Commit-Kürzel aussieht, hielt die Auslieferung an.
- **Behoben:** Bricht die Auslieferung unerwartet ab, sagt die Meldung jetzt, wie man den Wartungsmodus aufhebt; nach dem
  Zurückspielen einer älteren Datenbank zählt der Wächter Fehlläufe wieder richtig.

## 1.136.0 – 17.11.2026 · Abgeschottete Arbeiter am Arbeitsplatz
- **Neu (für Arbeitsplätze):** Die AMW kann einen kopflosen Arbeiter (`claude -p`) starten, der nur im Klon seines Platzes
  liest und schreibt, nur den Abnahme-Befehl ausführt (kein git – committen tut die AMW) und keine fremden Einstellungen, Hooks oder
  MCP-Server lädt. Weicht seine Startmeldung ab, wird er sofort beendet. Die Notbremse (`amw platz notbremse N`, nur der
  Mensch) beendet ihn samt aller Kindprozesse. Ohne Arbeitsplätze ändert sich nichts.

## 1.135.0 – 17.11.2026 · Agenten startet die AMW nur nach deiner Bestätigung
- **Richtigstellung (1.143.0):** Gemeint ist: Einen Agenten startet die AMW nur nach deiner Bestätigung; seit 1.143.0 schlägt sie
  Starts unter „Für dich“ selbst vor. Ursprünglicher Eintrag:
- **Verbessert:** Einen Agenten startet nur noch der Mensch – in der Workbench am PC (mit Rückfrage) oder im eigenen Terminal
  mit `--von Entwickler`. Ein Agent, auch der Lead, kann keinen Agenten starten, und online gibt es den Knopf nicht.
- **Verbessert:** Vor dem Start prüft die AMW, ob der Ordner noch da ist und ob ein Zwilling entstünde: Meldet der Ordner jede
  Sitzung als anderen Agenten oder für ein anderes Projekt an, oder arbeitet dort gerade ein Agent eines anderen Projekts,
  startet sie nicht und sagt warum.
- **Verbessert:** Ein Start setzt zuerst die letzte Sitzung fort; gibt es die nicht mehr, beginnt eine neue mit der
  Startanweisung – wie im Startskript. Lange Pfade in Meldungen brechen auf dem Handy um.

## 1.134.0 – 17.11.2026 · Wächter für Arbeitsplatz-Pakete
- **Neu:** Bevor die AMW ein Paket am Arbeitsplatz startet, prüft ein Wächter zehn feste Regeln – fehlende Abnahme,
  Überschneidung, schwere Pakete, volle Plätze, gesperrte Bereiche, Abnahme schon grün, Wartungsmodus, Wochenlimit ab
  80 %, Pause nach zwei unklaren Läufen, keine Plätze. Jeder Grund steht mit Nummer im Protokoll (`amw waechter`).
  Eine Auslieferung setzt den Wartungsmodus und wartet, bis laufende Pakete enden. Ohne Plätze ändert sich nichts.

## 1.131.3 – 17.11.2026 · Datenbank des Dienstes geschützt
- **Behoben:** Befehle aus einem Entwicklungs- oder Prüfordner können die Datenbank des Dienstes nur noch lesen –
  nicht mehr ändern oder auf ein neues Schema heben. Dort mit eigener Datei arbeiten (`AMW_DB`).
- **Behoben:** Die Auslieferung hielt an, wenn eine Aufgabe neu aufgesetzt worden war und ihre alte Prüfung noch grün
  stand. Jetzt zählt je Aufgabe nur die neueste grüne Prüfung.

## 1.131.2 – 17.11.2026 · Merge-OK durch den Prüfer
- **Neu:** Das Merge-OK gibt jetzt auch der Prüfer, der die jüngste Prüfung einer Aufgabe grün gesetzt hat – ohne volle
  Lead-Rechte. Eine Ausnahme vom Gesamtlauf vermerkt weiter nur der Lead.

## 1.131.1 – 17.11.2026 · „wartet auf dich“ nur, wenn du dran bist
- **Behoben:** Auf der Team-Karte stand „wartet auf dich“, obwohl der Agent auf den TL wartete – eine alte Aufgabe im Eingang
  hatte noch einen Wartegrund beim Menschen. Jetzt zählen nur aktive Aufgaben, die wirklich auf dich warten (auch über eine
  offene Frage an dich); wartet der Agent auf jemand anderen, steht dort grau „wartet auf TL“. Auf dem Handy bricht das
  Etikett in schmalen Karten um.

## 1.131.0 – 17.11.2026 · Arbeitspakete für kopflose Arbeiter
- **Neu:** Jede Aufgabe kann sagen, wer sie ausführt: ein vorhandener Agent (wie bisher), eine neue Sitzung oder ein frischer
  `claude -p`-Arbeiter (`--paket p`). Dazu gibt der Lead an, womit gearbeitet wird – Modell, Effort, Gewicht, Ressourcen,
  „nie gleichzeitig mit“, gemeinsame Ressource, Pakettyp – neben Abnahme-Befehl und Bereichen. `amw paket zeigen` zeigt alles,
  auch die Vorgaben; fehlt einem p-Paket etwas, sagt die AMW es gleich.
- **Neu:** p-Pakete haben eigene Zustände (Entwurf, startklar, läuft, abgegeben, in der Abnahme, bereit zum Merge, gemergt,
  fertig; daneben blockiert, unklar, wartet auf interaktiv, abgebrochen, zurückgestellt). Nur erlaubte Wechsel gehen, jeder
  steht im Planungs-Protokoll; in Planung und Übersicht erscheint ein p-Paket wie jede Aufgabe. Alle anderen Aufgaben bleiben,
  wie sie sind.
- **Verbessert:** Die Messung nimmt für p-Pakete die echten Zeitpunkte statt der Näherung.
- **Neu:** Hilfe „p-Pakete schreiben“ für den Lead. Die Datenbank bekommt dafür eine neue Tabelle (Schema 33); bestehende Daten
  bleiben unverändert.

## 1.130.0 – 17.11.2026 · Arbeitsplätze löschen nichts
- **Geändert:** Das Zurücksetzen eines Arbeitsplatzes löscht nichts mehr. Reste – ungesicherte Änderungen als Patch,
  Commits, fremde Dateien, der Datenordner – wandern ins Archiv neben den Plätzen; ist das Paket fertig, schiebt
  `amw platz aufraeumen` sie in den Lösch-Ordner, den nur der Mensch leert. `amw platz liste` zeigt, wie viel darin liegt.

## 1.129.0 – 17.11.2026 · Abnahme durch die AMW
- **Neu (für Arbeitsplätze):** Die AMW führt die Abnahme eines Pakets selbst aus – im Platz, mit Zeitlimit, ein hängender
  Test wird samt Kindprozessen beendet. Vor dem Bau muss sie rot sein. Danach prüft ein Diff-Tor, dass nur geplante
  Bereiche geändert sind und kein gesperrter Pfad (eine Liste: Auslieferung, Rechte, Hooks, Testskripte …; Testdateien
  nur beim Pakettyp „test-schreiben“). Arbeitsplätze löschen nur noch, wo eine Markierung liegt. Ohne Plätze ändert
  sich nichts.

## 1.128.0 – 17.11.2026 · Arbeitsplätze für kopflose Agenten
- **Neu:** Für Agenten ohne eigenes Fenster (`claude -p`) gibt es Arbeitsplätze: je Platz ein eigener Klon des Projekts
  und ein eigener Datenordner mit eigener Datenbank und eigenem Port – die echte Datenbank bleibt unberührt. Wo und wie
  viele, legt nur der Mensch in den Projekt-Einstellungen fest (platz_wurzel, plaetze); ohne Einstellung ändert sich nichts.
  `amw platz liste | vorbereiten N | zuruecksetzen N` – Zurücksetzen macht den Platz auch nach einem Abbruch sauber.

## 1.127.0 – 17.11.2026 · Wartezeit und Kosten je Aufgabe
- **Neu:** Im Fenster einer Aufgabe stehen neben den Kosten die Zeiten – aktiv und wartet (vor dem Start, beim Bauen nach
  Grund, nach der Abgabe) – und was nicht gemessen ist; `amw messung --vergleich` stellt die Woche der Vorwoche gegenüber. `amw messung` zeigt das für alle Aufgaben, `amw kosten
  erfassen` ordnet Läufe außerhalb einer Sitzung (z. B. `claude -p`) einer Aufgabe zu. Kosten einer Aufgabe, die gerade
  wartet, gehen nicht mehr an sie, sondern an die, an der der Agent wirklich arbeitet.

## 1.126.0 – 17.11.2026 · Meilenstein-Karte für den Menschen
- **Neu:** Ein Klick auf einen Balken in der Planung öffnet eine Karte, die zeigt, wo der Meilenstein steht und wo du
  eingreifen kannst: wer verantwortlich ist, ein Satz wie „5 von 15 Aufgaben fertig · 1 läuft · 1 wartet auf dich ·
  8 blockiert“, eine Zeitschiene bis zum Ziel und „was läuft, was hängt“ – nach Ursache gebündelt, mit dem passenden Knopf
  („Frage beantworten“, „Lauf vorziehen“, „Lead anschreiben“). Darunter die Aufgaben selbst, offene zuerst, je mit einer
  kleinen Zeitlinie und „verschoben aus Meilenstein …“.
- **Neu:** „Vorziehen“ zieht einen Meilenstein eins nach vorn; der Lead bekommt eine Meldung. Aktivieren, Abschließen,
  Rückblick und Bearbeiten stehen unter „Mehr … · Für den Lead“.
- **Verbessert:** Die Zeitleiste ist auch bei Farbsehschwäche lesbar: farbenblind-sichere Farben und zusätzlich Muster
  (geplant hohl, knapp gerippt, zu spät schräg gestreift).

## 1.125.3 – 16.11.2026 · Gelesen ist gelesen
- **Behoben:** Nachrichten, die du gelesen hattest, kamen immer wieder als neu. Jetzt hakt Antippen eine Nachricht als
  gelesen ab; dazu „Gelesen“ je Nachricht und „Alle gelesen“. Neue Nachträge zu einer Frage gelten als gelesen, sobald die
  Frage angezeigt wird. Online gilt „gelesen“ sofort auch auf der Nachrichten-Seite und im Zähler, nicht erst nach der
  Synchronisierung.

## 1.125.2 – 16.11.2026 · Keine ungeprüften Commits bei der Auslieferung
- **Behoben:** Beim Neu-Aufsetzen übernahm die Auslieferung eine Freigabe auch dann, wenn darunter ein neuer, noch
  ungeprüfter Commit lag. Jetzt geht eine Freigabe nur mit, wenn jeder Commit bis dahin geprüft ist; sonst hält die
  Auslieferung an und nennt die ungeprüften Commits.

## 1.125.1 – 16.11.2026 · Dienst überall gleich
- **Behoben:** Kopfzeile und Karte „Zustand“ zeigen den Dienst aus derselben Quelle – „Dienst läuft“ oben und „aus“ in
  der Karte gibt es nicht mehr. Der Verweis auf neue Nachrichten in „Für dich“ steht ohne Einrückung.

## 1.125.0 – 16.11.2026 · Chat-Leads sind nicht „beendet“
- **Behoben:** Ein Lead, der als Chat über den Connector (MCP) arbeitete, stand nach drei Stunden als „beendet“ – nur der
  Dateiaustausch setzte sein Lebenszeichen. Jetzt zählt jeder angenommene Aufruf. `amw agent liste` zeigt einen Chat als
  „aktiv (Chat)“ bzw. „zuletzt … (Chat)“, die Workbench „Chat – zuletzt da …“.

## 1.124.0 – 16.11.2026 · Eigene Arbeitskopien selbst aufräumen
- **Grund-Regelwerk 6:** G14 „Löschen und fremde Prozesse nur der Mensch“ hat eine einzige Ausnahme – eigene Arbeitskopien
  (git worktree) ohne offene Änderungen, deren Zweig gemergt ist, entfernt der Agent selbst.
- **Claude-Ablagen:** Solche Arbeitskopien schlägt die AMW dem Agenten der Sitzung vor (einmal, mit dem fertigen Befehl
  git worktree remove und prune); alle anderen bleiben Vorschläge an dich.
- **Neue Fassung einer Grundregel:** Der Abgleich unter Wissen › Regeln zeigt „neue Fassung“, der Lead bekommt einmal
  eine Meldung; „Neue Fassung übernehmen“ bzw. `amw regelwerk uebernehmen G14` ändert die Regel mit eigenem Beschluss.

## 1.123.0 – 16.11.2026 · Übersicht und sieben Menüpunkte
- **Weniger Menü:** Übersicht · Fragen · Planung · Nachrichten · Wissen · Betrieb · Einstellungen. Was bisher ein eigener
  Menüpunkt war, ist jetzt ein Reiter seines Bereichs: Aufgaben und Verlauf unter Planung, Team-Chat unter Nachrichten,
  Dokumente und Versionshinweise unter Wissen. Alte Adressen (z. B. #arbeit, #verlauf) zeigen den Reiter.
- **Neue Übersicht:** vier Karten auf einen Blick – „Für dich“ (Fragen, Freigaben und Schritte, bei denen du etwas tun
  musst, dazu neue Nachrichten), „Läuft gerade“ (arbeitende Agenten, Läufe, Warteschlange), „Stand“ (aktive Meilensteine
  mit Fortschritt) und „Zustand“ (Dienst, Arbeitsspeicher, Festplatten, Synchronisierung, Kosten heute, Wochenlimit).
  Team und Leitstand bleiben darunter.
- **Fragen** mit den Reitern Offen · Freigaben · Geparkt · Erledigt: Freigaben zeigt vorgelegte Spezifikationen und Pläne,
  Erledigt die zuletzt beantworteten Fragen mit deiner Antwort – auch online.
- **Am Handy** unten Übersicht, Fragen, Planung, Nachrichten und „Mehr“ – darunter Wissen, Betrieb, Einstellungen.

## 1.122.0 – 16.11.2026 · Schlüssel für den Connector
- **Behoben:** Ein Connector (MCP) für die Claude-App ließ sich in jedem Chat einschalten – auch im Chat eines anderen
  Projekts. Jetzt hat jedes Projekt einen eigenen Schlüssel (Einstellungen › Projekt, einmal sichtbar, nur als Prüfwert auf
  dem PC gespeichert); ohne ihn lehnt der Connector jeden Aufruf ohne Wirkung ab. Jeder Aufruf steht im Verlauf. Die Workbench
  zeigt die fertige Zeile für die Konfiguration. Nach dem Update einmal den Schlüssel erzeugen und in den Lead-Chat eintragen.

## 1.121.0 – 16.11.2026 · Lesebefehle für Leads
- **Neu:** `amw dokument zeigen D12 --inhalt` zeigt den Text eines Dokuments (bei Bildern und Videos Hinweis und Pfad),
  `amw agent liste` nennt je Agent die aktuelle Aufgabe und worauf sie wartet, `amw wortlaut --liste --seit …` zeigt die
  erfassten Aussagen des Menschen. Alles auch über den Dateiaustausch und als Werkzeuge in der Claude-App.

## 1.120.0 – 16.11.2026 · Leichte Läufe parallel
- **Verbessert:** Normales Bauen und Testen läuft parallel und wartet nie mehr auf schwere Läufe (KI, Grafikkarte, Fenster,
  viel Speicher). Wie viele leichte Läufe zugleich rechnen, steht unter Einstellungen › Dieser PC. Ein Agent rechnet nie zwei
  Läufe zugleich in seinem Ordner.
- **Neu:** `amw lauf ausfuehren` und `amw lauf start` verlangen `--leicht` oder `--schwer` (auch `amw rezept setzen`) – die
  AMW rät nicht mehr. Fehlt die Angabe, erklärt die Meldung den Unterschied.

## 1.119.0 – 16.11.2026 · Neu aufsetzen ohne neue Freigaben
- **Verbessert:** Wird ein geprüfter Stand nur neu aufgesetzt (gleicher Inhalt, neuer Commit), übernimmt die Auslieferung Grün
  und Merge-OK selbst und vermerkt die Quelle. Nur wenn sich der Inhalt geändert hat, braucht es eine neue Prüfung.
- **Verbessert:** Fehlen Freigaben, nennt die Auslieferung alle auf einmal (Prüfung, Merge-OK, Gesamtlauf, Reihenfolge) statt
  eine nach der anderen.

## 1.118.1 – 15.11.2026 · Web-Abzug in Sekunden
- **Behoben:** Der Web-Abzug der Auslieferung lief zweimal ins Zeitlimit (über 10 bzw. 30 Minuten). Jetzt entsteht der
  web-Zweig als ein Commit mit dem Inhalt von web/ über dem bisherigen Stand – in Sekunden, immer ohne Umschreiben.

## 1.118.0 – 15.11.2026 · Grund-Regelwerk 5: „Nur über die Schnittstelle“
- **Neu:** Grundregel G21 „Nur über die Schnittstelle“ – lesen und schreiben nur mit amw-Befehlen, kein direkter Zugriff auf
  die Datenbank. Eigene Regeln, die dem widersprechen, nennt der Abgleich; der Lead bekommt einmal eine Info.
- **Behoben:** `amw regelwerk uebernehmen` brach in Projekten mit Themen mit „--thema fehlt“ ab. Neu: `… uebernehmen alle`
  übernimmt alle fehlenden Grundregeln, `… G1,G2` mehrere.

## 1.117.0 – 15.11.2026 · Symbol im Infobereich: Bildschirm ohne Browser
- **Neu:** Ein Punkt im Infobereich der Taskleiste zeigt, ob der Bildschirm für Agenten frei ist (bernstein), du kurz da bist
  (blau) oder er belegt ist (grau). Rechtsklick: frei bis …, „Ich bin kurz da“ (15/30/60 min), Freigabe beenden, Workbench öffnen.
- **Neu:** „Ich bin kurz da“ – der Bildschirm bleibt frei, deine Eingaben schließen ihn nicht; neue Läufe mit Fenster warten,
  bis der PC 2 Minuten ruht. Die Startseite zeigt es in der Kachel „Bildschirm“.

## 1.116.1 – 15.11.2026 · Bildschirm: kein Programmname mehr
- **Verbessert:** Schließt die AMW die Bildschirm-Freigabe wegen einer Eingabe am PC, nennt sie kein Programm im Vordergrund
  mehr – auch frühere Einträge im Verlauf sind bereinigt.

## 1.116.0 – 15.11.2026 · Ladeanzeige und schnellere Dokumente online
- **Neu:** Dauert ein Abruf, den du ausgelöst hast, länger als 0,3 Sekunden, erscheint das AMW-Logo als Ladeanzeige – die
  Kreise wandern auf dem Schriftzug. Bei „Bewegung reduzieren“ wird es nur sanft heller und dunkler.
- **Verbessert:** Die Dokumente-Filter der Online-Seite laden den Suchtext nur noch, wenn du wirklich suchst – ein Klick auf
  einen Filter lädt statt bis zu 2 MB nur noch die schlanke Liste.

## 1.115.0 – 15.11.2026 · Die AMW als MCP-Server
- **Neu:** Chat-Leads in der Claude-App rufen die AMW direkt als Werkzeug auf – ohne Dateiaustausch: `takt`, Nachrichten,
  Aufgaben und Meilensteine, Prüfungen und Merge-OK, Fragen, Beschlüsse, Lead-Runde, Läufe, Suche, Dokumente, Bildschirm.
  Der Server läuft auf diesem PC (`python F:/amw/amw-mcp.py --projekt … --von …`), je Projekt ein Eintrag in der
  Claude-Konfiguration; jedes Werkzeug ruft denselben Befehl wie die Kommandozeile. Hilfe „AMW mit Claude verbinden (MCP)“.

## 1.114.0 – 15.11.2026 · Claude-Ablagen im Blick
- **Neu:** Die AMW misst die Arbeitsordner der Claude-Sitzungen in %TEMP%\claude – je Sitzung Größe, Dateien, letzte Änderung,
  mit Agent und Projekt (Einstellungen › Dieser PC › „Claude-Ablagen“). Ab 10 GB bekommen Lead und Mensch eine Meldung; alte
  Arbeitskopien stehen mit einem fertigen Befehl zum Entfernen da. Die AMW löscht nichts.

## 1.113.0 – 15.11.2026 · `amw takt`: ein Durchgang für Leads in einem Aufruf
- **Neu:** `amw takt` zeigt einem Lead knapp, was er für einen Durchgang braucht: Postfach mit gekürztem Text, Prüfbitten an
  ihn, Fragen der Agenten, Antworten des Menschen, Läufe mit Wartegrund, Lead-Runde und Auslieferungen – je Punkt eine Zeile
  mit dem Befehl zum ganz Lesen. Geht auch über den Dateiaustausch. `--abhaken` erledigt gezeigte Infos und Meldungen.
- **Neu:** `amw pruefung zeige <P>` und `amw frage zeige <F>` zeigen eine Prüfbitte bzw. Frage ganz (mit Optionen und Antwort).
- **Verbessert:** Der Dateiaustausch antwortet in ein bis zwei Sekunden statt bis zu sechs.
- **Verbessert:** Die Lese-Kopie der Datenbank für Leads ist abschaltbar (Einstellungen › Dieser PC) und ab jetzt aus – Leads
  nehmen `amw takt`. Hilfe „Rhythmus für einen Lead, der als Chat arbeitet“ ergänzt.
## 1.112.3 – 15.11.2026 · Keine aufblitzenden Konsolenfenster mehr
- **Behoben:** Der Dienst öffnete bei jeder Abfrage von git und gh kurz ein Konsolenfenster – am laufenden Band. Alle
  Hilfsprogramme laufen jetzt ohne Fenster.
- **Verbessert:** Nach gemergten Pull-Requests sieht die AMW nur noch auf Anlass nach (Merge-OK, Auslieferung, Ende
  eines Laufs mit Aufgabe, Meldung „gemergt“), sonst höchstens stündlich – statt alle 5 Minuten.
- **Behoben:** Ein Programm, das vor einem Lauf gestartet war, galt manchmal als dessen Fenster (Windows vergibt
  Prozess-Nummern neu). War eine Meldung trotzdem falsch, hebt `amw lauf fehlalarm <nr>` die Sperre auf.

## 1.112.2 – 15.11.2026 · Vorziehen und Grafikspeicher ehrlich
- **Behoben:** „Vorgezogen“ hieß bei einem Lead nur „vor die Läufe des eigenen Projekts“ – die Liste sah aber aus, als stünde
  der Lauf ganz vorn. Jetzt steht dort „vom Entwickler vorgezogen“ (ganz vorn, vor jeder Vorrang-Stufe) oder „im Projekt
  vorgezogen“, und `amw lauf vorziehen` sagt, wo der Lauf jetzt steht.
- **Verbessert:** Wartet ein Lauf auf Grafikspeicher, der so nie frei wird, nennt der Wartegrund die Karte, was außerhalb der
  Schlange belegt ist und von welchen Programmen, und was hilft (weniger anfordern oder ohne `--gpu`). Der Hinweis kommt schon
  beim Einreihen.

## 1.112.1 – 15.11.2026 · Knopf „Vorziehen“ für wartende Läufe
- **Behoben:** Die Meldung „… wartet seit … Minuten“ verwies auf einen Knopf zum Vorziehen, den es nicht gab. Jetzt stehen in
  der Rechner-Kachel (Start › Leitstand) die wartenden Läufe dieses Projekts mit Platz und je einem Knopf „Vorziehen“ (mit
  Rückfrage) – am PC, im Heimnetz und online (dort nur für System-Admins).

## 1.112.0 – 15.11.2026 · Messen: Lesen Agenten nach einem Weckruf noch nach?
- Betrieb › „Wofür das Geld geht“ zeigt, nach wie vielen Weckrufen ein Agent innerhalb von 2 Minuten noch einmal nachgelesen
  hat (`amw lesen`/`amw kontext`), und die Kosten je Weckruf vor und nach 1.98.0 (seitdem bringen Weckrufe den Inhalt mit).
  Gemessen wird ab dieser Version; festgehalten werden nur Zeit, Agent und Befehl, nie Inhalte.

## 1.111.2 – 15.11.2026 · Auch Konsolenfenster aus Läufen ohne Bildschirm werden erkannt
- **Behoben:** Öffnete ein Lauf ohne Bildschirm-Anmeldung ein neues Konsolenfenster (z. B. ein Konsolenprogramm, dem Windows
  je Aufruf eine eigene Konsole gibt), merkte die AMW das nicht – das Fenster gehört der Konsole bzw. dem Windows Terminal,
  nicht dem Lauf. Jetzt fragt sie für jeden Prozess des Laufs nach seinem Konsolenfenster und behandelt es wie jedes andere
  Fenster (melden, als Lauf mit Fenster führen, danach nur mit Bildschirm-Anmeldung). Hilfe „Schwere Läufe“: solche
  Programme unsichtbar starten.

## 1.111.1 – 15.11.2026 · Lead-Runde auch auf der Online-Seite
- Unter Nachrichten › Lead-Runde liest du jetzt auch auf der Online-Seite mit (z. B. am iPad) – nur lesen. Weil dort Einträge
  aller Projekte stehen, zeigt die Online-Seite sie nur System-Admins; die Seite prüft das selbst. Hilfe „Lead-Runde“ ergänzt.

## 1.111.0 – 15.11.2026 · Prüfbitte mit sichtbarer Änderung nur mit Bild
- Ändert ein Stand die Seite oder die Hilfe, nimmt `amw pruefung bitte` ihn nur an, wenn an der Aufgabe ein Bild-Dokument hängt,
  und nennt die Bilder in der Prüfbitte von selbst. Ohne Bild geht es nur mit `--ohne-bild <Grund>`, der Grund steht in der
  Prüfbitte. In einem Stapel zählt nur die eigene Änderung, nicht die der Stände darunter.

## 1.110.0 – 15.11.2026 · Versionsnummer wird schon bei der Prüfbitte geprüft
- `amw pruefung bitte` liest die Versionsnummer aus dem Stand (`VERSION`, `amw/__init__.py` oder `package.json`) und lehnt ab,
  wenn sie nicht über main liegt, als Tag schon existiert oder eine andere Aufgabe sie in einer offenen oder grünen, noch nicht
  ausgelieferten Prüfung trägt. Die Meldung nennt die nächste freie Nummer. Dieselbe Aufgabe darf ihre Nummer behalten
  (neuer Stand nach ROT, neu aufgesetzt). So fällt eine doppelt vergebene Nummer nicht erst beim Ausliefern auf.

## 1.109.2 – 15.11.2026 · Merge-OK passt immer zur Prüfung
- **Behoben:** Ein Merge-OK auf den falschen Zweig ließ die Auslieferung später hängen. Jetzt nimmt `amw freigabe merge A…`
  ohne `--zweig` den Zweig der jüngsten grünen Prüfung dieser Aufgabe; ein angegebener Zweig muss zu einer grünen oder offenen
  Prüfung passen, sonst nennt die Meldung die passenden. Vor der ersten Prüfung gilt ein Merge-OK wie bisher für jeden Zweig.

## 1.109.1 – 15.11.2026 · Release-Kette: Versionszeilen kommen vor dem Web-Abzug
- **Behoben:** Lief der Web-Abzug ins Zeitlimit, fehlten danach die Versionszeilen und der Lead musste sie von Hand eintragen.
  Jetzt trägt die Kette Versionszeilen (auch für Zwischenversionen) und die fertigen Aufgaben direkt nach dem GitHub-Release
  ein, erst danach kommt der Web-Abzug. Scheitert er, nennt die Meldung, wie er nachgeholt wird.
- Der Web-Abzug darf jetzt bis zu 30 Minuten dauern (unter Last brauchte er mehr als die bisherigen 10).

## 1.109.0 – 15.11.2026 · Planung: Wer gerade woran arbeitet, sieht man am Balken
- In der Übersicht hat jeder Meilenstein-Balken, an dem gerade jemand eine Aufgabe bearbeitet, einen dünnen hellen Rahmen,
  der sanft pulsiert – unabhängig von der Farbe des Balkens („zu spät“ verdeckt „in Arbeit“ nicht mehr). Neben dem Titel
  stehen die Kürzel der Agenten, die daran arbeiten (▶ CC1). Wer Bewegung abgeschaltet hat, sieht einen festen Rahmen.
- Die Legende erklärt den Rahmen.

## 1.108.0 – 15.11.2026 · Dauerläufe neben dem schweren Lauf
- Neue Laufart „Dauerlauf“ (`amw lauf start|ausfuehren --dauerlauf --braucht-gb <GB>`): kopflos, ohne KI, Grafikkarte oder
  Fenster, mit fester Speichergrenze. Er läuft neben dem schweren Lauf, seine Grenze zählt in die Vormerkung, und unter
  „Rechner“ steht, wie viel er gerade belegt.
- Belegt ein Dauerlauf mehr als seine Grenze oder wird der Arbeitsspeicher knapp, bittet die AMW seinen Agenten, ihn zu
  beenden, und sagt es dem Lead – beenden tut sie ihn nicht selbst. Hilfe „Schwere Läufe“ ergänzt.

## 1.107.0 – 15.11.2026 · Planung automatisch: Meilenstein fertig, wenn alle Aufgaben fertig sind
- Sind alle Aufgaben eines geplanten oder aktiven Meilensteins fertig (oder verworfen), steht in seiner Karte „Alle Aufgaben
  sind fertig – Meilenstein abschließen?“ mit dem Knopf „Abschließen“, und der Lead bekommt einmal eine Meldung.
- Neue Projekt-Einstellung „Meilenstein fertig“: vorschlagen (Vorgabe) oder automatisch – dann schließt die AMW selbst ab.
  Ist eine Version Pflicht und fehlt, bleibt es beim Vorschlag mit diesem Grund. Neue Frage in der Hilfe „Planung“.

## 1.106.3 – 15.11.2026 · Entwickler-Kanal entfernt – Wünsche an die AMW über die Lead-Runde
- **Geändert:** Den Entwickler-Kanal gibt es nicht mehr. Leads anderer Projekte schreiben Fehler, Wünsche und Fragen zur AMW
  in die Lead-Runde an den AMW-Lead (`amw runde schreiben --an AMW --kurz …`); der verteilt sie. Wer den Entwickler der AMW
  direkt anschreibt, bekommt genau diesen Weg genannt; die Startinformationen der Leads nennen ihn ebenfalls.
- Der Entwickler der AMW liest, schreibt und wird geweckt nur noch in seinem eigenen Projekt. Die Einstellung „Entwickler
  der AMW“ unter Dieser PC dient nur noch der Anzeige und diesem Hinweis.

## 1.106.2 – 15.11.2026 · Läufe ohne Bildschirm, die doch ein Fenster öffnen
- **Behoben:** Läufe, die ohne Bildschirm angemeldet waren, öffneten trotzdem Fenster (z. B. ein Spiel), während du am PC
  warst – und kamen nach dem Schließen wieder. Jetzt merkt die AMW das Fenster: Der Lauf gilt ab dann als Lauf mit Fenster,
  sein Agent und der Lead erfahren es, und bei belegtem Bildschirm wird der Agent gebeten, ihn zu beenden (die AMW beendet
  nichts selbst). Denselben Lauf nimmt die Schlange danach 7 Tage lang nur noch mit Bildschirm-Anmeldung an – ebenso, wenn
  so ein Lauf bei belegtem Bildschirm von außen geschlossen wurde.
- Die AMW sieht dabei nur, welches Programm ein Fenster hat, nie den Fenstertitel; Hilfe „Schwere Läufe“ ergänzt.

## 1.106.1 – 15.11.2026 · Einstellungen gehen nicht mehr verloren
- **Behoben:** Nach „Gespeichert“ stand eine Einstellung dieses PCs (z. B. „Aus dem Heimnetz erreichbar“) manchmal trotzdem
  leer in der Datei. War die Datei im selben Moment gesperrt oder halb geschrieben, galt sie als leer, und das Speichern schrieb
  nur den neuen Wert – alle anderen waren weg. Jetzt liest das Speichern kurz erneut; bleibt die Datei unlesbar, wird nichts
  überschrieben und du bekommst eine Meldung.
- **Behoben:** „Dieser PC“ speichert nur, was du dort geändert hast. Ein älter geladenes Formular (zweiter Tab, Handy im
  Heimnetz) überschreibt so keine Werte mehr, die inzwischen anders gesetzt wurden.
- Ist ein Wert ungültig, steht der Fehler rot direkt am Feld. Das Heimnetz-Feld zeigt „z. B. 192.168.178.0/24 – leer = aus“,
  und das Protokoll des Dienstes nennt beim Start die tatsächliche Adresse der Workbench (mit Heimnetz: alle Adressen).

## 1.106.0 – 15.11.2026 · Planung automatisch: fertig nach dem Merge auf GitHub
- Projekte, die über GitHub-Pull-Requests mergen: Beginnt der Titel eines gemergten PRs mit der Aufgabe („A1234: …“,
  „[A1234] …“, mehrere: „A1234, A1235: …“) oder steht im Text „fertig: A1234“ bzw. „closes A1234“, und sind seine Prüfungen
  grün, steht die Aufgabe dieses Projekts von selbst auf fertig (Beleg = Merge-Commit), der Lead bekommt eine Info. Bloßes
  Erwähnen („Vorarbeit für A1235“) zählt nicht.
  Offene Kriterien halten das nicht auf, sie stehen in der Info. Wartet die Aufgabe auf den Entwickler, bleibt sie offen.
- Die AMW fragt dafür höchstens alle 5 Minuten mit `gh` im Projektordner nach, in einem eigenen Faden des Dienstes – nur,
  wenn die Betriebsart die Verbindung erlaubt (github.com nur in „Cloud“, ein GitHub im Firmennetz auch in „Server“).
  Die Anmeldung hält `gh` selbst; in der AMW liegt kein Schlüssel. Abschaltbar mit „Planung automatisch“.

## 1.105.0 – 15.11.2026 · Planung: neue Aufgaben erst in den Eingang
- Neue Projekt-Einstellung „Neue Aufgaben landen“: im Meilenstein (wie bisher) oder im Eingang. Im Eingang landen neue
  Aufgaben ohne Meilenstein dort, wo auch der Leitstand „im Eingang“ zählt; die Planung zeigt sie oben unter „Eingang (n)“.
  Der Lead zieht sie bewusst in einen Meilenstein. Wer beim Anlegen einen Meilenstein nennt, landet direkt darin.
- In diesem Modus fragt `amw aufgabe neu` nicht mehr nach dem Meilenstein; neue Frage in der Hilfe „Planung“.

## 1.104.0 – 15.11.2026 · Planung automatisch: Auslieferung schließt die Aufgaben
- Nach `amw release ausliefern` steht jede Aufgabe von selbst auf fertig, deren grüner Stand mit Merge-OK in der Auslieferung
  steckt; Beleg ist der geprüfte Stand. Offene Kriterien halten das nicht auf – sie stehen in der Zusammenfassung, und der
  Lead erfährt sie mit der Meldung „Version … live“. Wartet eine Aufgabe auf den Entwickler (etwa eine Bestätigung am Gerät),
  bleibt sie offen.
- Den Satz für die Versionshinweise gibt die Prüfbitte mit: `amw pruefung bitte … --aufgabe <nr> --gruppe neu --hinweis "…"`;
  der Prüfer sieht ihn in der Prüfbitte.
- Abschaltbar mit „Planung automatisch“ (Einstellungen › Projekt); Hilfe „Prüfstufen und Release-Takt“ ergänzt.

## 1.103.0 – 15.11.2026 · Bildschirm-Freigabe verlängern, ohne zu beenden
- Ist der Bildschirm für Agenten frei, ändert „Bis ändern“ in der Bildschirm-Kachel nur die Uhrzeit, bis wann er frei bleibt:
  neue Uhrzeit eintragen oder „+1 Stunde“, „bis 22:00“, „ohne Ende“. Die Freigabe läuft weiter, im Verlauf steht die Änderung.
  Am PC, im Heimnetz und online (dort wie das Freigeben nur für System-Admins).
- `amw schirm frei --bis 15:00` ändert bei freiem Bildschirm ebenfalls nur die Uhrzeit (ohne `--bis`: ohne Ende).

## 1.102.0 – 15.11.2026 · Planung automatisch: Lauf startet die Aufgabe
- Startet ein Agent einen Lauf zu einer seiner Aufgaben, die noch nicht begonnen hat, steht sie jetzt von selbst auf „läuft“.
  Welche Aufgabe, liest die AMW aus dem Lauf, aus „A1234“ in der Beschreibung oder aus dem Zweig (a1234, a1234-2). Wartet
  die Aufgabe auf jemanden oder arbeitet der Agent schon an einem anderen Stück, bleibt alles, wie es ist.
- Neue Projekt-Einstellung „Planung automatisch“ (an/aus, Vorgabe an); neue Frage in der Hilfe „Planung“.

## 1.101.0 – 15.11.2026 · Planung: Was seit dem Start dazukam
- Unter jedem aktiven oder fertigen Meilenstein steht jetzt „Seit Start (05.11.): +5 hinzugekommen · 3 erledigt · 8 offen“, beim
  Drüberfahren über seinen Balken in der Übersicht ebenso. „Wo stehen wir gerade?“ zeigt „+5 seit Start“. So ist zu sehen,
  warum ein Balken nicht kürzer wird, obwohl Aufgaben fertig werden.
- Als hinzugekommen zählt, was nach dem Start angelegt oder in den Meilenstein gezogen wurde. Das Hineinziehen hält die AMW ab
  jetzt fest; früher hineingezogene Aufgaben zählen nur, wenn sie nach dem Start angelegt wurden.
- `amw bogen liste` zeigt dieselben Zahlen; neue Frage in der Hilfe „Planung“.

## 1.100.4 – 15.11.2026 · Bilder im Vollbild auf dem iPad
- **Behoben:** Auf dem iPad blieb ein Bild im Vollbild schwarz, obwohl Vorschau und Dialog es zeigten. Beim Laden des Bilds
  hatte das Vollbild noch keine Größe, das Bild wurde auf null verkleinert und danach nie neu eingepasst. Jetzt passt die
  Seite das Bild an, sobald das Vollbild seine Größe hat, und bei jeder Größenänderung (Drehen, Wechsel ins Vollbild).

## 1.100.3 – 15.11.2026 · Startseite am Handy und iPad
- **Behoben:** Am iPhone lagen die Kacheln des Leitstands auf der Startseite (Arbeit der Agenten, Bildschirm, Sitzungen …)
  übereinander, die Texte liefen ineinander. Jetzt stehen sie am Handy untereinander und am iPad zu zweit; das Wochenlimit
  geht über die ganze Breite.
- **Behoben:** Am Handy und am iPad ragten einige Seiten über den Rand: die Filterleiste unter „Nachrichten“ und „Lead-Runde“,
  die beiden Spalten dort am iPad, die Vorgeschichte geparkter Fragen, die Meldungen im Agenten-Fenster und die
  Agenten-Einstellungen. Lange Pfade und Adressen brechen jetzt um.
- Der Bedienbarkeits-Rundgang prüft jede Seite zusätzlich in iPad-Größe (820 × 1180) und meldet Inhalt, der aus seiner
  Kachel läuft.

## 1.100.2 – 14.11.2026 · Videos auf iPad und iPhone
- **Behoben:** Auf iPad und iPhone (Safari) ließen sich Videos aus „Dokumente“ online nicht abspielen. Ursache: Die Seite schickte
  Videos und Bilder mit einer Abschottung („sandbox“), bei der Safari seinen Videospieler abschaltet (WebKit-Fehler 225865).
  Bilder und Videos gehen jetzt ohne diese Abschottung hinaus – sie führen ohnehin nichts aus; SVG, Entwürfe (Mockups) und
  Downloads bleiben abgeschottet.
- **Videos starten schneller:** Neu abgelegte MP4-Videos bekommen ihr Inhaltsverzeichnis an den Anfang (wie „faststart“) –
  nur umgepackt, nichts neu codiert. Safari zeigt sie dann sofort, ohne erst das Dateiende zu holen.

## 1.100.1 – 14.11.2026 · Warteschlange: Läufe mit Fenster kommen wieder dran
- Wartet ein Lauf auf Grafikspeicher, den gerade kein anderer Lauf belegt (den Rest hält zum Beispiel der Bildschirm), hält er
  andere Läufe mit Fenster nicht mehr auf. Sie ziehen vorbei, und er startet, sobald genug Grafikspeicher frei ist. Vorher
  konnten Läufe mit Fenster dahinter stundenlang stehen.

## 1.100.0 – 14.11.2026 · Planung: Wo stehen wir?
- **„Wo stehen wir gerade?“** steht ganz oben in der Zeitleiste: der aktive Meilenstein mit „3 von 8 Aufgaben erledigt · Ziel …“,
  das nächste Ziel und „Gerade in Arbeit: CC an „Titel““ – ein Klick öffnet die Aufgabe.
- **Jetzt-Linie:** kräftig, mit „Jetzt“ beschriftet und nie durch einen Namen im Balken; beim Drüberfahren Datum, Uhrzeit und was
  gerade läuft. Ein Satz über der Grafik erklärt sie; die Legende ist kürzer und in Alltagssprache.
- **Aktives vorne:** Erledigte Meilensteine sind ausgeblendet („Erledigte einblenden“, blass mit ✓) und in der Zeitleiste eingeklappt.
- **Nichts verschwindet:** Offene Aufgaben ohne Meilenstein stehen unten unter „Ohne Meilenstein (n)“. Legt der Lead eine Aufgabe
  ohne `--bogen` an, solange ein Meilenstein aktiv oder geplant ist, nennt die AMW die Meilensteine mit einem Vorschlag; bewusst
  ohne: `--ohne-bogen`.
- **„Was der Rechner heute gemacht hat“** ist eingeklappt, bis du es öffnest; Läufe tragen ihren Namen nur, wo er hinpasst.
- Neue Hilfe „Planung: Wo stehen wir?“.

## 1.99.0 – 14.11.2026 · Profil ändern auf dein Wort, Release-Kette robuster
- Der Lead darf das Profil eines Agenten (Ordner, Zusatzordner, Modell, Denkaufwand …) jetzt auch ohne dich am PC ändern –
  aber nur auf dein Wort: `amw agent profil <Agent> … --wort W<nr>`, auch über den Dateiaustausch. Das Wort muss aus diesem
  Projekt und höchstens 24 Stunden alt sein. Rolle sowie eigene Rechte und Fernsteuerung des Leads bleiben beim Entwickler.
- Jede solche Änderung steht mit alt → neu im Verlauf, und du bekommst eine Info dazu.
- **Betrieb › Dienst:** Startet die AMW einen hängenden Teil neu, steht jetzt dabei, an welcher Stelle er hing – im
  Protokoll die ganze Aufrufkette. So lässt sich die Ursache finden.
- **Release-Kette:** Unversionierte Dateien im Arbeitsbaum halten sie nicht mehr an (nur ein Hinweis). Alte grüne Prüfungen
  von neu aufgesetzten oder längst ausgelieferten Ständen gelten als überholt und blockieren keine Auslieferung mehr.

## 1.98.0 – 14.11.2026 · Weckrufe mit Inhalt und Lead-Runde
- **Neu: Lead-Runde** – ein Kanal nur zwischen den Leads aller Projekte dieses PCs: `amw runde schreiben --kurz …` und
  `amw runde lesen [--neu]`, auch über den Dateiaustausch. Andere Agenten haben keinen Zugang. Du liest am PC unter
  Nachrichten › Lead-Runde mit.
- **Nur Information:** Einträge sind Info oder Frage – nie Aufträge, Stopps oder Freigaben an ein anderes Projekt. Die Richtlinie
  steht oben und unter jedem fremden Eintrag, und sie ist neue Grundregel G20 (Grund-Regelwerk 4).
- **Kein Wecken:** Mit `--an <Projekt>` bekommt der Lead dort zusätzlich eine Info in sein Postfach; Leads sehen
  „Lead-Runde: n neu“ in `amw lesen` und beim Start.
- Neue Hilfe „Lead-Runde“. Datenbank-Schema 32.
- **Ein Weckruf bringt alles mit:** Die Benachrichtigung an einen Agenten enthält jetzt die Nachrichten selbst (Text gekürzt,
  der Rest über `amw lesen <Nr>`), je betroffene Aufgabe eine Zeile mit Status und Wartegrund und darunter, was seit seinem
  letzten Halt neu ist (eigene Läufe fertig oder abgebrochen, Ergebnisse eigener Prüfbitten). Der Agent muss nicht erst
  nachfragen – das spart Durchgänge und Kosten. Nachrichten, die ganz im Weckruf stehen, gelten als gelesen.
- **Gebündelt beim nächsten Halt:** Arbeitet ein Agent gerade, wartet die AMW bis zu seinem nächsten Halt und schickt dann
  alles zusammen als eine Benachrichtigung. Sofort, auch mitten in der Arbeit, kommen nur Stopp, Korrekturen und was der
  Mensch schreibt.
- **Infos wecken nie:** auch nicht an einen einzelnen Empfänger – sie stehen im Postfach.
- Hilfe Nachrichten: „Wann benachrichtigt die AMW einen Agenten?“

## 1.97.1 – 14.11.2026 · Release-Kette: keine Version geht verloren
- Liegen in einem Stand mehrere Versionen (z. B. 1.94.0 unter 1.94.1), bekommt jetzt jede ihren Tag, ihr GitHub-Release und
  ihre Versionszeile – aufsteigend, die oberste bleibt „neueste“.
- Liegt eine kleinere Version grün und freigegeben bereit, die der Stand nicht enthält, hält `amw release ausliefern` an:
  erst sie ausliefern oder neu aufsetzen.
- `amw release version X --nachtrag` (Lead): eine fehlende kleinere Version nachtragen, die es als Git-Tag gibt – Zeit und
  Text kommen aus dem Tag und dem CHANGELOG. Die „letzte Version“ ist immer die höchste Nummer.

## 1.97.0 – 14.11.2026 · Prüfstufen und Release-Takt
- **Prüfstufe in jeder Prüfbitte:** Die AMW sieht nach, welche Dateien ein Stand ändert, und schreibt die Stufe oben in die
  Prüfbitte – hoch (alles mit Rechte- oder Sicherheitsprüfungen: Datenbank, Anmeldung, Befehlszeile, Dienst, Dateiaustausch …), mittel (Oberfläche, Hilfe,
  anderer Code) oder niedrig (nur Doku und Tests), mit den Dateien, die sie bestimmen. Muster je Projekt einstellbar.
- **Einstellungen › Projekt › Prüfstufen (Vorgabe aus):** Eingeschaltet prüft bei „hoch“ der Lead, bei „mittel“ ein anderer
  Agent als der, der gebaut hat. „Niedrig“ geht ohne Prüfbitte raus – mit Merge-OK und einem grünen Gesamtlauf auf genau
  diesem Stand (`amw release ausliefern --zweig X --aufgabe N`). Höher einstufen geht immer (`--stufe`), niedriger nie.
- **Einstellungen › Projekt › Release-Takt (Vorgabe aus):** sofort, täglich um eine Uhrzeit oder je Meilenstein meldet die AMW
  dem Zuständigen für Merges (sonst dem Lead) einmal, was ausgeliefert werden kann. Ausliefern tut sie nie selbst.
- Neue Hilfe „Release-Takt und Prüfstufen“.

## 1.96.0 – 14.11.2026 · Der Dienst passt auf sich selbst auf
- **Betrieb › Dienst:** Hauptschleife, Dateiaustausch, Synchronisierung und KI-Arbeiter melden sich nach jeder Runde. Je Teil
  steht da, ob er läuft (grün, gelb, rot), wann die letzte Runde war, wie lange sie gedauert hat, wie oft er neu gestartet
  wurde und sein letzter Fehler. Steht ein Teil, zeigt auch die Startseite ein Band.
- **Selbstheilung:** Ist der Dateiaustausch oder die Synchronisierung länger still als erlaubt, startet der Dienst ihn neu
  und sagt dir einmal Bescheid – die anderen Teile laufen weiter. Hauptschleife und KI-Arbeiter werden nur gemeldet (ein
  zweiter KI-Arbeiter würde einen laufenden Auftrag noch einmal rechnen). Lange Runden – viele Dateien, ein langer
  KI-Auftrag – gelten nicht als Stillstand.
- Online zählt nur die Farbe je Teil: die Seite wird nicht bei jeder Runde neu hochgeladen.
- Neue Hilfe „Den Dienst im Blick behalten“.

## 1.95.1 – 14.11.2026 · Release-Kette macht den Web-Abzug selbst
- `amw release ausliefern` aktualisiert den web-Zweig jetzt selbst (als leichter Lauf, sichtbar im Leitstand) und hält mit
  klarer Meldung an, wenn das nicht klappt. Bisher sollte der Dienst ihn rechnen – das lehnte er ab, wenn für den Agenten
  kein Arbeitsordner eingetragen war.

## 1.95.0 – 14.11.2026 · Lokale KIs nur bei Bedarf
- **Startet erst mit einem Auftrag:** Die AMW startet eine lokale KI (ComfyUI, Ollama) nicht mehr von selbst, sobald sie nicht
  antwortet, sondern erst, wenn ein Auftrag für sie dran ist. Hat sie die KI selbst gestartet und kommt 30 Minuten lang kein
  Auftrag – und benutzt sie auch sonst niemand, etwa direkt an der AMW vorbei –, beendet sie sie wieder und gibt Arbeits- und Grafikspeicher frei. Eine KI, die du selbst gestartet hast, beendet sie
  nie; die AMW erkennt ihren eigenen Prozess an Nummer und Startzeit.
- **Immer an, wenn du willst:** `amw ki aendern <name> --immer-an` (zurück mit `--bei-bedarf`) oder Einstellungen › Dieser PC ›
  Lokale KIs immer an. Die Minuten bis zum Beenden stellst du dort ebenfalls ein. Betrieb › KI zeigt je KI „nur bei Bedarf“ bzw.
  „immer an“ und ob die AMW sie gestartet hat; `amw ki liste` ebenso.
- Hilfe Lokale KI: warum eine KI plötzlich aus ist und warum Aufträge besser über die AMW laufen als direkt an der KI.

## 1.94.1 – 14.11.2026 · Release-Kette erkennt kurze Stände
- `amw release ausliefern` fand eine grüne Prüfung nicht, wenn die Prüfbitte einen kurzen Stand nannte (z. B. „39ca74a“).
  Jetzt zählen beide Schreibweisen (kurz mindestens 7 Zeichen), und neue Prüfbitten speichern den vollen Stand.
- Hilfe „Schwere Läufe“: warum ein Gesamtlauf nicht für die Auslieferung zählt, wenn erst ein Skript den Ordner wechselt.

## 1.94.0 – 14.11.2026 · Wofür das Geld geht
- **Betrieb › „Wofür das Geld geht“ (am PC):** Jeder Kostenzuwachs einer Sitzung gehört zu den Weckrufen im selben Zeitraum
  („Lauf ist dran“, Prüfbitte, Antwort, Auftrag …), ohne Weckruf zählt er als eigene Arbeit. Teuerster Anlass zuerst, mit
  Anteil, Zahl der Weckrufe und Kosten je Weckruf; „vermeidbar“ markiert, wofür der Agent nichts tun musste. Zeitraum 1, 7
  oder 30 Tage. Dasselbe in der Befehlszeile: `amw verbrauch pareto [--tage N]`.
- Hilfe Agenten: „Wofür geben die Agenten ihr Geld aus?“.

## 1.93.0 – 14.11.2026 · Workbench aus dem Heimnetz (Handy/Tablet im WLAN)
- **Einstellungen › Dieser PC › „Aus dem Heimnetz erreichbar“:** Netzbereich deines WLANs eintragen (z. B.
  192.168.178.0/24) und den Dienst neu starten – dann öffnest du die Workbench auf Handy oder Tablet unter
  http://<Adresse dieses PCs>:8780, mit allen Rechten wie am PC und ohne Anmeldung. Vorgabe: aus.
- **Sicherheit:** nur private Netze (10.x, 172.16–31.x, 192.168.x); jede Anfrage von einer Adresse außerhalb des Bereichs
  wird abgelehnt (ein Gastnetz bleibt so draußen), und als Adresse im Browser zählen nur localhost und IPs aus dem Bereich –
  nie ein Name (Schutz gegen DNS-Rebinding). Solange es an ist, steht „Heimnetz offen: …“ im Leitstand unter „Rechner“.
  Die AMW ändert nichts an Windows; die Hilfe „Betriebsart“ nennt die Firewall-Regel (Port 8780, nur Profil „Privat“).

## 1.92.0 – 13.11.2026 · Release in einem Schritt
- **`amw release ausliefern --zweig X`** (für das Repository der AMW selbst): prüft zuerst alles – grüne Prüfung auf genau
  diesem Stand, Merge-OK des Leads für ihre Aufgabe, grüner Gesamtlauf (ohne ihn nur mit einer Ausnahme, die der Lead
  vermerkt: `amw freigabe merge <Aufgabe> --ausnahme "Grund"`), main lässt sich vorspulen, Arbeitsbaum sauber, Tag neu –
  und macht dann ohne weitere Handgriffe: Sicherung, main vorspulen, Tag, Dienst neu (Version, Schema und quick_check
  geprüft), Push, GitHub-Release mit den Notizen aus dem CHANGELOG, Web-Abzug (rechnet der Dienst), Versionszeile und eine
  Info „Version x live“ an den Lead (weckt nicht). Fehlt etwas oder scheitert ein Schritt: Stopp mit einer Zeile, was
  erledigt ist und was fehlt. Nur im Terminal, nie über den Dateiaustausch.
- **Läufe belegen, was sie wirklich geprüft haben:** Beim tatsächlichen Start schreibt `amw lauf ausfuehren` (und der Dienst)
  den Stand des Ordners in die Ergebnis-Zeile und den Kopf der Ausgabe – „Stand <commit> sauber“ oder „geändert“. Die
  Release-Kette zählt nur einen Gesamtlauf, der genau den Release-Stand sauber geprüft hat; die Beschreibung allein reicht
  nicht mehr.

## 1.91.1 – 13.11.2026 · Tests an 1.91.0 angepasst
- Zwei Browser-Tests erwarteten noch den Stand vor 1.91.0: „Mehr“ am Handy hat jetzt 8 Einträge (mit Team-Chat), und unter
  „Nachrichten“ gibt es den Reiter „Fragen“ nicht mehr – Fragen haben ihre eigene Seite. Am Verhalten ändert sich nichts.

## 1.91.0 – 13.11.2026 · Postfach, Fragen getrennt, Team-Chat
- **Fragen nur unter „Fragen“:** Fragen der Agenten an dich, ihre Rückfragen, Nachträge und deine Antworten stehen nur
  noch unter dem Menüpunkt „Fragen“ – mit eigener Zahl und eigenem Kopf. Unter „Nachrichten“ steht oben nur ein Hinweis
  „n Fragen an dich offen › Fragen“; der Reiter „Fragen“ dort entfällt. Liste und Zahl der Nachrichten passen jetzt immer
  zusammen (bisher standen Nachträge im Eingang, zählten aber nicht – nach dem Parken umgekehrt).
- **Nachrichten = dein Postfach für alles andere:** Jede Zeile zeigt ihre Art – ✉ Nachricht eines Agenten, ⚙ Meldung der
  Workbench. Mehrere offene erledigst du auf einmal: Häkchen setzen oder „alle offenen markieren“, dann „Erledigt (n)“.
- **Neuer Menüpunkt „Team-Chat“:** was Agenten und Lead untereinander schreiben, neueste oben, mit Filter nach Agent und
  Suche – nur zum Lesen, zählt nie. Am PC und online.
- **Behoben:** Nach einer Rückfrage hängte sich jede weitere Nachricht des Agenten an dich von selbst an diese Frage (ein
  fremder Auftrag trug dann den Bezug der Frage). Jetzt gehören zu einer Frage nur ausdrückliche Nachträge; und eine
  Nachricht mit eigenem Bezug hängt sich nur an ein Gespräch mit demselben Bezug.
- Hilfe Nachrichten ergänzt.

## 1.90.0 – 13.11.2026 · Die Warteschlange entscheidet allein, Läufe gehen nicht mehr verloren
- **Läufe überleben das Fenster:** `amw lauf ausfuehren` merkt sich beim Einreihen Befehl, Ordner und Ergebnis-Datei. Beendet
  das Fenster des Agenten den wartenden Befehl (bei knappem Speicher), bleibt der Lauf in der Schlange; ist er dran, startet
  der Dienst genau diesen Befehl im selben Ordner, schreibt die Ausgabe in die Ergebnis-Datei und meldet dem Agenten den
  Rückgabewert. Nichts muss von Hand neu eingereiht werden. Läufe mit Fenster startet der Dienst nicht selbst.
  Sicherheit: Solche Befehle entstehen nur im Terminal des Agenten (nie über Dateiaustausch oder Online-Seite); der Dienst
  führt sie nur im Arbeitsordner (oder Zusatzordner) des Agenten aus, nie bei HALT oder entferntem Agenten, und jede
  Übernahme steht im Verlauf (wer, Befehl, Ordner, Rückgabewert).
- **Dateiaustausch hängt nicht mehr:** Jeder Befehl über den Dateiaustausch hat höchstens 2 Minuten; kommt er nicht zurück,
  bekommt seine Datei ein Fehlerergebnis („Zeitlimit“) und die nächste Datei läuft. Vorher konnte ein einziger Befehl alles
  dahinter aufhalten (13.11.: 20 Minuten Stillstand).
- **Bedarf ohne Schätzen:** Fehlt `--braucht-gb`, nimmt die AMW, was gleiche Läufe desselben Agenten zuletzt gemessen
  gebraucht haben (Median mit Zuschlag) – statt pauschal der Grenze des Projekts.
- **Weniger Weckrufe:** „ist dran“ (bei `lauf ausfuehren`) und „läuft länger als erwartet“ wecken niemanden mehr, sie stehen
  nur in der Workbench. `amw lauf warte` schreibt den Grund nur, wenn er sich ändert.
- Schema 31 (Lauf: Befehl, Ordner, Ergebnis-Datei, Frist, Warte-Prozess, wer ihn startet, gemessene Spitze). Hilfe Schwere Läufe.

## 1.89.1 – 13.11.2026 · Warteschlange: ein Lauf, der nie passt, hält niemanden auf
- **Behoben:** Ein Lauf mit Vorrang, der mehr Arbeitsspeicher brauchte, als selbst bei leerer Schlange frei wird (z. B.
  8 GB + 3 GB Reserve bei 9,4 GB frei), hielt die ganze Warteschlange auf – niemand überholt ihn, und für ihn wurde
  Platz frei gehalten. Jetzt gilt: Läuft kein schwerer Lauf und er passt trotzdem nicht, sperrt er niemanden und es wird
  kein Platz für ihn frei gehalten; er bleibt vorn und startet, sobald genug frei ist. Der Wartegrund sagt es („passt
  auch bei leerer Schlange nicht …“). Läuft etwas, wartet die Schlange wie bisher.

## 1.89.0 – 13.11.2026 · Nachrichten: Liste und Inhalt scrollen getrennt
- **Wie im Mail-Programm:** Unter „Nachrichten“ haben am PC die Liste links und die geöffnete Nachricht rechts je ihren
  eigenen Scrollbereich; die Seite selbst scrollt nicht mehr, Kopf und Reiter bleiben stehen. Wer unten in der Liste eine
  Nachricht öffnet und rechts weiterliest, behält die Liste im Blick; die gewählte Zeile bleibt sichtbar, eine neu
  gewählte Nachricht beginnt rechts oben. Am Handy bleibt es einspaltig (Liste → Nachricht mit Zurück).
- **Einstellungen › Agenten:** Die Liste der Agenten bleibt beim Scrollen des Formulars stehen.
- **Nachrichten öffnen auf „Eingang“,** wenn dort Neues liegt und du keinen Reiter gewählt hattest (bisher „Gesendet“).
- **Bedienbarkeits-Rundgang:** neue Prüfung für Liste und Inhalt nebeneinander – Scrollen im Inhalt muss die Liste
  stehen lassen, nichts darf unter den Fensterrand reichen (A1628).

## 1.88.0 – 13.11.2026 · Benutzer auch unterwegs verwalten
- **Einstellungen › Benutzer auf der Online-Seite:** Projekt-Admins und System-Admins verwalten Benutzer jetzt auch am
  Handy – anlegen, Rolle und Projekte vergeben, sperren und entsperren, freischalten. Ein Projekt-Admin sieht nur die
  Benutzer seiner Projekte und neue, die auf Freigabe warten; er vergibt Rollen höchstens bis Projekt-Admin, nur mit seinen
  eigenen Projekten, und ändert nie einen System-Admin. Freischalten, sperren oder die Rolle ändern darf er nur bei Benutzern,
  die ganz in seinen Projekten liegen und nicht selbst Projekt-Admin sind – sonst könnte er über den Code ein fremdes Konto
  übernehmen. Sich selbst sperren oder die eigene Rolle ändern geht für niemanden.
- **Freischalt-Code online:** Die Seite erzeugt ihn selbst und zeigt ihn genau einmal; gespeichert wird nur sein Hash. Der
  PC prüft danach, ob das erlaubt war – wenn nicht, macht er den Code sofort ungültig. In beiden Fällen bekommst du eine
  Meldung.
- Die Rechte prüfen Seite und PC unabhängig voneinander nach denselben Regeln.
- **Hilfe Benutzer:** online verwalten; die Rollen stehen jetzt wirklich in der Hilfe (der Abschnitt fiel bisher weg).

## 1.87.4 – 13.11.2026 · Vorrang: echtes „hoch“ vor aufgerücktem
- **Behoben:** Ein Lauf, der nach 30 Minuten Wartezeit auf „hoch“ aufgerückt war, stand bei Gleichstand nach Ankunft vor
  einem Lauf aus einem Projekt mit echtem „hoch“. Jetzt zählt bei gleicher Stufe zuerst die Stufe des Projekts, dann die
  Ankunft – in der Warteschlange, beim Anmelden eines Laufs und im Wartegrund. Aufrücken bleibt, damit nichts verhungert.

## 1.87.3 – 13.11.2026 · Nachrichten nur im gewählten Projekt
- **Behoben:** Unter „Nachrichten“ standen auch Nachrichten anderer Projekte, mit dem Filter „Alle Projekte“ – am PC und
  online. Jetzt zeigt die Seite nur das Projekt, das oben gewählt ist; den Filter gibt es nicht mehr. Auch die Zahl am Menü
  „Nachrichten“ zählt nur dieses Projekt.
- **Behoben:** Meldungen der Workbench selbst standen mit dem Absender „AMW“ da – leicht mit dem Projekt AMW zu
  verwechseln. Sie heißen jetzt „System“ (Nachrichten, Startseite, Verlauf, Aufgaben, Dokumente, Agenten).
- Online nennt „Betrieb“ bei Läufen anderer Projekte keinen Projektnamen mehr („anderes Projekt“); am PC wie bisher.

## 1.87.2 – 13.11.2026 · Klarere Meldung bei Prüfungen, vollständige Hilfen
- **Behoben:** `amw pruefung gruen|rot` ohne Nummer meldete „Prüfung PNone gibt es nicht“ – jetzt nennt die AMW die
  offenen Prüfungen für dich und wie der Befehl geht.
- **Behoben:** Zwei Hilfen zeigten einen Abschnitt nicht: die Rollen bei „Benutzer der Online-Seite“ und die Auslöser bei
  „Bildschirm-Freigabe“. Beide stehen jetzt als Tabelle in der Hilfe; ein Test sorgt dafür, dass kein Abschnitt mehr still
  wegfällt.

## 1.87.1 – 13.11.2026 · Grund-Regelwerk auch über den Dateiaustausch
- **Behoben:** `amw regelwerk abgleich` und `amw regelwerk uebernehmen Gx` gehen jetzt auch über den Dateiaustausch –
  ein Lead, der als Chat arbeitet, kann die Grundregeln für sein Projekt vergleichen und übernehmen. Übernehmen bleibt dem
  Lead und dem Menschen vorbehalten.

## 1.87.0 – 13.11.2026 · Vollbild am Handy immer schließbar, Bedienbarkeits-Rundgang
- **Behoben – Vollbild am Handy:** Das ✕ steht fest oben rechts im sichtbaren Bereich (auch neben Kerbe und Browser-
  Leisten); Esc, die Zurück-Taste bzw. Wischgeste und das ✕ schließen nur das Vollbild, der Dokument-Dialog darunter
  bleibt. Mockups und PDFs öffnen im Vollbild mit ✕ und „In neuem Tab“ – vorher ging nur der Rahmen ins Vollbild, am
  Handy ohne Ausweg.
- **Zwei Fenster nach einem Neustart:** Läuft nach einem Neustart per Startskript das alte Fenster eines Agenten noch,
  zeigt die Startseite „Zwei Fenster für …“ (die AMW benachrichtigt nur das neuere; das ältere schließt du selbst) statt
  „Nicht verbunden“ mit dem falschen Rat „anmelden“; ebenso `amw dienst status`.
- **Kleinigkeiten:** Online am Handy ist „Abmelden“ klein rechts oben; im Agenten-Dialog steht die Zahl neuer Nachrichten
  nur noch einmal.
- **Untermenüs am Handy:** Reiter, Filter und Sprungleisten im Seitenkopf, die sich waagrecht wischen lassen, enden nicht
  mehr stumm mitten im Wort – ein Verlauf an der Kante zeigt, dass es dort weitergeht.
- **Bedienbarkeits-Rundgang als Test:** Jede Seite und jeder Dialog wird am PC und am Handy, hell und dunkel, am PC und
  online geprüft – Fehler in der Konsole, nichts ragt seitwärts über den Rand, jedes ✕ im Bild und treffbar, keine
  abgeschnittenen Knopftexte, keine Fokus-Fallen. Neue Seiten hängen sich an dasselbe Gerüst. Geprüft sind Start,
  Nachrichten, Fragen, Planung, Aufgaben (jeder Reiter), Verlauf, Versionshinweise, Wissen (jeder Reiter), Dokumente,
  Betrieb, Einstellungen und die Dialoge zu Agent, Aufgabe, Thema und Dokument.

## 1.86.0 – 13.11.2026 · Empfehlung für Modell und Denkaufwand
- **Größe und Art je Aufgabe:** `amw aufgabe neu|aendern --groesse S|M|L|XL --art text|mechanisch|fehlersuche|oberflaeche|sicherheit|konzept`
  (Schema 30: zwei neue Spalten; `komplexitaet` bleibt, was sie ist). `amw aufgabe neu` erinnert daran, wenn sie fehlen.
- **Empfehlung:** Aus Größe × Art schlägt die AMW Modell und Denkaufwand vor, nach einer Tabelle je Projekt (Einstellungen › Projekt ›
  „Empfehlung Modell · Denkaufwand“; Startwerte sind eine Annahme). An der Aufgabe steht daneben, was fertige Aufgaben derselben
  Zelle gemessen verbraucht haben und wie oft ihre Prüfung rot war, und ob der zugeteilte Agent anders eingestellt ist.
- **Am Agenten:** die Empfehlung aus seinen letzten Aufgaben, „Ins Profil übernehmen“ (am PC); am Startbefehl ein Hinweis, wenn
  Profil und Empfehlung abweichen. Die AMW stellt nichts selbst um und startet niemanden neu – das Profil wirkt beim nächsten Start
  (A1611 Stufe E2, Konzept D906).

## 1.85.0 – 13.11.2026 · Vorrang der Projekte in der Warteschlange
- **Einstellungen › Dieser PC › „Vorrang der Projekte“:** je Projekt hoch, normal oder niedrig (Vorgabe normal). Die
  Einstellung gehört dem PC, nicht einem Projekt; ändern lässt sie sich nur am PC. Sie wirkt sofort.
- **Reihenfolge der Wartenden:** zuerst, was der Mensch vorgezogen hat, dann „hoch“, dann „normal“, dann „niedrig“ –
  innerhalb einer Stufe der Reihe nach, je Spur (CPU, Grafikkarte, Bildschirm) wie bisher. Ein Lauf, der schon läuft,
  wird nie abgebrochen. Ein Lead sortiert weiter nur unter den Läufen seines Projekts um.
- **Wartegrund:** nennt den Vorrang („Platz 1 von 3 (Vorrang für …)“, „vor dir: L12 (anderes Projekt, Vorrang)“) und,
  wenn der Lauf davor auf Arbeitsspeicher wartet, wie viel er braucht und wie viel nutzbar ist. Fehlt Arbeitsspeicher,
  steht dabei, für welchen laufenden Lauf wie viel vorgemerkt ist. Fremde Projekte bleiben ohne Namen.
- **`amw lauf liste`:** zeigt oben, was gerade auf diesem Rechner läuft – auch Läufe anderer Projekte (ohne Inhalt) –
  und wie viel Arbeitsspeicher dafür vorgemerkt ist; in der Warteschlange steht „Vorrang“ bzw. „niedriger Vorrang“.
- **Rechner – heute:** Vorrang-Läufe tragen ▲; Leitstand › „Rechner“ nennt die Projekte mit Vorrang (online nur das
  eigene).
- **Vorgemerkter Arbeitsspeicher:** Ein laufender Lauf ohne eigene Bedarfsangabe hält die Grenze seines Projekts nur
  noch in den ersten 15 Minuten frei; danach zählt, was er wirklich belegt. Läufe mit Angabe wie bisher.
- **Aufrücken nach Wartezeit:** Ein wartender Lauf rückt je 30 Minuten Wartezeit eine Stufe höher, höchstens bis
  „hoch“ – so kommt auch „niedrig“ sicher dran (Einstellungen › Dieser PC, 0 = aus). Der Wartegrund nennt es
  („aufgerückt nach Wartezeit“).
- **Platz freihalten für Vorrang** (Schalter, Vorgabe an): Wartet ein Lauf mit „hoch“, startet ein Lauf mit
  niedrigerer Stufe nur, wenn danach noch Arbeitsspeicher für ihn (sein Bedarf plus Reserve) frei bleibt – auch auf
  einer anderen Spur. Der Wartegrund nennt, für wen Platz frei gehalten wird.
- **Meldung:** Wartet ein Lauf mit „hoch“ trotzdem länger als 20 Minuten, bekommt der Mensch einmal eine Meldung mit
  dem Grund. Abgebrochen wird nichts; vorziehen kann nur der Mensch.
- Hilfe „Schwere Läufe“: zwei neue Fragen (Vorrang, vorgemerkter Arbeitsspeicher) und die neuen Einstellungen (A1623).

## 1.84.1 – 12.11.2026 · Kein Zwilling unter fremdem Namen
- **Behoben:** Eine zweite Claude-Sitzung, die ohne Startskript (ohne `AMW_AGENT`) läuft, konnte mit `--von <name>`
  als ein Agent schreiben, der gerade in einer anderen Sitzung angemeldet ist – Nachrichten lesen und posten, Aufgaben
  abschließen, ihn abmelden. Jetzt lehnt die AMW das ab, solange die angemeldete Sitzung lebt, und nennt sie (Sitzung,
  PID). Ist es wirklich der richtige Agent: `amw anmelden --von <name> --ersetzen`. Das Terminal des Entwicklers und die
  Brücke bleiben wie bisher.
- Hilfe Agenten: neuer Eintrag unter „Typische Fehler“.

## 1.84.0 – 12.11.2026 · Verbrauch je Aufgabe und je Agent
- **Agent › Übersicht › „Verbrauch je Aufgabe“:** Mittel (Median) der letzten zehn fertigen Aufgaben, das eingestellte
  Modell mit Denkaufwand, die Aufgabe in Arbeit bisher und je Aufgabe der Betrag mit Modell/Denkaufwand – als Grundlage,
  um Modell und Denkaufwand im Profil passend einzustellen (wirkt beim nächsten Start; die AMW stellt nichts selbst um).
- **Aufgabe › „Verbrauch“:** der gemessene Gegenwert in Dollar mit Modell/Denkaufwand; ebenso `amw aufgabe zeige <nr>`
  und `amw agent profil <name>`.
- Gerechnet aus dem Kosten-Zähler, den Claude Code je Sitzung meldet (auch im Abo): Jeder Zuwachs gehört zu der Aufgabe,
  die der Agent zu dieser Zeit zuletzt begonnen und noch nicht abgeschlossen hatte – eine Näherung. Kein Schema, keine
  KI (A1611 Stufe E1, Konzept D906).

## 1.83.0 – 12.11.2026 · Startbefehl je Agent zum Kopieren
- **⋯ am Agenten › „Startbefehl …“** und Einstellungen › Agenten › „Startbefehl zum Kopieren“: Ordner, Zusatzordner,
  Modell, Denkaufwand, Rechte, letzte Sitzung – und zwei fertige Zeilen „Fortsetzen“ und „Neu starten“ für PowerShell
  oder die Eingabeaufforderung, mit „Kopieren“. Genau so startet die AMW den Agenten auch selbst; Geheimnisse stehen
  nicht darin. Steht in der Datenbank, also auch nach einem Neustart des PCs da.
- Online nur zum Lesen und nur für System-Admins. Agenten, die als Chat oder in der Desktop-App arbeiten, bekommen den
  Hinweis, dass die AMW sie nicht startet.

## 1.82.0 – 12.11.2026 · Nachträge: Frist einstellbar, „Bildschirm“ überall, Knöpfe in den Hinweisen
- **Einstellungen › Projekt › „Frist für Sichern & beenden“** (Minuten, Vorgabe 5): so lange hat ein Agent Zeit, seinen
  Stand zu sichern und sich abzumelden, bevor der Dienst die Sitzung beendet.
- **„Bildschirm“ statt „Schirm“** auch in den Meldungen an Agenten, in `amw lauf`/`amw schirm` und im Pflicht-Kontext
  (z. B. „Bildschirm ZU seit …“, „Läufe mit Fenster“). Befehle und Optionen heißen weiter so (`amw schirm`, `--schirm`).
- **Startseite:** Jede Warnung hat einen Knopf zu dem Agenten, den sie betrifft; der Hinweis „nicht angemeldet“ führt zur
  Anleitung.
- Tests laufen nie im echten Zugangs-Ordner des PCs: jede Testdatei schottet sich als Erstes ab, ein Test prüft das.

## 1.81.0 – 12.11.2026 · Knopf-Namen im Server-Paket
- `amw web paket`, `amw speicher` und die LIESMICH im Paket nennen die Knöpfe so, wie sie in der Workbench heißen:
  „Verbindung testen“ (Speicher und Synchronisierung) und „Online-Seite testen“ – vorher stand dort „Speicher prüfen“
  bzw. „Seite prüfen“. Ein Test hält Paket und Workbench künftig gleich.

## 1.80.0 – 12.11.2026 · Grund-Regelwerk für bestehende Projekte
- **Wissen › Regeln › „Abgleich mit dem Grund-Regelwerk“:** jede Grundregel neben den Regeln des Projekts – übernommen,
  vermutlich durch eine eigene Regel abgedeckt (mit Verweis) oder fehlt. Nur ein Vorschlag; vorhandene Regeln bleiben.
- **„Übernehmen“** legt eine fehlende Grundregel mit der nächsten freien Nummer an, ein Beschluss nennt die Quelle
  (Lead oder du; online Projekt-Admin).
- `amw regelwerk abgleich [--ablegen]` – mit `--ablegen` als Dokument an den Lead; `amw regelwerk uebernehmen G7`.

## 1.79.0 – 12.11.2026 · Versionen als Pflicht
- **Einstellungen › Projekt › „Versionen“:** Pflicht, empfohlen (Vorgabe für bestehende Projekte) oder aus; neue Projekte
  mit Grund-Regelwerk stehen auf Pflicht. Dazu die Frist, ab der Fertiges ohne Version auffällt (Vorgabe 14 Tage).
- **`amw release version` prüft die Nummer:** Form MAJOR.MINOR.PATCH und größer als die letzte; die Meldung nennt die
  passenden nächsten Nummern.
- **Plan-Check:** ohne eingetragene Version ein Fehler (Pflicht) bzw. Hinweis (empfohlen); liegt Fertiges länger als die
  Frist ohne Version, eine Warnung mit Vorschlag für die nächste Nummer.
- **Meilenstein abschließen** geht bei Pflicht erst, wenn nach seiner letzten fertigen Aufgabe eine Version eingetragen
  ist – nur du kannst trotzdem abschließen.
- Der Pflicht-Kontext der Agenten nennt fehlende Versionen. Hilfe „Versionen eintragen“ (DE/EN).

## 1.78.0 – 12.11.2026 · Nachrichten aus allen Projekten an einer Stelle
- **„Nachrichten“ zeigt alle Projekte zusammen** – am PC alle dieses PCs, online die Projekte, die du sehen darfst.
  Jede Zeile trägt ihr Projekt (Farbpunkt), dazu der Filter „Alle Projekte“ / ein Projekt.
- Antworten, Nachfassen, Erledigt und Zurückziehen gehen an das Projekt der Nachricht; ein Klick auf den Bezug einer
  Nachricht aus einem anderen Projekt wechselt dorthin.
- **Eine Zahl für „an dich“:** Menü „Nachrichten“ und Reiter „Eingang“ zählen dasselbe – offene Nachrichten an dich aus
  allen Projekten (online: deinen), ohne ältere Infos ohne Bezug und ohne Nachträge zu offenen Fragen.

## 1.77.0 – 12.11.2026 · Nachrichten: Startseite aufgeräumt, Fragen als Reiter
- **Startseite:** statt der langen Liste „Nachrichten an dich“ eine Karte mit den drei neuesten und dem Sprung in den
  Eingang; „Ältere als gelesen markieren“ bleibt dort.
- **Fragen gehören zu den Nachrichten:** Die Fragen-Seite trägt dieselbe Reiterleiste Eingang · Gesendet · Fragen.
- **Antworten auf Fragen** haben die Frage als Bezug (Chip „F12 …“ im Gesendet, Klick führt zu den Fragen).

## 1.76.0 – 12.11.2026 · Paket für den eigenen Server im Firmennetz
- **`amw web paket`** baut am PC alles, was ein Webserver der Firma braucht, als eine ZIP: die Online-Seite, eine fertige
  Konfiguration (Adresse des eigenen libSQL-Servers, Schlüssel der Seite, erster Admin), Vorlagen für nginx und Apache,
  docker compose für den libSQL-Server und eine LIESMICH mit den Schritten. Dabei trägt die AMW den Zugang zum Speicher
  und die Adresse der Seite an diesem PC ein. Das Passwort des Admins erscheint einmal; den zweiten Faktor richtet er beim
  ersten Anmelden ein.
- **http im Firmennetz:** Online-Seite, Speicher, eigener ntfy-Server und der Link in Benachrichtigungen dürfen `http://`
  sein, wenn das Ziel im Firmennetz liegt. Die Anmeldeseite und die Einstellungen am PC warnen dann sichtbar; Dateien
  hochladen geht weiterhin nur über https.
- **Zertifikat der Firma** gilt jetzt auch für „Seite prüfen“ und den eigenen ntfy-Server.
- Betriebsart „Eigener Server im Firmennetz“: der Hinweis „wird später unterstützt“ ist weg – sie nennt jetzt den Weg.
- Geprüft gegen einen echten libSQL-Server: Paket bauen, Server mit dem Schlüssel aus dem Paket starten, Seite aus dem
  Paket – der Admin meldet sich an und bekommt den QR-Code für den zweiten Faktor.

## 1.75.0 – 12.11.2026 · Von überall schreiben, der Bezug geht mit
- **„✉ Nachricht dazu“** an Thema, Meilenstein, Beschluss, Lauf und Prüfung: Bezug eingetragen, Empfänger vorgeschlagen
  (Pfleger des Themas, der Agent des Laufs bzw. der Prüfung, sonst der Lead) – änderbar.
- **„Nachrichten dazu“** am Thema und am Meilenstein: das kleine Gespräch zu genau diesem Objekt.
- **Antworten finden ihr Gespräch:** Schreibt ein Agent nur an dich, hängt sich die Nachricht von selbst an deine letzte an
  ihn (bis 2 Tage, noch unbeantwortet) und erbt deren Bezug; `amw posten --neuer-faden` schaltet das ab.
- Der Pflichtkontext der Agenten nennt `--bezug` und das Anhängen.

## 1.74.0 – 12.11.2026 · Nachrichten an einer Stelle
- **Neue Seite „Nachrichten“** (Menü, mit Zahl für Offenes an dich): „Eingang“ – alles an dich, Ungelesenes fett;
  „Gesendet“ – alles von dir, je Empfänger der Stand gesendet › benachrichtigt › gelesen › erledigt (Uhrzeit beim
  Überfahren); „Fragen“ führt zur Fragen-Seite. Filter nach Agent, Bezug, „nur offene“ und Suche.
- **Gespräch** rechts (am Handy als eigene Ansicht): deine Nachricht und die Antworten darauf; „Antworten“ bzw.
  „Nachfassen“ schreibt gleich dorthin, der Bezug geht mit. „+ Schreiben“ an einen Agenten oder alle.
- **Bezug an jeder Nachricht** (Schema 29): worum es geht – Aufgabe, Frage, Dokument, Meilenstein, Prüfung, Lauf, Thema,
  Beschluss oder Agent – als Chip; ein Klick springt hin. Antworten erben ihn. Alte Nachrichten bekommen ihn aus Aufgabe,
  Dokument und Frage nachgetragen. Agenten setzen ihn mit `amw posten --bezug A12`.
- **Zurückziehen**, solange kein Empfänger die Nachricht gelesen hat – sie verschwindet bei ihm, bei dir steht
  „zurückgezogen“.
- **„gelesen“ stimmt jetzt:** Was ein Agent mit `amw lesen` in seiner Liste sieht, gilt als gelesen.
- Online steht Geschriebenes sofort im Gesendet („wird übertragen …“). Hilfe „Nachrichten: Eingang und Gesendet“.

## 1.73.0 – 12.11.2026 · Bildschirm-Freigabe ohne Pflicht-Uhrzeit
- **Bildschirm online freigeben: Uhrzeit freiwillig.** Ohne Uhrzeit bleibt der Bildschirm frei, bis jemand ihn belegt
  oder ein eingeschalteter Auslöser greift; die Rückfrage sagt das.

## 1.72.0 – 12.11.2026 · Team-Baum aufgeräumt
- Der Baum zeigt dauerhaft nur noch die Äste (du → Lead → Agenten). Prüfungen und Wartebeziehungen einer Karte
  erscheinen, sobald die Maus auf ihr steht (oder du sie antippst) – jede Linie in eigener Spur, die übrigen Karten
  abgeblendet. Keine Schleifen außen herum, keine Linien übereinander.
- „wartet auf dich“ steht als Markierung an der Karte statt als Linie zu dir.

## 1.71.0 – 12.11.2026 · Eigener Online-Speicher im Firmennetz
- **Eigener libSQL-Server statt Turso:** Unter Einstellungen › Speicher und Synchronisierung wählst du jetzt den Anbieter –
  Turso (Cloud) oder einen eigenen libSQL-Server im Firmennetz. Für den eigenen Server: Adresse (https, im Firmennetz auch
  http mit Warnung) und, wenn nötig, das Zertifikat der Firma. Die AMW prüft die Verbindung, bevor sie etwas speichert.
- **Schlüssel auf Knopfdruck:** `amw speicher schluessel --url https://…` erzeugt den Schlüssel für den Server, trägt den
  Zugang auf diesem PC ein und zeigt einmal den Schlüssel für die Online-Seite. Der geheime Teil wird nirgends gespeichert.
- **Online-Seite:** liest die Adresse des eigenen Servers nur aus ihrer Konfigurationsdatei (`speicher_url`,
  `speicher_token`, optional `speicher_ca`) – nie aus einem Formular.
- Geprüft gegen einen echten libSQL-Server: PC und Seite lesen und schreiben, ein falscher Schlüssel wird abgewiesen.

## 1.70.0 – 12.11.2026 · Firmen-Anmeldung (SSO)
- **Mit Firmenkonto anmelden:** Neben Passwort und zweitem Faktor gibt es auf der Online-Seite einen zweiten Weg – die
  Anmeldung beim Anmeldedienst der Firma (OpenID Connect, getestet wie Microsoft Entra ID). Kein zweiter Faktor in der
  AMW; den verlangt der Anmeldedienst. Der Knopf erscheint nur, wenn die Firmen-Anmeldung eingeschaltet ist.
- **Nur angelegte Benutzer:** Beim ersten Mal findet die AMW den Benutzer über die E-Mail, die du am PC eingetragen hast,
  und verbindet ihn fest mit seinem Firmenkonto. Eine neue E-Mail oder „Neu freischalten“ löst die Verbindung, Sperren
  wirkt sofort. Wer noch keine Rolle hat, sieht „Dein Zugang wird geprüft“, und du bekommst eine Meldung (auch als Push).
- **Einstellungen am PC** (Benutzer der Online-Seite › Firmen-Anmeldung): Aussteller, Client-ID, an/aus, die Adresse zum
  Eintragen beim Anbieter; neu die E-Mail je Benutzer. Auch als `amw web sso`.
- **Das Geheimnis bleibt beim Webhoster:** Client-Secret oder Zertifikat trägt ein System-Admin auf der Online-Seite ein
  (`sso.php?einrichten`); es steht nur in deren Konfigurationsdatei – nie auf dem PC, nie im Online-Speicher.
- Sicher gegen die üblichen Angriffe: PKCE, Prüfung von Signatur, Aussteller, Empfänger, Ablauf und Zufallswert; nur
  https, kein „common“-Aussteller; Fehlversuche zählen in die bestehende Sperre.
- Hilfe „Firmen-Anmeldung mit Microsoft Entra ID einrichten“ (DE/EN), Schritt für Schritt.

## 1.69.0 – 12.11.2026 · Agenten entfernen
- **Einstellungen › Agenten › „Entfernen …“** legt einen Agenten still und blendet ihn überall aus: Er wird nicht mehr
  gestartet, nicht mehr benachrichtigt, steht nicht mehr im Team und bekommt keine Nachrichten mehr. Was er geschrieben
  und getan hat, bleibt mit seinem Namen lesbar. Läuft seine Sitzung, wird sie vorher gesichert und beendet.
- **„Entfernt“** listet die entfernten Agenten; „Wieder aufnehmen“ holt einen zurück (Soll: aus).
- **„Endgültig löschen …“** geht nur bei einem Agenten ohne Verlauf; sonst ist der Knopf ausgegraut und nennt, was am
  Agenten hängt.
- Nur der Mensch – am PC oder online als System-Admin. Schema 28.

## 1.68.0 – 12.11.2026 · Bildschirm auch online freigeben
- **Online freigeben** – nur als System-Admin, mit Rückfrage und nur mit Uhrzeit, bis wann. Im Verlauf steht, wer es online
  war. Wieder belegen darf online jeder.
- **Was nur am PC geht, steht online ausgegraut da** – mit der Erklärung „Geht nur am PC“ (Sitzungen speichern und beenden,
  fehlende starten, Dienst neu starten) bzw. „Online nur für System-Admins“.
- **Oben nur der Zustand:** Die Leiste über dem Team zeigt, ob und bis wann der Bildschirm frei ist; geändert wird im
  Leitstand („Im Leitstand ändern“ führt hin).

## 1.67.0 – 12.11.2026 · Team-Baum mit Pfeilen und Warteplatz
- **Kräftigere Linien mit Pfeilen:** Äste zeigen, wohin die Aufträge laufen (du → Lead → Agenten), die gestrichelte
  blaue Linie, wohin die Arbeit zur Prüfung geht. Neu: eine gepunktete Linie in Bernstein vom Wartenden zu dem, auf
  den er wartet – ein anderer Agent oder du. Eine kleine Legende steht darunter.
- **Platz in der Warteschlange des Rechners:** Steht ein schwerer Lauf eines Agenten in der gemeinsamen Schlange
  aller Projekte, zeigt seine Kachel „Platz 2/3 hinter Spiel / G1“; der genaue Grund steht beim Überfahren. Am PC mit
  Projekt und Agent; online heißt ein fremdes Projekt „anderes Projekt“.

## 1.66.0 – 12.11.2026 · Online-Eingaben mit Rückmeldung, Bildschirm-Freigabe einstellbar
- **Online: Was du eingibst, bleibt stehen.** Gespeicherte Einstellungen (z. B. „Zuständig für“ eines Agenten) zeigt die
  Online-Seite sofort mit dem neuen Wert – auch nach dem Neuladen, bevor der PC sie übernommen hat. Vorher war das Feld
  nach dem Speichern leer und der Text kam erst nach etwa 20 Sekunden.
- **An der Stelle steht, was passiert:** „wird übertragen …“, dann „✓ gespeichert“ – oder „nicht gespeichert: Grund“
  (z. B. „Lead gibt es schon“). Das gilt für jede Eingabe auf der Online-Seite, auch nach dem Neuladen. Eine
  „gespeichert“-Meldung direkt nach dem Absenden gibt es online nicht mehr – sie wäre verfrüht.
- **Schneller:** Hat der PC eine Eingabe aus dem Briefkasten ausgeführt, lädt er den neuen Stand sofort hoch statt bis zu
  30 Sekunden später.
- Einstellungen › Dieser PC › „Bildschirm-Freigabe von selbst schließen“: bei Eingabe am PC (Tastatur, Maus), bei neuer
  Fernsitzung, bei Eingabe in der Workbench – jeder Auslöser einzeln an oder aus. So kannst du zwischendurch per
  Fernsitzung hineinschauen oder die Maus bewegen, ohne die Agenten zu unterbrechen.
- Ist ein Auslöser aus, beobachtet die AMW ihn gar nicht – sie misst nichts und schreibt nichts darüber auf. Ohne „Eingabe
  am PC“ starten Läufe mit Fenster auch, während du am PC bist; dann schließt du die Freigabe selbst.
- Neue Installationen haben alle drei an. Neue Hilfe „Bildschirm für Agenten freigeben“ (DE/EN).

## 1.65.1 – 12.11.2026 · Online: Erledigtes bleibt weg
- Als gelesen markierte Nachrichten, beantwortete und geparkte Fragen tauchten auf der Online-Seite für einige Sekunden
  wieder auf und verschwanden dann erneut. Grund: Sobald der PC die Eingabe ausgeführt hatte, galt sie nicht mehr als
  unterwegs – die neue Ansicht war aber noch nicht hochgeladen. Jetzt gilt eine Eingabe, bis eine Ansicht online ist,
  die nach ihr entstanden ist. Eingaben, die der PC abgewiesen hat, blenden nichts aus.

## 1.65.0 – 12.11.2026 · Mehrere Benutzer: Freischalten und Anmelden
- **Benutzer der Online-Seite** (Einstellungen am PC): anlegen, Rolle und Projekte vergeben, freischalten, sperren. Ein
  neuer Benutzer hat keine Rechte, bis du Rolle und Projekte vergibst.
- **Freischalt-Code statt Mail:** „Freischalten“ zeigt einmal einen Code aus 16 Zeichen (24 Stunden gültig), den du
  persönlich weitergibst. Online steht nur ein Hash davon, auf dem PC gar nichts. Auch als `amw benutzer freischalten NAME`.
- **Neue Anmeldung in drei Schritten:** Name und Code, eigenes Passwort (mindestens 12 Zeichen), zweiter Faktor per
  QR-Code. Erst mit der ersten Zahl aus der App gilt der Code als benutzt – alles auf einmal; bricht jemand vorher ab,
  gilt der Code weiter. Zwei mit demselben Code: nur der erste kommt durch.
- **Danach** meldet sich jeder mit Name, Passwort und Zahl aus der App an. Bis zur Freigabe sieht er nur „Dein Zugang
  wird geprüft“; du bekommst die Meldung „Neuer Benutzer … wartet auf Freigabe“ (auch als Push).
- **Rechte auf dem Webhoster:** Die Seite zeigt nur die zugewiesenen Projekte und weist Eingaben ab, für die die Rolle
  nicht reicht – der PC prüft noch einmal. Sperren und „Neu freischalten“ beenden laufende Sitzungen sofort.
- Hilfe „Benutzer der Online-Seite“ (DE/EN).

## 1.64.0 – 12.11.2026 · Dieselben Wörter auch in Meldungen und Befehlszeile
- Meldungen der AMW an die Agenten, Ausgaben und Hilfetexte der Befehlszeile, Fehlermeldungen und das Protokoll des
  Dienstes sprechen jetzt dieselbe Sprache wie Oberfläche und Hilfen: Meilenstein, Dienst, Synchronisierung,
  Dateiaustausch, Rhythmus, Stufe, Denkaufwand, Startinformationen, Name, benachrichtigen.
- Die Nachricht an eine Sitzung beginnt mit „AMW-Benachrichtigung für …“.
- Planungshinweise auf Englisch: milestone statt arc.
- **Geplante Aufgabe statt Wecker:** Ein Lead, der als Chat arbeitet, legt sich am Ende jedes Durchgangs eine einmalige
  geplante Aufgabe an – so heißt es in der Claude-App. Regel W4 und die Hilfe „Rhythmus für einen Lead, der als Chat
  arbeitet“ (DE/EN) nennen es jetzt so; „Worte des Menschen“ statt „Wortlaut“ in G8 und G9. Grund-Regelwerk Fassung 3.
- Befehle und Schalter bleiben unverändert (`amw bogen …`, `--bogen`, `--von`).

## 1.63.0 – 12.11.2026 · Mehrere Benutzer, erste Stufe
- **Benutzer mit Rolle:** Leser, Bearbeiter, Projekt-Admin oder System-Admin – eine Rolle je Benutzer, dazu die Projekte,
  die er sieht. Anlegen, ändern und sperren mit `amw benutzer …` (nur der Mensch am PC).
- **Der PC prüft jede Eingabe von der Online-Seite** gegen Rolle und Zuweisung, bevor er sie ausführt – ein Leser
  schreibt nichts, ein Bearbeiter nur in seinen Projekten, Einstellungen des PCs nur ein System-Admin.
- **Der Verlauf nennt den Menschen:** Nachrichten und Antworten tragen den Namen des Benutzers.
- **Abgleich:** Die Benutzer stehen ohne Passwort und Geheimnis im Online-Speicher; beides setzt jeder später selbst.
- **Ohne Namen keine Rechte:** Sobald es Benutzer gibt, weist der PC jede Eingabe von der Online-Seite ab, die keinen
  Benutzer mitbringt. Die Seite schickt immer mit, wer handelt – auch den bisherigen Zugang aus ihrer Konfiguration.
  Wer vor dem Update angemeldet war, meldet sich einmal neu an.
- **Neue Benutzer warten auf Freigabe:** Ohne Rolle hat ein Benutzer keine Rechte, bis ein Admin Rolle und Projekte
  vergibt.
- Der Mensch am PC und der bisherige Online-Zugang bleiben System-Admin. Anmelden können sich neue Benutzer mit der
  nächsten Stufe (Einladung).
- **Schema 27.** Bestehende Daten bleiben unverändert.

## 1.62.0 – 12.11.2026 · Versionshinweise ohne KI
- **Ein Satz für Nutzer beim Abschließen:** `amw aufgabe fertig … --gruppe neu|verbessert|behoben --hinweis "…"`. Die
  Startinformationen bitten die Agenten darum.
- **Entwurf der nächsten Version:** `amw release entwurf` zeigt Neu / Verbessert / Behoben aus den fertigen Aufgaben
  seit der letzten Version. Fehlt ein Satz, macht eine Regel aus der Zusammenfassung einen Vorschlag – erkennbar als
  „Vorschlag“. Keine KI, keine Tokens.
- **Version eintragen** (`amw release version …`) übernimmt den Entwurf als Text für alle; ein eigener Text geht mit
  `--oeffentlich-datei`.
- **Seite „Versionshinweise“** in Workbench und online: oben der Entwurf der nächsten Version, darunter jede Version mit
  ihrem Text; „Mit Aufgaben“ zeigt die Nummern dazu.
- **Schema 26:** zwei neue Felder an der Aufgabe. Bestehende Daten bleiben unverändert.

## 1.61.0 – 12.11.2026 · Team-Baum mit kräftigen, geraden Linien
- **Startseite › Team als Baum:** Die Äste sind deutlich dicker und durchgehend rechtwinklig; auch die gestrichelte
  Verbindung zwischen zwei Agenten, die gerade zusammenarbeiten, ist jetzt gerade statt gebogen – in eigener Farbe.
## 1.60.1 – 12.11.2026 · Ordnergrößen nur im laufenden Dienst messen
- **Behoben (vor der Veröffentlichung gefunden):** Die tägliche Messung der Ordnergrößen startete auch aus der
  Aufsicht-Runde heraus, die andere Teile der AMW einzeln aufrufen – ihr Hintergrund-Faden hielt dann die Datenbank
  offen. Jetzt startet sie nur die Schleife des laufenden Dienstes.
- **Behoben:** Die Linien des Team-Baums wurden nur gezeichnet, wenn der Browser einen Animations-Schritt ausführte –
  in einem Tab im Hintergrund blieben sie aus, bis sich die Größe änderte. Jetzt zeichnet die Seite sie in jedem Fall.

## 1.60.0 – 12.11.2026 · Hilfen in derselben Sprache wie die Oberfläche
- **Hilfen überarbeitet** (Deutsch und Englisch) mit den Wörtern der Oberfläche: Dienst, Synchronisierung,
  Startinformationen, Dateiaustausch, Meilenstein, Startanweisung, Name; im Englischen service, start information,
  file exchange, milestone, control center.
- **Rhythmus statt Takt** auch in der Regel für einen Lead, der als Chat arbeitet (Grund-Regelwerk, Fassung 2), in
  seiner Hilfe und in seinen Startinformationen („Dein Rhythmus“). Der „Wecker“ der Chat-App heißt weiter so.

## 1.59.0 – 12.11.2026 · Was auf der Platte wächst
- **Tägliche Messung der Ordnergrößen:** Der Dienst misst einmal am Tag die Projektordner dieses PCs, ihre typischen
  Ablagerungen (Build-Reste, Caches, Temp-Ordner), weitere Arbeitsbäume (Git-Worktrees) und den Ordner der Sicherungen –
  im Hintergrund und nie, während ein schwerer Lauf läuft. Messwerte bleiben 90 Tage.
- **Anzeige** unter Einstellungen › Dieser PC und in `amw rechner`: die größten Zuwächse der letzten 7 Tage und die
  größten Ablagerungen mit „seit n Tagen unverändert“. Die AMW misst und zeigt nur; sie löscht nichts.
- **Schema 25:** neue Tabelle für die Messwerte. Bestehende Daten bleiben unverändert.

## 1.58.0 – 12.11.2026 · Alte Sicherungen ins Archiv verschieben
- **Ein Klick ins Archiv:** Unter Einstellungen › Dieser PC verschiebst du Aufräumvorschläge (alte Sicherungen samt
  Dokumente-Ablage) einzeln oder alle in einen Archiv-Ordner. Die AMW löscht nichts und überschreibt nichts; jede
  Verschiebung steht in `archiv-protokoll.txt` im Archiv-Ordner.
- **Nur, was vorgeschlagen ist:** Verschoben werden nur Dateien, die gerade in der Vorschlagsliste stehen.
- Neue Einstellung „Archiv-Ordner“ (Dieser PC); ohne Eintrag gibt es keinen Knopf.

## 1.57.0 – 12.11.2026 · Grundregel „Eins nach dem anderen“
- **Grund-Regelwerk, Fassung 2:** neue Grundregel G19 „Eins nach dem anderen“ – jeder macht ein Stück fertig, bevor er
  das nächste beginnt; Neues kommt in den Eingang; dazwischenschieben entscheidet nur der Mensch. Neue Projekte bekommen
  sie mit; bestehende Projekte behalten ihre Regeln.
- **Neue Hilfe** „Reihenfolge der Arbeit“ (Deutsch und Englisch), aufrufbar unter Aufgaben › Listen beim Eingang.

## 1.56.0 – 12.11.2026 · Dazwischenschieben nur bewusst
- **Dazwischenschieben** ist ein eigener Schritt, und den macht nur der Mensch: in der Workbench bei der Aufgabe
  („Dazwischenschieben“, mit Grund) oder mit `amw aufgabe dazwischen <nr> --grund …`. Das laufende Stück des Agenten
  wartet dann auf die eingeschobene Aufgabe und kommt danach von selbst wieder an die Reihe; der Agent bekommt die
  Bitte, seinen Stand zu sichern. Im Verlauf steht „unterbrochen“.
- **Der Lead schlägt vor:** Ruft der Lead denselben Befehl auf, bekommt der Mensch eine Ja/Nein-Frage; „Ja“ führt es aus.
- **Aufträge mitten im Stück warten:** Ein Auftrag an einen Agenten, der gerade ein Stück in Arbeit hat, wird
  zugestellt, weckt ihn aber erst beim nächsten Wechsel – außer er gehört zum laufenden Stück. Fragen, Antworten,
  Freigaben und Meldungen wecken wie bisher.

## 1.55.0 – 11.11.2026 · Neue Aufgaben kommen in den Eingang
- **Eingang statt dazwischen:** Legt jemand eine Aufgabe für einen Agenten an, der gerade ein Stück in Arbeit hat,
  landet sie im Eingang und nicht in seiner Liste. Der Lead plant sie ein – frühestens hinter das laufende Stück. Mit
  `amw aufgabe neu … --sofort` kommt sie direkt hinter das laufende Stück.
- **Leitstand:** „Arbeit der Agenten“ zeigt, wie viele Aufgaben im Eingang warten.
- Aufgaben des Menschen bleiben frei.
## 1.54.1 – 11.11.2026 · Warteschlange: wartende Läufe kommen auch ohne Sitzung im Projekt dran
- **Behoben:** Ein Lauf, den ein Agent mit `amw lauf ausfuehren` anmeldet und der warten muss, kam nie dran, wenn der
  Agent im Projekt des Laufs keine angemeldete Sitzung hatte – etwa weil sein Ordner zwei Projekten gehört und die
  Sitzung im anderen angemeldet ist. Jetzt gilt der wartende Befehl selbst als Lebenszeichen: Solange er läuft, gibt die
  Warteschlange den Lauf frei, sobald Platz ist.

## 1.54.0 – 11.11.2026 · Eins nach dem anderen: das laufende Stück steht fest
- **Kein zweites Stück, solange eines läuft:** Startet ein Agent eine Aufgabe, während eine andere bei ihm läuft, weist
  die AMW das ab und nennt die Auswege: fertig machen, mit Grund warten lassen – oder der Mensch schiebt bewusst etwas
  dazwischen. Bisher wurde die laufende Aufgabe still zurückgestellt, und es entstanden halbe Stände.
- **Nichts vor das laufende Stück:** Ordnen, Schieben und neue Aufgaben mit kleinem Rang landen frühestens direkt
  dahinter.
- **Wird eine obere Aufgabe wieder frei,** meldet die AMW: „als Nächstes dran, sobald A… fertig ist“.
- Aufgaben des Menschen bleiben frei; für ihn gilt keine dieser Sperren.

## 1.53.0 – 11.11.2026 · Befehle aus der Oberfläche in die Hilfe
- **Keine Befehle der Befehlszeile mehr in den Texten der Oberfläche:** Wo ein Text bisher einen Befehl nannte, sagt er
  jetzt in Worten, was zu tun ist; die Befehle stehen in den Hilfen („? Anleitung“).
- **Neue Hilfen** (Deutsch und Englisch): „Agenten: Ordner einrichten, umbenennen, starten“, „Projekt-Server überwachen“,
  „Lokale KI einrichten und beauftragen“, „Testtermine und Fristen“, „Themen: was gerade gilt“; die Hilfe zu ntfy
  erklärt jetzt auch Telegram und eigene Kanalnamen.
- „Nacht-Aufträge“ statt „Aufträge mit --nachts“ beim KI-Fenster.

## 1.52.0 – 11.11.2026 · Oberfläche in normaler Sprache
- **Texte der Workbench und der Online-Seite überarbeitet** (Deutsch und Englisch, gut 200 Stellen): kurz, aktiv und mit
  den Wörtern, die übliche Software verwendet. Die wichtigsten Wörter:
  „Bogen“ → „Meilenstein“, „Wächter“ → „Dienst“, „Abgleich“ → „Synchronisierung“, „Takt“ → „Rhythmus“,
  „Brücke“ → „Dateiaustausch“, „Wortlaut“ → „Deine Worte“, „wecken“ → „benachrichtigen“, „Welle“ → „Stufe“,
  „Denkstufe“ → „Denkaufwand“, „Release Notes“ → „Versionshinweise“, „Pflicht-Kontext“ → „Startinformationen“,
  „Kennung“ → „Name“, „Baseline“ → „ursprünglicher Termin“, „Federführend“ → „Verantwortlich“, „Prüfbitte“ →
  „Prüfanfrage“, „Merge-OK“ → „Merge-Freigabe“, „Pool“ → „Eingang“, „Halt“ → „Anhalten“, „Sichern & beenden“ →
  „Speichern & beenden“. „Leitstand“ bleibt.
- **Behoben:** Drei Texte erschienen nie, weil ihr Schlüssel doppelt vergeben war – stattdessen stand die
  Spaltenüberschrift da: „speichert und wird beendet – spätestens …“ (stand: „Ende“), „zuletzt aktiv …“ im Hinweis zum
  Zustand eines Agenten (stand: „Puls“) und die Überschrift „Zustand und Verbrauch“ (stand: „Zustand“).
- Befehlszeile, Hilfeseiten und Meldungen der Agenten folgen in einem zweiten Schritt; Befehle verschwinden dann auch
  aus den Texten der Oberfläche und stehen in den Hilfen.

## 1.51.2 – 11.11.2026 · Warteschlange: laufende Läufe halten ihren Arbeitsspeicher frei
- **Behoben:** Die Warteschlange rechnete den Bedarf eines laufenden schweren Laufs nur in den ersten 3 Minuten nach
  seinem Start ein. Danach ließ sie einen weiteren schweren Lauf ein, sobald im Moment genug frei war – auch wenn der
  erste noch wuchs. Besonders ein Lauf mit Grafikkarte neben einem Lauf ohne Grafikkarte brach dann wegen
  Speichermangels ab, und der andere mit.
- **Jetzt:** Jeder laufende schwere Lauf hält seinen angemeldeten Bedarf frei, solange er läuft – abzüglich dessen, was
  er nachweislich schon belegt. Bei Läufen über `amw lauf ausfuehren` misst die AMW das am Prozess samt Kindern; bei
  anders gestarteten Läufen gilt der ganze Bedarf als vorgemerkt, bis der Lauf endet.
- Der Wartegrund nennt es: „nur 13.9 GB frei (8 GB davon für laufende Läufe vorgemerkt), gebraucht 8 GB und 3 GB Reserve“.
- Tipp: Läufe mit ihrem echten Bedarf anmelden (`--braucht-gb`); ohne Angabe gilt die Grenze des Projekts.

## 1.51.1 – 11.11.2026 · Abgleich lädt nicht mehr wegen bloßer Messwerte hoch
- **Behoben:** Seit 1.42.0 standen Messwerte des Rechners in den Ansichten, die der Abgleich hochlädt – freier
  Arbeitsspeicher, später freier Platz, Größe dauerhaft belegter Programme, die Uhrzeit „jetzt“ im Tages-Zeitstrahl und
  die Hochrechnung des Wochenlimits. Jede kleine Schwankung galt als Änderung, die Ansichten wären fortlaufend neu
  hochgeladen worden. Jetzt zählen diese Werte nicht mehr als Änderung; mitgeschickt werden sie, sobald sich sonst
  etwas ändert. Eine neue Aussage – ein Laufwerk wird knapp, ein Programm kommt dazu, ein Lauf startet oder endet –
  löst weiterhin das Hochladen aus.
- Der Zeitstrahl „Rechner – heute“ setzt die Linie „jetzt“ nach der Uhr des Geräts, damit sie auch online stimmt.

## 1.51.0 – 11.11.2026 · Planung: der Rechner heute als eigener Zeitstrahl
- **„Rechner – heute“** unter der Übersicht der Planung: der Tagesablauf des Rechners. Ein Balken je Lauf, die Füllung
  zeigt den Arbeitsspeicher; was läuft, reicht bis zum erwarteten Ende; Wartende hängen gestrichelt hinter „jetzt“.
  Läufe anderer Projekte erscheinen nur als „anderes Projekt“ mit Zeitraum und Bedarf – ohne Inhalt. Einklappbar.
- **Dauerhaft belegt als durchgehender Balken:** Ein Programm außerhalb der Warteschlange (lokaler KI-Server, virtuelle
  Maschine) zieht sich über den ganzen Zeitstrahl.
- **Streifen „Rechner“ auf der Zeitachse der Übersicht:** je Tag ein Stück, so hoch, wie viele Stunden der Rechner mit
  Läufen belegt war – Projektarbeit und Rechner-Belegung stehen übereinander.

## 1.50.0 – 11.11.2026 · Festplatte: Warnung bei knappem Platz, Aufräumvorschläge
- **Freier Platz je Laufwerk:** Die AMW misst die Laufwerke mit der Datenbank und den Projektordnern. Wird eines knapp
  (Vorgabe: unter 15 % Warnung, unter 5 % dringend), steht es im Leitstand unter „Rechner“; Lead und Mensch bekommen
  eine Nachricht – einmal je Stufe, nicht bei jedem Neustart.
- **Aufräumvorschläge:** Alte Sicherungen, die nach der Regel nicht mehr gebraucht werden, stehen mit Größe und Alter
  unter Einstellungen › Dieser PC. Es bleiben die neuesten (Vorgabe 10) und je veröffentlichter Version die letzte
  Sicherung davor. **Die AMW löscht und verschiebt nichts** – sie zeigt nur an.
- **Neuer Befehl `amw rechner`:** Arbeitsspeicher, was außerhalb der Warteschlange belegt, Laufwerke und
  Aufräumvorschläge auf einen Blick.
- **Einstellungen** unter „Dieser PC“: Warnschwellen in Prozent, Anzahl aufbewahrter Sicherungen.

## 1.49.0 – 11.11.2026 · Rechner: was außerhalb der Warteschlange Speicher belegt
- **Dauerhaft belegt:** Ein Programm, das außerhalb der Warteschlange länger als 10 Minuten viel Arbeitsspeicher belegt –
  ein lokaler KI-Server, eine virtuelle Maschine –, steht jetzt im Leitstand unter „Rechner“: Name, Größe, seit wann.
- **Wartet ein Lauf auf Arbeitsspeicher,** nennt der Wartegrund das Programm, das ihn belegt.
- **Die AMW beendet nichts.** Sie zeigt nur an; beenden kann ein solches Programm nur der Mensch.
- **Einstellung** „Dauerhaft belegt anzeigen ab (GB)“ unter „Dieser PC“ (Vorgabe 4 GB, 0 = aus). Gelesen werden nur Name,
  Arbeitsspeicher und Startzeit der Prozesse, keine Befehlszeilen. Läufe aus der Warteschlange zählen nicht dazu.

## 1.48.0 – 11.11.2026 · Wochenlimit: Pause nicht doppelt, Ampel mit Pause
- **Pausentage zählen nicht in den Durchsatz:** Tage, an denen das Wochenlimit mindestens einen halben Tag lang
  aufgebraucht war, fallen aus der Prognose heraus. Vorher steckte die Pause im Durchsatz und stand zusätzlich am Datum.
- **Die Ampel eines Meilensteins berücksichtigt die Pause:** grün nur, wenn der Termin auch mit Pause hält. Wäre er ohne
  die Pause zu halten, steht „(mit Pause)“ am Datum. Das gilt auch für den Status „Termin“ und den Plan-Check.
- **„Wochenlimit“ statt „Token-Woche“** in Planung und Leitstand.

## 1.47.0 – 11.11.2026 · Token-Pause: wie weit die Wochen-Grenze das Ende verschiebt
- **Eigenes Stück ⧗ am Balken:** In der Übersicht der Planung wird jeder Balken um die Token-Pause verlängert – das
  angehängte Stück in eigener Farbe, schraffiert und mit dem Zeichen ⧗ (hell und dunkel unterscheidbar, nicht nur über
  die Farbe). So sieht man, wie weit sich das Ende durch die Grenze verschiebt.
- **Am Datum:** `Prognose 27.11. – 01.12. ⧗ +12 T → ≈ 09.12.` – am Bogen und an jedem Schritt. Das erste Datum bleibt,
  wie es ohne Grenze wäre.
- **Token-Woche** über der Übersicht und im Leitstand der Startseite: Verbrauch der Woche, „leer voraussichtlich“, nächster
  Reset, Pause bis dahin. Der Rechenweg steht im Hinweistext (Tempo wahrscheinlich und vorsichtig, Rest, Reset, Arbeit
  und Pause je Folgewoche).
- **Gerechnet wird mit dem Gesamtverbrauch des Kontos** – alle Projekte dieses PCs zusammen, aus den Messwerten, die die
  AMW ohnehin mitschreibt. Ein Reset wird am Abfall erkannt, auch außer der Reihe, und zählt als Ereignis, nicht als
  Verbrauch. Keine neue Tabelle, nichts wird gespeichert.
- Ohne Messwerte erscheint nichts; bei zu wenigen Messtagen steht „unsicher“ dabei.

## 1.46.0 – 11.11.2026 · Betriebsart: festlegen, wohin die AMW Verbindungen aufbauen darf
- **Drei Betriebsarten** (Zahnrad › Betriebsart, `amw einrichten betriebsart [pc|server|cloud]`): „Nur dieser PC“ – keine
  Verbindung über den Rechner hinaus; „Eigener Server im Firmennetz“ – nur Adressen im eigenen Netz; „Cloud“ –
  Online-Speicher, Online-Seite und Benachrichtigungs-Dienste im Internet sind erlaubt.
- **Gesperrt im Code, nicht nur in der Oberfläche:** Abgleich mit dem Online-Speicher, Benachrichtigungen und die Prüfung
  der Online-Seite fragen dieselbe Stelle. Entschieden wird nach der Adresse des Ziels (dieser PC, Firmennetz, Internet) –
  ein eigener ntfy-Server im Firmennetz ist in „Eigener Server“ erlaubt, ein Dienst im Internet nicht. In „Nur dieser PC“
  wird nicht einmal ein Name aufgelöst. Fehlermeldungen nennen nur den Rechnernamen des Ziels, nie einen Schlüssel.
- **Nichts ändert sich von selbst:** Wer nichts wählt, behält, was bisher lief – mit eingeschaltetem Abgleich oder
  Benachrichtigungen „Cloud“, sonst „Nur dieser PC“. Neu: Wer den Online-Speicher zum ersten Mal einrichtet, wählt zuerst
  „Cloud“.
- **Prüf-Lauf „Verbindungen“:** Unter der Betriebsart steht jede Adresse, zu der diese Installation eine Verbindung
  aufbaut – wer, Ziel, wohin es führt, erlaubt oder gesperrt. „Jetzt prüfen“ testet die erlaubten Ziele (nur der
  Verbindungsaufbau). Rot ist, was eingeschaltet, aber gesperrt ist. Als Befehl: `amw einrichten verbindungen [--pruefen]`
  (endet dann mit Fehler).
- **„In Claude öffnen“** führt ins Internet und wird nur gezeigt, wenn die Betriebsart das zulässt.
- **„Online-Seite testen“ prüft auch die Version:** Die Seite hinterlegt beim Anmelden ihre Version im Online-Speicher;
  der PC vergleicht sie mit seiner. Öffentlich gibt die Seite ihre Version weiterhin nicht preis.
- **Geführte Einrichtung:** `amw einrichten` fragt die Betriebsart ab, solange noch keine gewählt ist.
- **Neue Hilfen** (Deutsch und Englisch, aufrufbar am Abschnitt): „Betriebsart wählen“, „Online-Seite beim Webhoster
  einrichten“, „Zweiter Faktor: neues oder verlorenes Handy“.
- Nicht erfasst ist, was außerhalb der AMW läuft: Claude Code spricht mit seinem Anbieter, Git mit seinem Server.

## 1.45.0 – 11.11.2026 · Schwere Befehle melden sich von selbst an
- **Automatismus statt Gebot:** Startet ein Agent eine ganze Test-Suite, Browser-Tests, einen Build oder den Abzug des
  Web-Zweigs direkt, wird der Befehl nicht ausgeführt. Er bekommt stattdessen den fertigen Befehl für die Warteschlange
  des Rechners: `amw lauf ausfuehren --beschreibung "Test-Suite" -- <sein Befehl>`. Einzelne Test-Module bleiben frei.
- **Einrichten:** `amw einrichten agenten-ordner <ordner>` trägt den Hook ein (für bestehende Ordner einmal wiederholen);
  laufende Sitzungen übernehmen ihn nach wenigen Sekunden.
- **Eigene Muster je Projekt:** Zahnrad › Projekt › „Weitere schwere Befehle“ (je Zeile `Name = Muster`).
- **Schalter je Rechner:** Zahnrad › Dieser PC › „Schwere Befehle über die Warteschlange“ (ab Werk an).
- **Sicher gebaut:** Ein Fehler des Hooks sperrt nie einen Befehl – fehlt seine Datei oder scheitert er, läuft der Befehl
  normal.
- **Neue Hilfe:** „Schwere Läufe: Tests und Builds über die Warteschlange“.

## 1.44.0 – 11.11.2026 · Ein Lauf meldet an, was er braucht
- **Bedarf je Lauf:** `amw lauf start` und `amw lauf ausfuehren` nehmen `--braucht-gb` (Arbeitsspeicher). Bisher rechnete
  ein Lauf ohne Rezept mit der Grenze seines Projekts (6 oder 8 GB) – ein Testlauf, der 2 GB braucht, wartete unnötig.
- **Grafikspeicher und Festplatte:** wahlweise `--braucht-vram-gb` und `--braucht-platte-gb`. Reicht der freie Wert
  nicht, wartet der Lauf mit klarer Begründung („nur 6 GB Grafikspeicher frei, gebraucht 8 GB“). Ohne Angabe wird nicht
  geprüft.
- **Rechner je Lauf:** Jeder Lauf merkt sich, auf welchem PC er angemeldet wurde; die Warteschlange zählt nur Läufe
  ihres eigenen Rechners.
- Über einen Lauf eines anderen Projekts steht jetzt auch sein angemeldeter Bedarf („… voraussichtlich bis 16:20, 4 GB“).
- **Datenbank:** Schema 24 (vier Spalten an `lauf`). Bestehende Läufe bleiben unverändert und zählen zu diesem Rechner.
  Vorher sichern: `amw sichern`.

## 1.43.0 – 11.11.2026 · Arbeitsspeicher-Reserve für den Menschen am Rechner
- **Reserve als Einstellung des Rechners** (Zahnrad › Dieser PC, Vorgabe 3 GB): Die Warteschlange lässt einen schweren
  Lauf erst ein, wenn nach seinem Bedarf noch die Reserve frei bleibt. So bleibt der PC bedienbar, auch wenn Agenten
  rechnen. Die Meldung nennt beides: „nur 10 GB frei, gebraucht 8 GB und 3 GB Reserve“. Mit 0 gilt das bisherige Verhalten.
- Leitstand › Rechner: „Aus diesem Projekt: 1 aktiv, 1 in der Warteschlange.“

## 1.42.0 – 11.11.2026 · Eine Warteschlange je Rechner, über alle Projekte
- **Schwere Läufe werden über Projekte hinweg abgesprochen.** Bisher galt die Reihenfolge der Wartenden nur innerhalb
  eines Projekts – ein wartender Lauf konnte von einem anderen Projekt überholt werden. Jetzt gibt es eine Warteschlange
  für den ganzen Rechner: wer zuerst kommt, ist zuerst dran, egal aus welchem Projekt.
- **Vorziehen:** Ein Lead zieht nur Läufe seines eigenen Projekts vor (sie tauschen untereinander die Plätze); über
  Projekte hinweg zieht nur der Mensch vor.
- **Projekte bleiben getrennt:** Über einen Lauf eines anderen Projekts steht nur, dass der Rechner belegt ist und bis
  wann – nie Agent, Beschreibung oder Projekt. Das gilt für Meldungen, Wartegründe und `amw lauf liste`.
- **Gleiche Kennung in zwei Projekten** sind zwei Agenten: Ihre Läufe halten einander nicht mehr auf.
- **Leitstand › Rechner:** wie viele Läufe laufen und warten, wie viele davon aus diesem Projekt, wann der Rechner
  voraussichtlich frei ist, wie viel Arbeitsspeicher frei ist.
- Der Wächter arbeitet die Warteschlange einmal je Runde für den ganzen Rechner ab.

## 1.41.0 – 11.11.2026 · Einstellungen neu gegliedert, mit Geltungsbereich und Verbindungstests
- **Neue Reihenfolge im Zahnrad:** Speicher und Abgleich · Online-Seite · Benachrichtigungen · Dieser PC · Projekt ·
  Agenten – erst, was die Installation trägt, dann das Projekt. Was zusammengehört, steht zusammen: die Takte des
  Abgleichs beim Speicher (bisher unter „Dieser PC“), die Adresse der Online-Seite bei der Online-Seite (bisher als
  „Link in der Meldung“ bei den Benachrichtigungen).
- **Wofür ein Abschnitt gilt:** „Gilt für diesen PC“, „… die Online-Seite“, „… dieses Projekt“ oder „… PC und Online-Seite“.
- **Standard und Neustart je Feld:** Weicht ein Wert vom Standard ab, steht der Standard darunter. Felder, die der
  Wächter nur beim Start liest, tragen ↻ „Wird nach einem Neustart des Wächters wirksam“ – statt eines Sammelhinweises.
- **Zwei Tests:** „Verbindung testen“ meldet sich am Online-Speicher an und sieht nach, ob die Datenbank eingerichtet
  ist; „Online-Seite testen“ prüft, ob die Adresse über https erreichbar ist und dort eine AMW-Seite läuft. Jeder Schritt
  steht mit Ergebnis da. Getestet werden die gespeicherten Werte, nur lesend, nur vom PC aus. Als Schnittstelle:
  `/api/pruefen?was=speicher|seite`.
- **Neu einstellbar:** Standardsprache (wie im Browser, Deutsch, Englisch – gilt, bis jemand sie selbst umstellt) und die
  Schaltfläche „In Claude öffnen“ an oder aus. Der Speicherort der Einstellungen wird angezeigt.
- **Neutrale Namen:** Der Abschnitt heißt „Speicher und Abgleich“; Turso ist die Art des Online-Speichers, nicht mehr
  sein Name.

## 1.40.0 – 11.11.2026 · Grund-Regelwerk: ein neues Projekt startet mit bewährten Regeln
- **Mitgeliefertes Grund-Regelwerk** (Deutsch und Englisch): 18 Regeln in drei Gruppen – Arbeit und Nachweis,
  Entscheidungen und Wissen, Sicherheit und Betrieb – und vier wahlweise. Jede Regel nennt ihr **Warum**; wo ein Anlass
  belegt ist, steht stattdessen die **Erfahrung**. Erfundene Vorfälle stehen nirgends.
- **Schritt „Regelwerk“ im Assistenten „Neues Projekt“:** Grund-Regelwerk (Vorgabe), Kopie der Arbeitsregeln eines anderen
  Projekts oder ohne. Die Regeln lassen sich einzeln abhaken und im Wortlaut anpassen. Arbeitet der Lead als Chat, ist
  die Regel zum Takt vorgewählt. Im Befehl: `amw einrichten` fragt danach, `amw einrichten schnell --grund-regelwerk`.
- **Was beim Anlegen entsteht:** die gewählten Regeln als Arbeitsregeln des Projekts, ein Beschluss als ihre Quelle, die
  Definition of Done im Leitbild und die erste Version 0.1.0 (Schema MAJOR.MINOR.PATCH).
- **Wissen › Regeln** zeigt die Grundregeln als eigene Gruppe: Nummer aus der Vorlage (G1 …), „angepasst“, wenn der
  Wortlaut geändert wurde, darunter das Warum bzw. die Erfahrung. Sie bleiben gewöhnliche Regeln des Projekts.
- **Pflicht-Kontext:** jede Sitzung sieht die aktuelle Version; ein Lead, der als Chat arbeitet, bekommt seine Takt-Regel
  im Wortlaut.
- **Neue Hilfen:** „Grund-Regelwerk für ein neues Projekt“ und „Takt für einen Lead, der als Chat arbeitet“.
- **Datenbank:** Schema 23 (eine Spalte `regel.vorlage` für die Herkunft, z. B. „G7/1“). Bestehende Regeln bleiben, wie
  sie sind. Vorher sichern: `amw sichern`.

## 1.39.0 – 11.11.2026 · Agenten einstellen: eine Ansicht, vier Blöcke
- **Eine Ansicht statt Tabelle und getrenntem Profil** (Zahnrad › Agenten): links die Agenten, rechts der gewählte in
  vier Blöcken – *Wer* (Lead, Fachgebiet, Arbeitsweise), *Auftrag* (Zuständig für, Fasst nicht an, Rundschreiben),
  *Sitzung* (Ordner, Modell, Rechte, Startsatz; nur am PC), *Überwachung* (soll laufen, Lebenszeichen). Ein „Speichern“
  für alles; am Handy stehen die Agenten als Reihe über dem Formular.
- **Lead ist ein Schalter, das Fachgebiet ein eigenes Feld.** Bisher stand beides in „Rolle“: genau das Wort „lead“ gab
  die Lead-Rechte, alles andere war eine Beschreibung. Jetzt: „führt das Projekt“ an oder aus, dazu das Fachgebiet als
  freier Text mit Vorschlägen (Code, Grafik, Prüfen …). Ein Lead kann zusätzlich ein Fachgebiet haben.
- **Arbeitsweise:** Claude Code im Terminal (die AMW startet, weckt und überwacht) · Claude Code in der Desktop-App (der
  Mensch startet; die AMW startet sie nie) · Chat über die Brücke (wird weder gestartet noch überwacht). Bisher galt
  unsichtbar „Lead ohne Arbeitsordner = Chat“. Ein Chat zählt in der Kopfzeile nicht mehr zu den Agenten, die laufen
  sollen; „Starten“ und „Fehlende starten“ betreffen nur Terminal-Agenten. Die Startseite zeigt je Arbeitsweise ein
  eigenes Zeichen.
- **„Zuständig für“ und „Fasst nicht an“** ersetzen das eine Feld „Grenzen“ und stehen im Pflicht-Kontext jeder Sitzung –
  zusammen mit Führung und Fachgebiet.
- **Vorschlag aus der Datenbank:** auf Knopfdruck leitet die AMW aus den fertigen Aufgaben, Dokumenten und Prüfungen
  eines Agenten ein Fachgebiet und seine Zuständigkeit ab und nennt die Grundlage. Der Vorschlag füllt nur leere Felder;
  gespeichert wird erst mit „Speichern“.
- **Befehle:** `amw agent neu|profil` mit `--fachgebiet`, `--arbeitsweise terminal|desktop|chat`, `--zustaendig`, `--nicht`;
  `--rolle` kennt nur noch `lead` oder leer (ein anderes Wort gilt wie bisher als Fachgebiet), `--grenzen` bleibt als
  früherer Name von `--zustaendig` gültig.
- **Datenbank:** Schema 22 (vier Spalten an `agent`). Der Bestand wird beim ersten Start übernommen: eine frühere Rolle
  außer „lead“ wird das Fachgebiet, „Grenzen“ wird „Zuständig für“, ein Lead ohne Arbeitsordner wird „Chat“, alle anderen
  „Terminal“. Vorher sichern: `amw sichern`.

## 1.38.0 – 11.11.2026 · Startseite: das Team als Baum oder Liste
- **Baum statt Kacheln:** oben du (deine Schritte, Fragen an dich, Freigaben), darunter der Lead (was er plant, Takt,
  letzte Meldung), darunter die Agenten als kleine Karten – Fachgebiet, Zustand, woran er arbeitet, worauf er wartet,
  Verbrauch, Länge seiner Liste. Linien zeigen die Hierarchie; gestrichelte Bögen verbinden, wer gerade zusammenarbeitet
  (offene Prüfbitte).
- **Liste als Umschaltung** (oben rechts, Vorgabe am Handy): dieselben Angaben, eine Zeile je Agent – acht Agenten
  brauchen etwa die halbe Höhe der bisherigen Kacheln. Die Wahl bleibt je Gerät.
- **Arbeitsweise sichtbar:** eigenes Zeichen für eine Claude-Code-Sitzung und für einen Lead, der als Chat über die
  Datei-Brücke arbeitet; ein Chat gilt nie als „läuft nicht“.
- Leitstand: „Fehlende starten“ zählt nur Agenten mit Arbeitsordner; Agenten ohne Profil sagen das im Aktionsmenü.

## 1.37.0 – 11.11.2026 · Schritt-für-Schritt-Hilfen direkt in der Workbench
- **Hilfe-Baustein:** Ein „? Anleitung“ neben einer Einstellung öffnet eine Schritt-für-Schritt-Hilfe – was du
  brauchst, nummerierte Schritte, welche Werte wohin gehören, typische Fehler, häufige Fragen. Am PC, online und am
  Handy, Deutsch und Englisch.
- **Eine Quelle:** Der Inhalt liegt als einfache Textdatei je Thema in `doc/hilfe/` (Englisch in `doc/hilfe/en/`) –
  dieselbe Datei ist die Anleitung im Repo. `amw web bauen` prüft jede Hilfe und legt sie für die Online-Seite ab
  (→ doc/hilfe/README.md: so schreibt man eine Hilfe).
- **Erste Hilfen:** Online-Speicher bei Turso anlegen (Einstellungen › Online-Speicher), Benachrichtigungen aufs Handy
  mit ntfy (Einstellungen › Benachrichtigungen), Neues Projekt – Schritt für Schritt (die bisherige Anleitung, jetzt
  aus derselben Quelle).
- Tests: Browser-Tests laufen auch unter hoher PC-Last durch (großzügigere Zeitgrenzen, sauberes Beenden des
  Test-Browsers, ein neuer Anlauf bei abgerissener Verbindung).

## 1.36.0 – 11.11.2026 · Leitstand und Aktionsmenü: alles Steuerbare an einer Stelle
- **Leitstand** auf der Startseite, direkt unter den Agenten: Arbeit der Agenten (Alle anhalten / Weiterarbeiten),
  Bildschirm (für Agenten freigeben / wieder belegen), Sitzungen (Alle sichern & beenden, Fehlende starten), Wächter
  (Neu starten). Der Knopf zum Anhalten steht nicht mehr in der Ecke der Kopfzeile, der Bildschirm nicht mehr zwischen
  den Hinweisen: Die erste Zeile zeigt nur noch Zustände und führt per Klick zum Leitstand, wenn etwas vom Normalfall
  abweicht (angehalten, Bildschirm frei, Sitzungen werden beendet).
- **Aktionsmenü „⋯“ je Agent** statt einzelner Knöpfe: Nachricht schreiben, Gespräch mitlesen, Übersicht und
  Aufgabenliste · Anhalten (nur diesen) / Weiterarbeiten lassen, Sichern & beenden lassen, Sofort beenden,
  Starten/fortsetzen, Neue Sitzung beginnen · Profil. Sitzungen starten und beenden weiter nur am PC.
- **Sichern & beenden** (z. B. vor einem Update), neu: Der Agent wird gebeten, seinen Stand festzuhalten und sich
  abzumelden; sobald er abgemeldet ist, beendet die AMW seine Sitzung – nach 5 Minuten auch ohne Abmeldung. Für alle
  im Leitstand, für einen im Aktionsmenü, nur vom Menschen am PC. Ohne Änderung der Datenbank (ein Halt mit Frist, den
  der Wächter abarbeitet) → doc/automatismen.md.
- **Fehlende starten:** startet alle, die laufen sollen und nicht laufen, nacheinander mit Abstand. **Wächter neu
  starten** geht jetzt auch aus der Workbench am PC.
- **Bildschirm statt Schirm** überall in der Oberfläche (Dialog, Hinweisbänder, Einstellungen, Terminplaner):
  „frei für Agenten“ / „belegt“, „Für Agenten freigeben …“ / „Wieder belegen“.

## 1.35.2 – 11.11.2026 · Verständliche Benennungen in der ersten Zeile und auf den Agenten-Kacheln
- **Erste Zeile in ganzen Wörtern**, Deutsch und Englisch gleich gebaut: „Wächter läuft“ (statt „Dienst“),
  „2 von 7 Agenten laufen“ (statt „2/7 Agenten“), „Arbeitsspeicher: 11 GB frei“, „Bildschirm: belegt“ bzw.
  „Bildschirm: frei für Agenten“ (statt „Schirm zu/frei“). Der Knopf heißt **Alle anhalten** / **Weiterarbeiten**
  (statt „Halt“ / „Weiter“). Das Kürzel „PC“ an den Hinweisen ist ein Hinweistext geworden.
- **Agenten-Kacheln:** „läuft nicht – sollte laufen“ (statt „beendet – soll laufen“), „✉ n offen“ für offene
  Nachrichten, „Arbeitet an:“, „keine Angabe, woran“, „n in der Liste“, „Letzte Meldung“, Knopf „Mitlesen“; das
  Lebenszeichen steht als Hinweistext am Zustand statt als Herz mit Zahl. Zeitangaben: „gestern“ und „vor n Tagen“
  statt „vor n T“.
- Die Hinweise der ersten Zeile bleiben in einer Zeile; die Suche gibt dafür Platz ab.
- Intern: eine überlange Bedingung beim Ändern der Agenten-Rolle sauber umbrochen (keine Änderung im Verhalten).

## 1.35.1 – 11.11.2026 · Mockups erscheinen online wieder im Dokument-Fenster
- **Online-Seite:** Ein Mockup (HTML) im Dokument-Fenster oder auf der Kachel wurde vom Browser abgewiesen („darf diese
  eingebettete Seite nicht öffnen“). Die `.htaccess` setzte `X-Frame-Options: DENY` zusätzlich zu der Angabe, die die
  Seite für Dokument-Dateien selbst setzt (`SAMEORIGIN`); bei zwei Angaben gilt die strengere. Die `.htaccess` setzt sie
  nicht mehr – die Seite verbietet das Einbetten weiter selbst, Dokument-Dateien dürfen nur in der eigenen Seite
  erscheinen (zusätzlich `frame-ancestors 'self'`). Am PC war nichts betroffen.

## 1.35.0 – 11.11.2026 · Untermenüs bleiben beim Scrollen oben stehen
- **Fester Seitenkopf auf jeder Seite:** Reiter, Filter und Sprungmarken einer Seite bleiben beim Scrollen oben stehen –
  auch ganz unten lässt sich der Reiter wechseln oder der Filter ändern. Die Titelzeile läuft dabei hinaus, damit der
  feste Teil flach bleibt. Gilt am PC, online und am Handy; ein gemeinsamer Baustein für alle Seiten.
- **Handy:** Jedes Untermenü ist eine einzige Zeile, die sich waagrecht wischen lässt (statt mehrerer umbrochener
  Zeilen); der gewählte Reiter rückt von selbst ins Bild, und die Zeile bleibt beim Neuzeichnen, wo sie war.
- **Betrieb** hat Sprungmarken zu seinen Abschnitten (wie die Einstellungen). Sprungziele landen unter dem festen Kopf.
- Dokumente: Die Filterzeile passt am PC wieder in eine Zeile (Suchfeld schmaler).
- **Rolle per Befehl ändern:** `amw agent profil <kennung> --rolle … --grenzen …` (Lead und Entwickler; bisher nur in den
  Einstellungen). Der einzige Lead gibt seine Rolle nicht selbst ab. Damit lässt sich ein Lead, der als Chat über die
  Datei-Brücke arbeitet, nachträglich vor ein Projekt setzen, das bisher ein Agent mit eigener Sitzung führt – die Brücke
  bucht dann unter dem Namen des Chat-Leads statt unter dem des Agenten (→ doc/architektur.md).

## 1.34.1 – 08.11.2026 · Schirm: kein Fehlalarm durch eine einzelne Eingabe
- **Eine Eingabe allein schließt den Schirm nicht mehr:** Erst eine zweite, spätere Eingabe innerhalb von 2 Minuten zeigt,
  dass jemand am PC ist. Zweimal hatte eine einzelne Eingabe den Schirm geschlossen, obwohl niemand da war.
- Meldung und Log nennen das **Programm im Vordergrund** (nur den Namen, nie den Fenstertitel) – so lässt sich ein
  Fehlalarm künftig zuordnen.

## 1.34.0 – 08.11.2026 · Jeder schreibt nur als er selbst
- **`--von` passt zur Sitzung:** Läuft ein Befehl in einer Agenten-Sitzung (das Startskript setzt `AMW_AGENT`), lehnt die
  AMW ein fremdes `--von` ab – kein Agent kann mehr als ein anderer posten, prüfen, freigeben oder ein Merge-OK geben.
  Frühere Kennungen (nach dem Umbenennen) gelten als dieselbe. Ohne `AMW_AGENT` (Terminal des Entwicklers) und über die
  Brücke bleibt alles wie bisher.

## 1.33.2 – 07.11.2026 · Online-Seite: Datei ausliefern robuster
- Liefert die Online-Seite eine Datei in Teilen aus (Video mit Spulen) und kann der Webspace einmal nicht lesen, bricht
  sie sauber ab, statt mit einem PHP-Fehler stehen zu bleiben.

## 1.33.1 – 07.11.2026 · Dokumente nach Format filtern
- **Filter „Format“** in den Dokumenten (am PC und online): Bilder, Videos, Texte, Mockups, PDF, Office – je mit Anzahl.
  Quer zur Art: Videos sind meist Art „Ergebnis“ und waren über die Art-Chips nicht zu finden.

## 1.33.0 – 07.11.2026 · Abnahme-Kette
- **Merge-Bitte von selbst:** Schaltet der Lead die Abnahme-Kette ein (Zahnrad › Projekt › Abnahme-Kette und Merge-Dienst,
  Vorgabe aus), gibt er sein Merge-OK je Aufgabe mit `amw freigabe merge A…`. Sobald der Prüfer die Aufgabe GRÜN meldet,
  geht die Merge-Bitte für genau diesen Stand (ganzer SHA) an den Merge-Dienst – Bauer, Zuständiger und Lead bekommen eine
  Kopie. Ohne OK fragt die AMW den Lead mit einer weckenden Zeile; sein Befehl schickt die Bitte nach. Ein überholter Stand
  bekommt nie eine Bitte, jede Prüfung höchstens eine. Setzt die Regel „Merge nur mit grüner Prüfung und OK des Leads“ als Automatik um.
- `amw agent umbenennen` stellt auch den Merge-Dienst des Projekts auf die neue Kennung um.

## 1.32.0 – 07.11.2026 · Videos als Dokument
- **Videos ablegen und abspielen:** `amw dokument ablegen abnahme.mp4 …` nimmt MP4 (H.264) und WebM an, auch beim
  Hochladen in der Workbench und am Handy (bis 25 MB). Die Workbench spielt sie im Dokument-Fenster ab, mit Vor- und
  Zurückspulen (am PC und online); die Kachel zeigt das erste Bild. Die AMW prüft, dass es wirklich ein Video ist; ein
  MP4 mit H.265/HEVC lehnt sie mit dem ffmpeg-Befehl für H.264 ab, weil nicht jeder Browser es abspielt. Gewünscht für
  Abnahmen und Look-Prototypen.

## 1.31.0 – 07.11.2026 · KI Stufe 2: Nachtfenster und Vermerke an KI-Ergebnissen
- **KI-Fenster für Aufträge, die nicht eilen:** `amw ki auftrag … --nachts` startet erst im KI-Fenster (Vorgabe 22–06 Uhr,
  Ortszeit; Zahnrad › Dieser PC › KI-Fenster) und nie in der Vorlaufzeit eines Testtermins (in irgendeinem Projekt). Bis
  dahin überholen ihn alle anderen Läufe – die Grafikkarte bleibt frei, solange du am PC arbeitest. Der Terminplaner zeigt
  das Fenster als Band über 24 h mit dem, was wartet (Zahl und Dauer nach Modell-Probe); `amw ki fenster` auch.
- **Vermerke an KI-Ergebnissen:** Im Dokument-Fenster eines KI-Bildes oder -Textes: Auswählen, Verwerfen und
  „Nachbearbeitung vermerken“ (was von Hand geändert wurde) – am PC, am Handy und über `amw ki vermerk D<nr> --art
  ausgewaehlt|verworfen|nachbearbeitet [--text …]`. Es gilt der jüngste Entscheid; nichts wird geändert oder gelöscht,
  jeder Vermerk steht mit wer, wann und Kanal. Die Kacheln der Dokumente zeigen „ausgewählt / verworfen / offen“.
  Schema 21 (Tabelle `ki_vermerk`).
- **Nachweis:** `amw ki nachweis` zählt ausgewählt / verworfen / ohne Entscheid / nachbearbeitet und nennt je Dokument
  Entscheid, Nachbearbeitung und den Beleg (Commit) der fertigen Aufgabe – Grundlage für die Steam-Angabe und das
  Urheberrecht (menschliche Gestaltungsentscheidung).

## 1.30.1 – 07.11.2026 · Mausmodus, KI-Schnittstelle „befehl“
- **Kein Mausmodus mehr nach hartem Stopp:** Endet Claude im Tab (auch beim Beenden aus der Workbench), setzt die
  PowerShell im Tab das Terminal zurück. Vorher schrieb jeder Mausklick Steuerzeichen. Gilt für Start aus der Workbench
  und für die Startskripte (neu erzeugen).
- **Eigene lokale KIs:** `amw ki neu <name> --schnittstelle befehl` trägt ein Programm ohne Dienst-Schnittstelle ein
  (z. B. eine Ton-KI in Python). Recht und Modell-Freigabe wie sonst; gerechnet wird über `amw lauf ausfuehren --gpu`.
  Hilfe und Fehlermeldungen nennen „befehl“ jetzt (Wunsch aus einem Projekt).
- **Fremde GPU-Last:** Rechnet etwas auf der Grafikkarte (ab 60 %, drei Prüfungen hintereinander), ohne dass ein Lauf
  mit Grafikkarte oder Schirm angemeldet ist, und warst du seit 5 min nicht am PC, bekommen die Leads eine Meldung –
  höchstens einmal je Stunde. Die AMW meldet nur und beendet nichts (KI Stufe 3).

## 1.30.0 – 07.11.2026 · Entwickler-Kanal, Wege im Projekt (Fehlerbericht aus einem Projekt)
- **Entwickler-Kanal:** Der Agent, der die AMW entwickelt (Zahnrad › Dieser PC › Entwickler-Kanal), ist in jedem Projekt
  erreichbar und darf dort schreiben. Die Leads finden ihn im Pflicht-Kontext; `amw lesen` zeigt ihm alle Projekte mit
  Namen, der Wächter weckt ihn aus jedem Projekt. Alle anderen Agenten bleiben in ihrem Projekt.
- **Agentenfragen zuerst an den Lead** (Vorgabe für alle Projekte): Eine Frage eines Agenten an dich geht an den Lead;
  er beantwortet sie oder leitet sie mit `amw frage weiterleiten <F>` weiter – dieselbe Frage, Verlauf bleibt.
- **Spezifikationen über den Lead:** Vorlegen nur der Lead (Vorgabe); freigeben auch der Lead, wenn das Projekt es
  erlaubt (`spec_frei = lead`, Vorgabe aus). Die Karte zeigt „verfasst: … · vorgelegt: … (geprüft)“. Eine neue Fassung
  hebt eine Freigabe nie mehr still auf: du und der Lead bekommen eine Meldung mit dem Unterschied alt → neu.
- **Meldungen mit Bezug:** `amw posten … --bis leitbild|aufgabe|A…|F…` – der Wächter erledigt sie, sobald das erfüllt ist
  (Schema 20: Spalte `nachricht.bis`). Neue Agenten melden sich beim Lead statt beim Entwickler. Der Lead schließt
  veraltete Meldungen an dich mit Grund (`amw erledigt <nr> --fuer Entwickler --bemerkung …`, steht im Verlauf).
  Infos ohne Bezug wandern nach 24 h (einstellbar) eingeklappt unter „Ältere Infos“.
- **Geparkte Fragen** heißen in der Online-Suche und in der Lesekopie der Brücke (Sicht `frage_zustand`) „geparkt“.
- **Beschluss mit Wortlaut in einem Zug:** `amw beschluss neu … --wortlaut-text "…"` erfasst den Wortlaut und verknüpft
  ihn – keine vorhergesagte W-Nummer mehr.
- `amw projekt einstellen <schluessel>=<wert>` für Lead und Entwickler, auch über die Datei-Brücke (dort nur das –
  Projekte anlegen bleibt am PC).

## 1.29.0 – 07.11.2026 · Logo
- **Eigenes Logo:** Oben links steht statt des Schriftzugs „AMW“ jetzt das Logo. A, M und W sind eine durchgehende
  Linie mit drei Knoten, wie ein kleines neuronales Netz: ein Knoten am Fuß des A, ein glühender im M, einer am Ende
  des W. Die Farbe läuft von Bernstein über Glut nach Blau und folgt dem Hell/Dunkel-Schalter. Daneben steht
  „Agenten Management Workbench“ mit hervorgehobenen Anfangsbuchstaben; auf dem Handy nur das Logo.
- **Favicon:** Der Browser-Tab zeigt das M mit dem glühenden Knoten, in der Workbench und auf den Online-Seiten
  (Anmeldung, Einrichtung). Die Logo-Dateien liegen als SVG in `doc/logo/`.

## 1.28.0 – 07.11.2026 · Lesbare Startskripte, Lead als Chat
- **Startskripte im Klartext:** `amw agent startskript` und „Neues Projekt“ schreiben eine `.bat` (Doppelklick) statt einer
  PowerShell-Datei mit verschlüsselten Befehlen. Je Agent eine Zeile mit allen Angaben aus dem Profil, ein Fenster je
  Projekt. Zuerst wird die letzte Sitzung fortgesetzt; gibt es keine, beginnt eine neue mit derselben ID und dem
  Startsatz. Ohne frühere Sitzung ist die ID fest, das Skript bleibt also gleich, egal wie oft es erzeugt wird.
  Vorhandene `.ps1` bleiben liegen.
- **Lead als Chat:** Im Dialog „Neues Projekt“ lässt sich angeben, dass der Lead in der Claude-App bzw. Cowork arbeitet.
  Er bekommt dann keinen Ordner im Profil und wird weder über die Kachel noch über das Startskript gestartet; er arbeitet
  über die Datei-Brücke. Bei einem bestehenden Projekt: den Ordner im Profil des Leads leeren.

## 1.27.3 – 07.11.2026 · Lokale KIs kommen nach einem Neustart wieder
- **Der Wächter holt lokale KIs hoch:** Antwortet eine aktive KI mit Startbefehl nicht (z. B. nach einem Neustart des PCs),
  startet er sie ohne Fenster – je KI höchstens alle 10 Minuten. Eine KI ohne Startbefehl bleibt aus. Soll eine KI ganz aus
  bleiben: `amw ki aendern <name> --abschalten`. Beendet wird eine KI von der AMW weiter nie.
- Tests laufen jetzt auch in einer Agenten-Sitzung (AMW_PROJEKT/AMW_AGENT aus dem Startbefehl galten sonst mit).

## 1.27.2 – 07.11.2026 · Warnung „nicht angemeldet“ je Projekt
- Der rote Kasten „Nicht angemeldet“ auf der Startseite zeigt nur noch Sitzungen des gewählten Projekts. Bisher erschien
  eine nicht angemeldete Sitzung eines anderen Projekts auch dort.

## 1.27.1 – 07.11.2026 · Gleiche Kennung in zwei Projekten: Weck-Adresse getrennt
Wichtige Korrektur für mehrere Projekte. Gefunden in der Probe „neues Projekt von A bis Z“.
- **Fehler:** Die Datei mit der Weck-Adresse einer Sitzung trug nur die Kennung im Namen. Startete ein CC1 in einem zweiten
  Projekt, überschrieb er die Adresse des CC1 im ersten. Der Wächter sah dann dessen Sitzung als beendet an und weckte ihn
  nicht mehr, und „Beenden“ konnte den Prozess des anderen Agenten treffen.
- **Jetzt:** eine Datei je Projekt und Kennung. Laufende Sitzungen behalten ihre alte Datei bis zur nächsten Anmeldung.
- **Beenden und „läuft er?“** gelten nur noch für den Prozess genau dieser Sitzung (Sitzungs-ID wird geprüft); eine Datei
  einer anderen Sitzung zählt nicht mehr.
- **`amw regeln`** sagt in einem Projekt ohne Regeln, dass es noch keine gibt, statt nichts auszugeben.

## 1.27.0 – 07.11.2026 · Neues Projekt: Anleitung am Knopf, erster Start ohne Raten
Aus einer Probe „neues Projekt von A bis Z“ (Wegwerf-Projekt auf einer Kopie der Datenbank).
- **Anleitung „Neues Projekt – Schritt für Schritt“ in der Workbench** mit Bildern: Projekt-Auswahl › „? Anleitung“,
  auch im Dialog „Neues Projekt“, nach dem Anlegen und unter Einstellungen › Projekt. **Online** nur zum Lesen
  („Anlegen geht am PC“). Dazu: woher der erste Agent alles weiß (Startsatz, Pflicht-Kontext, CLAUDE.md), was vor dem
  ersten Start auszufüllen ist (Leitbild, erste Aufgabe) und häufige Fragen (MCP, Wächter, Git, Sitzungen, gleiche
  Kennungen). Ausführlich in [doc/anleitung-projekte.md](doc/anleitung-projekte.md).
- **Projekt ohne Leitbild:** Der Pflicht-Kontext sagt „Projekt NEU“ – der Lead fragt den Entwickler nach Ziel und
  Nicht-Zielen und trägt sie ein, ein Agent meldet sich und wartet auf seine erste Aufgabe, statt zu raten.
- **Der amw-Befehl braucht im Agentenordner keine Rückfrage mehr** (Erlaubnis nur für diesen einen Befehl, auch mit Rechten
  „vorgabe“): sonst fragte Claude Code bei jedem `amw lesen`. Was ein Agent darf, prüft weiter die AMW. Bestehende Ordner
  bekommen es mit `amw einrichten agenten-ordner <ordner>`.
- **Tab-Titel mit Projekt:** mit mehreren Projekten heißt der Tab „CC1 · Webshop“ statt nur „CC1“.
- **Erster Start in einem neuen Ordner:** Claude Code fragt einmal, ob du dem Ordner vertraust – die Anleitung sagt es jetzt
  (vorher laufen weder Hook noch Startsatz).
- Agenten-Dialog: das ✕ verdeckt den Knopf „Nachricht“ nicht mehr; ein nicht laufender Agent zeigt „Läuft gerade nicht“
  statt „Hooks einrichten“.

## 1.26.0 – 06.11.2026 · Lauf-Schlange mit zwei Spuren
Bisher lief je Projekt nur ein schwerer Lauf. Auch die freie Grafikkarte wartete auf einen Headless-Build: KI-Aufträge
und Fenster-Läufe standen hinter Builds, die sie gar nicht stören.
- **Spur Grafikkarte/Schirm:** GPU-Läufe, KI-Aufträge und Läufe mit Fenster wie bisher PC-weit einer zur Zeit (jetzt
  auch Schirm-Läufe verschiedener Projekte).
- **Spur CPU:** schwere Läufe ohne Fenster und ohne Grafikkarte rechnen parallel, Vorgabe **2**. Einstellbar unter
  Zahnrad › Dieser PC › „Schwere Läufe ohne Fenster zugleich“ (`cpu_laeufe`, 1–8). Beide Spuren laufen nebeneinander.
- **Speicher je Lauf:** Jeder schwere Lauf braucht seine Speicher-Grenze frei. Ein gerade gestarteter Lauf zählt seine
  Grenze 3 Minuten lang als belegt, bis sein Speicher in der Messung auftaucht – zwei Starts kurz hintereinander
  überbuchen den RAM nicht.
- **Ein Agent rechnet nie zwei schwere Läufe zugleich** (sein Klon: nie zwei Godot-Imports im selben Ordner). KI-Aufträge
  zählen nicht dazu, die rechnet der Dienst.
- **Niemand überholt, aber nur auf seinem Platz:** Wer auf seinen Klon oder den Schirm wartet, hält die CPU-Spur nicht auf.
  Wer wegen Speicher wartet, wird auf seinen Spuren nicht überholt. `amw lauf zeige <nr>` nennt den Grund
  („CPU-Spur voll …“, „L… von CC3 läuft noch …“).
- Laufende Läufe bleiben unberührt; die neue Regel gilt ab der nächsten Runde des Wächters.

## 1.25.0 – 06.11.2026 · Ein Projekt als eigene Datenbank sichern
Entschieden nach der Prüfung „mehrere Projekte“: **eine Datenbank je Rechner bleibt** (Gründe in
[doc/plan-projektwahl.md](doc/plan-projektwahl.md), Abschnitt „Aufbau“).
- **`amw sichern --projekt <name>`** schreibt eine eigene, vollständige und lauffähige AMW-Datenbank nur mit diesem
  Projekt (Schutz-Trigger, Schema, Fremdschlüssel intakt) und daneben nur dessen Dokument-Dateien – zum Sichern eines
  einzelnen Projekts oder zum Umziehen auf einen anderen Rechner ([doc/anleitung-projekte.md](doc/anleitung-projekte.md)).
- Die Lese-Kopie der Brücke nutzt dieselbe Funktion und behält jetzt ebenfalls ihre Trigger.

## 1.24.0 – 06.11.2026 · Zeitleiste lesbar, Hauptaktion oben
Letzte Vorschläge aus dem Bedienbarkeits-Durchgang (1.21.0).
- **Planung, Übersicht:** Passt der Name eines Bogens nicht in seinen Balken, steht er rechts daneben (bis 250 px, am
  Rand gekürzt) statt nur „B1…“ – die Spuren halten dafür Platz frei. Klick auf den Namen springt wie der Balken zum Bogen.
- **Hauptaktion oben neben der Überschrift** wie bei den Dokumenten: „Neuer Bogen“ steht jetzt dort (bisher als Textknopf
  in der Reiterzeile, nur auf der Zeitleiste).

## 1.23.0 – 06.11.2026 · Handy: alles erreichbar, Daumen-Ziele
Vorschläge aus dem Bedienbarkeits-Durchgang (1.21.0) für das Handy.
- **Untere Leiste mit „Mehr“:** am Handy Start, Fragen, Plan, Arbeit und „Mehr“ – jedes Ziel mindestens 48 px breit statt
  neun schmaler. „Mehr“ öffnet ein Blatt von unten mit Verlauf, Release Notes, Wissen, Dokumente, Betrieb, Einstellungen,
  Hell/Dunkel und Sprache. Der **Verlauf** und die Umschalter waren am Handy bisher nicht erreichbar.
- **Filter am Handy sichtbar:** Reiter brechen um, statt seitlich wegzuscrollen – Agent-Filter und Suche der Aufgaben
  (und des Wissens) lagen bisher außerhalb des Bildes. Die Erklärung über den Listen ist eingeklappt (Klick: ganz).
- **Fragen:** alle Knöpfe unter einer Frage gleich groß.
- **Schirm-Dialog:** Felder wie in den anderen Dialogen (Beschriftung links, volle Breite).

## 1.22.0 – 06.11.2026 · Neues Projekt aus der Workbench, Brücke je Projekt
Abschluss der Prüfung „mehrere Projekte durchgängig?“ – Anleitung: [doc/anleitung-projekte.md](doc/anleitung-projekte.md).
- **Neues Projekt in der Workbench** (nur am PC): Projekt-Auswahl bzw. Einstellungen › „+ Neues Projekt“. Fragt Name,
  Projektordner, Lead, Agenten, Rechte, Arbeitsregeln (ohne oder Kopie eines anderen Projekts) und Farbe; richtet alles
  ein wie `amw einrichten` und wechselt auf Wunsch ins neue Projekt. Vom Handy aus nicht möglich.
- **Projektordner gehört zum Projekt:** steht in den Einstellungen des Projekts (`amw projekt ordner`,
  `amw projekt neu … --ordner`); neue Agenten bekommen ihn als Profil-Ordner. Ein Ordner gehört zu genau einem Projekt –
  geprüft, bevor etwas angelegt wird.
- **Assistent:** fragt bei einem weiteren Projekt, ob es die Arbeitsregeln eines anderen übernehmen soll.
- **Datei-Brücke je Projekt:** jedes weitere Projekt hat `eingang-<projekt>/` und `daten/lesen-<projekt>.db`, ausgeführt
  als sein Lead. Mit mehreren Projekten enthält jede Lese-Kopie nur ihr Projekt (bisher die ganze Datenbank), und ein
  Befehl wirkt nur im Projekt seiner Brücke. Mit einem Projekt ändert sich nichts.

## 1.21.0 – 06.11.2026 · Bedienbarkeits-Durchgang, Dokumente nach Art
Jede Seite und jeder Dialog am PC (1440 px) und am Handy (390 px) aufgerufen und auf einen gemeinsamen Standard geprüft.
- **Dokumente nach Art:** Die Arten stehen als Chips mit Anzahl über der Liste (wie die Arten im Verlauf), ein Klick
  filtert. Neu: **Zeitraum** (heute, 7 Tage, 30 Tage) und **Reihenfolge** (neueste, älteste, Titel A–Z, nach Art).
  „Hochladen“ steht wie andere Hauptaktionen oben neben der Überschrift.
- **Dialoge einheitlich:** Hauptknopf zuerst, dann „Abbrechen“ (Bogen, Risiko, Profil waren umgekehrt); Titel überall
  gleich gesetzt; im Agenten-Dialog nur noch ein ✕. **Enter** in einem einzeiligen Feld löst den Hauptknopf aus,
  Strg+Enter auch im Textfeld.
- **Ehrliche Zahlen:** Wissen zeigt in den Reitern alle Beschlüsse und Wortlaute (bisher die Zahl der gezeigten, höchstens
  60) und die Zahl der Themen auch, solange ihr Reiter zu ist; über der Liste steht „die neuesten 60 von N“.
  Betrieb nennt die Speicher-Grenze des Projekts statt fest „8 GB“.
- Kleinigkeiten: Sprungleiste der Einstellungen zeigte „Dieser PC dieser PC“; am Handy war „Releases“ in der unteren
  Leiste abgeschnitten (jetzt „Notes“); Dokument-Titel in Karten ließen eine dritte Zeile anschneiden.

## 1.20.2 – 06.11.2026 · Projektordner gehört zu seinem Projekt
Prüfung „mehrere Projekte wirklich durchgängig?“: Gab es eine Kennung in zwei Projekten (z. B. TL) und startete man den
Agenten von Hand statt über Kachel oder Startskript, meldete der Hook die Sitzung im ersten Projekt an – Nachrichten
dieses Projekts hätten sie geweckt.
- **Der Projektordner trägt sein Projekt:** `amw einrichten` und `amw einrichten agenten-ordner … --projekt <name>`
  schreiben `AMW_PROJEKT` in die Umgebung des Ordners (`env` in `.claude/settings.local.json`); Claude Code setzt es jeder
  Sitzung dort, auch von Hand gestartet. Ein Ordner gehört zu genau einem Projekt; mit mehreren Projekten fragt
  `agenten-ordner` nach dem Projekt.
- **Nie im falschen Projekt:** Ist das Projekt nicht gesetzt und die Kennung mehrdeutig, wählt der Hook über den
  Arbeitsordner (Profil-Ordner) oder eine frühere Anmeldung der Sitzung. Bleibt es offen, meldet er die Sitzung nicht an
  und sagt im Fenster, was zu tun ist.
- **Startskript je Projekt:** Richtet der Assistent ein weiteres Projekt ein, schreibt er `agenten-start-<projekt>.ps1`
  statt das Startskript des ersten Projekts zu überschreiben.
- Doku: Eine zweite AMW-Installation auf demselben Rechner ist nicht vorgesehen (gemeinsamer Dienst, Port und
  Einstellungen) – der frühere Hinweis darauf war falsch.

## 1.20.1 – 06.11.2026 · Seiten aktualisieren sich selbst
Fehler: Nach einer Antwort blieb die Frage in der Liste stehen, nur der Zähler im Menü stimmte. Ursache: Die Karte wurde
nach der Antwort nur gesperrt, und von selbst neu geladen haben sich nur Start und Betrieb. Alle anderen Seiten zeigten
Änderungen erst nach einem Wechsel – nach eigenen Aktionen wie nach Änderungen durch Agenten oder Brücke.
- **Nach einer eigenen Aktion** ist die beantwortete oder geparkte Frage sofort weg. Danach wird die offene Seite
  frisch gezeichnet, das gilt für jede Aktion auf jeder Seite, auch online und am Handy.
- **Änderungen von außen:** `/api/start` bringt je Seite einen Änderungs-Stempel (jüngste Änderung und Anzahl ihrer
  Daten: Fragen, Aufgaben, Planung, Verlauf, Wissen, Dokumente, Release Notes). Ändert er sich, zeichnet die Workbench
  die offene Seite still neu, Scrollstelle und aufgeklappte Abschnitte bleiben. Lebenszeichen der Agenten zählen nicht.
  Online kommt der Stempel mit dem Abgleich; die Seite lädt dann noch einmal nach. Die Projekt-Auswahl hält ihre Zahlen
  im selben Takt frisch.
- **Keine Eingabe geht verloren:** Wird gerade getippt, steht ungespeicherter Text in einem Feld, ist Text markiert
  oder ein Dialog offen, wird nicht neu gezeichnet. Stattdessen erscheint unten „Neuer Stand“ mit Knopf. Das gilt jetzt
  auch für Start und Betrieb.
- Test im echten Browser (Edge ohne Fenster): Antwort → Frage sofort weg; neue Frage von außen erscheint ohne Klick;
  halb geschriebener Text bleibt.

## 1.20.0 – 06.11.2026 · Projekte völlig getrennt
Entscheidung des Entwicklers: Jedes Projekt wird für sich gesteuert und hat keine Berührung zu einem anderen
([doc/plan-projektwahl.md](doc/plan-projektwahl.md), Abschnitt F). Schema 19 – vorher `amw sichern`.
- **Arbeitsregeln je Projekt.** KR galten bisher für alle Projekte einer AMW; jetzt gehören sie wie die PR dem
  Projekt. Vorhandene KR gehören dem Projekt ihres Beschlusses. `amw regeln`, Pflicht-Kontext, Suche und Workbench
  zeigen nur die des Projekts.
- **Neues Projekt mit Regel-Kopie:** `amw projekt neu <name> --regeln-von <Projekt>` kopiert die Arbeitsregeln einmal;
  danach ändert jedes Projekt seine Fassung allein. Ohne die Option startet es ohne Regeln.
- **KI-Vorlagen je Projekt.** Ein Bild-Workflow gehört dem Projekt, das ihn setzt; zwei Projekte können gleich
  benannte Vorlagen haben. KIs und Modelle bleiben PC-weit („dieser PC“).
- **Kein Agent in einem fremden Projekt.** `--projekt`/`AMW_PROJEKT` mit einem Projekt, in dem es die Kennung nicht
  gibt, lehnt die AMW ab, auch über die Brücke. Nur der Entwickler wählt frei. Steht im Startskript ein falsches
  Projekt, nimmt der Hook das Projekt der Kennung.
- Migrationen, die Tabellen neu anlegen, laufen jetzt ohne Fremdschlüssel-Prüfung und prüfen sie vor dem Abschluss
  (`PRAGMA foreign_key_check`).

## 1.19.1 – 06.11.2026 · Online-Speicher: neue Spalte wirklich anlegen
- Turso liefert Zahlen als Text. Die Prüfung „gibt es `eingang.projekt` schon?“ las deshalb „0“ als ja, und die Spalte
  fehlte. Der Abgleich brach dann beim Abholen ab, die Seite zeigte weiter die alten Ansichten. Jetzt wird die Zahl
  umgewandelt; ein Test ahmt Turso nach.

## 1.19.0 – 06.11.2026 · Mehrere Projekte, Teil 3: online je Projekt und auf mehreren Rechnern
Letzter Schritt aus [doc/plan-projektwahl.md](doc/plan-projektwahl.md).
- **Alles online trägt die Projekt-Kennung.** Ansichten liegen unter `<Kennung>:<Weg>`, ebenso Suchindex, Gespräche,
  „zuletzt gesehen“ und die Zuordnung der Dateien. Befehle vom Handy tragen die Kennung des Projekts, in dem du sie
  gibst.
- **Verzeichnis aller Projekte** im Online-Speicher: Name, Farbe, Rechner, offene Fragen, Halt und „zuletzt gesehen“.
  Online kannst du jetzt umschalten, auch zu Projekten anderer Rechner.
- **Mehrere Rechner an einem Online-Speicher:** Jeder Rechner lädt nur seine Projekte hoch. Er führt nur deren Befehle
  aus und löscht nichts, was einem anderen gehört. Eine Datei, die zwei Projekte nennen, bleibt online, bis keines sie
  mehr braucht. Ein Rechner prüft das vor dem Löschen frisch, denn der andere kann sie gerade angemeldet haben.
- **Workbench am PC:** Projekte anderer Rechner stehen mit „↗“ und Rechnername in der Auswahl und öffnen die
  Online-Seite des Projekts (Link aus Zahnrad › Push). Ein Projekt, das sich über 7 Tage nicht gemeldet hat, ist
  gekennzeichnet.
- **Übergang:** Der Online-Speicher bekommt die neuen Tabellen und die Spalte `eingang.projekt` von selbst. Alte
  Ansichten ohne Kennung löscht der PC nach dem ersten Hochladen; bis dahin liest die Seite sie weiter. Befehle ohne
  Kennung (alte Seite im Browser) gehen an das erste Projekt.
- Anleitung „Weiterer Rechner“ in [doc/installation.md](doc/installation.md).

## 1.18.0 – 06.11.2026 · Mehrere Projekte, Teil 2: Projekt-Auswahl in der Workbench
Zweiter Schritt aus [doc/plan-projektwahl.md](doc/plan-projektwahl.md). **Umschalten ändert nur die Ansicht**; kein
Projekt hält an.
- **Auswahl oben in der Navigation** mit Name und Farbe. Ein Klick öffnet die Liste aller Projekte mit Agenten, Halt und
  offenen Fragen an dich („3 ?“), damit man sieht, ob drüben etwas wartet. Am Handy steht das Projekt als Chip neben
  der Marke und öffnet ein Blatt von unten.
- Nach dem Wechsel lädt die Seite neu. Danach zeigt jede Ansicht nur das gewählte Projekt, und jeder Knopf wirkt nur
  dort. Jede Anfrage trägt das Projekt (`?projekt=<Kennung>`).
- Das Projekt steht in der Adresse, deshalb öffnen Links und Push-Meldungen genau dieses Projekt. Sicht und „Seit du weg
  warst“ merkt sich der Browser je Projekt.
- **Farbe je Projekt** (Einstellungen → Projekt) als Streifen über dem Kopf.
- **„dieser PC“:** Lokale KI, freier Speicher und „Dieser PC“ tragen die Marke. Bei mehreren Projekten bekommen die
  Signale Dienst, Speicher und Schirm ein kleines „PC“. Belegt ein anderes Projekt dieses PCs die Grafikkarte oder den
  Schirm, steht das oben in der Lauf-Liste, mit Projektname und Uhrzeit, ohne Titel.
- **Name dieses Rechners** (Einstellungen → Dieser PC), Vorgabe ist der Computername. Er wird gebraucht, sobald Projekte
  auf mehreren Rechnern laufen (Teil 3).
- Online zeigt die Seite das Projekt schon an. Umschalten geht online erst mit Teil 3, wenn der Abgleich je Projekt
  läuft.

## 1.17.0 – 06.11.2026 · Mehrere Projekte, Teil 1: Agenten, Brücke und Push je Projekt (Schema 18)
Erster Schritt zur Projekt-Auswahl ([doc/plan-projektwahl.md](doc/plan-projektwahl.md)). Mit nur einem Projekt ändert
sich nichts. Die Prüfung mit zwei Projekten hat drei Stellen gefunden, die bisher gescheitert wären:
- **Befehle der Agenten:** Fehlt `--projekt`/`AMW_PROJEKT`, nimmt die AMW das Projekt, in dem es die Kennung (`--von`)
  gibt. Bisher scheiterte jeder Befehl, sobald es ein zweites Projekt gab. Ist die Kennung mehrdeutig (z. B. derselbe
  Lead in zwei Projekten), nennt die Meldung die Projekte. Das Startskript eines Agenten setzt zusätzlich
  `AMW_PROJEKT`, und der Hook meldet die Sitzung im Projekt der Kennung an.
- **Brücke:** Befehlsdateien dürfen `"projekt": "<name>"` tragen. Ohne Angabe gilt das Projekt der Kennung. Der Puls
  zählt nur im genannten Projekt.
- **Push je Projekt (Schema 18):** Jede Meldung gehört zu einem Projekt, `push_versand.projekt_id`. Bisher hielt die
  Runde des einen Projekts die Meldungen des anderen für erledigt, und sie gingen nie raus. Mit mehreren Projekten
  steht der Name vorn im Titel, und der Link öffnet das Projekt (`?projekt=<Kennung>`). Vorhandene Einträge gehören
  dem ersten Projekt.
- **Verbrauch** wird über die Sitzung dem Projekt zugeordnet, nicht über die Kennung. Gleiche Kennungen in zwei
  Projekten zählen nicht mehr doppelt.
- `--projekt` nimmt auch die Projekt-Kennung (uid), so wie sie online steht.

## 1.16.2 – 06.11.2026 · Englische Oberfläche: Gegenlese durch die lokale KI
Der erste echte KI-Auftrag über die AMW: 6 Läufe mit qwen3.5:9b, je etwa 140 Zeilen „Schlüssel | Deutsch | Englisch“,
zusammen 66 Vorschläge. Geprüft wurde jede Zeile gegen den Code. Übernommen ist, was stimmt; vier Schlüssel hatte die
KI erfunden, viele Vorschläge hätten den Sinn verändert.
- **Fest eingebaute deutsche Texte** erscheinen jetzt auch übersetzt: Die KI fiel über „Bogen 3“ im Englischen; die
  Suche danach fand 14 Stellen, an denen „Bogen N“ fest im Code stand (Zeitleiste, Übersicht, Dokumente, Plan-Check,
  Verlauf, Fenstertitel). Dazu kamen „BILD“ auf Dokument-Kacheln, deutsche Anführungszeichen, der Platzhalter für den Link
  in Push-Meldungen und eine Fenster-Beschriftung für Vorleser.
- **Klarere englische Texte:** Online storage (Turso), sign out after inactivity, maximum session length, lockout after
  failed sign-ins, differences from the latest version, types statt kinds, im Verlauf „sent back“ und „step picked up“,
  „Request upload“ für Dokumente nur am PC.

## 1.16.1 – 06.11.2026 · Brücke: neuestes Ergebnis unter dem eigenen Namen, Wortlaut nicht doppelt
- **Brücke:** Kam eine Befehlsdatei mit einem Namen, den es in `eingang-tl/erledigt/` schon gab, lag ihr Ergebnis unter
  `name.2.ergebnis.json`; unter `name.ergebnis.json` stand weiter das alte. Das sah aus, als sei der Befehl nicht
  ausgeführt worden, und er wurde ein zweites Mal geschickt. Jetzt steht das neueste Ergebnis immer unter dem Namen der
  Befehlsdatei. Der frühere Beleg rückt auf `name.2`, `name.3` … und das neue Ergebnis nennt ihn unter `frueher`.
- **Wortlaut:** Dieselbe Aussage (gleiche Zeit, gleicher Text) wird nicht mehr doppelt erfasst. `amw wortlaut` lehnt
  sie mit der Nummer des vorhandenen Eintrags ab.

## 1.16.0 – 06.11.2026 · Lokale KIs in der AMW (Schema 17)
Umsetzung von Stufe 1 aus [doc/plan-lokale-ki.md](doc/plan-lokale-ki.md):
- **Eigene Art „KI“** (`amw ki`):
  - KIs (Ollama, ComfyUI) gelten für den ganzen PC; Endpunkte sind nur lokal erlaubt.
  - Modelle tragen Lizenz, Herkunft und Prüfsumme und haben eine **Freigabe** offen | frei | gesperrt. Frei gibt der Lead,
    bei Nutzungsregeln oder Registrierung nur der Entwickler; es gibt sie nur bei kommerziell nutzbarer Lizenz. Ändert
    sich eine Lizenzangabe, ist die Freigabe wieder offen.
  - Vorlagen sind ComfyUI-Workflows im API-Format mit Platzhaltern. Rechte zum Beauftragen gelten je Projekt.
  - Eintragen und Ändern (Endpunkt, Startbefehl) geht nur am PC, nicht über Brücke oder Online-Seite.
- **Aufträge über die AMW** (`amw ki auftrag`):
  - Ein Auftrag ist ein Lauf in der gemeinsamen Schlange: schwer und mit dem neuen Platz **gpu**.
  - Auf dem ganzen PC läuft höchstens ein GPU-Lauf zur Zeit. GPU- und Schirm-Läufe warten aufeinander, laufende Läufe
    werden nie unterbrochen.
  - Jede Modell-Datei, die eine Vorlage nennt, muss eingetragen und frei sein.
- **Ausführung durch die AMW:**
  - Ist ein Auftrag dran, führt ihn der Dienst selbst aus, auch wenn der Auftraggeber schläft.
  - ComfyUI startet er bei Bedarf mit dem eingetragenen Startbefehl ohne Fenster. Danach entlädt er die Modelle
    (`/free`, Ollama `keep_alive 0`).
  - Abbrechen geht mit `amw lauf ende <nr> --abgebrochen` (über `/interrupt`). Prozesse beendet die AMW nicht.
  - Ein Neustart des Dienstes holt laufende ComfyUI-Aufträge weiter ab.
- **Herkunft automatisch:**
  - Jedes Ergebnis wird ein Dokument zur Aufgabe.
  - Die AMW schreibt dazu unveränderlich: KI, Version, Modell(e) mit Lizenz, Vorlage mit Prüfsumme, Prompt, Seed,
    Parameter, Dauer und Spitze des Grafikspeichers.
  - Bei PNG prüft sie zusätzlich, ob der Seed im Bild steht. Der Auftraggeber wird mit den D-Nummern geweckt.
  - `amw ki zeige L<nr>` zeigt den Stand eines Auftrags, `amw ki nachweis` listet alle KI-Dokumente mit Modell und
    Lizenz (Grundlage für Store-Angaben).
- **Workbench und online:** Betrieb → „Lokale KI“ zeigt:
  - eine Kachel je KI (bereit/rechnet/aus, Version, Modelle im Grafikspeicher, wartende Aufträge, wer beauftragen darf);
  - die Modelle mit Freigabe, die Vorlagen und die KI-Aufträge mit Ergebnissen.
  Im Dokument-Fenster steht die Herkunft, in der Lauf-Liste die Marke „GPU“.
- **Eigene GPU-Läufe:** `amw lauf start|ausfuehren --gpu` und `amw rezept setzen --gpu`.
- **Brücke:** `ki` ist erlaubt (außer `neu`/`aendern`). `--text-datei` und `--prompt-datei` gehen wie `--datei` nur aus
  `eingang-tl/`; bisher konnte `--text-datei` jede Datei des PCs lesen.
- Schema 17: neue Tabellen `ki`, `ki_modell`, `ki_vorlage`, `ki_recht`, `ki_auftrag`, `ki_herkunft`; Spalte `gpu` an
  `lauf` und `rezept`. Die Umstellung läuft beim ersten Schreibzugriff und ändert nichts an vorhandenen Läufen.

## 1.15.3 – 05.11.2026 · Brücke: Wert als Positionsangabe
- **Brücke:** `"wert"` in einer Befehlsdatei ist jetzt die Positionsangabe nach der Nummer, z. B.
  `{"befehl": "bogen", "aktion": "status", "id": 5, "wert": "aktiv"}`. Bisher wurde daraus `--wert`, und der Befehl
  scheiterte. Die Form `{"args": [...]}` geht weiterhin.

## 1.15.2 – 05.11.2026 · Fenster schließen, Oberfläche ohne Projektbezug
- **Jedes Fenster hat oben rechts „✕“:** Dokument, Aufgabe, Thema, Bögen und Einstellungs-Dialoge. Bisher ging es nur mit
  Esc oder einem Klick daneben, am Handy oft gar nicht. Esc schließt jetzt nur das oberste Fenster, vorher alle
  übereinander. ✕ und Esc fragen im Text-Editor weiter nach, bevor Ungespeichertes verworfen wird.
- **Einstellungen › Projekt:** Der Reiter heißt „Projekt“. Der Name steht als Wert darin („Aktives Projekt“) mit dem
  Hinweis, dass er aus den Daten kommt. Bisher stand er in der Überschrift und sah fest eingebaut aus.
- **Universal-Durchgang über die sichtbare Oberfläche:** Jede Ansicht wurde mit einer leeren Demo-Datenbank geöffnet und
  ihr Text geprüft. Neutral gemacht wurden „Brücke für den TL“ und die Beispiel-Kennung „CC9“. Der Text für das
  Push-Ereignis „Testtermin“ fehlte. Dazu kommen Beispiele in Tests, Kommentaren und `doc/plan-lokale-ki.md`.

## 1.15.1 – 05.11.2026 · Absender wird geprüft
- **`--von` muss eine Kennung des Projekts sein.** Bisher nahm die AMW auch „CC5,TL“ als Absender an (#17299: der
  Empfänger stand in `--von`). Jetzt bricht sie mit einer Erklärung ab, und es wird nichts gesendet.

## 1.15.0 – 05.11.2026 · Aufgabe öffnen, Push nur was noch gilt
- **Aufgabe öffnen:** Ein Klick auf eine Aufgabe öffnet sie ganz. Das gilt für die Startseite („Wartet auf dich“,
  bisher ein Sprung in die Planung), für Liste, Board, Pool und die Listen-Ansicht. Die Ansicht zeigt:
  - Auftrag, Stand, Zuständigen und Wartegründe;
  - die Fragen dazu mit Antwort, auch die nur im Titel oder Auftrag genannten (F5165, D94–D101);
  - Dokumente, Beschlüsse, Läufe, Prüfungen und den Verlauf.
  Online geht das genauso, für offene Aufgaben und solche der letzten 3 Tage.
- **Dein Teil:** Bei Aufgaben des Entwicklers gibt es „Erledigt“ (die Notiz ist der Beleg) und „Später“ (ans Ende der
  eigenen Liste). Zu jeder Aufgabe gibt es „Antwort an …“. Wer die Aufgabe angelegt hat, erfährt es sofort (sonst die
  Federführung oder der Lead). Das geht auch vom Handy.
- **Fragen-Stand auf der Karte:** „alle 3 Fragen beantwortet“ bzw. „1 von 3 Fragen offen“.
- **Push:** Nach der Ruhezeit verschickt die AMW nur noch, was noch gilt. Eine nachts schon beantwortete Frage oder eine
  inzwischen gelesene Nachricht fällt weg. Eine Erinnerung zur selben Frage zählt nicht doppelt. Bisher kam morgens
  „6 neue Fragen“, obwohl alle beantwortet waren.
- Test: Der Schirm-Test von `lauf ausfuehren` hängt nicht mehr an echten Eingaben am PC.
- Entwurf `doc/plan-lokale-ki.md`: lokale KIs (Sprache, Bild, Ton, 3D) in der AMW, zur Diskussion.

## 1.14.0 – 05.11.2026 · Design-Dokument je Thema, Projekt-Stil
Eine Seite „gilt jetzt“ je System statt eines Stapels sich widersprechender Beschlüsse (→ `doc/automatismen.md`).
Schema 16. Die vorhandenen Themen der Beschlüsse werden beim Update übernommen.
- **`amw thema liste | zeige TH12 | neu "Name" [--pfleger X] [--stil] | einstellen | pflegen | bestaetigen | dokument`:**
  Die Seite eines Themas zeigt die gepflegte Zusammenfassung (in Fassungen) und alle geltenden Beschlüsse, darunter die
  unklaren und überholten.
- **Veraltet:** Ein neuer Beschluss im Thema markiert die Zusammenfassung als „veraltet seit B…“ und weckt den Pfleger,
  bis er sie anpasst oder bestätigt.
- **Beschlüsse:** Das Thema ist Pflicht (`--thema`, TH-Nummer oder eindeutiger Anfang, `--neues-thema`). `beschluss
  neu` zeigt die geltenden Beschlüsse desselben Themas. Neu sind `beschluss ueberholt B12 --durch B30`, `beschluss
  unklar B12`, `beschluss gilt B12` und `beschluss thema B12 --thema …`.
- **Projekt-Stil:** ein Thema mit Bildern. Der Pflicht-Kontext aller Agenten verweist darauf, und eine Abweichung ist
  eine Frage.
- **Workbench › Wissen › Themen:** Karten je Thema mit Stand und Pfleger. Die Seite öffnet als Dialog, mit Bildern im
  Vollbild. Online genauso.

## 1.13.0 – 05.11.2026 · Terminplaner
Testtermine des Entwicklers im festen Rhythmus, davor die Frist „Testbuild fertig“ für alle (→ `doc/automatismen.md`).
Schema 15.
- **`amw termin neu --titel … --art test|frist|schirm|sonstig --am "06.11. 18:00" [--woechentlich] [--bogen N]`**,
  `termin liste`, `aendern`, `absagen` (ganz oder ein Vorkommen). Planen dürfen Lead und Entwickler, auch über die
  Brücke.
- **Frist und Ampel:** Ein Testtermin setzt „Testbuild fertig“ 4 h vorher (`--vorlauf`). Ist ein Bogen verknüpft,
  vergleicht die Ampel seine Prognose mit der Frist.
- **`amw termin bereit N --text "was testen"`:** Meldung an den Entwickler mit der Kurzliste der Aufgaben und Merges, die
  seit dem letzten Test fertig wurden.
- **Erinnern:** Frist ohne Meldung weckt einmal den Lead. 1 h vor dem Test bekommt der Entwickler eine Push-Nachricht
  (neues Push-Ereignis „Termine“).
- **Sichtbar:** Band „Nächster Test“ auf der Startseite, Planung › Termine nach Tagen, Pflicht-Kontext.
- **Aufgaben des Entwicklers:** `aufgabe neu --agent Entwickler` (oder sein eingestellter Name) geht wieder. Seine
  Aufgaben stehen in seiner eigenen Arbeitsliste (`amw liste Entwickler`, `liste ordnen Entwickler …`). Unter
  Aufgaben › Listen steht sie als „Deine Aufgaben“ ganz vorn.

## 1.12.1 – 04.11.2026 · Arbeitsliste auch über die Brücke
- Die Brücke des Leads nimmt jetzt `liste` an (ordnen, schieben, ansehen), dazu `suche` und `zeige`.

## 1.12.0 – 04.11.2026 · Arbeitsliste je Agent
Jeder Agent arbeitet eine geordnete Liste von oben nach unten ab, genau eine Aufgabe ist in Arbeit. Ohne Bremse: Der
Umfang darf groß sein (→ `doc/automatismen.md`).
- **`amw liste [Agent|pool]`** zeigt die Listen mit Position, Status und Wartegründen. **`amw liste ordnen <Agent> A12
  A15 …`** und **`amw liste schieben A15 --vor A12 | --nach | --pos N | --oben | --unten`** ordnen sie (Lead).
  **`aufgabe neu … --pool`** legt eine Idee in den Pool.
- **Genau eine in Arbeit:** Startet ein Agent eine weiter oben stehende Aufgabe, wird die laufende untere von selbst
  zurückgestellt (wartet auf die obere). Startet er eine weiter unten, während eine obere läuft, bekommt er einen Hinweis,
  und der Lead erfährt es.
- **Von selbst weiter:** Ist eine Aufgabe fertig, weckt die AMW mit der nächsten startbaren Aufgabe der Liste. Wird eine
  obere wieder frei, nennt der Weckruf ihre Position („zuerst abschließen“).
- **Sichtbar:** Der Pflicht-Kontext zeigt „Deine Liste: 1. A12 [laeuft] … 2. A15 [wartet auf F12] …“. Workbench ›
  Aufgaben öffnet mit „Listen“: eine Spalte je Agent, darunter der Pool. Die Kachel zeigt „Liste 1/7“. Online genauso.

## 1.11.0 – 04.11.2026 · Federführung je Bogen und Aufgabe, Läufe aus einer Hand
Weniger wartet auf den Lead: Wer einen Bogen oder eine Aufgabe führt, nimmt Prüfergebnisse und Fragen dazu an
(→ `doc/plan-federfuehrung.md`). Schema 14.
- **Federführung:** `amw bogen aendern N --federfuehrend X` bzw. `amw aufgabe aendern N --federfuehrend X`. Setzen dürfen
  Lead und Entwickler, leer nimmt sie weg. Zuständig ist die Federführung der Aufgabe, sonst die ihres Bogens, sonst der
  Lead. Der neue Federführende bekommt einen Auftrag mit seiner Rolle.
- **`--an zustaendig --aufgabe N`** bei `posten` und `frage neu` erreicht, wer die Aufgabe gerade führt.
- **Prüfergebnisse** gehen an den Bauer und an den Zuständigen.
- **Eskalation:** Bleibt eine Frage, Prüfbitte oder ein Auftrag beim Federführenden 30 min ungelesen, bekommt der Lead
  einmal eine weckende Zeile. Die Frist steht in den Projekt-Einstellungen als `eskalation_min`, 0 schaltet sie aus.
- **Sichtbar:** Der Pflicht-Kontext zeigt „Du führst: Bogen 3 …, A1250 …“. Die Bogen-Karte zeigt „Federführend“, die
  Kachel des Agenten „◆ führt B3, A1250“.
- **`amw lauf ausfuehren --beschreibung … [--schirm] [--ergebnis datei] [--frist MIN] [--hoechstens MIN] -- <befehl …>`:**
  Der Befehl reiht ein, wartet, startet, schreibt die Ausgabe auf den Bildschirm und in die Ergebnis-Datei (mit Kopf und
  Ende), reicht den rc durch und meldet das Ende. Bei Schirm zu, Ende von außen, Frist oder Strg+C beendet er den eigenen
  Prozessbaum, was der Prozess des Agenten selbst tut, nicht der Dienst. Eigene Rückgabewerte: 200 nie gestartet, 201
  Schirm zu, 202 von außen beendet, 124 Frist, 130 Strg+C. Er ersetzt die eigenen Hüllen-Skripte um jeden Lauf.

## 1.10.1 – 04.11.2026 · Schirm-Läufe schließen den Schirm nicht mehr selbst, Dateien online als Einstellung
- **Eingaben eines Schirm-Laufs zählen nicht als „Entwickler ist da“:** Abläufe mit Fenster klicken und tippen selbst.
  Windows meldet das wie eine Eingabe am PC, und der Schirm ging zu, während der Entwickler am Handy war. Darauf brach
  der Lauf ab. Eingaben während eines Schirm-Laufs und bis 30 s nach seinem Ende schließen jetzt nicht mehr. Die anderen
  Signale gelten weiter: Fernsitzung, Eingabe in der Workbench am PC, Uhrzeit. Danach zählt jede Eingabe wieder.
- **Dateien online** (Zahnrad › Projekt): Hier steht, welche Dateien von Dokumenten der PC von selbst auf die
  Online-Seite lädt. Zur Wahl stehen „nur auf Wunsch“ (Vorgabe, wie bisher), „Bilder und Mockups“ und „alle (auch PDF,
  Office)“. Die Einstellung gilt für neue und vorhandene Dokumente. Zurückstellen nimmt nichts herunter, das geht je
  Dokument mit „Nur am PC“. Vorher zeigte die Online-Seite Bilder erst, nachdem jemand sie einzeln mit „Online
  anfordern“ geholt hatte. Ohne diesen Klick sah man an einem fremden Rechner keine Bilder.

## 1.10.0 – 04.11.2026 · Wünsche der Agenten aus dem Betrieb
Was die Agenten nach einer Woche Betrieb gebraucht und begründet haben, mit echten Fällen. Schema 13.
- **Eine info an genau einen Empfänger weckt.** Bisher weckte keine info. „Merge erledigt“ oder „Lauf jetzt möglich“ lagen
  so bis zu 75 Minuten ungelesen. Sammel-Infos an mehrere und Kopien der AMW wecken weiter nicht. Ältere Nachrichten
  wecken nach einem Update nicht auf einmal.
- **Warten auf die Datenbank wird sichtbar:** Nach 10 s Warten auf die Datenbank schreibt `amw` alle 10 s eine Zeile
  („warte seit 20 s auf die Datenbank – ein anderer Prozess schreibt gerade“). Nach 30 s bricht es mit Rückgabewert 3 und
  einer klaren Meldung ab. Vorher hing es still.
- **lesen:** `amw lesen 16707 16589` zeigt mehrere Nachrichten auf einmal. `lesen --neu` zeigt nur Ungelesenes, neueste
  zuerst. `lesen --verlauf` zeigt die letzten Nachrichten an mich, auch gelesene und erledigte. Ist die Aufgabe einer
  Nachricht schon abgeschlossen, steht „(A… schon fertig)“ dabei.
- **erledigt:** `erledigt --info [--vor 04.11.]` hakt alle info-Nachrichten auf einmal ab. Die AMW-Meldung „A…: X hat
  geschrieben (#…)“ ist mit der Nachricht, die sie meldet, gleich mit erledigt. `aufgabe start` hakt die Meldung „alle
  Gründe erledigt – weiter“ ab.
- **Nummern mit Vorsilbe überall:** `A1162`, `#16000`, `L12`, `F7` gehen, wo eine Nummer erwartet wird.
- **`amw abmelden`:** Die Sitzung ruht. Sie wird nicht mehr geweckt und nicht automatisch neu gestartet, bis zum nächsten
  `amw anmelden` oder Start. Der Lead erfährt es. Die Workbench zeigt „abgemeldet“.
- **Alter der Tätigkeit:** Workbench und `agent liste` zeigen, seit wann die eigene Angabe steht. Ab 2 h ist sie in
  Bernstein markiert („veraltet?“). `aufgabe start` und `lauf start` setzen die Tätigkeit nur, wenn keine da ist oder sie
  älter als 2 h ist. Eine eigene, genauere Angabe wird nicht überschrieben.
- **`--an alle`** erreicht auch Agenten mit Soll „aus“, deren Sitzung läuft. Wen es nicht erreicht, steht in der Ausgabe
  („nicht erreicht: CC7 (Soll aus, keine Sitzung)“).
- **`aufgabe nachtrag <nr> --titel …`:** Folgearbeit zu einer fertigen Aufgabe wird eine neue Aufgabe mit Bezug, mit dem
  gleichen Besitzer und Prüfer. Wer mit `--aufgabe` auf eine fertige Aufgabe zeigt, bekommt das als Vorschlag.
- **`aufgabe zeige <nr> --kurz`:** eine Zeile mit Status, Besitzer, Titel und Wartegründen.
- **Hinweis „A… gehört X – richtig?“** kommt nur noch beim ersten Beitrag zu einer fremden Aufgabe. Er entfällt für ihren
  Prüfer und bei Antworten auf eine Nachricht zu dieser Aufgabe.
- **`notiz zeige --suche CC5`:** nur Notizen, deren Schlüssel oder Text die Wörter enthält.
- **Startskript:** Die Agenten starten 20 s nacheinander statt alle auf einmal (`--abstand N`). `--alle` nimmt auch die
  mit Soll „aus“ oder „ruht“ dazu.
- **Freigabe-Zeile eines Laufs** wird an einer Wortgrenze gekürzt, nicht mitten im Inhalt. Die ganze Beschreibung steht
  im Text.
- **Aufruf-Fehler** nennen den Grund in der ersten Zeile, z. B. „invalid choice: 'plan' (choose from …)“, danach die
  Kurzhilfe.
- **Git-Bash-Pfade** (`/c/Users/…`, `/f/…`) gehen bei `--text-datei`, Dateien, Ordnern und Anhängen.

## 1.9.2 – 04.11.2026 · Brücke behält jeden Beleg
- **Brücke überschreibt nichts mehr:** Kam eine Befehlsdatei mit einem Namen, der in `eingang-tl/erledigt/` schon lag,
  ersetzte die Brücke Befehl und Ergebnis des früheren Durchgangs – die Spur war weg. Jetzt landet sie als `khp.2.json`
  usw. daneben. Das Protokoll nennt dazu den Befehl kurz („Brücke: khp.json → rc 0: posten“).

## 1.9.1 – 04.11.2026 · Universell: Name und Fernsitzung als Einstellung
- **Schirm geht nur noch bei Signalen am PC zu:** Eingabe am PC, eine neue Fernsitzung, eine Eingabe in der Workbench am
  PC oder die bis-Uhrzeit. Ein neuer Wortlaut (z. B. vom Lead aus einem Chat übernommen) und Eingaben auf der
  Online-Seite schließen ihn nicht mehr – wer vom Handy schreibt, sitzt nicht am PC. Zumachen von unterwegs geht weiter.
- **Name des Entwicklers als Projekt-Einstellung** (Zahnrad › Projekt, Vorgabe „Entwickler“): Meldungen sagen z. B.
  „Marie ist da (Workbench, 06:02)“ oder „Leerlauf: warten auf Marie“; als Wartegrund geht `--auf Marie` ebenso wie
  `--auf Entwickler`. Vorher stand ein fester Name im Code.
- **Fernsitzung als PC-Einstellung** (Zahnrad › Dieser PC, `fernsitzung_prozess`): das Programm, das nur während einer
  Fernwartungs-Verbindung läuft (bei TeamViewer z. B. `teamviewer_desktop.exe`). Leer = nicht prüfen. Vorher war
  TeamViewer fest eingebaut.
- Code, Kommentare, Hilfe und Änderungsliste nennen keine Nummern und Namen eines bestimmten Projekts mehr; der
  Entwurf der Automatismen ist als neutrale Beschreibung `doc/automatismen.md` im Repository.

## 1.9.0 – 04.11.2026 · Umbenennen mit Alias, Nachschlagen, Kacheln nach Rolle
- **`amw agent umbenennen <alt> <neu>`** (Entwickler/Lead): neue Kennung in allen Spalten, die eine Kennung tragen
  (Nachrichten von/an, Aufgaben, Fragen, Läufe, Prüfungen, Sperren, Wartegründe …) in einem Schreibvorgang; Freitexte
  bleiben. Die **alte Kennung bleibt als Alias gültig**: `--von`, `AMW_AGENT`, `--an`, `--agent`, Halt und die Brücke
  finden den Agenten weiter, laufende Sitzungen müssen nicht neu starten. Sitzungen hängen an ihrer ID, Verlauf,
  Gesprächsansicht und „In Claude öffnen“ bleiben. `amw agent liste` zeigt „(früher …)“. Vorher `amw sichern`.
- **`amw suche <Stichwort>`**: Volltext über Aufgaben, Beschlüsse, Fragen, Wortlaut, Nachrichten und Dokumente in kurzen
  Zeilen (`--art`, `--grenze`, `--wissen` zeigt dazu die passenden Beschlüsse/Fragen/Regeln wie bei `frage neu`).
- **`amw zeige B12 F7 A1201 W3 16000 D5 KR3 PR42`**: Einträge ganz lesen, mehrere auf einmal (Nachrichten ohne `#`).
- **Kacheln nach Rolle:** Die Startseite ordnet die Agenten nach ihrer Rolle (Lead zuerst, gleiche Rollen nebeneinander) und
  zeigt je Agent „A… wartet auf …“ aus den Wartegründen. Die Rolle ist je Agent frei einstellbar (Zahnrad › Agenten).

## 1.8.0 – 04.11.2026 · Wartegründe, Wecken, Frage-Prüfung
Automatismen statt Gebote, Teil 2: Wartegründe und Wecken, dazu die Prüfung neuer Fragen gegen das, was schon
entschieden ist (→ `doc/automatismen.md`). Schema 12.
- **Wartegrund als Verweis:** `amw aufgabe wartet|blockiert <nr> --auf F12,A120,L7,CC2,Entwickler,Monitor:<was>`.
  Ohne `--auf` lehnt die AMW „wartet“ und „blockiert“ ab – Freitext allein reicht nicht mehr (`--wartet-auf` bleibt als
  Erklärung). Eine neue, nicht begonnene Aufgabe steht weiter ohne Grund auf „wartet“ (= zu tun).
- **Erledigter Grund weckt:** Frage beantwortet, Aufgabe fertig oder verworfen, Lauf zu Ende, der genannte Agent
  schreibt mit `--aufgabe` dieser Aufgabe, der Entwickler beantwortet eine Frage zu ihr → der Besitzer bekommt eine
  weckende Meldung („A120: F12 beantwortet: B) … – noch offen: A121“ bzw. „alle Gründe erledigt – weiter“), Kopie an den
  Lead. Von Hand abhaken: `amw aufgabe wartet <nr> --erledigt F12` (Besitzer oder Lead, z. B. nach dem Wort des
  Entwicklers im Chat).
- **Leerlauf-Prüfung:** Ist eine Sitzung seit 30 min frei, ohne offene Post, und hat der Agent eine Aufgabe ohne
  offenen Grund (Vorgänger fertig, nicht geparkt), weckt ihn der Dienst mit dieser Aufgabe – einmal je Ruhephase. Warten
  alle Aufgaben eines freien Agenten auf den Entwickler, bekommt der Lead höchstens alle 6 h eine Sammelzeile.
- **Aufgaben-Bezug geprüft:** `posten`/`frage neu --aufgabe` mit einer Nummer, die es nicht gibt oder die fertig ist,
  wird abgelehnt; bei einer fremden Aufgabe kommt ein Hinweis.
- **Kopie an den Besitzer:** Eine `info`, `meldung` oder `antwort` zu einer fremden Aufgabe geht in Kopie an ihren
  Besitzer, weckend, wenn seine Aufgabe wartet. Nicht bei `auftrag` und `pruefbitte` (Merge- und Prüfbitten).
- **Was eine Frage aufhält:** Workbench und Online-Seite zeigen an jeder offenen Frage „hält A120 (CC1) seit …“.
- **Frage-Prüfung gegen die Datenbank:** `amw frage neu` sucht in geltenden Beschlüssen, beantworteten Fragen und
  Regeln nach den Wörtern der Frage. Fragen an den Entwickler brauchen `--geprueft "…"`; findet die AMW Treffer, muss es
  mindestens einen davon nennen („B5 passt nicht, weil …“). Bei Fragen an den Lead zeigt sie die Treffer nur. Die
  Workbench zeigt „Vorher geprüft: …“ an der Frage.
- `amw aufgabe liste`/`zeige` und der Pflicht-Kontext zeigen die offenen Gründe; „Wartet auf dich“ kennt die Verweise.
- Vorbereitet für 1.9.0 (Agenten nach Rolle umbenennen): Spalte `agent.alias`.

## 1.7.1 – 04.11.2026 · Korrektur Brücke
- **Beschlüsse über die Brücke gehen wieder:** 1.7.0 hatte `--quelle` über die Brücke für alle Befehle gesperrt. Bei
  `beschluss` ist `--quelle` aber die inhaltliche Quelle (z. B. „Entwickler 04.11. 11:35“) und Pflicht, so konnte der Lead
  keine Beschlüsse mehr anlegen. Gesperrt ist `--quelle` jetzt nur noch beim Schirm, dort setzt die Brücke sie selbst.

## 1.7.0 – 04.11.2026 · Schirm-Schalter
Automatismen statt Gebote, Teil 1 (→ `doc/automatismen.md`).
- **Schirm frei/zu als Zustand in der AMW:** Ob Agenten Läufe mit Fenster starten dürfen, steht jetzt in der AMW, nicht
  mehr nur in einem Beschluss. Ab Werk und nach jedem Neustart ist der Schirm **zu**. Frei geben nur der Entwickler
  (Workbench am PC) und der Lead auf sein Wort (`amw schirm frei --grund … [--bis 07:00]`, auch über die Brücke). Zu
  machen darf jeder, der Entwickler auch vom Handy.
- **Geht von selbst zu, sobald der Entwickler wieder da ist:** Eingabe an diesem PC (ab 2 Minuten nach dem Freigeben,
  auch über eine Fernsitzung), eine neue Fernsitzung, er schreibt in der Workbench (seit 1.9.1 nur noch am PC) oder (bis
  1.9.0) ein Wortlaut mit seiner Zeit kommt, oder die gewählte Uhrzeit ist erreicht. Der Grund steht dabei, z. B. „Eingabe am PC (06:02)“.
- **Lauf-Schlange hält sich daran:** `amw lauf start --schirm` startet nur bei freiem Schirm und ruhigem PC, sonst
  Fehler mit Grund bzw. mit `--warten` eingereiht. Ein wartender Schirm-Lauf hält Läufe ohne Fenster nicht auf. Geht der
  Schirm zu, bekommt ein laufender Schirm-Lauf eine weckende Bitte, sofort zu beenden (die AMW beendet keine Prozesse);
  läuft er 5 Minuten später noch, erfährt es der Lead. Wer eingereihte Schirm-Läufe hat, erfährt, dass sie warten.
- **Neu: `amw lauf warte <nr>`** blockiert, bis der Lauf dran ist (rc 0 = jetzt rechnen, 2 = abgebrochen, 3 =
  `--hoechstens` erreicht) und schreibt jede Minute den Grund. **`amw lauf zeige <nr>`** zeigt Platz und Grund. Die
  Hilfe zu `--warten` sagt jetzt deutlich: nur einreihen, noch nicht rechnen.
- **Workbench:** Anzeige „Schirm frei/zu“ in der Kopfzeile, auf der Startseite ein Band, solange der Schirm frei ist
  oder Läufe mit Fenster warten, und ein Dialog zum Freigeben (Grund, „spätestens zu um“) bzw. Zumachen. Der
  Pflichtkontext der Agenten nennt den Zustand.
- Schema 11 (Tabelle `schirm`, eine Zeile je Wechsel, wird nie gelöscht).

## 1.6.3 – 03.11.2026
- **Keine Push-Meldungen mehr aus den Tests:** Zwei Tests ließen eine Runde des Dienstes auf einer leeren Test-Datenbank
  laufen und benutzten dabei die echten Push-Einstellungen des PCs. Jeder Testlauf schickte so einen „Rückblick“ voller
  Nullen aufs Handy. Die Tests haben jetzt eigene, leere Einstellungen; kein Test liest mehr die echte `push.json`.
- **Täglicher Rückblick nur, wenn etwas passiert ist:** Waren alle Zahlen der letzten 24 Stunden 0, kommt keine Meldung.

## 1.6.2 – 03.11.2026
- **Probe-Knopf der Benachrichtigungen meldet sich:** Das Ergebnis steht jetzt direkt unter dem Knopf (und als Meldung
  unten), nicht mehr am Ende der Karte außer Sicht. Ungespeicherte Änderungen (z. B. ein neu eingetragener ntfy-Kanal)
  werden vor der Probe gespeichert – die Probe geht also an das, was in den Feldern steht.
- **Nach einem Neustart der Workbench:** Eine vorher geöffnete Seite bekam bei jedem Speichern und Klicken nur „nicht
  erlaubt“. Jetzt erscheint oben ein klarer Hinweis mit Knopf *Neu laden*.

## 1.6.1 – 03.11.2026
- **Tab-Titel bleibt die Kennung:** Beim Start aus der Workbench und im Skript von `amw agent startskript` öffnet jeder
  Agent seinen Tab mit `--suppressApplicationTitle`. Claude Code überschreibt den Titel dann nicht mehr, der Tab heißt
  weiter CC1, CC2 …

## 1.6.0 – 03.11.2026 · Fragen parken
- **Parken statt „GEPARKT“ im Text:** Fragen lassen sich parken wie Aufgaben – raus aus der offenen Liste, aus den
  Zählern und aus den Push-Erinnerungen, aber nicht verloren. Die Fragen-Seite hat dafür die Reiter *Offen* und *Geparkt*
  (statt „geparkte zeigen“), jede Karte *Parken* bzw. *Wieder aufnehmen*; das geht auch online.
- **Kommandozeile und TL-Brücke:** `amw frage parken <nr> [--grund …]`, `amw frage aufnehmen <nr>`,
  `amw frage liste --geparkt`; `frage verlauf` zeigt, seit wann eine Frage geparkt ist.
- Mit Zeit und Person (Schema 10: `frage.geparkt_utc`, `geparkt_von`), im Verlauf der Frage vermerkt; der Fragesteller
  bekommt eine Info. Offene Fragen, die bisher mit „GEPARKT …“ im Text abgelegt waren, sind beim Umstellen geparkt.
- Online: eine leere Eingabe aus dem Netz (PHP schreibt `[]`) wird nicht mehr als ungültig abgewiesen.

## 1.5.1 – 03.11.2026 · Optionen einer Frage wieder lesbar
- Stand bei einer Option der ganze Satz in der Kennung (`--option "V0: …"` statt `"V0=…"`), wurde er in der schmalen
  Kennungs-Spalte Wort für Wort untereinander gezeigt. Die Seite trennt die kurze Kennung jetzt ab und zeigt den Text
  normal, auch bei „Warum …“.
- `amw frage neu` versteht `--option "V0: Text"` wie `"V0=Text"` und lehnt eine Option ohne kurze Kennung oder ohne Text
  mit einer klaren Meldung ab.

## 1.5.0 – 02.11.2026 · Gespräch je Agent und „In Claude öffnen“
- **Gespräch mitlesen:** Kachel › *Gespräch* (oder der Reiter in der Übersicht) zeigt das Gespräch des Agenten mit Claude
  Code – live, ohne sein Fenster zu suchen. Du rechts, Claude links (mit Markdown), Weckrufe und Hinweise klein dazwischen.
  Arbeitsschritte sind je Strecke eingeklappt und zeigen aufgeklappt Eingabe und Ergebnis (Fehler rot). Ältere Einträge
  lädst du nach, frühere Sitzungen wählst du oben. Auch Verläufe über 100 MB öffnen sich sofort, gelesen wird nur das Ende.
- **In Claude öffnen:** Läuft der Agent mit Fernsteuerung, öffnet ein Knopf seine Sitzung auf claude.ai bzw. in der
  Claude-App – dort schreibst du direkt mit ihm.
- **Online nur auf Wunsch:** Das Gespräch geht erst hoch, wenn du es online öffnest, und nur 10 Minuten lang. Dabei gehen
  nur Texte und die Namen der Arbeitsschritte hoch, Geheimnis-Muster sind immer verdeckt.
- Am Handy ist der Kopf der Agenten-Übersicht kompakter.

## 1.4.1 – 02.11.2026 · Brücke: ein fehlerhafter Befehl hält nichts mehr an
- Ein Befehl, der mit einem unerwarteten Fehler endet (z. B. leeres Pflichtfeld in der Datenbank), wird zum Ergebnis mit
  rc 1 und Fehlertext in `erledigt/`; die Befehle dahinter laufen weiter. Vorher blieb die Brücke an so einer Datei
  stehen, und auch die Lesekopie wurde nicht mehr erneuert.
- Befehle über die Brücke warten nie auf eine Eingabe (stdin ist leer, Nachfragen enden sofort mit Fehler).
- `frage neu` ohne `--kurz` oder `--an` bricht mit einer klaren Meldung ab.
- Meldungen von Brücke und Abgleich stehen jetzt auch im Dienst-Log.

## 1.4.0 – 02.11.2026 · Dokumente: bearbeiten, vergleichen, hochladen, einsammeln (Stufe D3)
- **Bearbeiten im Browser** (Markdown/Text, am PC und online): Editor mit Vorschau und Notiz, speichert eine neue Version
  und benachrichtigt den Verfasser. Hat ein Agent inzwischen eine neuere Version abgelegt, wird nichts überschrieben – der
  Text bleibt im Editor, ein Vergleich zeigt die Unterschiede. Ältere Fassungen lassen sich als neue Version zurückholen.
- **Versionen vergleichen:** Texte Zeile für Zeile mit hervorgehobenen Wörtern, Bilder/Mockups/PDF nebeneinander.
- **Hochladen** am PC (wählen, hineinziehen, Bildschirmfoto mit Strg+V) und vom Handy (Foto aufnehmen). Fotos werden im
  Browser verkleinert, Standort und Kameradaten entfernt. Upload in Teilen mit Prüfsumme; online liegt die Datei gleich
  auf dem Webspace und läuft nicht doppelt. An jeder Frage: *Datei/Foto anhängen*.
- **Varianten in Fragen:** `amw frage neu … --anhang A=bild.png --anhang B=D12` – je Option ein Bild oder Mockup, in der
  Frage als Karten zum Großansehen, auch online.
- **Einsammeln:** `amw dokument einsammeln <ordner>` listet je Ablage mit Vorschlag (behalten/weg, Grund, Art, Bezug);
  `--melden` fragt den Entwickler, `--uebernehmen --frage N` übernimmt erst nach der Antwort und nur unveränderte Dateien.
- Datei-Brücke: Dateien für `--anhang` und Positionsangaben bei `dokument ablegen/version` nur aus `eingang-tl/`.
- Behoben: Fragen ohne Anhang zeigten das Wort „null“.

## 1.3.0 – 02.11.2026 · Dokumente online (Stufe D2)
- **Dokumente auf der Online-Seite**: Liste mit Filtern und Suche (auch im Text), Details, Versionen, Gespräch und alle
  Texte. Kommentieren, überarbeiten lassen, zuordnen und archivieren gehen über den Briefkasten. Bogen-Karte, Schritt (📎),
  Anhänge an Fragen und Verlauf verlinken online jetzt auch auf Dokumente.
- **Dateien nur bei Bedarf online**: Bilder, Mockups, PDF und Office liegen online nur, wenn das Dokument auf „auch online“
  steht. Unterwegs: *Online anfordern* oder *Alle Dateien von A… anfordern*. Der PC reicht die Datei über den
  Online-Speicher durch, die Seite legt sie einmal auf dem Webspace ab (außerhalb des Deploy-Ordners) und liefert sie
  nach der Anmeldung mit Browser-Cache aus. *Nur am PC* nimmt sie dort wieder weg. Beim Hoster ist nichts einzurichten.
- Vollbild online wie am PC (blättert durch die Bilder, die online liegen).
- Texte zeigen keinen irreführenden Hinweis „Datei nur am PC“ mehr – sie sind immer auch online.
- Der Abgleich holt die Gespräche aller Dokumente in einer Abfrage.

## 1.2.1 – 02.11.2026 · Übersicht als echte Zeitachse · Bilder im Vollbild
- **Übersicht über der Zeitleiste neu**: echte Zeitachse über die volle Breite, ein Block je Bogen mit Namen. Bögen,
  die sich zeitlich nicht überschneiden, teilen sich eine Spur, statt dass jeder Bogen eine eigene Zeile bekommt.
  Puffer bis zum Zieldatum gestrichelt. Der Zeitraum geht wahlweise bis zum Ende der Prognose oder bis zum letzten
  Zieldatum. Bögen ohne Prognose stehen als Liste darunter. Die Achse überlappt nicht mehr: Monate, bei wenig Platz
  jeder zweite oder Quartale, das Jahr darunter.
- **Bilder im Vollbild** (Dokumente): bildschirmfüllend, Zoom mit Mausrad, zwei Fingern, `+`/`−` oder Doppelklick,
  Ziehen verschiebt, ←/→ blättert durch die Bilder derselben Aufgabe oder desselben Bogens. Mockups und PDF lassen
  sich ebenfalls ins Vollbild schalten.

## 1.2.0 – 02.11.2026 · Dokumente (Stufe D1)
- **Dokumente**: Agenten legen Ergebnisse in der AMW ab statt lose als Datei – `amw dokument ablegen <datei> --titel …
  --art ergebnis|bericht|entwurf|mockup|bild|quelle --aufgabe|--bogen|--frage|--beschluss <nr>`, neue Fassung mit
  `amw dokument version`. Standard: Text als Markdown, Bilder, Mockup als eine HTML-Datei, PDF/Office von außen.
  Steht im Pflicht-Kontext jedes Agenten.
- **Workbench › Dokumente**: Raster mit Vorschaubildern oder Liste, Suche in Titel und Text (auch ältere Versionen,
  DOCX), Filter; Detail mit Vorschau (Markdown gerendert, Bild, klickbares Mockup, PDF), Versionen, Gespräch;
  Kommentieren, Überarbeiten lassen (weckt den Verfasser), Zuordnen, Archivieren, endgültig Löschen (nur am PC).
- Dokumente an Bogen-Karten, Schritten (📎) und als Anhang an Fragen (mit Vorschaubild), im Verlauf und in der Suche.
- Schutz: feste Formatliste, 25 MB, Abweisen bei Schlüssel-Mustern; Mockups/SVG abgeschottet (CSP sandbox).
- `amw sichern` nimmt die Dokumenten-Ablage mit. Schema 9 (`dokument`, `dokument_version`, `nachricht.dokument_id`).
- Handy: kürzere Beschriftung „Arbeit“ in der unteren Leiste.
- Planung: fertige und verworfene Schritte zeigen „Fertig“/„Verworfen“ statt eines Platzhalters.

## 1.1.0 – 02.11.2026 · Plan-Check, der erklärt · Übersicht über der Zeitleiste
- **Plan-Check neu**: je Befund *Bedeutung*, *Abhilfe* (mit Befehl) und *wer* handelt, gruppiert nach Projekt, Bogen
  und Risiken, Zähler je Stufe und eine kurze Erklärung der Stufen. Gleichartiges ist zusammengefasst (z. B. alle
  Anforderungen eines Bogens ohne Schritt in einem Befund).
- **Einlenken**: je Befund öffnen (Bogen, Anforderungen, Leitbild, Risiko, Schritt in der Zeitleiste), *An TL geben*
  (Auftrag an den Lead) oder Warnungen/Hinweise mit Grund **bewusst akzeptieren** – sie zählen dann nicht mehr und
  lassen sich wieder prüfen; auch an der Kommandozeile (`amw plan akzeptieren|wieder`) und online.
- **Übersicht über der Zeitleiste**: ein Balken je Bogen vom Start bis zur Prognose (P50 fest, bis P85 schraffiert),
  Zieldatum, deine Schritte, Heute-Linie, Gesamtstart und voraussichtliches Ende; Klick springt zum Bogen.
- Prognose liefert je Bogen auch den voraussichtlichen Start.
- `amw aufgabe aendern`: `--ohne-vorgaenger` löst Abhängigkeiten, `--zusammenfassung` lässt sich nachtragen.

## 1.0.3 – 02.11.2026 · Planung über die Brücke
- **Datei-Brücke kann planen**: `leitbild`, `bogen`, `spec`, `schritt`, `risiko`, `plan`, `rueckblick`, `verlauf`
  (bisher abgewiesen). Bei `spec`/`rueckblick` ist `"bogen"` (und `"teil"`) die Positionsangabe; `--datei` nur aus
  `eingang-tl/`. Freigaben gibt weiterhin nur der Mensch.
- **Verlauf**: bei „erledigt“ steht, wer abgeschlossen hat (z. B. der Lead für einen Agenten), nicht nur der Bearbeiter.
- `aufgabe neu|aendern`: `--pruefer` ging verloren, sobald Planungsangaben dabei waren; `--abhaengig-von` ist jetzt
  derselbe Schalter wie `--nach` (echte Vorgänger statt eines Textfelds).

## 1.0.2 – 02.11.2026 · Korrektur
- `amw einrichten agenten-ordner` auf einen schon eingerichteten Ordner ergänzt die Git-Ausnahme jetzt wirklich
  (1.0.1 versprach das, brach aber bei „nichts zu tun“ vorher ab).

## 1.0.1 – 02.11.2026 · Korrekturen
- „Seit du weg warst“ online: die Ansicht änderte sich jede Sekunde und wurde bei jedem Abgleich neu hochgeladen –
  die Zeitgrenze steht jetzt auf der vollen Stunde. Ein Test prüft, dass sich keine Ansicht von selbst ändert.
- `amw einrichten agenten-ordner`: auch die Sicherung `settings.local.json.vor-amw-*` wird im Git des Projekts lokal
  ausgenommen (bisher nur die Einstellungsdatei selbst); bestehende Einrichtungen ergänzt ein erneuter Aufruf.

## 1.0.0 – 02.11.2026 · Für jeden Anwender
AMW ist ohne Begleitung einsetzbar: aus dem Repo installieren, einrichten, betreiben.
- **`amw einrichten`**: geführte Einrichtung – Datenbank, Projekt, Lead und Agenten mit Profil, Hooks und
  Statusline-Brücke im Projektordner, Startskript, Wächter als geplante Aufgabe. Wiederholbar; ohne Fragen:
  `amw einrichten schnell --projekt-name … --agenten CC1,CC2 --ordner … [--mit-dienst]`.
- **`amw sichern`**: vollständige Kopie der Datenbank im laufenden Betrieb (`--ziel` Datei oder Ordner).
- **Neue Dokumentation**: Überblick, Installation (Schritt für Schritt, Aktualisieren, Entfernen), Betrieb,
  Architektur, Online, Sicherheit, Fehlerbehebung; **Befehlsreferenz** `doc/befehle.md` aus der Kommandozeile erzeugt
  (`amw befehle`), Tests prüfen, dass sie aktuell ist und alle Verweise stimmen.
- Repo neutral: projektbezogene Planungs- und Umzugsdokumente sind nicht mehr Teil des Repos.
- **Beenden nur durch den Menschen**: andere Agenten beendet nur der Entwickler in der Workbench am PC; an der
  Kommandozeile beendet ein Agent nur seine eigene Sitzung; über die Datei-Brücke kein Starten, Beenden oder Profil.
- **`amw` in jeder Shell**: Starter `bin/amw` (Git Bash – dort führt Claude Code unter Windows Befehle aus) und
  `bin/amw.cmd` (PowerShell, cmd); `<AMW-Ordner>\bin` in den Pfad. Der Pflicht-Kontext nennt jedem Agenten den genauen
  Befehl und eine Kurzanleitung (lesen → erledigt, posten, nächster Schritt, fertig melden, Frage an den Menschen).
- **Probe mit einem frischen Agenten** nach der Anleitung; behoben: wiederholtes `amw einrichten` überschrieb geänderte
  Profile (jetzt nur leere Felder); der Lead bekommt ein Profil und steht im Startskript; Eingaben werden vor dem Anlegen
  geprüft; `aufgabe neu --nach` mit unbekanntem Vorgänger legte die Aufgabe trotzdem an; `amw sichern --ziel <Ordner>`
  legt den Ordner an; Hinweise ohne festen Pfad; Bogen-Fortschritt ohne verworfene Schritte; Profil ansehen darf jeder.
- `amw dienst vordergrund` (Wächter zum Ausprobieren ohne geplante Aufgabe); `amw dienst status` zeigt, wenn die Aufgabe
  „AMW Dienst“ zu einer anderen Installation gehört – `neustart`/`entfernen` greifen dann nicht ein; Umlaute in der
  Ausgabe von Windows PowerShell korrekt.
- `amw einrichten agenten-ordner <pfad> --entfernen` nimmt Hooks, Statusline-Brücke und Sperr-Regeln wieder heraus;
  beim Einrichten wird `settings.local.json` im Git des Projekts lokal ausgenommen.
- Vorgaben für neue Installationen: Remote Control für neue Agenten aus (im Assistenten wählbar), Datei-Brücke aus
  (`bruecke_an`).
- Online: „Seit du weg warst“ auch auf der Online-Seite (je Gerät gezählt); Verlauf zeigt online den gewählten Zeitraum.

## 0.14.1 – 02.11.2026 · Korrektur Verlauf
- Verlauf „1 Tag“ beginnt um lokale Mitternacht (war UTC-Mitternacht des lokalen Datums – kurz nach Mitternacht stand
  der Beginn in der Zukunft und der Verlauf war leer).

## 0.14.0 – 02.11.2026 · Rückblick und Verlauf
- **Rückblick je Bogen** (gut · schlecht · ändern wir · gelernt): am Bogen „Rückblick (n)“, nach dem Abschluss
  hervorgehoben; eine Maßnahme wird mit einem Klick zur Aufgabe oder (Lead/Entwickler) zum Beschluss „Lessons Learned“.
  `amw rueckblick <bogen> --gut … --schlecht … --massnahme … --gelernt …`, `--uebernehmen <nr> --als aufgabe|beschluss`.
- **Verlauf**: neue Ansicht – alles, was passiert ist (Nachrichten, Erledigtes, Läufe, Prüfungen, Fragen, Beschlüsse,
  Planung, Sitzungen), je Tag gruppiert, filterbar nach Zeitraum, Agent und Art; auch online. `amw verlauf [--stunden 24]
  [--agent X] [--art …] [--zusammenfassung]`.
- **„Seit du weg warst“** auf der Startseite: Zahlen seit dem letzten Besuch (je Gerät) mit Höhepunkten und Link in den
  Verlauf; täglicher **Rückblick als Push** zur gewählten Uhrzeit (Vorgabe 08:00, nur Zahlen).
- Test prüft das Skript der Seite mit node (ein Syntaxfehler machte die Seite leer – fällt jetzt vor dem Release auf).
- Datenbank-Schema 8 (`rueckblick`).

## 0.13.0 – 02.11.2026 · Projektplanung
Neue Ansicht **Planung** und Befehle für TL und Agenten (Anleitung: `doc/anleitung-planung.md`, Methode:
`doc/recherche/planung.md`).
- **Leitbild**: Ziel, Kennzahlen, Nicht-Ziele, Prinzipien mit Prüffrage, Definition of Done – im Pflicht-Kontext der Agenten.
- **Bögen** (Meilensteine) mit prüfbarem Abnahmekriterium, Zieldatum und Baseline (Verschiebung nur mit Grund).
- **Spezifikation** je Bogen in drei Teilen (Anforderungen mit IDs, Entwurf, Schritte), nacheinander vorgelegt und vom
  Menschen freigegeben oder mit Kommentar zurückgegeben – auch online; `[KLÄREN: …]` wird automatisch eine Frage und
  blockiert die Freigabe.
- **Schritte**: Aufgaben mit Bogen, Abnahmekriterien (abhakbar), Abhängigkeiten (Kreise abgewiesen; alte Textangaben
  übernommen), Schätzung, Komplexität, Prüfbefehl, Dateibereich, Anforderungen; Plan-Freigabe ab Komplexität 7;
  „fertig“ nur mit erfüllten Kriterien und Zusammenfassung. `amw schritt naechster [--nehmen]` vergibt den nächsten
  bereiten Schritt atomar. Aufgaben ohne Bogen bleiben wie bisher.
- **Prognose** (Monte Carlo aus dem Tempo je Bearbeiter, P50/P85), Ampel je Bogen, Status je Dimension (Termin, Risiko,
  Qualität), **Plan-Check** (Lückenprüfung), **Risiken** mit Matrix 5 × 5, Planungs-Protokoll.
- Senkrechte **Zeitleiste** mit Heute-Linie, Zieldatum/Baseline/Prognose, Spezifikations-Chips und Schritten in Wellen
  (was parallel geht); Schritte des Menschen hervorgehoben. Freigaben unter „Wartet auf dich“ und als Push.
- Befehle: `amw leitbild`, `amw bogen`, `amw spec`, `amw schritt`, `amw risiko`, `amw plan pruefen|prognose|status`,
  `amw aufgabe neu|aendern … --bogen --kriterium --nach …`, `amw aufgabe kriterium|plan|planfrei`.
- Datenbank-Schema 7 (`bogen`, `spezifikation`, `abhaengigkeit`, `risiko`, `plan_ereignis`, Planungsfelder in `aufgabe`).

## 0.12.0 – 02.11.2026 · Agenten starten, beenden, nach Absturz fortsetzen
- **Profil je Agent** (Zahnrad › Agenten › Profil oder `amw agent profil <kennung> --ordner … --zusatz "A;B" --denkstufe high
  --modell … --rechte vorgabe|auto|umgehen --startsatz "…" [--neustart]`): woraus AMW den Startbefehl baut.
- **Starten / Fortsetzen / Neu beginnen / Beenden** in der Agenten-Übersicht (nur am PC, mit Rückfrage) und per
  `amw agent starten|beenden <kennung> [--neu]`: neuer Windows-Terminal-Tab (sonst Konsolenfenster), setzt die letzte
  Sitzung fort (`--resume`) oder beginnt eine neue mit eigener Sitzungs-ID; Beenden trifft nur den Claude-Prozess.
- **Nach Absturz fortsetzen** (im Profil einschaltbar): der Wächter setzt einen Agenten automatisch fort, wenn Claude
  abgestürzt ist und sein Fenster noch offen ist – nie nach bewusstem Ende (Fenster geschlossen, `/exit`, Beenden in
  AMW); höchstens 3-mal je Stunde, mit Meldung an den Lead. Dafür merkt sich die Anmeldung Prozess- und Fenster-PID.
- `amw agent startskript [--datei x.ps1]`: Startskript für alle Agenten mit Soll „an“, erzeugt aus den Profilen.
- PC-Einstellung `claude_befehl` (falls Claude Code nicht als `claude` im Pfad liegt). Profile und Starten nie über
  die Online-Seite (Ordner und Startsatz landen in einem Befehl auf dem PC).
- Datenbank-Schema 6 (Profil in `agent`, `sitzung.claude_pid/fenster_pid`).

## 0.11.0 – 02.11.2026 · Push aufs Handy, Zustand und Verbrauch je Agent
- **Benachrichtigungen aufs Handy** über ntfy, Pushover oder Telegram (einzeln an/aus, mehrere gleichzeitig): neue
  Frage an dich (Erinnerung nach 60 min), Nachricht an dich, Warnungen, Agent wartet auf Freigabe/Eingabe (ab 5 min),
  Halt. Nur Hinweise + Link, nie Inhalte. Gebündelt („3 neue Fragen“), höchstens 10 je Stunde, Ruhezeit (nur
  Dringendes, der Rest danach gesammelt), Wiederholung nur bei vorübergehenden Fehlern, Versandprotokoll.
  Zugangsdaten nur in `%LOCALAPPDATA%\amw\push.json`. Zahnrad-Abschnitt mit Probe je Anbieter; `amw push …`;
  Anleitung `doc/anleitung-push.md`.
- **Zustand je Agent aus Claude-Code-Hooks:** arbeitet · frei · wartet auf Freigabe · wartet auf Eingabe · Fehler
  (z. B. rate_limit). Warnung, wenn ein Agent ≥ 2 min an einer Berechtigungsabfrage hängt oder mit Fehler abbricht.
- **Kontext, Nutzungsgrenzen, Kosten je Agent** über eine Statusline-Brücke (`amw-statusline.py`), die die bisherige
  Statusline weiterreicht: Balken auf der Kachel, Zustand in der Übersicht, Warnung bei Kontext ≥ 90 % und
  5-Stunden-Grenze ≥ 90 %; Betrieb zeigt den Verbrauch je Agent und Tag (Schätzung zum Listenpreis).
- `amw einrichten agenten-ordner <pfad>`: führt Hooks, Statusline-Brücke und Sperr-Regeln in einen Agenten-Ordner
  zusammen (nichts wird überschrieben, Sicherung vorher, zweimal ausgeführt = nichts).
- Einstellungen mit Sprungmarken; am Handy passen alle Karten in die Breite. Betrieb: Verbrauch oben, Sitzungen
  gekürzt (laufende + letzte 8). Kachel-Zustand in einer Zeile.
- Test: eine umgestellte alte Datenbank muss Spalte für Spalte der frisch angelegten gleichen.
- Datenbank-Schema 5 (Sitzungs-Zustand, `verbrauch`, `push_versand`).

## 0.10.0 – 01.11.2026 · Überwachung und bessere Bedienung
- **Projekt-Server überwachen:** `amw server anmelden <name> --port N [--start "Befehl" --ordner Pfad --neustart
  --zustaendig X]`. Der Wächter prüft jede Runde, ob der Port antwortet, meldet Ausfall und Wiederkehr dem Zuständigen
  und den Leads und startet auf Wunsch neu (erst nach zwei Runden „aus“, höchstens 3 Neustarts je Stunde, Ausgabe in
  `daten/server-<name>.log`). `amw server liste|pruefen|abmelden`; Betrieb zeigt die Server.
- **Stillstand erkennen:** Warnung, wenn ein Agent mit laufender Sitzung auf einen Weckruf nicht reagiert (Vorgabe
  30 min, seitdem keine Meldung) oder ein Lauf länger dauert als erwartet (`amw lauf start --dauer N` → Warnung nach
  2 × N, sonst nach 90 min). Warnband auf der Startseite, je Warnung eine Meldung an den Lead; Schwellen im Zahnrad.
- **Startseite** nach Dringlichkeit: Warnungen → Fragen an dich (mit „neuer Nachtrag“) → Agenten (erst die, die laufen
  sollen) → Nachrichten (Text gekürzt, Klick zeigt alles). Nachträge zu offenen Fragen stehen nur noch in der Frage und
  gelten mit der Antwort als erledigt.
- **Aufgaben:** „Läuft“ zeigt, woran Agenten mit laufender Sitzung gerade arbeiten („jetzt: CC1“); jede Karte zeigt,
  wann sie zuletzt geändert wurde.
- **Wissen:** neuer Reiter „Notizen“.
- Kopfzeile: „7/7 Agenten · 2 außerplanmäßig“ statt „9/7“.
- Handy: Agenten-Übersicht einspaltig, Nummern brechen nicht mehr um, Menüpunkt „Setup“ statt abgeschnittenem Text.
- Zurück-Knopf des Browsers und Links mit `#ansicht` wechseln die Ansicht.
- Korrektur: Die Workbench konnte unter Windows still einen schon belegten Port mitbenutzen (dann sah man im Browser
  ein fremdes Programm). Jetzt exklusiv; ist der Port belegt, steht es im Protokoll.
- Datenbank-Schema 4 (Tabelle `server`, `lauf.erwartet_min`).

## 0.9.2 – 01.11.2026 · Anmelden auch nach Resume von Hand
- Nach einem Neustart per Resume ohne Startskript fehlte `AMW_AGENT`; der Start-Hook meldete niemanden an, Weckrufe
  kamen nicht an. Jetzt erkennt der Hook die Kennung an der Sitzungs-ID (ein Resume behält
  sie) und meldet automatisch an. Im Fenster steht sichtbar „AMW: als CC1 angemeldet“.
- Unbekannte Sitzung in einem Agenten-Ordner: deutliche Meldung im Fenster mit dem Befehl zum Anmelden.
- Workbench (Start) und `amw dienst status` warnen bei laufenden Agenten-Sitzungen, die nicht angemeldet sind.

## 0.9.1 – 01.11.2026 · Keine falschen Anmeldungen mehr
- Eine Hintergrund-Sitzung ohne Fenster konnte sich als Agent anmelden; Weckrufe gingen dann dorthin statt
  ins Fenster. Jetzt: Hintergrund-Sitzungen (Claude Code `kind=bg`) werden nie angemeldet, und
  `amw anmelden` löst eine noch lebende andere Sitzung derselben Kennung nur mit `--ersetzen` ab. Erkannt über
  `~/.claude/sessions/<pid>.json` (Postfach → Prozess).
- `amw dienst status` zeigt je Agent: Sitzung, Prozess, mit Fenster oder Hintergrund („← PRÜFEN“).

## 0.9.0 – 01.11.2026 · Warteschlange für Rechen-Läufe
- `amw lauf start … --warten`: Ist der Platz belegt (ein schwerer Lauf, ein Schirm-Lauf zur Zeit) oder der Speicher
  knapp, wird der Lauf eingereiht statt abgelehnt. Sobald er dran ist, startet der Wächter ihn und weckt den Agenten mit
  einer Freigabe „Lx ist dran“. Niemand überholt: Wer ohne `--warten` startet, während jemand für denselben Platz
  wartet, wird abgelehnt (vorher kam ein langsamerer Agent mehrmals nicht dran).
- `amw lauf vorziehen <nr>` (Lead/Entwickler, auch über die Brücke), `amw lauf liste` zeigt die Schlange,
  `amw lauf ende <nr> --abgebrochen` nimmt einen Lauf aus der Schlange oder gibt einen reservierten Platz frei.
  Agenten ohne laufende Sitzung werden übersprungen, bis sie wieder da sind.
- Agenten-Kachel: „offen“ zählt nur, was eine Handlung braucht (weckende Arten); reine Info zählt nicht mehr
  Die Übersicht zeigt weiter alles.
- Korrektur: offene Prüfbitten erschienen in der Agenten-Übersicht nie.
- Datenbank-Schema 3 (`lauf.rang`, `amw/migration_3.sql`).

## 0.8.0 – 01.11.2026 · Gesprächsverlauf je Frage
- Jede Frage hat einen Verlauf wie im Chat (Fragesteller links, du rechts): Rückfragen, Antworten des Fragestellers,
  deine Antwort – nichts wird mehr überschrieben. Online erscheint eine Rückfrage sofort als „unterwegs“.
- `amw frage nachtrag <nr> --text …` (Fragesteller oder Lead) und `amw frage verlauf <nr>`; eine Nachricht mit
  `--antwort-auf <Rückfrage-Nachricht>` wird automatisch als Nachtrag erkannt. Nachträge erscheinen auch unter
  „Nachrichten an dich“.
- Karte zeigt „wartet auf TL“, solange eine Rückfrage offen ist.
- Datenbank-Schema 2 (Tabelle `frage_verlauf`, gegen Löschen geschützt); ältere Datenbanken werden beim ersten
  Schreibzugriff umgestellt (`amw/migration_2.sql`), bisherige Rückfragen werden übernommen.

## 0.7.1 – 01.11.2026 · Übersicht lesbarer
- Agenten-Übersicht etwa zwei Drittel breit (vorher überschrieb die allgemeine Dialog-Breite von 520 px), zwei Spalten:
  links „Kommt noch“, Läufe, Prüfbitten – rechts neue Nachrichten, letzte Meldungen; auf dem Handy eine Spalte.
- Jeder Eintrag als eigener Block mit Kopfzeile (Nummer, Kennzeichen, Zeit) und farbigem Rand nach Status/Art;
  Anzahl je Abschnitt; Esc schließt.

## 0.7.0 – 01.11.2026 · Agenten auf einen Blick
- Agenten-Kachel: „Gerade“ (eigene Angabe › laufende Aufgabe › Aufgabe aus der letzten Meldung), „Zuletzt“ (letzte
  Meldung), offen zählt nur Neues seit dem Umzug, Altbestand aus dem alten Bus getrennt.
- Klick auf die Kachel: Übersicht – macht gerade, kommt noch (Aufgaben nach Rang), Rechen-Läufe, Prüfbitten,
  neue Nachrichten an ihn, seine letzten Meldungen; auch online.
- `amw taetigkeit "…" [--aufgabe N]`: Agenten sagen selbst, woran sie sind (auch über die Brücke).
- Start der Agenten: Startskript setzt `AMW_AGENT`, der SessionStart-Hook (`amw-hook.py`) meldet neue Sitzungen an.

## 0.6.0 – 01.11.2026 · Suche online
- Suche auf der Online-Seite: der PC lädt einen gepackten Suchindex hoch (Aufgaben, Beschlüsse, Fragen, Wortlaut
  vollständig, die letzten 2000 Nachrichten mit Kurztext; höchstens alle 15 min, nur bei Änderung).
- Doku: Fahrplan und Stufen auf den Stand gebracht (Stufe 1 und 2 in Betrieb).

## 0.5.0 – 01.11.2026 · Einstellungen
- Zahnrad „Einstellungen“ (lokal und online): Projekt (Takt, Speicher-Grenze), Agenten (anlegen, Rolle, Soll, Grenzen,
  Rundschreiben, Puls-Grenze), Online-Seite (Abmelden nach Leerlauf, längste Sitzung, Sperre nach Fehlversuchen).
- „Dieser PC“ (Datenbank-Pfad, Port, Takte von Wächter, Abgleich und Brücke) und „Online-Speicher“ (Adresse,
  Schlüssel, Abgleich) nur am PC änderbar, online nur sichtbar; der Schlüssel wird nie angezeigt.
  Gespeichert in `%LOCALAPPDATA%\amw\einstellungen.json`; `amw dienst neustart` übernimmt sie.
- Version unten links in der Workbench.
- `amw notiz entfernen <schlüssel …>` – nur Lead/Entwickler oder mit `--beschluss` auf einen geltenden Beschluss.
- Korrektur: Briefkasten-Einträge werden an Nummer, Zeit und Inhalt erkannt (eine neue Online-Datenbank zählt wieder ab 1);
  Einstellungen aus dem Briefkasten gehen in denselben Online-Speicher.

## 0.4.0 – 01.11.2026 · Online (Stufe 2)
- Workbench im Netz: PHP-Seite (Zweig `web`) über Turso – Schaufenster (Ansichten vom PC) + Briefkasten (Antworten,
  Nachrichten, Gelesen, Halt, Weiter); der PC bleibt aus dem Netz unerreichbar.
- Anmeldung mit Passwort + Einmalcode (TOTP, RFC 6238), QR-Code ohne fremde Bibliothek, Sperre nach Fehlversuchen.
- Einrichtungs-Assistent im Browser für jeden Anwender; `amw web einrichten` am PC. Die Seite speichert ihre
  Konfiguration selbst außerhalb des Deploy-Ordners.
- Nachrichten an den Entwickler (Empfänger `Entwickler`), in der Workbench „Nachrichten an dich“ mit Antworten/Gelesen.
- Datei-Brücke für Sitzungen ohne direkten Datenbankzugriff (z. B. ein Lead in einer VM): Lesekopie ohne WAL, Befehlsdateien, Puls.
- Workbench aktualisiert still: keine Einblend-Animation und kein Sprung nach oben beim Selbst-Aktualisieren.
- Versionierung: `amw --version`, Anzeige in der Workbench, CHANGELOG, Git-Tags.

## 0.3.0 – 01.11.2026 · Erster Einsatz im Team
- Bisheriger Nachrichten-Bus übernommen (alle Zählungen gleich), Wächter als geplante Aufgabe „AMW Dienst“.
- `amw anmelden` für laufende Sitzungen ohne Neustart, `amw-cli.py` ohne PYTHONPATH, `--von` auch hinter dem Befehl.
- Umzugs-Sperre im alten Bus (Rückweg: Schalter-Datei), Compact-Hook liefert den Kontext aus der AMW.
- Zeiten in Ortszeit.

## 0.2.0 – 01.11.2026 · Stufe 1 vollständig
- Kommandozeile für TL und Agenten vollständig (Läufe, Prüfungen, Anweisungen, Rezepte, Wortlaut, Beschlüsse, Regeln,
  Notizen, Release Notes).
- Workbench zweisprachig (DE/EN) und fürs Handy; Nachricht an Agenten; Takt für den Lead.
- Einrichtung des Wächters vorbereitet (`amw dienst`), Hook-Einstellungen (`amw hook zeige`).

## 0.1.0 – 01.11.2026 · Stufe 1 Kern
- Datenmodell (18 Tabellen), Datenzugriff, Fachlogik, CLI `amw`.
- Wächter: weckt Agenten über die Pipe ihrer Claude-Code-Sitzung; SessionStart-Hook mit Pflicht-Kontext.
- Übernahme aus einem bestehenden Bus (nur lesend); Workbench-Oberfläche (Leitstand).