"""Wartegründe als Verweis und Wecken (→ doc/automatismen.md).

Eine Aufgabe, die wartet oder blockiert ist, nennt, worauf: F12, A120, L7, CC2, Entwickler oder Monitor:<was>. Jeder
Grund ist eine Zeile in `wartegrund`. Wird ein Grund erledigt (Frage beantwortet, Aufgabe fertig, Lauf zu Ende, Agent
meldet sich zur Aufgabe, der Entwickler antwortet), weckt die AMW den Besitzer der Aufgabe, Kopie an den Lead.
Die Leerlauf-Prüfung im Dienst weckt Agenten, die frei sind, obwohl eine ihrer Aufgaben auf nichts mehr wartet.
Alle Funktionen außer `setzen`/`leerlauf` laufen innerhalb eines offenen Schreibvorgangs des Aufrufers.

Feste Art (A2053, TH155): jeder Grund hat eine Sorte – wartet_pruefung · wartet_stapel · wartet_lauf · wartet_antwort ·
wartet_paket. Ohne Schemaänderung (Lead F5388): Prüfung und Stapel stehen als maschinenlesbares Stichwort im Bezug
(Art „monitor“, Bezug „pruefung:P604“ / „stapel:stapel41“; mit --art auch „pruefung:CCamwTL“); L… ist wartet_lauf, A… wartet_paket,
alles andere wartet_antwort (sicher: hält fest). Nur stichwort()/sorte() kennen diese Speicherung – eine spätere Migration
tauscht nur sie. Prüfung, Stapel und Lauf geben den Agenten frei (die AMW verteilt weiter, verteilen.freie_agenten); Antwort
und Paket erst nach HALTEN_MIN.
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
SORTEN = ("wartet_pruefung", "wartet_stapel", "wartet_lauf", "wartet_antwort", "wartet_paket")
FREIGEBEND = ("wartet_pruefung", "wartet_stapel", "wartet_lauf")   # der Agent ist frei für anderes, sofort
HALTEN_MIN = 10           # wartet_antwort/wartet_paket halten den Agenten so lange fest, dann ist er frei für anderes
STICHWORT = ("pruefung", "stapel", "lauf", "antwort", "paket")


def stichwort(sorte, ref):
    """(art, bezug) für eine Sorte mit Verweis – die einzige Stelle, die die Speicherung als Stichwort kennt."""
    kurz = sorte.removeprefix("wartet_")
    return "monitor", f"{kurz}:{ref}"


def sorte(art, bezug, text=None):
    """Sorte eines Grundes aus (art, bezug); ohne Grund aus dem Freitext (grob, unbekannt = wartet_antwort)."""
    if art is None:
        return _sorte_text(text)
    m = re.match(r"(pruefung|stapel|lauf|antwort|paket):", bezug or "")
    if art == "monitor" and m:
        return "wartet_" + m.group(1)
    return {"lauf": "wartet_lauf", "aufgabe": "wartet_paket"}.get(art, "wartet_antwort")


def _sorte_text(text):
    t = (text or "").lower()
    if re.search(r"prüf|pruef|\bp\d+", t):
        return "wartet_pruefung"
    if re.search(r"stapel|release|auslieferung|kette", t):
        return "wartet_stapel"
    if re.search(r"\bl\d+|gesamtlauf", t):
        return "wartet_lauf"
    return "wartet_antwort"


def _sek(utc):
    return db.utc_sek(utc)


def bezug_lesen(con, pid, teil, art=None):
    """„F12“ → ("frage", "F12"); ebenso A…, L…, Agent-Kennung, Entwickler (oder sein eingestellter Name), Monitor[:was];
    A2053: P604 / pruefung:P604 → Prüfung, stapel:<zweig> → Stapel. art (--art: pruefung|stapel|lauf|antwort|paket) setzt die
    Sorte, wenn der Verweis sie nicht schon hat (z. B. --auf CCamwTL --art pruefung)."""
    t = teil.strip()
    m = re.fullmatch(r"(?i)(pruefung|stapel|lauf|antwort|paket)\s*:\s*(.+)", t)
    if m and not art:
        return bezug_lesen(con, pid, m.group(2), m.group(1).lower())
    if art:
        art = art.lower().removeprefix("wartet_")
        if art not in STICHWORT:
            raise kern.AmwFehler(f"Art „{art}“ – erlaubt: {', '.join(STICHWORT)}")
    m = re.fullmatch(r"[Pp]\s*(\d+)", t)
    if m:
        if not con.execute("SELECT 1 FROM pruefung WHERE id = ? AND projekt_id = ?", (int(m.group(1)), pid)).fetchone():
            raise kern.AmwFehler(f"P{m.group(1)} gibt es nicht")
        return stichwort("wartet_" + (art or "pruefung"), f"P{m.group(1)}")
    if art == "stapel":
        if not re.fullmatch(r"[\w./-]{1,80}", t):
            raise kern.AmwFehler(f"stapel:<zweig> – „{t}“ ist kein Zweig")
        return stichwort("wartet_stapel", t)
    a, b = _bezug_alt(con, pid, t)
    if art and sorte(a, b) != "wartet_" + art:
        return stichwort("wartet_" + art, b)
    return a, b


def _bezug_alt(con, pid, t):
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
        raise kern.AmwFehler(f"„{t}“ ist kein Wartegrund – erlaubt: F<nr>, A<nr>, L<nr>, P<nr>, stapel:<zweig>, Name eines Agenten,"
                             " Entwickler, Monitor:<was>")


def teile(text):
    return [t for t in re.split(r"[,;]", text or "") if t.strip()]


def offene(con, aid):
    return con.execute("SELECT * FROM wartegrund WHERE aufgabe_id = ? AND erledigt_utc IS NULL ORDER BY id", (aid,)).fetchall()


def anlegen(con, pid, von, aid, auf, art=None):
    """Neue Gründe zu einer Aufgabe (doppelte offene werden nicht noch einmal angelegt). Gibt die Bezüge zurück."""
    neu = []
    schon = {r["bezug"] for r in offene(con, aid)}
    for t in teile(auf):
        art_db, bezug = bezug_lesen(con, pid, t, art)
        if art_db == "aufgabe" and bezug == f"A{aid}":
            raise kern.AmwFehler(f"A{aid} kann nicht auf sich selbst warten")
        if bezug in schon or bezug in neu:
            continue
        if art_db == "lauf" and lauf_tot(con, pid, bezug):      # A2074: ein abgebrochener Lauf endet nicht mehr
            raise kern.AmwFehler(f"{bezug} ist abgebrochen – nenne den Ersatz (--auf L<neu>)")
        db.einfuegen(con, "wartegrund", projekt_id=pid, aufgabe_id=aid, art=art_db, bezug=bezug, angelegt_utc=db.jetzt(),
                     angelegt_von=von)
        neu.append(bezug)
        if art_db == "lauf":                                    # A2074: der Ersatz löst den abgebrochenen Lauf ab
            for g in offene(con, aid):
                if g["art"] == "lauf" and lauf_tot(con, pid, g["bezug"]):
                    con.execute("UPDATE wartegrund SET erledigt_utc = ?, erledigt_durch = ? WHERE id = ?",
                                (db.jetzt(), f"ersetzt durch {bezug}", g["id"]))
    return neu


# --- Abgebrochene Läufe (A2074) ------------------------------------------------------------------

UNBEKANNT = "lauf_unbekannt"     # plan_ereignis {"lauf": n}: zu Ende, aber der Rückgabewert ging verloren


def lauf_tot(con, pid, bezug):
    """Ist das ein Lauf ohne Ergebnis (abgebrochen oder Rückgabewert verloren)? Auf den wartet niemand mit Erfolg."""
    m = re.fullmatch(r"L(\d+)", bezug or "")
    if not m:
        return False
    r = con.execute("SELECT status FROM lauf WHERE id = ? AND projekt_id = ?", (int(m.group(1)), pid)).fetchone()
    return bool(r) and (r[0] == "abgebrochen" or con.execute("SELECT 1 FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND text = ?",
                                                             (pid, UNBEKANNT, json.dumps({"lauf": int(m.group(1))}))).fetchone() is not None)


def anzeige(con, pid, g):
    return g["bezug"] + (" (abgebrochen)" if g["art"] == "lauf" and lauf_tot(con, pid, g["bezug"]) else "")


def wartet_auf_lauf(con, pid, lid):
    """Aufgaben, die noch offen auf diesen Lauf warten."""
    return con.execute("SELECT DISTINCT a.* FROM wartegrund w JOIN aufgabe a ON a.id = w.aufgabe_id WHERE w.projekt_id = ? AND w.art = 'lauf'"
                       " AND w.bezug = ? AND w.erledigt_utc IS NULL AND a.status IN ('wartet', 'blockiert') ORDER BY a.id",
                       (pid, f"L{lid}")).fetchall()


def warteliste(lid, warten):
    return ("\nEs warten: " + ", ".join(f"A{a['id']} ({a['agent'] or '–'})" for a in warten)
            + f" – der Grund bleibt offen. Ersatz nennen: amw aufgabe wartet <nr> --auf L<neu> · aufheben: --erledigt L{lid}")


def lauf_abgebrochen(con, pid, lid, agent, ergebnis=None, melden=True):
    """Ein Lauf endete ohne Ergebnis: die Gründe bleiben offen, bis ein Ersatz genannt oder der Grund aufgehoben wird. Eine
    Nachricht je Empfänger (Besitzer des Laufs, Besitzer der wartenden Aufgaben, Lead) mit der Liste – nur wenn jemand wartet."""
    if con.execute("SELECT status FROM lauf WHERE id = ?", (lid,)).fetchone()[0] != "abgebrochen":
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=UNBEKANNT, text=json.dumps({"lauf": lid}))
    warten = wartet_auf_lauf(con, pid, lid)
    if not melden or not warten:
        return warten
    an = dict.fromkeys([agent] + [a["agent"] for a in warten] + [kern.lead(con, pid)])
    an = [k for k in an if k and con.execute("SELECT 1 FROM agent WHERE projekt_id = ? AND kennung = ? AND entfernt_utc IS NULL", (pid, k)).fetchone()]
    if an:
        kern._posten(con, pid, "AMW", ",".join(an), "meldung",
                     f"L{lid} abgebrochen – {', '.join('A' + str(a['id']) for a in warten)}: Grund bleibt offen"[:140],
                     (ergebnis or "") + warteliste(lid, warten))
    return warten


def lauf_ersetzen(con, pid, alt, neu):
    """Die AMW hat einen Ersatz: offene Gründe auf L<alt> gelten jetzt für L<neu>, still."""
    for a in wartet_auf_lauf(con, pid, alt):
        if f"L{neu}" in {g["bezug"] for g in offene(con, a["id"])}:
            con.execute("UPDATE wartegrund SET erledigt_utc = ?, erledigt_durch = ? WHERE aufgabe_id = ? AND bezug = ? AND erledigt_utc IS NULL",
                        (db.jetzt(), f"ersetzt durch L{neu}", a["id"], f"L{alt}"))
        else:
            anlegen(con, pid, "AMW", a["id"], f"L{neu}")


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
    from . import paket_schieben                          # A2094: dieselbe Auswahl, Handgriffe „früher/später“ gelten auch hier
    return paket_schieben.nachziehen(con, pid, aus)


def haelt_fest(con, pid, kennung, jetzt=None):
    """A2053: Hält eine wartende Aufgabe den Agenten fest? Prüfung, Stapel und Lauf nie (FREIGEBEND); Antwort und Paket nur in
    den ersten HALTEN_MIN Minuten (danach darf die AMW ihm anderes startklares geben). Rückgabe: der festhaltende Bezug oder None."""
    jetzt = jetzt or time.time()
    for a in con.execute("SELECT id, wartet_auf, geaendert_utc FROM aufgabe WHERE projekt_id = ? AND agent = ? AND einstufung = 'aktiv'"
                         " AND status IN ('wartet', 'blockiert')", (pid, kennung)).fetchall():
        gruende = offene(con, a["id"])
        if not gruende and (a["wartet_auf"] or "").strip():
            gruende = [{"art": None, "bezug": a["wartet_auf"], "angelegt_utc": a["geaendert_utc"]}]
        for g in gruende:
            if sorte(g["art"], g["bezug"], g["bezug"]) in FREIGEBEND:
                continue
            if g["angelegt_utc"] and (jetzt - _sek(g["angelegt_utc"])) / 60 < HALTEN_MIN:
                return g["bezug"]
    return None


def startklar_wecken(con, pid):
    """A2053 (4): Aufgabe mit Besitzer, „wartet“/„blockiert“ ohne offenen Grund und ohne Freitext, alle Vorgänger fertig, Besitzer
    ohne laufendes Stück → einmal ein Weckruf „A… ist startklar“ (je Aufgabe und Änderungsstand; nicht, wenn die AMW zu dieser
    Aufgabe seitdem schon geschrieben hat, z. B. „alle Gründe erledigt“). Rückgabe: Texte."""
    from . import herausnehmen, planung
    aus = []
    for a in con.execute("SELECT a.* FROM aufgabe a JOIN agent g ON g.projekt_id = a.projekt_id AND g.kennung = a.agent"
                         " LEFT JOIN paket k ON k.aufgabe_id = a.id WHERE a.projekt_id = ? AND a.status IN ('wartet', 'blockiert')"
                         " AND a.einstufung = 'aktiv' AND g.entfernt_utc IS NULL AND coalesce(k.art, 'agent') != 'p'", (pid,)).fetchall():
        if offene(con, a["id"]) or (a["wartet_auf"] or "").strip() or planung.offene_vorgaenger(con, a["id"]):
            continue
        if con.execute("SELECT 1 FROM aufgabe WHERE projekt_id = ? AND agent = ? AND status = 'laeuft'", (pid, a["agent"])).fetchone():
            continue                                    # eins nach dem anderen: er kommt dazu, wenn das laufende fertig ist
        if herausnehmen.darf_starten(con, pid, a["agent"], a["id"]):
            continue                                    # A2095: herausgenommen
        zeichen = f"{a['id']}:{a['geaendert_utc']}"
        if con.execute("SELECT 1 FROM plan_ereignis WHERE projekt_id = ? AND art = 'startklar_geweckt' AND text = ?", (pid, zeichen)).fetchone():
            continue
        if con.execute("SELECT 1 FROM nachricht WHERE projekt_id = ? AND von = 'AMW' AND aufgabe_id = ? AND zeit_utc >= ?",
                       (pid, a["id"], a["geaendert_utc"] or "")).fetchone():
            continue                                    # schon geweckt (alle Gründe erledigt, zugeteilt …)
        with db.schreiben(con):
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art="startklar_geweckt",
                         aufgabe_id=a["id"], text=zeichen)
            kern._posten(con, pid, "AMW", a["agent"], "auftrag", f"A{a['id']} ist startklar – weiter: amw aufgabe start {a['id']}",
                         f"„{a['titel'][:100]}“ wartet auf nichts mehr: kein offener Grund, alle Vorgänger fertig.",
                         aufgabe_id=a["id"])
        aus.append(f"{a['agent']} geweckt: A{a['id']} startklar")
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


def _bekommt_paket(con, pid, kennung):
    """A2053 (3): Mit „Verteilen an“ und einem startklaren Paket, das passt, teilt die AMW selbst zu – dann keine Meldung an den
    Lead. Die Meldung „nichts zu tun“ bleibt für den Fall ohne startklares (oder ohne passendes) Paket."""
    from . import verteilen
    if verteilen.einstellung(con, pid) != "an":
        return False
    return any(verteilen.passt(con, pid, kennung, a)[0] == "ja" for a, _ in verteilen.kandidaten(con, pid))


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
    from . import meilensteine
    frei = freie_bogen_aufgaben(con, pid)
    namen = ", ".join(k for k, *_ in neu)
    kurz = f"Leerlauf: {namen} {'hat' if len(neu) == 1 else 'haben'} nichts zu tun"
    zeilen = [f"{k}: seit {seit[11:16]} UTC frei ({int(frei_min)} min), keine Aufgabe in „läuft“ oder ohne Wartegrund,"
              " wartet auf keinen eigenen Lauf und keine Prüfung." for k, seit, frei_min, _ in neu]
    if frei:
        zeilen.append("Freie Aufgaben in aktiven Meilensteinen (ohne Bearbeiter): "
                      + "; ".join(f"A{a['id']} {a['titel'][:70]} ({meilensteine.name(con, a['bogen_id'])})" for a in frei[:LEER_FREI_ZEIGEN])
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
    from . import herausnehmen
    jetzt = jetzt or time.time()
    ereignisse = []
    for p in con.execute("SELECT id FROM projekt").fetchall():
        pid = p["id"]
        ereignisse += startklar_wecken(con, pid)        # A2053 (4)
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
            if frei_min < min(LEERLAUF_MIN, leer_min) or kern.halt_gilt(con, pid, k) or herausnehmen.ist(con, pid, k):
                continue                                # A2095: ein Herausgenommener ist nicht „ohne Arbeit“
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
                      and not wartet_auf_eigenes(con, pid, k) and not _verteil_offen(con, pid, k)
                      and not _bekommt_paket(con, pid, k)):
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
