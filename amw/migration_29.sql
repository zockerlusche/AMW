-- Schema 28 → 29 (AMW 1.74.0): Jede Nachricht kann einen Bezug tragen – ein Kürzel für das, worum es geht:
-- A<nr> Aufgabe · F<nr> Frage · D<nr> Dokument · M<nr> Meilenstein · P<nr> Prüfung · L<nr> Lauf · T<nr> Thema ·
-- B<nr> Beschluss · @<Kennung> Agent. Antworten erben ihn. Alte Nachrichten bekommen ihn aus aufgabe_id, dokument_id,
-- „bis“ (F<nr>) und – eine Stufe – aus der Nachricht, auf die sie antworten.
ALTER TABLE nachricht ADD COLUMN bezug TEXT;
UPDATE nachricht SET bezug = 'A' || aufgabe_id WHERE aufgabe_id IS NOT NULL;
UPDATE nachricht SET bezug = 'D' || dokument_id WHERE bezug IS NULL AND dokument_id IS NOT NULL;
UPDATE nachricht SET bezug = bis WHERE bezug IS NULL AND bis GLOB 'F[0-9]*';
UPDATE nachricht SET bezug = (SELECT b.bezug FROM nachricht b WHERE b.id = nachricht.antwort_auf)
 WHERE bezug IS NULL AND antwort_auf IS NOT NULL;
CREATE INDEX nachricht_bezug ON nachricht (projekt_id, bezug);
CREATE INDEX nachricht_antwort ON nachricht (antwort_auf);   -- Gespräche: Antworten auf eine Nachricht
