"""A2101: Was passiert, wenn ein Agent herausgenommen wird – die Sicht darauf.

Nur lesen: nichts wird gesetzt, zugeteilt oder gemeldet. Den Einbau (Befehl, Verteilung, Verlauf) macht A2095.

- laufend     – sein laufendes Stück (arbeitsliste.laufend): läuft zu Ende oder kommt mit Übergabe-Notiz zurück in den Pool.
- wartend     – was in den Pool geht: seine Liste in ihrer Reihenfolge (arbeitsliste.liste), dahinter, was für ihn noch im
                Eingang liegt (arbeitsliste.pool) – sonst hinge es weiter an einem Agenten, den es im Team nicht mehr gibt.
- unberuehrt  – Zahl seiner fertigen, verworfenen und geparkten Pakete.
- hinweise    – kurze Sätze für den, der entscheidet.
Aktiv ist, wer nicht entfernt und eingeschaltet ist (Soll an) oder eine laufende Sitzung hat.
"""
from . import arbeitsliste, kern

LAUFENDES = ("zu_ende", "zurueck")
TEXT = {"zu_ende": "läuft zu Ende", "zurueck": "kommt mit Übergabe-Notiz zurück in den Pool"}


def folgen(con, pid, agent, laufendes):
    """{laufend: {id, titel, folge, text} | None, wartend: [{id, titel, status, gruende}], unberuehrt: Zahl, hinweise: [Satz]}.
    laufendes: was mit dem laufenden Paket geschieht – „zu_ende“ oder „zurueck“."""
    if laufendes not in LAUFENDES:
        raise kern.AmwFehler(f"Das laufende Paket: {' | '.join(LAUFENDES)} – nicht „{laufendes}“")
    zeile = kern.agent_zeile(con, pid, agent)                   # unbekannt: AmwFehler; frühere Kennung → heutige
    kennung = zeile["kennung"]
    x = arbeitsliste.laufend(con, pid, kennung)
    offen = arbeitsliste.liste(con, pid, kennung) + [_mit_gruenden(con, a) for a in arbeitsliste.pool(con, pid) if a["agent"] == kennung]
    weitere = [a["id"] for a in offen if a["status"] == "laeuft" and not (x and a["id"] == x["id"])]
    wartend = [{"id": a["id"], "titel": a["titel"], "status": a["status"], "gruende": a["gruende"]}
               for a in offen if a["status"] != "laeuft"]
    unberuehrt = sum(a["status"] not in kern.OFFEN_STATUS or a["einstufung"] == "geparkt"
                     for a in kern.aufgaben(con, pid, kennung, alle=True))
    return {"laufend": {"id": x["id"], "titel": x["titel"], "folge": laufendes, "text": f"A{x['id']} {TEXT[laufendes]}"} if x else None,
            "wartend": wartend, "unberuehrt": unberuehrt, "hinweise": _hinweise(con, pid, zeile, weitere)}


def _mit_gruenden(con, a):
    from . import wartegrund
    return dict(a, gruende=[g["bezug"] for g in wartegrund.offene(con, a["id"])])


def _andere_aktive(con, pid, kennung):
    return [r["kennung"] for r in con.execute(
        "SELECT kennung FROM agent g WHERE projekt_id = ? AND kennung != ? AND entfernt_utc IS NULL AND (soll = 'an' OR EXISTS"
        " (SELECT 1 FROM sitzung s WHERE s.agent_id = g.id AND s.zustand = 'aktiv')) ORDER BY id", (pid, kennung))]


def _hinweise(con, pid, zeile, weitere):
    kennung, aus = zeile["kennung"], []
    if zeile["entfernt_utc"]:
        aus.append(f"{kennung} ist schon entfernt.")
    elif zeile["rolle"] == "lead":
        aus.append(f"{kennung} führt das Projekt – erst die Führung übergeben.")
    if weitere:
        aus.append(f"Bei {kennung} läuft noch mehr: {', '.join(f'A{i}' for i in weitere)} – das ist vorher zu klären.")
    aktive = _andere_aktive(con, pid, kennung)
    if not aktive:
        aus.append("Sonst ist niemand im Projekt aktiv – was in den Pool geht, bleibt dort liegen.")
    elif set(aktive) <= {kern.lead(con, pid), kern.co_entwickler(con, pid)}:      # ihnen teilt die AMW nichts zu (verteilen)
        aus.append(f"Sonst sind nur Lead und Co-Entwickler aktiv ({', '.join(aktive)}) – die AMW teilt ihnen keine Pakete zu.")
    return aus
