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
ARTEN = ("grob", "plan", "abschluss")       # abschluss: Ja zum Abschlussbericht (K7, A1944)


def plan_teil(con, a):
    """Ein Paket, wie es der Fingerabdruck des Plans sieht (auch delta_start: was hat ein Ja geändert?)."""
    from . import arbeitspaket, planung
    return [a["id"], a["titel"], a["auftrag"], a["groesse"], a["art"], a["pruefbefehl"], planung.vorgaenger(con, a["id"]),
            arbeitspaket.lesen(con, a["id"]).get("art")]


def fingerabdruck(con, pid, bid, art):
    """P461 (1), B2913 „zur selben Fassung“: was ein Ja bzw. eine Freigabe gesehen hat. grob: Titel, Ziel, Abnahme, Zieldatum und
    die Themen des Meilensteins; plan: seine Pakete (Nummer, Titel, Auftrag, Größe, Art, Abnahme-Befehl, Vorgänger, Ausführung)
    – nicht Status, Agent oder Zeiten, die sich in der Umsetzung ändern; abschluss: der Bericht. Kurz-Hash."""
    import hashlib
    from . import themen
    b = con.execute("SELECT * FROM bogen WHERE id = ? AND projekt_id = ?", (bid, pid)).fetchone()
    if not b:
        return None
    pakete = _pakete(con, pid, bid)
    if art == "grob":
        from . import grobplan
        # A2030 (CCamw2 #31619): ein Meilenstein aus dem Grobplan nennt seine Themen im Ziel – die Pakete der Feinplanung
        # kommen erst danach und ändern die Grob-Freigabe nicht. Alle anderen wie bisher (Themen aus den Paketen).
        th = [] if grobplan.aus_grobplan(con, pid, b["nr"]) else sorted({t for a in pakete for t in themen.verweise(con, pid, a["id"])})
        teile = [b["titel"], b["ziel"], b["abnahme"], b["zieldatum"], th]
    elif art == "plan":
        teile = [plan_teil(con, a) for a in sorted(pakete, key=lambda x: x["id"])]
    else:
        from . import tore
        teile = [tore.bericht(con, pid, bid)]
    return hashlib.sha256(json.dumps(teile, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()[:16]


def _zustaende(con, pid):
    """{(bogen, art): {"an", "von", "zeit_utc", "notiz", "geaendert"}} – der jüngste Eintrag je Meilenstein und Art. P461 (1): hat
    sich der Meilenstein bzw. Plan seit der Freigabe geändert (Fingerabdruck), gilt sie als offen (geaendert = True)."""
    aus = {}
    for r in con.execute("SELECT id, von, zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id", (pid, FREI)):
        try:
            d = json.loads(r["text"])
        except ValueError:
            continue
        aus[(d.get("bogen"), d.get("art"))] = {"an": bool(d.get("an")), "von": r["von"], "zeit_utc": r["zeit_utc"], "notiz": d.get("notiz"), "id": r["id"],
                                               "durch": d.get("durch"), "fp": d.get("fp"), "geaendert": False}
    for (bid, art), z in aus.items():
        if z["an"] and z["fp"] and fingerabdruck(con, pid, bid, art) != z["fp"]:
            z.update(an=False, geaendert=True)
    return aus


def _jas(con, pid):
    """{(bogen, art): {"co": Kennung, "lead": Kennung}} – die Ja seit dem letzten Freigeben oder Zurück, die zum JETZIGEN Stand
    passen (P461 (1), K1 „zur selben Fassung“: ein Ja zu einem älteren Stand zählt nicht)."""
    roh, fp = {}, {}
    for r in con.execute("SELECT von, art, text FROM plan_ereignis WHERE projekt_id = ? AND art IN (?, ?) ORDER BY id", (pid, FREI, JA)):
        try:
            d = json.loads(r["text"])
        except ValueError:
            continue
        k = (d.get("bogen"), d.get("art"))
        if r["art"] == FREI:
            roh.pop(k, None)
        else:
            roh.setdefault(k, {})[d.get("rolle")] = (r["von"], d.get("fp"))
    aus = {}
    for k, j in roh.items():
        if k not in fp:
            fp[k] = fingerabdruck(con, pid, *k)
        aus[k] = {rolle: von for rolle, (von, f) in j.items() if f is None or f == fp[k]}
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
        raise kern.AmwFehler("Freigabe: grob | plan | abschluss")
    from . import themen
    if von != kern.ENTWICKLER:                       # K1 (B2913), A2032: je Art die eigene Einstellung, und dann je ein Ja
        if themen.freigabe_regel(con, pid, art) != "co+lead":
            raise kern.AmwFehler(f"{ {'grob': 'Meilensteine', 'plan': 'Pläne', 'abschluss': 'Abschlüsse'}[art]} gibt in diesem"
                                 f" Projekt der Mensch frei ({themen.FREIGABE_EINSTELLUNG[art]} = mensch)")
        if not (kern.ist_co(con, pid, von) or kern.ist_lead(con, pid, von)):
            raise kern.AmwFehler("Ein Ja zur Freigabe geben der Co-Entwickler und der Lead (B2913) – sonst gibt der Mensch frei")
    b = _bogen(con, pid, bid)
    bereit = False
    if art == "abschluss":                           # K7: das Ja zum Abschlussbericht – erst, wenn er fertig ist und einen Bericht hat
        from . import planautomatik, tore
        bereit = planautomatik.bereit_zur_abnahme(con, b)   # A2002: endet mit Urteil – das Ja macht ihn erst fertig
        if b["status"] != "fertig" and not bereit:
            raise kern.AmwFehler(f"Meilenstein {b['nr']} ist noch nicht {planautomatik.BEREIT_TEXT} – erst alle Pakete fertig,"
                                 " dann der Abschluss")
        if tore.bericht(con, pid, bid) is None:
            raise kern.AmwFehler(f"Meilenstein {b['nr']}: der Abschlussbericht fehlt noch (die AMW erstellt ihn; sonst amw bogen bericht {bid})")
    elif b["status"] not in ("geplant", "aktiv"):
        raise kern.AmwFehler(f"Meilenstein {b['nr']} ist {b['status']}")
    z = _zustaende(con, pid)
    if (z.get((bid, art)) or {}).get("an"):
        raise kern.AmwFehler(f"Meilenstein {b['nr']}: schon freigegeben")
    if bereit:                                       # A2002: gibt dieses Ja frei, wird der Meilenstein zuerst fertig (fertig_utc) –
        rolle = "co" if kern.ist_co(con, pid, von) else "lead"   # scheitert das (Versions-Pflicht), bleibt alles, wie es war
        anderes = (_jas(con, pid).get((bid, art)) or {}).get("lead" if rolle == "co" else "co")
        if von == kern.ENTWICKLER or anderes:
            from . import planung
            planung.bogen_status(con, pid, von, bid, "fertig", automatik=True)
    if art == "plan":
        if not (z.get((bid, "grob")) or {}).get("an"):
            raise kern.AmwFehler(f"Meilenstein {b['nr']}: erst den Meilenstein freigeben, dann seinen Plan")
        if not _pakete(con, pid, bid):
            raise kern.AmwFehler(f"Meilenstein {b['nr']} hat noch keine Pakete – die AMW plant ihn, sobald der davor bereit zur Abnahme ist oder sein letztes Paket läuft")
    fp = fingerabdruck(con, pid, bid, art)           # P461 (1): Ja und Freigabe gelten für genau diesen Stand
    with db.schreiben(con):
        if von == kern.ENTWICKLER:                   # der Mensch allein
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=FREI, bogen_id=bid,
                         text=json.dumps({"bogen": bid, "art": art, "an": True, "fp": fp}, ensure_ascii=False))
            return {"frei": True}
        rolle = "co" if kern.ist_co(con, pid, von) else "lead"
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=JA, bogen_id=bid,
                     text=json.dumps({"bogen": bid, "art": art, "rolle": rolle, "fp": fp}, ensure_ascii=False))
        j = _jas(con, pid).get((bid, art), {})
        if not (j.get("co") and j.get("lead")):
            return {"frei": False, "ja_fehlt": [themen.ROLLEN_JA[r] for r in themen.ROLLEN_JA if not j.get(r)]}
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=FREI, bogen_id=bid,
                     text=json.dumps({"bogen": bid, "art": art, "an": True, "durch": [j["co"], j["lead"]], "regel_von": "B2913",
                                      "fp": fp}, ensure_ascii=False))
        was = {"plan": "Plan für Meilenstein", "abschluss": "Abschlussbericht für Meilenstein"}.get(art, "Meilenstein")
        kern._posten(con, pid, "AMW", kern.ENTWICKLER, "info", f"{was} {b['nr']} „{b['titel'][:50]}“ freigegeben von Co und Lead",
                     f"{j['co']} (Co-Entwickler) und {j['lead']} (Lead) haben {'den ' + was if art != 'grob' else 'den Meilenstein'}"
                     f" {b['nr']} „{b['titel']}“ freigegeben (B2913). Zurückholen kannst du jederzeit (Planung › Zurück).")
    return {"frei": True}


def zurueck(con, pid, von, bid, art, notiz):
    """Zurück mit Notiz (Pflicht): die Freigabe gilt nicht mehr; die Notiz geht als Auftrag an den Lead (bzw. Federführenden)."""
    if art not in ARTEN:
        raise kern.AmwFehler("Zurück: grob | plan | abschluss")
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
                         f"Meilenstein {b['nr']} „{b['titel'][:50]}“ zurück ({ {'plan': 'Plan', 'abschluss': 'Abschluss'}.get(art, 'Meilenstein')}):"
                         f" {notiz.strip()[:60]}",
                         f"{kern.entwickler_name(con, pid) if von == kern.ENTWICKLER else von} hat "
                         f"{ {'plan': 'den Plan', 'abschluss': 'den Abschlussbericht'}.get(art, 'den Meilenstein')} {b['nr']} „{b['titel']}“"
                         f" zurückgegeben:\n{notiz.strip()}"
                         + ("\nNach der Nacharbeit: amw bogen bericht " + str(bid) + " (neuer Bericht)" if art == "abschluss" else ""))


def verschieben(con, pid, von, bid, richtung):
    """Früher/Später (D1365 (d), keine Ziehen): mit dem Nachbarn (offene Meilensteine) die Nummer tauschen. Co, Lead, Mensch."""
    if not darf_freigeben(con, pid, von):
        raise kern.AmwFehler("Die Reihenfolge ändern Co, Lead oder der Mensch")
    b = _bogen(con, pid, bid)
    offen = con.execute("SELECT * FROM bogen WHERE projekt_id = ? AND status IN ('geplant', 'aktiv') ORDER BY nr, id", (pid,)).fetchall()
    i = next((k for k, x in enumerate(offen) if x["id"] == bid), None)
    if i is None:                                    # P461 (3): fertige/verworfene Meilensteine verschiebt man nicht
        raise kern.AmwFehler(f"Meilenstein {b['nr']} ist {b['status']} – nur geplante und laufende lassen sich verschieben")
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
    from . import empfehlung, messung
    if a["begonnen_utc"]:
        try:
            m = messung.kosten(con, pid, a["id"])             # A2040: Zähler UND erfasste Läufe (Headless)
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
    from . import abschlusslage, arbeitspaket, empfehlung, planautomatik, planung, themen
    z = _zustaende(con, pid)
    js = _jas(con, pid)
    co_lead = {art: themen.freigabe_regel(con, pid, art) == "co+lead" for art in ARTEN}     # A2032: je Art
    halt = _angehalten(con, pid)                         # K8: schon angehaltene zählen nicht mehr als „nicht begonnen“

    def fehlt(bid, art, frei):
        if frei or not co_lead[art]:
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
        g, pl, ab = z.get((b["id"], "grob")) or {}, z.get((b["id"], "plan")) or {}, z.get((b["id"], "abschluss")) or {}
        geaendert = []                                   # K8: Themen, die sich seit der Freigabe des Meilensteins geändert haben
        if g.get("an") and b["status"] in ("geplant", "aktiv"):
            for tid in th:
                f = _geaendert_seit(con, pid, tid, g["id"])
                if f is not None:
                    offen = [aid for x in betroffen(con, pid, tid) if x["bogen"]["id"] == b["id"] for aid in x["offen"] if aid not in halt]
                    geaendert.append({"id": tid, "name": th[tid], "fassung": f, "offen": offen})   # offen: anhaltbar (dieses Thema)
        lage = abschlusslage.lage(con, pid, b)            # A2082
        ms.append({"id": b["id"], "nr": b["nr"], "titel": b["titel"], "status": b["status"], "endet_mit": b["abnahme"],
                   "bereit": planautomatik.bereit_zur_abnahme(con, b),                                   # A2002
                   "lage": lage, "bei_dir": abschlusslage.bei_mensch(con, pid, lage), "laufend": abschlusslage.laufend(con, b["id"]),
                   "themen": [{"id": k, "name": v} for k, v in sorted(th.items())], "pakete": pakete,
                   "summe": round(sum(p["usd"] for p in pakete if p["usd"]), 2) if any(p["usd"] for p in pakete) else None,
                   "geaendert": geaendert,
                   "grob": {"frei": bool(g.get("an")), "von": g.get("von"), "durch": g.get("durch"), "zeit_utc": g.get("zeit_utc"),
                            "notiz": None if g.get("an") else g.get("notiz"), "ja_fehlt": fehlt(b["id"], "grob", g.get("an")),
                            "geaendert": bool(g.get("geaendert"))},
                   "plan": {"frei": bool(pl.get("an")), "von": pl.get("von"), "durch": pl.get("durch"), "zeit_utc": pl.get("zeit_utc"),
                            "notiz": None if pl.get("an") else pl.get("notiz"), "geaendert": bool(pl.get("geaendert")),
                            "ja_fehlt": fehlt(b["id"], "plan", pl.get("an")) if b and _pakete(con, pid, b["id"]) else []},
                   "abschluss": _abschluss(con, pid, b, ab, fehlt)})
    offen = [m for m in ms if m["status"] == "geplant"]
    grob_zu = bool(offen) and all(m["grob"]["frei"] for m in offen)
    voll = [m for m in offen if m["pakete"]]
    fein_zu = grob_zu and bool(voll) and all(m["plan"]["frei"] for m in voll)
    in_bogen = {tid for m in ms for tid in (t["id"] for t in m["themen"])}
    ohne = [{"id": t["id"], "name": t["name"]} for t in themen.liste(con, pid)
            if t["zustand"]["status"] == "frei" and not t["zustand"]["markiert"] and t["id"] not in in_bogen]
    tor = "umsetzung" if any(m["status"] == "aktiv" for m in ms) else ("fein" if grob_zu else "grob")
    return {"meilensteine": ms, "tor": tor, "grob_zu": grob_zu, "fein_zu": fein_zu, "ohne_meilenstein": ohne,
            "hat_themen": bool(namen), "starten": fein_zu, **entwuerfe(con, pid, namen), "aenderungen": _aenderungen(con, pid),
            "tore": _tore(con, pid)}


def _abschluss(con, pid, b, ab, fehlt):
    """K7: für fertige Meilensteine – Abschlussbericht (Dokument), Ja (frei, wer, ja_fehlt) oder zurück mit Notiz. A2002: auch für
    Meilensteine, die bereit zur Abnahme sind (das Ja macht sie fertig)."""
    from . import planautomatik, tore
    bereit = planautomatik.bereit_zur_abnahme(con, b)
    if b["status"] != "fertig" and not bereit:
        return None
    if not bereit and not tore._neu_fertig(con, pid, b) and tore.bericht(con, pid, b["id"]) is None:
        return None                                  # Altbestand vor dem Stichtag: kein Abschluss nötig
    return {"bericht": tore.bericht(con, pid, b["id"]), "frei": bool(ab.get("an")), "von": ab.get("von"), "durch": ab.get("durch"),
            "notiz": None if ab.get("an") else ab.get("notiz"), "ja_fehlt": fehlt(b["id"], "abschluss", ab.get("an"))}


def _tore(con, pid):
    from . import tore
    try:
        return tore.stand(con, pid)
    except Exception:                                    # noqa: BLE001 – die Ansicht darf daran nie scheitern
        return None


def _aenderungen(con, pid):
    """A1957: eigene Änderungen des Menschen, über die noch nicht entschieden ist (wird geprüft | wartet auf Ja | Prüfung ging nicht)."""
    from . import folgen
    try:
        return folgen.offene(con, pid)
    except Exception:                                    # noqa: BLE001 – die Ansicht darf daran nie scheitern
        return []


# --- K8 (A1942, Plan Co #30105, TH163 Rückkopplung): Änderungen von oben nach unten – Thema → Meilenstein → Paket ----------
# Ändert sich ein Thema (neue Fassung nach einer Freigabe, oder Zurück), zeigt die AMW die betroffenen Meilensteine und darunter
# die Pakete und schlägt die Anpassung vor (neu planen über K4, nicht begonnene anhalten); laufende bauen zu Ende, der Lead
# entscheidet. Abgeleitet, ohne Schemaänderung: ein Meilenstein ist betroffen, wenn eins seiner Themen nach der Freigabe des
# Meilensteins (grob) eine neue Fassung bekam oder zurückgegeben wurde.
ANGEHALTEN = "paket_angehalten"           # {"aufgabe", "thema", "bogen"} – zur Nachvollziehbarkeit


def _verweise_alle(con, pid):
    """{Aufgabe: {Themen}} – die geltenden Themen-Verweise (A1915) in einem Durchgang."""
    from . import themen
    aus = {}
    for r in con.execute("SELECT aufgabe_id, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id", (pid, themen.VERWEIS)):
        try:
            d = json.loads(r[1])
        except ValueError:
            continue
        (aus.setdefault(r[0], set()).add if d.get("an") else aus.setdefault(r[0], set()).discard)(d.get("thema"))
    return aus


def _nicht_begonnen(a):
    return a["status"] not in ("laeuft", "fertig", "verworfen") and not a["begonnen_utc"]


def _angehalten(con, pid):
    """Aufgaben, die K8 angehalten hat und die noch stehen (wartet/blockiert bzw. p-Paket zurückgestellt)."""
    from . import arbeitspaket
    aus = set()
    for (aid,) in con.execute("SELECT DISTINCT aufgabe_id FROM plan_ereignis WHERE projekt_id = ? AND art = ?", (pid, ANGEHALTEN)):
        a = con.execute("SELECT status FROM aufgabe WHERE id = ?", (aid,)).fetchone()
        if a and (a["status"] in ("wartet", "blockiert") or arbeitspaket.lesen(con, aid).get("zustand") == "zurueckgestellt"):
            aus.add(aid)
    return aus


def betroffen(con, pid, tid):
    """[{"bogen": {id, nr, titel, status}, "offen": [A…], "laeuft": [A…], "fertig": [A…]}] – Meilensteine, deren Pakete auf
    das Thema verweisen (geplante und laufende Meilensteine), mit ihren Paketen nach Stand."""
    vw = _verweise_alle(con, pid)
    je = {}
    for aid, ts in vw.items():
        if tid not in ts:
            continue
        a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
        if not a or not a["bogen_id"] or a["status"] == "verworfen":
            continue
        b = con.execute("SELECT id, nr, titel, status FROM bogen WHERE id = ?", (a["bogen_id"],)).fetchone()
        if not b or b["status"] not in ("geplant", "aktiv"):
            continue
        z = je.setdefault(b["id"], {"bogen": dict(b), "offen": [], "laeuft": [], "fertig": []})
        z["fertig" if a["status"] == "fertig" else "laeuft" if not _nicht_begonnen(a) else "offen"].append(aid)
    return sorted(je.values(), key=lambda x: x["bogen"]["nr"])


def folgen_melden(con, pid, tid, anlass):
    """Nach einer Änderung des Themas (themen.thema_geaendert / zurueck): dem Lead die betroffenen Meilensteine und Pakete mit
    dem Vorschlag – nichts wird von selbst angehalten. Rückgabe: Liste der Meilenstein-Nummern."""
    bt = betroffen(con, pid, tid)
    lead = kern.lead(con, pid)
    if not bt or not lead or lead == kern.ENTWICKLER:
        return []
    t = con.execute("SELECT name FROM thema WHERE id = ?", (tid,)).fetchone()
    zeilen = [f"- Meilenstein {x['bogen']['nr']} „{x['bogen']['titel'][:60]}“ [{x['bogen']['status']}]: "
              + ", ".join(f"{len(x[k])} {w}" for k, w in (("offen", "nicht begonnen"), ("laeuft", "laufend"), ("fertig", "fertig")) if x[k])
              + (f" (nicht begonnen: {', '.join(f'A{a}' for a in x['offen'])})" if x["offen"] else "") for x in bt]
    with db.schreiben(con):
        kern._posten(con, pid, "AMW", lead, "auftrag",
                     f"Thema geändert: TH{tid} „{(t['name'] if t else '')[:50]}“ ({anlass}) – betrifft {len(bt)} Meilenstein(e)",
                     "Betroffen:\n" + "\n".join(zeilen) + "\n\nVorschlag: neu planen (amw thema planen TH" + str(tid) + ") und die nicht"
                     " begonnenen Pakete anhalten (amw thema anhalten TH" + str(tid) + " [--meilenstein N] oder Planung › Meilensteine)."
                     " Laufende bauen zu Ende. Du entscheidest – angehalten wird nichts von selbst.")
    return [x["bogen"]["nr"] for x in bt]


def anhalten(con, pid, von, tid, bid=None):
    """Die nicht begonnenen Pakete eines Themas anhalten (alle betroffenen Meilensteine oder nur bid): p-Pakete zurückgestellt,
    die übrigen „wartet“ auf den Lead (bzw. den Menschen) mit Grund. Lead, Co oder Mensch. Rückgabe: angehaltene Aufgaben."""
    from . import arbeitspaket
    if not darf_freigeben(con, pid, von):
        raise kern.AmwFehler("Pakete anhalten dürfen Lead, Co-Entwickler oder der Mensch")
    lead = kern.lead(con, pid) or kern.ENTWICKLER
    grund = f"Thema TH{tid} geändert (K8) – der Lead prüft, ob das Paket noch passt"
    schon = _angehalten(con, pid)
    aus = []
    for x in betroffen(con, pid, tid):
        if bid is not None and x["bogen"]["id"] != bid:
            continue
        for aid in x["offen"]:
            if aid in schon:
                continue
            p = arbeitspaket.lesen(con, aid)
            if p.get("art") == "p":
                if p.get("zustand") in ("zurueckgestellt",) or "zurueckgestellt" not in arbeitspaket.UEBERGAENGE.get(p.get("zustand"), ()):
                    continue
                arbeitspaket.zustand_setzen(con, pid, von if von != kern.ENTWICKLER else lead, aid, "zurueckgestellt", grund=grund)
            else:
                kern.aufgabe_status(con, pid, von if von != kern.ENTWICKLER else lead, aid, "wartet", wartet_auf=grund, auf=lead)
            with db.schreiben(con):
                db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=ANGEHALTEN, aufgabe_id=aid,
                             bogen_id=x["bogen"]["id"], text=json.dumps({"aufgabe": aid, "thema": tid, "bogen": x["bogen"]["id"]}))
            aus.append(aid)
    return aus


def _geaendert_seit(con, pid, tid, seit_id):
    """Bekam das Thema nach dem Ereignis seit_id eine neue Fassung (vorgelegt, eigene Bearbeitung) oder wurde es zurückgegeben?
    Fassungsnummer oder None. Ereignis-Nummern statt Zeiten: gleiche Sekunde zählt richtig."""
    from . import themen
    arten = (themen.EREIGNIS["vorgelegt"], themen.EREIGNIS["bearbeitet"], themen.EREIGNIS["zurueck"])
    z = [e for e in themen._ereignisse(con, pid, tid) if e["art"] in arten and e["id"] > seit_id]
    return z[-1].get("fassung") if z else None


def entwuerfe(con, pid, namen):
    """A1940 (K4): offene Entwürfe des Planers zum Ja/Neu-planen und Planer, die gerade laufen – je Thema."""
    from . import planer, planer_fortschritt
    offen, laufend = [], []
    for tid, name in sorted(namen.items()):
        l = planer.laeuft(con, pid, tid)
        if l:
            f = planer_fortschritt.zum_thema(con, pid, tid, art="planer")      # A2025: was er tut, Dauer, Kosten
            laufend.append({"thema": tid, "name": name, "seit_utc": l["zeit_utc"], "fortschritt": f,
                            "fortschritt_zeile": planer_fortschritt.zeile(f) if f else None})
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


def entwurf_ja(con, pid, von, tid, eid=None):
    """Ja zum Entwurf (A1940): legt Meilensteine und Pakete an – Lead oder Mensch (planer.uebernehmen prüft). eid (P462 (5)):
    genau der Entwurf, den die Seite zeigte – ist inzwischen ein neuerer da, gilt das Ja nicht für ihn."""
    from . import planer
    if eid is not None:
        neu = planer.letzter_entwurf(con, pid, int(tid))
        if neu and neu["id"] != int(eid):
            raise kern.AmwFehler("Inzwischen gibt es einen neueren Entwurf – bitte die Seite neu laden und ihn ansehen")
    return planer.uebernehmen(con, pid, von, int(tid), eid=int(eid) if eid is not None else None)


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
    if not (von == kern.ENTWICKLER or kern.ist_lead(con, pid, von)):   # P461 (4)
        raise kern.AmwFehler("Jetzt starten dürfen der Lead oder der Mensch")
    d = daten(con, pid)
    if not d["starten"]:
        raise kern.AmwFehler("Jetzt starten geht erst, wenn alle Meilensteine und alle geplanten Pläne freigegeben sind")
    gestartet = []
    for m in d["meilensteine"]:
        if m["status"] == "geplant" and m["pakete"] and m["plan"]["frei"]:
            planung.bogen_status(con, pid, von, m["id"], "aktiv")
            gestartet.append(m["nr"])
    return gestartet
