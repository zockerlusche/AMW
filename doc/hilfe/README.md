# Schritt-für-Schritt-Hilfen

Jede Datei in diesem Ordner ist zugleich **Anleitung im Repo** und **Hilfe in der Workbench**: Ein „? Anleitung“ neben
einer Einstellung öffnet genau diesen Text als Dialog – am PC, online und am Handy. So laufen Doku und Hilfe nicht
auseinander.

| Datei | Thema | Wo der Knopf steht |
|---|---|---|
| [neues-projekt.md](neues-projekt.md) | Neues Projekt – Schritt für Schritt | Projekt-Auswahl, Einstellungen › Projekt |
| [online-speicher-turso.md](online-speicher-turso.md) | Online-Speicher bei Turso anlegen | Einstellungen › Speicher und Abgleich |
| [ntfy.md](ntfy.md) | Benachrichtigungen aufs Handy mit ntfy | Einstellungen › Benachrichtigungen |
| [regelwerk.md](regelwerk.md) | Grund-Regelwerk für ein neues Projekt | Assistent „Neues Projekt“, Wissen › Regeln |
| [takt-chat-lead.md](takt-chat-lead.md) | Takt für einen Lead, der als Chat arbeitet | Assistent „Neues Projekt“ (Lead als Chat) |
| [schwere-laeufe.md](schwere-laeufe.md) | Schwere Läufe: Tests und Builds über die Warteschlange | Einstellungen › Projekt („Weitere schwere Befehle“) |
| [betriebsart.md](betriebsart.md) | Betriebsart wählen | Einstellungen › Betriebsart |
| [online-seite-webhoster.md](online-seite-webhoster.md) | Online-Seite beim Webhoster einrichten | Einstellungen › Online-Seite |
| [zweiter-faktor.md](zweiter-faktor.md) | Zweiter Faktor: neues oder verlorenes Handy | Einstellungen › Online-Seite („Neues Handy“) |

Englisch liegt unter [en/](en/) mit denselben Dateinamen.

## Eine Hilfe schreiben

1. Datei `<thema>.md` hier anlegen (Name nur Kleinbuchstaben, Ziffern, Bindestrich) und dieselbe unter `en/`.
2. Fester Aufbau – die Überschriften müssen genau so heißen; außer Titel und Schritten darf alles fehlen:

```
# Titel
Ein Satz, wozu das gut ist.

## Du brauchst                    (en: You need)
- …

## Schritte                       (en: Steps)
1. **Kurztitel** Was zu tun ist. ![Bildbeschreibung](bildname)
2. …

## Diese Werte trägst du ein      (en: Values to enter)
| Feld in der AMW | Woher |
|---|---|
| … | … |

## Typische Fehler                (en: Common problems)
- **Was man sieht** – was hilft

## Danach                         (en: Next)
- …

## Häufige Fragen                 (en: Questions)
### Frage?
Antwort.
```

3. Im Text gelten nur `**fett**` und `` `Befehl` ``. Bilder liegen als `amw/hilfe/<bildname>.webp`.
4. In der Oberfläche einhängen: `hilfeKnopf("<thema>")` neben das Feld oder `mitHilfe("<thema>", karte)` an einen Abschnitt.
5. `amw web bauen` ausführen – es prüft jede Hilfe und legt sie für die Online-Seite ab. Die Tests
   (`tests/test_hilfen.py`) verlangen jede Hilfe in beiden Sprachen mit denselben Schritten und Bildern.

Regeln für den Inhalt: nummerierte Schritte in der Reihenfolge, in der man sie tut; je Schritt eine Handlung; sagen,
**welcher Wert wohin** kopiert wird; die Meldungen bei „Typische Fehler“ so nennen, wie die AMW sie zeigt; keine echten
Adressen, Schlüssel oder Namen.
