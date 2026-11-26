"""Zusammensetzen (A2120): alle abgenommenen Pakete – p und Fenster – per git auf den Stand von main setzen.

zusammensetzen(con, pid):
1. Abgenommen (kandidaten): p-Paket in merge_reihe, dessen jüngste Entscheidung E7 ist (Stand: ihr Kopf); Fenster-Paket, dessen
   jüngste Prüfung grün ist (Stand: genau ihr SHA – was danach auf dem Zweig liegt, kommt nicht mit).
2. Kennzeichnung (einordnen): die Riskant-Regeln nach TH167 F4 (riskant.einordnen) plus „release_main“ – das Paket berührt die
   Release-Kette oder git auf main. Trifft eine, liest der Lead: das Paket wird als „Lead liest“ markiert (plan_ereignis lead_liest)
   und kommt erst mit seinem Merge-OK ins Bündel. Alles andere nimmt die AMW selbst ab. Ein zurückgenommenes Merge-OK hält jedes
   Paket draußen. Lässt sich ein Paket nicht einordnen, liest der Lead.
3. Reihenfolge (ordnen): zuerst nach Abhängigkeiten („nach X“), dann nach Abnahmezeit. Kommt ein Vorgänger nicht mit, bleibt auch
   der Nachfolger draußen.
4. Je Paket seine Commits per cherry-pick im Bündel-Arbeitsbaum (<platz_wurzel>/buendel, neutrale git-Umgebung, keine Hooks).
   Konflikt → alles abgebrochen, der Arbeitsbaum steht wieder sauber auf main; der Befund nennt Paket, Dateien und Meldung.

A2123 (Ergänzungen des Leads): (a) ohne: Pakete, die draußen bleiben (ihre Nachfolger auch) – so setzt die Auslieferung nach einem
Konflikt ohne das Paket neu zusammen. (b) gebaut: Muster gebauter Dateien (web/inc/seite.html …) – ein Konflikt nur darin ist keiner,
die Fassung des Pakets gilt, gebaut wird danach einmal neu. (c) Versions-Commits („1.2.3: …“) in einem Paket-Zweig kommen nicht mit.
(d) Pakete mit demselben Kopf (ein Stapel) zählen einmal: das spätere ist mit drin (mit = das erste), aufgesetzt wird nur einmal.

Ergebnis ist ein Commit auf main im Bündel-Arbeitsbaum. Die Ref main, Zweige und der Projektordner bleiben, wie sie sind: auf main
kommt ein Stand erst nach Gesamtlauf über die Release-Kette (`release ausliefern`).
"""
import fnmatch
import heapq
import json
import os
import re
import subprocess

from . import buendel, db, kern

RELEASE_MAIN = "release_main"
RELEASE_KETTE = ("amw/auslieferung*.py", "amw/releasetakt*.py", "amw/buendel*.py", "amw/mergeliste*.py", "amw/freigabereif*.py",
                 "amw/veroeffentlichung*.py", "amw/versionsnummer*.py", "amw/versionshinweise*.py", "amw/planautomatik*.py",
                 ".github/workflows/*", ".githooks/*")
# git auf main im Code: verändernde git-Befehle als Argument ("push") oder Befehlszeile (git push); bei mehrdeutigen nur mit main
GIT_MAIN = re.compile(r"refs/heads/main\b|--ff-only\b|[\"'](?:push|update-ref|cherry-pick|rebase)[\"']"
                      r"|\bgit\s+(?:push|merge|rebase|cherry-pick|update-ref)\b"
                      r"|[\"'](?:merge|reset|branch|checkout|switch|commit|fetch|pull)[\"'].*[\"'](?:origin/)?main[\"']")
TEXT = (".md", ".txt", ".json")                           # Doku nennt Befehle, führt sie nicht aus


# --- Abgenommene Pakete -------------------------------------------------------------------------------------------------------

def kandidaten(con, pid):
    """Abgenommene Pakete: [{id, titel, art: p|fenster, zweig, kopf, abgenommen, agent}] (Reihenfolge macht ordnen)."""
    from . import arbeitspaket, mergeliste
    aus = []
    for a in con.execute("SELECT id, titel, agent FROM aufgabe WHERE projekt_id = ? AND status NOT IN ('fertig', 'verworfen') ORDER BY id",
                         (pid,)).fetchall():
        f = arbeitspaket.lesen(con, a["id"])
        if f.get("art") == "p":
            r = con.execute("SELECT zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND aufgabe_id = ?"
                            " AND art = 'paket_entscheidung' ORDER BY id DESC LIMIT 1", (pid, a["id"])).fetchone()
            try:
                d = json.loads((r["text"] if r else None) or "{}")
            except ValueError:
                d = {}
            if f.get("zustand") != "merge_reihe" or d.get("zeile") != "E7" or not d.get("kopf"):
                continue
            stand = {"art": "p", "zweig": mergeliste.zweig(a["id"]), "kopf": d["kopf"], "abgenommen": r["zeit_utc"], "agent": a["agent"]}
        else:                                                     # buendel-*: Kopien der Übernahme, nicht der Stand des Pakets
            r = con.execute("SELECT * FROM pruefung WHERE projekt_id = ? AND aufgabe_id = ? AND zweig NOT LIKE 'buendel-%'"
                            " ORDER BY id DESC LIMIT 1", (pid, a["id"])).fetchone()
            if not r or r["ergebnis"] != "gruen":
                continue
            stand = {"art": "fenster", "zweig": r["zweig"], "kopf": r["sha"], "abgenommen": r["ergebnis_utc"] or r["angefragt_utc"],
                     "agent": a["agent"] or r["bauer"]}
        from . import buendel_auslieferung                       # A2124: Befund auf genau diesem Stand → wartet auf einen neuen
        aus.append({"id": a["id"], "titel": a["titel"], "pakettyp": f.get("pakettyp"), **stand,
                    "befund": buendel_auslieferung.befund_offen(con, pid, a["id"], stand["kopf"])})
    return aus


# --- Kennzeichnung ------------------------------------------------------------------------------------------------------------

def release_main(d):
    """Warum der Diff (riskant.aus_git) die Release-Kette oder git auf main berührt – leer = tut er nicht."""
    from . import riskant
    kette = [p for p in d["geaendert"] if riskant._passt(p, RELEASE_KETTE)]
    code = lambda p: not riskant._test(p) and not p.lower().endswith(TEXT)
    git = sorted({p for p, z in [*d["plus"], *d["minus"]] if code(p) and GIT_MAIN.search(z)})
    return riskant._teile((kette, "Release-Kette: " + ", ".join(kette[:5])), (git, "git auf main: " + ", ".join(git[:5])))


def einordnen(con, pid, repo, p):
    """[(Regel, Begründung)] – leer: die AMW nimmt das Paket selbst ab; sonst liest der Lead."""
    from . import riskant
    try:
        git = ["git", "-C", repo]
        basis = _lauf(repo, None, "merge-base", "main", p["kopf"])[1]
        d = riskant.aus_git(git, basis, p["kopf"])
        gruende = riskant.einordnen(con, pid, p["id"], d, typ=p.get("pakettyp"))
        grund = release_main(d)
    except Exception as x:                                        # noqa: BLE001 – ohne Einordnung nie automatisch
        return [("einordnung", f"nicht möglich: {type(x).__name__}: {x}"[:200])]
    return gruende + ([(RELEASE_MAIN, grund)] if grund else [])


def markieren(con, pid, aid, gruende):
    """„Lead liest“ setzen – nur beim ersten Mal; eine spätere Entscheidung des Leads (auch das Aufheben) bleibt stehen."""
    from . import riskant
    if con.execute("SELECT 1 FROM plan_ereignis WHERE aufgabe_id = ? AND art = ?", (aid, riskant.LEAD_LIEST)).fetchone():
        return
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=riskant.LEAD_LIEST, aufgabe_id=aid,
                     text=json.dumps({"an": True, "grund": "; ".join(f"{r}: {g}" for r, g in gruende)[:500]}, ensure_ascii=False))


def _abnahme(con, pid, repo, p):
    """(wer abnimmt: AMW|Lead, Gründe, Hindernis oder None)."""
    from . import betrieb
    gruende = einordnen(con, pid, repo, p)
    if any(r == RELEASE_MAIN for r, _ in gruende):
        markieren(con, pid, p["id"], gruende)
    letztes = con.execute("SELECT art FROM plan_ereignis WHERE projekt_id = ? AND aufgabe_id = ? AND art IN ('merge_ok', 'merge_ok_zurueck')"
                          " ORDER BY id DESC LIMIT 1", (pid, p["id"])).fetchone()
    hindernis = None
    if letztes and letztes["art"] == "merge_ok_zurueck":
        hindernis = "Merge-OK zurückgenommen"
    elif gruende and not betrieb.merge_ok(con, pid, p["id"], p["zweig"]):
        hindernis = "Lead liest, Merge-OK fehlt – " + "; ".join(f"{r}: {g}" for r, g in gruende)
    return ("Lead" if gruende else "AMW"), gruende, hindernis


# --- Reihenfolge --------------------------------------------------------------------------------------------------------------

def ordnen(pakete, vor, erledigt):
    """Abhängigkeit, dann Abnahmezeit, dann Nummer. vor: {id: [Vorgänger]}; erledigt: fertige Aufgaben. Rückgabe (reihe, raus) –
    raus: Pakete mit einem Vorgänger, der weder fertig noch dabei ist (auch mittelbar), oder im Kreis."""
    dabei = {p["id"]: p for p in pakete}
    offen = {i: {v for v in vor.get(i, ()) if v not in erledigt} for i in dabei}
    reihe, gesetzt = [], set()
    bereit = [(dabei[i]["abgenommen"], i) for i in dabei if not offen[i]]
    heapq.heapify(bereit)
    while bereit:
        _, i = heapq.heappop(bereit)
        reihe.append(dabei[i])
        gesetzt.add(i)
        for j in dabei:
            if i in offen[j]:
                offen[j].discard(i)
                if not offen[j]:
                    heapq.heappush(bereit, (dabei[j]["abgenommen"], j))
    raus = [{**dabei[i], "grund": "kommt nach " + ", ".join(f"A{v}" for v in sorted(offen[i])) + " (nicht fertig und nicht im Bündel)"}
            for i in dabei if i not in gesetzt]
    return reihe, raus


# --- git ----------------------------------------------------------------------------------------------------------------------

def _lauf(ordner, daten, *args, ok=(0,)):
    """git → (rc, stdout, stderr); mit daten in der neutralen Umgebung des Bündels (ohne: nur lesend im Projekt-Repo)."""
    r = subprocess.run(["git", "-C", ordner, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       stdin=subprocess.DEVNULL, timeout=600, env=buendel._umgebung(daten, ordner) if daten else None,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    aus, fehler = (r.stdout or "").strip(), (r.stderr or "").strip()
    if ok is not None and r.returncode not in ok:
        raise buendel.BuendelFehler(f"git {' '.join(args[:3])}: {(aus + ' ' + fehler).strip()[-300:]}")
    return r.returncode, aus, fehler


def _zurueck(repo, ziel, daten, basis):
    """Halben cherry-pick aufgeben; der Arbeitsbaum steht danach sauber auf basis (Unversioniertes bleibt liegen)."""
    _lauf(ziel, daten, "cherry-pick", "--abort", ok=None)         # ohne laufenden cherry-pick: Fehler, unerheblich
    buendel.baum_auf(repo, ziel, daten, basis)


VERSIONS_BETREFF = re.compile(r"\d+\.\d+\.\d+:")                # A2123 (c): Versions-Commit eines alten Stapels


def _gebaut(pfad, gebaut):
    return any(fnmatch.fnmatchcase(pfad, m) for m in gebaut)


def _aufsetzen(ziel, daten, basis, kopf, gebaut=()):
    """Die Commits basis..kopf eines Pakets einzeln aufsetzen. Rückgabe (Anzahl, None) oder (Anzahl, {dateien, meldung, commit}).
    A2123: Versions-Commits fallen weg; ein Konflikt nur in gebauten Dateien (Muster gebaut) nimmt die Fassung des Pakets."""
    _, merges, _ = _lauf(ziel, daten, "rev-list", "--min-parents=2", f"{basis}..{kopf}")
    if merges:
        return 0, {"dateien": [], "commit": merges.split()[0],
                   "meldung": f"Merge-Commit {merges.split()[0][:8]} im Paket – bitte auf main umsetzen (rebase), dann neu prüfen lassen"}
    _, commits, _ = _lauf(ziel, daten, "log", "--reverse", "--topo-order", "--format=%H %s", f"{basis}..{kopf}")
    n = 0
    for zeile in commits.splitlines():
        c, _, betreff = zeile.partition(" ")
        if not c or VERSIONS_BETREFF.match(betreff):
            continue
        rc, aus, fehler = _lauf(ziel, daten, "cherry-pick", c, ok=None)
        if rc == 0:
            n += 1
            continue
        dateien = [x for x in _lauf(ziel, daten, "diff", "--name-only", "--diff-filter=U")[1].splitlines() if x]
        if dateien and gebaut and all(_gebaut(x, gebaut) for x in dateien):     # (b): die Fassung des Pakets, später neu gebaut
            _lauf(ziel, daten, "checkout", "--theirs", "--", *dateien)
            _lauf(ziel, daten, "add", "--", *dateien)
            rc2, aus2, fehler2 = _lauf(ziel, daten, "-c", "core.editor=true", "cherry-pick", "--continue", ok=None)
            if rc2 == 0:
                n += 1
                continue
            aus, fehler = aus2, fehler2
        laeuft = _lauf(ziel, daten, "rev-parse", "--verify", "--quiet", "CHERRY_PICK_HEAD", ok=None)[0] == 0
        if laeuft and not dateien and _lauf(ziel, daten, "diff", "--quiet", "HEAD", ok=None)[0] == 0:
            _lauf(ziel, daten, "cherry-pick", "--skip")            # leer: die Änderung ist schon da
            continue
        return n, {"dateien": dateien, "commit": c, "meldung": "\n".join(x for x in (aus, fehler) if x)[:2000]}
    return n, None


# --- Zusammensetzen -----------------------------------------------------------------------------------------------------------

def zusammensetzen(con, pid, ohne=(), gebaut=(), nur=None):
    """ohne, gebaut (A2123): siehe oben; nur: nur diese Pakete (Teilmengen beim Teilen), in der Reihenfolge des Bündels. Rückgabe {"ok", "basis", "sha", "drin", "raus", "befund", "ordner"}. ok False: Konflikt – befund {"aufgabe", "titel", "art",
    "zweig", "kopf", "agent", "commit", "dateien", "meldung", "nach"}, drin ist leer, nichts gesetzt. sha None: kein Paket dabei.
    drin: Pakete in der Reihenfolge des Bündels, je mit „abnahme“ (AMW|Lead) und „gruende“; raus: je mit „grund“."""
    repo = kern.projekt_ordner(con, pid)
    if not repo:
        raise buendel.BuendelFehler("Das Projekt hat keinen Ordner (amw projekt ordner …)")
    ziel = buendel.arbeitsbaum(con, pid)
    daten = os.path.join(os.path.dirname(ziel), "buendel-daten")
    os.makedirs(daten, exist_ok=True)
    offen = buendel.offenes_buendel(con, pid)                     # ein Arbeitsbaum – nie zwei Bündel zugleich
    if offen:
        raise buendel.BuendelFehler(f"Bündel {offen['zweig']} ist noch offen (Gesamtlauf nicht zu Ende) – erst abwarten")
    _, basis, _ = _lauf(repo, daten, "rev-parse", "--verify", "refs/heads/main^{commit}")
    erledigt = {r[0] for r in con.execute("SELECT id FROM aufgabe WHERE status = 'fertig'")}
    raus, bereit = [], []
    ohne = set(ohne)
    for p in kandidaten(con, pid):
        if p["id"] in ohne:
            raus.append({**p, "grund": "bleibt draußen (Konflikt, Befund an den Bauer)"})
            continue
        if nur is not None and p["id"] not in nur:
            continue
        if p.get("befund"):                                       # A2124: der Bauer hat den Befund, ein neuer Stand nimmt es wieder mit
            raus.append({**p, "grund": f"Befund ({'Konflikt' if p['befund'] == 'konflikt' else 'Gesamtlauf rot'}) auf diesem Stand –"
                                       " wartet auf einen neuen Stand des Bauers"})
            continue
        rc, kopf, _ = _lauf(repo, daten, "rev-parse", "--verify", "--quiet", f"{p['kopf']}^{{commit}}", ok=None)
        if rc != 0:
            raus.append({**p, "grund": f"Stand {p['kopf'][:8]} liegt nicht im Projekt-Repo"})
            continue
        p = {**p, "kopf": kopf}
        if _lauf(repo, daten, "merge-base", "--is-ancestor", kopf, basis, ok=(0, 1))[0] == 0:
            raus.append({**p, "grund": "ist schon in main enthalten"})
            erledigt.add(p["id"])                                 # der Nachfolger findet ihn in main
            continue
        wer, gruende, hindernis = _abnahme(con, pid, repo, p)
        p.update(abnahme=wer, gruende=gruende)
        if hindernis:
            raus.append({**p, "grund": hindernis})
        else:
            bereit.append(p)
    reihe, fehlt = ordnen(bereit, {p["id"]: buendel._vor(con, p["id"]) for p in bereit}, erledigt)
    raus += fehlt
    ergebnis = {"ok": True, "basis": basis, "sha": None, "drin": [], "raus": raus, "befund": None, "ordner": ziel}
    if not reihe:
        return ergebnis
    buendel.baum_auf(repo, ziel, daten, basis)
    drin, koepfe = [], {}
    try:
        for p in reihe:
            if p["kopf"] in koepfe:                               # (d): ein Stapel – gleicher Stand, einmal aufgesetzt
                drin.append({**p, "mit": koepfe[p["kopf"]]})
                continue
            n, konflikt = _aufsetzen(ziel, daten, basis, p["kopf"], gebaut)
            if konflikt:
                _zurueck(repo, ziel, daten, basis)
                befund = {"aufgabe": p["id"], **{k: p[k] for k in ("titel", "art", "zweig", "kopf", "agent")}, **konflikt,
                          "nach": [x["id"] for x in drin]}
                return {**ergebnis, "ok": False, "befund": befund}
            if n:
                drin.append(p)
                koepfe[p["kopf"]] = p["id"]
            else:
                raus.append({**p, "grund": "ist schon in main enthalten (oder in einem Paket davor)"})
        sha = _lauf(ziel, daten, "rev-parse", "HEAD")[1] if drin else None
    except Exception:                                             # nie ein halbes Bündel liegen lassen
        _zurueck(repo, ziel, daten, basis)
        raise
    return {**ergebnis, "drin": drin, "sha": sha}
