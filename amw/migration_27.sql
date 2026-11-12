-- Schema 26 → 27 (AMW 1.63.0): mehrere Benutzer (Stufe R1a). Ein Benutzer hat EINE Rolle (global, Beschluss des
-- Menschen) und bekommt Projekte zugewiesen. Passwörter und Geheimnisse liegen nie hier – nur im Online-Speicher.
--   rolle            leser | bearbeiter | projekt_admin | system_admin; leer = wartet auf Freigabe durch einen Admin (keine Rechte)
--   benutzer_projekt welche Projekte ein Benutzer sieht (System-Admins sehen alle)
--   nachricht.benutzer, frage_verlauf.benutzer   wer von den Menschen es war (leer = der Mensch am PC bzw. vor Schema 27)
-- Bestand: keine Benutzer; der Mensch am PC und der bisherige Online-Zugang bleiben System-Admin. Schema auf Wort des
-- Menschen (Mehrbenutzer) und Beschluss von Lead und Coder.
CREATE TABLE IF NOT EXISTS benutzer (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL UNIQUE,
  anzeige       TEXT,
  email         TEXT,
  rolle         TEXT CHECK (rolle IN ('leser', 'bearbeiter', 'projekt_admin', 'system_admin')),   -- leer = wartet auf Freigabe
  gesperrt      INTEGER NOT NULL DEFAULT 0,
  angelegt_utc  TEXT NOT NULL,
  angelegt_von  TEXT NOT NULL,
  uid           TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft      TEXT NOT NULL DEFAULT '',
  geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE TABLE IF NOT EXISTS benutzer_projekt (
  benutzer_id   INTEGER NOT NULL REFERENCES benutzer(id),
  projekt_id    INTEGER NOT NULL REFERENCES projekt(id),
  PRIMARY KEY (benutzer_id, projekt_id)
);
ALTER TABLE nachricht ADD COLUMN benutzer TEXT;
ALTER TABLE frage_verlauf ADD COLUMN benutzer TEXT;
