"""Grund-Regelwerk: die mitgelieferte Vorlage (amw/vorlagen/grundregelwerk.<sprache>.json) und ihr Weg ins Projekt.

Beim Anlegen eines Projekts werden die gewählten Regeln zu gewöhnlichen Arbeitsregeln des Projekts – eigene Kopie, eigene
Nummer, ein Beschluss als Quelle. Jede trägt dauerhaft ihre Herkunft in `regel.vorlage` („G7/1“ = Grundregel G7 aus
Fassung 1 der Vorlage); daran hängen die Anzeige („Grundregel“, „angepasst“), das Warum bzw. die Erfahrung dahinter und
der spätere Abgleich mit einer neuen Fassung. Projekteigene Regeln haben dort nichts stehen.

In der Vorlage hat jede Regel entweder eine „erfahrung“ (ein belegter Anlass) oder ein „warum“ (die Begründung aus der
Regel selbst) – nie einen erfundenen Vorfall.
"""
import json
import os

from . import db, kern

ORDNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vorlagen")
SPRACHEN = ("de", "en")


def vorlage(sprache="de"):
    """Die Vorlage in einer Sprache (unbekannte Sprache: Deutsch)."""
    with open(os.path.join(ORDNER, f"grundregelwerk.{sprache if sprache in SPRACHEN else 'de'}.json"), encoding="utf-8") as f:
        return json.load(f)


def pruefen():
    """Fehler der Vorlagen (leer = in Ordnung): beide Sprachen mit denselben Regeln in derselben Reihenfolge, je Regel
    Titel, Text und genau eines von erfahrung/warum – in beiden Sprachen dasselbe."""
    fehler = []
    de, en = vorlage("de"), vorlage("en")
    if de["nummer"] != en["nummer"] or de["versionen"] != en["versionen"] or len(de["dod"]) != len(en["dod"]):
        fehler.append("Nummer, Versionen oder Länge der Definition of Done weichen zwischen den Sprachen ab")
    if [r["nr"] for r in de["regeln"]] != [r["nr"] for r in en["regeln"]]:
        fehler.append("Regeln oder Reihenfolge weichen zwischen den Sprachen ab")
        return fehler
    for a, b in zip(de["regeln"], en["regeln"]):
        for r, sprache in ((a, "de"), (b, "en")):
            if not all((r.get(k) or "").strip() for k in ("titel", "text")) or r.get("gruppe") not in vorlage(sprache)["gruppen"]:
                fehler.append(f"{r['nr']} ({sprache}): Titel, Text oder Gruppe fehlt")
            if ("erfahrung" in r) == ("warum" in r):
                fehler.append(f"{r['nr']} ({sprache}): genau eines von erfahrung/warum")
        if ("erfahrung" in a) != ("erfahrung" in b) or bool(a.get("wahlweise")) != bool(b.get("wahlweise")) or a["gruppe"] != b["gruppe"]:
            fehler.append(f"{a['nr']}: Deutsch und Englisch unterscheiden sich in Art, Gruppe oder „wahlweise“")
    return fehler


def regeltext(r):
    """So steht eine Grundregel im Projekt: Kurztitel, dann der Satz."""
    return f"{r['titel']}. {r['text']}"


def vorgabe(lead_chat=False, sprache="de"):
    """Was ohne eigene Auswahl übernommen wird: alle Grundregeln; die wahlweise für Chat-Leads nur, wenn der Lead als Chat arbeitet."""
    return [r["nr"] for r in vorlage(sprache)["regeln"] if not r.get("wahlweise") or (lead_chat and r.get("chat_lead"))]


def uebernehmen(con, pid, von, auswahl=None, texte=None, sprache="de", lead_chat=False):
    """Neues Projekt: die gewählten Grundregeln als Arbeitsregeln anlegen (Nummern 1…n in der Reihenfolge der Vorlage),
    mit einem Beschluss als Quelle; die Definition of Done kommt ins Leitbild, wenn dort noch keine steht.
    auswahl: Nummern der Vorlage (None = vorgabe()); texte: {Nummer: eigener Wortlaut}. Rückgabe {"beschluss", "regeln", "dod"}."""
    from . import planung, wissen
    v = vorlage(sprache)
    bekannt = {r["nr"]: r for r in v["regeln"]}
    auswahl = vorgabe(lead_chat, sprache) if auswahl is None else list(auswahl)
    fremd = [k for k in auswahl if k not in bekannt]
    if fremd:
        raise kern.AmwFehler(f"unbekannte Grundregel: {', '.join(map(str, fremd))}")
    if not auswahl:
        raise kern.AmwFehler("keine Regel gewählt")
    if con.execute("SELECT 1 FROM regel WHERE projekt_id = ? AND ebene = 'arbeit'", (pid,)).fetchone():
        raise kern.AmwFehler("Das Projekt hat schon Arbeitsregeln – das Grund-Regelwerk übernehmen geht nur beim Anlegen")
    gewaehlt = [r for r in v["regeln"] if r["nr"] in set(auswahl)]            # Reihenfolge der Vorlage
    bid = wissen.beschluss_neu(con, pid, von, v["name"], f"{v['name']} {v['nummer']} übernommen: {', '.join(r['nr'] for r in gewaehlt)}",
                               "Assistent „Neues Projekt“")
    with db.schreiben(con):
        zeit = db.jetzt()
        for nr, r in enumerate(gewaehlt, start=1):
            eigener = " ".join(str((texte or {}).get(r["nr"]) or "").split())
            db.einfuegen(con, "regel", ebene="arbeit", projekt_id=pid, nr=nr, text=eigener or regeltext(r), beleg=f"B{bid}",
                         stand_utc=zeit, vorlage=f"{r['nr']}/{v['nummer']}")
    dod = False
    if not planung.leitbild(con, pid)["dod"]:
        planung.leitbild_setzen(con, pid, von, dod=list(v["dod"]))
        dod = True
    return {"beschluss": bid, "regeln": len(gewaehlt), "dod": dod}


def herkunft(kennzeichen, text=None, sprache="de"):
    """Zu `regel.vorlage` („G7/1“): {"nr", "fassung", "titel", "gruppe", "erfahrung" | "warum", "angepasst"} – oder None, wenn
    die Regel nicht aus der Vorlage stammt oder die Vorlage sie nicht (mehr) kennt. angepasst: der Wortlaut im Projekt
    weicht von dem der Vorlage ab (in jeder mitgelieferten Sprache verglichen)."""
    if not kennzeichen or "/" not in kennzeichen:
        return None
    nr, _, fassung = kennzeichen.partition("/")
    v = vorlage(sprache)
    r = next((x for x in v["regeln"] if x["nr"] == nr), None)
    if r is None:
        return None
    aus = {"nr": nr, "fassung": fassung, "titel": r["titel"], "gruppe": v["gruppen"].get(r["gruppe"], r["gruppe"]),
           "wahlweise": bool(r.get("wahlweise"))}
    aus["erfahrung" if "erfahrung" in r else "warum"] = r.get("erfahrung") or r.get("warum")
    if text is not None:
        gleich = {" ".join(regeltext(next(x for x in vorlage(s)["regeln"] if x["nr"] == nr)).split()) for s in SPRACHEN}
        aus["angepasst"] = " ".join(text.split()) not in gleich
    return aus


# --- Bestandsprojekte nachziehen (G-3) – nur Vorschlag, nie überschreiben ------------------------------------------------

AEHNLICH_ANTEIL = 0.34          # so viel vom Wortschatz einer Grundregel muss eine eigene Regel teilen, um als „ähnlich“ zu gelten
AEHNLICH_MIN = 2                # und mindestens so viele gemeinsame Wortstämme


def abgleich(con, pid):
    """Jede Grundregel der Vorlage gegen die Regeln des Projekts: „drin“ (aus der Vorlage übernommen), „aehnlich“ (eine eigene
    Regel teilt genug Wortstämme – Vermutung, der Lead entscheidet) oder „fehlt“. Nur lesend.
    {"vorlage", "regeln": [{nr, titel{de,en}, text{de,en}, wahlweise, status, ref, gemeinsam}], "zahl": {status: n}}."""
    from . import wissen
    de, en = vorlage("de"), vorlage("en")
    eigen = con.execute("SELECT ebene, nr, text, vorlage FROM regel WHERE projekt_id = ? ORDER BY ebene, nr", (pid,)).fetchall()
    drin = {r["vorlage"].partition("/")[0]: r for r in eigen if r["vorlage"]}
    staemme = [(r, set(wissen._staemme(r["text"]))) for r in eigen if not r["vorlage"]]
    ref = lambda r: ("KR" if r["ebene"] == "arbeit" else "PR") + str(r["nr"])
    aus = []
    for g, ge in zip(de["regeln"], en["regeln"]):
        x = {"nr": g["nr"], "titel": {"de": g["titel"], "en": ge["titel"]}, "text": {"de": regeltext(g), "en": regeltext(ge)},
             "wahlweise": bool(g.get("wahlweise")), "status": "fehlt", "ref": None, "gemeinsam": []}
        if g["nr"] in drin:
            x.update(status="drin", ref=ref(drin[g["nr"]]))
        else:
            gs = set(wissen._staemme(regeltext(g))) | set(wissen._staemme(regeltext(ge)))
            best = max(((len(gs & rs) / max(1, len(set(wissen._staemme(regeltext(g))))), r, gs & rs) for r, rs in staemme),
                       key=lambda t: t[0], default=(0, None, set()))
            if best[1] is not None and best[0] >= AEHNLICH_ANTEIL and len(best[2]) >= AEHNLICH_MIN:
                x.update(status="aehnlich", ref=ref(best[1]), gemeinsam=sorted(best[2])[:8])
        aus.append(x)
    zahl = {k: sum(1 for x in aus if x["status"] == k) for k in ("drin", "aehnlich", "fehlt")}
    return {"vorlage": f"{de['name']} {de['nummer']}", "regeln": aus, "zahl": zahl}


def nachziehen(con, pid, von, nr, text=None, sprache="de"):
    """Eine Grundregel in ein bestehendes Projekt übernehmen: nächste freie Nummer der Arbeitsregeln, Beschluss als Quelle,
    Herkunft „Gx/Fassung“. Vorhandene Regeln bleiben, wie sie sind. Nur Lead und Mensch."""
    from . import wissen
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Grundregeln übernehmen dürfen nur Lead und Mensch")
    v = vorlage(sprache)
    nr = str(nr or "").strip().upper()
    g = next((r for r in v["regeln"] if r["nr"] == nr), None)
    if not g:
        raise kern.AmwFehler(f"Grundregel {nr} gibt es nicht – {', '.join(r['nr'] for r in v['regeln'])}")
    da = con.execute("SELECT ebene, nr FROM regel WHERE projekt_id = ? AND vorlage LIKE ?", (pid, f"{nr}/%")).fetchone()
    if da:
        raise kern.AmwFehler(f"{nr} ist schon übernommen ({'KR' if da['ebene'] == 'arbeit' else 'PR'}{da['nr']})")
    eigener = " ".join(str(text or "").split())
    bid = wissen.beschluss_neu(con, pid, von, v["name"], f"{nr} „{g['titel']}“ aus {v['name']} {v['nummer']} übernommen",
                               "Abgleich Grund-Regelwerk")
    with db.schreiben(con):
        neu = (con.execute("SELECT max(nr) FROM regel WHERE projekt_id = ? AND ebene = 'arbeit'", (pid,)).fetchone()[0] or 0) + 1
        db.einfuegen(con, "regel", ebene="arbeit", projekt_id=pid, nr=neu, text=eigener or regeltext(g), beleg=f"B{bid}",
                     stand_utc=db.jetzt(), vorlage=f"{nr}/{v['nummer']}")
    return {"regel": neu, "beschluss": bid}


def bericht(con, pid, sprache="de"):
    """Der Abgleich als Markdown – für das Dokument an den Lead."""
    a = abgleich(con, pid)
    de = sprache != "en"
    zeichen = {"drin": "✓", "aehnlich": "≈", "fehlt": "–"}
    z = [f"# {'Abgleich mit dem' if de else 'Comparison with the'} {a['vorlage']}", "",
         (f"{a['zahl']['drin']} übernommen · {a['zahl']['aehnlich']} vermutlich abgedeckt · {a['zahl']['fehlt']} fehlen. Nur ein Vorschlag:"
          " Vorhandene Regeln bleiben, wie sie sind; fehlende übernimmt der Lead einzeln (`amw regelwerk uebernehmen G7`)."
          if de else
          f"{a['zahl']['drin']} adopted · {a['zahl']['aehnlich']} probably covered · {a['zahl']['fehlt']} missing. A proposal only:"
          " existing rules stay as they are; the lead adopts missing ones one by one (`amw regelwerk uebernehmen G7`)."), "",
         "| | Nr | " + ("Regel | Im Projekt" if de else "Rule | In the project") + " |", "|---|---|---|---|"]
    for x in a["regeln"]:
        wo = x["ref"] or ""
        if x["status"] == "aehnlich":
            wo += (" – gemeinsam: " if de else " – shared: ") + ", ".join(x["gemeinsam"])
        z.append(f"| {zeichen[x['status']]} | {x['nr']}{' *' if x['wahlweise'] else ''} | {x['titel']['de' if de else 'en']} | {wo} |")
    z += ["", ("* wahlweise (für einen Lead, der als Chat arbeitet, bzw. bei Bedarf)" if de else "* optional (for a lead working as a chat, or as needed)")]
    return "\n".join(z) + "\n"
