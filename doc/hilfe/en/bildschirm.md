# Releasing the screen for agents

Some runs need the screen: they open a window, click and type themselves – for example trials in the program or screenshots. That only works when you release the screen. When you are back, the AMW closes the release by itself – you choose how it notices.

## You need
- The Workbench at the PC – or online as a system admin. Closing works everywhere.
- To recognise a remote session: the program that only runs during a connection (Settings › This PC › “Remote access program”, for TeamViewer e.g. TeamViewer_Desktop.exe).

## Steps
1. **Release** Home › Screen for agents › “Free for agents …” – optionally with a time until when.
2. **Agents work** Runs with a window start one after the other; best leave the PC alone meanwhile.
3. **Back at the PC** The release closes by itself – or end it yourself: Home › Screen for agents › “End sharing”.

## Values to enter
| Trigger | When the release closes by itself |
|---|---|
| Input at the PC (keyboard, mouse) | on input at the PC, also through a remote session – a single movement is not enough, only a second one shortly after |
| New remote session | as soon as the program entered there starts |
| Input in the Workbench at the PC | on any input in the Workbench at the PC |
| Time (always) | at the time until which you released it |

## Common problems
- **The release closes although you only wanted a quick look** – Input at the PC or remote session is on. If you want to look in via a remote session or move the mouse without interrupting the agents: switch these triggers off.
- **An agent moves the mouse while you are watching** – This happens when “Input at the PC” is off: the AMW does not notice you are there, and runs with a window start even while you work. End the release yourself then (Home › Screen for agents › “End sharing”).
- **Remote session not recognised** – The program is not entered or has a different name.

## Next
- You switch the triggers one by one in Settings › This PC › “Close the screen release automatically”; new installations have all three on. When a trigger is off, **the AMW does not watch it at all** – it measures nothing and records nothing about it.
- If a run with a window keeps running after closing, the lead is told after 5 minutes.
- Online, only a system admin may release the screen, with a confirmation; the time until when is optional. Without a time the screen stays free until someone takes it back or a switched-on trigger fires. The history shows who it was. Anyone may close it online.
