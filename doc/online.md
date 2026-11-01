# Online: die Workbench im Netz

Optional. Dieselbe Workbench wie am PC, erreichbar über eine eigene (Sub-)Domain – zum Lesen und für Antworten,
Freigaben, Nachrichten und Halt von unterwegs. Geschützt mit Passwort und zweitem Faktor (Authenticator-App).

## 1 Aufbau: Schaufenster + Briefkasten
```
PC (Wächter)                               Online-Speicher (Turso)                Webhoster (PHP)
 amw.db ──fertige Ansichten (JSON)───────▶  ansicht   ◀────── liest ────────────  api.php ◀── Browser / Handy
        ◀──holt alle 15 s, führt aus─────  eingang   ◀────── legt Zeile ab ─────  (nach Anmeldung)
```
- **Der PC ist aus dem Netz nicht erreichbar.** Er baut die Verbindung selbst nach außen auf.
- **Schaufenster:** Der Wächter berechnet dieselben Ansichten wie die Workbench (Start, Fragen, Aufgaben, Planung,
  Verlauf, Wissen, Betrieb, Release Notes, Agenten, Suchindex) und lädt sie nur bei Änderung hoch (höchstens alle 30 s,
  sonst alle 5 min als Lebenszeichen). Online liegen keine Tabellen, nur diese Ansichten.
- **Briefkasten:** Online erlaubt sind: Frage beantworten, Nachricht an Agenten (Auftrag, Frage, Info, Korrektur,
  Freigabe), Nachrichten an dich als gelesen markieren, Halt, Weiter, Projekt-/Agenten-/Seiten-Einstellungen,
  Planung (Freigaben, Leitbild, Bögen, Risiken, Rückblick). Die Seite legt eine Zeile ab; der PC prüft und führt sie mit
  demselben Code aus wie lokal (`amw/aktionen.py`) – höchstens einmal – und meldet das Ergebnis zurück.
- **Nur am PC** (online abgewiesen, auch vom PC selbst): Einstellungen dieses PCs, Online-Zugang, Push-Zugänge,
  Agenten-Profile, Agenten starten/beenden, Push-Probe.
- **Eine Seite für beide:** `amw/workbench.html`; `amw web bauen` kopiert sie nach `web/inc/seite.html`.

## 2 Einrichten (etwa 15 Minuten)
Voraussetzungen: AMW läuft am PC (Wächter eingerichtet); ein Webhoster mit **PHP ≥ 8.1** (Erweiterungen curl, mbstring)
und **HTTPS**; ein kostenloses Konto bei **turso.tech**.

1. **Turso:** Datenbank anlegen (Region in deiner Nähe), dann bei der Datenbank „Create Token“ (Lesen + Schreiben).
   Adresse (`libsql://….turso.io`) und Schlüssel bereithalten – den Schlüssel nirgends speichern oder weitergeben.
2. **PC:** `amw web einrichten` – fragt Adresse und Schlüssel (verdeckt), prüft die Verbindung, legt die Tabellen an,
   schaltet den Abgleich ein und startet den Wächter neu. Der Zugang liegt danach nur in `%LOCALAPPDATA%\amw\turso.json`.
3. **Hoster:** Git-Bereitstellung aus diesem Repo (oder deinem Fork), **Zweig `web`** (enthält nur die Web-Dateien), in
   den Ordner der (Sub-)Domain; SSL einschalten. Ohne Git: den Inhalt des Ordners `web/` hochladen.
4. **Browser:** Seite öffnen – der Einrichtungs-Assistent:

| Schritt | Was passiert | Schutz |
|---|---|---|
| 1 Online-Speicher verbinden | Adresse + Schlüssel; die Seite prüft die Verbindung | Nur wer den Schlüssel hat, kann eine frisch bereitgestellte Seite einrichten; nur `*.turso.io`-Adressen werden angefragt |
| 2 Zugang | Benutzer (4–40 Zeichen) + Passwort (≥ 14 Zeichen, zweimal) | gespeichert nur als `password_hash` |
| 3 Zweiter Faktor | QR-Code mit der Authenticator-App scannen, erste Zahl bestätigen | 5 falsche Zahlen → von vorn; der Assistent verfällt nach 30 min |

Danach schreibt die Seite ihre Konfiguration **außerhalb des Bereitstellungs-Ordners** (ein Git-Deploy ersetzt den
Ordner) und meldet dich an. Darf sie dort nicht schreiben, legt sie die Datei in `inc/` ab (von außen gesperrt) und
sagt, dass die nächste Bereitstellung sie löscht. Der Assistent erscheint nur, solange keine Konfiguration da ist.

Neues Handy: `amw web zweitfaktor-neu` am PC, dann beim nächsten Anmelden neu scannen.
Abschalten: Zahnrad › Online-Speicher › Abgleich aus (oder `"abgleich": false` in `turso.json`); online sperren:
Ordner beim Hoster leeren oder in Turso Lesen/Schreiben blockieren.

## 3 Sicherheit
| Punkt | Umsetzung |
|---|---|
| Anmeldung | Benutzer + Passwort (`password_hash`) **und** 6-stelliger Code (TOTP, RFC 6238, ±30 s, jeder Code nur einmal) |
| Fehlversuche | Sperre nach 5 Fehlversuchen je Adresse in 15 min oder 20 insgesamt in 60 min (einstellbar) |
| Sitzung | Cookie `__Host-amw`: nur HTTPS, HttpOnly, SameSite=Strict; neue Sitzungs-ID beim Anmelden; Abmeldung nach Leerlauf (Vorgabe 30 min), spätestens nach 12 h |
| Schreibschutz | Sitzungsschlüssel im Kopf (`X-AMW-Token`) und gleiche Herkunft; höchstens 120 Einträge je Stunde; Körper ≤ 32 KB |
| Transport | `.htaccess` erzwingt HTTPS, HSTS; Content-Security-Policy, `frame-ancestors 'none'`, `noindex` |
| Dateien | Nur `index.php` und `api.php` sind erreichbar; `inc/` und versteckte Dateien gesperrt |
| Wirkung | Absender ist immer „Entwickler“, Kanal `netz`; der PC prüft jede Zeile noch einmal |

Der Code ist öffentlich; die Sicherheit hängt nur an den Zugangsdaten (Passwort, TOTP-Geheimnis, Turso-Schlüssel), die
nie im Repo stehen. Wer dein Hoster-, GitHub- oder Turso-Konto übernimmt, kann im Namen des Entwicklers handeln –
darum auch dort einen zweiten Faktor einrichten. Was online liegt (Fragen, Aufgaben, Beschlüsse, Planung …), liegt beim
Speicher-Anbieter; Geheimnisse gehören ohnehin nie in AMW.

## 4 Kosten
Der kostenlose Rahmen von Turso reicht: Hochladen höchstens alle 30 s nur geänderter Ansichten, der Briefkasten
alle 15 s eine Abfrage auf einem Index.

## 5 Dateien
| Datei | Zweck |
|---|---|
| `web/index.php`, `web/api.php`, `web/inc/lib.php`, `web/.htaccess` | Anmeldung, Ansichten, Briefkasten |
| `web/inc/einrichtung.php`, `web/inc/qr.php` | Einrichtungs-Assistent, QR-Code (eigener Erzeuger) |
| `amw/abgleich.py` | Hochladen und Abholen im Wächter |
| `amw web einrichten · bauen · schema · einmal · status · zweitfaktor-neu` | Zugang, Seite kopieren, Tabellen, ein Abgleich von Hand, Stand, neues Handy |
