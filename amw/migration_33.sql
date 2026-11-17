-- Schema 32 → 33 (AMW 1.129.0): Arbeitspakete für den Mischbetrieb (A1845, AMW 2.0 Stufe 1, D1258 v4 §3/§4, B2893).
-- Nur hinzufügen: eine Zeile je Aufgabe, die mehr als die Vorgaben hat. Keine Zeile = Art agent mit Standardwerten –
-- bestehende Aufgaben bleiben, wie sie sind. Zustände nur bei Art p; jeder Wechsel steht als plan_ereignis „paket_zustand“.
-- Abnahme-Befehl, Bereiche, Rang und „nach X“ stehen weiter an der Aufgabe (pruefbefehl, dateibereich, rang, abhaengigkeit).
CREATE TABLE paket (
  aufgabe_id        INTEGER PRIMARY KEY REFERENCES aufgabe(id),
  art               TEXT NOT NULL DEFAULT 'agent' CHECK (art IN ('agent', 'sitzung', 'p')),
  gewicht           TEXT CHECK (gewicht IN ('leicht', 'schwer')),
  ressourcen        TEXT,                          -- JSON ["gpu", "bildschirm"]
  modell            TEXT,
  effort            TEXT CHECK (effort IN ('low', 'medium', 'high')),
  pakettyp          TEXT CHECK (pakettyp IN ('normal', 'test-schreiben')),
  nie_gleichzeitig  TEXT,                          -- JSON [Aufgaben-Nummern]
  gleiche_ressource TEXT,
  zustand           TEXT CHECK (zustand IN ('entwurf', 'startklar', 'laeuft', 'abgegeben', 'abnahme', 'merge_reihe', 'gemergt',
                                            'fertig', 'blockiert', 'unklar', 'wartet_interaktiv', 'abgebrochen', 'zurueckgestellt')),
  zustand_utc       TEXT,
  herkunft          TEXT NOT NULL DEFAULT '',
  geaendert_utc     TEXT NOT NULL
);
