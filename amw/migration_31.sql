-- Schema 30 → 31 (AMW 1.90.0): Läufe überleben den Warte-Prozess, Bedarf lernt die AMW (A1640, A1641). „amw lauf ausfuehren“
-- speichert, was es ausführen will; stirbt sein Warte-Prozess im Fenster des Agenten, startet der Dienst genau diesen Befehl
-- im gespeicherten Ordner. Keine Umgebung, nichts Geheimes – nur, was der Agent ohnehin als Befehl übergeben hat.
ALTER TABLE lauf ADD COLUMN befehl TEXT;          -- JSON-Liste der Argumente (bei einem einzigen: Befehlszeile der Shell)
ALTER TABLE lauf ADD COLUMN ordner TEXT;          -- Arbeitsordner beim Einreihen
ALTER TABLE lauf ADD COLUMN ergebnis_datei TEXT;  -- wohin die Ausgabe geht (--ergebnis)
ALTER TABLE lauf ADD COLUMN frist_min REAL;       -- --frist: danach Ende (rc 124)
ALTER TABLE lauf ADD COLUMN waechter INTEGER;     -- PID des Warte-Prozesses („amw lauf ausfuehren“)
ALTER TABLE lauf ADD COLUMN ausfuehrer TEXT CHECK (ausfuehrer IN ('agent', 'dienst'));   -- wer den Befehl gestartet hat
ALTER TABLE lauf ADD COLUMN spitze_gb REAL;       -- gemessene Spitze des Prozessbaums (Bedarf späterer Läufe ohne Angabe)
