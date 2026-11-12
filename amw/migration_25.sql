-- Schema 24 → 25 (AMW 1.59.0): Größe der Ordner, gemessen vom Dienst einmal am Tag – damit sichtbar wird, was wächst
-- und wo sich Ablagerungen sammeln (Build-Reste, Worktrees, alte Sicherungen). Die AMW misst nur; sie löscht nichts.
--   art        projekt | ablage | worktree | sicherungen
--   bytes      Größe in Bytes, dateien = Anzahl Dateien
--   zuletzt_utc  jüngste Änderung einer Datei darin (zeigt, ob eine Ablage noch benutzt wird)
-- Messwerte älter als 90 Tage räumt der Dienst selbst weg. Schema auf Beschluss von Lead und Coder (Messwerte, kein Bestand).
CREATE TABLE IF NOT EXISTS ordner_messung (
  id            INTEGER PRIMARY KEY,
  zeit_utc      TEXT NOT NULL,
  rechner       TEXT,
  projekt_id    INTEGER REFERENCES projekt(id),
  ordner        TEXT NOT NULL,
  art           TEXT NOT NULL CHECK (art IN ('projekt', 'ablage', 'worktree', 'sicherungen')),
  bytes         INTEGER NOT NULL,
  dateien       INTEGER,
  zuletzt_utc   TEXT,
  uid           TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft      TEXT NOT NULL DEFAULT '',
  geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS ordner_messung_ordner ON ordner_messung (ordner, zeit_utc);
