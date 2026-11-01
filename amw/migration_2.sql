-- Schema 1 → 2 (AMW 0.8.0): Gesprächsverlauf je Frage; bisherige Rückfragen übernehmen
CREATE TABLE frage_verlauf (                    -- Gespräch zu einer Frage: Rückfragen, Nachträge, Antwort
  id            INTEGER PRIMARY KEY,
  frage_id      INTEGER NOT NULL REFERENCES frage(id),
  zeit_utc      TEXT NOT NULL,
  von           TEXT NOT NULL,
  art           TEXT NOT NULL CHECK (art IN ('rueckfrage', 'nachtrag', 'antwort')),
  text          TEXT NOT NULL,
  nachricht_id  INTEGER REFERENCES nachricht(id),  -- die Benachrichtigung dazu (Antwort darauf = Nachtrag)
  uid           TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft      TEXT NOT NULL DEFAULT '',
  geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX frage_verlauf_frage ON frage_verlauf (frage_id, id);
CREATE INDEX frage_verlauf_nachricht ON frage_verlauf (nachricht_id);
CREATE TRIGGER frage_verlauf_nie_loeschen BEFORE DELETE ON frage_verlauf BEGIN SELECT RAISE(ABORT, 'Verlauf: frage_verlauf wird nicht gelöscht'); END;

INSERT INTO frage_verlauf (frage_id, zeit_utc, von, art, text, nachricht_id)
  SELECT f.id, coalesce(f.antwort_utc, f.zeit_utc), 'Entwickler', 'rueckfrage', f.antwort,
         (SELECT max(n.id) FROM nachricht n WHERE n.kurz LIKE 'Rückfrage zu F' || f.id || ':%')
  FROM frage f WHERE f.antwort_art = 'rueckfrage' AND f.antwort IS NOT NULL;
