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
  (Archiv, nichts gelöscht) – nur, wenn das Paket ihn noch hält. Seit A2105 gibt schon E7 ihn ab: der geprüfte Kopf liegt als
  refs/amw/paket-A<nr> im Projekt-Repo, von dort liest die Liste und holt das Bündel den Zweig.

Gebündelt (Pakete aufeinander, Versions-Commit, CHANGELOG) wird in Stufe 1 von Hand aus den Zweigen `paket-A<nr>` (TL #29096 F2)."""
import fnmatch
import json
import os
import subprocess

from . import kern

DIFF_ZEILEN = 200                                   # gekürzter Diff je Paket in der Liste
SERVER = ("web/*.php",)                             # Online-Server-Code (fnmatch: * schließt Unterordner ein)
# feste Prüfliste für den Blick des Prüfers (§6a.5)
PRUEFLISTE = ("neue Endpunkte und deren Anmeldung/Rechte", "Aufrufe nach außen", "exec/eval/shell", "Datei- und DB-Zugriffe",
              "welche Daten ausgegeben werden")


def zweig(aid):
    return f"paket-A{aid}"


def gesichert(aid):
    """A1894: Ref im Projekt-Repo, unter der die AMW den Kopf eines Pakets bei E4/E6 vor dem Archivieren sichert."""
    return f"refs/amw/paket-A{aid}"


def _neutral(con, pid):
    """Pseudo-Platz nur für die neutrale git-Umgebung im Projekt-Repo (Daten unter <platz_wurzel>, nie im Projektordner)."""
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    wurzel = (json.loads((r[0] if r else None) or "{}").get("platz_wurzel") or "").strip()
    if not wurzel:
        raise kern.AmwFehler("Kein Ordner der Arbeitsplätze (platz_wurzel) – ohne ihn kein gesicherter Stand")
    return {"daten": os.path.join(wurzel, "mergeliste-daten")}


def kopf_sichern(con, pid, aid, pruef_repo, kopf):
    """A1894: den Kopf (refs/heads/paket-A<n> im Prüf-Repo bzw. Archiv) als refs/amw/paket-A<n> ins Projekt-Repo holen – nur
    dieser eine Ref, neutrale git-Umgebung, nichts ausgeführt. Rückgabe: der gesicherte Commit (muss = kopf sein)."""
    quelle = kern.projekt_ordner(con, pid)
    if not quelle:
        raise kern.AmwFehler("Das Projekt hat keinen Ordner (amw projekt ordner …)")
    p = _neutral(con, pid)
    rc, _, fehler = _git_projekt(quelle, p, "fetch", "-q", "--no-tags", "--no-write-fetch-head", pruef_repo,
                                 f"+refs/heads/{zweig(aid)}:{gesichert(aid)}")
    if rc != 0:
        raise kern.AmwFehler(f"Stand von A{aid} nicht gesichert: {fehler[-200:]}")
    rc, da, _ = _git_projekt(quelle, p, "rev-parse", "--verify", "--quiet", f"{gesichert(aid)}^{{commit}}")
    if da != kopf:
        raise kern.AmwFehler(f"gesicherter Stand von A{aid} ist {da[:8] or '–'}, nicht der Kopf {kopf[:8]}")
    return da


def _entscheidung(con, pid, aid):
    r = con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND aufgabe_id = ? AND art = 'paket_entscheidung'"
                    " ORDER BY id DESC LIMIT 1", (pid, aid)).fetchone()
    try:
        return json.loads((r[0] if r else None) or "{}")
    except ValueError:
        return {}


def annehmen(con, pid, von, aid, grund):
    """A1894: Der Lead (oder der Mensch) hat ein E4-Paket gelesen und nimmt es an (z. B. test-schreiben, Fehlalarm C/aussen):
    E7 „Lead nach E4“ mit dem gesicherten Kopf, Zustand → merge_reihe (einziger Weg dorthin aus wartet_interaktiv). Fehlt der
    gesicherte Stand (Paket vor A1894 archiviert), holt die AMW ihn einmalig aus dem Archiv der E4-Entscheidung."""
    from . import arbeitspaket, db
    grund = (grund or "").strip()
    if not grund:
        raise kern.AmwFehler("annehmen nur mit Grund (--grund: was du gelesen hast und warum es passt)")
    if not (von == kern.ENTWICKLER or kern.ist_lead(con, pid, von)):
        raise kern.AmwFehler("Ein Paket nach E4 annehmen darf der Lead oder der Mensch")
    f = arbeitspaket.lesen(con, aid)
    if f.get("art") != "p" or f.get("zustand") != "wartet_interaktiv":
        raise kern.AmwFehler(f"A{aid} ist nicht „wartet auf Lead“ (Zustand {f.get('zustand') or '–'}) – annehmen gilt nur nach E4")
    d = _entscheidung(con, pid, aid)
    wieder = d.get("zeile") == "E7" and d.get("code") == "lead_nach_e4"   # A1897 Zusatz 3: schon einmal angenommen, kurz herausgenommen
    if (d.get("zeile") != "E4" and not wieder) or not d.get("kopf"):
        raise kern.AmwFehler(f"A{aid}: die letzte Entscheidung ist {d.get('zeile') or 'keine'} – annehmen gilt nur nach E4 mit Stand aus Prüfung C")
    kopf, quelle = d["kopf"], kern.projekt_ordner(con, pid)
    rc, da, _ = _git_projekt(quelle, _neutral(con, pid), "rev-parse", "--verify", "--quiet", f"{gesichert(aid)}^{{commit}}")
    if da != kopf:
        archiv = d.get("archiv")
        repo = os.path.join(archiv, "daten", "pruefung", "repo.git") if archiv else None
        if not repo or not os.path.isdir(repo):
            raise kern.AmwFehler(f"A{aid}: kein gesicherter Stand und kein Archiv mit Prüf-Repo ({archiv or '–'}) – bitte nochmal frisch")
        kopf_sichern(con, pid, aid, repo, kopf)
    jetzt = db.jetzt()
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=jetzt, von=von, art="paket_entscheidung", aufgabe_id=aid,
                     text=json.dumps({"zeile": "E7", "code": "lead_nach_e4", "grund": grund[:300], "kopf": kopf, "quelle": "projekt",
                                      "von": von}, ensure_ascii=False))
    arbeitspaket.zustand_setzen(con, pid, von, aid, "merge_reihe", grund=f"E7 (Lead nach E4: {grund})"[:200], annahme=True)
    return {"aufgabe": aid, "kopf": kopf, "zweig": zweig(aid)}


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
    ent = _entscheidung(con, pid, aid)
    projekt = ent.get("quelle") == "projekt"                           # A1894: vom Lead nach E4 angenommen, Platz archiviert
    e = {"aufgabe": aid, "titel": a["titel"] if a else "", "zweig": zweig(aid), "kopf": kopf, "basis": basis,
         "platz": p["nr"] if p else None, "stat": "", "diff": "", "gekuerzt": False, "geaendert": [], "server": [], "blick": False,
         "aussen": [], "freigegeben": bool(betrieb.merge_ok(con, pid, aid, zweig(aid))), "fehler": None, "angenommen": projekt,
         "ohne_regression": ent.get("ohne_regression")}                # A1920
    if not (kopf and basis and (p or projekt)):
        e["fehler"] = "kein Stand aus Prüfung C (Kopf, Basis oder Platz fehlt)"
        return e
    from . import waechter
    if projekt and waechter.angenommen(con, aid):      # A2105: der Platz gehört ihm nicht mehr (dort kann ein anderes Paket laufen)
        e["platz"] = None
    if projekt:                                    # lesen aus dem Projekt-Repo (gesicherter Ref), nicht vom Platz
        quelle, neutral = kern.projekt_ordner(con, pid), _neutral(con, pid)

        def git(*args):
            rc, aus, fehler = _git_projekt(quelle, neutral, *args)
            if rc != 0:
                raise pruefung_c.PruefFehler(fehler[-200:])
            return aus + "\n"
    else:
        def git(*args):
            return pruefung_c._git(p, *args)
    try:
        zwischen = lambda n: "/__pycache__/" in "/" + n or n.endswith((".pyc", ".pyo"))
        e["geaendert"] = sorted(n for n in git("diff", "--no-renames", "--name-only", basis, kopf).splitlines() if n and not zwischen(n))
        e["stat"] = git("diff", "--no-renames", "--stat=100", basis, kopf).rstrip()
        if diff:
            zeilen = git("diff", "--no-renames", basis, kopf).splitlines()
            e["gekuerzt"] = len(zeilen) > DIFF_ZEILEN
            e["diff"] = "\n".join(zeilen[:DIFF_ZEILEN])
        zusaetze, pfad = [], None                  # wie pruefung_c.zusaetze, aber mit dem passenden Repo
        for z in git("diff", "--no-renames", "-U0", basis, kopf).splitlines():
            if z.startswith("+++ "):
                pfad = z[6:] if z.startswith("+++ b/") else None
            elif z.startswith("+") and pfad:
                zusaetze.append((pfad, z[1:]))
        e["aussen"] = [f"{x}: {w}" for x, w in pruefung_c.nach_aussen(zusaetze)][:8]
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
                       stdin=subprocess.DEVNULL, timeout=300, env=pruefung_c._umgebung(dict(p, autocrlf=pruefung_c.autocrlf_projekt(quelle))),
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


def _aus_gesichert(con, pid, quelle, e):
    """A1894: paket-A<n> im Projekt-Repo auf den gesicherten Kopf setzen – nur wenn der gesicherte Ref genau der Kopf ist und
    der Zweig fehlt oder schon darauf zeigt (nichts überschrieben)."""
    neutral = _neutral(con, pid)
    aid = e["aufgabe"]
    _, g, _ = _git_projekt(quelle, neutral, "rev-parse", "--verify", "--quiet", f"{gesichert(aid)}^{{commit}}")
    if g != e["kopf"]:
        raise kern.AmwFehler(f"gesicherter Stand von A{aid} ({g[:8] or '–'}) ist nicht der angenommene Kopf {e['kopf'][:8]}")
    rc, da, _ = _git_projekt(quelle, neutral, "rev-parse", "--verify", "--quiet", f"refs/heads/{e['zweig']}^{{commit}}")
    if rc == 0 and da != e["kopf"]:
        raise kern.AmwFehler(f"Zweig {e['zweig']} gibt es im Projekt schon mit anderem Stand ({da[:8]}) – nichts überschrieben; bitte den Lead")
    if rc != 0:
        rc, _, fehler = _git_projekt(quelle, neutral, "branch", e["zweig"], e["kopf"])
        if rc != 0:
            raise kern.AmwFehler(f"Zweig {e['zweig']}: {fehler[-200:]}")


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
            if e.get("angenommen"):                     # A1894: Zweig aus dem gesicherten Ref im Projekt-Repo
                _aus_gesichert(con, pid, quelle, e)
            else:
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
    """Nach der Auslieferung: ein p-Paket in merge_reihe geht über gemergt nach fertig, der Platz wird zurückgesetzt (Archiv) – nur,
    wenn das Paket ihn noch hält: ein angenommenes hat ihn schon abgegeben, dort kann inzwischen ein anderes laufen (A2105).
    Rückgabe: Text oder None (kein p-Paket in merge_reihe)."""
    from . import arbeitspaket, platz, waechter
    f = arbeitspaket.lesen(con, aid)
    if f.get("art") != "p" or f.get("zustand") != "merge_reihe":
        return None
    abgegeben = waechter.angenommen(con, aid)
    arbeitspaket.zustand_setzen(con, pid, "AMW", aid, "gemergt", grund="ausgeliefert")
    arbeitspaket.zustand_setzen(con, pid, "AMW", aid, "fertig", grund="ausgeliefert", beleg=beleg)
    p, _ = _platz(con, pid, aid)
    if abgegeben or not p:
        return "gemergt, fertig"
    r = platz.zuruecksetzen(p, projektordner=kern.projekt_ordner(con, pid), aufgabe=aid)
    return f"gemergt, fertig, Headless {p['nr']} frei" + (f" (Archiv {r.get('archiv')})" if r.get("archiv") else "")
