"""Wissen und Projektführung: Wortlaut, Beschlüsse, Regeln, Notizen, Release Notes, Einstufung von Aufgaben.

Heute schreibt der TL das per SQL in den Bus (KR26); in der AMW geht es über diese Funktionen bzw. `amw`.
Regeln zeigen nur den gültigen Text; jede Regeländerung nennt den Beschluss, der sie begründet.
"""
import json
import math
import re

from . import db, kern


def _nur_lead(con, pid, von, was):
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler(f"{was} nur Entwickler und Lead")


def wortlaut_neu(con, pid, von, text, kanal, zeit_utc=None, bemerkung=None):
    _nur_lead(con, pid, von, "Wortlaut erfassen")
    if not text.strip():
        raise kern.AmwFehler("Wortlaut ist leer")
    with db.schreiben(con):
        t = db.jetzt()
        return db.einfuegen(con, "wortlaut", projekt_id=pid, zeit_utc=zeit_utc or t, text=text, kanal=kanal,
                            erfasst_von=von, erfasst_utc=t, bemerkung=bemerkung)


def beschluss_neu(con, pid, von, stichwort, regel, quelle, thema=None, zeit_utc=None, wortlaut_ids=None,
                  aufgabe_ids=None, ersetzt=None):
    """Neuer Beschluss; mit `ersetzt` wird der alte auf ueberholt gesetzt und verweist auf den neuen."""
    _nur_lead(con, pid, von, "Beschlüsse anlegen")
    with db.schreiben(con):
        t = db.jetzt()
        bid = db.einfuegen(con, "beschluss", projekt_id=pid, zeit_utc=zeit_utc or t, thema=thema, stichwort=stichwort,
                           regel=regel, quelle=quelle, wortlaut_ids=wortlaut_ids, aufgabe_ids=aufgabe_ids,
                           angelegt_von=von, angelegt_utc=t)
        if ersetzt:
            n = con.execute("UPDATE beschluss SET status = 'ueberholt', ersetzt_durch = ? WHERE id = ? AND projekt_id = ?",
                            (bid, ersetzt, pid)).rowcount
            if not n:
                raise kern.AmwFehler(f"B{ersetzt} gibt es nicht")
    return bid


def regel_setzen(con, pid, von, ebene, nr, text, beschluss_id, teil=None):
    """Regel anlegen oder an Ort und Stelle ändern. Ohne Beschluss keine Regeländerung (KR30 heute)."""
    _nur_lead(con, pid, von, "Regeln ändern")
    if ebene not in ("arbeit", "projekt"):
        raise kern.AmwFehler("Ebene ist arbeit oder projekt")
    with db.schreiben(con):
        if not con.execute("SELECT 1 FROM beschluss WHERE id = ? AND projekt_id = ?", (beschluss_id, pid)).fetchone():
            raise kern.AmwFehler(f"B{beschluss_id} gibt es nicht – erst den Beschluss anlegen")
        projekt = None if ebene == "arbeit" else pid
        t = db.jetzt()
        alt = con.execute("SELECT id FROM regel WHERE ebene = ? AND coalesce(projekt_id, 0) = ? AND nr = ?",
                          (ebene, projekt or 0, nr)).fetchone()
        if alt:
            con.execute("UPDATE regel SET text = ?, teil = coalesce(?, teil), beleg = ?, stand_utc = ? WHERE id = ?",
                        (text, teil, f"B{beschluss_id}", t, alt["id"]))
            return "geändert"
        db.einfuegen(con, "regel", ebene=ebene, projekt_id=projekt, nr=nr, teil=teil, text=text,
                     beleg=f"B{beschluss_id}", stand_utc=t)
        return "angelegt"


def notiz_setzen(con, pid, von, schluessel, wert):
    _nur_lead(con, pid, von, "Notizen pflegen")
    with db.schreiben(con):
        if con.execute("SELECT 1 FROM notiz WHERE projekt_id = ? AND schluessel = ?", (pid, schluessel)).fetchone():
            con.execute("UPDATE notiz SET wert = ? WHERE projekt_id = ? AND schluessel = ?", (wert, pid, schluessel))
            return "geändert"
        db.einfuegen(con, "notiz", projekt_id=pid, schluessel=schluessel, wert=wert)
        return "angelegt"


def notiz_entfernen(con, pid, von, schluessel, beschluss=None):
    """Veraltete Notizen löschen – nur der Lead oder mit einem geltenden Beschluss (wie Regeln ändern).
    Notizen sind gepflegter Stand, keine Geschichte: vorher sichern, der Beschluss nennt die Sicherung."""
    if not kern.ist_lead(con, pid, von):
        b = con.execute("SELECT status FROM beschluss WHERE projekt_id = ? AND id = ?", (pid, beschluss)).fetchone() if beschluss else None
        if not b or b["status"] != "gilt":
            raise kern.AmwFehler("Notizen entfernen dürfen nur Lead und Entwickler – oder mit --beschluss auf einen geltenden Beschluss")
    weg, fehlt = [], []
    with db.schreiben(con):
        for s in schluessel:
            n = con.execute("DELETE FROM notiz WHERE projekt_id = ? AND schluessel = ?", (pid, s)).rowcount
            (weg if n else fehlt).append(s)
    return weg, fehlt


def einstufen(con, pid, von, aid, einstufung):
    """aktiv | keine_prio | geparkt | pool. Parken stempelt Zeit und Person."""
    if einstufung not in ("aktiv", "keine_prio", "geparkt", "pool"):
        raise kern.AmwFehler("Einstufung ist aktiv, keine_prio, geparkt oder pool")
    with db.schreiben(con):
        kern._aufgabe_fuer_aenderung(con, pid, von, aid)
        if einstufung == "geparkt":
            con.execute("UPDATE aufgabe SET einstufung = 'geparkt', geparkt_utc = ?, geparkt_von = ? WHERE id = ?",
                        (db.jetzt(), von, aid))
        else:
            con.execute("UPDATE aufgabe SET einstufung = ? WHERE id = ?", (einstufung, aid))


def release_merge(con, pid, von, titel, commit_sha, text=None, aufgaben=None):
    """Eine Zeile je Merge (damit zwischen zwei Pushes nichts verloren geht). Version bleibt leer bis release_version."""
    with db.schreiben(con):
        return db.einfuegen(con, "release", projekt_id=pid, art="merge", zeit_utc=db.jetzt(), commit_sha=commit_sha,
                            titel=titel, text_intern=text, aufgaben=aufgaben, eingetragen_von=von)


def release_version(con, pid, von, version, titel, commit_sha=None, text=None):
    """Fasst alle offenen Merge-Zeilen zu einer Version zusammen."""
    _nur_lead(con, pid, von, "Versionen setzen")
    with db.schreiben(con):
        if con.execute("SELECT 1 FROM release WHERE projekt_id = ? AND art = 'version' AND version = ?",
                       (pid, version)).fetchone():
            raise kern.AmwFehler(f"Version {version} gibt es schon")
        merges = con.execute("SELECT id, titel, aufgaben FROM release WHERE projekt_id = ? AND art = 'merge'"
                             " AND version IS NULL ORDER BY id", (pid,)).fetchall()
        sammel = text or "\n".join(f"- {m['titel']}" for m in merges)
        aufg = ", ".join(m["aufgaben"] for m in merges if m["aufgaben"])
        rid = db.einfuegen(con, "release", projekt_id=pid, art="version", version=version, zeit_utc=db.jetzt(),
                           commit_sha=commit_sha, titel=titel, text_intern=sammel, aufgaben=aufg or None,
                           eingetragen_von=von)
        con.execute("UPDATE release SET version = ? WHERE projekt_id = ? AND art = 'merge' AND version IS NULL",
                    (version, pid))
    return rid, len(merges)


# --- Frage-Prüfung gegen die Datenbank (B2422) -----------------------------------------------------

STOPP = set("""aber alle alles also auch bevor bitte bleibt dabei damit dann dass dein deine denn diese dieser dieses
doch durch eine einem einen einer eines erst etwas euch gibt habe haben hast hier ihre immer jede jeder jetzt kann
kein keine machen mehr muss nach neue neuen nicht noch nur oder ohne schon sein seine sich sind soll sollen sollte
ueber über und unsere unter viel vom von vor wann warum was weil welche welcher wenn werden wieder wie wird wirklich
wollen zum zur zwei frage fragen marcel option variante ja nein gilt geht""".split())
TREFFER_MAX = 6


def _staemme(text):
    """Wörter ab 4 Zeichen, ohne Füllwörter, als Wortanfang (7 Zeichen) – grob, aber ohne Wörterbuch."""
    aus = []
    for w in re.findall(r"[0-9A-Za-zÄÖÜäöüß]{4,}", text or ""):
        w = w.lower()
        if w not in STOPP and not w.isdigit():
            aus.append(w[:7])
    return list(dict.fromkeys(aus))


def treffer(con, pid, text, grenze=TREFFER_MAX):
    """Passende geltende Beschlüsse, beantwortete Fragen und Regeln zu einem Fragetext. Seltene Wörter zählen mehr.
    Liste von {"ref", "titel", "antwort", "zeit"} – die besten zuerst."""
    staemme = _staemme(text)
    if not staemme:
        return []
    docs = []
    for r in con.execute("SELECT id, stichwort, regel, zeit_utc FROM beschluss WHERE projekt_id = ? AND status = 'gilt'", (pid,)):
        docs.append((f"B{r['id']}", r["stichwort"], r["regel"], r["zeit_utc"], f"{r['stichwort']} {r['regel']}"))
    for r in con.execute("SELECT id, kurz, worum, optionen, antwort_art, antwort, antwort_utc FROM frage WHERE projekt_id = ?"
                         " AND status = 'beantwortet'", (pid,)):
        antwort = r["antwort"] or ""
        if r["antwort_art"] == "option":
            antwort = next((f"{o['kenn']}) {o['text']}" for o in json.loads(r["optionen"] or "[]") if o["kenn"] == antwort), antwort)
        docs.append((f"F{r['id']}", r["kurz"], antwort, r["antwort_utc"], f"{r['kurz']} {r['worum'] or ''} {antwort}"))
    for r in con.execute("SELECT ebene, nr, text, stand_utc FROM regel WHERE ebene = 'arbeit' OR projekt_id = ?", (pid,)):
        docs.append((f"{'KR' if r['ebene'] == 'arbeit' else 'PR'}{r['nr']}", r["text"][:120], "", r["stand_utc"], r["text"]))
    if not docs:
        return []
    klein = [d[4].lower() for d in docs]
    gewicht = {}
    for st in staemme:
        df = sum(1 for k in klein if st in k)
        gewicht[st] = math.log(1 + len(docs) / df) if df else 0
    noetig = 2 if len(staemme) >= 3 else 1
    aus = []
    for d, k in zip(docs, klein):
        da = [st for st in staemme if gewicht[st] and st in k]
        if len(da) >= noetig:
            aus.append((sum(gewicht[st] for st in da), d))
    aus.sort(key=lambda x: (-x[0], x[1][3] or ""), reverse=False)
    return [{"ref": d[0], "titel": d[1], "antwort": d[2], "zeit": d[3]} for _, d in aus[:grenze]]


def treffer_text(liste):
    zeilen = []
    for t in liste:
        z = f"  {t['ref']} ({(t['zeit'] or '')[:10]}): {t['titel'][:110]}"
        if t["antwort"]:
            z += f"\n      → {t['antwort'][:160]}"
        zeilen.append(z)
    return "\n".join(zeilen)


def pruefung_verlangen(con, pid, text, geprueft):
    """B2422: Fragen an den Entwickler nur mit --geprueft; gibt es Treffer, muss es mindestens einen nennen."""
    liste = treffer(con, pid, text)
    g = (geprueft or "").strip()
    refs = {t["ref"].upper() for t in liste}
    genannt = {x.upper() for x in re.findall(r"\b(?:[BF]\d+|[KP]R\d+)\b", g, re.I)}
    if g and (not liste or refs & genannt):
        return liste
    if not liste:
        raise kern.AmwFehler("Erst in der AMW prüfen, ob es schon entschieden ist (Beschlüsse, beantwortete Fragen,"
                             " Regeln) – die AMW findet nichts Passendes. Dann: --geprueft \"keine Treffer\"")
    raise kern.AmwFehler("Ist das schon entschieden? Die AMW findet dazu:\n" + treffer_text(liste)
                         + "\nPasst einer, die Frage nicht stellen. Sonst --geprueft mit mindestens einem davon, z. B."
                         f" --geprueft \"{liste[0]['ref']} passt nicht, weil …\"")
