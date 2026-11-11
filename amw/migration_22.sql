-- Schema 21 → 22 (AMW 1.39.0): Agenten-Einstellungen in einer Ansicht. Bisher mischte das Feld „rolle“ zwei Dinge:
-- ob jemand das Projekt führt (genau der Wert „lead“ gab die Lead-Rechte) und sein Fachgebiet (Freitext). Und ob ein
-- Agent als Chat arbeitet, hing unsichtbar daran, dass sein Profil keinen Arbeitsordner hat.
-- Neu: rolle ist nur noch „lead“ oder leer (der Schalter „führt das Projekt“); dazu vier eigene Felder.
-- Schema auf Wort des Entwicklers.
ALTER TABLE agent ADD COLUMN fachgebiet TEXT;             -- Grafik, Code, Prüfen … (frei, mit Vorschlägen)
ALTER TABLE agent ADD COLUMN arbeitsweise TEXT CHECK (arbeitsweise IN ('terminal', 'desktop', 'chat'));
ALTER TABLE agent ADD COLUMN zustaendig TEXT;             -- wofür er zuständig ist
ALTER TABLE agent ADD COLUMN fasst_nicht_an TEXT;         -- was er nicht anfasst
-- Bestand übernehmen: eine frühere Rolle außer „lead“ war das Fachgebiet; „Grenzen“ beschrieb die Zuständigkeit
UPDATE agent SET fachgebiet = rolle, rolle = NULL WHERE rolle IS NOT NULL AND lower(rolle) != 'lead';
UPDATE agent SET rolle = 'lead' WHERE lower(rolle) = 'lead';
UPDATE agent SET zustaendig = grenzen WHERE grenzen IS NOT NULL AND trim(grenzen) != '';
-- Arbeitsweise: ein Lead ohne Arbeitsordner galt schon als Chat; alle anderen starteten im Terminal
UPDATE agent SET arbeitsweise = CASE WHEN rolle = 'lead' AND (ordner IS NULL OR ordner = '') THEN 'chat' ELSE 'terminal' END;
