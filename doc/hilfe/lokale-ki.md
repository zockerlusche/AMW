# Lokale KI einrichten und beauftragen

Die AMW kann Aufträge an eine KI auf diesem PC geben – zum Beispiel Bilder mit ComfyUI oder Texte mit Ollama. Sie startet die KI bei Bedarf, rechnet über die Warteschlange und legt jedes Ergebnis als Dokument mit Herkunft ab.

## Du brauchst
- Eine installierte lokale KI, die nur auf diesem PC antwortet (z. B. ComfyUI oder Ollama).
- Die Lizenz des Modells, das du benutzen willst.

## Schritte
1. **KI eintragen** `amw ki neu <name> --art bild --schnittstelle comfyui` (für Texte: `--art sprache --schnittstelle ollama`). Mit `--start "…"` startet der Dienst die KI selbst, wenn sie nicht antwortet.
2. **Modell freigeben** `amw ki modell <name> <modell> --lizenz … --quelle <url> --kommerziell ja|nein|unklar`, dann `amw ki freigeben <name> <modell> --grund …`. Nur freigegebene Modelle bekommen Aufträge.
3. **Rechte vergeben** `amw ki recht <name> --wer <agent>` – wer außer Lead und dir beauftragen darf.
4. **Beauftragen** `amw ki auftrag <name> --modell … --prompt "…"`. Der Auftrag wartet in der Warteschlange, bis die Grafikkarte frei ist. Mit `--nachts` startet er erst im KI-Fenster.
5. **Entscheiden** Unter Dokumente beim Ergebnis „Auswählen“ oder „Verwerfen“ und, falls du nachgearbeitet hast, „Nachbearbeitung vermerken“.

## Diese Werte trägst du ein
| Feld in der AMW | Woher |
|---|---|
| KI-Fenster (Einstellungen › Dieser PC) | Zeitraum für Nacht-Aufträge, z. B. 22-06 |
| Lizenz, Quelle, kommerziell | von der Seite des Modells |

## Typische Fehler
- **Der Auftrag wartet lange** – Die Grafikkarte ist belegt, oder es ist ein Nacht-Auftrag und das KI-Fenster ist noch zu. Der Wartegrund steht beim Lauf.
- **„nicht freigegeben“** – Das Modell ist eingetragen, aber noch nicht freigegeben (Schritt 2).
- **Die KI antwortet nicht** – Ohne Startbefehl startet die AMW sie nicht. Selbst starten oder `--start` nachtragen.

## Danach
- Nachweis der menschlichen Gestaltungsentscheidung (Urheberrecht, Angabe bei Steam): `amw ki nachweis` listet zu jedem KI-Ergebnis, wer ausgewählt, verworfen oder nachbearbeitet hat.
- Nacht-Aufträge starten nie in der Vorlaufzeit eines Testtermins; bis dahin lassen sie allen anderen Läufen den Vortritt.

## Häufige Fragen
### Wer darf ein Modell freigeben?
Modelle mit freier Lizenz gibt der Lead frei. Modelle mit Nutzungsregeln (z. B. Open RAIL) gibt nur der Mensch frei.
