"""A2046 (V8, D1531 §8): Prognose messen – je fertigem Paket die Schätzung (P50) gegen das Ist.

Die Dauer, mit der Reihenfolge und Zeitplan rechnen (reihenfolge.dauer: gemessen P50, sonst Schätzung oder Vorgabe nach
Größe), wird beim Start eines Pakets einmal festgehalten – später ändert sie sich mit jeder neuen Messung. Ist das Paket fertig,
kommt das Ist dazu (begonnen bis fertig). Beides steht als plan_ereignis (ohne Schemaänderung):

  prognose_start   {"aufgabe", "schaetzung_h", "quelle"}                          – beim Start, einmal je Paket
  prognose_ist     {"aufgabe", "schaetzung_h", "quelle", "ist_h", "faktor"}       – beim Ende, einmal je Paket

Beide schreibt die Aufsichtsrunde des Dienstes (runde) – so zählt jeder Abschlussweg (Agent, p-Paket, Release-Kette, von
Hand), ohne dass jeder Weg sich selbst melden muss. Fehlt der Start (Paket vor A2046 begonnen oder zwischen zwei Runden fertig),
gilt die Schätzung zum Zeitpunkt der Messung; die Quelle sagt dann „beim Ende“.

Trefferquote (trefferquote): Anteil der fertigen Pakete, deren Ist im Rahmen liegt – höchstens IM_RAHMEN mal die Schätzung und
mindestens ihr Kehrwert –, dazu der Median des Faktors Ist/Schätzung, je Quelle (gemessen, geschätzt, Vorgabe).
"""
import json
import statistics

from . import db

START, IST = "prognose_start", "prognose_ist"
IM_RAHMEN = 1.5                     # wie tore.PROGNOSE_FAKTOR: bis 1,5-fach (und ab 1/1,5) gilt als getroffen


def _vermerkt(con, pid, art):
    aus = {}
    for r in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = ?", (pid, art)):
        try:
            d = json.loads(r["text"] or "{}")
        except ValueError:
            continue
        if d.get("aufgabe"):
            aus[d["aufgabe"]] = d
    return aus


def _stunden(a, b):
    try:
        return max(0.0, (db.utc_lesen(b) - db.utc_lesen(a)).total_seconds() / 3600)
    except (TypeError, ValueError):
        return None


def runde(con, pid):
    """Schätzung beim Start und Ist beim Ende festhalten – je Paket einmal. Rückgabe: Texte für das Protokoll."""
    from . import reihenfolge
    gemessen = reihenfolge._gemessen(con, pid)
    starts, iste = _vermerkt(con, pid, START), _vermerkt(con, pid, IST)
    neu, aus = [], []
    for a in con.execute("SELECT * FROM aufgabe WHERE projekt_id = ? AND begonnen_utc IS NOT NULL AND status IN ('laeuft', 'fertig')",
                         (pid,)).fetchall():
        if a["id"] in iste:
            continue
        if a["status"] == "laeuft":
            if a["id"] not in starts:
                h, quelle = reihenfolge.dauer(a, gemessen)
                neu.append((START, a["id"], {"aufgabe": a["id"], "schaetzung_h": round(h, 2), "quelle": quelle}))
            continue
        ist = _stunden(a["begonnen_utc"], a["fertig_utc"])
        if ist is None:
            continue
        s = starts.get(a["id"])
        if s:
            h, quelle = s["schaetzung_h"], s["quelle"]
        else:
            h, quelle = reihenfolge.dauer(a, gemessen)
            quelle = f"{quelle}, beim Ende"
        h = max(float(h), 0.01)
        neu.append((IST, a["id"], {"aufgabe": a["id"], "schaetzung_h": round(h, 2), "quelle": quelle, "ist_h": round(ist, 2),
                                   "faktor": round(ist / h, 2)}))
    if neu:
        with db.schreiben(con):
            for art, aid, werte in neu:
                db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=art, aufgabe_id=aid,
                             text=json.dumps(werte, ensure_ascii=False))
                if art == IST:
                    aus.append(f"A{aid}: geschätzt {werte['schaetzung_h']:g} h, gebraucht {werte['ist_h']:g} h (×{werte['faktor']:g})")
    return aus


def _quelle(q):
    q = (q or "").split(" ")[0].split(",")[0]
    return {"gemessen": "gemessen", "geschätzt": "geschätzt", "Vorgabe": "Vorgabe"}.get(q, "ohne Größe" if q == "ohne" else q or "–")


def trefferquote(con, pid, seit_utc=None):
    """{"n", "treffer", "quote", "faktor_median", "zu_lang", "zu_kurz", "je_quelle": {Quelle: {...}}, "pakete": [...]} über alle
    gemessenen Pakete (seit_utc: nur jüngere Messungen)."""
    zeilen = []
    for r in con.execute("SELECT zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND art = ?"
                         + (" AND zeit_utc >= ?" if seit_utc else "") + " ORDER BY id", (pid, IST, seit_utc) if seit_utc else (pid, IST)):
        d = json.loads(r["text"] or "{}")
        if isinstance(d.get("faktor"), (int, float)):
            zeilen.append({**d, "zeit_utc": r["zeit_utc"], "art_quelle": _quelle(d.get("quelle"))})

    def zahlen(liste):
        n = len(liste)
        t = sum(1 for x in liste if 1 / IM_RAHMEN <= x["faktor"] <= IM_RAHMEN)
        return {"n": n, "treffer": t, "quote": round(t / n, 2) if n else None,
                "faktor_median": round(statistics.median(x["faktor"] for x in liste), 2) if n else None,
                "zu_lang": sum(1 for x in liste if x["faktor"] > IM_RAHMEN), "zu_kurz": sum(1 for x in liste if x["faktor"] < 1 / IM_RAHMEN)}
    je = {}
    for x in zeilen:
        je.setdefault(x["art_quelle"], []).append(x)
    return {**zahlen(zeilen), "je_quelle": {k: zahlen(v) for k, v in sorted(je.items())}, "pakete": zeilen}
