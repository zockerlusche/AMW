"""Bündel-Auslöser (A2119; TH158 F5, Lead-Ja TL #32140): Soll jetzt ein Bündel gebildet werden?

`entscheiden` ist rein – keine Datenbank, keine Uhr, kein Agent, keine Tokens: alles steht in den Argumenten. Gründe (jeder
einzelne genügt, aber nie ohne ein bereites Paket):
- anzahl     n abgenommene Pakete sind bereit (Vorgabe 4),
- zeit       x Stunden seit der letzten Auslieferung (Vorgabe 3); noch nie ausgeliefert = fällig,
- leerlauf   kein Agent hat ein startklares Paket,
- blockiert  ein bereites Paket hält andere Arbeit auf – dann früher, ohne auf n oder x zu warten. Was blockiert, aber selbst
             nicht bereit ist, zählt nicht: das Bündel brächte es nicht nach main.

n und x gelten je Projekt (projekt.einstellungen: buendel_n, buendel_x_h; fehlt ein Wert oder ist er kaputt, gilt die Vorgabe).
Ändern: Lead oder Mensch (`einstellen`). Das Bündel selbst baut buendel.buendeln.
"""
import datetime
import json
import math

from . import db, kern

N, X = "buendel_n", "buendel_x_h"                      # Schlüssel in projekt.einstellungen
N_VORGABE, X_VORGABE_H = 4, 3
N_GRENZEN, X_GRENZEN_H = (1, 50), (0.25, 168)
_BLEIBT = object()


# --- Entscheidung (rein) -----------------------------------------------------------------------------------------------------

def _zeit(t):
    """Zeit mit Zeitzone – aus datetime oder dem gespeicherten UTC-Text; sonst ValueError."""
    if not isinstance(t, datetime.datetime):
        return db.utc_lesen(t)
    if t.tzinfo is None:
        raise ValueError("Zeit ohne Zeitzone")
    return t


def entscheiden(bereit, letzte_auslieferung, agenten_startklar, jetzt, blockierend=(), n=N_VORGABE, x_h=X_VORGABE_H):
    """Wird jetzt ein Bündel gebildet?
    bereit: Nummern der abgenommenen Pakete, die ins Bündel könnten · letzte_auslieferung, jetzt: datetime mit Zeitzone oder
    UTC-Text (letzte_auslieferung None = noch nie) · agenten_startklar: Agenten mit mindestens einem startklaren Paket ·
    blockierend: Nummern der Pakete, auf die andere Arbeit wartet.
    Rückgabe {"buendeln": bool, "gruende": [Codes, feste Reihenfolge], "blockierend": [bereite davon], "text": ein Satz}."""
    bereit = set(bereit)
    blockiert = sorted(bereit & set(blockierend))
    laufen_weiter = any(True for _ in agenten_startklar)
    alter_h = None if letzte_auslieferung is None else (_zeit(jetzt) - _zeit(letzte_auslieferung)).total_seconds() / 3600
    if not bereit:
        return {"buendeln": False, "gruende": [], "blockierend": [], "text": "kein Paket bereit"}
    anzahl = f"{len(bereit)} Paket{'e' if len(bereit) != 1 else ''} bereit"
    gruende = []
    if len(bereit) >= n:
        gruende.append(("anzahl", f"{anzahl} (ab {n})"))
    if alter_h is None:
        gruende.append(("zeit", "noch nie ausgeliefert"))
    elif alter_h >= x_h:
        gruende.append(("zeit", f"{alter_h:.1f} h seit der letzten Auslieferung (ab {x_h:g} h)"))
    if not laufen_weiter:
        gruende.append(("leerlauf", "Leerlauf: kein Agent hat ein startklares Paket"))
    if blockiert:
        gruende.append(("blockiert", "andere Arbeit wartet auf " + ", ".join(f"A{a}" for a in blockiert)))
    text = " · ".join(t for _, t in gruende) if gruende else f"wartet: {len(bereit)} von {n} Paketen bereit"
    return {"buendeln": bool(gruende), "gruende": [g for g, _ in gruende], "blockierend": blockiert, "text": text}


# --- Einstellungen je Projekt ---------------------------------------------------------------------------------------------------

def wert_pruefen(schluessel, v):
    """Bereinigter Wert für buendel_n bzw. buendel_x_h; None = leer (Vorgabe). Sonst ValueError."""
    lo, hi = N_GRENZEN if schluessel == N else X_GRENZEN_H
    fehler = ValueError(f"{schluessel}: {'ganze Zahl' if schluessel == N else 'Stunden'} {lo:g}–{hi:g} (leer = Vorgabe)")
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, bool):
        raise fehler
    try:
        z = float(v.strip().replace(",", ".") if isinstance(v, str) else v)
    except (TypeError, ValueError, OverflowError):
        raise fehler from None
    if not math.isfinite(z) or not lo <= z <= hi or (schluessel == N and z != int(z)):
        raise fehler
    return int(z) if z == int(z) else z


def einstellung(con, pid):
    """{"n", "x_h"} des Projekts – fehlt ein Wert oder ist er kaputt, die Vorgabe. Passt als **-Argumente zu entscheiden."""
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    try:
        e = json.loads((r[0] if r else None) or "{}")
    except ValueError:
        e = {}
    aus = {}
    for name, schluessel, vorgabe in (("n", N, N_VORGABE), ("x_h", X, X_VORGABE_H)):
        try:
            v = wert_pruefen(schluessel, e.get(schluessel) if isinstance(e, dict) else None)
        except ValueError:
            v = None
        aus[name] = vorgabe if v is None else v
    return aus


def einstellen(con, pid, von, n=_BLEIBT, x_h=_BLEIBT):
    """n und/oder x des Projekts setzen (leer = zurück zur Vorgabe). Lead oder Mensch. Rückgabe wie einstellung."""
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Wann ein Bündel gebildet wird, stellt der Lead oder der Mensch ein")
    try:
        neu = {k: wert_pruefen(k, v) for k, v in ((N, n), (X, x_h)) if v is not _BLEIBT}
    except ValueError as f:
        raise kern.AmwFehler(str(f)) from None
    with db.schreiben(con):
        r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
        if not r:
            raise kern.AmwFehler(f"Projekt {pid} gibt es nicht")
        try:
            e = json.loads(r[0] or "{}")
        except ValueError:
            e = None
        if not isinstance(e, dict):                    # nie überschreiben: sonst wären die anderen Einstellungen weg
            raise kern.AmwFehler("Die Projekt-Einstellungen sind nicht lesbar – nichts gespeichert")
        for k, v in neu.items():
            if v is None:
                e.pop(k, None)
            else:
                e[k] = v
        con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?", (json.dumps(e, ensure_ascii=False), pid))
    return einstellung(con, pid)
