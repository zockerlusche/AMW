-- Schema 18 → 19 (AMW 1.20.0): Projekte völlig getrennt (→ doc/plan-projektwahl.md). Arbeitsregeln (KR) galten für alle
-- Projekte einer AMW, KI-Vorlagen waren PC-weit – ein Projekt hätte so Regeln und Bild-Workflows des anderen geändert.
-- Jetzt gehört jede Regel und jede Vorlage genau einem Projekt. Vorhandene Arbeitsregeln gehören dem Projekt ihres
-- Beschlusses, Vorlagen dem Projekt ihres Absenders, sonst dem ersten Projekt. SQLite ändert keine CHECK/UNIQUE-
-- Bedingung, darum werden beide Tabellen neu angelegt; ki_auftrag verweist auf ki_vorlage (gleiche ids; migrieren() prüft
-- die Fremdschlüssel vor dem Abschluss).

CREATE TABLE regel_neu (
  id            INTEGER PRIMARY KEY,
  ebene         TEXT NOT NULL CHECK (ebene IN ('arbeit', 'projekt')),
  projekt_id    INTEGER NOT NULL REFERENCES projekt(id),
  nr            INTEGER NOT NULL,
  teil          TEXT,
  text          TEXT NOT NULL,
  beleg         TEXT,
  stand_utc     TEXT NOT NULL,
  uid           TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft      TEXT NOT NULL DEFAULT '',
  geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
INSERT INTO regel_neu (id, ebene, projekt_id, nr, teil, text, beleg, stand_utc, uid, herkunft, geaendert_utc)
  SELECT id, ebene, coalesce(projekt_id, (SELECT b.projekt_id FROM beschluss b WHERE 'B' || b.id = r.beleg),
                             (SELECT min(id) FROM projekt)),
         nr, teil, text, beleg, stand_utc, uid, herkunft, geaendert_utc FROM regel r;
DROP TABLE regel;
ALTER TABLE regel_neu RENAME TO regel;
CREATE UNIQUE INDEX regel_nr ON regel (projekt_id, ebene, nr);
CREATE TRIGGER regel_geaendert     AFTER UPDATE ON regel     BEGIN UPDATE regel     SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;

CREATE TABLE ki_vorlage_neu (                   -- benannter Workflow (ComfyUI: API-JSON) mit Platzhaltern {prompt} {seed} …
  id             INTEGER PRIMARY KEY,
  projekt_id     INTEGER NOT NULL REFERENCES projekt(id),
  ki_id          INTEGER NOT NULL REFERENCES ki(id),
  name           TEXT NOT NULL,
  beschreibung   TEXT,
  inhalt         TEXT NOT NULL,
  sha256         TEXT NOT NULL,
  von            TEXT NOT NULL,
  stand_utc      TEXT NOT NULL,
  aktiv          INTEGER NOT NULL DEFAULT 1,
  uid            TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft       TEXT NOT NULL DEFAULT '',
  geaendert_utc  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  UNIQUE (projekt_id, ki_id, name)
);
INSERT INTO ki_vorlage_neu (id, projekt_id, ki_id, name, beschreibung, inhalt, sha256, von, stand_utc, aktiv, uid, herkunft,
                            geaendert_utc)
  SELECT id, coalesce((SELECT min(a.projekt_id) FROM agent a WHERE a.kennung = v.von), (SELECT min(id) FROM projekt)),
         ki_id, name, beschreibung, inhalt, sha256, von, stand_utc, aktiv, uid, herkunft, geaendert_utc FROM ki_vorlage v;
DROP TABLE ki_vorlage;
ALTER TABLE ki_vorlage_neu RENAME TO ki_vorlage;
CREATE TRIGGER ki_vorlage_geaendert AFTER UPDATE ON ki_vorlage BEGIN UPDATE ki_vorlage SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
