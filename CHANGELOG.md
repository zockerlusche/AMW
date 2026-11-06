# Änderungen · Changelog

Versionen nach dem Schema MAJOR.MINOR.PATCH: MINOR für neue Fähigkeiten, PATCH für Korrekturen; 1.0.0, wenn die AMW
für andere Teams ohne Begleitung einsetzbar ist. Die Nummer steht in `amw/__init__.py`,
`amw --version` zeigt sie, die Workbench in der Kopfzeile. Zu jeder Version gibt es den Git-Tag `vX.Y.Z`.

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
