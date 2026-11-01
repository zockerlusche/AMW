-- AMW – Agentenmanagement Workbench · Datenmodell Stufe 1 (→ doc/10-architektur.md §3)
-- Schema-Version steht in PRAGMA user_version (kein eigener Meta-Tisch).
--
-- Gemeinsame Spalten jeder Tabelle (Abgleich-fähig, → 10 L4):
--   uid           global eindeutig, wird beim Anlegen erzeugt
--   herkunft      Rechner, auf dem die Zeile entstand (setzt die Datenzugriffs-Schicht)
--   geaendert_utc letzte Änderung, Trigger hält sie aktuell
-- Zeiten immer UTC im Format 2026-11-01T08:00:00Z.
-- Verlaufs-Tabellen (nachricht, wortlaut, beschluss, aufgabe, frage, lauf, pruefung, release) werden nie gelöscht.

PRAGMA foreign_keys = ON;

CREATE TABLE projekt (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL UNIQUE,
  beschreibung  TEXT,
  pfad_repo     TEXT,
  pfad_arbeit   TEXT,
  einstellungen TEXT NOT NULL DEFAULT '{}',      -- JSON
  angelegt_utc  TEXT NOT NULL,
  uid           TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft      TEXT NOT NULL DEFAULT '',
  geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE agent (
  id               INTEGER PRIMARY KEY,
  projekt_id       INTEGER NOT NULL REFERENCES projekt(id),
  kennung          TEXT NOT NULL,                -- z. B. TL, CC1, CCamw
  rolle            TEXT,
  grenzen          TEXT,                         -- z. B. „nur 3D“
  startbefehl      TEXT,
  soll             TEXT NOT NULL DEFAULT 'an' CHECK (soll IN ('an', 'aus', 'ruht')),
  empfaengt_rund   INTEGER NOT NULL DEFAULT 1,   -- bekommt Rundschreiben („alle“)
  puls_grenze_s    INTEGER NOT NULL DEFAULT 120,
  angelegt_utc     TEXT NOT NULL,
  uid              TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft         TEXT NOT NULL DEFAULT '',
  geaendert_utc    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  UNIQUE (projekt_id, kennung)
);

-- Eine Claude-Code-Sitzung eines Agenten. Der Weck-Schlüssel steht NIE hier, nur der Pfad der
-- geschützten Datei, in die der SessionStart-Hook Pipe-Pfad und Schlüssel schreibt (→ 05 §6).
CREATE TABLE sitzung (
  id                INTEGER PRIMARY KEY,
  agent_id          INTEGER NOT NULL REFERENCES agent(id),
  claude_sitzung    TEXT,                         -- Sitzungs-ID von Claude Code
  claude_version    TEXT,
  arbeitsordner     TEXT,
  schluessel_datei  TEXT,
  gestartet_utc     TEXT NOT NULL,
  letzter_puls_utc  TEXT,
  zustand           TEXT NOT NULL DEFAULT 'aktiv' CHECK (zustand IN ('aktiv', 'ruht', 'beendet', 'tot')),
  taetigkeit        TEXT,
  aufgabe_id        INTEGER REFERENCES aufgabe(id),
  beendet_utc       TEXT,
  uid               TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft          TEXT NOT NULL DEFAULT '',
  geaendert_utc     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Die EINE Liste der Nachrichten-Arten (→ 04 #15). weckt: 1 = Empfänger wird geweckt,
-- 0 = bleibt liegen bis zum nächsten Lesen.
CREATE TABLE nachricht_art (
  art           TEXT PRIMARY KEY,
  weckt         INTEGER NOT NULL CHECK (weckt IN (0, 1)),
  beschreibung  TEXT NOT NULL
);

CREATE TABLE nachricht (
  id            INTEGER PRIMARY KEY,
  projekt_id    INTEGER NOT NULL REFERENCES projekt(id),
  zeit_utc      TEXT NOT NULL,
  von           TEXT NOT NULL,
  art           TEXT NOT NULL REFERENCES nachricht_art(art),
  kurz          TEXT NOT NULL,
  text          TEXT,
  antwort_auf   INTEGER REFERENCES nachricht(id),
  aufgabe_id    INTEGER REFERENCES aufgabe(id),
  anhang_id     INTEGER REFERENCES anhang(id),
  uid           TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft      TEXT NOT NULL DEFAULT '',
  geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX nachricht_zeit ON nachricht (projekt_id, zeit_utc);

CREATE TABLE empfang (
  nachricht_id  INTEGER NOT NULL REFERENCES nachricht(id),
  agent         TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'offen' CHECK (status IN ('offen', 'gelesen', 'erledigt')),
  gelesen_utc   TEXT,
  erledigt_utc  TEXT,
  geweckt_utc   TEXT,                             -- wann der Dienst den Empfänger geweckt hat
  bemerkung     TEXT,
  uid           TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft      TEXT NOT NULL DEFAULT '',
  geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  PRIMARY KEY (nachricht_id, agent)
);
CREATE INDEX empfang_offen ON empfang (agent, status);

CREATE TABLE aufgabe (
  id             INTEGER PRIMARY KEY,
  projekt_id     INTEGER NOT NULL REFERENCES projekt(id),
  titel          TEXT NOT NULL,
  auftrag        TEXT,
  agent          TEXT,                            -- Besitzer; nur er (oder TL) darf Status setzen
  pruefer        TEXT,
  angelegt_von   TEXT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'wartet' CHECK (status IN ('wartet', 'laeuft', 'blockiert', 'fertig', 'verworfen')),
  einstufung     TEXT NOT NULL DEFAULT 'aktiv' CHECK (einstufung IN ('aktiv', 'keine_prio', 'geparkt', 'pool')),
  rang           INTEGER NOT NULL DEFAULT 50,
  wartet_auf     TEXT,
  abhaengig_von  TEXT,                            -- Aufgaben-Nummern, Komma-getrennt
  phase          TEXT,                            -- nur Meilensteine
  beleg          TEXT,                            -- Commit, Datei:Zeile, Folgeaufgabe – Pflicht bei fertig/verworfen
  bemerkung      TEXT,
  angelegt_utc   TEXT NOT NULL,
  begonnen_utc   TEXT,
  fertig_utc     TEXT,
  geparkt_utc    TEXT,
  geparkt_von    TEXT,
  uid            TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft       TEXT NOT NULL DEFAULT '',
  geaendert_utc  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX aufgabe_offen ON aufgabe (projekt_id, status, agent);

-- Fragen an den Entwickler oder an den TL, festes Format (→ 02 §6).
CREATE TABLE frage (
  id             INTEGER PRIMARY KEY,
  projekt_id     INTEGER NOT NULL REFERENCES projekt(id),
  an             TEXT NOT NULL CHECK (an IN ('entwickler', 'tl')),
  von            TEXT NOT NULL,
  zeit_utc       TEXT NOT NULL,
  kurz           TEXT NOT NULL,                   -- die Frage in einem Satz
  worum          TEXT,                            -- worum es geht
  optionen       TEXT NOT NULL DEFAULT '[]',      -- JSON-Liste [{"kenn":"A","text":"…"}]
  empfehlung     TEXT,                            -- Kennung der empfohlenen Option
  grund          TEXT,
  fundstellen    TEXT,
  aufgabe_id     INTEGER REFERENCES aufgabe(id),
  blockiert      INTEGER NOT NULL DEFAULT 0,
  folge_von      INTEGER REFERENCES frage(id),
  status         TEXT NOT NULL DEFAULT 'offen' CHECK (status IN ('offen', 'beantwortet', 'verworfen')),
  antwort_art    TEXT CHECK (antwort_art IN ('option', 'text', 'rueckfrage')),
  antwort        TEXT,
  antwort_utc    TEXT,
  antwort_kanal  TEXT,                            -- seite, chat, cli
  uid            TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft       TEXT NOT NULL DEFAULT '',
  geaendert_utc  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE wortlaut (
  id            INTEGER PRIMARY KEY,
  projekt_id    INTEGER NOT NULL REFERENCES projekt(id),
  zeit_utc      TEXT NOT NULL,
  text          TEXT NOT NULL,
  kanal         TEXT NOT NULL,                    -- chat-tl, chat-<agent>, seite
  erfasst_von   TEXT NOT NULL,
  erfasst_utc   TEXT NOT NULL,
  bemerkung     TEXT,
  uid           TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft      TEXT NOT NULL DEFAULT '',
  geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE beschluss (
  id             INTEGER PRIMARY KEY,
  projekt_id     INTEGER NOT NULL REFERENCES projekt(id),
  zeit_utc       TEXT NOT NULL,                   -- Pflicht (→ 04 #19)
  thema          TEXT,
  stichwort      TEXT NOT NULL,
  regel          TEXT NOT NULL,
  quelle         TEXT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'gilt' CHECK (status IN ('gilt', 'ueberholt', 'unklar')),
  ersetzt_durch  INTEGER REFERENCES beschluss(id),
  wortlaut_ids   TEXT,
  aufgabe_ids    TEXT,
  angelegt_von   TEXT NOT NULL,
  angelegt_utc   TEXT NOT NULL,
  uid            TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft       TEXT NOT NULL DEFAULT '',
  geaendert_utc  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Arbeitsregeln (ebene arbeit, projekt_id NULL = gilt für alle Projekte) und Projektregeln.
-- Nur der gültige Text; Änderungen über beschluss belegt (→ 02 §7).
CREATE TABLE regel (
  id            INTEGER PRIMARY KEY,
  ebene         TEXT NOT NULL CHECK (ebene IN ('arbeit', 'projekt')),
  projekt_id    INTEGER REFERENCES projekt(id),
  nr            INTEGER NOT NULL,
  teil          TEXT,
  text          TEXT NOT NULL,
  beleg         TEXT,
  stand_utc     TEXT NOT NULL,
  uid           TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft      TEXT NOT NULL DEFAULT '',
  geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  CHECK ((ebene = 'arbeit') = (projekt_id IS NULL))
);
CREATE UNIQUE INDEX regel_nr ON regel (ebene, coalesce(projekt_id, 0), nr);

CREATE TABLE rezept (
  id                   INTEGER PRIMARY KEY,
  projekt_id           INTEGER NOT NULL REFERENCES projekt(id),
  name                 TEXT NOT NULL,
  beschreibung         TEXT,
  befehl               TEXT NOT NULL,
  braucht_schirm       INTEGER NOT NULL DEFAULT 0,
  braucht_speicher_gb  REAL NOT NULL DEFAULT 0,
  schwer               INTEGER NOT NULL DEFAULT 1,  -- schwere Läufe: höchstens einer zur Zeit
  stand_utc            TEXT NOT NULL,
  uid                  TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft             TEXT NOT NULL DEFAULT '',
  geaendert_utc        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  UNIQUE (projekt_id, name)
);

CREATE TABLE lauf (
  id                INTEGER PRIMARY KEY,
  projekt_id        INTEGER NOT NULL REFERENCES projekt(id),
  agent             TEXT NOT NULL,
  rezept_id         INTEGER REFERENCES rezept(id),
  beschreibung      TEXT NOT NULL,
  schwer            INTEGER NOT NULL DEFAULT 1,
  schirm            INTEGER NOT NULL DEFAULT 0,
  status            TEXT NOT NULL DEFAULT 'angemeldet' CHECK (status IN ('angemeldet', 'laeuft', 'fertig', 'abgebrochen')),
  angemeldet_utc    TEXT NOT NULL,
  start_utc         TEXT,
  ende_utc          TEXT,
  rc                INTEGER,
  speicher_frei_gb  REAL,
  ergebnis          TEXT,
  aufgabe_id        INTEGER REFERENCES aufgabe(id),
  rang              INTEGER NOT NULL DEFAULT 0,      -- Warteschlange: > 0 = vorgezogen (Lead/Entwickler)
  uid               TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft          TEXT NOT NULL DEFAULT '',
  geaendert_utc     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE pruefung (
  id              INTEGER PRIMARY KEY,
  projekt_id      INTEGER NOT NULL REFERENCES projekt(id),
  aufgabe_id      INTEGER REFERENCES aufgabe(id),
  zweig           TEXT NOT NULL,
  sha             TEXT NOT NULL,
  bauer           TEXT NOT NULL,
  pruefer         TEXT NOT NULL,
  punkte          TEXT,
  ergebnis        TEXT NOT NULL DEFAULT 'offen' CHECK (ergebnis IN ('offen', 'gruen', 'rot')),
  bemerkung       TEXT,
  angefragt_utc   TEXT NOT NULL,
  ergebnis_utc    TEXT,
  uid             TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft        TEXT NOT NULL DEFAULT '',
  geaendert_utc   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Anweisungen, die für einen Agenten oder alle gelten (z. B. „keine Rechen-Jobs“).
-- art 'halt' = Halt (→ 10 §5): Dienst stellt sofort ein STOPP zu und weckt danach nur noch für
-- stopp/freigabe; amw verweigert neue Läufe und Aufgaben-Starts; gilt über Neustarts hinweg bis aufgehoben.
CREATE TABLE sperre (
  id              INTEGER PRIMARY KEY,
  projekt_id      INTEGER NOT NULL REFERENCES projekt(id),
  art             TEXT NOT NULL DEFAULT 'hinweis' CHECK (art IN ('hinweis', 'halt')),
  gilt_fuer       TEXT NOT NULL,                  -- Agent-Kennung oder 'alle'
  von             TEXT NOT NULL,
  text            TEXT NOT NULL,
  seit_utc        TEXT NOT NULL,
  bis_utc         TEXT,
  aufgehoben_utc  TEXT,
  uid             TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft        TEXT NOT NULL DEFAULT '',
  geaendert_utc   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE release (
  id                   INTEGER PRIMARY KEY,
  projekt_id           INTEGER NOT NULL REFERENCES projekt(id),
  art                  TEXT NOT NULL CHECK (art IN ('merge', 'version')),
  version              TEXT,                      -- leer bei merge, bis eine Version ihn aufnimmt
  zeit_utc             TEXT NOT NULL,
  commit_sha           TEXT,
  titel                TEXT NOT NULL,
  text_intern          TEXT,
  text_oeffentlich     TEXT,
  aufgaben             TEXT,
  freigabe_utc         TEXT,
  veroeffentlicht_utc  TEXT,
  eingetragen_von      TEXT NOT NULL,
  uid                  TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft             TEXT NOT NULL DEFAULT '',
  geaendert_utc        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Gepflegte Notizen (heute tl_stand), je Projekt ein Schlüssel einmal.
CREATE TABLE notiz (
  projekt_id    INTEGER NOT NULL REFERENCES projekt(id),
  schluessel    TEXT NOT NULL,
  wert          TEXT NOT NULL,
  uid           TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft      TEXT NOT NULL DEFAULT '',
  geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  PRIMARY KEY (projekt_id, schluessel)
);

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

CREATE TABLE anhang (
  id            INTEGER PRIMARY KEY,
  projekt_id    INTEGER NOT NULL REFERENCES projekt(id),
  pfad          TEXT NOT NULL,
  sha256        TEXT,
  groesse       INTEGER,
  beschreibung  TEXT,
  angelegt_utc  TEXT NOT NULL,
  uid           TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft      TEXT NOT NULL DEFAULT '',
  geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Nachrichten-Arten: Weck-Wirkung an EINER Stelle.
INSERT INTO nachricht_art (art, weckt, beschreibung) VALUES
  ('auftrag',   1, 'Arbeit für den Empfänger'),
  ('frage',     1, 'Frage, die eine Antwort braucht'),
  ('antwort',   1, 'Antwort auf eine Frage oder Nachricht'),
  ('korrektur', 1, 'Korrektur eines früheren Auftrags'),
  ('stopp',     1, 'Sofort anhalten'),
  ('freigabe',  1, 'Freigabe, z. B. Push oder Werte'),
  ('pruefbitte',1, 'Bitte um Prüfung (Datensatz in pruefung)'),
  ('meldung',   1, 'Ergebnis oder Befund an einen bestimmten Empfänger'),
  ('takt',      1, 'Regelmäßiger Takt des Dienstes an den Lead (Zusammenfassung seit dem letzten Takt)'),
  ('info',      0, 'Zur Kenntnis, weckt nicht');

-- geaendert_utc aktuell halten (eine Zeile je Tabelle; recursive_triggers ist aus).
CREATE TRIGGER projekt_geaendert   AFTER UPDATE ON projekt   BEGIN UPDATE projekt   SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER agent_geaendert     AFTER UPDATE ON agent     BEGIN UPDATE agent     SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER sitzung_geaendert   AFTER UPDATE ON sitzung   BEGIN UPDATE sitzung   SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER nachricht_geaendert AFTER UPDATE ON nachricht BEGIN UPDATE nachricht SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER empfang_geaendert   AFTER UPDATE ON empfang   BEGIN UPDATE empfang   SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE nachricht_id = NEW.nachricht_id AND agent = NEW.agent; END;
CREATE TRIGGER aufgabe_geaendert   AFTER UPDATE ON aufgabe   BEGIN UPDATE aufgabe   SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER frage_geaendert     AFTER UPDATE ON frage     BEGIN UPDATE frage     SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER wortlaut_geaendert  AFTER UPDATE ON wortlaut  BEGIN UPDATE wortlaut  SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER beschluss_geaendert AFTER UPDATE ON beschluss BEGIN UPDATE beschluss SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER regel_geaendert     AFTER UPDATE ON regel     BEGIN UPDATE regel     SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER rezept_geaendert    AFTER UPDATE ON rezept    BEGIN UPDATE rezept    SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER lauf_geaendert      AFTER UPDATE ON lauf      BEGIN UPDATE lauf      SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER pruefung_geaendert  AFTER UPDATE ON pruefung  BEGIN UPDATE pruefung  SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER sperre_geaendert    AFTER UPDATE ON sperre    BEGIN UPDATE sperre    SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER release_geaendert   AFTER UPDATE ON release   BEGIN UPDATE release   SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER notiz_geaendert     AFTER UPDATE ON notiz     BEGIN UPDATE notiz     SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE projekt_id = NEW.projekt_id AND schluessel = NEW.schluessel; END;
CREATE TRIGGER anhang_geaendert    AFTER UPDATE ON anhang    BEGIN UPDATE anhang    SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;

-- Verlauf wird nie gelöscht, nur über Status geführt.
CREATE TRIGGER nachricht_nie_loeschen BEFORE DELETE ON nachricht BEGIN SELECT RAISE(ABORT, 'Verlauf: nachricht wird nicht gelöscht'); END;
CREATE TRIGGER wortlaut_nie_loeschen  BEFORE DELETE ON wortlaut  BEGIN SELECT RAISE(ABORT, 'Verlauf: wortlaut wird nicht gelöscht'); END;
CREATE TRIGGER beschluss_nie_loeschen BEFORE DELETE ON beschluss BEGIN SELECT RAISE(ABORT, 'Verlauf: beschluss wird nicht gelöscht'); END;
CREATE TRIGGER aufgabe_nie_loeschen   BEFORE DELETE ON aufgabe   BEGIN SELECT RAISE(ABORT, 'Verlauf: aufgabe wird nicht gelöscht'); END;
CREATE TRIGGER frage_nie_loeschen     BEFORE DELETE ON frage     BEGIN SELECT RAISE(ABORT, 'Verlauf: frage wird nicht gelöscht'); END;
CREATE TRIGGER lauf_nie_loeschen      BEFORE DELETE ON lauf      BEGIN SELECT RAISE(ABORT, 'Verlauf: lauf wird nicht gelöscht'); END;
CREATE TRIGGER pruefung_nie_loeschen  BEFORE DELETE ON pruefung  BEGIN SELECT RAISE(ABORT, 'Verlauf: pruefung wird nicht gelöscht'); END;
CREATE TRIGGER release_nie_loeschen   BEFORE DELETE ON release   BEGIN SELECT RAISE(ABORT, 'Verlauf: release wird nicht gelöscht'); END;

-- Wortlaut bleibt unverändert (→ 02 §7).
CREATE TRIGGER wortlaut_unveraendert BEFORE UPDATE OF text ON wortlaut BEGIN SELECT RAISE(ABORT, 'Wortlaut wird nicht geändert'); END;

-- Fertig/verworfen nur mit Beleg (→ KR26 heute, 02 §4).
CREATE TRIGGER aufgabe_beleg BEFORE UPDATE OF status ON aufgabe
  WHEN NEW.status IN ('fertig', 'verworfen') AND coalesce(trim(NEW.beleg), '') = ''
  BEGIN SELECT RAISE(ABORT, 'fertig/verworfen nur mit Beleg'); END;
