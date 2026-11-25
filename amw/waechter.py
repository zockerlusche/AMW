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
    2: "Bereiche überschneiden sich mit einem anderen Paket",
    3: "Art p mit Grafikkarte/Bildschirm oder Gewicht schwer – nicht in Stufe 1",
    4: "alle Headless-Agenten belegt",
    5: "gesperrte Bereiche im Paket",
    6: "Abnahme vor dem Bau schon grün – sie prüft nichts",
    7: "Wartungsmodus aktiv",
    8: "Wochenlimit des Kontos bei 80 % oder mehr",
    9: "zweimal hintereinander unklar oder abgebrochen – Pause",
    10: "keine Headless-Agenten eingerichtet",
    11: "neue Claude-Code-Version noch nicht geprüft – die AMW prüft sie selbst (Negativprobe)",
    12: "Projekt ausgeschaltet (Projekt-Schalter aus oder probe)",
    13: "Anbieter in diesem Projekt nicht freigegeben (gibt nur der Mensch frei)",
    14: "Anbieter mit dieser Claude-Code-Version noch nicht geprüft – die AMW prüft ihn selbst (Negativprobe)",
    15: "angehalten bis zum Ja zu einer Konzeptänderung",
}
ARBEITEND = ("laeuft", "abgegeben", "abnahme")   # A1925: zählt für die PC-Grenze (plaetze_pc) – merge_reihe arbeitet nicht mehr
WARTEN = {2, 4, 7, 8, 9, 11, 14, 15}               # vorübergehend: später erneut prüfen; die anderen: nicht starten, Lead melden
LIMIT_PROZENT = 80
LAUFEND = ("laeuft", "abgegeben", "abnahme", "merge_reihe")   # P245: der Platz bleibt bis zum Merge belegt (Resume nur dort)


def _datei():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "amw", "waechter.json")


def zustand():
    """{"wartung": {"seit", "grund"} | None, "pause": {"seit", "grund", "bis"?} | None} – eine Pause mit abgelaufenem Ende
    (A2042) gilt nicht mehr."""
    try:
        with open(_datei(), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    pause = d.get("pause")
    if pause and pause.get("bis") and pause["bis"] <= _jetzt():
        pause = None
    return {"wartung": d.get("wartung"), "pause": pause}


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


def wartung_an(grund, kette=None):
    """kette (A2136): Prozess der Auslieferung, die ihn setzt – bricht sie ab, darf die nächste ihn übernehmen und beenden."""
    _setzen(wartung={"seit": _jetzt(), "grund": grund, **({"kette": kette} if kette else {})})


def wartung_von_kette():
    """Hat eine Auslieferung den Wartungsmodus gesetzt, die nicht mehr läuft (oder dieser Prozess selbst)? Ein von Hand gesetzter nie."""
    from . import steuerung
    k = (zustand()["wartung"] or {}).get("kette")
    return bool(k) and (k == os.getpid() or not steuerung.lebt(k))


def wartung_aus():
    _setzen(wartung=None)


def pause_an(grund, bis=None):
    """bis (A2042): UTC-ISO – danach gilt die Pause nicht mehr (zustand)."""
    _setzen(pause={"seit": _jetzt(), "grund": grund, **({"bis": bis} if bis else {})})


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
    """Angenommen – Stand im Projekt-Repo, Platz schon archiviert: vom Lead nach E4 (A1897 Zusatz 3, #29493) oder von der AMW nach
    E7 (A2105). Ein solches Paket in merge_reihe belegt keinen Platz und hält keine Auslieferung an. platz_frei false: gesichert, aber
    der Platz ließ sich nicht zurücksetzen – er bleibt belegt."""
    r = con.execute("SELECT text FROM plan_ereignis WHERE aufgabe_id = ? AND art = 'paket_entscheidung' ORDER BY id DESC LIMIT 1",
                    (aid,)).fetchone()
    try:
        d = json.loads((r[0] if r else None) or "{}")
        return d.get("quelle") == "projekt" and d.get("platz_frei", True) is not False
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


def offene_bereiche(con, pid):
    """A2105: alle p-Pakete, deren Dateien noch nicht ausgeliefert sind – die laufenden und alle bereit zum Merge, auch wenn ihr Platz
    schon frei ist (sonst gäbe es Konflikte im Bündel): [{"id", "titel", "bereiche", "angenommen"}]."""
    return [{"id": r["id"], "titel": r["titel"], "bereiche": bereiche(r["dateibereich"]), "angenommen": r["zustand"] == "merge_reihe"}
            for r in con.execute("SELECT a.id, a.titel, a.dateibereich, k.zustand FROM paket k JOIN aufgabe a ON a.id = k.aufgabe_id"
                                 f" WHERE a.projekt_id = ? AND k.art = 'p' AND k.zustand IN ({','.join('?' * len(LAUFEND))}) ORDER BY a.id",
                                 (pid, *LAUFEND)).fetchall()]


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
    from . import delta_halt, kern
    if g := delta_halt.haelt(con, aid):                   # A2140
        return _nein(15, f"wartet auf {g}")
    s = kern.projekt_schalter(con, pid)
    if s != "an":                                         # A1925 (E5): aus/probe – keine p-Starts
        return _nein(12, f"Schalter {s}")
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
    if f["anbieter"] != "anthropic":                     # A1931 (TH159): nur freigegebene Anbieter, lokale belegen die Grafikkarte
        from . import anbieter, versionsprobe
        e = anbieter.eintrag(con, pid, f["anbieter"])
        if not e:
            return _nein(13, f["anbieter"])
        if e.get("lokal"):
            return _nein(3, f"lokaler Anbieter {f['anbieter']} belegt die Grafikkarte")
        v = versionsprobe.installiert()
        if v and not versionsprobe.anbieter_geprueft(con, f["anbieter"], v):
            return dict(_nein(14, f"{f['anbieter']} mit Claude Code {v}"), anbieter=f["anbieter"], version=v)
    gesp = abnahme.startregel(b, f["pakettyp"], abnahme.projekt_muster(con, pid))   # A1919: feste Liste + Muster des Projekts
    if gesp:
        return _nein(5, ", ".join(f"{x} ({g})" for x, g in gesp))
    lauf = [x for x in laufende(con, pid) if x["id"] != aid]
    if len(lauf) >= len(plaetze):
        return _nein(4, f"{len(lauf)} von {len(plaetze)} belegt")
    pc = pc_belegt(con, aid)                             # A1925 (E2): gemeinsame Grenze über alle Projekte
    if pc["grenze"] and len(pc["arbeiten"]) >= pc["grenze"]:
        return _nein(4, f"wartet auf einen Platz (PC: {len(pc['arbeiten'])} von {pc['grenze']} belegt: "
                        + ", ".join(f"{n} A{a}" for n, a in pc["arbeiten"]) + ")")
    for x in offene_bereiche(con, pid):
        if x["id"] != aid and _ueberschneiden(b, x["bereiche"]):
            return _nein(2, f"mit A{x['id']} „{(x['titel'] or '')[:60]}“ – "
                            + ("angenommen, aber noch nicht ausgeliefert; startet danach" if x["angenommen"] else "läuft noch"))
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


def pc_belegt(con, ohne=None):
    """A1925: {"grenze": plaetze_pc (0 = keine), "arbeiten": [(Projektname, Aufgabe) …]} – p-Arbeiter aller Projekte, die
    gerade arbeiten (ARBEITEND), ohne die Aufgabe `ohne`."""
    from . import einstellungen
    zeilen = con.execute("SELECT a.id, p.name FROM paket k JOIN aufgabe a ON a.id = k.aufgabe_id JOIN projekt p ON p.id = a.projekt_id"
                         f" WHERE k.art = 'p' AND k.zustand IN ({','.join('?' * len(ARBEITEND))}) ORDER BY a.id",
                         ARBEITEND).fetchall()
    return {"grenze": einstellungen.wert("plaetze_pc"), "arbeiten": [(r["name"], r["id"]) for r in zeilen if r["id"] != ohne]}


def reihenfolge(con, pid):
    """Startklare p-Pakete in Startfolge – dieselbe Reihenfolge, die die AMW anzeigt (A2041, D1531 §8: reihenfolge.berechnen:
    aktiver Meilenstein zuerst, dann der längste Rest-Pfad, dann Rang und Nummer); was die Berechnung nicht kennt, kommt danach
    nach Rang und Nummer. Pakete, deren Vorgänger („nach X“) noch nicht fertig/gemergt sind, fehlen. Die Regeln des Wächters
    gelten weiter (pruefen). [{"id", "titel", "rang", "platz"}]"""
    from . import delta_halt, reihenfolge as rf
    try:
        platz = {z["aid"]: z["platz"] for z in rf.berechnen(con, pid)}
    except Exception:                                    # noqa: BLE001 – ohne Berechnung startet der Disponent wie bisher
        platz = {}
    kandidaten = sorted(con.execute(
        "SELECT a.id, a.titel, a.rang FROM paket k JOIN aufgabe a ON a.id = k.aufgabe_id WHERE a.projekt_id = ? AND k.art = 'p'"
        " AND k.zustand = 'startklar'", (pid,)).fetchall(),
        key=lambda k: (platz.get(k["id"], 10 ** 9), k["rang"] if k["rang"] is not None else 999999, k["id"]))
    aus = []
    for k in kandidaten:
        offen = con.execute(
            "SELECT 1 FROM abhaengigkeit d JOIN aufgabe v ON v.id = d.vor LEFT JOIN paket pv ON pv.aufgabe_id = v.id"
            " WHERE d.nach = ? AND d.extern IS NULL AND NOT (v.status IN ('fertig', 'verworfen') OR coalesce(pv.zustand, '') IN ('gemergt', 'fertig'))",
            (k["id"],)).fetchone()
        if not offen and not delta_halt.haelt(con, k["id"]):      # A2140: wartet auf das Ja zu einer Konzeptänderung
            aus.append({"id": k["id"], "titel": k["titel"], "rang": k["rang"], "platz": platz.get(k["id"])})
    return aus


def p_laufend(con):
    """Wird auf diesem PC an p-Paketen gearbeitet (alle Projekte)? Angenommene (merge_reihe) zählen nie (A2105). Ohne Tabelle paket
    (ältere Datenbank): nein."""
    import sqlite3
    try:
        return con.execute(f"SELECT 1 FROM paket WHERE art = 'p' AND zustand IN ({','.join('?' * len(ARBEITEND))}) LIMIT 1",
                           ARBEITEND).fetchone() is not None
    except sqlite3.Error:
        return False


def vor_auslieferung(con, frist_s=1800, warte_s=15, schlafen=time.sleep):
    """Auslieferung der AMW: Wartungsmodus setzen und warten, bis an keinem p-Paket mehr gearbeitet wird (alle Projekte dieses PCs). Ein
    angenommenes Paket (merge_reihe) hält sie nie auf, ob es seinen Platz schon abgegeben hat oder nicht: frei wird es erst durch sie
    (1.194.0 wartete am 25.11. auf zwei solche und wäre nie fertig geworden; A2105).
    Rückgabe (fertig: bool, noch_laufend: [A-Nummern]). Ohne laufende p-Pakete sofort fertig."""
    ids = lambda: [r["aufgabe_id"] for r in con.execute(
        f"SELECT aufgabe_id FROM paket WHERE art = 'p' AND zustand IN ({','.join('?' * len(ARBEITEND))}) ORDER BY aufgabe_id", ARBEITEND).fetchall()]
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
