"""Projektplanung (Stufe E, → doc/ausbau.md §6, Methode: doc/recherche/planung.md).

Leitbild (Ziel, Kennzahlen, Nicht-Ziele, Prinzipien mit Prüffrage, Definition of Done) → Bögen (Meilensteine mit
prüfbarem Abnahmekriterium, Zieldatum, Baseline) → Spezifikation je Bogen in drei Teilen mit Freigabe durch den
Menschen (`[KLÄREN: …]` wird zur Frage und blockiert die Freigabe) → Schritte (Aufgaben mit Bogen, Kriterien,
Abhängigkeiten, Schätzung, Komplexität, Plan) → nächster Schritt, Plan-Gate, Abnahme → Prognose (Monte Carlo aus dem
Durchsatz) und Plan-Check. Alles, was eine Freigabe oder Entscheidung ist, landet in plan_ereignis.
Regeln für „fertig“ gelten nur für Schritte in einem Bogen – bestehende Abläufe ohne Bogen bleiben wie sie sind.
"""
import datetime
import json
import random
import re

from . import db, kern

TEILE = ("anforderungen", "entwurf", "schritte")
KLAEREN = re.compile(r"\[KL(?:Ä|AE)REN:\s*([^\]]+)\]", re.IGNORECASE)
ANFORDERUNG = re.compile(r"\b(R\d{1,3})\b")
PLAN_AB_KOMPLEXITAET = 7
STRATEGIEN = ("vermeiden", "mindern", "uebertragen", "akzeptieren")
MENSCH = kern.ENTWICKLER


def _lead(con, pid, von, was):
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler(f"{was} dürfen nur Lead und Entwickler")


def _log(con, pid, von, art, text, bogen_id=None, aufgabe_id=None):
    db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=art, text=text,
                 bogen_id=bogen_id, aufgabe_id=aufgabe_id)


def _json(x, vorgabe):
    try:
        return json.loads(x) if x else vorgabe
    except ValueError:
        return vorgabe


def _datum(v):
    if v in (None, ""):
        return None
    try:
        return datetime.date.fromisoformat(str(v).strip()).isoformat()
    except ValueError:
        raise kern.AmwFehler("Datum als JJJJ-MM-TT") from None


# --- Leitbild ------------------------------------------------------------------------------------

def leitbild(con, pid):
    p = con.execute("SELECT leitbild, dod FROM projekt WHERE id = ?", (pid,)).fetchone()
    lb = {"ziel": "", "kennzahlen": [], "nicht_ziele": [], "prinzipien": [], **_json(p["leitbild"], {})}
    return {**lb, "dod": _json(p["dod"], [])}


def leitbild_setzen(con, pid, von, ziel=None, kennzahlen=None, nicht_ziele=None, prinzipien=None, dod=None):
    """Listen ersetzen die bisherigen (None = unverändert). prinzipien: [{"text", "pruefung"}] oder ["Text|Prüffrage"]."""
    _lead(con, pid, von, "Das Leitbild ändern")
    lb = leitbild(con, pid)
    alt_dod = lb.pop("dod")
    if ziel is not None:
        lb["ziel"] = ziel.strip()
    if kennzahlen is not None:
        lb["kennzahlen"] = [k.strip() for k in kennzahlen if k.strip()]
    if nicht_ziele is not None:
        lb["nicht_ziele"] = [k.strip() for k in nicht_ziele if k.strip()]
    if prinzipien is not None:
        lb["prinzipien"] = [p if isinstance(p, dict) else dict(zip(("text", "pruefung"), (p.split("|", 1) + [""])[:2]))
                            for p in prinzipien if (p.get("text") if isinstance(p, dict) else p.strip())]
    neu_dod = alt_dod if dod is None else [d.strip() for d in dod if d.strip()]
    with db.schreiben(con):
        con.execute("UPDATE projekt SET leitbild = ?, dod = ? WHERE id = ?",
                    (json.dumps(lb, ensure_ascii=False), json.dumps(neu_dod, ensure_ascii=False), pid))
        _log(con, pid, von, "leitbild", "Leitbild/DoD geändert")
    return leitbild(con, pid)


# --- Bögen ---------------------------------------------------------------------------------------

def bogen_zeile(con, pid, bid):
    b = con.execute("SELECT * FROM bogen WHERE id = ? AND projekt_id = ?", (bid, pid)).fetchone()
    if not b:
        raise kern.AmwFehler(f"Bogen {bid} gibt es nicht")
    return b


def bogen_neu(con, pid, von, titel, ziel=None, abnahme=None, zieldatum=None, nr=None):
    _lead(con, pid, von, "Bögen anlegen")
    if not (titel or "").strip():
        raise kern.AmwFehler("Titel fehlt")
    with db.schreiben(con):
        if nr is None:
            nr = (con.execute("SELECT max(nr) FROM bogen WHERE projekt_id = ?", (pid,)).fetchone()[0] or 0) + 1
        bid = db.einfuegen(con, "bogen", projekt_id=pid, nr=int(nr), titel=titel.strip(), ziel=ziel, abnahme=abnahme,
                           zieldatum=_datum(zieldatum), angelegt_von=von, angelegt_utc=db.jetzt())
        for t in TEILE:
            db.einfuegen(con, "spezifikation", bogen_id=bid, teil=t)
        _log(con, pid, von, "bogen_neu", titel.strip(), bogen_id=bid)
    return bid


def bogen_aendern(con, pid, von, bid, titel=None, ziel=None, abnahme=None, zieldatum=None, nr=None, grund=None):
    """Zieldatum eines aktiven Bogens mit Baseline ändern = Änderungssteuerung: nur mit Grund, wird protokolliert."""
    _lead(con, pid, von, "Bögen ändern")
    b = bogen_zeile(con, pid, bid)
    felder = {k: v for k, v in (("titel", titel), ("ziel", ziel), ("abnahme", abnahme), ("nr", nr)) if v is not None}
    if zieldatum is not None:
        neu = _datum(zieldatum)
        if b["baseline_datum"] and neu != b["zieldatum"] and not (grund or "").strip():
            raise kern.AmwFehler(f"Bogen {bid} hat eine Baseline ({b['baseline_datum']}) – neues Zieldatum nur mit --grund")
        felder["zieldatum"] = neu
    if not felder:
        return b
    with db.schreiben(con):
        con.execute(f"UPDATE bogen SET {', '.join(k + ' = ?' for k in felder)}, geaendert_utc = ? WHERE id = ?",
                    (*felder.values(), db.jetzt(), bid))       # Spaltennamen nur aus der festen Liste oben
        if "zieldatum" in felder and b["baseline_datum"]:
            con.execute("UPDATE bogen SET baseline_grund = ? WHERE id = ?", (grund, bid))
            _log(con, pid, von, "baseline", f"Zieldatum {b['zieldatum']} → {felder['zieldatum']}: {grund}", bogen_id=bid)
        else:
            _log(con, pid, von, "bogen_aendern", ", ".join(felder), bogen_id=bid)
    return bogen_zeile(con, pid, bid)


def bogen_status(con, pid, von, bid, status, erzwingen=False):
    _lead(con, pid, von, "Den Bogen-Status setzen")
    if status not in ("geplant", "aktiv", "fertig", "verworfen"):
        raise kern.AmwFehler("Status: geplant | aktiv | fertig | verworfen")
    b = bogen_zeile(con, pid, bid)
    if status == "fertig" and not erzwingen:
        offen = con.execute("SELECT count(*) FROM aufgabe WHERE bogen_id = ? AND status NOT IN ('fertig', 'verworfen')",
                            (bid,)).fetchone()[0]
        if offen:
            raise kern.AmwFehler(f"Bogen {bid} hat noch {offen} offene Schritte – erst abschließen (oder --erzwingen)")
    with db.schreiben(con):
        felder = {"status": status, "geaendert_utc": db.jetzt()}
        if status == "aktiv" and not b["baseline_datum"] and b["zieldatum"]:
            felder["baseline_datum"] = b["zieldatum"]           # Baseline einfrieren
        if status == "fertig":
            felder["fertig_utc"] = db.jetzt()
        con.execute(f"UPDATE bogen SET {', '.join(k + ' = ?' for k in felder)} WHERE id = ?", (*felder.values(), bid))
        _log(con, pid, von, "bogen_status", f"{b['status']} → {status}", bogen_id=bid)


def boegen(con, pid):
    aus = []
    for b in con.execute("SELECT * FROM bogen WHERE projekt_id = ? ORDER BY nr, id", (pid,)).fetchall():
        z = con.execute("SELECT count(*) AS gesamt, sum(status = 'fertig') AS fertig, sum(status = 'verworfen') AS verworfen,"
                        " sum(status = 'laeuft') AS laeuft FROM aufgabe WHERE bogen_id = ?", (b["id"],)).fetchone()
        spec = {s["teil"]: s["status"] for s in con.execute("SELECT teil, status FROM spezifikation WHERE bogen_id = ?", (b["id"],))}
        blockiert = sum(1 for (aid,) in con.execute("SELECT id FROM aufgabe WHERE bogen_id = ? AND status NOT IN ('fertig', 'verworfen')",
                                                    (b["id"],)).fetchall() if offene_vorgaenger(con, aid))
        aus.append({**dict(b), "gesamt": z["gesamt"] or 0, "fertig": z["fertig"] or 0, "verworfen": z["verworfen"] or 0,
                    "laeuft": z["laeuft"] or 0, "blockiert": blockiert, "spec": spec})
    return aus


# --- Spezifikation -------------------------------------------------------------------------------

def spec(con, bid, teil):
    s = con.execute("SELECT * FROM spezifikation WHERE bogen_id = ? AND teil = ?", (bid, teil)).fetchone()
    if not s:
        raise kern.AmwFehler(f"Teil {teil} gibt es nicht (anforderungen | entwurf | schritte)")
    return s


def spec_schreiben(con, pid, von, bid, teil, text):
    """Neuer Text. War der Teil schon freigegeben oder vorgelegt, beginnt eine neue Version (muss neu vorgelegt werden)."""
    bogen_zeile(con, pid, bid)
    s = spec(con, bid, teil)
    with db.schreiben(con):
        version = s["version"] + (1 if s["status"] in ("frei", "vorgelegt") else 0)
        con.execute("UPDATE spezifikation SET text = ?, status = 'entwurf', version = ?, geschrieben_von = ?, geaendert_utc = ?"
                    " WHERE id = ?", (text, version, von, db.jetzt(), s["id"]))
        _log(con, pid, von, "spec_geschrieben", f"{teil} v{version}", bogen_id=bid)
    return version


def _offene_klaerungen(con, pid, bid, teil):
    return con.execute("SELECT id, kurz FROM frage WHERE projekt_id = ? AND fundstellen = ? AND status = 'offen'",
                       (pid, f"bogen:{bid}:{teil}")).fetchall()


def spec_vorlegen(con, pid, von, bid, teil):
    """Zur Freigabe vorlegen. Reihenfolge wie Spec Kit: Entwurf erst nach freigegebenen Anforderungen, Schritte erst
    nach freigegebenem Entwurf. Jede Stelle [KLÄREN: …] wird eine Frage an den Entwickler (blockiert die Freigabe)."""
    b = bogen_zeile(con, pid, bid)
    s = spec(con, bid, teil)
    if not s["text"].strip():
        raise kern.AmwFehler(f"{teil} ist leer")
    vorher = TEILE[TEILE.index(teil) - 1] if teil != TEILE[0] else None
    if vorher and spec(con, bid, vorher)["status"] != "frei":
        raise kern.AmwFehler(f"erst „{vorher}“ freigeben lassen")
    fragen = []
    for punkt in KLAEREN.findall(s["text"]):
        if not con.execute("SELECT 1 FROM frage WHERE projekt_id = ? AND fundstellen = ? AND kurz = ?",
                           (pid, f"bogen:{bid}:{teil}", punkt.strip()[:300])).fetchone():
            fragen.append(kern.frage_neu(con, pid, von, "entwickler", punkt.strip()[:300],
                                         [("A", "beantworten (Text)")], "A", f"Klärung für Bogen {bid} „{b['titel']}“, Teil {teil}",
                                         worum=f"Spezifikation Bogen {bid} ({teil}) enthält: [KLÄREN: {punkt.strip()}]",
                                         fundstellen=f"bogen:{bid}:{teil}", blockiert=True,
                                         geprueft=f"von der AMW gestellt (KLÄREN in Bogen {bid})", pruefen=False))
    with db.schreiben(con):
        con.execute("UPDATE spezifikation SET status = 'vorgelegt', geaendert_utc = ? WHERE id = ?", (db.jetzt(), s["id"]))
        _log(con, pid, von, "spec_vorgelegt", f"{teil} v{s['version']}" + (f", {len(fragen)} Klärung(en)" if fragen else ""),
             bogen_id=bid)
    return fragen


def spec_entscheiden(con, pid, von, bid, teil, frei, kommentar=None):
    """Nur der Mensch gibt frei (Gate). Offene Klärungen blockieren die Freigabe. Der Verfasser wird benachrichtigt."""
    if von != MENSCH:
        raise kern.AmwFehler("Spezifikationen gibt nur der Entwickler frei")
    b = bogen_zeile(con, pid, bid)
    s = spec(con, bid, teil)
    if s["status"] != "vorgelegt":
        raise kern.AmwFehler(f"{teil} ist nicht vorgelegt (Status {s['status']})")
    if frei and _offene_klaerungen(con, pid, bid, teil):
        raise kern.AmwFehler("erst die offenen Klärungsfragen beantworten: "
                             + ", ".join(f"F{f['id']}" for f in _offene_klaerungen(con, pid, bid, teil)))
    if not frei and not (kommentar or "").strip():
        raise kern.AmwFehler("Zurück nur mit Kommentar, was zu ändern ist")
    with db.schreiben(con):
        con.execute("UPDATE spezifikation SET status = ?, kommentar = ?, freigabe_utc = ?, geaendert_utc = ? WHERE id = ?",
                    ("frei" if frei else "zurueck", kommentar, db.jetzt() if frei else None, db.jetzt(), s["id"]))
        _log(con, pid, von, "spec_frei" if frei else "spec_zurueck", f"{teil} v{s['version']}" + (f": {kommentar}" if kommentar else ""),
             bogen_id=bid)
        an = s["geschrieben_von"] or ",".join(r["kennung"] for r in con.execute(
            "SELECT kennung FROM agent WHERE projekt_id = ? AND rolle = 'lead'", (pid,)))
        if an and an != MENSCH:
            kern._posten(con, pid, von, an, "freigabe" if frei else "korrektur",
                         f"Bogen {bid} „{b['titel']}“: {teil} {'FREIGEGEBEN' if frei else 'ZURÜCK'}", kommentar)


# --- Abhängigkeiten ------------------------------------------------------------------------------

def vorgaenger(con, aid):
    return [r[0] for r in con.execute("SELECT vor FROM abhaengigkeit WHERE nach = ? ORDER BY vor", (aid,))]


def offene_vorgaenger(con, aid):
    return [r[0] for r in con.execute("SELECT d.vor FROM abhaengigkeit d JOIN aufgabe a ON a.id = d.vor WHERE d.nach = ?"
                                      " AND d.art = 'FS' AND a.status NOT IN ('fertig', 'verworfen')", (aid,))]


def _erreichbar(con, start, ziel):
    """Kommt man von start über Nachfolger zu ziel? (Zyklusprüfung)"""
    gesehen, stapel = set(), [start]
    while stapel:
        x = stapel.pop()
        if x == ziel:
            return True
        if x in gesehen:
            continue
        gesehen.add(x)
        stapel += [r[0] for r in con.execute("SELECT nach FROM abhaengigkeit WHERE vor = ?", (x,))]
    return False


def abhaengigkeit_setzen(con, pid, von, nach, vor_liste, art="FS", entfernen=False):
    for v in vor_liste:
        for x in (v, nach):
            if not con.execute("SELECT 1 FROM aufgabe WHERE id = ? AND projekt_id = ?", (x, pid)).fetchone():
                raise kern.AmwFehler(f"A{x} gibt es nicht")
        if v == nach or (not entfernen and _erreichbar(con, nach, v)):
            raise kern.AmwFehler(f"A{v} → A{nach} ergäbe einen Kreis")
    with db.schreiben(con):
        for v in vor_liste:
            if entfernen:
                con.execute("DELETE FROM abhaengigkeit WHERE vor = ? AND nach = ?", (v, nach))
            else:
                con.execute("INSERT OR REPLACE INTO abhaengigkeit (vor, nach, art) VALUES (?, ?, ?)", (v, nach, art))


def wellen(con, aids):
    """Schritte in Wellen: Welle 1 hat keine offenen Vorgänger in der Menge, Welle n hängt nur an Wellen < n."""
    menge, stufe = set(aids), {}
    def tiefe(a, pfad=()):
        if a in stufe:
            return stufe[a]
        vor = [v for v in vorgaenger(con, a) if v in menge and v not in pfad]
        stufe[a] = 1 + max((tiefe(v, pfad + (a,)) for v in vor), default=0)
        return stufe[a]
    for a in aids:
        tiefe(a)
    return stufe


# --- Schritte (Aufgaben erweitert) ---------------------------------------------------------------

FELDER = ("bogen_id", "kriterien", "schaetzung_h", "komplexitaet", "verantwortlich", "pruefbefehl", "dateibereich",
          "anforderungen", "auftrag", "rang", "titel", "agent", "pruefer", "zusammenfassung")


def _bearbeiter(con, pid, x):
    return kern.bearbeiter(con, pid, x)


def schritt_setzen(con, pid, von, aid=None, titel=None, nach=None, **werte):
    """Neu (aid=None) oder ändern. kriterien: Liste von Texten (neu) – erfüllt-Stand bleibt bei gleichem Text erhalten."""
    if aid is None and werte.get("bogen_id"):
        _lead(con, pid, von, "Schritte in einem Bogen planen")
    if "agent" in werte:
        werte["agent"] = _bearbeiter(con, pid, werte["agent"])
    if werte.get("bogen_id") is not None:
        bogen_zeile(con, pid, werte["bogen_id"])
    if werte.get("komplexitaet") is not None and not 1 <= int(werte["komplexitaet"]) <= 10:
        raise kern.AmwFehler("Komplexität 1–10")
    for v in nach or []:                            # erst prüfen, dann anlegen – kein halber Schritt
        if not con.execute("SELECT 1 FROM aufgabe WHERE id = ? AND projekt_id = ?", (v, pid)).fetchone():
            raise kern.AmwFehler(f"A{v} gibt es nicht (Vorgänger)")
    if aid is None:
        if not (titel or "").strip():
            raise kern.AmwFehler("Titel fehlt")
        with db.schreiben(con):
            aid = db.einfuegen(con, "aufgabe", projekt_id=pid, titel=titel.strip(), angelegt_von=von, angelegt_utc=db.jetzt(),
                               rang=werte.pop("rang", None) or 50)
    alt = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    if not alt:
        raise kern.AmwFehler(f"A{aid} gibt es nicht")
    if titel and titel.strip() != alt["titel"]:
        werte["titel"] = titel.strip()
    if werte.get("kriterien") is not None:
        bisher = {k["text"]: k.get("erfuellt", False) for k in _json(alt["kriterien"], [])}
        werte["kriterien"] = json.dumps([{"text": k, "erfuellt": bisher.get(k, False)} for k in werte["kriterien"] if k.strip()],
                                        ensure_ascii=False)
    satz = {k: v for k, v in werte.items() if k in FELDER and v is not None}
    if satz:
        with db.schreiben(con):
            con.execute(f"UPDATE aufgabe SET {', '.join(k + ' = ?' for k in satz)}, geaendert_utc = ? WHERE id = ?",
                        (*satz.values(), db.jetzt(), aid))      # Spaltennamen nur aus FELDER
    if nach:
        abhaengigkeit_setzen(con, pid, von, aid, nach)
    return aid


def kriterium(con, pid, von, aid, nr, erfuellt=True):
    a = kern._aufgabe_fuer_aenderung(con, pid, von, aid)
    liste = _json(a["kriterien"], [])
    if not 1 <= nr <= len(liste):
        raise kern.AmwFehler(f"A{aid} hat {len(liste)} Kriterien")
    liste[nr - 1]["erfuellt"] = bool(erfuellt)
    with db.schreiben(con):
        con.execute("UPDATE aufgabe SET kriterien = ?, geaendert_utc = ? WHERE id = ?",
                    (json.dumps(liste, ensure_ascii=False), db.jetzt(), aid))
    return liste


def plan_vorlegen(con, pid, von, aid, text):
    a = kern._aufgabe_fuer_aenderung(con, pid, von, aid)
    if not (text or "").strip():
        raise kern.AmwFehler("Plan ist leer")
    with db.schreiben(con):
        con.execute("UPDATE aufgabe SET plan = ?, plan_status = 'vorgelegt', geaendert_utc = ? WHERE id = ?", (text, db.jetzt(), aid))
        _log(con, pid, von, "plan_vorgelegt", a["titel"], bogen_id=a["bogen_id"], aufgabe_id=aid)
        an = a["verantwortlich"] or ",".join(r["kennung"] for r in con.execute(
            "SELECT kennung FROM agent WHERE projekt_id = ? AND rolle = 'lead'", (pid,)))
        if an and an != von:
            kern._posten(con, pid, von, an, "frage", f"Plan für A{aid} zur Freigabe: {a['titel'][:100]}", text, aufgabe_id=aid)


def plan_entscheiden(con, pid, von, aid, frei, kommentar=None):
    _lead(con, pid, von, "Pläne freigeben")
    a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    if not a or a["plan_status"] != "vorgelegt":
        raise kern.AmwFehler(f"A{aid}: kein Plan vorgelegt")
    if not frei and not (kommentar or "").strip():
        raise kern.AmwFehler("Zurück nur mit Kommentar")
    with db.schreiben(con):
        con.execute("UPDATE aufgabe SET plan_status = ?, geaendert_utc = ? WHERE id = ?", ("frei" if frei else "zurueck", db.jetzt(), aid))
        _log(con, pid, von, "plan_frei" if frei else "plan_zurueck", kommentar or a["titel"], bogen_id=a["bogen_id"], aufgabe_id=aid)
        if a["agent"] and a["agent"] != von and a["agent"] != MENSCH:
            kern._posten(con, pid, von, a["agent"], "freigabe" if frei else "korrektur",
                         f"Plan A{aid} {'FREIGEGEBEN – umsetzen' if frei else 'ZURÜCK'}", kommentar, aufgabe_id=aid)


def pruefe_status(con, a, neu, zusammenfassung=None):
    """Regeln für Bogen-Schritte (von kern.aufgabe_status aufgerufen). Wirft AmwFehler mit dem Grund. Aufgaben ohne Bogen
    bleiben frei – auch die aus alten Textangaben übernommenen Abhängigkeiten sperren sie nicht."""
    if not a["bogen_id"]:
        return
    if neu == "laeuft":
        offen = offene_vorgaenger(con, a["id"])
        if offen:
            raise kern.AmwFehler(f"A{a['id']} wartet auf " + ", ".join(f"A{x}" for x in offen) + " (Abhängigkeit)")
        if (a["komplexitaet"] or 0) >= PLAN_AB_KOMPLEXITAET and a["plan_status"] != "frei":
            raise kern.AmwFehler(f"A{a['id']} hat Komplexität {a['komplexitaet']} – erst Plan vorlegen und freigeben lassen"
                                 f" (amw aufgabe plan {a['id']} --text …)")
    if neu == "fertig":
        offen = [k["text"] for k in _json(a["kriterien"], []) if not k.get("erfuellt")]
        if offen:
            raise kern.AmwFehler(f"A{a['id']}: Kriterien nicht erfüllt: " + " | ".join(offen[:5])
                                 + f" (amw aufgabe kriterium {a['id']} <nr>)")
        if not (zusammenfassung or a["zusammenfassung"] or "").strip():
            raise kern.AmwFehler(f"A{a['id']}: Bogen-Schritte brauchen beim Abschluss --zusammenfassung")


def naechster(con, pid, von, nehmen=False):
    """Nächster bereiter Schritt für von: eigene oder freie, aktiver Bogen zuerst (nach Bogen-Nr), dann Rang.
    nehmen=True übernimmt ihn in derselben Transaktion (Bearbeiter = von, Status läuft)."""
    if nehmen and kern.halt_gilt(con, pid, von):
        raise kern.AmwFehler("HALT gilt – keine neuen Schritte")
    with db.schreiben(con) if nehmen else _nichts():
        for a in con.execute(
                "SELECT a.* FROM aufgabe a LEFT JOIN bogen b ON b.id = a.bogen_id WHERE a.projekt_id = ? AND a.status = 'wartet'"
                " AND a.einstufung IN ('aktiv', 'keine_prio') AND (a.agent = ? OR a.agent IS NULL OR a.agent = '')"
                " AND (b.id IS NULL OR b.status = 'aktiv')"
                " ORDER BY (b.id IS NULL), b.nr, (a.agent IS NULL), a.rang, a.id", (pid, von)).fetchall():
            if offene_vorgaenger(con, a["id"]):
                continue
            if nehmen:
                if (a["komplexitaet"] or 0) >= PLAN_AB_KOMPLEXITAET and a["plan_status"] != "frei":
                    con.execute("UPDATE aufgabe SET agent = ?, geaendert_utc = ? WHERE id = ?", (von, db.jetzt(), a["id"]))
                    return dict(a) | {"agent": von, "hinweis": "Komplexität ≥ 7: erst Plan vorlegen (amw aufgabe plan)"}
                t = db.jetzt()
                con.execute("UPDATE aufgabe SET agent = ?, status = 'laeuft', begonnen_utc = coalesce(begonnen_utc, ?),"
                            " geaendert_utc = ? WHERE id = ? AND status = 'wartet'", (von, t, t, a["id"]))
                _log(con, pid, von, "schritt_genommen", a["titel"], bogen_id=a["bogen_id"], aufgabe_id=a["id"])
                return dict(a) | {"agent": von, "status": "laeuft"}
            return dict(a)
    return None


class _nichts:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


# --- Risiken -------------------------------------------------------------------------------------

def risiko_setzen(con, pid, von, rid=None, **werte):
    if rid is None and not (werte.get("titel") or "").strip():
        raise kern.AmwFehler("Titel fehlt")
    for k in ("wahrscheinlichkeit", "auswirkung"):
        if werte.get(k) is not None and not 1 <= int(werte[k]) <= 5:
            raise kern.AmwFehler(f"{k} 1–5")
    if werte.get("strategie") and werte["strategie"] not in STRATEGIEN:
        raise kern.AmwFehler("Strategie: " + ", ".join(STRATEGIEN))
    if werte.get("status") and werte["status"] not in ("offen", "eingetreten", "erledigt"):
        raise kern.AmwFehler("Status: offen | eingetreten | erledigt")
    erlaubt = ("titel", "ursache", "wirkung", "wahrscheinlichkeit", "auswirkung", "strategie", "massnahme", "verantwortlich",
               "ausloeser", "status", "bogen_id")
    satz = {k: v for k, v in werte.items() if k in erlaubt and v is not None}
    with db.schreiben(con):
        if rid is None:
            rid = db.einfuegen(con, "risiko", projekt_id=pid, angelegt_von=von, angelegt_utc=db.jetzt(), **satz)
            _log(con, pid, von, "risiko_neu", satz.get("titel"), bogen_id=satz.get("bogen_id"))
        elif satz:
            if not con.execute("SELECT 1 FROM risiko WHERE id = ? AND projekt_id = ?", (rid, pid)).fetchone():
                raise kern.AmwFehler(f"Risiko {rid} gibt es nicht")
            con.execute(f"UPDATE risiko SET {', '.join(k + ' = ?' for k in satz)}, geaendert_utc = ? WHERE id = ?",
                        (*satz.values(), db.jetzt(), rid))
            if satz.get("status"):
                _log(con, pid, von, "risiko_status", f"Risiko {rid} → {satz['status']}")
    return rid


def risiken(con, pid):
    return [dict(r) | {"wert": r["wahrscheinlichkeit"] * r["auswirkung"]} for r in con.execute(
        "SELECT * FROM risiko WHERE projekt_id = ? ORDER BY status = 'erledigt', wahrscheinlichkeit * auswirkung DESC, id", (pid,))]


# --- Prognose (Monte Carlo) ----------------------------------------------------------------------

def durchsatz(con, pid, bearbeiter, tage=14, heute=None):
    """Erledigte Schritte je Tag der letzten `tage` Tage einschließlich heute (Liste). Ohne jede Erledigung: einer in der
    ganzen Zeit (sonst stünde die Prognose für immer still)."""
    heute = heute or datetime.date.today()
    ab = (heute - datetime.timedelta(days=tage - 1)).isoformat()
    zaehler = {}
    sql = ("SELECT substr(fertig_utc, 1, 10) AS tag, count(*) AS n FROM aufgabe WHERE projekt_id = ? AND status = 'fertig'"
           " AND fertig_utc >= ?" + (" AND agent = ?" if bearbeiter else "") + " GROUP BY tag")
    for r in con.execute(sql, (pid, ab, bearbeiter) if bearbeiter else (pid, ab)):
        zaehler[r["tag"]] = r["n"]
    liste = [zaehler.get((heute - datetime.timedelta(days=i)).isoformat(), 0) for i in range(tage)]
    return liste if sum(liste) else [0] * (tage - 1) + [1]


def _quantil(werte, q):
    s = sorted(werte)
    return s[min(len(s) - 1, int(q * len(s)))]


def prognose(con, pid, laeufe=1000, heute=None, zufall=None):
    """{"schritte": {aid: {"p50","p85","bearbeiter"}}, "boegen": {bid: {"start","p50","p85","ampel"}}} – Daten als JJJJ-MM-TT;
    start = Median des Tages, an dem der erste offene Schritt des Bogens beginnt (Bearbeiter frei, Vorgänger fertig).
    Je Bearbeiter (Agent, Mensch, „frei“ = Team) eine Warteschlange in Planreihenfolge; je Lauf zieht jeder Tag einen
    zufälligen Tageswert aus seinem Durchsatz; ein Schritt endet nie vor seinen Vorgängern."""
    heute = heute or datetime.date.today()
    zufall = zufall or random.Random(42)
    offen = con.execute(
        "SELECT a.id, a.agent, a.bogen_id FROM aufgabe a LEFT JOIN bogen b ON b.id = a.bogen_id WHERE a.projekt_id = ?"
        " AND a.status IN ('wartet', 'laeuft', 'blockiert') AND a.einstufung IN ('aktiv', 'keine_prio') AND a.bogen_id IS NOT NULL"
        " AND b.status IN ('geplant', 'aktiv') ORDER BY b.status != 'aktiv', b.nr, a.status != 'laeuft', a.rang, a.id", (pid,)).fetchall()
    if not offen:
        return {"schritte": {}, "boegen": {}}
    schlangen = {}
    for a in offen:
        schlangen.setdefault(a["agent"] or "", []).append(a["id"])
    raten = {b: durchsatz(con, pid, b or None, heute=heute) for b in schlangen}
    ids = [a["id"] for a in offen]
    vor = {i: [v for v in vorgaenger(con, i) if v in set(ids)] for i in ids}
    ende = {i: [] for i in ids}
    beginn = {i: [] for i in ids}
    for _ in range(laeufe):
        tag, ab = {}, {}
        for b, schlange in schlangen.items():
            d, rest, frei = 0, list(schlange), 0
            while rest and d < 3650:
                d += 1
                for _ in range(zufall.choice(raten[b])):
                    if rest:
                        x = rest.pop(0)
                        tag[x], ab[x], frei = d, frei, d          # beginnt, wenn der Bearbeiter frei wird
            for x in rest:
                tag[x], ab[x] = 3650, 3650
        for i in ids:                                    # Vorgänger: nie vor ihnen fertig (Reihenfolge der Liste genügt meist)
            for _ in range(2):
                if vor[i]:
                    tag[i] = max(tag[i], max(tag[v] for v in vor[i]) + 1)
                    ab[i] = max(ab[i], max(tag[v] for v in vor[i]))
        for i in ids:
            ende[i].append(tag[i])
            beginn[i].append(ab[i])
    datum = lambda d: (heute + datetime.timedelta(days=d)).isoformat()
    schritte = {i: {"p50": datum(_quantil(ende[i], .5)), "p85": datum(_quantil(ende[i], .85)),
                    "bearbeiter": next(a["agent"] for a in offen if a["id"] == i) or ""} for i in ids}
    boegen_p = {}
    for a in offen:
        boegen_p.setdefault(a["bogen_id"], []).append(a["id"])
    aus_b = {}
    for bid, liste in boegen_p.items():
        laeufe_max = [max(ende[i][k] for i in liste) for k in range(laeufe)]
        p50, p85 = datum(_quantil(laeufe_max, .5)), datum(_quantil(laeufe_max, .85))
        start = datum(_quantil([min(beginn[i][k] for i in liste) for k in range(laeufe)], .5))
        ziel = con.execute("SELECT zieldatum FROM bogen WHERE id = ?", (bid,)).fetchone()[0]
        ampel = None if not ziel else "gruen" if p85 <= ziel else "gelb" if p50 <= ziel else "rot"
        aus_b[bid] = {"start": start, "p50": p50, "p85": p85, "ampel": ampel}
    return {"schritte": schritte, "boegen": aus_b}


# --- Plan-Check (Lückenprüfung) und Status -------------------------------------------------------

# Plan-Check: wie Jira Plans („Warnungen“: Art, Grund, betroffene Einträge) und MS Project („Task Inspector“: Problem,
# Ursache, Abhilfe) – je Befund: was los ist, was es bedeutet, was zu tun ist und wer. Warnungen und Hinweise lassen
# sich mit Begründung bewusst akzeptieren (plan_ereignis check_akzeptiert/check_wieder, letzter Eintrag gilt).
# Je Art: Stufe, wer handelt (lead | du), wohin die Workbench springt, Texte de/en (Titel, Bedeutung, Abhilfe).
CHECKS = {
    "kein_ziel": ("fehler", "du", "leitbild", {
        "de": ("Kein Projektziel im Leitbild",
               "Ohne Ziel gibt es keinen Maßstab: Bögen, Nicht-Ziele und Abnahmen lassen sich nicht dagegen prüfen, Agenten wissen nicht, wofür sie bauen.",
               "Im Leitbild das Ziel in einem prüfbaren Satz eintragen (was ist am Ende anders?)."),
        "en": ("No project goal in the charter",
               "Without a goal there is no yardstick: arcs, non-goals and acceptance can't be checked against it, agents don't know what they build for.",
               "Enter the goal in the charter as one testable sentence (what is different at the end?).")}),
    "keine_nicht_ziele": ("warnung", "du", "leitbild", {
        "de": ("Keine Nicht-Ziele",
               "Agenten bauen gern mehr als verlangt. Nicht-Ziele sind die Grenze, auf die sie und der Lead sich berufen können.",
               "Im Leitbild 2–5 Dinge eintragen, die ausdrücklich nicht gemacht werden."),
        "en": ("No non-goals",
               "Agents tend to build more than asked. Non-goals are the boundary they and the lead can point to.",
               "Add 2–5 things to the charter that are explicitly out of scope.")}),
    "keine_dod": ("warnung", "du", "leitbild", {
        "de": ("Keine Definition of Done",
               "Ohne gemeinsame Definition entscheidet jeder Agent selbst, wann etwas „fertig“ ist – Prüfungen und Abnahmen werden beliebig.",
               "Im Leitbild festlegen, was für jeden Schritt gilt (z. B. Tests grün, geprüft, Zusammenfassung geschrieben)."),
        "en": ("No definition of done",
               "Without a shared definition every agent decides on its own when something is “done” – reviews and acceptance become arbitrary.",
               "Define in the charter what applies to every step (e.g. tests green, reviewed, summary written).")}),
    "keine_boegen": ("hinweis", "lead", "zeitleiste", {
        "de": ("Noch keine Bögen",
               "Ohne Bögen (Etappen) gibt es keine Prognose, keine Zeitleiste und keinen Rückblick.",
               "Den Plan in Etappen mit Ziel, Abnahme und Zieldatum gliedern („Neuer Bogen“)."),
        "en": ("No arcs yet",
               "Without arcs (milestones) there is no forecast, no timeline and no retrospective.",
               "Split the plan into milestones with goal, acceptance and target date (“New arc”).")}),
    "bogen_ohne_abnahme": ("fehler", "lead", "bogen", {
        "de": ("Bogen {b} „{titel}“ hat kein Abnahmekriterium",
               "Niemand kann sagen, wann der Bogen fertig ist – das Abschließen wird Bauchgefühl, und Agenten arbeiten ins Offene.",
               "Im Bogen eine prüfbare Abnahme eintragen (wer prüft was, woran sieht man es)."),
        "en": ("Arc {b} “{titel}” has no acceptance criterion",
               "Nobody can tell when the arc is done – closing it becomes gut feeling and agents work open-ended.",
               "Add a testable acceptance to the arc (who checks what, how can it be seen).")}),
    "bogen_ohne_zieldatum": ("warnung", "du", "bogen", {
        "de": ("Bogen {b} „{titel}“ hat kein Zieldatum",
               "Die Prognose läuft ({p50} – {p85}), aber es gibt keinen Termin zum Vergleichen: die Termin-Ampel bleibt grau, Verzug fällt niemandem auf.",
               "Ein Zieldatum setzen – realistisch ist der P85-Wert der Prognose. Ist der Bogen bewusst ohne Termin, akzeptieren."),
        "en": ("Arc {b} “{titel}” has no target date",
               "The forecast runs ({p50} – {p85}), but there is no date to compare with: the schedule light stays grey and nobody notices a slip.",
               "Set a target date – the forecast's P85 is realistic. If the arc deliberately has no date, accept.")}),
    "aktiv_ohne_anforderungen": ("warnung", "du", "spec_anforderungen", {
        "de": ("Bogen {b} ist aktiv, die Anforderungen sind nicht freigegeben",
               "Agenten arbeiten auf Anforderungen, die du noch nicht bestätigt hast – ändern sie sich, ist die Arbeit dafür verloren.",
               "Anforderungen ansehen und freigeben oder zurückgeben."),
        "en": ("Arc {b} is active but its requirements are not approved",
               "Agents work on requirements you have not confirmed – if they change, that work is lost.",
               "Review the requirements and approve or return them.")}),
    "prognose_rot": ("fehler", "du", "bogen", {
        "de": ("Bogen {b} „{titel}“ wird voraussichtlich zu spät fertig",
               "Schon die mittlere Prognose ({p50}) liegt nach dem Zieldatum {ziel}: wahrscheinlicher verspätet als pünktlich.",
               "Entscheiden: Umfang kürzen, Schritte auf mehr Agenten verteilen oder das Zieldatum mit Grund verschieben (die Baseline bleibt sichtbar)."),
        "en": ("Arc {b} “{titel}” is likely to finish late",
               "Even the median forecast ({p50}) is after the target date {ziel}: more likely late than on time.",
               "Decide: cut scope, spread steps over more agents or move the target date with a reason (the baseline stays visible).")}),
    "prognose_gelb": ("warnung", "du", "bogen", {
        "de": ("Bogen {b} „{titel}“: Termin wackelt",
               "Der Termin {ziel} ist nur zu 50–85 % zu halten (sicher erst {p85}). Kleine Störungen reichen für Verzug.",
               "Beobachten; wenn es wichtig ist: Puffer schaffen (Umfang, Reihenfolge, Bearbeiter)."),
        "en": ("Arc {b} “{titel}”: date at risk",
               "The date {ziel} holds only with 50–85 % (safe from {p85}). Small disruptions are enough for a slip.",
               "Keep an eye on it; if it matters: create buffer (scope, order, assignees).")}),
    "anforderung_ungedeckt": ("warnung", "lead", "spec_anforderungen", {
        "de": ("Bogen {b}: {n} Anforderung(en) ohne Schritt – {liste}",
               "Für diese Anforderungen ist nach heutigem Plan keine Arbeit vorgesehen. Die Abnahme des Bogens würde daran scheitern.",
               "Schritte dafür anlegen oder vorhandenen Schritten zuordnen (amw aufgabe aendern <Nr> --anforderungen R1,R2). Fällt eine weg: Anforderungen ändern."),
        "en": ("Arc {b}: {n} requirement(s) without a step – {liste}",
               "Today's plan has no work for these requirements. Accepting the arc would fail on them.",
               "Create steps for them or assign them to existing steps (amw aufgabe aendern <no> --anforderungen R1,R2). If one is dropped: change the requirements.")}),
    "schritt_ohne_kriterien": ("warnung", "lead", "schritt", {
        "de": ("A{a} „{titel}“ hat keine Abnahmekriterien",
               "Der Bearbeiter weiß nicht genau, wann er fertig ist, der Prüfer hat keinen Maßstab – typische Quelle für Nacharbeit.",
               "2–4 prüfbare Kriterien ergänzen (amw aufgabe aendern {a} --kriterium … --kriterium …)."),
        "en": ("A{a} “{titel}” has no acceptance criteria",
               "The assignee doesn't know exactly when it's done, the reviewer has no yardstick – a typical source of rework.",
               "Add 2–4 testable criteria (amw aufgabe aendern {a} --kriterium … --kriterium …).")}),
    "schritt_ohne_bearbeiter": ("hinweis", "lead", "schritt", {
        "de": ("A{a} „{titel}“ hat keinen Bearbeiter",
               "Der Schritt liegt im freien Vorrat – irgendein Agent nimmt ihn mit „schritt naechster“. Die Prognose rechnet mit dem Team-Durchsatz.",
               "Nur nötig, wenn ein bestimmter Agent ihn machen soll: Bearbeiter setzen."),
        "en": ("A{a} “{titel}” has no assignee",
               "The step is in the open pool – any agent picks it up with “schritt naechster”. The forecast uses team throughput.",
               "Only needed if a particular agent should do it: set an assignee.")}),
    "plan_fehlt": ("hinweis", "lead", "schritt", {
        "de": ("A{a}: Komplexität {k} – Plan fehlt oder ist nicht freigegeben",
               "Ab Komplexität {ab} darf der Schritt erst starten, wenn sein Plan freigegeben ist – sonst bleibt er stehen.",
               "Der Bearbeiter legt den Plan vor (amw aufgabe plan {a} --text …), der Verantwortliche gibt ihn frei."),
        "en": ("A{a}: complexity {k} – plan missing or not approved",
               "From complexity {ab} the step may only start once its plan is approved – otherwise it stalls.",
               "The assignee submits the plan (amw aufgabe plan {a} --text …), the responsible person approves it.")}),
    "zu_komplex": ("warnung", "lead", "schritt", {
        "de": ("A{a}: Komplexität {k} – besser teilen",
               "Sehr große Schritte sind schwer zu schätzen und zu prüfen; sie laufen am häufigsten aus dem Ruder.",
               "In 2–3 kleinere Schritte mit eigenen Kriterien teilen."),
        "en": ("A{a}: complexity {k} – better split",
               "Very large steps are hard to estimate and review; they are the most likely to get out of hand.",
               "Split into 2–3 smaller steps with their own criteria.")}),
    "ohne_zusammenfassung": ("hinweis", "lead", "schritt", {
        "de": ("Bogen {b}: {n} fertige(r) Schritt(e) ohne Zusammenfassung – {liste}",
               "Rückblick, Verlauf und „Seit du weg warst“ zeigen dann nicht, was herausgekommen ist.",
               "Zusammenfassung nachtragen (amw aufgabe aendern <Nr> --zusammenfassung …) oder akzeptieren."),
        "en": ("Arc {b}: {n} finished step(s) without summary – {liste}",
               "Retrospective, history and “since you were away” then don't show what came out of it.",
               "Add the summary (amw aufgabe aendern <no> --zusammenfassung …) or accept.")}),
    "risiko_ohne_massnahme": ("warnung", "du", "risiko", {
        "de": ("Risiko {r} „{titel}“ ohne Maßnahme oder Verantwortlichen",
               "Ein erkanntes Risiko ohne Maßnahme ist nur eine Notiz – tritt es ein, ist niemand vorbereitet.",
               "Maßnahme und Verantwortlichen eintragen – oder die Strategie „akzeptieren“ wählen."),
        "en": ("Risk {r} “{titel}” without mitigation or owner",
               "A known risk without mitigation is just a note – if it happens nobody is prepared.",
               "Enter mitigation and owner – or choose the strategy “accept”.")}),
    "risiko_eingetreten": ("fehler", "du", "risiko", {
        "de": ("Risiko {r} „{titel}“ ist eingetreten",
               "Das Risiko ist kein Risiko mehr, sondern ein Problem – Termine und Plan stimmen vermutlich nicht mehr.",
               "Folgen bewerten, Plan anpassen (Schritte, Termine) und das Risiko danach auf „erledigt“ setzen."),
        "en": ("Risk {r} “{titel}” has occurred",
               "The risk is now a problem – dates and plan are probably no longer right.",
               "Assess the impact, adjust the plan (steps, dates) and then set the risk to “done”.")}),
    "haengt_an_verworfenem": ("warnung", "lead", "schritt", {
        "de": ("A{a} „{titel}“ hängt an verworfener A{v}",
               "Der Vorgänger wird nie fertig. Der Schritt wartet deshalb auf etwas, das es nicht mehr gibt.",
               "Abhängigkeit lösen (amw aufgabe aendern {a} --ohne-vorgaenger {v}) oder durch den Ersatz-Schritt ersetzen (--nach <Nr>)."),
        "en": ("A{a} “{titel}” depends on discarded A{v}",
               "The predecessor will never be finished, so the step waits for something that no longer exists.",
               "Remove the dependency (amw aufgabe aendern {a} --ohne-vorgaenger {v}) or replace it with the successor step (--nach <no>).")}),
}
STUFEN = ("fehler", "warnung", "hinweis")


def check_entscheidungen(con, pid):
    """{schluessel: {"grund", "von", "zeit_utc"}} – bewusst akzeptierte Befunde (letzter Eintrag je Schlüssel gilt)."""
    aus = {}
    for r in con.execute("SELECT zeit_utc, von, art, text FROM plan_ereignis WHERE projekt_id = ? AND art IN"
                         " ('check_akzeptiert', 'check_wieder') ORDER BY id", (pid,)):
        schluessel, _, grund = (r["text"] or "").partition(" – ")
        if r["art"] == "check_akzeptiert":
            aus[schluessel] = {"grund": grund, "von": r["von"], "zeit_utc": r["zeit_utc"]}
        else:
            aus.pop(schluessel, None)
    return aus


def pruefen(con, pid, prog=None, mit_akzeptierten=False):
    """Befunde [{code, stufe, wer, ziel, text, werte, gruppe, ref, schluessel, bogen_id, aufgabe_id, risiko_id, akzeptiert}].
    text = deutscher Titel (Kommandozeile); die Workbench setzt Titel/Bedeutung/Abhilfe aus CHECKS je Sprache zusammen.
    Ohne mit_akzeptierten fehlen bewusst akzeptierte Befunde."""
    aus = []

    def add(code, ref, gruppe="projekt", bogen_id=None, aufgabe_id=None, risiko_id=None, **werte):
        stufe, wer, ziel, texte = CHECKS[code]
        aus.append({"code": code, "stufe": stufe, "wer": wer, "ziel": ziel, "text": texte["de"][0].format(**werte),
                    "werte": werte, "gruppe": gruppe, "ref": ref, "schluessel": f"{code}:{ref}" if ref else code,
                    "bogen_id": bogen_id, "aufgabe_id": aufgabe_id, "risiko_id": risiko_id, "akzeptiert": None})

    lb = leitbild(con, pid)
    if not lb["ziel"]:
        add("kein_ziel", None)
    if not lb["nicht_ziele"]:
        add("keine_nicht_ziele", None)
    if not lb["dod"]:
        add("keine_dod", None)
    bs = boegen(con, pid)
    if not bs:
        add("keine_boegen", None)
    prog = prog if prog is not None else prognose(con, pid, laeufe=300)
    for b in bs:
        if b["status"] in ("fertig", "verworfen"):
            continue
        g, bid, r = f"bogen:{b['id']}", b["id"], f"B{b['id']}"
        p = prog["boegen"].get(b["id"]) or {}
        tt = lambda x: f"{x[8:10]}.{x[5:7]}.{x[:4]}" if x else "–"          # Texte lesen Menschen: TT.MM.JJJJ
        bw = {"b": b["id"], "titel": b["titel"], "ziel": tt(b["zieldatum"]), "p50": tt(p.get("p50")), "p85": tt(p.get("p85"))}
        if not (b["abnahme"] or "").strip():
            add("bogen_ohne_abnahme", r, g, bid, **bw)
        if not b["zieldatum"]:
            add("bogen_ohne_zieldatum", r, g, bid, **bw)
        if b["status"] == "aktiv" and b["spec"].get("anforderungen") != "frei":
            add("aktiv_ohne_anforderungen", r, g, bid, **bw)
        if p.get("ampel") == "rot":
            add("prognose_rot", r, g, bid, **bw)
        elif p.get("ampel") == "gelb":
            add("prognose_gelb", r, g, bid, **bw)
        anf = set(ANFORDERUNG.findall(spec(con, b["id"], "anforderungen")["text"]))
        gedeckt = set()
        for (x,) in con.execute("SELECT anforderungen FROM aufgabe WHERE bogen_id = ? AND status != 'verworfen'", (b["id"],)):
            gedeckt |= set(ANFORDERUNG.findall(x or ""))
        fehlt = sorted(anf - gedeckt, key=lambda x: int(x[1:]))
        if fehlt:
            add("anforderung_ungedeckt", f"{r}:{','.join(fehlt)}", g, bid, n=len(fehlt), liste=", ".join(fehlt), **bw)
        for a in con.execute("SELECT * FROM aufgabe WHERE bogen_id = ? AND status NOT IN ('fertig', 'verworfen') ORDER BY rang, id",
                             (b["id"],)):
            aw = {"a": a["id"], "titel": a["titel"], "k": a["komplexitaet"], "ab": PLAN_AB_KOMPLEXITAET, "b": b["id"]}
            ra = f"A{a['id']}"
            if b["status"] == "aktiv" and not _json(a["kriterien"], []):
                add("schritt_ohne_kriterien", ra, g, bid, a["id"], **aw)
            if b["status"] == "aktiv" and not a["agent"]:
                add("schritt_ohne_bearbeiter", ra, g, bid, a["id"], **aw)
            if (a["komplexitaet"] or 0) >= PLAN_AB_KOMPLEXITAET and a["plan_status"] != "frei":
                add("plan_fehlt", ra, g, bid, a["id"], **aw)
            if (a["komplexitaet"] or 0) >= 9:
                add("zu_komplex", ra, g, bid, a["id"], **aw)
        ohne = [f"A{x}" for (x,) in con.execute("SELECT id FROM aufgabe WHERE bogen_id = ? AND status = 'fertig'"
                                               " AND coalesce(zusammenfassung, '') = '' ORDER BY id", (b["id"],))]
        if ohne:
            add("ohne_zusammenfassung", f"{r}:{','.join(ohne)}", g, bid, n=len(ohne), liste=", ".join(ohne), **bw)
    for x in risiken(con, pid):
        rw = {"r": x["id"], "titel": x["titel"]}
        g = f"bogen:{x['bogen_id']}" if x["bogen_id"] else "risiken"
        if x["status"] != "erledigt" and (not x["massnahme"] or not x["verantwortlich"]) and x["strategie"] != "akzeptieren":
            add("risiko_ohne_massnahme", f"R{x['id']}", g, x["bogen_id"], risiko_id=x["id"], **rw)
        if x["status"] == "eingetreten":
            add("risiko_eingetreten", f"R{x['id']}", g, x["bogen_id"], risiko_id=x["id"], **rw)
    for z in con.execute("SELECT b.id AS nach, b.titel, b.bogen_id, a.id AS vor FROM abhaengigkeit d JOIN aufgabe a ON a.id = d.vor"
                         " JOIN aufgabe b ON b.id = d.nach WHERE a.status = 'verworfen' AND b.status NOT IN ('fertig', 'verworfen')"
                         " AND b.projekt_id = ? ORDER BY b.id", (pid,)):
        add("haengt_an_verworfenem", f"A{z['nach']}:A{z['vor']}", f"bogen:{z['bogen_id']}" if z["bogen_id"] else "projekt",
            z["bogen_id"], z["nach"], a=z["nach"], v=z["vor"], titel=z["titel"])
    akzeptiert = check_entscheidungen(con, pid)
    for x in aus:
        if x["stufe"] != "fehler":
            x["akzeptiert"] = akzeptiert.get(x["schluessel"])
    if not mit_akzeptierten:
        aus = [x for x in aus if not x["akzeptiert"]]
    return aus


def check_akzeptieren(con, pid, von, schluessel, grund):
    """Befund bewusst so lassen (nur Warnungen/Hinweise, nur Lead/Entwickler, mit Grund) – er zählt dann nicht mehr."""
    _lead(con, pid, von, "Befunde akzeptieren")
    grund = (grund or "").strip()
    if not grund:
        raise kern.AmwFehler("Bitte einen Grund angeben – warum ist es so in Ordnung?")
    x = next((x for x in pruefen(con, pid, mit_akzeptierten=True) if x["schluessel"] == schluessel), None)
    if not x:
        raise kern.AmwFehler(f"Befund „{schluessel}“ gibt es (nicht mehr)")
    if x["stufe"] == "fehler":
        raise kern.AmwFehler("Fehler lassen sich nicht akzeptieren – sie müssen behoben werden")
    with db.schreiben(con):
        _log(con, pid, von, "check_akzeptiert", f"{schluessel} – {grund}", bogen_id=x["bogen_id"], aufgabe_id=x["aufgabe_id"])
    return x


def check_wieder(con, pid, von, schluessel):
    """Akzeptanz zurücknehmen – der Befund zählt wieder."""
    _lead(con, pid, von, "Befunde wieder prüfen")
    if schluessel not in check_entscheidungen(con, pid):
        raise kern.AmwFehler(f"„{schluessel}“ ist nicht akzeptiert")
    with db.schreiben(con):
        _log(con, pid, von, "check_wieder", schluessel)


def status(con, pid, prog=None):
    """RAG je Dimension mit Begründung (nach Regeln, nicht Bauchgefühl)."""
    prog = prog if prog is not None else prognose(con, pid, laeufe=300)
    ampeln = [p["ampel"] for b, p in prog["boegen"].items() if p["ampel"]]
    termin = "rot" if "rot" in ampeln else "gelb" if "gelb" in ampeln else "gruen" if ampeln else None
    rs = [r for r in risiken(con, pid) if r["status"] != "erledigt"]
    risiko = "rot" if any(r["wert"] >= 15 or r["status"] == "eingetreten" for r in rs) else "gelb" if any(r["wert"] >= 9 for r in rs) else "gruen"
    ab = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    q = con.execute("SELECT sum(ergebnis = 'rot'), sum(ergebnis = 'gruen') FROM pruefung WHERE projekt_id = ? AND ergebnis_utc >= ?",
                    (pid, ab)).fetchone()
    rot, gruen = q[0] or 0, q[1] or 0
    qualitaet = None if rot + gruen == 0 else "rot" if rot > gruen else "gelb" if rot else "gruen"
    return {"termin": termin, "risiko": risiko, "qualitaet": qualitaet,
            "begruendung": {"termin": f"{ampeln.count('rot')} rot, {ampeln.count('gelb')} gelb von {len(ampeln)} Bögen mit Zieldatum",
                            "risiko": f"{len(rs)} offene Risiken, höchster Wert {max((r['wert'] for r in rs), default=0)}",
                            "qualitaet": f"Prüfungen 7 Tage: {gruen} grün, {rot} rot"}}


def freigaben_offen(con, pid):
    """Was auf den Menschen wartet: vorgelegte Spezifikationen und Pläne, für die er verantwortlich ist, eigene Schritte."""
    spec_ = [dict(s) for s in con.execute(
        "SELECT s.bogen_id, s.teil, s.version, s.geaendert_utc, b.titel FROM spezifikation s JOIN bogen b ON b.id = s.bogen_id"
        " WHERE b.projekt_id = ? AND s.status = 'vorgelegt' ORDER BY s.geaendert_utc", (pid,))]
    plaene = [dict(a) for a in con.execute(
        "SELECT id, titel, agent, plan, geaendert_utc FROM aufgabe WHERE projekt_id = ? AND plan_status = 'vorgelegt'"
        " AND verantwortlich = ?", (pid, MENSCH))]
    eigene = [dict(a) for a in con.execute(
        "SELECT id, titel, auftrag, status, bogen_id FROM aufgabe WHERE projekt_id = ? AND agent = ? AND status IN ('wartet', 'laeuft', 'blockiert')"
        " ORDER BY rang, id", (pid, MENSCH))]
    return {"spezifikationen": spec_, "plaene": plaene, "eigene": eigene}


def kontext_zeilen(con, pid, kennung):
    """Für den Pflicht-Kontext der Agenten: Leitbild kurz, aktive Bögen, eigener nächster Schritt."""
    z = []
    lb = leitbild(con, pid)
    if lb["ziel"]:
        z.append("Projektziel: " + lb["ziel"] + (" · Nicht-Ziele: " + "; ".join(lb["nicht_ziele"]) if lb["nicht_ziele"] else ""))
    if lb["prinzipien"]:
        z.append("Prinzipien: " + " | ".join(p["text"] + (f" (Prüffrage: {p['pruefung']})" if p.get("pruefung") else "")
                                             for p in lb["prinzipien"]))
    if lb["dod"]:
        z.append("Definition of Done: " + " | ".join(lb["dod"]))
    aktiv = [b for b in boegen(con, pid) if b["status"] == "aktiv"]
    if aktiv:
        z.append("Aktive Bögen: " + "; ".join(f"Bogen {b['id']} „{b['titel']}“ {b['fertig']}/{b['gesamt'] - b['verworfen']} fertig"
                                               + (f", Ziel {b['zieldatum']}" if b["zieldatum"] else "") for b in aktiv)
                 + " – nächster Schritt: amw schritt naechster --von " + kennung)
    return z
