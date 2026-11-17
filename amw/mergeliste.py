"""Liste „bereit zum Merge“ mit einer Freigabe über alle (A1858, M50 S6b; D1258 v17 §6 Schritt 5 und §6a.5, D1270 Nr. 37,
Marcel F5348/B2900/W2382, TL #29096).

- liste(): je p-Paket in `merge_reihe` den Stand aus Prüfung C (Kopf im Prüf-Repo des Platzes, Basis aus dem Belegungs-Vermerk),
  `diff --stat` und den gekürzten Diff, Online-Server-Code (web/*.php), ob der Prüfer laut `merge_blick` hineinsehen muss, und
  Treffer nach außen (bei `merge_aussen_pruefung = aus` nur als Hinweis – mit „an“ hätte C das Paket schon angehalten).
- freigeben(): eine Freigabe über alle (oder die genannten) Pakete. Je Paket holt die AMW genau den einen Ref `paket-A<nr>` aus
  ihrem Prüf-Repo ins Projekt-Repo (git fetch mit neutraler Konfiguration, ohne Hooks – es wird nichts ausgeführt), vermerkt die
  Prüfung als „Prüfung C (AMW) + Freigabe <wer>“ (GRÜN auf genau diesen Kopf, nie ein eigenes Urteil des Prüfers) und das Merge-OK.
  Damit liefert die Kette wie heute aus, und A1875 (jede Aufgabe im Stand GRÜN) greift unverändert.
- ausgeliefert(): nach der Auslieferung (planautomatik.ausgeliefert) `merge_reihe → gemergt → fertig` und den Platz zurücksetzen
  (Archiv, nichts gelöscht).

Gebündelt (Pakete aufeinander, Versions-Commit, CHANGELOG) wird in Stufe 1 von Hand aus den Zweigen `paket-A<nr>` (TL #29096 F2)."""
import fnmatch
import json
import subprocess

from . import kern

DIFF_ZEILEN = 200                                   # gekürzter Diff je Paket in der Liste
SERVER = ("web/*.php",)                             # Online-Server-Code (fnmatch: * schließt Unterordner ein)
# feste Prüfliste für den Blick des Prüfers (§6a.5)
PRUEFLISTE = ("neue Endpunkte und deren Anmeldung/Rechte", "Aufrufe nach außen", "exec/eval/shell", "Datei- und DB-Zugriffe",
              "welche Daten ausgegeben werden")


def zweig(aid):
    return f"paket-A{aid}"


def _kopf(con, pid, aid):
    """Kopf aus der jüngsten Entscheidung des Pakets – nur wenn sie E7 („alles grün“) war."""
    r = con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND aufgabe_id = ? AND art = 'paket_entscheidung'"
                    " ORDER BY id DESC LIMIT 1", (pid, aid)).fetchone()
    try:
        d = json.loads((r[0] if r else None) or "{}")
    except ValueError:
        return None
    return d.get("kopf") if d.get("zeile") == "E7" else None


def _platz(con, pid, aid):
    """(Platz, Basis) aus dem Belegungs-Vermerk des Disponenten; (None, None), wenn es keinen gibt."""
    from . import disponent, platz
    v = disponent.vermerk(con, pid, aid)
    if not v:
        return None, None
    return next((p for p in platz.plaetze(con, pid) if p["nr"] == v.get("platz")), None), v.get("basis")


def server_code(pfade):
    return sorted(x for x in pfade if any(fnmatch.fnmatchcase(x.lower(), m) for m in SERVER))


def blick_noetig(con, pid, server):
    w = kern.projekt_wahl(con, pid, "merge_blick")
    return w == "alle" or (w == "server" and bool(server))


def eintrag(con, pid, aid, diff=True):
    from . import betrieb, pruefung_c
    a = con.execute("SELECT id, titel, rang FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    kopf = _kopf(con, pid, aid)
    p, basis = _platz(con, pid, aid)
    e = {"aufgabe": aid, "titel": a["titel"] if a else "", "zweig": zweig(aid), "kopf": kopf, "basis": basis,
         "platz": p["nr"] if p else None, "stat": "", "diff": "", "gekuerzt": False, "geaendert": [], "server": [], "blick": False,
         "aussen": [], "freigegeben": bool(betrieb.merge_ok(con, pid, aid, zweig(aid))), "fehler": None}
    if not (kopf and basis and p):
        e["fehler"] = "kein Stand aus Prüfung C (Kopf, Basis oder Platz fehlt)"
        return e
    try:
        e["geaendert"] = pruefung_c.geaendert(p, basis, kopf)
        e["stat"] = pruefung_c._git(p, "diff", "--no-renames", "--stat=100", basis, kopf).rstrip()
        if diff:
            zeilen = pruefung_c._git(p, "diff", "--no-renames", basis, kopf).splitlines()
            e["gekuerzt"] = len(zeilen) > DIFF_ZEILEN
            e["diff"] = "\n".join(zeilen[:DIFF_ZEILEN])
        e["aussen"] = [f"{x}: {w}" for x, w in pruefung_c.nach_aussen(pruefung_c.zusaetze(p, basis, kopf))][:8]
    except (pruefung_c.PruefFehler, OSError, subprocess.SubprocessError) as f:
        e["fehler"] = f"Stand nicht lesbar: {f}"[:300]
    e["server"] = server_code(e["geaendert"])
    e["blick"] = blick_noetig(con, pid, e["server"])
    return e


def liste(con, pid, diff=True):
    """{"pakete": [Eintrag …] nach Rang, "merge_blick", "merge_aussen_pruefung", "pruefliste"}."""
    aids = [r[0] for r in con.execute("SELECT k.aufgabe_id FROM paket k JOIN aufgabe a ON a.id = k.aufgabe_id WHERE a.projekt_id = ?"
                                      " AND k.art = 'p' AND k.zustand = 'merge_reihe' ORDER BY a.rang IS NULL, a.rang, a.id", (pid,))]
    return {"pakete": [eintrag(con, pid, aid, diff) for aid in aids], "merge_blick": kern.projekt_wahl(con, pid, "merge_blick"),
            "merge_aussen_pruefung": kern.projekt_wahl(con, pid, "merge_aussen_pruefung"), "pruefliste": list(PRUEFLISTE)}


def darf_freigeben(con, pid, von):
    from . import entscheidung
    return von == kern.ENTWICKLER or kern.ist_lead(con, pid, von) or von == entscheidung.empfaenger(con, pid, "pruefer")


def _git_projekt(quelle, p, *args):
    from . import pruefung_c
    r = subprocess.run(["git", "-C", quelle, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       stdin=subprocess.DEVNULL, timeout=300, env=pruefung_c._umgebung(p),
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def _holen(quelle, p, e):
    """Genau den einen Ref paket-A<nr> aus dem Prüf-Repo ins Projekt-Repo – nur wenn er dort genau auf den Kopf zeigt."""
    from . import pruefung_c
    ref = f"refs/heads/{e['zweig']}"
    if pruefung_c._git(p, "rev-parse", "--verify", f"{ref}^{{commit}}").strip() != e["kopf"]:
        raise kern.AmwFehler(f"{e['zweig']} im Prüf-Repo zeigt nicht auf den Stand aus Prüfung C")
    rc, da, _ = _git_projekt(quelle, p, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if rc == 0 and da != e["kopf"]:
        raise kern.AmwFehler(f"Zweig {e['zweig']} gibt es im Projekt schon mit anderem Stand ({da[:8]}) – nichts überschrieben;"
                             " bitte den Lead")
    if rc != 0:
        rc, _, fehler = _git_projekt(quelle, p, "fetch", "-q", "--no-tags", "--no-write-fetch-head", pruefung_c.repo(p), f"{ref}:{ref}")
        if rc != 0:
            raise kern.AmwFehler(f"git fetch {e['zweig']}: {fehler[-300:]}")
    rc, da, _ = _git_projekt(quelle, p, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if da != e["kopf"]:
        raise kern.AmwFehler(f"{e['zweig']} im Projekt zeigt nicht auf {e['kopf'][:8]}")


def freigeben(con, pid, von, aids=None, blick=()):
    """Eine Freigabe über alle Pakete in merge_reihe (aids=None) oder die genannten. Pakete, die laut merge_blick einen Blick
    brauchen, nur wenn sie in `blick` stehen (der Freigebende hat hineingesehen). Rückgabe [{aufgabe, ok, text}]."""
    from . import betrieb, db
    if not darf_freigeben(con, pid, von):
        raise kern.AmwFehler("Freigeben dürfen der Prüfer der Pakete (paket_pruefer), der Lead und der Mensch")
    quelle = kern.projekt_ordner(con, pid)
    if not quelle:
        raise kern.AmwFehler("Das Projekt hat keinen Ordner (amw projekt ordner …)")
    offen = {e["aufgabe"]: e for e in liste(con, pid, diff=False)["pakete"]}
    ziel = list(offen) if aids is None else [int(a) for a in aids]
    if not ziel:
        raise kern.AmwFehler("Kein Paket ist bereit zum Merge")
    blick = {int(b) for b in blick or ()}
    aus = []
    for aid in ziel:
        e = offen.get(aid)
        if not e:
            aus.append({"aufgabe": aid, "ok": False, "text": "ist nicht bereit zum Merge"})
            continue
        if e["fehler"]:
            aus.append({"aufgabe": aid, "ok": False, "text": e["fehler"]})
            continue
        if e["freigegeben"]:
            aus.append({"aufgabe": aid, "ok": False, "text": "ist schon freigegeben"})
            continue
        if e["blick"] and aid not in blick:
            warum = f"Server-Code: {', '.join(e['server'][:3])}" if e["server"] else "Einstellung merge_blick = alle"
            aus.append({"aufgabe": aid, "ok": False, "text": f"braucht erst deinen Blick in den Diff ({warum}) – danach einzeln mit Blick"
                        " freigeben"})
            continue
        p, _ = _platz(con, pid, aid)
        try:
            _holen(quelle, p, e)
        except kern.AmwFehler as f:
            aus.append({"aufgabe": aid, "ok": False, "text": str(f)})
            continue
        text = f"Prüfung C (AMW) + Freigabe {von}" + (" mit Blick in den Diff" if aid in blick else "")
        jetzt = db.jetzt()
        with db.schreiben(con):
            db.einfuegen(con, "pruefung", projekt_id=pid, aufgabe_id=aid, zweig=e["zweig"], sha=e["kopf"], bauer="AMW", pruefer=von,
                         punkte=text, ergebnis="gruen", bemerkung=text, angefragt_utc=jetzt, ergebnis_utc=jetzt)
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=jetzt, von=von, art="merge_freigabe", aufgabe_id=aid,
                         text=json.dumps({"zweig": e["zweig"], "kopf": e["kopf"], "blick": aid in blick, "server": e["server"][:10],
                                          "aussen": e["aussen"][:8]}, ensure_ascii=False))
        weiter = betrieb.freigabe_merge(con, pid, von, aid, e["zweig"])
        aus.append({"aufgabe": aid, "ok": True, "text": f"{e['zweig']}@{e['kopf'][:8]} freigegeben – {weiter}"})
    return aus


def ausgeliefert(con, pid, aid, beleg):
    """Nach der Auslieferung: ein p-Paket in merge_reihe geht über gemergt nach fertig, der Platz wird zurückgesetzt (Archiv).
    Rückgabe: Text oder None (kein p-Paket in merge_reihe)."""
    from . import arbeitspaket, platz
    f = arbeitspaket.lesen(con, aid)
    if f.get("art") != "p" or f.get("zustand") != "merge_reihe":
        return None
    arbeitspaket.zustand_setzen(con, pid, "AMW", aid, "gemergt", grund="ausgeliefert")
    arbeitspaket.zustand_setzen(con, pid, "AMW", aid, "fertig", grund="ausgeliefert", beleg=beleg)
    p, _ = _platz(con, pid, aid)
    if not p:
        return "gemergt, fertig"
    r = platz.zuruecksetzen(p, projektordner=kern.projekt_ordner(con, pid), aufgabe=aid)
    return f"gemergt, fertig, Platz {p['nr']} frei" + (f" (Archiv {r.get('archiv')})" if r.get("archiv") else "")
