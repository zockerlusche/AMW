-- Schema 6: Agenten steuern – Profil je Agent, Prozess- und Fenster-PID je Sitzung (Absturz erkennen).
ALTER TABLE agent ADD COLUMN ordner TEXT;                   -- Arbeitsordner (Projekt) des Agenten
ALTER TABLE agent ADD COLUMN zusatzordner TEXT;             -- JSON-Liste weiterer Ordner (--add-dir)
ALTER TABLE agent ADD COLUMN denkstufe TEXT;                -- low | medium | high | xhigh | max
ALTER TABLE agent ADD COLUMN modell TEXT;                   -- z. B. opus, sonnet (leer = Vorgabe)
ALTER TABLE agent ADD COLUMN startsatz TEXT;                -- erste Anweisung bei einer neuen Sitzung
ALTER TABLE agent ADD COLUMN rechte TEXT;                   -- vorgabe | auto | umgehen
ALTER TABLE agent ADD COLUMN fernsteuerung INTEGER NOT NULL DEFAULT 1;   -- Remote Control mit Namen = Kennung
ALTER TABLE agent ADD COLUMN neustart_auto INTEGER NOT NULL DEFAULT 0;   -- nach Absturz automatisch fortsetzen
ALTER TABLE sitzung ADD COLUMN claude_pid INTEGER;
ALTER TABLE sitzung ADD COLUMN fenster_pid INTEGER;         -- Shell/Fenster, in dem Claude läuft
