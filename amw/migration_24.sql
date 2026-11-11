-- Schema 23 → 24 (AMW 1.44.0): Auslastung des Rechners. Mehrere Projekte teilen sich einen PC; ein Lauf meldet an, was er
-- braucht, und die Warteschlange lässt ihn ein, wenn es frei ist.
--   braucht_gb          geschätzter Arbeitsspeicher dieses Laufs (sonst: Rezept, sonst die Grenze des Projekts)
--   braucht_vram_gb     Grafikspeicher (nur für Läufe auf der Grafikkarte; leer = nicht geprüft)
--   braucht_platte_gb   freier Platz auf dem Laufwerk des Projekts (leer = nicht geprüft)
--   rechner             Name des PCs, auf dem der Lauf angemeldet wurde – die Warteschlange zählt nur Läufe ihres Rechners
-- Bestand: alles leer; ein Lauf ohne Rechner gilt als Lauf dieses Rechners. Schema auf Wort des Entwicklers.
ALTER TABLE lauf ADD COLUMN braucht_gb REAL;
ALTER TABLE lauf ADD COLUMN braucht_vram_gb REAL;
ALTER TABLE lauf ADD COLUMN braucht_platte_gb REAL;
ALTER TABLE lauf ADD COLUMN rechner TEXT;
