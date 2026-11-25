"""A2142: „Für dich“ – alles, was der Mensch tun muss, genau einmal. Nur lesend; Grundlage der Seite (A2113).

sammeln(con, pid) → {"eintraege": [...], "zahl": n, "fehler": [{"quelle", "text"}]}. Nichts wird hier neu entschieden: ob etwas auf den
Menschen wartet, sagen die Module, die den Weg führen; hier kommt es zusammen.

Eintrag: {"art": frage|thema|grob|plan|aenderung|start|abnahme|aufgabe|pruefpunkt|vorschlag|eigene|nachricht,
 "id": Kürzel zum Anzeigen (F12, TH3, G2 = Grobplan Fassung 2, M4 = Projektnummer, A7, N99, „M4-entwurf“ = Spezifikation, sonst die
       Kennung); mit art zusammen eindeutig,
 "titel", "was": beantworten|freigeben|abnehmen|testen|starten|lesen|erledigen, "seit_utc",
 "ziel": {"sicht", "nr", …} – nr ist die interne Nummer des Dings (Meilenstein: bogen.id, Grobplan: Fassung, Agent: Kennung); sicht
         „aufgabe“ und „agent“ sind die Dialoge, alles andere eine Seite, "blockiert": bool (nur Fragen)}

Reihenfolge: blockierende Fragen, dann Freigaben und Abnahmen, dann der Rest; innen die ältesten zuerst. Steht ein Ding in zwei Quellen,
gilt die erste (QUELLEN). Scheitert eine Quelle, stehen die anderen da, und sie steht in "fehler". Nie dabei: was der Lead klärt oder Co
und Lead freigeben, was auf Auslieferung wartet, was der Mensch zurückgegeben hat (bis es neu vorliegt), Kleinproben, Infos.
"""
import logging
import re

from . import einmal, kern, planung

FREIGABEN = ("thema", "grob", "plan", "aenderung", "start", "abnahme", "aufgabe", "pruefpunkt")
KLEINPROBE = re.compile(r"(?:[^:–]{0,60}[:–]\s*)?Kleinproben?(?![-\w])", re.IGNORECASE)      # „Kleinprobe …“ oder „Seite: Kleinprobe“
# Meldungen, die nur sagen, was ein Eintrag schon zeigt (tore, grobplan, feinplanung, urteil, planung, kern)
M_BEREIT = re.compile(r"Meilenstein (\d+) .*bereit zur Abnahme \(D")
M_GROB = re.compile(r"Grobplan Fassung \d+: \d+ Meilensteine")
M_FEIN = re.compile(r"Feinplan (M\d+(?:, M\d+)*) Fassung \d+: \d+ Pakete angelegt")
M_AUFGABE = re.compile(r"A(\d+) bereit zur Abnahme\b")
M_PLAN = re.compile(r"Plan für A(\d+) zur Freigabe")
M_FRAGE = re.compile(r"Frage F(\d+)\b")


def _eintrag(ding, art, kuerzel, titel, was, seit, ziel, blockiert=False):
    """ding: woran „genau einmal“ hängt – dasselbe Ding aus zwei Quellen hat denselben Wert (nur intern)."""
    return ding, {"art": art, "id": str(kuerzel), "titel": titel, "was": was, "seit_utc": seit, "ziel": ziel, "blockiert": bool(blockiert)}


def _mensch_gibt(con, pid, stufe):
    """Gibt der Mensch diese Stufe frei (A2032)? Sonst Co und Lead."""
    from . import projektweg
    return kern.entwickler_name(con, pid) in projektweg._freigebende(con, pid, stufe)


def _wert(con, sql, *par):
    r = con.execute(sql, par).fetchone()
    return r[0] if r else None


# --- die Quellen ---------------------------------------------------------------------------------------------------------------
# je Quelle (con, pid, merk) → [(ding, eintrag)]; merk: was die Nachrichten von den anderen Quellen wissen müssen

def _fragen(con, pid, merk):
    from . import fragentopf
    return [_eintrag(f"F{f['id']}", "frage", f"F{f['id']}", f["kurz"], "beantworten", f["zeit_utc"], {"sicht": "fragen", "nr": f["id"]},
                     fragentopf.blockiert(con, pid, f["id"])) for f in kern.offene_fragen(con, pid, an="entwickler")]


def _themen(con, pid, merk):
    from . import themen
    aus, mensch = [], _mensch_gibt(con, pid, "thema")
    for t in themen.fuer_dich(con, pid):
        if t["status"] != "dich" or not (mensch or t.get("nur_mensch")):
            continue
        seit = _wert(con, "SELECT max(f.zeit_utc, coalesce(t.bestaetigt_utc, '')) FROM thema t JOIN thema_fassung f ON f.thema_id = t.id"
                          " WHERE t.id = ? ORDER BY f.nr DESC LIMIT 1", t["id"])
        aus.append(_eintrag(f"TH{t['id']}", "thema", f"TH{t['id']}", t["name"], "freigeben", seit, {"sicht": "themen", "nr": t["id"]}))
    return aus


def _grob(con, pid, merk):
    """Der Grobplan: die neueste Fassung, solange sie gilt und keiner angenommen ist."""
    from . import projektweg_seite
    g = projektweg_seite.grob(con, pid)
    if not g["fassungen"] or g["angenommen"] or g["laeuft"] or g["fassungen"][-1]["fehler"] or not _mensch_gibt(con, pid, "grob"):
        return []
    f = g["fassungen"][-1]
    return [_eintrag("G", "grob", f"G{f['fassung']}", f"Grobplan Fassung {f['fassung']}", "freigeben", f["zeit_utc"],
                     {"sicht": "projektweg", "schritt": "grob", "nr": f["fassung"]})]


def _abnahmen(con, pid, merk):
    from . import planansicht, projektweg, projektweg_seite, tore
    karten = projektweg_seite.abschluss(con, pid, projektweg.freigaben(con, pid))
    aus, noch_dran = [], set()
    if _mensch_gibt(con, pid, "abschluss"):
        z = planansicht._zustaende(con, pid)
        berichte = {}
        for e in tore._ereignisse(con, pid, tore.BERICHT):
            berichte[e.get("bogen")] = e
        for x in karten:
            if not x["bei_dir"] or x["frei"]:
                continue
            if x["lage"] != "abnehmbar":
                noch_dran.add(x["bogen"])                        # niemand holt die Prüfung nach: seine Meldung bleibt stehen
                continue
            v, b = z.get((x["bogen"], "abschluss")) or {}, berichte.get(x["bogen"]) or {}
            if v.get("notiz") and b.get("eid", 0) < v["id"]:
                continue                                         # zurückgegeben, noch kein neuer Bericht: der Lead ist dran
            aus.append(_eintrag(("bogen", x["bogen"]), "abnahme", f"M{x['nr']}", x["titel"], "abnehmen", b.get("zeit_utc"),
                                {"sicht": "projektweg", "schritt": "abschluss", "nr": x["bogen"]}))
    merk["noch_dran"] = noch_dran
    return aus


def _veroeffentlichung(con, pid, merk):
    """A1928: fertige Meilensteine, nach deren Abnahme die AMW veröffentlicht."""
    from . import veroeffentlichung
    return [_eintrag(("bogen", b["id"]), "abnahme", f"M{b['nr']}", b["titel"], "abnehmen", b["fertig_utc"], {"sicht": "start", "nr": b["id"]})
            for b in veroeffentlichung.zur_abnahme(con, pid)]


def _fein(con, pid, merk):
    """Feinpläne (vorher ihr Meilenstein, wenn er noch nicht frei ist), Änderungen und was aus einer Änderung noch zu starten ist."""
    from . import planansicht, projektweg, projektweg_seite
    f = projektweg_seite.fein(con, pid, projektweg.freigaben(con, pid))
    z = planansicht._zustaende(con, pid)
    aus = []
    for m in f["meilensteine"]:
        bid = m["bogen"]
        if m["status"] != "geplant" or m["laeuft"] or not m["pakete"]:
            continue
        seit, stand = con.execute("SELECT max(angelegt_utc), max(geaendert_utc) FROM aufgabe WHERE bogen_id = ? AND status != 'verworfen'", (bid,)).fetchone()
        ziel = {"sicht": "projektweg", "schritt": "fein", "nr": bid}
        if m["delta_start"]:
            aus.append(_eintrag(("bogen", bid), "start", f"M{m['nr']}", m["titel"], "starten", seit, {**ziel, "thema": m["delta_start"]["thema"]}))
            continue
        if m["frei"]:
            continue
        art = "plan" if (z.get((bid, "grob")) or {}).get("an") else "grob"       # erst der Meilenstein, dann sein Plan
        v = z.get((bid, art)) or {}
        zurueck = v.get("notiz") and (stand or "") <= v["zeit_utc"]              # zurückgegeben, seitdem nichts geändert: der Lead ist dran
        if not zurueck and _mensch_gibt(con, pid, art):
            aus.append(_eintrag(("bogen", bid), art, f"M{m['nr']}", m["titel"], "freigeben", seit, ziel if art == "plan" else {"sicht": "planung", "nr": bid}))
    ich = kern.entwickler_name(con, pid)
    for x in f["delta"]:
        if ich in x["wer"]:
            aus.append(_eintrag(f"E{x['eid']}", "aenderung", f"TH{x['thema']}", x["name"], "freigeben", x["zeit_utc"],
                                {"sicht": "projektweg", "schritt": "fein", "nr": x["eid"], "thema": x["thema"]}))
    return aus


def _kleinprobe(con, pid, a):
    """Nimmt der Co sie ab? Ausdrücklich (aufgabe.verantwortlich) oder als Kleinprobe nach dem Titel; ohne Co bleibt sie beim Menschen."""
    co = kern.co_entwickler(con, pid)
    if not co or a["verantwortlich"] == planung.MENSCH:
        return False
    return a["verantwortlich"] == co or bool(KLEINPROBE.match(a["titel"]))


def _aufgaben(con, pid, merk):
    from . import urteil
    aus = []
    for x in urteil.zur_abnahme(con, pid):
        a = con.execute("SELECT * FROM aufgabe WHERE id = ?", (x["id"],)).fetchone()
        if not x["pruefpunkt"] and _kleinprobe(con, pid, a):
            continue
        if x["grund_art"] == "gemeldet":
            seit = urteil._letztes(con, x["id"], urteil.BEREIT)["zeit_utc"]
        else:
            tab, spalte = {"pruefung": ("pruefung", "coalesce(ergebnis_utc, angefragt_utc)"), "dokument": ("dokument", "angelegt_utc")}[x["grund_art"]]
            seit = _wert(con, f"SELECT {spalte} FROM {tab} WHERE id = ?", int(x["grund_ref"][1:]))
        aus.append(_eintrag(f"A{x['id']}", "pruefpunkt" if x["pruefpunkt"] else "aufgabe", f"A{x['id']}", x["titel"],
                            "testen" if x["pruefpunkt"] else "abnehmen", seit, {"sicht": "aufgabe", "nr": x["id"]}))
    return aus


def _startvorschlaege(con, pid, merk):
    from . import steuerung
    aus = []
    for v in steuerung.startvorschlaege(con, pid):
        seit = _wert(con, "SELECT s.beendet_utc FROM sitzung s JOIN agent g ON g.id = s.agent_id WHERE g.projekt_id = ? AND g.kennung = ?"
                          " ORDER BY s.id DESC LIMIT 1", pid, v["kennung"])
        seit = seit or _wert(con, "SELECT angelegt_utc FROM aufgabe WHERE id = ?", v["aufgabe"])
        aus.append(_eintrag(f"@{v['kennung']}", "vorschlag", v["kennung"], f"{v['kennung']}: {v['text']}", "starten", seit,
                            {"sicht": "agent", "nr": v["kennung"]}))
    return aus


def _planung(con, pid, merk):
    """Vorgelegte Spezifikationen und Pläne, für die er verantwortlich ist, und seine eigenen Aufgaben (ohne geparkte)."""
    p, aus = planung.freigaben_offen(con, pid), []
    if not (kern.projekt_wahl(con, pid, "spec_frei") == "lead" and kern.lead(con, pid)):
        for s in p["spezifikationen"]:
            nr = _wert(con, "SELECT nr FROM bogen WHERE id = ?", s["bogen_id"])
            aus.append(_eintrag(f"S{s['bogen_id']}-{s['teil']}", "plan", f"M{nr}-{s['teil']}", s["titel"], "freigeben", s["geaendert_utc"],
                                {"sicht": "planung", "nr": s["bogen_id"], "teil": s["teil"]}))
    for a in p["plaene"]:
        aus.append(_eintrag(f"A{a['id']}", "plan", f"A{a['id']}", a["titel"], "freigeben", a["geaendert_utc"], {"sicht": "aufgabe", "nr": a["id"]}))
    for a in p["eigene"]:
        r = con.execute("SELECT angelegt_utc, einstufung FROM aufgabe WHERE id = ?", (a["id"],)).fetchone()
        if r["einstufung"] != "geparkt":
            aus.append(_eintrag(f"A{a['id']}", "eigene", f"A{a['id']}", a["titel"], "erledigen", r["angelegt_utc"], {"sicht": "aufgabe", "nr": a["id"]}))
    return aus


def _dargestellt(con, pid, n, dinge, noch_dran):
    """Sagt diese Nachricht nur, was ein Eintrag schon zeigt? dinge: {ding: art}; noch_dran: Meilensteine, die ohne Abnahme-Eintrag beim
    Menschen liegen (None: die Quelle ist gescheitert – dann bleibt die Meldung stehen)."""
    kurz, bezug = n["kurz"], n["bezug"] or ""
    if n["von"] == "AMW":
        if m := M_BEREIT.match(kurz):
            bid = int(bezug[1:]) if re.fullmatch(r"M\d+", bezug) else _bogen(con, pid, m.group(1))    # Altbestand ohne Bezug: die Nummer im Text
            return bid is not None and (("bogen", bid) in dinge or (noch_dran is not None and bid not in noch_dran))
        if M_GROB.match(kurz):
            return "G" in dinge
        if m := M_FEIN.match(kurz):
            return any(("bogen", _bogen(con, pid, x[1:])) in dinge for x in m.group(1).split(", "))
        if m := M_AUFGABE.match(kurz):
            return dinge.get(f"A{m.group(1)}") in ("aufgabe", "pruefpunkt")
        if bezug[:1] == "F" and bezug in dinge:
            return True
    if m := M_PLAN.match(kurz):
        return dinge.get(f"A{m.group(1)}") in ("plan", "aufgabe", "pruefpunkt")
    m = M_FRAGE.match(kurz)
    return bool(m) and f"F{m.group(1)}" in dinge


def _bogen(con, pid, nr):
    return _wert(con, "SELECT id FROM bogen WHERE projekt_id = ? AND nr = ? ORDER BY id LIMIT 1", pid, int(nr))


def _nachrichten(con, pid, merk):
    """Was beim Menschen zählt (workbench.ZAEHLT, wie workbench.an_dich_zahl), soweit es kein anderer Eintrag zeigt."""
    from . import workbench
    aus = []
    for n in con.execute("SELECT n.id, n.zeit_utc, n.von, n.art, n.kurz, n.bezug FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id WHERE n.projekt_id = ?"
                         f" AND e.agent = ? AND e.status != 'erledigt' AND {workbench.ZAEHLT}"
                         " AND n.id NOT IN (SELECT v.nachricht_id FROM frage_verlauf v WHERE v.nachricht_id IS NOT NULL) ORDER BY n.id",
                         (pid, planung.MENSCH)).fetchall():
        if not _dargestellt(con, pid, n, merk["dinge"], merk.get("noch_dran")):
            aus.append(_eintrag(f"N{n['id']}", "nachricht", f"N{n['id']}", n["kurz"], "beantworten" if n["art"] == "frage" else "lesen", n["zeit_utc"],
                                {"sicht": "nachrichten", "nr": n["id"]}))
    return aus


# Reihenfolge = Vorrang bei Doppelten; die Nachrichten zuletzt (sie sehen, was schon dasteht)
QUELLEN = (("fragen", _fragen), ("themen", _themen), ("grob", _grob), ("abnahmen", _abnahmen), ("veroeffentlichung", _veroeffentlichung), ("fein", _fein),
           ("aufgaben", _aufgaben), ("startvorschlaege", _startvorschlaege), ("planung", _planung), ("nachrichten", _nachrichten))


def _rang(e):
    gruppe = 0 if e["art"] == "frage" and e["blockiert"] else 1 if e["art"] in FREIGABEN else 2
    return gruppe, e["seit_utc"] or "9", e["art"], len(e["id"]), e["id"]


def sammeln(con, pid):
    eintraege, fehler, dinge = [], [], {}
    merk = {"dinge": dinge}
    with einmal.merken(con):
        for name, quelle in QUELLEN:
            try:
                neu = quelle(con, pid, merk)
            except Exception as x:                               # noqa: BLE001 – die anderen Quellen gehen auch ohne, aber nicht still
                text = f"{type(x).__name__}: {x}"
                logging.getLogger("amw.fuer_dich").warning("%s: %s", name, text)
                fehler.append({"quelle": name, "text": text[:300]})
                continue
            for ding, e in neu:
                if ding not in dinge:
                    dinge[ding] = e["art"]
                    eintraege.append(e)
    eintraege.sort(key=_rang)
    return {"eintraege": eintraege, "zahl": len(eintraege), "fehler": fehler}
