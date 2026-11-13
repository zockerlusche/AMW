# Planning: Where do we stand?

Planning shows at a glance which milestone is active right now, how far along it is, who is working on what, and what is not assigned to any milestone yet.

## Steps
1. **Read where we stand** At the very top of Planning › Timeline you see the active milestone with its progress (“3 of 8 done”), the next target date and, under “Working now”, which agent is working on which task. A click on a task opens it.
2. **Read the overview** Each milestone is a bar from its start to the forecast. The vertical line marked “Now” is today; hover over it to see date, time and what is running. Hover over a bar or a diamond to see title, status, progress, forecast and target date.
3. **Show finished ones (optional)** Finished milestones are hidden so that the active ones come first. “Show finished” in the overview brings them back, faded and with ✓. In the timeline below they are collapsed under “Finished milestones”.
4. **Assign tasks without a milestone** At the very bottom of the timeline, “Without milestone (n)” lists every open task that belongs to no milestone. Assign one: `amw aufgabe aendern <no> --bogen <no>`.

## Values to enter
| Field in the AMW | Where from |
|---|---|
| `--bogen` when creating a task | number of the milestone from Planning, e.g. 45 for B45 |

## Common problems
- **“Zu welchem Meilenstein gehört die Aufgabe?”** – The lead creates a task while there is an active or planned milestone. The message lists them and suggests one. Assign with `--bogen <no>` or deliberately skip it with `--ohne-bogen`.
- **“No milestone is active”** – All milestones are planned or finished. Start the next one in Planning with “Activate”.

## Next
- “Computer – today” below the overview is collapsed. A click opens it; it shows which runs ran on this PC today and which are waiting.

## Questions
### Why do I have to give a milestone when creating a task?
So that nothing disappears: a task without a milestone does not show up in the overview. Agents other than the lead may not set a milestone. Their tasks stay under “Without milestone” until the lead assigns them.
