-- Schema 4: Überwachung (Marcel 01.11.2026): Projekt-Server und erwartete Lauf-Dauer.
ALTER TABLE lauf ADD COLUMN erwartet_min REAL;
-- Projekt-Server, die der Wächter überwacht (Port antwortet?) und auf Wunsch neu startet (→ amw/ueberwachung.py).
-- Startbefehl nur über die Kommandozeile am PC, nie über Brücke oder Online-Seite.
CREATE TABLE server (
  id                   INTEGER PRIMARY KEY,
  projekt_id           INTEGER NOT NULL REFERENCES projekt(id),
  name                 TEXT NOT NULL,
  port                 INTEGER NOT NULL,
  startbefehl          TEXT,
  ordner               TEXT,
  neustart             INTEGER NOT NULL DEFAULT 0,
  zustaendig           TEXT NOT NULL,              -- wird bei Ausfall benachrichtigt (dazu die Leads)
  aktiv                INTEGER NOT NULL DEFAULT 1,
  zustand              TEXT NOT NULL DEFAULT 'unbekannt' CHECK (zustand IN ('unbekannt', 'laeuft', 'aus')),
  seit_utc             TEXT,
  geprueft_utc         TEXT,
  ausfaelle            INTEGER NOT NULL DEFAULT 0,
  neustarts            TEXT,                       -- JSON: Zeitpunkte der Neustarts der letzten Stunde
  letzter_neustart_utc TEXT,
  angelegt_utc         TEXT NOT NULL,
  uid                  TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft             TEXT NOT NULL DEFAULT '',
  geaendert_utc        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  UNIQUE (projekt_id, name)
);
