"""Fachlogik der AMW: Nachrichten, Aufgaben, Fragen, Halt, Pflicht-Kontext.

Jede Funktion bekommt eine offene Verbindung und schreibt über db.schreiben/db.einfuegen.
Regeln, die hier geprüft werden, beschreibt doc/architektur.md.
Die Prüfungen schützen vor Versehen, nicht vor Absicht: Agenten laufen unter dem Benutzer des Entwicklers.
"""
import json

from . import db

ENTWICKLER = "Entwickler"       # Absender für Eingaben über die Workbench
OFFEN_STATUS = ("wartet", "laeuft", "blockiert")


class AmwFehler(Exception):
    """Fehler, den der Aufrufer dem Nutzer zeigen soll (kein Programmfehler)."""


# --- Agenten und Projekt -------------------------------------------------------------------------

def agent_zeile(con, pid, kennung):
    r = con.execute("SELECT * FROM agent WHERE projekt_id = ? AND kennung = ?", (pid, kennung)).fetchone()
    if not r:
        raise AmwFehler(f"Agent „{kennung}“ gibt es im Projekt nicht")
    return r


def ist_lead(con, pid, kennung):
    if kennung == ENTWICKLER:
        return True
    r = con.execute("SELECT rolle FROM agent WHERE projekt_id = ? AND kennung = ?", (pid, kennung)).fetchone()
    return bool(r) and r["rolle"] == "lead"


def agent_neu(con, pid, kennung, rolle=None, grenzen=None, startbefehl=None, empfaengt_rund=True):
    with db.schreiben(con):
        return db.einfuegen(con, "agent", projekt_id=pid, kennung=kennung, rolle=rolle, grenzen=grenzen,
                            startbefehl=startbefehl, empfaengt_rund=int(empfaengt_rund), angelegt_utc=db.jetzt())


def projekt_einstellen(con, pid, von, **werte):
    """Zahnrad „Projekt“: takt_min (0 = aus, bis 1440), speicher_grenze_gb (1–512), stillstand_min und
    lauf_ohne_angabe_min (Warnungen, 5–1440). Nur Lead und Entwickler."""
    if not ist_lead(con, pid, von):
        raise AmwFehler("Projekt-Einstellungen dürfen nur Lead und Entwickler ändern")
    grenzen = {"takt_min": (0, 1440), "speicher_grenze_gb": (1, 512), "stillstand_min": (5, 1440), "lauf_ohne_angabe_min": (5, 1440)}
    with db.schreiben(con):
        e = json.loads(con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()[0] or "{}")
        for k, v in werte.items():
            if k not in grenzen:
                raise AmwFehler(f"unbekannte Projekt-Einstellung: {k}")
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise AmwFehler(f"{k}: Zahl erwartet") from None
            lo, hi = grenzen[k]
            if not lo <= v <= hi:
                raise AmwFehler(f"{k}: zwischen {lo} und {hi}")
            e[k] = int(v) if v == int(v) else v
        con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?", (json.dumps(e), pid))
    return e


def agent_einstellen(con, pid, von, kennung, neu=False, **werte):
    """Zahnrad „Agenten“: rolle, soll (an/aus/ruht), grenzen, empfaengt_rund, puls_grenze_s. Nur Lead und Entwickler."""
    if not ist_lead(con, pid, von):
        raise AmwFehler("Agenten dürfen nur Lead und Entwickler einstellen")
    kennung = (kennung or "").strip()
    if not kennung or len(kennung) > 20 or not all(c.isalnum() or c in "-_" for c in kennung) or kennung.lower() == ENTWICKLER.lower():
        raise AmwFehler("Kennung: bis 20 Zeichen, Buchstaben/Ziffern/-/_, nicht „Entwickler“")
    felder = {}
    for k, v in werte.items():
        if k == "rolle":
            v = (v or "").strip() or None
            if v and len(v) > 20:
                raise AmwFehler("rolle: höchstens 20 Zeichen")
        elif k == "soll":
            if v not in ("an", "aus", "ruht"):
                raise AmwFehler("soll: an, aus oder ruht")
        elif k == "grenzen":
            v = (v or "").strip()[:200] or None
        elif k == "empfaengt_rund":
            v = 1 if v in (True, 1, "1", "true", "ja", "an") else 0
        elif k == "puls_grenze_s":
            try:
                v = int(v)
            except (TypeError, ValueError):
                raise AmwFehler("puls_grenze_s: ganze Zahl") from None
            if not 60 <= v <= 86400:
                raise AmwFehler("puls_grenze_s: zwischen 60 und 86400")
        else:
            raise AmwFehler(f"unbekannte Agenten-Einstellung: {k}")
        felder[k] = v
    da = con.execute("SELECT 1 FROM agent WHERE projekt_id = ? AND kennung = ?", (pid, kennung)).fetchone()
    if neu and da:
        raise AmwFehler(f"{kennung} gibt es schon")
    if not neu and not da:
        raise AmwFehler(f"Agent {kennung} gibt es nicht")
    if neu:
        agent_neu(con, pid, kennung)
    if felder:
        with db.schreiben(con):
            con.execute(f"UPDATE agent SET {', '.join(k + ' = ?' for k in felder)} WHERE projekt_id = ? AND kennung = ?",
                        (*felder.values(), pid, kennung))
    return kennung


def taetigkeit(con, pid, kennung, text, aufgabe_id=None):
    """Was der Agent gerade tut (zeigt die Workbench auf seiner Kachel); leerer Text löscht die Angabe."""
    a = agent_zeile(con, pid, kennung)
    with db.schreiben(con):
        s = con.execute("SELECT id FROM sitzung WHERE agent_id = ? AND zustand = 'aktiv' ORDER BY id DESC LIMIT 1",
                        (a["id"],)).fetchone()
        if not s:
            raise AmwFehler(f"{kennung} hat keine aktive Sitzung – erst: amw anmelden --von {kennung}")
        con.execute("UPDATE sitzung SET taetigkeit = ?, aufgabe_id = ?, letzter_puls_utc = ? WHERE id = ?",
                    ((text or "").strip()[:200] or None, aufgabe_id, db.jetzt(), s["id"]))


# --- Halt und Sperren ----------------------------------------------------------------------------

def aktive_sperren(con, pid, kennung=None, art=None):
    sql = ("SELECT * FROM sperre WHERE projekt_id = ? AND aufgehoben_utc IS NULL"
           " AND (bis_utc IS NULL OR bis_utc > ?)")
    par = [pid, db.jetzt()]
    if kennung:
        sql += " AND gilt_fuer IN ('alle', ?)"
        par.append(kennung)
    if art:
        sql += " AND art = ?"
        par.append(art)
    return con.execute(sql + " ORDER BY seit_utc", par).fetchall()


def halt_gilt(con, pid, kennung):
    return bool(aktive_sperren(con, pid, kennung, "halt"))


def halt(con, pid, von, gilt_fuer, text):
    """Setzt einen Halt und schickt jedem Betroffenen ein STOPP (weckt; der Dienst stellt es zu)."""
    if not ist_lead(con, pid, von):
        raise AmwFehler("Halt dürfen nur Entwickler und Lead setzen")
    with db.schreiben(con):
        sid = db.einfuegen(con, "sperre", projekt_id=pid, art="halt", gilt_fuer=gilt_fuer, von=von,
                           text=text, seit_utc=db.jetzt())
        _posten(con, pid, von, gilt_fuer, "stopp", f"HALT: {text}",
                f"Halt #{sid} von {von}. Aktuelle Arbeit sauber beenden, nichts Neues anfangen, "
                f"bis „weiter“ kommt.")
    return sid


def weiter(con, pid, von, gilt_fuer):
    if not ist_lead(con, pid, von):
        raise AmwFehler("Weiter dürfen nur Entwickler und Lead geben")
    with db.schreiben(con):
        n = con.execute("UPDATE sperre SET aufgehoben_utc = ? WHERE projekt_id = ? AND art = 'halt'"
                        " AND gilt_fuer = ? AND aufgehoben_utc IS NULL", (db.jetzt(), pid, gilt_fuer)).rowcount
        if n:
            _posten(con, pid, von, gilt_fuer, "freigabe", "WEITER: Halt aufgehoben", f"{n} Halt aufgehoben von {von}.")
    return n


# --- Nachrichten ---------------------------------------------------------------------------------

def empfaenger(con, pid, an, von):
    namen = []
    for teil in an.replace(";", ",").split(","):
        teil = teil.strip()
        if not teil:
            continue
        if teil.lower() == "alle":
            namen += [r["kennung"] for r in con.execute(
                "SELECT kennung FROM agent WHERE projekt_id = ? AND empfaengt_rund = 1 AND soll != 'aus'"
                " ORDER BY id", (pid,))]
        elif teil.lower() == ENTWICKLER.lower():         # der Mensch: liest in der Workbench, wird nie geweckt
            namen.append(ENTWICKLER)
        else:
            agent_zeile(con, pid, teil)
            namen.append(teil)
    aus = [n for i, n in enumerate(namen) if n != von and n not in namen[:i]]
    if not aus:
        raise AmwFehler("kein Empfänger")
    return aus


def _posten(con, pid, von, an, art, kurz, text=None, antwort_auf=None, aufgabe_id=None):
    if not con.execute("SELECT 1 FROM nachricht_art WHERE art = ?", (art,)).fetchone():
        erlaubt = ", ".join(r[0] for r in con.execute("SELECT art FROM nachricht_art ORDER BY art"))
        raise AmwFehler(f"Art „{art}“ gibt es nicht; erlaubt: {erlaubt}")
    namen = empfaenger(con, pid, an, von)
    nid = db.einfuegen(con, "nachricht", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=art, kurz=kurz,
                       text=text, antwort_auf=antwort_auf, aufgabe_id=aufgabe_id)
    for n in namen:
        db.einfuegen(con, "empfang", nachricht_id=nid, agent=n)
    if antwort_auf:                                    # Antwort auf eine Rückfrage → Nachtrag im Verlauf der Frage
        r = con.execute("SELECT frage_id FROM frage_verlauf WHERE nachricht_id = ? AND art = 'rueckfrage'",
                        (antwort_auf,)).fetchone()
        if r:
            db.einfuegen(con, "frage_verlauf", frage_id=r["frage_id"], zeit_utc=db.jetzt(), von=von, art="nachtrag",
                         text=(kurz + ("\n" + text if text else "")).strip(), nachricht_id=nid)
    return nid, namen


def posten(con, pid, von, an, art, kurz, text=None, antwort_auf=None, aufgabe_id=None):
    with db.schreiben(con):
        return _posten(con, pid, von, an, art, kurz, text, antwort_auf, aufgabe_id)


def offene(con, pid, kennung, grenze=50, neueste_zuerst=False):
    return con.execute(
        "SELECT n.id, n.zeit_utc, n.von, n.art, n.kurz, n.aufgabe_id, e.status, a.weckt"
        " FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id JOIN nachricht_art a ON a.art = n.art"
        " WHERE n.projekt_id = ? AND e.agent = ? AND e.status != 'erledigt'"
        f" ORDER BY n.id {'DESC' if neueste_zuerst else ''} LIMIT ?",
        (pid, kennung, grenze)).fetchall()


def anzahl_offen(con, pid, kennung):
    return con.execute("SELECT count(*) FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id"
                       " WHERE n.projekt_id = ? AND e.agent = ? AND e.status != 'erledigt'",
                       (pid, kennung)).fetchone()[0]


def lesen(con, pid, kennung, nid):
    """Ganze Nachricht; markiert sie für den Leser als gelesen."""
    n = con.execute("SELECT * FROM nachricht WHERE id = ? AND projekt_id = ?", (nid, pid)).fetchone()
    if not n:
        raise AmwFehler(f"Nachricht #{nid} gibt es nicht")
    with db.schreiben(con):
        con.execute("UPDATE empfang SET status = 'gelesen', gelesen_utc = ? WHERE nachricht_id = ? AND agent = ?"
                    " AND status = 'offen'", (db.jetzt(), nid, kennung))
    return n


def erledigt(con, pid, kennung, nids, bemerkung=None):
    """Mehrere Nachrichten auf einmal erledigen . Gibt die Zahl der geänderten Empfänge zurück."""
    with db.schreiben(con):
        n = 0
        for nid in nids:
            n += con.execute(
                "UPDATE empfang SET status = 'erledigt', erledigt_utc = ?, bemerkung = coalesce(?, bemerkung)"
                " WHERE nachricht_id = ? AND agent = ? AND status != 'erledigt'"
                " AND nachricht_id IN (SELECT id FROM nachricht WHERE projekt_id = ?)",
                (db.jetzt(), bemerkung, nid, kennung, pid)).rowcount
    return n


# --- Aufgaben ------------------------------------------------------------------------------------

def aufgabe_neu(con, pid, von, titel, agent=None, auftrag=None, rang=50, pruefer=None, abhaengig_von=None):
    with db.schreiben(con):
        if agent:
            agent_zeile(con, pid, agent)
        return db.einfuegen(con, "aufgabe", projekt_id=pid, titel=titel, auftrag=auftrag, agent=agent,
                            pruefer=pruefer, angelegt_von=von, rang=rang, abhaengig_von=abhaengig_von,
                            angelegt_utc=db.jetzt())


def _aufgabe_fuer_aenderung(con, pid, von, aid):
    a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    if not a:
        raise AmwFehler(f"Aufgabe A{aid} gibt es nicht")
    if a["agent"] and a["agent"] != von and not ist_lead(con, pid, von):
        raise AmwFehler(f"A{aid} gehört {a['agent']} – nur der Besitzer oder Lead darf den Status ändern")
    return a


def aufgabe_status(con, pid, von, aid, status, beleg=None, wartet_auf=None, bemerkung=None, zusammenfassung=None):
    neu = {"start": "laeuft", "blockiert": "blockiert", "wartet": "wartet", "fertig": "fertig",
           "verwerfen": "verworfen"}.get(status, status)
    if neu == "laeuft" and halt_gilt(con, pid, von):
        raise AmwFehler("HALT gilt – keine neuen Aufgaben starten (amw kontext zeigt den Halt)")
    if neu in ("fertig", "verworfen") and not (beleg or "").strip():
        raise AmwFehler("fertig/verworfen nur mit --beleg (Commit, Datei:Zeile oder Folgeaufgabe)")
    with db.schreiben(con):
        a = _aufgabe_fuer_aenderung(con, pid, von, aid)
        from . import planung                       # Regeln der Planung: Vorgänger, Plan-Gate, Kriterien, Zusammenfassung
        planung.pruefe_status(con, a, neu, zusammenfassung)
        t = db.jetzt()
        felder = {"status": neu}
        if zusammenfassung:
            felder["zusammenfassung"] = zusammenfassung
        if neu == "laeuft" and not a["begonnen_utc"]:
            felder["begonnen_utc"] = t
        if neu in ("fertig", "verworfen"):
            felder["fertig_utc"] = t
            felder["beleg"] = beleg
        if wartet_auf is not None or neu in ("laeuft", "fertig", "verworfen"):
            felder["wartet_auf"] = wartet_auf
        if bemerkung:
            felder["bemerkung"] = ((a["bemerkung"] + " || ") if a["bemerkung"] else "") + f"{von} {t}: {bemerkung}"
        satz = ", ".join(f"{k} = ?" for k in felder)
        con.execute(f"UPDATE aufgabe SET {satz} WHERE id = ?", (*felder.values(), aid))
    return neu


def aufgaben(con, pid, agent=None, alle=False):
    sql = "SELECT * FROM aufgabe WHERE projekt_id = ?"
    par = [pid]
    if agent:
        sql += " AND agent = ?"
        par.append(agent)
    if not alle:
        sql += " AND status IN ('wartet', 'laeuft', 'blockiert')"
    return con.execute(sql + " ORDER BY rang, id", par).fetchall()


# --- Fragen --------------------------------------------------------------------------------------

def frage_neu(con, pid, von, an, kurz, optionen, empfehlung=None, grund=None, worum=None, fundstellen=None,
              aufgabe_id=None, blockiert=False, folge_von=None):
    """optionen: Liste von (kenn, text). Empfehlung muss eine der Kennungen sein."""
    kenn = [k for k, _ in optionen]
    if empfehlung and empfehlung not in kenn:
        raise AmwFehler(f"Empfehlung „{empfehlung}“ ist keine der Optionen {kenn}")
    if an == "entwickler" and optionen and not (empfehlung and grund):
        raise AmwFehler("Fragen an den Entwickler brauchen Empfehlung und Grund")
    with db.schreiben(con):
        fid = db.einfuegen(con, "frage", projekt_id=pid, an=an, von=von, zeit_utc=db.jetzt(), kurz=kurz,
                           worum=worum, optionen=json.dumps([{"kenn": k, "text": t} for k, t in optionen],
                                                            ensure_ascii=False),
                           empfehlung=empfehlung, grund=grund, fundstellen=fundstellen, aufgabe_id=aufgabe_id,
                           blockiert=int(blockiert), folge_von=folge_von)
        if an == "tl":
            lead = con.execute("SELECT kennung FROM agent WHERE projekt_id = ? AND rolle = 'lead' LIMIT 1",
                               (pid,)).fetchone()
            if lead:
                _posten(con, pid, von, lead["kennung"], "frage", f"Frage F{fid}: {kurz}", aufgabe_id=aufgabe_id)
    return fid


def frage_antworten(con, pid, fid, antwort_art, antwort, kanal, von=ENTWICKLER):
    """Speichert die Antwort und benachrichtigt den Fragesteller (weckt). Text des Entwicklers → wortlaut."""
    f = con.execute("SELECT * FROM frage WHERE id = ? AND projekt_id = ?", (fid, pid)).fetchone()
    if not f:
        raise AmwFehler(f"Frage F{fid} gibt es nicht")
    if f["status"] != "offen":
        raise AmwFehler(f"F{fid} ist schon {f['status']}")
    if antwort_art == "option":
        kenn = [o["kenn"] for o in json.loads(f["optionen"])]
        if antwort not in kenn:
            raise AmwFehler(f"„{antwort}“ ist keine der Optionen {kenn}")
    t = db.jetzt()
    with db.schreiben(con):
        status = "offen" if antwort_art == "rueckfrage" else "beantwortet"
        con.execute("UPDATE frage SET status = ?, antwort_art = ?, antwort = ?, antwort_utc = ?, antwort_kanal = ?"
                    " WHERE id = ?", (status, antwort_art, antwort, t, kanal, fid))
        if von == ENTWICKLER and antwort_art in ("text", "rueckfrage"):
            db.einfuegen(con, "wortlaut", projekt_id=pid, zeit_utc=t, text=antwort, kanal=kanal,
                         erfasst_von="amw", erfasst_utc=t, bemerkung=f"Antwort auf F{fid}")
        art = "frage" if antwort_art == "rueckfrage" else "antwort"
        nid = None
        if f["von"] != von:
            nid, _ = _posten(con, pid, von, f["von"], art, f"{'Rückfrage' if art == 'frage' else 'Antwort'} zu F{fid}: {antwort[:120]}",
                             text=antwort if len(antwort) > 120 else None, aufgabe_id=f["aufgabe_id"])
        if antwort_art == "option":                    # im Verlauf mit dem Text der Option
            antwort = next((f"{o['kenn']}) {o['text']}" for o in json.loads(f["optionen"]) if o["kenn"] == antwort), antwort)
        db.einfuegen(con, "frage_verlauf", frage_id=fid, zeit_utc=t, von=von,
                     art="rueckfrage" if antwort_art == "rueckfrage" else "antwort", text=antwort, nachricht_id=nid)
        # wer antwortet, hat die Nachträge im Verlauf gelesen – sie stehen nicht mehr unter „Nachrichten an dich“
        con.execute("UPDATE empfang SET status = 'erledigt', erledigt_utc = ? WHERE agent = ? AND status != 'erledigt'"
                    " AND nachricht_id IN (SELECT nachricht_id FROM frage_verlauf WHERE frage_id = ? AND nachricht_id IS NOT NULL)",
                    (t, von, fid))
    return status


def frage_nachtrag(con, pid, von, fid, text):
    """Der Fragesteller ergänzt seine Frage oder antwortet auf eine Rückfrage. Die Frage bleibt offen; wer gefragt
    wurde (Entwickler bzw. Lead), bekommt eine Nachricht – beim Entwickler unter „Nachrichten an dich“."""
    f = con.execute("SELECT * FROM frage WHERE id = ? AND projekt_id = ?", (fid, pid)).fetchone()
    if not f:
        raise AmwFehler(f"Frage F{fid} gibt es nicht")
    if f["status"] != "offen":
        raise AmwFehler(f"F{fid} ist schon {f['status']}")
    if von != f["von"] and not ist_lead(con, pid, von):
        raise AmwFehler(f"Nachträge zu F{fid} schreibt der Fragesteller ({f['von']}) oder der Lead")
    text = (text or "").strip()
    if not text:
        raise AmwFehler("Text fehlt")
    an = ENTWICKLER if f["an"] == "entwickler" else ",".join(
        r[0] for r in con.execute("SELECT kennung FROM agent WHERE projekt_id = ? AND rolle = 'lead'", (pid,))) or ENTWICKLER
    with db.schreiben(con):
        nid, _ = _posten(con, pid, von, an, "antwort", f"Nachtrag zu F{fid}: {text[:120]}",
                         text=text if len(text) > 120 else None, aufgabe_id=f["aufgabe_id"])
        db.einfuegen(con, "frage_verlauf", frage_id=fid, zeit_utc=db.jetzt(), von=von, art="nachtrag", text=text,
                     nachricht_id=nid)
    return nid


def offene_fragen(con, pid, an=None):
    sql = "SELECT * FROM frage WHERE projekt_id = ? AND status = 'offen'"
    par = [pid]
    if an:
        sql += " AND an = ?"
        par.append(an)
    return con.execute(sql + " ORDER BY blockiert DESC, id", par).fetchall()


# --- Pflicht-Kontext --------------------------------------------------------------------------

KONTEXT_MAX = 9000   # Hook-Grenze 10 000 Zeichen, mit Luft


def kontext(con, pid, kennung):
    """Text, den der SessionStart-Hook nach Start/Komprimierung einspielt. Erzeugt aus den Daten, nie fest."""
    a = agent_zeile(con, pid, kennung)
    proj = con.execute("SELECT name FROM projekt WHERE id = ?", (pid,)).fetchone()["name"]
    vorher = con.execute("SELECT max(gestartet_utc) FROM sitzung WHERE agent_id = ? AND zustand != 'aktiv'",
                         (a["id"],)).fetchone()[0]
    z = [f"AMW-PFLICHTKONTEXT für {kennung} (Projekt {proj}, Stand {db.jetzt()}). "
         f"Rolle: {a['rolle'] or '–'}" + (f" · Grenzen: {a['grenzen']}" if a["grenzen"] else "")]

    halte = aktive_sperren(con, pid, kennung, "halt")
    if halte:
        z.append("!! HALT GILT: " + " | ".join(f"#{s['id']} {s['von']}: {s['text']}" for s in halte)
                 + " – nichts Neues anfangen.")
    hinweise = aktive_sperren(con, pid, kennung, "hinweis")
    if hinweise:
        z.append("Geltende Anweisungen: " + " | ".join(f"{s['von']}: {s['text']}" for s in hinweise))

    try:                                            # Planung: Leitbild, aktive Bögen, nächster Schritt
        from . import planung
        z += planung.kontext_zeilen(con, pid, kennung)
    except Exception:
        pass

    eigene = aufgaben(con, pid, kennung)
    z.append(f"Deine offenen Aufgaben ({len(eigene)}): " + ("; ".join(
        f"A{x['id']} [{x['status']}] {x['titel']}" + (f" (wartet auf {x['wartet_auf']})" if x["wartet_auf"] else "")
        for x in eigene[:10]) or "keine"))

    wartende = con.execute("SELECT id, agent, titel FROM aufgabe WHERE projekt_id = ? AND status IN"
                           " ('wartet', 'blockiert') AND wartet_auf LIKE ? ORDER BY id LIMIT 10",
                           (pid, f"%{kennung}%")).fetchall()
    if wartende:
        z.append("Wartet auf dich: " + "; ".join(f"A{x['id']} ({x['agent']}) {x['titel']}" for x in wartende))

    pr = con.execute("SELECT * FROM pruefung WHERE projekt_id = ? AND ergebnis = 'offen' AND (pruefer = ? OR bauer = ?)"
                     " ORDER BY id", (pid, kennung, kennung)).fetchall()
    if pr:
        z.append("Offene Prüfungen: " + "; ".join(
            f"P{p['id']} {p['zweig']}@{p['sha'][:7]} {'prüfst du' if p['pruefer'] == kennung else 'prüft ' + p['pruefer']}"
            for p in pr))

    laeufe = con.execute("SELECT id, beschreibung, status FROM lauf WHERE projekt_id = ? AND agent = ?"
                         " AND status IN ('angemeldet', 'laeuft')", (pid, kennung)).fetchall()
    if laeufe:
        z.append("Deine Läufe: " + "; ".join(f"L{x['id']} [{x['status']}] {x['beschreibung']}" for x in laeufe))

    zahl = anzahl_offen(con, pid, kennung)
    if zahl:
        nachr = offene(con, pid, kennung, 8, neueste_zuerst=True)
        z.append(f"Offene Nachrichten ({zahl}, neueste zuerst): " + "; ".join(
            f"#{x['id']} {x['von']} [{x['art']}] {x['kurz'][:80]}" for x in nachr)
            + (" …" if zahl > 8 else "") + " → `amw lesen`")

    regeln = con.execute("SELECT nr, text, stand_utc, ebene FROM regel WHERE (ebene = 'arbeit' OR projekt_id = ?)"
                         " ORDER BY ebene, nr", (pid,)).fetchall()
    if regeln:
        neu = [r for r in regeln if vorher and r["stand_utc"] > vorher]
        z.append(f"Regeln: {len(regeln)} gültig (`amw regeln`)."
                 + (" GEÄNDERT seit deiner letzten Sitzung: " + " | ".join(
                     f"{'KR' if r['ebene'] == 'arbeit' else 'PR'}{r['nr']}: {r['text']}" for r in neu) if neu else ""))

    rez = con.execute("SELECT name FROM rezept WHERE projekt_id = ? ORDER BY name", (pid,)).fetchall()
    if rez:
        z.append("Lauf-Rezepte: " + ", ".join(r["name"] for r in rez) + " (`amw rezept zeige <name>`)")

    text = "\n".join(z)
    return text if len(text) <= KONTEXT_MAX else text[:KONTEXT_MAX - 40] + "\n… (gekürzt, Rest per amw)"
