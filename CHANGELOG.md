# Änderungen · Changelog

Versionen nach dem Schema MAJOR.MINOR.PATCH: MINOR für neue Fähigkeiten, PATCH für Korrekturen; 1.0.0, wenn die AMW
für andere Teams ohne Begleitung einsetzbar ist. Die Nummer steht in `amw/__init__.py`,
`amw --version` zeigt sie, die Workbench in der Kopfzeile. Zu jeder Version gibt es den Git-Tag `vX.Y.Z`.

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
