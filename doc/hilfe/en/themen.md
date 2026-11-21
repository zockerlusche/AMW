# Topics: what applies now

A topic collects all decisions about one system – “saving” or “map look”, for example – and has a maintained summary “applies now”. Nobody has to read old decisions one by one.

## You need
- A maintainer: the agent who writes the summary and keeps it up to date.

## Steps
1. **Create a topic** `amw thema neu "<name>" --pfleger <agent>`. You, the lead and the project's co-developer may create topics; you or the lead set the maintainer and the project style.
2. **Write the summary** The maintainer writes it with `amw thema pflegen <topic> --text-datei <file>`.
3. **Keep it current** When a new decision about the topic is added, the summary counts as outdated. The maintainer updates it or confirms it with `amw thema bestaetigen <topic>`.

## Common problems
- **“outdated since B…”** – A newer decision is not in the summary yet. The maintainer is reminded.
- **“No summary yet”** – Step 2 is missing.

## Next
- One topic can be the project style (`amw thema einstellen <topic> --stil`); all agents then see it in their start information.
- **Menu item “Topics”:** every topic shows exactly one status: “waiting for you” (a new version is there), “check again” (a new decision came after your approval – “because of: B…” is shown; the AI checks first, so it is not under “For you”), “in progress” or “approved”. Open a topic and you read its text as a whole. On the PC you only get what is possible right now: **Approve**, **Send back** (with a note – it goes to the maintainer as a task), **Edit** (your text becomes the new version and counts as approved by you; the maintainer gets a note) and **Mark for deletion** (nothing is deleted; you can unmark at any time). With “+ Topic” you create a topic yourself (title and text) – it is then “in progress” for the AI. On the phone you read along. Topics waiting for you appear under “For you” on the overview and lead straight there. Nobody sets the status by hand – AMW derives it from versions, decisions and your actions. Agents see it with `amw thema status`.
