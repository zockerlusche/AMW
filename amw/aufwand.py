"""Verbrauch je Aufgabe und je Agent (A1611 Stufe E1, Konzept D906): nur messen und zeigen – nichts steuern.

Die Statusline schreibt je Sitzung den Kosten-Zähler von Claude Code (Dollar-Gegenwert, auch bei Abo) in `verbrauch`.
Jeder Zuwachs zwischen zwei Messpunkten einer Sitzung gehört zu der Aufgabe, die der Agent zu dieser Zeit in Arbeit
hatte: von den Aufgaben, die er begonnen und noch nicht abgeschlossen hatte, die zuletzt begonnene (eins nach dem
anderen, G19); eine Aufgabe, die zu dem Zeitpunkt einen offenen Wartegrund hat, hat Nachrang (A1844). Bleiben mehrere,
ist es eine Näherung (naeherung). Kein KI-Aufruf, kein Schema.
"""
import statistics

LETZTE = 10                                   # je Agent: Median über so viele zuletzt fertige Aufgaben mit Messwert
NEU_UNTER_USD = 1.0                           # A1992: gesunkener Zähler unter diesem Wert = neu begonnen (zählt ganz)


def _aufgaben(con, pid, kennung):
    return con.execute("SELECT id, titel, status, begonnen_utc, fertig_utc FROM aufgabe WHERE projekt_id = ? AND agent = ?"
                       " AND begonnen_utc IS NOT NULL ORDER BY begonnen_utc, id", (pid, kennung)).fetchall()


def _zuordnen(con, pid, kennung, aufgaben, ab):
    """{aufgabe_id: {"usd", "modelle": {"Modell/Stufe": usd}}} aus den Sitzungen mit Messpunkten ab `ab`."""
    zeilen = con.execute(
        "SELECT v.sitzung_id, v.zeit_utc, v.kosten_usd, s.modell, s.denkstufe FROM verbrauch v JOIN sitzung s ON s.id = v.sitzung_id"
        " JOIN agent g ON g.id = s.agent_id AND g.projekt_id = ? AND g.kennung = ?"     # gleiche Kennung in zwei Projekten
        " WHERE v.agent = ? AND v.kosten_usd IS NOT NULL AND v.sitzung_id IN (SELECT sitzung_id FROM verbrauch WHERE agent = ?"
        " AND zeit_utc >= ?) ORDER BY v.sitzung_id, v.zeit_utc",          # ganze Sitzungen: gleiche Summe, egal ab wann gefragt
        (pid, kennung, kennung, kennung, ab)).fetchall()
    aus, vorher = {}, {}
    warten = {}                                   # A1844: Wartegründe je Aufgabe – eine wartende Aufgabe hat Nachrang
    for a in aufgaben:
        warten[a["id"]] = [(g["angelegt_utc"], g["erledigt_utc"] or "9") for g in con.execute(
            "SELECT angelegt_utc, erledigt_utc FROM wartegrund WHERE aufgabe_id = ?", (a["id"],))]
    for z in zeilen:
        alt = vorher.get(z["sitzung_id"])
        vorher[z["sitzung_id"]] = z["kosten_usd"]
        if alt is None:                       # erster Messpunkt: Stand davor unbekannt, ab hier wird gezählt
            continue
        if z["kosten_usd"] >= alt:
            zuwachs = z["kosten_usd"] - alt
        else:   # A1992 (Befund 23.11.): gesunken. Ein frisch begonnener Zähler startet nahe 0 – nur dann zählt der Wert ganz.
            # Ein nach dem Neustart fortgesetzter Prozess meldet weiter eine (neu berechnete) Summe, z. B. 177.51 → 133.85: das
            # ist kein Zuwachs von 133.85 $, sondern eine neue Grundlinie (vorher wurde A1989 so 135.69 $ statt ≈ 1 $).
            zuwachs = z["kosten_usd"] if z["kosten_usd"] < NEU_UNTER_USD else 0.0
        if zuwachs <= 0:
            continue
        t = z["zeit_utc"]
        offen = [a for a in aufgaben if a["begonnen_utc"] <= t and (not a["fertig_utc"] or a["fertig_utc"] >= t)]
        if not offen:
            continue                          # Zeit zwischen den Aufgaben (Lesen, Nachrichten) – keiner Aufgabe zuzuordnen
        aktiv = [a for a in offen if not any(v <= t < b for v, b in warten[a["id"]])] or offen
        a = max(aktiv, key=lambda x: (x["begonnen_utc"], x["id"]))
        e = aus.setdefault(a["id"], {"usd": 0.0, "modelle": {}, "naeherung": False})
        e["naeherung"] = e["naeherung"] or len(aktiv) > 1
        e["usd"] += zuwachs
        m = "/".join(x for x in (z["modell"], z["denkstufe"]) if x)
        if m:
            e["modelle"][m] = e["modelle"].get(m, 0.0) + zuwachs
    return aus


def _form(e):
    """Ausgabe: Summe gerundet, Modelle nach Anteil (größter zuerst)."""
    if not e:
        return None
    return {"usd": round(e["usd"], 2), "modelle": [m for m, _ in sorted(e["modelle"].items(), key=lambda x: -x[1])],
            **({"naeherung": True} if e.get("naeherung") else {})}


def je_aufgabe(con, pid, aid):
    """Gemessener Verbrauch einer Aufgabe oder None (nicht begonnen, ohne Agent, keine Messpunkte in ihrer Zeit)."""
    a = con.execute("SELECT agent, begonnen_utc FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    if not a or not a["agent"] or not a["begonnen_utc"]:
        return None
    aufgaben = _aufgaben(con, pid, a["agent"])
    return _form(_zuordnen(con, pid, a["agent"], aufgaben, a["begonnen_utc"]).get(aid))


def je_agent(con, pid, kennung, letzte=LETZTE):
    """Die letzten fertigen Aufgaben des Agenten mit Messwert, ihr Median und die laufende Aufgabe bisher.
    {"median", "n", "aufgaben": [{"id", "titel", "usd", "modelle"}], "laufend": {...} | None} oder None ohne Messwerte."""
    aufgaben = _aufgaben(con, pid, kennung)
    if not aufgaben:
        return None
    fertig = [a for a in aufgaben if a["status"] == "fertig" and a["fertig_utc"]]
    fertig.sort(key=lambda a: a["fertig_utc"], reverse=True)
    kandidaten = fertig[:letzte * 2]          # manche haben keinen Messwert (vor der Statusline, ohne Sitzung)
    laeuft = [a for a in aufgaben if a["status"] == "laeuft"]
    beginn = [a["begonnen_utc"] for a in kandidaten + laeuft]
    if not beginn:
        return None
    werte = _zuordnen(con, pid, kennung, aufgaben, min(beginn))
    liste = []
    for a in kandidaten:
        e = _form(werte.get(a["id"]))
        if e and e["usd"] > 0:
            liste.append({"id": a["id"], "titel": a["titel"], **e})
        if len(liste) >= letzte:
            break
    lauf = max(laeuft, key=lambda a: a["begonnen_utc"]) if laeuft else None
    jetzt = _form(werte.get(lauf["id"])) if lauf else None
    if not liste and not jetzt:
        return None
    return {"median": round(statistics.median([x["usd"] for x in liste]), 2) if liste else None, "n": len(liste),
            "aufgaben": liste, "laufend": {"id": lauf["id"], "titel": lauf["titel"], **jetzt} if jetzt else None}
