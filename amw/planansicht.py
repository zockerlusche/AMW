"""Ansichten Grob- und Feinplanung (A1950, K6, TH164) nach der abgenommenen Kleinprobe D1365 (Co nach B2914, #30224).

Ein Menüpunkt „Planung“, Reiter „Meilensteine“ (Grob) und „Pakete“ (Fein). Echte Daten, nichts von Hand gepflegt (B2907):
- Meilensteine (bogen) in Reihenfolge; ihre Themen ergeben sich aus den Themen-Verweisen ihrer Pakete (A1915) – kein Freitext.
- Pakete je Meilenstein: Agent bzw. -p mit Modell, Vorgänger (nach), Prüfung, Kosten – gemessen, sonst Median der Zelle
  Größe × Art (empfehlung.zellen); ohne beides „–“. Voll geplant ist ein Meilenstein mit mindestens einem Paket.
- Freigabe je Meilenstein (Grob) und je Meilenstein-Plan (Fein) wie bei den Themen (K1, A1937, B2913, #30329): der Mensch
  allein; bei thema_freigabe = co+lead geben Co-Entwickler und Lead je ein Ja – erst mit beiden (seit dem letzten Zurück) gibt
  die AMW frei („durch“ beide, Regel B2913); in der Ansicht „Ja fehlt noch: …“. Zurück genügt von einem (mit Notiz). Den Knopf
  gibt es einmal; wer freigegeben hat, steht als Fakt dabei. Ereignisse ohne Schemaänderung: meilenstein_frei
  {"bogen", "art": "grob"|"plan", "an": true|false, "notiz", "durch", "regel_von"} – der jüngste je (Meilenstein, Art) gilt;
  meilenstein_ja {"bogen", "art", "rolle": "co"|"lead"}.
- „Jetzt starten“: erst, wenn alle offenen Meilensteine freigegeben und alle voll geplanten Pläne freigegeben sind; bis K5 live
  ist, setzt er die voll geplanten Meilensteine auf „aktiv“ (planung.bogen_status) – Lead oder Mensch.
"""
import json

from . import db, kern

FREI = "meilenstein_frei"
JA = "meilenstein_ja"
ARTEN = ("grob", "plan")


def _zustaende(con, pid):
    """{(bogen, art): {"an", "von", "zeit_utc", "notiz"}} – der jüngste Eintrag je Meilenstein und Art."""
    aus = {}
    for r in con.execute("SELECT von, zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id", (pid, FREI)):
        try:
            d = json.loads(r["text"])
        except ValueError:
            continue
        aus[(d.get("bogen"), d.get("art"))] = {"an": bool(d.get("an")), "von": r["von"], "zeit_utc": r["zeit_utc"], "notiz": d.get("notiz"),
                                               "durch": d.get("durch")}
    return aus


def _jas(con, pid):
    """{(bogen, art): {"co": Kennung, "lead": Kennung}} – die Ja seit dem letzten Freigeben oder Zurück (K1: „zur selben Fassung“)."""
    aus = {}
    for r in con.execute("SELECT von, art, text FROM plan_ereignis WHERE projekt_id = ? AND art IN (?, ?) ORDER BY id", (pid, FREI, JA)):
        try:
            d = json.loads(r["text"])
        except ValueError:
            continue
        k = (d.get("bogen"), d.get("art"))
        if r["art"] == FREI:
            aus.pop(k, None)
        else:
            aus.setdefault(k, {})[d.get("rolle")] = r["von"]
    return aus


def darf_freigeben(con, pid, von):
    return von == kern.ENTWICKLER or kern.ist_lead(con, pid, von) or kern.ist_co(con, pid, von)


def _bogen(con, pid, bid):
    b = con.execute("SELECT * FROM bogen WHERE id = ? AND projekt_id = ?", (bid, pid)).fetchone()
    if not b:
        raise kern.AmwFehler(f"Meilenstein {bid} gibt es nicht")
    return b


def _pakete(con, pid, bid):
    return con.execute("SELECT * FROM aufgabe WHERE projekt_id = ? AND bogen_id = ? AND status != 'verworfen' ORDER BY rang, id",
                       (pid, bid)).fetchall()


def freigeben(con, pid, von, bid, art):
    """Grob: der Meilenstein steht so. Plan: seine Pakete stehen so (erst nach der Grob-Freigabe, nur mit Paketen)."""
    if art not in ARTEN:
        raise kern.AmwFehler("Freigabe: grob | plan")
    from . import themen
    if von != kern.ENTWICKLER:                       # K1 (B2913): nur mit thema_freigabe = co+lead, und dann je ein Ja
        if themen.freigabe_regel(con, pid) != "co+lead":
            raise kern.AmwFehler("Meilensteine gibt in diesem Projekt der Mensch frei (thema_freigabe = mensch)")
        if not (kern.ist_co(con, pid, von) or kern.ist_lead(con, pid, von)):
            raise kern.AmwFehler("Ein Ja zur Freigabe geben der Co-Entwickler und der Lead (B2913) – sonst gibt der Mensch frei")
    b = _bogen(con, pid, bid)
    if b["status"] not in ("geplant", "aktiv"):
        raise kern.AmwFehler(f"Meilenstein {b['nr']} ist {b['status']}")
    z = _zustaende(con, pid)
    if (z.get((bid, art)) or {}).get("an"):
        raise kern.AmwFehler(f"Meilenstein {b['nr']}: schon freigegeben")
    if art == "plan":
        if not (z.get((bid, "grob")) or {}).get("an"):
            raise kern.AmwFehler(f"Meilenstein {b['nr']}: erst den Meilenstein freigeben, dann seinen Plan")
        if not _pakete(con, pid, bid):
            raise kern.AmwFehler(f"Meilenstein {b['nr']} hat noch keine Pakete – er wird geplant, wenn der davor läuft")
    with db.schreiben(con):
        if von == kern.ENTWICKLER:                   # der Mensch allein
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=FREI, bogen_id=bid,
                         text=json.dumps({"bogen": bid, "art": art, "an": True}, ensure_ascii=False))
            return {"frei": True}
        rolle = "co" if kern.ist_co(con, pid, von) else "lead"
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=JA, bogen_id=bid,
                     text=json.dumps({"bogen": bid, "art": art, "rolle": rolle}, ensure_ascii=False))
        j = _jas(con, pid).get((bid, art), {})
        if not (j.get("co") and j.get("lead")):
            return {"frei": False, "ja_fehlt": [themen.ROLLEN_JA[r] for r in themen.ROLLEN_JA if not j.get(r)]}
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=FREI, bogen_id=bid,
                     text=json.dumps({"bogen": bid, "art": art, "an": True, "durch": [j["co"], j["lead"]], "regel_von": "B2913"},
                                     ensure_ascii=False))
        was = "Plan für Meilenstein" if art == "plan" else "Meilenstein"
        kern._posten(con, pid, "AMW", kern.ENTWICKLER, "info", f"{was} {b['nr']} „{b['titel'][:50]}“ freigegeben von Co und Lead",
                     f"{j['co']} (Co-Entwickler) und {j['lead']} (Lead) haben {was.lower() if art == 'plan' else 'den Meilenstein'}"
                     f" {b['nr']} „{b['titel']}“ freigegeben (B2913). Zurückholen kannst du jederzeit (Planung › Zurück).")
    return {"frei": True}


def zurueck(con, pid, von, bid, art, notiz):
    """Zurück mit Notiz (Pflicht): die Freigabe gilt nicht mehr; die Notiz geht als Auftrag an den Lead (bzw. Federführenden)."""
    if art not in ARTEN:
        raise kern.AmwFehler("Zurück: grob | plan")
    if not darf_freigeben(con, pid, von):
        raise kern.AmwFehler("Zurückgeben dürfen Co, Lead oder der Mensch")
    if not (notiz or "").strip():
        raise kern.AmwFehler("Zurück nur mit Notiz: was soll anders werden?")
    b = _bogen(con, pid, bid)
    an = b["federfuehrend"] or kern.lead(con, pid)
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=FREI, bogen_id=bid,
                     text=json.dumps({"bogen": bid, "art": art, "an": False, "notiz": notiz.strip()[:2000]}, ensure_ascii=False))
        if an and an not in (von, kern.ENTWICKLER):
            kern._posten(con, pid, "AMW", an, "auftrag",
                         f"Meilenstein {b['nr']} „{b['titel'][:50]}“ zurück ({'Plan' if art == 'plan' else 'Meilenstein'}): {notiz.strip()[:60]}",
                         f"{kern.entwickler_name(con, pid) if von == kern.ENTWICKLER else von} hat "
                         f"{'den Plan' if art == 'plan' else 'den Meilenstein'} {b['nr']} „{b['titel']}“ zurückgegeben:\n{notiz.strip()}")


def verschieben(con, pid, von, bid, richtung):
    """Früher/Später (D1365 (d), keine Ziehen): mit dem Nachbarn (offene Meilensteine) die Nummer tauschen. Co, Lead, Mensch."""
    if not darf_freigeben(con, pid, von):
        raise kern.AmwFehler("Die Reihenfolge ändern Co, Lead oder der Mensch")
    b = _bogen(con, pid, bid)
    offen = con.execute("SELECT * FROM bogen WHERE projekt_id = ? AND status IN ('geplant', 'aktiv') ORDER BY nr, id", (pid,)).fetchall()
    i = next(k for k, x in enumerate(offen) if x["id"] == bid)
    j = i - 1 if richtung == "frueher" else i + 1
    if richtung not in ("frueher", "spaeter") or not 0 <= j < len(offen):
        raise kern.AmwFehler(f"Meilenstein {b['nr']} steht schon ganz {'vorn' if richtung == 'frueher' else 'hinten'}")
    n = offen[j]
    with db.schreiben(con):
        con.execute("UPDATE bogen SET nr = ?, geaendert_utc = ? WHERE id = ?", (n["nr"], db.jetzt(), b["id"]))
        con.execute("UPDATE bogen SET nr = ?, geaendert_utc = ? WHERE id = ?", (b["nr"], db.jetzt(), n["id"]))
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art="bogen_reihenfolge", bogen_id=bid,
                     text=f"Meilenstein {b['titel'][:60]}: {'früher' if richtung == 'frueher' else 'später'} ({b['nr']} ↔ {n['nr']})")


def _kosten(con, pid, a, zellen):
    """(usd, gemessen) – gemessen aus dem Verbrauch, sonst Median der Zelle Größe × Art; sonst (None, False)."""
    from . import aufwand, empfehlung
    if a["begonnen_utc"]:
        try:
            m = aufwand.je_aufgabe(con, pid, a["id"])
        except Exception:                                # noqa: BLE001 – eine Messung darf die Ansicht nie verhindern
            m = None
        if m and m.get("usd"):
            return round(float(m["usd"]), 2), True
    if a["groesse"] and a["art"]:
        z = zellen.get((empfehlung.GRUPPE[a["art"]], a["groesse"]))
        if z:
            return z["median"], False
    return None, False


def _wer(a, paket):
    if paket.get("art") == "p":
        return f"-p {paket.get('modell') or ''}".strip()
    return a["agent"] or "–"


def daten(con, pid):
    """Für die Workbench (Planung › Meilensteine/Pakete)."""
    from . import arbeitspaket, empfehlung, planung, themen
    z = _zustaende(con, pid)
    js, co_lead = _jas(con, pid), themen.freigabe_regel(con, pid) == "co+lead"

    def fehlt(bid, art, frei):
        if frei or not co_lead:
            return []
        j = js.get((bid, art), {})
        return [themen.ROLLEN_JA[r] for r in themen.ROLLEN_JA if not j.get(r)]
    try:
        zellen = empfehlung.zellen(con, pid)
    except Exception:                                    # noqa: BLE001
        zellen = {}
    namen = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM thema WHERE projekt_id = ?", (pid,))}
    ms = []
    for b in con.execute("SELECT * FROM bogen WHERE projekt_id = ? AND status IN ('geplant', 'aktiv', 'fertig') ORDER BY nr, id",
                         (pid,)).fetchall():
        pakete, th = [], {}
        for a in _pakete(con, pid, b["id"]):
            p = arbeitspaket.lesen(con, a["id"])
            usd, gemessen = _kosten(con, pid, a, zellen)
            for tid in themen.verweise(con, pid, a["id"]):
                th[tid] = namen.get(tid, f"TH{tid}")
            pakete.append({"id": a["id"], "titel": a["titel"], "status": a["status"], "wer": _wer(a, p), "p": p.get("art") == "p",
                           "nach": planung.vorgaenger(con, a["id"]), "pruefung": a["pruefer"] or ("AMW" if p.get("art") == "p" else "–"),
                           "usd": usd, "gemessen": gemessen})
        g, pl = z.get((b["id"], "grob")) or {}, z.get((b["id"], "plan")) or {}
        ms.append({"id": b["id"], "nr": b["nr"], "titel": b["titel"], "status": b["status"], "endet_mit": b["abnahme"],
                   "themen": [{"id": k, "name": v} for k, v in sorted(th.items())], "pakete": pakete,
                   "summe": round(sum(p["usd"] for p in pakete if p["usd"]), 2) if any(p["usd"] for p in pakete) else None,
                   "grob": {"frei": bool(g.get("an")), "von": g.get("von"), "durch": g.get("durch"), "zeit_utc": g.get("zeit_utc"),
                            "notiz": None if g.get("an") else g.get("notiz"), "ja_fehlt": fehlt(b["id"], "grob", g.get("an"))},
                   "plan": {"frei": bool(pl.get("an")), "von": pl.get("von"), "durch": pl.get("durch"), "zeit_utc": pl.get("zeit_utc"),
                            "notiz": None if pl.get("an") else pl.get("notiz"),
                            "ja_fehlt": fehlt(b["id"], "plan", pl.get("an")) if b and _pakete(con, pid, b["id"]) else []}})
    offen = [m for m in ms if m["status"] == "geplant"]
    grob_zu = bool(offen) and all(m["grob"]["frei"] for m in offen)
    voll = [m for m in offen if m["pakete"]]
    fein_zu = grob_zu and bool(voll) and all(m["plan"]["frei"] for m in voll)
    in_bogen = {tid for m in ms for tid in (t["id"] for t in m["themen"])}
    ohne = [{"id": t["id"], "name": t["name"]} for t in themen.liste(con, pid)
            if t["zustand"]["status"] == "frei" and not t["zustand"]["markiert"] and t["id"] not in in_bogen]
    tor = "umsetzung" if any(m["status"] == "aktiv" for m in ms) else ("fein" if grob_zu else "grob")
    return {"meilensteine": ms, "tor": tor, "grob_zu": grob_zu, "fein_zu": fein_zu, "ohne_meilenstein": ohne,
            "hat_themen": bool(namen), "starten": fein_zu, **entwuerfe(con, pid, namen)}


def entwuerfe(con, pid, namen):
    """A1940 (K4): offene Entwürfe des Planers zum Ja/Neu-planen und Planer, die gerade laufen – je Thema."""
    from . import planer
    offen, laufend = [], []
    for tid, name in sorted(namen.items()):
        l = planer.laeuft(con, pid, tid)
        if l:
            laufend.append({"thema": tid, "name": name, "seit_utc": l["zeit_utc"]})
            continue
        e = planer.letzter_entwurf(con, pid, tid)
        if not e or planer.erledigt(con, pid, e["id"]):
            continue
        d = e.get("entwurf")
        offen.append({"thema": tid, "name": name, "eid": e["id"], "zeit_utc": e["zeit_utc"], "modell": e.get("modell"), "usd": e.get("usd"),
                      "fehler": e.get("fehler"), "nichts": bool(d and d["nichts_zu_bauen"]), "grund": d.get("grund") if d else None,
                      "meilensteine": len(d["meilensteine"]) if d and not d["nichts_zu_bauen"] else 0,
                      "pakete": len(d["pakete"]) if d and not d["nichts_zu_bauen"] else 0,
                      "zeilen": planer.zusammenfassung(d).split(chr(10)) if d and not d["nichts_zu_bauen"] else []})
    return {"entwuerfe": offen, "planer_laeuft": laufend}


def entwurf_ja(con, pid, von, tid):
    """Ja zum Entwurf (A1940): legt Meilensteine und Pakete an – Lead oder Mensch (planer.uebernehmen prüft)."""
    from . import planer
    return planer.uebernehmen(con, pid, von, int(tid))


def neu_planen(con, pid, von, tid):
    """Den Planer für die aktuelle Fassung noch einmal anstoßen (Lead, Co oder Mensch)."""
    from . import planer, themen
    if not darf_freigeben(con, pid, von):
        raise kern.AmwFehler("Neu planen lassen Lead, Co-Entwickler oder der Mensch")
    t = themen.finden(con, pid, int(tid))
    s = themen.status(con, t)
    if not s["fassung"]:
        raise kern.AmwFehler(f"TH{t['id']} hat noch keinen Text")
    return planer.anstossen(con, pid, t["id"], s["fassung"], von=von, erneut=True)


def jetzt_starten(con, pid, von):
    """„Jetzt starten“ (TH164): die voll geplanten, freigegebenen Meilensteine gehen in die Umsetzung. Bis K5 (Disponent) live
    ist: Status „aktiv“. Lead oder Mensch."""
    from . import planung
    d = daten(con, pid)
    if not d["starten"]:
        raise kern.AmwFehler("Jetzt starten geht erst, wenn alle Meilensteine und alle geplanten Pläne freigegeben sind")
    gestartet = []
    for m in d["meilensteine"]:
        if m["status"] == "geplant" and m["pakete"] and m["plan"]["frei"]:
            planung.bogen_status(con, pid, von, m["id"], "aktiv")
            gestartet.append(m["nr"])
    return gestartet
