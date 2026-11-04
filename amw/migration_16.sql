-- Schema 15 → 16 (AMW 1.14.0): Design-Dokument je Thema – Seite „gilt jetzt“ aus den geltenden Beschlüssen, dazu eine
-- gepflegte Zusammenfassung (versioniert) mit Pfleger; ein neuer Beschluss im Thema macht sie „veraltet“, bis der Pfleger
-- sie anpasst oder bestätigt. Ein Thema kann der Projekt-Stil sein (stil = 1), mit Bildern als verknüpfte Dokumente.
CREATE TABLE thema (
  id             INTEGER PRIMARY KEY,
  projekt_id     INTEGER NOT NULL REFERENCES projekt(id),
  name           TEXT NOT NULL,                   -- wie beschluss.thema (Groß/klein egal)
  pfleger        TEXT,                            -- Kennung: hält die Zusammenfassung aktuell
  stil           INTEGER NOT NULL DEFAULT 0 CHECK (stil IN (0, 1)),
  bestaetigt_utc TEXT,                            -- Zusammenfassung nach einem neuen Beschluss als weiter gültig bestätigt
  bestaetigt_von TEXT,
  angelegt_von   TEXT NOT NULL,
  angelegt_utc   TEXT NOT NULL,
  uid            TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft       TEXT NOT NULL DEFAULT '',
  geaendert_utc  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE UNIQUE INDEX thema_name ON thema (projekt_id, name COLLATE NOCASE);
CREATE TRIGGER thema_geaendert AFTER UPDATE ON thema BEGIN UPDATE thema SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER thema_nie_loeschen BEFORE DELETE ON thema BEGIN SELECT RAISE(ABORT, 'Verlauf: thema wird nicht gelöscht'); END;
CREATE TABLE thema_fassung (                    -- Zusammenfassung „gilt jetzt“, jede Fassung bleibt
  id             INTEGER PRIMARY KEY,
  thema_id       INTEGER NOT NULL REFERENCES thema(id),
  nr             INTEGER NOT NULL,
  text           TEXT NOT NULL,
  von            TEXT NOT NULL,
  zeit_utc       TEXT NOT NULL,
  uid            TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft       TEXT NOT NULL DEFAULT '',
  geaendert_utc  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  UNIQUE (thema_id, nr)
);
CREATE TRIGGER thema_fassung_nie_loeschen BEFORE DELETE ON thema_fassung BEGIN SELECT RAISE(ABORT, 'Verlauf: thema_fassung wird nicht gelöscht'); END;
CREATE TABLE thema_dokument (                   -- Bilder/Referenzen zur Seite (z. B. Stil: Farben, Figuren, Maßstab)
  thema_id       INTEGER NOT NULL REFERENCES thema(id),
  dokument_id    INTEGER NOT NULL REFERENCES dokument(id),
  von            TEXT NOT NULL,
  zeit_utc       TEXT NOT NULL,
  PRIMARY KEY (thema_id, dokument_id)
);
-- vorhandene Themen der Beschlüsse übernehmen (je Projekt einmal, Groß/klein egal)
INSERT INTO thema (projekt_id, name, angelegt_von, angelegt_utc)
  SELECT projekt_id, min(trim(thema)), 'AMW', strftime('%Y-%m-%dT%H:%M:%SZ', 'now') FROM beschluss
  WHERE thema IS NOT NULL AND trim(thema) != '' GROUP BY projekt_id, lower(trim(thema));
