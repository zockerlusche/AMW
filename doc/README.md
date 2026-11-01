# Dokumentation

**Für Anwender**
1. [Überblick](ueberblick.md) – Begriffe, wie die Teile zusammenspielen, ein Tag mit AMW
2. [Installation](installation.md) – Voraussetzungen, `amw einrichten`, erster Start, Aktualisieren, Entfernen
3. [Betrieb](betrieb.md) – Workbench, mit Agenten arbeiten, Überwachung, Sicherung
4. [Planung](anleitung-planung.md) – Leitbild, Bögen, Spezifikation, Schritte, Prognose, Rückblick
5. [Push aufs Handy](anleitung-push.md) – ntfy, Pushover, Telegram
6. [Online](online.md) – die Workbench im Netz (PHP-Webhoster + Turso)
7. [Fehlerbehebung](fehlerbehebung.md)
8. [Befehle](befehle.md) – alle `amw`-Befehle (aus der Kommandozeile erzeugt)

**Hintergrund**
- [Architektur](architektur.md) – Bausteine, Abläufe, Datenmodell, Grenzen
- [Sicherheit](sicherheit.md) – Vertrauensmodell, wo Geheimnisse liegen, was AMW selbst startet
- [Ausbau](ausbau.md) – Plan und Stand des Ausbaus zum vollständigen Lead-Werkzeug
- Recherchen: [Projektplanung](recherche/planung.md) · [Agenten-Workbenches](recherche/workbenches.md) · [Push-Dienste](recherche/push.md)

Für Entwickler an AMW: Tests mit `python -m unittest discover -s tests`; neue Datenbank-Versionen als
`amw/migration_<n>.sql` und `SCHEMA_VERSION` in `amw/db.py`; nach Änderungen an `amw/workbench.html` `amw web bauen`,
nach Änderungen an Befehlen `amw befehle > doc/befehle.md` (beides prüfen Tests).
