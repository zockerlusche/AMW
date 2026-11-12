# Online: die Workbench im Netz

Optional. Dieselbe Workbench wie am PC, erreichbar über eine eigene (Sub-)Domain – zum Lesen und für Antworten,
Freigaben, Nachrichten und Halt von unterwegs. Geschützt mit Passwort und zweitem Faktor (Authenticator-App).

## 1 Aufbau: Schaufenster + Briefkasten
```
PC (Wächter)                               Online-Speicher (Turso)                Webhoster (PHP)
 amw.db ──fertige Ansichten (JSON)───────▶  ansicht   ◀────── liest ────────────  api.php ◀── Browser / Handy
        ◀──holt alle 15 s, führt aus─────  eingang   ◀────── legt Zeile ab ─────  (nach Anmeldung)
 dokumente/ ──Dateien „auch online“─────▶  datei     ────── holt einmal ab ───▶  amw-dateien/ (neben der Konfiguration)
```
- **Der PC ist aus dem Netz nicht erreichbar.** Er baut die Verbindung selbst nach außen auf.
- **Schaufenster:** Der Wächter berechnet dieselben Ansichten wie die Workbench (Start, Fragen, Aufgaben, Planung,
  Verlauf, Wissen, Betrieb, Release Notes, Agenten, Dokumente mit Texten, Suchindex) und lädt sie nur bei Änderung hoch (höchstens alle 30 s,
  sonst alle 5 min als Lebenszeichen). Online liegen keine Tabellen, nur diese Ansichten.
- **Briefkasten:** Online erlaubt sind: Frage beantworten, Nachricht an Agenten (Auftrag, Frage, Info, Korrektur,
  Freigabe), Nachrichten an dich als gelesen markieren, Halt, Weiter, Projekt-/Agenten-/Seiten-Einstellungen,
  Planung (Freigaben, Leitbild, Bögen, Risiken, Rückblick), Aufgaben (eigene erledigt/später, Antwort an den
  Zuständigen), Dokumente (kommentieren, überarbeiten lassen, zuordnen,
  archivieren, Datei online anfordern, Text berichtigen, hochgeladene Datei anlegen). Die Seite legt eine Zeile ab; der PC prüft und führt sie mit
  demselben Code aus wie lokal (`amw/aktionen.py`) – höchstens einmal – und meldet das Ergebnis zurück.
- **Nur am PC** (online abgewiesen, auch vom PC selbst): Einstellungen dieses PCs, Online-Zugang, Push-Zugänge,
  Agenten-Profile, Agenten starten/beenden, Push-Probe, Dokument endgültig löschen.
- **Dateien der Dokumente** (Bilder, Mockups, PDF, Office) sind nur online, wenn das Dokument auf „auch online“ steht
  (am PC, vom Agenten mit `--online`, unterwegs „Online anfordern“ oder von selbst nach Zahnrad › Projekt › „Dateien online“: nur auf Wunsch | Bilder und Mockups | alle). Der PC legt die Datei in Teilen im Speicher ab
  (`datei`, `datei_teil`); die Seite holt sie beim nächsten Aufruf einmal ab, prüft Größe und Prüfsumme, legt sie in
  `amw-dateien/` neben ihre Konfiguration (außerhalb des Deploy-Ordners, per `.htaccess` gesperrt) und löscht die Teile.
  Ausgeliefert wird sie nur nach der Anmeldung, mit Browser-Cache. Steht ein Dokument wieder „nur am PC“, meldet der PC
  die Datei ab und die Seite löscht ihre Kopie (spätestens nach 10 min). Dafür braucht der PC weder die Adresse der Seite
  noch einen weiteren Schlüssel. Texte (Markdown) gehen immer als Ansicht mit.
- **Hochladen vom Handy** (`hoch`, `hoch_teil`): Der Browser rechnet Fotos neu (ohne Standort/EXIF) und schickt die Datei in
  Teilen zu 192 KB mit Prüfsumme an `/api/hochladen`. Die Seite legt die Teile in den Speicher und zugleich in ihre Ablage;
  ist alles da, meldet `/api/dokument/neu` die Datei über den Briefkasten. Der PC holt die Teile, prüft Größe, Prüfsumme und
  Inhalt (Format, Geheimnis-Muster), legt das Dokument an und löscht die Teile. Die Kopie auf dem Webspace gilt als
  abgelegt, steht das Dokument nicht online, meldet der PC sie wieder ab. Grenzen: 25 MB je Datei, 100 MB unterwegs,
  60 Uploads je Stunde; Liegengebliebenes ist nach einem Tag weg.
- **Gespräch je Agent** (nur auf Wunsch): Öffnest du online das Gespräch eines Agenten, setzt die Seite im Speicher
  `zustand` „gespraech:<Agent>“ auf die Uhrzeit (höchstens einmal je Minute) und zeigt bis zur ersten Lieferung „Der PC holt
  das Gespräch …“. Solange dieser Wunsch jünger als 10 Minuten ist, legt der PC alle 15 s die letzten 120 Einträge als
  Ansicht ab. Das sind nur Texte und die Namen der Arbeitsschritte, ohne Eingaben und Ergebnisse, mit verdeckten
  Geheimnissen. Danach löscht er die Ansicht wieder. Ältere Einträge gibt es nur am PC. *In Claude öffnen* steht online
  genauso da, der Link funktioniert nur mit deinem Claude-Konto.
- **Mehrere Projekte, auch auf mehreren Rechnern** ([plan-projektwahl.md](plan-projektwahl.md)): Jede Ansicht liegt
  unter `<Kennung>:<Weg>`; die Kennung ist `projekt.uid`. Das Verzeichnis `projekt` nennt alle Projekte mit Rechner,
  Farbe, offenen Fragen und „zuletzt gesehen“. Jeder Rechner trägt nur seine eigenen Projekte ein.
  - Die Seite fragt mit `&projekt=<Kennung>`; ohne Angabe gilt das erste Projekt im Verzeichnis.
  - Befehle vom Handy tragen die Kennung (`eingang.projekt`), und nur der Rechner des Projekts führt sie aus.
  - Gespräche heißen `gespraech:<Kennung>:<Agent>`, „zuletzt gesehen“ `pc_gesehen_utc:<Kennung>`.
  - Dateien gehören über `datei_projekt` zu Projekten. Eine Datei verschwindet erst, wenn kein Projekt sie mehr nennt.
  - Einen zweiten Rechner richtest du wie den ersten ein und gibst ihm denselben Online-Speicher, siehe
    [installation.md](installation.md) „Weiterer Rechner“.
- **Eine Seite für beide:** `amw/workbench.html`; `amw web bauen` kopiert sie nach `web/inc/seite.html`.

## 1a Eigener Server statt Turso (Betriebsart „eigener Server im Firmennetz“)
Der Online-Speicher kann auch ein **eigener libSQL-Server** (sqld) im Firmennetz sein – derselbe Server, auf dem Turso
läuft, mit demselben Protokoll (HTTP `/v2/pipeline`, Schlüssel als Bearer-Token). Geprüft mit sqld 0.24.32.
- **Schlüssel:** `amw speicher schluessel --url https://amw-db.firma.lan [--ca firma.pem]` erzeugt ein Ed25519-Paar
  (Python-Paket `cryptography`, sonst `openssl` ≥ 3), schreibt den **öffentlichen** Schlüssel als
  `amw-speicher-oeffentlich.pem` (für `sqld --auth-jwt-key-file`), trägt den Zugang am PC ein (Synchronisierung noch aus)
  und zeigt einmal den Schlüssel für die Seite. Der private Schlüssel wird verworfen. Der Server prüft kein Ablaufdatum:
  ungültig werden die Schlüssel erst mit einem neuen Paar. Im Token steht kein `id` – sqld läse es als Datenbank-Namen.
- **PC:** Einstellungen › Speicher und Synchronisierung › Anbieter „Eigener libSQL-Server“, Adresse `https://…`
  (`http://` nur im Firmennetz, mit Warnung), optional das Zertifikat der Firmen-CA als PEM-Datei.
- **Seite:** in `amw-konfig.php` `'speicher_url' => 'https://amw-db.firma.lan'`, `'speicher_token' => '…'`, optional
  `'speicher_ca' => '/pfad/firma-ca.pem'`. Die Adresse steht nur in dieser Datei – kein Formular im Netz kann sie setzen.
- Anleitung zum Aufbau (Docker, https davor, Paket für den Webserver) folgt mit Stufe R3b/R3c.

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
Abschalten: Zahnrad › Speicher und Abgleich › Abgleich aus (oder `"abgleich": false` in `turso.json`); online sperren:
Ordner beim Hoster leeren oder in Turso Lesen/Schreiben blockieren.

## 3 Sicherheit
| Punkt | Umsetzung |
|---|---|
| Anmeldung | Benutzer + Passwort (`password_hash`) **und** 6-stelliger Code (TOTP, RFC 6238, ±30 s, jeder Code nur einmal) – oder Firmen-Anmeldung (unten) |
| Firmen-Anmeldung | OpenID Connect, Authorization Code Flow mit PKCE (S256), `state` und `nonce` im eigenen Cookie `__Host-amw-sso` (SameSite=Lax, 10 min, einmal); ID-Token: Signatur RS256/384/512 mit dem Schlüssel des Anbieters (JWKS), Aussteller genau wie eingestellt (kein `common`), Empfänger = Client-ID, Ablauf ±120 s, `nonce`; nur angelegte Benutzer – beim ersten Mal über die E-Mail, danach fest an Aussteller + `sub` gebunden (neue E-Mail oder neu freischalten löst die Bindung); kein zweiter Faktor in der AMW. Client-Secret oder Zertifikat (`private_key_jwt`) nur in `amw-konfig.php` beim Webhoster; eingetragen von einem System-Admin auf `sso.php?einrichten`. Hilfe: doc/hilfe/firmen-anmeldung.md |
| Fehlversuche | Sperre nach 5 Fehlversuchen je Adresse in 15 min oder 20 insgesamt in 60 min (einstellbar) |
| Sitzung | Cookie `__Host-amw`: nur HTTPS, HttpOnly, SameSite=Strict; neue Sitzungs-ID beim Anmelden; Abmeldung nach Leerlauf (Vorgabe 30 min), spätestens nach 12 h |
| Schreibschutz | Sitzungsschlüssel im Kopf (`X-AMW-Token`) und gleiche Herkunft; höchstens 120 Einträge je Stunde; Körper ≤ 32 KB |
| Transport | `.htaccess` erzwingt HTTPS, HSTS; Content-Security-Policy, `frame-ancestors 'none'`, `noindex`. Einbetten verbietet die Seite selbst (`X-Frame-Options: DENY`); nur Dokument-Dateien (Mockup, PDF, Video) dürfen in der eigenen Seite erscheinen (`SAMEORIGIN`, `frame-ancestors 'self'`, weiter abgeschottet) – die `.htaccess` setzt diese Angabe deshalb nicht noch einmal |
| Dateien | Nur `index.php`, `api.php` und `sso.php` (Firmen-Anmeldung) sind erreichbar; `inc/` und versteckte Dateien gesperrt |
| Wirkung | Absender ist immer „Entwickler“, Kanal `netz`; der PC prüft jede Zeile noch einmal |
| Dokument-Dateien | nur nach Anmeldung; Mockups (HTML) und SVG abgeschottet (CSP `sandbox`), Office nur als Download; Ablage außerhalb des Web-Ordners |
| Gespräch je Agent | nur auf Wunsch und 10 Minuten lang, nur Text und Schrittnamen, Geheimnis-Muster verdeckt; die Kennung muss ein bekannter Agent sein |
| Hochladen | nur angemeldet mit CSRF-Schlüssel; Formatliste, Größen- und Mengengrenzen auf der Seite, Prüfsumme und Geheimnis-Prüfung am PC |

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
| `web/sso.php`, `web/inc/sso.php` | Firmen-Anmeldung (OpenID Connect) und Eintragen ihres Geheimnisses |
| `web/inc/einrichtung.php`, `web/inc/qr.php` | Einrichtungs-Assistent, QR-Code (eigener Erzeuger) |
| `amw/abgleich.py` | Hochladen und Abholen im Wächter, Dateien der Dokumente |
| `amw web einrichten · bauen · schema · einmal · status · zweitfaktor-neu · sso` | Zugang, Seite kopieren, Tabellen, ein Abgleich von Hand, Stand, neues Handy, Firmen-Anmeldung |
