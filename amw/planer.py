"""Grobplanung aus Themen (K4 / A1940, D1304 v12 §2, Umsetzungsplan #30103): ein frischer claude -p-Planer entwirft zu einem
freigegebenen Thema Meilenstein(e) und Pakete – als DATEN nach festem Schema, nicht als Text. Die AMW prüft den Entwurf, der
Lead sagt Ja oder ändert ihn, erst dann legt die AMW alles an und verknüpft es mit dem Thema (A1915). Kein Anlegen ohne Ja.
Ein Thema, das nichts braucht, bekommt den Vermerk „nichts zu bauen“ mit Grund.

Stand der Vorbereitung (#30112): Schema, Prüfung, Entwurf eintragen, Übernehmen – mit Tests aus festen Planer-Ergebnissen.
Das Anstoßen bei der Freigabe, `amw thema planen` und die Ansicht kommen nach Marcels Ja zur Kleinprobe A1916 (F5366).

Ereignisse (plan_ereignis, ohne Schemaänderung, Text JSON mit "thema" vorn wie alle Themen-Ereignisse):
  thema_planentwurf   {"thema", "fassung", "modell", "usd", "lauf", "entwurf" | "fehler"}   – ein geprüfter Entwurf (oder Fehler)
  thema_plan_ja       {"thema", "entwurf" (Ereignis-Nr.), "angelegt": {Schlüssel: "M12" | "A345"}, "geaendert"}
  thema_nichts_zu_bauen {"thema", "entwurf", "grund"}

Schema des Planer-Ergebnisses (JSON):
  {"nichts_zu_bauen": false,
   "meilensteine": [{"schluessel": "M1", "titel": "…", "endet_mit": "vorfuehrung|bericht"}  |  {"schluessel": "M1", "bestehend": 52}],
   "pakete": [{"schluessel": "P1", "meilenstein": "M1", "titel": "…", "auftrag": "…", "groesse": "S|M|L|XL",
               "art": "text|mechanisch|fehlersuche|oberflaeche|sicherheit|konzept", "ausfuehrung": "agent|p",
               "modell": "haiku|sonnet|opus", "effort": "low|medium|high", "fertig_quelle": "commit|release|thema|dokument|frist|ja",
               "nach": ["P0", "A1234"], "abnahme_befehl": "python -m unittest tests.test_x" | null}]}
  oder {"nichts_zu_bauen": true, "grund": "…"}
"""
import json
import os
import subprocess
import sys
import tempfile
import time

from . import db, kern

ENTWURF, JA, NICHTS = "thema_planentwurf", "thema_plan_ja", "thema_nichts_zu_bauen"
FERTIG_QUELLEN = ("commit", "release", "thema", "dokument", "frist", "ja")     # K2 (TH155 2/3/6)
AUSFUEHRUNG = ("agent", "p")
MODELLE = ("haiku", "sonnet", "opus")
EFFORTS = ("low", "medium", "high")
MAX_PAKETE, MAX_MEILENSTEINE = 30, 5
LAENGE = {"titel": 120, "auftrag": 4000, "grund": 1000, "abnahme_befehl": 300}
ENDET_MIT = {"vorfuehrung": "Vorführung", "bericht": "Bericht"}   # TH164: ein Meilenstein endet mit Vorführung oder Bericht


class PlanFehler(kern.AmwFehler):
    """Der Entwurf passt nicht zum Schema – .fehler ist die Liste der Funde (alle auf einmal, nicht nur der erste)."""
    def __init__(self, fehler):
        self.fehler = list(fehler)
        super().__init__("Entwurf passt nicht zum Schema: " + "; ".join(self.fehler[:8]) + (" …" if len(self.fehler) > 8 else ""))


def _text(x, feld, wo, f, pflicht=True):
    v = " ".join(str(x).split()) if feld in ("titel",) and isinstance(x, str) else (x.strip() if isinstance(x, str) else x)
    if v is None or v == "":
        if pflicht:
            f.append(f"{wo}: {feld} fehlt")
        return None
    if not isinstance(v, str):
        f.append(f"{wo}: {feld} ist kein Text")
        return None
    if len(v) > LAENGE[feld]:
        f.append(f"{wo}: {feld} länger als {LAENGE[feld]} Zeichen")
    return v


def _wahl(x, erlaubt, feld, wo, f, klein=True):
    v = str(x).strip() if x is not None else ""
    v = v.lower() if klein else v.upper()
    if v not in erlaubt:
        f.append(f"{wo}: {feld} „{x}“ – erlaubt: {' | '.join(erlaubt)}")
        return None
    return v


def pruefen(daten, con=None, pid=None):
    """Prüft ein Planer-Ergebnis (dict oder JSON-Text) gegen das Schema und gibt es vereinheitlicht zurück. Mit con/pid auch:
    bestehende Meilensteine und Aufgaben (Verweise „A1234“) gibt es im Projekt. Fehler: PlanFehler mit allen Funden."""
    from . import empfehlung
    if isinstance(daten, str):
        try:
            daten = json.loads(daten)
        except ValueError as e:
            raise PlanFehler([f"kein JSON: {e}"]) from None
    if not isinstance(daten, dict):
        raise PlanFehler(["oben muss ein Objekt stehen"])
    f = []
    unbekannt = set(daten) - {"nichts_zu_bauen", "grund", "meilensteine", "pakete"}
    if unbekannt:
        f.append("unbekannte Felder: " + ", ".join(sorted(unbekannt)))
    if daten.get("nichts_zu_bauen") is True:
        grund = _text(daten.get("grund"), "grund", "nichts zu bauen", f)
        if daten.get("meilensteine") or daten.get("pakete"):
            f.append("nichts zu bauen, aber Meilensteine oder Pakete angegeben")
        if f:
            raise PlanFehler(f)
        return {"nichts_zu_bauen": True, "grund": grund}
    ms, ps = daten.get("meilensteine"), daten.get("pakete")
    if not isinstance(ms, list) or not ms:
        f.append("meilensteine: mindestens einer")
        ms = []
    if not isinstance(ps, list) or not ps:
        f.append("pakete: mindestens eins")
        ps = []
    if len(ms) > MAX_MEILENSTEINE:
        f.append(f"höchstens {MAX_MEILENSTEINE} Meilensteine je Thema")
    if len(ps) > MAX_PAKETE:
        f.append(f"höchstens {MAX_PAKETE} Pakete je Thema")
    aus_m, aus_p, schluessel = [], [], set()
    for i, m in enumerate(ms, 1):
        wo = f"Meilenstein {i}"
        if not isinstance(m, dict):
            f.append(f"{wo}: kein Objekt")
            continue
        s = str(m.get("schluessel") or "").strip()
        if not s:
            f.append(f"{wo}: schluessel fehlt")
        elif s in schluessel:
            f.append(f"{wo}: Schlüssel {s} doppelt")
        schluessel.add(s)
        wo = f"Meilenstein {s or i}"
        if m.get("bestehend") is not None:
            try:
                nr = int(str(m["bestehend"]).lstrip("Mm"))
            except ValueError:
                f.append(f"{wo}: bestehend ist keine Meilenstein-Nummer")
                continue
            if con is not None and not con.execute("SELECT 1 FROM bogen WHERE projekt_id = ? AND nr = ?", (pid, nr)).fetchone():
                f.append(f"{wo}: Meilenstein {nr} gibt es im Projekt nicht")
            aus_m.append({"schluessel": s, "bestehend": nr})
            continue
        if m.get("ziel") or m.get("abnahme"):           # TH164: Ziel und Abnahme als Verweis (aufs Thema), nicht als Freitext
            f.append(f"{wo}: ziel/abnahme nicht als Text – ein Meilenstein verweist auf seine Themen und endet_mit")
        aus_m.append({"schluessel": s, "titel": _text(m.get("titel"), "titel", wo, f),
                      "endet_mit": _wahl(m.get("endet_mit"), tuple(ENDET_MIT), "endet_mit", wo, f)})
    m_namen = {m["schluessel"] for m in aus_m}
    p_namen = [str(p.get("schluessel") or "").strip() for p in ps if isinstance(p, dict)]
    for i, p in enumerate(ps, 1):
        wo = f"Paket {i}"
        if not isinstance(p, dict):
            f.append(f"{wo}: kein Objekt")
            continue
        s = str(p.get("schluessel") or "").strip()
        if not s:
            f.append(f"{wo}: schluessel fehlt")
        elif s in schluessel:
            f.append(f"{wo}: Schlüssel {s} doppelt")
        schluessel.add(s)
        wo = f"Paket {s or i}"
        m = str(p.get("meilenstein") or "").strip()
        if m not in m_namen:
            f.append(f"{wo}: Meilenstein „{m}“ steht nicht in meilensteine")
        nach = []
        for v in p.get("nach") or []:
            v = str(v).strip()
            if v in p_namen:
                nach.append(v)
            elif v[:1] in "Aa" and v[1:].isdigit():
                if con is not None and not con.execute("SELECT 1 FROM aufgabe WHERE projekt_id = ? AND id = ?", (pid, int(v[1:]))).fetchone():
                    f.append(f"{wo}: nach {v} – die Aufgabe gibt es im Projekt nicht")
                nach.append("A" + v[1:])
            else:
                f.append(f"{wo}: nach „{v}“ ist weder ein Paket dieses Entwurfs noch eine Aufgabe (A1234)")
        if s and s in nach:
            f.append(f"{wo}: hängt von sich selbst ab")
        groesse = _wahl(p.get("groesse"), empfehlung.GROESSEN, "groesse", wo, f, klein=False)
        aus_p.append({"schluessel": s, "meilenstein": m, "titel": _text(p.get("titel"), "titel", wo, f),
                      "auftrag": _text(p.get("auftrag"), "auftrag", wo, f), "groesse": groesse,
                      "art": _wahl(p.get("art"), empfehlung.ARTEN, "art", wo, f),
                      "ausfuehrung": _wahl(p.get("ausfuehrung") or "agent", AUSFUEHRUNG, "ausfuehrung", wo, f),
                      "modell": _wahl(p.get("modell"), MODELLE, "modell", wo, f) if p.get("modell") else None,
                      "effort": _wahl(p.get("effort"), EFFORTS, "effort", wo, f) if p.get("effort") else None,
                      "fertig_quelle": _wahl(p.get("fertig_quelle"), FERTIG_QUELLEN, "fertig_quelle", wo, f),
                      "nach": nach, "abnahme_befehl": _text(p.get("abnahme_befehl"), "abnahme_befehl", wo, f, pflicht=False)})
        if aus_p[-1]["ausfuehrung"] == "p" and not aus_p[-1]["abnahme_befehl"]:
            f.append(f"{wo}: ein p-Paket braucht einen Abnahme-Befehl (die AMW nimmt es selbst ab)")
        if aus_p[-1]["abnahme_befehl"]:                  # P462 (2): wie beim Start des Arbeiters – ein Befehl, keine Verkettung
            from . import arbeiter
            try:
                arbeiter.freigabe(aus_p[-1]["abnahme_befehl"])
            except arbeiter.ArbeiterFehler as x:
                f.append(f"{wo}: {x}")
    kreis = _kreis({p["schluessel"]: [v for v in p["nach"] if v in p_namen] for p in aus_p})
    if kreis:
        f.append("Abhängigkeiten im Kreis: " + " → ".join(kreis))
    leer = sorted(m_namen - {p["meilenstein"] for p in aus_p} - {m["schluessel"] for m in aus_m if m.get("bestehend")})
    if leer:
        f.append("neue Meilensteine ohne Pakete: " + ", ".join(leer))
    if f:
        raise PlanFehler(f)
    return {"nichts_zu_bauen": False, "meilensteine": aus_m, "pakete": aus_p}


def _kreis(nach):
    """Ein Kreis in den Abhängigkeiten als Liste von Schlüsseln (erster = letzter) – oder None."""
    farbe = {}

    def tief(k, weg):
        farbe[k] = 1
        for v in nach.get(k, []):
            if farbe.get(v) == 1:
                return weg[weg.index(v):] + [v]
            if not farbe.get(v):
                r = tief(v, weg + [v])
                if r:
                    return r
        farbe[k] = 2
        return None

    for k in nach:
        if not farbe.get(k):
            r = tief(k, [k])
            if r:
                return r
    return None


def reihenfolge(entwurf):
    """Pakete so sortiert, dass jedes nach seinen Vorgängern im Entwurf kommt (stabil: sonst wie geliefert)."""
    rest, fertig, aus = list(entwurf["pakete"]), set(), []
    while rest:
        for p in rest:
            if all(v in fertig or v.startswith("A") for v in p["nach"]):
                aus.append(p)
                fertig.add(p["schluessel"])
                rest.remove(p)
                break
        else:                                            # kann nach pruefen() nicht vorkommen (kein Kreis)
            raise PlanFehler(["Abhängigkeiten im Kreis"])
    return aus


# --- Ereignisse -----------------------------------------------------------------------------------------------------------

def _ereignisse(con, pid, tid, art):
    aus = []
    for r in con.execute("SELECT id, von, zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND text LIKE ? ORDER BY id",
                         (pid, art, f'{{"thema": {int(tid)},%')):
        try:
            aus.append({"id": r["id"], "von": r["von"], "zeit_utc": r["zeit_utc"], **json.loads(r["text"])})
        except ValueError:
            continue
    return aus


def _ereignis(con, pid, von, art, tid, **werte):
    return db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=art,
                        text=json.dumps({"thema": int(tid), **werte}, ensure_ascii=False))


def entwurf_eintragen(con, pid, tid, fassung, ergebnis, modell=None, usd=None, lauf=None, fehler=None):
    """Das Ergebnis des Planers eintragen: geprüft als Entwurf – oder mit den Funden als Fehler (fehler: der Lauf selbst ging
    nicht). Der Lead bekommt einen Auftrag (Ja oder ändern) bzw. eine Meldung. Rückgabe: Nummer des Ereignisses."""
    t = con.execute("SELECT * FROM thema WHERE id = ? AND projekt_id = ?", (tid, pid)).fetchone()
    if not t:
        raise kern.AmwFehler(f"TH{tid} gibt es nicht")
    if fehler:
        entwurf, fehler = None, [f"Planer-Lauf: {fehler}"]
    else:
        try:
            entwurf, fehler = pruefen(ergebnis, con, pid), None
        except PlanFehler as e:
            entwurf, fehler = None, e.fehler
    lead = kern.lead(con, pid)
    kosten = f"{usd:.2f} $" if isinstance(usd, (int, float)) else "Kosten unbekannt"
    with db.schreiben(con):
        eid = _ereignis(con, pid, "AMW", ENTWURF, tid, fassung=fassung, modell=modell, usd=usd, lauf=lauf,
                        **({"entwurf": entwurf} if entwurf else {"fehler": fehler}))
        if lead and lead != kern.ENTWICKLER:
            if fehler:
                kern._posten(con, pid, "AMW", lead, "meldung", f"Planentwurf TH{tid} „{t['name'][:50]}“ "
                             + ("ging nicht" if fehler[0].startswith("Planer-Lauf:") else "passt nicht zum Schema"),
                             "Funde:\n" + "\n".join(f"- {x}" for x in fehler[:20]) + f"\n\n({modell or '–'}, {kosten})")
            elif entwurf["nichts_zu_bauen"]:
                kern._posten(con, pid, "AMW", lead, "auftrag", f"Planentwurf TH{tid} „{t['name'][:50]}“: nichts zu bauen – stimmt das?",
                             f"Grund des Planers: {entwurf['grund']}\n\nJa oder neu planen lassen. ({kosten})")
            else:
                kern._posten(con, pid, "AMW", lead, "auftrag",
                             f"Planentwurf TH{tid} „{t['name'][:50]}“: {len(entwurf['meilensteine'])} Meilenstein(e), "
                             f"{len(entwurf['pakete'])} Pakete – Ja oder ändern", zusammenfassung(entwurf) + f"\n\n({modell or '–'}, {kosten})")
    return eid


def zusammenfassung(entwurf):
    if entwurf["nichts_zu_bauen"]:
        return f"Nichts zu bauen: {entwurf['grund']}"
    zeilen = []
    for m in entwurf["meilensteine"]:
        zeilen.append(f"{m['schluessel']} " + (f"(bestehender Meilenstein {m['bestehend']})" if m.get("bestehend")
                                                else f"{m['titel']} · endet mit {ENDET_MIT[m['endet_mit']]}"))
        for p in reihenfolge(entwurf):
            if p["meilenstein"] == m["schluessel"]:
                zeilen.append(f"  {p['schluessel']} {p['titel']} · {p['groesse']} · {p['art']} · {p['ausfuehrung']}"
                              + (f" {p['modell']}" if p["modell"] else "") + f" · fertig: {p['fertig_quelle']}"
                              + (f" · nach {', '.join(p['nach'])}" if p["nach"] else ""))
                zeilen.append(f"    Auftrag: {' '.join((p['auftrag'] or '').split())[:600]}")   # P462 (2): was angelegt wird
                if p["abnahme_befehl"]:
                    zeilen.append(f"    Abnahme-Befehl: {p['abnahme_befehl']}")
    return "\n".join(zeilen)


def letzter_entwurf(con, pid, tid):
    ev = _ereignisse(con, pid, tid, ENTWURF)
    return ev[-1] if ev else None


def erledigt(con, pid, eid):
    """Ist dieser Entwurf schon übernommen (Ja oder „nichts zu bauen“)?"""
    return any(e.get("entwurf") == eid for art in (JA, NICHTS)
               for e in [json.loads(r[0]) for r in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = ?",
                                                               (pid, art))])


# --- Ja des Leads: anlegen -----------------------------------------------------------------------------------------------

def uebernehmen(con, pid, von, tid, eid=None, geaendert=None):
    """Ja des Leads (oder des Menschen): den jüngsten (oder genannten) Entwurf anlegen – neue Meilensteine, Pakete mit Größe,
    Art, Ausführung, Modell/Effort, Abnahme-Befehl und Abhängigkeiten, je Paket der Verweis aufs Thema (A1915). geaendert:
    ein vom Lead geänderter Entwurf (gleiches Schema, wird neu geprüft). Rückgabe: {Schlüssel: "M<nr>" | "A<id>"}."""
    from . import themen
    if not (von == kern.ENTWICKLER or kern.ist_lead(con, pid, von)):
        raise kern.AmwFehler("Den Planentwurf nimmt der Lead an (oder der Mensch)")
    e = next((x for x in _ereignisse(con, pid, tid, ENTWURF) if x["id"] == eid), None) if eid else letzter_entwurf(con, pid, tid)
    if not e:
        raise kern.AmwFehler(f"TH{tid} hat keinen Planentwurf" + (f" Nr. {eid}" if eid else ""))
    if erledigt(con, pid, e["id"]):
        raise kern.AmwFehler(f"Der Planentwurf zu TH{tid} ist schon angenommen")
    entwurf = pruefen(geaendert, con, pid) if geaendert is not None else e.get("entwurf")
    if not entwurf:
        raise kern.AmwFehler(f"Der Planentwurf zu TH{tid} passte nicht zum Schema – neu planen lassen oder geändert übergeben")
    s = themen.status(con, themen.finden(con, pid, tid))     # P462 (4): nur für die freigegebene Fassung, die er gelesen hat
    if s["status"] != "frei":
        raise kern.AmwFehler(f"TH{tid} ist nicht freigegeben ({s['text']}) – erst freigeben, dann planen lassen")
    if e.get("fassung") is not None and s["fassung"] != e.get("fassung"):
        raise kern.AmwFehler(f"Der Entwurf gilt für Fassung {e.get('fassung')}, TH{tid} hat jetzt Fassung {s['fassung']} – neu planen lassen")
    for m in entwurf.get("meilensteine") or []:
        if m.get("bestehend") and not con.execute("SELECT 1 FROM bogen WHERE projekt_id = ? AND nr = ? AND status IN ('geplant', 'aktiv')",
                                                  (pid, m["bestehend"])).fetchone():
            raise kern.AmwFehler(f"Meilenstein {m['bestehend']} aus dem Entwurf gibt es nicht mehr offen – neu planen lassen oder geändert übergeben")
    with db.schreiben(con):                          # P462 (4): angenommen wird einmal – Marke zuerst, in einer Transaktion
        if erledigt(con, pid, e["id"]):
            raise kern.AmwFehler(f"Der Planentwurf zu TH{tid} ist schon angenommen")
        merke = _ereignis(con, pid, von, JA, tid, entwurf=e["id"], angelegt={}, laeuft=True)
    schon = {}
    try:
        return _anlegen(con, pid, von, tid, e, entwurf, geaendert, merke, schon)
    except Exception as x:
        with db.schreiben(con):
            if not schon:                            # nichts angelegt: die Marke lösen, ein neues Ja darf es noch einmal versuchen
                con.execute("DELETE FROM plan_ereignis WHERE id = ?", (merke,))
            else:                                    # Vorab-Prüfung 1.164.0 (8): teilweise angelegt – die Marke bleibt (kein
                con.execute("UPDATE plan_ereignis SET text = ? WHERE id = ?",   # zweites Anlegen), sie nennt, was schon da ist
                            (json.dumps({"thema": tid, "entwurf": e["id"], "angelegt": schon, "abgebrochen": str(x)[:300]},
                                        ensure_ascii=False), merke))
                kern._posten(con, pid, "AMW", kern.lead(con, pid) or kern.ENTWICKLER, "meldung",
                             f"Planentwurf TH{tid} nur teilweise angelegt"[:140],
                             f"Abbruch beim Anlegen: {str(x)[:300]}\nSchon angelegt: "
                             + ", ".join(f"{k} → {v}" for k, v in schon.items())
                             + "\nDer Rest fehlt – bitte von Hand ergänzen oder das Angelegte prüfen; ein neues Ja legt nichts doppelt an.")
        raise


def _anlegen(con, pid, von, tid, e, entwurf, geaendert, merke, angelegt):
    from . import arbeitspaket, planung, themen
    if entwurf["nichts_zu_bauen"]:
        with db.schreiben(con):
            con.execute("DELETE FROM plan_ereignis WHERE id = ?", (merke,))
            _ereignis(con, pid, von, NICHTS, tid, entwurf=e["id"], grund=entwurf["grund"])
        return {}
    bogen = {}
    for m in entwurf["meilensteine"]:                    # erst prüfen (pruefen oben), dann anlegen
        if m.get("bestehend"):
            bogen[m["schluessel"]] = con.execute("SELECT id FROM bogen WHERE projekt_id = ? AND nr = ?", (pid, m["bestehend"])).fetchone()[0]
            angelegt[m["schluessel"]] = f"M{m['bestehend']}"
        else:
            t = con.execute("SELECT name FROM thema WHERE id = ?", (tid,)).fetchone()
            bid = planung.bogen_neu(con, pid, von, m["titel"], ziel=f"TH{tid} {t['name'] if t else ''}".strip(),   # Verweis (TH164)
                                    abnahme=ENDET_MIT[m["endet_mit"]])
            bogen[m["schluessel"]] = bid
            angelegt[m["schluessel"]] = f"M{planung.bogen_zeile(con, pid, bid)['nr']}"
    for p in reihenfolge(entwurf):
        nach = [int(v[1:]) if v.startswith("A") else int(angelegt[v][1:]) for v in p["nach"]]
        aid = planung.schritt_setzen(con, pid, von, titel=p["titel"], auftrag=p["auftrag"], bogen_id=bogen[p["meilenstein"]],
                                     groesse=p["groesse"], art=p["art"], pruefbefehl=p["abnahme_befehl"], nach=nach or None)
        felder = {"art": p["ausfuehrung"], **({"modell": p["modell"]} if p["modell"] else {}),
                  **({"effort": p["effort"]} if p["effort"] else {})}
        arbeitspaket.setzen(con, pid, von, aid, **felder)
        themen.verweise_setzen(con, pid, von, aid, [tid])
        angelegt[p["schluessel"]] = f"A{aid}"
    with db.schreiben(con):
        con.execute("DELETE FROM plan_ereignis WHERE id = ?", (merke,))
        _ereignis(con, pid, von, JA, tid, entwurf=e["id"], angelegt=angelegt, geaendert=geaendert is not None,
                  fertig_quellen={p["schluessel"]: p["fertig_quelle"] for p in entwurf["pakete"]})   # K2 übernimmt sie
    return angelegt


# --- der Planer-Lauf (frischer claude -p, nur Lesen) – #30117 ----------------------------------------------------------------
# Auslöser: Freigabe eines Themas (auch die eigene Bearbeitung des Menschen, F5358 A) und `amw thema planen TH<n>` (Lead/Co).
# Projekt-Einstellung themen_planer = sonnet (Vorgabe) | aus. Er läuft wie der Gegenleser als angemeldeter Lauf der
# Lauf-Schlange (leicht) in einem losgelösten Prozess, liest Thema, Beschlüsse, Meilensteine und Pakete als Dateien und
# antwortet mit JSON nach dem Schema oben. Feste Frist; Kosten ins Ereignis.
ANGESTOSSEN = "thema_planer"                     # {"thema", "fassung", "modell", "prozess"}
EINSTIEG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "amw-planer.py")
OHNE_FENSTER = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FRIST_S = 15 * 60
LAEUFT_H = 6                                     # P462 (6): Warten in der Lauf-Schlange + Frist 15 min, mit Luft
AUFTRAG = (
    "Du bist der Planer eines Software-Projekts. Lies thema.md (ein vom Menschen freigegebenes Konzept-Thema), beschluesse.md, "
    "meilensteine.md und pakete.md (was es schon gibt) sowie schema.md (das Antwort-Format). Entwirf, was gebaut werden muss, "
    "damit das Thema erfüllt ist: einen oder wenige Meilensteine (Lieferpunkte, die mit einer Vorführung oder einem Bericht enden – "
    "endet_mit; kein Ziel- oder Abnahme-Text, der Meilenstein verweist auf das Thema; "
    "einen bestehenden Meilenstein nimmst du mit \"bestehend\": Nummer) und kleine Pakete (je eins für einen Agenten an einem Tag "
    "oder weniger), mit Abhängigkeiten. Was es schon gibt, planst du nicht noch einmal; brauchst du ein vorhandenes Paket als "
    "Vorgänger, nennst du es als \"A1234\". Braucht das Thema nichts (schon gebaut, nur ein Begriff), antworte mit "
    "nichts_zu_bauen und Grund. Antworte NUR mit dem JSON-Objekt nach schema.md – kein Text davor oder danach. "
    "Du änderst nichts, du schreibst keine Dateien, du führst nichts aus.")


def einstellung(con, pid):
    return kern.projekt_wahl(con, pid, "themen_planer")


def _angestossen(con, pid, tid):
    return _ereignisse(con, pid, tid, ANGESTOSSEN)


def laeuft(con, pid, tid):
    """Plant gerade ein Planer dieses Thema? Das Ereignis „angestoßen“ ohne Entwurf danach (und nicht älter als LAEUFT_H)."""
    import datetime
    an = _angestossen(con, pid, tid)
    if not an:
        return None
    if any(e["id"] > an[-1]["id"] for e in _ereignisse(con, pid, tid, ENTWURF)):
        return None
    t = datetime.datetime.strptime(an[-1]["zeit_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    return None if (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() > LAEUFT_H * 3600 else an[-1]


def _spawn(pid, tid, fassung, umgebung=None):
    befehl = [sys.executable, "-I", "-X", "utf8", EINSTIEG, "--projekt-id", str(pid), "--thema", str(tid), "--fassung", str(fassung)]
    flags = (0x00000008 | 0x00000200 | OHNE_FENSTER) if os.name == "nt" else 0        # DETACHED, NEW_GROUP wie der Gegenleser
    return subprocess.Popen(befehl, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                            creationflags=flags, env=umgebung, start_new_session=os.name != "nt").pid


STARTER = _spawn             # Tests setzen eine Attrappe; tests/abschotten schaltet das Anstoßen ganz ab (AMW_PLANER_AUS)


def _nichts_vermerkt(con, pid, tid):
    ev = _ereignisse(con, pid, tid, NICHTS)
    return bool(ev) and ev[-1].get("an", True)


def anstossen(con, pid, tid, fassung, von="AMW", erneut=False):
    """Nach der Freigabe (themen.freigeben/bearbeiten, eigene Transaktion) bzw. auf Befehl: einen Planer anstoßen – außer die
    Einstellung ist aus, das Thema hat „nichts zu bauen“, für diese Fassung gab es schon einen (ohne erneut) oder einer läuft.
    Rückgabe: Text oder None."""
    if os.environ.get("AMW_PLANER_AUS") or einstellung(con, pid) == "aus":
        return "Planer ist aus (themen_planer=aus)" if erneut else None
    modell = einstellung(con, pid)
    with db.schreiben(con):                               # in einer Schreib-Transaktion: nie doppelt angestoßen
        if laeuft(con, pid, tid):
            return f"TH{tid}: es plant schon ein Planer" if erneut else None
        if not erneut and (any(e.get("fassung") == fassung for e in _angestossen(con, pid, tid)) or _nichts_vermerkt(con, pid, tid)):
            return None
        eid = _ereignis(con, pid, von, ANGESTOSSEN, tid, fassung=fassung, modell=modell)
    try:
        prozess = STARTER(pid, tid, fassung)
    except OSError as e:                                  # ließ sich nicht starten → Entwurf mit Fehler, der Lead erfährt es
        entwurf_eintragen(con, pid, tid, fassung, None, modell=modell, fehler=f"Planer ließ sich nicht starten: {e}")
        return f"TH{tid}: Planer ließ sich nicht starten ({e})"
    with db.schreiben(con):
        con.execute("UPDATE plan_ereignis SET text = ? WHERE id = ?",
                    (json.dumps({"thema": int(tid), "fassung": fassung, "modell": modell, "prozess": prozess}, ensure_ascii=False), eid))
    return f"TH{tid} Fassung {fassung}: Planer ({modell}) angestoßen"


SCHEMA_TEXT = __doc__[__doc__.index("Schema des Planer-Ergebnisses"):].strip()


def _dateien(con, pid, t, fassung, ordner):
    from . import themen
    f = con.execute("SELECT text FROM thema_fassung WHERE thema_id = ? AND nr = ?", (t["id"], fassung)).fetchone()
    if not f:
        raise kern.AmwFehler(f"TH{t['id']} hat keine Fassung {fassung}")
    b = con.execute("SELECT id, stichwort, regel FROM beschluss WHERE projekt_id = ? AND thema = ? COLLATE NOCASE AND status = 'gilt'"
                    " ORDER BY id", (pid, t["name"])).fetchall()
    ms = con.execute("SELECT nr, titel, status, ziel FROM bogen WHERE projekt_id = ? AND status != 'verworfen' ORDER BY nr", (pid,)).fetchall()
    zum_thema = {a["id"] for a in themen.aufgaben_zu(con, pid, t["id"])}
    offen = con.execute("SELECT id, titel, status FROM aufgabe WHERE projekt_id = ? AND status NOT IN ('fertig', 'verworfen')"
                        " ORDER BY id DESC LIMIT 200", (pid,)).fetchall()
    teile = {"thema.md": f"# TH{t['id']} {t['name']} – Fassung {fassung}\n\n{f['text']}\n",
             "beschluesse.md": "# Geltende Beschlüsse zum Thema\n\n"
                               + ("\n".join(f"- B{x['id']} {x['stichwort']}: {x['regel']}" for x in b) or "(keine)") + "\n",
             "meilensteine.md": "# Meilensteine des Projekts\n\n"
                                + ("\n".join(f"- {x['nr']}: {x['titel']} [{x['status']}]" + (f" – {x['ziel']}" if x["ziel"] else "")
                                             for x in ms) or "(keine)") + "\n",
             "pakete.md": "# Offene Pakete des Projekts (★ = schon mit diesem Thema verknüpft)\n\n"
                          + ("\n".join(f"- A{x['id']} [{x['status']}] {x['titel']}" + (" ★" if x["id"] in zum_thema else "")
                                       for x in offen) or "(keine)") + "\n",
             "schema.md": "# Antwort-Format\n\n" + SCHEMA_TEXT + "\n"}
    for name, text in teile.items():
        with open(os.path.join(ordner, name), "w", encoding="utf-8", newline="\n") as d:
            d.write(text)
    return sorted(teile)


def json_aus_text(text):
    """Das JSON-Objekt aus der Antwort (auch in einem Code-Block oder mit einem Satz drumherum) – oder der Text selbst."""
    s = (text or "").strip()
    a, b = s.find("{"), s.rfind("}")
    return s[a:b + 1] if 0 <= a < b else s


def planen(con, pid, t, fassung, modell, prog=None, zusatz=None):
    """Der Planer selbst, in einem leeren eigenen Ordner (wie ein Platz). Rückgabe {"ergebnis", "usd", "fehler"}."""
    from . import arbeiter, platz, versionsprobe
    with tempfile.TemporaryDirectory(prefix="amw-planer-", ignore_cleanup_errors=True) as ordner:
        p = platz.pfade(os.path.join(ordner, "plaetze"), 1)
        os.makedirs(p["klon"])
        subprocess.run(["git", "init", "-q", "-b", "main", p["klon"]], check=True, capture_output=True, creationflags=OHNE_FENSTER)
        dateien = _dateien(con, pid, t, fassung, p["klon"])
        r = arbeiter.laufen(p, AUFTRAG + "\n\nDateien: " + ", ".join(dateien), None, modell=modell, effort="medium", prog=prog,
                            zusatz=zusatz, nur_lesen=True, geprueft=versionsprobe.geprueft(con), frist_s=FRIST_S)
    erg = r.get("ergebnis") or {}
    usd = erg.get("total_cost_usd")
    if r.get("abweichungen"):
        return {"ergebnis": None, "usd": usd, "fehler": "; ".join(r["abweichungen"])[:500]}
    text = (erg.get("result") or "").strip()
    if r.get("rc") != 0 or erg.get("is_error") or not text:
        return {"ergebnis": None, "usd": usd, "fehler": r.get("fehler") or f"kein Ergebnis (rc {r.get('rc')})"}
    return {"ergebnis": json_aus_text(text), "usd": usd, "fehler": None}


def ausfuehren(con, pid, tid, fassung, prog=None, zusatz=None):
    """Als angemeldeter Lauf der Lauf-Schlange (leicht): warten, bis er dran ist, planen, Entwurf eintragen (auch einen Fehler)."""
    from . import belegung, betrieb
    modell = (_angestossen(con, pid, tid) or [{}])[-1].get("modell") or "sonnet"
    t = con.execute("SELECT * FROM thema WHERE id = ? AND projekt_id = ?", (tid, pid)).fetchone()
    agent = kern.lead(con, pid) or kern.ENTWICKLER
    lid = betrieb.lauf_start(con, pid, agent, f"Planer TH{tid} Fassung {fassung} ({modell}, A1940, automatisch)", None, False, False,
                             None, warten=True, waechter=os.getpid(), befehl=None, ordner=None, selbst=True)   # A1948: kein Weckruf
    belegung.lauf_merken(lid, os.getpid())
    aus = None
    try:
        while True:
            l = betrieb.lauf_zeile(con, pid, lid)
            if l["status"] == "laeuft":
                break
            if l["status"] in ("fertig", "abgebrochen"):
                raise RuntimeError(f"L{lid} ist {l['status']} – nicht geplant")
            time.sleep(5)
        betrieb.lauf_uebernehmen(con, lid, "agent")
        if not t:
            raise kern.AmwFehler(f"TH{tid} gibt es nicht")
        aus = planen(con, pid, t, fassung, modell, prog=prog, zusatz=zusatz)
    except Exception as e:                                # noqa: BLE001 – niemand sieht die Ausgabe: als Fehler eintragen
        aus = {"ergebnis": None, "usd": None, "fehler": f"{type(e).__name__}: {e}"[:300]}
    finally:
        aus = aus or {"ergebnis": None, "usd": None, "fehler": "abgebrochen"}
        kosten = f"{aus['usd']:.2f} $" if isinstance(aus.get("usd"), (int, float)) else "Kosten unbekannt"
        try:
            betrieb.lauf_ende(con, pid, agent, lid, 1 if aus.get("fehler") else 0,
                              (f"Planer TH{tid} Fassung {fassung}: " + (f"Fehler – {aus['fehler']}" if aus.get("fehler") else "fertig")
                               + f" · {kosten}")[:500])
        finally:
            belegung.lauf_vergessen(lid)
    entwurf_eintragen(con, pid, tid, fassung, aus.get("ergebnis"), modell=modell, usd=aus.get("usd"), lauf=lid, fehler=aus.get("fehler"))
    return aus


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="amw-planer")
    ap.add_argument("--projekt-id", type=int, required=True)
    ap.add_argument("--thema", type=int, required=True)
    ap.add_argument("--fassung", type=int, required=True)
    x = ap.parse_args(argv)
    con = db.verbinde()
    try:
        ausfuehren(con, x.projekt_id, x.thema, x.fassung)
    finally:
        con.close()
