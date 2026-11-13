# Keep an eye on the service

The AMW service works in several parts side by side: the main loop (notifications, supervision, queue), the file exchange, the sync with the online storage and the AI worker. Each part reports after every round. A watchdog checks that they all report.

## Steps
1. **Look** Operations › Service shows for each part whether it is running, when its last round was, how long it took, how often it was restarted and its last error.
2. **Watch the colour** Green: all fine. Yellow: the last round had an error, the part has been silent longer than allowed, or it was restarted in the last hour. Red: the part is stalled – then the start page shows a banner too.
3. **Nothing to do** If a part stays silent longer than allowed, AMW restarts it by itself and sends you one message. The other parts keep running.
4. **Only step in for the main loop** The main loop cannot replace itself. If it stalls you get a message; then restart the service: `amw dienst neustart`.

## Values to enter
| Part | Allowed silence |
|---|---|
| Main loop | 3 minutes |
| File exchange | 5 minutes |
| Sync | 15 minutes |
| AI worker | 30 minutes (it runs jobs within its round) |

## Common problems
- **Everything red, "The service has stopped reporting"** – The service is not running or hangs completely. `amw dienst status` shows whether it runs; `amw dienst neustart` restarts it.
- **A part stays yellow** – Its last round had an error, for example no network for the sync. The error is shown in the table; often the next round clears it.
- **"off"** – The part is not switched on in this service, for example the sync without online storage.
