"""„freigabereif“ von selbst (A1897, Befund Marcel 21.11. ~09:40: „es arbeitet keiner“): Endet ein Gesamtlauf grün auf genau
dem Stand einer grünen Prüfung ohne Merge-OK, meldet die AMW dem Prüfer „A<n> freigabereif …“ (weckt) und dem Bauer zur Info.
Bisher meldete sie ein Lauf-Ende nur, wenn vorher jemand „aufgabe wartet --auf L<nr>“ gesetzt hatte – ein Gebot statt eines
Automatismus: der Lead wartete auf den Coder, der Coder auf das Merge-OK.

- Gesamtlauf = Beschreibung enthält „Gesamtlauf“ oder der Befehl enthält den gesamtlauf_befehl des Projekts.
- Stand = „Stand <sha> sauber“ im Ergebnis des Laufs (dasselbe Merkmal, an dem die Release-Kette den Lauf erkennt).
- Rot (rc ≠ 0) → „Gesamtlauf rot“ an Prüfer und Bauer der Prüfungen auf diesem Stand.
- Kommt die grüne Prüfung erst nach dem grünen Lauf, gilt dieselbe Meldung beim Grün-Setzen.
- Eine Meldung je Prüfung und Stand (plan_ereignis „freigabereif“ bzw. „gesamtlauf_rot“), keine Doppelungen.
"""
import json
import re

from . import db, kern

STAND = re.compile(r"Stand ([0-9a-f]{40}) sauber")


def _gesamtlauf_befehl(con, pid):
    try:
        from . import buendel
        return buendel.einstellungen(con, pid)["gesamtlauf_befehl"]
    except kern.AmwFehler:
        return None


def ist_gesamtlauf(con, pid, l):
    if "gesamtlauf" in (l["beschreibung"] or "").lower():
        return True
    b = _gesamtlauf_befehl(con, pid)
    try:
        befehl = " ".join(json.loads(l["befehl"] or "[]"))
    except (ValueError, TypeError):
        befehl = str(l["befehl"] or "")
    return bool(b) and b in befehl


def stand(l):
    """Der sauber geprüfte Stand eines Laufs (voller SHA) oder None."""
    m = STAND.search(l["ergebnis"] or "")
    return m.group(1) if m else None


def _schon(con, pid, art, schluessel):
    return con.execute("SELECT 1 FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND text = ?", (pid, art, schluessel)).fetchone()


def _pruefungen(con, pid, sha, ergebnisse=("gruen",)):
    """Je Aufgabe die neueste Prüfung auf genau diesem Stand (SHA voll oder ≥7 Zeichen als Anfang)."""
    aus, gesehen = [], set()
    for p in con.execute(f"SELECT * FROM pruefung WHERE projekt_id = ? AND ergebnis IN ({','.join('?' * len(ergebnisse))})"
                         " ORDER BY id DESC", (pid, *ergebnisse)).fetchall():
        s = p["sha"] or ""
        if len(s) < 7 or not sha.startswith(s) or p["aufgabe_id"] in gesehen:
            continue
        gesehen.add(p["aufgabe_id"])
        aus.append(p)
    return aus


def _freigabereif(con, pid, p, lid, sha):
    from . import betrieb
    if not p["aufgabe_id"] or betrieb.merge_ok(con, pid, p["aufgabe_id"], p["zweig"]):
        return None
    schluessel = f"P{p['id']}:{sha}"
    if _schon(con, pid, "freigabereif", schluessel):
        return None
    kurz = (f"A{p['aufgabe_id']} freigabereif: P{p['id']} grün, Gesamtlauf L{lid} grün auf genau {sha[:8]} – Merge-OK: amw freigabe"
            f" merge {p['aufgabe_id']} --zweig {p['zweig']}")
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art="freigabereif", aufgabe_id=p["aufgabe_id"],
                     text=schluessel)
        kern._posten(con, pid, "AMW", p["pruefer"], "meldung", kurz[:200], kurz, aufgabe_id=p["aufgabe_id"])
        if p["bauer"] and p["bauer"] not in (p["pruefer"], "AMW"):
            kern._posten(con, pid, "AMW", p["bauer"], "info", kurz[:200], "Zur Info – das Merge-OK gibt der Prüfer.", aufgabe_id=p["aufgabe_id"])
    return kurz


def nach_lauf(con, pid, lid):
    """Nach dem Ende eines Laufs (betrieb.lauf_ende): freigabereif bzw. Gesamtlauf rot. Rückgabe: Texte."""
    l = con.execute("SELECT * FROM lauf WHERE id = ? AND projekt_id = ?", (lid, pid)).fetchone()
    if not l or l["status"] != "fertig" or not ist_gesamtlauf(con, pid, l):
        return []
    sha = stand(l)
    if not sha:
        return []
    if l["rc"] == 0:
        return [t for t in (_freigabereif(con, pid, p, lid, sha) for p in _pruefungen(con, pid, sha)) if t]
    aus = []
    for p in _pruefungen(con, pid, sha, ("gruen", "offen")):
        schluessel = f"P{p['id']}:{sha}:L{lid}"
        if not p["aufgabe_id"] or _schon(con, pid, "gesamtlauf_rot", schluessel):
            continue
        kurz = f"A{p['aufgabe_id']}: Gesamtlauf L{lid} rot (rc {l['rc']}) auf {sha[:8]} – kein Merge"
        with db.schreiben(con):
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art="gesamtlauf_rot",
                         aufgabe_id=p["aufgabe_id"], text=schluessel)
            an = ",".join(dict.fromkeys(x for x in (p["pruefer"], p["bauer"]) if x and x != "AMW"))
            if an:
                kern._posten(con, pid, "AMW", an, "meldung", kurz[:200], f"{kurz}. Ergebnis: {(l['ergebnis'] or '')[:300]}",
                             aufgabe_id=p["aufgabe_id"])
        aus.append(kurz)
    return aus


def nach_gruen(con, pid, prid):
    """Nach dem Grün-Setzen einer Prüfung (betrieb.pruefung_ergebnis): gibt es schon einen grünen Gesamtlauf auf genau diesem
    Stand, dieselbe Meldung „freigabereif“. Rückgabe: Text oder None."""
    p = con.execute("SELECT * FROM pruefung WHERE id = ? AND projekt_id = ?", (prid, pid)).fetchone()
    if not p or p["ergebnis"] != "gruen" or len(p["sha"] or "") < 7:
        return None
    for l in con.execute("SELECT * FROM lauf WHERE projekt_id = ? AND status = 'fertig' AND rc = 0 AND ergebnis LIKE ? ORDER BY id DESC",
                         (pid, f"%Stand {p['sha'][:7]}%sauber%")).fetchall():
        sha = stand(l)
        if sha and sha.startswith(p["sha"]) and ist_gesamtlauf(con, pid, l):
            return _freigabereif(con, pid, p, l["id"], sha)
    return None
