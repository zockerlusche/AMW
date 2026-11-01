# Sicherheit

## 1 Vertrauensmodell
- **Am PC** laufen Wächter, Workbench und Agenten unter **deinem Windows-Benutzer**. Wer auf diesem Benutzer Programme
  ausführen kann – auch ein Agent –, kann `amw` mit jeder Kennung aufrufen. Die Prüfungen in AMW (nur der Lead darf
  Beschlüsse, nur der Mensch gibt Spezifikationen frei, Kreise in Abhängigkeiten …) schützen vor **Versehen**, nicht vor
  Absicht. Das ist dasselbe Vertrauen, das du Claude Code ohnehin gibst.
- Die **Workbench** lauscht nur auf `127.0.0.1` (exklusiv – ist der Port belegt, startet sie nicht). Schreiben braucht
  einen Schlüssel, der bei jedem Start neu gewürfelt und nur in die Seite eingebettet wird.
- **Online** ist nur ein Spiegel mit Briefkasten; der PC ist aus dem Netz nicht erreichbar ([online.md](online.md)).

## 2 Geheimnisse – wo sie liegen, wo nie
| Geheimnis | liegt | nie |
|---|---|---|
| Schlüssel der Claude-Code-Pipe je Sitzung | `%LOCALAPPDATA%\amw\sitzungen\<Kennung>.json` | Datenbank, Online, Repo |
| Online-Speicher (Turso-Schlüssel) | `%LOCALAPPDATA%\amw\turso.json`; online in der Konfiguration außerhalb des Web-Ordners | Datenbank, Repo, Ausgaben |
| Push-Zugänge (ntfy-Kanal, Pushover, Telegram) | `%LOCALAPPDATA%\amw\push.json` | Datenbank, Online, Repo; Anzeige nur „gespeichert“ |
| Passwort / TOTP der Online-Seite | Hash bzw. Geheimnis beim Hoster und im Online-Speicher | Repo |

**Grundregel für dein Team:** Passwörter, Schlüssel, Fernwartungs-IDs gehören nie in Nachrichten, Aufgaben, Beschlüsse
oder Notizen – sie würden online gespiegelt und von Agenten gelesen.

## 3 Schutz des Wächters vor den Agenten
`amw einrichten` trägt in den Projektordner Sperr-Regeln ein, die Claude Code auch im Modus „alles erlauben“ beachtet:
Agenten können die geplante Aufgabe „AMW Dienst“ nicht beenden/ändern und `amw dienst entfernen|einrichten` nicht aufrufen.
`amw dienst neustart` bleibt erlaubt.

## 4 Was AMW selbst startet
- **Projekt-Server** nur mit Befehl, den du per Kommandozeile am PC angemeldet hast (nie über Online oder die Datei-Brücke).
- **Agenten** nur auf Klick am PC, per `amw agent starten` oder – wenn im Profil erlaubt – nach einem erkannten Absturz
  (Fenster offen, kein bewusstes Ende, höchstens 3 je Stunde). Ein geschlossenes Fenster wird nie neu geöffnet.
- **Beenden** tut AMW nie von sich aus. Andere Agenten beendet nur der Mensch in der Workbench am PC; an der
  Kommandozeile kann ein Agent nur seine eigene Sitzung beenden, über die Datei-Brücke und online gar keine.
  Projekt-Server werden nur gestartet, nie beendet.
- Profile (Ordner, Startsatz, Rechte) sind nur am PC änderbar, weil sie in einen Befehl auf diesem PC eingehen.

## 5 Push
Meldungen enthalten nur Hinweise („Neue Frage F12 von TL“) und einen Link; der Inhalt steht hinter der Anmeldung.
Der ntfy-Kanal wird zufällig erzeugt (≥ 128 Bit) und wirkt wie ein Passwort. Fehlertexte enthalten nie das Telegram-Token.

## 6 Lücken melden
Bitte ohne öffentliches Issue an den Betreiber des Repositories (GitHub-Profil); beschreibe die Art des Problems,
keinen fertigen Angriff.
