# Monitor project servers

If a project runs its own server on this PC – a test server or a local interface, for example – the AMW checks regularly whether it answers and restarts it if you want.

## You need
- The port the server answers on.
- Optionally the command that starts it and its working folder.

## Steps
1. **Register the server** Run `amw server anmelden <name> --port <port>`.
2. **Set up restart (optional)** With a start command: `amw server anmelden <name> --port <port> --start "pythonw C:/path/server.py --port 8766" --ordner C:/path --neustart`. If the server fails, the service restarts it.
3. **Check** Operations › Project servers shows state, failures and who is notified on failure. Check now: `amw server pruefen <name>`.

## Values to enter
| Field in the AMW | Where from |
|---|---|
| Name | your choice, short, e.g. “gameserver” |
| Port | port the server answers on locally |
| Start command | command without a window, e.g. with `pythonw` |
| Responsible | who gets a message on failure (default: you) |

## Common problems
- **“not checked yet”** – The service checks in its next round; after a minute the state is shown.
- **The server does not restart** – Without `--neustart` and a start command the AMW only reports the failure.

## Next
- Unregister: `amw server abmelden <name>`. The server itself keeps running; the AMW never stops anything.
