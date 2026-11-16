# AMW mit Claude verbinden (MCP)

Ein Lead, der als Chat in der Claude-App arbeitet, kann die AMW direkt als Werkzeug aufrufen – ohne Dateiaustausch, schneller und mit weniger Text. Die AMW läuft dafür als kleiner MCP-Server auf diesem PC; die Claude-App startet ihn selbst.

## Du brauchst
- Die Claude-App für Windows auf diesem PC (der Server läuft lokal, nicht im Browser).
- Python auf diesem PC (dasselbe, mit dem die AMW läuft).
- Den Namen des Projekts und des Leads, z. B. Projekt `GlassWorld`, Lead `TL`.
- Je Projekt einen eigenen Schlüssel. Ohne ihn lehnt der Connector jeden Aufruf ab.

## Schritte
1. **Schlüssel erzeugen** In der Workbench am PC: Einstellungen › Projekt › „Connector für den Lead-Chat (MCP)“ › „Schlüssel erzeugen“. Der Schlüssel erscheint genau einmal – kopieren. Gespeichert wird auf diesem PC nur ein Prüfwert, nicht im Repository und nicht in der Datenbank. Im Terminal geht es auch: `amw mcp schluessel --projekt GlassWorld --von Entwickler` (nicht aus einer Agenten-Sitzung).
2. **Schlüssel in den Lead-Chat** In der Claude-App im Claude-Projekt des Leads die Projekt-Anweisungen öffnen und eine Zeile ergänzen, z. B. „AMW-Schlüssel: amw-…“. Nur dort – nie in einen anderen Chat, nie in eine Nachricht.
3. **Konfiguration öffnen** In der Claude-App: Einstellungen › Entwickler › „Konfiguration bearbeiten“. Es öffnet sich die Datei `claude_desktop_config.json`.
4. **Eintrag einfügen** Die fertige Zeile steht in der Workbench beim Schlüssel („Zeile kopieren“). Je Projekt ein Eintrag unter `mcpServers`, Name `amw-<projekt>`, der Pfad ist der Ordner der AMW: `"amw-glassworld": {"command": "python", "args": ["F:/amw/amw-mcp.py", "--projekt", "GlassWorld", "--von", "TL"]}`. Gibt es `mcpServers` noch nicht, die ganze Datei so: `{"mcpServers": { … }}` mit dem Eintrag an der Stelle der drei Punkte; steht dort schon etwas, den neuen Eintrag mit Komma dazuschreiben.
5. **Claude-App neu starten** Ganz beenden (auch im Infobereich der Taskleiste) und wieder öffnen.
6. **Im Chat einschalten** Im Chat des Leads unter „Suche und Werkzeuge“ den Eintrag `amw-…` seines Projekts einschalten – und nur diesen.
7. **Ausprobieren** Den Lead bitten: „Ruf takt auf.“ Er bekommt seinen Durchgang: Postfach, Prüfbitten, Fragen, Antworten, Läufe, Lead-Runde, Auslieferungen.

## Typische Fehler
- **Die Werkzeuge erscheinen nicht** – Die App wurde nicht ganz beendet, oder in der Datei fehlt ein Komma. Die App zeigt Fehler unter Einstellungen › Entwickler.
- **„Python nicht gefunden“** – Statt `python` den ganzen Pfad zu python.exe eintragen.
- **„Abgelehnt: Dieser Connector gehört zu Projekt …“** – Der Schlüssel fehlt in den Anweisungen des Chats, ist alt (nach „Schlüssel erneuern“) oder der Chat gehört zu einem anderen Projekt. Es wurde nichts gelesen und nichts geändert. Im fremden Chat den Eintrag ausschalten; im eigenen den aktuellen Schlüssel eintragen.
- **„Für Projekt … ist noch kein Schlüssel erzeugt“** – Schritt 1 fehlt.
- **Der Lead handelt im falschen Projekt** – Im Chat ist der Eintrag eines anderen Projekts eingeschaltet. Jeder Eintrag handelt fest als der Agent, der dort steht; im Chat nur den eigenen einschalten.

## Danach
- In der Claude-App ist jeder eingetragene Connector in jedem Chat wählbar. Was einen fremden Chat aufhält, ist allein der Schlüssel: Er steht nur in den Anweisungen des eigenen Lead-Chats.
- Der Schlüssel schützt, solange er nicht weitergegeben wird. Wer ihn hat, kann über diesen Eintrag alles, was der Lead kann. Gerät er in einen anderen Chat oder in eine Nachricht: sofort „Schlüssel erneuern“ – der alte gilt dann nicht mehr.
- Er schützt gegen fremde Chats, nicht gegen jemanden mit Zugriff auf diesen PC.
- Jeder Aufruf steht im Verlauf (Planung › Verlauf): Zeit, Werkzeug, Ergebnis, abgelehnt oder nicht – nie der Inhalt.
- **takt** – ein Durchgang in einem Aufruf (wie `amw takt`); **lesen**, **posten**, **erledigt** – Nachrichten.
- **aufgabe_liste / _zeige / _neu / _aendern**, **bogen_liste / _zeigen** – Aufgaben und Meilensteine.
- **pruefung_liste / _zeige / _urteil**, **freigabe_merge** – Prüfungen und Merge-OK.
- **frage_liste / _zeige / _neu / _antworten**, **beschluss_neu**, **wortlaut** – Fragen und Wissen.
- **runde_lesen / _schreiben** – Lead-Runde; **lauf_liste / _zeige / _vorziehen** – Läufe; **schirm** – Bildschirm-Freigabe.
- **suche**, **zeige** (B5 F12 A120 …), **dokument_zeigen** (mit Pfad der Datei, auf Wunsch mit Inhalt), **agent_liste**, **wortlaut_liste**, **kontext**.
- Jedes Werkzeug ruft denselben Befehl wie die Kommandozeile – mit denselben Rechten und Prüfungen.
- Der Dateiaustausch bleibt als Rückfall bestehen.
- Eintragen tut der Mensch: Die Datei gehört zur Claude-App, nicht zur AMW. Den Schlüssel erzeugt und verteilt nur der Mensch.
