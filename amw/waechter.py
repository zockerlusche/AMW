"""Wächter für kopflose Arbeiter (M50 S4 / A1847) – harte Startregeln, Plätze, Wartungsmodus, Protokoll (D1258 v4 §5;
D1270 Nr. 6, 9, 14, 17, 34, 35; Regel 8 nach Marcel F5344 / B2891).

Bevor die AMW ein Paket der Art p startet, fragt sie hier. Jede Regel hat eine Nummer; „nicht gestartet, Regel N“ steht
im Planungs-Protokoll (plan_ereignis „waechter“, nur bei Änderung – kein Protokoll-Rauschen bei jeder Runde).
Regel 10 ist der Aus-Schalter: ohne eingerichtete Plätze (plaetze = 0) startet nichts, die AMW arbeitet wie bisher.
Regel 6 („Abnahme vor dem Bau rot“) braucht den vorbereiteten Platz – der Starter (S5) prüft sie mit abnahme.rot_vor_bau
und meldet das Ergebnis über `regel6`.

Wartungsmodus und Pause sind ein Zustand dieses PCs (%LOCALAPPDATA%\\amw\\waechter.json): eine Auslieferung der AMW setzt
den Wartungsmodus und wartet, bis laufende p-Pakete enden; zweimal hintereinander „unklar“/„abgebrochen“ setzt die Pause.
Beides hebt der Lead oder der Mensch auf (amw waechter weiter).
"""
import datetime
import json
import os
import re
import time

from . import db

REGELN = {
    1: "Art p ohne Abnahme-Befehl oder ohne Bereiche",
    2: "Bereiche überschneiden sich mit einem laufenden Paket",
    3: "Art p mit Grafikkarte/Bildschirm oder Gewicht schwer – nicht in Stufe 1",
    4: "alle Arbeitsplätze belegt",
    5: "gesperrte Bereiche im Paket",
    6: "Abnahme vor dem Bau schon grün – sie prüft nichts",
    7: "Wartungsmodus aktiv",
    8: "Wochenlimit des Kontos bei 80 % oder mehr",
    9: "zweimal hintereinander unklar oder abgebrochen – Pause",
    10: "keine Arbeitsplätze eingerichtet",
    11: "neue Claude-Code-Version noch nicht geprüft – die AMW prüft sie selbst (Negativprobe)",
}
WARTEN = {2, 4, 7, 8, 9, 11}               # vorübergehend: später erneut prüfen; die anderen: nicht starten, Lead melden
LIMIT_PROZENT = 80
LAUFEND = ("laeuft", "abgegeben", "abnahme", "merge_reihe")   # P245: der Platz bleibt bis zum Merge belegt (Resume nur dort)


def _datei():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "amw", "waechter.json")


def zustand():
    """{"wartung": {"seit", "grund"} | None, "pause": {"seit", "grund"} | None}"""
    try:
        with open(_datei(), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    return {"wartung": d.get("wartung"), "pause": d.get("pause")}


def _setzen(**werte):
    d = zustand()
    d.update(werte)
    os.makedirs(os.path.dirname(_datei()), exist_ok=True)
    tmp = _datei() + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, _datei())


def _jetzt():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def wartung_an(grund):
    _setzen(wartung={"seit": _jetzt(), "grund": grund})


def wartung_aus():
    _setzen(wartung=None)


def pause_an(grund):
    _setzen(pause={"seit": _jetzt(), "grund": grund})


def weiter(con=None, pid=None, von="AMW"):
    """Wartungsmodus und Pause aufheben (Lead/Mensch). P253: Regel 9 zählt danach nur neue Enden, sonst setzte die alte Folge
    „unklar, unklar“ die Pause sofort wieder. P265 (b): der Merker ist ein Ereignis „waechter_weiter“ in der Datenbank selbst –
    nach dem Zurückspielen einer älteren DB gilt deren eigener Stand, nicht eine Zahl aus der Datei dieses PCs."""
    if con is not None and pid is not None:
        from . import db
        with db.schreiben(con):
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art="waechter_weiter",
                         text="Wartungsmodus und Pause aufgehoben")
    _setzen(wartung=None, pause=None)


def _weiter_nach(con):
    """Ereignis-Nummer des letzten „weiter“ (alle Projekte – Pause und Wartungsmodus gelten für den ganzen PC)."""
    return con.execute("SELECT coalesce(max(id), 0) FROM plan_ereignis WHERE art = 'waechter_weiter'").fetchone()[0] or 0


def bereiche(text):
    """Freitext der Aufgabe (--dateien) → Liste: getrennt an Komma, Semikolon, Leerraum."""
    return [b for b in re.split(r"[,;\s]+", text or "") if b]


def _ueberschneiden(a, b):
    """Zwei Bereichslisten überschneiden sich, wenn ein Eintrag Präfix des anderen ist oder sie gleich sind (Klein)."""
    from . import abnahme
    for x in a:
        for y in b:
            x2, y2 = abnahme._klein(x), abnahme._klein(y)
            if x2 == y2 or x2.startswith(y2.rstrip("*")) or y2.startswith(x2.rstrip("*")):
                return True
    return False


def angenommen(con, aid):
    """A1897 Zusatz 3 (#29493): vom Lead nach E4 angenommen – Stand im Projekt-Repo, Platz schon archiviert. Ein solches Paket
    in merge_reihe belegt keinen Platz und hält keine Auslieferung an."""
    r = con.execute("SELECT text FROM plan_ereignis WHERE aufgabe_id = ? AND art = 'paket_entscheidung' ORDER BY id DESC LIMIT 1",
                    (aid,)).fetchone()
    try:
        return json.loads((r[0] if r else None) or "{}").get("quelle") == "projekt"
    except ValueError:
        return False


def belegt(con, zeilen, id_spalte="aufgabe_id"):
    """Zeilen (mit Spalten id_spalte und zustand) ohne angenommene Pakete in merge_reihe."""
    return [r for r in zeilen if not (r["zustand"] == "merge_reihe" and angenommen(con, r[id_spalte]))]


def laufende(con, pid):
    """p-Pakete des Projekts, die einen Platz belegen: [{"id", "bereiche"}]."""
    return [{"id": r["id"], "bereiche": bereiche(r["dateibereich"])} for r in belegt(con, con.execute(
        "SELECT a.id, a.dateibereich, k.zustand FROM paket k JOIN aufgabe a ON a.id = k.aufgabe_id WHERE a.projekt_id = ? AND k.art = 'p'"
        f" AND k.zustand IN ({','.join('?' * len(LAUFEND))})", (pid, *LAUFEND)).fetchall(), "id")]


def _letzte_enden(con, pid, n=2, nach=0):
    """Die letzten n Enden von p-Läufen (Übergang aus „laeuft“) nach Ereignis `nach` (dem letzten „weiter“) – Zielzustand.
    A1849 (§6a.4 Fehlserie): ein Abbruch durch Notbremse oder Limit (E1n) zählt nicht – er wird übersprungen."""
    aus = []
    for r in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = 'paket_zustand' AND text LIKE 'laeuft → %'"
                         " AND id > ? ORDER BY id DESC", (pid, nach)):
        rest = r["text"].split("→", 1)[1]
        if ":" in rest and rest.split(":", 1)[1].strip().startswith("E1n"):
            continue
        aus.append(rest.split(":", 1)[0].strip())
        if len(aus) >= n:
            break
    return aus


def pruefen(con, pid, aid, limit=None):
    """Darf Paket `aid` jetzt starten? {"ok", "regel", "grund", "warten"} – Regel 6 prüft der Starter am Platz (regel6).
    limit: Wochenlimit in Prozent (sonst aus tokenprognose)."""
    from . import abnahme, arbeitspaket, platz
    a = con.execute("SELECT id, pruefbefehl, dateibereich FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    if not a:
        from . import kern
        raise kern.AmwFehler(f"A{aid} gibt es nicht")
    f = arbeitspaket.lesen(con, aid)
    if f["art"] != "p":
        return {"ok": False, "regel": None, "grund": "kein Paket der Art p – der Wächter startet nur p", "warten": False}
    plaetze = platz.plaetze(con, pid)
    if not plaetze:
        return _nein(10)
    z = zustand()
    if z["wartung"]:
        return _nein(7, z["wartung"].get("grund"))
    if z["pause"]:
        return _nein(9, z["pause"].get("grund"))
    from . import versionsprobe
    neu = versionsprobe.sperre(con)                           # A1906: ungeprüfte Version → kein Start, die Probe läuft
    if neu:
        return dict(_nein(11, f"Claude Code {neu}"), version=neu)
    enden = _letzte_enden(con, pid, nach=_weiter_nach(con))
    if len(enden) == 2 and all(e in ("unklar", "abgebrochen") for e in enden):
        pause_an("zweimal hintereinander unklar oder abgebrochen")
        return _nein(9)
    hinweis = None
    if limit is None:
        try:
            from . import tokenprognose
            lage = tokenprognose.lage_gemerkt(con)
            limit = lage.get("wert") if lage else None
        except Exception:
            limit = None
    if limit is None:
        hinweis = "Wochenlimit unbekannt – Start erlaubt"         # P245: Marcel will nicht 100 % überwachen, aber es steht im Protokoll
    elif limit >= LIMIT_PROZENT:
        return _nein(8, f"{limit:.0f} % verbraucht")
    b = bereiche(a["dateibereich"])
    if not (a["pruefbefehl"] or "").strip() or not b:
        return _nein(1)
    if f["gewicht"] == "schwer" or f["ressourcen"]:
        return _nein(3)
    gesp = abnahme.startregel(b, f["pakettyp"])
    if gesp:
        return _nein(5, ", ".join(f"{x} ({g})" for x, g in gesp))
    lauf = [x for x in laufende(con, pid) if x["id"] != aid]
    if len(lauf) >= len(plaetze):
        return _nein(4, f"{len(lauf)} von {len(plaetze)} belegt")
    for x in lauf:
        if _ueberschneiden(b, x["bereiche"]):
            return _nein(2, f"mit A{x['id']}")
    return {"ok": True, "regel": None, "grund": None, "warten": False, "hinweis": hinweis}


def _nein(n, zusatz=None):
    return {"ok": False, "regel": n, "grund": REGELN[n] + (f" – {zusatz}" if zusatz else ""), "warten": n in WARTEN}


def regel6(ergebnis):
    """Ergebnis von abnahme.rot_vor_bau → Wächter-Antwort (der Starter prüft es am vorbereiteten Platz)."""
    return {"ok": True, "regel": None, "grund": None, "warten": False} if ergebnis.get("ok") else _nein(6, ergebnis.get("grund"))


def protokollieren(con, pid, aid, antwort, von="AMW"):
    """„A12 nicht gestartet, Regel 4: …“ ins Planungs-Protokoll – nur, wenn es sich gegenüber dem letzten Eintrag ändert."""
    if antwort.get("ok") and antwort.get("hinweis"):
        text = f"A{aid} darf starten – {antwort['hinweis']}"[:300]
    elif antwort.get("ok") or not antwort.get("regel"):
        return False
    else:
        text = f"A{aid} nicht gestartet, Regel {antwort['regel']}: {antwort['grund']}"[:300]
    letzt = con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = 'waechter' AND aufgabe_id = ? ORDER BY id DESC LIMIT 1",
                        (pid, aid)).fetchone()
    if letzt and letzt["text"] == text:
        return False
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art="waechter", aufgabe_id=aid, text=text)
    return True


def protokoll(con, pid, aid=None, grenze=50):
    sql = "SELECT zeit_utc, aufgabe_id, text FROM plan_ereignis WHERE projekt_id = ? AND art = 'waechter'"
    p = [pid]
    if aid:
        sql += " AND aufgabe_id = ?"
        p.append(aid)
    return [dict(r) for r in con.execute(sql + " ORDER BY id DESC LIMIT ?", (*p, grenze))]


def reihenfolge(con, pid):
    """Startklare p-Pakete in Startfolge: Rang (kleiner zuerst), dann Nummer; Pakete, deren Vorgänger („nach X“) noch nicht
    fertig/gemergt sind, fehlen. [{"id", "titel", "rang"}]"""
    kandidaten = con.execute(
        "SELECT a.id, a.titel, a.rang FROM paket k JOIN aufgabe a ON a.id = k.aufgabe_id WHERE a.projekt_id = ? AND k.art = 'p'"
        " AND k.zustand = 'startklar' ORDER BY coalesce(a.rang, 999999), a.id", (pid,)).fetchall()
    aus = []
    for k in kandidaten:
        offen = con.execute(
            "SELECT 1 FROM abhaengigkeit d JOIN aufgabe v ON v.id = d.vor LEFT JOIN paket pv ON pv.aufgabe_id = v.id"
            " WHERE d.nach = ? AND d.extern IS NULL AND NOT (v.status IN ('fertig', 'verworfen') OR coalesce(pv.zustand, '') IN ('gemergt', 'fertig'))",
            (k["id"],)).fetchone()
        if not offen:
            aus.append({"id": k["id"], "titel": k["titel"], "rang": k["rang"]})
    return aus


def p_laufend(con):
    """Laufen auf diesem PC p-Pakete (alle Projekte)? Ohne Tabelle paket (ältere Datenbank): nein."""
    import sqlite3
    try:
        return bool(belegt(con, con.execute(f"SELECT aufgabe_id, zustand FROM paket WHERE art = 'p' AND zustand IN"
                                            f" ({','.join('?' * len(LAUFEND))})", LAUFEND).fetchall()))
    except sqlite3.Error:
        return False


def vor_auslieferung(con, frist_s=1800, warte_s=15, schlafen=time.sleep):
    """Auslieferung der AMW: Wartungsmodus setzen und warten, bis keine p-Pakete mehr laufen (alle Projekte dieses PCs).
    Rückgabe (fertig: bool, noch_laufend: [A-Nummern]). Ohne laufende p-Pakete sofort fertig."""
    ids = lambda: [r["aufgabe_id"] for r in belegt(con, con.execute(   # A1897 Zusatz 3: angenommene Pakete halten nicht an
        f"SELECT aufgabe_id, zustand FROM paket WHERE art = 'p' AND zustand IN ({','.join('?' * len(LAUFEND))})", LAUFEND).fetchall())]
    if not zustand()["wartung"]:
        wartung_an("Auslieferung der AMW")
    ende = time.monotonic() + frist_s
    while True:
        lauf = ids()
        if not lauf:
            return True, []
        if time.monotonic() >= ende:
            return False, lauf
        schlafen(warte_s)
