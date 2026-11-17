"""Messen je Paket (A1844, AMW 2.0 Stufe 1 / P1, Marcel 17.11.: kein Token-Limit, aber lückenlose Aufzeichnung).

Rein zusätzlich, kein Schema, nichts wird gesteuert. Definition D1258 v2 Abschnitt 8:
- Wartezeit = startklar → läuft + abgegeben → gemergt. Bis es „startklar“ als Zustand gibt (M50 S2), gilt: startklar ≈
  angelegt, läuft = begonnen, abgegeben = erste Prüfbitte, gemergt = fertig (Auslieferung) – als Näherung benannt.
  Aufgeteilt je Grund: „vor dem Start“, „nach der Abgabe“ und die Wartegründe (`wartegrund`, Überlappungen einmal).
- Aktiv = begonnen → abgegeben (bzw. fertig/jetzt) ohne die Wartegründe dazwischen.
- Kosten aus dem Kosten-Zähler der Sitzungen (aufwand: Zuwachs zwischen zwei Messpunkten, der Aufgabe zugeordnet, die
  der Agent gerade in Arbeit hatte – eine Aufgabe, die gerade wartet, hat dabei Nachrang) und aus von Hand erfassten
  Läufen (`amw kosten erfassen`, z. B. die JSON-Ausgabe eines `claude -p`) als plan_ereignis „kosten“.
- Lücken werden genannt, nicht geschätzt.
"""
import datetime
import json

from . import db, kern

ARTEN = ("frage", "aufgabe", "lauf", "agent", "entwickler", "monitor")


def _t(utc):
    return datetime.datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


def _vereinigt(spannen):
    """Gesamtdauer (s) einer Menge von Zeitspannen [(a, b)], Überlappungen einmal."""
    s, ende = 0.0, None
    for a, b in sorted(spannen):
        if ende is None or a > ende:
            s += (b - a).total_seconds()
            ende = b
        elif b > ende:
            s += (b - ende).total_seconds()
            ende = b
    return s


def wartespannen(con, aid, jetzt=None):
    """[(art, bezug, von, bis)] der Wartegründe einer Aufgabe; offene bis jetzt."""
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    return [(g["art"], g["bezug"], _t(g["angelegt_utc"]), _t(g["erledigt_utc"]) if g["erledigt_utc"] else jetzt)
            for g in con.execute("SELECT art, bezug, angelegt_utc, erledigt_utc FROM wartegrund WHERE aufgabe_id = ? ORDER BY id", (aid,))]


def zeiten(con, pid, aid, jetzt=None):
    """{"liege_s", "aktiv_s", "abgabe_s", "warten_s", "warten": {grund: s}, "offen": bool} – warten_s nach D1258 v2 §8
    (vor dem Start + nach der Abgabe + Wartegründe dazwischen, ohne Doppelzählung); None, wenn es die Aufgabe nicht gibt."""
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    a = con.execute("SELECT angelegt_utc, begonnen_utc, fertig_utc, status FROM aufgabe WHERE id = ? AND projekt_id = ?",
                    (aid, pid)).fetchone()
    if not a:
        return None
    angelegt = _t(a["angelegt_utc"])
    beginn = _t(a["begonnen_utc"]) if a["begonnen_utc"] else None
    ende = _t(a["fertig_utc"]) if a["fertig_utc"] else jetzt
    p = con.execute("SELECT min(angefragt_utc) FROM pruefung WHERE aufgabe_id = ?", (aid,)).fetchone()[0]
    abgabe = max(_t(p), beginn) if p and beginn else None
    bau_ende = min(abgabe, ende) if abgabe else ende
    sp = [(art, x, max(v, beginn or v), min(b, bau_ende)) for art, x, v, b in wartespannen(con, aid, jetzt)]
    sp = [s for s in sp if beginn and s[3] > s[2]]
    je_art = {}
    liege = ((beginn or jetzt) - angelegt).total_seconds()
    nach = (ende - abgabe).total_seconds() if abgabe and ende > abgabe else 0
    if liege:
        je_art["vor_start"] = round(liege)
    for art in ARTEN:
        d = _vereinigt([(v, b) for x, _, v, b in sp if x == art])
        if d:
            je_art[art] = round(d)
    if nach:
        je_art["nach_abgabe"] = round(nach)
    dazwischen = _vereinigt([(v, b) for _, _, v, b in sp])
    bau = (bau_ende - beginn).total_seconds() if beginn else 0
    return {"liege_s": round(liege), "aktiv_s": round(max(0.0, bau - dazwischen)), "abgabe_s": round(nach),
            "warten_s": round(liege + dazwischen + nach), "warten": je_art, "offen": a["status"] not in ("fertig", "verworfen")}


def erfassen(con, pid, von, aid, usd=None, unbekannt=False, json_text=None, notiz=None):
    """Kosten eines Laufs außerhalb der Sitzungs-Zähler (z. B. claude -p) einer Aufgabe zuordnen. Aus der JSON-Ausgabe von
    claude -p werden total_cost_usd, Tokens, Turns, Dauer und Modell übernommen. „unbekannt“: Lauf ohne Ergebnis
    (abgebrochen) – er wird als Lücke geführt, nicht geschätzt. Rückgabe: der gespeicherte Eintrag."""
    if not con.execute("SELECT 1 FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone():
        raise kern.AmwFehler(f"A{aid} gibt es in diesem Projekt nicht")
    e = {"usd": None, "unbekannt": bool(unbekannt), "notiz": (notiz or "").strip()[:200] or None}
    if json_text:
        try:
            j = json.loads(json_text)
        except ValueError:
            raise kern.AmwFehler("--json: keine gültige JSON-Ausgabe (claude -p --output-format json)") from None
        u = j.get("usage") or {}                       # D1258 v2 §8: Rohwerte getrennt
        e.update(usd=j.get("total_cost_usd"), turns=j.get("num_turns"), dauer_s=round((j.get("duration_ms") or 0) / 1000) or None,
                 eingabe=u.get("input_tokens"), cache_schreiben=u.get("cache_creation_input_tokens"),
                 cache_lesen=u.get("cache_read_input_tokens"), ausgabe=u.get("output_tokens"),
                 denken=(u.get("output_tokens_details") or {}).get("thinking_tokens"),
                 modell=",".join(sorted((j.get("modelUsage") or {}).keys())) or None, sitzung=j.get("session_id"))
        if e["usd"] is None:
            raise kern.AmwFehler("--json enthält kein total_cost_usd")
    elif usd is not None:
        if usd < 0:
            raise kern.AmwFehler("--usd darf nicht negativ sein")
        e["usd"] = round(float(usd), 4)
    elif not unbekannt:
        raise kern.AmwFehler("Kosten fehlen: --json <datei>, --usd <betrag> oder --unbekannt (Lauf ohne Ergebnis)")
    e = {k: v for k, v in e.items() if v is not None}
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art="kosten", aufgabe_id=aid,
                     text=json.dumps(e, ensure_ascii=False))
    return e


def erfasst(con, pid, aid):
    """Von Hand erfasste Kosten einer Aufgabe: [{"von", "zeit_utc", …}]."""
    aus = []
    for r in con.execute("SELECT von, zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND aufgabe_id = ? AND art = 'kosten'"
                         " ORDER BY id", (pid, aid)):
        try:
            aus.append({"von": r["von"], "zeit_utc": r["zeit_utc"], **json.loads(r["text"])})
        except ValueError:
            continue
    return aus


def je_aufgabe(con, pid, aid, jetzt=None):
    """Alles Gemessene zu einer Aufgabe: Zeiten, Kosten (Zähler + erfasst), Summe und die Lücken in Worten."""
    from . import aufwand
    z = zeiten(con, pid, aid, jetzt)
    if z is None:
        return None
    a = con.execute("SELECT agent, begonnen_utc FROM aufgabe WHERE id = ?", (aid,)).fetchone()
    zaehler = aufwand.je_aufgabe(con, pid, aid)
    extra = erfasst(con, pid, aid)
    luecken = []
    if a["begonnen_utc"]:
        luecken.append("„startklar“ und „gemergt“ genähert (angelegt bzw. fertig) – eigene Zustände kommen mit M50 S2")
    if a["begonnen_utc"] and not zaehler:
        chat = con.execute("SELECT arbeitsweise FROM agent WHERE projekt_id = ? AND kennung = ?", (pid, a["agent"] or "")).fetchone()
        luecken.append("Agent arbeitet als Chat – kein Kosten-Zähler" if chat and chat["arbeitsweise"] == "chat"
                       else "keine Messpunkte des Kosten-Zählers in der Zeit der Aufgabe")
    if zaehler and zaehler.get("naeherung"):
        luecken.append("mehrere Aufgaben gleichzeitig offen – Zuordnung genähert")
    if any(e.get("unbekannt") for e in extra):
        n = sum(1 for e in extra if e.get("unbekannt"))
        luecken.append(f"{n} Lauf ohne Kostenangabe (unbekannt)" if n == 1 else f"{n} Läufe ohne Kostenangabe (unbekannt)")
    if a["begonnen_utc"]:
        luecken.append("Lead-Arbeit für diese Aufgabe (Prüfung, Planung) und der erste Messpunkt jeder Sitzung zählen nicht mit")
    usd = (zaehler or {}).get("usd", 0.0) + sum(e.get("usd") or 0.0 for e in extra)
    return {**z, "agent": a["agent"], "zaehler": zaehler, "erfasst": extra, "usd": round(usd, 2), "luecken": luecken}


def liste(con, pid, seit=None, agent=None, jetzt=None):
    """Je begonnener Aufgabe (neueste zuerst, ab `seit`): Messung wie je_aufgabe, dazu Titel und Status."""
    sql = "SELECT id, titel, status FROM aufgabe WHERE projekt_id = ? AND begonnen_utc IS NOT NULL"
    p = [pid]
    if seit:
        sql += " AND coalesce(fertig_utc, '9') >= ?"
        p.append(seit)
    if agent:
        sql += " AND agent = ?"
        p.append(agent)
    return [{"id": r["id"], "titel": r["titel"], "status": r["status"], **je_aufgabe(con, pid, r["id"], jetzt)}
            for r in con.execute(sql + " ORDER BY begonnen_utc DESC LIMIT 100", p)]


def vergleich(con, pid, jetzt=None, tage=7):
    """D1258 v2 §8: dieselbe Rechnung für die letzten `tage` Tage und die davor – je Zeitraum die fertigen Aufgaben:
    Anzahl, Median Kosten, Median Wartezeit, Median aktiv, Summe Kosten, Anzahl mit Lücken."""
    import statistics
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    aus = []
    for i in (1, 2):
        von, bis = jetzt - datetime.timedelta(days=tage * i), jetzt - datetime.timedelta(days=tage * (i - 1))
        f = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")
        ids = [r[0] for r in con.execute("SELECT id FROM aufgabe WHERE projekt_id = ? AND status = 'fertig' AND begonnen_utc IS NOT NULL"
                                         " AND fertig_utc >= ? AND fertig_utc < ?", (pid, f(von), f(bis)))]
        ms = [je_aufgabe(con, pid, a, jetzt) for a in ids]
        med = lambda xs: round(statistics.median(xs), 2) if xs else None
        aus.append({"von": f(von), "bis": f(bis), "n": len(ms), "usd_median": med([m["usd"] for m in ms]),
                    "usd_summe": round(sum(m["usd"] for m in ms), 2), "warten_median_s": med([m["warten_s"] for m in ms]),
                    "aktiv_median_s": med([m["aktiv_s"] for m in ms]), "mit_luecken": sum(1 for m in ms if len(m["luecken"]) > 1)})
    return {"diese": aus[0], "vorher": aus[1]}


def dauer(s):
    """„2 h 05 min“, „12 min“, „40 s“."""
    s = int(s or 0)
    if s >= 3600:
        return f"{s // 3600} h {(s % 3600) // 60:02d} min"
    if s >= 60:
        return f"{s // 60} min"
    return f"{s} s"
