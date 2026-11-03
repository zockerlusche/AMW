-- Schema 9 → 10 (AMW 1.6.0): Fragen parken wie Aufgaben – raus aus der offenen Liste, nicht verloren (→ doc/betrieb.md).
-- Geparkt ist eine offene Frage mit geparkt_utc; „wieder aufnehmen“ leert beides, der Verlauf behält es.
ALTER TABLE frage ADD COLUMN geparkt_utc TEXT;
ALTER TABLE frage ADD COLUMN geparkt_von TEXT;

-- bisher geparkt per Text („GEPARKT …“ vorn in der Frage): jetzt als Kennzeichen
UPDATE frage SET geparkt_utc = geaendert_utc, geparkt_von = 'Entwickler' WHERE status = 'offen' AND kurz LIKE 'GEPARKT%';
