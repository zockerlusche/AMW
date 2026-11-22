"""Projekt-Schalter (A1926, Mehrprojekt 8, D1304 v12 §5): aus | probe | an je Projekt (projekt.einstellungen.schalter).

- probe (Lead oder Mensch): eine Kopie der Projektdaten (db.sichern mit nur diesem Projekt – eine lauffähige AMW-Datenbank,
  die Sicherung bleibt liegen) und eine Zählprobe: je Tabelle des Projekts Zeilen und Nummern, dazu die Verweise auf eigene
  Ziele – in der Live-Datenbank und in der Kopie. Bestanden, wenn alles gleich ist („Nummern bleiben“). Bericht als Dokument.
  Nur ein ausdrücklich ausgeschaltetes Projekt steht danach auf „probe“ (keine p-Starts, Regel 12); eins ohne Eintrag oder mit
  „an“ bleibt an (P406-Auflage: ohne Eintrag gilt an, auch bei der Probe – eine Probe auf der AMW hält nichts an).
- an (nur der Mensch, im eigenen Terminal): nur nach einer bestandenen Probe – p-Pakete (Disponent) und Themen-Ablauf
  (Gegenlesen) für das Projekt frei.
- aus (nur der Mensch): wie bis 1.15x ohne Schalter-Ablauf: keine p-Starts, kein automatisches Gegenlesen.
Ohne Eintrag gilt „an“ (A1925 E5, #29883) – bestehende Projekte laufen weiter wie bisher. Nichts wird gelöscht.
"""
import hashlib
import json
import os
import sqlite3

from . import db, kern

STUFEN = ("aus", "probe", "an")
ART = "projekt_schalter"
VERWEISE = {"aufgabe_id": "aufgabe", "bogen_id": "bogen", "thema_id": "thema", "dokument_id": "dokument", "frage_id": "frage",
            "nachricht_id": "nachricht", "beschluss_id": "beschluss"}


def _tabellen(k):
    return [r[0] for r in k.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def _spalten(k, t):
    return [c[1] for c in k.execute(f"PRAGMA table_info({t})")]


def zaehlen(k, pid):
    """Zählprobe einer Datenbank für Projekt pid: {tabelle: {"zeilen", "nummern" (sha256 der sortierten rowids),
    "verweise": {spalte: Anzahl auf ein vorhandenes Ziel DIESES Projekts}, "fremd": {spalte: Anzahl auf ein anderes Projekt}}}.
    Nur Tabellen mit projekt_id. Spalten- und Tabellennamen stammen aus dem Schema, nie von außen."""
    aus = {}
    tabellen = set(_tabellen(k))
    for t in sorted(tabellen):
        sp = _spalten(k, t)
        if "projekt_id" not in sp:
            continue
        ids = [r[0] for r in k.execute(f"SELECT rowid FROM {t} WHERE projekt_id = ? ORDER BY rowid", (pid,))]
        e = {"zeilen": len(ids), "nummern": hashlib.sha256(",".join(map(str, ids)).encode()).hexdigest()[:16], "verweise": {}, "fremd": {}}
        for s, ziel in VERWEISE.items():
            if s not in sp or ziel not in tabellen or s == f"{t}_id":
                continue
            eigen = "projekt_id" in _spalten(k, ziel)
            bed = f" AND z.projekt_id = {int(pid)}" if eigen else ""
            e["verweise"][s] = k.execute(f"SELECT count(*) FROM {t} x JOIN {ziel} z ON z.rowid = x.{s} WHERE x.projekt_id = ?{bed}",
                                         (pid,)).fetchone()[0]
            if eigen:
                e["fremd"][s] = k.execute(f"SELECT count(*) FROM {t} x JOIN {ziel} z ON z.rowid = x.{s} WHERE x.projekt_id = ?"
                                          " AND z.projekt_id != ?", (pid, pid)).fetchone()[0]
        aus[t] = e
    return aus


def vergleichen(live, kopie):
    """[(tabelle, was, live, kopie)] der Unterschiede – leer = bestanden. Verweise auf andere Projekte sind kein Unterschied
    (die Kopie leert sie bewusst), sie stehen im Bericht als Hinweis."""
    diff = []
    for t in sorted(set(live) | set(kopie)):
        a, b = live.get(t), kopie.get(t)
        if not a or not b:
            diff.append((t, "Tabelle", bool(a), bool(b)))
            continue
        for was in ("zeilen", "nummern"):
            if a[was] != b[was]:
                diff.append((t, was, a[was], b[was]))
        for s in sorted(set(a["verweise"]) | set(b["verweise"])):
            if a["verweise"].get(s) != b["verweise"].get(s):
                diff.append((t, f"Verweise {s}", a["verweise"].get(s), b["verweise"].get(s)))
    return diff


def stufe(con, pid):
    return kern.projekt_schalter(con, pid)


def _name(con, pid):
    return (con.execute("SELECT name FROM projekt WHERE id = ?", (pid,)).fetchone() or [f"P{pid}"])[0]


def _setzen(con, pid, wert):
    e = json.loads(con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()[0] or "{}")
    e["schalter"] = wert
    con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?", (json.dumps(e, ensure_ascii=False), pid))


def bericht(name, kopie, live, diff):
    z = [f"# Probe Projekt-Schalter – {name}", "", "Kopie der Projektdaten (Sicherung, bleibt liegen): " + os.path.basename(kopie), "",
         f"Ergebnis: **{'bestanden' if not diff else 'nicht bestanden'}** – " + (
             "Zeilen, Nummern und Verweise sind in der Kopie gleich." if not diff else f"{len(diff)} Unterschied(e)."), "",
         "| Tabelle | Zeilen | Verweise (eigene Ziele) | auf andere Projekte |", "|---|---|---|---|"]
    for t, e in sorted(live.items()):
        if not e["zeilen"]:
            continue
        v = ", ".join(f"{s} {n}" for s, n in sorted(e["verweise"].items()) if n) or "–"
        f = ", ".join(f"{s} {n}" for s, n in sorted(e["fremd"].items()) if n) or "–"
        z.append(f"| {t} | {e['zeilen']} | {v} | {f} |")
    if diff:
        z += ["", "Unterschiede (live → Kopie):", *[f"- {t} · {w}: {a} → {b}" for t, w, a, b in diff]]
    if any(n for e in live.values() for n in e["fremd"].values()):
        z += ["", "Hinweis: Verweise auf andere Projekte sind in der Kopie geleert (sie gehört nur diesem Projekt) – kein Fehler."]
    return "\n".join(z) + "\n"


def probe(con, pid, von, ziel=None):
    """Kopie + Zählprobe + Bericht. Lead oder Mensch. Rückgabe {"bestanden", "dokument", "kopie", "unterschiede", "stufe"}."""
    from . import dokumente
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Die Probe des Projekt-Schalters macht der Lead oder der Mensch")
    name = _name(con, pid)
    if not ziel:                                              # eigener Name je Probe (zwei Proben in einer Minute)
        import datetime
        basis = os.path.join(os.path.dirname(db.db_pfad()), f"schalter-probe-{db.kurzname(name, pid)}-"
                             f"{datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')}")
        ziel, n = basis + ".db", 1
        while os.path.exists(ziel):
            n += 1
            ziel = f"{basis}-{n}.db"
    kopie = db.sichern(ziel, pid=pid, name=name)
    live = zaehlen(con, pid)
    k = sqlite3.connect(f"file:{kopie}?mode=ro", uri=True)
    try:
        nachher = zaehlen(k, pid)
    finally:
        k.close()
    diff = vergleichen(live, nachher)
    did = dokumente.ablegen_inhalt(con, pid, "AMW", bericht(name, kopie, live, diff).encode("utf-8"), f"schalter-probe-{pid}.md",
                                   titel=f"Probe Projekt-Schalter {name}", art="bericht")
    alt = stufe(con, pid)
    neu = "probe" if alt == "aus" else alt                    # P406: ohne Eintrag bleibt es an (und ohne Eintrag)
    with db.schreiben(con):
        if neu != alt:
            _setzen(con, pid, neu)
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=ART,
                     text=json.dumps({"schritt": "probe", "bestanden": not diff, "dokument": did, "kopie": kopie, "vorher": alt,
                                      "nachher": neu, "unterschiede": len(diff)}, ensure_ascii=False))
    return {"bestanden": not diff, "dokument": did, "kopie": kopie, "unterschiede": diff, "stufe": neu}


def letzte_probe(con, pid):
    for r in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id DESC", (pid, ART)).fetchall():
        try:
            d = json.loads(r[0])
        except ValueError:
            continue
        if d.get("schritt") == "probe":
            return d
    return None


def umschalten(con, pid, von, wert):
    """an | aus – nur der Mensch (die Befehlszeile prüft zusätzlich: nicht aus einer Agenten-Sitzung). an nur nach einer
    bestandenen Probe. Nichts wird gelöscht."""
    if wert not in ("an", "aus"):
        raise kern.AmwFehler("amw projekt schalter <Projekt> probe | an | aus")
    if von != kern.ENTWICKLER:
        raise kern.AmwFehler("Ein- und ausschalten nur der Mensch (--von Entwickler im eigenen Terminal)")
    if wert == "an":
        p = letzte_probe(con, pid)
        if not p or not p.get("bestanden"):
            raise kern.AmwFehler("Einschalten erst nach einer bestandenen Probe: amw projekt schalter <Projekt> probe")
    alt = stufe(con, pid)
    with db.schreiben(con):
        _setzen(con, pid, wert)
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=ART,
                     text=json.dumps({"schritt": wert, "vorher": alt, "nachher": wert}, ensure_ascii=False))
    return alt, wert
