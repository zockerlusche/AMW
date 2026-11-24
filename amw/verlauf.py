"""Rückblick und Verlauf (Stufe F, → doc/ausbau.md §7).

- Rückblick je Bogen: „Was lief gut / was nicht / was ändern wir / was haben wir gelernt“. Eine Maßnahme wird mit einem
  Schritt zur Aufgabe oder (Lead/Entwickler) zum Beschluss – der Bezug bleibt erhalten.
- Verlauf: eine Zeitleiste aus den vorhandenen Daten (Nachrichten, Erledigtes, Läufe, Prüfungen, Fragen, Beschlüsse,
  Planung, Sitzungen) – nichts wird doppelt erfasst.
- Zusammenfassung seit einem Zeitpunkt („Seit du weg warst“, täglicher Push-Rückblick): nur Zahlen.
- Projektweg (A2024, TH164 „Verlauf“): „wer hat was getan“ – Mensch, AMW, Planer, Prüfer, Agent – mit Uhrzeit und Text über
  den ganzen Weg, älteste zuerst (projektweg). Was die AMW schon festhält (Themen, Gegenlesen, Planer, Freigaben und
  Abnahmen der Meilensteine), wird gelesen, nicht doppelt gespeichert; was keine eigene Stelle hat, speichert ereignis()
  als plan_ereignis art „protokoll“ (Text als JSON {"rolle", "text"}) – keine neue Tabelle.
"""
import datetime
import json
import re

from . import db, kern

ARTEN = ("gut", "schlecht", "massnahme", "gelernt")
VERLAUF_ARTEN = ("nachricht", "erledigt", "lauf", "pruefung", "frage", "beschluss", "plan", "sitzung", "dokument")

PROTOKOLL = "protokoll"                         # plan_ereignis.art der eigens gespeicherten Ereignisse im Projektweg
ROLLEN = ("mensch", "amw", "planer", "pruefer", "agent")
_VON_VORGABE = {"mensch": kern.ENTWICKLER, "amw": "AMW", "planer": "Planer", "pruefer": "Prüfer"}   # Agent: Kennung Pflicht
_ZEIT = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
# Was die AMW im Projektweg schon festhält: art → (feste Rolle oder None = nach „von“, Text). {t} Thema, {f} Fassung,
# {m} Meilenstein-Nummer, {x} Zusatz aus dem Ereignis.
WEG_ARTEN = {
    "thema_vorgelegt": (None, "TH{t} Fassung {f} vorgelegt"),
    "thema_bearbeitet": (None, "TH{t} bearbeitet (Fassung {f})"),
    "thema_freigegeben": (None, "TH{t} freigegeben"),
    "thema_zurueck": (None, "TH{t} zurückgegeben"),
    "thema_ja": (None, "TH{t}: Ja"),
    "thema_loeschen_markiert": (None, "TH{t} zum Löschen markiert"),
    "thema_markierung_aufgehoben": (None, "TH{t}: Löschmarkierung aufgehoben"),
    "thema_gegenlesen": ("amw", "TH{t} Fassung {f}: Gegenlesen angestoßen"),
    "thema_gegengelesen": ("pruefer", "TH{t} Fassung {f} gegengelesen"),
    "thema_planer": ("amw", "TH{t} Fassung {f}: Planer angestoßen"),
    "thema_planentwurf": ("planer", "TH{t} Fassung {f}: {x}"),
    "thema_plan_ja": (None, "TH{t}: Plan angenommen"),
    "thema_nichts_zu_bauen": (None, "TH{t}: nichts zu bauen"),
    "konzept_uebernommen": (None, "Konzept übernommen"),
    "meilenstein_frei": (None, "M{m}: {x} freigegeben"),
    "meilenstein_ja": (None, "M{m}: Ja zu {x}"),
    "abschluss_bericht": ("amw", "M{m}: Abschlussbericht vorbereitet"),
}


def ereignis(con, pid, rolle, text, von=None, aufgabe_id=None, bogen_id=None, zeit_utc=None):
    """Ein Ereignis im Projektweg speichern, das keine eigene Stelle in der AMW hat. rolle: mensch | amw | planer | pruefer |
    agent; von: wer genau (beim Agenten Pflicht, sonst Vorgabe je Rolle). Rückgabe: id des Eintrags."""
    if rolle not in ROLLEN:
        raise kern.AmwFehler("Rolle: " + " | ".join(ROLLEN))
    text = (text or "").strip()
    if not text:
        raise kern.AmwFehler("Text fehlt")
    von = (von or "").strip() or _VON_VORGABE.get(rolle)
    if not von:
        raise kern.AmwFehler("wer (von) fehlt – beim Agenten die Kennung")
    zeit_utc = zeit_utc or db.jetzt()
    if not _ZEIT.match(zeit_utc):
        raise kern.AmwFehler(f"Uhrzeit {zeit_utc!r}: Format JJJJ-MM-TTThh:mm:ssZ (UTC)")
    if aufgabe_id is not None and not con.execute("SELECT 1 FROM aufgabe WHERE id = ? AND projekt_id = ?",
                                                  (aufgabe_id, pid)).fetchone():
        raise kern.AmwFehler(f"Aufgabe {aufgabe_id} gibt es nicht")
    if bogen_id is not None and not con.execute("SELECT 1 FROM bogen WHERE id = ? AND projekt_id = ?", (bogen_id, pid)).fetchone():
        raise kern.AmwFehler(f"Meilenstein {bogen_id} gibt es nicht")
    with db.schreiben(con):
        return db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=zeit_utc, von=von, art=PROTOKOLL,
                            aufgabe_id=aufgabe_id, bogen_id=bogen_id,
                            text=json.dumps({"rolle": rolle, "text": text}, ensure_ascii=False))


def _rolle(von, fest=None):
    if fest:
        return fest
    if von == kern.ENTWICKLER:
        return "mensch"
    return "amw" if von == "AMW" else "agent"


def _json(text):
    try:
        d = json.loads(text or "{}")
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


FREIGABE_TEXT = {"grob": "Grobplan", "plan": "Feinplan", "abschluss": "Abschluss"}     # planansicht.ARTEN
ROLLE_TEXT = {"co": "Co-Entwickler", "lead": "Lead"}


def _weg_text(art, d, nr):
    fest, muster = WEG_ARTEN[art]
    x = ""
    if art == "thema_planentwurf":
        x = "Planer meldet einen Fehler" if d.get("fehler") else (
            "Planer: nichts zu bauen" if (d.get("entwurf") or {}).get("nichts_zu_bauen") else "Planentwurf liegt vor")
    elif art in ("meilenstein_frei", "meilenstein_ja"):
        x = FREIGABE_TEXT.get(d.get("art"), d.get("art") or "?")
    t = muster.format(t=d.get("thema", "?"), f=d.get("fassung", "?"), m=nr if nr is not None else "?", x=x)
    if art == "meilenstein_frei" and d.get("an") is False:
        t = t.replace(" freigegeben", ": Freigabe zurückgenommen")
    if art in ("thema_ja", "meilenstein_ja") and d.get("rolle"):
        t += f" ({ROLLE_TEXT.get(d['rolle'], d['rolle'])})"
    return fest, t


def projektweg(con, pid, ab_utc=None, bis_utc=None, rolle=None, grenze=2000):
    """Der ganze Projektweg (oder [ab_utc, bis_utc)) in zeitlicher Reihenfolge, älteste zuerst; gleiche Sekunde nach Eingang.
    Je Eintrag {"id", "zeit", "rolle", "von", "text", "art", "aufgabe_id", "bogen_id"}."""
    if rolle is not None and rolle not in ROLLEN:
        raise kern.AmwFehler("Rolle: " + " | ".join(ROLLEN))
    arten = (PROTOKOLL, *WEG_ARTEN)
    sql = ("SELECT e.id, e.zeit_utc, e.von, e.art, e.text, e.aufgabe_id, e.bogen_id, b.nr FROM plan_ereignis e"
           " LEFT JOIN bogen b ON b.id = e.bogen_id WHERE e.projekt_id = ? AND e.art IN (" + ", ".join("?" * len(arten)) + ")")
    par = [pid, *arten]
    for bed, wert in (("e.zeit_utc >= ?", ab_utc), ("e.zeit_utc < ?", bis_utc)):
        if wert is not None:
            sql += " AND " + bed
            par.append(wert)
    aus = []
    for r in con.execute(sql + " ORDER BY e.zeit_utc, e.id", par):
        d = _json(r["text"])
        if r["art"] == PROTOKOLL:
            ro, text = d.get("rolle") or _rolle(r["von"]), d.get("text") or (r["text"] or "")
        else:
            fest, text = _weg_text(r["art"], d, r["nr"])
            ro = _rolle(r["von"], fest)
        if rolle is None or ro == rolle:
            aus.append({"id": r["id"], "zeit": r["zeit_utc"], "rolle": ro, "von": r["von"], "text": text, "art": r["art"],
                        "aufgabe_id": r["aufgabe_id"], "bogen_id": r["bogen_id"]})
    return aus[-int(grenze):]


def rueckblick_neu(con, pid, von, bogen_id, art, text):
    if art not in ARTEN:
        raise kern.AmwFehler("Art: " + " | ".join(ARTEN))
    if not (text or "").strip():
        raise kern.AmwFehler("Text fehlt")
    if bogen_id is not None and not con.execute("SELECT 1 FROM bogen WHERE id = ? AND projekt_id = ?", (bogen_id, pid)).fetchone():
        raise kern.AmwFehler(f"Meilenstein {bogen_id} gibt es nicht")
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
    herkunft = f"Rückblick {rid}" + (f" zu Meilenstein {r['bogen_id']}" if r["bogen_id"] else "")
    if als == "aufgabe":
        aid = kern.aufgabe_neu(con, pid, von, r["text"][:200], agent, auftrag=f"{r['text']}\n\n(aus {herkunft})", sofort=False)
        with db.schreiben(con):
            con.execute("UPDATE rueckblick SET aufgabe_id = ? WHERE id = ?", (aid, rid))
        return aid
    if als == "beschluss":
        from . import wissen
        bid = wissen.beschluss_neu(con, pid, von, r["text"][:120], r["text"], herkunft, thema="Lessons Learned",
                                   neues_thema=True)
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
        q.append(("SELECT fertig_utc, 'erledigt', coalesce((SELECT e.von FROM plan_ereignis e WHERE e.aufgabe_id = aufgabe.id"
                  " AND e.art = 'aufgabe_abschluss' ORDER BY e.id DESC LIMIT 1), agent, ''), 'A' || id, titel, status"
                  " FROM aufgabe WHERE projekt_id = ? AND status IN ('fertig', 'verworfen') AND fertig_utc >= ? AND fertig_utc < ?", p))
    if "lauf" in arten:
        q.append(("SELECT start_utc, 'lauf', agent, 'L' || id, beschreibung, 'start' FROM lauf WHERE projekt_id = ?"
                  " AND start_utc >= ? AND start_utc < ?", p))
        # vom Dienst gerechnet (A1640): wer, Befehl gekürzt, Ordner, rc stehen im Verlauf (TL D982)
        q.append(("SELECT ende_utc, 'lauf', agent, 'L' || id, beschreibung, status || ' rc ' || coalesce(rc, '–')"
                  " || CASE WHEN ausfuehrer = 'dienst' THEN ' · vom Dienst gerechnet: ' || substr(coalesce(befehl, ''), 1, 120)"
                  " || ' in ' || coalesce(ordner, '?') ELSE '' END FROM lauf"
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
                  " FROM plan_ereignis WHERE projekt_id = ? AND zeit_utc >= ? AND zeit_utc < ? AND art != 'aufgabe_abschluss'", p))
    if "sitzung" in arten:
        q.append(("SELECT s.gestartet_utc, 'sitzung', a.kennung, 'S' || s.id, 'Sitzung gestartet', 'start' FROM sitzung s"
                  " JOIN agent a ON a.id = s.agent_id WHERE a.projekt_id = ? AND s.gestartet_utc >= ? AND s.gestartet_utc < ?", p))
        q.append(("SELECT s.beendet_utc, 'sitzung', a.kennung, 'S' || s.id, 'Sitzung beendet', 'ende' FROM sitzung s"
                  " JOIN agent a ON a.id = s.agent_id WHERE a.projekt_id = ? AND s.beendet_utc >= ? AND s.beendet_utc < ?", p))
    if "dokument" in arten:
        q.append(("SELECT v.zeit_utc, 'dokument', v.von, 'D' || d.id, d.titel, CASE WHEN v.nr = 1 THEN d.art ELSE 'v' || v.nr END"
                  " FROM dokument_version v JOIN dokument d ON d.id = v.dokument_id WHERE d.projekt_id = ? AND v.zeit_utc >= ?"
                  " AND v.zeit_utc < ?", p))
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
                                      " AND geparkt_utc IS NULL", (pid,)).fetchone()[0]
    aus["highlights"] = [dict(r) for r in con.execute(
        "SELECT id, titel, agent FROM aufgabe WHERE projekt_id = ? AND status = 'fertig' AND fertig_utc >= ? ORDER BY fertig_utc DESC LIMIT 5",
        (pid, seit_utc))]
    return aus


SEIT_ARTEN = ("an_dich", "erledigt", "laeufe", "gruen", "rot", "fragen_neu", "beschluesse", "boegen_fertig")


def seit_daten(con, pid, tage=7):
    """Für die Online-Seite: Zeitpunkte je Art der letzten Tage – dort wird „seit deinem Besuch“ je Gerät gezählt
    (seit_zaehlen; dieselbe Rechnung macht web/api.php)."""
    # auf die volle Stunde: sonst ändert sich die Ansicht jede Sekunde und der Abgleich lädt sie jedes Mal hoch
    grenze = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=tage)).strftime("%Y-%m-%dT%H:00:00Z")
    q = {"an_dich": ("SELECT n.zeit_utc FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id WHERE n.projekt_id = ?"
                     " AND n.zeit_utc >= ? AND e.agent = ?", (kern.ENTWICKLER,)),
         "erledigt": ("SELECT fertig_utc FROM aufgabe WHERE projekt_id = ? AND status = 'fertig' AND fertig_utc >= ?", ()),
         "laeufe": ("SELECT ende_utc FROM lauf WHERE projekt_id = ? AND ende_utc >= ?", ()),
         "gruen": ("SELECT ergebnis_utc FROM pruefung WHERE projekt_id = ? AND ergebnis_utc >= ? AND ergebnis = 'gruen'", ()),
         "rot": ("SELECT ergebnis_utc FROM pruefung WHERE projekt_id = ? AND ergebnis_utc >= ? AND ergebnis = 'rot'", ()),
         "fragen_neu": ("SELECT zeit_utc FROM frage WHERE projekt_id = ? AND zeit_utc >= ? AND an = 'entwickler'", ()),
         "beschluesse": ("SELECT angelegt_utc FROM beschluss WHERE projekt_id = ? AND angelegt_utc >= ?", ()),
         "boegen_fertig": ("SELECT zeit_utc FROM plan_ereignis WHERE projekt_id = ? AND zeit_utc >= ? AND art = 'bogen_status'"
                           " AND text LIKE '%→ fertig'", ())}
    ereignisse = sorted([r[0], art] for art, (sql, extra) in q.items() for r in con.execute(sql, (pid, grenze, *extra)))
    hl = [dict(r) for r in con.execute(
        "SELECT id, titel, agent, fertig_utc AS zeit FROM aufgabe WHERE projekt_id = ? AND status = 'fertig' AND fertig_utc >= ?"
        " ORDER BY fertig_utc DESC LIMIT 30", (pid, grenze))]
    offen = con.execute("SELECT count(*) FROM frage WHERE projekt_id = ? AND an = 'entwickler' AND status = 'offen'"
                        " AND geparkt_utc IS NULL", (pid,)).fetchone()[0]
    return {"ab": grenze, "ereignisse": ereignisse, "highlights": hl, "fragen_offen": offen}


def seit_zaehlen(d, ab):
    """Gegenstück zu zusammenfassung() aus seit_daten (Referenz für web/api.php)."""
    aus = dict.fromkeys(SEIT_ARTEN, 0)
    for zeit, art in d["ereignisse"]:
        if zeit >= ab:
            aus[art] += 1
    aus["fragen_offen"] = d["fragen_offen"]
    aus["highlights"] = [{k: h[k] for k in ("id", "titel", "agent")} for h in d["highlights"] if h["zeit"] >= ab][:5]
    return aus


def kurztext(z):
    """Zahlen als eine Zeile (für Push und Startseite)."""
    teile = [f"{z['erledigt']} erledigt", f"{z['laeufe']} Läufe", f"Prüfungen {z['gruen']} grün / {z['rot']} rot",
             f"{z['fragen_neu']} neue Fragen ({z['fragen_offen']} offen)", f"{z['an_dich']} Nachrichten an dich"]
    if z["boegen_fertig"]:
        teile.insert(0, f"{z['boegen_fertig']} Meilenstein(e) fertig")
    if z["beschluesse"]:
        teile.append(f"{z['beschluesse']} Beschlüsse")
    return " · ".join(teile)
