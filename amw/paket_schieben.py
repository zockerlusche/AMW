"""Eingriff „Paket früher oder später“ (A2094, TH164 „Eingriffe“, Probe D1481 v4).

Gespeichert wird je Handgriff ein Paar „A12 vor A15“ als plan_ereignis (keine Schemaänderung): ein Paar übersteht neue und fertige
Pakete, ein Platz nicht. reihenfolge.berechnen wendet die geltenden Paare an – damit folgen Disponent, Verteilen, Zeitplan und
Prognose. Weckruf und „schritt naechster“ ordnen ihre eigene Auswahl nach denselben Paaren (nachziehen); ohne Paar ändert sich dort
nichts. Der Plan-Stand (Vergleich für den Verzug) bleibt, wie er ist.

Grenzen: nur innerhalb eines Meilensteins, nie vor ein laufendes Paket, nie gegen eine Abhängigkeit (auch mittelbar). Ein Paar des
Menschen dreht der Lead nicht um. Der neueste Handgriff gilt: ein Gegengriff ersetzt das ältere Paar.
Das Paar ist eine Reihenfolge, keine Abhängigkeit: kann das vordere gerade nicht beginnen, startet das hintere trotzdem.

Ein Paar endet mit einem Ereignis und Grund (ENDE_TEXT). Was nicht erfüllt wurde, steht im Verlauf und geht gebündelt an den Lead
(eine Nachricht je Runde und Meilenstein).
"""
import json

from . import db, kern

ART = "paket_schieben"
ENDE = "paket_schieben_ende"
RICHTUNGEN = ("frueher", "spaeter")
WORT = {"frueher": "früher", "spaeter": "später"}
ENDE_TEXT = {"erfuellt": "erfüllt", "ueberholt": "„{b}“ hat vorher begonnen", "abhaengigkeit": "„{a}“ braucht jetzt „{b}“",
             "meilenstein": "die Pakete stehen nicht mehr im selben Meilenstein", "weg": "ein Paket ist verworfen oder zurückgestellt",
             "ersetzt": "neuer Handgriff", "ring": "widerspricht einem anderen Handgriff"}


def _json(text):
    try:
        d = json.loads(text or "{}")
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def offene_paare(con, pid):
    """Alle noch nicht beendeten Handgriffe, der neueste zuerst: {id, vor, nach, aid, bogen, von, grund, richtung, zeit_utc} – je Stand
    der Datenbank nur einmal gelesen (A2081)."""
    from . import einmal
    return einmal.einmal(con, (ART, pid), lambda: _offene_paare(con, pid), kopie=True)


def _offene_paare(con, pid):
    # über den Index (bogen_id, art): die Ereignisse eines Handgriffs tragen den Meilenstein, in dem er galt
    zeilen = con.execute("SELECT id, zeit_utc, von, art, text, aufgabe_id, bogen_id FROM plan_ereignis WHERE projekt_id = ? AND art IN (?, ?)"
                         " AND bogen_id IN (SELECT id FROM bogen WHERE projekt_id = ?) ORDER BY id DESC", (pid, ART, ENDE, pid)).fetchall()
    zu, aus = {_json(r["text"]).get("zu") for r in zeilen if r["art"] == ENDE}, []
    for r in zeilen:
        d = _json(r["text"])
        if r["art"] == ART and r["id"] not in zu and d.get("vor") and d.get("nach"):
            aus.append({"id": r["id"], "vor": d["vor"], "nach": d["nach"], "aid": r["aufgabe_id"], "bogen": r["bogen_id"], "von": r["von"],
                        "grund": d.get("grund"), "richtung": d.get("richtung"), "zeit_utc": r["zeit_utc"]})
    return aus


# --- Abhängigkeiten ----------------------------------------------------------------------------------------------------------

def _kanten(con, pid):
    """{aid: {Vorgänger}} über offene Pakete (nur „fertig, dann Beginn“ – die sperrt den Start)."""
    k = {}
    for v, n in con.execute("SELECT d.vor, d.nach FROM abhaengigkeit d JOIN aufgabe a ON a.id = d.vor JOIN aufgabe x ON x.id = d.nach"
                            " WHERE a.projekt_id = ? AND d.art = 'FS' AND a.status NOT IN ('fertig', 'verworfen')"
                            " AND x.status NOT IN ('fertig', 'verworfen')", (pid,)):
        k.setdefault(n, set()).add(v)
    return k


def _braucht(kanten, aid):
    """Alle offenen Pakete, die aid unmittelbar oder mittelbar braucht."""
    gesehen, stapel = set(), list(kanten.get(aid, ()))
    while stapel:
        x = stapel.pop()
        if x not in gesehen:
            gesehen.add(x)
            stapel += kanten.get(x, ())
    return gesehen


# --- Geltung -----------------------------------------------------------------------------------------------------------------

def _endet(con, paare, kanten):
    """{id: Art} der Paare, die nicht mehr gelten (Stand jetzt)."""
    ids = tuple({p[k] for p in paare for k in ("vor", "nach")})
    if not ids:
        return {}
    a = {r["id"]: r for r in con.execute(f"SELECT id, status, einstufung, bogen_id FROM aufgabe WHERE id IN ({','.join('?' * len(ids))})", ids)}
    aus = {}
    for p in paare:
        v, h = a.get(p["vor"]), a.get(p["nach"])
        if not v or not h or "verworfen" in (v["status"], h["status"]):
            aus[p["id"]] = "weg"
        elif v["status"] in ("fertig", "laeuft"):
            aus[p["id"]] = "erfuellt"
        elif h["status"] in ("fertig", "laeuft"):
            aus[p["id"]] = "ueberholt"
        elif v["bogen_id"] != h["bogen_id"] or v["bogen_id"] != p["bogen"]:
            aus[p["id"]] = "meilenstein"
        elif any(x["einstufung"] not in ("aktiv", "keine_prio") for x in (v, h)):
            aus[p["id"]] = "weg"
        elif p["nach"] in _braucht(kanten, p["vor"]):
            aus[p["id"]] = "abhaengigkeit"
    return aus


def _vertraeglich(paare, kanten):
    """Die Paare, die zusammen keinen Ring ergeben: die des Menschen zuerst, dann die neuesten. ([Paare], {id der übrigen})."""
    gilt, rest, k = [], set(), {n: set(v) for n, v in kanten.items()}
    for p in sorted(paare, key=lambda p: (p["von"] != kern.ENTWICKLER, -p["id"])):
        if p["nach"] == p["vor"] or p["nach"] in _braucht(k, p["vor"]):
            rest.add(p["id"])
            continue
        k.setdefault(p["nach"], set()).add(p["vor"])
        gilt.append(p)
    return gilt, rest


def geltende(con, pid):
    """Die geltenden Paare (ohne Beendetes und Unverträgliches)."""
    paare = offene_paare(con, pid)
    if not paare:
        return []
    kanten = _kanten(con, pid)
    zu = _endet(con, paare, kanten)
    return _vertraeglich([p for p in paare if p["id"] not in zu], kanten)[0]


def _ordnen(ids, paare, kanten):
    """ids in ihrer Reihenfolge, aber jedes Paar und jede Abhängigkeit darin gewahrt: immer das erste, dem nichts mehr vorgeht."""
    menge = set(ids)
    vor = {i: _braucht(kanten, i) & menge for i in ids}
    for p in paare:
        if p["vor"] in menge and p["nach"] in menge:
            vor[p["nach"]].add(p["vor"])
    rest, aus = list(ids), []
    while rest:
        offen = set(rest)
        x = next((i for i in rest if not vor[i] & offen), rest[0])           # ein Ring in den Abhängigkeiten: wie geliefert
        rest.remove(x)
        aus.append(x)
    return aus


def anwenden(con, pid, zeilen):
    """Für reihenfolge.berechnen: die sortierten Zeilen ({aid, bogen, zustand, …}) mit den geltenden Handgriffen. Innerhalb jedes
    Meilensteins tauschen nur die nicht laufenden ihre Plätze; jede verschobene Zeile bekommt z["hand"]."""
    paare = geltende(con, pid)
    if not paare:
        return zeilen
    kanten, aus, je = _kanten(con, pid), list(zeilen), {}
    for i, z in enumerate(zeilen):
        if z["bogen"] is not None and z["zustand"] != "laeuft":
            je.setdefault(z["bogen"], []).append(i)
    for bid in {p["bogen"] for p in paare}:
        plaetze = je.get(bid, [])
        nach_id = {zeilen[i]["aid"]: zeilen[i] for i in plaetze}
        for i, aid in zip(plaetze, _ordnen([zeilen[i]["aid"] for i in plaetze], [p for p in paare if p["bogen"] == bid], kanten)):
            aus[i] = nach_id[aid]
    je_aid = {z["aid"]: z for z in aus}
    for p in sorted(paare, key=lambda p: p["id"]):                         # der neueste zuletzt
        if p["aid"] in je_aid:
            je_aid[p["aid"]]["hand"] = {k: p[k] for k in ("von", "grund", "richtung", "zeit_utc")}
    return aus


def nachziehen(con, pid, zeilen):
    """Für Weckruf und „schritt naechster“: dieselbe Auswahl (Zeilen mit id, bogen_id, status) – nur Pakete eines Meilensteins, in dem
    ein geltender Handgriff zwei davon nennt, tauschen untereinander die Plätze. Sonst unverändert."""
    paare = geltende(con, pid) if len(zeilen) > 1 else []
    if not paare:
        return zeilen
    kanten, aus, je = _kanten(con, pid), list(zeilen), {}
    for i, z in enumerate(zeilen):
        if z["bogen_id"] is not None and z["status"] != "laeuft":
            je.setdefault(z["bogen_id"], []).append(i)
    for bid in {p["bogen"] for p in paare}:
        plaetze = je.get(bid, [])
        ids = [zeilen[i]["id"] for i in plaetze]
        eigene = [p for p in paare if p["bogen"] == bid and p["vor"] in ids and p["nach"] in ids]
        if not eigene:
            continue
        nach_id = {zeilen[i]["id"]: zeilen[i] for i in plaetze}
        for i, aid in zip(plaetze, _ordnen(ids, eigene, kanten)):
            aus[i] = nach_id[aid]
    return aus


# --- Was geht? ---------------------------------------------------------------------------------------------------------------

def _gesperrt(art, text, x=None):
    return {"geht": False, "art": art, "grund": text, "x": x}          # x: Titel bzw. Name – die Seite setzt ihn in ihre Sprache ein


def _name(con, pid, von):
    return kern.entwickler_name(con, pid) if von == kern.ENTWICKLER else von


def _richtung(con, pid, von, steht, laeuft, i, j, paare, kanten):
    """Darf das Paket auf Platz i (unter den nicht laufenden seines Meilensteins) mit dem auf Platz j tauschen?"""
    frueher = j < i
    if j < 0:
        return _gesperrt("laeuft", f"„{laeuft[-1]['titel']}“ läuft schon", laeuft[-1]["titel"]) if laeuft else _gesperrt("vorn", "steht schon vorn")
    if j >= len(steht):
        return _gesperrt("hinten", "steht schon hinten")
    z, n = steht[i], steht[j]
    erst, dann = (n, z) if frueher else (z, n)
    if erst["aid"] in _braucht(kanten, dann["aid"]):
        return _gesperrt("braucht" if frueher else "braucht_es", f"braucht „{n['titel']}“" if frueher else f"„{n['titel']}“ braucht es", n["titel"])
    if von != kern.ENTWICKLER and any(p["von"] == kern.ENTWICKLER and p["vor"] == erst["aid"] and p["nach"] == dann["aid"] for p in paare):
        name = _name(con, pid, kern.ENTWICKLER)
        return _gesperrt("mensch", f"von {name} so gesetzt", name)
    return {"geht": True, "art": None, "grund": None, "mit": n["aid"], "x": n["titel"]}


def moeglich_alle(con, pid, von=kern.ENTWICKLER):
    """{aid: {"frueher": {"geht", "grund", "art", "mit"}, "spaeter": …}} für alle offenen, nicht laufenden Pakete offener Meilensteine."""
    from . import reihenfolge
    je, aus = {}, {}
    for z in reihenfolge.berechnen(con, pid):
        je.setdefault(z["bogen"], []).append(z)
    paare, kanten = geltende(con, pid), _kanten(con, pid)
    for (bid,) in con.execute("SELECT id FROM bogen WHERE projekt_id = ? AND status IN ('geplant', 'aktiv')", (pid,)).fetchall():
        laeuft = [z for z in je.get(bid, []) if z["zustand"] == "laeuft"]
        steht = [z for z in je.get(bid, []) if z["zustand"] != "laeuft"]
        for i, z in enumerate(steht):
            aus[z["aid"]] = {"frueher": _richtung(con, pid, von, steht, laeuft, i, i - 1, paare, kanten),
                             "spaeter": _richtung(con, pid, von, steht, laeuft, i, i + 1, paare, kanten)}
    return aus


def moeglich(con, pid, aid, von=kern.ENTWICKLER):
    """{"frueher": …, "spaeter": …} für ein Paket; lässt es sich gar nicht schieben, sind beide mit demselben Grund gesperrt."""
    a = con.execute("SELECT a.*, b.status AS b_status FROM aufgabe a LEFT JOIN bogen b ON b.id = a.bogen_id WHERE a.id = ? AND a.projekt_id = ?",
                    (aid, pid)).fetchone()
    if not a:
        raise kern.AmwFehler(f"A{aid} gibt es nicht")
    if a["status"] in ("fertig", "verworfen"):
        g = _gesperrt("zu", f"ist schon {a['status']}")
    elif a["status"] == "laeuft":
        g = _gesperrt("laeuft_selbst", "läuft schon")
    elif a["einstufung"] not in ("aktiv", "keine_prio"):
        g = _gesperrt("zurueckgestellt", "ist zurückgestellt")
    elif a["bogen_id"] is None:
        g = _gesperrt("ohne", "gehört zu keinem Meilenstein")
    elif a["b_status"] not in ("geplant", "aktiv"):
        g = _gesperrt("zu", "der Meilenstein ist abgeschlossen")
    else:
        m = moeglich_alle(con, pid, von).get(aid)
        if m:
            return m
        g = _gesperrt("zu", "steht nicht in der Reihenfolge")
    return {"frueher": g, "spaeter": dict(g)}


# --- Schieben ----------------------------------------------------------------------------------------------------------------

def _titel(con, ids):
    ids = tuple(ids)
    return {r["id"]: r["titel"] for r in con.execute(f"SELECT id, titel FROM aufgabe WHERE id IN ({','.join('?' * len(ids))})", ids)} if ids else {}


def _ende_text(art, p, titel):
    return ENDE_TEXT[art].format(a=titel.get(p["vor"], f"A{p['vor']}"), b=titel.get(p["nach"], f"A{p['nach']}"))


def _beenden(con, pid, von, paare, art, titel):
    """In der Transaktion des Aufrufers: diese Paare mit Grund beenden."""
    for p in paare:
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=ENDE, aufgabe_id=p["aid"], bogen_id=p["bogen"],
                     text=json.dumps({"zu": p["id"], "vor": p["vor"], "nach": p["nach"], "art": art, "grund": _ende_text(art, p, titel)},
                                     ensure_ascii=False))


def _lage(con, pid, aid, bid):
    """Platz, geplante Zeiten und Prognose eines Pakets und seines Meilensteins – für vorher/nachher."""
    from . import planung, zeitplan
    z = next((x for x in zeitplan.berechnen(con, pid)["pakete"] if x["aid"] == aid), None) or {}
    prog = planung.prognose(con, pid, laeufe=300)
    return {"platz": z.get("platz"), "start_utc": z.get("start_utc"), "ende_utc": z.get("ende_utc"),
            "paket_p50": (prog["schritte"].get(aid) or {}).get("p50"), "meilenstein_p50": (prog["boegen"].get(bid) or {}).get("p50")}


def _handordnung(con, pid, von, v, h, grund):
    """Gilt für den Agenten beider Pakete eine Handordnung (amw liste ordnen), zieht der neueste Handgriff auch dort um."""
    from . import arbeitsliste, reihenfolge
    agenten = {r["agent"] for r in con.execute("SELECT agent FROM aufgabe WHERE id IN (?, ?)", (v, h))}
    agent = agenten.pop() if len(agenten) == 1 else None
    liste = arbeitsliste.liste(con, pid, agent) if agent else []
    ids = [x["id"] for x in liste]
    if not liste or not liste[0]["hand"] or v not in ids or h not in ids or ids.index(v) < ids.index(h):
        return
    ids.remove(v)
    ids.insert(ids.index(h), v)
    arbeitsliste._nummerieren(con, ids)
    reihenfolge.hand_setzen(con, pid, von, agent, ids, grund or liste[0]["hand"]["grund"])


def verschieben(con, pid, von, aid, richtung, grund=None):
    """Ein Paket mit seinem Nachbarn im selben Meilenstein tauschen (Mensch und Lead; der Lead mit Grund). Rückgabe: {"aufgabe",
    "richtung", "mit", "vorher", "nachher", "moeglich"}."""
    if richtung not in RICHTUNGEN:
        raise kern.AmwFehler("wohin? frueher | spaeter")
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Pakete verschieben der Mensch oder der Lead")
    grund = " ".join((grund or "").split())[:300]
    if not grund and von != kern.ENTWICKLER:
        raise kern.AmwFehler("Die Reihenfolge rechnet die AMW (kritischer Pfad) – von Hand verschieben nur mit Grund: --grund …")

    def pruefen():
        m = moeglich(con, pid, aid, von)[richtung]
        if not m["geht"]:
            raise kern.AmwFehler(f"A{aid} {WORT[richtung]} geht nicht: {m['grund']}")
        return m["mit"]
    pruefen()
    bid, nr = con.execute("SELECT b.id, b.nr FROM aufgabe a JOIN bogen b ON b.id = a.bogen_id WHERE a.id = ?", (aid,)).fetchone()
    vorher = _lage(con, pid, aid, bid)
    with db.schreiben(con):
        n = pruefen()                                                          # in der Transaktion noch einmal: es kann sich geändert haben
        v, h = (aid, n) if richtung == "frueher" else (n, aid)
        titel = _titel(con, (v, h))
        _beenden(con, pid, von, [p for p in offene_paare(con, pid) if {p["vor"], p["nach"]} == {v, h}], "ersetzt", titel)
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=ART, aufgabe_id=aid, bogen_id=bid,
                     text=json.dumps({"vor": v, "nach": h, "richtung": richtung, "grund": grund or None}, ensure_ascii=False))
        _handordnung(con, pid, von, v, h, grund)
        lead, wo = kern.lead(con, pid), "vor" if richtung == "frueher" else "hinter"
        if lead and lead != von:
            kern._posten(con, pid, von, lead, "info", f"M{nr}: A{aid} {WORT[richtung]} – jetzt {wo} A{n}",
                         f"„{titel[aid]}“ steht jetzt {wo} „{titel[n]}“" + (f". Grund: {grund}" if grund else "")
                         + ". Reihenfolge, Zeitplan und Prognose sind neu gerechnet.", aufgabe_id=aid)
    return {"aufgabe": aid, "richtung": richtung, "mit": n, "vorher": vorher, "nachher": _lage(con, pid, aid, bid),
            "moeglich": moeglich(con, pid, aid, von)}


def liste_geordnet(con, pid, von, ids):
    """In der Transaktion von arbeitsliste (ordnen, schieben, dazwischen): der neueste Handgriff gilt. Widerspricht die neue Liste
    einem Paar des Menschen, weist die AMW den Lead ab; andere widersprechende Paare enden."""
    platz = {aid: i for i, aid in enumerate(ids)}
    gegen = [p for p in geltende(con, pid) if p["vor"] in platz and p["nach"] in platz and platz[p["vor"]] > platz[p["nach"]]]
    if not gegen:
        return
    p = next((p for p in gegen if p["von"] == kern.ENTWICKLER), None)
    if p and von != kern.ENTWICKLER:
        raise kern.AmwFehler(f"A{p['vor']} steht vor A{p['nach']} – von {_name(con, pid, kern.ENTWICKLER)} so gesetzt")
    _beenden(con, pid, von, gegen, "ersetzt", _titel(con, {x[k] for x in gegen for k in ("vor", "nach")}))


# --- Verfall -----------------------------------------------------------------------------------------------------------------

def abgelaufen(con, pid):
    """Dienst: Handgriffe, die nicht mehr gelten, mit Grund beenden. Was nicht erfüllt wurde, geht an den Lead – eine Nachricht je
    Runde und Meilenstein. Rückgabe: Texte fürs Protokoll."""
    paare = offene_paare(con, pid)
    if not paare or len(geltende(con, pid)) == len(paare):
        return []
    aus, gemeldet = [], {}
    with db.schreiben(con):
        paare, kanten = offene_paare(con, pid), _kanten(con, pid)
        zu = _endet(con, paare, kanten)
        for i in _vertraeglich([p for p in paare if p["id"] not in zu], kanten)[1]:
            zu[i] = "ring"
        titel = _titel(con, {p[k] for p in paare for k in ("vor", "nach")})
        for p in reversed(paare):                                              # älteste zuerst
            art = zu.get(p["id"])
            if not art:
                continue
            _beenden(con, pid, "AMW", [p], art, titel)
            aus.append(f"A{p['vor']} vor A{p['nach']}: {art}")
            if art != "erfuellt":
                wer = _name(con, pid, p["von"]) + (f": {p['grund']}" if p["grund"] else "")
                gemeldet.setdefault(p["bogen"], []).append(f"A{p['aid']} „{titel.get(p['aid'], '?')}“ {WORT.get(p['richtung'], '')} ({wer}) – "
                                                           + _ende_text(art, p, titel))
        lead = kern.lead(con, pid)
        for bid, zeilen in gemeldet.items() if lead else ():
            nr, n = con.execute("SELECT nr FROM bogen WHERE id = ?", (bid,)).fetchone()[0], len(zeilen)
            kern._posten(con, pid, "AMW", lead, "info", f"M{nr}: {n} Verschiebung{'en gelten' if n != 1 else ' gilt'} nicht mehr – die AMW ordnet wieder",
                         "\n".join(zeilen))
    return aus
