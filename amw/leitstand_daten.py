"""A2143: Daten der künftigen Startseite „Leitstand“ – nur lesend, ohne Seite (die baut A2006).

daten(con, pid, jetzt=None) fasst zusammen, was andere Module rechnen: Zeitplan (zeitplan.berechnen), Prognose (planung.prognose),
Verlauf (verlauf_quellen), das laufende Stück eines Agenten (arbeitsliste). Eigene Abfragen gibt es nur, wo keine Funktion die Daten
hat, und je Art genau eine – nie eine je Paket.

- fortschritt: Pakete der aktiven Meilensteine (verworfene zählen nicht). p50/p85: wann der letzte von ihnen fertig ist (mit
  Token-Pause), ziel: das späteste Zieldatum. verzug_tage: der größte Abstand eines Meilensteins zu seinem eigenen Ziel (p50 − Ziel;
  positiv = später), None ohne Ziel oder ohne offene Pakete.
- zuletzt: älteste zuerst; auch Pakete und Versionen ohne Meilenstein.
- jetzt: der Mensch fehlt (seine Aufgaben bleiben frei). Headless vom Start bis zum Ende der Abnahme; gezählt ab dem letzten Start.
- als_naechstes: ohne Headless-Pakete, die schon abgegeben oder bereit zum Merge sind (ihre Aufgabe steht dann wieder auf „wartet“);
  nur Pakete aus aktiven Meilensteinen (A2006, Lead #34119); wartet_mensch: ein offener Grund beim Menschen (Entwickler, offene Frage an
  ihn), sonst wartet_grund: der erste andere offene Grund kurz (Monitor ohne „Monitor:“, Prüfung, Agent, Lauf; A2162).
- entscheidungen: neueste zuerst, nur das eigene Projekt (A2006, Lead #34119 – über alle Projekte zeigt die Gesamtsicht, A2014).
- haengt (A2149): Pakete, die seit mehr als 24 h nur mit einem Wartetext von Hand warten, ohne offenen Grund – „hängt ohne Grund“.
- zeitplan (A2006): je offenem Meilenstein mit Prognose – Ziel gegen voraussichtlich (start, p50, p85 mit Token-Pause), verzug_tage
  (p50 − Ziel), bereit (alle Pakete fertig, der Meilenstein wartet auf seine Abnahme); nach Nummer, ohne eigene Abfrage.

Text in Menschensprache; die Nummer (A12, L3, Version) steht nur im Feld nummer, ein Meilenstein hat keine.
"""
import datetime

from . import arbeitsliste, db, einmal, kern, paketliste, planung, verlauf_quellen, waechter, zeitplan

UTC = datetime.timezone.utc
LETZTE = 10                      # so viele Einträge in zuletzt und entscheidungen
GRUPPEN = 8                      # so viele Startzeiten in als_naechstes
LAEUFE = 300                     # Durchläufe der Prognose, wie überall bei Anzeigen
HEADLESS = "Headless"
# Regel des Wächters → ein Wort, warum ein Paket nicht startete
WARUM = {1: "unvollständig", 2: "Dateikonflikt", 3: "Grafikkarte", 4: "belegt", 5: "geschützt", 6: "Abnahmebefehl", 7: "Wartung", 8: "Wochenlimit",
         9: "Pause", 10: "Einrichtung", 11: "Versionsprüfung", 12: "ausgeschaltet", 13: "Anbieter", 14: "Anbieterprüfung",
         15: "Konzeptänderung", 16: "nacheinander"}
WARUM_SONST = "gesperrt"


def daten(con, pid, jetzt=None):
    """{"fortschritt", "zuletzt", "jetzt", "als_naechstes", "entscheidungen", "haengt", "zeitplan"} eines Projekts – Aufbau: Kopf dieses Moduls."""
    uhr = jetzt or datetime.datetime.now(UTC)
    with einmal.merken(con):                             # Zeitplan und Prognose rechnen dieselbe Reihenfolge nur einmal
        mensch = kern.entwickler_name(con, pid)
        boegen = _boegen(con, pid)
        prognose = planung.prognose(con, pid, laeufe=LAEUFE, heute=jetzt.date() if jetzt else None)["boegen"]
        plan = zeitplan.berechnen(con, pid, jetzt=uhr)["pakete"]
        headless = _headless(con, pid)
        return {"fortschritt": _fortschritt(boegen, prognose),
                "zuletzt": _zuletzt(con, pid, boegen, mensch),
                "jetzt": _jetzt(con, pid, plan, headless, mensch, uhr),
                "als_naechstes": _als_naechstes(plan, headless, mensch, _bereit(con, pid, plan)),
                "entscheidungen": _entscheidungen(con, pid),
                "haengt": _haengt(con, pid, mensch, uhr),
                "zeitplan": _zeitplan(boegen, prognose)}


def _haengt(con, pid, mensch, uhr):
    """A2149: „hängt ohne Grund“ – wartet nur mit Freitext, länger als wartegrund.HAENGT_H."""
    from . import wartegrund
    return [{"titel": x["titel"], "nummer": f"A{x['id']}", "wer": _wer(x["agent"], mensch), "wartet_auf": x["wartet_auf"], "seit_utc": x["seit_utc"]}
            for x in wartegrund.haengt_ohne_grund(con, pid, jetzt=uhr.timestamp())]


def _wer(kennung, mensch):
    return mensch if kennung == kern.ENTWICKLER else kennung or None


# --- Fortschritt -------------------------------------------------------------------------------------------------------------

def _boegen(con, pid):
    """{id: Zeile} aller Meilensteine mit ihren Paketen (gesamt ohne verworfene, fertig)."""
    return {r["id"]: r for r in con.execute(
        "SELECT b.id, b.nr, b.titel, b.status, b.zieldatum, count(a.id) AS gesamt, coalesce(sum(a.status = 'fertig'), 0) AS fertig FROM bogen b"
        " LEFT JOIN aufgabe a ON a.bogen_id = b.id AND a.status != 'verworfen' WHERE b.projekt_id = ? GROUP BY b.id", (pid,))}


def _fortschritt(boegen, prognose):
    aktiv = [b for b in boegen.values() if b["status"] == "aktiv"]
    fertig, gesamt = sum(b["fertig"] for b in aktiv), sum(b["gesamt"] for b in aktiv)
    ende = {}                                            # Meilenstein → (p50, p85), mit Token-Pause
    for b in aktiv:
        p = prognose.get(b["id"])
        if p:
            ende[b["id"]] = (p.get("p50_mit") or p["p50"], p.get("p85_mit") or p["p85"])
    tage = lambda ziel, ist: (datetime.date.fromisoformat(ist) - datetime.date.fromisoformat(ziel)).days
    verzug = [tage(b["zieldatum"], ende[b["id"]][0]) for b in aktiv if b["zieldatum"] and b["id"] in ende]
    return {"fertig": fertig, "gesamt": gesamt, "prozent": 100 * fertig // gesamt if gesamt else 0,      # 100 erst, wenn alles fertig ist
            "p50": max((e[0] for e in ende.values()), default=None), "p85": max((e[1] for e in ende.values()), default=None),
            "ziel": max((b["zieldatum"] for b in aktiv if b["zieldatum"]), default=None), "verzug_tage": max(verzug, default=None)}


def _zeitplan(boegen, prognose):
    """A2006: Meilensteine, die noch nicht fertig sind und eine Prognose haben – Ziel gegen voraussichtlich, nach Nummer."""
    aus = []
    for b in sorted(boegen.values(), key=lambda b: (b["nr"] or 0, b["id"])):
        p = prognose.get(b["id"])
        if not p or b["status"] in ("fertig", "verworfen"):
            continue
        p50, p85 = p.get("p50_mit") or p["p50"], p.get("p85_mit") or p["p85"]
        verzug = (datetime.date.fromisoformat(p50) - datetime.date.fromisoformat(b["zieldatum"])).days if b["zieldatum"] and p50 else None
        aus.append({"nr": b["nr"], "titel": b["titel"], "status": b["status"], "ziel": b["zieldatum"], "start": p.get("start"),
                    "p50": p50, "p85": p85, "verzug_tage": verzug, "bereit": b["gesamt"] > 0 and b["fertig"] == b["gesamt"]})
    return aus


# --- Zuletzt -----------------------------------------------------------------------------------------------------------------

def _zuletzt(con, pid, boegen, mensch):
    aus = []                                             # (Zeit, Rang bei gleicher Sekunde, Aufgabe, Eintrag)

    def dazu(zeit, rang, art, titel, nummer, wer, aufgabe=None):
        aus.append((zeit, rang, aufgabe, {"zeit_utc": zeit, "art": art, "titel": titel, "nummer": nummer, "wer": _wer(wer, mensch)}))
    for e in verlauf_quellen._umsetzung(con, pid):
        if e["art"] == "fertig":
            dazu(e["zeit"], e["rang"], "paket", e["titel"], f"A{e['aufgabe_id']}", e["von"], e["aufgabe_id"])
    rang = verlauf_quellen.RANG.index                    # der Verlauf kennt nur Pakete und Versionen mit Meilenstein – hier die übrigen
    for r in con.execute("SELECT a.id, a.titel, a.agent, a.fertig_utc, (SELECT e.von FROM plan_ereignis e WHERE e.aufgabe_id = a.id"
                         " AND e.art = 'aufgabe_abschluss' ORDER BY e.id DESC LIMIT 1) AS von FROM aufgabe a WHERE a.projekt_id = ? AND a.bogen_id IS NULL"
                         " AND a.status = 'fertig' AND a.fertig_utc IS NOT NULL ORDER BY a.fertig_utc DESC, a.id DESC LIMIT ?", (pid, LETZTE)):
        dazu(r["fertig_utc"], (rang("abschluss"), r["id"]), "paket", r["titel"], f"A{r['id']}", r["von"] or r["agent"] or "AMW", r["id"])
    for r in con.execute("SELECT id, zeit_utc, version FROM release WHERE projekt_id = ? AND art = 'version' ORDER BY zeit_utc DESC, id DESC LIMIT ?",
                         (pid, LETZTE)):
        dazu(r["zeit_utc"], (rang("auslieferung"), r["id"]), "version", f"Version {r['version']}", r["version"], "AMW")
    abgenommen = {}                                      # je Meilenstein das letzte Mal; ein wieder geöffneter zählt nicht
    for e in verlauf_quellen._abschluss(con, pid):
        b = boegen.get(e["bogen_id"])
        if e["id"].startswith("ms_fertig:") and b and b["status"] == "fertig":
            alt = abgenommen.get(b["id"])
            if not alt or (e["zeit"], e["rang"]) > (alt["zeit"], alt["rang"]):
                abgenommen[b["id"]] = e
    for bid, e in abgenommen.items():
        dazu(e["zeit"], e["rang"], "meilenstein", boegen[bid]["titel"], None, e["von"])
    aus = sorted(aus, key=lambda x: x[:2])[-LETZTE:]
    ids = [x[2] for x in aus if x[2]]
    p = {r[0] for r in con.execute(f"SELECT aufgabe_id FROM paket WHERE art = 'p' AND aufgabe_id IN ({','.join('?' * len(ids)) or 'NULL'})", ids)}
    return [{**e, "wer": HEADLESS} if aid in p else e for _, _, aid, e in aus]


# --- Jetzt -------------------------------------------------------------------------------------------------------------------

def _headless(con, pid):
    """{Aufgabe: Zeile} der Headless-Pakete, die schon angefangen haben und noch nicht fertig sind (auch bereit zum Merge)."""
    angefangen = (*waechter.LAUFEND, "gemergt")
    return {r["id"]: r for r in con.execute(
        "SELECT a.id, a.titel, a.status, a.begonnen_utc, k.zustand, (SELECT max(e.zeit_utc) FROM plan_ereignis e WHERE e.aufgabe_id = a.id"
        " AND e.art = 'headless_start') AS start_utc FROM paket k JOIN aufgabe a ON a.id = k.aufgabe_id WHERE a.projekt_id = ? AND k.art = 'p'"
        f" AND a.status NOT IN ('fertig', 'verworfen') AND (a.status = 'laeuft' OR k.zustand IN ({','.join('?' * len(angefangen))})) ORDER BY a.id",
        (pid, *angefangen))}


def _eintrag(art, wer, titel, nummer, seit, erwartet, uhr):
    """Ein laufendes Stück; ohne erwartete Dauer gibt es keinen Anteil und kein „über der Zeit“."""
    try:
        minuten = (uhr - db.utc_lesen(seit)).total_seconds() / 60
    except ValueError:
        seit, minuten = zeitplan._iso(uhr), 0.0          # Beginn unbekannt: wie der Zeitplan ab jetzt
    anteil = min(1.0, max(0.0, minuten / erwartet)) if erwartet else 0.0
    return {"art": art, "wer": wer, "titel": titel, "nummer": nummer, "seit_utc": seit, "erwartet_min": erwartet or None,
            "ueber": bool(erwartet and minuten > erwartet), "anteil": round(anteil, 3)}


def _jetzt(con, pid, plan, headless, mensch, uhr):
    je = {x["aid"]: x for x in plan}
    fenster = {}                                         # Agent → seine laufenden Pakete
    for x in plan:
        if x["zustand"] == "laeuft" and x["art"] == "fenster" and x["agent"] and x["agent"] != kern.ENTWICKLER:
            fenster.setdefault(x["agent"], []).append(x)
    aus = []
    for agent, stuecke in fenster.items():
        stueck = arbeitsliste.laufend(con, pid, agent) if len(stuecke) > 1 else None
        x = next((s for s in stuecke if stueck and s["aid"] == stueck["id"]), stuecke[0])
        aus.append(_eintrag("fenster", agent, x["titel"], f"A{x['aid']}", x["start_utc"], x["dauer_min"], uhr))
    for r in headless.values():
        if r["status"] == "laeuft" or r["zustand"] in waechter.ARBEITEND:
            x = je.get(r["id"])
            aus.append(_eintrag("headless", HEADLESS, r["titel"], f"A{r['id']}", r["start_utc"] or r["begonnen_utc"], x["dauer_min"] if x else None, uhr))
    for r in con.execute("SELECT l.id, l.agent, l.beschreibung, l.start_utc, l.angemeldet_utc, l.erwartet_min, a.titel FROM lauf l"
                         " LEFT JOIN aufgabe a ON a.id = l.aufgabe_id WHERE l.projekt_id = ? AND l.status = 'laeuft' ORDER BY l.id", (pid,)):
        aus.append(_eintrag("lauf", _wer(r["agent"], mensch), r["beschreibung"] or r["titel"] or "Lauf", f"L{r['id']}",
                            r["start_utc"] or r["angemeldet_utc"], r["erwartet_min"], uhr))
    return aus


# --- Als Nächstes ------------------------------------------------------------------------------------------------------------

def _bereit(con, pid, plan):
    """A2006/A2162: {Aufgabe: (wartet auf den Menschen?, anderer Grund kurz oder None)} – nur Pakete aus aktiven Meilensteinen (fehlt eines,
    kommt es nicht gleich). Gründe der Art „aufgabe“ zählen nicht (die zeigt „nach A…“). Zwei Abfragen, gleich viele bei jeder Menge."""
    ids = [x["aid"] for x in plan if x["zustand"] != "laeuft"]
    if not ids:
        return {}
    marken = ",".join("?" * len(ids))
    aktiv = {r[0] for r in con.execute(f"SELECT a.id FROM aufgabe a JOIN bogen b ON b.id = a.bogen_id WHERE a.id IN ({marken}) AND b.status = 'aktiv'", ids)}
    mensch, grund = set(), {}
    for r in con.execute(
            f"SELECT w.aufgabe_id, w.art, w.bezug, (w.art = 'entwickler' OR (w.art = 'frage' AND EXISTS (SELECT 1 FROM frage f WHERE 'F' || f.id = w.bezug"
            f" AND f.an = 'entwickler' AND f.status = 'offen'))) AS beim_menschen FROM wartegrund w WHERE w.aufgabe_id IN ({marken})"
            " AND w.erledigt_utc IS NULL AND w.art != 'aufgabe' ORDER BY w.id", ids):
        if r["beim_menschen"]:
            mensch.add(r["aufgabe_id"])
        elif r["art"] != "frage":                        # eine Frage an einen Agenten nennt der Agent selbst
            grund.setdefault(r["aufgabe_id"], _grund_kurz(r["bezug"]))
    return {a: (a in mensch, None if a in mensch else grund.get(a)) for a in aktiv}


def _grund_kurz(bezug):
    t = " ".join((bezug or "").split())
    t = t[len("Monitor:"):].strip() if t.lower().startswith("monitor:") else t
    return t if len(t) <= 40 else t[:39] + "…"


def _als_naechstes(plan, headless, mensch, bereit):
    gruppen = {}                                         # Startminute → Pakete, in der Reihenfolge des Plans
    for x in plan:
        if x["zustand"] != "laeuft" and x["aid"] not in headless and x["aid"] in bereit:
            gruppen.setdefault(x["start_utc"][:16], []).append(x)
    return [{"start_utc": min(x["start_utc"] for x in gruppen[g]),
             "pakete": [{"titel": x["titel"], "nummer": f"A{x['aid']}", "wer": HEADLESS if x["art"] == "headless" else _wer(x["agent"], mensch),
                         "dauer_min": x["dauer_min"], "wartet_auf": x["wartet_auf"],
                         "wartet_mensch": bereit[x["aid"]][0], "wartet_grund": bereit[x["aid"]][1]} for x in gruppen[g]]}
            for g in sorted(gruppen)[:GRUPPEN]]


# --- Entscheidungen ----------------------------------------------------------------------------------------------------------

def _entscheidungen(con, pid):
    """Nur das eigene Projekt (A2006): [{"zeit_utc", "projekt", "text", "nummer"}], neueste zuerst."""
    aus = []
    for r in con.execute("SELECT e.zeit_utc, e.art, e.text, a.id AS aufgabe, a.titel, p.name FROM plan_ereignis e JOIN projekt p ON p.id = e.projekt_id"
                         " LEFT JOIN aufgabe a ON a.id = e.aufgabe_id WHERE e.projekt_id = ? AND (e.art IN ('headless_start', 'verteilt')"
                         " OR (e.art = 'waechter' AND e.text LIKE '% nicht gestartet, Regel %')) ORDER BY e.zeit_utc DESC, e.id DESC LIMIT ?", (pid, LETZTE)):
        was = f"„{verlauf_quellen._titel_kurz(r['titel'])}“" if r["titel"] else "ein Paket"
        if r["art"] == "waechter":
            m = paketliste._REGEL.match(r["text"])
            satz = f"{was} nicht gestartet – {WARUM.get(int(m.group(1)), WARUM_SONST) if m else WARUM_SONST}"
        else:
            d = verlauf_quellen._json(r["text"])
            if r["art"] == "verteilt":
                satz = f"{was} an {d['agent']} verteilt" if d.get("agent") else f"{was} verteilt"
            else:
                satz = f"{was} {'von Hand ' if d.get('von') not in (None, 'AMW') else ''}als {HEADLESS} gestartet"
        aus.append({"zeit_utc": r["zeit_utc"], "projekt": r["name"], "text": f"{r['name']}: {satz}", "nummer": f"A{r['aufgabe']}" if r["aufgabe"] else None})
    return aus
