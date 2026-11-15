# AMW mit Claude verbinden (MCP)

Ein Lead, der als Chat in der Claude-App arbeitet, kann die AMW direkt als Werkzeug aufrufen – ohne Dateiaustausch, schneller und mit weniger Text. Die AMW läuft dafür als kleiner MCP-Server auf diesem PC; die Claude-App startet ihn selbst.

## Du brauchst
- Die Claude-App für Windows auf diesem PC (der Server läuft lokal, nicht im Browser).
- Python auf diesem PC (dasselbe, mit dem die AMW läuft).
- Den Namen des Projekts und des Leads, z. B. Projekt `GlassWorld`, Lead `TL`.

## Schritte
1. **Konfiguration öffnen** In der Claude-App: Einstellungen › Entwickler › „Konfiguration bearbeiten“. Es öffnet sich die Datei `claude_desktop_config.json`.
2. **Eintrag einfügen** Je Projekt ein Eintrag unter `mcpServers` – der Name ist frei, der Pfad ist der Ordner der AMW:
   ```json
   {
     "mcpServers": {
       "amw-glassworld": {
         "command": "python",
         "args": ["F:/amw/amw-mcp.py", "--projekt", "GlassWorld", "--von", "TL"]
       }
     }
   }
   ```
   Steht schon etwas unter `mcpServers`, nur den neuen Eintrag dazuschreiben (mit Komma).
3. **Claude-App neu starten** Ganz beenden (auch im Infobereich der Taskleiste) und wieder öffnen.
4. **Im Chat einschalten** Im Chat des Leads unter „Suche und Werkzeuge“ den Eintrag `amw-…` seines Projekts einschalten – und nur diesen.
5. **Ausprobieren** Den Lead bitten: „Ruf takt auf.“ Er bekommt seinen Durchgang: Postfach, Prüfbitten, Fragen, Antworten, Läufe, Lead-Runde, Auslieferungen.

## Typische Fehler
- **Die Werkzeuge erscheinen nicht** – Die App wurde nicht ganz beendet, oder in der Datei fehlt ein Komma. Die App zeigt Fehler unter Einstellungen › Entwickler.
- **„Python nicht gefunden“** – Statt `python` den ganzen Pfad zu python.exe eintragen.
- **Der Lead handelt im falschen Projekt** – Im Chat ist der Eintrag eines anderen Projekts eingeschaltet. Jeder Eintrag handelt fest als der Agent, der dort steht; im Chat nur den eigenen einschalten.

## Danach
- **takt** – ein Durchgang in einem Aufruf (wie `amw takt`); **lesen**, **posten**, **erledigt** – Nachrichten.
- **aufgabe_liste / _zeige / _neu / _aendern**, **bogen_liste / _zeigen** – Aufgaben und Meilensteine.
- **pruefung_liste / _zeige / _urteil**, **freigabe_merge** – Prüfungen und Merge-OK.
- **frage_liste / _zeige / _neu / _antworten**, **beschluss_neu**, **wortlaut** – Fragen und Wissen.
- **runde_lesen / _schreiben** – Lead-Runde; **lauf_liste / _zeige / _vorziehen** – Läufe; **schirm** – Bildschirm-Freigabe.
- **suche**, **zeige** (B5 F12 A120 …), **dokument_zeigen** (mit Pfad der Datei), **kontext**.
- Jedes Werkzeug ruft denselben Befehl wie die Kommandozeile – mit denselben Rechten und Prüfungen.
- Der Dateiaustausch bleibt als Rückfall bestehen.
- Eintragen tut der Mensch: Die Datei gehört zur Claude-App, nicht zur AMW.
