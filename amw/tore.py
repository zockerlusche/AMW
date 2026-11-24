"""K7 (A1944, TH154 Fassung 4, D1304 v12 §2): die fünf Tore Konzept → Grobplanung → Feinplanung → Umsetzung → Abschluss.

Den Tor-Stand rechnet die AMW aus den Daten aus; niemand setzt ihn von Hand (TH154). Wo ein Urteil nötig ist, schließt es mit dem
Ja (Mensch allein oder Co + Lead nach thema_freigabe, B2913/K1):

- Konzept: alle nötigen Themen freigegeben (themen.tor, A1913).
- Grobplanung: jedes freigegebene Thema steckt in einem Meilenstein (über die Pakete) oder hat einen bestätigten Vermerk „nichts zu
  bauen“ (den Grund schreibt der Lead, der Co bestätigt), und jeder geplante Meilenstein ist freigegeben (Urteil).
- Feinplanung: Grobplanung zu und „Jetzt starten“ gegeben – ein Meilenstein läuft (oder alle sind fertig).
- Umsetzung: alle Meilensteine fertig. Unterwegs weckt die AMW den Lead nur bei Abweichungen; neu hier: Prognose überschritten
  (gemessene Kosten eines Pakets über PROGNOSE_FAKTOR × Prognose aus Größe × Art) – rot und Fragen melden sich schon selbst.
- Abschluss: je fertigem Meilenstein ein Abschlussbericht der AMW gegen die Erfolgskriterien (mit Resten und Lehren, als Dokument);
  das Tor schließt mit dem Ja zu allen Berichten (planansicht.freigeben(..., "abschluss")).

Zur Nachvollziehbarkeit hält runde() fest, wann ein Tor schloss oder wieder aufging (Ereignis tor_stand, mit Themen bzw.
Meilensteinen); Konzept schreibt sein tor_geschlossen weiter selbst (A1913).
"""
import json
import re

from . import db, kern

TORE = ("konzept", "grobplanung", "feinplanung", "umsetzung", "abschluss")
NAMEN = {"konzept": "Konzept", "grobplanung": "Grobplanung", "feinplanung": "Feinplanung", "umsetzung": "Umsetzung",
         "abschluss": "Abschluss"}
STAND = "tor_stand"                      # {"tor", "zu", "womit"}
BERICHT = "abschluss_bericht"            # {"bogen", "dokument"}
NICHTS_JA = "thema_nichts_ja"            # {"thema"} – der Co bestätigt „nichts zu bauen“
UEBER = "prognose_ueberschritten"        # {"aufgabe", "usd", "prognose"}
SEIT = "tore_seit"                       # {"seit"} – Stichtag: erst danach fertige Meilensteine bekommen einen Abschlussbericht


def seit(con, pid):
    """Der Stichtag des Abschluss-Tors (erste Dienst-Runde mit K7) oder None. Ältere fertige Meilensteine sind Altbestand:
    kein Bericht, kein Ja nötig (Vorab-Prüfung 1.164.0 (2))."""
    r = con.execute("SELECT zeit_utc FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id LIMIT 1", (pid, SEIT)).fetchone()
    return r[0] if r else None


def _neu_fertig(con, pid, b):
    s = seit(con, pid)
    return bool(s) and (b["fertig_utc"] or "") >= s
PROGNOSE_FAKTOR = 1.5


def _ereignisse(con, pid, art):
    for r in con.execute("SELECT id, von, zeit_utc, text, bogen_id FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id",
                         (pid, art)):
        try:
            yield {"eid": r["id"], "von": r["von"], "zeit_utc": r["zeit_utc"], "bogen_id": r["bogen_id"], **json.loads(r["text"])}
        except ValueError:
            continue


# --- „nichts zu bauen“: der Lead schreibt den Grund, der Co bestätigt (TH154) ------------------------------------------------

def nichts_bestaetigen(con, pid, von, name):
    from . import themen
    if not (von == kern.ENTWICKLER or kern.ist_co(con, pid, von)):
        raise kern.AmwFehler("„nichts zu bauen“ bestätigen der Co-Entwickler oder der Mensch")
    t = themen.finden(con, pid, name)
    if t["id"] not in themen.nichts_vermerkt(con, pid):
        raise kern.AmwFehler(f"TH{t['id']} hat keinen Vermerk „nichts zu bauen“")
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=NICHTS_JA,
                     text=json.dumps({"thema": t["id"]}, ensure_ascii=False))
    return t["id"]


def nichts_gilt(con, pid):
    """{Thema: {"grund", "bestaetigt"}} – bestätigt: vom Mensch vermerkt oder bestätigt, vom Co vermerkt oder bestätigt, oder es
    gibt keinen Co (dann reicht der Lead)."""
    from . import themen
    co = kern.co_entwickler(con, pid)
    letzter, ja = {}, {}
    for d in _ereignisse(con, pid, themen.NICHTS_ZU_BAUEN):
        letzter[d.get("thema")] = d
    for d in _ereignisse(con, pid, NICHTS_JA):
        ja.setdefault(d.get("thema"), []).append(d)
    aus = {}
    for tid, d in letzter.items():
        if not d.get("an", True):
            continue
        b = (not co or d["von"] in (kern.ENTWICKLER, co)
             or any(x["eid"] > d["eid"] and x["von"] in (kern.ENTWICKLER, co) for x in ja.get(tid, [])))
        aus[tid] = {"grund": d.get("grund") or "", "bestaetigt": b, "von": d["von"]}
    return aus


# --- der Stand der fünf Tore -------------------------------------------------------------------------------------------------

def _meilensteine(con, pid):
    from . import planansicht, themen
    z = planansicht._zustaende(con, pid)
    aus = []
    for b in con.execute("SELECT * FROM bogen WHERE projekt_id = ? AND status IN ('geplant', 'aktiv', 'fertig') ORDER BY nr, id",
                         (pid,)).fetchall():
        pakete = planansicht._pakete(con, pid, b["id"])
        th = {tid for a in pakete for tid in themen.verweise(con, pid, a["id"])}
        th |= {int(x) for x in re.findall(r"\bTH(\d+)\b", b["ziel"] or "")}   # A2030: der Grobplan verweist im Ziel auf Themen
        aus.append({"id": b["id"], "nr": b["nr"], "titel": b["titel"], "status": b["status"], "themen": th,
                    "neu_fertig": b["status"] == "fertig" and _neu_fertig(con, pid, b),
                    "pakete": len(pakete), "fertig": sum(a["status"] == "fertig" for a in pakete),
                    "grob": bool((z.get((b["id"], "grob")) or {}).get("an")), "plan": bool((z.get((b["id"], "plan")) or {}).get("an")),
                    "abschluss": bool((z.get((b["id"], "abschluss")) or {}).get("an"))})
    return aus


def stand(con, pid):
    """{"tore": [{"tor", "name", "zu", "n", "g", "text"}], "aktuell": erstes offenes Tor (oder None), "zeile": Text für eine Zeile,
    "nichts_offen": [Themen mit unbestätigtem Vermerk], "fuer_dich": {"themen", "meilensteine"} – A1972: was auf den Menschen
    wartet}. n/g: was gezählt wird (Text sagt was)."""
    from . import themen
    k = themen.tor(con, pid)
    frei = {t["id"]: t["name"] for t in themen.liste(con, pid) if t["zustand"]["status"] == "frei" and not t["zustand"]["markiert"]}
    nichts = nichts_gilt(con, pid)
    ms = _meilensteine(con, pid)
    in_ms = {tid for m in ms for tid in m["themen"]}
    zugeordnet = {tid for tid in frei if tid in in_ms or (nichts.get(tid) or {}).get("bestaetigt")}
    geplant = [m for m in ms if m["status"] == "geplant"]
    grob_frei = [m for m in geplant if m["grob"]]
    grob_zu = k["konzept_zu"] and bool(frei) and len(zugeordnet) == len(frei) and len(grob_frei) == len(geplant) and bool(ms)
    laufend = [m for m in ms if m["status"] == "aktiv"]
    fertig = [m for m in ms if m["status"] == "fertig"]
    fein_zu = grob_zu and (bool(laufend) or (bool(fertig) and not geplant))
    mit_plan = [m for m in geplant if m["pakete"]]
    um_zu = fein_zu and bool(fertig) and not laufend and not geplant
    p_g = sum(m["pakete"] for m in laufend)
    p_n = sum(m["fertig"] for m in laufend)
    zu_schliessen = [m for m in fertig if m["neu_fertig"]]        # Altbestand vor dem Stichtag zählt nicht
    ab = [m for m in zu_schliessen if m["abschluss"]]
    ab_zu = um_zu and len(ab) == len(zu_schliessen)
    t = [
        {"tor": "konzept", "zu": k["konzept_zu"], "n": k["n"], "g": k["g"], "text": f"{k['n']} von {k['g']} Themen freigegeben"},
        {"tor": "grobplanung", "zu": grob_zu, "n": len(zugeordnet), "g": len(frei), "mn": len(grob_frei), "mg": len(geplant),
         "text": f"{len(zugeordnet)} von {len(frei)} Themen in Meilensteinen"
                 + (f" · {len(grob_frei)} von {len(geplant)} Meilensteinen freigegeben" if geplant else "")},
        {"tor": "feinplanung", "zu": fein_zu, "n": sum(m["plan"] for m in mit_plan), "g": len(mit_plan),
         "text": (f"{sum(m['plan'] for m in mit_plan)} von {len(mit_plan)} Plänen freigegeben – dann „Jetzt starten“" if mit_plan
                  else "noch kein Meilenstein mit Paketen")},
        {"tor": "umsetzung", "zu": um_zu, "n": p_n, "g": p_g, "laufend": bool(laufend), "mn": len(fertig), "mg": len(ms),
         "text": (f"{p_n} von {p_g} Paketen fertig" if laufend else f"{len(fertig)} von {len(ms)} Meilensteinen fertig")},
        {"tor": "abschluss", "zu": ab_zu, "n": len(ab), "g": len(zu_schliessen),
         "text": f"{len(ab)} von {len(zu_schliessen)} Abschlussberichten bestätigt"},
    ]
    for x in t:
        x["name"] = NAMEN[x["tor"]]
    aktuell = next((x for x in t if not x["zu"]), None)
    # A1972 (TH156 Regel 3/5/6): was der Mensch jetzt tun muss – nur Anzahlen für EINE Zeile mit Sprung. Meilensteine nur, wenn
    # der Mensch freigibt (thema_freigabe = mensch); bei co+lead geben Co und Lead das Ja, das ist dann kein Handlungsbedarf.
    ms_dich = 0
    if themen.freigabe_regel(con, pid) != "co+lead":
        ms_dich = (sum(1 for m in geplant if not m["grob"] or (m["pakete"] and not m["plan"]))
                   + sum(1 for m in zu_schliessen if not m["abschluss"] and bericht(con, pid, m["id"]) is not None))
    fuer_dich = {"themen": len(themen.fuer_dich(con, pid)), "meilensteine": ms_dich}
    zeile =(f"{aktuell['name']} · {aktuell['text']}" if aktuell else "Abschluss · alle Tore geschlossen")
    return {"tore": t, "aktuell": aktuell["tor"] if aktuell else None, "zeile": zeile, "fuer_dich": fuer_dich,
            "nichts_offen": [{"id": tid, "name": frei.get(tid, f"TH{tid}"), "grund": d["grund"], "von": d["von"]}
                             for tid, d in sorted(nichts.items()) if not d["bestaetigt"] and tid in frei]}


# --- Abschlussbericht je Meilenstein (gegen die Erfolgskriterien, mit Resten und Lehren) ------------------------------------

def bericht(con, pid, bid):
    """Die Dokument-Nummer des jüngsten Abschlussberichts des Meilensteins oder None."""
    d = [x for x in _ereignisse(con, pid, BERICHT) if x.get("bogen") == bid]
    return d[-1]["dokument"] if d else None


def bericht_text(con, pid, bid):
    from . import aufwand, empfehlung, planansicht
    b = planansicht._bogen(con, pid, bid)
    alle = con.execute("SELECT * FROM aufgabe WHERE projekt_id = ? AND bogen_id = ? ORDER BY rang, id", (pid, bid)).fetchall()
    try:
        zellen = empfehlung.zellen(con, pid)
    except Exception:                                    # noqa: BLE001
        zellen = {}
    z = [f"# Abschlussbericht Meilenstein {b['nr']} „{b['titel']}“", "",
         f"Ziel: {b['ziel'] or '–'}  ", f"Endet mit (Erfolgskriterium): {b['abnahme'] or '–'}  ",
         f"Zieldatum: {b['zieldatum'] or '–'} · "
         + (f"fertig: {(b['fertig_utc'] or '–')[:10]}" if b["status"] == "fertig"
            else "bereit zur Abnahme – fertig mit dem Ja zum Abschluss"),   # A2002
         "", "## Erfolgskriterien", ""]
    offen_k, summe, prog = [], 0.0, 0.0
    fertig = [a for a in alle if a["status"] == "fertig"]
    z.append(f"- Meilenstein: {b['abnahme'] or 'ohne Erfolgskriterium'} – {len(fertig)} von {len([a for a in alle if a['status'] != 'verworfen'])}"
             " Paketen fertig")
    for a in fertig:
        kr = json.loads(a["kriterien"] or "[]") if a["kriterien"] else []
        if kr:
            ok = sum(bool(k.get("erfuellt")) for k in kr)
            z.append(f"- A{a['id']} {a['titel']}: {ok} von {len(kr)} Kriterien erfüllt")
            offen_k += [f"A{a['id']}: {k.get('text')}" for k in kr if not k.get("erfuellt")]
    z += ["", "## Pakete", "", "| Paket | Status | Kosten | Prognose |", "|---|---|---|---|"]
    ueber = []
    for a in alle:
        usd = None
        try:
            m = aufwand.je_aufgabe(con, pid, a["id"]) if a["begonnen_utc"] else None
            usd = round(float(m["usd"]), 2) if m and m.get("usd") else None
        except Exception:                                # noqa: BLE001 – eine Messung darf den Bericht nie verhindern
            usd = None
        p = (zellen.get((empfehlung.GRUPPE.get(a["art"]), a["groesse"])) or {}).get("median") if a["groesse"] and a["art"] else None
        summe += usd or 0
        prog += p or 0
        if usd and p and usd > PROGNOSE_FAKTOR * p:
            ueber.append(f"A{a['id']} kostete {usd:.2f} $ statt ≈ {p:.2f} $")
        z.append(f"| A{a['id']} {a['titel'][:70]} | {a['status']} | {f'{usd:.2f} $' if usd else '–'} | {f'≈ {p:.2f} $' if p else '–'} |")
    z += ["", f"Summe: {summe:.2f} $ gemessen" + (f" · Prognose ≈ {prog:.2f} $" if prog else ""), "", "## Reste", ""]
    reste = [f"verworfen: A{a['id']} {a['titel']}" for a in alle if a["status"] == "verworfen"]
    reste += [f"offenes Kriterium {k}" for k in offen_k]
    reste += [f"nicht fertig: A{a['id']} {a['titel']} ({a['status']})" for a in alle if a["status"] not in ("fertig", "verworfen")]
    z += [f"- {r}" for r in reste] or ["- keine"]
    z += ["", "## Lehren", ""]
    lehren = [f"{r['art']}: {r['text']}" for r in con.execute(
        "SELECT art, text FROM rueckblick WHERE projekt_id = ? AND bogen_id = ? ORDER BY id", (pid, bid))]
    lehren += [f"über Prognose: {u}" for u in ueber]
    rot = con.execute("SELECT count(*) FROM pruefung WHERE aufgabe_id IN (SELECT id FROM aufgabe WHERE bogen_id = ?) AND ergebnis = 'rot'",
                      (bid,)).fetchone()[0]
    if rot:
        lehren.append(f"{rot} Prüfung(en) rot unterwegs")
    z += [f"- {x}" for x in lehren] or ["- keine festgehalten (Rückblick: amw rueckblick)"]
    z += ["", "Bestätigen: Planung › Meilensteine › Abschluss (Ja oder Zurück mit Notiz). Erstellt von der AMW (A1944)."]
    return "\n".join(z) + "\n"


def bericht_erstellen(con, pid, bid, bereit=False):
    """bereit (A2002): der Meilenstein endet mit einem Urteil und alle Pakete sind fertig – der Bericht geht als Meldung „bereit
    zur Abnahme“ an Lead und Co (und an den Menschen, wenn er freigibt); fertig wird der Meilenstein erst mit dem Ja."""
    from . import dokumente, planansicht
    b = planansicht._bogen(con, pid, bid)
    did = dokumente.ablegen_inhalt(con, pid, "AMW", bericht_text(con, pid, bid).encode("utf-8"), f"abschluss-m{b['nr']}.md",
                                   titel=f"Abschlussbericht Meilenstein {b['nr']} „{b['titel'][:80]}“", art="bericht", bogen=bid)
    from . import themen
    an = kern.co_entwickler(con, pid) if themen.freigabe_regel(con, pid) == "co+lead" else None
    if bereit:
        mensch = themen.freigabe_regel(con, pid) != "co+lead"
        wer_ja = "Co-Entwickler und Lead" if not mensch else "der Mensch"
        with db.schreiben(con):
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=BERICHT, bogen_id=bid,
                         text=json.dumps({"bogen": bid, "dokument": did}, ensure_ascii=False))
            for wer in dict.fromkeys(x for x in (kern.lead(con, pid), kern.co_entwickler(con, pid), kern.ENTWICKLER if mensch else None) if x):
                kern._posten(con, pid, "AMW", wer, "meldung", f"Meilenstein {b['nr']} „{b['titel'][:50]}“ bereit zur Abnahme (D{did})",
                             f"Alle Pakete sind fertig. Der Meilenstein endet mit: {b['abnahme']}. Die AMW hat den Abschlussbericht"
                             f" erstellt (D{did}, mit Resten und Lehren). Fertig wird der Meilenstein erst mit dem Ja zum Abschluss"
                             f" ({wer_ja}): Planung › Meilensteine (Ja oder Zurück mit Notiz) oder amw bogen freigeben {bid} --art abschluss.")
        return did
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=BERICHT, bogen_id=bid,
                     text=json.dumps({"bogen": bid, "dokument": did}, ensure_ascii=False))
        for wer in [x for x in (kern.ENTWICKLER if not an else None, an, kern.lead(con, pid) if an else None) if x]:
            kern._posten(con, pid, "AMW", wer, "info", f"Abschlussbericht Meilenstein {b['nr']} „{b['titel'][:50]}“ (D{did})",
                         f"Der Meilenstein ist fertig. Die AMW hat den Bericht gegen die Erfolgskriterien erstellt (D{did}, mit Resten"
                         " und Lehren). Das Tor Abschluss schließt mit dem Ja dazu: Planung › Meilensteine (Ja oder Zurück mit Notiz).")
    return did


# --- Umsetzung: Prognose überschritten → Lead (einmal je Paket) -------------------------------------------------------------

def _paar(con, aid, messung):
    """Modell/Effort eines Pakets: aus dem p-Paket, sonst das Modell/Stufe mit den meisten Kosten der Sitzungen – oder None."""
    from . import arbeitspaket, eignung
    try:
        f = arbeitspaket.lesen(con, aid)
    except Exception:                                    # noqa: BLE001 – kein p-Paket
        f = None
    if f and f.get("art") == "p" and f.get("modell") and f.get("effort"):
        return f"{eignung.kurz(f['modell'])}/{f['effort']}"
    meist = ((messung or {}).get("modelle") or [None])[0]
    if not meist:
        return None
    m, _, st = meist.partition("/")
    return f"{eignung.kurz(m)}/{st}" if st else None


def prognose(con, pid, a, messung, zellen, eig):
    """A1971: Prognose eines Pakets = Median gleicher Größe und Art (Gruppe × Größe) – mit gleichem Modell/Effort, wenn die
    Eignungstabelle dafür mindestens eignung.MIN_N Messungen hat, sonst über alle Modelle der Zelle. (usd, Grundlage) | None."""
    from . import eignung, empfehlung
    zelle = (empfehlung.GRUPPE.get(a["art"]), a["groesse"])
    paar = _paar(con, a["id"], messung)
    w = (eig.get(zelle) or {}).get(paar) if paar else None
    if w and w["n"] >= eignung.MIN_N and w.get("kosten_median"):
        return w["kosten_median"], f"{paar}, n = {w['n']}"
    z = zellen.get(zelle) or {}
    return (z["median"], f"alle Modelle, n = {z.get('n')}") if z.get("median") else None


def prognose_pruefen(con, pid):
    """Umsetzung (TH154): nur OFFENE Pakete (wartet/laeuft/blockiert) eines aktiven Meilensteins über PROGNOSE_FAKTOR × Prognose
    wecken den Lead – einmal je Paket; fertige oder verworfene nie (A1971: die erste Runde meldete längst fertige)."""
    from . import aufwand, eignung, empfehlung
    lead = kern.lead(con, pid)
    if not lead:
        return []
    schon = {d.get("aufgabe") for d in _ereignisse(con, pid, UEBER)}
    try:
        zellen = empfehlung.zellen(con, pid)
    except Exception:                                    # noqa: BLE001
        return []
    eig = None
    aus = []
    offen = ",".join("?" * len(kern.OFFEN_STATUS))
    for a in con.execute("SELECT a.* FROM aufgabe a JOIN bogen b ON b.id = a.bogen_id WHERE a.projekt_id = ? AND b.status = 'aktiv'"
                         f" AND a.status IN ({offen}) AND a.begonnen_utc IS NOT NULL", (pid, *kern.OFFEN_STATUS)).fetchall():
        if a["id"] in schon or not (a["groesse"] and a["art"]) or a["art"] not in empfehlung.GRUPPE:
            continue
        try:
            m = aufwand.je_aufgabe(con, pid, a["id"])
        except Exception:                                # noqa: BLE001
            continue
        usd = float(m["usd"]) if m and m.get("usd") else 0
        if not usd:
            continue
        if eig is None:
            try:
                eig = eignung.tabelle(con, pid)
            except Exception:                            # noqa: BLE001
                eig = {}
        pg = prognose(con, pid, a, m, zellen, eig)
        if not pg:
            continue
        p, grundlage = pg
        if usd <= PROGNOSE_FAKTOR * p:
            continue
        with db.schreiben(con):
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=UEBER, aufgabe_id=a["id"],
                         text=json.dumps({"aufgabe": a["id"], "usd": round(usd, 2), "prognose": p}, ensure_ascii=False))
            kern._posten(con, pid, "AMW", lead, "meldung", f"A{a['id']} über Prognose: {usd:.2f} $ statt ≈ {p:.2f} $"[:140],
                         f"A{a['id']} „{a['titel']}“ ({a['groesse']} · {a['art']}) kostet bisher {usd:.2f} $ – mehr als"
                         f" {PROGNOSE_FAKTOR:g} × Prognose (≈ {p:.2f} $, Median gleicher Größe und Art, {grundlage}). Abweichung in der Umsetzung"
                         " (TH154): weiterlaufen lassen, neu schneiden oder anhalten?", aufgabe_id=a["id"])
        aus.append(f"A{a['id']} über Prognose")
    return aus


# --- Dienst-Runde ------------------------------------------------------------------------------------------------------------

def runde(con, pid):
    """Berichte für fertige Meilensteine ohne Bericht, Prognose-Abweichungen, Wechsel der Tore festhalten. Rückgabe: Texte."""
    aus = []
    if seit(con, pid) is None:                       # erste Runde: Stichtag – was vorher fertig war, ist Altbestand
        with db.schreiben(con):
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=SEIT,
                         text=json.dumps({"seit": db.jetzt()}, ensure_ascii=False))
    for b in con.execute("SELECT * FROM bogen WHERE projekt_id = ? AND status = 'fertig' ORDER BY id", (pid,)).fetchall():
        bid = b["id"]
        if not _neu_fertig(con, pid, b):
            continue
        if bericht(con, pid, bid) is None and con.execute("SELECT 1 FROM aufgabe WHERE bogen_id = ? LIMIT 1", (bid,)).fetchone():
            aus.append(f"Abschlussbericht M{bid}: D{bericht_erstellen(con, pid, bid)}")
    aus += prognose_pruefen(con, pid)
    s = stand(con, pid)
    zuletzt = {}
    for d in _ereignisse(con, pid, STAND):
        zuletzt[d.get("tor")] = d.get("zu")
    for x in s["tore"][1:]:                              # Konzept hält A1913 selbst fest
        if bool(zuletzt.get(x["tor"])) != x["zu"] and (x["zu"] or x["tor"] in zuletzt):
            with db.schreiben(con):
                db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=STAND,
                             text=json.dumps({"tor": x["tor"], "zu": x["zu"], "womit": x["text"]}, ensure_ascii=False))
            aus.append(f"Tor {x['name']} {'geschlossen' if x['zu'] else 'wieder offen'}")
    return aus
