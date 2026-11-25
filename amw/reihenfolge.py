"""Feinplanung und Timeline (A1941, K5; TH164 „Reihenfolge und Timeline“; Entwurf #30232, Antwort #30233).

Die AMW rechnet die Arbeitsreihenfolge selbst – aus Paketen, Abhängigkeiten, Größe und gemessener Dauer. Handpflege ist die
Ausnahme mit Grund. Ohne Schemaänderung: Ereignisse liste_hand (Handordnung), plan_stand (Stand bei „Jetzt starten“).

Dauer je Paket (Stunden), in dieser Reihenfolge:
1. gemessen: Median der Dauer aus der Eignungstabelle (A1930) für die Zelle Art-Gruppe × Größe, ab MIN_MESSUNGEN Messungen,
2. geschätzt: aufgabe.schaetzung_h,
3. Vorgabe je Größe (S 1 h, M 3 h, L 8 h, XL 20 h), ohne Größe OHNE_H.

Reihenfolge (berechnen):
1. aktiver Meilenstein vor geplantem vor „ohne Meilenstein“, dann nach Nummer des Meilensteins,
2. was läuft vor startklar vor wartend (startklar = wartet ohne offenen Wartegrund und ohne offenen Vorgänger),
3. längerer Rest-Pfad zuerst – kritischer Pfad über die Abhängigkeiten „nach“ (Summe der Dauern bis zum Ende),
4. Rang (nur noch Gleichstand-Brecher), dann Nummer.
„nie gleichzeitig“ und „gleiche Ressource“ rechnet die Reihenfolge nicht – das bleibt bei Disponent und Lauf-Schlange.

Handordnung (liste_hand): `amw liste ordnen <Agent> A… --grund …` gilt, bis sich die offene Liste des Agenten ändert (ein Paket
kommt dazu oder fällt weg); danach ordnet wieder die AMW und meldet das dem Lead einmal.
"""
import hashlib
import json

from . import db, kern

VORGABE_H = {"S": 1.0, "M": 3.0, "L": 8.0, "XL": 20.0}
OHNE_H = 3.0
MIN_MESSUNGEN = 3
HAND = "liste_hand"
HAND_ENDE = "liste_hand_ende"
PLAN_STAND = "plan_stand"
OFFEN = ("wartet", "laeuft", "blockiert")


def _offene(con, pid):
    return con.execute("SELECT a.*, b.status AS b_status, b.nr AS b_nr FROM aufgabe a LEFT JOIN bogen b ON b.id = a.bogen_id"
                       " WHERE a.projekt_id = ? AND a.status IN ('wartet', 'laeuft', 'blockiert') AND a.einstufung IN ('aktiv', 'keine_prio')",
                       (pid,)).fetchall()


def _gemessen(con, pid):
    """{(gruppe, groesse): (median_h, n)} aus den Messzeilen der Eignungstabelle."""
    from . import eignung
    je = {}
    try:
        zeilen = eignung.zeilen(con, pid)
    except Exception:                                    # noqa: BLE001 – ohne Messung rechnet die Reihenfolge mit Schätzung/Vorgabe
        return {}
    for z in zeilen:
        if z.get("zelle") and z.get("dauer_s"):
            je.setdefault(tuple(z["zelle"]), []).append(z["dauer_s"])
    aus = {}
    for zelle, xs in je.items():
        if len(xs) >= MIN_MESSUNGEN:
            xs = sorted(xs)
            m = xs[len(xs) // 2] if len(xs) % 2 else (xs[len(xs) // 2 - 1] + xs[len(xs) // 2]) / 2
            aus[zelle] = (round(m / 3600, 2), len(xs))
    return aus


def dauer(a, gemessen):
    """(Stunden, Quelle) für eine Aufgabe."""
    from . import empfehlung
    zelle = (empfehlung.GRUPPE.get(a["art"]), a["groesse"]) if a["art"] and a["groesse"] else None
    if zelle and zelle in gemessen:
        h, n = gemessen[zelle]
        return max(h, 0.05), f"gemessen ({n})"
    if a["schaetzung_h"]:
        return float(a["schaetzung_h"]), "geschätzt"
    if a["groesse"] in VORGABE_H:
        return VORGABE_H[a["groesse"]], f"Vorgabe {a['groesse']}"
    return OHNE_H, "ohne Größe"


def _nachfolger(con, ids):
    from . import planung
    menge, nach = set(ids), {i: [] for i in ids}
    for i in ids:
        for v in planung.vorgaenger(con, i):
            if v in menge:
                nach[v].append(i)
    return nach


def rest_pfad(con, ids, dauern):
    """{aid: Stunden} – Dauer des Pakets plus die längste Kette offener Nachfolger (kritischer Pfad). Kreise brechen ab."""
    nach = _nachfolger(con, ids)
    rest = {}

    def tiefe(a, pfad=()):
        if a in rest:
            return rest[a]
        weiter = [tiefe(n, pfad + (a,)) for n in nach.get(a, []) if n not in pfad]
        rest[a] = round(dauern[a] + max(weiter, default=0.0), 2)
        return rest[a]
    for i in ids:
        tiefe(i)
    return rest


def berechnen(con, pid):
    """Wie _berechnen – je Anfrage bzw. Runde nur einmal (A2081)."""
    from . import einmal
    return einmal.einmal(con, ("reihenfolge", pid), lambda: _berechnen(con, pid), kopie=True)


def _berechnen(con, pid):
    """Die Reihenfolge aller offenen Pakete: [{aid, titel, agent, bogen, platz, dauer_h, quelle, rest_h, zustand, grund}]."""
    from . import planung, wartegrund
    offen = _offene(con, pid)
    gemessen = _gemessen(con, pid)
    d = {a["id"]: dauer(a, gemessen) for a in offen}
    rest = rest_pfad(con, [a["id"] for a in offen], {k: v[0] for k, v in d.items()})
    interaktiv = _wartet_interaktiv(con, [a["id"] for a in offen])
    zeilen = []
    for a in offen:
        # ein p-Paket, das auf den interaktiven Agenten wartet (Aufgabe blockiert), ist für ihn jetzt dran – startklar
        bereit = a["status"] == "wartet" or (a["status"] == "blockiert" and a["id"] in interaktiv)
        if a["status"] == "laeuft":
            zustand = "laeuft"
        elif bereit and not wartegrund.offene(con, a["id"]) and not planung.offene_vorgaenger(con, a["id"]):
            zustand = "startklar"
        else:
            zustand = "wartet"
        bogen = {"aktiv": 0, "geplant": 1}.get(a["b_status"], 2)
        schluessel = (bogen, a["b_nr"] if a["b_nr"] is not None else 99999, {"laeuft": 0, "startklar": 1}.get(zustand, 2),
                      -rest[a["id"]], a["rang"] if a["rang"] is not None else 999999, a["id"])
        zeilen.append((schluessel, {"aid": a["id"], "titel": a["titel"], "agent": a["agent"], "bogen": a["bogen_id"],
                                    "dauer_h": d[a["id"]][0], "quelle": d[a["id"]][1], "rest_h": rest[a["id"]], "zustand": zustand}))
    zeilen.sort(key=lambda x: x[0])
    aus = []
    for i, (_, z) in enumerate(zeilen, 1):
        z["platz"] = i
        z["grund"] = (f"{'läuft' if z['zustand'] == 'laeuft' else z['zustand']} · Rest-Pfad {z['rest_h']:g} h"
                      f" · {z['dauer_h']:g} h {z['quelle']}")
        aus.append(z)
    return aus


def _wartet_interaktiv(con, ids):
    """Die Aufgaben unter ids, deren p-Paket auf den interaktiven Agenten wartet."""
    if not ids:
        return set()
    try:
        return {r[0] for r in con.execute(f"SELECT aufgabe_id FROM paket WHERE zustand = 'wartet_interaktiv'"
                                          f" AND aufgabe_id IN ({','.join('?' * len(ids))})", ids)}
    except Exception:                                      # ältere Datenbank ohne Tabelle paket
        return set()


def plaetze(con, pid):
    """{aid: Platz} der berechneten Reihenfolge."""
    return {z["aid"]: z["platz"] for z in berechnen(con, pid)}


# --- Handordnung ------------------------------------------------------------------------------------------------------------

def _stand(ids):
    return hashlib.sha1(",".join(str(i) for i in sorted(ids)).encode()).hexdigest()[:12]


def hand_setzen(con, pid, von, agent, ids_offen, grund):
    """In der Transaktion des Aufrufers: Handordnung eines Agenten mit Grund – gilt für genau diese offene Liste."""
    db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=HAND,
                 text=json.dumps({"agent": agent, "stand": _stand(ids_offen), "grund": grund}, ensure_ascii=False))


def hand(con, pid, agent, ids_offen):
    """Die geltende Handordnung des Agenten ({von, grund, zeit_utc}) oder None – sie gilt, solange die offene Liste dieselbe ist."""
    for r in con.execute("SELECT von, text, zeit_utc FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id DESC LIMIT 20",
                         (pid, HAND)).fetchall():
        try:
            d = json.loads(r["text"])
        except ValueError:
            continue
        if d.get("agent") != agent:
            continue
        if d.get("stand") == _stand(ids_offen):
            return {"von": r["von"], "grund": d.get("grund"), "zeit_utc": r["zeit_utc"]}
        return None                                      # die neueste Handordnung dieses Agenten gilt nicht mehr
    return None


def hand_abgelaufen(con, pid):
    """Dienst: Handordnungen, deren Liste sich geändert hat → einmal an den Lead („die AMW ordnet wieder“). Rückgabe: Texte."""
    aus = []
    for r in con.execute("SELECT id, von, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id DESC LIMIT 50",
                         (pid, HAND)).fetchall():
        try:
            d = json.loads(r["text"])
        except ValueError:
            continue
        agent = d.get("agent")
        neuer = con.execute("SELECT 1 FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND id > ? AND text LIKE ?",
                            (pid, HAND, r["id"], f'%"agent": "{agent}"%')).fetchone()
        if neuer or con.execute("SELECT 1 FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND text = ?",
                                (pid, HAND_ENDE, str(r["id"]))).fetchone():
            continue
        ids = [x["id"] for x in con.execute("SELECT id FROM aufgabe WHERE projekt_id = ? AND agent = ? AND status IN"
                                            " ('wartet', 'laeuft', 'blockiert') AND einstufung IN ('aktiv', 'keine_prio')", (pid, agent))]
        if d.get("stand") == _stand(ids):
            continue
        lead = kern.lead(con, pid)
        with db.schreiben(con):
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=HAND_ENDE, text=str(r["id"]))
            if lead:
                kern._posten(con, pid, "AMW", lead, "info", f"Liste {agent}: Handordnung endet – die AMW ordnet wieder"[:140],
                             f"Die Liste von {agent} hat sich geändert (Paket dazu oder fertig). Deine Handordnung"
                             f" („{d.get('grund')}“) gilt nicht mehr; die Reihenfolge rechnet wieder die AMW (kritischer Pfad)."
                             f" Wieder von Hand: amw liste ordnen {agent} A… --grund …")
        aus.append(f"Handordnung {agent} beendet")
    return aus


def neue_startklar(con, pid, starter, bid, aids):
    """A2083 (aus delta_start, A2080): in einem LAUFENDEN Meilenstein nur diese – gerade angelegten – Pakete startklar setzen
    (Pflichtfelder wie starten) und verteilen. Kein anderes Paket (zurückgehaltene bleiben), der Plan-Stand bleibt – der erste
    Start eines Meilensteins ist starten. Rückgabe: {aid: [fehlende Felder]}."""
    from . import arbeitspaket, verteilen
    fehlt = {}
    aids = {int(a) for a in aids}
    if not aids:
        return fehlt
    for a in con.execute("SELECT * FROM aufgabe WHERE bogen_id = ? AND projekt_id = ? AND status IN ('wartet', 'laeuft', 'blockiert') ORDER BY id",
                         (bid, pid)).fetchall():
        if a["id"] not in aids:
            continue
        f_ = fehlende_felder(con, pid, a)
        if f_:
            fehlt[a["id"]] = f_
            continue
        f = arbeitspaket.lesen(con, a["id"])
        if f["art"] == "p" and f["zustand"] in (None, "entwurf"):
            arbeitspaket.zustand_setzen(con, pid, starter, a["id"], "startklar", grund="mit neuen Paketen gestartet")
    verteilen.verteilen(con, pid)
    return fehlt


# --- Plan-Stand und Abweichung ------------------------------------------------------------------------------------------------

def plan_stand_merken(con, pid, von, bid):
    """In der Transaktion des Aufrufers: P50 je Paket und Meilenstein beim Start – Grundlage der Abweichung."""
    from . import planung
    prog = planung.prognose(con, pid, laeufe=300)
    pakete = {str(a["id"]): (prog["schritte"].get(a["id"]) or {}).get("p50")
              for a in con.execute("SELECT id FROM aufgabe WHERE bogen_id = ? AND status IN ('wartet', 'laeuft', 'blockiert')", (bid,))}
    db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=PLAN_STAND, bogen_id=bid,
                 text=json.dumps({"bogen": (prog["boegen"].get(bid) or {}).get("p50"), "pakete": pakete}))


def abweichung(con, pid, bid, prog=None):
    """{"bogen": Tage, "pakete": {aid: Tage}, "seit": Zeit} gegenüber dem Plan-Stand beim Start – oder None ohne Plan-Stand.
    Positiv = später als geplant."""
    import datetime
    from . import planung
    r = con.execute("SELECT text, zeit_utc FROM plan_ereignis WHERE bogen_id = ? AND art = ? ORDER BY id DESC LIMIT 1",
                    (bid, PLAN_STAND)).fetchone()
    if not r:
        return None
    alt = json.loads(r["text"])
    prog = prog or planung.prognose(con, pid, laeufe=300)
    tage = lambda a, b: (datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days if a and b else None
    pakete = {}
    for aid, p50 in (alt.get("pakete") or {}).items():
        jetzt = (prog["schritte"].get(int(aid)) or {}).get("p50")
        if jetzt and p50:
            pakete[int(aid)] = tage(p50, jetzt)
    return {"bogen": tage(alt.get("bogen"), (prog["boegen"].get(bid) or {}).get("p50")), "pakete": pakete, "seit": r["zeit_utc"]}


# --- „Jetzt starten“ ------------------------------------------------------------------------------------------------------

def fehlende_felder(con, pid, a):
    """Pflichtfelder nach TH165, die einem Paket fehlen (leer = startklar zu planen)."""
    from . import arbeitspaket, fertigquelle, themen
    fehlt = []
    if not (a["auftrag"] or "").strip():
        fehlt.append("Ziel (Auftrag)")
    if not themen.verweise(con, pid, a["id"]):
        fehlt.append("Thema")
    if not fertigquelle.lesen(con, a["id"]):
        fehlt.append("Fertig-Quelle")
    if arbeitspaket.lesen(con, a["id"])["art"] == "p":
        if not (a["pruefbefehl"] or "").strip():
            fehlt.append("Abnahme-Befehl")
        if not (a["dateibereich"] or "").strip():
            fehlt.append("Bereiche")
    return fehlt


def starten(con, pid, von, bid):
    """`amw bogen starten N` (Lead oder Mensch): Meilenstein aktiv, Plan-Stand merken, startklare Pakete an den Disponenten
    (Art p: Zustand startklar; Art agent: eine Verteil-Runde), Meldung an den Lead. Pakete ohne Pflichtfelder bleiben Entwurf
    und stehen mit dem fehlenden Feld in der Meldung. Rückgabe {"startklar": [aid], "fehlt": {aid: [Felder]}, "verteilt": [Texte]}."""
    from . import arbeitspaket, planung, verteilen
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Einen Meilenstein startet der Lead oder der Mensch")
    b = planung.bogen_zeile(con, pid, bid)
    if b["status"] in ("fertig", "verworfen"):
        raise kern.AmwFehler(f"M{b['nr']} ist {b['status']}")
    pakete = con.execute("SELECT * FROM aufgabe WHERE bogen_id = ? AND status IN ('wartet', 'laeuft', 'blockiert') ORDER BY id",
                         (bid,)).fetchall()
    if not pakete:
        raise kern.AmwFehler(f"M{b['nr']} hat keine offenen Pakete")
    fehlt = {a["id"]: f for a in pakete if (f := fehlende_felder(con, pid, a))}
    if b["status"] != "aktiv":
        planung.bogen_status(con, pid, von, bid, "aktiv")
    klar = [a["id"] for a in pakete if a["id"] not in fehlt]
    for aid in klar:
        f = arbeitspaket.lesen(con, aid)
        if f["art"] == "p" and f["zustand"] in (None, "entwurf"):
            arbeitspaket.zustand_setzen(con, pid, von, aid, "startklar", grund=f"M{b['nr']} gestartet")
    with db.schreiben(con):
        plan_stand_merken(con, pid, von, bid)
    verteilt = verteilen.verteilen(con, pid)
    reihe = [z for z in berechnen(con, pid) if z["bogen"] == bid]
    lead = kern.lead(con, pid)
    if lead and lead != von:
        with db.schreiben(con):
            kern._posten(con, pid, "AMW", lead, "info", f"M{b['nr']} „{b['titel'][:80]}“ gestartet – {len(klar)} Pakete startklar",
                         "Reihenfolge (die AMW rechnet sie):\n" + "\n".join(f"{z['platz']}. A{z['aid']} {z['titel'][:70]} – {z['grund']}"
                                                                            for z in reihe[:30])
                         + ("\nNoch nicht startklar: " + "; ".join(f"A{k}: {', '.join(v)}" for k, v in fehlt.items()) if fehlt else ""))
    return {"startklar": klar, "fehlt": fehlt, "verteilt": verteilt}
