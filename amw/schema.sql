-- AMW – Agentenmanagement Workbench · Datenmodell Stufe 1 (→ doc/architektur.md)
-- Schema-Version steht in PRAGMA user_version (kein eigener Meta-Tisch).
--
-- Gemeinsame Spalten jeder Tabelle (Abgleich-fähig):
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
  leitbild         TEXT,                         -- JSON (→ amw/planung.py)
  dod              TEXT,                         -- JSON-Liste
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
  ordner           TEXT,                         -- Profil zum Starten (→ amw/steuerung.py)
  zusatzordner     TEXT,                         -- JSON-Liste (--add-dir)
  denkstufe        TEXT,
  modell           TEXT,
  startsatz        TEXT,
  rechte           TEXT,                         -- vorgabe | auto | umgehen
  fernsteuerung    INTEGER NOT NULL DEFAULT 1,
  neustart_auto    INTEGER NOT NULL DEFAULT 0,
  alias            TEXT,                         -- frühere Kennungen nach dem Umbenennen (Schema 12)
  fachgebiet       TEXT,                         -- Grafik, Code, Prüfen … (Schema 22; rolle ist nur noch „lead“ oder leer)
  arbeitsweise     TEXT CHECK (arbeitsweise IN ('terminal', 'desktop', 'chat')),   -- nur „terminal“ startet die AMW selbst
  zustaendig       TEXT,                         -- wofür er zuständig ist
  fasst_nicht_an   TEXT,                         -- was er nicht anfasst
  angelegt_utc     TEXT NOT NULL,
  uid              TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft         TEXT NOT NULL DEFAULT '',
  geaendert_utc    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  UNIQUE (projekt_id, kennung)
);

-- Eine Claude-Code-Sitzung eines Agenten. Der Weck-Schlüssel steht NIE hier, nur der Pfad der
-- geschützten Datei, in die der SessionStart-Hook Pipe-Pfad und Schlüssel schreibt.
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
  taetigkeit_utc    TEXT,                         -- wann taetigkeit gesetzt wurde (Alter)
  aufgabe_id        INTEGER REFERENCES aufgabe(id),
  beendet_utc       TEXT,
  kontext_prozent   REAL,
  limit_5h          REAL,
  limit_5h_reset_utc TEXT,
  limit_7t          REAL,
  limit_7t_reset_utc TEXT,
  kosten_usd        REAL,
  modell            TEXT,
  denkstufe         TEXT,
  status_utc        TEXT,
  ereignis          TEXT,
  ereignis_text     TEXT,
  ereignis_utc      TEXT,
  claude_pid        INTEGER,
  fenster_pid       INTEGER,
  uid               TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft          TEXT NOT NULL DEFAULT '',
  geaendert_utc     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Die EINE Liste der Nachrichten-Arten. weckt: 1 = Empfänger wird geweckt,
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
  dokument_id   INTEGER REFERENCES dokument(id),           -- Kommentar/Auftrag zu einem Dokument
  bis           TEXT,                            -- erledigt sich von selbst: leitbild | aufgabe | A<nr> | F<nr> (Schema 20)
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

-- Bogen = Meilenstein mit prüfbarem Abnahmekriterium; Zieldatum wird beim Aktivieren als Baseline eingefroren.
CREATE TABLE bogen (
  id               INTEGER PRIMARY KEY,
  projekt_id       INTEGER NOT NULL REFERENCES projekt(id),
  nr               INTEGER NOT NULL,                -- Reihenfolge
  titel            TEXT NOT NULL,
  ziel             TEXT,
  abnahme          TEXT,                            -- prüfbares Kriterium (Gate)
  status           TEXT NOT NULL DEFAULT 'geplant' CHECK (status IN ('geplant', 'aktiv', 'fertig', 'verworfen')),
  zieldatum        TEXT,                            -- JJJJ-MM-TT
  federfuehrend    TEXT,                            -- Kennung: nimmt Prüfergebnisse, Merge-Bitten, Fragen zum Bogen an
  baseline_datum   TEXT,
  baseline_grund   TEXT,
  angelegt_von     TEXT NOT NULL,
  angelegt_utc     TEXT NOT NULL,
  fertig_utc       TEXT,
  uid              TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft         TEXT NOT NULL DEFAULT '',
  geaendert_utc    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Spezifikation je Bogen in drei Teilen, jeder mit Freigabe durch den Menschen.
CREATE TABLE spezifikation (
  id               INTEGER PRIMARY KEY,
  bogen_id         INTEGER NOT NULL REFERENCES bogen(id),
  teil             TEXT NOT NULL CHECK (teil IN ('anforderungen', 'entwurf', 'schritte')),
  text             TEXT NOT NULL DEFAULT '',
  status           TEXT NOT NULL DEFAULT 'entwurf' CHECK (status IN ('entwurf', 'vorgelegt', 'frei', 'zurueck')),
  version          INTEGER NOT NULL DEFAULT 1,
  kommentar        TEXT,                            -- Rückmeldung des Menschen
  geschrieben_von  TEXT,
  freigabe_utc     TEXT,
  uid              TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft         TEXT NOT NULL DEFAULT '',
  geaendert_utc    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  UNIQUE (bogen_id, teil)
);

CREATE TABLE aufgabe (
  id             INTEGER PRIMARY KEY,
  projekt_id     INTEGER NOT NULL REFERENCES projekt(id),
  titel          TEXT NOT NULL,
  auftrag        TEXT,
  agent          TEXT,                            -- Besitzer; nur er (oder TL) darf Status setzen
  pruefer        TEXT,
  federfuehrend  TEXT,                            -- vor der des Bogens; zuständig = diese › Bogen › Lead
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
  bogen_id       INTEGER REFERENCES bogen(id),
  kriterien      TEXT,
  schaetzung_h   REAL,
  komplexitaet   INTEGER,
  verantwortlich TEXT,
  pruefbefehl    TEXT,
  dateibereich   TEXT,
  plan           TEXT,
  plan_status    TEXT,
  zusammenfassung TEXT,
  anforderungen  TEXT,
  uid            TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft       TEXT NOT NULL DEFAULT '',
  geaendert_utc  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX aufgabe_offen ON aufgabe (projekt_id, status, agent);

CREATE TABLE abhaengigkeit (
  vor              INTEGER NOT NULL REFERENCES aufgabe(id),
  nach             INTEGER NOT NULL REFERENCES aufgabe(id),
  art              TEXT NOT NULL DEFAULT 'FS' CHECK (art IN ('FS', 'SS', 'FF')),
  extern           TEXT,                            -- Beschreibung einer Abhängigkeit außerhalb des Projekts
  uid              TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft         TEXT NOT NULL DEFAULT '',
  geaendert_utc    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  PRIMARY KEY (vor, nach)
);

CREATE TABLE risiko (
  id               INTEGER PRIMARY KEY,
  projekt_id       INTEGER NOT NULL REFERENCES projekt(id),
  bogen_id         INTEGER REFERENCES bogen(id),
  titel            TEXT NOT NULL,
  ursache          TEXT,
  wirkung          TEXT,
  wahrscheinlichkeit INTEGER NOT NULL DEFAULT 3 CHECK (wahrscheinlichkeit BETWEEN 1 AND 5),
  auswirkung       INTEGER NOT NULL DEFAULT 3 CHECK (auswirkung BETWEEN 1 AND 5),
  strategie        TEXT CHECK (strategie IN ('vermeiden', 'mindern', 'uebertragen', 'akzeptieren')),
  massnahme        TEXT,
  verantwortlich   TEXT,
  ausloeser        TEXT,
  status           TEXT NOT NULL DEFAULT 'offen' CHECK (status IN ('offen', 'eingetreten', 'erledigt')),
  angelegt_von     TEXT NOT NULL,
  angelegt_utc     TEXT NOT NULL,
  uid              TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft         TEXT NOT NULL DEFAULT '',
  geaendert_utc    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Protokoll der Planung: Freigaben, Statuswechsel, Baseline-Änderungen (Grundlage für Verlauf und Statusbericht).
CREATE TABLE plan_ereignis (
  id               INTEGER PRIMARY KEY,
  projekt_id       INTEGER NOT NULL REFERENCES projekt(id),
  zeit_utc         TEXT NOT NULL,
  von              TEXT NOT NULL,
  art              TEXT NOT NULL,                   -- z. B. bogen_status, spec_vorgelegt, spec_frei, spec_zurueck, plan_frei, baseline
  bogen_id         INTEGER,
  aufgabe_id       INTEGER,
  text             TEXT,
  uid              TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft         TEXT NOT NULL DEFAULT '',
  geaendert_utc    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX plan_ereignis_zeit ON plan_ereignis (projekt_id, zeit_utc);

CREATE TABLE rueckblick (
  id               INTEGER PRIMARY KEY,
  projekt_id       INTEGER NOT NULL REFERENCES projekt(id),
  bogen_id         INTEGER REFERENCES bogen(id),
  art              TEXT NOT NULL CHECK (art IN ('gut', 'schlecht', 'massnahme', 'gelernt')),
  text             TEXT NOT NULL,
  von              TEXT NOT NULL,
  zeit_utc         TEXT NOT NULL,
  aufgabe_id       INTEGER REFERENCES aufgabe(id),      -- Maßnahme wurde zur Aufgabe
  beschluss_id     INTEGER REFERENCES beschluss(id),    -- … oder zum Beschluss
  uid              TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft         TEXT NOT NULL DEFAULT '',
  geaendert_utc    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Fragen an den Entwickler oder an den TL, festes Format.
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
  geparkt_utc    TEXT,                            -- geparkt: offen, aber nicht in der offenen Liste (Schema 10)
  geparkt_von    TEXT,
  geprueft       TEXT,                            -- was vorher in der Datenbank geprüft wurde (Schema 12)
  uid            TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft       TEXT NOT NULL DEFAULT '',
  geaendert_utc  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Worauf eine Aufgabe wartet (Schema 12): je Grund eine Zeile, erledigt_utc gesetzt = Grund weg.
CREATE TABLE wartegrund (
  id            INTEGER PRIMARY KEY,
  projekt_id    INTEGER NOT NULL REFERENCES projekt(id),
  aufgabe_id    INTEGER NOT NULL REFERENCES aufgabe(id),
  art           TEXT NOT NULL CHECK (art IN ('frage', 'aufgabe', 'lauf', 'agent', 'entwickler', 'monitor')),
  bezug         TEXT NOT NULL,                    -- F12, A120, L7, CC2, Entwickler, Monitor:<was>
  angelegt_utc  TEXT NOT NULL,
  angelegt_von  TEXT NOT NULL,
  erledigt_utc  TEXT,
  erledigt_durch TEXT,
  uid           TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft      TEXT NOT NULL DEFAULT '',
  geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX wartegrund_offen ON wartegrund (projekt_id, art, bezug) WHERE erledigt_utc IS NULL;
CREATE INDEX wartegrund_aufgabe ON wartegrund (aufgabe_id);

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
  zeit_utc       TEXT NOT NULL,                   -- Pflicht
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

-- Arbeitsregeln (ebene arbeit, KR) und Projektregeln (PR) – beide je Projekt (Schema 19: Projekte völlig getrennt).
-- Nur der gültige Text; Änderungen über beschluss belegt.
CREATE TABLE regel (
  id            INTEGER PRIMARY KEY,
  ebene         TEXT NOT NULL CHECK (ebene IN ('arbeit', 'projekt')),
  projekt_id    INTEGER NOT NULL REFERENCES projekt(id),
  nr            INTEGER NOT NULL,
  teil          TEXT,
  text          TEXT NOT NULL,
  beleg         TEXT,
  vorlage       TEXT,                             -- „G7/1“: aus dem Grund-Regelwerk (Regel/Fassung); leer = projekteigen (Schema 23)
  stand_utc     TEXT NOT NULL,
  uid           TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft      TEXT NOT NULL DEFAULT '',
  geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE UNIQUE INDEX regel_nr ON regel (projekt_id, ebene, nr);

CREATE TABLE rezept (
  id                   INTEGER PRIMARY KEY,
  projekt_id           INTEGER NOT NULL REFERENCES projekt(id),
  name                 TEXT NOT NULL,
  beschreibung         TEXT,
  befehl               TEXT NOT NULL,
  braucht_schirm       INTEGER NOT NULL DEFAULT 0,
  braucht_speicher_gb  REAL NOT NULL DEFAULT 0,
  schwer               INTEGER NOT NULL DEFAULT 1,  -- schwere Läufe: höchstens einer zur Zeit
  gpu                  INTEGER NOT NULL DEFAULT 0,  -- belegt die Grafikkarte (Schema 17)
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
  erwartet_min      REAL,                            -- erwartete Dauer; doppelt so lang → Warnung
  gpu               INTEGER NOT NULL DEFAULT 0,      -- belegt die Grafikkarte: PC-weit ein Lauf zur Zeit (Schema 17)
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

-- Schirm-Schalter (Schema 11): darf gerade ein Lauf am Bildschirm laufen? Eine Zeile je Wechsel, die jüngste
-- gilt; keine Zeile = zu. PC-weit (ein Bildschirm), deshalb ohne projekt_id.
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

-- Anweisungen, die für einen Agenten oder alle gelten (z. B. „keine Rechen-Jobs“).
-- art 'halt' = Halt: Dienst stellt sofort ein STOPP zu und weckt danach nur noch für
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
  projekt_id       INTEGER NOT NULL REFERENCES projekt(id),        -- je Projekt (Schema 18)
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

-- Dokumente (Schema 9): Ergebnisse der Agenten mit Versionen; Dateien im Datenordner unter dokumente/.
CREATE TABLE dokument (
  id               INTEGER PRIMARY KEY,
  projekt_id       INTEGER NOT NULL REFERENCES projekt(id),
  titel            TEXT NOT NULL,
  art              TEXT NOT NULL CHECK (art IN ('ergebnis', 'bericht', 'entwurf', 'mockup', 'bild', 'quelle')),
  bezug_art        TEXT CHECK (bezug_art IN ('bogen', 'aufgabe', 'frage', 'beschluss')),
  bezug_id         INTEGER,
  status           TEXT NOT NULL DEFAULT 'aktuell' CHECK (status IN ('aktuell', 'archiviert', 'geloescht')),
  online           INTEGER NOT NULL DEFAULT 0,          -- Datei auch online zeigen (Texte sind immer online)
  angelegt_von     TEXT NOT NULL,
  angelegt_utc     TEXT NOT NULL,
  uid              TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft         TEXT NOT NULL DEFAULT '',
  geaendert_utc    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX dokument_bezug ON dokument (projekt_id, bezug_art, bezug_id);

CREATE TABLE dokument_version (
  id               INTEGER PRIMARY KEY,
  dokument_id      INTEGER NOT NULL REFERENCES dokument(id),
  nr               INTEGER NOT NULL,
  sha256           TEXT NOT NULL,
  endung           TEXT NOT NULL,
  groesse          INTEGER NOT NULL,
  notiz            TEXT,
  von              TEXT NOT NULL,
  zeit_utc         TEXT NOT NULL,
  suchtext         TEXT,
  uid              TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft         TEXT NOT NULL DEFAULT '',
  geaendert_utc    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  UNIQUE (dokument_id, nr)
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
CREATE TRIGGER wartegrund_geaendert AFTER UPDATE ON wartegrund BEGIN UPDATE wartegrund SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
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
CREATE TRIGGER wartegrund_nie_loeschen BEFORE DELETE ON wartegrund BEGIN SELECT RAISE(ABORT, 'Verlauf: wartegrund wird nicht gelöscht'); END;
CREATE TRIGGER schirm_nie_loeschen    BEFORE DELETE ON schirm    BEGIN SELECT RAISE(ABORT, 'Verlauf: schirm wird nicht gelöscht'); END;

-- Wortlaut bleibt unverändert.
CREATE TRIGGER wortlaut_unveraendert BEFORE UPDATE OF text ON wortlaut BEGIN SELECT RAISE(ABORT, 'Wortlaut wird nicht geändert'); END;

-- Fertig/verworfen nur mit Beleg (→ KR26 heute, 02 §4).
CREATE TRIGGER aufgabe_beleg BEFORE UPDATE OF status ON aufgabe
  WHEN NEW.status IN ('fertig', 'verworfen') AND coalesce(trim(NEW.beleg), '') = ''
  BEGIN SELECT RAISE(ABORT, 'fertig/verworfen nur mit Beleg'); END;
CREATE TRIGGER dokument_geaendert AFTER UPDATE ON dokument BEGIN UPDATE dokument SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER dokument_nie_loeschen BEFORE DELETE ON dokument BEGIN SELECT RAISE(ABORT, 'Verlauf: dokument wird nicht gelöscht (Status geloescht)'); END;
CREATE TRIGGER dokument_version_nie_loeschen BEFORE DELETE ON dokument_version BEGIN SELECT RAISE(ABORT, 'Verlauf: dokument_version wird nicht gelöscht'); END;

-- Terminplaner (Schema 15): Testtermine, Fristen, Schirm-Fenster; je Vorkommen „bereit“ (Testbuild) oder abgesagt
CREATE TABLE termin (
  id            INTEGER PRIMARY KEY,
  projekt_id    INTEGER NOT NULL REFERENCES projekt(id),
  titel         TEXT NOT NULL,
  art           TEXT NOT NULL CHECK (art IN ('test', 'frist', 'schirm', 'sonstig')),
  beginn_utc    TEXT NOT NULL,                    -- erstes Vorkommen
  dauer_min     INTEGER,
  woechentlich  INTEGER NOT NULL DEFAULT 0 CHECK (woechentlich IN (0, 1)),
  bis_datum     TEXT,                             -- letzte Woche der Wiederholung (JJJJ-MM-TT), leer = ohne Ende
  vorlauf_h     REAL,                             -- test: „Testbuild fertig“ so viele Stunden vorher
  bogen_id      INTEGER REFERENCES bogen(id),     -- Ampel: Prognose dieses Bogens gegen die Frist
  notiz         TEXT,
  status        TEXT NOT NULL DEFAULT 'geplant' CHECK (status IN ('geplant', 'abgesagt')),
  angelegt_von  TEXT NOT NULL,
  angelegt_utc  TEXT NOT NULL,
  uid           TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft      TEXT NOT NULL DEFAULT '',
  geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE TRIGGER termin_geaendert AFTER UPDATE ON termin BEGIN UPDATE termin SET geaendert_utc = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END;
CREATE TRIGGER termin_nie_loeschen BEFORE DELETE ON termin BEGIN SELECT RAISE(ABORT, 'Verlauf: termin wird nicht gelöscht'); END;
CREATE TABLE termin_meldung (                   -- je Vorkommen: Testbuild bereit (mit Kurzliste) oder nur dieses abgesagt
  id            INTEGER PRIMARY KEY,
  termin_id     INTEGER NOT NULL REFERENCES termin(id),
  am_utc        TEXT NOT NULL,                    -- Beginn des Vorkommens
  art           TEXT NOT NULL CHECK (art IN ('bereit', 'abgesagt')),
  von           TEXT NOT NULL,
  zeit_utc      TEXT NOT NULL,
  text          TEXT,
  uid           TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft      TEXT NOT NULL DEFAULT '',
  geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  UNIQUE (termin_id, am_utc, art)
);
CREATE TRIGGER termin_meldung_nie_loeschen BEFORE DELETE ON termin_meldung BEGIN SELECT RAISE(ABORT, 'Verlauf: termin_meldung wird nicht gelöscht'); END;

-- Design-Dokument je Thema (Schema 16): Pfleger, Zusammenfassung „gilt jetzt“ (Fassungen), Bilder; ein Thema kann der Stil sein
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

-- Lokale KIs (Schema 17): PC-weit ki, ki_modell; je Projekt ki_vorlage (Schema 19), ki_recht; Aufträge als Läufe (Platz gpu), Herkunft
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
-- Vermerke an KI-Ergebnissen (Schema 21): ausgewählt / verworfen / nachbearbeitet – neue Zeile je Vermerk, nie geändert
CREATE TABLE ki_vermerk (
  id             INTEGER PRIMARY KEY,
  projekt_id     INTEGER NOT NULL REFERENCES projekt(id),
  dokument_id    INTEGER NOT NULL REFERENCES dokument(id),
  version_nr     INTEGER NOT NULL,                -- die Fassung, die beim Vermerk gezeigt war
  art            TEXT NOT NULL CHECK (art IN ('ausgewaehlt', 'verworfen', 'nachbearbeitet')),
  text           TEXT,                            -- nachbearbeitet: was von Hand geändert wurde (Pflicht); sonst Grund
  von            TEXT NOT NULL,
  kanal          TEXT NOT NULL CHECK (kanal IN ('cli', 'workbench', 'netz', 'bruecke')),
  zeit_utc       TEXT NOT NULL,
  uid            TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft       TEXT NOT NULL DEFAULT '',
  geaendert_utc  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX ki_vermerk_dokument ON ki_vermerk (dokument_id);
CREATE TRIGGER ki_vermerk_nie_loeschen BEFORE DELETE ON ki_vermerk BEGIN SELECT RAISE(ABORT, 'Verlauf: ki_vermerk wird nicht gelöscht'); END;
CREATE TRIGGER ki_vermerk_unveraenderlich BEFORE UPDATE ON ki_vermerk BEGIN SELECT RAISE(ABORT, 'Verlauf: ki_vermerk wird nicht geändert – neuer Vermerk'); END;
