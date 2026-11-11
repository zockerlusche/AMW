# Agents: set up the folder, rename, start

An agent works in a folder on this PC. So that the AMW can notify it, monitor it and show its usage, the AMW sets up this folder once.

## You need
- The folder the agent works in (usually the project folder).
- The command line on the PC (`amw …`).

## Steps
1. **Set up the folder** Run `amw einrichten agenten-ordner <folder> --projekt <project>`. The AMW adds its entries to the Claude Code settings in this folder and backs up the file first. After that, the agent's “State and usage” appears.
2. **Check the profile** Settings › Agents shows folder, model, effort, permissions and first prompt. Change them there or with `amw agent profil <name> --ordner … --modell …`.
3. **Start** On the home page click the agent › “Start / resume”. The AMW opens it in a new terminal tab.

## Values to enter
| Field in the AMW | Where from |
|---|---|
| Working folder | the project folder the agent works in |
| First prompt | first sentence of a new session, e.g. “Read your messages and work through them.” |

## Common problems
- **“No data yet” under State and usage** – The folder is not set up yet (step 1), or the session was started before the setup. Restart it once.
- **“Not connected”** – The session is running but does not know its name. In the agent's window run `amw anmelden --von <name>`.
- **The folder already belongs to another project** – A folder belongs to exactly one project. Use a separate folder for a second project.

## Next
- Rename: `amw agent umbenennen <old> <new>`. The old name stays valid as a second name, so older messages and commands keep working.
- `amw einrichten agenten-ordner <folder> --entfernen` removes what the AMW added to the folder.

## Questions
### Why can't I rename in the Workbench?
The name is used in start scripts and running sessions on this PC. The command line changes everything in one place without a running session losing its name.
