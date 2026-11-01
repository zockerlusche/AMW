-- Schema 5: Zustand und Verbrauch je Sitzung (Statusline, Hooks) und Push-Versand.
ALTER TABLE sitzung ADD COLUMN kontext_prozent REAL;        -- Füllstand des Kontextfensters
ALTER TABLE sitzung ADD COLUMN limit_5h REAL;               -- Nutzungsgrenze 5 Stunden in %
ALTER TABLE sitzung ADD COLUMN limit_5h_reset_utc TEXT;
ALTER TABLE sitzung ADD COLUMN limit_7t REAL;               -- Nutzungsgrenze 7 Tage in %
ALTER TABLE sitzung ADD COLUMN limit_7t_reset_utc TEXT;
ALTER TABLE sitzung ADD COLUMN kosten_usd REAL;             -- Kosten der Sitzung (Schätzung zum Listenpreis)
ALTER TABLE sitzung ADD COLUMN modell TEXT;
ALTER TABLE sitzung ADD COLUMN denkstufe TEXT;
ALTER TABLE sitzung ADD COLUMN status_utc TEXT;             -- letzte Meldung der Statusline
ALTER TABLE sitzung ADD COLUMN ereignis TEXT;               -- arbeitet | frei | wartet_freigabe | wartet_eingabe | fehler
ALTER TABLE sitzung ADD COLUMN ereignis_text TEXT;
ALTER TABLE sitzung ADD COLUMN ereignis_utc TEXT;

-- Messpunkte für den Verbrauch je Agent und Tag (der Wächter schreibt höchstens alle 5 Minuten einen je Sitzung).
CREATE TABLE verbrauch (
  id               INTEGER PRIMARY KEY,
  sitzung_id       INTEGER NOT NULL REFERENCES sitzung(id),
  agent            TEXT NOT NULL,
  zeit_utc         TEXT NOT NULL,
  kosten_usd       REAL,
  kontext_prozent  REAL,
  limit_5h         REAL,
  limit_7t         REAL,
  uid              TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft         TEXT NOT NULL DEFAULT '',
  geaendert_utc    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX verbrauch_agent_zeit ON verbrauch (agent, zeit_utc);

-- Push-Benachrichtigungen: was wann an wen ging (schluessel verhindert Doppelte).
CREATE TABLE push_versand (
  id               INTEGER PRIMARY KEY,
  zeit_utc         TEXT NOT NULL,
  ereignis         TEXT NOT NULL,                  -- frage | nachricht | warnung | eingabe | halt | rueckblick | probe
  schluessel       TEXT NOT NULL UNIQUE,
  titel            TEXT NOT NULL,
  text             TEXT,
  prioritaet       INTEGER NOT NULL DEFAULT 3,     -- 1 (leise) … 5 (dringend)
  sicht            TEXT,                           -- Ansicht, die der Link öffnet
  kanaele          TEXT,                           -- ntfy,pushover,telegram
  buendel          INTEGER,                        -- gemeinsam gesendet: id des ersten Eintrags
  ergebnis         TEXT NOT NULL DEFAULT 'offen' CHECK (ergebnis IN ('offen', 'gesendet', 'teilweise', 'fehler', 'unterdrueckt')),
  fehler           TEXT,
  versuche         INTEGER NOT NULL DEFAULT 0,
  uid              TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft         TEXT NOT NULL DEFAULT '',
  geaendert_utc    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
