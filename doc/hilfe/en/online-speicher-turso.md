# Create the online store at Turso

The online store is where your PC and the online page exchange data. You create it once and enter its address and key in the AMW.

## You need
- The AMW runs on this PC (the watcher is set up).
- A free account at turso.tech.
- About 10 minutes.

## Steps
1. **Account and database** Sign in at turso.tech and create a database (“Create Database”). Any name works; pick a location near you.
2. **Copy the address** The database page shows the address (“Database URL”). It starts with `libsql://` and ends in `.turso.io`.
3. **Create a key** On the same page choose “Create Token”: read and write, no expiry. Copy the key – it is shown only once.
4. **Enter it on the PC** In the AMW: Settings › Online store. Paste address and key and save. The AMW checks the connection, creates the tables and switches the sync on. The command `amw web einrichten` does the same.
5. **Restart the watcher** The AMW says so: the sync starts with the next start of the watcher (control desk › Watcher › Restart).
6. **Check** Settings › Online store shows “key saved” and the sync is on. `amw web status` shows the last upload.

## Values to enter
| Field in the AMW | Where it comes from |
|---|---|
| Address | Turso, database page: “Database URL” (`libsql://name-account.turso.io`) |
| Key | Turso, “Create Token” (read and write) |

## Common problems
- **“Adresse libsql://….turso.io und Schlüssel nötig”** (address and key required) – The website address was copied instead of the “Database URL”, or a field is empty.
- **“nicht erreichbar oder Schlüssel abgelehnt – nichts gespeichert”** (not reachable or key rejected) – Either the key belongs to another database, is read-only or has expired (create a new one with read and write), or there is no internet connection right now.
- **Nothing arrives online** – The watcher is not running or was not restarted after you entered the values.

## Next
- Set up the online page: on first open it asks for the same address and key.
- Do not store or share the key. The AMW keeps it on this PC only and never shows it.

## Questions
### Does it cost anything?
For one or two projects the free Turso plan is enough.

### What is kept in the online store?
A copy of what the online page shows, and the mailbox with what you do while away. The complete data stays on your PC.

### How do I switch it off again?
Settings › Online store › sync off. The online page then shows the last state and accepts nothing more.
