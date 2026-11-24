"""A2028 (TH164 „Überarbeiten lassen“): Hinweise an den Planer und neue Fassungen mit markierten Änderungen.

Eine Ergänzung oder Änderung an einer Karte – Thema, Meilenstein oder Paket – geht als Hinweis an den Planer (Ereignis
plan_hinweis). „Überarbeiten lassen“ startet ihn wieder: Er bekommt seinen vorigen Entwurf und die offenen Hinweise, prüft sie
und legt eine neue Fassung vor. Das geht beliebig oft; jede Fassung bleibt sichtbar (grobplan_entwurf bzw. thema_planentwurf),
und die Änderungen gegenüber der Fassung davor sind markiert (vergleich). Offen ist ein Hinweis, solange nach ihm noch kein
neuer Entwurf desselben Plans kam. Gilt für den Grobplan über das ganze Konzept (plan „grob“) und den Plan je Thema (TH12);
der Feinplan je Meilenstein (A2031) hängt sich mit seinem Plan-Schlüssel an dieselbe Stelle.

Ereignis (plan_ereignis, ohne Schemaänderung): plan_hinweis {"plan": "grob" | "TH12", "thema": 12 | null, "bezug": "TH3" |
"M2" | "P4" | "A123" | null, "text"}. Der Verlauf (A2024) liest es.
"""
import json
import re

from . import db, kern

ART = "plan_hinweis"
MAX_TEXT = 2000
_BEZUG = re.compile(r"^(TH|M|P|A)\d+$")

AUFTRAG = (
    "ÜBERARBEITEN: Du hast diesen Plan schon einmal entworfen (vorige.json). Lies hinweise.md – Ergänzungen und Änderungen, die "
    "Mensch, Lead oder Co-Entwickler an einzelnen Karten (Thema, Meilenstein, Paket) gemacht haben. Prüfe jeden Hinweis gegen "
    "das Konzept und lege eine vollständige neue Fassung im gewohnten Schema vor: übernimm, was passt, und ändere nur, was die "
    "Hinweise verlangen oder was daraus folgt. Lehnst du einen Hinweis ab, nenne den Grund im Feld grund bzw. als Befund.")


def plan_schluessel(plan):
    """„grob“ oder ein Thema (12, „TH12“) → („grob“, None) bzw. („TH12“, 12)."""
    s = str(plan).strip()
    if s.lower() == "grob":
        return "grob", None
    m = re.fullmatch(r"(?i)(?:TH)?(\d+)", s)
    if not m:
        raise kern.AmwFehler(f"Plan „{plan}“: grob oder TH<n>")
    return f"TH{int(m.group(1))}", int(m.group(1))


def _letzter_entwurf_id(con, pid, plan):
    from . import grobplan, planer
    s, tid = plan_schluessel(plan)
    if s == "grob":
        e = grobplan.entwurf(con, pid)
    else:
        e = planer.letzter_entwurf(con, pid, tid)
    return e["id"] if e else None


def hinweis(con, pid, von, plan, text, bezug=None):
    """Einen Hinweis zu einem Plan festhalten – der Mensch, der Lead oder der Co-Entwickler. bezug: die Karte (TH3, M2, P4,
    A123) oder None für den ganzen Plan. Rückgabe: Ereignis-Nummer."""
    from . import themen
    if not (von == kern.ENTWICKLER or kern.ist_lead(con, pid, von) or kern.ist_co(con, pid, von)):
        raise kern.AmwFehler("Hinweise an den Planer geben der Mensch, der Lead und der Co-Entwickler")
    s, tid = plan_schluessel(plan)
    text = (text or "").strip()
    if not text:
        raise kern.AmwFehler("Text fehlt: was soll der Planer ergänzen oder ändern?")
    if len(text) > MAX_TEXT:
        raise kern.AmwFehler(f"Hinweis länger als {MAX_TEXT} Zeichen")
    if bezug is not None:
        bezug = str(bezug).strip().upper()
        if not _BEZUG.match(bezug):
            raise kern.AmwFehler(f"Karte „{bezug}“: TH3, M2, P4 oder A123")
    if _letzter_entwurf_id(con, pid, s) is None:
        raise kern.AmwFehler(("Es gibt noch keinen Grobplan" if s == "grob" else f"TH{tid} hat noch keinen Planentwurf")
                             + " – Hinweise gehen an einen vorliegenden Entwurf")
    if tid is not None:
        themen.finden(con, pid, tid)
    with db.schreiben(con):
        return db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=ART,
                            text=json.dumps({"thema": tid, "plan": s, "bezug": bezug, "text": text}, ensure_ascii=False))


def alle(con, pid, plan):
    """Alle Hinweise zu einem Plan, älteste zuerst: [{"id", "von", "zeit_utc", "bezug", "text", "offen"}]."""
    s, _ = plan_schluessel(plan)
    letzter = _letzter_entwurf_id(con, pid, s) or 0
    aus = []
    for r in con.execute("SELECT id, von, zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id", (pid, ART)):
        d = json.loads(r["text"] or "{}")
        if d.get("plan") == s:
            aus.append({"id": r["id"], "von": r["von"], "zeit_utc": r["zeit_utc"], "bezug": d.get("bezug"), "text": d.get("text"),
                        "offen": r["id"] > letzter})
    return aus


def offene(con, pid, plan):
    return [h for h in alle(con, pid, plan) if h["offen"]]


def ueberarbeiten(con, pid, von, plan):
    """„Überarbeiten lassen“: den Planer mit den offenen Hinweisen neu starten. Rückgabe: Text."""
    from . import grobplan, planer, themen
    if not (von == kern.ENTWICKLER or kern.ist_lead(con, pid, von) or kern.ist_co(con, pid, von)):
        raise kern.AmwFehler("Überarbeiten lassen dürfen der Mensch, der Lead und der Co-Entwickler")
    s, tid = plan_schluessel(plan)
    if not offene(con, pid, s):
        raise kern.AmwFehler("Keine offenen Hinweise – erst einen Hinweis geben (oder neu planen lassen)")
    if s == "grob":
        return grobplan.anstossen(con, pid, von=von)
    st = themen.status(con, themen.finden(con, pid, tid))
    return planer.anstossen(con, pid, tid, st["fassung"], von=von, erneut=True)


def dateien(con, pid, plan):
    """Für den Planer-Lauf: {"vorige.json", "hinweise.md"} – oder {} ohne offene Hinweise."""
    from . import grobplan, planer
    s, tid = plan_schluessel(plan)
    h = offene(con, pid, s)
    if not h:
        return {}
    e = grobplan.entwurf(con, pid) if s == "grob" else planer.letzter_entwurf(con, pid, tid)
    vorher = (e or {}).get("entwurf") or {}
    md = [f"# Hinweise zum Plan ({'Grobplan' if s == 'grob' else s}), zur Fassung {(e or {}).get('fassung')}", ""]
    for x in h:
        md.append(f"- {x['von']}" + (f" zu {x['bezug']}" if x["bezug"] else " zum ganzen Plan") + f": {x['text']}")
    return {"vorige.json": json.dumps(vorher, ensure_ascii=False, indent=1), "hinweise.md": "\n".join(md) + "\n"}


# --- Änderungen zwischen zwei Fassungen ---------------------------------------------------------------------------------

_FELDER = {"meilensteine": ("ziel", "themen", "fertig_wenn", "endet_mit", "nach", "gleichzeitig", "aufwand", "tage", "usd", "bestehend"),
           "pakete": ("auftrag", "groesse", "art", "ausfuehrung", "modell", "fertig_quelle", "nach", "abnahme_befehl", "bereiche")}


def _schluessel_zu_titel(liste):
    return {x.get("schluessel"): (x.get("titel") or f"Meilenstein {x.get('bestehend')}") for x in liste}


def _vergleichbar(x, feld, namen):
    v = x.get(feld)
    if feld == "nach" or feld == "gleichzeitig":         # Schlüssel können sich verschieben – über den Titel vergleichen
        return sorted(namen.get(k, k) for k in v or [])
    return v


def vergleich(alt, neu):
    """Änderungen von Fassung alt zu Fassung neu (zwei Entwürfe): {"neu": [Titel], "geaendert": [(Titel, [Felder])],
    "entfallen": [Titel]} – je Art (meilensteine, pakete); verglichen wird über den Titel, nicht den Schlüssel."""
    aus = {}
    for art in ("meilensteine", "pakete"):
        a, n = (alt or {}).get(art) or [], (neu or {}).get(art) or []
        na, nn = _schluessel_zu_titel((alt or {}).get("meilensteine", []) + (alt or {}).get("pakete", [])), \
            _schluessel_zu_titel((neu or {}).get("meilensteine", []) + (neu or {}).get("pakete", []))
        ta = {(x.get("titel") or f"Meilenstein {x.get('bestehend')}"): x for x in a}
        tn = {(x.get("titel") or f"Meilenstein {x.get('bestehend')}"): x for x in n}
        geaendert = []
        for t, x in tn.items():
            if t in ta:
                felder = [f for f in _FELDER[art] if _vergleichbar(x, f, nn) != _vergleichbar(ta[t], f, na)]
                if felder:
                    geaendert.append((t, felder))
        aus[art] = {"neu": [t for t in tn if t not in ta], "geaendert": geaendert, "entfallen": [t for t in ta if t not in tn]}
    return aus


def zeilen(alt, neu, gegen):
    """Lesbare Zeilen „Änderungen gegenüber <gegen>“ (z. B. „Fassung 2“, „Entwurf 1“) – leer, wenn nichts geändert ist."""
    v = vergleich(alt, neu)
    z = []
    for art, name in (("meilensteine", "Meilenstein"), ("pakete", "Paket")):
        for t in v[art]["neu"]:
            z.append(f"  + neu: {name} „{t}“")
        for t, felder in v[art]["geaendert"]:
            z.append(f"  ~ geändert: {name} „{t}“ ({', '.join(felder)})")
        for t in v[art]["entfallen"]:
            z.append(f"  − entfallen: {name} „{t}“")
    return ([f"Änderungen gegenüber {gegen}:"] + z) if z else []


def schreiben(con, pid, plan, ordner):
    """Legt vorige.json und hinweise.md in den Ordner des Planers, wenn es offene Hinweise gibt. Rückgabe: die Dateinamen."""
    import os
    teile = dateien(con, pid, plan)
    for name, text in teile.items():
        with open(os.path.join(ordner, name), "w", encoding="utf-8", newline="\n") as d:
            d.write(text)
    return sorted(teile)
