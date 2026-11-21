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
- **Menüpunkt „Themen“:** Jedes Thema steht mit genau einem Status da: „wartet auf dich“ (eine neue Fassung ist da), „neu prüfen“ (nach deiner Freigabe kam ein neuer Beschluss – der Grund steht dabei), „in Arbeit“ oder „freigegeben“. Öffnest du ein Thema, liest du den Text als Ganzes. Am PC gibt es nur, was gerade geht: **Freigeben**, **Zurück** (mit Notiz – sie geht als Auftrag an den Betreuer), **Bearbeiten** (dein Text wird die neue Fassung, der Betreuer arbeitet sie ein) und **Löschen markieren** (gelöscht wird nichts; aufheben geht jederzeit). Am Handy liest du mit. Wartende Themen stehen unter „Für dich“ in der Übersicht und führen direkt hin. Den Status setzt niemand von Hand – die AMW leitet ihn aus Fassungen, Beschlüssen und deinen Handlungen ab. Agenten sehen ihn mit `amw thema status`.
