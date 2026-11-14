# Release rhythm and review levels

AMW can handle two things for you: how strictly a change is reviewed (review level) and when it reports that something can be released (release rhythm). Both stay off until the lead switches them on.

## Steps
1. **Switch on review levels** Settings › Project › Review levels to “on”. From then on every review request starts with its level and the files that decide it.
2. **Who reviews** High – everything with permission or security checks: database, sign-in, command line, online actions, service, file exchange, queue, release, PHP of the online page – is reviewed by the lead. Medium – interface, help and other code – by an agent other than the builder. Low – docs and tests only – needs no review request.
3. **Release low-level changes** With the lead's merge approval and a green full run on exactly this commit: `amw release ausliefern --zweig <branch> --aufgabe <nr>`.
4. **Raise the level** The builder can raise a review request: `amw pruefung bitte … --stufe hoch`. Lowering is not possible.
5. **Pick a release rhythm** Settings › Project › Release rhythm: immediately, daily at a time, or per milestone. When something is ready – green review, merge approval, full run on exactly this commit – whoever handles merges (otherwise the lead) gets one message. AMW never releases by itself.

## Values to enter
| Field in AMW | Meaning |
|---|---|
| Review levels | on or off (default off) |
| Release rhythm | off, immediately, daily at HH:MM, per milestone |
| Own patterns | Command line: `amw projekt einstellen 'pruef_muster={"hoch": ["src/db/*"], "mittel": ["ui/*"], "niedrig": ["docs/*", "tests/*"]}'` |

## Common problems
- **“Prüfstufe hoch – prüfen muss …”** – The review request went to an agent, the level requires the lead. Ask the lead instead.
- **“Prüfstufe unbekannt”** – AMW could not read the changed files: the project folder is missing or the commit is unknown there. It then counts as high.
- **No message with “per milestone”** – It only reports once every open task of the milestone is ready.
