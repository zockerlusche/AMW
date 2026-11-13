# Users of the online site

Several people can sign in on the online site – each with their own password and two-factor. You add them at the PC, give them an activation code and assign a role and projects. Until then a new user has no rights.

## You need
- The online site and online storage, set up (Settings › Online storage and Online site).
- The Workbench at the PC – users are managed only there.
- For each user a phone with an authenticator app (Google Authenticator, Microsoft Authenticator …).

## Steps
1. **Add** Settings › Users of the online site › enter a name › “Add”. The name is what they sign in with (no spaces).
2. **Activate** Choose “Activate” for the user. The AMW shows an activation code (16 characters, e.g. `K7QM-2XRD-9WFH-T4PB`) – exactly once, valid for 24 hours. Give it to the user in person, spoken or in a chat. It is stored nowhere else.
3. **First sign-in** The user opens the online site, chooses “First sign-in”, enters name and code, sets a password (at least 12 characters) and scans the QR code with their app. With the first number from the app their access is set up.
4. **Approve** You get the message “New user … awaiting approval” (also as a push). Until then they only see “Your access is being reviewed”. Choose their role and projects and save.

## Values to enter
| Role | What it may do |
|---|---|
| Reader | sees their projects, changes nothing. |
| Editor | works in their projects: answer questions, messages, tasks, documents, approvals, pausing. |
| Project admin | additionally the settings of their projects and agents. |
| System admin | everything, in all projects. At the PC you are always system admin, as with the existing access of the online site. |

## Common problems
- **“Name or activation code is wrong”** – Typo, code expired or already used. Upper/lower case and dashes do not matter. Remedy: reset access.
- **The number from the app is not accepted** – The phone's clock is off. Let the phone set the time automatically; the site accepts numbers up to 30 seconds off.
- **“Time is up” at the QR code** – More than 10 minutes passed between code and QR code. Start again with the same activation code – it stays valid until the access is fully set up.
- **“Your access is being reviewed” does not go away** – Role and projects are still missing. Assign them at the PC, then the user reloads the page.

## Next
- Forgotten password or lost phone: “Reset access”. Password and two-factor are reset, all of the user's sessions end, and they set both up again with the new code.
- Blocking takes effect with their next request. Unblocking restores the previous access.
- What a user writes online carries their name in the history.

## Questions
### Why no link by email?
The AMW does not send emails. The code is passed on in person; someone who only knows the name cannot get in without it.

### Can someone else use the code?
Only if they have it and are faster. Then the right user sees “already used” and tells you – you block, reset access and pass on the new code.

### Where are password and two-factor stored?
Only in the online storage, as a hash or secret – never on the PC, never in the history. Of the activation code only a hash is stored there.
