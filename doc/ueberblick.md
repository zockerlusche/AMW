# Überblick

AMW ist der Leitstand für **einen Menschen** (in AMW „Entwickler“), der mit **mehreren KI-Agenten** an einem Projekt
arbeitet. Jeder Agent ist eine eigene Claude-Code-Sitzung in einem Terminal-Fenster. Einer davon ist meist der
**Lead** (Team-Lead): er plant, verteilt Arbeit und fragt den Menschen; die anderen bauen, prüfen und melden zurück.

## Begriffe
| Begriff | Bedeutung |
|---|---|
| **Projekt** | Ein Vorhaben mit eigenen Agenten, Aufgaben, Wissen und Planung (eine Datenbank kann mehrere enthalten). |
| **Agent** | Eine Claude-Code-Sitzung mit einer Kennung (z. B. `TL`, `CC1`). Hat ein Soll (an/ruht/aus), eine Rolle, ein Profil zum Starten. |
| **Lead** | Agent mit Rolle `lead`: darf Bögen, Beschlüsse, Regeln, Halt; bekommt den Takt (Zusammenfassung) und Warnungen. |
| **Entwickler** | Der Mensch. Gibt frei, beantwortet Fragen, bekommt Push-Meldungen. Wird nie „geweckt“. |
| **Nachricht** | Von einem Agenten an einen oder mehrere (oder „alle“). Die **Art** bestimmt, ob der Empfänger geweckt wird (auftrag, frage, antwort, korrektur, stopp, freigabe, pruefbitte, meldung, takt) oder nie (info). Arbeitet der Empfänger gerade, kommt alles gesammelt bei seinem nächsten Halt – sofort nur stopp, korrektur und was der Mensch schreibt. |
| **Wecken** | Der Wächter schreibt einem schlafenden Agenten über die Nachrichten-Pipe seiner Sitzung „Du hast neue Nachrichten“ – der Agent liest dann mit `amw lesen`. |
| **Frage** | An den Entwickler (oder Lead): mit Optionen, Empfehlung, Begründung; Antwort per Klick, Text oder Rückfrage; Gesprächsverlauf bleibt erhalten. |
| **Aufgabe / Schritt** | Arbeitseinheit mit Bearbeiter und Status (wartet, läuft, blockiert, fertig, verworfen). Ein Schritt ist eine Aufgabe in einem Bogen – mit Abnahmekriterien, Abhängigkeiten, Schätzung. |
| **Wartegrund** | Worauf eine wartende Aufgabe wartet, als Verweis (Frage, Aufgabe, Lauf, Agent, Entwickler, Monitor). Ist er erledigt, weckt die AMW den Bearbeiter. |
| **Leitbild** | Ziel, Kennzahlen, Nicht-Ziele, Prinzipien, Definition of Done – steht im Pflicht-Kontext jedes Agenten. |
| **Bogen** | Meilenstein mit prüfbarem Abnahmekriterium, Zieldatum (Baseline), Spezifikation in drei Teilen mit Freigabe. |
| **Wissen** | Beschlüsse (mit Status und Ersatz), Regeln (nur mit Beschluss änderbar), Wortlaut des Entwicklers (unveränderlich), Notizen. |
| **Lauf** | Ein Rechen-Lauf (Build, Test …) mit Regeln: einer zur Zeit an Grafikkarte/Bildschirm, schwere ohne Fenster parallel (Vorgabe 2, je Agent einer), Speichergrenze je Lauf, Warteschlange. |
| **Schirm** | Schalter, ob Läufe mit Fenster gerade dürfen. Ab Werk zu; frei gibt der Entwickler (oder der Lead auf sein Wort); geht von selbst zu, sobald der Entwickler wieder da ist. |
| **Prüfung** | Prüfbitte an einen anderen Agenten je Stand (Commit), Ergebnis grün oder rot. |
| **Halt** | Hält alle (oder einen) Agenten an: nichts Neues beginnen, nur noch Stopp/Freigabe wecken – bis „Weiter“. |
| **Pflicht-Kontext** | Was ein Agent beim Start und nach jeder Komprimierung bekommt: Halt, Anweisungen, Leitbild, eigene Aufgaben, offene Nachrichten, Regeln. |
| **Wächter** | Hintergrundprozess („AMW Dienst“): weckt, überwacht Sitzungen/Server/Stillstand, verschickt Push, gleicht mit dem Online-Speicher ab, liefert die Workbench. |
| **Workbench** | Die Oberfläche im Browser: http://127.0.0.1:8780 (online optional). |

## So spielen die Teile zusammen
```
 Du (Browser / Handy)                       Agenten (Claude Code in Terminal-Tabs)
   │  Workbench: Fragen, Freigaben,           │  amw lesen / posten / aufgabe / schritt …
   │  Planung, Halt, Starten                  │  Hook beim Start: anmelden + Pflicht-Kontext
   ▼                                          ▼  Statusline: Kontext, Grenzen, Kosten
 ┌──────────────────────── amw.db (SQLite) ─────────────────────────┐
 │ Nachrichten · Aufgaben · Fragen · Wissen · Planung · Läufe · …   │
 └──────────────────────────────────────────────────────────────────┘
   ▲                                                        │
   │                Wächter („AMW Dienst“)                  ▼
   └── Workbench · Wecken über die Pipe · Überwachung · Push · Abgleich ──▶ Online-Speicher ──▶ Online-Seite
```

## Ein Tag mit AMW
1. **Morgens** zeigt die Startseite, was seit gestern passiert ist, und alles, was auf dich wartet: Freigaben,
   Fragen, eigene Schritte, Warnungen. Die Planung zeigt, ob die Bögen im Zeitplan sind.
2. **Der Lead** zerlegt die Arbeit, stellt dir Fragen und legt Spezifikationen zur Freigabe vor; die Agenten holen sich
   mit `amw schritt naechster --nehmen` den nächsten Schritt, bauen, prüfen sich gegenseitig und melden zurück.
3. **Unterwegs** bekommst du Push-Meldungen und antwortest auf der Online-Seite.
4. **Hängt etwas** – ein Agent wartet auf eine Freigabe in seinem Fenster, ein Server ist aus, ein Lauf dauert zu
   lange –, erscheint eine Warnung auf der Startseite und auf dem Handy.
5. **Nach einem Bogen** hältst du einen Rückblick: was lief gut, was ändern wir – Maßnahmen werden Aufgaben oder
   Beschlüsse.
