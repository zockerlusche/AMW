-- Schema 27 → 28 (AMW 1.69.0): Agenten entfernen. Ein entfernter Agent ist stillgelegt (Soll aus) und aus allen Listen
-- ausgeblendet; sein Verlauf (Nachrichten, Aufgaben, Prüfungen) bleibt mit Namen lesbar. Wieder aufnehmen setzt die Spalte
-- zurück. Endgültig gelöscht wird nur ein Agent ohne Verlauf (dann ist die Zeile weg, nicht nur markiert).
ALTER TABLE agent ADD COLUMN entfernt_utc TEXT;
