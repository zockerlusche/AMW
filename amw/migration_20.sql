-- Schema 19 → 20 (AMW 1.30.0): Bezug einer Meldung („wartet auf Leitbild“, „… auf eine Aufgabe“, A…, F…). Ist er
-- erfüllt, setzt der Wächter die Empfänge auf erledigt – veraltete Wartemeldungen bleiben nicht stehen (Fehlerbericht
-- GlassWorld 07.11., Punkt 1b; Schema auf Marcels Wort).
ALTER TABLE nachricht ADD COLUMN bis TEXT;
