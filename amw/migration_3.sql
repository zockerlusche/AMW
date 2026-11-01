-- Schema 3: Warteschlange für Rechen-Läufe (lauf start --warten).
-- Wartende Läufe haben status 'angemeldet'; rang > 0 = von Lead/Entwickler vorgezogen.
ALTER TABLE lauf ADD COLUMN rang INTEGER NOT NULL DEFAULT 0;
