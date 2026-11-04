-- Schema 14 → 15 (AMW 1.13.0): Terminplaner – Testtermine des Entwicklers (auch wöchentlich), Fristen, Schirm-Fenster.
-- Ein Testtermin setzt die Frist „Testbuild fertig“ (vorlauf_h vorher); je Vorkommen eine Meldung „bereit“ mit Kurzliste.
CREATE TABLE termin (
  id            INTEGER PRIMARY KEY,
  projekt_id    INTEGER NOT NULL REFERENCES projekt(id),
  titel         TEXT NOT NULL,
  art           TEXT NOT NULL CHECK (art IN ('test', 'frist', 'schirm', 'sonstig')),
  beginn_utc    TEXT NOT NULL,                    -- erstes Vorkommen
  dauer_min     INTEGER,
  woechentlich  INTEGER NOT NULL DEFAULT 0 CHECK (woechentlich IN (0, 1)),
  bis_datum     TEXT,                             -- letzte Woche der Wiederholung (JJJJ-MM-TT), leer = ohne Ende
  vorlauf_h     REAL,                             -- test: „Testbuild fertig“ so viele Stunden vorher
  bogen_id      INTEGER REFERENCES bogen(id),     -- Ampel: Prognose dieses Bogens gegen die Frist
  notiz         TEXT,
  status        TEXT NOT NULL DEFAULT 'geplant' CHECK (status IN ('geplant', 'abgesagt')),
  angelegt_von  TEXT NOT NULL,
  angelegt_utc  TEXT NOT NULL,
  uid           TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft      TEXT NOT NULL DEFAULT '',
  geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE TRIGGER termin_geaendert AFTER UPDATE ON termin BEGIN UPDATE termin SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER termin_nie_loeschen BEFORE DELETE ON termin BEGIN SELECT RAISE(ABORT, 'Verlauf: termin wird nicht gelöscht'); END;
CREATE TABLE termin_meldung (                   -- je Vorkommen: Testbuild bereit (mit Kurzliste) oder nur dieses abgesagt
  id            INTEGER PRIMARY KEY,
  termin_id     INTEGER NOT NULL REFERENCES termin(id),
  am_utc        TEXT NOT NULL,                    -- Beginn des Vorkommens
  art           TEXT NOT NULL CHECK (art IN ('bereit', 'abgesagt')),
  von           TEXT NOT NULL,
  zeit_utc      TEXT NOT NULL,
  text          TEXT,
  uid           TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft      TEXT NOT NULL DEFAULT '',
  geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  UNIQUE (termin_id, am_utc, art)
);
CREATE TRIGGER termin_meldung_nie_loeschen BEFORE DELETE ON termin_meldung BEGIN SELECT RAISE(ABORT, 'Verlauf: termin_meldung wird nicht gelöscht'); END;
