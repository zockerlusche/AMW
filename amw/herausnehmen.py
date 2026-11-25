"""A2101: Was passiert, wenn ein Agent herausgenommen wird – die Sicht darauf (folgen, nur lesen). Darunter A2095: herausnehmen und
wieder freigeben.

- laufend     – sein laufendes Stück (arbeitsliste.laufend): läuft zu Ende oder kommt mit Übergabe-Notiz zurück in den Pool.
- wartend     – was in den Pool geht: seine Liste in ihrer Reihenfolge (arbeitsliste.liste), dahinter, was für ihn noch im
                Eingang liegt (arbeitsliste.pool) – sonst hinge es weiter an einem Agenten, den es im Team nicht mehr gibt.
- unberuehrt  – Zahl seiner fertigen, verworfenen und geparkten Pakete.
- hinweise    – kurze Sätze für den, der entscheidet.
Aktiv ist, wer nicht entfernt und eingeschaltet ist (Soll an) oder eine laufende Sitzung hat.
"""
import json
from typing import Any

from . import arbeitsliste, db, kern

LAUFENDES = ("zu_ende", "zurueck")
TEXT = {"zu_ende": "läuft zu Ende", "zurueck": "kommt mit Übergabe-Notiz zurück in den Pool"}


def folgen(con, pid, agent, laufendes):
    """{laufend: {id, titel, folge, text} | None, wartend: [{id, titel, status, gruende}], bleibt: [Nummern der gebauten, A2095],
    unberuehrt: Zahl, hinweise: [Satz]}.
    laufendes: was mit dem laufenden Paket geschieht – „zu_ende“ oder „zurueck“."""
    if laufendes not in LAUFENDES:
        raise kern.AmwFehler(f"Das laufende Paket: {' | '.join(LAUFENDES)} – nicht „{laufendes}“")
    zeile = kern.agent_zeile(con, pid, agent)                   # unbekannt: AmwFehler; frühere Kennung → heutige
    kennung = zeile["kennung"]
    x = arbeitsliste.laufend(con, pid, kennung)
    offen = arbeitsliste.liste(con, pid, kennung) + [_mit_gruenden(con, a) for a in arbeitsliste.pool(con, pid) if a["agent"] == kennung]
    headless = {r[0] for r in con.execute("SELECT aufgabe_id FROM paket WHERE art = 'p'")}                 # A2095: führt der Arbeiter aus
    offen = [a for a in offen if a["id"] not in headless]
    bleibt = [a["id"] for a in offen if a["status"] != "laeuft" and gebaut(con, a["id"])]                     # A2095: nur noch Prüfung/Auslieferung
    weitere = [a["id"] for a in offen if a["status"] == "laeuft" and not (x and a["id"] == x["id"])]
    wartend = [{"id": a["id"], "titel": a["titel"], "status": a["status"], "gruende": a["gruende"]}
               for a in offen if a["status"] != "laeuft" and a["id"] not in bleibt]
    unberuehrt = sum(a["status"] not in kern.OFFEN_STATUS or a["einstufung"] == "geparkt"
                     for a in kern.aufgaben(con, pid, kennung, alle=True))
    return {"laufend": {"id": x["id"], "titel": x["titel"], "folge": laufendes, "text": f"A{x['id']} {TEXT[laufendes]}"} if x else None,
            "wartend": wartend, "bleibt": bleibt, "unberuehrt": unberuehrt, "hinweise": _hinweise(con, pid, zeile, weitere)}


def _mit_gruenden(con, a):
    from . import wartegrund
    return dict(a, gruende=[g["bezug"] for g in wartegrund.offene(con, a["id"])])


def _andere_aktive(con, pid, kennung):
    return [r["kennung"] for r in con.execute(
        "SELECT kennung FROM agent g WHERE projekt_id = ? AND kennung != ? AND entfernt_utc IS NULL AND (soll = 'an' OR EXISTS"
        " (SELECT 1 FROM sitzung s WHERE s.agent_id = g.id AND s.zustand = 'aktiv')) ORDER BY id", (pid, kennung))]


def _hinweise(con, pid, zeile, weitere):
    kennung, aus = zeile["kennung"], []
    if zeile["entfernt_utc"]:
        aus.append(f"{kennung} ist schon entfernt.")
    elif zeile["rolle"] == "lead":
        aus.append(f"{kennung} führt das Projekt – erst die Führung übergeben.")
    if weitere:
        aus.append(f"Bei {kennung} läuft noch mehr: {', '.join(f'A{i}' for i in weitere)} – das ist vorher zu klären.")
    aktive = _andere_aktive(con, pid, kennung)
    if not aktive:
        aus.append("Sonst ist niemand im Projekt aktiv – was in den Pool geht, bleibt dort liegen.")
    elif set(aktive) <= {kern.lead(con, pid), kern.co_entwickler(con, pid)}:      # ihnen teilt die AMW nichts zu (verteilen)
        aus.append(f"Sonst sind nur Lead und Co-Entwickler aktiv ({', '.join(aktive)}) – die AMW teilt ihnen keine Pakete zu.")
    return aus


# --- Herausnehmen und wieder freigeben (A2095) ----------------------------------------------------------------------------------
# Zustand als Ereignis, kein Schema: agent_heraus {"agent", "laufendes", "stueck", "grund", "pakete", "bleibt"} und agent_frei
# {"agent", "grund"}; der jüngste je Agent gilt. Solange er heraus ist, bekommt er nichts Neues (verteilen, „schritt naechster“, Start,
# Zuweisen von Hand, Leerlauf- und Startklar-Weckrufe); geweckt wird er nur noch zu seinem laufenden Stück. Nichts geht verloren:
# seine Nachrichten warten und wecken ihn beim Freigeben. Prozesse und Läufe beendet niemand. Gebaute Pakete (Prüfung offen oder grün)
# bleiben bei ihm; wird die Prüfung rot, gehen sie mit Übergabe-Notiz in den Pool (nachziehen, in der Verteilrunde).
HERAUS, FREI = "agent_heraus", "agent_frei"


def _json(text):
    try:
        d = json.loads(text or "{}")
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def stand(con, pid):
    """{Kennung: {"von", "seit_utc", "laufendes", "stueck", "grund"}} der herausgenommenen Agenten – je Stand der Datenbank einmal."""
    from . import einmal
    return einmal.einmal(con, (HERAUS, pid), lambda: _stand(con, pid), kopie=True)


def _stand(con, pid):
    aus = {}
    for r in con.execute("SELECT zeit_utc, von, art, text FROM plan_ereignis WHERE projekt_id = ? AND art IN (?, ?) ORDER BY id", (pid, HERAUS, FREI)):
        d = _json(r["text"])
        if r["art"] == FREI:
            aus.pop(d.get("agent"), None)
        else:
            aus[d.get("agent")] = {"von": r["von"], "seit_utc": r["zeit_utc"], "laufendes": d.get("laufendes"), "stueck": d.get("stueck"),
                                   "grund": d.get("grund")}
    return aus


def ist(con, pid, kennung):
    """Herausgenommen? Der Eintrag aus stand() oder None."""
    s: Any = stand(con, pid)
    return s.get(kennung) if kennung and kennung != kern.ENTWICKLER else None


def name(con, pid, von):
    return kern.entwickler_name(con, pid) if von == kern.ENTWICKLER else von


def sperrtext(con, pid, kennung):
    """„CC2 ist herausgenommen (von Alex: Urlaub) – erst freigeben: …“ – oder None."""
    h = ist(con, pid, kennung)
    return (f"{kennung} ist herausgenommen (von {name(con, pid, h['von'])}" + (f": {h['grund']}" if h["grund"] else "")
            + f") – erst freigeben: amw agent freigeben {kennung}") if h else None


def zuweisen_pruefen(con, pid, agent, aid=None):
    """Vor dem Zuweisen von Hand: an einen Herausgenommenen geht nichts Neues (was ihm schon gehört, darf bleiben)."""
    t = sperrtext(con, pid, agent)
    if t and not (aid and con.execute("SELECT 1 FROM aufgabe WHERE id = ? AND agent = ?", (aid, agent)).fetchone()):
        raise kern.AmwFehler(t)


def darf_starten(con, pid, agent, aid):
    """Start eines Pakets: ein Herausgenommener darf nur sein laufendes Stück und Gebautes weiterführen. Text oder None."""
    h = ist(con, pid, agent)
    return None if not h or aid == h["stueck"] or gebaut(con, aid) else sperrtext(con, pid, agent)


def darf_wecken(con, pid, agent, aid, art):
    """Geweckt wird ein Herausgenommener nur noch zu seinem laufenden Stück; stopp (das Herausnehmen selbst) immer."""
    h = ist(con, pid, agent)
    return not h or art == "stopp" or bool(h["stueck"] and aid == h["stueck"] and con.execute(
        "SELECT 1 FROM aufgabe WHERE id = ? AND agent = ? AND status NOT IN ('fertig', 'verworfen')", (aid, agent)).fetchone())


def gebaut(con, aid):
    """Fertig gebaut, wartet nur noch auf Prüfung, Stapel oder Auslieferung: die jüngste Prüfung ist offen oder grün."""
    r = con.execute("SELECT ergebnis FROM pruefung WHERE aufgabe_id = ? ORDER BY id DESC LIMIT 1", (aid,)).fetchone()
    return bool(r) and r["ergebnis"] in ("offen", "gruen")


def _eigene(con, pid, kennung):
    """Offene Pakete des Agenten (ohne geparkte und ohne Headless – die führt der Arbeiter der AMW aus)."""
    return con.execute("SELECT a.* FROM aufgabe a LEFT JOIN paket k ON k.aufgabe_id = a.id WHERE a.projekt_id = ? AND a.agent = ?"
                       " AND a.status IN ('wartet', 'laeuft', 'blockiert') AND a.einstufung != 'geparkt' AND coalesce(k.art, 'agent') != 'p'"
                       " ORDER BY a.rang, a.id", (pid, kennung)).fetchall()


def _zurueck(con, pid, von, a, kennung):
    """In der Transaktion: ein Paket ohne Bearbeiter in den Pool; war es begonnen, mit Übergabe-Notiz (wie beim Ausfall)."""
    from . import verteilen
    notiz = None
    if a["begonnen_utc"]:
        s = con.execute("SELECT s.* FROM sitzung s JOIN agent g ON g.id = s.agent_id WHERE g.projekt_id = ? AND g.kennung = ? ORDER BY s.id DESC LIMIT 1",
                        (pid, kennung)).fetchone()
        notiz = verteilen.uebergabe(con, pid, a, s)
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art="uebergabe", aufgabe_id=a["id"], bogen_id=a["bogen_id"],
                     text=json.dumps({"aufgabe": a["id"], "agent": kennung, "notiz": notiz}, ensure_ascii=False))
    con.execute("UPDATE aufgabe SET agent = NULL, status = CASE status WHEN 'laeuft' THEN 'wartet' ELSE status END, geaendert_utc = ? WHERE id = ?",
                (db.jetzt(), a["id"]))
    return notiz


def _schwer(con, pid, kennung):
    """Warum sein laufendes Stück jetzt nicht zurückkommen kann (Auslieferung oder schwerer Lauf) – oder None."""
    from . import betrieb, waechter
    w = waechter.zustand().get("wartung")
    if w and "auslieferung" in str(w.get("grund") or "").lower():
        return "gerade wird ausgeliefert"
    for l in con.execute("SELECT * FROM lauf WHERE projekt_id = ? AND agent = ? AND status = 'laeuft'", (pid, kennung)).fetchall():
        if l["schwer"] or betrieb._gesamt(con, l):
            return f"sein Lauf L{l['id']} rechnet noch"
    return None


def pruefen(con, pid, von, agent, laufendes, grund=None):
    """Darf von das? → Zeile des Agenten; sonst AmwFehler."""
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Einen Agenten nimmt der Mensch oder der Lead heraus")
    if von != kern.ENTWICKLER and not (grund or "").strip():
        raise kern.AmwFehler("Herausnehmen nur mit Grund: --grund …")
    if laufendes not in LAUFENDES:
        raise kern.AmwFehler(f"Das laufende Paket: {' | '.join(LAUFENDES)}")
    z = kern.agent_zeile(con, pid, agent)
    k = z["kennung"]
    if z["entfernt_utc"]:
        raise kern.AmwFehler(f"{k} ist schon entfernt")
    if z["rolle"] == "lead":
        raise kern.AmwFehler(f"{k} führt das Projekt – erst die Führung übergeben")
    if ist(con, pid, k):
        raise kern.AmwFehler(sperrtext(con, pid, k))
    if laufendes == "zurueck" and arbeitsliste.laufend(con, pid, k) and (g := _schwer(con, pid, k)):
        raise kern.AmwFehler(f"{k} gibt sein laufendes Paket jetzt nicht zurück: {g} – „läuft zu Ende“ geht (--laufendes zu_ende)")
    return z


def _prognose(con, pid, bogen):
    from . import planung
    p = planung.prognose(con, pid, laeufe=200)["boegen"]
    return {b: (p.get(b) or {}).get("p50") for b in bogen}


def nehmen(con, pid, von, agent, laufendes, grund=None):
    """Herausnehmen. Rückgabe: {"agent", "laufendes", "stueck", "pool": [A…], "bleibt": [A…], "hinweise", "prognose": {Meilenstein-Nummer: (vorher, nachher)}}."""
    z = pruefen(con, pid, von, agent, laufendes, grund)
    k, grund = z["kennung"], " ".join((grund or "").split())[:300] or None
    vorschau = folgen(con, pid, k, laufendes)
    bogen = sorted({a["bogen_id"] for a in _eigene(con, pid, k) if a["bogen_id"]})
    vorher = _prognose(con, pid, bogen)
    with db.schreiben(con):
        pruefen(con, pid, von, agent, laufendes, grund)                          # in der Transaktion noch einmal
        x = arbeitsliste.laufend(con, pid, k)
        stueck = x["id"] if x and laufendes == "zu_ende" else None
        pool, bleibt = [], []
        for a in _eigene(con, pid, k):
            if a["id"] == stueck or (a["status"] != "laeuft" and gebaut(con, a["id"])):
                bleibt.append(a["id"])
            else:
                _zurueck(con, pid, von, a, k)
                pool.append(a)
        je = {}
        for a in pool:
            je[a["bogen_id"]] = je.get(a["bogen_id"], 0) + 1
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=HERAUS,
                     text=json.dumps({"agent": k, "laufendes": laufendes, "stueck": stueck, "grund": grund, "pakete": [a["id"] for a in pool],
                                      "bleibt": bleibt, "je": {str(b): n for b, n in je.items() if b}}, ensure_ascii=False))
        weg = ", ".join(f"A{a['id']}" for a in pool)
        kern._posten(con, pid, "AMW", k, "stopp", f"Du bist herausgenommen (von {name(con, pid, von)}) – nichts Neues anfangen"[:140],
                     (f"Grund: {grund}\n" if grund else "")
                     + (f"A{stueck} machst du noch zu Ende; du wirst nur noch dazu geweckt.\n" if stueck else
                        (f"A{x['id']} geht mit Übergabe-Notiz in den Pool: Stand committen, dann nichts mehr daran tun.\n" if x else ""))
                     + (f"In den Pool gegangen: {weg}.\n" if weg else "")
                     + (f"Bei dir bleibt (gebaut oder laufend): {', '.join(f'A{i}' for i in bleibt)}.\n" if bleibt else "")
                     + "Nachrichten gehen nicht verloren, sie warten, bis du wieder freigegeben bist. Laufende Läufe laufen weiter.")
        lead = kern.lead(con, pid)
        if lead and lead != von:
            kern._posten(con, pid, von, lead, "meldung", f"{k} herausgenommen – {len(pool)} Paket{'e' if len(pool) != 1 else ''} im Pool"[:140],
                         "\n".join(([f"Grund: {grund}"] if grund else []) + ([f"Pool: {weg}"] if weg else [])
                                   + ([f"läuft zu Ende: A{stueck}"] if stueck else []) + vorschau["hinweise"] + _hinweis_verteilen(con, pid)))
    nachher = _prognose(con, pid, bogen)
    nr = {r["id"]: r["nr"] for r in con.execute("SELECT id, nr FROM bogen WHERE projekt_id = ?", (pid,))}
    return {"agent": k, "laufendes": laufendes, "stueck": stueck, "pool": [a["id"] for a in pool], "bleibt": bleibt,
            "hinweise": vorschau["hinweise"] + _hinweis_verteilen(con, pid),
            "prognose": {f"M{nr[b]}": (vorher[b], nachher[b]) for b in bogen if b in nr}}


def _hinweis_verteilen(con, pid):
    from . import verteilen
    w = str(verteilen.einstellung(con, pid))
    return {"an": [], "vorschlag": ["Das Verteilen steht auf „vorschlag“: der Lead teilt die Pakete im Pool zu."],
            "aus": ["Das Verteilen ist aus: die Pakete bleiben im Pool, bis jemand sie zuteilt."]}.get(w, [])


def freigeben(con, pid, von, agent, grund=None):
    """Wieder normal. Was der Mensch herausgenommen hat, gibt der Lead nicht frei. Die weggegebenen Pakete kommen nicht zurück."""
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Einen Agenten gibt der Mensch oder der Lead frei")
    k = kern.agent_zeile(con, pid, agent)["kennung"]
    with db.schreiben(con):
        h = ist(con, pid, k)
        if not h:
            raise kern.AmwFehler(f"{k} ist nicht herausgenommen")
        if h["von"] == kern.ENTWICKLER and von != kern.ENTWICKLER:
            raise kern.AmwFehler(f"{k} hat {name(con, pid, kern.ENTWICKLER)} herausgenommen – das hebt nur {name(con, pid, kern.ENTWICKLER)} auf")
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=FREI,
                     text=json.dumps({"agent": k, "grund": " ".join((grund or "").split())[:300] or None}, ensure_ascii=False))
        kern._posten(con, pid, "AMW", k, "freigabe", f"Du bist wieder dabei (von {name(con, pid, von)})"[:140],
                     "Neues bekommst du wie zuvor über die Verteilung; was in den Pool ging, kommt nicht von selbst zurück.")
        lead = kern.lead(con, pid)
        if lead and lead != von:
            kern._posten(con, pid, von, lead, "info", f"{k} ist wieder freigegeben", (grund or "").strip() or None)
    return {"agent": k}


def nachziehen(con, pid):
    """Dienst (vor jeder Verteilrunde): was ein Herausgenommener nicht mehr weiterführt, geht in den Pool – Gebautes mit roter Prüfung,
    und sein Stück, sobald es auf etwas anderes wartet als Prüfung, Stapel oder Lauf. Rückgabe: Texte."""
    from . import wartegrund
    aus = []
    for k, h in stand(con, pid).items():
        for a in _eigene(con, pid, k):
            if a["status"] == "laeuft" or gebaut(con, a["id"]):
                continue
            gr = wartegrund.offene(con, a["id"])
            if a["id"] == h["stueck"] and all(wartegrund.sorte(g["art"], g["bezug"], g["bezug"]) in wartegrund.FREIGEBEND for g in gr):
                continue
            with db.schreiben(con):
                _zurueck(con, pid, "AMW", a, k)
                if lead := kern.lead(con, pid):
                    kern._posten(con, pid, "AMW", lead, "meldung", f"A{a['id']} von {k} (herausgenommen) zurück in den Pool"[:140],
                                 f"„{a['titel'][:100]}“", aufgabe_id=a["id"])
            aus.append(f"A{a['id']} von {k} zurück in den Pool")
    return aus
