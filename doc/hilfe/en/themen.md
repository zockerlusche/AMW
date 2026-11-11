# Topics: what applies now

A topic collects all decisions about one system – “saving” or “map look”, for example – and has a maintained summary “applies now”. Nobody has to read old decisions one by one.

## You need
- A maintainer: the agent who writes the summary and keeps it up to date.

## Steps
1. **Create a topic** `amw thema neu "<name>" --pfleger <agent>`.
2. **Write the summary** The maintainer writes it with `amw thema pflegen <topic> --text-datei <file>`.
3. **Keep it current** When a new decision about the topic is added, the summary counts as outdated. The maintainer updates it or confirms it with `amw thema bestaetigen <topic>`.

## Common problems
- **“outdated since B…”** – A newer decision is not in the summary yet. The maintainer is reminded.
- **“No summary yet”** – Step 2 is missing.

## Next
- One topic can be the project style (`amw thema einstellen <topic> --stil`); all agents then see it in their start information.
