# Heavy runs: tests and builds through the queue

Several projects share one PC. If test suites, builds or image runs start at the same time, memory runs out and all of them fail. The AMW therefore puts such runs into one queue for the whole computer – automatically, without an agent having to remember it.

## You need
- Agent folders set up by the AMW (`amw einrichten agenten-ordner <folder>`).
- The switch “Send heavy commands through the queue” under Settings › This PC (on by default).

## Steps
1. **Update the folders** Run `amw einrichten agenten-ordner <folder>` once for every agent folder. This adds the hook; running sessions pick it up after a few seconds.
2. **What happens then** If an agent starts a heavy command directly (for example the whole test suite), the command is not executed. Instead the agent gets the ready-made replacement: `amw lauf ausfuehren --beschreibung "Test-Suite" -- <its command>`. It waits until the computer is free, then runs and returns the result.
3. **Add your own commands** Under Settings › Project › “More heavy commands”, enter one `Name = pattern` per line, for example `Render maps = maps\.py`.
4. **State the need** If you know what a run needs, say so: `--braucht-gb 4` (memory), optionally `--braucht-vram-gb` (graphics memory) and `--braucht-platte-gb` (free disk space). Without it the AMW uses the project's memory limit.
5. **Check** Home › control panel › “Computer” shows how many runs are in progress and waiting, and when the computer is expected to be free.

## Values to enter
| Field in the AMW | Where it comes from |
|---|---|
| Send heavy commands through the queue (This PC) | leave it on; off means agents start everything directly |
| Memory reserve (This PC) | how much stays free for you, default 3 GB |
| Show long-term memory use from (This PC) | a program outside the queue that uses at least this much memory appears in the control panel, default 4 GB, 0 = off |
| More heavy commands (Project) | Name = pattern, one entry per line; the pattern is a regular expression |

## Common problems
- **An agent still starts tests directly** – Its folder does not have the hook yet: run `amw einrichten agenten-ordner <folder>`.
- **A run waits for a long time** – The control panel says why: the computer is busy or too little memory is free. The human can move a run to the front (`amw lauf vorziehen <nr>`).
- **A single short test is rejected** – The pattern is too broad. Single test modules stay free; make your own patterns narrower.
- **“Muster ungültig”** – The pattern is not a valid regular expression, for example a bracket is missing.

- **The computer is idle, but nothing starts** – A program outside the queue is using the memory, for example a local AI server or a virtual machine. The control panel shows under “Computer” which program it is, how much it uses and since when. Close it yourself when you no longer need it – the AMW never closes anything.

## Next
- Heavy by default: whole test suites, browser tests, builds and the split of the web branch.
- About runs of another project you only see that the computer is busy and until when – never what is running there.
- Every computer has its own queue.

## Questions
### What happens if the hook fails for once?
Then the command simply runs – an error never blocks anything. The error is written to the log `%LOCALAPPDATA%\amw\hook-fehler.log` on this PC; if there is something in it, have a look, because heavy commands then start directly again.

### What does “in long-term use” mean?
A program that does not run through the queue and has been using a lot of memory for more than 10 minutes. The AMW only reads the name, memory and start time of the processes – no command lines. Many small processes, such as a browser, do not count.

### Can I switch this off for one computer?
Yes: Settings › This PC › switch off “Send heavy commands through the queue”. The queue itself stays, only the rejecting stops.
