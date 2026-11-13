# Benutzer der Online-Seite

Mehrere Menschen können sich auf der Online-Seite anmelden – jeder mit eigenem Passwort und zweitem Faktor. Du legst sie am PC an, gibst ihnen einen Freischalt-Code und vergibst Rolle und Projekte. Bis dahin hat ein neuer Benutzer keine Rechte.

## Du brauchst
- Die Online-Seite und den Online-Speicher, eingerichtet (Einstellungen › Online-Speicher und Online-Seite).
- Die Workbench am PC – Benutzer verwaltest du nur dort.
- Für jeden Benutzer ein Handy mit einer Authenticator-App (Google Authenticator, Microsoft Authenticator …).

## Schritte
1. **Anlegen** Einstellungen › Benutzer der Online-Seite › Name eintragen › „Anlegen“. Der Name ist das, womit er sich anmeldet (ohne Leerzeichen).
2. **Freischalten** Beim Benutzer „Freischalten“ wählen. Die AMW zeigt einen Freischalt-Code (16 Zeichen, z. B. `K7QM-2XRD-9WFH-T4PB`) – genau einmal, gültig 24 Stunden. Gib ihn dem Benutzer persönlich weiter, mündlich oder im Chat. Er steht nirgends sonst.
3. **Neue Anmeldung** Der Benutzer öffnet die Online-Seite, wählt „Neue Anmeldung“, gibt Name und Code ein, setzt sein Passwort (mindestens 12 Zeichen) und scannt den QR-Code mit seiner App. Mit der ersten Zahl aus der App ist sein Zugang eingerichtet.
4. **Freigeben** Du bekommst die Meldung „Neuer Benutzer … wartet auf Freigabe“ (auch als Push). Bis dahin sieht er nur „Dein Zugang wird geprüft“. Wähle seine Rolle und die Projekte und speichere.

## Diese Werte trägst du ein
| Rolle | Was sie darf |
|---|---|
| Leser | sieht seine Projekte, ändert nichts. |
| Bearbeiter | arbeitet in seinen Projekten: Fragen beantworten, Nachrichten, Aufgaben, Dokumente, Freigaben, Anhalten. |
| Projekt-Admin | dazu die Einstellungen seiner Projekte und ihrer Agenten. |
| System-Admin | alles, in allen Projekten. Am PC bist du immer System-Admin, ebenso mit dem bisherigen Zugang der Online-Seite. |

## Typische Fehler
- **„Name oder Freischalt-Code stimmt nicht“** – Tippfehler, Code abgelaufen oder schon benutzt. Groß- und Kleinschreibung und Bindestriche sind egal. Abhilfe: neu freischalten.
- **Die Zahl aus der App wird nicht angenommen** – Die Uhr des Handys geht falsch. In den Einstellungen des Handys die Uhrzeit automatisch stellen lassen; die Seite nimmt Zahlen bis 30 Sekunden daneben an.
- **„Zeit abgelaufen“ beim QR-Code** – Zwischen Code und QR-Code lagen mehr als 10 Minuten. Noch einmal mit demselben Freischalt-Code beginnen – er gilt, bis der Zugang fertig eingerichtet ist.
- **„Dein Zugang wird geprüft“ bleibt stehen** – Rolle und Projekte fehlen noch. Am PC vergeben, dann lädt der Benutzer die Seite neu.

## Danach
- Passwort vergessen oder Handy verloren: „Neu freischalten“. Passwort und zweiter Faktor werden zurückgesetzt, alle Sitzungen des Benutzers enden, er richtet beides mit dem neuen Code neu ein.
- Sperren wirkt sofort bei seiner nächsten Anfrage. Entsperren gibt den bisherigen Zugang zurück.
- Was ein Benutzer online schreibt, trägt im Verlauf seinen Namen.

## Häufige Fragen
### Warum kein Link per E-Mail?
Die AMW verschickt keine Mails. Der Code geht persönlich weiter; wer nur den Namen kennt, kommt ohne ihn nicht hinein.

### Kann jemand anderes den Code benutzen?
Nur wenn er ihn hat und schneller ist. Dann sieht der richtige Benutzer „schon benutzt“ und meldet sich bei dir – du sperrst, schaltest neu frei und gibst den neuen Code weiter.

### Wo stehen Passwort und zweiter Faktor?
Nur im Online-Speicher, als Hash bzw. Geheimnis – nie auf dem PC, nie im Verlauf. Vom Freischalt-Code steht dort nur ein Hash.
