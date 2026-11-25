"""A2033 (TH164 F2, Kleinprobe D1516 v3): die Daten für die Seite „Projektweg“ – fünf Schritte als Leiste, je Schritt die Ansicht,
dazu Verlauf, laufende Planer (Fortschritt) und offene Fragen. Nur lesen und zusammenstellen; der Browser hält keinen eigenen
Zustand (G12) – alles kommt aus den Modulen, die den Weg schon führen:

- Leiste: projektweg.sicht (A2023) – Zustand je Schritt, wer dran ist;
- Konzept: themen (Status je Thema, Tor), grobplan.abgeschlossen (A2030);
- Grobplan: grobplan.fassungen/entwurf (jede Fassung bleibt), planhinweis (A2028: Hinweise, Änderungen gegenüber der vorigen);
- Feinplan: Meilensteine mit ihren Paketen in Stufen (planung.wellen), Freigaben (planansicht), Feinplaner (A2031), offene
  Delta-Entwürfe der Planer je Thema (A2027, planansicht.entwuerfe);
- Umsetzung: laufende Meilensteine mit Paket-Status;
- Abschluss: Prüf-Ergebnis (A2029), Abschlussbericht und Abnahme je Meilenstein;
- Verlauf: verlauf.projektweg (A2024), Fortschritt: planer_fortschritt.laufende (A2025).

Handlungen (Konzept abschließen, Grobplan freigeben, Hinweis, Überarbeiten lassen) laufen über aktionen.py → die Module selbst;
sie prüfen Rechte und Reihenfolge (projektweg.uebergang_pruefen, Freigaben je Projekt A2032).
"""
import re

from . import kern, projektweg

AUFTRAG_KURZ = 600                              # A2075: so viel steht gleich da, „mehr“ holt den ganzen Auftrag des Pakets
VERLAUF_GRENZE = 400                            # A2063: je Schritt gefiltert – darum mehr als früher 80
SCHRITT_NR = {s: i for i, s in enumerate(projektweg.SCHRITTE)}


def _themen(con, pid):
    from . import themen
    aus = []
    for t in themen.liste(con, pid):
        z = t.get("zustand") or {}
        aus.append({"id": t["id"], "name": t["name"], "status": z.get("status"), "markiert": bool(z.get("markiert"))})
    return aus


def bestand(con, pid):
    """A2061: Meilensteine aus der Zeit vor dem Grobplan (Projekt mit Bestand, ohne Grobplan-Ja und ohne Grobplan-Fassung) –
    neueste zuerst; [] bei einem neuen Projekt oder sobald es einen Grobplan gibt. A2030 kennt noch keine Übernahme
    (Themen den vorhandenen Meilensteinen zuordnen) – bis dahin zeigt die Seite den Bestand und kein „Konzept abschließen“."""
    from . import grobplan
    if grobplan.angenommen(con, pid) or grobplan.fassungen(con, pid):
        return []
    return [{"bogen": r["id"], "nr": r["nr"], "titel": r["titel"], "status": r["status"], "pakete": r["n"] or 0, "fertig": r["f"] or 0}
            for r in con.execute("SELECT b.id, b.nr, b.titel, b.status, (SELECT count(*) FROM aufgabe a WHERE a.bogen_id = b.id AND a.status != 'verworfen') n,"
                                 " (SELECT count(*) FROM aufgabe a WHERE a.bogen_id = b.id AND a.status = 'fertig') f FROM bogen b"
                                 " WHERE b.projekt_id = ? AND b.status IN ('geplant', 'aktiv', 'fertig')"
                                 " ORDER BY CASE b.status WHEN 'aktiv' THEN 0 WHEN 'geplant' THEN 1 ELSE 2 END, b.id DESC", (pid,))]


def konzept(con, pid, best=None):
    from . import grobplan, themen
    tor = themen.tor(con, pid)
    best = bestand(con, pid) if best is None else best
    return {"themen": _themen(con, pid), "n": tor["n"], "g": tor["g"], "zu": bool(tor["konzept_zu"]),
            "abgeschlossen": bool(grobplan.abgeschlossen(con, pid)), "grob_angenommen": bool(grobplan.angenommen(con, pid)),
            "grob_laeuft": bool(grobplan.laeuft(con, pid)), "bestand": len(best)}


def _meilenstein(m):
    return {k: m.get(k) for k in ("schluessel", "titel", "ziel", "themen", "fertig_wenn", "endet_mit", "nach", "gleichzeitig",
                                  "aufwand", "tage", "usd", "bestehend", "status")}          # A2062: übernommener Bestand


def grob(con, pid):
    """Alle Fassungen des Grobplans (älteste zuerst) mit Meilensteinen, Befunden, Fragen und den Änderungen gegenüber der vorigen
    gültigen Fassung; dazu die Hinweise an den Planer und ob er gerade läuft oder der Grobplan schon angenommen ist."""
    from . import grobplan, planhinweis
    fassungen, vorige = [], None
    ja = grobplan.angenommen(con, pid)
    weg = _verworfene_schluessel(con, pid, ja)
    for f in grobplan.fassungen(con, pid):
        if f.get("laeuft"):
            continue
        e = grobplan.entwurf(con, pid, f["fassung"]) or {}
        d = e.get("entwurf")
        x = {"fassung": f["fassung"], "id": f["id"], "zeit_utc": f["zeit_utc"], "modell": f.get("modell"), "usd": f.get("usd"),
             "fehler": f.get("fehler"), "angenommen": f.get("angenommen"), "meilensteine": [], "befunde": [], "fragen": [],
             "grund": None, "aenderung": None}
        if d:
            x.update(meilensteine=[_meilenstein(m) for m in d.get("meilensteine") or []], befunde=d.get("befunde") or [],
                     fragen=d.get("fragen") or [], grund=d.get("grund"))
            if vorige is not None:
                v = planhinweis.vergleich(vorige, d)["meilensteine"]
                x["aenderung"] = {"neu": v["neu"], "geaendert": [{"titel": t, "felder": fe} for t, fe in v["geaendert"]],
                                  "entfallen": v["entfallen"]}
            vorige = d
            if ja and weg and f["fassung"] == ja.get("fassung"):           # A2086 (1): verworfene auch in Liste und Zuordnung weglassen
                x["meilensteine"] = [{**m, **{k: [y for y in m.get(k) or [] if y not in weg] for k in ("nach", "gleichzeitig")}}
                                     for m in x["meilensteine"] if m.get("schluessel") not in weg]
        fassungen.append(x)
    return {"fassungen": fassungen, "laeuft": bool(grobplan.laeuft(con, pid)), "bestand": bestand(con, pid),
            "angenommen": {"fassung": ja.get("fassung"), "angelegt": ja.get("angelegt") or {}, "n": _gueltige(con, pid, ja)} if ja else None,
            "hinweise": planhinweis.alle(con, pid, "grob") if fassungen else []}


def _gueltige(con, pid, ja):
    """A2075: Meilensteine des angenommenen Grobplans ohne die verworfenen – wie der Verlauf „Bestand übernommen: n“."""
    nrn = {int(str(v).lstrip("Mm")) for v in (ja.get("angelegt") or {}).values() if str(v).lstrip("Mm").isdigit()}
    return len(nrn - _verworfene(con, pid))


def _verworfene(con, pid):
    return {r[0] for r in con.execute("SELECT nr FROM bogen WHERE projekt_id = ? AND status = 'verworfen'", (pid,))}


def _verworfene_schluessel(con, pid, ja):
    """A2086 (1): die Schlüssel („M4“) des angenommenen Grobplans, deren Meilenstein verworfen ist – nur für die Anzeige."""
    weg = {f"M{n}" for n in _verworfene(con, pid)}
    return {k for k, v in ((ja or {}).get("angelegt") or {}).items() if str(v).upper() in weg}


def _wer(ap, aufgabe):
    """„Headless · Sonnet“ bzw. „Fenster · CC1“ – Wörter wie im Wörterbuch (TL #31722: nicht „-p sonnet“)."""
    modell = (ap.get("modell") or "").split("/")[-1].split("-")[0].strip()
    if ap.get("art") == "p":
        return "Headless" + (f" · {modell.capitalize()}" if modell else "")
    return "Fenster" + (f" · {aufgabe['agent']}" if aufgabe["agent"] else "")


def _pakete(con, pid, bid):
    from . import arbeitspaket, planung
    rows = con.execute("SELECT * FROM aufgabe WHERE projekt_id = ? AND bogen_id = ? AND status != 'verworfen' ORDER BY rang, id",
                       (pid, bid)).fetchall()
    stufe = planung.wellen(con, [r["id"] for r in rows])
    aus = []
    for r in rows:
        ap = arbeitspaket.lesen(con, r["id"])
        nach = [x[0] for x in con.execute("SELECT vor FROM abhaengigkeit WHERE nach = ?", (r["id"],))]
        aus.append({"id": r["id"], "titel": r["titel"], "status": r["status"], "stufe": stufe.get(r["id"], 1), "agent": r["agent"],
                    "art": ap.get("art"), "wer": _wer(ap, r), "modell": ap.get("modell"), "effort": ap.get("effort"),
                    "groesse": r["groesse"], "auftrag": (r["auftrag"] or "")[:AUFTRAG_KURZ], "auftrag_mehr": len(r["auftrag"] or "") > AUFTRAG_KURZ, "pruefbefehl": r["pruefbefehl"],
                    "dateibereich": r["dateibereich"], "nach": nach, "beleg": r["beleg"]})
    return aus


def _meilensteine(con, pid):
    return con.execute("SELECT * FROM bogen WHERE projekt_id = ? AND status IN ('geplant', 'aktiv', 'fertig') ORDER BY nr, id",
                       (pid,)).fetchall()


def fein(con, pid, freigaben):
    """Je Meilenstein: Pakete in Stufen, Plan frei?, Feinplaner läuft?; dazu offene Entwürfe der Planer je Thema (Delta, A2027)."""
    from . import delta_start, feinplanung, planansicht, planfunde, planhinweis
    fehlt = delta_start.unvollstaendig(con, pid)
    warten = delta_start.wartende(con, pid)                  # A2080: aus einer freigegebenen Änderung, noch nicht gestartet
    frei = {f["bogen"]: f["frei"] for f in freigaben["fein"]}
    entwuerfe = feinplanung._ereignisse(con, pid, feinplanung.ENTWURF)
    aus = []
    for b in _meilensteine(con, pid):
        pakete = _pakete(con, pid, b["id"])
        laeuft = bool(feinplanung.laeuft(con, pid, [b["id"]]))
        letzter = next((e for e in reversed(entwuerfe) if b["id"] in (e.get("boegen") or [])), None)
        fehler = letzter.get("fehler") if letzter and not pakete and not laeuft else None   # A2056: ein abgelehnter Feinplan ist sichtbar
        if not pakete and not laeuft and not fehler:
            continue
        aus.append({"bogen": b["id"], "nr": b["nr"], "titel": b["titel"], "status": b["status"], "ziel": b["ziel"],
                    "abnahme": b["abnahme"], "frei": bool(frei.get(b["id"])), "laeuft": laeuft, "pakete": pakete,
                    "fehler": ([fehler] if isinstance(fehler, str) else list(fehler)) if fehler else None,
                    "gruende": planfunde.deuten(con, pid, fehler) if fehler else [],          # A2076: in Menschensprache
                    "fassung": letzter.get("fassung") if letzter else None,
                    "start_fehlt": fehlt.get(b["id"]) or [],
                    "delta_start": (lambda w: {"thema": w["thema"], "fehler": w["fehler"]} if w else None)(warten.get(b["id"]))})
    namen = {t["id"]: t["name"] for t in _themen(con, pid)}
    e = planansicht.entwuerfe(con, pid, namen)
    from . import planer
    delta, delta_fehler = [], []
    for x in e["entwuerfe"]:
        letzter = planer.letzter_entwurf(con, pid, x["thema"]) or {}
        d = letzter.get("entwurf") or {}
        if letzter.get("fehler") and _ist_aenderung(con, pid, x["thema"], letzter):    # A2076: gescheiterte Änderung – mit Grund
            delta_fehler.append({"thema": x["thema"], "name": x["name"], "eid": x["eid"], "fassung": letzter.get("fassung"),
                                 "gruende": planfunde.deuten(con, pid, letzter["fehler"]),
                                 "hinweise": planhinweis.offene(con, pid, x["thema"])})
        if d.get("delta"):
            delta.append({"wer": delta_start.wer(con, pid, d), "neuer_ms": delta_start.legt_an(d),
                          "startet": delta_start.legt_an(d) or _laeuft_frei(con, pid, d, aus),
                          **{k: v for k, v in x.items() if k != "zeilen"}, **_entwurf_karten(con, pid, d),
                          "hinweise": planhinweis.offene(con, pid, x["thema"])})
    delta_fehler += _teilweise(con, pid, namen)
    da = {x["bogen"] for x in aus}
    naechster = next(({"bogen": b["id"], "nr": b["nr"], "titel": b["titel"]} for b in _meilensteine(con, pid)      # A2086 (8)
                      if b["status"] == "geplant" and b["id"] not in da), None)
    return {"meilensteine": aus, "delta": delta, "delta_fehler": delta_fehler, "lead_klaert": lead_klaert(con, pid), "naechster": naechster}


def _geklaert(con, pid, tid, eid):
    """Nach diesem Entwurf „nichts zu bauen“ vermerkt (oder bestätigt) oder ein Plan angenommen? Dann ist nichts mehr zu tun."""
    from . import planer, tore
    nichts = [x for x in planer._ereignisse(con, pid, tid, planer.NICHTS) if x["id"] > eid]
    if nichts:
        return bool(nichts[-1].get("an", True))
    return any(x["id"] > eid for art in (planer.JA, tore.NICHTS_JA) for x in planer._ereignisse(con, pid, tid, art))


def lead_klaert(con, pid):
    """B2938: Ein gescheiterter Planer ist zuerst Sache des Leads – sein Name, oder None (kein Lead: der Mensch)."""
    lead = kern.lead(con, pid)
    return lead if lead and lead != kern.ENTWICKLER else None


def _laeuft_frei(con, pid, d, meilensteine):
    """Zielt die Änderung auf einen laufenden Meilenstein mit freiem Plan? Dann starten die neuen Pakete mit dem Ja (A2080)."""
    ziele = {m["bestehend"] for m in d.get("meilensteine") or [] if m.get("bestehend")}
    return any(m["nr"] in ziele and m["frei"] and m["status"] == "aktiv" for m in meilensteine)


def _teilweise(con, pid, namen):
    """A2080 (4): das jüngste Ja zu einer Änderung brach beim Anlegen ab – solange kein neuer Entwurf vorliegt, steht es da."""
    from . import planer, planhinweis
    aus = []
    for tid, name in sorted(namen.items()):
        ja = planer._ereignisse(con, pid, tid, planer.JA)
        e = planer.letzter_entwurf(con, pid, tid) if ja and ja[-1].get("abgebrochen") else None
        if e and e["id"] < ja[-1]["id"] and (e.get("entwurf") or {}).get("delta") and not planer.laeuft(con, pid, tid):
            def titel(liste):
                return ", ".join(f"„{t or a}“" for a in liste for t in [_paket_titel(con, pid, a)[1]])
            j = ja[-1]
            bestehend = {m["schluessel"] for m in (e.get("entwurf") or {}).get("meilensteine") or [] if m.get("bestehend")}
            da = ", ".join(str(v) for k, v in (j.get("angelegt") or {}).items() if k not in bestehend)
            gruende = [{"art": "teil_" + art, "x": {"x": text}} for art, text in (
                ("angelegt", da), ("geaendert", titel(j.get("geaendert") or [])), ("verworfen", titel(j.get("verworfen") or [])),
                ("offen", ", ".join(y for y in (titel(j.get("offen") or []), ", ".join(f"„{t}“" for t in j.get("offen_neu") or [])) if y))) if text]
            aus.append({"thema": tid, "name": name, "eid": e["id"], "fassung": e.get("fassung"), "teilweise": True,
                        "gruende": gruende + [{"art": "teil_lead", "x": {}}], "hinweise": planhinweis.offene(con, pid, tid)})
    return aus


def _fehler_wort(fehler):
    """A2086 (4): nur teilweise umgesetzt ist kein „Plan passte nicht“."""
    teil = sum(1 for x in fehler if x.get("teilweise"))
    return "teilweise umgesetzt" if teil == len(fehler) else "der Plan passte nicht" if not teil else "zu klären"


def _ist_aenderung(con, pid, tid, e):
    """Gehört dieser abgelehnte Entwurf zur freigegebenen Fassung und war er eine Konzeptänderung? Ältere Ereignisse ohne das Feld
    delta: nach dem heutigen Stand des Themas."""
    from . import planer_delta, themen
    if themen.status(con, themen.finden(con, pid, tid)).get("freigegeben") != e.get("fassung") or _geklaert(con, pid, tid, e["id"]):
        return False
    return bool(e.get("delta")) or planer_delta.kontext(con, pid, tid) is not None


def _paket_titel(con, pid, ref):
    try:
        aid = int(str(ref).lstrip("Aa"))
    except ValueError:
        return None, None
    r = con.execute("SELECT id, titel FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    return (r["id"], r["titel"]) if r else (aid, None)


def _entwurf_karten(con, pid, d):
    """A2065: ein Entwurf des Planers (auch ein Delta) als Karten – neue Pakete in Stufen (aus „nach“ innerhalb des Entwurfs),
    „wer“ in Worten, Ziel-Meilenstein mit Projektnummer (bestehend) oder als neu; dazu geändert/verworfen mit dem bisherigen Titel.
    Auftrag, Abnahme-Befehl, Bereiche und Grund nur für das Seitenfenster."""
    ms = {m.get("schluessel"): m for m in d.get("meilensteine") or []}

    def ziel(k):
        m = ms.get(k) or {}
        if m.get("bestehend"):
            r = con.execute("SELECT nr, titel FROM bogen WHERE projekt_id = ? AND nr = ?", (pid, m["bestehend"])).fetchone()   # die Projektnummer
            return {"nr": m["bestehend"], "titel": r["titel"] if r else None, "neu": False}
        return {"nr": None, "titel": m.get("titel") or k, "neu": True}
    pakete = d.get("pakete") or []
    nach_key = {x.get("schluessel"): [v for v in x.get("nach") or [] if v in {y.get("schluessel") for y in pakete}] for x in pakete}
    stufe = {}

    def tiefe(k, pfad=()):
        if k in stufe:
            return stufe[k]
        if k in pfad:
            return 1
        stufe[k] = 1 + max((tiefe(v, pfad + (k,)) for v in nach_key.get(k) or []), default=0)
        return stufe[k]
    karten = []
    for x in pakete:
        modell = (x.get("modell") or "").capitalize()
        karten.append({"schluessel": x.get("schluessel"), "titel": x.get("titel"), "stufe": tiefe(x.get("schluessel")),
                       "wer": ("Headless" + (f" · {modell}" if modell else "")) if x.get("ausfuehrung") == "p" else "Fenster",
                       "groesse": x.get("groesse"), "ziel": ziel(x.get("meilenstein")), "auftrag": x.get("auftrag") or "",
                       "abnahme": x.get("abnahme_befehl"), "bereiche": x.get("bereiche"), "grund": x.get("interaktiv_grund"),
                       "nach": x.get("nach") or []})
    aendern, verwerfen, nacharbeit = [], [], []
    for y in d.get("aendern") or []:
        aid, alt = _paket_titel(con, pid, y.get("paket"))
        aendern.append({"aufgabe": aid, "alt": alt, "titel": y.get("titel"), "grund": y.get("grund")})
    for y in d.get("verwerfen") or []:
        aid, alt = _paket_titel(con, pid, y.get("paket"))
        verwerfen.append({"aufgabe": aid, "alt": alt, "grund": y.get("grund")})
    for y in d.get("nacharbeit") or []:                      # A2059: nur, was der Planer ausdrücklich als Nacharbeit nennt
        aid, alt = _paket_titel(con, pid, y.get("paket"))
        nacharbeit.append({"aufgabe": aid, "alt": alt, "grund": y.get("grund")})
    ziele = []
    for k in karten:
        z = k["ziel"]
        if z not in ziele:
            ziele.append(z)
    return {"karten": karten, "aendern": aendern, "verwerfen": verwerfen, "nacharbeit": nacharbeit, "ziele": ziele}


def umsetzung(fein_):
    laufend = [m for m in fein_["meilensteine"] if m["status"] == "aktiv"]
    for m in laufend:
        m["fertig"] = sum(p["status"] == "fertig" for p in m["pakete"])
    return {"meilensteine": laufend}


def pruefung_starten(con, pid, von, bid):
    """A2064 (TL #32217): Meilensteine, die vor A2029 „bereit zur Abnahme“ wurden, bekommen ihre Prüfung nie von selbst – der
    Mensch (oder der Lead) holt sie nach: Gesamttest und Prüfer gegen das Konzept (abschluss.vor_bereit, Tagesgrenze der Planer
    gilt). Rückgabe {"ergebnis": "pruefung" | "melden" | "nacharbeit"}."""
    from . import abschluss as ab, abschlusslage, planautomatik
    if not (von == kern.ENTWICKLER or kern.ist_lead(con, pid, von)):
        raise kern.AmwFehler("Die Abschlussprüfung holen der Mensch oder der Lead nach")
    b = con.execute("SELECT * FROM bogen WHERE id = ? AND projekt_id = ?", (bid, pid)).fetchone()
    if not b:
        raise kern.AmwFehler(f"Meilenstein {bid} gibt es nicht")
    if abschlusslage.ruht(con, b):
        raise kern.AmwFehler(f"M{b['nr']} ist laufend – die Prüfung startet, wenn er vorgelegt wird: amw bogen vorlegen M{b['nr']}")
    if not planautomatik.bereit_zur_abnahme(con, b):
        raise kern.AmwFehler(f"M{b['nr']} ist nicht bereit zur Abnahme – die Prüfung startet die AMW selbst, wenn alle Pakete fertig sind")
    e = abschlusslage.ergebnis(con, pid, b)
    if e and not (e.get("fehler") and not e.get("angelegt")):    # A2072: ein Ergebnis mit Fehler zählt nicht – erneut starten geht
        raise kern.AmwFehler(f"M{b['nr']} hat schon ein Prüf-Ergebnis – bei Bedarf Nacharbeit anfordern")
    stand = abschlusslage.stand(con, b)
    if ab._laeuft(con, pid, bid, stand):
        raise kern.AmwFehler(f"M{b['nr']}: die Prüfung läuft schon")
    return {"ergebnis": ab.vor_bereit(con, pid, b, stand, erneut=True)}


def abschluss(con, pid, freigaben):
    from . import abschluss as ab, abschlusslage
    aus = []
    for a in freigaben["abnahme"]:
        b = con.execute("SELECT * FROM bogen WHERE id = ?", (a["bogen"],)).fetchone()
        lage = abschlusslage.lage(con, pid, b)            # A2082: wie es steht und wer dran ist – die Seite rechnet nichts davon selbst
        e = {} if lage == "laeuft" else (abschlusslage.ergebnis(con, pid, b) if lage else ab.ergebnis(con, pid, a["bogen"])) or {}
        aus.append({"bogen": a["bogen"], "nr": a["nr"], "titel": a["titel"], "status": b["status"], "frei": a["frei"],
                    "bereit": lage is not None, "bericht": a["bericht"], "lage": lage, "bei_dir": abschlusslage.bei_mensch(con, pid, lage),
                    "pruefung_laeuft": lage == "laeuft",
                    "pakete": con.execute("SELECT count(*) FROM aufgabe WHERE bogen_id = ? AND status != 'verworfen'", (a["bogen"],)).fetchone()[0],
                    "pruefung": {"test": e.get("test"), "themen": e.get("themen") or [], "vorfuehrung": e.get("vorfuehrung") or [],
                                 "ok": e.get("ok"), "fehler": bool(e.get("fehler")), "gruende": ab.deuten(e.get("fehler")),
                                 "ziel": e.get("ziel")} if e else None})
    return aus


def laufende(con, pid):
    """A2082: Meilensteine, die als laufend geschaltet sind – [{"bogen", "nr", "titel", "ruht"}]; ruht: noch nicht vorgelegt."""
    from . import abschlusslage
    return [{"bogen": b["id"], "nr": b["nr"], "titel": b["titel"], "ruht": abschlusslage.ruht(con, b)}
            for b in con.execute("SELECT * FROM bogen WHERE projekt_id = ? AND status IN ('geplant', 'aktiv') ORDER BY nr, id", (pid,)).fetchall()
            if abschlusslage.laufend(con, b["id"])]


def fragen(con, pid):
    """Offene Fragen an den Menschen wie auf der Seite „Fragen“ (workbench.daten_fragen – dieselbe Karte, dort beantwortbar), je
    Frage dazu, woraus sie stammt: Paket (Titel, Meilenstein) oder ohne Paket (vom Planer bzw. Lead, A2021)."""
    from . import workbench
    lead, aus = kern.lead(con, pid), []
    for f in workbench.daten_fragen(con, pid):
        paket = con.execute("SELECT titel, bogen_id FROM aufgabe WHERE id = ?", (f["aufgabe_id"],)).fetchone() if f.get("aufgabe_id") else None
        aus.append({**f, "paket": paket["titel"] if paket else None, "bogen": paket["bogen_id"] if paket else None,
                    "vom_lead": f.get("von") == lead})
    return aus


_SCHRITT_ART = {
    "konzept": ("thema_vorgelegt", "thema_bearbeitet", "thema_freigegeben", "thema_zurueck", "thema_ja", "thema_loeschen_markiert",
                "thema_markierung_aufgehoben", "thema_gegenlesen", "thema_gegengelesen", "konzept_uebernommen", "konzept_abschluss_ja",
                "konzept_abschluss"),
    "grob": ("grobplan_angestossen", "grobplan_entwurf", "grobplan_ja_stimme", "grobplan_ja"),
    "fein": ("thema_planer", "thema_planentwurf", "thema_plan_ja", "thema_nichts_zu_bauen"),   # ein Planer zu einer Konzeptänderung gehört zu Fein
    "abschluss": ("abschluss_bericht",),
}
_ART_SCHRITT = {art: schritt for schritt, arten in _SCHRITT_ART.items() for art in arten}
ZEILE_MAX = 140
_TH = re.compile(r"\bTH(\d+)\b")
_KUERZEL = re.compile(r"(#\d+|\b[PF]\d+\b)")


def _schritt_des_eintrags(e):
    """Zu welchem Schritt gehört ein Eintrag im Verlauf? (A2063, TL #32153)"""
    art, text = e["art"], e.get("text") or ""
    if art in _ART_SCHRITT:
        return _ART_SCHRITT[art]
    if art in ("meilenstein_frei", "meilenstein_ja"):
        return "grob" if "Grobplan" in text else "abschluss" if "Abschluss" in text else "fein"
    if art == "plan_hinweis":
        return "grob" if "– Grobplan" in text else "fein"
    return {"pruefer": "abschluss", "planer": "fein"}.get(e.get("rolle"), "umsetzung")   # eigens gespeicherte Ereignisse (A2024)


def verlauf_lesbar(eintraege, namen, saetze=None):
    """Je Eintrag: Schritt, eine Zeile in Menschensprache (Thema mit Namen statt TH-Nummer, ohne interne Kürzel wie #…, P4, F4),
    der ganze Text nur, wenn er länger ist (auf Klick). saetze (A2076): macht aus den Funden eines Eintrags Sätze – als Grund auf Klick."""
    aus = []
    for e in eintraege:
        text = _TH.sub(lambda m: f"Thema „{namen[int(m.group(1))]}“" if int(m.group(1)) in namen else m.group(0), e.get("text") or "")
        text = re.sub(r"\s{2,}", " ", _KUERZEL.sub("", text)).strip(" ·–,")
        zeile = text if len(text) <= ZEILE_MAX else text[:ZEILE_MAX].rsplit(" ", 1)[0] + " …"
        lang = text if zeile != text else e.get("mehr")        # A2075: z. B. die Meilensteine einer Übernahme
        grund = saetze(e["fehler"]) if saetze and e.get("fehler") else None
        if grund:
            lang = (lang + " – " if lang else "") + " ".join(grund)
        aus.append({**{k: v for k, v in e.items() if k not in ("fehler", "mehr")}, "schritt": e.get("schritt") or _schritt_des_eintrags(e), "zeile": zeile, "lang": lang})
    return aus


def verlauf_gesamt(con, pid, namen=None):
    """Der Verlauf der Seite (A2077): gespeicherte Ereignisse des Projektwegs und die abgeleiteten (verlauf_quellen), je Schritt."""
    from . import planfunde, verlauf, verlauf_quellen
    if namen is None:
        namen = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM thema WHERE projekt_id = ?", (pid,))}
    weg = verlauf.projektweg(con, pid, grenze=VERLAUF_GRENZE, buendeln=True)
    return verlauf_lesbar(verlauf_quellen.gesamt(con, pid, weg, _schritt_des_eintrags), namen, lambda x: planfunde.saetze(con, pid, x))


def _abnahme_dran(con, pid, schritte, dran, f, u, ab, ich):
    """A2080 (7): wartet ein Meilenstein auf seine Abnahme, ist Abschluss dran; sind alle Pakete aller laufenden Meilensteine
    fertig, ist Umsetzung nicht mehr dran (erledigt, wenn nichts mehr geplant ist – sonst offen). Rückgabe: der Schritt, der dran ist."""
    je = {x["schritt"]: x for x in schritte}
    alles_fertig = bool(u["meilensteine"]) and all(m["pakete"] and all(p["status"] in ("fertig", "verworfen") for p in m["pakete"])
                                                   for m in u["meilensteine"])
    um = je["umsetzung"]
    if alles_fertig and um["zustand"] == "dran":
        geplant = con.execute("SELECT 1 FROM bogen WHERE projekt_id = ? AND status = 'geplant' LIMIT 1", (pid,)).fetchone()
        z = "offen" if geplant else "erledigt"
        um.update(zustand=z, zeichen=projektweg.ZEICHEN[z], wer=[], bei_dir=False)
    if any(x["bereit"] and not x["frei"] for x in ab):
        wer = (projektweg._freigebende(con, pid, "abschluss") if any(x["bei_dir"] and not x["frei"] for x in ab)
               else projektweg._lead(con, pid))              # A2082 (B2938): fehlt die Prüfung oder ging sie nicht, ist der Lead dran
        je["abschluss"].update(zustand="dran", zeichen=projektweg.ZEICHEN["dran"], wer=wer, bei_dir=ich in wer)
        if dran is None or (dran == "umsetzung" and alles_fertig):
            dran = "abschluss"
    return dran


def _trotz_offenem_konzept(schritte, g, u, fr):
    """A2091 (10): wartet wieder eine Fassung im Konzept, gelten die Schritte danach als offen – laufen aber Meilensteine, stimmt die
    Anzeige ○ nicht: Umsetzung bleibt ●, die angenommene Grobplanung ✓. Nur die Anzeige; wer dran ist und jede Freigabe-Regel bleiben."""
    je = {x["schritt"]: x for x in schritte}
    if not any(p["status"] not in ("fertig", "verworfen") for m in u["meilensteine"] for p in m["pakete"]):
        return
    for s, z in (("grob", "erledigt" if g["angenommen"] and fr["grob"]["n"] == fr["grob"]["g"] else None), ("umsetzung", "dran")):
        if z and je[s]["zustand"] == "offen":
            je[s].update(zustand=z, zeichen=projektweg.ZEICHEN[z])


LAUF_SCHRITT = {"gegenlesen": "konzept", "grobplaner": "grob", "feinplaner": "fein", "planer": "fein", "abschluss": "abschluss"}


def laeufe(con, pid):
    """A2078: was gerade läuft – mit Schritt, wer es ausgelöst hat (Rolle) und ob der Mensch es selbst angeklickt hat („mein“:
    nur dann öffnet sich das Fenster). Alte Einträge ohne Auslöser: kein Fenster."""
    from . import abschluss as ab, planer_fortschritt
    aus = []
    for l in planer_fortschritt.laufende(con, pid) + ab.laufende(con, pid):
        a = l.get("ausloeser")
        rolle = ("mensch" if a == kern.ENTWICKLER else "amw" if a == "AMW" else "lead" if a and kern.ist_lead(con, pid, a)
                 else "co" if a and kern.ist_co(con, pid, a) else "agent" if a else None)
        aus.append({**l, "schritt": LAUF_SCHRITT.get(l.get("art"), "fein"), "rolle": rolle, "mein": rolle == "mensch" and l.get("anlass") == "klick"})
    return aus


def daten(con, pid):
    """Alles für die Seite in einer Antwort (eine Anfrage je Neuzeichnen, auch online)."""
    s = projektweg.sicht(con, pid)
    fr = s["freigaben"]
    f = fein(con, pid, fr)
    ich = kern.entwickler_name(con, pid)
    g = grob(con, pid)
    schritte = []
    for x in s["schritte"]:
        wer = x.get("wer") or []
        if x["schritt"] == "grob" and x["zustand"] == "dran" and g["fassungen"] and not g["angenommen"] and not g["laeuft"]                 and not g["fassungen"][-1]["fehler"]:
            wer = projektweg._freigebende(con, pid, "grob")      # A2030: ein Grobplan liegt vor – das Ja gibt, wer Grobpläne freigibt
        schritte.append({**x, "wer": wer, "nr": SCHRITT_NR[x["schritt"]], "bei_dir": x["zustand"] == "dran" and ich in wer})
    dran = s["dran"]
    lead = f["lead_klaert"]
    fehler_wer = [lead] if lead else projektweg._freigebende(con, pid, "plan")      # A2076/B2938: zuerst der Lead, ohne Lead der Mensch
    if any(m["fehler"] and m["status"] == "geplant" for m in f["meilensteine"]) and not any(
            m["pakete"] and not m["frei"] and m["status"] == "geplant" for m in f["meilensteine"]):
        wer_plan = fehler_wer
        for x in schritte:
            if x["schritt"] == "fein" and x["zustand"] == "dran":
                x.update(wer=wer_plan, bei_dir=ich in wer_plan)
    start = [m for m in f["meilensteine"] if m["delta_start"]]         # A2080 (5): wartet auf „freigeben und starten“
    if f["delta"] or f["delta_fehler"] or start:                  # A2076: auch eine gescheiterte Änderung; A2068: eine offene Änderung wartet auf ihr Ja – auch nach erledigtem Feinplan
        wer_plan = f["delta"][0]["wer"] if f["delta"] else [ich] if start else fehler_wer
        for x in schritte:
            if x["schritt"] == "fein":
                x.update(zustand="dran", zeichen=projektweg.ZEICHEN["dran"], wer=wer_plan, bei_dir=ich in wer_plan,
                         fehlt=(f"{len(f['delta'])} Änderung(en) am Konzept warten auf das Ja" if f["delta"]
                                else f"{len(f['delta_fehler'])} Änderung(en) am Konzept: {_fehler_wort(f['delta_fehler'])}" if f["delta_fehler"]
                                else f"{len(start)} Meilenstein(e) einer Änderung warten auf das Starten"))
        nur_lead = lead and not f["delta"] and not start     # B2938: was der Lead klärt, holt den Menschen nicht von seinem Schritt weg
        if not nur_lead and dran in (None, "umsetzung", "abschluss") or (dran == "grob" and start and g["angenommen"]):   # früher Offenes geht vor –
            dran = "fein"                                # außer der Grobplan steht schon und nur der Start der Änderung fehlt
    k = konzept(con, pid, g["bestand"])
    g_themen = k["themen"]
    u, ab = umsetzung(f), abschluss(con, pid, fr)
    dran = _abnahme_dran(con, pid, schritte, dran, f, u, ab, ich)
    _trotz_offenem_konzept(schritte, g, u, fr)
    return {"schritte": schritte, "dran": dran, "zeile": s["zeile"], "konzept": k, "grob": g,
            "fein": f, "umsetzung": u, "abschluss": ab, "laufende": laufende(con, pid), "fragen": fragen(con, pid),
            "laeufe": laeufe(con, pid),
            "verlauf": verlauf_gesamt(con, pid, {t["id"]: t["name"] for t in g_themen})}
