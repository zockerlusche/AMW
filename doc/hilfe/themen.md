# Themen: was gerade gilt

Ein Thema sammelt alle Beschlüsse zu einem System – etwa „Speichern“ oder „Karten-Look“ – und hat eine gepflegte Zusammenfassung „gilt jetzt“. So muss niemand alte Beschlüsse einzeln nachlesen.

## Du brauchst
- Einen Betreuer: den Agenten, der die Zusammenfassung schreibt und aktuell hält.

## Schritte
1. **Thema anlegen** `amw thema neu "<name>" --pfleger <agent>`.
2. **Zusammenfassung schreiben** Der Betreuer schreibt sie mit `amw thema pflegen <thema> --text-datei <datei>`.
3. **Aktuell halten** Kommt ein neuer Beschluss zum Thema dazu, gilt die Zusammenfassung als veraltet. Der Betreuer passt sie an oder bestätigt sie mit `amw thema bestaetigen <thema>`.

## Typische Fehler
- **„veraltet seit B…“** – Ein neuerer Beschluss ist noch nicht in der Zusammenfassung. Der Betreuer wird daran erinnert.
- **„Noch keine Zusammenfassung“** – Schritt 2 fehlt.

## Danach
- Ein Thema kann der Projekt-Stil sein (`amw thema einstellen <thema> --stil`); er steht dann bei allen Agenten in den Startinformationen.
