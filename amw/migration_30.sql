-- Schema 29 → 30 (AMW 1.85.0): Größe und Art je Aufgabe (A1611 Stufe E2, Konzept D906). Daraus schlägt die AMW Modell
-- und Denkaufwand vor (Tabelle je Projekt in projekt.einstellungen „empfehlung“) – nur als Empfehlung, gesetzt wird im
-- Profil des Agenten. komplexitaet (1–10, Plan ab 7) bleibt, was sie ist.
ALTER TABLE aufgabe ADD COLUMN groesse TEXT CHECK (groesse IN ('S', 'M', 'L', 'XL'));
ALTER TABLE aufgabe ADD COLUMN art TEXT CHECK (art IN ('text', 'mechanisch', 'fehlersuche', 'oberflaeche', 'sicherheit', 'konzept'));
