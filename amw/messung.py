"""Messen je Paket (A1844, AMW 2.0 Stufe 1 / P1, Marcel 17.11.: kein Token-Limit, aber lückenlose Aufzeichnung).

Rein zusätzlich, kein Schema, nichts wird gesteuert. Definition D1258 v2 Abschnitt 8:
- Wartezeit = startklar → läuft + abgegeben → gemergt. Für Art p (A1845) gelten die echten Zustände aus dem
  Planungs-Protokoll (arbeitspaket.zeitpunkte), je Zeitpunkt einzeln; fehlt einer, und für alle anderen Aufgaben gilt die
  Näherung: startklar ≈ angelegt, läuft = begonnen, abgegeben = erste Prüfbitte, gemergt = fertig (Auslieferung).
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
    return db.utc_lesen(utc)


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
    from . import arbeitspaket                   # A1845: Art p – echte Zustände, je Zeitpunkt einzeln, sonst die Näherung
    zp = arbeitspaket.zeitpunkte(con, aid) or {}
    angelegt = _t(zp.get("startklar") or a["angelegt_utc"])
    beginn = _t(zp.get("laeuft") or a["begonnen_utc"]) if (zp.get("laeuft") or a["begonnen_utc"]) else None
    ende = _t(zp.get("gemergt") or a["fertig_utc"]) if (zp.get("gemergt") or a["fertig_utc"]) else jetzt
    p = zp.get("abgegeben") or con.execute("SELECT min(angefragt_utc) FROM pruefung WHERE aufgabe_id = ?", (aid,)).fetchone()[0]
    abgabe = max(_t(p), beginn) if p and beginn else None
    bau_ende = min(abgabe, ende) if abgabe else ende
    sp = [(art, x, max(v, beginn or v), min(b, bau_ende)) for art, x, v, b in wartespannen(con, aid, jetzt)]
    sp = [s for s in sp if beginn and s[3] > s[2]]
    je_art = {}
    liege = ((beginn or ende) - angelegt).total_seconds()   # nie begonnen und abgeschlossen: bis zum Abschluss, nicht bis jetzt
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
            "warten_s": round(liege + dazwischen + nach), "warten": je_art,
            "offen": a["status"] not in ("fertig", "verworfen") and not zp.get("gemergt")}   # p: nach „gemergt“ steht die Messung


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
    from . import arbeitspaket
    zp = arbeitspaket.zeitpunkte(con, aid)
    if a["begonnen_utc"] and zp is None:
        luecken.append("„startklar“ und „gemergt“ genähert (angelegt bzw. fertig) – echte Zustände gibt es nur bei p-Paketen")
    elif a["begonnen_utc"] and not zp["startklar"]:
        luecken.append("„startklar“ genähert (angelegt)")
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


# --- A2004: p als Vorgabe – Anteil p an fertigen Paketen je Tag, Kosten p gegen interaktiv -----------------------------------
ZIEL_P = 0.5                                     # TL #31229 / Marcel 23.11.: mindestens die Hälfte der Pakete als p
P_MELDUNG = "p_quote_meldung"                    # plan_ereignis {"tag", "anteil", "n"} – einmal je Tag an den Lead


def _tag(utc):
    return _t(utc).astimezone().date().isoformat()         # Ortszeit des PCs – so meint der Mensch „heute“


def p_quote(con, pid, tage=7, jetzt=None, kosten=True):
    """Fertige Aufgaben der letzten `tage` Tage: je Tag (Ortszeit) Anzahl, davon p, Anteil; dazu gesamt und – kosten=True –
    Kosten p gegen interaktiv (Median, Summe, Anzahl mit Messwert; aus je_aufgabe, Lücken zählen nicht als 0)."""
    import statistics
    from . import arbeitspaket
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    seit = (jetzt - datetime.timedelta(days=tage)).strftime("%Y-%m-%dT%H:%M:%SZ")
    je_tag, usd = {}, {"p": [], "interaktiv": []}
    warten = {k: {"vor_start": [], "nach_abgabe": []} for k in usd}
    for r in con.execute("SELECT id, fertig_utc FROM aufgabe WHERE projekt_id = ? AND status = 'fertig' AND fertig_utc >= ?"
                         " ORDER BY fertig_utc", (pid, seit)).fetchall():
        ist_p = arbeitspaket.lesen(con, r["id"])["art"] == "p"
        d = je_tag.setdefault(_tag(r["fertig_utc"]), {"n": 0, "p": 0})
        d["n"] += 1
        d["p"] += ist_p
        if kosten:
            m = je_aufgabe(con, pid, r["id"], jetzt)
            k = "p" if ist_p else "interaktiv"
            if m and m["usd"] > 0:
                usd[k].append(m["usd"])
            for w in ("vor_start", "nach_abgabe"):                 # Wartezeiten aus den Ereignissen (zeiten())
                if m and m["warten"].get(w):
                    warten[k][w].append(m["warten"][w])
    n, p = sum(d["n"] for d in je_tag.values()), sum(d["p"] for d in je_tag.values())
    aus = {"tage": [{"tag": t, **d, "anteil": round(d["p"] / d["n"], 2)} for t, d in sorted(je_tag.items())],
           "n": n, "p": p, "anteil": round(p / n, 2) if n else None, "ziel": ZIEL_P}
    if kosten:
        aus["kosten"] = {k: {"n": len(v), "median": round(statistics.median(v), 2) if v else None, "summe": round(sum(v), 2),
                             **{f"{w}_median_s": round(statistics.median(x)) if x else None for w, x in warten[k].items()}}
                         for k, v in usd.items()}
    return aus


def p_quote_melden(con, pid, jetzt=None):
    """Einmal je Tag (Ortszeit): liegt der Anteil p der letzten 7 Tage unter ZIEL_P, eine Meldung an den Lead. Nur in Projekten
    mit Arbeitsplätzen (ohne Platz kann kein p laufen) und mit mindestens einem fertigen Paket. Rückgabe: Text oder None."""
    from . import platz
    if not platz.einstellung(con, pid)[1]:
        return None
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    heute = jetzt.astimezone().date().isoformat()
    if con.execute("SELECT 1 FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND text LIKE ?",
                   (pid, P_MELDUNG, f'{{"tag": "{heute}"%')).fetchone():
        return None
    q = p_quote(con, pid, jetzt=jetzt, kosten=False)
    lead = kern.lead(con, pid)
    if not q["n"] or q["anteil"] >= ZIEL_P or not lead:
        return None
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=P_MELDUNG,
                     text=json.dumps({"tag": heute, "anteil": q["anteil"], "n": q["n"]}, ensure_ascii=False))
        kern._posten(con, pid, "AMW", lead, "meldung", f"Anteil p {round(q['anteil'] * 100)} % (Ziel ≥ {round(ZIEL_P * 100)} %)",
                     f"In den letzten 7 Tagen liefen {q['p']} von {q['n']} fertigen Paketen als p. p ist die Vorgabe für S und"
                     " M-mechanisch ohne Oberfläche; interaktiv nur mit Grund. Je Tag: "
                     + ", ".join(f"{t['tag'][5:]} {t['p']}/{t['n']}" for t in q["tage"])
                     + ". Kosten p gegen interaktiv: amw messung --p.")
    return f"Anteil p {round(q['anteil'] * 100)} % – Meldung an {lead}"


def p_quote_runde(con, jetzt=None):
    """Vom Dienst je Aufsichtsrunde: alle Projekte; ein Projekt hält die anderen nie auf."""
    aus = []
    for (pid,) in con.execute("SELECT id FROM projekt").fetchall():
        try:
            t = p_quote_melden(con, pid, jetzt)
        except Exception as x:                           # noqa: BLE001
            t = f"Projekt {pid}: {type(x).__name__}: {x}"
        if t:
            aus.append(t)
    return aus


def dauer(s):
    """„2 h 05 min“, „12 min“, „40 s“."""
    s = int(s or 0)
    if s >= 3600:
        return f"{s // 3600} h {(s % 3600) // 60:02d} min"
    if s >= 60:
        return f"{s // 60} min"
    return f"{s} s"


# --- A2040 (D1531 §10): Kosten aus beiden Quellen, Summe und Rest je Projekt -------------------------------------------------

def _erfasst_je_aufgabe(con, pid):
    """{aufgabe_id: (usd, unbekannt)} aus allen kosten-Ereignissen des Projekts – eine Abfrage."""
    aus = {}
    for r in con.execute("SELECT aufgabe_id, text FROM plan_ereignis WHERE projekt_id = ? AND art = 'kosten' AND aufgabe_id IS NOT NULL",
                         (pid,)):
        try:
            e = json.loads(r["text"] or "{}")
        except ValueError:
            continue
        usd, unb = aus.get(r["aufgabe_id"], (0.0, 0))
        aus[r["aufgabe_id"]] = (usd + (e["usd"] if isinstance(e.get("usd"), (int, float)) else 0.0), unb + bool(e.get("unbekannt")))
    return aus


def kosten(con, pid, aid):
    """Gemessene Kosten einer Aufgabe aus BEIDEN Quellen: Kosten-Zähler der Sitzung (Fenster-Agent, aufwand.je_aufgabe) und
    erfasste Läufe (plan_ereignis „kosten“: Headless-Pakete aus der stream-json-Ausgabe, von Hand). Ohne zeiten() – für Ansichten,
    Berichte und die Prognose-Warnung. {"usd", "modelle", "zaehler_usd", "erfasst_usd", "unbekannt", "naeherung"?} oder None,
    wenn es keine Messung gibt. Vorher lasen Planansicht, Abschlussbericht und Warnung nur den Zähler (D1531 §10)."""
    from . import aufwand
    try:
        z = aufwand.je_aufgabe(con, pid, aid)
    except Exception:                                    # noqa: BLE001 – eine Messung darf die Ansicht nie verhindern
        z = None
    usd_e, unbekannt = _erfasst_je_aufgabe_eine(con, pid, aid)
    if not z and not usd_e and not unbekannt:
        return None
    zu = (z or {}).get("usd") or 0.0
    b_z = (z or {}).get("bauen_usd")
    bauen = (b_z if isinstance(b_z, (int, float)) else zu) + usd_e   # A2058: Headless = bauen
    return {"usd": round(zu + usd_e, 2), "bauen_usd": round(bauen, 2), "taetigkeiten": (z or {}).get("taetigkeiten") or {},
            "modelle": (z or {}).get("modelle") or [], "zaehler_usd": round(zu, 2),
            "erfasst_usd": round(usd_e, 2), "unbekannt": unbekannt, **({"naeherung": True} if (z or {}).get("naeherung") else {})}


def _erfasst_je_aufgabe_eine(con, pid, aid):
    usd, unb = 0.0, 0
    for e in erfasst(con, pid, aid):
        usd += e["usd"] if isinstance(e.get("usd"), (int, float)) else 0.0
        unb += bool(e.get("unbekannt"))
    return usd, unb


def projekt_kosten(con, pid):
    """Kosten je Projekt: bisher (gemessen: Zähler der Fenster-Agenten + erfasste Läufe), noch (Schätzung der offenen Pakete:
    Median gleicher Größe und Art, abzüglich schon Gemessenem, nie unter 0), gesamt; dazu der Anteil Headless (erfasste Läufe)
    an „bisher“ und wie viele offene Pakete keine Schätzung haben. Nur lesen, kein KI-Aufruf.
    {"bisher", "noch", "gesamt", "fenster_usd", "erfasst_usd", "offen", "ohne_schaetzung", "unbekannt"}"""
    from . import aufwand, empfehlung
    zaehler = {}
    for (kennung,) in con.execute("SELECT DISTINCT agent FROM aufgabe WHERE projekt_id = ? AND agent IS NOT NULL AND begonnen_utc IS NOT NULL",
                                  (pid,)).fetchall():
        alle = aufwand._aufgaben(con, pid, kennung)
        if alle:
            for aid, e in aufwand._zuordnen(con, pid, kennung, alle, alle[0]["begonnen_utc"]).items():
                zaehler[aid] = zaehler.get(aid, 0.0) + e["usd"]
    erf = _erfasst_je_aufgabe(con, pid)
    try:
        zellen = empfehlung.zellen(con, pid)
    except Exception:                                    # noqa: BLE001
        zellen = {}
    noch, offen, ohne = 0.0, 0, 0
    for a in con.execute(f"SELECT id, groesse, art FROM aufgabe WHERE projekt_id = ? AND status IN ({','.join('?' * len(kern.OFFEN_STATUS))})",
                         (pid, *kern.OFFEN_STATUS)).fetchall():
        offen += 1
        z = zellen.get((empfehlung.GRUPPE.get(a["art"]), a["groesse"])) if a["groesse"] and a["art"] else None
        if not z or z.get("median") is None:
            ohne += 1
            continue
        noch += max(0.0, z["median"] - zaehler.get(a["id"], 0.0) - erf.get(a["id"], (0.0, 0))[0])
    fenster = sum(zaehler.values())
    erfasst_usd = sum(u for u, _ in erf.values())
    bisher = fenster + erfasst_usd
    return {"bisher": round(bisher, 2), "noch": round(noch, 2), "gesamt": round(bisher + noch, 2), "fenster_usd": round(fenster, 2),
            "erfasst_usd": round(erfasst_usd, 2), "offen": offen, "ohne_schaetzung": ohne,
            "unbekannt": sum(n for _, n in erf.values())}
