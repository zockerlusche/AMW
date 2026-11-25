"""Rotes Bündel teilen (A2122): halbieren, bis das schuldige Paket feststeht.

`teilen` ist rein – keine Datenbank, kein git, keine Uhr: den Gesamtlauf macht der übergebene Prüfer.
- Jede Hälfte läuft auf dem, was schon grün ist (in der Reihenfolge des Bündels). So läuft nie ein Paket ohne seinen Vorgänger, und
  zwei Pakete, die nur zusammen rot sind, werden gefunden: schuldig ist das spätere.
- Hälfte grün → sie zählt zum Grünen, das schuldige Paket steckt im Rest. Hälfte rot → dort weiter. Bleibt eines, steht es fest; es
  geht als Befund heraus, seine Nachfolger warten. Danach läuft alles Übrige zusammen: grün → fertig, rot → nächstes schuldiges.
- Freigegeben wird nur eine Menge, die genau so grün gelaufen ist.
- Beschuldigt wird nie auf Verdacht: wäre es das erste Paket auf main, läuft zuerst main allein (rot → BASIS_ROT); waren alle
  Hälften grün, läuft das Ganze noch einmal (grün → WACKELIG). Ein Lauf ohne klares Ergebnis hält an (UNKLAR). In diesen drei
  Fällen wird nichts freigegeben; schon feststehende Befunde bleiben.
- Pakete der Release-Kette (Regel release_main aus buendel_zusammensetzen) sind als „Lead liest“ markiert, ebenso Pakete ohne
  Einordnung. Ist eines davon unter den grünen, gibt der Lead die Menge frei, sonst die AMW.
"""
import copy

from .buendel_zusammensetzen import RELEASE_MAIN

GETEILT, BASIS_ROT, WACKELIG, UNKLAR = "geteilt", "basis_rot", "wackelig", "unklar"
EINORDNUNG = "einordnung"                                         # Regel aus buendel_zusammensetzen: Einordnung nicht möglich


class _Halt(Exception):
    def __init__(self, status, meldung):
        super().__init__(meldung)
        self.status, self.meldung = status, meldung


def lead_gruende(p):
    """Warum der Lead das Paket liest: [(Regel, Begründung)] – leer = muss er nicht."""
    if p.get("gruende") is None:
        return [(EINORDNUNG, "Paket ist nicht eingeordnet")]
    return [(r, g) for r, g in p["gruende"] if r in (RELEASE_MAIN, EINORDNUNG)]


def _pruefen(reihe, vor):
    ids = [p["id"] for p in reihe]
    if not ids:
        raise ValueError("leeres Bündel")
    if len(set(ids)) != len(ids):
        raise ValueError("ein Paket steht doppelt im Bündel")
    stelle = {i: n for n, i in enumerate(ids)}
    for i in ids:
        for v in vor.get(i, ()):
            if v in stelle and stelle[v] >= stelle[i]:
                raise ValueError(f"A{i} steht vor seinem Vorgänger A{v}")


def teilen(reihe, pruefer, vor=None):
    """reihe: Pakete des roten Bündels in seiner Reihenfolge (wie „drin“ von buendel_zusammensetzen, je mit „id“ und „gruende“) ·
    pruefer(pakete): Gesamtlauf über main + genau diese Pakete (leer = nur main) → {"ok": True|False, "meldung"}; jedes andere ok
    und jeder Fehler heißt: kein Ergebnis. Lässt sich die Menge nicht zusammensetzen, ist das rot · vor: {id: [Vorgänger]}.
    Rückgabe {"status", "meldung" (None bei GETEILT), "frei", "freigabe", "befunde", "wartet", "lead_liest", "laeufe"}:
    frei: grüne Pakete, je mit „lead_liest“ · freigabe: wer sie freigibt, AMW|Lead (None = nichts frei) · befunde: je schuldigem
    Paket {"aufgabe", "titel", "art", "zweig", "kopf", "agent", "meldung", "nach" (lief auf diesen grünen Paketen), "lead_liest"} ·
    wartet: der Rest, je mit „grund“ und „lead_liest“ · lead_liest: [{"aufgabe", "gruende"}] zum Markieren · laeufe: was lief,
    [{"pakete", "ok", "meldung"}]. Jedes Paket steht in genau einer der Listen frei, befunde, wartet."""
    reihe, vor = list(reihe), {k: list(v) for k, v in (vor or {}).items()}
    _pruefen(reihe, vor)
    gruende = {p["id"]: lead_gruende(p) for p in reihe}
    laeufe, befunde, wartet = [], [], []

    def lauf(teil):
        ids = [p["id"] for p in teil]
        try:
            a = pruefer(copy.deepcopy(teil))
        except Exception as x:                                    # noqa: BLE001 – ohne Ergebnis wird niemand beschuldigt
            a = {"ok": None, "meldung": f"{type(x).__name__}: {x}"[:500]}
        a = a if isinstance(a, dict) else {}
        ok, meldung = a.get("ok"), str(a.get("meldung") or "").strip()
        ok = ok if isinstance(ok, bool) else None
        laeufe.append({"pakete": ids, "ok": ok, "meldung": meldung})
        if ok is None:
            raise _Halt(UNKLAR, "Gesamtlauf ohne Ergebnis (" + (", ".join(f"A{i}" for i in ids) or "main") + ")" + (f": {meldung}" if meldung else ""))
        return ok, meldung or "Gesamtlauf rot (ohne Meldung)"

    def suchen(gruen, rest, meldung, basis_gruen):
        """Das schuldige Paket in rest (gruen + rest ist rot) → (Grünes davor, Paket, Meldung seines roten Laufs)."""
        teil, ganz = rest, True                                   # ganz: gruen + teil ist noch die ganze Ausgangsmenge
        while len(teil) > 1:
            links, rechts = teil[:len(teil) // 2], teil[len(teil) // 2:]
            ok, m = lauf(gruen + links)
            if ok:
                gruen, teil = gruen + links, rechts
            else:
                teil, meldung, ganz = links, m, False
        if ganz:                                                  # alle Hälften grün: zählt nur, wenn das Rot sich wiederholt
            ok, meldung = lauf(gruen + teil)
            if ok:
                raise _Halt(WACKELIG, "Bündel war rot, dieselbe Menge läuft jetzt grün – kein Paket ist belegt schuldig")
        if not gruen and not basis_gruen:
            ok, m = lauf([])
            if not ok:
                raise _Halt(BASIS_ROT, f"main ist schon ohne Pakete rot: {m}")
        return gruen, teil[0], meldung

    def ergebnis(status, meldung, frei):
        marke = lambda p: {**p, "lead_liest": bool(gruende[p["id"]])}
        frei = [marke(p) for p in frei]
        return {"status": status, "meldung": meldung, "frei": frei,
                "freigabe": ("Lead" if any(p["lead_liest"] for p in frei) else "AMW") if frei else None,
                "befunde": befunde, "wartet": [marke(p) for p in wartet],
                "lead_liest": [{"aufgabe": i, "gruende": g} for i, g in gruende.items() if g], "laeufe": laeufe}

    gruen, rest, meldung, basis_gruen = [], reihe, "", False
    try:
        while rest:
            gruen, p, meldung = suchen(gruen, rest, meldung, basis_gruen)
            basis_gruen = True                                    # main lief allein oder unter grünen Paketen
            befunde.append({"aufgabe": p["id"], **{k: p.get(k) for k in ("titel", "art", "zweig", "kopf", "agent")},
                            "meldung": meldung, "nach": [x["id"] for x in gruen], "lead_liest": bool(gruende[p["id"]])})
            fertig, draussen, neu = {x["id"] for x in gruen}, {p["id"]} | {x["id"] for x in wartet}, []
            for x in rest:
                if x["id"] in fertig or x["id"] == p["id"]:
                    continue
                fehlt = [v for v in vor.get(x["id"], ()) if v in draussen]
                if fehlt:
                    draussen.add(x["id"])
                    wartet.append({**x, "grund": "kommt nach " + ", ".join(f"A{v}" for v in fehlt) + " (schuldig oder wartet selbst)"})
                else:
                    neu.append(x)
            rest = neu
            if rest:
                ok, meldung = lauf(gruen + rest)
                if ok:
                    gruen, rest = gruen + rest, []
    except _Halt as h:
        weg = {b["aufgabe"] for b in befunde} | {x["id"] for x in wartet}
        wartet += [{**x, "grund": h.meldung} for x in reihe if x["id"] not in weg]
        return ergebnis(h.status, h.meldung, [])
    return ergebnis(GETEILT, None, gruen)
