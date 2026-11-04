"""Arbeitsliste je Agent: geordnete Aufgaben, genau eine in Arbeit, die nächste von selbst (→ doc/automatismen.md).

Die Reihenfolge ist das Feld `rang` der Aufgabe (kleiner = weiter oben); der Lead ordnet und sortiert aus dem Pool ein.
Ein Agent arbeitet seine Liste von oben nach unten ab. Muss er warten (Prüfung, Lauf, Frage – Wartegründe), darf er die
nächste nehmen; wird eine obere wieder frei, weckt ihn die AMW, und startet er sie, wird die laufende untere von selbst
zurückgestellt (wartet auf die obere). Ist eine Aufgabe fertig, weckt die AMW mit der nächsten startbaren.
"""
from . import db, kern, wartegrund

OFFEN = ("wartet", "laeuft", "blockiert")
IN_LISTE = ("aktiv", "keine_prio")              # geparkt und pool stehen nicht in der Liste
ABSTAND = 10                                    # rang-Schritte beim Neu-Nummerieren (Platz zum Einschieben von Hand)


def liste(con, pid, agent):
    """Die Liste eines Agenten in Reihenfolge: dict je Aufgabe mit pos und offenen Gründen."""
    aus = []
    for i, r in enumerate(con.execute(
            "SELECT * FROM aufgabe WHERE projekt_id = ? AND agent = ? AND status IN ('wartet', 'laeuft', 'blockiert')"
            " AND einstufung IN ('aktiv', 'keine_prio') ORDER BY rang, id", (pid, agent)).fetchall(), 1):
        d = dict(r)
        d["pos"] = i
        d["gruende"] = [g["bezug"] for g in wartegrund.offene(con, r["id"])]
        aus.append(d)
    return aus


def pool(con, pid):
    """Ideen und Aufgaben ohne Platz in einer Liste: Einstufung pool, oder offen ohne Agent."""
    return [dict(r) for r in con.execute(
        "SELECT * FROM aufgabe WHERE projekt_id = ? AND status IN ('wartet', 'laeuft', 'blockiert')"
        " AND (einstufung = 'pool' OR ((agent IS NULL OR agent = '') AND einstufung != 'geparkt')) ORDER BY rang, id", (pid,))]


def position(con, pid, aid):
    """(agent, pos, laenge) einer Aufgabe in ihrer Liste, oder None."""
    a = con.execute("SELECT agent FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    if not a or not a["agent"]:
        return None
    l = liste(con, pid, a["agent"])
    for x in l:
        if x["id"] == aid:
            return a["agent"], x["pos"], len(l)
    return None


def _nummerieren(con, ids):
    for i, aid in enumerate(ids, 1):
        con.execute("UPDATE aufgabe SET rang = ? WHERE id = ?", (i * ABSTAND, aid))


def ordnen(con, pid, von, agent, ids):
    """Lead: diese Aufgaben in dieser Reihenfolge oben in die Liste des Agenten (aus dem Pool oder ohne Agent: werden
    ihm zugeteilt), der Rest seiner Liste folgt dahinter in bisheriger Reihenfolge."""
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Listen ordnen dürfen nur Lead und Entwickler")
    agent = kern.agent_zeile(con, pid, agent)["kennung"]
    if len(set(ids)) != len(ids):
        raise kern.AmwFehler("eine Aufgabe doppelt genannt")
    with db.schreiben(con):
        for aid in ids:
            a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
            if not a:
                raise kern.AmwFehler(f"A{aid} gibt es nicht")
            if a["status"] not in OFFEN:
                raise kern.AmwFehler(f"A{aid} ist {a['status']} – nur offene Aufgaben in die Liste")
            if a["agent"] and a["agent"] != agent:
                raise kern.AmwFehler(f"A{aid} gehört {a['agent']} – erst dort herausnehmen (amw aufgabe aendern {aid} --agent {agent})")
            con.execute("UPDATE aufgabe SET agent = ?, einstufung = CASE WHEN einstufung IN ('pool', 'geparkt')"
                        " THEN 'aktiv' ELSE einstufung END WHERE id = ?", (agent, aid))
        rest = [x["id"] for x in liste(con, pid, agent) if x["id"] not in ids]
        _nummerieren(con, list(ids) + rest)
    return liste(con, pid, agent)


def schieben(con, pid, von, aid, vor=None, nach=None, pos=None, oben=False, unten=False):
    """Lead: eine Aufgabe innerhalb ihrer Liste verschieben (vor/nach einer anderen, an Position pos, ganz oben/unten)."""
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Listen ordnen dürfen nur Lead und Entwickler")
    p = position(con, pid, aid)
    if not p:
        raise kern.AmwFehler(f"A{aid} steht in keiner Liste (offen, mit Agent, nicht geparkt/pool)")
    agent = p[0]
    ids = [x["id"] for x in liste(con, pid, agent) if x["id"] != aid]
    if oben:
        i = 0
    elif unten:
        i = len(ids)
    elif pos:
        i = max(0, min(len(ids), int(pos) - 1))
    elif vor or nach:
        bezug = vor or nach
        if bezug not in ids:
            raise kern.AmwFehler(f"A{bezug} steht nicht in der Liste von {agent}")
        i = ids.index(bezug) + (1 if nach else 0)
    else:
        raise kern.AmwFehler("wohin? --vor A… | --nach A… | --pos N | --oben | --unten")
    ids.insert(i, aid)
    with db.schreiben(con):
        _nummerieren(con, ids)
    return liste(con, pid, agent)


def beim_start(con, pid, von, a, hinweise=None):
    """In aufgabe_status (Transaktion läuft): genau eine in Arbeit. Läuft eine WEITER UNTEN stehende, wird sie
    zurückgestellt (wartet auf die gestartete); läuft eine WEITER OBEN stehende, gibt es einen Hinweis und der Lead
    erfährt es. Rückgabe: Liste der zurückgestellten Nummern."""
    agent = a["agent"] or von
    zurueck = []
    for x in con.execute("SELECT * FROM aufgabe WHERE projekt_id = ? AND agent = ? AND status = 'laeuft' AND id != ?"
                         " AND einstufung IN ('aktiv', 'keine_prio')", (pid, agent, a["id"])).fetchall():
        if (x["rang"], x["id"]) > (a["rang"], a["id"]):          # die laufende steht weiter unten → zurückstellen
            con.execute("UPDATE aufgabe SET status = 'wartet' WHERE id = ?", (x["id"],))
            wartegrund.anlegen(con, pid, von, x["id"], f"A{a['id']}")
            zurueck.append(x["id"])
            if hinweise is not None:
                hinweise.append(f"A{x['id']} zurückgestellt – wartet auf A{a['id']}; ist die fertig, weckt dich die AMW damit")
        else:
            if hinweise is not None:
                hinweise.append(f"Achtung: A{x['id']} steht weiter oben und läuft noch – genau eine in Arbeit. Erst fertig"
                                f" oder mit Grund warten lassen (amw aufgabe wartet {x['id']} --auf …)")
            l = kern.lead(con, pid)
            if l and l != agent:
                kern._posten(con, pid, "AMW", l, "meldung", f"{agent} hat zwei in Arbeit: A{x['id']} (weiter oben) und"
                             f" A{a['id']}", f"A{x['id']}: {x['titel']}\nA{a['id']}: {a['titel']}", aufgabe_id=a["id"])
    return zurueck


def beim_abschluss(con, pid, a, geweckt):
    """In aufgabe_status nach fertig/verworfen (Transaktion läuft): den Besitzer mit der nächsten startbaren Aufgabe
    seiner Liste wecken – außer die AMW hat ihn gerade schon mit einer geweckt (geweckt: Nummern) oder er arbeitet schon
    an einer."""
    agent = a["agent"]
    if not agent or agent == kern.ENTWICKLER or not con.execute(
            "SELECT 1 FROM agent WHERE projekt_id = ? AND kennung = ?", (pid, agent)).fetchone():
        return None
    if con.execute("SELECT 1 FROM aufgabe WHERE projekt_id = ? AND agent = ? AND status = 'laeuft'", (pid, agent)).fetchone():
        return None
    eigene_geweckt = {x for x in geweckt or [] if con.execute("SELECT 1 FROM aufgabe WHERE id = ? AND agent = ?",
                                                              (x, agent)).fetchone()}
    if eigene_geweckt:
        return None
    frei = [x for x in wartegrund.freie_arbeit(con, pid, agent) if x["id"] != a["id"]]
    if not frei:
        return None
    n = frei[0]
    p = position(con, pid, n["id"])
    kern._posten(con, pid, "AMW", agent, "meldung",
                 f"A{a['id']} {a['status'] if a['status'] in ('fertig', 'verworfen') else 'abgeschlossen'} – weiter in deiner"
                 f" Liste: A{n['id']}" + (f" (Pos {p[1]}/{p[2]})" if p else "") + f": {n['titel'][:100]}",
                 f"amw aufgabe start {n['id']}", aufgabe_id=n["id"])
    return n["id"]
