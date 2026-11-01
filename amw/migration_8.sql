-- Schema 8: Rückblick je Bogen (gut / schlecht / Maßnahme / gelernt) – Grundlage für Lessons Learned.
CREATE TABLE rueckblick (
  id               INTEGER PRIMARY KEY,
  projekt_id       INTEGER NOT NULL REFERENCES projekt(id),
  bogen_id         INTEGER REFERENCES bogen(id),
  art              TEXT NOT NULL CHECK (art IN ('gut', 'schlecht', 'massnahme', 'gelernt')),
  text             TEXT NOT NULL,
  von              TEXT NOT NULL,
  zeit_utc         TEXT NOT NULL,
  aufgabe_id       INTEGER REFERENCES aufgabe(id),      -- Maßnahme wurde zur Aufgabe
  beschluss_id     INTEGER REFERENCES beschluss(id),    -- … oder zum Beschluss
  uid              TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft         TEXT NOT NULL DEFAULT '',
  geaendert_utc    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
