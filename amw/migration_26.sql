-- Schema 25 → 26 (AMW 1.62.0): Versionshinweise ohne KI. Beim Abschließen einer Aufgabe gibt der Agent optional einen
-- Satz für Nutzer und die Gruppe an; daraus entsteht der Entwurf der nächsten Version (amw release).
--   hinweis         ein Satz für die Versionshinweise, in der Sprache der Nutzer
--   hinweis_gruppe  neu | verbessert | behoben
-- Bestand: leer (dann macht eine Regel aus der Zusammenfassung einen Vorschlag). Schema auf Beschluss von Lead und Coder.
ALTER TABLE aufgabe ADD COLUMN hinweis TEXT;
ALTER TABLE aufgabe ADD COLUMN hinweis_gruppe TEXT CHECK (hinweis_gruppe IN ('neu', 'verbessert', 'behoben'));
