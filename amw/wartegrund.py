"""Wartegründe als Verweis und Wecken (→ doc/automatismen.md).

Eine Aufgabe, die wartet oder blockiert ist, nennt, worauf: F12, A120, L7, CC2, Entwickler oder Monitor:<was>. Jeder
Grund ist eine Zeile in `wartegrund`. Wird ein Grund erledigt (Frage beantwortet, Aufgabe fertig, Lauf zu Ende, Agent
meldet sich zur Aufgabe, der Entwickler antwortet), weckt die AMW den Besitzer der Aufgabe, Kopie an den Lead.
Die Leerlauf-Prüfung im Dienst weckt Agenten, die frei sind, obwohl eine ihrer Aufgaben auf nichts mehr wartet.
Alle Funktionen außer `setzen`/`leerlauf` laufen innerhalb eines offenen Schreibvorgangs des Aufrufers.
"""
import json
import re
import time

from . import db, kern

LEERLAUF_MIN = 30         # so lange frei, dann Weckruf, wenn Arbeit da ist (L3)
LEER_MIN = 10             # A1884: so lange frei OHNE Arbeit, dann ein Weckruf an den Lead (Projekt: leerlauf_lead_min)
LEER_FREI_ZEIGEN = 8      # so viele freie Aufgaben der aktiven Meilensteine nennt dieser Weckruf
ENTWICKLER_ZEILE_H = 6    # wartet alles auf den Entwickler: höchstens so oft eine Zeile an den Lead
ARBEIT_ZEIGEN = 3         # so viele freie Aufgaben nennt der Weckruf

ERLEDIGT_TEXT = {"frage": "beantwortet", "aufgabe": "abgeschlossen", "lauf": "zu Ende"}


def _sek(utc):
    return db.utc_sek(utc)


def bezug_lesen(con, pid, teil):
    """„F12“ → ("frage", "F12"); ebenso A…, L…, Agent-Kennung, Entwickler (oder sein eingestellter Name), Monitor[:was]."""
    t = teil.strip()
    m = re.fullmatch(r"([FfAaLl])\s*(\d+)", t)
    if m:
        art, tabelle = {"f": ("frage", "frage"), "a": ("aufgabe", "aufgabe"), "l": ("lauf", "lauf")}[m.group(1).lower()]
        if not con.execute(f"SELECT 1 FROM {tabelle} WHERE id = ? AND projekt_id = ?", (int(m.group(2)), pid)).fetchone():
            raise kern.AmwFehler(f"{m.group(1).upper()}{m.group(2)} gibt es nicht")
        return art, f"{m.group(1).upper()}{m.group(2)}"
    if t.lower() in (kern.ENTWICKLER.lower(), kern.entwickler_name(con, pid).lower()):
        return "entwickler", kern.ENTWICKLER
    m = re.fullmatch(r"(?i)monitor(?:\s*:\s*(.+))?", t)
    if m:
        return "monitor", "Monitor" + (f": {m.group(1).strip()}" if m.group(1) else "")
    try:
        return "agent", kern.agent_zeile(con, pid, t)["kennung"]
    except kern.AmwFehler:
        raise kern.AmwFehler(f"„{t}“ ist kein Wartegrund – erlaubt: F<nr>, A<nr>, L<nr>, Name eines Agenten, Entwickler, Monitor:<was>")


def teile(text):
    return [t for t in re.split(r"[,;]", text or "") if t.strip()]


def offene(con, aid):
    return con.execute("SELECT * FROM wartegrund WHERE aufgabe_id = ? AND erledigt_utc IS NULL ORDER BY id", (aid,)).fetchall()


def anlegen(con, pid, von, aid, auf):
    """Neue Gründe zu einer Aufgabe (doppelte offene werden nicht noch einmal angelegt). Gibt die Bezüge zurück."""
    neu = []
    schon = {r["bezug"] for r in offene(con, aid)}
    for t in teile(auf):
        art, bezug = bezug_lesen(con, pid, t)
        if art == "aufgabe" and bezug == f"A{aid}":
            raise kern.AmwFehler(f"A{aid} kann nicht auf sich selbst warten")
        if bezug in schon or bezug in neu:
            continue
        db.einfuegen(con, "wartegrund", projekt_id=pid, aufgabe_id=aid, art=art, bezug=bezug, angelegt_utc=db.jetzt(),
                     angelegt_von=von)
        neu.append(bezug)
    return neu


def schliessen(con, aid, durch):
    """Alle offenen Gründe einer Aufgabe still erledigen (sie läuft wieder, ist fertig oder verworfen)."""
    con.execute("UPDATE wartegrund SET erledigt_utc = ?, erledigt_durch = ? WHERE aufgabe_id = ? AND erledigt_utc IS NULL",
                (db.jetzt(), durch, aid))


def von_hand(con, pid, von, aid, auf):
    """--erledigt F12,CC2: Gründe von Hand abhaken (z. B. der Lead nach dem Wort des Entwicklers im Chat). Weckt wie automatisch."""
    a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    weg = []
    for t in teile(auf):
        art, bezug = bezug_lesen(con, pid, t)
        n = con.execute("UPDATE wartegrund SET erledigt_utc = ?, erledigt_durch = ? WHERE aufgabe_id = ? AND bezug = ?"
                        " AND erledigt_utc IS NULL", (db.jetzt(), f"von Hand: {von}", aid, bezug)).rowcount
        if not n:
            raise kern.AmwFehler(f"A{aid} wartet nicht (mehr) auf {bezug}")
        weg.append(bezug)
    if von != a["agent"]:
        _melden(con, pid, a, f"{', '.join(weg)} erledigt ({von})")
    return weg


def erledige(con, pid, art, bezug, durch, aufgabe_id=None):
    """Ein Ereignis erledigt alle offenen Gründe art/bezug (nur die einer Aufgabe, wenn aufgabe_id) und weckt je
    Aufgabe den Besitzer, Kopie an den Lead (L2). Gibt die betroffenen Aufgaben-Nummern zurück."""
    sql = "SELECT * FROM wartegrund WHERE projekt_id = ? AND art = ? AND bezug = ? AND erledigt_utc IS NULL"
    par = [pid, art, bezug]
    if aufgabe_id:
        sql += " AND aufgabe_id = ?"
        par.append(aufgabe_id)
    gruende = con.execute(sql, par).fetchall()
    if not gruende:
        return []
    t = db.jetzt()
    for g in gruende:
        con.execute("UPDATE wartegrund SET erledigt_utc = ?, erledigt_durch = ? WHERE id = ?", (t, durch, g["id"]))
    aids = sorted({g["aufgabe_id"] for g in gruende})
    for aid in aids:
        a = con.execute("SELECT * FROM aufgabe WHERE id = ?", (aid,)).fetchone()
        _melden(con, pid, a, durch)
    return aids


def _melden(con, pid, a, durch):
    if a["status"] not in ("wartet", "blockiert") or not a["agent"]:
        return
    rest = [r["bezug"] for r in offene(con, a["id"])]
    weiter = f"noch offen: {', '.join(rest)}" if rest else f"alle Gründe erledigt – weiter: amw aufgabe start {a['id']}"
    if not rest:                                       # Arbeitsliste: steht sie über der laufenden, zuerst diese
        from . import arbeitsliste
        p = arbeitsliste.position(con, pid, a["id"])
        unten = con.execute("SELECT id FROM aufgabe WHERE projekt_id = ? AND agent = ? AND status = 'laeuft' AND id != ?"
                            " AND (rang > ? OR (rang = ? AND id > ?)) LIMIT 1",
                            (pid, a["agent"], a["id"], a["rang"], a["rang"], a["id"])).fetchone()
        lauf = con.execute("SELECT id FROM aufgabe WHERE projekt_id = ? AND agent = ? AND status = 'laeuft' AND id != ? LIMIT 1",
                           (pid, a["agent"], a["id"])).fetchone()
        if lauf:                                       # eins nach dem anderen: erst das laufende Stück abschließen
            weiter = f"alle Gründe erledigt – als Nächstes dran, sobald A{lauf['id']} fertig ist"
        elif p and unten:
            weiter += f" (Pos {p[1]} deiner Liste)"
    an = [a["agent"]] + ([kern.lead(con, pid)] if kern.lead(con, pid) else [])
    an = [k for k in an if con.execute("SELECT 1 FROM agent WHERE projekt_id = ? AND kennung = ?", (pid, k)).fetchone()]
    if an:
        kern._posten(con, pid, "AMW", ",".join(dict.fromkeys(an)), "meldung", f"A{a['id']}: {durch} – {weiter}",
                     text=a["titel"], aufgabe_id=a["id"])


# --- Leerlauf (L3) -------------------------------------------------------------------------------

def freie_arbeit(con, pid, kennung):
    """Aufgaben, an denen der Agent arbeiten kann: läuft, oder wartet/blockiert ohne offenen Grund, ohne Freitext,
    ohne offenen Vorgänger, nicht geparkt."""
    from . import planung
    aus = []
    for a in con.execute("SELECT * FROM aufgabe WHERE projekt_id = ? AND agent = ? AND einstufung = 'aktiv'"
                         " AND status IN ('wartet', 'laeuft', 'blockiert') ORDER BY rang, id", (pid, kennung)):
        if a["status"] != "laeuft" and (offene(con, a["id"]) or (a["wartet_auf"] or "").strip()
                                       or planung.offene_vorgaenger(con, a["id"])):
            continue
        aus.append(a)
    return aus


def wartet_auf_entwickler(con, pid, kennung):
    """Offene Gründe der Aufgaben des Agenten, wenn sie alle auf den Entwickler warten (direkt oder Frage an ihn), sonst []."""
    gruende = con.execute(
        "SELECT w.art, w.bezug FROM wartegrund w JOIN aufgabe a ON a.id = w.aufgabe_id WHERE a.projekt_id = ?"
        " AND a.agent = ? AND a.einstufung = 'aktiv' AND a.status IN ('wartet', 'blockiert') AND w.erledigt_utc IS NULL",
        (pid, kennung)).fetchall()
    if not gruende:
        return []
    for g in gruende:
        if g["art"] == "entwickler":
            continue
        if g["art"] == "frage":
            f = con.execute("SELECT an FROM frage WHERE id = ?", (int(g["bezug"][1:]),)).fetchone()
            if f and f["an"] == "entwickler":
                continue
        return []
    return sorted({g["bezug"] for g in gruende})


def wartet_auf_eigenes(con, pid, kennung):
    """A1884: Wartet der Agent auf einen eigenen Lauf oder auf die Prüfung seines Stands? Dann ist er nicht leer.
    Rückgabe: „L12“ / „P34“ oder None."""
    lauf = con.execute("SELECT id FROM lauf WHERE projekt_id = ? AND agent = ? AND status IN ('angemeldet', 'laeuft')"
                       " ORDER BY id DESC LIMIT 1", (pid, kennung)).fetchone()
    if lauf:
        return f"L{lauf['id']}"
    p = con.execute("SELECT id FROM pruefung WHERE projekt_id = ? AND bauer = ? AND ergebnis = 'offen' ORDER BY id DESC LIMIT 1",
                    (pid, kennung)).fetchone()
    return f"P{p['id']}" if p else None


def _einst(con, pid, schluessel):
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    try:
        return json.loads((r[0] if r else None) or "{}").get(schluessel)
    except ValueError:
        return None


def leer_lead(con, pid):
    """A1884: Wer den Leerlauf-Weckruf bekommt – Projekt-Einstellung leerlauf_lead, sonst der Lead; nur ein Agent, der im
    Terminal arbeitet (einen Chat-Lead weckt die AMW nicht). None = in diesem Projekt kein Weckruf."""
    k = str(_einst(con, pid, "leerlauf_lead") or "").strip() or kern.lead(con, pid)
    if not k:
        return None
    r = con.execute("SELECT arbeitsweise FROM agent WHERE projekt_id = ? AND kennung = ? AND entfernt_utc IS NULL",
                    (pid, k)).fetchone()
    return k if r and r["arbeitsweise"] == "terminal" else None


def _verteil_offen(con, pid, kennung):
    """A1927 (P374): Gibt es zu diesem Agenten einen offenen Vorschlag des Verteilens? Dann keine zweite Meldung „nichts zu tun“."""
    from . import verteilen
    return bool(verteilen.offener_vorschlag(con, pid, kennung))


def freie_bogen_aufgaben(con, pid):
    """Offene Aufgaben der aktiven Meilensteine ohne Bearbeiter – ohne p-Pakete (die führt der Arbeiter der AMW aus, nie ein
    interaktiver Agent; A1892)."""
    return con.execute("SELECT a.id, a.titel, a.bogen_id FROM aufgabe a JOIN bogen b ON b.id = a.bogen_id"
                       " LEFT JOIN paket k ON k.aufgabe_id = a.id WHERE a.projekt_id = ?"
                       " AND b.status = 'aktiv' AND coalesce(a.agent, '') = '' AND a.status NOT IN ('fertig', 'verworfen')"
                       " AND a.einstufung = 'aktiv' AND coalesce(k.art, 'agent') != 'p'"
                       " ORDER BY coalesce(a.rang, 999999), a.id", (pid,)).fetchall()


def _leer_weckruf(con, pid, lead, leere):
    """A1884: ein Weckruf mit Inhalt an den Lead – je Agent höchstens einmal je Ruhephase (Signatur Agent + Beginn)."""
    neu = []
    for k, seit, frei_min in leere:
        signatur = f"{k}:{seit}"
        if con.execute("SELECT 1 FROM plan_ereignis WHERE projekt_id = ? AND art = 'leerlauf_weckruf' AND text = ?",
                       (pid, signatur)).fetchone():
            continue                                    # diese Ruhephase ist schon gemeldet – bis sich etwas ändert
        neu.append((k, seit, frei_min, signatur))
    if not neu:
        return None
    frei = freie_bogen_aufgaben(con, pid)
    namen = ", ".join(k for k, *_ in neu)
    kurz = f"Leerlauf: {namen} {'hat' if len(neu) == 1 else 'haben'} nichts zu tun"
    zeilen = [f"{k}: seit {seit[11:16]} UTC frei ({int(frei_min)} min), keine Aufgabe in „läuft“ oder ohne Wartegrund,"
              " wartet auf keinen eigenen Lauf und keine Prüfung." for k, seit, frei_min, _ in neu]
    if frei:
        zeilen.append("Freie Aufgaben in aktiven Meilensteinen (ohne Bearbeiter): "
                      + "; ".join(f"A{a['id']} {a['titel'][:70]} (M{a['bogen_id']})" for a in frei[:LEER_FREI_ZEIGEN])
                      + (f" … und {len(frei) - LEER_FREI_ZEIGEN} weitere" if len(frei) > LEER_FREI_ZEIGEN else ""))
    else:
        zeilen.append("In den aktiven Meilensteinen gibt es keine freie Aufgabe ohne Bearbeiter.")
    zeilen.append(f"Was fehlt: eine Aufgabe zuteilen (amw aufgabe aendern <nr> --agent {neu[0][0]}) oder neue schneiden.")
    with db.schreiben(con):
        for *_, signatur in neu:
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art="leerlauf_weckruf", text=signatur)
        kern._posten(con, pid, "AMW", lead, "meldung", kurz[:140], "\n".join(zeilen))
    return f"Lead {lead}: {kurz}"


def leerlauf(con, jetzt=None):
    """Dienst-Runde: freie Sitzungen mit Arbeit wecken, „alles wartet auf den Entwickler“ höchstens alle 6 h an den Lead."""
    jetzt = jetzt or time.time()
    ereignisse = []
    for p in con.execute("SELECT id FROM projekt").fetchall():
        pid = p["id"]
        entwickler, leere = [], []
        leer_an = leer_lead(con, pid)                   # A1884: nur mit einem Lead im Terminal
        try:
            leer_min = int(_einst(con, pid, "leerlauf_lead_min") or LEER_MIN)
        except (TypeError, ValueError):
            leer_min = LEER_MIN
        for s in con.execute(
                "SELECT s.id, s.ereignis_utc, a.kennung, a.arbeitsweise FROM sitzung s JOIN agent a ON a.id = s.agent_id"
                " WHERE a.projekt_id = ? AND a.soll = 'an' AND s.zustand = 'aktiv' AND s.schluessel_datei IS NOT NULL"
                " AND s.ereignis = 'frei' AND s.ereignis_utc IS NOT NULL", (pid,)).fetchall():
            k = s["kennung"]
            frei_min = (jetzt - _sek(s["ereignis_utc"])) / 60
            if frei_min < min(LEERLAUF_MIN, leer_min) or kern.halt_gilt(con, pid, k):
                continue
            if con.execute("SELECT 1 FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id WHERE n.projekt_id = ?"
                           " AND e.agent = ? AND e.status = 'offen' LIMIT 1", (pid, k)).fetchone():
                continue                                # ungelesene Post: dafür gibt es Wecken und Stillstand
            arbeit = freie_arbeit(con, pid, k)
            if arbeit:
                if frei_min < LEERLAUF_MIN:
                    continue
                if con.execute("SELECT 1 FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE n.projekt_id = ?"
                               " AND n.von = 'AMW' AND e.agent = ? AND n.kurz LIKE 'Leerlauf:%' AND n.zeit_utc >= ?",
                               (pid, k, s["ereignis_utc"])).fetchone():
                    continue                            # in dieser Ruhephase schon geweckt
                liste = "; ".join(f"A{a['id']} [{a['status']}] {a['titel'][:70]}" for a in arbeit[:ARBEIT_ZEIGEN])
                with db.schreiben(con):
                    kern._posten(con, pid, "AMW", k, "meldung",
                                 f"Leerlauf: seit {int(frei_min)} min frei, Arbeit liegt vor – {liste}",
                                 text="Weiter mit der ersten – oder, wenn sie wirklich wartet: "
                                      f"amw aufgabe wartet {arbeit[0]['id']} --auf F…/A…/L…/Agent/Entwickler/Monitor:…",
                                 aufgabe_id=arbeit[0]["id"])
                ereignisse.append(f"{k} benachrichtigt (Leerlauf, A{arbeit[0]['id']})")
            else:
                worauf = wartet_auf_entwickler(con, pid, k)
                if worauf:
                    if frei_min >= LEERLAUF_MIN:
                        entwickler.append(f"{k} ({', '.join(worauf)})")
                elif (leer_an and k != leer_an and s["arbeitsweise"] == "terminal" and frei_min >= leer_min
                      and not wartet_auf_eigenes(con, pid, k) and not _verteil_offen(con, pid, k)):
                    leere.append((k, s["ereignis_utc"], frei_min))   # A1884: nichts zu tun → Lead wecken
        if leere:
            e = _leer_weckruf(con, pid, leer_an, leere)
            if e:
                ereignisse.append(e)
        lead = kern.lead(con, pid)
        if entwickler and lead:
            grenze = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(jetzt - ENTWICKLER_ZEILE_H * 3600))
            if not con.execute("SELECT 1 FROM nachricht WHERE projekt_id = ? AND von = 'AMW' AND kurz LIKE 'Leerlauf: warten auf %'"
                               " AND zeit_utc >= ?", (pid, grenze)).fetchone():
                with db.schreiben(con):
                    kern._posten(con, pid, "AMW", lead, "info",
                                 f"Leerlauf: warten auf {kern.entwickler_name(con, pid)} – " + "; ".join(entwickler))
                ereignisse.append("Lead: alles wartet auf den Entwickler")
    return ereignisse
