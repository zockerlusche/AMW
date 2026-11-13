# Set up and use a local AI

The AMW can give jobs to an AI on this PC – images with ComfyUI or texts with Ollama, for example. It starts the AI when needed, computes through the queue and files every result as a document with its origin.

## You need
- An installed local AI that only answers on this PC (e.g. ComfyUI or Ollama).
- The licence of the model you want to use.

## Steps
1. **Register the AI** `amw ki neu <name> --art bild --schnittstelle comfyui` (for texts: `--art sprache --schnittstelle ollama`). With `--start "…"` the service starts the AI itself as soon as a job for it is due and it does not answer.
2. **Approve a model** `amw ki modell <name> <model> --lizenz … --quelle <url> --kommerziell ja|nein|unklar`, then `amw ki freigeben <name> <model> --grund …`. Only approved models receive jobs.
3. **Grant access** `amw ki recht <name> --wer <agent>` – who besides the lead and you may give jobs.
4. **Give a job** `amw ki auftrag <name> --modell … --prompt "…"`. The job waits in the queue until the graphics card is free. With `--nachts` it only starts in the AI window.
5. **Decide** Under Documents choose “Select” or “Discard” on the result and, if you reworked it, “Record rework”.

## Values to enter
| Field in the AMW | Where from |
|---|---|
| AI window (Settings › This PC) | time range for night jobs, e.g. 22-06 |
| Licence, source, commercial | from the model's page |
| Stop a local AI after … minutes without a job (Settings › This PC) | default 30 |
| Local AIs always on (Settings › This PC) | names of the AIs that should run all the time; empty = all only when needed |

## Common problems
- **The job waits a long time** – The graphics card is busy, or it is a night job and the AI window is still closed. The run shows the reason.
- **“not approved”** – The model is registered but not approved yet (step 2).
- **The AI does not answer** – Without a start command the AMW does not start it. Start it yourself or add `--start`.
- **The AI is not running although it is registered** – That is intended: the AMW only starts it when a job comes.
- **A direct call to the AI fails (“connection refused”)** – The AI is off. Let `amw ki auftrag` start it, or keep it running with `amw ki aendern <name> --immer-an`.

## Next
- Proof of the human creative decision (copyright, Steam disclosure): `amw ki nachweis` lists who selected, discarded or reworked each AI result.
- Night jobs never start in the lead time of a test date; until then every other run goes first.

## Questions
### Why is my AI suddenly off?
The AMW starts a local AI only when needed: when a job for it is due. If no job comes for 30 minutes after that and nobody else uses it, it stops the AI again and frees memory and GPU memory. It only does this with an AI it started itself – it never stops an AI you started yourself. To keep an AI running all the time: `amw ki aendern <name> --immer-an` (back with `--bei-bedarf`) or Settings › This PC › Local AIs always on.

### May an agent use the AI directly, bypassing the AMW?
Better not. A job via `amw ki auftrag` (or a run via `amw lauf ausfuehren --gpu`) sits in the queue, and the AMW knows the graphics card is busy. Whoever talks to the AI directly is invisible to the queue: another run may then start at the same time, and both run short of memory.

### Who may approve a model?
The lead approves models with a free licence. Models with usage rules (e.g. Open RAIL) are approved only by the person running the AMW.
