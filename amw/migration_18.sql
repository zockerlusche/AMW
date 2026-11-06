-- Schema 17 → 18 (AMW 1.17.0): Push je Projekt (→ doc/plan-projektwahl.md). Bisher war die Warteschlange PC-weit, und eine
-- Runde hielt die Meldungen eines anderen Projekts für erledigt. Jetzt gehört jede Meldung einem Projekt; der Schlüssel
-- ist je Projekt eindeutig. Vorhandene Einträge gehören dem ersten Projekt. SQLite ändert keine UNIQUE-Bedingung, darum
-- wird die Tabelle neu angelegt.
CREATE TABLE push_versand_neu (
  id               INTEGER PRIMARY KEY,
  projekt_id       INTEGER NOT NULL REFERENCES projekt(id),
  zeit_utc         TEXT NOT NULL,
  ereignis         TEXT NOT NULL,                  -- frage | nachricht | warnung | eingabe | halt | rueckblick | probe
  schluessel       TEXT NOT NULL,
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
  geaendert_utc    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  UNIQUE (projekt_id, schluessel)
);
INSERT INTO push_versand_neu (id, projekt_id, zeit_utc, ereignis, schluessel, titel, text, prioritaet, sicht, kanaele, buendel,
                              ergebnis, fehler, versuche, uid, herkunft, geaendert_utc)
  SELECT id, (SELECT min(id) FROM projekt), zeit_utc, ereignis, schluessel, titel, text, prioritaet, sicht, kanaele, buendel,
         ergebnis, fehler, versuche, uid, herkunft, geaendert_utc FROM push_versand;
DROP TABLE push_versand;
ALTER TABLE push_versand_neu RENAME TO push_versand;
