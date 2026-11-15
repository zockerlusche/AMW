# Release rhythm and review levels

AMW can handle two things for you: how strictly a change is reviewed (review level) and when it reports that something can be released (release rhythm). Both stay off until the lead switches them on.

## Steps
1. **Switch on review levels** Settings › Project › Review levels to “on”. From then on every review request starts with its level and the files that decide it.
2. **Who reviews** High – everything with permission or security checks: database, sign-in, command line, online actions, service, file exchange, queue, release, PHP of the online page – is reviewed by the lead. Medium – interface, help and other code – by an agent other than the builder. Low – docs and tests only – needs no review request.
3. **Release low-level changes** With the lead's merge approval and a green full run on exactly this commit: `amw release ausliefern --zweig <branch> --aufgabe <nr>`.
4. **Raise the level** The builder can raise a review request: `amw pruefung bitte … --stufe hoch`. Lowering is not possible.
5. **Pick a release rhythm** Settings › Project › Release rhythm: immediately, daily at a time, or per milestone. When something is ready – green review, merge approval, full run on exactly this commit – whoever handles merges (otherwise the lead) gets one message. AMW never releases by itself.
6. **Releasing closes the tasks** After `amw release ausliefern`, every task whose green commit with merge approval is included counts as done – the reviewed commit is the evidence. Give the sentence for the release notes right in the review request: `amw pruefung bitte … --aufgabe <no> --gruppe neu --hinweis "…"`. Open criteria do not block this; the lead is told about them. A task waiting for the developer (for example a confirmation on the device) stays open. Projects that merge through GitHub pull requests: when the title of a merged PR starts with the task (“A1234: …”, “[A1234] …”) or its text says “fertig: A1234” or “closes A1234”, and its checks are green, the task is set to done as well (evidence = merge commit). Merely mentioning a task (“groundwork for A1235”) does not count. AMW asks with `gh` in the project folder at most every 5 minutes – only if the operating mode allows the connection (github.com only in “Cloud”); `gh` keeps its own sign-in. To switch it off: Settings › Project › Automatic planning.

## Values to enter
| Field in AMW | Meaning |
|---|---|
| Review levels | on or off (default off) |
| Release rhythm | off, immediately, daily at HH:MM, per milestone |
| Own patterns | Command line: `amw projekt einstellen 'pruef_muster={"hoch": ["src/db/*"], "mittel": ["ui/*"], "niedrig": ["docs/*", "tests/*"]}'` |

## Common problems
- **“Version 1.2.0 ist schon vergeben” on a review request** – Another task already carries this number (open or green review not yet released), it is not above main, or the tag exists. The message names the next free number; change it in the commit and submit again.
- **“Prüfstufe hoch – prüfen muss …”** – The review request went to an agent, the level requires the lead. Ask the lead instead.
- **“Prüfstufe unbekannt”** – AMW could not read the changed files: the project folder is missing or the commit is unknown there. It then counts as high.
- **No message with “per milestone”** – It only reports once every open task of the milestone is ready.
