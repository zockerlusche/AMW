-- Schema 34 → 35 (A2090, Entscheidung F5395): nur Indizes, keine Daten, keine Spalten. Fast jede Ansicht sucht nach Aufgabe oder
-- Meilenstein; ohne diese Indizes las SQLite dafür jedes Mal die ganze Tabelle (nachricht: alle Zeilen des Projekts).
-- IF NOT EXISTS: ein zweiter Lauf ändert nichts.
CREATE INDEX IF NOT EXISTS nachricht_aufgabe ON nachricht (aufgabe_id, id);
CREATE INDEX IF NOT EXISTS lauf_aufgabe ON lauf (aufgabe_id, id);
CREATE INDEX IF NOT EXISTS pruefung_aufgabe ON pruefung (aufgabe_id, id);
CREATE INDEX IF NOT EXISTS plan_ereignis_aufgabe ON plan_ereignis (aufgabe_id, art, id);
CREATE INDEX IF NOT EXISTS plan_ereignis_bogen ON plan_ereignis (bogen_id, art, id);
CREATE INDEX IF NOT EXISTS aufgabe_bogen ON aufgabe (bogen_id);
CREATE INDEX IF NOT EXISTS frage_aufgabe ON frage (aufgabe_id);
