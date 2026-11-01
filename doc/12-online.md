# 12 · Online (Stufe 2): Workbench im Netz über Hostinger

Wunsch Marcel 01.11. (nach dem Umzug): die Workbench auch im Internet sehen und bedienen, Auslieferung über GitHub auf Hostinger, abgesichert mit Login. Stand: **gebaut und am PC erprobt, noch nicht online** – es fehlen nur die Schritte in §5, die Marcels Konten brauchen.

## 1 Aufbau: Schaufenster + Briefkasten
```
PC (AMW Dienst)                          Turso (EU, Frankfurt)                 Hostinger (PHP)
 amw.db ──Ansichten als fertiges JSON──▶  ansicht   ◀──── liest ─────────────  api.php ◀── Browser/Handy
        ◀──holt alle 15 s, führt aus──── eingang   ◀──── legt Zeile ab ──────  (nach Login)
```
- **Der PC ist aus dem Netz nicht erreichbar.** Er baut die Verbindung selbst nach außen auf; Workbench lokal bleibt 127.0.0.1.
- **Schaufenster:** Der Dienst berechnet dieselben Ansichten wie die lokale Workbench (Start, Fragen, Aufgaben je Sicht, Wissen, Betrieb, Release Notes) und lädt sie nur bei Änderung hoch (höchstens alle 30 s, sonst alle 5 min als Lebenszeichen). Online liegen keine Tabellen, nur diese Ansichten.
- **Briefkasten:** Online erlaubt sind genau vier Aktionen wie lokal – Frage beantworten, Nachricht an Agenten (auftrag/frage/info/korrektur/freigabe), Halt, Weiter. Die Seite legt sie als Zeile in `eingang` ab; der PC führt sie über denselben Code aus wie die lokale Seite (`amw/aktionen.py`), prüft alles noch einmal und meldet das Ergebnis zurück. Jede Zeile wirkt höchstens einmal (Liste `netz_eingang` in amw.db).
- **Eine Seite für beide:** `amw/workbench.html` läuft lokal und online; online holt sie die Daten über `api.php?weg=…`, zeigt „PC-Stand vor x min“ und „n unterwegs“ und hat „Abmelden“. `amw web bauen` kopiert sie nach `web/inc/seite.html` (ein Test meldet, wenn die Kopie veraltet ist).
- **Warum PHP:** Der Online-Teil ist dünn (Login, Ansicht ausliefern, Zeile einwerfen). PHP läuft auf jedem Hostinger-Tarif ohne Dauerprozess, braucht keine npm-Pakete (Passwort-Hash, TOTP, Sitzung sind eingebaut) – weniger Angriffsfläche und Pflege. Der Aufbau hängt nicht an PHP; ein Wechsel auf Node.js betrifft nur `web/`.

## 2 Sicherheit
| Punkt | Umsetzung |
|---|---|
| Anmeldung | Benutzer + Passwort (≥ 14 Zeichen, `password_hash`) **und** 6-stelliger Code aus einer Authenticator-App (TOTP, RFC 6238, ±30 s); jeder Code gilt nur einmal. **Einrichtung beim ersten Anmelden:** Code-Feld leer lassen → die Seite zeigt einen QR-Code (eigener Erzeuger `inc/qr.php`, mit einem QR-Leser geprüft) → scannen → erste Zahl bestätigt; das Geheimnis (160 Bit) liegt danach im Online-Speicher, eine zweite Einrichtung ist gesperrt. Neues Handy: `amw web zweitfaktor-neu` am PC |
| Fehlversuche | Sperre nach 5 Fehlversuchen je Adresse in 15 min oder 20 insgesamt in 60 min; Meldung absichtlich unspezifisch |
| Sitzung | Cookie `__Host-amw`: nur HTTPS, HttpOnly, SameSite=Strict; neue Sitzungs-ID beim Login; Abmeldung nach 30 min ohne Klick, spätestens nach 12 h |
| Schreibschutz | Jede Aktion braucht den Sitzungsschlüssel im Kopf (`X-AMW-Token`) und gleiche Herkunft (Origin); höchstens 120 Einträge je Stunde; Körper ≤ 32 KB |
| Transport | `.htaccess` erzwingt HTTPS, HSTS; CSP wie lokal, `frame-ancestors 'none'`, `noindex` |
| Dateien | Nur `index.php` und `api.php` sind erreichbar; `inc/` und versteckte Dateien gesperrt. Zugangsdaten (`amw-konfig.php`, nie im Repo) werden nach `inc/` hochgeladen; beim ersten Aufruf verschiebt die Seite sie selbst **aus dem Deploy-Ordner hinaus** (neben public_html), weil ein Git-Deploy den Ordner ersetzt (beobachtet 01.11.). Klappt das Verschieben nicht, zeigt die Anmeldeseite einen Hinweis |
| Wirkung | Absender ist immer „Entwickler“, Kanal `netz` – in Antworten und Nachrichten nachvollziehbar; die Adresse steht je Eintrag im Briefkasten |
| Kein Fernzugriff | Keine Befehle, keine Dateien, kein Start/Stopp von Agenten oder Dienst aus dem Netz – nur die vier Aktionen; der Dienst bleibt Marcels Sache (10 §5) |

**Öffentlicher Code:** Das Repo ist öffentlich. Die Sicherheit hängt nur an den Zugangsdaten (Passwort, TOTP-Geheimnis, Turso-Schlüssel), die nie im Repo stehen – nie daran, dass der Code unbekannt ist.

**Restrisiken (bewusst):** Bis zur ersten Einrichtung genügt das Passwort, um den zweiten Faktor einzurichten – darum gleich nach dem Hochladen der Konfiguration selbst anmelden. Wer Marcels Hostinger-Konto, GitHub-Konto (Auslieferung) oder den Turso-Schlüssel der Seite hat, kann im Namen des Entwicklers antworten, Nachrichten schicken oder Halt setzen – darum zweiter Faktor auch bei Hostinger, GitHub und Turso. Die Ansichten (Fragen, Aufgaben, Beschlüsse, Wortlaut, Release Notes, Agentenstand) liegen bei Turso in Frankfurt; Geheimnisse gehören nach den Grundregeln ohnehin nicht hinein. Noch nicht gebaut: Suche online, mehrere Benutzer/Rollen, Passkeys, Anzeige des Briefkasten-Protokolls.

## 3 Kosten (Turso, kostenloser Rahmen)
Hochladen: je Änderungsschub höchstens alle 30 s ein paar Ansichten → grob ≤ 300 000 Schreibzeilen im Monat; Briefkasten: 5 760 Abfragen am Tag auf einem Index. Beides weit im freien Rahmen (→ 06 §6).

## 4a Einstellungen (Zahnrad, ab 0.5.0)
| Bereich | Wo gespeichert | Lokal | Online |
|---|---|---|---|
| Projekt (Takt, Speicher-Grenze) | amw.db, projekt.einstellungen | ändern | ändern (Briefkasten) |
| Agenten | amw.db, agent | ändern | ändern (Briefkasten) |
| Online-Seite (Leerlauf, Sitzung, Sperren) | Online-Speicher, zustand „web_einstellungen“ | ändern | ändern (Briefkasten) |
| Dieser PC (Datenbank, Port, Takte, Brücke) | `%LOCALAPPDATA%\amw\einstellungen.json` | ändern, wirkt nach `amw dienst neustart` | nur ansehen |
| Online-Speicher (Adresse, Schlüssel, Abgleich) | `%LOCALAPPDATA%\amw\turso.json` | ändern (neuer Zugang wird vorher geprüft) | nur ansehen, Schlüssel nie |

Warum PC und Zugang nicht online: Wer sich online anmeldet, soll die AMW nicht auf eine andere Datenbank umbiegen oder den Zugang aussperren können (api.php weist es ab, der PC zusätzlich).

## 4 Bausteine
| Datei | Zweck |
|---|---|
| `amw/abgleich.py` | Speicher (Turso über HTTP, SQLite für Proben), Ansichten bauen, hochladen, Briefkasten; eigener Faden im Dienst |
| `amw/aktionen.py` | die vier erlaubten Aktionen – gemeinsam für lokale Seite und Briefkasten |
| `amw web bauen \| schema \| einmal \| status` | Seite kopieren, Tabellen online anlegen, ein Abgleich von Hand, Stand |
| `web/index.php`, `web/api.php`, `web/inc/lib.php`, `web/.htaccess` | Online-Teil für Hostinger (PHP ≥ 8.1 mit curl, mbstring) |
| `web/inc/einrichtung.php` | Einrichtungs-Assistent (Turso, Zugang, QR-Code); schreibt die Konfiguration selbst |
| `amw web einrichten` | am PC: Turso-Zugang (Schlüssel verdeckt), Abgleich an, Wächter neu starten |
| `tests/test_abgleich.py` | Hochladen nur bei Änderung, Briefkasten einmalig, Fehler zurückgemeldet, Seite aktuell |

Am PC erprobt (01.11., Kopien, `php -S`): Login-Seite; API ohne Login gesperrt; falsches Passwort / falscher Code abgewiesen; Login mit Code; Ansichten mit PC-Stand; Aufgaben-Filter; Antwort ohne Schlüssel und von fremder Herkunft abgewiesen; Antwort → Briefkasten → am PC beantwortet (Kanal netz); beantwortete Frage online ausgeblendet; Nachricht kommt an; „stopp“ aus dem Netz abgewiesen; Rückmeldung je Zeile; kein Doppel; Abmelden; Sperre nach Fehlversuchen – alles grün.

## 5 Einrichtung (für jeden Anwender, ohne Dateien und Terminal-Geheimnisse)
Wie in der README „Online in 4 Schritten“: Turso-Datenbank + Schlüssel → am PC `amw web einrichten` → beim Hoster Git-Bereitstellung aus Zweig `web` → Seite öffnen, **Einrichtungs-Assistent** (`web/inc/einrichtung.php`):

| Schritt | Was passiert | Schutz |
|---|---|---|
| 1 Turso verbinden | Adresse + Schlüssel; die Seite prüft die Verbindung und legt ihre Tabellen an | Nur wer den Schlüssel hat, kann eine frisch bereitgestellte Seite einrichten. Es werden nur `*.turso.io`-Adressen angefragt (kein Umweg ins interne Netz). |
| 2 Zugang | Benutzer (4–40 Zeichen) + Passwort (≥ 14, zweimal) | gespeichert nur als `password_hash` |
| 3 Zweiter Faktor | QR-Code (eigener Erzeuger, mit QR-Leser geprüft) scannen, erste Zahl bestätigt; gibt es schon einen zweiten Faktor (Umzug, verlorene Konfiguration): Zahl aus der vorhandenen App | 5 falsche Zahlen → von vorn; Assistent verfällt nach 30 min |

Danach schreibt die Seite ihre Konfiguration selbst **außerhalb des Deploy-Ordners** (der Hoster ersetzt den Ordner bei jedem Deploy – beobachtet 01.11.) und meldet an. Darf sie dort nicht schreiben, legt sie die Datei in `inc/` ab (von außen gesperrt) und sagt deutlich, dass der nächste Deploy sie löscht. Der Assistent erscheint nur, solange keine Konfiguration da ist.

Geprüft (01.11., `php -S` mit Ordnern wie beim Hoster, QR mit zxing gelesen): frische Seite → Assistent; Turso verbunden; zu kurzes / ungleiches Passwort abgewiesen; QR gelesen; falsche Zahl abgewiesen; richtige Zahl → eingerichtet + angemeldet; Konfiguration außerhalb, nur Hash; Neu-Deploy → Anmeldung statt Assistent; Login mit Passwort + Zahl; verlorene Konfiguration bei vorhandenem zweiten Faktor → kein neuer QR, Zahl aus der App; 5 falsche Zahlen → Anfang. Turso-Weg der Seite gegen die echte Datenbank: richtiger Schlüssel → Tabellen gefunden, falscher → abgelehnt (Turso antwortet 400). TOTP gegen RFC-6238-Prüfwerte. Herkunft im echten Browser (Edge): Formulare senden mit `Referrer-Policy: same-origin` die richtige Herkunft (mit `no-referrer` „null“ – darum umgestellt).

Abschalten jederzeit: `"abgleich": false` (PC lädt nichts mehr hoch und holt nichts mehr ab); online sperren: Hostinger-Ordner leeren oder in Turso „Block Reads/Writes“.
