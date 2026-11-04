-- Schema 13 → 14 (AMW 1.11.0): Federführung je Bogen und je Aufgabe. Zuständig für eine Aufgabe ist ihre Federführung,
-- sonst die ihres Bogens, sonst der Lead (→ doc/plan-federfuehrung.md).
ALTER TABLE bogen ADD COLUMN federfuehrend TEXT;
ALTER TABLE aufgabe ADD COLUMN federfuehrend TEXT;
