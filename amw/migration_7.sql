-- Schema 7: Projektplanung (→ doc/ausbau.md §6, doc/recherche/planung.md).
ALTER TABLE projekt ADD COLUMN leitbild TEXT;               -- JSON: ziel, kennzahlen[], nicht_ziele[], prinzipien[{text, pruefung}]
ALTER TABLE projekt ADD COLUMN dod TEXT;                    -- JSON-Liste: Definition of Done für jeden Schritt

-- Bogen = Meilenstein mit prüfbarem Abnahmekriterium; Zieldatum wird beim Aktivieren als Baseline eingefroren.
CREATE TABLE bogen (
  id               INTEGER PRIMARY KEY,
  projekt_id       INTEGER NOT NULL REFERENCES projekt(id),
  nr               INTEGER NOT NULL,                -- Reihenfolge
  titel            TEXT NOT NULL,
  ziel             TEXT,
  abnahme          TEXT,                            -- prüfbares Kriterium (Gate)
  status           TEXT NOT NULL DEFAULT 'geplant' CHECK (status IN ('geplant', 'aktiv', 'fertig', 'verworfen')),
  zieldatum        TEXT,                            -- JJJJ-MM-TT
  baseline_datum   TEXT,
  baseline_grund   TEXT,
  angelegt_von     TEXT NOT NULL,
  angelegt_utc     TEXT NOT NULL,
  fertig_utc       TEXT,
  uid              TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft         TEXT NOT NULL DEFAULT '',
  geaendert_utc    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Spezifikation je Bogen in drei Teilen, jeder mit Freigabe durch den Menschen.
CREATE TABLE spezifikation (
  id               INTEGER PRIMARY KEY,
  bogen_id         INTEGER NOT NULL REFERENCES bogen(id),
  teil             TEXT NOT NULL CHECK (teil IN ('anforderungen', 'entwurf', 'schritte')),
  text             TEXT NOT NULL DEFAULT '',
  status           TEXT NOT NULL DEFAULT 'entwurf' CHECK (status IN ('entwurf', 'vorgelegt', 'frei', 'zurueck')),
  version          INTEGER NOT NULL DEFAULT 1,
  kommentar        TEXT,                            -- Rückmeldung des Menschen
  geschrieben_von  TEXT,
  freigabe_utc     TEXT,
  uid              TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft         TEXT NOT NULL DEFAULT '',
  geaendert_utc    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  UNIQUE (bogen_id, teil)
);

ALTER TABLE aufgabe ADD COLUMN bogen_id INTEGER REFERENCES bogen(id);
ALTER TABLE aufgabe ADD COLUMN kriterien TEXT;              -- JSON [{text, erfuellt}]
ALTER TABLE aufgabe ADD COLUMN schaetzung_h REAL;
ALTER TABLE aufgabe ADD COLUMN komplexitaet INTEGER;        -- 1–10; ≥ 7 verlangt einen freigegebenen Plan
ALTER TABLE aufgabe ADD COLUMN verantwortlich TEXT;         -- wer abnimmt (Mensch oder Lead); Bearbeiter = agent
ALTER TABLE aufgabe ADD COLUMN pruefbefehl TEXT;            -- wie der Bearbeiter selbst prüft
ALTER TABLE aufgabe ADD COLUMN dateibereich TEXT;           -- was er anfassen darf
ALTER TABLE aufgabe ADD COLUMN plan TEXT;
ALTER TABLE aufgabe ADD COLUMN plan_status TEXT;            -- keiner | vorgelegt | frei | zurueck
ALTER TABLE aufgabe ADD COLUMN zusammenfassung TEXT;        -- Pflicht beim Abschluss eines Bogen-Schritts
ALTER TABLE aufgabe ADD COLUMN anforderungen TEXT;          -- abgedeckte Anforderungs-IDs, z. B. R1,R3

CREATE TABLE abhaengigkeit (
  vor              INTEGER NOT NULL REFERENCES aufgabe(id),
  nach             INTEGER NOT NULL REFERENCES aufgabe(id),
  art              TEXT NOT NULL DEFAULT 'FS' CHECK (art IN ('FS', 'SS', 'FF')),
  extern           TEXT,                            -- Beschreibung einer Abhängigkeit außerhalb des Projekts
  uid              TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft         TEXT NOT NULL DEFAULT '',
  geaendert_utc    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  PRIMARY KEY (vor, nach)
);

CREATE TABLE risiko (
  id               INTEGER PRIMARY KEY,
  projekt_id       INTEGER NOT NULL REFERENCES projekt(id),
  bogen_id         INTEGER REFERENCES bogen(id),
  titel            TEXT NOT NULL,
  ursache          TEXT,
  wirkung          TEXT,
  wahrscheinlichkeit INTEGER NOT NULL DEFAULT 3 CHECK (wahrscheinlichkeit BETWEEN 1 AND 5),
  auswirkung       INTEGER NOT NULL DEFAULT 3 CHECK (auswirkung BETWEEN 1 AND 5),
  strategie        TEXT CHECK (strategie IN ('vermeiden', 'mindern', 'uebertragen', 'akzeptieren')),
  massnahme        TEXT,
  verantwortlich   TEXT,
  ausloeser        TEXT,
  status           TEXT NOT NULL DEFAULT 'offen' CHECK (status IN ('offen', 'eingetreten', 'erledigt')),
  angelegt_von     TEXT NOT NULL,
  angelegt_utc     TEXT NOT NULL,
  uid              TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft         TEXT NOT NULL DEFAULT '',
  geaendert_utc    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Protokoll der Planung: Freigaben, Statuswechsel, Baseline-Änderungen (Grundlage für Verlauf und Statusbericht).
CREATE TABLE plan_ereignis (
  id               INTEGER PRIMARY KEY,
  projekt_id       INTEGER NOT NULL REFERENCES projekt(id),
  zeit_utc         TEXT NOT NULL,
  von              TEXT NOT NULL,
  art              TEXT NOT NULL,                   -- z. B. bogen_status, spec_vorgelegt, spec_frei, spec_zurueck, plan_frei, baseline
  bogen_id         INTEGER,
  aufgabe_id       INTEGER,
  text             TEXT,
  uid              TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft         TEXT NOT NULL DEFAULT '',
  geaendert_utc    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX plan_ereignis_zeit ON plan_ereignis (projekt_id, zeit_utc);

-- Bisherige Textangaben „abhaengig_von“ (Nummern, Komma-getrennt) als Abhängigkeiten übernehmen.
INSERT OR IGNORE INTO abhaengigkeit (vor, nach)
  WITH RECURSIVE teile(nach, rest, nr) AS (
    SELECT id, replace(replace(abhaengig_von, ' ', ''), 'A', '') || ',', NULL FROM aufgabe
      WHERE abhaengig_von IS NOT NULL AND trim(abhaengig_von) != ''
    UNION ALL
    SELECT nach, substr(rest, instr(rest, ',') + 1), substr(rest, 1, instr(rest, ',') - 1) FROM teile WHERE rest != ''
  )
  SELECT CAST(nr AS INTEGER), nach FROM teile
    WHERE nr GLOB '[0-9]*' AND nr != '' AND CAST(nr AS INTEGER) IN (SELECT id FROM aufgabe) AND CAST(nr AS INTEGER) != nach;
