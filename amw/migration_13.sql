-- Schema 12 → 13 (AMW 1.10.0): wann die Tätigkeit gesetzt wurde – Workbench und Kontext zeigen ihr Alter,
-- aufgabe start/lauf start setzen sie nur, wenn sie leer oder älter als 2 h ist.
ALTER TABLE sitzung ADD COLUMN taetigkeit_utc TEXT;
