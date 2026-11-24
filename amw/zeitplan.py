"""A2045 (V7, D1531 §8): Zeitplan je Paket – geplante Start- und Endzeit.

Grundlage ist die berechnete Reihenfolge (reihenfolge.berechnen: Meilenstein, läuft/startklar, kritischer Pfad, Rang) mit der
Dauer je Paket (gemessen P50, sonst Schätzung oder Vorgabe nach Größe). Die AMW legt die Pakete in dieser Reihenfolge auf ihre
Ressourcen:
- Headless (p-Paket): die Arbeitsplätze des Projekts (platz.plaetze) – so viele gleichzeitig, wie es Plätze gibt;
- Fenster: der Agent, dem das Paket gehört – ein Paket nach dem anderen;
- ohne Agent und ohne Platz: nur die Vorgänger begrenzen; die Zeile sagt „ohne Agent“ bzw. „kein Platz“.
Ein Paket beginnt frühestens jetzt, nach dem Ende all seiner offenen Vorgänger und sobald seine Ressource frei ist. Was läuft,
beginnt bei seinem Start (begonnen_utc). Dauert es länger als geplant, endet es „jetzt“ und die Zeile nennt „+n min“ – die
Pakete dahinter rücken mit. Pakete mit gleicher geplanter Startminute laufen „gleichzeitig“.

Nur Rechnung, nichts wird gespeichert (bei jedem Abruf neu, wie die Prognose). „nie gleichzeitig“ und „gleiche Ressource“
(Bildschirm, GPU) rechnet der Zeitplan nicht – das bleibt bei Disponent und Lauf-Schlange.
"""
import datetime

from . import db

UTC = datetime.timezone.utc


def _iso(t):
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if t else None


def _zeit(text):
    try:
        return db.utc_lesen(text) if text else None
    except (ValueError, TypeError):
        return None


def _ressource(a, art):
    if art == "p":
        return "headless"
    return f"agent:{a['agent']}" if a["agent"] else None


def berechnen(con, pid, jetzt=None):
    """{"jetzt", "plaetze", "pakete": [{aid, titel, agent, art, ressource, zustand, platz, start_utc, ende_utc, dauer_min, plus_min,
    gleichzeitig, nach, hinweis}]} in der Reihenfolge von reihenfolge.berechnen."""
    from . import arbeitspaket, planung, platz, reihenfolge
    jetzt = jetzt or datetime.datetime.now(UTC)
    reihe = reihenfolge.berechnen(con, pid)
    offen = {z["aid"] for z in reihe}
    n_plaetze = len(platz.plaetze(con, pid))
    headless = [jetzt] * n_plaetze                      # wann jeder Platz frei wird
    agenten = {}                                        # Agent → frei ab
    ende = {}                                           # aid → geplantes Ende
    vor = {z["aid"]: [v for v in planung.vorgaenger(con, z["aid"]) if v in offen] for z in reihe}
    zeilen = {r["id"]: r for r in con.execute(
        f"SELECT id, agent, begonnen_utc FROM aufgabe WHERE id IN ({','.join('?' * len(offen)) or 'NULL'})", tuple(offen))}
    erledigt, aus = set(), []
    rest = [x for x in reihe if x["zustand"] == "laeuft"] + [x for x in reihe if x["zustand"] != "laeuft"]   # Laufendes belegt zuerst
    while rest:                                         # Reihenfolge der Berechnung, Vorgänger zuerst (Kreise: wie geliefert)
        z = next((x for x in rest if all(v in erledigt for v in vor[x["aid"]])), rest[0])
        rest.remove(z)
        aid, a = z["aid"], zeilen[z["aid"]]
        art = arbeitspaket.lesen(con, aid).get("art") or "agent"
        res = _ressource(a, art)
        dauer = datetime.timedelta(hours=z["dauer_h"])
        hinweis, plus, platz_nr = None, 0, None
        if res == "headless" and headless:
            platz_nr = min(range(len(headless)), key=lambda k: headless[k])   # der Platz, der zuerst frei wird
        elif res == "headless":
            hinweis = "kein Platz"
        elif not res:
            hinweis = "ohne Agent"
        if z["zustand"] == "laeuft":
            start = _zeit(a["begonnen_utc"]) or jetzt
            schluss = start + dauer
            if schluss < jetzt:                          # dauert länger als geplant: endet „jetzt“, +n min
                plus = int((jetzt - schluss).total_seconds() // 60)
                schluss = jetzt
        else:
            start = max([jetzt] + [ende[v] for v in vor[aid] if v in ende])
            if platz_nr is not None:
                start = max(start, headless[platz_nr])
            elif res and res != "headless":
                start = max(start, agenten.get(res, jetzt))
            schluss = start + dauer
        if platz_nr is not None:
            headless[platz_nr] = schluss
        elif res and res != "headless":
            agenten[res] = max(agenten.get(res, jetzt), schluss)
        ende[aid] = schluss
        erledigt.add(aid)
        aus.append({"aid": aid, "titel": z["titel"], "agent": z["agent"], "art": "headless" if art == "p" else "fenster",
                    "ressource": res, "zustand": z["zustand"], "platz": z["platz"], "start_utc": _iso(start), "ende_utc": _iso(schluss),
                    "dauer_min": int(round(z["dauer_h"] * 60)), "plus_min": plus, "nach": vor[aid], "hinweis": hinweis})
    je_start = {}
    for x in aus:
        if x["zustand"] != "laeuft":
            je_start.setdefault(x["start_utc"][:16], []).append(x["aid"])
    for x in aus:
        gruppe = je_start.get(x["start_utc"][:16], []) if x["zustand"] != "laeuft" else []
        x["gleichzeitig"] = [g for g in gruppe if g != x["aid"]]
    aus.sort(key=lambda x: x["platz"])
    return {"jetzt": _iso(jetzt), "plaetze": n_plaetze, "pakete": aus}


def zeile(x, ortszeit=None):
    """Eine Zeile für die Befehlszeile: „A12 12:14–12:39 · 25 min · gleichzeitig mit A13 · nach A11“."""
    f = ortszeit or (lambda t: db.utc_lesen(t).astimezone().strftime("%H:%M"))
    teile = [f"A{x['aid']}", f"{f(x['start_utc'])}–{f(x['ende_utc'])}", f"{x['dauer_min']} min"]
    if x["plus_min"]:
        teile.append(f"+{x['plus_min']} min")
    if x["gleichzeitig"]:
        teile.append("gleichzeitig mit " + ", ".join(f"A{g}" for g in x["gleichzeitig"]))
    if x["nach"]:
        teile.append("nach " + ", ".join(f"A{v}" for v in x["nach"]))
    if x["hinweis"]:
        teile.append(x["hinweis"])
    return " · ".join(teile)
