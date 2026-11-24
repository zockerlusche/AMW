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
from . import kern, projektweg

VERLAUF_GRENZE = 80
SCHRITT_NR = {s: i for i, s in enumerate(projektweg.SCHRITTE)}


def _themen(con, pid):
    from . import themen
    aus = []
    for t in themen.liste(con, pid):
        z = t.get("zustand") or {}
        aus.append({"id": t["id"], "name": t["name"], "status": z.get("status"), "markiert": bool(z.get("markiert"))})
    return aus


def konzept(con, pid):
    from . import grobplan, themen
    tor = themen.tor(con, pid)
    return {"themen": _themen(con, pid), "n": tor["n"], "g": tor["g"], "zu": bool(tor["konzept_zu"]),
            "abgeschlossen": bool(grobplan.abgeschlossen(con, pid)), "grob_angenommen": bool(grobplan.angenommen(con, pid)),
            "grob_laeuft": bool(grobplan.laeuft(con, pid))}


def _meilenstein(m):
    return {k: m.get(k) for k in ("schluessel", "titel", "ziel", "themen", "fertig_wenn", "endet_mit", "nach", "gleichzeitig",
                                  "aufwand", "tage", "usd")}


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
    return {"fassungen": fassungen, "laeuft": bool(grobplan.laeuft(con, pid)),
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
    aus = []
    for b in _meilensteine(con, pid):
        pakete = _pakete(con, pid, b["id"])
        laeuft = bool(feinplanung.laeuft(con, pid, [b["id"]]))
        if not pakete and not laeuft:
            continue
        aus.append({"bogen": b["id"], "nr": b["nr"], "titel": b["titel"], "status": b["status"], "ziel": b["ziel"],
                    "abnahme": b["abnahme"], "frei": bool(frei.get(b["id"])), "laeuft": laeuft, "pakete": pakete})
    namen = {t["id"]: t["name"] for t in _themen(con, pid)}
    e = planansicht.entwuerfe(con, pid, namen)
    from . import planer
    delta = []
    for x in e["entwuerfe"]:
        d = (planer.letzter_entwurf(con, pid, x["thema"]) or {}).get("entwurf") or {}
        if d.get("delta"):
            delta.append({**x, "hinweise": planhinweis.offene(con, pid, x["thema"])})
    return {"meilensteine": aus, "delta": delta}


def umsetzung(fein_):
    laufend = [m for m in fein_["meilensteine"] if m["status"] == "aktiv"]
    for m in laufend:
        m["fertig"] = sum(p["status"] == "fertig" for p in m["pakete"])
    return {"meilensteine": laufend}


def abschluss(con, pid, freigaben):
    from . import abschluss as ab, planautomatik
    aus = []
    for a in freigaben["abnahme"]:
        b = con.execute("SELECT * FROM bogen WHERE id = ?", (a["bogen"],)).fetchone()
        e = ab.ergebnis(con, pid, a["bogen"]) or {}
        aus.append({"bogen": a["bogen"], "nr": a["nr"], "titel": a["titel"], "status": b["status"], "frei": a["frei"],
                    "bereit": bool(planautomatik.bereit_zur_abnahme(con, b)), "bericht": a["bericht"],
                    "pakete": con.execute("SELECT count(*) FROM aufgabe WHERE bogen_id = ? AND status != 'verworfen'", (a["bogen"],)).fetchone()[0],
                    "pruefung": {"test": e.get("test"), "themen": e.get("themen") or [], "vorfuehrung": e.get("vorfuehrung") or [],
                                 "ok": e.get("ok"), "fehler": e.get("fehler")} if e else None})
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
    return {"schritte": schritte, "dran": s["dran"], "zeile": s["zeile"], "konzept": konzept(con, pid), "grob": g,
            "fein": f, "umsetzung": umsetzung(f), "abschluss": abschluss(con, pid, fr), "fragen": fragen(con, pid),
            "laeufe": planer_fortschritt.laufende(con, pid),
            "verlauf": verlauf.projektweg(con, pid, grenze=VERLAUF_GRENZE)}
