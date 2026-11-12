# New project – step by step

A project stands on its own: its own agents, rules, tasks and documents. The only thing you create by hand is the project folder – AMW does the rest.

## You need
- Projects can only be created at the PC (Workbench on the computer running AMW). Here you can read the steps.

## Steps
1. **Create the project folder** In Explorer, e.g. F:\webshop. The agents work in it (usually the repository). A folder belongs to exactly one project.
2. **Open “+ New project”** Workbench at the PC › project switcher at the top of the navigation › “+ New project” (also under Settings › Project). ![Open “+ New project”](np-auswahl)
3. **Fill in and create** Name, project folder, lead (empty if you lead yourself), agents, permissions, rule set (the shipped base rule set – tick and adjust single rules –, a copy of another project, or none) and colour. “Create” sets up the folder (hooks, project id, amw command without confirmation), creates lead and agents with a profile and start prompt and writes a start script of its own. ![Fill in and create](np-dialog) ![Fill in and create](np-fertig)
4. **Before the first start: mission and first task** “Go to project” › Planning › Mission: goal, non-goals, principles. Then a first task (Work) or a milestone (Planning) – otherwise the agent finds nothing to do. Project knowledge (tech, build, style) goes into a CLAUDE.md in the project folder; AMW does not create one. ![Before the first start: mission and first task](np-leitbild)
5. **Start an agent** Home › agent tile › “Start”. A tab “CC1 · project name” opens. On the very first start in a new folder Claude Code asks once whether you trust the folder – confirm with “Yes, proceed” in the tab; nothing runs before that. Then the window says “AMW: als CC1 angemeldet”. ![Start an agent](np-start)
6. **First message** The agent reads rules and messages, fetches its work and reports. You see its messages on Home, in History and on its tile (Conversation). ![First message](np-nachricht)

## Questions
### How does the first agent know everything?
Start prompt – the first sentence of every new session, in the agent's profile (tile › Profile, editable there): who it is, how it calls AMW and what to start with (lead: plan and distribute, agent: fetch work). Start information – on every start, resume and compaction the start hook gives it: command and short guide, goal, non-goals and principles from the mission, active milestones, its task list, open messages and rules. Project knowledge – Claude Code reads your CLAUDE.md in the project folder by itself.

### Does a new project need MCP?
No. Agents work through the hooks and the amw command; “Create” sets up both in the project folder. Only a lead without direct access (e.g. in Cowork or a VM) uses the file exchange: Settings › This PC › file exchange on; commands in eingang-<project>\befehle in the AMW folder, read copy daten\lesen-<project>.db – the AMW folder must be connected in the desktop app.

### Do I have to copy the service?
No. One service per PC notifies the agents of each project separately. Do not create a second AMW installation.

### What do I create by hand?
Only the project folder (and, if you like, a CLAUDE.md in it). AMW creates project, agents, profiles, hooks and start script.

### Do I need a Git repository?
Not for AMW. Recommended for code: an agent closes tasks with evidence – a commit, file:line or a follow-up task.

### Where are the Claude Code sessions?
The agents work in the project folder. Claude Code keeps the history in your user folder under .claude\projects, per folder. In the Workbench: tile › Conversation.

### May the agents have the same names as in the other project?
Yes, CC1 may exist in every project. The tab is then called “CC1 · project name”; each session registers only in its own project.

### Move a project to another computer?
amw sichern --projekt <name> writes the project as a database of its own including documents (guide “Several projects” in the docs).
