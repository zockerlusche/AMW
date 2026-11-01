# Recherche: Push-Benachrichtigungen – Grundlage für Stufe B

Stand 01.11.2026. „(u)“ = nicht verifiziert.

## Anbieter (alle mit urllib)
**ntfy** (docs.ntfy.sh/publish): JSON an die Wurzel-URL `POST https://ntfy.sh/` mit `topic`, `message`, `title`,
`tags[]`, `priority` 1–5, `click`, `actions[]` (≤ 3; `{"action":"view","label":…,"url":…,"clear":true}`), `markdown`.
JSON umgeht Umlaut-Probleme in Headern. Anmeldung `Authorization: Bearer tk_…` oder Basic. Text ≤ 4096 Bytes.
ntfy.sh anonym: 250 Nachrichten/Tag je IP, Burst 60, dann 1 je 5 s. `X-Cache: no` = nicht speichern; `X-Firebase: no`
verzögert Android (nicht setzen). Topic-Name = Passwort → ≥ 128 Bit Zufall (`secrets.token_urlsafe(24)`).
Handy: App (Android/iOS), Topic abonnieren, Link `ntfy://ntfy.sh/<topic>`.

**Pushover** (pushover.net/api): `POST https://api.pushover.net/1/messages.json` (Formular): `token`, `user`, `message`,
`title`, `url` (≤ 512), `url_title` (≤ 100), `priority` −2..2 (2 = Notfall mit `retry` ≥ 30, `expire` ≤ 10800),
`html=1`, `ttl`. Nachricht ≤ 1024, Titel ≤ 250; 10 000/Monat. Antwort `{"status":1}`; **4xx nie wiederholen**, 5xx/keine
Antwort nach ≥ 5 s. Prüfen: `POST /1/users/validate.json`.

**Telegram** (core.telegram.org/bots/api): `POST https://api.telegram.org/bot<TOKEN>/sendMessage` JSON: `chat_id`,
`text` (≤ 4096), `parse_mode: "HTML"` (`html.escape`), `disable_notification`, `link_preview_options:{is_disabled:true}`,
`reply_markup:{inline_keyboard:[[{text, url}]]}` (nur https). Antwort `ok`/`description`/`parameters.retry_after`.
Einrichtung: @BotFather `/newbot` → Token; dem Bot schreiben; `getUpdates` → `message.chat.id`. ~1 Nachricht/s je Chat.
Token steht in der URL → Fehlertexte bereinigen.

## Gestaltung (GitHub, PagerDuty, Opsgenie, Slack, Linear, Sentry)
- Hauptschalter + Schalter je Ereignis; Dringlichkeit je Ereignis.
- Ruhezeiten in lokaler Zeit; währenddessen sammeln, danach als Sammelmeldung; dringend (Halt, Server aus) kommt durch.
- Doppelte vermeiden: Schlüssel (Ereignis, Objekt); gleiche Warnung höchstens alle 30 min; „wieder OK“ einmal.
- Bündeln: mehrere Fragen in kurzer Folge → eine Meldung „3 neue Fragen“; Obergrenze je Stunde, Rest in Sammelmeldung.
- Erinnern: unbeantwortete Frage nach 60 min einmal erneut.
- Probe-Knopf je Anbieter mit API-Antwort; Versandprotokoll (ohne Geheimnisse).
- Wiederholung nur bei Netzfehler/5xx/429 mit Backoff (5 s → 30 s → 2 min, ≤ 3).
- Nur Metadaten + Link auf die eigene Seite (Login schützt den Inhalt).
- Geheimnisse nur in einer Datei des Benutzers außerhalb von Repo und Datenbank.

| Ereignis | Vorgabe | ntfy / Pushover / Telegram |
|---|---|---|
| Neue Frage an dich | an | 4 / 0 / laut |
| Agent wartet auf Freigabe/Eingabe | an, nach 5 min | 4 / 0 / laut |
| Halt | an | 5 / 1 / laut |
| Warnung (Server, Stillstand, Lauf) | an | 4 / 1 / laut |
| Nachricht an dich | an | 3 / 0 / laut |
| Rückblick täglich | an, 08:00 | 2 / −1 / stumm |

Quellen: docs.ntfy.sh/{publish,config,faq,subscribe/phone} · pushover.net/api · core.telegram.org/bots/{api,faq} ·
docs.github.com (notifications) · support.pagerduty.com · support.atlassian.com/opsgenie · slack.com/help · linear.app/docs/notifications · sentry.
