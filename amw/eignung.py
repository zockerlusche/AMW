"""Eignungstabelle je Modell und Pakettyp (A1930, TH159, Entscheidungen CCamwTL #29978): gemessen statt geschätzt.

Je erledigter Arbeit eine Zeile – nichts wird von Hand gepflegt (B2907):
- p-Pakete: Modell/Effort aus dem Paket, Zelle (Gruppe der Art × Größe) aus der Aufgabe, Pakettyp, Kosten und Dauer aus den
  Kosten-Ereignissen, „ohne Nacharbeit“ nach F5362 A: erste Entscheidung E7, oder bei Test-Paketen E4 und danach vom Lead
  ohne Änderung angenommen. Nacharbeit: ein zweiter Lauf (E5), Abgabe an einen interaktiven Agenten (E8), jedes andere Ende.
- Interaktive Aufgaben (fertig, mit Größe und Art): Modell/Stufe aus den Sitzungen, die die Aufgabe am meisten gekostet haben
  (aufwand), Kosten ebenso, Dauer = aktive Zeit (messung), ohne Nacharbeit = keine rote Prüfung.

tabelle() fasst je Zelle und Modell/Effort zusammen (Anzahl, Anteil ohne Nacharbeit, Median Kosten und Dauer, Pakettypen –
nur zur Anzeige). beste(): unter den Paaren mit n ≥ MIN_N das mit dem höchsten Anteil ohne Nacharbeit, bei Gleichstand die
niedrigeren Median-Kosten; es ersetzt den Startwert nur, wenn sein Anteil mindestens so hoch ist wie der gemessene des
Startwerts (falls der n ≥ MIN_N hat). Fable ist nie eine Empfehlung.
"""
import json
import statistics

from . import kern

MIN_N = 5
ANNAHME = "lead_nach_e4"                 # mergeliste.annehmen: E7 nach E4, vom Lead ohne Änderung angenommen (A1894)
TESTTYPEN = ("test-schreiben", "test-ergaenzen")


def kurz(modell):
    """Modellname → Kurzname der Empfehlung (opus/sonnet/haiku/fable); fremde Anbieter (anbieter@modell) bleiben, wie sie sind."""
    m = (modell or "").strip().lower()
    if "@" in m:
        return m
    for f in ("opus", "sonnet", "haiku", "fable"):
        if f in m:
            return f
    return m or "?"


def _entscheidungen(con, aid):
    aus = []
    for (t,) in con.execute("SELECT text FROM plan_ereignis WHERE aufgabe_id = ? AND art = 'paket_entscheidung' ORDER BY id", (aid,)):
        try:
            d = json.loads(t or "{}")
        except ValueError:
            continue
        if d.get("zeile"):
            aus.append((d["zeile"], d.get("code")))
    return aus


def ohne_nacharbeit_p(entscheidungen, pakettyp):
    """F5362 A. None = noch keine Entscheidung (zählt nicht)."""
    if not entscheidungen:
        return None
    zeilen = [z for z, _ in entscheidungen]
    if "E5" in zeilen or "E8" in zeilen:
        return False
    if zeilen[0] == "E7" and entscheidungen[0][1] != ANNAHME:
        return True
    if zeilen[0] == "E4" and pakettyp in TESTTYPEN and any(z == "E7" and c == ANNAHME for z, c in entscheidungen[1:]):
        return True
    return False


def _kosten(con, aid):
    usd, dauer, da = 0.0, 0.0, False
    for (t,) in con.execute("SELECT text FROM plan_ereignis WHERE aufgabe_id = ? AND art = 'kosten'", (aid,)):
        try:
            d = json.loads(t or "{}")
        except ValueError:
            continue
        if d.get("usd") is not None:
            usd, da = usd + float(d["usd"]), True
        dauer += float(d.get("dauer_s") or 0)
    return (round(usd, 4) if da else None), (dauer or None)


def zeilen(con, pid):
    """Alle Messzeilen des Projekts: [{"aufgabe", "quelle", "zelle", "paar", "pakettyp", "usd", "dauer_s", "ohne"}]."""
    from . import arbeitspaket, aufwand, empfehlung, messung
    aus = []
    for r in con.execute("SELECT a.id, a.art, a.groesse FROM aufgabe a JOIN paket k ON k.aufgabe_id = a.id WHERE a.projekt_id = ?"
                         " AND k.art = 'p' ORDER BY a.id", (pid,)).fetchall():
        f = arbeitspaket.lesen(con, r["id"])
        ohne = ohne_nacharbeit_p(_entscheidungen(con, r["id"]), f["pakettyp"])
        if ohne is None:
            continue
        usd, dauer = _kosten(con, r["id"])
        aus.append({"aufgabe": r["id"], "quelle": "p", "zelle": _zelle(r, empfehlung), "paar": f"{kurz(f['modell'])}/{f['effort']}",
                    "pakettyp": f["pakettyp"], "usd": usd, "dauer_s": dauer, "ohne": ohne})
    p_ids = {x["aufgabe"] for x in aus}
    agenten = [k for (k,) in con.execute("SELECT DISTINCT agent FROM aufgabe WHERE projekt_id = ? AND status = 'fertig' AND agent IS NOT NULL"
                                         " AND agent != ? AND begonnen_utc IS NOT NULL", (pid, kern.ENTWICKLER)).fetchall()]
    for kennung in agenten:
        alle = aufwand._aufgaben(con, pid, kennung)
        if not alle:
            continue
        gemessen = aufwand._zuordnen(con, pid, kennung, alle, alle[0]["begonnen_utc"])
        for a in con.execute("SELECT id, art, groesse FROM aufgabe WHERE projekt_id = ? AND agent = ? AND status = 'fertig'"
                             " AND groesse IS NOT NULL AND art IS NOT NULL", (pid, kennung)).fetchall():
            e = gemessen.get(a["id"])
            if a["id"] in p_ids or not e or not e.get("modelle"):
                continue
            meist = max(e["modelle"].items(), key=lambda x: x[1])[0]          # „Modell/Stufe“ mit den meisten Kosten
            m, _, s = meist.partition("/")
            rot = con.execute("SELECT 1 FROM pruefung WHERE aufgabe_id = ? AND ergebnis = 'rot'", (a["id"],)).fetchone()
            z = messung.zeiten(con, pid, a["id"]) or {}
            aus.append({"aufgabe": a["id"], "quelle": "interaktiv", "zelle": _zelle(a, empfehlung), "paar": f"{kurz(m)}/{s or '?'}",
                        "pakettyp": "interaktiv", "usd": round(e["usd"], 4) if e.get("usd") is not None else None,
                        "dauer_s": z.get("aktiv_s"), "ohne": not rot})
    return aus


def _zelle(r, empfehlung):
    if r["art"] in empfehlung.GRUPPE and r["groesse"] in empfehlung.GROESSEN:
        return (empfehlung.GRUPPE[r["art"]], r["groesse"])
    return None


def _median(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None


def tabelle(con, pid, messzeilen=None):
    """{(gruppe, groesse): {"modell/effort": {"n", "ohne_anteil", "kosten_median", "dauer_median_s", "pakettypen"}}}."""
    gruppen = {}
    for z in (zeilen(con, pid) if messzeilen is None else messzeilen):
        if z["zelle"]:
            gruppen.setdefault(z["zelle"], {}).setdefault(z["paar"], []).append(z)
    aus = {}
    for zelle, paare in gruppen.items():
        for paar, zs in paare.items():
            typen = {}
            for z in zs:
                typen[z["pakettyp"]] = typen.get(z["pakettyp"], 0) + 1
            aus.setdefault(zelle, {})[paar] = {"n": len(zs), "ohne_anteil": round(sum(1 for z in zs if z["ohne"]) / len(zs), 2),
                                               "kosten_median": _median(z["usd"] for z in zs),
                                               "dauer_median_s": _median(z["dauer_s"] for z in zs), "pakettypen": typen}
    return aus


def beste(zellwerte, startwert, min_n=MIN_N):
    """Paar für eine Zelle nach der Regel oben – oder None (es bleibt der Startwert)."""
    kandidaten = [(p, w) for p, w in (zellwerte or {}).items() if w["n"] >= min_n and not p.startswith("fable/")]
    if not kandidaten:
        return None
    p, w = sorted(kandidaten, key=lambda x: (-x[1]["ohne_anteil"], x[1]["kosten_median"] if x[1]["kosten_median"] is not None else 1e9))[0]
    s = (zellwerte or {}).get(startwert)
    if s and s["n"] >= min_n and w["ohne_anteil"] < s["ohne_anteil"]:
        return None
    return None if p == startwert else p
