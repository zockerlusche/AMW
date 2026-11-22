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
   "meilensteine": [{"schluessel": "M1", "titel": "…", "ziel": "…", "abnahme": "…"}  |  {"schluessel": "M1", "bestehend": 52}],
   "pakete": [{"schluessel": "P1", "meilenstein": "M1", "titel": "…", "auftrag": "…", "groesse": "S|M|L|XL",
               "art": "text|mechanisch|fehlersuche|oberflaeche|sicherheit|konzept", "ausfuehrung": "agent|p",
               "modell": "haiku|sonnet|opus", "effort": "low|medium|high", "fertig_quelle": "commit|release|thema|dokument|frist|ja",
               "nach": ["P0", "A1234"], "abnahme_befehl": "python -m unittest tests.test_x" | null}]}
  oder {"nichts_zu_bauen": true, "grund": "…"}
"""
import json

from . import db, kern

ENTWURF, JA, NICHTS = "thema_planentwurf", "thema_plan_ja", "thema_nichts_zu_bauen"
FERTIG_QUELLEN = ("commit", "release", "thema", "dokument", "frist", "ja")     # K2 (TH155 2/3/6)
AUSFUEHRUNG = ("agent", "p")
MODELLE = ("haiku", "sonnet", "opus")
EFFORTS = ("low", "medium", "high")
MAX_PAKETE, MAX_MEILENSTEINE = 30, 5
LAENGE = {"titel": 120, "auftrag": 4000, "ziel": 1000, "abnahme": 1000, "grund": 1000, "abnahme_befehl": 300}


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
        aus_m.append({"schluessel": s, "titel": _text(m.get("titel"), "titel", wo, f), "ziel": _text(m.get("ziel"), "ziel", wo, f),
                      "abnahme": _text(m.get("abnahme"), "abnahme", wo, f)})
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


def entwurf_eintragen(con, pid, tid, fassung, ergebnis, modell=None, usd=None, lauf=None):
    """Das Ergebnis des Planers eintragen: geprüft als Entwurf – oder mit den Funden als Fehler. Der Lead bekommt einen Auftrag
    (Ja oder ändern) bzw. eine Meldung. Rückgabe: Nummer des Ereignisses."""
    t = con.execute("SELECT * FROM thema WHERE id = ? AND projekt_id = ?", (tid, pid)).fetchone()
    if not t:
        raise kern.AmwFehler(f"TH{tid} gibt es nicht")
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
                kern._posten(con, pid, "AMW", lead, "meldung", f"Planentwurf TH{tid} „{t['name'][:50]}“ passt nicht zum Schema",
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
        zeilen.append(f"{m['schluessel']} " + (f"(bestehender Meilenstein {m['bestehend']})" if m.get("bestehend") else m["titel"]))
        for p in reihenfolge(entwurf):
            if p["meilenstein"] == m["schluessel"]:
                zeilen.append(f"  {p['schluessel']} {p['titel']} · {p['groesse']} · {p['art']} · {p['ausfuehrung']}"
                              + (f" {p['modell']}" if p["modell"] else "") + f" · fertig: {p['fertig_quelle']}"
                              + (f" · nach {', '.join(p['nach'])}" if p["nach"] else ""))
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
    from . import arbeitspaket, planung, themen
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
    if entwurf["nichts_zu_bauen"]:
        with db.schreiben(con):
            _ereignis(con, pid, von, NICHTS, tid, entwurf=e["id"], grund=entwurf["grund"])
        return {}
    angelegt, bogen = {}, {}
    for m in entwurf["meilensteine"]:                    # erst prüfen (pruefen oben), dann anlegen
        if m.get("bestehend"):
            bogen[m["schluessel"]] = con.execute("SELECT id FROM bogen WHERE projekt_id = ? AND nr = ?", (pid, m["bestehend"])).fetchone()[0]
            angelegt[m["schluessel"]] = f"M{m['bestehend']}"
        else:
            bid = planung.bogen_neu(con, pid, von, m["titel"], ziel=m["ziel"], abnahme=m["abnahme"])
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
        _ereignis(con, pid, von, JA, tid, entwurf=e["id"], angelegt=angelegt, geaendert=geaendert is not None,
                  fertig_quellen={p["schluessel"]: p["fertig_quelle"] for p in entwurf["pakete"]})   # K2 übernimmt sie
    return angelegt
