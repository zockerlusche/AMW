# Connect the AMW to Claude (MCP)

A lead who works as a chat in the Claude app can call the AMW directly as a tool – without the file exchange, faster and with less text. For this the AMW runs as a small MCP server on this PC; the Claude app starts it itself.

## You need
- The Claude app for Windows on this PC (the server runs locally, not in the browser).
- Python on this PC (the same one the AMW runs with).
- The name of the project and of the lead, e.g. project `GlassWorld`, lead `TL`.
- A key of its own per project. Without it the connector rejects every call.

## Steps
1. **Create the key** In the Workbench on the PC: Settings › Project › “Connector for the lead chat (MCP)” › “Create key”. The key is shown exactly once – copy it. Only a check value is stored on this PC, not in the repository and not in the database. In a terminal: `amw mcp schluessel --projekt GlassWorld --von Entwickler` (not from an agent session).
2. **Put the key into the lead chat** In the Claude app, open the project instructions of the lead's Claude project and add a line, e.g. “AMW key: amw-…”. Only there – never in another chat, never in a message.
3. **Open the configuration** In the Claude app: Settings › Developer › “Edit config”. This opens the file `claude_desktop_config.json`.
4. **Add an entry** The ready line is in the Workbench next to the key (“Copy line”). One entry per project under `mcpServers`, name `amw-<project>`, the path is the AMW folder: `"amw-glassworld": {"command": "python", "args": ["F:/amw/amw-mcp.py", "--projekt", "GlassWorld", "--von", "TL"]}`. If there is no `mcpServers` yet, the whole file is `{"mcpServers": { … }}` with the entry in place of the three dots; if there is something already, add the new entry with a comma.
5. **Restart the Claude app** Quit it completely (also from the notification area of the taskbar) and open it again.
6. **Switch it on in the chat** In the lead's chat, under “Search and tools”, switch on the `amw-…` entry of its project – and only that one.
7. **Try it** Ask the lead: “Call takt.” They get their check-in: inbox, review requests, questions, answers, runs, lead round, deliveries.

## Common problems
- **The tools do not appear** – The app was not quit completely, or a comma is missing in the file. The app shows errors under Settings › Developer.
- **“Python not found”** – Enter the full path to python.exe instead of `python`.
- **“Abgelehnt: Dieser Connector gehört zu Projekt …” (rejected)** – The key is missing from the chat's instructions, is old (after “Renew key”), or the chat belongs to another project. Nothing was read and nothing changed. Switch the entry off in the other chat; put the current key into your own.
- **“Für Projekt … ist noch kein Schlüssel erzeugt” (no key yet)** – Step 1 is missing.
- **The lead acts in the wrong project** – The entry of another project is switched on in the chat. Each entry always acts as the agent named in it; switch on only your own in the chat.

## Next
- In the Claude app every configured connector can be chosen in every chat. The only thing that stops another chat is the key: it is only in the instructions of your own lead chat.
- The key protects as long as it is not passed on. Whoever has it can do everything the lead can through this entry. If it gets into another chat or a message: “Renew key” at once – the old one stops working.
- It protects against other chats, not against someone with access to this PC.
- Every call is in the history (Planning › History): time, tool, result, rejected or not – never the content.
- **takt** – one check-in in one call (like `amw takt`); **lesen**, **posten**, **erledigt** – messages.
- **aufgabe_liste / _zeige / _neu / _aendern**, **bogen_liste / _zeigen** – tasks and milestones.
- **pruefung_liste / _zeige / _urteil**, **freigabe_merge** – reviews and merge OK.
- **frage_liste / _zeige / _neu / _antworten**, **beschluss_neu**, **wortlaut** – questions and knowledge.
- **runde_lesen / _schreiben** – lead round; **lauf_liste / _zeige / _vorziehen** – runs; **schirm** – screen release.
- **suche**, **zeige** (B5 F12 A120 …), **dokument_zeigen** (with the path of the file, optionally with the content), **agent_liste**, **wortlaut_liste**, **kontext**.
- Every tool calls the same command as the command line – with the same rights and checks.
- The file exchange stays as a fallback.
- The human adds the entry: the file belongs to the Claude app, not to the AMW. Only the human creates and hands out the key.
