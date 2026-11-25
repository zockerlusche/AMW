"""A2118 (2): einen offenen Entwurf des Planers zurückstellen – er wartet, mit Grund, bis Lead oder Co ihn wieder freischalten.

Solange steht im Projektweg und in Planung › Meilensteine statt des Knopfs „wartet: <Grund>“; er zählt nicht als „wartet auf dich“ und
hält die Schritt-Leiste nicht. Dem Menschen nimmt das kein Recht: „Trotzdem freigeben“ steht hinter einem Klick, mit Rückfrage. Lead und
Co geben ihn erst nach dem Freischalten frei. Es gilt für genau diesen Entwurf – ein neuer Entwurf wartet nicht.

Ereignis, kein Schema: thema_entwurf_wartet {"thema", "entwurf", "an", "grund"}; das jüngste je Entwurf gilt.
"""
import json

from . import db, kern

ART = "thema_entwurf_wartet"
GRUND_MAX = 200


def stand(con, pid, eid):
    """{"grund", "von", "seit_utc"}, wenn dieser Entwurf wartet – sonst None."""
    for r in con.execute("SELECT zeit_utc, von, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id DESC", (pid, ART)):
        d = json.loads(r["text"] or "{}")
        if d.get("entwurf") == eid:
            return {"grund": d.get("grund"), "von": r["von"], "seit_utc": r["zeit_utc"]} if d.get("an") else None
    return None


def _entwurf(con, pid, von, name):
    from . import planer, themen
    if not (kern.ist_lead(con, pid, von) or kern.ist_co(con, pid, von)):
        raise kern.AmwFehler("Einen Entwurf stellen Lead, Co-Entwickler oder der Mensch zurück")
    t = themen.finden(con, pid, name)
    e = planer.letzter_entwurf(con, pid, t["id"])
    if not e or e.get("fehler") or planer.erledigt(con, pid, e["id"]) or planer.geklaert(con, pid, t["id"], e["id"]):
        raise kern.AmwFehler(f"TH{t['id']} hat keinen offenen Entwurf")
    return t["id"], e


def _eintragen(con, pid, von, tid, eid, an, grund=None):
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=ART,
                     text=json.dumps({"thema": tid, "entwurf": eid, "an": an, "grund": grund}, ensure_ascii=False))


def _vom_menschen(con, pid, von, tid, w):
    """Wartet er durch den Menschen, ändert nur der Mensch Grund oder Zustand."""
    if w and w["von"] == kern.ENTWICKLER and von != kern.ENTWICKLER:
        raise kern.AmwFehler(f"Den Entwurf zu TH{tid} hat {kern.entwickler_name(con, pid)} zurückgestellt – das hebt nur {kern.entwickler_name(con, pid)} auf")


def zurueckstellen(con, pid, von, name, grund):
    """`amw thema entwurf-warten TH<n> --grund …`. Rückgabe: Themennummer."""
    grund = " ".join((grund or "").split())
    if not grund:
        raise kern.AmwFehler("Zurückstellen nur mit Grund: --grund …")
    if len(grund) > GRUND_MAX:
        raise kern.AmwFehler(f"Der Grund steht auf der Karte – höchstens {GRUND_MAX} Zeichen")
    tid, e = _entwurf(con, pid, von, name)
    _vom_menschen(con, pid, von, tid, stand(con, pid, e["id"]))         # sonst wäre der Lead der jüngste Eintrag und schaltete selbst frei
    _eintragen(con, pid, von, tid, e["id"], True, grund)
    return tid


def freischalten(con, pid, von, name):
    """`amw thema entwurf-weiter TH<n>`. Was der Mensch zurückgestellt hat, schaltet nur er frei. Rückgabe: Themennummer."""
    tid, e = _entwurf(con, pid, von, name)
    w = stand(con, pid, e["id"])
    if not w:
        raise kern.AmwFehler(f"Der Entwurf zu TH{tid} wartet nicht")
    _vom_menschen(con, pid, von, tid, w)
    _eintragen(con, pid, von, tid, e["id"], False)
    return tid


def sperre(con, pid, von, tid, eid):
    """Vor dem Ja: Lead und Co geben einen wartenden Entwurf erst nach dem Freischalten frei; der Mensch darf es."""
    w = stand(con, pid, eid) if von != kern.ENTWICKLER else None
    if w:
        raise kern.AmwFehler(f"Der Entwurf zu TH{tid} wartet ({w['grund']}) – erst freischalten: amw thema entwurf-weiter TH{tid}")
