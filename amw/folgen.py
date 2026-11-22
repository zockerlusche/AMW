"""Folgenprüfung vor der eigenen Änderung des Menschen (K8b / A1957, F5358/F5359, Änderungsgrenze F5353, TH163/TH164).

Ändert der Mensch selbst einen Meilenstein (Titel, Ziel, Abnahme, Zieldatum) oder ein Paket (Titel, Auftrag, Kriterien,
Meilenstein), gilt die Änderung nicht sofort: Die AMW trägt sie als Vorschlag ein, ein frischer claude -p (nur Lesen, Modell wie
themen_gegenlesen, feste Frist, Kosten im Ereignis) liest Änderung und alles darunter und antwortet mit JSON
{"beruehrt_ziel", "beruehrt_erfolg", "beruehrt_kosten", "folgen": [...]}. Berührt sie nichts davon, gilt sie von selbst (F5353)
und der Mensch bekommt die Folgen als Info; sonst zeigt die Planung alt → neu mit den Folgen und sie gilt erst mit Ja (sonst
Verwerfen). Frist oder Fehler des Prüfers: sie bleibt Vorschlag – „Prüfung fehlgeschlagen – Ja übernimmt trotzdem“. Die Seite
zeigt sofort „wird geprüft“. Ist themen_gegenlesen = aus (oder in Tests AMW_FOLGEN_AUS), gilt die Änderung wie bisher sofort.

Ereignisse (plan_ereignis, ohne Schemaänderung):
  aenderung_vorgeschlagen {"ebene": "meilenstein"|"paket", "id", "alt": {...}, "neu": {...}, "grund"}
  aenderung_geprueft      {"aenderung", "beruehrt_ziel", "beruehrt_erfolg", "beruehrt_kosten", "folgen", "modell", "usd", "lauf", "fehler"}
  aenderung_entschieden   {"aenderung", "gilt": true|false, "automatisch": true|false}
"""
import json
import os
import subprocess
import sys
import tempfile
import time

from . import db, kern

VORGESCHLAGEN, GEPRUEFT, ENTSCHIEDEN = "aenderung_vorgeschlagen", "aenderung_geprueft", "aenderung_entschieden"
FELDER = {"meilenstein": ("titel", "ziel", "abnahme", "zieldatum"), "paket": ("titel", "auftrag", "kriterien", "bogen_id")}
NAMEN = {"titel": "Titel", "ziel": "Ziel", "abnahme": "Abnahme", "zieldatum": "Zieldatum", "auftrag": "Auftrag", "kriterien": "Kriterien",
         "bogen_id": "Meilenstein"}
EINSTIEG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "amw-folgen.py")
OHNE_FENSTER = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FRIST_S = 10 * 60
LAEUFT_H = 1
AUFTRAG = (
    "Du prüfst die Folgen einer Änderung, die der Mensch an der Planung eines Software-Projekts machen will. Lies aenderung.md "
    "(was sich ändert: alt → neu) und darunter.md (was davon abhängt: Pakete, Themen, Ziele). Beurteile: Berührt die Änderung ein "
    "Ziel, ein Erfolgskriterium (Abnahme) oder den Kostenrahmen (mehr Arbeit, mehr Pakete, teurere Pakete)? Nenne die konkreten "
    "Folgen für die Pakete darunter (je Folge ein kurzer Satz mit der A-Nummer). Antworte NUR mit einem JSON-Objekt: "
    '{"beruehrt_ziel": true|false, "beruehrt_erfolg": true|false, "beruehrt_kosten": true|false, "folgen": ["…"]}. '
    "Du änderst nichts, du schreibst keine Dateien, du führst nichts aus.")


class FolgenFehler(kern.AmwFehler):
    pass


def modell(con, pid):
    return kern.projekt_wahl(con, pid, "themen_gegenlesen")


def _aus(con, pid):
    return bool(os.environ.get("AMW_FOLGEN_AUS")) or modell(con, pid) == "aus"


def _ereignisse(con, pid, art):
    aus = []
    for r in con.execute("SELECT id, von, zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id", (pid, art)):
        try:
            aus.append({"eid": r["id"], "von": r["von"], "zeit_utc": r["zeit_utc"], **json.loads(r["text"])})
        except ValueError:
            continue
    return aus


def _ereignis(con, pid, von, art, **werte):
    return db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=art,
                        text=json.dumps(werte, ensure_ascii=False))


def _alt(con, pid, ebene, oid):
    if ebene == "meilenstein":
        r = con.execute("SELECT * FROM bogen WHERE id = ? AND projekt_id = ?", (oid, pid)).fetchone()
        if not r:
            raise FolgenFehler(f"Meilenstein {oid} gibt es nicht")
        return {k: r[k] for k in FELDER["meilenstein"]}
    r = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (oid, pid)).fetchone()
    if not r:
        raise FolgenFehler(f"A{oid} gibt es nicht")
    krit = [k.get("text") for k in json.loads(r["kriterien"] or "[]")] if r["kriterien"] else []
    return {"titel": r["titel"], "auftrag": r["auftrag"], "kriterien": krit, "bogen_id": r["bogen_id"]}


def _anwenden(con, pid, v):
    from . import planung
    n = v["neu"]
    if v["ebene"] == "meilenstein":
        planung.bogen_aendern(con, pid, kern.ENTWICKLER, v["id"], n.get("titel"), n.get("ziel"), n.get("abnahme"), n.get("zieldatum"),
                              grund=v.get("grund"))
    else:
        planung.schritt_setzen(con, pid, kern.ENTWICKLER, aid=v["id"], **{k: n[k] for k in n})


def vorschlagen(con, pid, von, ebene, oid, grund=None, **neu):
    """Die eigene Änderung des Menschen als Vorschlag (nur geänderte Felder). Rückgabe {"aenderung": eid, "stand": ...}:
    "gilt" (Prüfung aus – sofort angewendet), "prueft" (Prüfer angestoßen) oder "unveraendert"."""
    if von != kern.ENTWICKLER:
        raise FolgenFehler("Die Folgenprüfung gilt für die eigene Änderung des Menschen")
    if ebene not in FELDER:
        raise FolgenFehler("Ebene: meilenstein | paket")
    alt = _alt(con, pid, ebene, oid)
    neu = {k: v for k, v in neu.items() if k in FELDER[ebene] and v is not None and v != alt.get(k)}
    if not neu:
        return {"aenderung": None, "stand": "unveraendert"}
    v = {"ebene": ebene, "id": oid, "alt": {k: alt.get(k) for k in neu}, "neu": neu, "grund": grund}
    if _aus(con, pid):                                  # wie bisher: gilt sofort
        _anwenden(con, pid, v)
        return {"aenderung": None, "stand": "gilt"}
    with db.schreiben(con):
        eid = _ereignis(con, pid, von, VORGESCHLAGEN, **v)
    try:
        STARTER(pid, eid)
    except OSError as e:
        abschliessen(con, pid, eid, None, fehler=f"Prüfer ließ sich nicht starten: {e}")
    return {"aenderung": eid, "stand": "prueft"}


def _spawn(pid, eid):
    befehl = [sys.executable, "-I", "-X", "utf8", EINSTIEG, "--projekt-id", str(pid), "--aenderung", str(eid)]
    flags = (0x00000008 | 0x00000200 | OHNE_FENSTER) if os.name == "nt" else 0
    return subprocess.Popen(befehl, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                            creationflags=flags, start_new_session=os.name != "nt").pid


STARTER = _spawn             # Tests setzen eine Attrappe


def vorschlag(con, pid, eid):
    v = next((x for x in _ereignisse(con, pid, VORGESCHLAGEN) if x["eid"] == eid), None)
    if not v:
        raise FolgenFehler(f"Änderung Ä{eid} gibt es nicht")
    return v


def _pruefung(con, pid, eid):
    p = [x for x in _ereignisse(con, pid, GEPRUEFT) if x.get("aenderung") == eid]
    return p[-1] if p else None


def _entschieden(con, pid, eid):
    return next((x for x in _ereignisse(con, pid, ENTSCHIEDEN) if x.get("aenderung") == eid), None)


def pruefen(ergebnis):
    """Das JSON des Prüfers prüfen und vereinheitlichen (oder FolgenFehler)."""
    if isinstance(ergebnis, str):
        s = ergebnis.strip()
        a, b = s.find("{"), s.rfind("}")
        try:
            ergebnis = json.loads(s[a:b + 1] if 0 <= a < b else s)
        except ValueError as e:
            raise FolgenFehler(f"kein JSON: {e}") from None
    if not isinstance(ergebnis, dict):
        raise FolgenFehler("oben muss ein Objekt stehen")
    aus = {}
    for k in ("beruehrt_ziel", "beruehrt_erfolg", "beruehrt_kosten"):
        if not isinstance(ergebnis.get(k), bool):
            raise FolgenFehler(f"{k}: true oder false")
        aus[k] = ergebnis[k]
    f = ergebnis.get("folgen") or []
    if not isinstance(f, list) or not all(isinstance(x, str) for x in f):
        raise FolgenFehler("folgen: Liste von Sätzen")
    aus["folgen"] = [x.strip()[:300] for x in f if x.strip()][:30]
    return aus


def abschliessen(con, pid, eid, ergebnis, modell_=None, usd=None, lauf=None, fehler=None):
    """Ergebnis des Prüfers eintragen. Nichts berührt → die Änderung gilt von selbst (Info mit Folgen an den Menschen); sonst
    oder bei Fehler/Frist bleibt sie Vorschlag und wartet auf das Ja des Menschen."""
    v = vorschlag(con, pid, eid)
    if _entschieden(con, pid, eid):
        return None
    if not fehler:
        try:
            e = pruefen(ergebnis)
        except FolgenFehler as x:
            fehler = f"Antwort des Prüfers unbrauchbar: {x}"
    with db.schreiben(con):
        _ereignis(con, pid, "AMW", GEPRUEFT, aenderung=eid, modell=modell_, usd=usd, lauf=lauf, fehler=fehler,
                  **({} if fehler else e))
    was = _was(con, pid, v)
    if fehler:
        with db.schreiben(con):
            kern._posten(con, pid, "AMW", kern.ENTWICKLER, "info", f"Folgenprüfung ging nicht: {was}",
                         f"{fehler}\nDie Änderung wartet als Vorschlag – Ja übernimmt sie trotzdem (Planung › Meilensteine).")
        return "wartet"
    if not (e["beruehrt_ziel"] or e["beruehrt_erfolg"] or e["beruehrt_kosten"]):
        _anwenden(con, pid, v)
        with db.schreiben(con):
            _ereignis(con, pid, "AMW", ENTSCHIEDEN, aenderung=eid, gilt=True, automatisch=True)
            kern._posten(con, pid, "AMW", kern.ENTWICKLER, "info", f"Änderung gilt: {was}",
                         "Ziel, Erfolgskriterien und Kosten sind nicht berührt (F5353). Folgen:\n"
                         + ("\n".join(f"- {x}" for x in e["folgen"]) or "- keine"))
        return "gilt"
    with db.schreiben(con):
        kern._posten(con, pid, "AMW", kern.ENTWICKLER, "info", f"Änderung wartet auf dein Ja: {was}",
                     "Berührt: " + ", ".join(n for k, n in (("beruehrt_ziel", "Ziel"), ("beruehrt_erfolg", "Erfolgskriterien"),
                                                             ("beruehrt_kosten", "Kosten")) if e[k])
                     + ". Folgen:\n" + ("\n".join(f"- {x}" for x in e["folgen"]) or "- keine") + "\nPlanung › Meilensteine: Ja oder Verwerfen.")
    return "wartet"


def _was(con, pid, v):
    if v["ebene"] == "meilenstein":
        r = con.execute("SELECT nr, titel FROM bogen WHERE id = ?", (v["id"],)).fetchone()
        ziel = f"Meilenstein {r['nr']} „{r['titel'][:50]}“" if r else f"Meilenstein {v['id']}"
    else:
        r = con.execute("SELECT titel FROM aufgabe WHERE id = ?", (v["id"],)).fetchone()
        ziel = f"A{v['id']} „{(r['titel'] if r else '')[:50]}“"
    return ziel + " – " + ", ".join(NAMEN[k] for k in v["neu"])


def entscheiden(con, pid, von, eid, ja):
    """Ja (die Änderung gilt) oder Verwerfen – nur der Mensch, je Vorschlag einmal."""
    if von != kern.ENTWICKLER:
        raise FolgenFehler("Über die eigene Änderung entscheidet der Mensch")
    v = vorschlag(con, pid, eid)
    if _entschieden(con, pid, eid):
        raise FolgenFehler(f"Ä{eid} ist schon entschieden")
    if ja:
        _anwenden(con, pid, v)
    with db.schreiben(con):
        _ereignis(con, pid, von, ENTSCHIEDEN, aenderung=eid, gilt=bool(ja), automatisch=False)
    return "gilt" if ja else "verworfen"


def offene(con, pid):
    """Vorschläge ohne Entscheidung, für die Planung: {"aenderung", "ebene", "id", "was", "alt", "neu", "stand": "prueft"|"wartet"|
    "fehler", "seit_utc", "beruehrt": [...], "folgen", "fehler", "usd"}."""
    import datetime
    entsch = {x.get("aenderung") for x in _ereignisse(con, pid, ENTSCHIEDEN)}
    aus = []
    for v in _ereignisse(con, pid, VORGESCHLAGEN):
        if v["eid"] in entsch:
            continue
        p = _pruefung(con, pid, v["eid"])
        stand = "prueft" if not p else ("fehler" if p.get("fehler") else "wartet")
        if stand == "prueft":                           # hängt ein Prüfer länger als LAEUFT_H, zählt er als fehlgeschlagen
            t = datetime.datetime.strptime(v["zeit_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
            if (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() > LAEUFT_H * 3600:
                stand = "fehler"
        aus.append({"aenderung": v["eid"], "ebene": v["ebene"], "id": v["id"], "was": _was(con, pid, v), "alt": v["alt"], "neu": v["neu"],
                    "stand": stand, "seit_utc": v["zeit_utc"], "folgen": (p or {}).get("folgen") or [], "fehler": (p or {}).get("fehler"),
                    "usd": (p or {}).get("usd"),
                    "beruehrt": [n for k, n in (("beruehrt_ziel", "Ziel"), ("beruehrt_erfolg", "Erfolg"), ("beruehrt_kosten", "Kosten"))
                                 if (p or {}).get(k)]})
    return aus


# --- der Prüfer-Lauf ------------------------------------------------------------------------------------------------------

def _dateien(con, pid, v, ordner):
    from . import planansicht, themen
    zeilen = [f"# Änderung ({'Meilenstein' if v['ebene'] == 'meilenstein' else 'Paket'} {v['id']})", ""]
    for k in v["neu"]:
        zeilen += [f"## {NAMEN[k]}", f"alt: {v['alt'].get(k)}", f"neu: {v['neu'][k]}", ""]
    unten = ["# Was davon abhängt", ""]
    if v["ebene"] == "meilenstein":
        b = con.execute("SELECT * FROM bogen WHERE id = ?", (v["id"],)).fetchone()
        unten += [f"Meilenstein {b['nr']}: {b['titel']} – Ziel: {b['ziel'] or '–'} – Abnahme: {b['abnahme'] or '–'}", "", "## Pakete"]
        for a in planansicht._pakete(con, pid, v["id"]):
            ts = ", ".join(f"TH{t}" for t in themen.verweise(con, pid, a["id"]))
            unten.append(f"- A{a['id']} [{a['status']}] {a['titel']} ({ts or 'ohne Thema'}): {(a['auftrag'] or '')[:300]}")
    else:
        a = con.execute("SELECT * FROM aufgabe WHERE id = ?", (v["id"],)).fetchone()
        b = con.execute("SELECT nr, titel, ziel, abnahme FROM bogen WHERE id = ?", (a["bogen_id"],)).fetchone() if a["bogen_id"] else None
        unten += [f"Paket A{a['id']}: {a['titel']} – Meilenstein: {(str(b['nr']) + ' ' + b['titel']) if b else '–'}"
                  + (f" (Ziel: {b['ziel'] or '–'}, Abnahme: {b['abnahme'] or '–'})" if b else ""), "", "## Pakete danach (hängen davon ab)"]
        for (nach,) in con.execute("SELECT nach FROM abhaengigkeit WHERE vor = ? ORDER BY nach", (a["id"],)).fetchall():
            x = con.execute("SELECT id, titel, status FROM aufgabe WHERE id = ?", (nach,)).fetchone()
            if x:
                unten.append(f"- A{x['id']} [{x['status']}] {x['titel']}")
    for name, text in (("aenderung.md", "\n".join(zeilen)), ("darunter.md", "\n".join(unten))):
        with open(os.path.join(ordner, name), "w", encoding="utf-8", newline="\n") as d:
            d.write(text + "\n")
    return ["aenderung.md", "darunter.md"]


def pruefer(con, pid, v, modell_, prog=None, zusatz=None):
    """Der Prüfer selbst (frischer -p, nur Lesen, Frist). Rückgabe {"ergebnis", "usd", "fehler"}."""
    from . import arbeiter, platz, versionsprobe
    with tempfile.TemporaryDirectory(prefix="amw-folgen-", ignore_cleanup_errors=True) as ordner:
        p = platz.pfade(os.path.join(ordner, "plaetze"), 1)
        os.makedirs(p["klon"])
        subprocess.run(["git", "init", "-q", "-b", "main", p["klon"]], check=True, capture_output=True, creationflags=OHNE_FENSTER)
        dateien = _dateien(con, pid, v, p["klon"])
        r = arbeiter.laufen(p, AUFTRAG + "\n\nDateien: " + ", ".join(dateien), None, modell=modell_, effort="medium", prog=prog,
                            zusatz=zusatz, nur_lesen=True, geprueft=versionsprobe.geprueft(con), frist_s=FRIST_S)
    erg = r.get("ergebnis") or {}
    usd = erg.get("total_cost_usd")
    if r.get("abweichungen"):
        return {"ergebnis": None, "usd": usd, "fehler": "; ".join(r["abweichungen"])[:500]}
    text = (erg.get("result") or "").strip()
    if r.get("rc") != 0 or erg.get("is_error") or not text:
        return {"ergebnis": None, "usd": usd, "fehler": r.get("fehler") or f"kein Ergebnis (rc {r.get('rc')})"}
    return {"ergebnis": text, "usd": usd, "fehler": None}


def ausfuehren(con, pid, eid, prog=None, zusatz=None):
    """Als angemeldeter Lauf der Lauf-Schlange (leicht, selbst – kein Weckruf): prüfen und abschließen (auch einen Fehler)."""
    from . import belegung, betrieb
    v = vorschlag(con, pid, eid)
    m = modell(con, pid)
    m = m if m != "aus" else "haiku"
    agent = kern.lead(con, pid) or kern.ENTWICKLER
    lid = betrieb.lauf_start(con, pid, agent, f"Folgenprüfung Ä{eid} ({m}, A1957, automatisch)", None, False, False, None, warten=True,
                             waechter=os.getpid(), befehl=None, ordner=None, selbst=True)
    belegung.lauf_merken(lid, os.getpid())
    aus = None
    try:
        while True:
            l = betrieb.lauf_zeile(con, pid, lid)
            if l["status"] == "laeuft":
                break
            if l["status"] in ("fertig", "abgebrochen"):
                raise RuntimeError(f"L{lid} ist {l['status']} – nicht geprüft")
            time.sleep(5)
        betrieb.lauf_uebernehmen(con, lid, "agent")
        aus = pruefer(con, pid, v, m, prog=prog, zusatz=zusatz)
    except Exception as e:                               # noqa: BLE001 – niemand sieht die Ausgabe: als Fehler eintragen
        aus = {"ergebnis": None, "usd": None, "fehler": f"{type(e).__name__}: {e}"[:300]}
    finally:
        aus = aus or {"ergebnis": None, "usd": None, "fehler": "abgebrochen"}
        kosten = f"{aus['usd']:.2f} $" if isinstance(aus.get("usd"), (int, float)) else "Kosten unbekannt"
        try:
            betrieb.lauf_ende(con, pid, agent, lid, 1 if aus.get("fehler") else 0,
                              (f"Folgenprüfung Ä{eid}: " + (f"Fehler – {aus['fehler']}" if aus.get("fehler") else "fertig") + f" · {kosten}")[:500])
        finally:
            belegung.lauf_vergessen(lid)
    abschliessen(con, pid, eid, aus.get("ergebnis"), modell_=m, usd=aus.get("usd"), lauf=lid, fehler=aus.get("fehler"))
    return aus


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="amw-folgen")
    ap.add_argument("--projekt-id", type=int, required=True)
    ap.add_argument("--aenderung", type=int, required=True)
    x = ap.parse_args(argv)
    con = db.verbinde()
    try:
        ausfuehren(con, x.projekt_id, x.aenderung)
    finally:
        con.close()
