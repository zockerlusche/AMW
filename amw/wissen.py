"""Wissen und Projektführung: Wortlaut, Beschlüsse, Regeln, Notizen, Release Notes, Einstufung von Aufgaben.

Heute schreibt der TL das per SQL in den Bus (KR26); in der AMW geht es über diese Funktionen bzw. `amw`.
Regeln zeigen nur den gültigen Text; jede Regeländerung nennt den Beschluss, der sie begründet (→ doc/02 §7).
"""
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
    """Eine Zeile je Merge (→ 04: Lücke zwischen den Pushes). Version bleibt leer bis release_version."""
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
