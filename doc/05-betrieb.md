# 05 · Betrieb

Anforderungen an den Unterbau. Begründungen → 04.

## 1 Wecken und Takt
- Jede handlungspflichtige Nachricht an einen Agenten weckt ihn zuverlässig – egal ob direkt oder an mehrere adressiert.
- Fällt der Wecker eines Agenten aus, merkt das System es (Puls) und weckt über einen zweiten Weg (z. B. Nachrichten zwischen Claude-Code-Sitzungen).
- Der TL-Takt (z. B. alle 2 h) läuft ohne Handarbeit; abgelaufene Erinnerungen räumen sich selbst weg.

## 2 Ressourcen
- Freien Speicher, laufende Sitzungen und Hintergrund-Prozesse anzeigen; Grenzwert je Rechen-Lauf (heute ≥ 8 GB frei).
- Höchstens ein schwerer Lauf zur Zeit (Warteschlange); Schirm-Läufe nur, wenn keine Fernwartung läuft und die Auflösung stimmt.
- Nichts Fremdes beenden.

## 3 Server
- Der Web-Server der Workbench läuft als Dienst, startet nach Absturz oder Update selbst neu, nur auf localhost.
- Neue Version wirkt ohne Handgriff des Entwicklers.

## 4 Gedächtnis
- Beim Start und nach jedem Komprimieren bekommt jeder Agent seinen Pflicht-Kontext: gültige Regeln, eigene offene Aufgaben, letzte Beschlüsse seines Themas.
- Der TL hat eigene, gepflegte Notizen (heute `tl_stand`) – Teil der Struktur, nicht Wildwuchs.

## 5 Datenhaltung
- Eine Datenbank, eine feste Struktur; Verlauf (Wortlaut, Beschlüsse, Aufgaben, Fragen, Nachrichten) wird nie gelöscht, nur im Status geführt; Regeln zeigen nur den gültigen Stand.
- Vor jeder Struktur- oder Regeländerung eine Sicherung; Änderungen nur mit Wort des Entwicklers.
- Dateien nur als Anhang mit Verweis; kein Wissen allein in Dateien.
- Zeiten in UTC speichern, in Ortszeit anzeigen.

## 6 Sicherheit
- **Standard ist lokal**; Betrieb im Netz nur bewusst über die Einstellungen.
- **Transport:** nur HTTPS (TLS), HSTS; die Datenbank ist nie direkt aus dem Netz erreichbar, nur über die AMW.
- **Anmeldung:** Konten mit starkem Passwort-Hash (z. B. Argon2) und zweitem Faktor (TOTP/Passkey); Sperre nach Fehlversuchen; Sitzungen mit sicheren Cookies (HttpOnly, Secure, SameSite), Ablauf.
- **Rechte:** Rollen je Benutzer und je Projekt; Agenten-Schlüssel nur mit den Rechten ihrer Rolle (z. B. nur eigene Nachrichten/Aufgaben).
- **Web-Angriffe:** Schutz gegen die OWASP Top 10 – Eingaben prüfen, parametrisierte Abfragen, Ausgaben maskieren, CSRF-Schutz, Content-Security-Policy und weitere Sicherheits-Header, Begrenzung der Anfragen je Zeit.
- **Geheimnisse:** keine Passwörter, Schlüssel oder Fernwartungs-IDs in DB-Texten, Repo oder Doku; Zugangsdaten nur in geschützter Konfiguration bzw. Schlüsselspeicher des Systems.
- **Nachvollziehbarkeit:** Protokoll aller Anmeldungen, Rechteänderungen und Veröffentlichungen.
- **Daten:** Sicherung verschlüsselt; personenbezogene Daten sparsam (DSGVO); Nutzerdaten der Projekte (z. B. Spielstände) nie überschreiben, nur Kopien.
- **Abhängigkeiten:** feste Versionen, regelmäßige Prüfung auf bekannte Lücken.

## 7 Verteilung und Abgleich
- **Lokal zuerst:** Agenten arbeiten immer gegen die lokale Datenbank ihres Rechners – schnell, auch ohne Netz, Wecken bleibt lokal.
- **Zentral:** ein Abgleich-Dienst schiebt Änderungen gebündelt (nicht bei jeder Zeile) an den zentralen Speicher und holt fremde Änderungen ab.
- **Konflikte:** jede Zeile hat Herkunft (Rechner) und Änderungszeit; Verlaufszeilen werden nur angehängt, nie überschrieben – Konflikte entstehen nur bei Status-Feldern und werden angezeigt.
- **Homepage:** liest nur den veröffentlichten Auszug (→ 02 §9).

## 8 Installation
- Ein Installationspaket je Betriebsart (Windows-Installer bzw. Container für den Webserver), Einrichtungs-Assistent (→ 02 §1).
- Aktualisierung ohne Datenverlust, mit Sicherung davor und Rückweg.

## 9 Kosten
- Agenten lesen gezielt (Abfragen statt ganze Tabellen), damit wenig Tokens verbraucht werden.


