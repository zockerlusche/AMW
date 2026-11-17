# Planning: Where do we stand?

Planning shows at a glance which milestone is active right now, how far along it is, who is working on what, and what is not assigned to any milestone yet.

## Steps
1. **Read “Where do we stand right now?”** At the very top of Planning › Timeline you see the active milestone with its progress (“Final version 2.0: 3 of 8 tasks done · target 20.11.”), the next target and, under “Being worked on”, which agent is working on which task. A click on a task opens it.
2. **Read the overview** Each milestone is a bar from its start to the forecast. Colour AND pattern tell you how it stands: hollow with a dashed edge = planned, blue = in progress, yellow ribbed = tight, orange-red diagonal stripes = late, bluish green = done. The vertical line marked “Now” is now; hover over it to see date, time and what is running. Hover over a bar or a diamond to see title, status, progress, forecast and target date.
3. **Read the milestone card** A click on a bar opens the milestone’s card. At the top: who owns it, status and target; below it a sentence like “5 of 15 tasks done · 1 running · 1 waiting for you · 8 blocked” and the timeline from start through today to the target (dashed: the forecast). Then “what is running, what is stuck” – grouped by cause, with the way to step in: “Answer question” when something waits for you, “Move run up” when tasks wait for a run in the queue, “Write to lead” for reviews or agents. Then the tasks themselves, open ones first, each with a small timeline (tick = created, solid = in progress, dashed = waiting) and “moved here from milestone …” when it came from another one. Requirements, design, acceptance and the order of the steps are under “Details” at the bottom.
4. **Show completed ones (optional)** Completed milestones are hidden so that the active ones come first. “Show completed” in the overview brings them back, faded and with ✓. In the timeline below they are collapsed under “Completed milestones”.
5. **Assign tasks without a milestone** At the very bottom of the timeline, “Without milestone (n)” lists every open task that belongs to no milestone. Assign one: `amw aufgabe aendern <no> --bogen <no>`.

## Values to enter
| Field in the AMW | Where from |
|---|---|
| `--bogen` when creating a task | number of the milestone from Planning, e.g. 45 for B45 |

## Common problems
- **“Zu welchem Meilenstein gehört die Aufgabe?”** – The lead creates a task while there is an active or planned milestone. The message lists them and suggests one. Assign with `--bogen <no>` or deliberately skip it with `--ohne-bogen`.
- **“No milestone is active”** – All milestones are planned or finished. Start the next one in Planning with “Activate”.

## Next
- “What the computer did today” below the overview is collapsed. A click opens it; it shows which runs ran on this PC today and which are waiting.

## Questions
### Why is a task “running” although nobody started it?
When an agent starts a run for one of its tasks that has not started yet, AMW sets it to “running” – the task comes from the run (`--aufgabe`), from “A1234” in the description or from the branch (a1234, a1234-2). If the task is waiting for someone, or the agent is already working on another piece, everything stays as it is. To switch it off: Settings › Project › Automatic planning.

### Who closes a milestone when everything is done?
When all tasks of a planned or active milestone are done (or dropped), its card shows “All tasks are done – close the milestone?” and the lead gets one notice; “Close” is under “More … · For the lead”. With Settings › Project › “Milestone done” set to “automatic”, AMW closes it itself. If a version is mandatory and none is recorded yet, it stays a suggestion with that reason.

### What does “Move up” do?
The button at the top of the card moves the milestone up by one – ahead of the next open one before it. The lead gets a message and reorders the tasks. Activate, Close, Retrospective and Edit are the lead’s job; they are under “More … · For the lead”.

### Why patterns and not just colours?
So the timeline stays readable with red-green colour blindness: the colours (blue, bluish green, yellow, orange-red) are chosen to be told apart with colour vision deficiency, and every state also has its own pattern – nothing depends on colour alone.

### Why does the bar not get shorter although tasks get done?
Because new tasks were added since the start. In the milestone card under “Details › Added” you see “Since start (05.11.): +5 added · 3 done · 8 open”, and the same when you hover over the bar; “Where do we stand right now?” shows “+5 since start”. Counted as added is anything created after the start or pulled into the milestone.

### Why do I have to give a milestone when creating a task?
So that nothing disappears: a task without a milestone does not show up in the overview. Agents other than the lead may not set a milestone. Their tasks stay under “Without milestone” until the lead assigns them.

### Can I collect new tasks first and plan them later?
Yes: Settings › Project › “New tasks go” set to “into the inbox”. New tasks without a milestone then land in the inbox (the same as “in the inbox” in the control center); Planning shows them at the top under “Inbox (n)”. The lead deliberately pulls them into a milestone: `amw aufgabe aendern <no> --bogen <no>`. Naming `--bogen` when creating – for example because the task is needed for acceptance – puts it straight into the milestone.
