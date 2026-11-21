-- Schema 33 → 34 (AMW 1.152.0, A1898, Entscheidung F5361 A): paket.pakettyp erlaubt zusätzlich 'test-ergaenzen' (A1895).
-- SQLite kann eine CHECK-Klausel nicht ändern: Tabelle neu anlegen, alle Zeilen kopieren, alte ersetzen. Auf paket liegen
-- keine Indizes, Trigger oder Sichten. Läuft in der Transaktion von db.migrieren (Fremdschlüssel aus, danach geprüft).
CREATE TABLE paket_neu (
  aufgabe_id        INTEGER PRIMARY KEY REFERENCES aufgabe(id),
  art               TEXT NOT NULL DEFAULT 'agent' CHECK (art IN ('agent', 'sitzung', 'p')),
  gewicht           TEXT CHECK (gewicht IN ('leicht', 'schwer')),
  ressourcen        TEXT,                          -- JSON ["gpu", "bildschirm"]
  modell            TEXT,
  effort            TEXT CHECK (effort IN ('low', 'medium', 'high')),
  pakettyp          TEXT CHECK (pakettyp IN ('normal', 'test-schreiben', 'test-ergaenzen')),
  nie_gleichzeitig  TEXT,                          -- JSON [Aufgaben-Nummern]
  gleiche_ressource TEXT,
  zustand           TEXT CHECK (zustand IN ('entwurf', 'startklar', 'laeuft', 'abgegeben', 'abnahme', 'merge_reihe', 'gemergt',
                                            'fertig', 'blockiert', 'unklar', 'wartet_interaktiv', 'abgebrochen', 'zurueckgestellt')),
  zustand_utc       TEXT,
  herkunft          TEXT NOT NULL DEFAULT '',
  geaendert_utc     TEXT NOT NULL
);
INSERT INTO paket_neu (aufgabe_id, art, gewicht, ressourcen, modell, effort, pakettyp, nie_gleichzeitig, gleiche_ressource, zustand,
                       zustand_utc, herkunft, geaendert_utc)
  SELECT aufgabe_id, art, gewicht, ressourcen, modell, effort, pakettyp, nie_gleichzeitig, gleiche_ressource, zustand,
         zustand_utc, herkunft, geaendert_utc FROM paket;
DROP TABLE paket;
ALTER TABLE paket_neu RENAME TO paket;
