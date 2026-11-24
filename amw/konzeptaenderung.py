"""A2026: Konzeptänderung – die Betroffenen über Thema → Meilenstein → Paket finden.

Wird ein freigegebenes Thema geändert (neue Fassung nach einer Freigabe) oder kommt eins dazu (zum ersten Mal freigegeben),
bestimmt die AMW über die Verknüpfungen, welche Meilensteine und Pakete es betrifft:

- Thema → Paket: die geltenden Themen-Verweise der Aufgaben (themen.VERWEIS, A1915).
- Paket → Meilenstein: aufgabe.bogen_id. Ein Meilenstein ist betroffen, wenn mindestens eins seiner Pakete auf das Thema
  verweist; betroffen sind genau diese Pakete. Verworfene Meilensteine und Pakete zählen nicht, Pakete ohne Meilenstein auch
  nicht (der Weg geht über den Meilenstein).

Die betroffenen Pakete teilt sie ein in
- „stoppen“      – nicht begonnen: anhalten, bevor sie nach dem alten Konzept gebaut werden,
- „zu_ende“      – laufend: zu Ende bauen, danach prüfen,
- „nacharbeit“   – fertig (auch gemergte p-Pakete): gebaut nach dem alten Stand, Nacharbeit nötig.

Nur lesen: nichts wird gesetzt, angehalten oder gemeldet. Nicht betroffene Meilensteine bleiben unberührt – sie stehen
nur als Nummern unter „unberuehrt“, damit die Anzeige zeigen kann, dass sie geprüft wurden.
"""
import json

GRUPPEN = ("stoppen", "zu_ende", "nacharbeit")
TEXT = {"stoppen": "nicht begonnen – stoppen", "zu_ende": "laufend – zu Ende bauen", "nacharbeit": "fertig – Nacharbeit nötig"}
ART_TEXT = {"geaendert": "freigegebenes Thema geändert", "neu": "Thema neu dazugekommen"}

_P_NICHT_BEGONNEN = (None, "", "entwurf", "startklar", "zurueckgestellt")
_P_FERTIG = ("gemergt", "fertig")


def einteilen(con, a):
    """Gruppe eines Pakets (Zeile aus aufgabe): stoppen | zu_ende | nacharbeit – None für verworfene."""
    from . import arbeitspaket
    if a["status"] == "verworfen":
        return None
    if a["status"] == "fertig":
        return "nacharbeit"
    p = arbeitspaket.lesen(con, a["id"])
    if p.get("art") == "p":
        z = p.get("zustand")
        if z in _P_FERTIG:
            return "nacharbeit"
        if z not in _P_NICHT_BEGONNEN:
            return "zu_ende"
    if a["status"] == "laeuft" or a["begonnen_utc"]:
        return "zu_ende"
    return "stoppen"


def _verweise(con, pid):
    """{Aufgabe: {Themen}} – die geltenden Themen-Verweise; der jüngste Eintrag je (Aufgabe, Thema) gilt."""
    from . import themen
    aus = {}
    for aid, text in con.execute("SELECT aufgabe_id, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id",
                                 (pid, themen.VERWEIS)):
        try:
            d = json.loads(text)
        except (TypeError, ValueError):
            continue
        s = aus.setdefault(aid, set())
        (s.add if d.get("an") else s.discard)(d.get("thema"))
    return aus


def _thema_ids(con, pid, themen_):
    from . import themen
    if isinstance(themen_, (int, str)):
        themen_ = [themen_]
    return list(dict.fromkeys(themen.finden(con, pid, t)["id"] for t in themen_ if str(t).strip()))


def betroffene(con, pid, themen_):
    """Betroffene der Änderung eines oder mehrerer Themen (Nummern, „TH3“ oder Namen).

    Rückgabe {"themen": [TH-Nummern], "meilensteine": [{"bogen": {id, nr, titel, status}, "themen": [...],
    "stoppen": [A…], "zu_ende": [A…], "nacharbeit": [A…]}] (nach Reihenfolge), "pakete": {A: Gruppe},
    "unberuehrt": [Meilenstein-Nummern (id) ohne betroffenes Paket]}."""
    tids = _thema_ids(con, pid, themen_)
    gesucht = set(tids)
    vw = _verweise(con, pid)
    je, pakete = {}, {}
    for aid in sorted(vw):
        treffer = vw[aid] & gesucht
        if not treffer:
            continue
        a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
        if not a or not a["bogen_id"]:
            continue
        b = con.execute("SELECT id, nr, titel, status FROM bogen WHERE id = ? AND projekt_id = ?", (a["bogen_id"], pid)).fetchone()
        if not b or b["status"] == "verworfen":
            continue
        g = einteilen(con, a)
        if not g:
            continue
        z = je.setdefault(b["id"], {"bogen": dict(b), "themen": set(), **{k: [] for k in GRUPPEN}})
        z["themen"] |= treffer
        z[g].append(aid)
        pakete[aid] = g
    ms = sorted(je.values(), key=lambda x: (x["bogen"]["nr"], x["bogen"]["id"]))
    for x in ms:
        x["themen"] = sorted(x["themen"])
    unberuehrt = [r[0] for r in con.execute("SELECT id FROM bogen WHERE projekt_id = ? AND status != 'verworfen' ORDER BY nr, id", (pid,))
                  if r[0] not in je]
    return {"themen": tids, "meilensteine": ms, "pakete": pakete, "unberuehrt": unberuehrt}


def art(con, pid, thema):
    """Was am Thema geschah: "geaendert" (es war vor der jetzigen Fassung schon freigegeben), "neu" (die jetzige Fassung ist
    die erste freigegebene) oder None (nie freigegeben – noch keine Änderung am Konzept)."""
    from . import themen
    t = themen.finden(con, pid, thema)
    f = themen._fassung(con, t["id"])
    if not f:
        return None
    if themen._war_freigegeben(con, pid, t["id"], f["nr"]):
        return "geaendert"
    if themen.status(con, t)["status"] == "frei":
        return "neu"
    return None


def aenderung(con, pid, thema):
    """Eine Konzeptänderung an einem Thema: {"thema", "name", "art", …betroffene}. Ohne Konzeptänderung (art None) ist
    nichts betroffen – alle Meilensteine bleiben unberührt."""
    from . import themen
    t = themen.finden(con, pid, thema)
    a = art(con, pid, t["id"])
    if a is None:
        alle = [r[0] for r in con.execute("SELECT id FROM bogen WHERE projekt_id = ? AND status != 'verworfen' ORDER BY nr, id", (pid,))]
        bt = {"themen": [t["id"]], "meilensteine": [], "pakete": {}, "unberuehrt": alle}
    else:
        bt = betroffene(con, pid, t["id"])
    return {"thema": t["id"], "name": t["name"], "art": a, **bt}


def zeilen(aus):
    """Lesbare Zeilen für Lead und Mensch."""
    if not aus.get("meilensteine"):
        return ["Keine Meilensteine betroffen."]
    kopf = [f"TH{aus['thema']} „{aus.get('name', '')}“: {ART_TEXT[aus['art']]}"] if aus.get("art") else []
    z = []
    for x in aus["meilensteine"]:
        b = x["bogen"]
        teile = [f"{TEXT[g]}: " + ", ".join(f"A{a}" for a in x[g]) for g in GRUPPEN if x[g]]
        z.append(f"- Meilenstein {b['nr']} „{b['titel'][:60]}“ [{b['status']}] – " + " · ".join(teile))
    if aus.get("unberuehrt"):
        z.append(f"Unberührt: {len(aus['unberuehrt'])} Meilenstein(e).")
    return kopf + z
