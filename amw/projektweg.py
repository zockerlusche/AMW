"""A2023: der Projektweg – fünf Schritte Konzept → Grobplan → Feinplan → Umsetzung → Abschluss als Sicht.

Nichts wird hier gespeichert (G12: keine neuen Tabellen, kein Zustand im Browser). Der Zustand der Schritte kommt aus den Toren
(tore.stand, K7), die die AMW aus ihren Daten ableitet; die Freigaben stehen schon als plan_ereignis (planansicht: FREI/JA)
bzw. als Themen-Freigaben (themen.tor) und werden nur gelesen:

- Konzept: einmal (alle zählenden Themen freigegeben),
- Grobplan: einmal (alle geplanten Meilensteine freigegeben, Art „grob“),
- Feinplan: je Meilenstein (Art „plan“),
- Abnahme: je Meilenstein (Art „abschluss“).

Zustand je Schritt: erledigt (✓), dran (●) – der erste nicht erledigte –, offen (○). Erledigt zählt nur, wenn alle Schritte
davor erledigt sind: Übergänge gibt es nur in dieser Reihenfolge (uebergang_pruefen). Weil alles abgeleitet ist, liefert die
AMW nach einem Neustart denselben Stand (wiedereinstieg).
"""
from . import kern

SCHRITTE = ("konzept", "grob", "fein", "umsetzung", "abschluss")
NAMEN = {"konzept": "Konzept", "grob": "Grobplan", "fein": "Feinplan", "umsetzung": "Umsetzung", "abschluss": "Abschluss"}
TOR = {"konzept": "konzept", "grob": "grobplanung", "fein": "feinplanung", "umsetzung": "umsetzung", "abschluss": "abschluss"}
ZEICHEN = {"erledigt": "✓", "dran": "●", "offen": "○"}


def _schritt(s):
    s = str(s or "").strip().lower()
    for k, v in TOR.items():
        if s in (k, v, NAMEN[k].lower()):
            return k
    raise kern.AmwFehler(f"Schritt „{s}“ gibt es nicht – {' | '.join(SCHRITTE)}")


# --- Freigaben (nur lesen) ---------------------------------------------------------------------------------------------------

def freigaben(con, pid):
    """{"konzept": {"frei"}, "grob": {"frei", "n", "g"}, "fein": [{"bogen", "nr", "titel", "frei", "pakete"}],
    "abnahme": [{"bogen", "nr", "titel", "frei", "bericht"}]} – aus themen.tor und planansicht (jüngste Freigabe je Meilenstein
    und Art; geänderter Stand gilt als offen)."""
    from . import planansicht, themen, tore
    z = planansicht._zustaende(con, pid)

    def frei(bid, art):
        return bool((z.get((bid, art)) or {}).get("an"))
    ms = con.execute("SELECT * FROM bogen WHERE projekt_id = ? AND status IN ('geplant', 'aktiv', 'fertig') ORDER BY nr, id",
                     (pid,)).fetchall()
    geplant = [b for b in ms if b["status"] == "geplant"]
    fein = []
    for b in ms:
        n = len(planansicht._pakete(con, pid, b["id"]))
        if n:
            fein.append({"bogen": b["id"], "nr": b["nr"], "titel": b["titel"], "frei": frei(b["id"], "plan"), "pakete": n})
    abnahme = []
    for b in ms:
        bericht = tore.bericht(con, pid, b["id"])
        if b["status"] == "fertig" or bericht is not None:
            abnahme.append({"bogen": b["id"], "nr": b["nr"], "titel": b["titel"], "frei": frei(b["id"], "abschluss"),
                            "bericht": bericht})
    g_n = sum(frei(b["id"], "grob") for b in geplant)
    return {"konzept": {"frei": bool(themen.tor(con, pid)["konzept_zu"])},
            "grob": {"frei": bool(geplant) and g_n == len(geplant), "n": g_n, "g": len(geplant)},
            "fein": fein, "abnahme": abnahme}


# --- wer ist dran -----------------------------------------------------------------------------------------------------------

def _freigebende(con, pid):
    """Wer das Ja gibt: der Mensch (thema_freigabe = mensch) oder Co-Entwickler und Lead (co+lead)."""
    from . import themen
    if themen.freigabe_regel(con, pid) == "co+lead":
        aus = [x for x in (kern.co_entwickler(con, pid), kern.lead(con, pid)) if x]
        if aus:
            return aus
    return [kern.entwickler_name(con, pid)]


def _lead(con, pid):
    return [kern.lead(con, pid) or kern.entwickler_name(con, pid)]


def _wer(con, pid, schritt, st, fr):
    from . import themen
    if schritt == "konzept":
        return _freigebende(con, pid) if themen.fuer_dich(con, pid) else _lead(con, pid)
    if schritt == "grob":
        tor = next(x for x in st["tore"] if x["tor"] == "grobplanung")
        alle_drin = tor["n"] == tor["g"] and tor["g"] > 0 and not st.get("nichts_offen")
        return _freigebende(con, pid) if alle_drin and fr["grob"]["g"] and not fr["grob"]["frei"] else _lead(con, pid)
    if schritt == "fein":
        if any(not f["frei"] for f in fr["fein"]):
            return _freigebende(con, pid)
        return _lead(con, pid)                       # planen bzw. „Jetzt starten“
    if schritt == "abschluss":
        offen = [a for a in fr["abnahme"] if not a["frei"]]
        if offen and all(a["bericht"] is None for a in offen):
            return ["AMW"]                           # der Abschlussbericht kommt von der AMW
        return _freigebende(con, pid)
    return _lead(con, pid)


# --- die Sicht ---------------------------------------------------------------------------------------------------------------

def sicht(con, pid):
    """{"schritte": [{"schritt", "name", "zustand", "zeichen", "fehlt", "wer", "text"}], "dran": Schritt oder None,
    "freigaben": freigaben(), "zeile": Wiedereinstieg in einer Zeile}."""
    from . import tore
    st = tore.stand(con, pid)
    fr = freigaben(con, pid)
    je = {x["tor"]: x for x in st["tore"]}
    schritte, bisher_zu, dran = [], True, None
    for s in SCHRITTE:
        t = je[TOR[s]]
        zu = bisher_zu and bool(t["zu"])             # Reihenfolge: erledigt nur, wenn alles davor erledigt ist
        bisher_zu = zu
        if zu:
            zustand = "erledigt"
        elif dran is None:
            zustand, dran = "dran", s
        else:
            zustand = "offen"
        schritte.append({"schritt": s, "name": NAMEN[s], "zustand": zustand, "zeichen": ZEICHEN[zustand], "text": t["text"],
                         "fehlt": None if zu else t["text"],
                         "wer": _wer(con, pid, s, st, fr) if zustand == "dran" else []})
    return {"schritte": schritte, "dran": dran, "freigaben": fr, "zeile": _zeile(schritte, dran)}


def _zeile(schritte, dran):
    kette = " ".join(f"{x['zeichen']} {x['name']}" for x in schritte)
    if dran is None:
        return f"{kette} – alle Schritte erledigt"
    d = next(x for x in schritte if x["schritt"] == dran)
    return f"{kette} – dran: {d['name']} · fehlt: {d['fehlt']} · wer: {', '.join(d['wer']) or '–'}"


def wiedereinstieg(con, pid):
    """Wo es weitergeht (nach Neustart oder Kompaktierung): {"schritt", "name", "fehlt", "wer", "zeile"} – abgeleitet, also
    nach einem Neustart derselbe Stand."""
    s = sicht(con, pid)
    d = next((x for x in s["schritte"] if x["schritt"] == s["dran"]), None)
    return {"schritt": s["dran"], "name": d["name"] if d else None, "fehlt": d["fehlt"] if d else None,
            "wer": d["wer"] if d else [], "zeile": s["zeile"]}


def uebergang_pruefen(con, pid, schritt):
    """Darf an diesem Schritt gearbeitet bzw. freigegeben werden? Nur, wenn alle Schritte davor erledigt sind – sonst
    AmwFehler mit dem ersten offenen. Rückgabe: der Zustand des Schritts."""
    k = _schritt(schritt)
    s = sicht(con, pid)
    for x in s["schritte"]:
        if x["schritt"] == k:
            return x["zustand"]
        if x["zustand"] != "erledigt":
            raise kern.AmwFehler(f"{NAMEN[k]} geht erst nach {x['name']} – dort fehlt: {x['fehlt']}")
    return None
