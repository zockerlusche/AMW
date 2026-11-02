-- Schema 9: Dokumente – Ergebnisse der Agenten mit Versionen (→ doc/plan-dokumente.md). Die Dateien liegen im
-- Datenordner unter dokumente/, hier nur Verweis (Hash), Metadaten und Suchtext. Kommentare: nachricht.dokument_id.
CREATE TABLE dokument (
  id               INTEGER PRIMARY KEY,
  projekt_id       INTEGER NOT NULL REFERENCES projekt(id),
  titel            TEXT NOT NULL,
  art              TEXT NOT NULL CHECK (art IN ('ergebnis', 'bericht', 'entwurf', 'mockup', 'bild', 'quelle')),
  bezug_art        TEXT CHECK (bezug_art IN ('bogen', 'aufgabe', 'frage', 'beschluss')),
  bezug_id         INTEGER,
  status           TEXT NOT NULL DEFAULT 'aktuell' CHECK (status IN ('aktuell', 'archiviert', 'geloescht')),
  online           INTEGER NOT NULL DEFAULT 0,          -- Datei auch online zeigen (Texte sind immer online)
  angelegt_von     TEXT NOT NULL,
  angelegt_utc     TEXT NOT NULL,
  uid              TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft         TEXT NOT NULL DEFAULT '',
  geaendert_utc    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX dokument_bezug ON dokument (projekt_id, bezug_art, bezug_id);

CREATE TABLE dokument_version (
  id               INTEGER PRIMARY KEY,
  dokument_id      INTEGER NOT NULL REFERENCES dokument(id),
  nr               INTEGER NOT NULL,
  sha256           TEXT NOT NULL,
  endung           TEXT NOT NULL,
  groesse          INTEGER NOT NULL,
  notiz            TEXT,
  von              TEXT NOT NULL,
  zeit_utc         TEXT NOT NULL,
  suchtext         TEXT,
  uid              TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft         TEXT NOT NULL DEFAULT '',
  geaendert_utc    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  UNIQUE (dokument_id, nr)
);

ALTER TABLE nachricht ADD COLUMN dokument_id INTEGER REFERENCES dokument(id);

CREATE TRIGGER dokument_geaendert AFTER UPDATE ON dokument BEGIN UPDATE dokument SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER dokument_nie_loeschen BEFORE DELETE ON dokument BEGIN SELECT RAISE(ABORT, 'Verlauf: dokument wird nicht gelöscht (Status geloescht)'); END;
CREATE TRIGGER dokument_version_nie_loeschen BEFORE DELETE ON dokument_version BEGIN SELECT RAISE(ABORT, 'Verlauf: dokument_version wird nicht gelöscht'); END;
