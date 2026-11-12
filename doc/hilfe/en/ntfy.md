# Phone notifications with ntfy

The AMW sends a short message to your phone when something is waiting for you – a question, an approval, a halt. ntfy is the simplest way: a free app and a secret channel name.

## You need
- The AMW runs on this PC (the service is set up).
- The **ntfy** app on your phone (Google Play, F-Droid or App Store).

## Steps
1. **Create a channel** Run the command `amw push ntfy` on the PC. The AMW creates a random, secret channel name, shows it and stores it – afterwards it is listed under Settings › phone notifications as the channel (topic).
2. **Subscribe on the phone** In the app tap “+”, enter the channel name exactly and subscribe. The server stays `ntfy.sh` unless you run your own.
3. **Set the link** So that tapping a message opens the right page: under Settings › Online site, enter the “Address of the online page” (`https://…`). As a command: `amw push link https://your-page.example/`.
4. **Switch on and test** Switch on the main switch and ntfy, save and press the test button for ntfy. As commands: `amw push an`, then `amw push probe ntfy`. The test arrives within a few seconds.

## Values to enter
| Field in the AMW | Where it comes from |
|---|---|
| Channel (topic) | created by the AMW – subscribe to exactly this on the phone |
| Server | `https://ntfy.sh` or the address of your own ntfy server |
| Address of the online page (section Online site) | address of your online page |

## Common problems
- **The test does not arrive** – The channel name on the phone differs (case matters) or the app is not allowed to show notifications.
- **Messages arrive late (Android without Google services)** – Switch on “Instant delivery” in the app.
- **Nothing arrives any more** – The service is not running (`amw dienst status`); it sends the messages.
- **“ntfy-Server: https://…”** – The server address must start with `https://`.

## Next
- The channel name is like a password: whoever knows it can read along. That is why messages only say that something is waiting – no content.
- Quiet hours and what gets reported are set in the same place.

## Questions
### Can I use my own ntfy server?
Yes. Enter its address under “Server” and subscribe to the channel on that server in the app.

### Does it work without ntfy?
Yes, via Pushover or Telegram – both sit next to it in the settings.

### How do I set up Telegram?
In Telegram create a bot with @BotFather and copy its token. Send the new bot a message. Then run `amw push telegram --token <token>` on the PC: the AMW shows the chat ID from your message. `amw push telegram --token <token> --chat <ID>` stores both.

### How do I choose my own topic name?
`amw push ntfy --kanal <name>` sets your own name; without `--kanal` the AMW creates a random one.
