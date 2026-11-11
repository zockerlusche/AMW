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
