-- Schema 16 → 17 (AMW 1.16.0): lokale KIs (→ doc/plan-lokale-ki.md). Programme und Grafikkarte gehören dem PC, deshalb sind
-- ki, ki_modell und ki_vorlage PC-weit (wie der Schirm); wer beauftragen darf, gilt je Projekt (ki_recht). Ein Auftrag ist ein
-- Lauf in der gemeinsamen Schlange mit dem Platz „gpu“ (PC-weit); ausgeführt wird er vom Dienst, nicht vom Agenten.
CREATE TABLE ki (
  id             INTEGER PRIMARY KEY,
  name           TEXT NOT NULL,                   -- z. B. ollama, comfyui
  art            TEXT NOT NULL CHECK (art IN ('sprache', 'bild', 'ton', '3d', 'video', 'sonstig')),
  schnittstelle  TEXT NOT NULL CHECK (schnittstelle IN ('ollama', 'comfyui', 'befehl')),
  endpunkt       TEXT NOT NULL,                   -- nur 127.0.0.1 / localhost / ::1
  version        TEXT,                            -- Programm-Version (die AMW liest sie bei jedem Auftrag neu)
  lizenz         TEXT,                            -- Lizenz des Programms
  ablage         TEXT,                            -- Ordner der Installation bzw. der Modelle
  startbefehl    TEXT,                            -- nur am PC (Kommandozeile), nie über Brücke oder Online-Seite
  ordner         TEXT,                            -- Arbeitsordner für den Startbefehl
  vram_gb        REAL,                            -- Richtwert
  aktiv          INTEGER NOT NULL DEFAULT 1,
  zustand        TEXT NOT NULL DEFAULT 'unbekannt' CHECK (zustand IN ('unbekannt', 'an', 'aus', 'belegt', 'gestoert')),
  zustand_text   TEXT,
  geladen        TEXT,                            -- JSON: Modelle gerade im Grafikspeicher (soweit die Schnittstelle es sagt)
  geprueft_utc   TEXT,
  angelegt_von   TEXT NOT NULL,
  angelegt_utc   TEXT NOT NULL,
  uid            TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft       TEXT NOT NULL DEFAULT '',
  geaendert_utc  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE UNIQUE INDEX ki_name ON ki (name COLLATE NOCASE);
CREATE TRIGGER ki_geaendert AFTER UPDATE ON ki BEGIN UPDATE ki SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER ki_nie_loeschen BEFORE DELETE ON ki BEGIN SELECT RAISE(ABORT, 'Verlauf: ki wird nicht gelöscht (aktiv = 0)'); END;
CREATE TABLE ki_modell (
  id              INTEGER PRIMARY KEY,
  ki_id           INTEGER NOT NULL REFERENCES ki(id),
  name            TEXT NOT NULL,                  -- Ollama: Modellname (qwen3.5:9b); ComfyUI: Kurzname
  datei           TEXT,                           -- ComfyUI: Dateiname, wie er in Vorlagen steht
  version         TEXT,
  sha256          TEXT,                           -- Prüfsumme bzw. Digest
  quelle          TEXT,                           -- URL
  lizenz          TEXT,
  nutzungsregeln  INTEGER NOT NULL DEFAULT 0 CHECK (nutzungsregeln IN (0, 1)),   -- z. B. Open RAIL++-M
  kommerziell     TEXT NOT NULL DEFAULT 'unklar' CHECK (kommerziell IN ('ja', 'nein', 'registrierung', 'unklar')),
  freigabe        TEXT NOT NULL DEFAULT 'offen' CHECK (freigabe IN ('offen', 'frei', 'gesperrt')),
  freigabe_grund  TEXT,
  freigabe_von    TEXT,
  freigabe_utc    TEXT,
  vram_gb         REAL,                           -- Probe
  sekunden        REAL,                           -- Probe: Sekunden je Auftrag (Schätzung für die Reihe)
  notiz           TEXT,
  angelegt_von    TEXT NOT NULL,
  angelegt_utc    TEXT NOT NULL,
  uid             TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft        TEXT NOT NULL DEFAULT '',
  geaendert_utc   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  UNIQUE (ki_id, name)
);
CREATE TRIGGER ki_modell_geaendert AFTER UPDATE ON ki_modell BEGIN UPDATE ki_modell SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER ki_modell_nie_loeschen BEFORE DELETE ON ki_modell BEGIN SELECT RAISE(ABORT, 'Verlauf: ki_modell wird nicht gelöscht (Freigabe gesperrt)'); END;
CREATE TABLE ki_vorlage (                       -- benannter Workflow (ComfyUI: API-JSON) mit Platzhaltern {prompt} {seed} …
  id             INTEGER PRIMARY KEY,
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
  UNIQUE (ki_id, name)
);
CREATE TRIGGER ki_vorlage_geaendert AFTER UPDATE ON ki_vorlage BEGIN UPDATE ki_vorlage SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TABLE ki_recht (                         -- wer im Projekt beauftragen darf (Lead und Entwickler immer)
  id             INTEGER PRIMARY KEY,
  projekt_id     INTEGER NOT NULL REFERENCES projekt(id),
  ki_id          INTEGER NOT NULL REFERENCES ki(id),
  wer            TEXT NOT NULL,                   -- 'alle' | 'rolle:<rolle>' | Kennung
  von            TEXT NOT NULL,
  seit_utc       TEXT NOT NULL,
  uid            TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft       TEXT NOT NULL DEFAULT '',
  geaendert_utc  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  UNIQUE (projekt_id, ki_id, wer)
);
CREATE TABLE ki_auftrag (                       -- gehört zu genau einem Lauf (Platz gpu); der Dienst führt ihn aus
  id             INTEGER PRIMARY KEY,
  projekt_id     INTEGER NOT NULL REFERENCES projekt(id),
  lauf_id        INTEGER NOT NULL UNIQUE REFERENCES lauf(id),
  ki_id          INTEGER NOT NULL REFERENCES ki(id),
  modell_id      INTEGER REFERENCES ki_modell(id),
  vorlage_id     INTEGER REFERENCES ki_vorlage(id),
  vorlage_sha256 TEXT,                            -- Stand der Vorlage beim Auftrag
  auftraggeber   TEXT NOT NULL,
  aufgabe_id     INTEGER REFERENCES aufgabe(id),
  titel          TEXT,
  prompt         TEXT NOT NULL,
  negativ        TEXT,
  seed           INTEGER NOT NULL,
  anzahl         INTEGER NOT NULL DEFAULT 1,
  breite         INTEGER,
  hoehe          INTEGER,
  eingabe        TEXT,                            -- JSON: Eingabe-Dokumente (D-Nummern)
  parameter      TEXT,                            -- JSON: weitere Angaben (z. B. temperature)
  zustand        TEXT NOT NULL DEFAULT 'wartet' CHECK (zustand IN ('wartet', 'laeuft', 'fertig', 'fehler', 'abgebrochen')),
  fortschritt    TEXT,
  extern         TEXT,                            -- JSON: Kennungen bei der KI (ComfyUI prompt_id) – nach Neustart weiter abholen
  dokumente      TEXT,                            -- JSON: abgelegte Dokumente (D-Nummern)
  fehler         TEXT,
  start_utc      TEXT,
  ende_utc       TEXT,
  dauer_s        REAL,
  vram_spitze_gb REAL,
  angelegt_utc   TEXT NOT NULL,
  uid            TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft       TEXT NOT NULL DEFAULT '',
  geaendert_utc  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX ki_auftrag_zustand ON ki_auftrag (zustand);
CREATE TRIGGER ki_auftrag_geaendert AFTER UPDATE ON ki_auftrag BEGIN UPDATE ki_auftrag SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER ki_auftrag_nie_loeschen BEFORE DELETE ON ki_auftrag BEGIN SELECT RAISE(ABORT, 'Verlauf: ki_auftrag wird nicht gelöscht'); END;
CREATE TABLE ki_herkunft (                      -- je Dokument-Version, die eine KI erzeugt hat; schreibt nur die AMW
  id               INTEGER PRIMARY KEY,
  dokument_version_id INTEGER NOT NULL UNIQUE REFERENCES dokument_version(id),
  auftrag_id       INTEGER NOT NULL REFERENCES ki_auftrag(id),
  lauf_id          INTEGER NOT NULL REFERENCES lauf(id),
  ki               TEXT NOT NULL,
  ki_version       TEXT,
  ki_lizenz        TEXT,
  modell           TEXT,
  modell_datei     TEXT,
  modell_sha256    TEXT,
  modell_lizenz    TEXT,
  modelle          TEXT,                          -- JSON: alle beteiligten Modelle (Datei, Lizenz) – z. B. VAE, Text-Encoder
  vorlage          TEXT,
  vorlage_sha256   TEXT,
  prompt           TEXT NOT NULL,
  negativ          TEXT,
  seed             INTEGER,
  parameter        TEXT,                          -- JSON
  eingabe          TEXT,                          -- JSON: D-Nummern
  dauer_s          REAL,
  vram_spitze_gb   REAL,
  gegenprobe       TEXT,                          -- z. B. Seed im PNG gefunden
  zeit_utc         TEXT NOT NULL,
  uid              TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft         TEXT NOT NULL DEFAULT '',
  geaendert_utc    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE TRIGGER ki_herkunft_nie_loeschen BEFORE DELETE ON ki_herkunft BEGIN SELECT RAISE(ABORT, 'Verlauf: ki_herkunft wird nicht gelöscht'); END;
CREATE TRIGGER ki_herkunft_unveraenderlich BEFORE UPDATE ON ki_herkunft BEGIN SELECT RAISE(ABORT, 'Verlauf: ki_herkunft wird nicht geändert'); END;
ALTER TABLE lauf ADD COLUMN gpu INTEGER NOT NULL DEFAULT 0;      -- belegt die Grafikkarte (PC-weit ein Lauf zur Zeit)
ALTER TABLE rezept ADD COLUMN gpu INTEGER NOT NULL DEFAULT 0;
