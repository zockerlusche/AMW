# Choosing the operating mode

The operating mode defines where this installation may connect to. It is enforced at every point where the AMW reaches outwards – not just in the interface.

## You need
- The AMW runs on this PC.
- An answer to the question: may data of this project leave the machine or the company network?

## Steps
1. **Look at the current state** Settings › Operating mode. Below it you find the list “Connections of the AMW”: every address the AMW connects to and where it leads (this PC only, company network, internet). As a command: `amw einrichten verbindungen`.
2. **Choose the mode** Click one of the three cards and save. As a command: `amw einrichten betriebsart pc` (or `server`, `cloud`).
3. **Test** Press “Test connections”. Every allowed address is tested for reachability (connection only, no data). Red marks what is switched on but blocked in this mode.
4. **Clean up** Fix red rows: switch the service off (e.g. sync off, notifications off) or choose another mode.

## Values to enter
| Field in the AMW | Where it comes from |
|---|---|
| This PC only | Nothing leaves the machine: no sync, no online page, no notifications |
| Own server on the company network | Connections only to addresses on your own network (e.g. `192.168.…`, `10.…`, names like `ntfy.company.lan`) |
| Cloud | Online storage, online page and notification services on the internet are allowed |

## Common problems
- **“Betriebsart …: Verbindung zum Online-Speicher zu … ist blockiert”** – The chosen mode does not allow this address. Change the mode or switch the sync off.
- **Notifications no longer arrive** – In “This PC only”, and for internet services also in “Own server”, they are not sent; the delivery log states the reason.
- **A name on the company network counts as internet** – A name with a dot only counts as company network if it points exclusively to addresses on your own network. Otherwise enter the address as a number.

## Next
- Nothing chosen yet? Then what ran so far applies: with sync or notifications switched on “Cloud”, otherwise “This PC only”.
- The operating mode applies to this PC and all projects on it.

## Questions
### Does really nothing leave the machine in “This PC only”?
The AMW itself then opens no outbound connection. What runs outside the AMW is not covered: Claude Code talks to its provider, Git to its server.

### Can I use ntfy in “Own server”?
Yes, with your own ntfy server on the company network – there also via `http://`. The public service `ntfy.sh` is on the internet and is then blocked.

### Online storage and online page on my own network?
Yes: your own libSQL server as storage and the online page on a company web server. `amw web paket --seite https://amw.company.lan --speicher https://amw-db.company.lan` builds a ZIP on the PC with everything the web server needs, including instructions, and enters the access on this PC. On the company network `http://` works too – the sign-in page and the settings then warn, because passwords travel unencrypted.

### What happens to the “Open in Claude” button?
It leads to the internet and is only shown in the “Cloud” mode.
