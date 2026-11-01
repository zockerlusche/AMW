"""Rückblick und Verlauf (Stufe F, → doc/ausbau.md §7).

- Rückblick je Bogen: „Was lief gut / was nicht / was ändern wir / was haben wir gelernt“. Eine Maßnahme wird mit einem
  Schritt zur Aufgabe oder (Lead/Entwickler) zum Beschluss – der Bezug bleibt erhalten.
- Verlauf: eine Zeitleiste aus den vorhandenen Daten (Nachrichten, Erledigtes, Läufe, Prüfungen, Fragen, Beschlüsse,
  Planung, Sitzungen) – nichts wird doppelt erfasst.
- Zusammenfassung seit einem Zeitpunkt („Seit du weg warst“, täglicher Push-Rückblick): nur Zahlen.
"""
from . import db, kern

ARTEN = ("gut", "schlecht", "massnahme", "gelernt")
VERLAUF_ARTEN = ("nachricht", "erledigt", "lauf", "pruefung", "frage", "beschluss", "plan", "sitzung")


def rueckblick_neu(con, pid, von, bogen_id, art, text):
    if art not in ARTEN:
        raise kern.AmwFehler("Art: " + " | ".join(ARTEN))
    if not (text or "").strip():
        raise kern.AmwFehler("Text fehlt")
    if bogen_id is not None and not con.execute("SELECT 1 FROM bogen WHERE id = ? AND projekt_id = ?", (bogen_id, pid)).fetchone():
        raise kern.AmwFehler(f"Bogen {bogen_id} gibt es nicht")
    with db.schreiben(con):
        return db.einfuegen(con, "rueckblick", projekt_id=pid, bogen_id=bogen_id, art=art, text=text.strip(), von=von,
                            zeit_utc=db.jetzt())


def rueckblicke(con, pid, bogen_id=None):
    sql = "SELECT * FROM rueckblick WHERE projekt_id = ?" + (" AND bogen_id = ?" if bogen_id is not None else "") + " ORDER BY id"
    return [dict(r) for r in con.execute(sql, (pid, bogen_id) if bogen_id is not None else (pid,))]


def massnahme_uebernehmen(con, pid, von, rid, als, agent=None):
    """Maßnahme → Aufgabe (jeder) oder Beschluss (Lead/Entwickler). Rückgabe: neue Nummer."""
    r = con.execute("SELECT * FROM rueckblick WHERE id = ? AND projekt_id = ?", (rid, pid)).fetchone()
    if not r:
        raise kern.AmwFehler(f"Rückblick-Eintrag {rid} gibt es nicht")
    if r["aufgabe_id"] or r["beschluss_id"]:
        raise kern.AmwFehler(f"schon übernommen ({'A' + str(r['aufgabe_id']) if r['aufgabe_id'] else 'B' + str(r['beschluss_id'])})")
    herkunft = f"Rückblick {rid}" + (f" zu Bogen {r['bogen_id']}" if r["bogen_id"] else "")
    if als == "aufgabe":
        aid = kern.aufgabe_neu(con, pid, von, r["text"][:200], agent, auftrag=f"{r['text']}\n\n(aus {herkunft})")
        with db.schreiben(con):
            con.execute("UPDATE rueckblick SET aufgabe_id = ? WHERE id = ?", (aid, rid))
        return aid
    if als == "beschluss":
        from . import wissen
        bid = wissen.beschluss_neu(con, pid, von, r["text"][:120], r["text"], herkunft, thema="Lessons Learned")
        with db.schreiben(con):
            con.execute("UPDATE rueckblick SET beschluss_id = ? WHERE id = ?", (bid, rid))
        return bid
    raise kern.AmwFehler("als: aufgabe | beschluss")


def verlauf(con, pid, ab_utc, bis_utc=None, agent=None, arten=None, grenze=300):
    """Ereignisse zwischen ab_utc und bis_utc, neueste zuerst: {"zeit", "art", "wer", "ref", "text"}."""
    bis_utc = bis_utc or "9999"
    arten = set(arten or VERLAUF_ARTEN)
    q = []
    p = (pid, ab_utc, bis_utc)
    if "nachricht" in arten:
        q.append(("SELECT zeit_utc AS zeit, 'nachricht' AS art, von AS wer, '#' || id AS ref, kurz AS text, art AS zusatz"
                  " FROM nachricht WHERE projekt_id = ? AND zeit_utc >= ? AND zeit_utc < ?", p))
    if "erledigt" in arten:
        q.append(("SELECT fertig_utc, 'erledigt', coalesce(agent, ''), 'A' || id, titel, status FROM aufgabe"
                  " WHERE projekt_id = ? AND status IN ('fertig', 'verworfen') AND fertig_utc >= ? AND fertig_utc < ?", p))
    if "lauf" in arten:
        q.append(("SELECT start_utc, 'lauf', agent, 'L' || id, beschreibung, 'start' FROM lauf WHERE projekt_id = ?"
                  " AND start_utc >= ? AND start_utc < ?", p))
        q.append(("SELECT ende_utc, 'lauf', agent, 'L' || id, beschreibung, status || ' rc ' || coalesce(rc, '–') FROM lauf"
                  " WHERE projekt_id = ? AND ende_utc >= ? AND ende_utc < ?", p))
    if "pruefung" in arten:
        q.append(("SELECT ergebnis_utc, 'pruefung', pruefer, 'P' || id, zweig || ' ' || substr(sha, 1, 8), ergebnis FROM pruefung"
                  " WHERE projekt_id = ? AND ergebnis_utc >= ? AND ergebnis_utc < ?", p))
    if "frage" in arten:
        q.append(("SELECT zeit_utc, 'frage', von, 'F' || id, kurz, 'gestellt' FROM frage WHERE projekt_id = ?"
                  " AND zeit_utc >= ? AND zeit_utc < ?", p))
        q.append(("SELECT antwort_utc, 'frage', 'Entwickler', 'F' || id, kurz, 'beantwortet' FROM frage WHERE projekt_id = ?"
                  " AND status = 'beantwortet' AND antwort_utc >= ? AND antwort_utc < ?", p))
    if "beschluss" in arten:
        q.append(("SELECT angelegt_utc, 'beschluss', angelegt_von, 'B' || id, stichwort, status FROM beschluss"
                  " WHERE projekt_id = ? AND angelegt_utc >= ? AND angelegt_utc < ?", p))
    if "plan" in arten:
        q.append(("SELECT zeit_utc, 'plan', von, coalesce('Bogen ' || bogen_id, 'A' || aufgabe_id, ''), coalesce(text, ''), art"
                  " FROM plan_ereignis WHERE projekt_id = ? AND zeit_utc >= ? AND zeit_utc < ?", p))
    if "sitzung" in arten:
        q.append(("SELECT s.gestartet_utc, 'sitzung', a.kennung, 'S' || s.id, 'Sitzung gestartet', 'start' FROM sitzung s"
                  " JOIN agent a ON a.id = s.agent_id WHERE a.projekt_id = ? AND s.gestartet_utc >= ? AND s.gestartet_utc < ?", p))
        q.append(("SELECT s.beendet_utc, 'sitzung', a.kennung, 'S' || s.id, 'Sitzung beendet', 'ende' FROM sitzung s"
                  " JOIN agent a ON a.id = s.agent_id WHERE a.projekt_id = ? AND s.beendet_utc >= ? AND s.beendet_utc < ?", p))
    if not q:
        return []
    # Spaltennamen fest vorgeben – sonst hängen sie davon ab, welche Teilabfrage zuerst kommt
    sql = "WITH e(zeit, art, wer, ref, text, zusatz) AS (" + " UNION ALL ".join(s for s, _ in q) + ") SELECT * FROM e"
    par = [x for _, ps in q for x in ps]
    if agent:
        sql += " WHERE wer = ?"
        par.append(agent)
    sql += " ORDER BY zeit DESC LIMIT ?"
    par.append(int(grenze))
    return [{"zeit": r[0], "art": r[1], "wer": r[2], "ref": r[3], "text": r[4], "zusatz": r[5]} for r in con.execute(sql, par)]


def zusammenfassung(con, pid, seit_utc):
    """Zahlen seit seit_utc – für „Seit du weg warst“ und den täglichen Rückblick."""
    z = lambda sql, *a: con.execute(sql, (pid, seit_utc, *a)).fetchone()[0] or 0
    aus = {
        "an_dich": z("SELECT count(*) FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id WHERE n.projekt_id = ?"
                     " AND n.zeit_utc >= ? AND e.agent = ?", kern.ENTWICKLER),
        "erledigt": z("SELECT count(*) FROM aufgabe WHERE projekt_id = ? AND status = 'fertig' AND fertig_utc >= ?"),
        "laeufe": z("SELECT count(*) FROM lauf WHERE projekt_id = ? AND ende_utc >= ?"),
        "gruen": z("SELECT count(*) FROM pruefung WHERE projekt_id = ? AND ergebnis_utc >= ? AND ergebnis = 'gruen'"),
        "rot": z("SELECT count(*) FROM pruefung WHERE projekt_id = ? AND ergebnis_utc >= ? AND ergebnis = 'rot'"),
        "fragen_neu": z("SELECT count(*) FROM frage WHERE projekt_id = ? AND zeit_utc >= ? AND an = 'entwickler'"),
        "beschluesse": z("SELECT count(*) FROM beschluss WHERE projekt_id = ? AND angelegt_utc >= ?"),
        "boegen_fertig": z("SELECT count(*) FROM plan_ereignis WHERE projekt_id = ? AND zeit_utc >= ? AND art = 'bogen_status'"
                           " AND text LIKE '%→ fertig'"),
        "nachrichten": z("SELECT count(*) FROM nachricht WHERE projekt_id = ? AND zeit_utc >= ?"),
    }
    aus["fragen_offen"] = con.execute("SELECT count(*) FROM frage WHERE projekt_id = ? AND an = 'entwickler' AND status = 'offen'"
                                      " AND kurz NOT LIKE 'GEPARKT%'", (pid,)).fetchone()[0]
    aus["highlights"] = [dict(r) for r in con.execute(
        "SELECT id, titel, agent FROM aufgabe WHERE projekt_id = ? AND status = 'fertig' AND fertig_utc >= ? ORDER BY fertig_utc DESC LIMIT 5",
        (pid, seit_utc))]
    return aus


def kurztext(z):
    """Zahlen als eine Zeile (für Push und Startseite)."""
    teile = [f"{z['erledigt']} erledigt", f"{z['laeufe']} Läufe", f"Prüfungen {z['gruen']} grün / {z['rot']} rot",
             f"{z['fragen_neu']} neue Fragen ({z['fragen_offen']} offen)", f"{z['an_dich']} Nachrichten an dich"]
    if z["boegen_fertig"]:
        teile.insert(0, f"{z['boegen_fertig']} Bogen fertig")
    if z["beschluesse"]:
        teile.append(f"{z['beschluesse']} Beschlüsse")
    return " · ".join(teile)
