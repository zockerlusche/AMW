"""Messung vorher/nachher der Umstellung auf das Bündeln ohne Agent (A2128): je Tag Tokens, Wartezeit der Pakete bis zur
Auslieferung und Zahl der Neustarts; Vergleich der Zeiträume vor und nach der Umstellung und die Zahlen für den Abschlussbericht.

Nur lesen, kein Schema, nichts wird gesteuert. Lücken werden genannt, nicht geschätzt (wie messung, A1844).
- Tag = Ortszeit des PCs (messung._tag) – so meint der Mensch „heute“.
- Tokens: aus den erfassten Läufen (plan_ereignis „kosten“, z. B. Headless-Pakete aus der JSON-Ausgabe von claude -p): eingabe,
  cache_schreiben, cache_lesen, ausgabe; Summe = alle vier. Ein Lauf ohne Token-Angaben zählt als Lücke (laeufe_ohne_tokens), nicht
  als 0. Der Kosten-Zähler der Fenster-Sitzungen kennt nur Dollar – er steht als usd_zaehler daneben, ohne Tokens.
- Wartezeit: je Paket, das an diesem Tag fertig (ausgeliefert) wurde, messung.zeiten(): warten_s (startklar → läuft + Wartegründe +
  abgegeben → gemergt, D1258 v2 §8) und nach_abgabe_s (abgegeben → gemergt – der Teil, den das Bündeln verkürzen soll). Median je
  Tag bzw. Zeitraum über die Pakete, nicht Mittel der Tagesmediane.
- Neustarts: jede eingetragene Version (release, art version) ist eine Auslieferung mit einem Neustart des Dienstes; Versionen
  innerhalb von NEUSTART_FENSTER_S (Zwischenversionen eines Stands, eine Kette) zählen als einer. Neustarts von Hand stehen nicht in
  der Datenbank – sie zählen nicht mit (Lücke im Bericht).
- Umstellung: Vorgabe ist die erste Auslieferung eines Bündels ohne Agent (plan_ereignis buendel_auslieferung, schritt
  „ausgeliefert“, A2123); sonst von Hand (umstellung="JJJJ-MM-TTTHH:MM:SSZ").
"""
import datetime
import json
import statistics

from . import buendel_auslieferung, kern, messung

NEUSTART_FENSTER_S = 600
TOKEN_FELDER = ("eingabe", "cache_schreiben", "cache_lesen", "ausgabe")
TAGE = 7


def _utc(d):
    return d.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _median(xs):
    return round(statistics.median(xs)) if xs else None


def umstellung(con, pid):
    """Zeitpunkt (UTC-Text) der ersten Auslieferung eines Bündels ohne Agent – oder None, wenn es noch keine gab."""
    for r in con.execute("SELECT zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY zeit_utc, id",
                         (pid, buendel_auslieferung.ART)):
        try:
            if json.loads(r["text"] or "{}").get("schritt") == "ausgeliefert":
                return r["zeit_utc"]
        except (ValueError, AttributeError):
            continue
    return None


def _leer(tag):
    return {"tag": tag, "tokens": {**{k: 0 for k in TOKEN_FELDER}, "summe": 0}, "usd": 0.0, "usd_zaehler": 0.0, "laeufe": 0,
            "laeufe_ohne_tokens": 0, "pakete": 0, "warten": [], "nach_abgabe": [], "versionen": [], "neustarts": 0}


def _tage(von, bis):
    """Ortszeit-Tage (ISO) von `von` bis vor `bis` (datetime, UTC)."""
    t, ende = von.astimezone().date(), (bis - datetime.timedelta(microseconds=1)).astimezone().date()
    aus = []
    while t <= ende:
        aus.append(t.isoformat())
        t += datetime.timedelta(days=1)
    return aus


def _neustarts(zeiten):
    """Versionen → Neustarts: Zeiten innerhalb von NEUSTART_FENSTER_S nach dem vorigen Neustart zählen nicht neu."""
    n, letzte = 0, None
    for t in sorted(zeiten):
        if letzte is None or (t - letzte).total_seconds() > NEUSTART_FENSTER_S:
            n += 1
            letzte = t
    return n


def _zaehler_je_tag(con, pid, von_utc, bis_utc):
    """{tag: usd} der Sitzungs-Zähler aller Agenten des Projekts im Zeitraum (aufwand.zuwaechse – dieselbe Rechnung)."""
    from . import aufwand
    aus = {}
    for (kennung,) in con.execute("SELECT kennung FROM agent WHERE projekt_id = ?", (pid,)).fetchall():
        try:
            for zeit, usd in aufwand.zuwaechse(con, pid, kennung, von_utc):
                if von_utc <= zeit < bis_utc:
                    t = messung._tag(zeit)
                    aus[t] = aus.get(t, 0.0) + usd
        except Exception:                                # noqa: BLE001 – eine Messung darf den Bericht nie verhindern
            continue
    return aus


def je_tag(con, pid, von, bis, jetzt=None):
    """Je Ortszeit-Tag im Zeitraum [von, bis) (datetime): Tokens, Kosten, Läufe, Pakete mit Median-Wartezeiten, Neustarts.
    Jeder Tag steht in der Liste, auch ohne Daten (Mittel je Tag zählen ihn mit). Die Rohlisten (warten, nach_abgabe, versionen)
    bleiben für die Zusammenfassung im Ergebnis unter „_roh“."""
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    von_utc, bis_utc = _utc(von), _utc(bis)
    tage = {t: _leer(t) for t in _tage(von, bis)}

    def tag(utc):
        t = messung._tag(utc)
        return tage.get(t)

    for r in con.execute("SELECT zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND art = 'kosten' AND zeit_utc >= ?"
                         " AND zeit_utc < ? ORDER BY zeit_utc, id", (pid, von_utc, bis_utc)):
        d = tag(r["zeit_utc"])
        try:
            e = json.loads(r["text"] or "{}")
        except ValueError:
            e = {}
        if d is None or not isinstance(e, dict):
            continue
        d["laeufe"] += 1
        if isinstance(e.get("usd"), (int, float)):
            d["usd"] += e["usd"]
        werte = {k: e[k] for k in TOKEN_FELDER if isinstance(e.get(k), int)}
        if not werte:
            d["laeufe_ohne_tokens"] += 1
        for k, v in werte.items():
            d["tokens"][k] += v
            d["tokens"]["summe"] += v

    for t, usd in _zaehler_je_tag(con, pid, von_utc, bis_utc).items():
        if t in tage:
            tage[t]["usd_zaehler"] += usd

    for r in con.execute("SELECT id, fertig_utc FROM aufgabe WHERE projekt_id = ? AND status = 'fertig' AND begonnen_utc IS NOT NULL"
                         " AND fertig_utc >= ? AND fertig_utc < ? ORDER BY fertig_utc, id", (pid, von_utc, bis_utc)).fetchall():
        d = tag(r["fertig_utc"])
        m = messung.zeiten(con, pid, r["id"], jetzt)
        if d is None or not m:
            continue
        d["pakete"] += 1
        d["warten"].append(m["warten_s"])
        d["nach_abgabe"].append(m["abgabe_s"])

    for r in con.execute("SELECT zeit_utc FROM release WHERE projekt_id = ? AND art = 'version' AND zeit_utc >= ? AND zeit_utc < ?"
                         " ORDER BY zeit_utc", (pid, von_utc, bis_utc)):
        d = tag(r["zeit_utc"])
        if d is not None:
            d["versionen"].append(messung._t(r["zeit_utc"]))

    aus = []
    for t in sorted(tage):
        d = tage[t]
        d["neustarts"] = _neustarts(d["versionen"])
        roh = {"warten": d.pop("warten"), "nach_abgabe": d.pop("nach_abgabe"), "versionen": d.pop("versionen")}
        aus.append({**d, "usd": round(d["usd"], 2), "usd_zaehler": round(d["usd_zaehler"], 2), "versionen": len(roh["versionen"]),
                    "warten_median_s": _median(roh["warten"]), "nach_abgabe_median_s": _median(roh["nach_abgabe"]), "_roh": roh})
    return aus


def _zusammenfassen(tage, von, bis):
    """Mittel je Tag über die Dauer des Zeitraums (Randtage in Ortszeit sind angebrochen – sie zählen anteilig)."""
    dauer = (bis - von).total_seconds() / 86400
    n = dauer or 1
    warten = [x for d in tage for x in d["_roh"]["warten"]]
    nach = [x for d in tage for x in d["_roh"]["nach_abgabe"]]
    tokens = sum(d["tokens"]["summe"] for d in tage)
    neustarts = sum(d["neustarts"] for d in tage)
    pakete = sum(d["pakete"] for d in tage)
    return {"von": _utc(von), "bis": _utc(bis), "tage": round(dauer, 1), "pakete": pakete,
            "tokens": tokens, "tokens_je_tag": round(tokens / n), "tokens_je_paket": round(tokens / pakete) if pakete else None,
            "usd": round(sum(d["usd"] for d in tage), 2), "usd_zaehler": round(sum(d["usd_zaehler"] for d in tage), 2),
            "laeufe": sum(d["laeufe"] for d in tage), "laeufe_ohne_tokens": sum(d["laeufe_ohne_tokens"] for d in tage),
            "neustarts": neustarts, "neustarts_je_tag": round(neustarts / n, 2),
            "pakete_je_neustart": round(pakete / neustarts, 2) if neustarts else None,
            "warten_median_s": _median(warten), "nach_abgabe_median_s": _median(nach),
            "je_tag": [{k: v for k, v in d.items() if k != "_roh"} for d in tage]}


def _aenderung(alt, neu):
    """Änderung in Prozent (gerundet) – None, wenn ein Wert fehlt oder vorher 0 war."""
    if alt is None or neu is None or not alt:
        return None
    return round((neu - alt) / alt * 100)


VERGLEICH = ("tokens_je_tag", "tokens_je_paket", "neustarts_je_tag", "pakete_je_neustart", "warten_median_s", "nach_abgabe_median_s")


def vergleich(con, pid, umstellung_utc=None, tage=TAGE, jetzt=None):
    """Vorher = die `tage` Tage vor der Umstellung, nachher = ab der Umstellung bis höchstens `tage` Tage danach (oder jetzt).
    {"umstellung", "vorher", "nachher", "aenderung": {wert: Prozent}, "luecken": [Text]}. Ohne Umstellung: AmwFehler."""
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    u = umstellung_utc or umstellung(con, pid)
    if not u:
        raise kern.AmwFehler("Noch keine Auslieferung eines Bündels ohne Agent – Zeitpunkt der Umstellung angeben")
    ut = messung._t(u)
    if ut > jetzt:
        raise kern.AmwFehler(f"Die Umstellung {u} liegt in der Zukunft")
    v_von, n_bis = ut - datetime.timedelta(days=tage), min(ut + datetime.timedelta(days=tage), jetzt)
    vorher = _zusammenfassen(je_tag(con, pid, v_von, ut, jetzt), v_von, ut)
    nachher = _zusammenfassen(je_tag(con, pid, ut, n_bis, jetzt), ut, n_bis) if n_bis > ut else _zusammenfassen([], ut, ut)
    luecken = []
    for name, z in (("vorher", vorher), ("nachher", nachher)):
        if z["laeufe_ohne_tokens"]:
            luecken.append(f"{name}: {z['laeufe_ohne_tokens']} von {z['laeufe']} Läufen ohne Token-Angabe")
        if not z["pakete"]:
            luecken.append(f"{name}: kein ausgeliefertes Paket – keine Wartezeit")
    if nachher["tage"] < vorher["tage"]:
        luecken.append(f"nachher erst {nachher['tage']} von {vorher['tage']} Tagen – Werte je Tag vergleichen, nicht Summen")
    luecken.append("Tokens nur aus erfassten Läufen (Headless); Fenster-Sitzungen nur in Dollar (usd_zaehler)")
    luecken.append("Neustarts = Auslieferungen mit Version; Neustarts von Hand stehen nicht in der Datenbank")
    def roh(z, dauer, k):                                # Änderung aus ungerundeten Werten je Tag
        if k.endswith("_je_tag"):
            return z[k[:-len("_je_tag")]] / dauer if dauer else None
        return z[k]
    d_v, d_n = (ut - v_von).total_seconds() / 86400, (n_bis - ut).total_seconds() / 86400
    return {"umstellung": u, "vorher": vorher, "nachher": nachher,
            "aenderung": {k: _aenderung(roh(vorher, d_v, k), roh(nachher, d_n, k)) for k in VERGLEICH}, "luecken": luecken}


def _zahl(x):
    return "–" if x is None else f"{x:,}".replace(",", ".") if isinstance(x, int) else f"{x:.2f}".replace(".", ",")


def _prozent(p):
    return "" if p is None else f" ({'+' if p > 0 else ''}{p} %)"


def bericht(v):
    """Die Zahlen für den Abschlussbericht als Markdown-Zeilen (Text)."""
    a, b, d = v["vorher"], v["nachher"], v["aenderung"]
    zeit = lambda s: "–" if s is None else messung.dauer(s)
    zeilen = [f"Umstellung: {v['umstellung']} · vorher {a['tage']} Tage, nachher {b['tage']} Tage", "",
              "| Wert | vorher | nachher |", "|---|---|---|",
              f"| Pakete ausgeliefert | {a['pakete']} | {b['pakete']} |",
              f"| Tokens je Tag | {_zahl(a['tokens_je_tag'])} | {_zahl(b['tokens_je_tag'])}{_prozent(d['tokens_je_tag'])} |",
              f"| Tokens je Paket | {_zahl(a['tokens_je_paket'])} | {_zahl(b['tokens_je_paket'])}{_prozent(d['tokens_je_paket'])} |",
              f"| Neustarts je Tag | {_zahl(a['neustarts_je_tag'])} | {_zahl(b['neustarts_je_tag'])}{_prozent(d['neustarts_je_tag'])} |",
              f"| Pakete je Neustart | {_zahl(a['pakete_je_neustart'])} | {_zahl(b['pakete_je_neustart'])}{_prozent(d['pakete_je_neustart'])} |",
              f"| Wartezeit (Median) | {zeit(a['warten_median_s'])} | {zeit(b['warten_median_s'])}{_prozent(d['warten_median_s'])} |",
              f"| abgegeben → ausgeliefert (Median) | {zeit(a['nach_abgabe_median_s'])} | {zeit(b['nach_abgabe_median_s'])}"
              f"{_prozent(d['nach_abgabe_median_s'])} |"]
    if v["luecken"]:
        zeilen += ["", "Lücken:"] + [f"- {x}" for x in v["luecken"]]
    return "\n".join(zeilen)
