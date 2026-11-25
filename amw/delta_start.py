"""A2080 (F5384 B): Das Ja zu einer Konzeptänderung ist EIN Block – und startet.

- Neuer Meilenstein aus der Änderung: Das Ja ist zugleich seine Grob- und Plan-Freigabe, und er startet (reihenfolge.starten).
- Bestehender Meilenstein: War sein Plan vor dem Ja frei, bleibt er frei (neuer Fingerabdruck, nur durch dieses Ja); läuft er,
  werden genau die mit diesem Ja angelegten Pakete startklar – kein anderes (zurückgehaltene bleiben), und der Plan-Stand
  (Grundlage der Abweichung) bleibt. War der Plan schon offen oder geändert, bleibt er offen – die Pakete dieses Ja starten im laufenden
  Meilenstein trotzdem (A2118: der Mensch hat genau sie freigegeben), kein anderes.
- Kein neues Recht: Legt die Änderung einen neuen Meilenstein an, gibt sie nur frei, wer Grobplan UND Feinplan freigeben darf.
- Erneuert wird nur, was das Ja selbst geändert hat: Hat sich am Meilenstein daneben noch etwas anderes bewegt (ein Paket eines
  anderen, Titel, Ziel), bleibt die Freigabe offen und der Lead bekommt eine Meldung.

Ereignisse (plan_ereignis, kein Schema): Freigaben wie planansicht.freigeben, dazu "quelle": "delta", "ja": <Ereignis>, "durch";
thema_delta_start {"thema", "entwurf", "ja", "gestartet": [bogen], "erneuert": [bogen], "offen": {bogen: Grund}, "fehler": {bogen: Text}, "fehlt": {Paket: [Felder]}} – fehlt: neue Pakete, die noch nicht starten können.
"""
import json

from . import db, kern

START = "thema_delta_start"


def legt_an(entwurf):
    """Legt diese Änderung einen neuen Meilenstein an?"""
    return any(not m.get("bestehend") for m in (entwurf or {}).get("meilensteine") or [])


def mensch_noetig(con, pid, entwurf):
    """Darf nur der Mensch dieses Ja geben? Feinplan beim Menschen – oder neuer Meilenstein und Grobplan beim Menschen."""
    from . import themen
    if themen.freigabe_regel(con, pid, "plan") != "co+lead":
        return True
    return legt_an(entwurf) and themen.freigabe_regel(con, pid, "grob") != "co+lead"


def wer(con, pid, entwurf):
    """Wessen Ja die Änderung braucht (Namen) – für die Karte und die Leiste."""
    if not mensch_noetig(con, pid, entwurf):
        aus = [x for x in (kern.co_entwickler(con, pid), kern.lead(con, pid)) if x]
        if aus:
            return aus
    return [kern.entwickler_name(con, pid)]


def recht_pruefen(con, pid, von, entwurf):
    """Für alle außer dem Menschen: neuer Meilenstein und grobplan_freigabe = mensch → das Ja gibt der Mensch."""
    if von != kern.ENTWICKLER and legt_an(entwurf) and mensch_noetig(con, pid, entwurf):
        raise kern.AmwFehler("Diese Änderung legt einen neuen Meilenstein an – das Ja gibt der Mensch"
                             " (grobplan_freigabe bzw. feinplan_freigabe = mensch)")


# --- was ein Ja geändert hat ---------------------------------------------------------------------------------------------

def _bogen_der(con, pid, entwurf):
    """Die bestehenden Meilensteine, die das Ja berührt: Ziele der neuen Pakete und die der geänderten/verworfenen."""
    ids = set()
    for m in entwurf.get("meilensteine") or []:
        if m.get("bestehend"):
            r = con.execute("SELECT id FROM bogen WHERE projekt_id = ? AND nr = ?", (pid, m["bestehend"])).fetchone()
            if r:
                ids.add(r[0])
    for k in ("aendern", "verwerfen"):
        for x in entwurf.get(k) or []:
            r = con.execute("SELECT bogen_id FROM aufgabe WHERE id = ? AND projekt_id = ?", (int(str(x["paket"]).lstrip("Aa")), pid)).fetchone()
            if r and r[0]:
                ids.add(r[0])
    return sorted(ids)


def _kopf(con, bid):
    b = con.execute("SELECT titel, ziel, abnahme, zieldatum FROM bogen WHERE id = ?", (bid,)).fetchone()
    return list(b) if b else None


def _teile(con, pid, bid):
    """{Paket: Inhalt} – genau das, was der Fingerabdruck des Plans sieht (planansicht.plan_teil)."""
    from . import planansicht
    return {a["id"]: planansicht.plan_teil(con, a) for a in planansicht._pakete(con, pid, bid)}


def merken(con, pid, entwurf):
    """Vor dem Anwenden: je berührtem bestehendem Meilenstein die Freigaben und der Inhalt."""
    from . import planansicht
    z = planansicht._zustaende(con, pid)
    return {bid: {"grob": bool((z.get((bid, "grob")) or {}).get("an")), "plan": bool((z.get((bid, "plan")) or {}).get("an")),
                  "kopf": _kopf(con, bid), "teile": _teile(con, pid, bid)} for bid in _bogen_der(con, pid, entwurf)}


def _fremd(con, pid, bid, vorher, eigene):
    """Was sich außer den eigenen Paketen des Ja geändert hat – Text oder None."""
    if _kopf(con, bid) != vorher["kopf"]:
        return "Titel, Ziel oder Abnahme des Meilensteins hat sich geändert"
    jetzt = _teile(con, pid, bid)
    anders = sorted(a for a in set(jetzt) | set(vorher["teile"]) if a not in eigene and jetzt.get(a) != vorher["teile"].get(a))
    return ("inzwischen geändert: " + ", ".join(f"A{a}" for a in anders)) if anders else None


# --- nach dem Anwenden -----------------------------------------------------------------------------------------------------

def _letztes_ja(con, pid, eid):
    from . import planer
    for r in con.execute("SELECT id, von, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id DESC", (pid, planer.JA)):
        d = json.loads(r["text"] or "{}")
        if d.get("entwurf") == eid:
            return {"id": r["id"], "von": r["von"], **d}
    return None


def _durch(con, pid, von, eid):
    """Wer das Ja gegeben hat: der Mensch – oder Co und Lead (ihre Stimmen zu diesem Entwurf)."""
    from . import planer_delta
    if von == kern.ENTWICKLER:
        return [kern.ENTWICKLER]
    aus = []
    for r in con.execute("SELECT von, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id", (pid, planer_delta.STIMME)):
        if json.loads(r["text"] or "{}").get("entwurf") == eid and r["von"] not in aus:
            aus.append(r["von"])
    return aus


def _frei(con, pid, von, bid, art, ja, durch):
    """Eine Freigabe eintragen (in der Transaktion des Aufrufers)."""
    from . import planansicht
    mensch = von == kern.ENTWICKLER
    db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von if mensch else "AMW", art=planansicht.FREI, bogen_id=bid,
                 text=json.dumps({"bogen": bid, "art": art, "an": True, "fp": planansicht.fingerabdruck(con, pid, bid, art), "quelle": "delta",
                                  "ja": ja, "durch": durch, **({} if mensch else {"regel_von": "B2913"})}, ensure_ascii=False))


def _starter(con, pid, von):
    return von if kern.ist_lead(con, pid, von) else (kern.lead(con, pid) or kern.ENTWICKLER)


def _neue_startklar(con, pid, von, bid, neu, aus):
    """In einem laufenden Meilenstein nur die Pakete dieses Ja startklar setzen (Pflichtfelder wie reihenfolge.starten) und verteilen."""
    from . import reihenfolge
    aus["fehlt"].update({str(a): f for a, f in reihenfolge.neue_startklar(con, pid, _starter(con, pid, von), bid, neu).items()})   # leer: nur geändert


def _ergebnis(con, pid, tid, eid, ja, aus):
    """Das Ergebnis festhalten; Fehler und offen Gebliebenes meldet die AMW dem Lead."""
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=START,
                     text=json.dumps({"thema": int(tid), "entwurf": eid, "ja": ja, **aus}, ensure_ascii=False))
        offen = {**aus["fehler"], **aus["offen"]}
        lead = kern.lead(con, pid)
        if aus["fehlt"] and lead and lead != kern.ENTWICKLER:     # der Lead ist oft selbst der Starter – dann meldet starten nichts
            titel = {r["id"]: r["titel"] for r in con.execute("SELECT id, titel FROM aufgabe WHERE projekt_id = ?", (pid,))}
            kern._posten(con, pid, "AMW", lead, "meldung", f"Änderung TH{tid}: {len(aus['fehlt'])} Paket(e) starten noch nicht – Angaben fehlen"[:140],
                         "\n".join(f"- A{a} {titel.get(int(a), '')}: {', '.join(f)}" for a, f in aus["fehlt"].items()))
        if offen and lead and lead != kern.ENTWICKLER:
            nr = {r["id"]: r["nr"] for r in con.execute("SELECT id, nr FROM bogen WHERE projekt_id = ?", (pid,))}
            kern._posten(con, pid, "AMW", lead, "meldung", f"Änderung TH{tid}: {len(offen)} Meilenstein(e) nicht frei oder nicht gestartet"[:140],
                         "\n".join(f"- M{nr.get(int(b), b)}: {t}" for b, t in offen.items()))
    return aus


def nach_dem_ja(con, pid, von, tid, eid, entwurf, angelegt, vorher):
    """Nach _anlegen und anwenden: neue Meilensteine grob und fein freigeben und starten, freie Pläne bestehender erneuern. Ein
    Fehler beim Starten bleibt nicht still – die Seite zeigt ihn am Meilenstein, nachholen() versucht es erneut."""
    ja = _letztes_ja(con, pid, eid)
    if not ja:
        return None
    durch = _durch(con, pid, von, eid)
    aus = {"gestartet": [], "erneuert": [], "offen": {}, "fehler": {}, "fehlt": {}}
    neue = []
    for m in entwurf.get("meilensteine") or []:
        if not m.get("bestehend") and m["schluessel"] in angelegt:
            r = con.execute("SELECT id FROM bogen WHERE projekt_id = ? AND nr = ?", (pid, int(angelegt[m["schluessel"]][1:]))).fetchone()
            if r:
                neue.append(r[0])
    for bid in neue:
        _neuer(con, pid, von, bid, ja["id"], durch, aus)
    neu = {int(v[1:]) for v in angelegt.values() if v.startswith("A")}
    eigene = set(neu)
    for k in ("aendern", "verwerfen"):
        eigene |= {int(str(x["paket"]).lstrip("Aa")) for x in entwurf.get(k) or []}
    from . import planansicht, themen
    for bid, v in vorher.items():
        laeuft = con.execute("SELECT status FROM bogen WHERE id = ?", (bid,)).fetchone()[0] == "aktiv"
        try:
            fremd = _fremd(con, pid, bid, v, eigene) if v["plan"] else None
            if fremd:
                aus["offen"][str(bid)] = fremd
            if fremd or not v["plan"]:                    # der Plan war oder ist offen: er bleibt es; die eigenen Pakete starten (A2118)
                if laeuft:
                    _neue_startklar(con, pid, von, bid, neu, aus)
                continue
            z = planansicht._zustaende(con, pid)
            grob_weg = v["grob"] and not (z.get((bid, "grob")) or {}).get("an")     # ohne Grobplan zählen die Themen der Pakete mit
            with db.schreiben(con):
                if grob_weg and (von == kern.ENTWICKLER or themen.freigabe_regel(con, pid, "grob") == "co+lead"):
                    _frei(con, pid, von, bid, "grob", ja["id"], durch)
                if not (z.get((bid, "plan")) or {}).get("an"):
                    _frei(con, pid, von, bid, "plan", ja["id"], durch)
            aus["erneuert"].append(bid)
            if laeuft:
                _neue_startklar(con, pid, von, bid, neu, aus)
        except Exception as x:                           # noqa: BLE001 – angelegt ist schon alles; der Fehler gehört auf die Seite
            aus["fehler"][str(bid)] = str(x)[:300]
    return _ergebnis(con, pid, tid, eid, ja["id"], aus)


def _offene(con, bid):
    return con.execute("SELECT 1 FROM aufgabe WHERE bogen_id = ? AND status IN ('wartet', 'laeuft', 'blockiert') LIMIT 1", (bid,)).fetchone()


def _neuer(con, pid, von, bid, ja, durch, aus):
    from . import planansicht, reihenfolge
    try:
        z = planansicht._zustaende(con, pid)
        with db.schreiben(con):
            for art in ("grob", "plan"):
                if not (z.get((bid, art)) or {}).get("an"):
                    _frei(con, pid, von, bid, art, ja, durch)
        r = reihenfolge.starten(con, pid, _starter(con, pid, von), bid)
        aus["fehlt"].update({str(a): f for a, f in (r.get("fehlt") or {}).items()})
        aus["gestartet"].append(bid)
    except Exception as x:                               # noqa: BLE001 – siehe nach_dem_ja
        aus["fehler"][str(bid)] = str(x)[:300]


# --- Nachholen ---------------------------------------------------------------------------------------------------------------

def wartende(con, pid):
    """{bogen: {"thema", "entwurf", "ja", "fehler"}} – Meilensteine aus einer freigegebenen Änderung, die noch nicht laufen: aus der
    Zeit vor A2080 (nie freigegeben) oder nach einem Fehler beim Starten. Hat der Mensch sie mit Notiz zurückgegeben, warten sie
    nicht auf ihn."""
    from . import planansicht, planer
    z = None
    aus = {}
    for r in con.execute("SELECT id, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id", (pid, planer.JA)).fetchall():
        d = json.loads(r["text"] or "{}")
        e = con.execute("SELECT text FROM plan_ereignis WHERE id = ?", (d.get("entwurf"),)).fetchone() if d.get("entwurf") else None
        entwurf = (json.loads(e["text"] or "{}").get("entwurf") or {}) if e else {}
        if not entwurf.get("delta") or d.get("abgebrochen") or d.get("laeuft"):
            continue
        for m in entwurf.get("meilensteine") or []:
            nr = (d.get("angelegt") or {}).get(m["schluessel"])
            if m.get("bestehend") or not nr:
                continue
            b = con.execute("SELECT id, status FROM bogen WHERE projekt_id = ? AND nr = ?", (pid, int(nr[1:]))).fetchone()
            if not b or b["status"] != "geplant" or not _offene(con, b["id"]):
                continue
            z = planansicht._zustaende(con, pid) if z is None else z
            if any((z.get((b["id"], art)) or {}).get("notiz") for art in ("grob", "plan")):
                continue
            aus[b["id"]] = {"thema": d.get("thema"), "entwurf": d["entwurf"], "ja": r["id"], "fehler": None}
    if aus:
        for (t,) in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id", (pid, START)):
            for b, f in (json.loads(t or "{}").get("fehler") or {}).items():
                if int(b) in aus:
                    aus[int(b)]["fehler"] = f
    return aus


def unvollstaendig(con, pid):
    """{bogen: [Titel]} – mit einer Änderung angelegte Pakete, die noch nicht starten können (Angaben fehlen immer noch)."""
    from . import reihenfolge
    aus, gesehen = {}, set()
    for (t,) in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = ?", (pid, START)).fetchall():
        for aid in (json.loads(t or "{}").get("fehlt") or {}):
            a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ? AND status IN ('wartet', 'blockiert')", (int(aid), pid)).fetchone()
            if a and a["id"] not in gesehen and reihenfolge.fehlende_felder(con, pid, a):
                gesehen.add(a["id"])
                aus.setdefault(a["bogen_id"], []).append(a["titel"])
    return aus


def nachholen(con, pid, von, bid):
    """Der Mensch gibt einen wartenden Meilenstein einer Änderung frei und startet ihn (wie das Ja zum Block heute)."""
    if von != kern.ENTWICKLER:
        raise kern.AmwFehler("Das Freigeben und Starten holt der Mensch nach")
    w = wartende(con, pid).get(int(bid))
    if not w:
        raise kern.AmwFehler("Dieser Meilenstein wartet nicht (mehr) auf das Starten einer Änderung")
    aus = {"gestartet": [], "erneuert": [], "offen": {}, "fehler": {}, "fehlt": {}}
    _neuer(con, pid, von, int(bid), w["ja"], [kern.ENTWICKLER], aus)
    _ergebnis(con, pid, w["thema"], w["entwurf"], w["ja"], aus)
    if aus["fehler"]:
        raise kern.AmwFehler("Der Meilenstein ließ sich nicht starten: " + "; ".join(aus["fehler"].values()))
    return aus
