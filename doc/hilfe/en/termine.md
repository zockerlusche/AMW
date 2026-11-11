# Test dates and deadlines

A test date says when you test. The AMW derives the deadline “test build ready” for everyone and shows with a traffic light whether the linked milestone will be done by then.

## You need
- The time of the test, and the weekday for recurring tests.

## Steps
1. **Create the date** `amw termin neu --titel "Weekly test" --art test --am "13.11. 18:00"` – weekly with `--woechentlich`, until a day with `--bis YYYY-MM-DD`.
2. **Link a milestone (optional)** Add `--bogen <number>`. The traffic light then compares its forecast with the deadline.
3. **Adjust the lead time (optional)** Default: the test build is due 4 hours before the date. Change it with `--vorlauf <hours>`.

## Values to enter
| Field in the AMW | Where from |
|---|---|
| Title | short, e.g. “Weekly test” |
| Time | local time, e.g. “13.11. 18:00” |
| Milestone | number from Planning |

## Common problems
- **“test build not reported yet”** – The agent reports the finished test build with `amw termin bereit <date> --text "what is new"`.
- **A single date is cancelled** – `amw termin absagen <date> --am "20.11. 18:00"` cancels only that occurrence.

## Next
- Dates are under Planning › Dates; the next test is also on the home page.
