-- Schema 31 → 32 (AMW 1.96.0): Lead-Runde (A1658) – ein Kanal nur zwischen den Leads aller Projekte dieser Datenbank.
-- Nur Information: Arten info und frage, nie Aufträge, Stopps oder Freigaben an andere Projekte (Richtlinie Marcel 13.11.).
CREATE TABLE runde (
  id            INTEGER PRIMARY KEY,
  von_projekt_id INTEGER NOT NULL REFERENCES projekt(id),
  von           TEXT NOT NULL,                    -- Lead (Kennung im eigenen Projekt) oder Entwickler
  an_projekt_id INTEGER REFERENCES projekt(id),   -- direkte Anrede (--an): Info ins Postfach des Leads dort
  art           TEXT NOT NULL CHECK (art IN ('info', 'frage')),
  kurz          TEXT NOT NULL,
  text          TEXT,
  antwort_auf   INTEGER REFERENCES runde(id),
  zeit_utc      TEXT NOT NULL,
  uid           TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft      TEXT NOT NULL DEFAULT '',
  geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE TRIGGER runde_nie_loeschen BEFORE DELETE ON runde BEGIN SELECT RAISE(ABORT, 'Lead-Runde: Einträge werden nicht gelöscht'); END;
CREATE TABLE runde_gelesen (
  projekt_id    INTEGER PRIMARY KEY REFERENCES projekt(id),   -- bis wohin der Lead dieses Projekts gelesen hat
  bis_id        INTEGER NOT NULL,
  geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
