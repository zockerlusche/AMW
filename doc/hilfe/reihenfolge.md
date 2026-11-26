# Reihenfolge der Arbeit: eins nach dem anderen

Jeder Agent arbeitet seine Liste von oben nach unten ab und macht ein Stück fertig, bevor er das nächste beginnt. So entstehen keine halben Stände, und du siehst immer, woran gerade gearbeitet wird.

## Du brauchst
- Ein Projekt mit Lead und Agenten.

## Schritte
1. **Neues landet im Eingang** Legt der Lead oder du eine Aufgabe für einen Agenten an, der gerade arbeitet, kommt sie in den Eingang (Planung › Aufgaben › Listen). Die Steuerung zeigt, wie viele dort warten.
2. **Einplanen** Der Lead ordnet die Aufgabe in die Liste ein – frühestens hinter das laufende Stück. Als Befehl: `amw liste ordnen <agent> A12 A15`.
3. **Warten erlaubt das Nächste** Muss das laufende Stück warten (Prüfung, Lauf, Frage), trägt der Agent den Grund ein und darf das nächste beginnen. Ist der Grund erledigt, kommt das wartende Stück dran, sobald das aktuelle fertig ist.
4. **Dazwischenschieben, wenn es wirklich sein muss** Öffne die Aufgabe und drücke „Dazwischenschieben“ (mit Grund). Der Agent speichert seinen Stand, macht diese Aufgabe zuerst, danach geht es mit dem unterbrochenen Stück weiter.
5. **Freie Agenten bekommen Arbeit** Ist ein Agent frei, sucht die AMW die nächste passende startklare Aufgabe ohne Bearbeiter in einem aktiven Meilenstein – nach Rang, bei gleichem Rang die mit mehr wartenden Nachfolgern zuerst – und teilt sie in neuen Projekten selbst zu und nennt den Grund (Fachgebiet und Größe passen). In älteren Projekten schlägt sie sie dem Lead vor, bis du oder der Lead `amw projekt einstellen verteilen=an` stellen. Passt das Modell eines Agenten nicht zur Größe, bleibt es beim Vorschlag. Fällt ein Agent aus, geht seine laufende Aufgabe mit einer Übergabe-Notiz zurück, und du bekommst die Frage, ob seine Sitzung neu starten soll – starten tut nur du.

## Typische Fehler
- **„A… läuft noch – eins nach dem anderen“** – Ein Agent wollte ein zweites Stück starten. Er macht das laufende fertig oder lässt es mit Grund warten (`amw aufgabe wartet <nr> --auf …`).
- **Eine Aufgabe wartet noch auf etwas, das längst erledigt ist** – `--auf` fügt Wartegründe nur hinzu; alte bleiben offen, bis sie sich von selbst erledigen, abgehakt werden oder die Aufgabe wieder startet (ein Start schließt alle offenen Gründe). Abhaken mit `amw aufgabe wartet <nr> --erledigt <Grund>`, alten abhaken und neuen setzen in einem Schritt mit `--erledigt <alt> --auf <neu>`. Bleibt nach `--auf` ein alter Grund offen, sagt die AMW das gleich dazu.
- **Ein Auftrag kommt beim Agenten nicht an** – Er arbeitet gerade an etwas anderem. Der Auftrag liegt bereit und meldet sich, sobald der Agent eine Pause macht, sein laufendes Stück wartet oder fertig ist. Gehört er zum laufenden Stück, mit `--aufgabe <nr>` schicken. Steht seine Aufgabe in der Liste vor dem laufenden Stück, wartet er nicht auf dieses Stück.

## Danach
- Schlägt der Lead vor, etwas dazwischenzuschieben, bekommst du eine Frage mit „Ja“ und „Nein“. „Ja“ führt es aus.
- Willst du zwischendurch selbst testen, setzt der Lead (oder du) hinter ein Paket einen Prüfpunkt: `amw aufgabe pruefpunkt <nr> --grund …`. Ein Agent packt den Stand, er steht unter „Für dich“, und die Pakete dahinter warten auf dein Ja. Alles andere läuft weiter.
- Deine eigenen Aufgaben (unter „Deine Aufgaben“) ordnest du frei.
