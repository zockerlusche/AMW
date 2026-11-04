-- Schema 11 → 12 (AMW 1.8.0): Wartegründe als Verweis, Frage-Prüfung, Alias für umbenannte Agenten.
-- Worauf eine Aufgabe wartet: je Grund eine Zeile; erledigt_utc gesetzt = Grund weg (weckt den Besitzer, L2).
CREATE TABLE wartegrund (
  id            INTEGER PRIMARY KEY,
  projekt_id    INTEGER NOT NULL REFERENCES projekt(id),
  aufgabe_id    INTEGER NOT NULL REFERENCES aufgabe(id),
  art           TEXT NOT NULL CHECK (art IN ('frage', 'aufgabe', 'lauf', 'agent', 'entwickler', 'monitor')),
  bezug         TEXT NOT NULL,                    -- F12, A120, L7, CC2, Entwickler, Monitor:<was>
  angelegt_utc  TEXT NOT NULL,
  angelegt_von  TEXT NOT NULL,
  erledigt_utc  TEXT,
  erledigt_durch TEXT,                            -- was ihn erledigt hat („F12 beantwortet“, „von Hand: TL“)
  uid           TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft      TEXT NOT NULL DEFAULT '',
  geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX wartegrund_offen ON wartegrund (projekt_id, art, bezug) WHERE erledigt_utc IS NULL;
CREATE INDEX wartegrund_aufgabe ON wartegrund (aufgabe_id);
CREATE TRIGGER wartegrund_geaendert AFTER UPDATE ON wartegrund BEGIN UPDATE wartegrund SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER wartegrund_nie_loeschen BEFORE DELETE ON wartegrund BEGIN SELECT RAISE(ABORT, 'Verlauf: wartegrund wird nicht gelöscht'); END;
-- Was der Fragesteller vorher in der Datenbank geprüft hat (B…/F…/Regeln), Pflicht bei Fragen an den Entwickler.
ALTER TABLE frage ADD COLUMN geprueft TEXT;
-- Frühere Kennungen (Komma-getrennt) nach dem Umbenennen: gelten weiter als Absender und Empfänger.
ALTER TABLE agent ADD COLUMN alias TEXT;
