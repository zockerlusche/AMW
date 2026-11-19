# Order of work: one thing at a time

Every agent works through its list from top to bottom and finishes one piece before starting the next. That way there are no half-finished states, and you always see what is being worked on.

## You need
- A project with a lead and agents.

## Steps
1. **New things land in the inbox** If the lead or you create a task for an agent who is working, it goes to the inbox (Planning › Tasks › Lists). The control center shows how many are waiting there.
2. **Schedule** The lead puts the task into the list – at the earliest behind the running piece. As a command: `amw liste ordnen <agent> A12 A15`.
3. **Waiting allows the next one** If the running piece has to wait (review, run, question), the agent enters the reason and may start the next one. When the reason is resolved, the waiting piece comes next as soon as the current one is done.
4. **Put first when it really matters** Open the task and press “Put first” (with a reason). The agent saves its work, does this task first, and then continues with the interrupted piece.

## Common problems
- **“A… is still running – one thing at a time”** – An agent wanted to start a second piece. It finishes the running one or lets it wait for a reason (`amw aufgabe wartet <nr> --auf …`).
- **A task still waits for something that was settled long ago** – `--auf` only adds wait reasons; old ones stay open until they settle by themselves, are ticked off, or the task starts again (a start closes all open reasons). Tick off with `amw aufgabe wartet <nr> --erledigt <reason>`, or tick off the old one and set the new one in one step with `--erledigt <old> --auf <new>`. If an old reason stays open after `--auf`, AMW tells you right away.
- **An instruction does not reach the agent** – It is working on something else. The instruction is waiting and arrives as soon as the running piece is done or waits. If it belongs to the running piece, send it with `--aufgabe <nr>`.

## Next
- If the lead proposes to put something first, you get a question with “Yes” and “No”. “Yes” carries it out.
- You order your own tasks (under “Your tasks”) freely.
