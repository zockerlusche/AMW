-- Schema 10 → 11 (AMW 1.7.0): Schirm-Schalter (B2419, → doc/plan-automatismen.md).
-- Darf gerade ein Lauf am Bildschirm laufen? Eine Zeile je Wechsel, die jüngste gilt; keine Zeile = zu.
-- PC-weit (ein Bildschirm), deshalb ohne projekt_id.
CREATE TABLE schirm (
  id            INTEGER PRIMARY KEY,
  frei          INTEGER NOT NULL CHECK (frei IN (0, 1)),
  seit_utc      TEXT NOT NULL,
  bis_utc       TEXT,                             -- nur bei frei: geht dann von selbst zu
  grund         TEXT NOT NULL,
  von           TEXT NOT NULL,
  quelle        TEXT NOT NULL CHECK (quelle IN ('workbench', 'netz', 'cli', 'bruecke', 'automatik')),
  uid           TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft      TEXT NOT NULL DEFAULT '',
  geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE TRIGGER schirm_nie_loeschen BEFORE DELETE ON schirm BEGIN SELECT RAISE(ABORT, 'Verlauf: schirm wird nicht gelöscht'); END;
