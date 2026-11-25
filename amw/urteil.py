"""K3 (A1939; TH155 Punkte 1, 4, 5): Meilenstein automatisch – „bereit zur Abnahme“ bei einem Urteil, Themen statt Spezifikation,
Ziel und Abnahme als Verweis.

Bereit zur Abnahme: Eine Aufgabe mit der Fertig-Quelle „ja“ (K2) schließt die AMW nie selbst – sie hängt an einem Urteil. Sobald
ein Fakt zeigt, dass das Ergebnis steht, meldet die AMW sie unter „Für dich“:
- der Bearbeiter meldet es (`amw aufgabe bereit N`), oder
- eine grüne Prüfung der Aufgabe, oder
- ein Ergebnis oder Bericht zur Aufgabe (amw dokument ablegen … --aufgabe N),
jeweils seit Beginn der Aufgabe und nach dem letzten „Zurück“.
Ein Ja genügt (der Mensch, oder der Lead – nie der Bearbeiter selbst): die AMW hakt die offenen Kriterien ohne Prüfquelle mit
„Ja von …“ ab, setzt fertig und schreibt Beleg und Zusammenfassung. „Zurück“ braucht einen Grund und geht an den Bearbeiter.

Verweise: Ziel und Abnahme eines Meilensteins dürfen TH<n> und D<n> nennen; die AMW zeigt dazu Titel und geltende Fassung.
Themen des Meilensteins: die Themen seiner Aufgaben (A1915) mit Status.
Ohne Schemaänderung: Ereignisse zur_abnahme, abnahme_ja, abnahme_zurueck.
"""
import json
import re

from . import db, kern

BEREIT, JA, ZURUECK = "zur_abnahme", "abnahme_ja", "abnahme_zurueck"
AUTO = "AMW"
VERWEIS = re.compile(r"\b(TH|D)(\d+)\b")


def _aufgabe(con, pid, aid):
    a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    if not a:
        raise kern.AmwFehler(f"A{aid} gibt es nicht")
    return a


def _urteil(con, a):
    from . import fertigquelle
    q = fertigquelle.lesen(con, a["id"])
    return bool(q) and q["art"] == "ja"


def _letztes(con, aid, art):
    r = con.execute("SELECT zeit_utc, von, text FROM plan_ereignis WHERE aufgabe_id = ? AND art = ? ORDER BY id DESC LIMIT 1",
                    (aid, art)).fetchone()
    return r


def fakt(con, a):
    """Der Fakt, der die Aufgabe bereit macht: (art, ref) mit art gemeldet | pruefung | dokument, oder None. Zählt seit Beginn
    der Aufgabe und nach dem letzten „Zurück“."""
    z = _letztes(con, a["id"], ZURUECK)
    start = a["begonnen_utc"] or a["angelegt_utc"]
    seit = max(start, z["zeit_utc"] if z else "")
    nach = ">" if z and z["zeit_utc"] >= start else ">="              # ab Beginn; nach einem „Zurück“ erst danach
    r = _letztes(con, a["id"], BEREIT)
    if r and r["zeit_utc"] >= seit and not (z and r["zeit_utc"] == z["zeit_utc"]):
        return ("gemeldet", r["von"])
    p = con.execute("SELECT id FROM pruefung WHERE aufgabe_id = ? AND ergebnis = 'gruen' AND COALESCE(ergebnis_utc, angefragt_utc) " + nach + " ?"
                    " ORDER BY id DESC LIMIT 1", (a["id"], seit)).fetchone()
    if p:
        return ("pruefung", f"P{p['id']}")
    d = con.execute("SELECT id FROM dokument WHERE projekt_id = ? AND bezug_art = 'aufgabe' AND bezug_id = ? AND art IN ('ergebnis', 'bericht')"
                    " AND status = 'aktuell' AND angelegt_utc " + nach + " ? ORDER BY id DESC LIMIT 1", (a["projekt_id"], a["id"], seit)).fetchone()
    if d:
        return ("dokument", f"D{d['id']}")
    return None


GRUND = {"gemeldet": "gemeldet von {r}", "pruefung": "{r} grün", "dokument": "{r} abgelegt"}


def grund(con, a):
    """Der Fakt als Text (für Beleg und Befehlszeile) oder None."""
    f = fakt(con, a)
    return GRUND[f[0]].format(r=f[1]) if f else None


def offene_urteile(a):
    from . import planung
    return [k["text"] for k in planung._json(a["kriterien"], []) if not k.get("erfuellt") and not k.get("quelle")]


def zur_abnahme(con, pid):
    """Für „Für dich“: offene Aufgaben mit Fertig-Quelle „ja“, deren Ergebnis steht. [{id, titel, agent, grund, offen, pruefpunkt, davor}] –
    davor (A2134): Titel des Pakets, hinter dem ein Prüfpunkt steht."""
    from . import zwischenpruefung
    aus, nach = [], {p["paket"]: p["nach"] for p in zwischenpruefung.offene(con, pid)}
    for a in con.execute("SELECT * FROM aufgabe WHERE projekt_id = ? AND status NOT IN ('fertig', 'verworfen') AND id IN"
                         " (SELECT aufgabe_id FROM plan_ereignis WHERE projekt_id = ? AND art = 'fertig_quelle') ORDER BY rang, id",
                         (pid, pid)).fetchall():
        if not _urteil(con, a):
            continue
        f = fakt(con, a)
        if f:
            v = con.execute("SELECT titel FROM aufgabe WHERE id = ?", (nach.get(a["id"]),)).fetchone()
            aus.append({"id": a["id"], "titel": a["titel"], "agent": a["agent"], "grund": GRUND[f[0]].format(r=f[1]), "davor": v[0] if v else None,
                        "grund_art": f[0], "grund_ref": f[1], "offen": offene_urteile(a), "pruefpunkt": zwischenpruefung.ist(con, a["id"])})
    return aus


def bereit_melden(con, pid, von, aid):
    """`amw aufgabe bereit N` – der Bearbeiter meldet: das Ergebnis steht. Nur bei Fertig-Quelle „ja“."""
    a = _aufgabe(con, pid, aid)
    if von != a["agent"] and not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler(f"A{aid}: bereit meldet der Bearbeiter ({a['agent'] or '–'})")
    if a["status"] in ("fertig", "verworfen"):
        raise kern.AmwFehler(f"A{aid} ist schon {a['status']}")
    if not _urteil(con, a):
        raise kern.AmwFehler(f"A{aid} schließt die AMW selbst (Fertig-Quelle) – „bereit“ gibt es nur bei --fertig-wenn ja")
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=BEREIT, aufgabe_id=aid, text="")
        lead = kern.lead(con, pid)
        if lead and lead not in (von, kern.ENTWICKLER):
            kern._posten(con, pid, AUTO, lead, "info", f"A{aid} bereit zur Abnahme: {a['titel'][:100]}",
                         "Steht unter „Für dich“. Ein Ja genügt (der Mensch oder du: amw aufgabe abnehmen "
                         f"{aid}), den Status setzt die AMW.", aufgabe_id=aid)


def entscheiden(con, pid, von, aid, ja=True, grund_text=None):
    """Ja oder Zurück zu einer Aufgabe, die bereit zur Abnahme ist – der Mensch oder der Lead, nie der Bearbeiter selbst."""
    from . import planung
    a = _aufgabe(con, pid, aid)
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Abnehmen kann der Mensch oder der Lead")
    from . import zwischenpruefung
    pruefpunkt = zwischenpruefung.ist(con, aid)
    if pruefpunkt and von != kern.ENTWICKLER:            # A2096: der Prüfpunkt gehört dem Menschen
        raise kern.AmwFehler(f"A{aid} ist ein Prüfpunkt und wartet auf {kern.entwickler_name(con, pid)}")
    if von == a["agent"]:
        raise kern.AmwFehler(f"A{aid}: der Bearbeiter nimmt seine eigene Aufgabe nicht ab")
    if a["status"] in ("fertig", "verworfen"):
        raise kern.AmwFehler(f"A{aid} ist schon {a['status']}")
    g = grund(con, a) if _urteil(con, a) else None
    if not g:
        raise kern.AmwFehler(f"A{aid} ist nicht bereit zur Abnahme")
    wer = "dem Menschen" if von == kern.ENTWICKLER else von
    if not ja:
        if not (grund_text or "").strip():
            raise kern.AmwFehler("Zurück nur mit Grund")
        with db.schreiben(con):
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=ZURUECK, aufgabe_id=aid,
                         text=grund_text.strip()[:500])
            if a["agent"] and a["agent"] != kern.ENTWICKLER:
                kern._posten(con, pid, AUTO, a["agent"], "korrektur", f"A{aid} nicht abgenommen – zurück von {wer}",
                             grund_text.strip(), aufgabe_id=aid)
            lead = kern.lead(con, pid)
            if pruefpunkt and lead and lead != a["agent"]:      # A2096: die Nacharbeit schneidet der Lead
                kern._posten(con, pid, AUTO, lead, "auftrag", f"Prüfpunkt A{aid}: zurück von {kern.entwickler_name(con, pid)} – Nacharbeit schneiden"[:140],
                             f"{(grund_text or '').strip()}\n\nDie Pakete dahinter warten weiter. Nacharbeit als Vorgänger von A{aid} anlegen (amw aufgabe neu …,"
                             f" dann die Abhängigkeit setzen); danach packt der Packer neu.", aufgabe_id=aid)
        return "zurueck"
    liste = planung._json(a["kriterien"], [])
    for k in liste:
        if not k.get("erfuellt") and not k.get("quelle"):
            k["erfuellt"], k["beleg"] = True, f"Ja von {von}"
    erfuellt = sum(1 for k in liste if k.get("erfuellt"))
    with db.schreiben(con):
        con.execute("UPDATE aufgabe SET kriterien = ?, geaendert_utc = ? WHERE id = ?", (json.dumps(liste, ensure_ascii=False), db.jetzt(), aid))
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=JA, aufgabe_id=aid, text=g)
    zusammen = (f"Abgenommen von {wer} ({g})." + (f" Kriterien {erfuellt}/{len(liste)}." if liste else "")
                + " Den Status hat die AMW gesetzt.")
    kern.aufgabe_status(con, pid, AUTO, aid, "fertig", beleg=f"Ja von {von} · {g}", zusammenfassung=zusammen, automatik="pruefpunkt")
    if a["agent"] and a["agent"] not in (kern.ENTWICKLER, von):
        with db.schreiben(con):
            kern._posten(con, pid, AUTO, a["agent"], "info", f"A{aid} abgenommen – fertig", zusammen, aufgabe_id=aid)
    return "fertig"


# --- Verweise und Themen des Meilensteins ------------------------------------------------------------------------------------

def verweise(con, pid, text):
    """TH<n> und D<n> im Text → [{ref, titel, stand}] mit geltender Fassung; unbekannte Nummern mit stand „gibt es nicht“."""
    from . import themen
    aus, gesehen = [], set()
    for art, n in VERWEIS.findall(text or ""):
        ref = f"{art}{n}"
        if ref in gesehen:
            continue
        gesehen.add(ref)
        if art == "TH":
            try:
                t = themen.finden(con, pid, int(n))
            except kern.AmwFehler:
                aus.append({"ref": ref, "titel": None, "stand": "fehlt"})
                continue
            s = themen.status(con, t)
            aus.append({"ref": ref, "titel": t["name"], "stand": s["status"], "fassung": s.get("freigegeben") or s.get("fassung")})
        else:
            d = con.execute("SELECT d.titel, (SELECT max(nr) FROM dokument_version v WHERE v.dokument_id = d.id) AS nr, d.status"
                            " FROM dokument d WHERE d.id = ? AND d.projekt_id = ?", (int(n), pid)).fetchone()
            aus.append({"ref": ref, "titel": d["titel"] if d else None, "stand": (d["status"] if d else "fehlt"),
                        "fassung": d["nr"] if d else None})
    return aus


def verweis_text(v):
    if not v["titel"]:
        return f"{v['ref']} gibt es nicht"
    if v["ref"].startswith("TH"):
        from . import themen
        return f"{v['ref']} {v['titel']} · " + ({"frei": f"freigegeben (Fassung {v['fassung']})"}.get(v["stand"])
                                                 or themen.STATUS_TEXT.get(v["stand"], v["stand"]))
    return f"{v['ref']} {v['titel']} · Fassung {v['fassung']}" + ("" if v["stand"] == "aktuell" else f" ({v['stand']})")


def bogen_themen(con, pid, bid):
    """Themen der Aufgaben des Meilensteins (A1915) mit Status: [{id, name, status, aufgaben}]."""
    from . import themen
    je = {}
    for (aid,) in con.execute("SELECT id FROM aufgabe WHERE bogen_id = ? AND status != 'verworfen' ORDER BY id", (bid,)).fetchall():
        for tid in themen.verweise(con, pid, aid):
            je.setdefault(tid, []).append(aid)
    aus = []
    for tid, aids in sorted(je.items()):
        try:
            t = themen.finden(con, pid, tid)
        except kern.AmwFehler:
            continue
        aus.append({"id": tid, "name": t["name"], "status": themen.status(con, t)["status"], "aufgaben": aids})
    return aus
