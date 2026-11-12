"""Empfehlung für Modell und Denkaufwand (A1611 Stufe E2, Konzept D906) – nur zum Ansehen, gesetzt wird im Profil.

Der Lead gibt einer Aufgabe beim Anlegen Größe (S|M|L|XL) und Art. Die Arten fallen in drei Gruppen; eine Tabelle je
Projekt (Gruppe × Größe → „modell/denkaufwand“, Projekt-Einstellung „empfehlung“) liefert den Vorschlag. Daneben steht,
was fertige Aufgaben derselben Zelle gemessen verbraucht haben (aufwand.py) und wie oft ihre Prüfung rot war. Je Agent:
die häufigste Zelle seiner letzten Aufgaben. Die AMW stellt nichts selbst um und startet nichts neu (Marcel #22441).
"""
import json
import statistics

from . import aufwand, kern

GROESSEN = ("S", "M", "L", "XL")
ARTEN = ("text", "mechanisch", "fehlersuche", "oberflaeche", "sicherheit", "konzept")
GRUPPE = {"text": "einfach", "mechanisch": "einfach", "fehlersuche": "mittel", "oberflaeche": "mittel",
          "sicherheit": "heikel", "konzept": "heikel"}
GRUPPEN = ("einfach", "mittel", "heikel")
MODELLE = ("haiku", "sonnet", "opus", "fable")          # Kurznamen, wie `claude --model` sie nimmt
STUFEN = ("low", "medium", "high", "xhigh", "max")
STANDARD = {                                            # Startwerte (D906 Abschnitt 2) – Annahme, nicht gemessen
    "einfach": {"S": "sonnet/low", "M": "sonnet/medium", "L": "sonnet/medium", "XL": "opus/medium"},
    "mittel": {"S": "sonnet/medium", "M": "opus/medium", "L": "opus/high", "XL": "opus/high"},
    "heikel": {"S": "opus/medium", "M": "opus/high", "L": "opus/high", "XL": "opus/xhigh"},
}
LETZTE = 10                                             # je Agent: häufigste Zelle seiner letzten so vielen Aufgaben


def wert_pruefen(w):
    """„opus/high“ → „opus/high“; sonst ValueError."""
    m, _, s = str(w or "").strip().lower().partition("/")
    if m not in MODELLE or s not in STUFEN:
        raise ValueError(f"„{w}“: Modell/Denkaufwand, z. B. sonnet/medium (Modell: {' | '.join(MODELLE)};"
                         f" Denkaufwand: {' | '.join(STUFEN)})")
    return f"{m}/{s}"


def tabelle_pruefen(t):
    """Projekt-Einstellung „empfehlung“: {gruppe: {groesse: "modell/stufe"}}. Gespeichert wird nur, was vom Standard
    abweicht (so wandern spätere bessere Startwerte mit)."""
    if isinstance(t, str):
        t = json.loads(t or "{}")
    if not isinstance(t, dict):
        raise ValueError("Tabelle erwartet: {gruppe: {S|M|L|XL: modell/stufe}}")
    aus = {}
    for g, zeile in t.items():
        if g not in GRUPPEN or not isinstance(zeile, dict):
            raise ValueError(f"Gruppe „{g}“ gibt es nicht: {' | '.join(GRUPPEN)}")
        for gr, w in zeile.items():
            if gr not in GROESSEN:
                raise ValueError(f"Größe „{gr}“ gibt es nicht: {' | '.join(GROESSEN)}")
            w = wert_pruefen(w)
            if w != STANDARD[g][gr]:
                aus.setdefault(g, {})[gr] = w
    return aus


def tabelle(con, pid):
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    eigen = (json.loads(r[0] or "{}") if r else {}).get("empfehlung") or {}
    return {g: {gr: (eigen.get(g) or {}).get(gr) or STANDARD[g][gr] for gr in GROESSEN} for g in GRUPPEN}


def _teile(w):
    m, _, s = w.partition("/")
    return {"modell": m, "denkstufe": s}


def passt(profil, vorschlag):
    """Profil des Agenten gegen den Vorschlag: True/False; None, wenn das Profil Modell oder Denkaufwand offen lässt
    (dann gilt, was Claude Code von sich aus nimmt – das weiß die AMW nicht)."""
    if not profil or not profil.get("modell") or not profil.get("denkstufe"):
        return None
    return vorschlag["modell"] in str(profil["modell"]).lower() and profil["denkstufe"] == vorschlag["denkstufe"]


def zellen(con, pid):
    """Gemessen je Zelle (gruppe, groesse): Median, Anzahl fertiger Aufgaben mit Messwert, davon mit roter Prüfung."""
    werte = {}
    for (kennung,) in con.execute("SELECT DISTINCT agent FROM aufgabe WHERE projekt_id = ? AND status = 'fertig' AND groesse IS NOT NULL"
                                  " AND art IS NOT NULL AND begonnen_utc IS NOT NULL AND agent IS NOT NULL", (pid,)).fetchall():
        alle = aufwand._aufgaben(con, pid, kennung)
        werte.update({aid: e["usd"] for aid, e in aufwand._zuordnen(con, pid, kennung, alle, alle[0]["begonnen_utc"]).items()})
    aus = {}
    for a in con.execute("SELECT a.id, a.groesse, a.art, EXISTS (SELECT 1 FROM pruefung p WHERE p.aufgabe_id = a.id AND p.ergebnis = 'rot')"
                         " AS rot FROM aufgabe a WHERE a.projekt_id = ? AND a.status = 'fertig' AND a.groesse IS NOT NULL AND a.art IS NOT NULL",
                         (pid,)).fetchall():
        if werte.get(a["id"], 0) > 0:
            z = aus.setdefault((GRUPPE[a["art"]], a["groesse"]), {"usd": [], "rot": 0})
            z["usd"].append(werte[a["id"]])
            z["rot"] += a["rot"]
    return {k: {"median": round(statistics.median(z["usd"]), 2), "n": len(z["usd"]), "rot": z["rot"]} for k, z in aus.items()}


def fuer_aufgabe(con, pid, aid):
    """Vorschlag für eine Aufgabe mit Größe und Art, sonst None. Mit Messwert der Zelle und Profil des Zugeteilten."""
    a = con.execute("SELECT agent, groesse, art FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    if not a or not a["groesse"] or not a["art"]:
        return None
    g = GRUPPE[a["art"]]
    v = _teile(tabelle(con, pid)[g][a["groesse"]])
    profil = None
    if a["agent"] and a["agent"] != kern.ENTWICKLER:
        z = con.execute("SELECT modell, denkstufe FROM agent WHERE projekt_id = ? AND kennung = ?", (pid, a["agent"])).fetchone()
        profil = {"modell": z["modell"], "denkstufe": z["denkstufe"]} if z else None
    return {"groesse": a["groesse"], "art": a["art"], "gruppe": g, **v, "zelle": zellen(con, pid).get((g, a["groesse"])),
            "agent": a["agent"], "profil": profil, "passt": passt(profil, v)}


def fuer_agent(con, pid, kennung, letzte=LETZTE):
    """Häufigste Zelle der letzten Aufgaben des Agenten (begonnen, mit Größe und Art; bei Gleichstand die jüngere) →
    Vorschlag, verglichen mit seinem Profil. None ohne solche Aufgaben."""
    liste = con.execute("SELECT groesse, art FROM aufgabe WHERE projekt_id = ? AND agent = ? AND groesse IS NOT NULL AND art IS NOT NULL"
                        " AND begonnen_utc IS NOT NULL AND status != 'verworfen' ORDER BY begonnen_utc DESC, id DESC LIMIT ?",
                        (pid, kennung, letzte)).fetchall()
    if not liste:
        return None
    zaehler = {}
    for i, a in enumerate(liste):
        k = (GRUPPE[a["art"]], a["groesse"])
        n, erst = zaehler.get(k, (0, i))
        zaehler[k] = (n + 1, erst)
    (g, gr), (n, _) = max(zaehler.items(), key=lambda x: (x[1][0], -x[1][1]))
    v = _teile(tabelle(con, pid)[g][gr])
    z = con.execute("SELECT modell, denkstufe FROM agent WHERE projekt_id = ? AND kennung = ?", (pid, kennung)).fetchone()
    profil = {"modell": z["modell"], "denkstufe": z["denkstufe"]} if z else None
    return {**v, "gruppe": g, "groesse": gr, "n": n, "von": len(liste), "profil": profil, "passt": passt(profil, v)}


def felder_pruefen(werte):
    """aufgabe neu/aendern: groesse (S|M|L|XL, auch klein geschrieben) und art prüfen und vereinheitlichen."""
    if werte.get("groesse") is not None:
        werte["groesse"] = str(werte["groesse"]).strip().upper()
        if werte["groesse"] not in GROESSEN:
            raise kern.AmwFehler(f"Größe: {' | '.join(GROESSEN)}")
    if werte.get("art") is not None:
        werte["art"] = str(werte["art"]).strip().lower()
        if werte["art"] not in ARTEN:
            raise kern.AmwFehler(f"Art: {' | '.join(ARTEN)}")
    return werte
