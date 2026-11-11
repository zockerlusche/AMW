# Second factor: new or lost phone

When you sign in, the online page asks for a six-digit number from your authenticator app in addition to the password. If the phone is new or gone, you set up the second factor again from the PC.

## You need
- Access to the PC the AMW runs on – the second factor can only be reset from there.
- User name and password of the online page.
- An authenticator app on the new phone.

## Steps
1. **Reset on the PC** Run the command `amw web zweitfaktor-neu`. It deletes the previous secret in the online storage; the old app no longer shows valid numbers afterwards.
2. **Sign in online** Open the online page, enter user name and password and leave the field for the number empty.
3. **Scan again** The page shows a new QR code. Scan it with the authenticator app and confirm the first number.
4. **Delete the old entry** Remove the AMW entry on the old phone or in the old app.

## Common problems
- **“Verbindung zum Online-Speicher … ist blockiert”** – The operating mode does not allow the online storage; choose “Cloud” under Settings › Operating mode.
- **The number is not accepted** – The phone’s clock is wrong (the number is only valid for about 30 seconds) or the number has been used before; wait for the next one.
- **Locked after failed attempts** – After 5 failed attempts from one address, sign-in is locked for up to 15 minutes. Wait; the limits are under Settings › Online site.

## Next
- Resetting only works on the PC. Someone who only knows the password cannot get around the second factor.
- The password stays as it was.

## Questions
### I lost my phone – do I have to act right away?
Yes: reset (step 1) so that the app on the lost phone no longer delivers valid numbers, then set it up again.

### Can I use two phones?
Yes, if both scan the same QR code during setup. Later, a second device can only be added by resetting and scanning again with both.
