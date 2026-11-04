"""Terminplaner: Testtermine des Entwicklers (auch wöchentlich), Fristen, Schirm-Fenster (→ doc/automatismen.md).

Ein Testtermin setzt die Frist „Testbuild fertig“ (vorlauf_h vorher, Vorgabe 4 h). Ist ein Bogen verknüpft, zeigt die
Ampel, ob seine Prognose die Frist hält. Wer den Testbuild fertig hat, meldet ihn mit `amw termin bereit`; die AMW legt
die Kurzliste dazu (was seit dem letzten Test fertig wurde) und schickt alles an den Entwickler. Der Dienst erinnert
den Lead an eine Frist ohne Meldung; Push an den Entwickler 1 h vor dem Test (push.py).
Termine werden nie gelöscht, nur abgesagt (ganz oder ein Vorkommen).
"""
import time
from datetime import date, datetime, timedelta, timezone

from . import db, kern

ARTEN = ("test", "frist", "schirm", "sonstig")
VORLAUF_H = 4
VORHER_MIN = 60          # Push an den Entwickler so lange vor einem Testtermin


def _utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dt(utc):
    return datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def zeit_lesen(text):
    """Ortszeit „2026-11-06 18:00“, „06.11. 18:00“, „06.11.2026 18:00“ → UTC-Zeitstempel."""
    t = " ".join((text or "").split())
    for f in ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M"):
        try:
            return _utc(datetime.strptime(t, f).astimezone())
        except ValueError:
            pass
    try:
        d = datetime.strptime(f"{t.split(' ')[0]}{date.today().year} {t.split(' ')[1]}", "%d.%m.%Y %H:%M")
        return _utc(d.astimezone())
    except (ValueError, IndexError):
        raise kern.AmwFehler(f"Zeit „{text}“: JJJJ-MM-TT HH:MM oder TT.MM. HH:MM (Ortszeit)") from None


def lokal(utc, mit_tag=True):
    d = _dt(utc).astimezone()
    tage = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
    return (f"{tage[d.weekday()]} {d:%d.%m. %H:%M}" if mit_tag else f"{d:%H:%M}")


def _lead(con, pid, von):
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Termine planen dürfen Lead und Entwickler")


def neu(con, pid, von, titel, art, am, dauer_min=None, woechentlich=False, bis=None, vorlauf_h=None, bogen_id=None, notiz=None):
    _lead(con, pid, von)
    if art not in ARTEN:
        raise kern.AmwFehler(f"Art: {' | '.join(ARTEN)}")
    if not (titel or "").strip():
        raise kern.AmwFehler("--titel fehlt")
    if bogen_id and not con.execute("SELECT 1 FROM bogen WHERE id = ? AND projekt_id = ?", (bogen_id, pid)).fetchone():
        raise kern.AmwFehler(f"Bogen {bogen_id} gibt es nicht")
    with db.schreiben(con):
        return db.einfuegen(con, "termin", projekt_id=pid, titel=titel.strip()[:200], art=art, beginn_utc=zeit_lesen(am),
                            dauer_min=dauer_min, woechentlich=int(bool(woechentlich)), bis_datum=bis or None,
                            vorlauf_h=(vorlauf_h if vorlauf_h is not None else VORLAUF_H) if art == "test" else vorlauf_h,
                            bogen_id=bogen_id, notiz=notiz, angelegt_von=von, angelegt_utc=db.jetzt())


def aendern(con, pid, von, tid, **werte):
    _lead(con, pid, von)
    t = zeile(con, pid, tid)
    felder = {}
    for k, v in werte.items():
        if v is None:
            continue
        if k == "am":
            felder["beginn_utc"] = zeit_lesen(v)
        elif k in ("titel", "dauer_min", "bis_datum", "vorlauf_h", "bogen_id", "notiz", "woechentlich"):
            felder[k] = int(bool(v)) if k == "woechentlich" else v
        else:
            raise kern.AmwFehler(f"unbekanntes Feld {k}")
    if felder:
        with db.schreiben(con):
            con.execute(f"UPDATE termin SET {', '.join(k + ' = ?' for k in felder)} WHERE id = ?", (*felder.values(), t["id"]))
    return zeile(con, pid, tid)


def zeile(con, pid, tid):
    t = con.execute("SELECT * FROM termin WHERE id = ? AND projekt_id = ?", (tid, pid)).fetchone()
    if not t:
        raise kern.AmwFehler(f"Termin T{tid} gibt es nicht")
    return t


def absagen(con, pid, von, tid, am=None):
    """Ganzen Termin (bzw. die Serie) absagen, oder mit am nur dieses Vorkommen."""
    _lead(con, pid, von)
    t = zeile(con, pid, tid)
    with db.schreiben(con):
        if am:
            am_utc = zeit_lesen(am)
            if am_utc not in {v["am_utc"] for v in _vorkommen_eines(t, _dt(am_utc) - timedelta(minutes=1),
                                                                     _dt(am_utc) + timedelta(minutes=1))}:
                raise kern.AmwFehler(f"T{tid} hat am {am} kein Vorkommen")
            db.einfuegen(con, "termin_meldung", termin_id=tid, am_utc=am_utc, art="abgesagt", von=von, zeit_utc=db.jetzt())
        else:
            con.execute("UPDATE termin SET status = 'abgesagt' WHERE id = ?", (tid,))


def _vorkommen_eines(t, ab, bis):
    """Vorkommen (am_utc) eines Termins zwischen ab und bis (datetime, UTC)."""
    erst = _dt(t["beginn_utc"])
    if not t["woechentlich"]:
        return [{"am_utc": t["beginn_utc"]}] if ab <= erst <= bis else []
    ende = datetime.strptime(t["bis_datum"], "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1) if t["bis_datum"] else bis
    aus, d = [], erst
    if d < ab:                                   # auf die erste Woche ab „ab“ springen (Ortszeit bleibt über Sommerzeit)
        wochen = (ab - d).days // 7
        d = _woche(erst, wochen)
    while d <= min(bis, ende):
        if d >= ab:
            aus.append({"am_utc": _utc(d)})
        wochen = round((d - erst).days / 7) + 1
        d = _woche(erst, wochen)
    return aus


def _woche(erst, n):
    """erst + n Wochen in Ortszeit (18:00 bleibt 18:00, auch über die Umstellung der Uhr)."""
    lokal_erst = erst.astimezone()
    d = (lokal_erst.replace(tzinfo=None) + timedelta(weeks=n))
    return datetime.fromtimestamp(time.mktime(d.timetuple()), timezone.utc)


def vorkommen(con, pid, tage=21, ab=None, mit_vergangenen_h=0):
    """Alle Vorkommen der nächsten `tage` Tage (geplant, nicht einzeln abgesagt), zeitlich sortiert, mit Frist, Ampel
    und Meldung „bereit“."""
    ab = ab or datetime.now(timezone.utc) - timedelta(hours=mit_vergangenen_h)
    bis = ab + timedelta(days=tage, hours=mit_vergangenen_h)
    prog = None
    aus = []
    for t in con.execute("SELECT * FROM termin WHERE projekt_id = ? AND status = 'geplant'", (pid,)).fetchall():
        meld = {(m["am_utc"], m["art"]): dict(m) for m in con.execute("SELECT * FROM termin_meldung WHERE termin_id = ?", (t["id"],))}
        for v in _vorkommen_eines(t, ab, bis):
            if (v["am_utc"], "abgesagt") in meld:
                continue
            x = {"termin_id": t["id"], "titel": t["titel"], "art": t["art"], "am_utc": v["am_utc"], "dauer_min": t["dauer_min"],
                 "woechentlich": bool(t["woechentlich"]), "bogen_id": t["bogen_id"], "notiz": t["notiz"],
                 "bereit": meld.get((v["am_utc"], "bereit"))}
            if t["art"] == "test" and t["vorlauf_h"]:
                x["frist_utc"] = _utc(_dt(v["am_utc"]) - timedelta(hours=t["vorlauf_h"]))
                if t["bogen_id"]:
                    if prog is None:
                        from . import planung
                        prog = planung.prognose(con, pid, laeufe=300)
                    p = prog["boegen"].get(t["bogen_id"])
                    frist_tag = _dt(x["frist_utc"]).astimezone().date().isoformat()
                    if p and p.get("p50"):
                        x["ampel"] = "gruen" if p["p85"] <= frist_tag else "gelb" if p["p50"] <= frist_tag else "rot"
                        x["prognose"] = {"p50": p["p50"], "p85": p["p85"]}
            aus.append(x)
    return sorted(aus, key=lambda x: x["am_utc"])


def naechster_test(con, pid):
    l = [v for v in vorkommen(con, pid, tage=60) if v["art"] == "test"]
    return l[0] if l else None


def _vorkommen(con, pid, tid, am=None):
    """Das gemeinte Vorkommen: am (Ortszeit) oder das nächste (auch eines, das gerade läuft, bis 12 h danach)."""
    t = zeile(con, pid, tid)
    if am:
        am_utc = zeit_lesen(am)
        if not _vorkommen_eines(t, _dt(am_utc) - timedelta(minutes=1), _dt(am_utc) + timedelta(minutes=1)):
            raise kern.AmwFehler(f"T{tid} hat am {am} kein Vorkommen")
        return t, am_utc
    l = [v for v in vorkommen(con, pid, tage=60, mit_vergangenen_h=12) if v["termin_id"] == tid]
    if not l:
        raise kern.AmwFehler(f"T{tid} hat kein kommendes Vorkommen")
    return t, l[0]["am_utc"]


def kurzliste(con, pid, tid, am=None):
    """Was seit dem letzten Testtermin (sonst 7 Tagen) fertig wurde: Aufgaben und Merges – Grundlage für „was ist neu“."""
    t, am_utc = _vorkommen(con, pid, tid, am)
    frueher = [v["am_utc"] for v in vorkommen(con, pid, tage=60, ab=_dt(am_utc) - timedelta(days=60))
               if v["art"] == "test" and v["am_utc"] < am_utc]
    seit = frueher[-1] if frueher else _utc(_dt(am_utc) - timedelta(days=7))
    aufgaben = con.execute("SELECT id, agent, titel FROM aufgabe WHERE projekt_id = ? AND status = 'fertig' AND fertig_utc >= ?"
                           " AND fertig_utc < ? ORDER BY fertig_utc", (pid, seit, am_utc)).fetchall()
    merges = con.execute("SELECT titel, commit_sha FROM release WHERE projekt_id = ? AND art = 'merge' AND zeit_utc >= ?"
                         " AND zeit_utc < ? ORDER BY zeit_utc", (pid, seit, am_utc)).fetchall()
    z = [f"Seit {lokal(seit)}: {len(aufgaben)} Aufgaben fertig, {len(merges)} Merges"]
    z += [f"- A{a['id']} ({a['agent'] or '–'}) {a['titel'][:110]}" for a in aufgaben[:40]]
    z += [f"- Merge: {m['titel'][:110]}" + (f" ({m['commit_sha'][:8]})" if m["commit_sha"] else "") for m in merges[:20]]
    return "\n".join(z)


def bereit(con, pid, von, tid, text, am=None):
    """Testbuild fertig für dieses Vorkommen: Meldung mit „was testen“ (text) + Kurzliste an den Entwickler, Kopie an den Lead."""
    if not (text or "").strip():
        raise kern.AmwFehler("--text: was ist neu, was soll getestet werden (kurz)")
    t, am_utc = _vorkommen(con, pid, tid, am)
    if t["art"] != "test":
        raise kern.AmwFehler(f"T{tid} ist kein Testtermin")
    liste = kurzliste(con, pid, tid, am)
    with db.schreiben(con):
        if con.execute("SELECT 1 FROM termin_meldung WHERE termin_id = ? AND am_utc = ? AND art = 'bereit'", (tid, am_utc)).fetchone():
            raise kern.AmwFehler(f"Testbuild für T{tid} am {lokal(am_utc)} ist schon gemeldet")
        db.einfuegen(con, "termin_meldung", termin_id=tid, am_utc=am_utc, art="bereit", von=von, zeit_utc=db.jetzt(),
                     text=text.strip())
        an = [kern.ENTWICKLER] + [l for l in [kern.lead(con, pid)] if l and l != von]
        nid, _ = kern._posten(con, pid, von, ",".join(an), "meldung", f"Testbuild bereit für {t['titel']} ({lokal(am_utc)})",
                              f"Was testen:\n{text.strip()}\n\n{liste}")
    return nid


def runde(con, pid, jetzt=None):
    """Dienst: Frist erreicht ohne Meldung „bereit“ → einmal eine weckende Zeile an den Lead. Rückgabe: Texte fürs Log."""
    jetzt = jetzt or datetime.now(timezone.utc)
    l = kern.lead(con, pid)
    if not l:
        return []
    aus = []
    for v in vorkommen(con, pid, tage=2, ab=jetzt - timedelta(hours=24)):
        if v["art"] != "test" or not v.get("frist_utc") or v["bereit"] or not (_dt(v["frist_utc"]) <= jetzt < _dt(v["am_utc"])):
            continue
        kurz = f"Frist T{v['termin_id']} {lokal(v['am_utc'])}:"
        if con.execute("SELECT 1 FROM nachricht WHERE projekt_id = ? AND von = 'AMW' AND kurz LIKE ?", (pid, kurz + "%")).fetchone():
            continue
        with db.schreiben(con):
            kern._posten(con, pid, "AMW", l, "meldung", f"{kurz} Testbuild sollte fertig sein – noch nicht gemeldet"
                         f" ({v['titel']})", f"Melden: amw termin bereit {v['termin_id']} --text \"was neu, was testen\"")
        aus.append(kurz)
    return aus


def kontext_zeile(con, pid):
    v = naechster_test(con, pid)
    if not v:
        return None
    frist = f" – Testbuild fertig bis {lokal(v['frist_utc'])}" if v.get("frist_utc") else ""
    stand = " (gemeldet)" if v["bereit"] else ""
    return f"Nächster Testtermin T{v['termin_id']}: {v['titel']} {lokal(v['am_utc'])}{frist}{stand}"
