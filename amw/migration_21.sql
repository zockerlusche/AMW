-- Schema 20 → 21 (AMW 1.31.0): Vermerke an KI-Ergebnissen (KI Stufe 2, doc/plan-lokale-ki.md §4) – wer hat ein KI-Bild
-- oder einen KI-Text wann ausgewählt, verworfen oder von Hand nachbearbeitet (und was). Das ist der Nachweis der
-- menschlichen Gestaltungsentscheidung für Urheberrecht und Steam-Angabe; `amw ki nachweis` liest ihn. Jeder Vermerk ist
-- eine neue Zeile (nie geändert, nie gelöscht); es gilt der jüngste ausgewählt/verworfen. Schema auf Marcels Wort (F5254).
CREATE TABLE ki_vermerk (
  id             INTEGER PRIMARY KEY,
  projekt_id     INTEGER NOT NULL REFERENCES projekt(id),
  dokument_id    INTEGER NOT NULL REFERENCES dokument(id),
  version_nr     INTEGER NOT NULL,                -- die Fassung, die beim Vermerk gezeigt war
  art            TEXT NOT NULL CHECK (art IN ('ausgewaehlt', 'verworfen', 'nachbearbeitet')),
  text           TEXT,                            -- nachbearbeitet: was von Hand geändert wurde (Pflicht); sonst Grund
  von            TEXT NOT NULL,
  kanal          TEXT NOT NULL CHECK (kanal IN ('cli', 'workbench', 'netz', 'bruecke')),
  zeit_utc       TEXT NOT NULL,
  uid            TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft       TEXT NOT NULL DEFAULT '',
  geaendert_utc  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX ki_vermerk_dokument ON ki_vermerk (dokument_id);
CREATE TRIGGER ki_vermerk_nie_loeschen BEFORE DELETE ON ki_vermerk BEGIN SELECT RAISE(ABORT, 'Verlauf: ki_vermerk wird nicht gelöscht'); END;
CREATE TRIGGER ki_vermerk_unveraenderlich BEFORE UPDATE ON ki_vermerk BEGIN SELECT RAISE(ABORT, 'Verlauf: ki_vermerk wird nicht geändert – neuer Vermerk'); END;
