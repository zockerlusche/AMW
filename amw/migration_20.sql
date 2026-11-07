-- Schema 19 → 20 (AMW 1.30.0): Bezug einer Meldung („wartet auf Leitbild“, „… auf eine Aufgabe“, A…, F…). Ist er
-- erfüllt, setzt der Wächter die Empfänge auf erledigt – veraltete Wartemeldungen bleiben nicht stehen (Fehlerbericht
-- aus einem Projekt; Schema auf Wort des Entwicklers).
ALTER TABLE nachricht ADD COLUMN bis TEXT;
