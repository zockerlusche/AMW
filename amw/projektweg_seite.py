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
        fassungen.append(x)
    ja = grobplan.angenommen(con, pid)
    return {"fassungen": fassungen, "laeuft": bool(grobplan.laeuft(con, pid)), "bestand": bestand(con, pid),
            "angenommen": {"fassung": ja.get("fassung"), "angelegt": ja.get("angelegt") or {}} if ja else None,
            "hinweise": planhinweis.alle(con, pid, "grob") if fassungen else []}


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
                    "groesse": r["groesse"], "auftrag": (r["auftrag"] or "")[:600], "pruefbefehl": r["pruefbefehl"],
                    "dateibereich": r["dateibereich"], "nach": nach, "beleg": r["beleg"]})
    return aus


def _meilensteine(con, pid):
    return con.execute("SELECT * FROM bogen WHERE projekt_id = ? AND status IN ('geplant', 'aktiv', 'fertig') ORDER BY nr, id",
                       (pid,)).fetchall()


def fein(con, pid, freigaben):
    """Je Meilenstein: Pakete in Stufen, Plan frei?, Feinplaner läuft?; dazu offene Entwürfe der Planer je Thema (Delta, A2027)."""
    from . import feinplanung, planansicht, planhinweis
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
                    "fassung": letzter.get("fassung") if letzter else None})
    namen = {t["id"]: t["name"] for t in _themen(con, pid)}
    e = planansicht.entwuerfe(con, pid, namen)
    from . import planer
    delta = []
    for x in e["entwuerfe"]:
        d = (planer.letzter_entwurf(con, pid, x["thema"]) or {}).get("entwurf") or {}
        if d.get("delta"):
            delta.append({**{k: v for k, v in x.items() if k != "zeilen"}, **_entwurf_karten(con, pid, d),
                          "hinweise": planhinweis.offene(con, pid, x["thema"])})
    return {"meilensteine": aus, "delta": delta}


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
            r = con.execute("SELECT nr, titel FROM bogen WHERE id = ? AND projekt_id = ?", (m["bestehend"], pid)).fetchone()
            return {"nr": r["nr"] if r else None, "titel": r["titel"] if r else None, "neu": False}
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
                       "groesse": x.get("groesse"), "ziel": ziel(x.get("meilenstein")), "auftrag": (x.get("auftrag") or "")[:800],
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


def _pruef_stand(con, b):
    """Der Stand, zu dem die AMW die Abschlussprüfung führt – derselbe wie in planautomatik.meilenstein_projekt."""
    from . import planautomatik
    letzte = con.execute("SELECT max(coalesce(fertig_utc, geaendert_utc, angelegt_utc)) FROM aufgabe WHERE bogen_id = ?",
                         (b["id"],)).fetchone()[0] or ""
    return planautomatik._stand(con, b, letzte)


def pruefung_starten(con, pid, von, bid):
    """A2064 (TL #32217): Meilensteine, die vor A2029 „bereit zur Abnahme“ wurden, bekommen ihre Prüfung nie von selbst – der
    Mensch (oder der Lead) holt sie nach: Gesamttest und Prüfer gegen das Konzept (abschluss.vor_bereit, Tagesgrenze der Planer
    gilt). Rückgabe {"ergebnis": "pruefung" | "melden" | "nacharbeit"}."""
    from . import abschluss as ab, planautomatik
    if not (von == kern.ENTWICKLER or kern.ist_lead(con, pid, von)):
        raise kern.AmwFehler("Die Abschlussprüfung holen der Mensch oder der Lead nach")
    b = con.execute("SELECT * FROM bogen WHERE id = ? AND projekt_id = ?", (bid, pid)).fetchone()
    if not b:
        raise kern.AmwFehler(f"Meilenstein {bid} gibt es nicht")
    if not planautomatik.bereit_zur_abnahme(con, b):
        raise kern.AmwFehler(f"M{b['nr']} ist nicht bereit zur Abnahme – die Prüfung startet die AMW selbst, wenn alle Pakete fertig sind")
    e = ab.ergebnis(con, pid, bid)
    if e and not (e.get("fehler") and not e.get("angelegt")):    # A2072: ein Ergebnis mit Fehler zählt nicht – erneut starten geht
        raise kern.AmwFehler(f"M{b['nr']} hat schon ein Prüf-Ergebnis – bei Bedarf Nacharbeit anfordern")
    stand = _pruef_stand(con, b)
    if ab._laeuft(con, pid, bid, stand):
        raise kern.AmwFehler(f"M{b['nr']}: die Prüfung läuft schon")
    return {"ergebnis": ab.vor_bereit(con, pid, b, stand, erneut=True)}


def abschluss(con, pid, freigaben):
    from . import abschluss as ab, planautomatik
    aus = []
    for a in freigaben["abnahme"]:
        b = con.execute("SELECT * FROM bogen WHERE id = ?", (a["bogen"],)).fetchone()
        e = ab.ergebnis(con, pid, a["bogen"]) or {}
        bereit = bool(planautomatik.bereit_zur_abnahme(con, b))
        laeuft = bool(bereit and (not e or e.get("fehler")) and ab._laeuft(con, pid, a["bogen"], _pruef_stand(con, b)))
        if laeuft:
            e = {}                                        # A2072: neu gestartet nach einem Fehler – die Karte zeigt „läuft“
        aus.append({"bogen": a["bogen"], "nr": a["nr"], "titel": a["titel"], "status": b["status"], "frei": a["frei"],
                    "bereit": bereit, "bericht": a["bericht"],
                    "pruefung_laeuft": laeuft,
                    "pakete": con.execute("SELECT count(*) FROM aufgabe WHERE bogen_id = ? AND status != 'verworfen'", (a["bogen"],)).fetchone()[0],
                    "pruefung": {"test": e.get("test"), "themen": e.get("themen") or [], "vorfuehrung": e.get("vorfuehrung") or [],
                                 "ok": e.get("ok"), "fehler": bool(e.get("fehler")), "gruende": ab.deuten(e.get("fehler")),
                                 "ziel": e.get("ziel")} if e else None})
    return aus


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


def verlauf_lesbar(eintraege, namen):
    """Je Eintrag: Schritt, eine Zeile in Menschensprache (Thema mit Namen statt TH-Nummer, ohne interne Kürzel wie #…, P4, F4),
    der ganze Text nur, wenn er länger ist (auf Klick)."""
    aus = []
    for e in eintraege:
        text = _TH.sub(lambda m: f"Thema „{namen[int(m.group(1))]}“" if int(m.group(1)) in namen else m.group(0), e.get("text") or "")
        text = re.sub(r"\s{2,}", " ", _KUERZEL.sub("", text)).strip(" ·–,")
        zeile = text if len(text) <= ZEILE_MAX else text[:ZEILE_MAX].rsplit(" ", 1)[0] + " …"
        aus.append({**e, "schritt": _schritt_des_eintrags(e), "zeile": zeile, "lang": text if zeile != text else None})
    return aus


def daten(con, pid):
    """Alles für die Seite in einer Antwort (eine Anfrage je Neuzeichnen, auch online)."""
    from . import planer_fortschritt, verlauf
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
    if f["delta"]:                                       # A2068: eine offene Änderung wartet auf ihr Ja – auch nach erledigtem Feinplan
        wer_plan = projektweg._freigebende(con, pid, "plan")
        for x in schritte:
            if x["schritt"] == "fein":
                x.update(zustand="dran", zeichen=projektweg.ZEICHEN["dran"], wer=wer_plan, bei_dir=ich in wer_plan,
                         fehlt=f"{len(f['delta'])} Änderung(en) am Konzept warten auf das Ja")
        if dran in (None, "umsetzung", "abschluss"):    # früher Offenes (Konzept, Grobplan) geht vor
            dran = "fein"
    k = konzept(con, pid, g["bestand"])
    g_themen = k["themen"]
    return {"schritte": schritte, "dran": dran, "zeile": s["zeile"], "konzept": k, "grob": g,
            "fein": f, "umsetzung": umsetzung(f), "abschluss": abschluss(con, pid, fr), "fragen": fragen(con, pid),
            "laeufe": planer_fortschritt.laufende(con, pid),
            "verlauf": verlauf_lesbar(verlauf.projektweg(con, pid, grenze=VERLAUF_GRENZE),
                                      {t["id"]: t["name"] for t in g_themen})}
