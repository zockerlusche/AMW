"""A2102: Eingriffe – wer auf einen Prüfpunkt warten würde.

Für eine Stelle im Plan (hinter einem Paket) sagt diese Sicht, was bei einem Prüfpunkt beim Menschen warten würde und was
weiterläuft. Vorgänger sind die der Planung (Tabelle abhaengigkeit; die alte Textspalte aufgabe.abhaengig_von ist seit
Schema 7 dorthin übernommen und wird nirgends mehr gelesen). Ob ein Paket schon begonnen hat, entscheidet dieselbe Einteilung
wie bei der Konzeptänderung (auch für p-Pakete nach ihrem Zustand).

wartende() liest nur. Den Prüfpunkt setzen, entfernen und nachziehen: A2096, unten.
"""
import json

from . import db, kern, konzeptaenderung, planung


def wartende(con, pid, nach_aufgabe):
    """Was bei einem Prüfpunkt hinter nach_aufgabe geschähe – Nummern in der Reihenfolge Rang, Nummer:

    {"wartet": [A…]        – nicht begonnene Pakete direkt oder über mehrere Stufen dahinter (auch hinter fertigen),
     "laeuft_schon": [A…]  – davon die schon begonnenen; sie laufen zu Ende,
     "weiter": n}          – Zahl der übrigen offenen Pakete des Projekts (auch nach_aufgabe selbst, solange es offen ist).

    Fertige (auch gemergte p-Pakete) und verworfene zählen nirgends mit."""
    a = con.execute("SELECT id FROM aufgabe WHERE id = ? AND projekt_id = ?", (nach_aufgabe, pid)).fetchone()
    if not a:
        raise kern.AmwFehler(f"A{nach_aufgabe} gibt es nicht")
    start = a["id"]
    aus = {"wartet": [], "laeuft_schon": [], "weiter": 0}
    for x in kern.aufgaben(con, pid):                     # offene, nach Rang und Nummer
        gruppe = konzeptaenderung.einteilen(con, x)
        if gruppe not in ("stoppen", "zu_ende"):
            continue
        if x["id"] == start or not planung._erreichbar(con, start, x["id"]):     # im Kreis wartet ein Paket nicht auf sich selbst
            aus["weiter"] += 1
        else:
            aus["wartet" if gruppe == "stoppen" else "laeuft_schon"].append(x["id"])
    return aus


# --- Prüfpunkt einfügen (A2096, TH164 „Eingriffe“) ---------------------------------------------------------------------------
#
# Ein Prüfpunkt ist EIN Paket „Stand packen – <Name> testet“ mit der Fertig-Quelle „ja“ (A1938): der Packer meldet es bereit, unter
# „Für dich“ sagt der Mensch ja oder „zurück“ (urteil). Bis zum Ja bleibt es offen – die Pakete dahinter warten über ganz normale
# Abhängigkeiten, alles andere läuft weiter. Kein Schema: das Ereignis pruefpunkt merkt sich hinter welchem Paket, wer, warum und genau
# die Kanten, die das Einfügen gesetzt hat; nur diese nimmt entfernen() wieder weg. Kommen später Nachfolger dazu, hält nachziehen()
# auch sie auf (beim Setzen der Abhängigkeit und je Dienst-Runde); eine von Hand gelöste Kante setzt es nicht noch einmal.

ART, KANTEN, ENDE = "pruefpunkt", "pruefpunkt_kanten", "pruefpunkt_ende"
GRENZE = ("Grenze: nichts nach außen. Kein Push, kein Tag, kein Release, kein Web-Abzug, kein „release ausliefern“ mit diesem Paket."
          " Der Stand bleibt auf diesem Rechner.")


def _json(text):
    try:
        d = json.loads(text or "{}")
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def ist(con, aid):
    """Ist diese Aufgabe ein Prüfpunkt-Paket?"""
    return con.execute("SELECT 1 FROM plan_ereignis WHERE aufgabe_id = ? AND art = ? LIMIT 1", (aid, ART)).fetchone() is not None


def offene(con, pid):
    """Alle offenen Prüfpunkte: [{paket, titel, bogen, nach, von, grund, kanten, zeit_utc}], die ältesten zuerst – je Stand der Datenbank
    nur einmal gelesen (A2081)."""
    from . import einmal
    return einmal.einmal(con, (ART, pid), lambda: _offene(con, pid), kopie=True)


def _offene(con, pid):
    zeilen = con.execute("SELECT e.aufgabe_id, e.art, e.text, e.von, e.zeit_utc, a.titel, a.bogen_id FROM aufgabe a JOIN plan_ereignis e ON e.aufgabe_id = a.id"
                         " AND e.art IN (?, ?) WHERE a.projekt_id = ? AND a.status NOT IN ('fertig', 'verworfen') ORDER BY e.id", (ART, KANTEN, pid)).fetchall()
    aus = {}
    for r in zeilen:
        d = _json(r["text"])
        if r["art"] == ART:
            aus[r["aufgabe_id"]] = {"paket": r["aufgabe_id"], "titel": r["titel"], "bogen": r["bogen_id"], "nach": d.get("nach"), "von": r["von"],
                                    "grund": d.get("grund"), "kanten": [tuple(k) for k in d.get("kanten") or []], "zeit_utc": r["zeit_utc"]}
        elif r["aufgabe_id"] in aus:
            aus[r["aufgabe_id"]]["kanten"] += [tuple(k) for k in d.get("kanten") or []]
    return list(aus.values())


def zustand(con, aid):
    """„packt“ | „wartet_mensch“ (bereit gemeldet, der Mensch testet) | „zurueck“ (mit Notiz zurück, wird nachgebessert)."""
    from . import urteil
    a = con.execute("SELECT * FROM aufgabe WHERE id = ?", (aid,)).fetchone()
    if urteil.fakt(con, a):
        return "wartet_mensch"
    return "zurueck" if urteil._letztes(con, aid, urteil.ZURUECK) else "packt"


def dahinter(con, pid):
    """{aid: Prüfpunkt-Paket} – alle offenen Pakete, die (auch über mehrere Stufen) hinter einem offenen Prüfpunkt stehen."""
    pp = offene(con, pid)
    if not pp:
        return {}
    aus = {}
    for x in kern.aufgaben(con, pid):
        p = next((p for p in pp if p["paket"] != x["id"] and planung._erreichbar(con, p["paket"], x["id"])), None)
        if p:
            aus[x["id"]] = p["paket"]
    return aus


def uebersicht(con, pid):
    """Für die Startdaten: [{paket, titel, bogen, nach, von, grund, zustand, wartet}] je offenem Prüfpunkt."""
    d = dahinter(con, pid)
    return [{**{k: p[k] for k in ("paket", "titel", "bogen", "nach", "von", "grund", "zeit_utc")}, "zustand": zustand(con, p["paket"]),
             "wartet": sorted(a for a, x in d.items() if x == p["paket"])} for p in offene(con, pid)]


def _vorderste(con, nach, paket, wartet):
    """Die Pakete aus wartet, vor denen der Prüfpunkt stehen muss: ihr Vorgänger ist nach oder etwas auf dem Weg, das selbst nicht wartet.
    Alle weiteren warten dann von selbst. Was vor dem Packen gebaut werden soll (Nacharbeit), zählt nicht."""
    menge, aus = set(wartet), []
    for x in wartet:
        if x == paket or planung._erreichbar(con, x, paket):
            continue
        for v in planung.vorgaenger(con, x):
            if v == nach or (v not in menge and v != paket and planung._erreichbar(con, nach, v)):
                aus.append(x)
                break
    return aus


def _kanten_setzen(con, paare):
    """In der Transaktion des Aufrufers: nur Kanten, die es noch nicht gibt – von Hand gesetzte gehören uns nicht. Rückgabe: die neuen."""
    neu = []
    for v, n in paare:
        if not con.execute("SELECT 1 FROM abhaengigkeit WHERE vor = ? AND nach = ?", (v, n)).fetchone():
            con.execute("INSERT INTO abhaengigkeit (vor, nach, art) VALUES (?, ?, 'FS')", (v, n))
            neu.append((v, n))
    return neu


def auftrag(con, pid, titel, hinweis=None):
    """Der Auftrag des Pakets: was „Stand packen“ in diesem Projekt heißt (Projekt-Einstellung packen_befehl, sonst allgemein)."""
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    befehl = str(_json(r[0] if r else None).get("packen_befehl") or "").strip()
    name = kern.entwickler_name(con, pid)
    return (f"Prüfpunkt hinter „{titel}“: den Stand packen, {name} testet ihn. Bis zum Ja warten die Pakete dahinter.\n"
            + (f"Packen (Projekt-Einstellung packen_befehl), über die Lauf-Schlange: {befehl}\n" if befehl else
               "Packen: den jetzigen Stand so bauen, dass man ihn starten und ansehen kann, nach den Regeln des Projekts (Version bzw. Build,"
               " Tests grün auf genau dem Stand).\n")
            + "Dann ein Dokument ablegen (amw dokument ablegen … --art ergebnis --aufgabe <diese>): wo der Stand liegt, wie man ihn startet, was neu ist,"
              " was zu testen ist. Mit dem Dokument steht er unter „Für dich“.\n" + GRENZE + (f"\nHinweis: {hinweis}" if hinweis else ""))


def _prognose(con, pid):
    return {b: x["p50"] for b, x in planung.prognose(con, pid, laeufe=300)["boegen"].items()}


def _recht(con, pid, von, grund, was):
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler(f"{was} der Mensch oder der Lead")
    grund = " ".join((grund or "").split())[:300]
    if not grund and von != kern.ENTWICKLER:
        raise kern.AmwFehler(f"{was}: der Lead nur mit Grund (--grund …)")
    return grund


def einfuegen(con, pid, von, nach, agent=None, grund=None, hinweis=None):
    """Einen Prüfpunkt hinter das Paket nach setzen (Mensch, oder der Lead mit Grund). Rückgabe: {"paket", "nach", "wartet", "laeuft_schon",
    "weiter", "kanten", "fehlt", "vorher", "nachher"} – vorher/nachher: Prognose je Meilenstein."""
    from . import fertigquelle, reihenfolge, themen
    grund = _recht(con, pid, von, grund, "Einen Prüfpunkt setzen")
    a = con.execute("SELECT a.*, b.status AS b_status, b.nr AS b_nr FROM aufgabe a LEFT JOIN bogen b ON b.id = a.bogen_id WHERE a.id = ? AND a.projekt_id = ?",
                    (nach, pid)).fetchone()
    if not a:
        raise kern.AmwFehler(f"A{nach} gibt es nicht")
    if a["status"] == "verworfen" or a["bogen_id"] is None or a["b_status"] not in ("geplant", "aktiv"):
        raise kern.AmwFehler(f"A{nach}: ein Prüfpunkt steht hinter einem Paket eines geplanten oder laufenden Meilensteins")
    if ist(con, nach):
        raise kern.AmwFehler(f"A{nach} ist selbst ein Prüfpunkt")
    if any(p["nach"] == nach for p in offene(con, pid)):
        raise kern.AmwFehler(f"Hinter A{nach} steht schon ein Prüfpunkt")
    w = wartende(con, pid, nach)
    if not w["wartet"]:
        raise kern.AmwFehler(f"Hinter A{nach} wartet kein Paket – ein Prüfpunkt hielte nichts auf. Am Ende des Meilensteins testest du bei der Abnahme.")
    name = kern.entwickler_name(con, pid)
    vorher = _prognose(con, pid)
    aid = planung.schritt_setzen(con, pid, von, titel=f"Stand packen – {name} testet"[:120], auftrag=auftrag(con, pid, a["titel"], hinweis), bogen_id=a["bogen_id"],
                                 agent=agent, groesse="S", art="mechanisch", rang=a["rang"])
    fertigquelle.setzen(con, pid, von, aid, "ja")
    th = themen.verweise(con, pid, nach)
    if th:
        themen.verweise_setzen(con, pid, von, aid, th)
    with db.schreiben(con):
        # in der Transaktion noch einmal: es kann sich geändert haben
        w = wartende(con, pid, nach)
        paare = ([] if a["status"] == "fertig" else [(nach, aid)]) + [(aid, x) for x in _vorderste(con, nach, aid, w["wartet"])]
        kanten = _kanten_setzen(con, paare)
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=ART, aufgabe_id=aid, bogen_id=a["bogen_id"],
                     text=json.dumps({"nach": nach, "grund": grund or None, "kanten": kanten, "wartet": len(w["wartet"])}, ensure_ascii=False))
        lead = kern.lead(con, pid)
        if lead and lead != von:
            kern._posten(con, pid, von, lead, "info", f"M{a['b_nr']}: Prüfpunkt hinter A{nach} – A{aid}, {len(w['wartet'])} Pakete warten"[:140],
                         f"Hinter „{a['titel']}“ packt A{aid} den Stand, {name} testet ihn. Bis zum Ja warten: " + ", ".join(f"A{x}" for x in w["wartet"]) + "."
                         + (f" Grund: {grund}." if grund else "") + " Reihenfolge, Zeitplan und Prognose sind neu gerechnet, der Plan-Stand bleibt.", aufgabe_id=aid)
    fehlt = reihenfolge.neue_startklar(con, pid, von, a["bogen_id"], [aid]) if a["b_status"] == "aktiv" else {}
    return {"paket": aid, "nach": nach, "wartet": w["wartet"], "laeuft_schon": w["laeuft_schon"], "weiter": w["weiter"], "kanten": [list(k) for k in kanten],
            "fehlt": fehlt.get(aid) or [], "vorher": vorher, "nachher": _prognose(con, pid), "wartet_auf": name}


def entfernen(con, pid, von, aid, grund=None):
    """Den Prüfpunkt wegnehmen, bevor der Mensch ja gesagt hat: der Mensch immer, der Lead nur einen eigenen (mit Grund). Weg kommen genau die
    Kanten, die er gesetzt hat; das Paket wird verworfen."""
    grund = _recht(con, pid, von, grund, "Einen Prüfpunkt entfernen")
    p = next((p for p in offene(con, pid) if p["paket"] == aid), None)
    if not p:
        raise kern.AmwFehler(f"A{aid} ist kein offener Prüfpunkt")
    if von != kern.ENTWICKLER and p["von"] != von:
        wer = kern.entwickler_name(con, pid) if p["von"] == kern.ENTWICKLER else p["von"]
        raise kern.AmwFehler(f"A{aid}: den Prüfpunkt hat {wer} gesetzt – entfernen kann ihn nur {kern.entwickler_name(con, pid)}")
    vorher = _prognose(con, pid)
    with db.schreiben(con):
        for v, n in p["kanten"]:
            con.execute("DELETE FROM abhaengigkeit WHERE vor = ? AND nach = ?", (v, n))
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=ENDE, aufgabe_id=aid, bogen_id=p["bogen"],
                     text=json.dumps({"art": "entfernt", "nach": p["nach"], "grund": grund or None}, ensure_ascii=False))
        lead = kern.lead(con, pid)
        if lead and lead != von:
            kern._posten(con, pid, von, lead, "info", f"Prüfpunkt A{aid} entfernt – die Pakete dahinter laufen weiter", grund or None, aufgabe_id=aid)
    kern.aufgabe_status(con, pid, "AMW", aid, "verwerfen", beleg=f"Prüfpunkt entfernt von {von}", zusammenfassung="Prüfpunkt entfernt", automatik="pruefpunkt")
    return {"paket": aid, "nach": p["nach"], "kanten": [list(k) for k in p["kanten"]], "vorher": vorher, "nachher": _prognose(con, pid)}


def nacharbeit(con, pid, paket, vor_liste):
    """Ein Paket, das bisher hinter dem Prüfpunkt wartete, soll jetzt davor gebaut werden (Nacharbeit nach „Zurück“): die Kante, die der
    Prüfpunkt selbst dorthin gesetzt hat, kommt weg – eine von Hand gesetzte nicht (dann ist es ein Kreis und wird abgewiesen)."""
    p = next((p for p in offene(con, pid) if p["paket"] == paket), None)
    if not p:
        return
    for v in vor_liste:
        if (paket, v) in p["kanten"]:
            with db.schreiben(con):
                con.execute("DELETE FROM abhaengigkeit WHERE vor = ? AND nach = ?", (paket, v))


def nachziehen(con, pid):
    """Später dazugekommene Nachfolger warten auch (neues Paket, neue Abhängigkeit). Aus planung.abhaengigkeit_setzen und je Dienst-Runde.
    Eine Kante, die der Prüfpunkt schon einmal gesetzt hatte und die jemand gelöst hat, kommt nicht wieder. Rückgabe: Texte fürs Protokoll."""
    aus = []
    for p in offene(con, pid):
        if not p["nach"] or not con.execute("SELECT 1 FROM aufgabe WHERE id = ? AND status != 'verworfen'", (p["nach"],)).fetchone():
            continue
        wartet = [x for x in wartende(con, pid, p["nach"])["wartet"] if x != p["paket"] and not planung._erreichbar(con, p["paket"], x)]
        paare = [(p["paket"], x) for x in _vorderste(con, p["nach"], p["paket"], wartet) if (p["paket"], x) not in p["kanten"]]
        if not paare:
            continue
        with db.schreiben(con):
            neu = _kanten_setzen(con, paare)
            if neu:
                db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=KANTEN, aufgabe_id=p["paket"], bogen_id=p["bogen"],
                             text=json.dumps({"kanten": neu}, ensure_ascii=False))
                aus.append(f"Prüfpunkt A{p['paket']}: " + ", ".join(f"A{n}" for _, n in neu) + " wartet jetzt auch")
    return aus


def sperre(con, pid, aid, neu):
    """Aus kern.aufgabe_status: ein Prüfpunkt-Paket setzt niemand sonst auf fertig oder verworfen, auch die Auslieferung nicht – sonst wäre er
    ohne Ja weg."""
    if neu in ("fertig", "verworfen") and ist(con, aid):
        name = kern.entwickler_name(con, pid)
        raise kern.AmwFehler(f"A{aid} ist ein Prüfpunkt: fertig wird er nur mit dem Ja von {name} („Für dich“)" if neu == "fertig" else
                             f"A{aid} ist ein Prüfpunkt: wegnehmen mit amw aufgabe pruefpunkt {aid} --entfernen")
