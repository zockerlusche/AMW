"""Fensterkosten je Tätigkeit (A2058): bei jedem Wechsel der Tätigkeit eines Agenten eine Marke (plan_ereignis „taetigkeit“,
ohne Schemaänderung); jeder Kosten-Zuwachs seiner Sitzung (verbrauch) gehört zur letzten Marke davor.

Tätigkeiten: bauen · stapeln · pruefen_lassen · warten · fehlersuche · sonstiges (zwischen den Aufgaben).
Wechsel (wer merkt): Aufgabe starten → bauen; Aufgabe wartet/blockiert → nach der Art des Wartegrunds (Prüfung → pruefen_lassen,
Stapel → stapeln, sonst warten); Aufgabe fertig/verworfen → sonstiges (kern.aufgabe_status) · Prüfbitte → pruefen_lassen
(betrieb.pruefbitte) · eigener Lauf angemeldet → warten, eigener Lauf rot zu Ende → fehlersuche (betrieb) · Auslieferung → stapeln
(auslieferung). Ohne Marke gilt „bauen“ (wie bisher: der Zuwachs gehört der laufenden Aufgabe).
Die Prognose-Warnung vergleicht nur den Anteil „bauen“ (aufwand.je_aufgabe → bauen_usd, messung.kosten). `amw messung --kosten`
zeigt je Tag und Tätigkeit (je_tag).
"""
import json

from . import db

ART = "taetigkeit"
TAETIGKEITEN = ("bauen", "stapeln", "pruefen_lassen", "warten", "fehlersuche", "sonstiges")
NAMEN = {"bauen": "bauen", "stapeln": "stapeln", "pruefen_lassen": "prüfen lassen", "warten": "warten", "fehlersuche": "Fehlersuche",
         "sonstiges": "sonstiges"}
VORGABE = "bauen"


def merken(con, pid, agent, taetigkeit, aufgabe=None):
    """Marke setzen – im Schreibvorgang des Aufrufers oder für sich. Gleiche Tätigkeit und Aufgabe wie zuletzt: keine neue."""
    if not agent or taetigkeit not in TAETIGKEITEN or agent in ("AMW",):
        return None
    letzte = con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND von = ? ORDER BY id DESC LIMIT 1",
                         (pid, ART, agent)).fetchone()
    if letzte:
        d = json.loads(letzte[0] or "{}")
        if d.get("taetigkeit") == taetigkeit and d.get("aufgabe") == aufgabe:
            return None
    return db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=agent, art=ART, aufgabe_id=aufgabe,
                        text=json.dumps({"taetigkeit": taetigkeit, "aufgabe": aufgabe}, ensure_ascii=False))


def beim_warten(con, aid):
    """Tätigkeit einer wartenden Aufgabe aus ihren offenen Gründen (A2053: feste Art)."""
    from . import wartegrund
    sorten = {wartegrund.sorte(g["art"], g["bezug"]) for g in wartegrund.offene(con, aid)}
    if "wartet_pruefung" in sorten:
        return "pruefen_lassen"
    if "wartet_stapel" in sorten:
        return "stapeln"
    return "warten"


def marken(con, pid, agent):
    """[(zeit_utc, taetigkeit, aufgabe)] des Agenten, älteste zuerst."""
    aus = []
    for r in con.execute("SELECT zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND von = ? ORDER BY zeit_utc, id",
                         (pid, ART, agent)):
        try:
            d = json.loads(r["text"] or "{}")
        except ValueError:
            continue
        aus.append((r["zeit_utc"], d.get("taetigkeit") or VORGABE, d.get("aufgabe")))
    return aus


def bei(liste, t):
    """Tätigkeit zum Zeitpunkt t (letzte Marke davor) – ohne Marke die Vorgabe „bauen“."""
    tk = VORGABE
    for zeit, x, _ in liste:
        if zeit > t:
            break
        tk = x
    return tk


def je_tag(con, pid, ab=None):
    """{tag: {taetigkeit: usd}} über alle Fenster-Agenten des Projekts (Zuwächse der Sitzungs-Zähler, wie aufwand)."""
    from . import aufwand
    aus = {}
    for (kennung,) in con.execute("SELECT DISTINCT kennung FROM agent WHERE projekt_id = ?", (pid,)).fetchall():
        liste = marken(con, pid, kennung)
        for t, zuwachs in aufwand.zuwaechse(con, pid, kennung, ab or "0"):
            tk = bei(liste, t)
            tag = aus.setdefault(t[:10], {})
            tag[tk] = round(tag.get(tk, 0.0) + zuwachs, 4)
    return dict(sorted(aus.items()))
