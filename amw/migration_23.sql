-- Schema 22 → 23 (AMW 1.40.0): Herkunft einer Regel aus dem mitgelieferten Grund-Regelwerk.
-- „G7/1“ = Grundregel G7 aus Fassung 1 der Vorlage; leer bei projekteigenen Regeln. Die Regel bleibt eine gewöhnliche
-- Arbeitsregel des Projekts (eigene Kopie, eigene Nummer, eigener Beschluss) – das Kennzeichen übersteht Umformulieren und
-- Umnummerieren und trägt Anzeige („Grundregel“, „angepasst“) und den späteren Abgleich mit einer neuen Fassung.
-- Schema auf Wort des Entwicklers.
ALTER TABLE regel ADD COLUMN vorlage TEXT;
