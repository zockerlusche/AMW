# AMW – Agentenmanagement Workbench

<picture><source media="(prefers-color-scheme: dark)" srcset="doc/logo/amw-logo-dunkel.svg"><img src="doc/logo/amw-logo-hell.svg" alt="AMW-Logo: A, M und W als eine Linie mit drei Knoten" width="160"></picture>

**Ein Leitstand für einen Menschen, der Software mit einem Team aus KI-Agenten baut.** AMW verbindet mehrere
[Claude-Code](https://code.claude.com)-Sitzungen – meist ein Team-Lead-Agent und einige Coding-Agenten – zu einem Team:
Nachrichten zwischen den Agenten mit automatischem Wecken, Fragen an dich mit Optionen und Empfehlung, Projektplanung
mit Freigaben und Prognose, Wissen, Überwachung und eine Workbench im Browser, auch vom Handy.

- **Läuft auf deinem Windows-PC**, nur mit Python (Standardbibliothek) und SQLite – keine Pakete, kein Cloud-Zwang.
- **Agenten-Bus:** `amw posten / lesen / erledigt`; ein Wächter weckt schlafende Agenten über Claude Codes eigene
  Nachrichten-Pipe, sobald etwas für sie ankommt.
- **Fragen an den Menschen** mit Optionen, Empfehlung, Begründung und Gesprächsverlauf – beantwortet in der Workbench
  oder unterwegs.
- **Projektplanung:** Leitbild, Meilensteine („Bögen“) mit Abnahmekriterium, Spezifikation mit deiner Freigabe,
  Schritte mit Abhängigkeiten und Kriterien, Monte-Carlo-Prognose, Plan-Check, Risiken, Rückblick.
- **Überblick:** was jeder Agent gerade tut, ob er auf eine Freigabe wartet, Kontext-Füllstand, Nutzungsgrenzen,
  Kosten; Verlauf aller Ereignisse; „Seit du weg warst“.
- **Steuern:** Agenten per Klick starten, fortsetzen, beenden; Neustart nach Absturz; Halt für alle.
- **Betrieb:** Rechen-Läufe mit Warteschlange, Prüfungen (grün/rot je Commit), Überwachung von Projekt-Servern,
  Stillstand-Warnungen, Push aufs Handy (ntfy, Pushover, Telegram).
- **Online (optional):** dieselbe Workbench im Netz über einen PHP-Webhoster und eine kostenlose Turso-Datenbank,
  mit Passwort und zweitem Faktor. Der PC bleibt aus dem Netz unerreichbar.

## Schnellstart
```
git clone https://github.com/zockerlusche/AMW.git C:\amw
C:\amw\bin\amw.cmd einrichten
```
Der Assistent legt Datenbank, Projekt und Agenten an, richtet deinen Projektordner ein (Hooks, Statusline-Brücke),
schreibt ein Startskript und richtet den Wächter ein. Danach: http://127.0.0.1:8780/ öffnen.
Ausführlich: **[doc/installation.md](doc/installation.md)**.

## Dokumentation
| | |
|---|---|
| [Überblick](doc/ueberblick.md) | Begriffe und wie die Teile zusammenspielen |
| [Installation](doc/installation.md) | Schritt für Schritt, Aktualisieren, Entfernen |
| [Betrieb](doc/betrieb.md) | Arbeiten mit der Workbench und den Agenten, Sicherung |
| [Befehle](doc/befehle.md) | alle `amw`-Befehle |
| [Planung](doc/anleitung-planung.md) | Projekte planen: Leitbild, Bögen, Spezifikation, Prognose |
| [Mehrere Projekte](doc/anleitung-projekte.md) | neues Projekt anlegen, Trennung, weiterer Rechner |
| [Push aufs Handy](doc/anleitung-push.md) | ntfy, Pushover, Telegram |
| [Online](doc/online.md) | Workbench im Netz einrichten |
| [Architektur](doc/architektur.md) | Bausteine, Datenfluss, Datenmodell |
| [Sicherheit](doc/sicherheit.md) | Vertrauensmodell, Geheimnisse, Schutzmaßnahmen |
| [Fehlerbehebung](doc/fehlerbehebung.md) | wenn etwas nicht geht |
| [Änderungen](CHANGELOG.md) | was in welcher Version neu ist |

## Voraussetzungen
Windows 10/11 · Python ≥ 3.11 · Claude Code (mit `claude` im Pfad) · Git · empfohlen: Windows Terminal.
Für den Online-Teil: ein Webhoster mit PHP ≥ 8.1 (curl, mbstring) und HTTPS, ein kostenloses Konto bei turso.tech.

## Lizenz
[MIT](LICENSE) – frei zu benutzen, zu ändern und weiterzugeben. Zweig `web` enthält nur den Online-Teil (für das Hosting).

---

### English
AMW is a control room for one person building software with a team of AI agents (Claude Code sessions): a message bus
with automatic wake-up, questions to the human with options and a recommendation, project planning with approvals and
a forecast, knowledge, monitoring, push notifications and a browser workbench (also online, behind password + 2FA).
Windows, Python standard library and SQLite only. Start with `amw einrichten` – see [doc/installation.md](doc/installation.md)
(German; the user interface is German and English).
