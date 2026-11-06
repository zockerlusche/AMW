"""Workbench-Oberfläche: kleiner HTTP-Server nur auf 127.0.0.1 (→ doc/architektur.md).

Liefert eine Seite (workbench.html) und eine JSON-Schnittstelle. Läuft als Faden im amw-dienst oder allein:
  python -X utf8 -m amw.workbench [--port 8780]
Sicherheit (Stufe 1): nur 127.0.0.1; Schreibwege nur mit dem Sitzungs-Schlüssel der Seite (X-AMW-Token, bei jedem
Serverstart neu) und passendem Host/Origin; nur parametrisierte Abfragen; die Seite setzt Text nur über textContent.
Schreibt ausschließlich über kern (als „Entwickler“).
"""
import argparse
import datetime
import json
import re
import os
import secrets
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import aktionen, db, kern
from .betrieb import speicher_frei_gb, speicher_grenze

STANDARD_PORT = 8780
HIER = os.path.dirname(os.path.abspath(__file__))


def zeilen(cur):
    return [dict(r) for r in cur.fetchall()]


# --- Lesen ---------------------------------------------------------------------------------------

def altbestand_bis(con, pid):
    """Letzte Nachricht aus dem alten Bus (Übernahme); offene Empfänge davor zählen als Altbestand."""
    e = json.loads(con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()[0] or "{}")
    return int(e.get("altbestand_bis", 0))


AUFGABE_IN_TEXT = re.compile(r"\bA(\d{3,5})\b")


def gerade(con, pid, kennung, sitzung_taetigkeit=None):
    """Was der Agent gerade macht: eigene Angabe (amw taetigkeit), sonst laufende Aufgabe, sonst die Aufgabe aus
    seiner letzten Meldung (Nummer oder A1234 im Text). Rückgabe: (text, aufgabe_id, quelle)."""
    if sitzung_taetigkeit:
        return sitzung_taetigkeit, None, "angabe"
    a = con.execute("SELECT id, titel FROM aufgabe WHERE projekt_id = ? AND agent = ? AND status = 'laeuft'"
                    " ORDER BY begonnen_utc DESC LIMIT 1", (pid, kennung)).fetchone()
    if a:
        return f"A{a['id']} · {a['titel']}", a["id"], "aufgabe"
    m = con.execute("SELECT aufgabe_id, kurz FROM nachricht WHERE projekt_id = ? AND von = ? ORDER BY id DESC LIMIT 1",
                    (pid, kennung)).fetchone()
    if m:
        aid = m["aufgabe_id"] or (int(AUFGABE_IN_TEXT.search(m["kurz"] or "").group(1)) if AUFGABE_IN_TEXT.search(m["kurz"] or "") else None)
        t = con.execute("SELECT titel FROM aufgabe WHERE projekt_id = ? AND id = ?", (pid, aid)).fetchone() if aid else None
        if t:
            return f"A{aid} · {t['titel']}", aid, "meldung"
    return None, None, None


def _naechster_test(con, pid):
    from . import termine
    try:
        return termine.naechster_test(con, pid)
    except Exception:                    # Termine dürfen die Startseite nie verhindern
        return None


def daten_themen(con, pid):
    from . import themen
    return themen.liste(con, pid)


def daten_thema(con, pid, tid):
    from . import dokumente, themen
    s = themen.seite(con, pid, int(tid) if str(tid).isdigit() else tid)
    for d in s["dokumente"]:
        d["vorschau"] = dokumente.FORMATE.get(d["endung"], ("", "", "download"))[2]
    return s


def daten_listen(con, pid):
    """Arbeitslisten je Agent in Reihenfolge und der Pool (Workbench › Aufgaben › Listen, auch online)."""
    from . import arbeitsliste
    agenten = []
    for g in con.execute("SELECT kennung, rolle FROM agent WHERE projekt_id = ? ORDER BY id", (pid,)).fetchall():
        l = arbeitsliste.liste(con, pid, g["kennung"])
        if l:
            agenten.append({"kennung": g["kennung"], "rolle": g["rolle"],
                            "liste": [{k: x[k] for k in ("id", "pos", "titel", "status", "gruende", "wartet_auf", "rang")} for x in l]})
    agenten.sort(key=lambda a: (a["rolle"] != "lead", (a["rolle"] or "~").casefold()))
    eigene = arbeitsliste.liste(con, pid, kern.ENTWICKLER)          # „Deine Aufgaben“ – die Liste des Entwicklers zuerst
    if eigene:
        agenten.insert(0, {"kennung": kern.ENTWICKLER, "rolle": "entwickler", "name": kern.entwickler_name(con, pid),
                           "liste": [{k: x[k] for k in ("id", "pos", "titel", "status", "gruende", "wartet_auf", "rang")} for x in eigene]})
    return {"agenten": agenten, "pool": [{k: x[k] for k in ("id", "titel", "status", "agent", "einstufung")}
                                          for x in arbeitsliste.pool(con, pid)]}


VERWEIS = re.compile(r"\b([FDB])(\d{1,6})(?:\s*[–-]\s*\1?(\d{1,6}))?\b")


def verweise(*texte):
    """F/D/B-Nummern aus Titel und Auftrag, auch Bereiche „D94–D101“ (höchstens 30 je Bereich)."""
    aus = {"F": [], "D": [], "B": []}
    for m in VERWEIS.finditer(" ".join(t or "" for t in texte)):
        a = int(m.group(2))
        b = int(m.group(3)) if m.group(3) and 0 < int(m.group(3)) - a <= 30 else a
        for n in range(a, b + 1):
            if n not in aus[m.group(1)]:
                aus[m.group(1)].append(n)
    return aus


def fragen_stand(con, pid, aid, titel, auftrag):
    """Fragen zu einer Aufgabe (verknüpft, als Wartegrund oder im Text genannt) mit Stand – für Karte und Ansicht."""
    ids = verweise(titel, auftrag)["F"]
    ids += [r[0] for r in con.execute("SELECT id FROM frage WHERE projekt_id = ? AND aufgabe_id = ?", (pid, aid))]
    ids += [int(r[0][1:]) for r in con.execute("SELECT bezug FROM wartegrund WHERE aufgabe_id = ? AND bezug LIKE 'F%'", (aid,))
            if r[0][1:].isdigit()]
    aus = []
    for fid in dict.fromkeys(ids):
        f = con.execute("SELECT id, kurz, status, antwort_art, antwort, antwort_utc, geparkt_utc FROM frage WHERE id = ? AND projekt_id = ?",
                        (fid, pid)).fetchone()
        if f:
            aus.append(dict(f))
    return aus


def daten_aufgabe(con, pid, aid):
    """Eine Aufgabe ganz: Auftrag, Stand, Wartegründe, Verlauf, Fragen, Dokumente, Beschlüsse, Läufe, Prüfungen."""
    a = con.execute("SELECT a.*, b.titel AS bogen_titel FROM aufgabe a LEFT JOIN bogen b ON b.id = a.bogen_id"
                    " WHERE a.id = ? AND a.projekt_id = ?", (int(aid), pid)).fetchone()
    if not a:
        raise LookupError(f"A{aid} gibt es nicht")
    a = dict(a)
    from . import dokumente
    v = verweise(a["titel"], a["auftrag"])
    a["zustaendig"] = kern.zustaendig(con, pid, a["id"])
    a["wartegruende"] = zeilen(con.execute("SELECT art, bezug, angelegt_utc, angelegt_von, erledigt_utc, erledigt_durch FROM wartegrund"
                                           " WHERE aufgabe_id = ? ORDER BY id", (a["id"],)))
    a["fragen"] = fragen_stand(con, pid, a["id"], a["titel"], a["auftrag"])
    a["verlauf"] = list(reversed(zeilen(con.execute(        # die letzten 30 Nachrichten dazu, älteste zuerst
        "SELECT id, zeit_utc, von, art, kurz, substr(text, 1, 3000) AS text FROM nachricht WHERE projekt_id = ? AND aufgabe_id = ?"
        " ORDER BY id DESC LIMIT 30", (pid, a["id"])))))
    dok = zeilen(con.execute(
        "SELECT d.id, d.titel, d.art, d.online, v.endung FROM dokument d JOIN dokument_version v ON v.dokument_id = d.id"
        " AND v.nr = (SELECT max(nr) FROM dokument_version WHERE dokument_id = d.id) WHERE d.projekt_id = ? AND d.status != 'geloescht'"
        " AND ((d.bezug_art = 'aufgabe' AND d.bezug_id = ?) OR d.id IN (SELECT value FROM json_each(?))) ORDER BY d.id",
        (pid, a["id"], json.dumps(v["D"]))))
    for d in dok:
        d["vorschau"] = dokumente.FORMATE.get(d["endung"], ("", "", "download"))[2]
    a["dokumente"] = dok
    a["beschluesse"] = zeilen(con.execute(
        "SELECT id, stichwort, regel, status FROM beschluss WHERE projekt_id = ? AND (id IN (SELECT value FROM json_each(?))"
        " OR (',' || replace(replace(replace(coalesce(aufgabe_ids, ''), ' ', ''), '[', ''), ']', '') || ',') LIKE ?) ORDER BY id", (pid, json.dumps(v["B"]), f"%,{a['id']},%")))
    a["laeufe"] = zeilen(con.execute("SELECT id, agent, status, beschreibung, rc, start_utc, ende_utc FROM lauf WHERE aufgabe_id = ?"
                                     " ORDER BY id DESC LIMIT 10", (a["id"],)))
    a["pruefungen"] = zeilen(con.execute("SELECT id, pruefer, ergebnis, sha, bemerkung, ergebnis_utc FROM pruefung WHERE aufgabe_id = ?"
                                         " ORDER BY id DESC LIMIT 10", (a["id"],)))
    a["fuer_dich"] = a["agent"] == kern.ENTWICKLER
    return a


# Was jede Sicht zeigt – ändert sich hier etwas (neue Zeile, neuer Stand), zeichnet die Workbench die offene Sicht neu.
# Start und Betrieb laden ohnehin alle 15 s; Einstellungen nie von selbst (dort tippt man). Kind-Tabellen über ihr Projekt.
_STAND_QUELLEN = {
    "frage": "frage WHERE projekt_id = :p",
    "frage_verlauf": "frage_verlauf x JOIN frage f ON f.id = x.frage_id WHERE f.projekt_id = :p",
    "aufgabe": "aufgabe WHERE projekt_id = :p",
    "abhaengigkeit": "abhaengigkeit x JOIN aufgabe a ON a.id = x.nach WHERE a.projekt_id = :p",
    "pruefung": "pruefung WHERE projekt_id = :p",
    "lauf": "lauf WHERE projekt_id = :p",
    "bogen": "bogen WHERE projekt_id = :p",
    "spezifikation": "spezifikation x JOIN bogen b ON b.id = x.bogen_id WHERE b.projekt_id = :p",
    "risiko": "risiko WHERE projekt_id = :p",
    "rueckblick": "rueckblick WHERE projekt_id = :p",
    "plan_ereignis": "plan_ereignis WHERE projekt_id = :p",
    "termin": "termin WHERE projekt_id = :p",
    "nachricht": "nachricht WHERE projekt_id = :p",
    "beschluss": "beschluss WHERE projekt_id = :p",
    "regel": "regel WHERE projekt_id = :p",
    "wortlaut": "wortlaut WHERE projekt_id = :p",
    "notiz": "notiz WHERE projekt_id = :p",
    "thema": "thema WHERE projekt_id = :p",
    "thema_fassung": "thema_fassung x JOIN thema t ON t.id = x.thema_id WHERE t.projekt_id = :p",
    "dokument": "dokument WHERE projekt_id = :p",
    "dokument_version": "dokument_version x JOIN dokument d ON d.id = x.dokument_id WHERE d.projekt_id = :p",
    "release": "release WHERE projekt_id = :p",
}
STAND_SICHTEN = {
    "fragen": ("frage", "frage_verlauf", "dokument"),
    "arbeit": ("aufgabe", "abhaengigkeit", "frage", "pruefung", "lauf"),
    "planung": ("bogen", "aufgabe", "abhaengigkeit", "spezifikation", "risiko", "rueckblick", "plan_ereignis", "termin", "frage"),
    "verlauf": ("nachricht", "aufgabe", "lauf", "pruefung", "beschluss"),
    "wissen": ("beschluss", "regel", "wortlaut", "notiz", "thema", "thema_fassung"),
    "dokumente": ("dokument", "dokument_version"),
    "releases": ("release",),
}


def stand_je_sicht(con, pid):
    """Änderungs-Stempel je Sicht: jüngste Änderung und Anzahl der Zeilen ihrer Tabellen (Anzahl: auch Löschen zählt)."""
    teile = {t: con.execute(f"SELECT coalesce(max({'x.' if ' x ' in q else ''}geaendert_utc), '') || '/' || count(*) FROM {q}",
                            {"p": pid}).fetchone()[0] for t, q in _STAND_QUELLEN.items()}
    return {s: ";".join(teile[t] for t in tabellen) for s, tabellen in STAND_SICHTEN.items()}


def daten_start(con, pid):
    alt = altbestand_bis(con, pid)
    agenten = zeilen(con.execute(
        "SELECT g.kennung, g.rolle, g.soll, g.grenzen, s.zustand, s.letzter_puls_utc, s.gestartet_utc, s.taetigkeit,"
        " s.taetigkeit_utc, s.ereignis, s.ereignis_text, s.ereignis_utc, s.kontext_prozent, s.limit_5h, s.limit_5h_reset_utc, s.limit_7t, s.limit_7t_reset_utc, s.kosten_usd, s.modell, s.denkstufe, s.status_utc,"
        " (SELECT count(*) FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id JOIN nachricht_art k ON k.art = n.art"
        "   WHERE e.agent = g.kennung AND n.projekt_id = g.projekt_id AND e.status = 'offen' AND n.id > :alt"
        "   AND " + kern.WECKT_SQL + ") AS offen,"       # nur was weckt (Sammel-Infos zählen nicht)
        " (SELECT count(*) FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id"
        "   WHERE e.agent = g.kennung AND n.projekt_id = g.projekt_id AND e.status = 'offen' AND n.id <= :alt) AS offen_alt,"
        " (SELECT kurz FROM nachricht WHERE projekt_id = g.projekt_id AND von = g.kennung ORDER BY id DESC LIMIT 1) AS zuletzt,"
        " (SELECT zeit_utc FROM nachricht WHERE projekt_id = g.projekt_id AND von = g.kennung ORDER BY id DESC LIMIT 1) AS zuletzt_utc"
        " FROM agent g LEFT JOIN sitzung s ON s.id = (SELECT max(id) FROM sitzung WHERE agent_id = g.id)"
        " WHERE g.projekt_id = :p ORDER BY g.id", {"p": pid, "alt": alt}))
    for a in agenten:
        from . import arbeitsliste                                        # Arbeitsliste: Länge und was in Arbeit ist
        l = arbeitsliste.liste(con, pid, a["kennung"])
        a["liste_n"], a["liste_lauf"] = len(l), next((x["pos"] for x in l if x["status"] == "laeuft"), None)
        boegen, gefuehrt = kern.fuehrt(con, pid, a["kennung"])          # Federführung auf der Kachel
        a["fuehrt"] = [f"B{b['id']}" for b in boegen] + [f"A{x['id']}" for x in gefuehrt]
        a["gerade"], a["gerade_aufgabe"], a["gerade_quelle"] = gerade(con, pid, a["kennung"],
                                                                      a["taetigkeit"] if a["zustand"] == "aktiv" else None)
        a["wartet"] = [{"aufgabe": r["aufgabe_id"], "auf": r["auf"]} for r in con.execute(   # Wartegründe auf der Kachel
            "SELECT w.aufgabe_id, group_concat(w.bezug, ', ') AS auf FROM wartegrund w JOIN aufgabe x ON x.id = w.aufgabe_id"
            " WHERE x.projekt_id = ? AND x.agent = ? AND x.status IN ('wartet', 'blockiert') AND x.einstufung = 'aktiv'"
            " AND w.erledigt_utc IS NULL GROUP BY w.aufgabe_id ORDER BY w.aufgabe_id LIMIT 2", (pid, a["kennung"]))]
    # nach Rolle geordnet: Lead zuerst, gleiche Rollen nebeneinander, sonst in der angelegten Reihenfolge
    agenten.sort(key=lambda a: (a["rolle"] != "lead", (a["rolle"] or "~").casefold()))
    fragen = zeilen(con.execute(           # nachtraege: ungelesene Nachträge im Verlauf der Frage (stehen dort, nicht doppelt)
        "SELECT f.id, f.kurz, f.von, f.zeit_utc, f.blockiert, (SELECT count(*) FROM frage_verlauf v JOIN empfang e"
        "   ON e.nachricht_id = v.nachricht_id AND e.agent = :e AND e.status = 'offen' WHERE v.frage_id = f.id) AS nachtraege"
        " FROM frage f WHERE f.projekt_id = :p AND f.an = 'entwickler' AND f.status = 'offen' AND f.geparkt_utc IS NULL"
        " ORDER BY f.blockiert DESC, f.id DESC LIMIT 20", {"p": pid, "e": kern.ENTWICKLER}))
    an_dich = zeilen(con.execute(           # ohne Nachträge zu offenen Fragen – die zeigt die Frage selbst (geparkte nicht)
        "SELECT n.id, n.zeit_utc, n.von, n.art, n.kurz, n.text, n.antwort_auf FROM empfang e JOIN nachricht n"
        " ON n.id = e.nachricht_id WHERE n.projekt_id = ? AND e.agent = ? AND e.status != 'erledigt'"
        " AND n.id NOT IN (SELECT v.nachricht_id FROM frage_verlauf v JOIN frage f ON f.id = v.frage_id"
        "   WHERE f.status = 'offen' AND f.geparkt_utc IS NULL AND v.nachricht_id IS NOT NULL)"
        " ORDER BY n.id DESC LIMIT 30", (pid, kern.ENTWICKLER)))
    halte = [dict(s) for s in kern.aktive_sperren(con, pid, art="halt")]
    zaehler = dict(con.execute(
        "SELECT"
        " (SELECT count(*) FROM frage WHERE projekt_id = :p AND an = 'entwickler' AND status = 'offen'"
        "   AND geparkt_utc IS NULL) AS fragen,"
        " (SELECT count(*) FROM aufgabe WHERE projekt_id = :p AND status IN ('wartet','laeuft','blockiert')"
        "   AND einstufung IN ('aktiv','keine_prio')) AS offen,"
        " (SELECT count(*) FROM aufgabe WHERE projekt_id = :p AND einstufung = 'geparkt'"
        "   AND status NOT IN ('fertig','verworfen')) AS geparkt,"
        " (SELECT count(*) FROM beschluss WHERE projekt_id = :p AND status = 'gilt') AS beschluesse,"
        " (SELECT count(*) FROM regel WHERE projekt_id = :p) AS regeln,"
        " (SELECT count(*) FROM release WHERE projekt_id = :p) AS releases", {"p": pid}).fetchone())
    frei, gesamt = speicher_frei_gb()
    zaehler["an_dich"] = len(an_dich)
    from . import planung
    try:
        planung_wartet = planung.freigaben_offen(con, pid)
        for a in planung_wartet["eigene"]:            # Fragen dazu (im Titel/Auftrag genannt): „alle beantwortet“ auf der Karte
            f = fragen_stand(con, pid, a["id"], a["titel"], a.get("auftrag"))
            a["fragen_n"], a["fragen_offen"] = len(f), sum(1 for x in f if x["status"] == "offen")
            a.pop("auftrag", None)
    except Exception:
        planung_wartet = {"spezifikationen": [], "plaene": [], "eigene": []}
    zaehler["freigaben"] = sum(len(v) for v in planung_wartet.values())
    from . import __version__, hook, ueberwachung
    try:
        unangemeldet = hook.unangemeldet(con, pid)     # laufende Agenten-Sitzungen, die der Wächter nicht wecken kann
    except Exception:
        unangemeldet = []
    try:
        warnungen = ueberwachung.warnungen(con, pid)   # Server aus, Weckruf unbeantwortet, Lauf überfällig
    except Exception:
        warnungen = []
    from . import schirm
    sz = schirm.zustand(con)
    sz["laeufe"] = zeilen(con.execute("SELECT id, agent, status, beschreibung FROM lauf WHERE projekt_id = ? AND schirm = 1"
                                      " AND status IN ('laeuft', 'angemeldet') ORDER BY id", (pid,)))
    return {"version": __version__, "agenten": agenten, "fragen": fragen, "an_dich": an_dich, "halt": halte, "zaehler": zaehler,
            "unangemeldet": unangemeldet, "warnungen": warnungen, "planung_wartet": planung_wartet, "schirm": sz,
            "naechster_test": _naechster_test(con, pid), "stand": stand_je_sicht(con, pid),
            "speicher": {"frei": frei, "gesamt": gesamt}, "zeit": db.jetzt()}


def daten_planung(con, pid):
    """Ansicht „Planung“: Leitbild, Bögen mit Fortschritt/Prognose/Spezifikation, Schritte in Wellen, Risiken,
    Plan-Check, Status (Ampel je Dimension), was auf den Menschen wartet, Planungs-Protokoll."""
    from . import planung, verlauf
    prog = planung.prognose(con, pid, laeufe=600)
    boegen = planung.boegen(con, pid)
    from . import termine
    termin_liste = termine.vorkommen(con, pid, tage=28, mit_vergangenen_h=24)
    for b in boegen:
        b["prognose"] = prog["boegen"].get(b["id"])
        b["specs"] = {s["teil"]: {k: s[k] for k in ("status", "version", "kommentar", "text", "geaendert_utc", "geschrieben_von")}
                      for s in con.execute("SELECT * FROM spezifikation WHERE bogen_id = ?", (b["id"],))}
        b["klaerungen"] = zeilen(con.execute("SELECT id, kurz, status, fundstellen FROM frage WHERE projekt_id = ? AND fundstellen LIKE ?",
                                             (pid, f"bogen:{b['id']}:%")))
        schritte = zeilen(con.execute(
            "SELECT id, titel, agent, status, einstufung, rang, kriterien, schaetzung_h, komplexitaet, plan_status, verantwortlich,"
            " anforderungen, zusammenfassung, fertig_utc FROM aufgabe WHERE bogen_id = ? ORDER BY rang, id", (b["id"],)))
        welle = planung.wellen(con, [s["id"] for s in schritte])
        for s in schritte:
            s["welle"] = welle.get(s["id"], 1)
            s["vorgaenger"] = planung.vorgaenger(con, s["id"])
            s["blockiert_durch"] = planung.offene_vorgaenger(con, s["id"]) if s["status"] not in ("fertig", "verworfen") else []
            s["kriterien"] = planung._json(s["kriterien"], [])
            s["prognose"] = prog["schritte"].get(s["id"])
        b["schritte"] = schritte
        b["rueckblick"] = verlauf.rueckblicke(con, pid, b["id"])
        b["dokumente"] = con.execute("SELECT count(*) FROM dokument WHERE projekt_id = ? AND bezug_art = 'bogen' AND bezug_id = ?"
                                     " AND status = 'aktuell'", (pid, b["id"])).fetchone()[0]
        for s in schritte:
            s["dokumente"] = con.execute("SELECT count(*) FROM dokument WHERE projekt_id = ? AND bezug_art = 'aufgabe'"
                                         " AND bezug_id = ? AND status = 'aktuell'", (pid, s["id"])).fetchone()[0]
        b["beginn_ist"] = (con.execute("SELECT min(coalesce(begonnen_utc, fertig_utc)) FROM aufgabe WHERE bogen_id = ?"
                                       " AND status != 'verworfen'", (b["id"],)).fetchone()[0] or "")[:10] or None   # Übersicht
    return {"termine": termin_liste, "leitbild": planung.leitbild(con, pid), "boegen": boegen, "risiken": planung.risiken(con, pid),
            "pruefung": planung.pruefen(con, pid, prog, mit_akzeptierten=True), "status": planung.status(con, pid, prog),
            "check_texte": {k: {"wer": v[1], "ziel": v[2], **v[3]} for k, v in planung.CHECKS.items()}, "lead": kern.lead(con, pid),
            "wartet": planung.freigaben_offen(con, pid), "heute": datetime.date.today().isoformat(),   # lokales Datum für die Heute-Linie
            "ereignisse": zeilen(con.execute("SELECT zeit_utc, von, art, bogen_id, aufgabe_id, text FROM plan_ereignis"
                                             " WHERE projekt_id = ? AND art != 'aufgabe_abschluss' ORDER BY id DESC LIMIT 80",
                                             (pid,)))}


def daten_verlauf(con, pid, q):
    """Verlauf der letzten `tage` Tage (1–14, Vorgabe 3); gefiltert wird auf der Seite (geht so auch online)."""
    from . import verlauf
    try:
        tage = max(1, min(14, int(q.get("tage", ["3"])[0])))
    except ValueError:
        tage = 3
    # ab lokaler Mitternacht (in UTC umgerechnet) – ein sekundengenauer Start änderte den Inhalt bei jedem Abgleich
    tag = datetime.date.today() - datetime.timedelta(days=tage - 1)
    ab = datetime.datetime.combine(tag, datetime.time.min).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"tage": tage, "ab": ab, "ereignisse": verlauf.verlauf(con, pid, ab, grenze=2500),
            "agenten": [r[0] for r in con.execute("SELECT kennung FROM agent WHERE projekt_id = ? ORDER BY id", (pid,))]}


def daten_seit(con, pid, q):
    """Zusammenfassung seit dem letzten Besuch (Zeitpunkt kommt von der Seite)."""
    from . import verlauf
    ab = q.get("ab", [""])[0]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", ab):
        raise LookupError("ab")
    return verlauf.zusammenfassung(con, pid, ab)


def daten_push(con):
    """Push-Einstellungen ohne Geheimnisse und das Versandprotokoll (nur am PC; nicht im Online-Spiegel)."""
    from . import push
    return {"einstellungen": push.oeffentlich(), "protokoll": push.protokoll(con, 30), "ereignisse": list(push.EREIGNISSE)}


def daten_einstellungen(con, pid, speicher=None):
    """Zahnrad: alles, was einstellbar ist – nie Schlüssel oder Passwörter (der Turso-Schlüssel nur als „gespeichert“)."""
    from . import __version__, abgleich, einstellungen, ueberwachung
    p = con.execute("SELECT name, einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    pe = json.loads(p["einstellungen"] or "{}")
    from .betrieb import SPEICHER_GRENZE_GB
    from .dienst import TAKT_MIN
    agenten = zeilen(con.execute("SELECT kennung, rolle, soll, grenzen, empfaengt_rund, puls_grenze_s, ordner, zusatzordner,"
                                 " denkstufe, modell, startsatz, rechte, fernsteuerung, neustart_auto FROM agent"
                                 " WHERE projekt_id = ? ORDER BY id", (pid,)))
    for a in agenten:
        try:
            a["zusatzordner"] = json.loads(a["zusatzordner"] or "[]")
        except ValueError:
            a["zusatzordner"] = []
    try:
        with open(abgleich.zugang_pfad(), encoding="utf-8") as f:
            z = json.load(f)
    except (OSError, ValueError):
        z = {}
    sp = speicher or abgleich.speicher_aus_zugang(nur_wenn_an=False)
    try:
        web = abgleich.web_einstellungen(sp) if sp else None
    except (OSError, ValueError, KeyError):
        web = None
    return {"version": __version__,
            "projekt": {"name": p["name"], "takt_min": pe.get("takt_min", TAKT_MIN),
                        "speicher_grenze_gb": pe.get("speicher_grenze_gb", SPEICHER_GRENZE_GB),
                        "stillstand_min": pe.get("stillstand_min", ueberwachung.STILLSTAND_MIN),
                        "lauf_ohne_angabe_min": pe.get("lauf_ohne_angabe_min", ueberwachung.LAUF_OHNE_ANGABE_MIN),
                        "entwickler_name": pe.get("entwickler_name", ""), "farbe": kern.projekt_wahl(con, pid, "farbe"),
                        "dateien_online": kern.projekt_wahl(con, pid, "dateien_online")},
            "agenten": agenten,
            "pc": {**einstellungen.laden(), "datei": einstellungen.pfad()},
            "turso": {"url": z.get("url", ""), "abgleich": bool(z.get("abgleich")), "schluessel_gespeichert": bool(z.get("token"))},
            "web": web, "web_grenzen": {k: [lo, hi] for k, (_, lo, hi) in abgleich.WEB_EINSTELLUNGEN.items()}}


def daten_agent(con, pid, kennung):
    """Klick auf die Kachel: was macht er, was kommt noch, was liegt bei ihm."""
    a = con.execute("SELECT g.kennung, g.rolle, g.soll, g.grenzen, s.zustand, s.letzter_puls_utc, s.gestartet_utc,"
                    " s.ereignis, s.ereignis_text, s.ereignis_utc, s.kontext_prozent, s.limit_5h, s.limit_5h_reset_utc, s.limit_7t, s.limit_7t_reset_utc, s.kosten_usd, s.modell, s.denkstufe, s.status_utc, s.taetigkeit, s.taetigkeit_utc, s.claude_sitzung FROM agent g LEFT JOIN sitzung s ON s.id = (SELECT max(id) FROM sitzung WHERE agent_id = g.id)"
                    " WHERE g.projekt_id = ? AND g.kennung = ?", (pid, kennung)).fetchone()
    if not a:
        raise LookupError(kennung)
    alt = altbestand_bis(con, pid)
    text, aid, quelle = gerade(con, pid, kennung, a["taetigkeit"] if a["zustand"] == "aktiv" else None)
    from . import gespraech, steuerung
    try:
        steuern = {"profil": steuerung.profil(con, pid, kennung), "prozess_laeuft": steuerung.laeuft(con, pid, kennung),
                   "fortsetzbar": bool(steuerung.letzte_sitzung(con, pid, kennung))}
    except Exception:                      # z. B. ohne Windows-API (Tests anderswo) – Anzeige geht trotzdem
        steuern = {}
    try:                                   # „In Claude öffnen“: laufende Sitzung mit Fernsteuerung
        steuern["claude_link"] = gespraech.link(a["claude_sitzung"]) if a["zustand"] == "aktiv" else None
    except Exception:
        steuern["claude_link"] = None
    return {
        **{k: v for k, v in dict(a).items() if k != "claude_sitzung"}, **steuern, "gerade": text, "gerade_aufgabe": aid, "gerade_quelle": quelle,
        "naechste": zeilen(con.execute(
            "SELECT id, titel, status, einstufung, rang, wartet_auf FROM aufgabe WHERE projekt_id = ? AND agent = ?"
            " AND status IN ('laeuft','wartet','blockiert') AND einstufung IN ('aktiv','keine_prio')"
            " AND id != coalesce(?, -1) ORDER BY CASE status WHEN 'laeuft' THEN 0 WHEN 'wartet' THEN 1 ELSE 2 END, rang, id LIMIT 8",
            (pid, kennung, aid))),
        "meldungen": zeilen(con.execute(
            "SELECT id, zeit_utc, art, kurz FROM nachricht WHERE projekt_id = ? AND von = ? ORDER BY id DESC LIMIT 5", (pid, kennung))),
        "an_ihn": zeilen(con.execute(
            "SELECT n.id, n.zeit_utc, n.von, n.art, n.kurz FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id"
            " WHERE n.projekt_id = ? AND e.agent = ? AND e.status = 'offen' AND n.id > ? ORDER BY n.id DESC LIMIT 8",
            (pid, kennung, alt))),
        "offen_alt": con.execute("SELECT count(*) FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id WHERE n.projekt_id = ?"
                                 " AND e.agent = ? AND e.status = 'offen' AND n.id <= ?", (pid, kennung, alt)).fetchone()[0],
        "laeufe": zeilen(con.execute(
            "SELECT id, beschreibung, status, coalesce(start_utc, angemeldet_utc) AS start_utc, aufgabe_id FROM lauf WHERE projekt_id = ? AND agent = ?"
            " AND status IN ('angemeldet','laeuft') ORDER BY id DESC", (pid, kennung))),
        "pruefungen": zeilen(con.execute(
            "SELECT id, aufgabe_id, zweig, sha, bauer, pruefer, angefragt_utc FROM pruefung WHERE projekt_id = ?"
            " AND ergebnis = 'offen' AND (pruefer = ? OR bauer = ?) ORDER BY id DESC LIMIT 8", (pid, kennung, kennung))),
    }


def daten_gespraech(con, pid, q):
    from . import gespraech
    zahl = lambda k: int(q[k][0]) if q.get(k, [""])[0].isdigit() else None
    return gespraech.daten(con, pid, q.get("kennung", [""])[0], q.get("sitzung", [""])[0] or None, vor=zahl("vor"), ab=zahl("ab"))


def daten_agenten_alle(con, pid):
    return {r["kennung"]: daten_agent(con, pid, r["kennung"])
            for r in con.execute("SELECT kennung FROM agent WHERE projekt_id = ? AND soll != 'aus'", (pid,))}


def vorgeschichte(con, pid, f):
    v = []
    if f["aufgabe_id"]:
        a = con.execute("SELECT id, titel, status, agent, bemerkung FROM aufgabe WHERE id = ?", (f["aufgabe_id"],)).fetchone()
        if a:
            v.append({"art": "aufgabe", "ref": f"A{a['id']}", "titel": a["titel"],
                      "text": (a["bemerkung"] or "")[-900:], "zusatz": f"{a['status']} · {a['agent'] or '–'}"})
    vor, tiefe = f["folge_von"], 0
    while vor and tiefe < 5:
        p = con.execute("SELECT id, kurz, antwort, folge_von FROM frage WHERE id = ?", (vor,)).fetchone()
        if not p:
            break
        v.append({"art": "frage", "ref": f"F{p['id']}", "titel": p["kurz"], "text": p["antwort"] or "(offen)"})
        vor, tiefe = p["folge_von"], tiefe + 1
    muster = [f"%Frage {f['id']}%", f"%F{f['id']} %", f"%F-{f['id']}%"]
    for b in con.execute("SELECT id, zeit_utc, stichwort, regel FROM beschluss WHERE projekt_id = ? AND"
                         " (regel LIKE ? OR regel LIKE ? OR regel LIKE ? OR quelle LIKE ?) ORDER BY id DESC LIMIT 5",
                         (pid, *muster, muster[0])):
        v.append({"art": "beschluss", "ref": f"B{b['id']}", "titel": b["stichwort"], "text": b["regel"][:600],
                  "zeit": b["zeit_utc"]})
    bedingung = "kurz LIKE ? OR kurz LIKE ? OR kurz LIKE ?"
    par = list(muster)
    if f["aufgabe_id"]:
        bedingung += " OR aufgabe_id = ?"
        par.append(f["aufgabe_id"])
    for n in con.execute(f"SELECT id, zeit_utc, von, kurz FROM nachricht WHERE projekt_id = ? AND ({bedingung})"
                         " ORDER BY id DESC LIMIT 6", (pid, *par)):
        v.append({"art": "nachricht", "ref": f"#{n['id']}", "titel": n["kurz"], "text": n["von"], "zeit": n["zeit_utc"]})
    return v


def haelt(con, pid, f):
    """Welche Aufgaben diese Frage aufhält: Wartegründe auf F…, sonst die Aufgabe einer blockierenden Frage."""
    aus = zeilen(con.execute(
        "SELECT a.id, a.agent, a.titel, min(w.angelegt_utc) AS seit FROM wartegrund w JOIN aufgabe a ON a.id = w.aufgabe_id"
        " WHERE w.projekt_id = ? AND w.art = 'frage' AND w.bezug = ? AND w.erledigt_utc IS NULL"
        " AND a.status IN ('wartet', 'blockiert') GROUP BY a.id ORDER BY a.id", (pid, f"F{f['id']}")))
    if f["blockiert"] and f["aufgabe_id"] and not any(x["id"] == f["aufgabe_id"] for x in aus):
        a = con.execute("SELECT id, agent, titel, status FROM aufgabe WHERE id = ?", (f["aufgabe_id"],)).fetchone()
        if a and a["status"] not in ("fertig", "verworfen"):
            aus.append({"id": a["id"], "agent": a["agent"], "titel": a["titel"], "seit": f["zeit_utc"]})
    return aus


def daten_fragen(con, pid, alle=False):
    from . import dokumente
    sql = "SELECT * FROM frage WHERE projekt_id = ? AND an = 'entwickler' AND status = 'offen'"
    if not alle:
        sql += " AND geparkt_utc IS NULL"
    aus = []
    for f in con.execute(sql + " ORDER BY geparkt_utc IS NOT NULL, blockiert DESC, id DESC LIMIT 80", (pid,)).fetchall():
        d = dict(f)
        d["optionen"] = json.loads(f["optionen"] or "[]")
        d["vorgeschichte"] = vorgeschichte(con, pid, f)
        d["verlauf"] = zeilen(con.execute("SELECT zeit_utc, von, art, text FROM frage_verlauf WHERE frage_id = ?"
                                          " ORDER BY id", (f["id"],)))
        d["wartet_auf_fragesteller"] = bool(d["verlauf"]) and d["verlauf"][-1]["art"] == "rueckfrage"
        d["haelt"] = haelt(con, pid, f)
        d["dokumente"] = zeilen(con.execute(
            "SELECT d.id, d.titel, d.art, d.online, v.endung FROM dokument d JOIN dokument_version v ON v.dokument_id = d.id AND v.nr ="
            " (SELECT max(nr) FROM dokument_version WHERE dokument_id = d.id) WHERE d.projekt_id = ? AND d.bezug_art = 'frage'"
            " AND d.bezug_id = ? AND d.status = 'aktuell' ORDER BY d.id", (pid, f["id"])))
        for x in d["dokumente"]:
            x["vorschau"] = dokumente.FORMATE.get(x["endung"], ("", "", "download"))[2]
        # Varianten: Dokument an einer Option (amw frage neu --anhang A=…) – auch eins, das woanders hängt
        for o in d["optionen"]:
            if o.get("dokument"):
                x = next((x for x in d["dokumente"] if x["id"] == o["dokument"]), None) or (zeilen(con.execute(
                    "SELECT d.id, d.titel, d.art, d.online, v.endung FROM dokument d JOIN dokument_version v ON v.dokument_id = d.id"
                    " AND v.nr = (SELECT max(nr) FROM dokument_version WHERE dokument_id = d.id) WHERE d.id = ? AND d.projekt_id = ?"
                    " AND d.status != 'geloescht'", (o["dokument"], pid))) or [None])[0]
                if x:
                    x["vorschau"] = dokumente.FORMATE.get(x["endung"], ("", "", "download"))[2]
                o["anhang"] = x
        varianten = {o["dokument"] for o in d["optionen"] if o.get("anhang")}
        d["dokumente"] = [x for x in d["dokumente"] if x["id"] not in varianten]
        aus.append(d)
    return aus


def daten_aufgaben(con, pid, q):
    sql = ("SELECT id, titel, agent, status, einstufung, rang, wartet_auf, angelegt_utc, fertig_utc, geaendert_utc FROM aufgabe"
           " WHERE projekt_id = ?")
    par = [pid]
    sicht = q.get("sicht", ["offen"])[0]
    if sicht == "offen":
        sql += " AND status IN ('wartet','laeuft','blockiert') AND einstufung IN ('aktiv','keine_prio')"
    elif sicht == "geparkt":
        sql += " AND einstufung = 'geparkt' AND status NOT IN ('fertig','verworfen')"
    elif sicht == "pool":
        sql += " AND einstufung = 'pool' AND status NOT IN ('fertig','verworfen')"
    elif sicht == "erledigt":
        sql += " AND status IN ('fertig','verworfen')"
    if q.get("agent", [""])[0]:
        sql += " AND agent = ?"
        par.append(q["agent"][0])
    if q.get("q", [""])[0]:
        sql += " AND (titel LIKE ? OR bemerkung LIKE ?)"
        par += [f"%{q['q'][0]}%"] * 2
    ordnung = " ORDER BY fertig_utc DESC" if sicht == "erledigt" else " ORDER BY rang, id DESC"
    liste = zeilen(con.execute(sql + ordnung + " LIMIT 400", par))
    if sicht == "offen":                    # „läuft jetzt“: woran ein Agent mit laufender Sitzung gerade arbeitet
        jetzt = aktuelle_aufgaben(con, pid)
        for x in liste:
            x["jetzt"] = jetzt.get(x["id"])
    return liste


def aktuelle_aufgaben(con, pid):
    """Aufgabe → Agent, an der eine laufende Sitzung gerade arbeitet (Tätigkeit mit A1234, laufende Aufgabe, letzte Meldung).
    Agenten setzen den Aufgaben-Status selten auf „läuft“; so bleibt die Spalte trotzdem nicht leer."""
    erg = {}
    for a in con.execute("SELECT g.kennung, s.taetigkeit FROM agent g JOIN sitzung s ON s.agent_id = g.id AND s.zustand = 'aktiv'"
                         " WHERE g.projekt_id = ?", (pid,)).fetchall():
        aid = None
        m = AUFGABE_IN_TEXT.search(a["taetigkeit"] or "")
        if m:
            aid = int(m.group(1))
        else:
            aid = gerade(con, pid, a["kennung"])[1]
        if aid:
            erg.setdefault(aid, a["kennung"])
    return erg


def daten_wissen(con, pid, q):
    such = q.get("q", [""])[0].strip()
    muster = f"%{such}%"
    if such:
        b = con.execute("SELECT id, zeit_utc, thema, stichwort, regel, quelle, status FROM beschluss WHERE projekt_id = ?"
                        " AND (stichwort LIKE ? OR regel LIKE ?) ORDER BY id DESC LIMIT 80", (pid, muster, muster))
        w = con.execute("SELECT id, zeit_utc, text, kanal FROM wortlaut WHERE projekt_id = ? AND text LIKE ?"
                        " ORDER BY id DESC LIMIT 80", (pid, muster))
    else:
        b = con.execute("SELECT id, zeit_utc, thema, stichwort, regel, quelle, status FROM beschluss WHERE projekt_id = ?"
                        " AND status = 'gilt' ORDER BY id DESC LIMIT 60", (pid,))
        w = con.execute("SELECT id, zeit_utc, text, kanal FROM wortlaut WHERE projekt_id = ? ORDER BY id DESC LIMIT 60",
                        (pid,))
    r = con.execute("SELECT ebene, nr, teil, text, stand_utc FROM regel WHERE projekt_id = ?"
                    + (" AND text LIKE ?" if such else "") + " ORDER BY ebene, nr", (pid, muster) if such else (pid,))
    n = con.execute("SELECT schluessel, wert, geaendert_utc FROM notiz WHERE projekt_id = ?"
                    + (" AND (schluessel LIKE ? OR wert LIKE ?)" if such else "") + " ORDER BY schluessel",
                    (pid, muster, muster) if such else (pid,))
    z = lambda sql, *par: con.execute(sql, (pid, *par)).fetchone()[0]
    anzahl = {"themen": z("SELECT count(*) FROM thema WHERE projekt_id = ?"),       # alle, nicht nur die gezeigten
              "beschluesse": z("SELECT count(*) FROM beschluss WHERE projekt_id = ? AND (stichwort LIKE ? OR regel LIKE ?)",
                               muster, muster) if such else z("SELECT count(*) FROM beschluss WHERE projekt_id = ? AND status = 'gilt'"),
              "wortlaut": z("SELECT count(*) FROM wortlaut WHERE projekt_id = ? AND text LIKE ?", muster) if such
              else z("SELECT count(*) FROM wortlaut WHERE projekt_id = ?")}
    return {"beschluesse": zeilen(b), "wortlaut": zeilen(w), "regeln": zeilen(r), "notizen": zeilen(n), "anzahl": anzahl}


def daten_suche(con, pid, q):
    such = q.get("q", [""])[0].strip()
    if len(such) < 2:
        return []
    m = f"%{such}%"
    teile = [
        ("aufgabe", "SELECT 'A' || id AS ref, titel AS titel, status AS zusatz, angelegt_utc AS zeit FROM aufgabe"
                    " WHERE projekt_id = ? AND (titel LIKE ? OR bemerkung LIKE ?)", 3),
        ("beschluss", "SELECT 'B' || id, stichwort, status, zeit_utc FROM beschluss WHERE projekt_id = ?"
                      " AND (stichwort LIKE ? OR regel LIKE ?)", 3),
        ("frage", "SELECT 'F' || id, kurz, status, zeit_utc FROM frage WHERE projekt_id = ? AND (kurz LIKE ? OR antwort LIKE ?)", 3),
        ("wortlaut", "SELECT 'W' || id, substr(text, 1, 200), kanal, zeit_utc FROM wortlaut WHERE projekt_id = ? AND text LIKE ?", 2),
        ("nachricht", "SELECT '#' || id, kurz, von, zeit_utc FROM nachricht WHERE projekt_id = ? AND (kurz LIKE ? OR text LIKE ?)", 3),
        ("dokument", "SELECT 'D' || d.id, d.titel, d.art, d.angelegt_utc FROM dokument d WHERE d.projekt_id = ? AND d.status != 'geloescht'"
                     " AND (d.titel LIKE ? OR EXISTS (SELECT 1 FROM dokument_version v WHERE v.dokument_id = d.id AND v.suchtext LIKE ?))", 3),
    ]
    aus = []
    for art, sql, n in teile:
        for r in con.execute(sql + " ORDER BY 4 DESC LIMIT 25", (pid, *[m] * (n - 1))):
            aus.append({"art": art, "ref": r[0], "titel": r[1], "zusatz": r[2], "zeit": r[3]})
    return aus


def daten_dokumente(con, pid, q):
    """Bereich „Dokumente“: Liste mit Filtern (Art, Bezug, Agent, Suche, Status) und was es zum Filtern gibt."""
    from . import dokumente, planung
    w = lambda k: (q.get(k, [""])[0] or "").strip() or None
    status = w("status") or "aktuell"
    liste = dokumente.liste(con, pid, w("art"), w("bezug_art"), int(w("bezug_id")) if (w("bezug_id") or "").isdigit() else None,
                            w("von"), w("q"), None if status == "alle" else status)
    for d in liste:
        d.pop("sha256", None)
    zahl = lambda sql: {r[0]: r[1] for r in con.execute(sql, (pid,))}
    return {"dokumente": liste, "arten": zahl("SELECT art, count(*) FROM dokument WHERE projekt_id = ? AND status = 'aktuell' GROUP BY art"),
            "von": zahl("SELECT angelegt_von, count(*) FROM dokument WHERE projekt_id = ? AND status = 'aktuell' GROUP BY angelegt_von"),
            "archiviert": con.execute("SELECT count(*) FROM dokument WHERE projekt_id = ? AND status = 'archiviert'", (pid,)).fetchone()[0],
            "boegen": [{"id": b["id"], "titel": b["titel"]} for b in planung.boegen(con, pid)]}


def daten_dokument(con, pid, q, gespraech=None):
    """Ein Dokument: Versionen, Gespräch, wozu es gehört; bei Text-Formaten der Inhalt der gewählten Version.
    `gespraech`: schon geholt (der Abgleich holt die Gespräche aller Dokumente auf einmal)."""
    from . import dokumente
    did = int(q.get("id", ["0"])[0] or 0)
    d = dokumente.dokument(con, pid, did)
    for v in d["versionen"]:
        v.pop("sha256", None)
    d["gespraech"] = dokumente.gespraech(con, pid, did) if gespraech is None else gespraech
    if d["bezug_art"]:
        spalte = {"bogen": "titel", "aufgabe": "titel", "frage": "kurz", "beschluss": "stichwort"}[d["bezug_art"]]
        r = con.execute(f"SELECT {spalte} FROM {d['bezug_art']} WHERE id = ?", (d["bezug_id"],)).fetchone()
        d["bezug_titel"] = r[0] if r else None
    nr = int(q.get("v", ["0"])[0] or 0) or d["versionen"][-1]["nr"]
    v = next((x for x in d["versionen"] if x["nr"] == nr), d["versionen"][-1])
    d["gezeigt"] = v["nr"]
    from . import ki
    d["ki_herkunft"] = [{k: h[k] for k in ("nr", "ki", "ki_version", "modell", "modell_lizenz", "modelle", "vorlage", "prompt",
                                           "negativ", "seed", "lauf_id", "dauer_s", "vram_spitze_gb", "gegenprobe", "zeit_utc")}
                        for h in ki.herkunft_von(con, pid, did)]
    if v["vorschau"] == "text" and d["status"] != "geloescht":
        roh, _ = dokumente.inhalt(con, pid, did, v["nr"])
        d["text"] = roh.decode("utf-8", errors="replace")
    return d


def daten_projekte(con, pid):
    """Projekt-Auswahl: alle Projekte dieser AMW mit dem, was man ohne Wechsel sehen will (offene Fragen an den
    Entwickler, Halt). Umschalten ändert nur die Ansicht (doc/plan-projektwahl.md)."""
    from . import einstellungen
    aus = []
    for p in con.execute("SELECT id, uid, name, einstellungen, angelegt_utc FROM projekt ORDER BY id").fetchall():
        z = con.execute(
            "SELECT (SELECT count(*) FROM frage WHERE projekt_id = :p AND an = 'entwickler' AND status = 'offen'"
            "  AND geparkt_utc IS NULL) AS fragen,"
            " (SELECT count(*) FROM agent WHERE projekt_id = :p) AS agenten", {"p": p["id"]}).fetchone()
        aus.append({"uid": p["uid"], "name": p["name"], "farbe": kern.projekt_wahl(con, p["id"], "farbe"),
                    "fragen": z["fragen"], "agenten": z["agenten"], "seit": p["angelegt_utc"], "aktiv": p["id"] == pid,
                    "halt": bool(kern.aktive_sperren(con, p["id"], art="halt"))})
    rechner = einstellungen.wert("rechner")
    for e in aus:
        e["rechner"] = rechner
    # Projekte anderer Rechner: aus dem Verzeichnis im Online-Speicher (der Abgleich liest es mit); öffnen = Online-Seite
    from . import abgleich, push
    link = (push.laden().get("link") or "").rstrip("/")
    eigene = {e["uid"] for e in aus}
    grenze = time.time() - 7 * 86400
    for f in abgleich.VERZEICHNIS["projekte"]:
        if f["uid"] in eigene:
            continue
        try:
            gesehen = datetime.datetime.strptime(f["gesehen_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp()
        except (TypeError, ValueError):
            gesehen = 0
        aus.append({"uid": f["uid"], "name": f["name"], "farbe": f["farbe"] or "bernstein", "fragen": int(f["fragen"] or 0),
                    "agenten": int(f["agenten"] or 0), "halt": bool(int(f["halt"] or 0)), "aktiv": False, "fern": True,
                    "rechner": f["rechner"], "erreichbar": gesehen > grenze,
                    "online": f"{link}/?projekt={f['uid']}" if link.startswith("https://") else ""})
    return {"projekte": aus, "rechner": rechner}


def daten_betrieb(con, pid):
    sitz = zeilen(con.execute(
        "SELECT g.kennung, s.zustand, s.gestartet_utc, s.letzter_puls_utc, s.beendet_utc FROM sitzung s"
        " JOIN agent g ON g.id = s.agent_id WHERE g.projekt_id = ? ORDER BY s.id DESC LIMIT 30", (pid,)))
    laeufe = zeilen(con.execute("SELECT id, agent, beschreibung, status, angemeldet_utc, start_utc, ende_utc, rc, gpu"
                                " FROM lauf WHERE projekt_id = ? ORDER BY id DESC LIMIT 30", (pid,)))
    # Grafikkarte und Schirm gibt es auf dem PC nur einmal: was ein anderes Projekt dort gerade belegt (ohne Inhalt)
    fremd = zeilen(con.execute("SELECT p.name AS projekt, l.gpu, l.schirm, l.start_utc FROM lauf l JOIN projekt p"
                               " ON p.id = l.projekt_id WHERE l.projekt_id != ? AND l.status = 'laeuft'"
                               " AND (l.gpu = 1 OR l.schirm = 1)", (pid,)))
    sperren = [dict(s) for s in kern.aktive_sperren(con, pid)]
    server = zeilen(con.execute("SELECT name, port, zustand, seit_utc, geprueft_utc, zustaendig, neustart, ausfaelle,"
                                " letzter_neustart_utc FROM server WHERE projekt_id = ? AND aktiv = 1 ORDER BY name", (pid,)))
    logdatei = os.path.join(os.path.dirname(db.db_pfad()), "dienst.log")
    log = []
    if os.path.exists(logdatei):
        with open(logdatei, encoding="utf-8", errors="replace") as f:
            log = f.readlines()[-25:]
    frei, gesamt = speicher_frei_gb()
    from . import statusline
    from . import ki
    return {"sitzungen": sitz, "laeufe": laeufe, "fremd": fremd, "sperren": sperren, "server": server,
            "log": [z.rstrip() for z in log],
            "verbrauch": statusline.verbrauch_tage(con, pid, 7), "ki": ki.uebersicht(con, pid),
            "speicher": {"frei": frei, "gesamt": gesamt, "grenze": speicher_grenze(con, pid)}, "db": db.db_pfad()}


def daten_releases(con, pid):
    return zeilen(con.execute("SELECT id, art, version, zeit_utc, commit_sha, titel, text_intern, aufgaben,"
                              " veroeffentlicht_utc FROM release WHERE projekt_id = ? ORDER BY zeit_utc DESC LIMIT 200",
                              (pid,)))


# --- Server --------------------------------------------------------------------------------------

def baue_handler(port, token):
    with open(os.path.join(HIER, "workbench.html"), encoding="utf-8") as f:
        seite = f.read().replace("__AMW_TOKEN__", token).encode("utf-8")
    erlaubt = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        server_version = "amw-workbench"

        def log_message(self, *args):
            pass

        def _senden(self, code, daten, typ="application/json; charset=utf-8"):
            body = daten if isinstance(daten, bytes) else json.dumps(daten, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", typ)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            if typ.startswith("text/html"):
                self.send_header("Content-Security-Policy",
                                 "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline';"
                                 " connect-src 'self'; img-src 'self' data: blob:; frame-src 'self'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(body)

        def _datei(self, q):
            """Datei eines Dokuments. HTML (Mockup) und SVG laufen abgeschottet (CSP sandbox, eigener Ursprung) – sie
            kommen nicht an die Seite und ihr Token heran; Office nur als Download."""
            from . import dokumente
            try:
                con = db.verbinde(nur_lesen=True)
                try:
                    roh, endung = dokumente.inhalt(con, self._projekt(con, q), int(q.get("id", ["0"])[0] or 0),
                                                   int(q.get("v", ["0"])[0] or 0) or None)
                finally:
                    con.close()
            except (kern.AmwFehler, ValueError) as e:
                return self._senden(404, {"fehler": str(e)})
            _, typ, vorschau = dokumente.FORMATE[endung]
            self.send_response(200)
            self.send_header("Content-Type", typ)
            self.send_header("Content-Length", str(len(roh)))
            self.send_header("Cache-Control", "private, max-age=3600")   # Inhalt je Version unveränderlich
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "SAMEORIGIN")
            self.send_header("Referrer-Policy", "no-referrer")
            if vorschau == "mockup":
                self.send_header("Content-Security-Policy", "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline';"
                                 " style-src 'unsafe-inline'; img-src data: blob:; font-src data:; media-src data: blob:")
            elif vorschau != "pdf":
                self.send_header("Content-Security-Policy", "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:")
            name = f"D{q.get('id', ['0'])[0]}{endung}"
            self.send_header("Content-Disposition", f'{"attachment" if vorschau == "download" else "inline"}; filename="{name}"')
            self.end_headers()
            self.wfile.write(roh)

        def _projekt(self, con, q):
            name = q.get("projekt", [""])[0]
            if name:
                return db.projekt_id(con, name)
            return con.execute("SELECT min(id) FROM projekt").fetchone()[0]

        def do_GET(self):
            if self.headers.get("Host") not in erlaubt:
                return self._senden(403, {"fehler": "Host"})
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path in ("/", "/index.html"):
                return self._senden(200, seite, "text/html; charset=utf-8")
            if u.path == "/api/dokument/datei":
                return self._datei(q)
            wege = {"/api/start": lambda c, p: daten_start(c, p),
                    "/api/fragen": lambda c, p: daten_fragen(c, p, q.get("alle", ["0"])[0] == "1"),
                    "/api/aufgaben": lambda c, p: daten_aufgaben(c, p, q),
                    "/api/listen": lambda c, p: daten_listen(c, p),
                    "/api/themen": lambda c, p: daten_themen(c, p),
                    "/api/thema": lambda c, p: daten_thema(c, p, q.get("id", ["0"])[0]),
                    "/api/aufgabe": lambda c, p: daten_aufgabe(c, p, q.get("id", ["0"])[0] or 0),
                    "/api/wissen": lambda c, p: daten_wissen(c, p, q),
                    "/api/suche": lambda c, p: daten_suche(c, p, q),
                    "/api/betrieb": lambda c, p: daten_betrieb(c, p),
                    "/api/releases": lambda c, p: daten_releases(c, p),
                    "/api/einstellungen": lambda c, p: daten_einstellungen(c, p),
                    "/api/agent": lambda c, p: daten_agent(c, p, q.get("kennung", [""])[0]),
                    "/api/gespraech": lambda c, p: daten_gespraech(c, p, q),
                    "/api/push": lambda c, p: daten_push(c),
                    "/api/planung": lambda c, p: daten_planung(c, p),
                    "/api/verlauf": lambda c, p: daten_verlauf(c, p, q),
                    "/api/seit": lambda c, p: daten_seit(c, p, q),
                    "/api/dokumente": lambda c, p: daten_dokumente(c, p, q),
                    "/api/dokument": lambda c, p: daten_dokument(c, p, q),
                    "/api/projekte": lambda c, p: daten_projekte(c, p)}
            weg = wege.get(u.path)
            if not weg:
                return self._senden(404, {"fehler": "unbekannt"})
            try:
                con = db.verbinde(nur_lesen=True)
                try:
                    return self._senden(200, weg(con, self._projekt(con, q)))
                finally:
                    con.close()
            except LookupError:
                return self._senden(404, {"fehler": "unbekannt"})
            except kern.AmwFehler as e:
                return self._senden(409, {"fehler": str(e)})
            except Exception as e:
                return self._senden(500, {"fehler": f"{type(e).__name__}: {e}"})

        def do_POST(self):
            herkunft = self.headers.get("Origin")
            if self.headers.get("Host") not in erlaubt or (herkunft and herkunft.split("//", 1)[-1] not in erlaubt):
                return self._senden(403, {"fehler": "nicht erlaubt"})
            if self.headers.get("X-AMW-Token") != token:     # meist: Seite stammt von vor einem Neustart der Workbench
                return self._senden(403, {"fehler": "nicht erlaubt", "neu_laden": True})
            try:
                laenge = min(int(self.headers.get("Content-Length") or 0), 3_000_000)   # Text berichtigen bis 400 000 Zeichen
                daten = json.loads(self.rfile.read(laenge) or b"{}")
            except ValueError:
                return self._senden(400, {"fehler": "JSON"})
            u = urlparse(self.path)
            q = parse_qs(u.query)
            try:
                con = db.verbinde()
                try:
                    return self._senden(200, aktionen.ausfuehren(con, self._projekt(con, q), u.path, daten))
                except aktionen.Ungueltig as e:
                    return self._senden(400, {"fehler": str(e)})
                except LookupError:
                    return self._senden(404, {"fehler": "unbekannt"})
                finally:
                    con.close()
            except kern.AmwFehler as e:
                return self._senden(409, {"fehler": str(e)})
            except Exception as e:
                return self._senden(500, {"fehler": f"{type(e).__name__}: {e}"})

    return Handler


class Server(ThreadingHTTPServer):
    """Ohne SO_REUSEADDR: unter Windows ließe es den Port eines anderen Programms mitbenutzen – die Workbench liefe
    dann still „neben“ einem fremden Server, und der Browser sähe den fremden. Belegter Port → OSError beim Start."""
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def starten(port=STANDARD_PORT, im_hintergrund=True):
    token = secrets.token_urlsafe(24)
    srv = Server(("127.0.0.1", port), baue_handler(port, token))
    srv.daemon_threads = True
    if im_hintergrund:
        threading.Thread(target=srv.serve_forever, name="workbench", daemon=True).start()
    return srv


def main(argv=None):
    p = argparse.ArgumentParser(prog="amw-workbench")
    p.add_argument("--port", type=int, default=STANDARD_PORT)
    a = p.parse_args(argv)
    srv = starten(a.port, im_hintergrund=False)
    print(f"Workbench: http://127.0.0.1:{a.port}/  ({db.db_pfad()})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
