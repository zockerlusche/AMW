"""A2140 (TH163/TH164): liegt ein Entwurf zu einer Konzeptänderung vor, hält die AMW die nicht begonnenen Pakete an, die er ändert oder
verwirft – bis zum Ja, auch ohne Lead. Laufende bauen zu Ende; eine neue Textfassung allein hält nichts an.

Angehalten heißt: ein eigener Wartegrund „das Ja zur Änderung TH12“ an der Aufgabe, mehr nicht. Status, Zustand eines Headless-Pakets
und alle anderen Wartegründe bleiben, wie sie sind – deshalb ist beim Lösen nichts zurückzustellen. Verteilen und „nächster Schritt“
lassen solche Pakete aus, der Wächter startet sie nicht (Regel 15), von Hand startet sie nur der Mensch. Den Grund aufheben kann der
Lead, der Co-Entwickler oder der Mensch: amw aufgabe wartet <nr> --erledigt "Änderung TH12".

abgleichen() vergleicht, was der offene Entwurf nennt, mit dem, was angehalten ist. Frei werden die Pakete so mit dem Ja (verworfene sind
dann verworfen), mit „gilt weiter“, mit „nichts zu bauen“ und mit einem neuen Entwurf, der sie nicht mehr nennt. Ein zurückgestellter
Entwurf (A2118) ist offen und hält weiter an; ein neuer Planer-Lauf, der scheitert, ändert nichts. Was von Hand gelöst ist, hält
derselbe Entwurf nicht noch einmal an.

Ereignisse, kein Schema:
  delta_angehalten  {"thema", "entwurf", "pakete": [neu angehalten], "weiter": [schon vom vorigen Entwurf angehalten]}
  delta_frei        {"thema", "entwurf", "pakete": [wieder frei], "verworfen": [mit dem Ja verworfen], "warum": "ja|gilt|nichts|neu"}
"""
import json
import re

from . import db, kern

ANGEHALTEN, FREI = "delta_angehalten", "delta_frei"
_BEZUG = re.compile(r"(?:das Ja zur )?Änderung TH(\d+)", re.IGNORECASE)


def bezug(tid):
    return f"das Ja zur Änderung TH{int(tid)}"


def _thema_aus(text):
    m = _BEZUG.fullmatch(" ".join((text or "").split()))
    return int(m.group(1)) if m else None


def lesen(text):
    """„Änderung TH12“ oder der ganze Bezug → ("monitor", Bezug) – sonst None."""
    t = _thema_aus(text)
    return ("monitor", bezug(t)) if t is not None else None


def ist(art, bezug_):
    return art == "monitor" and lesen(bezug_) is not None


def haelt(con, aid):
    """Worauf das Paket wartet („das Ja zur Änderung TH12“) – oder None."""
    for r in con.execute("SELECT art, bezug FROM wartegrund WHERE aufgabe_id = ? AND erledigt_utc IS NULL AND art = 'monitor' ORDER BY id", (aid,)):
        if ist(r["art"], r["bezug"]):
            return r["bezug"]
    return None


def gehalten(con, pid):
    """{Aufgabe: {Thema}} – was gerade angehalten ist."""
    aus = {}
    for r in con.execute("SELECT aufgabe_id, art, bezug FROM wartegrund WHERE projekt_id = ? AND erledigt_utc IS NULL AND art = 'monitor'", (pid,)):
        t = _thema_aus(r["bezug"])
        if t is not None:
            aus.setdefault(r["aufgabe_id"], set()).add(t)
    return aus


def darf_starten(con, von, aid):
    """Start von Hand: ein angehaltenes Paket startet nur der Mensch. Text oder None."""
    g = haelt(con, aid) if von != kern.ENTWICKLER else None
    return (f"A{aid} wartet auf {g} – es startet danach von selbst wieder mit. Den Grund aufheben können Lead, Co-Entwickler und Mensch:"
            f" amw aufgabe wartet {aid} --erledigt \"{g.removeprefix('das Ja zur ')}\"") if g else None


def _eintraege(con, pid, tid, art):
    from . import planer
    return planer._ereignisse(con, pid, tid, art)


def _gilt_weiter(con, pid, tid, e):
    """Wurde das Thema nach diesem Entwurf mit „gilt weiter“ bestätigt?"""
    from . import themen
    if any(x.get("bestaetigt") and x["id"] > e["id"] for x in themen._ereignisse(con, pid, tid) if x["art"] == themen.EREIGNIS["vorgelegt"]):
        return True
    t = con.execute("SELECT bestaetigt_utc, bestaetigt_von FROM thema WHERE id = ?", (tid,)).fetchone()      # der Mensch: nur am Thema
    return bool(t and t["bestaetigt_von"] == kern.ENTWICKLER and (t["bestaetigt_utc"] or "") >= e["zeit_utc"])


def lage(con, pid, tid):
    """(Entwurf-Ereignis, {genannte Pakete}, warum frei) – genannt ist nichts, wenn der Entwurf geklärt ist."""
    from . import planer
    alle = [e for e in _eintraege(con, pid, tid, planer.ENTWURF) if e.get("entwurf")]      # ein gescheiterter Lauf ändert nichts
    e = alle[-1] if alle else None
    d = (e or {}).get("entwurf") or {}
    if not e or not d.get("delta"):
        return e, set(), "neu"
    if any(x.get("entwurf") == e["id"] for x in _eintraege(con, pid, tid, planer.JA)):
        return e, set(), "ja"
    if planer.erledigt(con, pid, e["id"]) or planer.geklaert(con, pid, tid, e["id"]):
        return e, set(), "nichts"
    if _gilt_weiter(con, pid, tid, e):
        return e, set(), "gilt"
    return e, {int(x["paket"]) for k in ("aendern", "verwerfen") for x in d.get(k) or []}, "neu"


def _themen(con, pid, tid):
    if tid is not None:
        return [int(tid)]
    from . import planer
    aus = {t for ts in gehalten(con, pid).values() for t in ts}
    for art in (planer.ENTWURF, ANGEHALTEN):
        for r in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = ?", (pid, art)):
            try:
                d = json.loads(r["text"])
            except (TypeError, ValueError):
                continue
            if art == ANGEHALTEN or (d.get("entwurf") or {}).get("delta"):
                aus.add(int(d["thema"]))
    return sorted(aus)


def abgleichen(con, pid, tid=None):
    """Anhalten und lösen, was der Stand der Entwürfe verlangt (ein Thema oder alle). Rückgabe: Texte (leer = nichts geändert)."""
    aus = []
    for t in _themen(con, pid, tid):
        with db.schreiben(con):
            aus += _thema(con, pid, t)
    return aus


def _thema(con, pid, tid):
    from . import konzeptaenderung, planer
    e, genannt, warum = lage(con, pid, tid)
    jetzt = {a for a, ts in gehalten(con, pid).items() if tid in ts}
    frei, halt = _eintraege(con, pid, tid, FREI), _eintraege(con, pid, tid, ANGEHALTEN)
    halt = [x for x in halt if not frei or x["id"] > frei[-1]["id"]]                         # seit dem letzten Lösen
    aus = []
    weg = sorted(jetzt - genannt)
    verworfen = []
    if halt and not genannt and warum == "ja":
        verworfen = [a for a in sorted({int(x["paket"]) for x in ((e or {}).get("entwurf") or {}).get("verwerfen") or []} & {a for x in halt for a in x["pakete"] + x["weiter"]})
                     if con.execute("SELECT status FROM aufgabe WHERE id = ?", (a,)).fetchone()[0] == "verworfen"]
    if weg or verworfen:
        for a in weg:
            con.execute("UPDATE wartegrund SET erledigt_utc = ?, erledigt_durch = ? WHERE aufgabe_id = ? AND art = 'monitor' AND bezug = ?"
                        " AND erledigt_utc IS NULL", (db.jetzt(), "AMW", a, bezug(tid)))
            con.execute("UPDATE aufgabe SET geaendert_utc = ? WHERE id = ?", (db.jetzt(), a))     # der Startklar-Weckruf zählt neu
        planer._ereignis(con, pid, "AMW", FREI, tid, entwurf=e["id"] if e else None, pakete=weg, verworfen=verworfen, warum=warum)
        aus.append(f"TH{tid}: {len(weg)} wieder frei")
    if not genannt or not e:
        return aus
    schon = {a for x in halt if x.get("entwurf") == e["id"] for a in x["pakete"] + x["weiter"]}
    neu = []
    for a in sorted(genannt - jetzt - schon):
        r = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (a, pid)).fetchone()
        if r and konzeptaenderung.einteilen(con, r) == "stoppen":
            db.einfuegen(con, "wartegrund", projekt_id=pid, aufgabe_id=a, art="monitor", bezug=bezug(tid), angelegt_utc=db.jetzt(), angelegt_von="AMW")
            neu.append(a)
    weiter = sorted((genannt & jetzt) - schon)                                                # der neue Entwurf nennt sie auch
    if neu or weiter:
        planer._ereignis(con, pid, "AMW", ANGEHALTEN, tid, entwurf=e["id"], pakete=neu, weiter=weiter)
    if neu:
        aus.append(f"TH{tid}: {len(neu)} angehalten")
    return aus


def meldung(entwurf):
    """Zeilen für die Meldung an den Lead: was bis zum Ja angehalten ist und was zu Ende gebaut wird."""
    nenn = sorted({int(x["paket"]) for k in ("aendern", "verwerfen") for x in entwurf.get(k) or []})
    laeuft = sorted(int(a) for a, g in ((entwurf.get("delta") or {}).get("pakete") or {}).items() if g == "zu_ende")
    z = [f"Bis zum Ja angehalten: {', '.join(f'A{a}' for a in nenn)}"] if nenn else []
    return z + ([f"Laufende bauen zu Ende: {', '.join(f'A{a}' for a in laeuft)}"] if laeuft else [])


def verlauf_text(art, d):
    """Eine Zeile für den Verlauf – oder None (nichts zu sagen)."""
    n, th = len(d.get("pakete") or []), f"TH{d.get('thema', '?')}"
    pakete = f"{n} Paket{'e' if n != 1 else ''}"
    if art == ANGEHALTEN:
        return f"{pakete} angehalten bis zur Freigabe der Änderung {th}" if n else None
    v = len(d.get("verworfen") or [])
    teile = ([f"{pakete} wieder frei"] if n else []) + ([f"{v} verworfen"] if v else [])
    warum = {"ja": f"Änderung {th} freigegeben", "gilt": f"{th} gilt weiter", "nichts": f"{th}: nichts zu bauen"}.get(d.get("warum") or "", f"neuer Entwurf zu {th}")
    return f"{warum}, {', '.join(teile)}" if teile else None
